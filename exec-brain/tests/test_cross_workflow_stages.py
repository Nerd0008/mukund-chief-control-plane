import sys,json,ast,time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'exec-brain'),str(ROOT/'career-ops')]
import workflow_routing as wr
from router_brain import RouterDecisionError

@pytest.fixture(autouse=True)
def receipts(tmp_path,monkeypatch):monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts')

def test_research_denial_is_structured_and_stops_queries():
    from discovery.web_research import CodexWebSearchProvider
    provider=CodexWebSearchProvider();provider._resolved='fixture-codex'
    with patch.object(wr,'select',side_effect=RouterDecisionError('router_cli_timeout')) as route:
        result=provider.research([{'query_id':str(i),'query':'synthetic'} for i in range(3)],timeout=60)
    assert result['routing_blocked'] and result['requests']==0 and route.call_count==1
    assert result['queries'][0]['executed'] is False and result['limitation']=='router_cli_timeout'

def test_semantic_denial_never_uses_another_worker():
    from discovery import pipeline
    with patch.object(wr,'select',side_effect=RouterDecisionError('router_cli_timeout')),patch.object(pipeline,'_execute_semantic_stage') as worker:
        result=pipeline._semantic_stage([],semantic='codex',deepseek_model='fixture',batch_size=1,timeout=60,mode='high_recall')
    assert result['routing_blocked'] and not result['classifications'];worker.assert_not_called()

def test_judge_stops_after_one_known_routing_failure():
    import re
    tree=ast.parse((ROOT/'career-ops/linkedin_factcheck.py').read_text(encoding='utf-8'))
    child=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_JUDGE_CHILD' for t in n.targets))
    loop=next(n for n in ast.parse(child).body if isinstance(n,ast.For));calls=[]
    def generate(**kw):calls.append(kw);raise RouterDecisionError('router_cli_timeout')
    scope={'client':NS(models=NS(generate_content=generate)),'runs':2,'responses':[],'out':[],'prompt':'synthetic','model':'fixture','re':re,'json':json,'RouterDecisionError':RouterDecisionError}
    exec(compile(ast.Module(body=[loop],type_ignores=[]),'judge-loop','exec'),scope)
    assert len(calls)==1 and scope['responses'][0]['error']=='router_cli_timeout'

def test_genai_timeout_subtracts_route_and_disables_hidden_retries():
    native=NS(models=NS(generate_content=lambda **kw:kw))
    def select(*a,**kw):assert kw['timeout']<=5;time.sleep(.02);return 'native',{}
    with patch.object(wr,'select',side_effect=select):
        result=wr.RoutedGenAIClient(native).models.generate_content(model='text',contents='synthetic',config={'http_options':{'timeout':5000}})
    assert 0<result['config']['http_options']['timeout']<4990
    assert result['config']['http_options']['retry_options']=={'attempts':1}

def test_async_transport_cannot_ignore_wall_clock_budget():
    import asyncio
    async def slow(**kw):await asyncio.sleep(10)
    sdk=NS(chat=NS(completions=NS(create=slow)))
    client=wr.RoutedClient(sdk,'p','m',async_mode=True)
    started=time.monotonic()
    with patch.object(wr,'select',return_value=('native',{})):
        with pytest.raises(TimeoutError):asyncio.run(client.chat.completions.create(messages=[],timeout=.05))
    assert time.monotonic()-started<1

def test_cover_content_worker_receives_explicit_constraint():
    import cover_content_adapter as adapter
    paragraphs=['A complete paragraph.']*5
    response=NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps({'paragraphs':paragraphs})))])
    with patch.object(wr,'complete_text',return_value=(response,{'selected_provider':'openai'})) as request:
        result,receipt=adapter.plan(paragraphs,'Example','Graduate',timeout=5,worker='codex')
    assert result==paragraphs and request.call_args.kwargs['worker']=='codex'
    assert request.call_args.kwargs['workflow']=='career.cover.plan'

def test_cover_worker_failure_never_renders_or_retries(tmp_path,monkeypatch):
    import hermes_cv_compiler_guard as guard
    import hermes_cover_tool as cover
    import cover_content_adapter as adapter
    monkeypatch.setattr(cover,'ROOT',tmp_path)
    token=guard.JOB.set({'deadline':time.monotonic()+180,'cv_active':True,'content_worker':'codex'})
    args={'company':'Example','role':'Graduate','paragraphs':['A complete paragraph.']*5}
    try:
        with patch.object(adapter,'plan',side_effect=RouterDecisionError('bounded_text_worker_usage_limit')) as model,patch.object(cover.subprocess,'run') as render:
            result=json.loads(cover.cover_tool(args))
            again=json.loads(cover.cover_tool(dict(args,paragraphs=['A corrected paragraph.']*5)))
        assert result['status']=='FAIL' and result['reason']=='bounded_text_worker_usage_limit'
        assert again['status']=='FAIL' and model.call_count==1;render.assert_not_called()
    finally:guard.JOB.reset(token)

def test_negative_worker_request_is_honored():
    from workflow_control import requested_worker
    assert requested_worker("Don't use Codex for this CV")=='native'
    assert requested_worker('Use Codex for the router') is None
    assert requested_worker('Use Codex for this cover letter')=='codex'
