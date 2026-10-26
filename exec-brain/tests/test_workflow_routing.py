import sys,json,asyncio,os
from pathlib import Path
from types import SimpleNamespace
from collections import namedtuple
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'exec-brain'))
sys.path.append(str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'hermes/hermes-agent'))
import workflow_routing as wr
import native_router_plugin as plugin
from router_brain import RouterDecisionError

@pytest.fixture(autouse=True)
def no_live_provider(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,"RECEIPT_ROOT",tmp_path/"workflow-receipts")
    wr._cache.clear()
    class Brain:
        def rank(self,rows,**kwargs):return rows,{'status':'FIXTURE','worker_order':[r.worker_id for r in rows]}
    with patch.object(wr.RouterBrain,'configured',return_value=Brain()):yield

class SDK:
    def __init__(self):
        self.calls=[];self.value=object()
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.messages=SimpleNamespace(create=self.create)
        self.responses=SimpleNamespace(create=self.create)
    def create(self,**kwargs):self.calls.append(kwargs);return self.value
    def with_options(self,**kwargs):return self


def test_shared_brain_is_consulted_and_receipt_identifies_actual_transport():
    called=[]
    class Brain:
        def rank(self,rows,**kwargs):called.append(kwargs);return rows,{'worker_order':[rows[0].worker_id]}
    with patch.object(wr.RouterBrain,'configured',return_value=Brain()):
        chosen,receipt=wr.select('fixture',[wr.native_offer('native-provider','native-model')],task='synthetic')
    assert called and chosen=='native' and receipt['selected_provider']=='native-provider'


def test_unknown_worker_cannot_execute():
    class Brain:
        def rank(self,rows,**kwargs):return [SimpleNamespace(worker_id='invented')],{}
    with patch.object(wr.RouterBrain,'configured',return_value=Brain()):
        with pytest.raises(RouterDecisionError):wr.select('fixture',[wr.native_offer('provider','model')])


@pytest.mark.parametrize('kwargs',[
 {'messages':[{'role':'user','content':'task'}],'tools':[{'type':'function','function':{'name':'read'}}]},
 {'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,AAAA'}}]}]},
 {'messages':[{'role':'user','content':'task'}],'functions':[{'name':'read'}]},
])
def test_tools_and_images_are_never_offered_to_text_cli(kwargs):
    sdk=SDK();client=wr.RoutedClient(sdk,'native','model')
    real=wr.select;seen=[]
    def choose(workflow,offers,**kw):seen.extend(o['id'] for o in offers);return real(workflow,offers,**kw)
    with patch.object(wr,'select',side_effect=choose),patch.object(wr,'text_via_codex',side_effect=AssertionError('CLI must not receive native tool/image calls')):
        assert client.chat.completions.create(**kwargs) is sdk.value
    assert seen==['native'] and sdk.calls[0]['messages'] is kwargs['messages']


def test_blocked_route_makes_zero_provider_calls():
    sdk=SDK();client=wr.RoutedClient(sdk,'native','model')
    with patch.object(wr,'select',side_effect=RouterDecisionError('denied')):
        with pytest.raises(RouterDecisionError):client.chat.completions.create(messages=[])
    assert sdk.calls==[]


@pytest.mark.parametrize('protocol',['messages','responses'])
def test_native_protocol_shape_is_preserved(protocol):
    sdk=SDK();client=wr.RoutedClient(sdk,'native','model')
    args={'model':'model','input':'request'}
    assert getattr(client,protocol).create(**args) is sdk.value
    assert len(sdk.calls)==1 and {k:v for k,v in sdk.calls[0].items() if k!="timeout"}==args
    assert 0<sdk.calls[0]["timeout"]<=90


def test_async_native_stream_is_returned_unchanged():
    sdk=SDK()
    async def create(**kwargs):sdk.calls.append(kwargs);return sdk.value
    sdk.chat.completions.create=create
    client=wr.RoutedClient(sdk,'native','model',async_mode=True,allow_cli=False)
    assert asyncio.run(client.chat.completions.create(messages=[],stream=True)) is sdk.value


def test_with_options_does_not_strip_routing():
    client=wr.RoutedClient(SDK(),'native','model').with_options(timeout=5)
    assert isinstance(client,wr.RoutedClient)
    with patch.object(wr,'select',side_effect=RouterDecisionError('denied')):
        with pytest.raises(RouterDecisionError):client.chat.completions.create(messages=[])


