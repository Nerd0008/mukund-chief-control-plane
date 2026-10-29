"""Bounded existing Career Ops workflows; no invented facts, SDK paths or consent."""
from __future__ import annotations
import hashlib,json,re,sqlite3
from pathlib import Path
from datetime import datetime,timedelta,date
import linkedin_state as state


def intent(text,workflow):
    text=str(text).strip()
    if workflow=='career_search':
        if re.search(r'(?i)^(?:please |can you )?(?:fix|repair|investigate|debug|explain|write|build|create|stop|pause|disable)\b',text):return 'INVESTIGATE'
        if re.search(r'(?i)\b(?:report|status|results|last scan|what.*found|where.*jobs)\b',text):return 'SEARCH_REPORT'
        if re.search(r'(?i)^(?:please |can you )?(?:run|start|resume|find|search for)\b',text):return 'RUN_SEARCH'
        return 'QUERY'
    if workflow!='linkedin':return None
    from linkedin_conversation import interpret
    if not re.search(r'(?i)^(?:please |can you )?(?:investigate|debug|fix|repair)\b',text):
        spoken=interpret(text)
        if spoken['approved'] or spoken['skip_image'] or spoken['publish_at']:
            return 'PUBLISH_NOW' if spoken['publish_now'] else 'APPROVAL'
    if re.match(r'(?i)^(?:approved[,!. ]+)?(?:(?:please|can you|could you) )?(?:publish|post)\b.*\bnow\b',text):return 'PUBLISH_NOW'
    if re.match(r'(?i)^approve(?:d)?\b',text) or (re.match(r'(?i)^(?:perfect|yes|schedule)\b',text) and re.search(r'(?i)\bapproved\b',text)):return 'APPROVAL'
    if re.search(r'(?i)^(?:please |can you )?(?:investigate|debug|fix|repair)\b',text):return 'INVESTIGATE'
    if re.search(r'(?i)\bbuild\b.*(?:artefact|artifact)',text):return 'BUILD_ARTIFACTS'
    if re.search(r'(?i)\b(?:show|see|give|remaining|rest of)\b.*(?:posts?|drafts?|remaining|week)|show me (?:them|the remaining ones)',text):return 'SHOW_DRAFTS'
    if re.search(r'(?i)\b(?:generate|create|make)\b.*\bimages?\b',text):return 'IMAGE'
    if re.search(r'(?i)\b(?:draft|write|prepare|generate|create)\b.*\bposts?\b',text):return 'PREPARE'
    return 'STATUS'


def show(*,week_of=None,root=state.ROOT,jobs_path=state.JOBS,db_path=None):
    monday=week_of or (datetime.now(state.LONDON).date()-timedelta(days=datetime.now(state.LONDON).weekday())).isoformat()
    result=state.week_status(monday,root=root,jobs_path=jobs_path,db_path=db_path)
    return {'ok':True,'week_of':monday,'days':result['days'],'publish_performed':False,'network_calls':0,'writes':0}


def render_drafts(doc):
    lines=['Existing LinkedIn drafts — '+doc['week_of']]
    for row in doc['days']:
        if row.get('published'):
            lines.append(row['day'].title()+': already published; it will not be posted again.');continue
        labels={'AWAITING_OWNER_APPROVAL':'Ready for your review','DRAFT_BLOCKED':'Factual checks need attention','APPROVED_BUT_BLOCKED':'Approved; checks need attention','SCHEDULED':'Scheduled','NO_ARTIFACT':'No draft yet','APPROVED_READY_PAUSED':'Approved and ready','APPROVED_READY_UNSCHEDULED':'Approved; waiting for a time'}
        lines+=['',row['day'].title()+' '+row['date']+' — '+labels.get(row['phase'],'Draft status available')]
        if row.get('draft_exists'):
            lines += [row['post_text']]
            if row.get('reviews_ready') and not row.get('owner_approved'):lines+=['You can approve this in your own words, and tell me when to post or whether to skip the image.']
            elif not row.get('reviews_ready'):lines+=['You can approve the text now. Publication will wait for the factual checks.']
            elif row.get('owner_approved') and not row.get('content_ready'):lines+=['Your approval is preserved. Required image or integrity checks are incomplete; do not approve the unchanged text again.']
            if row.get('alternatives'):lines+=['Another version is preserved separately; it has not silently replaced this selected draft.']
        else:lines+=['No dated draft is available.']
    lines+=['','No image was generated, approval granted or post published by this retrieval.']
    return '\n\n'.join(lines)


