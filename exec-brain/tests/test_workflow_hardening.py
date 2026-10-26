import asyncio,json,sys,time,threading,concurrent.futures
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import workflow_routing as wr
import workflow_control as ctl
from router_brain import RouterDecisionError

@pytest.fixture(autouse=True)
def offline(tmp_path,monkeypatch):
    wr._cache.clear();monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts')
    class Brain:
        def rank(self,rows,**kwargs):return rows,{'status':'ROUTED','worker_order':[r.worker_id for r in rows]}
    monkeypatch.setattr(wr.RouterBrain,'configured',classmethod(lambda cls:Brain()))

class SDK:
    def __init__(self):
        self.calls=[];self.chat=NS(completions=NS(create=self.create));self.responses=NS(create=self.create);self.messages=NS(create=self.create)
    def create(self,**kwargs):self.calls.append(kwargs);return 'response'
    async def acreate(self,**kwargs):return self.create(**kwargs)
    def with_options(self,**kwargs):return self

def test_async_timeout_is_reduced_by_routing():
    sdk=SDK();sdk.chat.completions.create=sdk.acreate;client=wr.RoutedClient(sdk,'p','m',async_mode=True,allow_cli=False)
    def select(*args,**kwargs):time.sleep(.02);return 'native',{}
    with patch.object(wr,'select',side_effect=select):asyncio.run(client.chat.completions.create(messages=[],timeout=5))
    assert 0<sdk.calls[0]['timeout']<4.99

def test_async_cli_receives_remaining_budget():
    client=wr.RoutedClient(SDK(),'p','m',async_mode=True)
    with patch.object(wr,'select',return_value=('codex',{})),patch.object(wr,'text_via_codex',return_value='ok') as worker:
        asyncio.run(client.chat.completions.create(messages=[],timeout=5))
    assert 0<worker.call_args.kwargs['timeout']<=5

@pytest.mark.parametrize('protocol',['messages','responses'])
def test_nonchat_deadline_shared(protocol):
    sdk=SDK();client=wr.RoutedClient(sdk,'p','m')
    def select(*a,**kw):assert kw['timeout']<=2;time.sleep(.02);return 'native',{}
    with patch.object(wr,'select',side_effect=select):getattr(client,protocol).create(input='synthetic',timeout=2)
    assert 0<sdk.calls[0]['timeout']<1.99

def test_with_options_limit_survives():
    sdk=SDK();client=wr.RoutedClient(sdk,'p','m',allow_cli=False).with_options(timeout=5)
    client.chat.completions.create(messages=[])
    assert 0<sdk.calls[0]['timeout']<=5

def test_responses_input_reaches_router():
    assert wr._request_task({'input':'first'})!=wr._request_task({'input':'second'})

def test_concurrent_cache_miss_is_single_flight():
    entered=threading.Event();release=threading.Event();calls=[]
    class Brain:
        def rank(self,rows,**kwargs):calls.append(1);entered.set();assert release.wait(3);return rows,{}
    with patch.object(wr.RouterBrain,'configured',return_value=Brain()),concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        one=pool.submit(wr.select,'fixture',[wr.cli_offer()],task='same')
        assert entered.wait(3)
        two=pool.submit(wr.select,'fixture',[wr.cli_offer()],task='same');time.sleep(.03);release.set()
        results=[one.result(3),two.result(3)]
    assert len(calls)==1 and any(r[1].get('coalesced') for r in results)

def test_receipts_include_workflow_cache_and_no_content(tmp_path):
    wr.select('fixture',[wr.cli_offer()],task='PRIVATE-CONTENT')
    wr.select('fixture',[wr.cli_offer()],task='PRIVATE-CONTENT')
    records=[json.loads(p.read_text()) for p in (tmp_path/'receipts').glob('*.json')]
    assert len(records)==2 and all(r['workflow']=='fixture' and r['operation_id'] for r in records)
    assert any(r['cached'] for r in records) and 'PRIVATE-CONTENT' not in json.dumps(records)

def test_cancellation_waits_for_router_cleanup():
    entered=threading.Event();finished=threading.Event()
    def route(*args,**kwargs):
        state=ctl.CURRENT.get();entered.set();assert state.cancel.wait(3);finished.set();raise RouterDecisionError('workflow_cancelled')
    async def run():
        sdk=SDK();sdk.chat.completions.create=sdk.acreate
        task=asyncio.create_task(wr.RoutedClient(sdk,'p','m',async_mode=True).chat.completions.create(messages=[],timeout=5))
        while not entered.is_set():await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert finished.is_set() and sdk.calls==[]
    with patch.object(wr,'select',side_effect=route):asyncio.run(run())

@pytest.mark.parametrize('output,code',[
    ({'status':'TIMEOUT'},'bounded_text_worker_timeout'),
    ({'status':'FAILED','stderr':'Usage limit reached PRIVATE'},'bounded_text_worker_usage_limit'),
    ({'status':'FAILED','stderr':'401 unauthorized PRIVATE'},'bounded_text_worker_auth')])
def test_worker_failure_keeps_safe_category(output,code):
    import codex_adapter
    with patch.object(codex_adapter,'CodexExecutionAdapter',return_value=NS(dispatch=lambda c:output)):
        with pytest.raises(RouterDecisionError,match=code) as error:wr.text_via_codex([],timeout=5)
    assert 'PRIVATE' not in json.dumps(error.value.receipt)

def test_stream_stops_at_total_deadline_and_closes():
    closed=[]
    class Stream:
        def __iter__(self):yield 'first';time.sleep(.03);yield 'late'
        def close(self):closed.append(True)
    with ctl.operation(.01) as state:
        stream=ctl.finish(Stream(),state,True);it=iter(stream);assert next(it)=='first'
        with pytest.raises(TimeoutError):next(it)
    assert closed==[True]

def test_owned_child_is_stopped_on_cancel():
    event=threading.Event();timer=threading.Timer(.25,event.set);timer.start();started=time.monotonic()
    try:
        with pytest.raises(ctl.ProcessCancelled):
            ctl.run_process([sys.executable,'-c','import time; time.sleep(30)'],cancel_event=event,timeout=5,text=True,creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0))
    finally:timer.cancel()
    assert time.monotonic()-started<6

def test_explicit_worker_constraint_never_broadens_protocols():
    sdk=SDK();client=wr.RoutedClient(sdk,'p','m',worker='codex')
    with pytest.raises(RouterDecisionError,match='incompatible'):
        client.chat.completions.create(messages=[],tools=[{'type':'function'}])
    assert sdk.calls==[]
