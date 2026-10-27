"""Canonical LinkedIn approval/review/schedule state. Status is computed, never guessed."""
from __future__ import annotations
import argparse,hashlib,json,os,re,sys,tempfile
from contextlib import contextmanager,nullcontext
from datetime import date,datetime,time,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import linkedin_approval as consent
import linkedin_factcheck as news
import linkedin_personal_review as personal

REPO=Path(__file__).resolve().parent.parent
ROOT=REPO/'runtime/linkedin'
HOME=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'hermes'
JOBS=HOME/'cron/jobs.json'
JOB_IDS={'tuesday':'beb0251ed70c','wednesday':'f1b1452f18b1','thursday':'8e6048e2dfa7'}
LONDON=ZoneInfo('Europe/London')

class StateConflict(RuntimeError):pass


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def body_of(doc):
    text=doc.get('post_text') or doc.get('body') or doc.get('text')
    if not isinstance(text,str) or not text.strip():raise ValueError('single-post artifact has no body')
    return text.strip()


def personal_ok(gate,body):
    return (isinstance(gate,dict) and gate.get('available',True) is not False and
        gate.get('gate_name')=='verify-cv-facts' and gate.get('body_sha256')==consent.digest(body) and
        gate.get('verdict') in ('pass','passed','warn') and gate.get('exit_code',0)==0 and personal.scope_matches(gate,body))


def review_state(doc,body,*,db_path=None):
    approval=consent.verify_receipt(doc.get('owner_approval'),body,db_path=db_path)
    pg=doc.get('personal_fact_gate') or doc.get('fact_gate')
    n_ok,n_reason=news.provenance_ok(doc.get('news_fact_gate'),body)
    override=False
    if not n_ok and isinstance(doc.get('owner_override'),dict):
        ov=doc['owner_override']
        override=(ov.get('body_sha256')==consent.digest(body) and bool(ov.get('reason')) and
            consent.verify_receipt(doc.get('owner_approval'),body,db_path=db_path,require_override=True)['ok'])
    return {'owner_approved':bool(approval['ok'] and not doc.get('cancelled')),'historical_owner_approval':approval['ok'],'approval_detail':approval['reason'],
        'approval_message_id':doc.get('owner_approval',{}).get('hermes_message_id') if isinstance(doc.get('owner_approval'),dict) else None,
        'personal_review_passed':bool(personal_ok(pg,body)),'news_review_passed':bool(n_ok),
        'news_review_detail':n_reason,'explicit_owner_override':bool(override),
        'reviews_ready':bool(personal_ok(pg,body) and (n_ok or override) and (not doc.get('blocked') or override))}


@contextmanager
def locked(root=ROOT):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    f=(root/'.state.lock').open('a+b');f.seek(0,2)
    if f.tell()==0:f.write(b'0');f.flush()
    f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError,BlockingIOError):
        f.close();raise StateConflict('another LinkedIn state operation is active')
    try:yield
    finally:
        f.seek(0)
        if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        f.close()


