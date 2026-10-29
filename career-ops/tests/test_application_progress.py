import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
import application_package_state as package
import hermes_cv_compiler_guard as guard
import hermes_cover_tool as cover


@pytest.fixture(autouse=True)
def private_packages(tmp_path,monkeypatch):
    monkeypatch.setattr(package,'ROOT',tmp_path/'packages')


def install(run):
    runtime=NS(_current_max_iterations=lambda:150)
    class Turn: _run_agent=run
    class Media:
        async def send_document(self,*a,**k):return NS(success=True)
    guard.install_runtime(runtime,Turn,Media)
    return Turn,runtime


def test_retry_guard_engaged_before_first_tool_and_blocks_original_loop():
    async def run(self,*args,**kwargs):
        assert guard.active_job()
        assert guard.pre_tool('execute_code',{'code':'print("BUILDING CV AND COVER LETTER NOW")'})['action']=='block'
        assert guard.pre_tool('read_file',{'path':'JD.txt'}) is None
        assert guard.pre_tool('read_file',{'path':'JD.txt'})['action']=='block'
        return {'final_response':'Building now','failed':True}
    Turn,_=install(run)
    response=asyncio.run(Turn()._run_agent('Try again','',[{'role':'user','content':'Build my CV and cover letter'}],None,'application-a'))
    assert 'Repeated preparation' in response['final_response']
    assert 'MEDIA:' not in response['final_response']


def test_unrelated_session_and_intervening_task_do_not_inherit_job():
    package.save({'session_id':'one','cv_active':True,'request_id':'a'})
    async def run(self,*a,**k):return {'active':bool(guard.active_job())}
    Turn,_=install(run)
    assert not asyncio.run(Turn()._run_agent('Try again','',[],None,'two'))['active']
    asyncio.run(Turn()._run_agent('What is the weather?','',[],None,'one'))
    assert not package.load('one')


def test_both_receipts_recover_on_empty_history_without_llm_or_compiler(monkeypatch):
    monkeypatch.setattr(package,'source_matches',lambda result:True)
    monkeypatch.setattr(guard,'verified_attachment',lambda path:path=='verified-cv.pdf')
    monkeypatch.setattr(cover,'verified',lambda path:path=='verified-cover.pdf')
    package.save({'session_id':'one','cv_active':True,'request_id':'a','results':{
        'cv':{'status':'PASS','verified_pdf':'verified-cv.pdf'},'cover':{'status':'PASS','verified_pdf':'verified-cover.pdf'}}})
    async def run(*a,**k):pytest.fail('already-verified package must not regenerate')
    Turn,_=install(run)
    response=asyncio.run(Turn()._run_agent('Continue','',[],None,'one'))
    assert response['final_response'].count('MEDIA:')==2
    assert response['application_delivery']=='pending'
    assert not response['failed']


def test_exhausted_summary_uses_receipts_without_provider(monkeypatch):
    monkeypatch.setattr(package,'source_matches',lambda result:True)
    from agent import chat_completion_helpers as helpers
    monkeypatch.setattr(guard,'verified_attachment',lambda path:True)
    async def run(self,*a,**k):
        guard.JOB.get()['results']={'cv':{'status':'PASS','verified_pdf':'verified-cv.pdf'}}
        response=helpers.handle_max_iterations(NS(),[],150)
        assert 'MEDIA:verified-cv.pdf' in response
        assert 'Cover letter: incomplete' in response
        return {'final_response':'misleading generic summary','failed':True}
    Turn,_=install(run)
    result=asyncio.run(Turn()._run_agent('Build my CV and cover letter','',[],None,'one'))
    assert 'misleading generic' not in result['final_response']
    assert not result['failed'] # permits verified partial attachment; explicit partial outcome remains
    assert result['application_status']=='PARTIAL'


def test_stale_export_not_attached(monkeypatch):
    monkeypatch.setattr(guard,'verified_attachment',lambda path:False)
    state={'results':{'cv':{'status':'PASS','verified_pdf':'corrupt.pdf'}}}
    assert 'MEDIA:' not in package.render(state)


def test_large_skill_payload_removed_but_user_jd_and_tool_receipt_retained():
    history=[{'role':'user','content':'JD plus owner facts'},
        {'role':'assistant','tool_calls':[{'id':'s','function':{'name':'skill_view'}}]},
        {'role':'tool','tool_call_id':'s','content':'x'*73015},
        {'role':'tool','tool_call_id':'cv','name':'career_cv_compile','content':'PASS receipt'}]
    cleaned=package.trim_history(history)
    assert cleaned==[history[0],history[3]]


def test_original_read_print_history_repetition_is_removed_without_losing_latest_jd():
    code='with open("JD.txt", "r", encoding="utf-8") as f:\n    jd=f.read()\nprint(jd)'
    history=[]
    for i in range(150):
        history.extend([{'role':'assistant','tool_calls':[{'id':str(i),'function':{'name':'execute_code','arguments':json.dumps({'code':code})}}]},
                        {'role':'tool','tool_call_id':str(i),'content':'JD content'}])
    result=package.trim_history(history)
    assert len(result)==2 and result[-1]['content']=='JD content'
    assert package.readonly_cell({'function':{'name':'execute_code','arguments':{'code':'with open("a", "w") as f: f.write("x")'}}}) is None


