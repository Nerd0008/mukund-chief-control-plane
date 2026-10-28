"""Fresh read-only operational evidence and narrowly scoped status rendering.

No archive-wide keyword search, model call, credential probe, scheduler mutation
or publisher dispatch is performed here. Durable owner facts stay in their own
reference overlay; historical operational prose is never current-state authority.
"""
from __future__ import annotations
import hashlib,json,re,sqlite3
from pathlib import Path
from datetime import datetime,timedelta
import linkedin_state as state

MARKER='CURRENT_OPERATIONAL_EVIDENCE_V1'


def _instant(value):
    if not value:return None
    dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if dt.tzinfo is None:raise ValueError('unqualified operational timestamp')
    return dt


def latest_run(job_id,*,home=state.HOME):
    if not re.fullmatch(r'[0-9a-f]{8,32}',str(job_id)):raise ValueError('invalid job identifier')
    home=Path(home);jobs=state.read(home/'cron/jobs.json');jobs=jobs if isinstance(jobs,list) else jobs['jobs']
    job=next((j for j in jobs if j.get('id')==job_id),None)
    if not job:return {'job_id':job_id,'available':False,'reason_code':'job_not_found'}
    execution=None;db=home/'cron/executions.db'
    if db.exists():
        with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as con:
            con.row_factory=sqlite3.Row
            row=con.execute('SELECT id,status,claimed_at,started_at,finished_at FROM executions WHERE job_id=? ORDER BY COALESCE(started_at,claimed_at) DESC, rowid DESC LIMIT 1',(job_id,)).fetchone()
            if row:execution=dict(row)
    out={'job_id':job_id,'available':False,'job_enabled':job.get('enabled') is True,
         'last_run_at':job.get('last_run_at'),'last_status':job.get('last_status'),'execution':execution}
    candidates=[];base=home/'cron/output'
    for p in (base/job_id).glob('*.md'):
        try:stamp=datetime.strptime(p.stem,'%Y-%m-%d_%H-%M-%S').replace(tzinfo=state.LONDON)
        except ValueError:continue
        candidates.append((stamp,1,p))
    for p in base.glob(job_id+'_*.txt'):
        try:stamp=datetime.strptime(p.stem[len(job_id)+1:],'%Y%m%d_%H%M%S').replace(tzinfo=state.LONDON)
        except ValueError:continue
        candidates.append((stamp,0,p))
    if not candidates:return {**out,'reason_code':'no_saved_output'}
    stamp,_,path=max(candidates,key=lambda v:(v[0],v[1]))
    # A new execution supersedes last_run_at, even before it has output. Never
    # match its predecessor's green result via the previous job timestamp.
    if execution:
        finished=_instant(execution.get('finished_at'))
        started=_instant(execution.get('started_at') or execution.get('claimed_at'))
        matches=bool(finished and abs((stamp-finished).total_seconds())<=120 and (not started or stamp>=started-timedelta(seconds=2)))
    else:
        last=_instant(job.get('last_run_at'))
        matches=bool(last and abs((stamp-last).total_seconds())<=120)
    if not matches:
        return {**out,'reason_code':'latest_execution_output_not_available','historical_log_ignored':str(path)}
    first=path.stat()
    if first.st_size>2*1024*1024:return {**out,'reason_code':'latest_output_too_large','path':str(path)}
    raw=path.read_bytes();after=path.stat()
    if (first.st_size,first.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        return {**out,'reason_code':'output_changed_during_read'}
    text=raw.decode('utf-8',errors='replace').replace('\r\n','\n')
    payload=None;region='';error_region=''
    # Match the host's actual no-agent success/failure envelopes. Prompt text
    # in agent run documents is never a structured script result.
    if re.search(r'^\*\*Mode:\*\* no_agent \(script\)$',text,re.M):
        body=text.split('**Mode:** no_agent (script)',1)[1]
        if '\n---\n' in body:region=body.split('\n---\n',1)[1].strip()
        elif re.search(r'^stdout:\s*$',body,re.M):region=re.split(r'^stdout:\s*$',body,maxsplit=1,flags=re.M)[1].strip()
    elif path.suffix=='.txt' and '## Prompt' not in text:
        region=text.strip() if text.lstrip().startswith('{') else ''
    if region.startswith('{'):
        try:payload,_=json.JSONDecoder().raw_decode(region)
        except ValueError:pass
    typed={k:payload[k] for k in ('phase','outcome','reason_code','publish_performed','network_calls','owner_approved','reviews_ready','published','body_sha256') if isinstance(payload,dict) and k in payload}
    error_code=None
    # For an agent document use ONLY its final result section, never an error
    # heading quoted inside its prompt or a successful model response.
    sections=list(re.finditer(r'^## (Error|Response)\s*$',text,re.M))
    if sections and sections[-1].group(1)=='Error':error_region=text[sections[-1].end():]
    execution_status=str((execution or {}).get('status') or job.get('last_status') or '').lower()
    if error_region and execution_status in ('error','failed','failure'):
        match=re.search(r'(router_cli_usage_limit|no_healthy_compatible_worker|invalid_grant|provider_rate_limit|HTTP 429)',error_region)
        error_code=match.group(1) if match else 'recorded_execution_error'
    return {**out,'available':True,'reason_code':'latest_execution_output_selected',
        'path':str(path),'log_run_at':stamp.isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),
        'structured_result':typed,'execution_error_code':error_code}


