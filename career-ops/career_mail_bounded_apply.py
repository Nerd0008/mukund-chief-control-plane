"""One report-scoped owner approval. Never enables scheduled/general Gmail writes."""
from __future__ import annotations
import copy, datetime as dt, hashlib, json, os, tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from career_mail_monitor import report_hash, atomic_json, time_key
from career_mail_parser import stable_id
from career_mail_matching import compatible
from career_mail_rules import company_key, company_aliases, role_key
from career_mail_tracker import WorkbookTracker, digest

APPROVED_REPORT='c974caa787d82e6f31176e57dbab4d725bf4ed595e673ceeaceda4c906cb339f'
CONFIRMED={'S23':('Amey','Graduate Digital Technology Consultant'), 'S24':('Menzies','Graduate Programme 2027 — Technology Risk Auditing'), 'S25':('EY','Consultant — Cyber Security Analyst — Consulting Service Delivery, FS'), 'S26':('Arup','Graduate Security Risk Consultant — London')}
REVIEW_DEADLINES={'FTI Consulting':'2026-10-08T16:21:32Z','Shell':'2026-10-10T14:40:23Z','National Highways':'2026-10-14T11:34:00Z'}

from career_tracker_layout import resolve_profiles

def validate_report(report):
    if report.get('report_id')!=APPROVED_REPORT or report_hash(report)!=APPROVED_REPORT:
        raise ValueError('owner approval is bound to a different or modified report')

def fresh_candidates(signal,records):
    ref=signal.get('application_identity')
    referenced=[r for r in records if ref and signal.get('reference_type')!='candidate' and (ref==r.get('application_identity') or ref in r.get('job_reference_ids',[]))]
    threaded=[r for r in records if signal.get('gmail_thread_id') in r.get('thread_ids',[])]
    pairs=[r for r in records if signal.get('company') and signal.get('role') and company_key(signal['company']) in company_aliases(r['company']) and role_key(signal['role'])==role_key(r['role'])]
    if referenced:return [r for r in referenced if compatible(signal,r)]
    consistent=[r for r in threaded if compatible(signal,r) and (not signal.get('role') or role_key(signal['role'])==role_key(r['role']))]
    return consistent or [r for r in pairs if compatible(signal,r)]

def merge_signal(record,signal):
    result=copy.deepcopy(record)
    mid=signal['gmail_message_id'];thread=signal['gmail_thread_id']
    duplicate=mid in result.get('seen_message_ids',[])
    if duplicate:return result,True
    protected=set(record.get('owner_confirmed_fields',[]))|{'company','role','region','application_id','row','canonical_owner_status','job_reference_ids','canonical_job_host'}
    result['seen_message_ids']=sorted(set(result.get('seen_message_ids',[]))|{mid})
    result['thread_ids']=sorted(set(result.get('thread_ids',[]))|{thread})
    if time_key(signal.get('last_update_timestamp'))>=time_key(record.get('last_update_timestamp')):
        allowed={'application_date','source_application_channel','current_stage','latest_status','assessment_type','assessment_provider','assessment_received_date','assessment_interview_link','recruiter_contact','gmail_message_id','gmail_thread_id','last_update_timestamp','application_identity','reference_type'}
        for key in allowed-protected:
            value=signal.get(key)
            if value is not None and not(key=='application_date' and result.get(key)):result[key]=value
        deadline=signal.get('deadline',{})
        if 'deadline' not in protected and deadline.get('value') and not deadline.get('needs_review'):result['deadline']=copy.deepcopy(deadline)
    for field in protected:
        if field in record and result.get(field)!=record[field]:raise ValueError('owner-confirmed field conflict')
    return result,False

