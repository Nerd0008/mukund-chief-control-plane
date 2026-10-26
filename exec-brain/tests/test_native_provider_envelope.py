import json,sys
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as NS
import pytest
import native_controller_router as controller
import workflow_health as health
import workflow_routing as wr
import native_router_plugin as plugin
from router_brain import RouterBrain
from providers import get_provider_profile
from agent.transports.chat_completions import ChatCompletionsTransport
PRIMARY='meituan/longcat-2.5-preview:free'
STEP='stepfun/step-3.7-flash:free'
PROOF={k:True for k in ('chat','tools','tool_continuation','stream','english','vision')}

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts');wr._cache.clear()


def native_request():
    return ChatCompletionsTransport().build_kwargs(PRIMARY,[{'role':'user','content':'Synthetic native protocol test'}],
        tools=[{'type':'function','function':{'name':'noop','parameters':{'type':'object'}}}],
        provider_profile=get_provider_profile('nous'),session_id='SYNTHETIC_PRIVATE_SESSION',
        reasoning_config={'enabled':True,'effort':'high'},supports_reasoning=True,max_tokens=2048)


def test_real_hermes_native_envelope_reaches_qualified_alternative(tmp_path):
    request=native_request();controller.qualify(STEP,PROOF)
    assert 'tags' in request['extra_body'] and 'session_id' in request['extra_body']
    saved=json.dumps(request,sort_keys=True)
    controller.qualify(PRIMARY,{'withdrawn':True})
    class Brain:
        def rank(self,candidates,**kw):return candidates,{}
    captured=[]
    with patch.object(RouterBrain,'configured',return_value=Brain()):
        assert plugin.llm_execution(request,lambda r:captured.append(r) or 'OK',provider='nous',model=PRIMARY,api_mode='chat_completions')=='OK'
    assert captured[0]['model']==STEP
    assert captured[0]['extra_body']==request['extra_body']
    assert json.dumps(request,sort_keys=True)==saved
    logs=''.join(p.read_text() for p in (tmp_path/'receipts').glob('*.json'))
    assert 'SYNTHETIC_PRIVATE_SESSION' not in logs

@pytest.mark.parametrize('metadata',[{'tags':{'invalid':True}},{'session_id':123},{'tags':['valid',3]},
    {'provider':{'only':['unapproved']}},{'unknown_parameter':True}])
def test_metadata_allowance_does_not_allow_other_provider_overrides(metadata):
    row=next(r for r in controller.policy()[0]['models'] if r['model']==STEP)
    assert not controller.compatible({'messages':[],'extra_body':metadata},row)


def test_actual_withdrawal_is_remembered_even_without_old_qualification():
    class Withdrawn(Exception):
        status_code=404
        body={'status':404,'message':"This model is no longer free. To continue using LongCat, switch to the paid model."}
    error=Withdrawn();detail=health.record_failure({'selected_provider':'nous','selected_model':PRIMARY},error)
    assert detail['error']=='provider_model_withdrawn' and detail['failure_scope']=='model'
    controller.qualify(STEP,PROOF)
    assert PRIMARY not in {r['model'] for r in controller.offers('nous',PRIMARY,'chat_completions',native_request())}
    controller.qualify(PRIMARY,{})
    assert PRIMARY not in {r['model'] for r in controller.offers('nous',PRIMARY,'chat_completions',native_request())}
    controller.qualify(PRIMARY,PROOF)
    assert PRIMARY in {r['model'] for r in controller.offers('nous',PRIMARY,'chat_completions',native_request())}


def test_generic_404_is_not_guessed_to_mean_withdrawal():
    e=NS(status_code=404,body={'message':'Unknown endpoint'})
    assert health.metadata(e)['error']=='provider_model_not_found'
