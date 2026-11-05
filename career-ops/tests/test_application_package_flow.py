import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
import application_package_flow as flow
import application_package_state as package
import hermes_cv_compiler_guard as guard
import hermes_cover_tool as cover_module

REAL_CV_VERIFIED=guard.verified_attachment
REAL_COVER_VERIFIED=cover_module.verified

JD = ('Example Ltd\nGraduate Security Analyst\nJob requisition R123\nThe role\n'
      'Responsibilities: investigate security alerts, maintain documentation and learn incident triage. '
      'Requirements: graduates in information security are welcome. No prior employment is required. ' * 3)


def valid_plan():
    return {'outcome':'READY_TO_COMPILE','company':'Example Ltd','company_evidence':'Example Ltd',
            'role':'Graduate Security Analyst','role_evidence':'Graduate Security Analyst',
            'short_role':'Security Analyst','job_id':'R123',
            'paragraphs':['I am applying for the graduate role.','My studies provide relevant foundations.',
                          'I can explain my academic project work.','I would welcome learning from the team.',
                          'Thank you for considering my application.']}


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(package,'ROOT',tmp_path/'packages')
    monkeypatch.setattr(guard,'verified_attachment',lambda path:True)
    import hermes_cover_tool as cover
    monkeypatch.setattr(cover,'verified',lambda path:True)
    import student_eligibility
    monkeypatch.setattr(student_eligibility,'current_student_confirmed',lambda:False)
    import workflow_routing
    monkeypatch.setattr(workflow_routing,'complete_text',lambda *a,**k:pytest.fail('Unstubbed provider call'))


def state():
    return {'session_id':'fixture','request_id':'r','cv_active':True,'intake':{'jd':JD,'source':'fixture'}}


def install(monkeypatch,old=None):
    async def no_narrator(*args,**kwargs):pytest.fail('A production application must not depend on narrator tool choice')
    class Turn:_run_agent=old or no_narrator
    class Media:
        async def send_document(self,*args,**kwargs):pytest.fail('No live document delivery')
    guard.install_runtime(NS(_current_max_iterations=lambda:150),Turn,Media)
    return Turn


def compilers(monkeypatch,tmp_path,fail_cv=False,fail_cover=False):
    calls=[]
    def build(kind,args):
        calls.append(kind)
        saved=guard.JOB.get()
        assert package.load(saved['session_id'])['phase']==kind.upper()+'_COMPILING'
        if (kind=='cv' and fail_cv) or (kind=='cover' and fail_cover):
            result={'status':'FAIL','reason':'fixture provider timeout'}
        else:
            pdf=tmp_path/(kind+'.pdf');pdf.write_bytes(b'private fixture '+kind.encode())
            result={'status':'PASS','verified_pdf':str(pdf),'compiler_pdf':str(pdf)}
        package.record(saved,kind,args,result)
        return json.dumps(result)
    monkeypatch.setattr(guard,'compile_tool',lambda args:build('cv',args))
    import hermes_cover_tool as cover
    monkeypatch.setattr(cover,'cover_tool',lambda args:build('cover',args))
    return calls


def test_employer_words_cannot_authorize_cv_production():
    text='[Content of message.txt]:\n'+JD+'\nWe build platforms. Candidates selected after CV review.'
    assert not guard.cv_request(text)
    assert flow.prepare(text,[],{}, {}) is None
    assert not guard.cv_request(JD+'\nWe build platforms. Candidates selected after CV review.')


def test_eligibility_question_does_not_build_from_existing_active_session():
    message='Check my eligibility\n[Content of JD.txt]:\n'+JD
    assert flow.prepare(message,[],{},state()) is None


def test_state_write_failure_never_invokes_planner_or_compiler(monkeypatch,tmp_path):
    calls=compilers(monkeypatch,tmp_path)
    monkeypatch.setattr(package,'save',lambda state:(_ for _ in ()).throw(OSError('fixture')))
    result=flow.dispatch(state())
    assert result['application_status']=='STATE_FAILED' and not calls


