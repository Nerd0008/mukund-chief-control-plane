import asyncio,json,time
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
import workflow_routing as wr
import workflow_health as health
import native_controller_router as controller
import native_router_plugin as plugin
from router_brain import RouterBrain,RouterDecisionError
from workflow_control import operation,finish

PRIMARY='meituan/longcat-2.5-preview:free'
QWEN='qwen/qwen3-235b-a22b-thinking-2507'
LLAMA='meta-llama/llama-3.3-70b-instruct'
REQUEST={'model':PRIMARY,'messages':[{'role':'user','content':'Synthetic test'}],'tools':[{'type':'function','function':{'name':'noop','parameters':{'type':'object'}}}]}

class ProviderError(Exception):
    def __init__(self,status,code='rate_limited',retry=13):
        self.status_code=status;self.body={'reason':code,'retry_after':retry};self.response=NS(headers={'Retry-After':str(retry)})
        super().__init__('PRIVATE_SENTINEL')

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    wr._cache.clear();plugin._request_budgets.clear()
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts')
    controller.qualify(PRIMARY,{k:True for k in ('chat','tools','tool_continuation','stream','english')})


def qualified():
    for name in (QWEN,LLAMA):controller.qualify(name,{k:True for k in ('chat','tools','tool_continuation','stream','english')})

def brain():
    class Brain:
        def rank(self,candidates,**kwargs):return candidates,{}
    return patch.object(RouterBrain,'configured',return_value=Brain())


def test_no_unqualified_alternative_and_no_embedding_offer():
    assert len(controller.offers('nous',PRIMARY,'chat_completions',REQUEST))==1
    qualified();offers=controller.offers('nous',PRIMARY,'chat_completions',REQUEST)
    assert len(offers)==3 and not any('embed' in x['model'] for x in offers)