def build_plan(report,records,confirmed_regions):
    validate_report(report)
    working=copy.deepcopy(records);changed={};skipped=[];duplicates=0;authorized=[]
    for signal in sorted(report['signal_analysis'],key=lambda x:time_key(x.get('last_update_timestamp'))):
        item=signal['item'];owner=item in CONFIRMED
        if not owner and signal['category']!='confident existing application match':continue
        sig=copy.deepcopy(signal)
        if owner:
            company,role=CONFIRMED[item]
            if company_key(sig.get('company'))!=company_key(company) or role_key(sig.get('role'))!=role_key(role):raise ValueError('confirmed source identity differs from owner decision')
            region=confirmed_regions.get(item)
            if region not in {'uk','dubai','japan','singapore'}:raise ValueError('owner-confirmed application region unresolved')
            sig.update(region=region)
        candidates=fresh_candidates(sig,working)
        if len(candidates)>1 or (not owner and len(candidates)!=1):
            skipped.append({'item':item,'reason':'fresh canonical match is ambiguous or absent','candidate_count':len(candidates)});continue
        if candidates:record=candidates[0]
        else:
            company,role=CONFIRMED[item]
            record={'application_id':stable_id(company,role,sig.get('application_identity') or sig['gmail_thread_id']),'company':company,'role':role,'region':sig['region'],'seen_message_ids':[],'thread_ids':[],'owner_confirmed_fields':['company','role','region'],'owner_approval_report':APPROVED_REPORT,'owner_confirmed_application':True}
            working.append(record)
        merged,duplicate=merge_signal(record,sig)
        duplicates+=int(duplicate)
        if merged!=record:changed[merged['application_id']]=merged;record.clear();record.update(merged)
        authorized.append({'item':item,'application_id':record['application_id'],'new':not bool(record.get('row')),'duplicate':duplicate})
    return {'records':list(changed.values()),'authorized':authorized,'skipped':skipped,'duplicate_signals_avoided':duplicates,'review_events':review_events(report),'remaining_review_signals':[s['item'] for s in report['signal_analysis'] if s['category'] not in {'confident existing application match','false positive / generic recruitment content'} and s['item'] not in CONFIRMED]}

def review_events(report):
    events=[]
    for company,deadline in REVIEW_DEADLINES.items():
        when=dt.datetime.fromisoformat(deadline.replace('Z','+00:00'))
        signals=[s for s in report['signal_analysis'] if s.get('company')==company and s.get('deadline',{}).get('kind')=='DERIVED' and not s['deadline'].get('needs_review') and time_key(s['deadline'].get('value'))==when.timestamp()]
        if not signals:raise ValueError('approved review deadline lacks reliable report evidence')
        key=hashlib.sha256((company+'|'+deadline).encode()).hexdigest();eid='rev'+key[:48]
        descriptions=['Application identity requires review. Confirm against the source Gmail message before acting.',f'Company: {company}',f'Derived assessment deadline: {deadline}','No canonical application association.']
        for s in signals:
            d=s['deadline'];descriptions.append(f"Source Gmail message ID: {s['gmail_message_id']}; thread ID: {s['gmail_thread_id']}; derivation source message: {d['source_message_id']}; derivation: {d.get('reason','')}")
        events.append({'id':eid,'summary':f'REVIEW — {company} — Assessment deadline','description':'\n'.join(descriptions),'start':{'dateTime':deadline},'end':{'dateTime':(when+dt.timedelta(minutes=1)).isoformat()},'reminders':{'useDefault':False,'overrides':[{'method':'popup','minutes':1440},{'method':'popup','minutes':180}]},'extendedProperties':{'private':{'careerOpsApplication':'review:'+key,'careerOpsMode':'identity-review','careerOpsSourceReport':APPROVED_REPORT}}})
    return events

@contextmanager
def exclusive_file(path):
    """Windows share=0 excludes writes AND atomic replacement during CAS/commit."""
    if os.name=='nt':
        import ctypes,msvcrt
        from ctypes import wintypes
        create=ctypes.WinDLL('kernel32',use_last_error=True).CreateFileW
        create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];create.restype=wintypes.HANDLE
        handle=create(str(path),0xC0000000,0,None,3,0x80,None)
        if handle==ctypes.c_void_p(-1).value:raise OSError('canonical workbook is busy; no write attempted')
        fd=msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY)
        with os.fdopen(fd,'r+b') as stream:yield stream
    else:
        import fcntl
        with open(path,'r+b') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:yield stream
            finally:fcntl.flock(stream,fcntl.LOCK_UN)

