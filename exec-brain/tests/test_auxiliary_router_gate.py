import asyncio,sys,time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),r'C:/Users/mukun/AppData/Local/hermes/hermes-agent']
import native_router_plugin as plugin
from workflow_control import operation
from router_brain import RouterDecisionError

@pytest.fixture
def guarded_aux(monkeypatch):
    from agent import auxiliary_client as aux
    names=('_relay_sync_completion','_relay_async_completion','_relay_sync_stream','_call_llm_impl','_async_call_llm_impl','_start_recovery_ladder','_stream_request_plan','_mandatory_router_installed','_mandatory_router_contract')
    prior={n:getattr(aux,n,None) for n in names}
    if hasattr(aux,'_mandatory_router_installed'):delattr(aux,'_mandatory_router_installed')
    plugin.install_auxiliary(aux)
    try:yield aux
    finally:
        for name,value in prior.items():
            if value is None:
                if hasattr(aux,name):delattr(aux,name)
            else:setattr(aux,name,value)

def fake_fallback(monkeypatch,aux,calls):
    destination=NS(provider='fixture',api_mode='chat_completions',base_url='https://example.invalid')
    monkeypatch.setattr(aux,'_plan_fallback_candidate',lambda *a,**kw:(destination,{'messages':[],'timeout':5},None))
    monkeypatch.setattr(aux,'_create_with_progress',lambda c,kw,*a,**other:calls.append(kw) or 'response')
    monkeypatch.setattr(aux,'_validate_llm_response',lambda response,*a,**kw:response)
    return lambda:aux._call_fallback_candidate_sync(NS(),'fixture','fixture',task='vision',messages=[],temperature=0,max_tokens=1,tools=None,effective_timeout=5,effective_extra_body={},reasoning_config=None)

def test_real_aux_fallback_is_routed(guarded_aux,monkeypatch):
    calls=[];run=fake_fallback(monkeypatch,guarded_aux,calls)
    with patch.object(plugin,'select',return_value=('native',{})) as route,operation(5):
        assert run()=='response'
    assert len(calls)==1 and route.call_count==1 and 0<calls[0]['timeout']<=5

def test_denied_fallback_never_sends(guarded_aux,monkeypatch):
    calls=[];run=fake_fallback(monkeypatch,guarded_aux,calls)
    with patch.object(plugin,'select',side_effect=RouterDecisionError('router_cli_timeout')),operation(5):
        with pytest.raises(RouterDecisionError):run()
    assert calls==[]

def test_router_denial_never_starts_recovery(guarded_aux):
    with pytest.raises(RouterDecisionError):guarded_aux._start_recovery_ladder(RouterDecisionError('router_cli_timeout'))

def test_async_physical_call_is_routed(guarded_aux,monkeypatch):
    calls=[]
    async def relay(c,kw,**options):calls.append(kw);return 'response'
    # The existing wrapper must retain its real transport; exercise async SDK via a callback.
    async def create(**kw):calls.append(kw);return 'response'
    client=NS(chat=NS(completions=NS(create=create)))
    monkeypatch.setattr(guarded_aux,'_acreate_with_progress',lambda c,kw,*a,**options:create(**kw))
    async def run():
        with operation(5):return await guarded_aux._relay_async_completion(client,{'messages':[],'timeout':5},provider='fixture')
    with patch.object(plugin,'select',return_value=('native',{})) as route:
        assert asyncio.run(run())=='response'
    assert route.call_count==1 and len(calls)==1