def test_native_middleware_preserves_call_payload():
    request={'messages':[{'role':'user','content':'synthetic'}],'tools':[{'type':'function'}]}
    called=[]
    value=plugin.llm_execution(request,lambda x:called.append(x) or 'response',provider='native',model='model')
    assert value=='response' and len(called)==1 and called[0]['messages'] is request['messages'] and called[0]['tools'] is request['tools']
    assert 0<called[0]['timeout']<=120


def test_native_host_fail_open_middleware_cannot_swallow_router_denial():
    from hermes_cli import middleware,plugins
    manager=SimpleNamespace(_middleware={'llm_execution':[plugin.llm_execution]},_report_hook_failure=lambda *a,**kw:None)
    calls=[]
    with patch.object(plugins,'_delivery_manager',return_value=manager),patch.object(plugin,'select',side_effect=RouterDecisionError('denied')):
        with pytest.raises(RouterDecisionError,match='denied'):
            middleware.run_llm_execution_middleware({'messages':[]},lambda req:calls.append(req),provider='native',model='model')
    assert calls==[]


def test_auxiliary_install_fails_closed_on_missing_physical_contract():
    resolver=lambda *a,**kw:None
    module=SimpleNamespace(_resolve_call_client=resolver)
    with pytest.raises(RuntimeError,match='physical-attempt contract'):
        plugin.install_auxiliary(module)
    assert module._resolve_call_client is resolver


def test_genai_image_keeps_image_capable_backend():
    sdk=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **k:('image',k)))
    with patch.object(wr,'text_via_codex',side_effect=AssertionError('no text worker for images')):
        result=wr.RoutedGenAIClient(sdk).models.generate_content(model='image-model',contents='draw')
    assert result[0]=='image'


def test_genai_grounding_keeps_vendor_tool_backend():
    sdk=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **k:'grounded'))
    seen=[]
    def choose(workflow,offers,**kwargs):seen.extend(o['id'] for o in offers);return 'native',{}
    with patch.object(wr,'select',side_effect=choose):
        assert wr.RoutedGenAIClient(sdk).models.generate_content(model='text-model',contents='research',config={'tools':['search']})=='grounded'
    assert seen==['native']


def test_cv_adapter_requires_a_routed_result_before_resolving_facts():
    sys.path.insert(0,str(ROOT/'career-ops/cv-template-prototype'))
    import cv_content_adapter as cv
    request={'jd':'synthetic','capacities':[],'mode':'generate'}
    with patch.object(wr,'complete_text',side_effect=RouterDecisionError('denied')):
        with pytest.raises(RouterDecisionError):cv.generate(request)


def test_cv_routed_plan_remains_inside_original_fact_bank():
    sys.path.insert(0,str(ROOT/'career-ops/cv-template-prototype'))
    import cv_content_adapter as cv
    bank=json.loads((ROOT/'career-ops/cv-template-prototype/fact_bank.json').read_text())
    selections={k:next(iter(v)) for k,v in bank['slots'].items()}
    response=SimpleNamespace(model='fixture',choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps({'selections':selections})))])
    with patch.object(wr,'complete_text',return_value=(response,{'selected_provider':'fixture'})) as call:
        content=cv.generate({'jd':'synthetic','capacities':[],'mode':'generate'})
    assert set(content)==set(bank['slots']) and call.call_args.kwargs['workflow']=='career.cv.plan'
    assert cv.generate.last_metadata['provider']=='fixture'


def test_profile_scope_cache_does_not_reuse_a_different_model_or_task():
    calls=[]
    class Brain:
        def rank(self,rows,**kwargs):calls.append(1);return rows,{}
    with patch.object(wr.RouterBrain,'configured',return_value=Brain()):
        wr.select('scope',[wr.native_offer('p','m')],task='a')
        _,cached=wr.select('scope',[wr.native_offer('p','m')],task='a')
        wr.select('scope',[wr.native_offer('p','m2')],task='a')
        wr.select('scope',[wr.native_offer('p','m')],task='b')
    assert len(calls)==3 and cached['cached']


def test_discovery_auto_uses_brain_choice_not_local_provider_order():
    import ast
    path=ROOT/'career-ops/discovery/pipeline.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_semantic_stage')
    calls=[]
    scope={'deepseek_probe':lambda model:{'available':True},
        '_execute_semantic_stage':lambda records,**kw:calls.append(kw['semantic']) or {'provider':kw['semantic'],'classified':1,'classifications':{'fixture':{}}}}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    with patch.object(wr,'select',return_value=('codex',{'worker_order':['codex','deepseek']})):
        result=scope['_semantic_stage']([],semantic='auto',deepseek_model='fixture',batch_size=1,timeout=10,mode='high_recall')
    assert calls==['codex'] and result['requested']=='auto' and 'router_decision' in result