def test_explicit_request_dispatches_both_stages_without_narrator(monkeypatch,tmp_path):
    observed=[]
    def planner(s):
        observed.append(package.load('fixture'))
        return valid_plan()
    monkeypatch.setattr(flow,'plan',planner)
    calls=compilers(monkeypatch,tmp_path)
    Turn=install(monkeypatch)
    result=asyncio.run(Turn()._run_agent('Generate my CV and cover letter\n[Content of JD.txt]:\n'+JD,'',[],None,'fixture'))
    assert calls==['cv','cover'] and result['application_status']=='VERIFIED_READY'
    assert result['final_response'].count('MEDIA:')==2 and not result['failed']
    assert result['agent_persisted'] is False
    assert observed[0]['intake']['jd']==JD.strip()
    assert observed[0]['intake']['jd_sha256']==hashlib.sha256(JD.strip().encode()).hexdigest()
    assert package.load('fixture')['phase']=='DOCUMENTS_READY'


def test_current_student_requirement_is_actionable_not_generic(monkeypatch,tmp_path):
    calls=compilers(monkeypatch,tmp_path)
    monkeypatch.setattr(flow,'plan',lambda s:pytest.fail('Must check student requirement first'))
    Turn=install(monkeypatch)
    jd=JD+'\nWe can only consider applicants enrolled on a sandwich degree programme with an expected graduation in 2029.'
    result=asyncio.run(Turn()._run_agent('Generate CV and cover letter\n[Content of JD.txt]:\n'+jd,'',[],None,'fixture'))
    assert result['application_status']=='OWNER_INPUT_REQUIRED' and not result['failed']
    assert '2029' in result['final_response'] and 'not established' in result['final_response']
    assert 'not completed within' not in result['final_response'] and not calls
    assert package.load('fixture')['eligibility']['outcome']=='OWNER_INPUT_REQUIRED'


def test_explicit_owner_student_answer_resumes_same_saved_application(monkeypatch,tmp_path):
    monkeypatch.setattr(flow,'plan',lambda s:valid_plan())
    calls=compilers(monkeypatch,tmp_path)
    Turn=install(monkeypatch)
    jd=JD+'\nWe can only consider applicants enrolled on a sandwich degree programme with an expected graduation in 2029.'
    first=asyncio.run(Turn()._run_agent('Generate my CV and cover letter\n[Content of JD.txt]:\n'+jd,'',[],None,'fixture'))
    saved=package.load('fixture')
    assert first['application_status']=='OWNER_INPUT_REQUIRED' and not calls
    second=asyncio.run(Turn()._run_agent('I am currently enrolled in a sandwich Cyber Security degree, graduating in 2029.','',[],None,'fixture'))
    assert calls==['cv','cover'] and second['application_status']=='VERIFIED_READY'
    assert package.load('fixture')['request_id']==saved['request_id']


def test_missing_jd_asks_for_input_without_claiming_build(monkeypatch):
    Turn=install(monkeypatch)
    result=asyncio.run(Turn()._run_agent('Generate my CV and cover letter','',[],None,'fixture'))
    assert result['application_status']=='OWNER_INPUT_REQUIRED'
    assert 'no saved job description' in result['final_response'] and not result['failed']


def test_uploaded_pdf_is_used_before_network_fetch(monkeypatch,tmp_path):
    import pymupdf
    cache=tmp_path/'documents';cache.mkdir()
    pdf=cache/'jd.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page();page.insert_textbox((30,30,550,700),JD)
        doc.save(pdf)
    monkeypatch.setattr(flow,'DOCUMENT_ROOT',cache)
    message='[The user sent a document. It is saved at: '+str(pdf)+'.]\nGenerate my CV and cover letter'
    intake=flow.prepare(message,[],{},state())
    assert intake['source']=='uploaded_document' and 'Graduate Security Analyst' in intake['jd']
    outside=tmp_path/'private.txt';outside.write_text(JD)
    assert flow.prepare('Generate my CV\n[The user sent a document. It is saved at: '+str(outside)+'.]',[],{}, {})['source']=='owner_request'


