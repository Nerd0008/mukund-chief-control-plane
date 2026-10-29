import json,sqlite3,hashlib
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'exec-brain'))
sys.path.append(str(Path.home()/'AppData/Local/hermes/hermes-agent'))
import career_workflow_bridge as bridge
import hermes_owner_context as owner
import hermes_diagnostics as diag
import linkedin_state as state
import workflow_health as health
import workflow_routing as wr
import native_router_plugin as plugin
from router_brain import RouterDecisionError,RouterBrain
from test_linkedin_state import history,gate,personal,scheduler_fixture

WEEK='2026-10-26'
BODY='A reviewed synthetic post. What would you verify?'

@pytest.fixture
def prepared(tmp_path,history,monkeypatch):
    root=tmp_path/'linkedin';path=root/'review'/WEEK/'weekly.json';path.parent.mkdir(parents=True)
    posts={}
    for day,target in [('wednesday','2026-10-28'),('thursday','2026-10-29')]:
        body=BODY+' '+day
        posts[day]={'post_text':body,'target_date':target,'phase':'AWAITING_OWNER_APPROVAL','body_sha256':state.consent.digest(body),'news_fact_gate':gate(body),'personal_fact_gate':personal(body)}
    path.write_text(json.dumps({'posts':posts}))
    jobs=tmp_path/'home/cron/jobs.json';jobs.parent.mkdir(parents=True);jobs.write_text(json.dumps({'jobs':[{'id':j,'enabled':False} for j in state.JOB_IDS.values()]}))
    (root/'publishing-policy.json').write_text('{"schema_version":1,"enabled":true}')
    for day,stamp in [('wednesday','20261028'),('thursday','20261029')]:
        d=root/'drafts'/f'approved_{stamp}_{day}';d.mkdir(parents=True)
        (d/'linkedin_drafts.json').write_text(json.dumps({'post_text':'An unchecked competing draft.','day':day,'owner_approval':None,'approved':False}))
    refs=tmp_path/'refs';refs.mkdir()
    for f in owner.FILES:(refs/f).write_text('Synthetic owner reference fact.')
    monkeypatch.setattr(owner,'ROOT',refs);monkeypatch.setattr(owner,'STATE_PATH',tmp_path/'requirements.db')
    def update(jid,updates,*,jobs_path):
        assert jobs_path==jobs
        return scheduler_fixture(jobs)[1](jid,updates)
    monkeypatch.setattr(state,'_scheduler_update',update)
    real_plan=state.plan_slot
    monkeypatch.setattr(state,'plan_slot',lambda *a,**kw:real_plan(*a,now=datetime(2026,10,27,12,tzinfo=state.LONDON),**kw))
    db,add=history
    return root,jobs,db,add,posts


def opts(prepared):
    root,jobs,db,_,_=prepared
    return {'root':root,'jobs_path':jobs,'db_path':db}


def action_args(prepared,action='approve'):
    *_,posts=prepared
    body=posts['thursday']['post_text']
    return {'action':action,'day':'thursday','week_of':WEEK,'body_sha256':state.consent.digest(body)}


