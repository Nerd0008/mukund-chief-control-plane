from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
import workflow_routing as wr
from router_brain import RouterDecisionError

def test_success_counters_do_not_charge_another_brain_decision(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path);wr._cache.clear();calls=[]
    def rank(rows,**kwargs):calls.append(1);return rows,{}
    offers=[wr.native_offer('fixture','controller')]
    with patch.object(wr.RouterBrain,'configured',return_value=NS(rank=rank)):
        _,route=wr.select('fixture',offers,task='Same bounded stage')
        wr.execute('fixture',route,lambda:'Successful tool round')
        _,again=wr.select('fixture',offers,task='Same bounded stage')
    assert calls==[1] and again['cached'] is True

def test_failure_invalidation_and_changed_permissions_still_require_new_selection(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path);wr._cache.clear();calls=[]
    def rank(rows,**kwargs):calls.append(1);return rows,{}
    offer=wr.native_offer('fixture','controller')
    with patch.object(wr.RouterBrain,'configured',return_value=NS(rank=rank)):
        _,route=wr.select('fixture',[offer],task='Same stage')
        def fail():raise RouterDecisionError('request_rejected')
        with pytest.raises(RouterDecisionError):wr.execute('fixture',route,fail)
        wr.select('fixture',[offer],task='Same stage')
        wr.select('fixture',[dict(offer,capabilities=['changed-contract'])],task='Same stage')
    assert len(calls)==3