def test_native_finalizer_persists_verified_result_before_message_write(monkeypatch):
    import logging
    from agent import turn_finalizer as core
    monkeypatch.setattr(core,'_invoke_hook_safely',lambda name,logger,**kw:[guard.transform_output(**kw)])
    monkeypatch.setattr(guard,'verified_attachment',lambda path:True)
    monkeypatch.setattr(package,'source_matches',lambda result:True)
    token=guard.JOB.set({'cv_active':True,'results':{'cv':{'status':'PASS','verified_pdf':'verified.pdf'}}})
    try:
        result,changed,_=core.apply_llm_output_transform(NS(session_id='one',model='fixture'),'I ran out of steps',turn_id='one',logger=logging.getLogger(__name__))
        assert changed and 'MEDIA:verified.pdf' in result
        assert 'out of steps' not in result
    finally:guard.JOB.reset(token)


def test_cover_only_request_is_guarded():
    assert guard.cv_request('Write my cover letter only')
    assert package.required({'cover_only':True})==['cover']


def test_nested_shell_bypass_blocked():
    token=guard.JOB.set({'cv_active':True,'deadline':time.monotonic()+180})
    try:assert guard.pre_tool('tool_call',{'calls':[{'name':'execute_code','arguments':{'code':'print("building")'}}]})['action']=='block'
    finally:guard.JOB.reset(token)


def test_preparation_budget_cannot_be_evaded_by_changing_query():
    token=guard.JOB.set({'cv_active':True,'deadline':time.monotonic()+180})
    try:
        for i in range(8): assert guard.pre_tool('web_search',{'query':str(i)}) is None
        assert guard.pre_tool('web_search',{'query':'ninth'})['action']=='block'
        assert guard.pre_tool('career_cv_compile',{}) is None
    finally:guard.JOB.reset(token)


def test_partial_resume_reuses_cv_and_preserves_exact_inputs(monkeypatch):
    monkeypatch.setattr(package,'source_matches',lambda result:True)
    monkeypatch.setattr(guard,'verified_attachment',lambda p:True)
    args={'jd':'Exact role JD','company':'Example','short_role':'Analyst','job_id':'one'}
    package.save({'session_id':'one','request_id':'r','cv_active':True,'cv_args':args,
                  'results':{'cv':{'status':'PASS','verified_pdf':'existing.pdf'}}})
    monkeypatch.setattr(guard,'compile_prototype',lambda *a,**k:pytest.fail('must reuse matching CV'))
    async def run(self,message,context,*a,**k):
        assert 'Exact role JD' in context
        result=json.loads(guard.compile_tool(args))
        assert result['verified_pdf']=='existing.pdf'
        return {'final_response':'done'}
    Turn,_=install(run)
    assert asyncio.run(Turn()._run_agent('Try again','',[],None,'one'))['application_status']=='PARTIAL'


def test_real_compilers_and_final_handoff_without_model_summary(tmp_path,monkeypatch):
    from role_family_acceptance import offline_selection
    from agent import chat_completion_helpers as helpers
    import cv_workflow
    monkeypatch.setattr(guard,'OUTPUT_ROOT',tmp_path/'cv')
    monkeypatch.setattr(guard,'EXPORT_ROOT',tmp_path/'exports-cv')
    monkeypatch.setattr(guard,'generate',offline_selection)
    monkeypatch.setattr(cover,'ROOT',tmp_path/'cover')
    monkeypatch.setattr(cover,'EXPORT_ROOT',tmp_path/'exports-cover')
    # Real renderer and fact gate seam, no external calls or owner mailbox.
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**k:{'available':True,'exit_code':0})
    def render_cover(command,**kwargs):
        cover.build(command[-1]);return NS(returncode=0)
    monkeypatch.setattr(cover.subprocess,'run',render_cover)
    async def run(self,*a,**k):
        cv=json.loads(guard.compile_tool({'jd':'Graduate security analyst','job_id':'e2e','company':'Example','short_role':'Analyst'}))
        assert cv['status']=='PASS',cv
        letter=json.loads(cover.cover_tool({'company':'Example','role':'Graduate Analyst','paragraphs':[
            'I am applying for this graduate opportunity.','I would like to discuss how my studies relate to the role.',
            'I can explain the work included in my application.','I welcome the opportunity to discuss the team responsibilities.',
            'Thank you for considering my application.']}))
        assert letter['status']=='PASS',letter
        return {'final_response':helpers.handle_max_iterations(NS(),[],12),'failed':True}
    Turn,_=install(run)
    result=asyncio.run(Turn()._run_agent('Build my CV and cover letter','',[],None,'end-to-end'))
    assert result['application_status']=='VERIFIED_READY' and not result['failed']
    assert result['final_response'].count('MEDIA:')==2
    assert len(package.accepted(package.load('end-to-end')))==2