def stage_workbooks(plan,profiles,before,root):
    import openpyxl,shutil
    root=Path(root);root.mkdir(parents=True,exist_ok=True);staged=copy.deepcopy(profiles)
    touched={r['region'] for r in plan['records']}
    for region in touched:
        src=Path(profiles['regions'][region]['tracker']);target=root/(region+'.xlsx');shutil.copy2(src,target)
        if digest(target)!=before[region]:raise ValueError('workbook changed before staging')
        staged['regions'][region]['tracker']=str(target)
    tracker=WorkbookTracker(staged,root/'staging-backups');receipts=[]
    for record in plan['records']:
        receipts.append({'application_id':record['application_id'],'new':not bool(record.get('row')),'region':record['region'],'write':tracker.upsert(record)})
    # Owner confirmed new applications receive Applied, not To Review.
    for region in touched:
        cfg=staged['regions'][region];path=Path(cfg['tracker']);wb=openpyxl.load_workbook(path)
        from openpyxl.utils import column_index_from_string as ci
        for record in plan['records']:
            if record['region']==region and record.get('owner_confirmed_application') and any(x['application_id']==record['application_id'] and x['new'] for x in receipts):
                wb[cfg['sheet']].cell(record['row'],ci(cfg['status_columns']['application_status']),'Applied')
        wb.save(path);wb.close()
        original=openpyxl.load_workbook(profiles['regions'][region]['tracker']);updated=openpyxl.load_workbook(path)
        try:
            ws=original[cfg['sheet']];new=updated[cfg['sheet']]
            from career_mail_tracker import HEADERS
            email_columns={c.column for c in new[cfg['header_row']] if c.value in HEADERS.values()}
            added_rows={r['row'] for r in plan['records'] if r['region']==region and r.get('owner_confirmed_application') and not any(x['write']['row']==r['row'] and not x['new'] for x in receipts)}
            new_allowed={ci(cfg['id']['column']),ci(cfg['field_map']['company']),ci(cfg['field_map']['title']),ci(cfg['status_columns']['application_status'])}
            for row in ws:
                for cell in row:
                    if cell.column in email_columns:continue
                    if cell.row in added_rows and cell.column in new_allowed and cell.value is None:continue
                    if cell.value!=new[cell.coordinate].value:raise ValueError('staging would overwrite an existing canonical cell')
        finally:original.close();updated.close()
    return {region:Path(staged['regions'][region]['tracker']).read_bytes() for region in touched},receipts

def commit_staged(staged,profiles,before,calendar_events,calendar,audit_path):
    from career_google_auth import GoogleError
    audit={'state':'preflight','before_hashes':before,'workbooks':[],'calendar':[]}
    atomic_json(audit_path,audit)
    with ExitStack() as stack:
        streams={region:stack.enter_context(exclusive_file(cfg['tracker'])) for region,cfg in profiles['regions'].items() if region in before}
        for region,stream in streams.items():
            data=stream.read();stream.seek(0)
            if hashlib.sha256(data).hexdigest()!=before[region]:raise ValueError('concurrent workbook change; staged apply aborted before writes')
        # All participating workbook handles remain exclusive through calendar ACKs.
        for region,data in staged.items():
            stream=streams[region];stream.seek(0);stream.write(data);stream.truncate();stream.flush();os.fsync(stream.fileno());stream.seek(0)
            after=hashlib.sha256(stream.read()).hexdigest()
            if after!=hashlib.sha256(data).hexdigest():raise ValueError('workbook write verification failed; preserve backup')
            audit['workbooks'].append({'region':region,'before':before[region],'after':after});atomic_json(audit_path,audit)
        for event in calendar_events:
            exists=True
            try:calendar._call('GET',event['id'])
            except GoogleError as exc:
                if exc.status!=404:raise
                exists=False
            response=calendar.ensure(event)
            if response.get('id')!=event['id']:raise ValueError('calendar delivery receipt mismatch')
            check=calendar._call('GET',event['id'])
            if check.get('summary')!=event['summary'] or check.get('status')=='cancelled':raise ValueError('calendar read-back verification failed')
            audit['calendar'].append({'event_id':event['id'],'created':not exists,'verified':True});atomic_json(audit_path,audit)
        audit['state']='applied';atomic_json(audit_path,audit)
    return audit