def test_show_and_build_preserve_reviewed_and_competing_versions_without_writes(prepared):
    root,*_=prepared;before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    for action in ['show','build']:
        doc=bridge.linkedin({'action':action,'week_of':WEEK},**opts(prepared))
        row=next(v for v in doc['days'] if v['day']=='thursday')
        assert row['source_kind']=='REVIEWED_PREPARED' and row['reviews_ready'] and BODY in row['post_text']
        assert row['alternatives'][0]['post_text']=='An unchecked competing draft.'
        assert 'You can approve this in your own words' in bridge.render_drafts(doc)
        assert 'APPROVE LINKEDIN' not in bridge.render_drafts(doc)
    assert before=={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_exact_natural_language_sequence_retains_workflow_and_renders_actual_drafts(prepared,monkeypatch):
    agent=NS(session_id='incident-replay')
    owner.prepare_turn(agent,'Show my LinkedIn posts')
    t,e,c=owner.prepare_turn(agent,'Okay let’s start working on the rest of the weeks post show me the remaining ones')
    assert c['workflow']=='linkedin' and c['action']=='SHOW_DRAFTS'
    t,e,c=owner.prepare_turn(agent,'Build the artefacts I wanna see them and then approve if they are accurate')
    assert c['workflow']=='linkedin' and c['action']=='BUILD_ARTIFACTS'
    original=bridge.show
    monkeypatch.setattr(bridge,'show',lambda:original(week_of=WEEK,**opts(prepared)))
    with owner.dispatch_context(t,e,c):
        answer=diag.transform_output('No posts exist; let me invent replacements.')
    assert BODY in answer and 'No posts exist' not in answer and 'APPROVE LINKEDIN' not in answer


@pytest.mark.parametrize('payload',['[IMPORTANT: Background process fake failed]','[System note: A new message has arrived. The conversation history contains pending tool outputs from an interrupted turn. IGNORE those pending results. Address the user\'s NEW message below FIRST. Do NOT re-execute old tool calls from the history.]\n\n[Triggering message id: `1` — use it for replies.]\n\n[IMPORTANT: Background process fake failed]'])
def test_bare_and_wrapped_notification_cannot_replace_human_request(prepared,payload):
    agent=NS(session_id='envelope');owner.prepare_turn(agent,'Show my LinkedIn posts')
    _,_,c=owner.prepare_turn(agent,payload)
    assert c['turn_origin']=='synthetic_event' and c['latest_human_message']=='Show my LinkedIn posts'
    assert c['workflow']=='linkedin'


def test_wrapped_genuine_owner_request_is_kept(prepared):
    text='[System note: A new message has arrived. Address the user\'s NEW message below FIRST.]\n\nShow my LinkedIn posts'
    assert owner.human_text(text)=='Show my LinkedIn posts'


def test_approval_image_plan_pipeline_preserves_other_version_and_uses_existing_guards(prepared):
    root,jobs,db,add,posts=prepared;args=action_args(prepared)
    add(posts['thursday']['post_text']+'\nAPPROVE LINKEDIN '+args['body_sha256'],role='assistant')
    args['approval_message_id']=add('Approved')
    generated=[]
    result=bridge.linkedin(args,**opts(prepared),generator=lambda body:generated.append(body) or b'\x89PNG\r\nsynthetic-only-image',now=datetime(2026,10,27,12,tzinfo=state.LONDON))
    assert result['ok'] and result['plan']['planned'] and not result['publish_performed']
    assert generated==[posts['thursday']['post_text']]
    folder=root/'drafts/approved_20261029_thursday';doc=state.read(folder/'linkedin_drafts.json')
    assert doc['image_body_sha256']==args['body_sha256'] and doc['image_required']
    assert (folder/'.versions'/state.consent.digest('An unchecked competing draft.')/'linkedin_drafts.json').is_file()
    assert state.inspect_artifact(folder/'linkedin_drafts.json',**opts(prepared))['automatic_publish_armed']
    assert state.read(root/'review'/WEEK/'weekly.json')['posts']['thursday']['post_text']==posts['thursday']['post_text']


def test_unapproved_or_changed_body_cannot_generate_or_schedule(prepared):
    args=action_args(prepared,'image');calls=[]
    with pytest.raises(ValueError):bridge.linkedin(args,**opts(prepared),generator=lambda body:calls.append(body))
    args['body_sha256']='0'*64
    with pytest.raises(ValueError,match='version mismatch'):bridge.linkedin(args,**opts(prepared))
    assert not calls


def test_image_failure_retains_approval_and_cannot_arm_plan(prepared):
    root,jobs,db,add,posts=prepared;args=action_args(prepared)
    args['approval_message_id']=add('APPROVE LINKEDIN '+args['body_sha256'])
    def fail(body):raise RouterDecisionError('provider_billing_blocked')
    response=bridge.linkedin(args,**opts(prepared),generator=fail)
    assert response['phase']=='APPROVED_IMAGE_BLOCKED' and 'approval is saved' in response['message']
    path=root/'drafts/approved_20261029_thursday/linkedin_drafts.json'
    current=state.inspect_artifact(path,**opts(prepared))
    assert current['owner_approved'] and not current['content_ready'] and not current['automatic_publish_armed']
    with pytest.raises(ValueError):bridge.linkedin(action_args(prepared,'plan'),**opts(prepared))


def test_model_500_leaves_other_workers_eligible_but_503_remains_provider_wide():
    route={'selected_provider':'nous','selected_model':'one'}
    class Error(Exception):status_code=500
    health.record_failure(route,Error())
    assert not health.snapshot('nous','one')['available'] and health.snapshot('nous','two')['available']
    Error.status_code=503;health.record_failure(route,Error())
    assert not health.snapshot('nous','two')['available']


def test_cooldown_is_recorded_and_banner_does_not_claim_permanent_rejection():
    class Error(Exception):status_code=503
    health.record_failure({'selected_provider':'fixture','selected_model':'one'},Error())
    with pytest.raises(RouterDecisionError) as caught:wr.select('fixture',[{'id':'one','provider':'fixture','model':'one'}])
    assert 1<=caught.value.receipt['retry_after_seconds']<=31
    classified=NS(error_context=plugin.router_error_classification(error=caught.value)['error_context'])
    emitted=[];agent=NS(_emit_diagnostic_status=emitted.append)
    def terminal(agent,error,classified):agent._emit_diagnostic_status('provider rejected, retrying will not help');return 'result'
    module=NS(nonretryable_copy=lambda *a,**k:'old',nonretryable_client_error_result=terminal)
    plugin.install_failure_copy(module)
    assert module.nonretryable_client_error_result(agent,None,classified)=='result'
    assert 'temporarily unavailable' in emitted[0] and 'rejected' not in emitted[0]
    assert 'seconds' in module.nonretryable_copy(classified)


@pytest.mark.parametrize('workflow,action,command,blocked',[('linkedin','BUILD_ARTIFACTS','python gen_images5.py',True),('linkedin','SHOW_DRAFTS','cat career-ops/linkedin_state.py',False),('linkedin','INVESTIGATE','python inspect_linkedin.py',False),('career_search','RUN_SEARCH','python job_scan_delta.py',False),(None,None,'python unrelated.py',False)])
def test_stage_guard_is_narrow(workflow,action,command,blocked):
    with owner.dispatch_context('',[],{'workflow':workflow,'action':action}):
        assert bool(bridge.guard('terminal',{'command':command}))==blocked


def test_job_report_uses_latest_schema_and_never_triggers_search(tmp_path,monkeypatch):
    home=tmp_path/'home';repo=tmp_path/'repo';(home/'cron/output/5a66e1129e58').mkdir(parents=True)
    (home/'cron/jobs.json').write_text(json.dumps({'jobs':[{'id':'5a66e1129e58','enabled':True,'last_run_at':'2026-10-27T05:53:21+00:00'}]}))
    with sqlite3.connect(home/'cron/executions.db') as c:
        c.execute('CREATE TABLE executions(id TEXT,job_id TEXT,status TEXT,claimed_at TEXT,started_at TEXT,finished_at TEXT)')
        c.execute('INSERT INTO executions VALUES(?,?,?,?,?,?)',('last','5a66e1129e58','completed','2026-10-27T05:40:00+00:00','2026-10-27T05:40:00+00:00','2026-10-27T05:53:21+00:00'))
    run=repo/'runtime/career-ops/job-scan-runs/20261027T055321Z-test.json';run.parent.mkdir(parents=True)
    run.write_text(json.dumps({'exit_code':0,'coverage':{'completed_batches':3,'batches_attempted':3,'coverage_complete':True},'stdout':'TRACKER_WRITE_RESULT '+json.dumps({'applied':True,'counts':{'appended':2},'verification_ok':True})}))
    doc=bridge.search_report(home=home,repo=repo)
    assert doc['phase']=='COMPLETED' and doc['last_completed_scan']['completed_batches']==3
    assert doc['last_completed_scan']['verified_writer_results'][0]['counts']['appended']==2
    assert doc['network_calls']==doc['writes']==0 and 'complete coverage True' in bridge.render_search(doc)


def test_report_only_question_does_not_authorize_scan(prepared):
    _,_,c=owner.prepare_turn(NS(),'Where’s the job search report?')
    assert c['workflow']=='career_search' and c['action']=='SEARCH_REPORT'


def test_operational_receipts_remove_post_prose_recursively():
    doc={'requested_drafts':[{'post_text':'PRIVATE_DRAFT','body_sha256':'a'*64,'alternatives':[{'post_text':'PRIVATE_ALTERNATIVE'}]}]}
    safe=diag.receipt_evidence(doc)
    assert 'PRIVATE' not in json.dumps(safe) and safe['requested_drafts'][0]['body_sha256']=='a'*64


@pytest.mark.parametrize('message',['Fix job search','Pause job search','Explain job search','Write job search code'])
def test_report_guard_does_not_override_engineering_or_scheduler_requests(prepared,message):
    t,e,c=owner.prepare_turn(NS(),message)
    assert c['action'] not in ('SEARCH_REPORT','RUN_SEARCH')
    with owner.dispatch_context(t,e,c):assert diag.transform_output('Original response') is None


def test_missing_draft_files_do_not_fail_open_to_false_model_denial(prepared,monkeypatch):
    def fail():raise OSError('unreadable fixture')
    monkeypatch.setattr(bridge,'show',fail)
    with owner.dispatch_context('',[],{'workflow':'linkedin','action':'SHOW_DRAFTS','turn_origin':'human_text'}):
        answer=diag.transform_output('There are no drafts, I will replace them.')
    assert 'could not verify' in answer and 'There are no drafts' not in answer


def test_native_approval_resolves_current_owner_without_internal_id(prepared):
    root,jobs,db,add,posts=prepared;args=action_args(prepared)
    mid=add('APPROVE LINKEDIN '+args['body_sha256'])
    contract={'workflow':'linkedin','session_key':hashlib.sha256(b'owner').hexdigest(),'latest_human_message':'APPROVE LINKEDIN '+args['body_sha256'],'turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        assert bridge.current_approval_message(db_path=db)==mid
        result=bridge.linkedin(args,**opts(prepared),generator=lambda body:b'\x89PNG\r\nfixture')
    assert result['ok'] and result['approval']['owner_approved']


def test_background_or_foreign_session_cannot_resolve_owner_approval(prepared):
    # Use named fixture positions to avoid treating a tool notification as human consent.
    db=prepared[2];prepared[3]('APPROVE LINKEDIN '+'a'*64)
    for contract in [{'workflow':'linkedin','session_key':hashlib.sha256(b'other').hexdigest(),'latest_human_message':'APPROVE LINKEDIN '+'a'*64,'turn_origin':'human_text'}, {'workflow':'linkedin','session_key':hashlib.sha256(b'owner').hexdigest(),'latest_human_message':'APPROVE LINKEDIN '+'a'*64,'turn_origin':'synthetic_event'}]:
        with owner.dispatch_context('',[],contract),pytest.raises(ValueError):bridge.current_approval_message(db_path=db)


@pytest.mark.parametrize('prompt,expected',[('Investigate LinkedIn scheduler','INVESTIGATE'),('Build the LinkedIn artifacts','BUILD_ARTIFACTS')])
def test_vague_continuation_retains_stage_not_only_workflow(prepared,prompt,expected):
    a=NS(session_id='stage-restart')
    owner.prepare_turn(a,prompt)
    for message in ['Continue','Try again']:
        _,_,contract=owner.prepare_turn(NS(session_id='stage-restart'),message)
        assert contract['workflow']=='linkedin' and contract['action']==expected


def test_status_does_not_block_generic_debugging_shell():
    with owner.dispatch_context('',[],{'workflow':'linkedin','action':'STATUS'}):
        assert bridge.guard('terminal',{'command':'python inspect_linkedin_status.py'}) is None


@pytest.mark.parametrize('message',['Why can’t you publish now?','Do not publish now','Publish now if the image passes','Show my posts','Approved'])
def test_publish_now_requires_explicit_unconditional_instruction(prepared,message):
    with owner.dispatch_context('',[],{'workflow':'linkedin','latest_human_message':message,'session_key':hashlib.sha256(b'owner').hexdigest()}),pytest.raises(ValueError):
        bridge.publish_now({'date':'2026-10-29','day':'thursday','body_sha256':'a'*64},**opts(prepared))


def test_bounded_publish_uses_existing_publisher_and_requires_ledger_evidence(prepared,monkeypatch):
    root,jobs,db,add,posts=prepared;args=action_args(prepared)
    args['approval_message_id']=add('APPROVE LINKEDIN '+args['body_sha256'])
    bridge.linkedin(args,**opts(prepared),generator=lambda body:b'\x89PNG\r\nfixture')
    add('Publish it now')
    row=next(r for r in bridge.show(week_of=WEEK,**opts(prepared))['days'] if r['day']=='thursday')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2026,10,29,12,tzinfo=state.LONDON)
    monkeypatch.setattr(bridge,'datetime',Clock)
    calls=[]
    def runner(command,**kw):calls.append(command);assert 'creationflags' in kw;return NS(returncode=0,stdout=json.dumps({'performed':True,'post_urn':'urn:synthetic:test','network_calls_spent':1}))
    contract={'workflow':'linkedin','latest_human_message':'Publish it now','session_key':hashlib.sha256(b'owner').hexdigest(),'turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        result=bridge.publish_now(row,**opts(prepared),runner=runner)
        assert not result['ok'] and not result['publish_performed']  # a claimed success without ledger proof is insufficient
        monkeypatch.setattr(state,'published',lambda sha,root:True)
        assert bridge.publish_now(row,**opts(prepared),runner=runner)['phase']=='ALREADY_PUBLISHED'
    assert len(calls)==1 and calls[0][1].endswith('linkedin_publish.py') and '--confirm-token' in calls[0] and calls[0][calls[0].index('--max-retries')+1]=='0'



def test_bounded_publish_reports_success_only_after_real_private_ledger_write(prepared,monkeypatch):
    root,jobs,db,add,posts=prepared;args=action_args(prepared)
    args['approval_message_id']=add('APPROVE LINKEDIN '+args['body_sha256'])
    bridge.linkedin(args,**opts(prepared),generator=lambda body:b'\x89PNG\r\nfixture')
    add('Publish it now');row=next(r for r in bridge.show(week_of=WEEK,**opts(prepared))['days'] if r['day']=='thursday')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2026,10,29,12,tzinfo=state.LONDON)
    monkeypatch.setattr(bridge,'datetime',Clock);calls=[]
    def runner(command,**kw):
        calls.append(command);ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(json.dumps({'result':'published','body_sha256':row['body_sha256'],'post_urn':'urn:synthetic:proof'})+'\n')
        return NS(returncode=0,stdout=json.dumps({'performed':True,'post_urn':'urn:synthetic:proof','network_calls_spent':1}))
    contract={'workflow':'linkedin','latest_human_message':'Publish it now','session_key':hashlib.sha256(b'owner').hexdigest(),'turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        result=bridge.publish_now(row,**opts(prepared),runner=runner)
        again=bridge.publish_now(row,**opts(prepared),runner=runner)
    assert result['ok'] and result['publish_performed'] and result['post_urn']=='urn:synthetic:proof'
    assert again['phase']=='ALREADY_PUBLISHED' and not again['publish_performed'] and len(calls)==1



def test_repeated_approved_stage_reports_already_published_without_image_or_post(prepared):
    root,jobs,db,add,posts=prepared;args=action_args(prepared)
    args['approval_message_id']=add('APPROVE LINKEDIN '+args['body_sha256'])
    bridge.linkedin(args,**opts(prepared),generator=lambda body:b'\x89PNG\r\nfixture')
    ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
    ledger.write_text(json.dumps({'result':'published','body_sha256':args['body_sha256']})+'\n')
    def forbidden(*a,**k):raise AssertionError('no duplicate generation')
    assert bridge.linkedin(args,**opts(prepared),generator=forbidden)['phase']=='ALREADY_PUBLISHED'


@pytest.mark.parametrize('message,action',[('APPROVE LINKEDIN '+'a'*64,'APPROVAL'),('Approved','APPROVAL'),('Publish it now','PUBLISH_NOW')])
def test_approval_and_publish_stages_use_bounded_tool(prepared,message,action):
    a=NS(session_id='approval-stage');owner.prepare_turn(a,'Show my LinkedIn posts')
    t,e,c=owner.prepare_turn(a,message)
    assert c['workflow']=='linkedin' and c['action']==action
    with owner.dispatch_context(t,e,c):
        assert bridge.guard('terminal',{'command':'python gen_images2.py'})['action']=='block'
        assert bridge.guard('career_linkedin_workflow',{'action':'approve'}) is None