def test_provider_failure_is_saved_and_explained(monkeypatch,tmp_path):
    calls=compilers(monkeypatch,tmp_path)
    def broken(s):raise TimeoutError('private provider body must not be exposed')
    monkeypatch.setattr(flow,'plan',broken)
    token=guard.JOB.set(state())
    try:result=flow.dispatch(guard.JOB.get())
    finally:guard.JOB.reset(token)
    assert result['application_status']=='PLANNING_FAILED' and result['failed']
    assert 'Application planning stopped:' in result['final_response'] and 'private provider' not in result['final_response']
    assert package.load('fixture')['phase']=='PLANNING_FAILED' and not calls


def test_cv_failure_does_not_block_cover_then_retry_only_cv(monkeypatch,tmp_path):
    plans=[]
    monkeypatch.setattr(flow,'plan',lambda s:(plans.append(1) or valid_plan()))
    calls=compilers(monkeypatch,tmp_path,fail_cv=True)
    Turn=install(monkeypatch)
    first=asyncio.run(Turn()._run_agent('Generate my CV and cover letter\n[Content of JD.txt]:\n'+JD,'',[],None,'fixture'))
    assert calls==['cv','cover'] and first['application_status']=='PARTIAL'
    assert first['final_response'].count('MEDIA:')==1
    calls=compilers(monkeypatch,tmp_path)
    second=asyncio.run(Turn()._run_agent('try again','',[],None,'fixture'))
    assert calls==['cv'] and plans==[1]
    assert second['application_status']=='VERIFIED_READY'


def test_legacy_empty_retry_recovers_actual_jd_before_planning(monkeypatch,tmp_path):
    package.save({'session_id':'fixture','request_id':'legacy','cv_active':True})
    monkeypatch.setattr(flow,'plan',lambda s:valid_plan())
    calls=compilers(monkeypatch,tmp_path)
    Turn=install(monkeypatch)
    result=asyncio.run(Turn()._run_agent('try again','',[{'role':'user','content':JD}],None,'fixture'))
    assert calls==['cv','cover'] and result['application_status']=='VERIFIED_READY'
    assert package.load('fixture')['intake']['source']=='history_recovery'


@pytest.mark.parametrize('value',[{}, {'outcome':'READY_TO_COMPILE'}, {'outcome':'INELIGIBLE'}])
def test_invalid_saved_plan_never_reaches_compilers(value,monkeypatch,tmp_path):
    s=state();s['plan']=value
    monkeypatch.setattr(flow,'plan',lambda s:value)
    calls=compilers(monkeypatch,tmp_path)
    token=guard.JOB.set(s)
    try:result=flow.dispatch(s)
    finally:guard.JOB.reset(token)
    assert not calls and result['application_status']=='PLANNING_FAILED'


def test_saved_jd_mismatch_cannot_reuse_plan(monkeypatch,tmp_path):
    s=state();s['intake']['jd_sha256']='wrong';s['plan']=valid_plan()
    calls=compilers(monkeypatch,tmp_path)
    token=guard.JOB.set(s)
    try:result=flow.dispatch(s)
    finally:guard.JOB.reset(token)
    assert not calls and 'hash changed' in result['final_response']


def test_transient_windows_checkpoint_sharing_error_retries(monkeypatch):
    original=package.os.replace
    calls=[]
    def replace(source,target):
        calls.append(1)
        if len(calls)<3:
            error=PermissionError('fixture sharing error');error.winerror=5
            raise error
        return original(source,target)
    monkeypatch.setattr(package.os,'replace',replace)
    package.save(state())
    assert len(calls)==3 and package.load('fixture')['request_id']=='r'


def test_persistent_windows_checkpoint_error_remains_failure(monkeypatch):
    def replace(*args):
        error=PermissionError('fixture sharing error');error.winerror=5
        raise error
    monkeypatch.setattr(package.os,'replace',replace)
    with pytest.raises(PermissionError):package.save(state())
    assert not list(package.ROOT.glob('*.tmp'))


