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
