import copy,json,time
from unittest.mock import patch
import pytest
import native_controller_router as c
import native_router_plugin as p
import workflow_routing as wr
from router_brain import RouterDecisionError

PRIMARY='meituan/longcat-2.5-preview:free'
STEP='stepfun/step-3.7-flash:free'
PASS={k:True for k in ('chat','tools','tool_continuation','stream','english','vision')}

def test_primary_has_no_qualification_bypass(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path)
    request={'messages':[{'role':'user','content':'short'}]}
    offers=c.offers('nous',PRIMARY,'chat_completions',request)
    assert offers==[] and offers.block_reason=='no_qualified_controller'
    c.qualify(PRIMARY,PASS)
    assert c.offers('nous',PRIMARY,'chat_completions',request)[0]['model']==PRIMARY

def test_true_capacity_failure_requests_native_compression_not_worker_rotation(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path)
    c.qualify(STEP,PASS)
    request={'messages':[{'role':'user','content':'\u4e00'*250000}]}
    original=copy.deepcopy(request)
    offers=c.offers('nous',PRIMARY,'chat_completions',request)
    with pytest.raises(RouterDecisionError,match='native_context_capacity_exceeded'):
        wr.select('fixture',offers)
    verdict=p.router_error_classification(error=RouterDecisionError(offers.block_reason))
    from agent.error_classifier import FailoverReason
    assert FailoverReason(verdict['reason'])==FailoverReason.context_overflow
    assert verdict['should_compress'] and not verdict['should_fallback']
    assert not verdict['should_rotate_credential'] and not verdict['retryable']
    assert request==original

def test_protocol_and_expired_qualification_are_distinct(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path)
    c.qualify(STEP,PASS)
    offers=c.offers('nous',PRIMARY,'chat_completions',{'messages':[],'unknown_feature':True})
    assert offers.block_reason=='native_request_protocol_incompatible'
    with patch.object(c.time,'time',return_value=time.time()+604801):
        assert c.offers('nous',PRIMARY,'chat_completions',{'messages':[]}).block_reason=='no_qualified_controller'

def test_incomplete_profile_never_reaches_router_or_worker(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[2]/'career-ops'))
    import hermes_owner_context as owner
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path)
    called=[]
    with owner.dispatch_context('AUTHORITATIVE_FULL_OVERLAY',[],{'scope':'professional'}):
        with patch.object(p,'select',side_effect=AssertionError('router called')):
            with pytest.raises(Exception,match='owner_context_coverage_failed'):
                p.llm_execution({'messages':[]},lambda r:called.append(r),provider='custom',model='m')
    assert called==[]