def _selected(day,sha,**options):
    if day not in state.JOB_IDS:raise ValueError('day must be tuesday, wednesday or thursday')
    row=next(r for r in show(**options)['days'] if r['day']==day)
    if not row.get('draft_exists'):raise ValueError('no dated draft')
    if sha!=row['body_sha256']:raise ValueError('version mismatch: retrieve and approve the exact selected draft first')
    return row


def image(row,*,root=state.ROOT,jobs_path=state.JOBS,db_path=None,generator=None):
    path=Path(root)/'drafts'/f"approved_{date.fromisoformat(row['date']):%Y%m%d}_{row['day']}"/'linkedin_drafts.json'
    current=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
    if current['published']:return {'ok':True,'phase':'ALREADY_PUBLISHED','publish_performed':False}
    if not current['owner_approved'] or not current['reviews_ready']:raise ValueError('exact owner approval and passing reviews required before image generation')
    if current['body_sha256']!=row['body_sha256']:raise ValueError('image version mismatch')
    doc=state.read(path);before=state.file_hash(path);sha=current['body_sha256']
    asset=Path(doc['image_path']) if doc.get('image_path') else None
    if doc.get('image_body_sha256')==sha and asset and asset.is_file():return {'ok':True,'phase':'IMAGE_READY','image':str(asset),'reused':True}
    if generator is None:
        if Path(root).resolve()!=state.ROOT.resolve():raise ValueError('private fixture requires an injected image generator')
        import sys
        source=state.REPO/'exec-brain'
        if str(source) not in sys.path:sys.path.insert(0,str(source))
        import linkedin_content_gen as gen
        generator=lambda body:gen.generate_image_bytes(gen.build_image_prompt(body))
    data=generator(state.body_of(doc))
    if not data:raise ValueError('image generator returned no image')
    suffix='.png' if data.startswith(b'\x89PNG') else '.jpg'
    asset=path.parent/('image-'+sha[:16]+suffix)
    with state.locked(root):
        if state.file_hash(path)!=before:raise state.StateConflict('draft changed during image generation')
        state.audited_write(asset,data,state.file_hash(asset),root=root,operation='approved_image_generated',body_sha=sha)
        doc.update(image_path=str(asset),image_body_sha256=sha)
        state.audited_json(path,doc,before,root=root,operation='image_bound_to_approved_body',body_sha=sha)
    return {'ok':True,'phase':'IMAGE_READY','image':str(asset),'publish_performed':False}


def current_approval_message(*,db_path=None):
    from hermes_diagnostics import current_contract
    from hermes_owner_context import human_text
    contract=current_contract();key=contract.get('session_key');message=human_text(contract.get('latest_human_message',''))
    if not key or not message or contract.get('turn_origin')=='synthetic_event':raise ValueError('current authenticated owner approval message required')
    path=Path(db_path or state.HOME/'state.db')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
        rows=con.execute("SELECT m.id,m.session_id,m.content FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.role='user' AND m.platform_message_id IS NOT NULL AND s.source='discord' AND s.user_id=? ORDER BY m.id DESC LIMIT 200",(state.consent.OWNER_DISCORD_ID,)).fetchall()
    for mid,sid,content in rows:
        if hashlib.sha256(sid.encode()).hexdigest()==key and human_text(content)==message:return mid
    raise ValueError('current owner message could not be matched to authenticated Discord history')