def test_same_filename_other_request_is_not_a_valid_resume(tmp_path,monkeypatch):
    source=tmp_path/'original.pdf';source.write_bytes(b'original')
    export=tmp_path/'CV.pdf';export.write_bytes(b'original')
    state={'session_id':'one','cv_active':True}
    package.record(state,'cv',{}, {'status':'PASS','compiler_pdf':str(source),'verified_pdf':str(export)})
    assert package.source_matches(state['results']['cv'])
    export.write_bytes(b'another application')
    assert not package.source_matches(state['results']['cv'])
    monkeypatch.setattr(guard,'verified_attachment',lambda path:True)
    assert not package.accepted(state)


def test_adapter_failure_then_success_preserves_only_pending_attachments(tmp_path,monkeypatch):
    source=tmp_path/'source.pdf';source.write_bytes(b'pdf')
    cv=tmp_path/'CV.pdf';cv.write_bytes(b'pdf')
    letter=tmp_path/'Cover.pdf';letter.write_bytes(b'pdf')
    monkeypatch.setattr(guard,'verified_attachment',lambda path:True)
    monkeypatch.setattr(cover,'verified',lambda path:True)
    state={'session_id':'one','cv_active':True,'resuming':True}
    for kind,path in [('cv',cv),('cover',letter)]:
        package.record(state,kind,{}, {'status':'PASS','compiler_pdf':str(source),'verified_pdf':str(path)})
    runtime=NS(_current_max_iterations=lambda:150)
    class Turn:
        async def _run_agent(self,*a,**k):return {}
    class Media:
        def __init__(self):self.success=False
        async def send_document(self,*a,**k):return NS(success=self.success)
    guard.install_runtime(runtime,Turn,Media)
    adapter=Media()
    assert not asyncio.run(adapter.send_document('fake-test-only',cv)).success
    assert package.render(state).count('MEDIA:')==2
    adapter.success=True
    assert asyncio.run(adapter.send_document('fake-test-only',cv)).success
    assert package.render(state).count('MEDIA:')==1
    state['resend']=True
    assert package.render(state).count('MEDIA:')==2


def test_exported_cover_is_verified_and_delivery_acknowledged(tmp_path,monkeypatch):
    monkeypatch.setattr(cover,'ROOT',tmp_path/'compiled')
    monkeypatch.setattr(cover,'EXPORT_ROOT',tmp_path/'exported')
    cover.EXPORT_ROOT.mkdir()
    pdf=cover.EXPORT_ROOT/'Cover.pdf';pdf.write_bytes(b'fixture')
    monkeypatch.setattr(guard,'verified_attachment',lambda path:False)
    valid=[False];monkeypatch.setattr(cover,'verified',lambda path:valid[0])
    class Media:
        async def send(self,*a,**k):pass
        async def send_document(self,*a,**k):return NS(success=True)
    runtime=NS(_current_max_iterations=lambda:150)
    class Turn:
        async def _run_agent(self,*a,**k):return {}
    guard.install_runtime(runtime,Turn,Media)
    result=asyncio.run(Media().send_document('fake-only',pdf))
    assert not result.success and not package.delivered(pdf)
    valid[0]=True
    assert asyncio.run(Media().send_document('fake-only',pdf)).success
    assert package.delivered(pdf)


def test_identical_bytes_from_different_request_receipt_are_not_reused(tmp_path):
    source=tmp_path/'request-one.pdf';source.write_bytes(b'same')
    other=tmp_path/'request-two.pdf';other.write_bytes(b'same')
    exported=tmp_path/'CV.pdf';exported.write_bytes(b'same')
    state={'session_id':'one','cv_active':True}
    package.record(state,'cv',{}, {'status':'PASS','compiler_pdf':str(source),'verified_pdf':str(exported)})
    exported.with_suffix('.verification.json').write_text(json.dumps({'source':str(other)}))
    assert not package.source_matches(state['results']['cv'])


def test_cv_planner_reserves_routing_and_generation_inside_parent_limit(monkeypatch):
    import cv_content_adapter as adapter
    import workflow_routing
    bank=json.loads((adapter.cv.HERE/'fact_bank.json').read_text(encoding='utf-8'))
    selections={slot:next(iter(variants)) for slot,variants in bank['slots'].items()}
    observed={}
    def complete(messages,**kwargs):
        observed.update(kwargs)
        return NS(model='fixture',choices=[NS(finish_reason='stop',message=NS(content=json.dumps({'selections':selections})))]),{'selected_provider':'fixture'}
    monkeypatch.setattr(workflow_routing,'complete_text',complete)
    result=adapter.generate({'jd':'Synthetic graduate role','capacities':[],'mode':'generate','worker':'codex'})
    assert set(result)==set(bank['slots'])
    assert observed['timeout']==120 and observed['max_tokens']==1024
    assert observed['worker']=='codex'
