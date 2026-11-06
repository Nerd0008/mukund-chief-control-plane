import logging
from types import SimpleNamespace as NS
import pytest
import hermes_cv_compiler_guard as guard
import application_question_recovery as recovery
from agent import turn_finalizer as core

STALE='Application: OWNER_INPUT_REQUIRED.\nCV: incomplete — need role.\nCover letter: incomplete — need role.'

def test_recovery_occurs_before_core_persists_the_answer(monkeypatch):
    observed=[]
    monkeypatch.setattr(recovery,'recover',lambda question,saved:observed.append((question,saved)) or 'A relevant answer.')
    monkeypatch.setattr(core,'_invoke_hook_safely',lambda name,logger,**kw:[guard.transform_output(**kw)])
    agent=NS(session_id='fixture',model='fixture')
    state={'question_only':True,'question_message':'Answer this question','question_checkpoint':{'intake':{'jd':'fixture'}},'cv_active':False}
    token=guard.JOB.set(state)
    try:
        answer,changed,original=core.apply_llm_output_transform(agent,STALE,turn_id='fixture',logger=logging.getLogger(__name__))
        assert changed and original==STALE and answer=='A relevant answer.'
        assert len(observed)==1
        repeated,_,_=core.apply_llm_output_transform(agent,answer,turn_id='fixture',logger=logging.getLogger(__name__))
        assert repeated==answer and len(observed)==1
    finally:guard.JOB.reset(token)

def test_failure_does_not_return_old_status_or_start_cv(monkeypatch):
    monkeypatch.setattr(recovery,'recover',lambda *a:(_ for _ in ()).throw(RuntimeError('fixture')))
    token=guard.JOB.set({'question_only':True,'question_message':'question','question_checkpoint':{},'cv_active':False})
    try:
        result=guard.transform_output(STALE)
        assert 'could not safely produce an answer' in result and 'CV: incomplete' not in result
        assert not guard.active_job()
    finally:guard.JOB.reset(token)

def test_correct_answer_untouched(monkeypatch):
    monkeypatch.setattr(recovery,'recover',lambda *a:pytest.fail('Recovery not needed'))
    token=guard.JOB.set({'question_only':True,'cv_active':False})
    try:assert guard.transform_output('I am interested in this role because...') is None
    finally:guard.JOB.reset(token)

def test_full_wrapper_and_host_persistence_hook_keep_recovered_answer(monkeypatch):
    import asyncio
    import application_package_state as package
    monkeypatch.setattr(package,'load',lambda session:{})
    monkeypatch.setattr(package,'save',lambda state:None)
    monkeypatch.setattr(recovery,'recover',lambda *a:'A direct application answer.')
    monkeypatch.setattr(core,'_invoke_hook_safely',lambda name,logger,**kw:[guard.transform_output(**kw)])
    class Turn:
        async def _run_agent(self,message,context,history,*args,**kwargs):
            value,changed,_=core.apply_llm_output_transform(NS(session_id='fixture',model='fixture'),
                STALE,turn_id='wrapper-test',logger=logging.getLogger(__name__))
            assert changed
            return {'final_response':value,'failed':False}
    class Media:
        async def send_document(self,*a,**kw):pytest.fail('No delivery')
    guard.install_runtime(NS(_current_max_iterations=lambda:150),Turn,Media)
    result=asyncio.run(Turn()._run_agent('Please answer this application question','',[],None,'fixture'))
    assert result['final_response']=='A direct application answer.'