def publish_now(row,*,root=state.ROOT,jobs_path=state.JOBS,db_path=None,runner=None):
    from hermes_diagnostics import current_contract
    from hermes_owner_context import human_text
    message=human_text(current_contract().get('latest_human_message',''))
    from linkedin_conversation import interpret
    spoken=interpret(message)
    if not spoken['approved'] or not spoken['publish_now']:raise ValueError('Tell me explicitly if you want this post published now.')
    message_id=current_approval_message(db_path=db_path)
    path=Path(root)/'drafts'/f"approved_{date.fromisoformat(row['date']):%Y%m%d}_{row['day']}"/'linkedin_drafts.json'
    status=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
    if status['published']:return {'ok':True,'phase':'ALREADY_PUBLISHED','publish_performed':False,'network_calls':0}
    if spoken.get('skip_image') and status['owner_approved'] and status['body_sha256']==row['body_sha256']:
        with state.locked(root):
            before=state.file_hash(path);doc=state.read(path)
            doc.update(image_required=False,image_path=None,image_sha256=None,image_body_sha256=None,
                       preference_message_id=message_id)
            state.audited_json(path,doc,before,root=root,operation='owner_requested_text_only_publication',body_sha=row['body_sha256'])
        status=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
    if not state.publishing_enabled(root) or not status['content_ready'] or status['body_sha256']!=row['body_sha256']:raise ValueError('enabled publishing, exact approval, reviews and required image must pass')
    if row['date']!=datetime.now(state.LONDON).date().isoformat():raise ValueError('publish-now cannot move a dated post to another day')
    import subprocess,sys
    doc=state.read(path);command=[sys.executable,str(state.REPO/'career-ops/linkedin_publish.py'),'publish','--drafts',str(path),'--approve-publish','--confirm-token',row['body_sha256'],'--max-retries','0']
    if doc.get('image_path'):command+=['--image',doc['image_path']]
    if runner is None and Path(root).resolve()!=state.ROOT.resolve():raise ValueError('private fixture requires an injected publisher')
    result=(runner or subprocess.run)(command,cwd=str(state.REPO),capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:payload=json.loads(result.stdout)
    except ValueError:payload={}
    verified=bool(result.returncode==0 and payload.get('performed') and payload.get('post_urn') and state.published(row['body_sha256'],root))
    return {'ok':verified,'phase':'PUBLISHED' if verified else 'PUBLISH_FAILED','publish_performed':verified,
        'post_urn':payload.get('post_urn') if verified else None,'child_exit_code':result.returncode,
        'blocker_category':payload.get('blocker_category'),'network_calls':payload.get('network_calls_spent')}


def linkedin(args,*,root=state.ROOT,jobs_path=state.JOBS,db_path=None,generator=None,now=None):
    now=now or datetime.now(state.LONDON)
    mode=args.get('action','show')
    if mode not in ('show','build','prepare','approve','image','plan','publish'):raise ValueError('unsupported LinkedIn action')
    opts={'root':root,'jobs_path':jobs_path,'db_path':db_path,'week_of':args.get('week_of')}
    if mode in ('show','build'):return show(**opts)  # Reviewed preparation is already an artifact; never regenerate it merely to display it.
    if mode=='prepare':
        import linkedin_weekly
        monday=args.get('week_of') or show(**opts)['week_of']
        doc=linkedin_weekly.prepare(monday,root=root)
        return {'ok':bool(doc['ok']),'preparation':show(**opts),'publish_performed':False}
    row=_selected(args.get('day'),args.get('body_sha256'),**opts)
    if row.get('published'):return {'ok':True,'phase':'ALREADY_PUBLISHED','publish_performed':False,'network_calls':0}
    if mode=='approve':
        if row['source_kind'] in ('REVIEWED_PREPARED','PREPARED'):
            source=state.read(row['artifact'])['posts'][row['day']]
        else:source=state.read(row['artifact'])
        message_id=args.get('approval_message_id') or current_approval_message(db_path=db_path)
        approval=state.consent.verify_message(message_id,row['post_text'],db_path=db_path)
        preferences=(approval.get('receipt') or {}).get('preferences') or approval.get('preferences') or {}
        skip_image=preferences.get('skip_image',False) or source.get('image_required') is False
        capture_id=message_id
        if not approval['ok']:
            existing=state.consent.verify_receipt(source.get('owner_approval'),row['post_text'],db_path=db_path)
            if not (approval.get('authenticated_owner') and existing['ok'] and
                    (preferences.get('skip_image') or preferences.get('publish_at'))):
                raise ValueError(approval['reason'])
            capture_id=existing['receipt']['hermes_message_id']
        due=datetime.fromisoformat(preferences.get('publish_at') or source['requested_publish_at']) if (preferences.get('publish_at') or source.get('requested_publish_at')) else datetime.combine(date.fromisoformat(row['date']),state.time(8),state.LONDON)
        target=due.date().isoformat()
        target_path=Path(root)/'drafts'/f"approved_{due:%Y%m%d}_{due.strftime('%A').lower()}"/'linkedin_drafts.json'
        conflict=target!=row['date'] and target_path.exists() and state.body_of(state.read(target_path))!=row['post_text']
        capture_target=row['date'] if conflict else target
        result=state.capture(row['post_text'],capture_target,capture_id,replace=(capture_target==row['date']),root=root,db_path=db_path)
        path=Path(result['artifact'])
        with state.locked(root):
            before=state.file_hash(path);doc=state.read(path)
            if state.consent.digest(state.body_of(doc))!=row['body_sha256']:raise state.StateConflict('captured version changed')
            doc.update(news_fact_gate=source.get('news_fact_gate'),personal_fact_gate=source.get('personal_fact_gate'),
                       image_required=not skip_image,requested_publish_at=due.isoformat(),
                       preference_message_id=message_id)
            # Preserve independently authenticated override consent across date/image changes.
            old_override=source.get('owner_override')
            if isinstance(old_override,dict) and old_override.get('body_sha256')==row['body_sha256']:
                old_receipt=old_override.get('receipt') or source.get('owner_approval')
                if state.consent.verify_receipt(old_receipt,row['post_text'],db_path=db_path,require_override=True)['ok']:
                    doc['owner_override']={**old_override,'receipt':old_receipt}
            if skip_image:doc.update(image_path=None,image_sha256=None,image_body_sha256=None)
            if preferences.get('override'):
                override=state.consent.verify_message(message_id,row['post_text'],db_path=db_path,require_override=True)
                if override['ok']:
                    doc['owner_override']={'approved_by':'Mukund','body_sha256':row['body_sha256'],
                        'reason':'Owner explicitly acknowledged the fact-check warning and approved this exact version despite it.',
                        'receipt':override['receipt']}
            state.audited_json(path,doc,before,root=root,operation='natural_owner_approval_and_preferences',body_sha=row['body_sha256'])
        status=state.inspect_artifact(path,root=root,jobs_path=jobs_path,db_path=db_path)
        if not status['reviews_ready']:
            return {'ok':True,'phase':'APPROVED_BUT_BLOCKED','message':'Your approval is saved. The post is held for factual review; you do not need to approve this unchanged text again.',
                    'approval':result,'publish_performed':False}
        if conflict:
            return {'ok':True,'phase':'SCHEDULE_CONFLICT','message':'Your approval is saved. Another post already has that date. Which post should use that slot?',
                    'approval':result,'publish_performed':False}
        selected={**row,'date':capture_target,'day':due.strftime('%A').lower()}
        image_result={'ok':True,'phase':'IMAGE_SKIPPED'}
        if not skip_image:
            try:image_result=image(selected,root=root,jobs_path=jobs_path,db_path=db_path,generator=generator)
            except Exception as exc:
                return {'ok':True,'phase':'APPROVED_IMAGE_BLOCKED','message':'Your approval is saved. Image generation is unavailable. You can say “skip the image”.',
                        'blocker_type':type(exc).__name__,'publish_performed':False}
        if due<=now:
            return {'ok':True,'phase':'APPROVED_READY_NEEDS_PUBLISH_INSTRUCTION','approval':result,'image':image_result,
                    'message':'Your approval is saved. That time has passed; tell me when you want it posted.','publish_performed':False}
        return {'ok':True,'approval':result,'image':image_result,
                'plan':state.plan_slot(path,capture_target,root=root,db_path=db_path,jobs_path=jobs_path),'publish_performed':False}
    if mode=='publish':return publish_now(row,root=root,jobs_path=jobs_path,db_path=db_path)
    if mode=='image':return image(row,root=root,jobs_path=jobs_path,db_path=db_path,generator=generator)
    if mode=='plan':
        path=Path(root)/'drafts'/f"approved_{date.fromisoformat(row['date']):%Y%m%d}_{row['day']}"/'linkedin_drafts.json'
        return {'ok':True,'plan':state.plan_slot(path,row['date'],root=root,db_path=db_path,jobs_path=jobs_path),'publish_performed':False}
    raise ValueError('unsupported LinkedIn action')


def search_report(*,home=state.HOME,repo=state.REPO):
    from hermes_diagnostics import latest_run
    home=Path(home);job=latest_run('5a66e1129e58',home=home);execution=job.get('execution') or {}
    phase='PAUSED' if job.get('job_enabled') is False else 'RUNNING' if execution.get('status') in ('running','claimed') else str(execution.get('status') or 'UNKNOWN').upper()
    complete=None;db=home/'cron/executions.db'
    if db.exists():
        with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as con:
            con.row_factory=sqlite3.Row
            r=con.execute("SELECT id,status,finished_at FROM executions WHERE job_id=? AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1",('5a66e1129e58',)).fetchone()
            complete=dict(r) if r else None
    prior=None
    if complete:
        finished=datetime.fromisoformat(complete['finished_at'].replace('Z','+00:00'));candidates=[]
        for p in (Path(repo)/'runtime/career-ops/job-scan-runs').glob('*.json'):
            try:stamp=datetime.strptime(p.name[:16],'%Y%m%dT%H%M%SZ').replace(tzinfo=finished.tzinfo)
            except ValueError:continue
            if abs((stamp-finished).total_seconds())<=120:candidates.append((abs((stamp-finished).total_seconds()),p))
        if candidates:
            p=min(candidates,key=lambda r:r[0])[1];d=state.read(p);coverage=d.get('coverage') or {}
            writes=[]
            for line in str(d.get('stdout') or '').splitlines():
                if line.startswith('TRACKER_WRITE_RESULT '):
                    try:v=json.loads(line.split(' ',1)[1]);writes.append({k:v.get(k) for k in ('applied','counts','verification_ok')})
                    except ValueError:pass
            prior={'execution':complete,'path':str(p),'exit_code':d.get('exit_code'),'coverage_complete':coverage.get('coverage_complete'),
                'completed_batches':coverage.get('completed_batches'),'batches_attempted':coverage.get('batches_attempted'),'verified_writer_results':writes,
                'silent_delivery':job.get('available') and not bool(job.get('structured_result'))}
    result={'schema_version':1,'workflow':'career_search','checked_at':datetime.now(state.LONDON).isoformat(),'phase':phase,'latest_execution':job,
        'last_completed_scan':prior,'network_calls':0,'writes':0,'authority':'exact scheduler execution and matching delta-run schema; missing evidence is UNKNOWN'}
    result['evidence_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest();return result


def render_search(doc):
    lines=['UK job search: '+doc['phase']+'. Checked '+doc['checked_at']+'.']
    prior=doc.get('last_completed_scan')
    if prior:lines+=['Last completed scan: '+str(prior['execution']['finished_at'])+'; exit '+str(prior['exit_code'])+'; completed batches '+str(prior['completed_batches'])+'; complete coverage '+str(prior['coverage_complete'])+'.','Verified tracker write results: '+json.dumps(prior['verified_writer_results'])+'. No new-job total is inferred from missing report fields.']
    else:lines+=['No matching completed scan artifact is available; older failures are not substituted.']
    lines+=['Evidence: '+doc['evidence_sha256'][:16]+'. This report did not start or stop a scan.']
    return '\n\n'.join(lines)


def guard(tool_name,args=None,**kwargs):
    from hermes_diagnostics import current_contract
    c=current_contract();args=args or {}
    if c.get('workflow')!='linkedin' or c.get('action') not in ('SHOW_DRAFTS','BUILD_ARTIFACTS','PREPARE','IMAGE','APPROVAL','PUBLISH_NOW'):return None
    if tool_name not in ('terminal','write_file','execute_code','python','patch'):return None
    payload=json.dumps(args).lower()
    if re.search(r'linkedin|gen_images|career_ops|pythob',payload) and (tool_name!='terminal' or re.search(r'python|gen_images|<<|powershell.*-c',payload)):
        return {'action':'block','message':'Use career_linkedin_workflow for this LinkedIn stage (show/build/prepare/image/approve/plan). It preserves exact versions, review provenance and the supported Hermes image router. Do not create scratch compilers or use the retired desktop bot. Read-only shell inspection remains available outside the bounded stage.'}
    return None
