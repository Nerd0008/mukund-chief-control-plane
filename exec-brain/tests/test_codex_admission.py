"""Contention and provider-backoff regression without real model requests."""
import datetime,json,os,subprocess,sys,threading,time
from pathlib import Path
from unittest.mock import patch
import pytest
import codex_admission as gate
import workflow_control as ctl
import codex_adapter
from router_brain import RouterBrain,RouterDecisionError,cli_failure_code
from e3_router import RouterCandidate


def test_three_processes_share_one_physical_model_slot(tmp_path):
    source=Path(gate.__file__).parent
    script=tmp_path/'worker.py'
    script.write_text("import sys,time,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import codex_admission as g; g.ROOT=Path(sys.argv[2]);\nwith g.admit('synthetic',timeout=5):\n start=time.monotonic();time.sleep(.15);end=time.monotonic();Path(sys.argv[3]).write_text(json.dumps([start,end]))\n")
    procs=[subprocess.Popen([sys.executable,str(script),str(source),str(tmp_path/'gate'),str(tmp_path/f'{i}.json')],
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) for i in range(3)]
    assert all(p.wait(timeout=10)==0 for p in procs)
    spans=sorted(json.loads((tmp_path/f'{i}.json').read_text()) for i in range(3))
    assert all(a[1]<=b[0] for a,b in zip(spans,spans[1:]))


def test_crashed_process_releases_os_admission_lock(tmp_path):
    source=Path(gate.__file__).parent
    script="import sys,os;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import codex_admission as g;g.ROOT=Path(sys.argv[2]);\nwith g.admit('synthetic',timeout=2):os._exit(0)"
    proc=subprocess.run([sys.executable,'-c',script,str(source),str(gate.ROOT)],timeout=5,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert proc.returncode==0
    with gate.admit('synthetic',timeout=.2):pass


def test_busy_queue_never_dispatches_or_resets_deadline():
    with gate.admit('synthetic',timeout=1):
        with patch.object(ctl,'run_process',side_effect=AssertionError('model dispatched')):
            with pytest.raises(gate.AdmissionBlocked) as failed:
                gate.run(['never'],model='synthetic',timeout=.1)
    assert failed.value.kind=='BUSY' and not failed.value.request_dispatched


def test_real_429_retry_sleep_is_stopped_and_shared_cooldown_blocks_next_request():
    # Captured CLI shape, synthetic timestamp. No provider call is made.
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
    line=stamp+' WARN codex_core::responses_retry: stream disconnected - retrying sampling request (1/5 in 197s)... sampling_error=exceeded retry limit, last status: 429 Too Many Requests'
    code="import sys,time;print("+repr(line)+",file=sys.stderr,flush=True);time.sleep(20)"
    start=time.monotonic()
    with pytest.raises(gate.AdmissionBlocked) as first:
        gate.run([sys.executable,'-c',code],model='synthetic',timeout=5,cancel_event=threading.Event(),
                 capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert time.monotonic()-start<4
    assert first.value.kind=='RATE_LIMITED' and first.value.request_dispatched
    assert 190<=first.value.retry_after_seconds<=197
    with patch.object(ctl,'run_process',side_effect=AssertionError('cooldown ignored')):
        with pytest.raises(gate.AdmissionBlocked) as second:
            gate.run(['never'],model='synthetic',timeout=1)
    assert not second.value.request_dispatched and second.value.kind=='RATE_LIMITED'
    state=json.loads(next(gate.ROOT.glob('*.json')).read_text())
    assert set(state)=={'not_before','http_status','updated_at'}


def test_expired_cooldown_allows_new_request_without_a_reset():
    lock,state=gate._paths('synthetic')
    state.write_text(json.dumps({'not_before':time.time()-1}))
    with patch.object(ctl,'run_process',return_value=subprocess.CompletedProcess(['fixture'],0,'ok','')) as run:
        assert gate.run(['fixture'],model='synthetic',timeout=1).stdout=='ok'
    assert run.call_count==1


def test_trace_id_or_fractional_timestamp_is_not_http_429():
    assert gate.rate_limit_signal(stderr='2026-10-28T15:00:00.429Z trace=abc429fff') is None
    assert gate.rate_limit_signal(stdout=json.dumps({'type':'item.completed','item':{'type':'reasoning','text':'429 Too Many Requests'}})) is None


def test_cancellation_while_waiting_does_not_launch_a_model():
    cancel=threading.Event()
    with gate.admit('synthetic',timeout=1):
        timer=threading.Timer(.05,cancel.set);timer.start()
        try:
            with pytest.raises(ctl.ProcessCancelled):
                gate.run(['never'],model='synthetic',timeout=1,cancel_event=cancel)
        finally:timer.cancel()


def test_router_receipt_distinguishes_rate_limit_from_timeout(tmp_path):
    worker=type('Adapter',(),{'dispatch':lambda self,c:{'status':'RATE_LIMITED','request_dispatched':False,
               'retry_after_seconds':197,'http_status':429}})()
    candidate=RouterCandidate('synthetic','provider','model','workflow-worker','MEDIUM',[],'synthetic')
    with pytest.raises(RouterDecisionError,match='router_cli_rate_limited') as failed:
        RouterBrain(worker,receipt_root=tmp_path).rank([candidate],objective='PRIVATE',task_family='analysis',roles=[])
    receipt=failed.value.receipt
    assert receipt['provider_call_made'] is False and receipt['retry_after_seconds']==197
    assert receipt['http_status']==429 and 'PRIVATE' not in json.dumps(receipt)
    assert cli_failure_code({'status':'BUSY'})=='router_cli_busy'


def test_fractional_timestamp_does_not_poison_progress_category():
    assert codex_adapter.execution_progress('', '2026-10-28T15:00:00.429Z shell snapshot warning')['error_category']=='none'


def test_nonfinite_cooldown_fails_closed_without_model_dispatch():
    lock,state=gate._paths('synthetic')
    state.write_text('{"not_before":NaN}')
    with patch.object(ctl,'run_process',side_effect=AssertionError('invalid state dispatched')):
        with pytest.raises(gate.AdmissionBlocked) as failed:
            gate.run(['never'],model='synthetic',timeout=1)
    assert failed.value.kind=='STATE_UNAVAILABLE'
