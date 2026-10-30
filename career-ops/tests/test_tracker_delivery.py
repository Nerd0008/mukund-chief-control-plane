import json,os,ctypes
from pathlib import Path
import pytest
import tracker_delivery as delivery
import job_scan_delta as delta

def test_busy_retains_before_advancing_and_never_writes(monkeypatch,tmp_path):
    monkeypatch.setattr(delivery,'workbook_busy',lambda p:True)
    order=[]
    def retain(rows):order.append('retain');return tmp_path/'queue.json'
    result,receipt=delivery.write_or_defer(lambda:pytest.fail('must not write'),tmp_path/'a.xlsx',[{'url':'x'}],retain,lambda:order.append('advance'))
    assert result is None and order==['retain','advance']
    assert receipt['applied'] is False and receipt['tracker_writes']==0
    assert receipt['requires_fresh_verification'] is True

def test_retention_failure_never_advances(monkeypatch,tmp_path):
    monkeypatch.setattr(delivery,'workbook_busy',lambda p:True)
    def bad(rows):raise OSError('queue disk full')
    with pytest.raises(OSError,match='disk full'):
        delivery.write_or_defer(lambda:None,tmp_path/'a.xlsx',[],bad,lambda:pytest.fail('lost retry evidence'))

@pytest.mark.parametrize('failure',[PermissionError('ACL denied'),OSError('disk full'),ValueError('integrity refused')])
def test_unrelated_failure_not_disguised_as_busy(monkeypatch,tmp_path,failure):
    monkeypatch.setattr(delivery,'workbook_busy',lambda p:False)
    def fail():raise failure
    with pytest.raises(type(failure)):
        delivery.write_or_defer(fail,tmp_path/'a.xlsx',[],lambda r:pytest.fail('not a busy retry'),lambda:pytest.fail('not complete'))

def test_success_uses_real_writer_without_advancing_early(monkeypatch,tmp_path):
    monkeypatch.setattr(delivery,'workbook_busy',lambda p:False)
    result,deferred=delivery.write_or_defer(lambda:{'applied':True},tmp_path/'a.xlsx',[],lambda r:pytest.fail('no defer'),lambda:pytest.fail('writer caller owns success advancement'))
    assert result=={'applied':True} and deferred is None

def test_deferred_complete_batch_advances_and_stops_further_calls(monkeypatch,tmp_path):
    out='SEARCH_COVERAGE '+json.dumps({'coverage_complete':True})+'\nTRACKER_WRITE_DEFERRED '+json.dumps({'status':'DEFERRED','proposed_new_rows':2})
    monkeypatch.setattr(delta,'CURSOR',tmp_path/'cursor.json')
    calls=[]
    def run(offset,*a,**kw):calls.append(offset);return 0,out,''
    monkeypatch.setattr(delta,'run_search',run)
    code,stdout,stderr,summary=delta.run_searches(3,10,max_batches=3,budget_seconds=1000,pool_size=12)
    assert code==0 and calls==[3] and summary['coverage_complete']
    assert summary['stop_reason']=='tracker_delivery_deferred'
    assert json.loads(delta.CURSOR.read_text())['next_offset']==4
    assert delta.current_run_roles(stdout)==[]

def test_search_failure_is_still_failure_and_never_advances(monkeypatch,tmp_path):
    monkeypatch.setattr(delta,'CURSOR',tmp_path/'cursor.json')
    monkeypatch.setattr(delta,'run_search',lambda *a,**kw:(2,'SEARCH_COVERAGE {"coverage_complete":false}','provider failed'))
    code,_,_,summary=delta.run_searches(3,10,budget_seconds=1000,pool_size=12)
    assert code==2 and not summary['coverage_complete'] and not delta.CURSOR.exists()

@pytest.mark.skipif(os.name!='nt',reason='real Windows sharing semantics')
def test_real_windows_replace_failure_then_deferral_then_unlocked_delivery(tmp_path):
    from ctypes import wintypes as w
    p=tmp_path/'canonical.xlsx';p.write_bytes(b'owner data')
    stage=tmp_path/'stage.xlsx'
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
    api.CreateFileW.restype=w.HANDLE;api.CloseHandle.argtypes=[w.HANDLE]
    handle=api.CreateFileW(str(p),0x80000000,1,None,3,0,None)
    assert handle!=ctypes.c_void_p(-1).value
    def write():stage.write_bytes(b'new verified data');stage.replace(p);return {'applied':True}
    try:
        assert delivery.workbook_busy(p)
        with pytest.raises(OSError) as exc:write()
        assert exc.value.winerror in (5,32,33)
        assert p.read_bytes()==b'owner data'
        events=[]
        result,receipt=delivery.write_or_defer(write,p,[{}],lambda r:events.append('retained') or tmp_path/'queue',lambda:events.append('advance'))
        assert result is None and receipt['status']=='DEFERRED' and events==['retained','advance']
    finally:api.CloseHandle(handle)
    assert not delivery.workbook_busy(p)
    result,receipt=delivery.write_or_defer(write,p,[{}],lambda r:pytest.fail('not busy'),lambda:pytest.fail('not busy'))
    assert result['applied'] and receipt is None and p.read_bytes()==b'new verified data'


def test_failure_summary_names_tracker_stage():
    summary=delta.failure_summary({'batches':[{'exit_code':2,'delivery_failure':{'stage':'tracker_commit'},'coverage':{}}]})
    assert 'tracker_write_failed=1' in summary
    assert 'search_or_tracker_failure' not in summary


def test_deferred_tag_cannot_hide_incomplete_search(monkeypatch,tmp_path):
    monkeypatch.setattr(delta,'CURSOR',tmp_path/'cursor.json')
    out='SEARCH_COVERAGE {"coverage_complete":false}\nTRACKER_WRITE_DEFERRED {"applied":false}'
    monkeypatch.setattr(delta,'run_search',lambda *a,**kw:(0,out,''))
    code,_,_,summary=delta.run_searches(3,10,budget_seconds=1000,pool_size=12)
    assert code!=0 and not summary['coverage_complete'] and not delta.CURSOR.exists()
