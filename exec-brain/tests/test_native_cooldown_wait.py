from types import SimpleNamespace as NS
import pytest
import native_router_plugin as plugin
from router_brain import RouterDecisionError

@pytest.mark.parametrize('available,delay,budget,expected',[(True,20,90,0),(False,20,90,1),(False,120,300,0),(False,20,5,0)])
def test_bounded_wait_before_dispatch(monkeypatch,available,delay,budget,expected):
    import workflow_health
    calls=[]
    monkeypatch.setattr(plugin.time,'time',lambda:100)
    monkeypatch.setattr(workflow_health,'snapshot',lambda *a:{'available':available,'cooldown_until':100+delay})
    state=NS(remaining=lambda:budget,cancel=NS(wait=lambda seconds:calls.append(seconds) or False))
    plugin.wait_native_capacity([{'provider':'custom','model':'test'}],state)
    assert len(calls)==expected
    if calls:assert delay<=calls[0]<delay+1

def test_cancelled_wait_does_not_dispatch(monkeypatch):
    import workflow_health
    monkeypatch.setattr(plugin.time,'time',lambda:100)
    monkeypatch.setattr(workflow_health,'snapshot',lambda *a:{'available':False,'cooldown_until':105})
    with pytest.raises(RouterDecisionError,match='workflow_cancelled'):
        plugin.wait_native_capacity([{}],NS(remaining=lambda:90,cancel=NS(wait=lambda seconds:True)))



def test_eager_host_alias_gets_temporary_cooldown_diagnosis(monkeypatch):
    import sys
    from types import SimpleNamespace as NS
    from router_brain import RouterDecisionError
    import workflow_routing
    emitted=[]
    def terminal(agent,classified):
        agent._emit_diagnostic_status("Custom endpoint rejected the request and retrying won't help")
        return 'original-contract'
    recovery=NS(nonretryable_copy=lambda *a,**k:'old',nonretryable_client_error_result=terminal)
    consumer=NS(nonretryable_client_error_result=terminal)
    monkeypatch.setitem(sys.modules,'agent.turn_api_error',consumer)
    plugin.install_failure_copy(recovery)
    error=RouterDecisionError('no_healthy_compatible_worker',{'retry_after_seconds':28,
        'worker_cooldowns':[{'provider':'custom','model':'fixture','last_failure_code':'provider_timeout'}]})
    classified=NS(**plugin.router_error_classification(error=error))
    agent=NS(_emit_diagnostic_status=emitted.append)
    assert consumer.nonretryable_client_error_result(agent,classified)=='original-contract'
    assert len(emitted)==1 and 'timed out' in emitted[0] and '28 seconds' in emitted[0]
    assert 'rejected' not in emitted[0] and "won't help" not in emitted[0]


def test_blocked_selection_receipt_preserves_actual_worker_cause(monkeypatch,tmp_path):
    import json
    import workflow_health
    import workflow_routing
    monkeypatch.setattr(workflow_routing,'RECEIPT_ROOT',tmp_path)
    monkeypatch.setattr(workflow_health,'snapshot',lambda *a:{'available':False,'cooldown_until':plugin.time.time()+28,'last_failure_code':'provider_timeout'})
    with pytest.raises(RouterDecisionError,match='no_healthy_compatible_worker'):
        workflow_routing.select('fixture',[{'id':'one','provider':'custom','model':'fixture'}])
    receipt=json.loads(next(tmp_path.glob('*.json')).read_text())
    assert receipt['worker_cooldowns'][0]['last_failure_code']=='provider_timeout'
    assert receipt['retry_after_seconds']>=28