def test_discovery_fallback_follows_only_brain_authorized_order():
    import ast
    path=ROOT/'career-ops/discovery/pipeline.py';tree=ast.parse(path.read_text(encoding="utf-8"))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_semantic_stage')
    calls=[]
    def execute(records,**kw):
        calls.append(kw['semantic'])
        return {'provider':'none','classified':0,'classifications':{}} if kw['semantic']=='deepseek' else {'provider':'codex','classified':1,'classifications':{'fixture':{}}}
    scope={'deepseek_probe':lambda model:{'available':True},'_execute_semantic_stage':execute}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    with patch.object(wr,'select',return_value=('deepseek',{'worker_order':['deepseek','codex']})):
        result=scope['_semantic_stage']([],semantic='auto',deepseek_model='fixture',batch_size=1,timeout=10,mode='high_recall')
    assert calls==['deepseek','codex'] and result['provider']=='codex'


def test_linkedin_judge_child_wraps_its_client_before_generation():
    import ast
    path=ROOT/'career-ops/linkedin_factcheck.py';tree=ast.parse(path.read_text(encoding="utf-8"))
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_JUDGE_CHILD' for t in n.targets))
    script=ast.literal_eval(assignment.value)
    ast.parse(script)
    assert 'client = RoutedGenAIClient(genai.Client' in script


def test_direct_business_adapter_imports_are_removed_from_review_copy():
    import importlib.util
    spec=importlib.util.spec_from_file_location('proposal_arch_audit',ROOT/'scripts/e3_architecture_audit.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.audit()
    assert report['pass'],report['failures']


def test_bounded_classifier_profile_cannot_write_or_spawn_subagents():
    import codex_adapter as ca
    with patch.object(ca,'_resolve_codex_executable',return_value=Path('codex')),patch.object(ca.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='',stderr='')) as run:
        ca.CodexExecutionAdapter('classification').dispatch({'model':'gpt-6-sol','objective':'synthetic'})
        command=run.call_args_list[0].args[0]
    assert command[command.index('--sandbox')+1]=='read-only'
    assert 'shell_tool' in command and 'multi_agent' in command


@pytest.mark.parametrize("failure",[ValueError("unexpected"),RuntimeError("unexpected")])
def test_native_host_cannot_fail_open_on_unexpected_router_failure(failure):
    from hermes_cli import middleware,plugins
    manager=SimpleNamespace(_middleware={"llm_execution":[plugin.llm_execution]},_report_hook_failure=lambda *a,**kw:None)
    calls=[]
    with patch.object(plugins,"_delivery_manager",return_value=manager),patch.object(plugin,"select",side_effect=failure):
        with pytest.raises(type(failure),match="unexpected"):
            middleware.run_llm_execution_middleware({"messages":[]},lambda req:calls.append(req),provider="native",model="model")
    assert calls==[]


def test_genai_structured_config_stays_on_native_backend():
    sdk=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **k:k))
    seen=[]
    def choose(workflow,offers,**kwargs):seen.extend(o["id"] for o in offers);return "native",{}
    config={"response_mime_type":"application/json","response_schema":{"type":"object"}}
    with patch.object(wr,"select",side_effect=choose):
        result=wr.RoutedGenAIClient(sdk).models.generate_content(model="text-model",contents="synthetic",config=config)
    assert seen==["native"] and all(result["config"][k]==v for k,v in config.items())
    assert "http_options" not in config and 0<result["config"]["http_options"]["timeout"]<=90000


def test_missing_cli_usage_is_unknown_not_fabricated_zero():
    assert wr._completion("synthetic","model").usage is None


def test_streaming_and_unsupported_controls_keep_native_transport():
    assert not wr._plain({"messages":[],"stream":True})
    assert not wr._plain({"messages":[],"response_format":{"type":"json_object"}})
    assert not wr._plain({"messages":[],"temperature":0.7})


def test_route_and_generation_share_one_elapsed_budget():
    sdk=SDK();client=wr.RoutedClient(sdk,"provider","model")
    def select(workflow,offers,**kw):
        assert kw["timeout"]<=5
        return "native",{}
    with patch.object(wr,"select",side_effect=select):
        client.chat.completions.create(messages=[],timeout=5)
    assert 0<sdk.calls[0]["timeout"]<=5


def test_exhausted_budget_blocks_downstream():
    sdk=SDK();client=wr.RoutedClient(sdk,"provider","model")
    with pytest.raises(TimeoutError):client.chat.completions.create(messages=[],timeout=0)
    assert not sdk.calls


