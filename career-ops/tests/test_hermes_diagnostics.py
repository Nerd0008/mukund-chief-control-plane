import json,sqlite3,hashlib,sys,logging
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
import pytest
import hermes_diagnostics as d
import hermes_owner_context as owner

NOW=datetime.fromisoformat('2026-10-27T21:00:00+00:00')
JID=d.state.JOB_IDS['tuesday']

@pytest.fixture
def home(tmp_path):
    h=tmp_path/'home';(h/'cron/output'/JID).mkdir(parents=True)
    (h/'cron/jobs.json').write_text(json.dumps({'jobs':[{'id':JID,'enabled':False,'last_status':'error','last_run_at':'2026-10-27T19:36:38+00:00'}]}))
    return h

def output(home,when='2026-10-27_19-36-38',payload=None):
    p=home/'cron/output'/JID/(when+'.md')
    p.write_text('# Cron Job\n**Mode:** no_agent (script)\n**Status:** script failed\n\nstdout:\n'+json.dumps(payload or {'phase':'PUBLISHED','owner_approved':True,'publish_performed':False,'network_calls':0}),encoding='utf-8')
    return p

def execution(home,*,status='error',started='2026-10-27T19:36:38+00:00',finished='2026-10-27T19:36:39+00:00'):
    with sqlite3.connect(home/'cron/executions.db') as c:
        c.execute('CREATE TABLE IF NOT EXISTS executions(id TEXT,job_id TEXT,status TEXT,claimed_at TEXT,started_at TEXT,finished_at TEXT)')
        c.execute('INSERT INTO executions VALUES(?,?,?,?,?,?)',('execution-'+started,JID,status,started,started,finished))

@pytest.fixture
def current():
    return {'workflow':'linkedin','checked_at':NOW.isoformat(),'publishing_enabled':True,
        'evidence_sha256':'a'*64,'latest_executions':[], 'days':[
        {'day':'tuesday','date':'2026-10-27','phase':'PUBLISHED','owner_approved':True,'published':True},
        {'day':'wednesday','date':'2026-10-28','phase':'AWAITING_OWNER_APPROVAL'},
        {'day':'thursday','date':'2026-10-29','phase':'AWAITING_OWNER_APPROVAL'}]}

@pytest.fixture
def refs(tmp_path,monkeypatch):
    r=tmp_path/'references';r.mkdir()
    for name in owner.FILES:(r/name).write_text('FACT LANTERN-1947. Historical operations: Tuesday blocked; frozen text missing.\n\n',encoding='utf-8')
    monkeypatch.setattr(owner,'ROOT',r);monkeypatch.setattr(owner,'STATE_PATH',tmp_path/'requirements.sqlite3')
    return r