@pytest.mark.parametrize('payload,expected',[
    ({**REQUEST,'messages':[{'role':'user','content':'\u4e00'*130000}]},set()),
    ({**REQUEST,'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'https://example.invalid/image'}}]}]},set()),
    ({**REQUEST,'reasoning_effort':'high'},{QWEN}),
    ({**REQUEST,'response_format':{'type':'json_object'}},{LLAMA}),
    ({**REQUEST,'extra_body':{'thinking':{'type':'enabled'}}},set()),
    ({**REQUEST,'unknown_feature':True},set()),
    ({**REQUEST,'messages':[{'role':'user','content':[{'type':'input_audio'}]}]},set()),
])
def test_incompatible_alternatives_never_offered(payload,expected):
    qualified();result=controller.offers('nous',PRIMARY,'chat_completions',payload)
    assert {o['model'] for o in result if o['model']!=PRIMARY}==expected

@pytest.mark.parametrize('status,reason,scope',[(429,'rate_limited','model'),(429,'insufficient_quota','provider'),
 (402,'billing','provider'),(503,'unavailable','provider'),(401,'auth','request'),(403,'denied','request'),
 (400,'context_length_exceeded','request'),(404,'not_found','model')])
def test_failure_scope(status,reason,scope):
    e=ProviderError(status,reason);route={'selected_provider':'nous','selected_model':PRIMARY}
    health.record_failure(route,e)
    assert health.metadata(e)['failure_scope']==scope
    assert health.snapshot('nous',PRIMARY)['available']==(scope=='request')
    assert health.snapshot('nous',QWEN)['available']==(scope!='provider')


def test_429_changes_real_next_model_without_changing_config():
    qualified();routes=[]
    def dispatch(request):
        routes.append(request['model'])
        if request['model']==PRIMARY:raise ProviderError(429)
        return 'OK'
    with brain():
        with pytest.raises(Exception):plugin.llm_execution(REQUEST,dispatch,provider='nous',model=PRIMARY,api_mode='chat_completions')
        assert plugin.llm_execution(REQUEST,dispatch,provider='nous',model=PRIMARY,api_mode='chat_completions')=='OK'
    assert routes==[PRIMARY,QWEN]
    assert REQUEST['model']==PRIMARY


def test_provider_outage_does_not_cycle_through_same_endpoint():
    qualified();health.record_failure({'selected_provider':'nous','selected_model':PRIMARY},ProviderError(503))
    with brain(),pytest.raises(RouterDecisionError,match='no_healthy_compatible_worker'):
        wr.select('fixture',controller.offers('nous',PRIMARY,'chat_completions',REQUEST))


def test_router_still_required_with_one_healthy_model():
    called=[]
    class Denied:
        def rank(self,*a,**kw):raise RouterDecisionError('router_cli_usage_limit')
    with patch.object(RouterBrain,'configured',return_value=Denied()),pytest.raises(Exception):
        plugin.llm_execution(REQUEST,lambda r:called.append(r),provider='nous',model=PRIMARY)
    assert not called


def test_cooldown_expiry_and_inflight_success_cannot_revive_failure():
    route={'selected_provider':'p','selected_model':'m'};started=time.time()-10
    health.record_failure(route,ProviderError(429,retry=13));health.record_success(route,.1,started)
    assert not health.snapshot('p','m')['available']
    assert health.snapshot('p','m',now=time.time()+31)['available']


def test_qualification_expiry_policy_change_and_partial_checks():
    qualified()
    with health.database() as con:con.execute('UPDATE qualification SET observed_at=0')
    assert len(controller.offers('nous',PRIMARY,'chat_completions',REQUEST))==0
    qualified()
    with health.database() as con:con.execute("UPDATE qualification SET policy_sha='stale'")
    assert len(controller.offers('nous',PRIMARY,'chat_completions',REQUEST))==0
    controller.qualify(QWEN,{'chat':True})
    assert len(controller.offers('nous',PRIMARY,'chat_completions',REQUEST))==0


def test_dispatch_health_race_prevents_send():
    calls=[];route={'selected_provider':'p','selected_model':'m'}
    health.record_failure(route,ProviderError(429))
    with pytest.raises(RouterDecisionError,match='worker_health_changed'):wr.execute('fixture',route,lambda:calls.append(1))
    assert not calls


def test_retries_share_elapsed_budget_but_next_api_call_is_independent():
    assert plugin.request_budget({'api_request_id':'one'},1)<=1
    with plugin._budget_lock:
        deadline,created=plugin._request_budgets['one'];plugin._request_budgets['one']=(deadline-2,created)
    with pytest.raises(RouterDecisionError,match='workflow_deadline_exceeded'):plugin.request_budget({'api_request_id':'one'},1)
    assert plugin.request_budget({'api_request_id':'two'},1)>0


def receipts(tmp_path):return [json.loads(p.read_text()) for p in (tmp_path/'receipts').glob('*.json')]

@pytest.mark.parametrize('fail_after',[0,1,2])
def test_partial_stream_failure_never_marks_success_or_replays(tmp_path,fail_after):
    error=ProviderError(429);seen=[]
    def generator():
        for n in range(fail_after):seen.append(n);yield {'content':str(n),'tool_calls':[]}
        raise error
    with operation(5) as state:
        stream=wr.execute('fixture',{'selected_provider':'p','selected_model':'m'},generator,stream=True)
        assert finish(stream,state,True) is stream
        with pytest.raises(ProviderError) as caught:list(stream)
    assert caught.value is error and seen==list(range(fail_after))
    statuses={r['status'] for r in receipts(tmp_path)}
    assert statuses=={'STREAM_STARTED','FAILED'}
    assert not health.snapshot('p','m')['available']


def test_stream_completion_and_abandonment(tmp_path):
    with operation(5):
        stream=wr.execute('fixture',{},lambda:iter(['OK']),stream=True)
        assert not any(r['status']=='COMPLETED' for r in receipts(tmp_path))
        assert list(stream)==['OK']
    with operation(5):wr.execute('fixture',{},lambda:iter(['unused']),stream=True).close()
    assert {r['status'] for r in receipts(tmp_path)}=={'STREAM_STARTED','COMPLETED','CANCELLED'}

def test_async_partial_stream_preserves_failure(tmp_path):
    async def run():
        error=ProviderError(503)
        async def source():
            yield 'part';raise error
        async def make():return source()
        with operation(5):
            stream=await wr.aexecute('fixture',{},make,stream=True)
            with pytest.raises(ProviderError) as caught:[part async for part in stream]
        assert caught.value is error
        assert {r['status'] for r in receipts(tmp_path)}=={'STREAM_STARTED','FAILED'}
    asyncio.run(run())

def test_async_cancellation_does_not_quarantine_provider(tmp_path):
    async def run():
        async def source():
            yield 'part';raise asyncio.CancelledError()
        async def make():return source()
        with operation(5):
            stream=await wr.aexecute('fixture',{'selected_provider':'p','selected_model':'m'},make,stream=True)
            with pytest.raises(asyncio.CancelledError):[part async for part in stream]
        assert health.snapshot('p','m')['available']
        assert {r['status'] for r in receipts(tmp_path)}=={'STREAM_STARTED','CANCELLED'}
    asyncio.run(run())

@pytest.mark.parametrize('retry,expected',[(13,13),(9999,600),(-1,None),('nan',None),('invalid',None)])
def test_retry_after_bounded(retry,expected):assert health.retry_after(ProviderError(429,retry=retry))==expected


def test_health_database_unavailable_fails_closed(tmp_path,monkeypatch):
    target=tmp_path/'directory';target.mkdir();monkeypatch.setattr(health,'DB_PATH',target)
    with pytest.raises(RouterDecisionError,match='router_health_unavailable'):wr.select('fixture',[wr.native_offer('p','m')])


def test_same_provider_required_and_nonchat_protocol_never_swapped():
    qualified()
    for provider,mode in [('google','chat_completions'),('nous','responses'),('nous','anthropic')]:
        assert len(controller.offers(provider,PRIMARY,mode,REQUEST))==1


def test_close_error_cannot_mask_original_provider_failure():
    error=ProviderError(429)
    class BadClose:
        def __iter__(self):raise error;yield
        def close(self):raise OSError('Synthetic close failure')
    with operation(5):
        stream=wr.execute('fixture',{},BadClose,stream=True)
        with pytest.raises(ProviderError) as caught:list(stream)
    assert caught.value is error


def test_audit_io_failure_preserves_failed_send_but_blocks_success(monkeypatch):
    error=ProviderError(429)
    monkeypatch.setattr(wr,'persist',lambda r:(_ for _ in ()).throw(RouterDecisionError('workflow_receipt_unavailable')))
    with pytest.raises(ProviderError) as caught:wr.execute('fixture',{},lambda:(_ for _ in ()).throw(error))
    assert caught.value is error
    with pytest.raises(RouterDecisionError,match='workflow_receipt_unavailable'):wr.execute('fixture',{},lambda:'OK')


def test_paid_model_denial_is_model_billing_not_endpoint_or_missing_model():
    route={'selected_provider':'nous','selected_model':QWEN}
    error=ProviderError(404,'insufficient_credits_for_paid_model')
    health.record_failure(route,error)
    assert health.metadata(error)['error']=='provider_model_billing_blocked'
    assert not health.snapshot('nous',QWEN)['available']
    assert health.snapshot('nous',PRIMARY)['available']


def test_model_policy_corruption_stops_before_provider(tmp_path,monkeypatch):
    path=tmp_path/'policy.json';path.write_text('{}');monkeypatch.setattr(controller,'POLICY_PATH',path)
    with pytest.raises(RouterDecisionError,match='controller_policy_invalid'):controller.offers('nous',PRIMARY,'chat_completions',REQUEST)


def test_auxiliary_uses_selected_native_model_and_preserves_client():
    from contextvars import ContextVar
    calls=[]
    def sync(client,kwargs,**options):calls.append((client,kwargs['model']));return 'OK'
    module=NS(_relay_sync_completion=sync,_relay_async_completion=None,_relay_sync_stream=sync,
              _call_llm_impl=lambda *a,**k:None,_async_call_llm_impl=lambda *a,**k:None,
              _start_recovery_ladder=lambda *a,**k:None,_stream_request_plan=lambda kw:(kw,kw.get('model'),90),
              _RELAY_AUX_CALL_CONTEXT=ContextVar('test',default={}))
    plugin.install_auxiliary(module);qualified();client=object()
    health.record_failure({'selected_provider':'nous','selected_model':PRIMARY},ProviderError(429))
    with brain():assert module._relay_sync_completion(client,REQUEST,provider='nous',api_mode='chat_completions')=='OK'
    assert calls==[(client,QWEN)] and REQUEST['model']==PRIMARY


def test_sdk_facade_uses_chosen_model_not_stale_bound_model():
    qualified();seen=[]
    client=NS(chat=NS(completions=NS(create=lambda **kw:seen.append(kw['model']) or 'OK')))
    proxy=wr.RoutedClient(client,'nous',PRIMARY,allow_cli=False)
    health.record_failure({'selected_provider':'nous','selected_model':PRIMARY},ProviderError(429))
    with brain():assert proxy.chat.completions.create(**REQUEST)=='OK'
    assert seen==[QWEN] and proxy._model==PRIMARY