def test_guarded_gateway_blocks_missing_router_before_host():
    import router_gateway_entry as entry
    calls=[]
    host=SimpleNamespace(run_llm_execution_middleware=lambda *a,**kw:calls.append(a))
    plugins=SimpleNamespace(_delivery_manager=lambda:SimpleNamespace(_middleware={}))
    entry.install_guard(host,plugins)
    with pytest.raises(RuntimeError,match="Mandatory router"):
        host.run_llm_execution_middleware({},lambda request:None)
    assert not calls


def test_guarded_gateway_rechecks_registration_each_call():
    import router_gateway_entry as entry
    callbacks=[plugin.llm_execution];calls=[]
    manager=SimpleNamespace(_middleware={"llm_execution":callbacks})
    plugins=SimpleNamespace(_delivery_manager=lambda:manager)
    host=SimpleNamespace(run_llm_execution_middleware=lambda *a,**kw:calls.append(a) or "ok")
    entry.install_guard(host,plugins)
    assert host.run_llm_execution_middleware({},lambda request:None)=="ok"
    callbacks.clear()
    with pytest.raises(RuntimeError):host.run_llm_execution_middleware({},lambda request:None)
    assert len(calls)==1


def test_guarded_launcher_is_recognized_by_native_lifecycle_controls():
    from gateway.status import looks_like_gateway_command_line
    command='python "'+str(ROOT/'exec-brain/hermes_cli.main_router.py')+'" gateway run'
    assert looks_like_gateway_command_line(command)
    assert not looks_like_gateway_command_line(command.replace('gateway run','gateway status'))


def test_router_uses_45_seconds_without_retries():
    calls=[]
    class Brain:
        def rank(self,rows,**kwargs):calls.append(kwargs['timeout']);return rows,{}
    with patch.object(wr.RouterBrain,'configured',return_value=Brain()):
        wr.select('bounded',[wr.cli_offer()],task='synthetic')
    assert len(calls)==1 and 44<calls[0]<=45


def test_explicit_codex_never_initializes_or_calls_native():
    with patch.object(wr,'native_client',side_effect=AssertionError('No native access')),patch.object(wr,'text_via_codex',return_value='synthetic') as worker:
        response,receipt=wr.complete_text([{'role':'user','content':'synthetic'}],workflow='career.cv.plan',worker='codex')
    assert receipt['selected_provider']=='openai' and response.model=='gpt-6.1-sol'
    assert 0<worker.call_args.kwargs['timeout']<=90


def test_explicit_codex_still_requires_brain_authorization():
    with patch.object(wr,'select',side_effect=RouterDecisionError('router_cli_timeout')),patch.object(wr,'text_via_codex') as worker:
        with pytest.raises(RouterDecisionError):wr.complete_text([],workflow='fixture',worker='codex')
    worker.assert_not_called()


def test_router_error_is_nonretryable_through_host_classification():
    from agent.error_classifier import classify_api_error
    from hermes_cli import plugins
    error=RouterDecisionError('router_cli_timeout')
    with patch.object(plugins,'invoke_hook',return_value=[plugin.router_error_classification(error=error)]):
        result=classify_api_error(error,provider='nous',model='fixture')
    assert not result.retryable and not result.should_fallback and not result.should_compress
    assert not result.should_rotate_credential
    assert result.error_context['component']=='router_brain'
    assert plugin.router_error_classification(error=RuntimeError('router_cli_timeout')) is None


def test_router_copy_is_specific_and_preserves_unrelated_errors():
    module=SimpleNamespace(nonretryable_copy=lambda *a,**kw:'original')
    plugin.install_failure_copy(module)
    error=SimpleNamespace(error_context={'component':'router_brain','router_failure':'router_cli_timeout'})
    text=module.nonretryable_copy(error,provider='nous',summary='PRIVATE-TOKEN')
    assert 'Codex router' in text and 'Nous' not in text and 'PRIVATE-TOKEN' not in text
    assert 'without automatic retries' in text
    assert module.nonretryable_copy(SimpleNamespace(error_context={}))=='original'


def test_codex_cv_preference_survives_pickling_and_reaches_worker():
    import pickle
    sys.path.insert(0,str(ROOT/'career-ops/cv-template-prototype'))
    import cv_content_adapter as cv
    planner=pickle.loads(pickle.dumps(cv.RoutedContentPlanner('codex')))
    with patch.object(cv,'generate',return_value={'fixture':'result'}) as generate:
        assert planner({'jd':'synthetic'})=={'fixture':'result'}
        assert generate.call_args.args[0]['worker']=='codex'