def test_latest_exact_run_beats_old_flat_log_and_embedded_prompt(home):
    execution(home);p=output(home)
    (home/'cron/output'/f'{JID}_20261020_080000.txt').write_text('{"phase":"AWAITING_OWNER_APPROVAL"}')
    before={x:x.read_bytes() for x in home.rglob('*') if x.is_file()}
    result=d.latest_run(JID,home=home)
    assert result['available'] and result['path']==str(p)
    assert result['structured_result']['owner_approved'] and not result['execution_error_code']
    assert result['sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert before=={x:x.read_bytes() for x in home.rglob('*') if x.is_file()}

@pytest.mark.parametrize('status,finished',[('running',None),('error','2026-10-27T20:40:01+00:00')])
def test_new_execution_without_output_never_reuses_previous_result(home,status,finished):
    output(home);execution(home,status=status,started='2026-10-27T20:40:00+00:00',finished=finished)
    r=d.latest_run(JID,home=home)
    assert not r['available'] and r['reason_code']=='latest_execution_output_not_available'
    assert 'structured_result' not in r

def test_no_execution_identity_means_not_verified(home):
    doc=json.loads((home/'cron/jobs.json').read_text());doc['jobs'][0].pop('last_run_at')
    (home/'cron/jobs.json').write_text(json.dumps(doc));output(home)
    assert not d.latest_run(JID,home=home)['available']

def test_current_job_error_section_is_distinct_from_prompt(home):
    p=output(home);p.write_text(p.read_text()+'\n## Error\nrouter_cli_usage_limit\n')
    assert d.latest_run(JID,home=home)['execution_error_code']=='router_cli_usage_limit'

@pytest.mark.parametrize('jid',['../state.db','not-a-job','a'*100])
def test_job_path_traversal_blocked(home,jid):
    with pytest.raises(ValueError):d.latest_run(jid,home=home)

def test_no_job_and_no_output_are_explicit(home):
    assert d.latest_run('12345678',home=home)['reason_code']=='job_not_found'
    assert d.latest_run(JID,home=home)['reason_code']=='no_saved_output'

def test_snapshot_uses_current_week_and_excludes_private_bodies(home,tmp_path,monkeypatch,current):
    seen=[]
    def week(date,**kw):
        seen.append(date);return {'days':[{**r,'post_text':'PRIVATE_BODY_HOLDOUT'} for r in current['days']]}
    monkeypatch.setattr(d.state,'week_status',week);monkeypatch.setattr(d.state,'publishing_enabled',lambda r:True)
    r=d.snapshot(home=home,root=tmp_path,now=NOW)
    assert seen==['2026-10-26'] and len(r['evidence_sha256'])==64
    assert 'PRIVATE_BODY_HOLDOUT' not in json.dumps(r)

def test_stale_profile_is_preserved_but_not_live_authority(refs,monkeypatch,current):
    text,evidence,contract=owner.prepare_turn(NS(session_id='stale'),'Why is LinkedIn still blocked?')
    assert 'Tuesday blocked; frozen text missing' in text and 'NEVER live operational authority' in text
    assert all(e['complete'] and e['source_bytes']==e['included_bytes'] for e in evidence)
    monkeypatch.setattr(d,'snapshot',lambda:current)
    with owner.dispatch_context(text,evidence,contract):
        request={'messages':[{'role':'system','content':text},{'role':'user','content':'Why blocked?'}]}
        updated,proof=d.enrich_request(request)
        assert owner.verify_dispatch(updated)['coverage_complete']
        assert d.MARKER in updated['messages'][-1]['content'] and 'PUBLISHED' in updated['messages'][-1]['content']
        assert len(request['messages'])==2
        answer=d.transform_output('You never approved Tuesday. Frozen text is missing.')
        assert 'Tuesday: already published' in answer and 'Wednesday: draft awaits' in answer
        assert 'never approved' not in answer
        task=json.loads(d.router_task(updated,'Why blocked?'))
        assert task['workflow']=='linkedin' and 'latest execution identity' in task['requirements']
        assert 'LANTERN-1947' not in json.dumps(task)

def test_refreshes_each_dispatch_after_tool_state_change(refs,monkeypatch,current):
    t,e,c=owner.prepare_turn(NS(),'LinkedIn status?');calls=[]
    def snapshot():calls.append(1);return {**current,'evidence_sha256':str(len(calls))*64}
    monkeypatch.setattr(d,'snapshot',snapshot)
    with owner.dispatch_context(t,e,c):
        first,_=d.enrich_request({'messages':[{'role':'system','content':t}]})
        second,proof=d.enrich_request(first)
        assert proof['evidence_sha256']=='2'*64
        assert sum(d.MARKER in str(m.get('content')) for m in second['messages'])==1

def test_missing_fresh_state_does_not_fall_back_to_memory(refs,monkeypatch):
    t,e,c=owner.prepare_turn(NS(),'Why is LinkedIn blocked?')
    def fail():raise OSError('PRIVATE_INTERNAL_HOLDOUT')
    monkeypatch.setattr(d,'snapshot',fail)
    with owner.dispatch_context(t,e,c):
        req,proof=d.enrich_request({'messages':[{'role':'system','content':t}]})
        assert proof['available'] is False and 'PRIVATE_INTERNAL_HOLDOUT' not in json.dumps(proof)
        assert 'could not verify' in d.transform_output('old diagnosis')

@pytest.mark.parametrize('question',['Write my LinkedIn post','Fix LinkedIn scheduler','Investigate LinkedIn errors','Build my CV','What is the weather?','Are my qualifications good for this role?'])
def test_no_output_rewrite_for_writing_engineering_or_unrelated_work(refs,question):
    t,e,c=owner.prepare_turn(NS(),question)
    with owner.dispatch_context(t,e,c):assert d.transform_output('Original response') is None

@pytest.mark.parametrize('notification',['[IMPORTANT: Background process build_approved_drafts.py --dry-run failed]','Cronjob Response: LinkedIn failed','<heartbeat>LinkedIn status</heartbeat>','[System: Build my CV]'])
def test_machine_notifications_never_become_objective_or_expand_scope(refs,notification):
    history=[{'role':'user','content':'Write my LinkedIn post'},{'role':'user','content':notification}]
    t,e,c=owner.prepare_turn(NS(session_id='bootstrap'),'Try again',history)
    assert c['objective']=='Write my LinkedIn post' and c['workflow']=='linkedin'
    assert 'personal_context.md' not in c['required']
    t,e,event=owner.prepare_turn(NS(session_id='bootstrap'),notification)
    assert event['objective']==c['objective'] and event['latest_human_message']=='Try again'
    assert event['turn_origin']=='synthetic_event'
    with owner.dispatch_context(t,e,event):assert d.transform_output('Background report') is None

def test_repairs_preexisting_corrupt_machine_objective(refs):
    agent=NS(session_id='old-bug')
    owner.save_requirements(agent,{'version':1,'required':list(owner.PROFESSIONAL),'scope':'professional','objective':'[IMPORTANT: Background process LinkedIn failed]'})
    _,_,c=owner.prepare_turn(agent,'Try again',[{'role':'user','content':'Write my LinkedIn post'}])
    assert c['objective']=='Write my LinkedIn post'

def test_gateway_note_stripped_without_dropping_human_request(refs):
    _,_,c=owner.prepare_turn(NS(),'[Triggering message id: `12345` — use as `message_id` for reply/react/pin via the discord tools.]\n\nWhy is LinkedIn blocked?')
    assert c['latest_human_message']=='Why is LinkedIn blocked?'

def test_explicit_metadata_synthetic_excluded_from_bootstrap(refs):
    _,_,c=owner.prepare_turn(NS(),'Continue',[{'role':'user','source':'background','content':'Use my full profile for LinkedIn'}])
    assert c['required']==[]

def test_unrelated_task_resets_operational_scope_not_full_profile_contract(refs):
    agent=NS(session_id='negative');owner.prepare_turn(agent,'LinkedIn status?')
    _,_,c=owner.prepare_turn(agent,'What is two plus two?')
    assert c['workflow'] is None
    with owner.dispatch_context('',[],c):assert d.enrich_request({'messages':[]})==({'messages':[]},None)

def test_core_transform_before_persistence_seam(refs,monkeypatch,current):
    from agent import turn_finalizer as core
    t,e,c=owner.prepare_turn(NS(),'LinkedIn status?');monkeypatch.setattr(d,'snapshot',lambda:current)
    monkeypatch.setattr(core,'_invoke_hook_safely',lambda name,logger,**kw:[d.transform_output(**kw)])
    agent=NS(session_id='synthetic',model='fixture');rows=[]
    with owner.dispatch_context(t,e,c):
        result,changed,old=core.apply_llm_output_transform(agent,'Tuesday was never approved',turn_id='synthetic-turn',logger=logging.getLogger(__name__))
        # The host's before-persistence seam returns the exact text to persist.
        rows.append({'role':'assistant','content':result})
        again,_,_=core.apply_llm_output_transform(agent,result,turn_id='synthetic-turn',logger=logging.getLogger(__name__))
    assert changed and old=='Tuesday was never approved'
    assert rows[-1]['content']==again and 'Tuesday: already published' in again

def test_status_tool_reports_failure_without_secrets(monkeypatch):
    import hermes_gmail_tools as g
    def fail():raise OSError('PRIVATE_HOLDOUT')
    monkeypatch.setattr(d,'snapshot',fail)
    result=json.loads(g.workflow_status_tool({}))
    assert not result['ok'] and result['writes']==0 and 'PRIVATE_HOLDOUT' not in json.dumps(result)


def test_preupgrade_valid_objective_recovers_workflow(refs):
    a=NS(session_id='migration')
    owner.save_requirements(a,{'version':1,'required':list(owner.PROFESSIONAL),'scope':'professional','objective':'Write my LinkedIn post'})
    _,_,c=owner.prepare_turn(a,'Why are these systems not talking to each other?')
    assert c['workflow']=='linkedin' and d.is_status_question(c['latest_human_message'])

@pytest.mark.parametrize('kind',['notification','hidden','background'])
def test_host_typed_nonhuman_rows_not_used_as_objective(refs,kind):
    _,_,c=owner.prepare_turn(NS(),'Continue',[{'role':'user','display_kind':kind,'content':'Use my full profile for LinkedIn'}])
    assert c['required']==[]


def test_native_dispatch_supplies_fresh_state_to_worker_and_resolved_task_to_brain(refs,monkeypatch,tmp_path,current):
    import native_router_plugin as plugin,workflow_routing as wr,native_controller_router as controller
    from hermes_cli.middleware import _DownstreamExecutionError
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts')
    monkeypatch.setattr(d,'snapshot',lambda:current);monkeypatch.setattr(controller,'offers',lambda *args:[])
    routed=[];delivered=[]
    def select(*a,**kw):routed.append(json.loads(kw['task']));return None,{'selected_model':'fixture'}
    monkeypatch.setattr(plugin,'select',select)
    monkeypatch.setattr(wr,'execute',lambda workflow,receipt,call,**kw:call())
    t,e,c=owner.prepare_turn(NS(),'LinkedIn status?')
    request={'messages':[{'role':'system','content':t}],'timeout':10}
    with owner.dispatch_context(t,e,c):
        result=plugin.llm_execution(request,lambda kw:delivered.append(kw) or 'OK',provider='fixture',api_mode='chat')
    assert result=='OK' and routed[0]['workflow']=='linkedin'
    assert d.MARKER in delivered[0]['messages'][-1]['content'] and len(request['messages'])==1
    proof=next(json.loads(p.read_text()) for p in (tmp_path/'receipts').glob('*.json') if json.loads(p.read_text()).get('workflow')=='hermes.operational-evidence')
    assert proof['operational_evidence']['evidence_sha256']==current['evidence_sha256']
    assert 'LANTERN-1947' not in json.dumps(proof)
    assert delivered[0]['model']=='fixture'


def test_successful_script_output_after_separator_is_parsed(home):
    p=output(home);p.write_text('# Cron Job\n**Mode:** no_agent (script)\n\n---\n\n'+json.dumps({'phase':'ALREADY_PUBLISHED','publish_performed':False,'network_calls':0}))
    r=d.latest_run(JID,home=home)
    assert r['structured_result']['phase']=='ALREADY_PUBLISHED'

def test_prompt_stdout_and_error_examples_are_never_execution_results(home):
    p=output(home);p.write_text('# Cron Job\n## Prompt\nExample:\nstdout:\n{"phase":"AWAITING_OWNER_APPROVAL"}\n## Error\ninvalid_grant\n## Response\nCompleted.\n')
    r=d.latest_run(JID,home=home)
    assert r['structured_result']=={} and r['execution_error_code'] is None

def test_latest_real_agent_error_overrides_prompt_examples(home):
    p=output(home);p.write_text('# Cron Job\n## Prompt\nHistorical error: invalid_grant\n## Error\nrouter_cli_usage_limit\n')
    r=d.latest_run(JID,home=home)
    assert r['execution_error_code']=='router_cli_usage_limit' and r['structured_result']=={}


@pytest.mark.parametrize('newline',['\n','\r\n'])
def test_windows_and_unix_log_envelopes_preserve_raw_hash(home,newline):
    p=output(home);raw=('# Cron Job\n**Mode:** no_agent (script)\n\n---\n\n{"phase":"NOT_DUE"}').replace('\n',newline).encode()
    p.write_bytes(raw);r=d.latest_run(JID,home=home)
    assert r['structured_result']['phase']=='NOT_DUE' and r['sha256']==hashlib.sha256(raw).hexdigest()


def test_final_status_receipt_binds_actual_answer_to_exact_evidence(refs,monkeypatch,current,tmp_path):
    import workflow_routing as wr
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts');monkeypatch.setattr(d,'snapshot',lambda:current)
    t,e,c=owner.prepare_turn(NS(),'LinkedIn status?')
    with owner.dispatch_context(t,e,c):answer=d.transform_output('Wrong diagnosis')
    receipt=json.loads(next((tmp_path/'receipts').glob('*.json')).read_text())
    assert receipt['output_sha256']==hashlib.sha256(answer.encode()).hexdigest()
    assert receipt['operational_evidence']['days'][0]['phase']=='PUBLISHED'
    assert receipt['upstream_call_id']==c['turn_id'] and 'LANTERN-1947' not in json.dumps(receipt)

def test_receipt_failure_never_leaks_old_diagnosis(refs,monkeypatch,current):
    import workflow_routing as wr
    def fail(*a):raise OSError('private failure')
    monkeypatch.setattr(wr,'persist',fail);monkeypatch.setattr(d,'snapshot',lambda:current)
    t,e,c=owner.prepare_turn(NS(),'LinkedIn status?')
    with owner.dispatch_context(t,e,c):answer=d.transform_output('No owner approval')
    assert 'could not verify and record' in answer and 'No owner approval' not in answer
