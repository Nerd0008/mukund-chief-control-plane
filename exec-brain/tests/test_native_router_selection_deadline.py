"""Slow selector recovery never replays tools or extends the parent deadline."""
import json, subprocess, sys, threading
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
import native_router_plugin as plugin
import native_controller_router as controller
import workflow_control as ctl
import workflow_routing as wr
import router_brain as brain
from e3_router import RouterCandidate
import codex_adapter as adapter


@pytest.mark.parametrize('elapsed,expected', [(50,True),(95,False)])
def test_native_selection_can_outlast_45s_within_shared_budget(monkeypatch,tmp_path,elapsed,expected):
    clock=[0.0];calls=[];decisions=[]
    monkeypatch.setattr(ctl.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts')
    monkeypatch.setattr(controller,'offers',lambda *a:[wr.native_offer('synthetic','model')])
    monkeypatch.setattr(plugin,'request_budget',lambda *a:120)
    monkeypatch.setitem(sys.modules,'hermes_diagnostics',NS(enrich_request=lambda r:(r,None),router_task=lambda r,t:t,receipt_evidence=lambda r:r))
    wr._cache.clear()
    class Adapter:
        def dispatch(self,contract):
            decisions.append(contract)
            clock[0]+=elapsed
            profiles=json.loads(contract['objective'].split('\nINPUT\n')[1])['eligible_candidates']
            return {'status':'COMPLETED','raw_output':[], 'final_message':json.dumps({
                'ranked_handles':[p['handle'] for p in profiles], 'needs_owner':False,'reason_codes':['TASK_FIT']})}
    with patch.object(brain.RouterBrain,'configured',return_value=brain.RouterBrain(Adapter())):
        def downstream(request):
            calls.append(request)
            return 'OK'
        if expected:
            assert plugin.llm_execution({'messages':[],'timeout':120},downstream,provider='synthetic',model='model')=='OK'
        else:
            with pytest.raises(Exception):plugin.llm_execution({'messages':[],'timeout':120},downstream,provider='synthetic',model='model')
    assert len(decisions)==1  # No retry even for a timed-out selection.
    assert 89<=decisions[0]['timeout']<=90
    assert len(calls)==int(expected)
    if expected:assert 69<=calls[0]['timeout']<=70


def test_progress_is_safe_and_does_not_store_output_text():
    raw='\n'.join(map(json.dumps,[{'type':'thread.started'}, {'type':'turn.started'},
        {'type':'item.completed','item':{'type':'reasoning','text':'PRIVATE REASONING'}},
        {'type':'error','message':'PRIVATE TOKEN 429 Too many requests'}]))
    result=adapter.execution_progress(raw,'PRIVATE TOKEN connection reset')
    assert result['thread_started'] and result['turn_started']
    assert not result['final_message_observed'] and not result['tool_event_observed']
    assert result['error_category']=='usage_limit'
    assert 'PRIVATE' not in json.dumps(result) and 'reasoning' not in json.dumps(result)


def test_cancel_aware_timeout_preserves_capture_for_safe_diagnostics():
    cmd=[sys.executable,'-c',"import time; print('{\"type\":\"turn.started\"}',flush=True); time.sleep(20)"]
    with pytest.raises(subprocess.TimeoutExpired) as failed:
        ctl.run_process(cmd,cancel_event=threading.Event(),timeout=.5,text=True,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    raw=failed.value.output
    if isinstance(raw,bytes):raw=raw.decode()
    assert raw and 'turn.started' in raw


def test_timeout_receipt_contains_only_allowlisted_progress(tmp_path):
    candidate=RouterCandidate('synthetic','provider','model','workflow-worker','MEDIUM',[], 'synthetic')
    progress={'thread_started':True,'turn_started':True,'final_message_observed':False,
              'tool_event_observed':False,'error_category':'connection', 'PRIVATE':'secret'}
    worker=NS(dispatch=lambda c:{'status':'TIMEOUT','execution_progress':progress})
    with pytest.raises(brain.RouterDecisionError):
        brain.RouterBrain(worker,receipt_root=tmp_path).rank([candidate],objective='PRIVATE',task_family='analysis',roles=[])
    receipt=json.loads(next(tmp_path.glob('*.json')).read_text())
    assert receipt['execution_progress']['turn_started'] is True
    assert receipt['execution_progress']['error_category']=='connection'
    assert 'PRIVATE' not in json.dumps(receipt)
