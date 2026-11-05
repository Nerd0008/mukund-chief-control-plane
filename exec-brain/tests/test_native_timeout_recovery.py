"""Real routing/health/receipt timeout recovery with a simulated clock only."""
import json
from pathlib import Path
import types
from contextlib import contextmanager, nullcontext
from unittest.mock import patch
import pytest
import native_router_plugin as plugin
import workflow_routing as routing
import workflow_health as health
import workflow_control as control
from router_brain import RouterDecisionError
import httpx
from openai import APITimeoutError

@pytest.fixture(autouse=True)
def private_context(monkeypatch):
    import sys
    diagnostics=types.ModuleType('hermes_diagnostics')
    diagnostics.enrich_request=lambda request:(request,None)
    diagnostics.router_task=lambda request,fallback:fallback
    diagnostics.receipt_evidence=lambda evidence:evidence
    monkeypatch.setitem(sys.modules,'hermes_diagnostics',diagnostics)
    routing._cache.clear()

def scenario(module, tmp_path, retry_delay=2.65, retry_budget=120):
    clock=[1000.0]
    counts={'selector_calls':0,'downstream_calls':0,'waits':[]}
    class Cancel:
        def is_set(self):return False
        def set(self):pass
        def wait(self,seconds):
            counts['waits'].append(round(seconds,2));clock[0]+=seconds;return False
    actual_operation=control.operation
    @contextmanager
    def operation(*args,**kwargs):
        with actual_operation(*args,**kwargs) as state:
            state.cancel=Cancel()
            yield state
    def select(*args,**kwargs):
        counts['selector_calls']+=1
        return 'native',{'candidate_count':1,'selected_provider':'custom','selected_model':'LongCat-2.5'}
    def downstream(request):
        counts['downstream_calls']+=1
        if counts['downstream_calls']==1:
            clock[0]+=22.75
            raise APITimeoutError(request=httpx.Request('POST','https://api.longcat.ai/openai/v1/chat/completions'))
        return {'fixture':'success'}
    def call(timeout):
        try:
            response=module.llm_execution({'model':'LongCat-2.5','timeout':timeout,'messages':[{'role':'user','content':'offline fixture'}]},
                downstream,provider='custom',model='LongCat-2.5',api_mode='chat_completions')
            return {'status':'COMPLETED','response':response}
        except Exception as exc:
            cause=getattr(exc,'original',exc)
            return {'status':'BLOCKED' if isinstance(cause,RouterDecisionError) else 'FAILED',
                    'error':str(cause) if isinstance(cause,RouterDecisionError) else type(cause).__name__,
                    'retry_after':(getattr(cause,'receipt',None) or {}).get('retry_after_seconds')}
    private=tmp_path
    with nullcontext(str(private)) as temporary:
        with patch.object(health,'DB_PATH',Path(temporary)/'health.sqlite3'), \
             patch.object(routing,'RECEIPT_ROOT',Path(temporary)/'receipts'), \
             patch.object(routing,'_select_once',select), \
             patch.object(control,'operation',operation),patch.object(routing,'operation',operation), \
             patch('time.time',lambda:1793900000+clock[0]),patch('time.monotonic',lambda:clock[0]):
            first=call(120)
            assert first['error']=='APITimeoutError'
            clock[0]+=retry_delay
            second=call(retry_budget)
    return {'first':first,'second':second,**counts}


@pytest.mark.parametrize('delay,budget,status,calls,waits',[
    (2.65,120,'COMPLETED',2,[27.45]),
    (31,120,'COMPLETED',2,[]),
    (2.65,10,'BLOCKED',1,[]),
])
def test_timeout_then_retry_uses_health_and_remaining_budget(tmp_path,delay,budget,status,calls,waits):
    result=scenario(plugin,tmp_path,retry_delay=delay,retry_budget=budget)
    assert result['second']['status']==status
    assert result['downstream_calls']==calls
    assert result['waits']==waits
    if status=='BLOCKED':
        assert result['second']['error']=='no_healthy_compatible_worker'
        assert result['second']['retry_after']==28