@pytest.mark.skipif(__import__('os').name!='nt',reason='Windows sharing semantics')
def test_real_windows_reader_releases_before_checkpoint_retry():
    import ctypes,threading
    from ctypes import wintypes as w
    package.save(state())
    path=package.ROOT/(hashlib.sha256(b'fixture').hexdigest()+'.json')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0,None)
    assert handle not in (None,ctypes.c_void_p(-1).value)
    timer=threading.Timer(.09,lambda:kernel.CloseHandle(handle))
    timer.start()
    try:
        changed=state();changed['phase']='DOCUMENTS_READY'
        package.save(changed)
        assert package.load('fixture')['phase']=='DOCUMENTS_READY'
    finally:timer.join()


def test_plaintext_clarification_survives_core_output_transform(monkeypatch):
    import logging
    from agent import turn_finalizer as core
    monkeypatch.setattr(core,'_invoke_hook_safely',lambda name,logger,**kw:[guard.transform_output(**kw)])
    s=state();token=guard.JOB.set(s)
    try:
        result,changed,original=core.apply_llm_output_transform(NS(session_id='fixture',model='fixture'),
            'Please confirm your current student eligibility.',turn_id='fixture',logger=logging.getLogger(__name__))
    finally:guard.JOB.reset(token)
    assert changed and original in result and package.load('fixture')['diagnostic']==original


def test_finished_foreground_context_does_not_restrict_memory_or_rewrite_output():
    s=state();s['foreground_complete']=True;token=guard.JOB.set(s)
    try:
        assert guard.pre_tool('memory',{'action':'add'}) is None
        assert guard.transform_output('Background memory review completed.') is None
    finally:guard.JOB.reset(token)


def test_parallel_duplicate_build_is_declined_without_provider(monkeypatch):
    from run_lock import acquire_run_lock
    s=state();key=hashlib.sha256(b'fixture').hexdigest()
    lock=acquire_run_lock(package.ROOT/'locks'/(key+'.lock'))
    try:result=flow.dispatch(s)
    finally:lock.close()
    assert result['application_status']=='ALREADY_RUNNING' and not result['failed']


def test_structured_planner_uses_router_and_complete_owner_references(monkeypatch):
    import hermes_owner_context as owner
    import workflow_routing
    seen={}
    monkeypatch.setattr(owner,'retrieve',lambda message,**kw:('private reference fixture', [{'file':name,'complete':True} for name in kw['required']]))
    monkeypatch.setattr(guard,'master_tool',lambda args:'{"verified_facts":[]}')
    def complete(messages,**kwargs):
        seen.update(kwargs);seen['messages']=messages
        return NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps(valid_plan())))]),{'status':'OFFLINE_TEST_ROUTED'}
    monkeypatch.setattr(workflow_routing,'complete_text',complete)
    s=state();s['deadline']=__import__('time').monotonic()+300;s['intake']['jd_sha256']=hashlib.sha256(JD.encode()).hexdigest()
    assert flow.plan(s)['outcome']=='READY_TO_COMPILE'
    assert seen['workflow']=='career.application.plan'
    assert {x['file'] for x in package.load('fixture')['owner_reference_evidence']}==set(owner.FILES)
    assert package.load('fixture')['routing']['status']=='OFFLINE_TEST_ROUTED'