def run_bounded(report_path,profiles_path,root,*,apply=False,calendar=None):
    import shutil
    from career_google_auth import access_token,GoogleError
    from career_google_clients import DeadlineCalendar
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    report=json.loads(Path(report_path).read_text(encoding='utf-8'));validate_report(report)
    profiles=resolve_profiles(json.loads(Path(profiles_path).read_text(encoding='utf-8')))
    tracker=WorkbookTracker(profiles,root/'backups');records,before=tracker.read()
    if any(digest(profiles['regions'][r]['tracker'])!=h for r,h in before.items()):raise ValueError('workbook changed during fresh read')
    # This one-time owner decision concerns the UK application pool; S23/S24
    # Gmail UK evidence and S26 London were verified before apply.
    plan=build_plan(report,records,{item:'uk' for item in CONFIRMED})
    atomic_json(root/'fresh-plan.json',{'approved_report':APPROVED_REPORT,'workbook_fingerprints':before,'plan':plan,'automatic_writes_enabled':False})
    summary={'status':'DRY_RUN','tracker_rows_added':0,'tracker_rows_updated':0,'calendar_events_created':0,'duplicates_avoided':plan['duplicate_signals_avoided'],'before_hashes':before,'changed_application_ids':[],'event_ids':[],'fresh_match_skips':plan['skipped'],'remaining_unresolved_signals':plan['remaining_review_signals'],'gmail_mutations':0,'checkpoint_advanced':False,'automatic_writes_enabled':False}
    if not apply:return summary
    calendar=calendar or DeadlineCalendar(access_token,'primary')
    # Calendar access/ownership preflight occurs BEFORE any canonical writes.
    for event in plan['review_events']:
        try:
            old=calendar._call('GET',event['id'])
            if (old.get('extendedProperties') or {}).get('private',{}).get('careerOpsApplication')!=event['extendedProperties']['private']['careerOpsApplication']:raise ValueError('review event ownership conflict')
        except GoogleError as exc:
            if exc.status!=404:raise
    for region,h in before.items():
        src=Path(profiles['regions'][region]['tracker']);target=root/'backups'/(region+'-'+h+'.xlsx');target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copy2(src,target)
        if digest(target)!=h:raise ValueError('canonical backup hash mismatch')
    staged,receipts=stage_workbooks(plan,profiles,before,root/'staged')
    atomic_json(root/'staged-receipts.json',receipts)
    audit=commit_staged(staged,profiles,before,plan['review_events'],calendar,root/'apply-audit.json')
    after_records,after=tracker.read()
    post=build_plan(report,after_records,{item:'uk' for item in CONFIRMED})
    atomic_json(root/'post-apply-dry-reconciliation.json',{'workbook_fingerprints':after,'plan':post,'mode':'dry-run','gmail_mutations':0,'checkpoint_advanced':False})
    summary.update(status='PASS' if not post['records'] and not plan['skipped'] else 'BLOCKED',tracker_rows_added=sum(x['new'] for x in receipts),tracker_rows_updated=sum(not x['new'] for x in receipts),calendar_events_created=sum(x['created'] for x in audit['calendar']),duplicates_avoided=plan['duplicate_signals_avoided']+3,after_hashes=after,changed_application_ids=[{'application_id':x['application_id'],'region':x['region'],'row':x['write']['row'],'new':x['new']} for x in receipts],event_ids=[x['event_id'] for x in audit['calendar']],post_apply_remaining_writes=len(post['records']),post_apply_duplicate_signals=post['duplicate_signals_avoided'])
    if any(after[x['region']]!=x['after'] for x in audit['workbooks']):summary['status']='BLOCKED';summary['post_apply_drift']=True
    atomic_json(root/'result.json',summary)
    return summary


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True);parser.add_argument('--profiles',required=True);parser.add_argument('--runtime',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:
        result=run_bounded(args.report,args.profiles,args.runtime,apply=args.apply)
        print(json.dumps(result,indent=2));return 0 if result['status']!='BLOCKED' else 1
    except Exception as exc:
        result={'status':'BLOCKED','failure_type':type(exc).__name__,'reason':'Staged apply halted; inspect private audit. No automatic writes enabled.','gmail_mutations':0,'checkpoint_advanced':False,'automatic_writes_enabled':False}
        # Only these deterministic local errors are safe to echo; API text is not.
        if isinstance(exc,ValueError):result['reason']=str(exc)
        atomic_json(Path(args.runtime)/'blocked-result.json',result);print(json.dumps(result));return 1

if __name__=='__main__':raise SystemExit(main())