def replace_bytes(path,data,expected):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if file_hash(path)!=expected:raise StateConflict('concurrent change: '+str(path))
    if path.exists() and path.read_bytes()==data:return False
    fd,temp=tempfile.mkstemp(prefix='.linkedin-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        if file_hash(path)!=expected:raise StateConflict('concurrent change before commit: '+str(path))
        os.replace(temp,path);return True
    finally:
        if Path(temp).exists():Path(temp).unlink()


def save_json(path,doc,expected):
    return replace_bytes(path,(json.dumps(doc,indent=2,ensure_ascii=False)+'\n').encode('utf-8'),expected)


def event(root,operation,path,before,after,body_sha):
    entry={'at':datetime.now(timezone.utc).isoformat(),'operation':operation,'artifact':str(path),
        'before_sha256':before,'after_sha256':after,'body_sha256':body_sha}
    with (Path(root)/'state-events.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(entry)+'\n');f.flush();os.fsync(f.fileno())


def audited_write(path,data,expected,*,root,operation,body_sha):
    path=Path(path)
    if path.exists() and path.read_bytes()==data:return False
    after=hashlib.sha256(data).hexdigest()
    # Intent is durable before changing anything. An incomplete transaction is
    # recoverable by matching the journal's before/after hashes to disk.
    event(root,operation+':intent',path,expected,after,body_sha)
    changed=replace_bytes(path,data,expected)
    if changed:event(root,operation+':committed',path,expected,after,body_sha)
    return changed


def audited_json(path,doc,expected,*,root,operation,body_sha):
    return audited_write(path,(json.dumps(doc,indent=2,ensure_ascii=False)+'\n').encode('utf-8'),expected,
        root=root,operation=operation,body_sha=body_sha)


def artifact_date(path):
    match=re.fullmatch(r'approved_(\d{8})_(tuesday|wednesday|thursday)',Path(path).parent.name)
    if not match:return None
    result=datetime.strptime(match[1],'%Y%m%d').date()
    if result.strftime('%A').lower()!=match[2]:raise ValueError('artifact date and weekday disagree')
    return result


def absolute(path):
    p=Path(path);return p.resolve() if p.is_absolute() else (REPO/p).resolve()


def load_slots(path):
    if not Path(path).exists():return {}
    doc=read(path)
    if doc.get('schema_version')==2:
        if doc.get('timezone')!='Europe/London' or not isinstance(doc.get('slots'),dict):raise ValueError('invalid canonical schedule')
        return dict(doc['slots'])
    # Legacy entries are migrated by exact dated artifact identity, never weekday guessing.
    result={}
    for day,slot in doc.items():
        if day not in JOB_IDS or not isinstance(slot,dict) or not slot.get('draft_path'):raise ValueError('unknown legacy schedule entry')
        target=artifact_date(absolute(slot['draft_path']))
        if not target or target.strftime('%A').lower()!=day:raise ValueError('legacy schedule identity is ambiguous')
        result[target.isoformat()]={**slot,'body_sha256':slot.get('body_sha256') or slot.get('confirm_token'),
            'publish_at':datetime.combine(target,time(8),LONDON).isoformat(),'legacy':True}
    return result


def job_state(day,*,jobs_path=JOBS):
    try:
        data=read(jobs_path);jobs=data if isinstance(data,list) else data.get('jobs',[])
        found=[j for j in jobs if j.get('id')==JOB_IDS[day]]
        if len(found)!=1:return {'known':False,'enabled':False,'reason':'publishing job missing or duplicated'}
        job=found[0]
        enabled=job.get('enabled') is True and not job.get('paused_at') and job.get('state') not in ('paused','completed','cancelled')
        return {'known':True,'enabled':bool(enabled),'job_id':job['id'],'next_run_at':job.get('next_run_at') if enabled else None}
    except (OSError,ValueError,KeyError):return {'known':False,'enabled':False,'reason':'publishing job unavailable'}


def published(body_sha,root=ROOT):
    p=Path(root)/'published/posts.jsonl'
    if not p.exists():return False
    return any(read_entry.get('result')=='published' and read_entry.get('body_sha256')==body_sha
        for read_entry in (json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()))


def verify_integrity(path,doc=None):
    path=Path(path);doc=read(path) if doc is None else doc;body=body_of(doc)
    frozen=path.parent/'frozen_text.txt'
    if not frozen.exists():return False,'frozen text is missing'
    if frozen.read_text(encoding='utf-8').strip()!=body:return False,'frozen text differs from current body'
    if doc.get('confirm_token')!=consent.digest(body):return False,'confirmation hash differs from current body'
    return True,'Text/hash integrity matches; owner approval and publish readiness are separate checks'


def inspect_artifact(path,*,root=ROOT,db_path=None,jobs_path=JOBS):
    path=Path(path).resolve();doc=read(path);body=body_of(doc);sha=consent.digest(body)
    review=review_state(doc,body,db_path=db_path)
    frozen=path.parent/'frozen_text.txt'
    frozen_ok=verify_integrity(path,doc)[0]
    image=absolute(doc['image_path']) if doc.get('image_path') else None
    image_ok=image is None or image.is_file()
    target=artifact_date(path);day=doc.get('day') or (target.strftime('%A').lower() if target else None)
    job=job_state(day,jobs_path=jobs_path) if day in JOB_IDS else {'known':False,'enabled':False,'reason':'no publishing weekday'}
    slots=load_slots(Path(root)/'drafts/schedule.json');slot=slots.get(target.isoformat()) if target else None
    slot_ok=False;slot_reason='no exact dated schedule slot'
    if slot:
        when=datetime.combine(target,time(8),LONDON).isoformat()
        slot_ok=(not slot.get('legacy') and absolute(slot.get('draft_path',''))==path and slot.get('body_sha256')==sha and slot.get('publish_at')==when
            and (not slot.get('image_sha256') or (image is not None and file_hash(image)==slot['image_sha256'])))
        slot_reason='exact artifact/hash/date matched' if slot_ok else 'schedule artifact/hash/time/image changed'
    identity_ok=bool(target and day==target.strftime('%A').lower())
    content_ready=bool(identity_ok and review['owner_approved'] and review['reviews_ready'] and frozen_ok and image_ok and not doc.get('cancelled'))
    is_published=published(sha,root)
    if doc.get('cancelled'):phase='CANCELLED'
    elif is_published:phase='PUBLISHED'
    elif not review['owner_approved']:phase='AWAITING_OWNER_APPROVAL'
    elif not content_ready:phase='APPROVED_BUT_BLOCKED'
    elif not job['enabled']:phase='APPROVED_READY_PAUSED'
    elif not slot_ok:phase='APPROVED_READY_UNSCHEDULED'
    else:phase='SCHEDULED'
    return {'schema_version':2,'phase':phase,'artifact':str(path),'body_sha256':sha,'body_chars':len(body),
        **review,'artifact_identity_valid':identity_ok,'text_integrity_passed':bool(frozen_ok),'image_available':image_ok,
        'content_ready':content_ready,'published':is_published,'cancelled':bool(doc.get('cancelled')),
        'target_date':target.isoformat() if target else None,'publish_at':slot.get('publish_at') if slot else None,
        'slot_matches':bool(slot_ok),'slot_detail':slot_reason,'job':job,
        'automatic_publish_armed':bool(content_ready and slot_ok and job['enabled'] and not is_published)}


def recover_news(body,old,*,root=ROOT):
    current_ok=news.provenance_ok(old,body)[0]
    sources=set((old or {}).get('sources') or [])
    matches=[]
    for path in sorted((Path(root)/'gate-runs').glob('*.json')):
        try:
            audit=read(path);gate=audit.get('gate',{})
            exact=(gate.get('gate_name')==news.GATE_NAME and gate.get('gate_version')==news.GATE_VERSION and
                gate.get('verification_complete') is True and gate.get('body_sha256')==news.sha256_text(news.post_prose(body)))
            if not exact or gate.get('verdict') not in ('pass','block') or set(gate.get('sources') or [])!=sources:continue
            hashes=gate.get('source_sha256') or {}
            if not hashes or any(not news.cached_source_text(url) or news.sha256_text(news.cached_source_text(url))!=value for url,value in hashes.items()):continue
            matches.append((str(gate.get('ran_at') or path.name),path,gate))
        except (OSError,ValueError,AttributeError):continue
    if matches:
        _,path,gate=sorted(matches,key=lambda row:row[0])[-1]
        if gate['verdict']=='block':return gate,'latest complete audited review blocks this exact content'
        return gate,'recovered audited pass: '+path.name
    if current_ok:return old,'reused current receipt'
    return old or {},'no reusable valid receipt'


def reconcile(path,*,message_id=None,root=ROOT,db_path=None,jobs_path=JOBS,personal_runner=None,news_runner=None,dry_run=False):
    path=Path(path).resolve();root=Path(root)
    with (nullcontext() if dry_run else locked(root)):
        if dry_run:personal_runner=None;news_runner=None
        before=file_hash(path);doc=read(path);body=body_of(doc)
        if doc.get('cancelled'):raise ValueError('cancelled artifact cannot be reconciled/armed')
        if message_id is None:
            approval=consent.verify_receipt(doc.get('owner_approval'),body,db_path=db_path)
        else:approval=consent.verify_message(message_id,body,db_path=db_path)
        if not approval['ok']:raise ValueError(approval['reason'])
        doc['owner_approval']=approval['receipt'];doc['approved']=True;doc['confirm_token']=consent.digest(body)
        # Persist consent before expensive/failed review, independently of its outcome.
        if not dry_run:
            audited_json(path,doc,before,root=root,operation='approval_recorded',body_sha=consent.digest(body))
            before=file_hash(path)
        doc['news_fact_gate'],recovered=recover_news(body,doc.get('news_fact_gate'),root=root)
        errors=[]
        if not news.provenance_ok(doc['news_fact_gate'],body)[0] and news_runner:
            try:doc['news_fact_gate']=news_runner(body,list(doc['news_fact_gate'].get('sources') or []))
            except Exception as exc:errors.append('news review unavailable: '+type(exc).__name__)
        if not personal_ok(doc.get('personal_fact_gate'),body) and personal_runner:
            try:doc['personal_fact_gate']=personal_runner(body,path.parent.name)
            except Exception as exc:errors.append('personal review unavailable: '+type(exc).__name__)
        if not dry_run:
            audited_json(path,doc,before,root=root,operation='reviews_reconciled',body_sha=consent.digest(body))
            frozen=path.parent/'frozen_text.txt'
            if not frozen.exists():audited_write(frozen,(body+'\n').encode('utf-8'),None,root=root,operation='text_frozen',body_sha=consent.digest(body))
            # A differing frozen text needs explicit investigation, never a silent overwrite.
            status=inspect_artifact(path,root=root,db_path=db_path,jobs_path=jobs_path)
        else:
            status=review_state(doc,body,db_path=db_path)
            status.update(phase='DRY_RUN',content_ready=bool(status['owner_approved'] and status['reviews_ready']))
        return {**status,'recovery':recovered,'review_errors':errors,'dry_run':dry_run,'publish_performed':False}


def publishing_enabled(root=ROOT):
    path=Path(root)/'publishing-policy.json'
    if not path.exists():return False
    policy=read(path)
    if policy.get('schema_version')!=1 or not isinstance(policy.get('enabled'),bool):raise ValueError('invalid publishing policy')
    return policy['enabled']


def _scheduler_update(job_id,updates,*,jobs_path=JOBS):
    # Production uses the existing scheduler's locked API. Tests must inject
    # an updater; a private fixture must never touch the real cron directory.
    if Path(jobs_path).resolve()!=JOBS.resolve():raise ValueError('private scheduler requires an explicit updater')
    sys.path.insert(0,str(HOME/'hermes-agent'))
    from cron.jobs import update_job
    return update_job(job_id,updates)


def refresh_publishing_jobs(*,root=ROOT,db_path=None,jobs_path=JOBS,now=None,updater=None):
    """Arm only the earliest verified, approved, exact future slot per weekday.

    Empty, already-published and blocked slots never create recurring noise.
    This changes scheduler readiness, never grants approval or publishes.
    """
    now=now or datetime.now(LONDON)
    if now.tzinfo is None:raise ValueError('timezone-aware scheduling time required')
    enabled=publishing_enabled(root);ready={};blocked=[]
    if enabled:
        for target,slot in sorted(load_slots(Path(root)/'drafts/schedule.json').items()):
            if datetime.fromisoformat(slot['publish_at'])<=now:continue
            path=absolute(slot['draft_path'])
            if not path.is_relative_to((Path(root)/'drafts').resolve()):raise ValueError('scheduled artifact outside canonical drafts')
            try:
                status=inspect_artifact(path,root=root,db_path=db_path,jobs_path=jobs_path)
                if status['target_date']==target and status['content_ready'] and status['slot_matches'] and not status['published']:
                    ready.setdefault(date.fromisoformat(target).strftime('%A').lower(),slot)
                else:blocked.append(target)
            except (OSError,ValueError):blocked.append(target)
    armed=[];paused=[]
    for day,job_id in JOB_IDS.items():
        job=job_state(day,jobs_path=jobs_path)
        if not job['known']:
            if day in ready:raise ValueError('publishing job missing: '+day)
            continue
        slot=ready.get(day)
        if slot:
            updates={'enabled':True,'state':'scheduled','paused_at':None,'paused_reason':None,'next_run_at':slot['publish_at']}
        elif job['enabled']:
            updates={'enabled':False,'state':'paused','paused_at':now.isoformat(),'paused_reason':'No future approved, verified exact LinkedIn slot'}
        else:continue
        if not slot or not job['enabled'] or job.get('next_run_at')!=slot['publish_at']:
            result=updater(job_id,updates) if updater else _scheduler_update(job_id,updates,jobs_path=jobs_path)
            if not result:raise ValueError('scheduler update failed: '+day)
        if slot:armed.append({'day':day,'next_run_at':slot['publish_at']})
        else:paused.append(day)
    return {'publishing_enabled':enabled,'armed':armed,'paused':paused,'blocked_slots':blocked,'publish_performed':False}


def set_publishing(enabled,*,root=ROOT,db_path=None,jobs_path=JOBS,now=None,updater=None):
    if not isinstance(enabled,bool):raise ValueError('publishing enabled must be boolean')
    with locked(root):
        path=Path(root)/'publishing-policy.json';before=file_hash(path)
        doc={'schema_version':1,'enabled':enabled,'exact_owner_approval_required':True,
             'verified_reviews_required':True,'updated_at':(now or datetime.now(LONDON)).isoformat()}
        audited_json(path,doc,before,root=root,operation='publishing_policy_changed',body_sha=None)
        return refresh_publishing_jobs(root=root,db_path=db_path,jobs_path=jobs_path,now=now,updater=updater)


def plan_slot(path,target,*,root=ROOT,db_path=None,jobs_path=JOBS,dry_run=False,now=None,updater=None):
    path=Path(path).resolve();root=Path(root);target=date.fromisoformat(str(target))
    if not path.is_relative_to((root/'drafts').resolve()):raise ValueError('schedule artifact is outside LinkedIn drafts')
    if artifact_date(path)!=target:raise ValueError('schedule date does not match artifact identity')
    with (nullcontext() if dry_run else locked(root)):
        artifact_before=file_hash(path)
        status=inspect_artifact(path,root=root,db_path=db_path,jobs_path=jobs_path)
        if not status['content_ready'] or status['published']:raise ValueError('only verified, owner-approved, unpublished content can be planned')
        sched=root/'drafts/schedule.json';before=file_hash(sched);slots=load_slots(sched);doc=read(path)
        image=absolute(doc['image_path']) if doc.get('image_path') else None
        value={'draft_path':str(path),'body_sha256':status['body_sha256'],
            'image_sha256':file_hash(image) if image else None,'publish_at':datetime.combine(target,time(8),LONDON).isoformat()}
        prior=slots.get(target.isoformat())
        if prior and (absolute(prior['draft_path'])!=path or (prior.get('body_sha256')!=status['body_sha256'] and published(prior.get('body_sha256'),root))):
            raise StateConflict('another post already occupies this exact date')
        slots[target.isoformat()]=value
        result={'schema_version':2,'timezone':'Europe/London','slots':slots}
        if file_hash(path)!=artifact_before:raise StateConflict('artifact changed while planning exact slot')
        if not dry_run:audited_json(sched,result,before,root=root,operation='slot_planned',body_sha=status['body_sha256'])
        armed=refresh_publishing_jobs(root=root,db_path=db_path,jobs_path=jobs_path,now=now,updater=updater) if not dry_run and publishing_enabled(root) else None
        return {'planned':True,'slot':value,'dry_run':dry_run,'job_enablement_changed':bool(armed and armed['armed']),'publishing':armed,'job':job_state(target.strftime('%A').lower(),jobs_path=jobs_path),'publish_performed':False}


def capture(body,target,message_id,*,sources=(),image=None,replace=False,root=ROOT,db_path=None,dry_run=False):
    root=Path(root);target=date.fromisoformat(str(target));day=target.strftime('%A').lower()
    if day not in JOB_IDS:raise ValueError('scheduled capture supports Tuesday/Wednesday/Thursday only')
    body=body.strip();approval=consent.verify_message(message_id,body,db_path=db_path)
    if not approval['ok']:raise ValueError(approval['reason'])
    path=root/'drafts'/f'approved_{target:%Y%m%d}_{day}'/'linkedin_drafts.json'
    with (nullcontext() if dry_run else locked(root)):
        before=file_hash(path);prior=read(path) if path.exists() else None
        if prior and prior.get('cancelled'):raise ValueError('cancelled artifact cannot be replaced implicitly')
        changed=prior is not None and body_of(prior)!=body
        if changed and not replace:raise StateConflict('existing body differs; explicit replacement with fresh exact approval required')
        if prior and published(consent.digest(body_of(prior)),root):raise ValueError('published artifact cannot be replaced')
        if image is not None:
            asset=Path(image).resolve()
            if not asset.is_relative_to(path.parent.resolve()) or asset.suffix.lower() not in ('.jpg','.jpeg','.png','.webp') or not asset.is_file():
                raise ValueError('image must be an existing image asset inside this artifact directory')
        if prior and not changed:
            doc=dict(prior)
        else:
            doc={'schema_version':2,'post_text':body,'day':day,'news_fact_gate':{'sources':list(sources)},'personal_fact_gate':{}}
        doc.update(owner_approval=approval['receipt'],approved=True,confirm_token=consent.digest(body))
        if image is not None:doc['image_path']=str(Path(image).resolve())
        elif prior and prior.get('image_path'):doc['image_path']=prior['image_path']
        if not dry_run:
            if changed:
                version=path.parent/'.versions'/consent.digest(body_of(prior))
                for old in [path,path.parent/'frozen_text.txt']:
                    if old.exists():
                        dest=version/old.name
                        if dest.exists() and dest.read_bytes()!=old.read_bytes():raise StateConflict('historical version differs; refused overwrite')
                        if not dest.exists():audited_write(dest,old.read_bytes(),None,root=root,operation='version_preserved',body_sha=consent.digest(body_of(prior)))
            audited_json(path,doc,before,root=root,operation='approved_body_captured',body_sha=consent.digest(body))
            frozen=path.parent/'frozen_text.txt'
            audited_write(frozen,(body+'\n').encode('utf-8'),file_hash(frozen),root=root,operation='approved_text_frozen',body_sha=consent.digest(body))
        return {'captured':True,'artifact':str(path),'body_sha256':consent.digest(body),'owner_approved':True,
            'dry_run':dry_run,'publish_performed':False,'job_enablement_changed':False}


def cancel_artifact(path,reason,*,root=ROOT):
    path=Path(path).resolve();root=Path(root)
    with locked(root):
        before=file_hash(path);doc=read(path);body=body_of(doc)
        if published(consent.digest(body),root):raise ValueError('already published; cancellation cannot unpublish it')
        doc.update(cancelled=True,cancelled_reason=reason or 'owner cancelled')
        doc.setdefault('cancelled_at',datetime.now(timezone.utc).isoformat())
        audited_json(path,doc,before,root=root,operation='cancelled',body_sha=consent.digest(body))
        sched=root/'drafts/schedule.json';before=file_hash(sched);slots=load_slots(sched)
        kept={key:value for key,value in slots.items() if absolute(value['draft_path'])!=path}
        if len(kept)!=len(slots):audited_json(sched,{'schema_version':2,'timezone':'Europe/London','slots':kept},before,root=root,operation='cancelled_slot_removed',body_sha=consent.digest(body))
        return {'cancelled':True,'historical_approval_preserved':True,'publish_performed':False}


def _personal_runner(body,label):
    import cv_workflow as cvw
    import uuid
    cfg=cvw.load_config(REPO/'career-ops/cv_workflow_config.json')
    cfg={**cfg,'renderer':{**cfg.get('renderer',{}),'timeout_s':30}}
    return personal.review(cfg,body,label=label,scratch=ROOT/'.gate-scratch'/('state-'+uuid.uuid4().hex))


def week_status(week_of=None,*,root=ROOT,db_path=None,jobs_path=JOBS):
    today=datetime.now(LONDON).date()
    monday=date.fromisoformat(week_of) if week_of else today+timedelta(days=(7-today.weekday())%7)
    if monday.weekday()!=0:raise ValueError('week-of must be a Monday')
    days=[]
    for offset,day in [(1,'tuesday'),(2,'wednesday'),(3,'thursday')]:
        target=monday+timedelta(days=offset);path=Path(root)/'drafts'/f'approved_{target:%Y%m%d}_{day}'/'linkedin_drafts.json'
        if path.is_file():
            row=inspect_artifact(path,root=root,db_path=db_path,jobs_path=jobs_path)
            row['post_text']=body_of(read(path))
        else:row={'phase':'NO_ARTIFACT','owner_approved':None,'approval_detail':'No canonical artifact; chat drafts or chat approvals are not inferred.','automatic_publish_armed':False,'job':job_state(day,jobs_path=jobs_path)}
        days.append({'day':day,'date':target.isoformat(),**row})
    count=sum(row['automatic_publish_armed'] for row in days)
    return {'week_of':monday.isoformat(),'timezone':'Europe/London','days':days,'automatic_posts_armed':count,
        'summary':f'{count} automatic posts armed; '+str(sum(row.get('owner_approved') is True for row in days))+' owner-approved artifact(s)',
        'network_calls':0,'writes':0}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ['status','reconcile','plan','cancel']:
        p=sub.add_parser(command);p.add_argument('--drafts',required=True)
        if command in ('reconcile','plan','cancel'):p.add_argument('--dry-run',action='store_true')
        if command=='reconcile':
            p.add_argument('--approve-message-id',type=int);p.add_argument('--refresh-news',action='store_true')
        if command=='plan':p.add_argument('--date',required=True)
        if command=='cancel':p.add_argument('--reason',default='owner cancelled')
    p=sub.add_parser('capture');p.add_argument('--text-file',required=True);p.add_argument('--date',required=True);p.add_argument('--approve-message-id',required=True,type=int)
    p.add_argument('--source-url',action='append',default=[]);p.add_argument('--image');p.add_argument('--replace',action='store_true');p.add_argument('--dry-run',action='store_true')
    p=sub.add_parser('publishing');p.add_argument('mode',choices=['enable','disable','status'])
    p=sub.add_parser('week');p.add_argument('--week-of')
    p=sub.add_parser('check-jobs');p.add_argument('--week-of')
    args=parser.parse_args(argv)
    try:
        if args.command=='publishing':
            result=({'publishing_enabled':publishing_enabled(),'publish_performed':False} if args.mode=='status' else set_publishing(args.mode=='enable'))
        elif args.command=='capture':result=capture(Path(args.text_file).read_text(encoding='utf-8'),args.date,args.approve_message_id,sources=args.source_url,image=args.image,replace=args.replace,dry_run=args.dry_run)
        elif args.command=='status':result=inspect_artifact(args.drafts)
        elif args.command in ('week','check-jobs'):
            result=week_status(args.week_of)
            if args.command=='check-jobs':
                result['enabled_jobs']=sum(row['job']['enabled'] for row in result['days'])
                result['blocked_enabled_jobs']=[row['day'] for row in result['days'] if row['job']['enabled'] and not row.get('automatic_publish_armed')]
                result['ok']=not result['blocked_enabled_jobs']
        elif args.command=='reconcile':
            news_runner=None
            if args.refresh_news:
                news_runner=lambda body,sources:news.verify_post(body,sources,use_llm=True,api_key=news._load_api_key())
            result=reconcile(args.drafts,message_id=args.approve_message_id,personal_runner=_personal_runner,
                news_runner=news_runner,dry_run=args.dry_run)
        elif args.command=='plan':result=plan_slot(args.drafts,args.date,dry_run=args.dry_run)
        else:
            result=({'dry_run':True,'would_cancel':str(args.drafts),'writes':0} if args.dry_run else cancel_artifact(args.drafts,args.reason))
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 1 if (args.command=='reconcile' and not result.get('content_ready')) or (args.command=='check-jobs' and not result['ok']) else 0
    except (OSError,ValueError,StateConflict) as exc:
        print(json.dumps({'ok':False,'phase':'BLOCKED','error_type':type(exc).__name__,'reason':str(exc),'publish_performed':False}));return 1


if __name__=='__main__':raise SystemExit(main())
