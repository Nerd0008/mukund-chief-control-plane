import json,hashlib
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
import pytest
import linkedin_state as state
import linkedin_approval as consent
from linkedin_conversation import interpret
import career_workflow_bridge as bridge
import hermes_owner_context as owner
from test_career_workflow_bridge import prepared,opts,action_args,WEEK
from test_linkedin_state import history

@pytest.mark.parametrize('text',['publish','Publish it','post','please publish','wtf publish man skip the image'])
def test_simple_publish_is_natural_immediate_consent(text):
    parsed=interpret(text)
    assert parsed['approved'] and parsed['publish_now'] and not parsed['override']

@pytest.mark.parametrize('text',['do not publish','publish if the checks pass','Why publish?','write a post','publish both posts'])
def test_unconditional_scope_is_preserved(text):
    assert not interpret(text)['approved']


def test_publish_approval_and_text_only_execute_once(prepared,monkeypatch):
    root,jobs,db,add,posts=prepared;body=posts['thursday']['post_text']
    weekly=root/'review/2026-10-26/weekly.json';data=state.read(weekly)
    data['posts']['thursday']['image_required']=False;weekly.write_text(json.dumps(data))
    add(body,role='assistant');mid=add('publish')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2026,10,29,12,tzinfo=state.LONDON)
    monkeypatch.setattr(bridge,'datetime',Clock)
    calls=[]
    def publish(command,**kw):
        calls.append(command);ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(json.dumps({'result':'published','body_sha256':consent.digest(body)})+'\n')
        return NS(returncode=0,stdout=json.dumps({'performed':True,'post_urn':'urn:test:one'}))
    args=action_args(prepared,action='publish');args['approval_message_id']=mid
    contract={'workflow':'linkedin','action':'PUBLISH_NOW','latest_human_message':'publish','session_key':hashlib.sha256(b'owner').hexdigest(),'turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        result=bridge.linkedin(args,**opts(prepared),runner=publish)
        assert result['publish_performed'] and len(calls)==1
        assert bridge.linkedin(args,**opts(prepared),runner=publish)['phase']=='ALREADY_PUBLISHED'
    assert len(calls)==1 and not (root/'drafts/schedule.json').exists()


def test_image_block_is_not_a_schedule_circularity(prepared):
    root,jobs,db,add,posts=prepared;body=posts['thursday']['post_text'];add(body,role='assistant');mid=add('Approved')
    path=Path(state.capture(body,'2026-10-29',mid,root=root,db_path=db,replace=True)['artifact'])
    doc=state.read(path);doc.update(news_fact_gate=posts['thursday']['news_fact_gate'],personal_fact_gate=posts['thursday']['personal_fact_gate'],image_required=True)
    path.write_text(json.dumps(doc))
    result=state.inspect_artifact(path,**opts(prepared))
    assert result['reviews_ready'] and result['content_blockers']==['required_image_unavailable']
    with pytest.raises(ValueError,match='required_image_unavailable'):state.plan_slot(path,'2026-10-29',**opts(prepared))
    doc['image_required']=False;path.write_text(json.dumps(doc))
    assert state.inspect_artifact(path,**opts(prepared))['content_ready']
    assert not state.inspect_artifact(path,**opts(prepared))['slot_matches']


def test_scratch_script_filename_cannot_bypass_stage_guard():
    with owner.dispatch_context('',[],{'workflow':'linkedin','action':'APPROVAL'}):
        for command in ['python /tmp/write_gates2.py','python helper.py','cat > /tmp/fix.py <<EOF','powershell -c Set-Content artifact.json data']:
            assert bridge.guard('terminal',{'command':command})['action']=='block'
        assert bridge.guard('terminal',{'command':'cat career-ops/linkedin_state.py'}) is None


def test_completed_fact_decision_is_reused_and_new_evidence_rechecks(tmp_path,monkeypatch):
    import linkedin_factcheck as fc
    monkeypatch.setattr(fc,'__file__',str(tmp_path/'career-ops/linkedin_factcheck.py'))
    count=[]
    def judge(body,source,**kw):
        count.append(source)
        return {'used':True,'complete':True,'claims':[{'claim':'A factual claim.','verdict':'unsupported'}],
                'source_chars_fed':len(source),'section_coverage':[],'runs_used':3,'runs_requested':3}
    monkeypatch.setattr(fc,'llm_verify_claims',judge)
    url='https://synthetic.invalid/source'
    a=fc.verify_post('A factual claim.',[url],source_texts={url:'First evidence.'},api_key='test')
    assert a['verdict']=='block'
    b=fc.verify_post('A factual claim.',[url],source_texts={url:'First evidence.'},api_key='test')
    assert b['review_reused'] and len(count)==1 and b['verdict']=='block'
    fc.verify_post('A factual claim.',[url],source_texts={url:'New evidence.'},api_key='test')
    assert len(count)==2


def test_quoted_image_prompt_does_not_invalidate_the_public_post(history):
    db,add=history;body='The public post. #Security'
    add(body,role='assistant')
    add('Image generation is blocked by billing.\n\nThe prompt I would have used:\n> Visual medium: analogue photograph\n> A locked door.\n\nPublish the text-only post instead.',role='assistant')
    result=consent.verify_message(add('wtf publish man skip the image'),body,db_path=db)
    assert result['ok'] and result['receipt']['preferences']['skip_image']


@pytest.mark.parametrize('phrase',['Override fact check','skip fact check'])
def test_natural_override_needs_the_exact_post_and_warning(history,phrase):
    db,add=history;body='A public post.'
    add(body,role='assistant')
    assert not consent.verify_message(add(phrase),body,db_path=db,require_override=True)['ok']
    add('The fact-check blocked this post because a historical claim needs a source.',role='assistant')
    assert consent.verify_message(add(phrase),body,db_path=db,require_override=True)['ok']


def test_publication_turn_budget_is_restored_on_failure(monkeypatch):
    import hermes_gmail_tools as tools
    monkeypatch.setattr(owner,'prepare_turn',lambda *a,**kw:('',[],{'workflow':'linkedin','action':'PUBLISH_NOW','turn_origin':'human_text'}))
    class Agent:
        max_iterations=150
        ephemeral_system_prompt='original'
        def run_conversation(self,*args,**kw):
            assert self.max_iterations==8
            raise RuntimeError('synthetic failure')
    tools.install_language_policy(Agent);agent=Agent()
    with pytest.raises(RuntimeError,match='synthetic failure'):agent.run_conversation('publish')
    assert agent.max_iterations==150 and agent.ephemeral_system_prompt=='original'


def test_status_reports_image_requirement_without_guessing_a_schedule_loop(prepared,monkeypatch):
    import hermes_diagnostics as diag
    monkeypatch.setattr(bridge,'show',lambda:{'days':[{'owner_approved':True,'published':False,'content_blockers':['required_image_unavailable']}]})
    with owner.dispatch_context('',[],{'workflow':'linkedin','action':'PUBLISH_NOW','turn_origin':'human_text'}):
        answer=diag.transform_output('It is a chicken and egg scheduling defect.')
    assert 'required image is unavailable' in answer and 'chicken' not in answer and 'approval is saved' in answer


@pytest.mark.parametrize('text',['nah publish it now','build it and publish it','publish it today now'])
def test_incident_instructions_are_immediate(text):
    parsed=interpret(text,now=datetime(2026,11,4,18,tzinfo=state.LONDON))
    assert parsed['approved'] and parsed['publish_now'] and parsed['publish_at'] is None
    assert bridge.intent(text,'linkedin')=='PUBLISH_NOW'

@pytest.mark.parametrize('text',['do not build it and publish it','build it and publish it if ready','publish it tomorrow now','publish it today at 8 am'])
def test_immediate_repair_does_not_override_conditions_or_schedules(text):
    parsed=interpret(text,now=datetime(2026,11,4,18,tzinfo=state.LONDON))
    assert not parsed['publish_now']


def test_fresh_chat_post_same_day_approval_review_and_dedup(prepared,monkeypatch):
    import linkedin_content_gen as gen
    import linkedin_weekly
    import topic_reuse_check as topics
    from test_linkedin_state import gate,personal
    root,jobs,db,add,posts=prepared
    old=root/'drafts/approved_20261029_thursday/linkedin_drafts.json'
    old_bytes=old.read_bytes()
    ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
    ledger.write_text(json.dumps({'result':'published','body_sha256':consent.digest(state.body_of(state.read(old)))})+'\n')
    body='A fresh synthetic post about software security.'
    add('Here is a draft:\n```\n'+body+'\n```',role='assistant');mid=add('publish it today now skip the image')
    monkeypatch.setattr(topics,'check_text',lambda *a,**k:{'blocked':False})
    monkeypatch.setattr(gen,'factcheck_post',lambda text,sources:gate(text))
    monkeypatch.setattr(state,'_personal_runner',lambda text,label:personal(text))
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2026,10,29,12,tzinfo=state.LONDON)
    monkeypatch.setattr(bridge,'datetime',Clock)
    calls=[]
    def publish(command,**kw):
        calls.append(command);ledger=root/'published/posts.jsonl'
        with ledger.open('a') as f:f.write(json.dumps({'result':'published','body_sha256':consent.digest(body)})+'\n')
        return NS(returncode=0,stdout=json.dumps({'performed':True,'post_urn':'urn:test:chat'}))
    contract={'workflow':'linkedin','action':'PUBLISH_NOW','latest_human_message':'publish it today now skip the image','session_key':hashlib.sha256(b'owner').hexdigest(),'turn_origin':'human_text'}
    args={'action':'publish_chat','post_text':body,'sources':['https://example.invalid/story'],'approval_message_id':mid}
    with owner.dispatch_context('',[],contract):
        result=bridge.linkedin(args,**opts(prepared),runner=publish)
        assert result['publish_performed'],result
        assert bridge.linkedin(args,**opts(prepared),runner=publish)['phase']=='ALREADY_PUBLISHED'
    assert len(calls)==1 and old.read_bytes()==old_bytes
    assert (root/('drafts/approved_20261029_thursday_'+consent.digest(body))/'linkedin_drafts.json').exists()

