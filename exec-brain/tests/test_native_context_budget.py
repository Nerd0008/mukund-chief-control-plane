import json
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
import native_controller_router as controller
import workflow_routing as wr
from router_brain import RouterBrain

PRIMARY='meituan/longcat-2.5-preview:free'
STEP='stepfun/step-3.7-flash:free'
ROW=next(r for r in controller.policy()[0]['models'] if r['model']==STEP)

def test_realistic_large_history_is_measured_in_tokens_not_wire_bytes():
    content=('Synthetic audit evidence for a fictional organisation. No action is requested. '*7000)
    request={'messages':[{'role':'user','content':content}]}
    original=json.dumps(request)
    assert len(original.encode())>500000
    budget=controller.context_budget(request)
    assert budget['reserved_input_tokens']>=budget['estimated_input_tokens']*1.5
    assert controller.compatible(request,ROW)
    assert json.dumps(request)==original

@pytest.mark.parametrize('payload',[
 {'messages':[{'role':'user','content':'\u4e00'*180000}]},
 {'messages':[{'role':'user','content':'short'}],'max_tokens':250000},
 {'messages':[{'role':'user','content':'short'}],'tools':[{'type':'function','function':{'name':'large','description':'\u4e00'*180000}}]},
])
def test_true_context_excess_and_large_tool_schemas_still_block(payload):
    assert not controller.compatible(payload,ROW)


def test_inline_image_bytes_are_not_counted_as_text_tokens():
    request={'messages':[{'role':'user','content':[{'type':'text','text':'Describe the synthetic image.'},
             {'type':'image_url','image_url':{'url':'data:image/png;base64,'+'A'*600000}}]}]}
    budget=controller.context_budget(request)
    assert budget['estimated_input_tokens']<100000
    assert controller.compatible(request,ROW)

@pytest.mark.parametrize('output',[float('nan'),float('inf'),-1,0,'8192',True])
def test_invalid_output_budget_fails_closed(output):
    from router_brain import RouterDecisionError
    with pytest.raises(RouterDecisionError,match='invalid_native_output_budget'):controller.context_budget({'max_tokens':output})


def test_actual_large_request_routes_without_mutating_or_replaying_it(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts');wr._cache.clear()
    controller.qualify(PRIMARY,{'withdrawn':True})
    controller.qualify(STEP,{k:True for k in ('chat','tools','tool_continuation','stream','english','vision')})
    request={'messages':[{'role':'user','content':'Synthetic fictional audit evidence. '*14000}],
             'extra_body':{'tags':['product=hermes-agent'],'session_id':'SYNTHETIC_PRIVATE_SESSION','reasoning':{'enabled':True,'effort':'high'}}}
    before=json.dumps(request)
    offers=controller.offers('nous',PRIMARY,'chat_completions',request)
    assert [r['model'] for r in offers]==[STEP]
    class Brain:
        def rank(self,candidates,**kw):return candidates,{}
    with patch.object(RouterBrain,'configured',return_value=Brain()):
        chosen,route=wr.select('fixture',offers)
    assert route['selected_model']==STEP and json.dumps(request)==before
    assert 'SYNTHETIC_PRIVATE_SESSION' not in ''.join(p.read_text() for p in (tmp_path/'receipts').glob('*.json'))