def snapshot(*,home=state.HOME,root=state.ROOT,db_path=None,now=None):
    now=now or datetime.now(state.LONDON);monday=now.date()-timedelta(days=now.weekday())
    status=state.week_status(monday.isoformat(),root=root,db_path=db_path,jobs_path=Path(home)/'cron/jobs.json')
    fields=('day','date','phase','owner_approved','reviews_ready','content_ready','published','slot_matches','automatic_publish_armed','publishing_enabled','body_sha256','job','draft_exists','artifact','source_kind','alternatives')
    days=[{k:row[k] for k in fields if k in row} for row in status['days']]
    for row in days:
        if row.get('alternatives'):row['alternatives']=[{k:v for k,v in alt.items() if k!='post_text'} for alt in row['alternatives']]
    logs=[latest_run(jid,home=home) for jid in state.JOB_IDS.values()]
    value={'schema_version':1,'workflow':'linkedin','checked_at':now.isoformat(),
        'publishing_enabled':state.publishing_enabled(root),'days':days,'latest_executions':logs,
        'authority':'current canonical files and exact latest job execution; historical profile snapshots are not live state'}
    value['evidence_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
    return value


def workflow_for(text,prior=None):
    if re.search(r'(?i)job (?:search|scan)|jobs? (?:report|digest)|career (?:report|daily report)',text):return 'career_search'
    if re.search(r'(?i)\blinkedin\b|beb0251ed70c|f1b1452f18b1|8e6048e2dfa7',text):return 'linkedin'
    if re.search(r'(?i)\b(?:cv|resume|cover letter|gmail|calendar|job search)\b|my (?:profile|goals|background)|new (?:unrelated )?task|weather',text):return None
    if prior=='career_search' and re.search(r'(?i)^(?:okay |ok |yes |yeah )?(?:run|start|continue|show|check|resume)|report|results|scan',text):return prior
    if prior=='linkedin' and (re.search(r'(?i)\b(?:posts?|drafts?|artefacts?|artifacts?|images?|remaining|approve|approval|schedule)\b',text) or is_status_question(text) or re.match(r'(?i)^\s*(?:yes|yeah|ok|okay|continue|try again|repeat|rewrite|revise|edit|make|use that|do it)\b',text)):return prior
    return None


def is_status_question(text):
    if re.search(r'(?i)^(?:please |can you |could you |i want you to )?(?:fix|repair|build|write|draft|generate|publish|schedule|resume|enable|disable|create|update|change|investigate|debug)\b',text.strip()):return False
    return bool(re.search(r'(?i)\bstatus\b|\b(?:why|what|is|are|has|have|check)\b.{0,110}\b(?:blocked|publish|published|upload|approval|approved|ready|scheduled|enabled|disabled|exit code|failed|failing)\b|why are these systems not talking',text))


def current_contract():
    import hermes_owner_context as owner
    context=owner.DISPATCH_CONTEXT.get()
    return (context or {}).get('contract') or {}


def enrich_request(request):
    contract=current_contract()
    if contract.get('workflow') not in ('linkedin','career_search'):return request,None
    try:
        if contract['workflow']=='career_search':
            from career_workflow_bridge import search_report
            evidence=search_report()
        else:
            evidence=snapshot()
            if contract.get('action') in ('SHOW_DRAFTS','BUILD_ARTIFACTS'):
                from career_workflow_bridge import show
                evidence['requested_drafts']=show()['days']
                evidence['evidence_sha256']=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
    except Exception as exc:evidence={'workflow':'linkedin','available':False,'reason_code':'current_status_unavailable','error_type':type(exc).__name__,'checked_at':datetime.now(state.LONDON).isoformat()}
    message={'role':'system','content':MARKER+'\n'+json.dumps(evidence,sort_keys=True,ensure_ascii=False)+
        '\nUse this fresh structured evidence for present operational claims. Earlier logs and owner-reference status snapshots describe history only. A completed model call is not a completed publication.'}
    updated=dict(request);updated['messages']=[m for m in request.get('messages',[]) if not (m.get('role')=='system' and str(m.get('content','')).startswith(MARKER))]+[message]
    return updated,evidence


def receipt_evidence(value):
    """Source/version evidence only; unapproved post prose is not telemetry."""
    if isinstance(value,dict):return {k:receipt_evidence(v) for k,v in value.items() if k!='post_text'}
    if isinstance(value,list):return [receipt_evidence(v) for v in value]
    return value


def render(evidence):
    if evidence.get('available') is False:return 'I could not verify the current LinkedIn state. I will not infer it from old logs or profile notes.'
    lines=['LinkedIn status, checked '+evidence['checked_at']+'.',
        'Publishing is '+('enabled.' if evidence['publishing_enabled'] else 'paused.')]
    for day in evidence['days']:
        phase=day['phase'];label=day['day'].title()
        if phase=='PUBLISHED':detail='already published. The existing post must not be posted again.'
        elif phase=='AWAITING_OWNER_APPROVAL':detail='draft awaits your exact-text approval.'
        elif phase=='NO_ARTIFACT':detail='no current dated draft exists.'
        elif phase=='APPROVED_BUT_BLOCKED':detail='your approval is preserved, but review or integrity checks are incomplete.'
        elif phase=='APPROVED_READY_PAUSED':detail='approved and reviewed; automatic publication is not armed.'
        elif phase=='SCHEDULED':detail='approved, reviewed and scheduled for '+str(day.get('date'))+'.'
        else:detail=phase.replace('_',' ').lower()+'.'
        lines.append(label+': '+detail)
    for log in evidence['latest_executions']:
        label=next((k for k,v in state.JOB_IDS.items() if v==log['job_id']),log['job_id'])
        if not log.get('available'):
            if log.get('execution'):lines.append('Latest '+label+' execution output is unavailable ('+log['reason_code']+'); an older run was not used as a substitute.')
            continue
        if log.get('execution_error_code'):lines.append('Latest '+label+' execution recorded '+log['execution_error_code']+'. This identifies the recorded error, not an inferred underlying cause.')
        typed=log.get('structured_result') or {};phase=typed.get('phase')
        if phase in ('PUBLISHED','ALREADY_PUBLISHED') and typed.get('publish_performed') is False:
            lines.append('The latest Tuesday attempt stopped because this body was already published. It made '+str(typed.get('network_calls',0))+' network calls. Its old failure label does not mean approval or fact checks are missing.')
        elif phase=='NOT_DUE':lines.append('The latest '+next(k for k,v in state.JOB_IDS.items() if v==log['job_id'])+' catch-up was not due; it did not publish.')
    lines.append('Current readiness and the last execution result are separate observations. No claim about why an earlier attempt failed is inferred from the current state.')
    lines.append('Evidence: '+evidence['evidence_sha256'][:16]+'. No publication was performed by this status check.')
    return '\n\n'.join(lines)


def _record_response(contract,evidence,answer):
    from workflow_routing import persist
    import uuid
    persist({'workflow':'hermes.operational-answer','call_id':uuid.uuid4().hex,'stage':contract.get('action') or 'final_status',
        'status':'CANONICAL_STAGE_RESULT','upstream_call_id':contract.get('turn_id'),
        'input_sha256':evidence.get('evidence_sha256') or hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
        'output_sha256':hashlib.sha256(answer.encode()).hexdigest(),'validation_passed':evidence.get('ok') is not False,
        'operational_evidence':receipt_evidence(evidence)})
    return answer


def transform_output(response_text,**kwargs):
    contract=current_contract()
    if contract.get('turn_origin')!='synthetic_event' and contract.get('action') in ('SHOW_DRAFTS','BUILD_ARTIFACTS') and contract.get('workflow')=='linkedin':
        from career_workflow_bridge import show,render_drafts
        try:
            evidence=show();return _record_response(contract,evidence,render_drafts(evidence))
        except Exception:return 'I could not verify the current draft files. I will not infer that your drafts are missing or create replacements from old notes.'
    if contract.get('turn_origin')!='synthetic_event' and contract.get('action')=='SEARCH_REPORT':
        from career_workflow_bridge import search_report,render_search
        try:
            evidence=search_report();return _record_response(contract,evidence,render_search(evidence))
        except Exception:return 'The current job-search report could not be verified. No search was started or stopped by this report request.'
    if contract.get('turn_origin')=='synthetic_event' or contract.get('workflow')!='linkedin' or not is_status_question(contract.get('latest_human_message','')):return None
    try:
        evidence=snapshot();answer=render(evidence)
        from workflow_routing import persist
        import uuid
        persist({'workflow':'hermes.operational-answer','call_id':uuid.uuid4().hex,'stage':'final_status',
            'status':'CANONICAL_STATUS_RENDERED','upstream_call_id':contract.get('turn_id'),
            'input_sha256':evidence.get('evidence_sha256'),'output_sha256':hashlib.sha256(answer.encode()).hexdigest(),
            'validation_passed':evidence.get('available') is not False,'operational_evidence':evidence})
        return answer
    except Exception:return 'I could not verify and record current LinkedIn status. I will not diagnose it using historical logs or memory.'


def router_task(request,default):
    c=current_contract()
    if c.get('workflow') not in ('linkedin','career_search'):return default
    return json.dumps({'workflow':c['workflow'],'action':c.get('action'),'task_kind':'current operational diagnosis' if is_status_question(c.get('latest_human_message','')) else 'owner-requested LinkedIn task',
        'owner_request':c.get('latest_human_message') or c.get('objective'),'requirements':['fresh canonical workflow state','latest execution identity','preserve exact approval and no duplicate publication']},ensure_ascii=False)