def test_dispatch_real_renderers_then_restart_reuses_verified_pdfs(monkeypatch,tmp_path):
    from role_family_acceptance import offline_selection
    import cv_workflow
    monkeypatch.setattr(guard,'verified_attachment',REAL_CV_VERIFIED)
    monkeypatch.setattr(cover_module,'verified',REAL_COVER_VERIFIED)
    monkeypatch.setattr(guard,'OUTPUT_ROOT',tmp_path/'cv')
    monkeypatch.setattr(guard,'EXPORT_ROOT',tmp_path/'cv-exports')
    monkeypatch.setattr(guard,'generate',offline_selection)
    monkeypatch.setattr(cover_module,'ROOT',tmp_path/'cover')
    monkeypatch.setattr(cover_module,'EXPORT_ROOT',tmp_path/'cover-exports')
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**k:{'available':True,'exit_code':0})
    def render(command,**kwargs):
        cover_module.build(command[-1])
        return NS(returncode=0)
    monkeypatch.setattr(cover_module.subprocess,'run',render)
    monkeypatch.setattr(flow,'plan',lambda s:valid_plan())
    Turn=install(monkeypatch)
    first=asyncio.run(Turn()._run_agent('Generate my CV and cover letter\n[Content of JD.txt]:\n'+JD,'',[],None,'fixture'))
    assert first['application_status']=='VERIFIED_READY',first
    saved=package.load('fixture')
    assert len(package.accepted(saved))==2
    import pymupdf
    for path in package.accepted(saved).values():
        with pymupdf.open(path) as pdf:
            assert pdf.page_count==1
    monkeypatch.setattr(guard,'compile_tool',lambda *a,**k:pytest.fail('Restart must reuse CV'))
    monkeypatch.setattr(cover_module,'cover_tool',lambda *a,**k:pytest.fail('Restart must reuse cover'))
    monkeypatch.setattr(flow,'plan',lambda *a,**k:pytest.fail('Restart must reuse plan'))
    # The saved JSON is the only shared state, not the earlier in-memory state.
    second=asyncio.run(Turn()._run_agent('try again','',[],None,'fixture'))
    assert second['application_status']=='VERIFIED_READY' and second['final_response'].count('MEDIA:')==2


def test_actual_gateway_persists_direct_dispatch_without_agent_flush(monkeypatch):
    from gateway.run_turn import GatewayTurnMixin
    saved=[]
    class Store:
        async def append_to_transcript(self,sid,row,**kwargs):saved.append((row,kwargs))
        async def update_session(self,*args,**kwargs):pass
    async def refresh(*args):pass
    stub=NS(async_session_store=Store(),_session_db=object(),
            _hmwa_user_transcript_entry=lambda *args:{'role':'user','content':'fixture'},
            _refresh_agent_cache_message_count=refresh)
    dispatch_result=flow.result({'phase':'OWNER_INPUT_REQUIRED','blocked_reason':'Provide the JD.'})
    asyncio.run(GatewayTurnMixin._hmwa_persist_turn_transcript(stub,event=NS(message_id='fixture',internal=False),
        source=NS(platform=None),session_entry=NS(session_id='fixture',session_key='fixture'),session_key='fixture',
        agent_result=dispatch_result,agent_messages=[],prepared=NS(history=[{'role':'user','content':'old'}]),
        response=dispatch_result['final_response'],agent_failed_early=False,hidden_reasoning_incomplete=False,
        is_context_overflow_failure=False))
    assert len(saved)==2 and all(entry[1]['skip_db'] is False for entry in saved)
    assert saved[-1][0]['content']==dispatch_result['final_response']

import application_continuation as continuation


@pytest.mark.parametrize('message',["its okay draft","it's okay, draft","go ahead","draft anyway","okay proceed","just draft it","write both please"])
def test_document_permission_resumes_warning_without_inventing_eligibility(monkeypatch,tmp_path,message):
    monkeypatch.setattr(flow,'plan',lambda s:valid_plan())
    calls=compilers(monkeypatch,tmp_path)
    Turn=install(monkeypatch)
    jd=JD+'\nWe can only consider applicants enrolled on a sandwich degree programme with an expected graduation in 2029.'
    first=asyncio.run(Turn()._run_agent('Generate CV and cover letter\n[Content of JD.txt]:\n'+jd,'',[],None,'fixture'))
    assert first['application_status']=='OWNER_INPUT_REQUIRED' and not calls
    before=package.load('fixture')
    result=asyncio.run(Turn()._run_agent(message,'',[],None,'fixture'))
    saved=package.load('fixture')
    assert calls==['cv','cover'] and result['application_status']=='VERIFIED_READY'
    assert saved['request_id']==before['request_id']
    assert saved['eligibility']['outcome']=='UNCONFIRMED_DRAFT_AUTHORIZED'
    assert saved['intake']['document_authorization']['eligibility_confirmed'] is False
    assert 'remain unconfirmed' in result['final_response']