def test_chat_draft_requires_exact_presented_text(prepared):
    root,jobs,db,add,posts=prepared
    add('Different public text',role='assistant');mid=add('publish')
    contract={'workflow':'linkedin','action':'PUBLISH_NOW','latest_human_message':'publish','turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract),pytest.raises(ValueError):
        bridge.linkedin({'action':'publish_chat','post_text':'Invented unseen text','approval_message_id':mid},**opts(prepared))


def test_failed_prepare_is_not_repeated_in_same_turn(monkeypatch):
    import hermes_gmail_tools as tools
    calls=[]
    monkeypatch.setattr(bridge,'linkedin',lambda args: calls.append(args) or {'ok':False,'publish_performed':False})
    token=tools._FAILED_PREPARATIONS.set({})
    try:
        args={'action':'prepare','week_of':'2026-10-26'}
        assert not json.loads(tools.linkedin_workflow_tool(args))['ok']
        assert json.loads(tools.linkedin_workflow_tool(args))['repeated_stage_suppressed']
        assert len(calls)==1
    finally:tools._FAILED_PREPARATIONS.reset(token)

def test_chat_draft_blocked_review_never_calls_publisher(prepared,monkeypatch):
    import linkedin_weekly,linkedin_content_gen as gen,topic_reuse_check as topics
    from test_linkedin_state import personal
    root,jobs,db,add,posts=prepared;body='An unverified synthetic claim.'
    add('Here is a draft:\n```\n'+body+'\n```',role='assistant');mid=add('publish')
    monkeypatch.setattr(topics,'check_text',lambda *a,**k:{'blocked':False})
    monkeypatch.setattr(gen,'factcheck_post',lambda text,sources:{'verdict':'block','sources':sources})
    monkeypatch.setattr(state,'_personal_runner',lambda text,label:personal(text))
    contract={'workflow':'linkedin','action':'PUBLISH_NOW','latest_human_message':'publish','turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        result=bridge.linkedin({'action':'publish_chat','post_text':body,'sources':['https://example.invalid/story'],'approval_message_id':mid},**opts(prepared),runner=lambda *a,**k:pytest.fail('publisher must not run'))
    assert result['phase']=='APPROVED_BUT_BLOCKED' and not result['publish_performed']


def test_exact_incident_schedule_chat_and_arm(history,tmp_path,monkeypatch):
    import sqlite3,linkedin_weekly,linkedin_content_gen as gen,topic_reuse_check as topics
    from test_linkedin_state import gate,personal,scheduler_fixture
    root=tmp_path/'linkedin';root.mkdir();(root/'publishing-policy.json').write_text('{"schema_version":1,"enabled":true}')
    jobs=tmp_path/'jobs.json';jobs.write_text(json.dumps({'jobs':[{'id':j,'enabled':False} for j in state.JOB_IDS.values()]}))
    monkeypatch.setattr(state,'_scheduler_update',lambda jid,updates,**kw:scheduler_fixture(jobs)[1](jid,updates))
    db,add=history;body='A fresh personal post about a synthetic project.'
    add('Here is the draft:\n```\n'+body+'\n```',role='assistant');mid=add('Perfect approved publish at 8 am')
    stamp=datetime(2026,11,5,3,46,tzinfo=state.LONDON).timestamp()
    with sqlite3.connect(db) as c:c.execute('update messages set timestamp=? where id=?',(stamp,mid))
    monkeypatch.setattr(bridge,'current_approval_message',lambda **kw:mid)
    monkeypatch.setattr(topics,'check_text',lambda *a,**kw:{'blocked':False})
    monkeypatch.setattr(gen,'factcheck_post',lambda body,sources:gate(body))
    monkeypatch.setattr(state,'_personal_runner',lambda body,label:personal(body))
    now=datetime(2026,11,5,3,46,tzinfo=state.LONDON)
    contract={'workflow':'linkedin','action':'APPROVAL','latest_human_message':'Perfect approved publish at 8 am','turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        result=bridge.linkedin({'action':'publish_chat','post_text':body,'approval_message_id':1567746920628224051},root=root,jobs_path=jobs,db_path=db,now=now,generator=lambda body:b'\x89PNG\r\n\x1a\nsynthetic')
    assert result['phase']=='SCHEDULED',result
    slot=state.load_slots(root/'drafts/schedule.json')['2026-11-05']
    assert slot['publish_at']=='2026-11-05T08:00:00+00:00'
    assert slot['body_sha256']==consent.digest(body)
    assert state.job_state('thursday',jobs_path=jobs,root=root)['enabled']
    canonical=root/'drafts/approved_20261105_thursday/linkedin_drafts.json';canonical.parent.mkdir(parents=True)
    canonical.write_text(json.dumps({'post_text':'Different old draft','day':'thursday'}))
    view=state.week_status('2026-11-02',root=root,jobs_path=jobs,db_path=db)
    thursday=next(row for row in view['days'] if row['day']=='thursday')
    assert thursday['body_sha256']==consent.digest(body) and thursday['automatic_publish_armed']
    assert any(row['post_text']=='Different old draft' for row in thursday['alternatives'])
    assert not result['publish_performed']
    import linkedin_scheduled as scheduled
    calls=[]
    def fake_publish(command,**kw):
        calls.append(command);ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(json.dumps({'result':'published','body_sha256':consent.digest(body)})+'\n')
        return NS(returncode=0,stdout=json.dumps({'performed':True,'post_urn':'urn:test:scheduled'}))
    code,receipt=scheduled.run_day('thursday',dry_run=False,root=root,jobs_path=jobs,db_path=db,now=datetime(2026,11,5,8,0,tzinfo=state.LONDON),runner=fake_publish)
    assert code==0 and receipt['publish_performed'] and len(calls)==1
    code,receipt=scheduled.run_day('thursday',dry_run=False,root=root,jobs_path=jobs,db_path=db,now=datetime(2026,11,5,8,1,tzinfo=state.LONDON),runner=fake_publish)
    assert receipt['phase']=='ALREADY_PUBLISHED' and len(calls)==1

def test_clock_without_day_is_today_not_immediate():
    parsed=interpret('Perfect approved publish at 8 am',now=datetime(2026,11,5,3,46,tzinfo=state.LONDON))
    assert parsed['approved'] and not parsed['publish_now'] and parsed['publish_at']=='2026-11-05T08:00:00+00:00'


def test_retry_uses_previous_exact_authenticated_schedule(history,monkeypatch):
    import sqlite3
    db,add=history;body='A specific approved post.'
    add('Here is the draft:\n```\n'+body+'\n```',role='assistant')
    approved=add('Perfect approved publish at 8 am')
    with sqlite3.connect(db) as c:c.execute('update messages set timestamp=? where id=?',(datetime(2026,11,5,3,46,tzinfo=state.LONDON).timestamp(),approved))
    add('The previous attempt was blocked.',role='assistant')
    current=add('Try again\n\nEarlier explanation was pasted here.')
    monkeypatch.setattr(bridge,'current_approval_message',lambda **kwargs:current)
    contract={'workflow':'linkedin','latest_human_message':'Try again\n\nEarlier explanation was pasted here.','turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        mid,receipt=bridge.retry_chat_approval(body,db_path=db)
    assert mid==approved and receipt['receipt']['preferences']['publish_at']=='2026-11-05T08:00:00+00:00'
    with owner.dispatch_context('',[],contract),pytest.raises(ValueError):bridge.retry_chat_approval('Different text',db_path=db)

def test_retry_does_not_skip_intervening_owner_cancellation(history,monkeypatch):
    db,add=history;body='A specific approved post.'
    add(body,role='assistant');add('Perfect approved publish at 8 am');add('Cancel this post');current=add('Try again')
    monkeypatch.setattr(bridge,'current_approval_message',lambda **kwargs:current)
    with owner.dispatch_context('',[],{'workflow':'linkedin','latest_human_message':'Try again','turn_origin':'human_text'}),pytest.raises(ValueError):bridge.retry_chat_approval(body,db_path=db)


def test_approve_with_discord_platform_id_resolves_authenticated_current(prepared,monkeypatch):
    root,jobs,db,add,posts=prepared;body=posts['thursday']['post_text']
    add('Thursday draft:\n```\n'+body+'\n```',role='assistant');mid=add('Approved publish')
    monkeypatch.setattr(bridge,'current_approval_message',lambda **kw:mid)
    args=action_args(prepared);args['approval_message_id']=1567760970267492483
    result=bridge.linkedin(args,**opts(prepared),generator=lambda body:b'\x89PNG\r\n\x1a\nsynthetic')
    assert result['approval']['owner_approved']
    assert result['approval']['body_sha256']==consent.digest(body)


def test_image_failure_falls_back_to_text_only_and_schedules(prepared):
    root,jobs,db,add,posts=prepared;body=posts['thursday']['post_text']
    add(body,role='assistant');mid=add('Perfect approved for Thursday at 8 am')
    args=action_args(prepared);args['approval_message_id']=mid
    def broken_image(body):raise RuntimeError('provider unavailable')
    result=bridge.linkedin(args,**opts(prepared),generator=broken_image,now=datetime(2026,10,27,12,tzinfo=state.LONDON))
    assert result['image']['phase']=='IMAGE_UNAVAILABLE_TEXT_ONLY'
    assert result['image']['reason'] and result['plan']['planned']
    path=Path(result['approval']['artifact']);doc=state.read(path)
    assert doc['image_required'] is False and doc['owner_approval']['body_sha256']==consent.digest(body)


def test_new_post_ids_distinguish_same_text_and_bind_scheduled_artifact(history,tmp_path,monkeypatch):
    from test_linkedin_state import gate,personal,scheduler_fixture
    db,add=history;body='Same synthetic text for two separate posts.'
    add(body,role='assistant');mid=add('Approved')
    root=tmp_path/'linkedin';root.mkdir();(root/'publishing-policy.json').write_text('{"schema_version":1,"enabled":true}')
    jobs=tmp_path/'jobs.json';jobs.write_text(json.dumps({'jobs':[{'id':j,'enabled':False} for j in state.JOB_IDS.values()]}))
    monkeypatch.setattr(state,'_scheduler_update',lambda jid,updates,**kw:scheduler_fixture(jobs)[1](jid,updates))
    first=state.capture(body,'2026-10-29',mid,root=root,db_path=db)
    second=state.capture(body,'2026-10-29',mid,root=root,db_path=db,distinct=True)
    assert len(first['post_id'])==32 and first['post_id']!=second['post_id']
    for record in (first,second):
        path=Path(record['artifact']);doc=state.read(path)
        doc.update(news_fact_gate=gate(body),personal_fact_gate=personal(body),image_required=False,requested_publish_at='2026-10-29T08:00:00+00:00')
        path.write_text(json.dumps(doc))
    state.plan_slot(second['artifact'],'2026-10-29',root=root,db_path=db,jobs_path=jobs,now=datetime(2026,10,27,12,tzinfo=state.LONDON))
    opts={'week_of':'2026-10-26','root':root,'db_path':db,'jobs_path':jobs}
    assert bridge._selected('thursday',None,post_id=second['post_id'],**opts)['artifact']==second['artifact']
    assert bridge._selected('thursday',None,post_id=first['post_id'],**opts)['artifact']==first['artifact']
    assert bridge._selected(None,None,post_id=first['post_id'],**opts)['artifact']==first['artifact']
    assert bridge._selected(None,None,post_id=second['post_id'],**opts)['artifact']==second['artifact']
    with pytest.raises(ValueError):bridge._selected('thursday',None,post_id='f'*32,**opts)
    slots=state.load_slots(root/'drafts/schedule.json');assert slots['2026-10-29']['post_id']==second['post_id']
    slots['2026-10-29']['post_id']=first['post_id']
    (root/'drafts/schedule.json').write_text(json.dumps({'schema_version':2,'timezone':'Europe/London','slots':slots}))
    assert not state.inspect_artifact(second['artifact'],root=root,db_path=db,jobs_path=jobs)['slot_matches']

def test_existing_idless_capture_is_not_migrated(history,tmp_path):
    db,add=history;body='Legacy approved post';add(body,role='assistant');mid=add('Approved')
    root=tmp_path/'linkedin';path=root/'drafts/approved_20261029_thursday/linkedin_drafts.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'post_text':body,'day':'thursday'}))
    result=state.capture(body,'2026-10-29',mid,root=root,db_path=db)
    assert result['post_id'] is None and 'post_id' not in state.read(path)


def test_chat_draft_gets_id_before_approval_and_keeps_it(history,tmp_path):
    db,add=history;root=tmp_path/'linkedin';body='New unapproved chat draft.'
    contract={'workflow':'linkedin','turn_origin':'human_text','latest_human_message':'Draft a post'}
    with owner.dispatch_context('',[],contract):
        draft=bridge.linkedin({'action':'draft_chat','post_text':body,'target_date':'2026-10-29'},root=root,db_path=db)
        repeat=bridge.linkedin({'action':'draft_chat','post_text':body,'target_date':'2026-10-29'},root=root,db_path=db)
    assert draft['post_id']==repeat['post_id'] and not draft['owner_approved']
    add(body,role='assistant');mid=add('Approved')
    approved=state.capture(body,'2026-10-29',mid,root=root,db_path=db,distinct=True)
    assert approved['post_id']==draft['post_id'] and approved['owner_approved']
    assert bridge._selected(None,None,post_id=draft['post_id'],root=root,db_path=db)['artifact']==draft['artifact']


def test_chat_revision_preserves_post_id_and_requires_new_text_approval(history,tmp_path):
    db,add=history;root=tmp_path/'linkedin';contract={'workflow':'linkedin','turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        first=bridge.linkedin({'action':'draft_chat','post_text':'First version','target_date':'2026-10-29'},root=root,db_path=db)
        revised=bridge.linkedin({'action':'draft_chat','post_id':first['post_id'],'post_text':'Changed version'},root=root,db_path=db)
    assert revised['post_id']==first['post_id'] and revised['artifact']==first['artifact']
    assert revised['body_sha256']!=first['body_sha256']
    assert bridge._selected(None,None,post_id=first['post_id'],root=root,db_path=db)['post_text']=='Changed version'
    add('Changed version',role='assistant');mid=add('Approved')
    result=state.capture('Changed version','2026-10-29',mid,root=root,db_path=db,post_id=first['post_id'],artifact_path=first['artifact'])
    assert result['post_id']==first['post_id'] and result['owner_approved']
    with owner.dispatch_context('',[],contract),pytest.raises(ValueError):
        bridge.linkedin({'action':'draft_chat','post_id':first['post_id'],'post_text':'Unapproved rewrite'},root=root,db_path=db)