def test_unrelated_turn_preserves_checkpoint_and_does_not_draft(monkeypatch):
    calls=[]
    async def narrator(*a,**k):calls.append(True);return {'final_response':'other task'}
    Turn=install(monkeypatch,narrator)
    package.save(state())
    before=package.load('fixture')
    asyncio.run(Turn()._run_agent('What is the weather?','',[],None,'fixture'))
    assert calls and package.load('fixture')==before
    assert continuation.resume('go ahead',[{'role':'user','content':'What is the weather?'}],before) is None


def test_cancel_preserves_intake_but_deactivates(monkeypatch):
    package.save(state());Turn=install(monkeypatch)
    result=asyncio.run(Turn()._run_agent('cancel this application','',[],None,'fixture'))
    assert result['application_status']=='CANCELLED' and package.load('fixture')=={}
    stored=json.loads(next(package.ROOT.glob('*.json')).read_text())
    assert not stored['active'] and stored['intake']['jd']==JD


def test_recovers_legacy_lost_intake_only_from_latest_job():
    history=[{'role':'user','content':'Generate CV and cover letter\n[Content of JD.txt]:\n'+JD},
             {'role':'assistant','content':'Owner input required'}, {'role':'user','content':'its okay draft'}]
    intake=continuation.resume('draft anyway',history,{})
    assert intake and intake['jd']==JD.strip() and continuation.draft_authorized(intake)
    assert continuation.resume('draft anyway',history+[{'role':'user','content':'Research LinkedIn news'}],{}) is None
    intake['jd']+=' changed job'
    assert not continuation.draft_authorized(intake)


@pytest.mark.parametrize('message',["don't draft","why can't you draft?","publish it","send email please","cancel","draft LinkedIn please","its not okay draft","draft new posts please"])
def test_other_intents_cannot_authorize_documents(message):
    assert continuation.resume(message,[],state()) is None


def test_draft_anyway_does_not_bypass_mandatory_clearance(monkeypatch,tmp_path):
    calls=compilers(monkeypatch,tmp_path)
    saved=state();saved['intake']['jd']+='\nApplicants must hold security clearance.'
    saved['intake']=continuation.resume('draft anyway',[],saved)
    result=flow.dispatch(saved)
    assert result['application_status']=='INELIGIBLE' and not calls
    assert 'must hold security clearance' in result['final_response']


def test_negated_clearance_does_not_block_drafting(monkeypatch,tmp_path):
    monkeypatch.setattr(flow,'plan',lambda s:valid_plan())
    calls=compilers(monkeypatch,tmp_path)
    Turn=install(monkeypatch)
    result=asyncio.run(Turn()._run_agent('Generate CV and cover letter\n[Content of JD.txt]:\n'+JD+'\nSecurity clearance is not required.','',[],None,'fixture'))
    assert result['application_status']=='VERIFIED_READY' and calls==['cv','cover']


def test_short_permission_cannot_reuse_saved_intake_after_different_jd():
    history=[{'role':'user','content':'[Content of JD.txt]:\n'+JD+'\nDifferent requisition R999'}]
    assert continuation.resume('go ahead',history,state()) is None


def test_legacy_retry_recovers_jd_without_inventing_drafting_permission():
    history=[{'role':'user','content':'Generate CV and cover letter\n[Content of JD.txt]:\n'+JD}]
    intake=continuation.resume('try again',history,{})
    assert intake['jd']==JD.strip()
    assert not continuation.draft_authorized(intake)
    assert continuation.resume('try again',history+[{'role':'user','content':'Research LinkedIn news'}],state()) is None


def test_generic_retry_after_other_task_does_not_dispatch_saved_application(monkeypatch):
    package.save(state())
    calls=[]
    async def narrator(*a,**k):calls.append(True);return {'final_response':'other task'}
    Turn=install(monkeypatch,narrator)
    result=asyncio.run(Turn()._run_agent('try again','',[{'role':'user','content':'What is the weather?'}],None,'fixture'))
    assert calls and result['final_response']=='other task'
    assert package.load('fixture')['intake']['jd']==JD
