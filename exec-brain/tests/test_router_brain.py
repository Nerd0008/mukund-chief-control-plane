"""Router reasoning never grants authority or exposes provider identities."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from e3_router import RouterCandidate
from router_brain import RouterBrain, RouterDecisionError


@pytest.fixture(autouse=True)
def source_module_isolation():
    # Older suites intentionally import installed copies and mutate sys.path.
    # These regressions must exercise the changed source, never stale runtime.
    names = ('codex_adapter', 'e3_service', 'e3_shadow_orchestrator')
    prior = {name: sys.modules.get(name) for name in names}
    old_path = list(sys.path)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for name in names:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name, value in prior.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        sys.path[:] = old_path


def candidate(wid,provider,score):
    return RouterCandidate(wid,provider,'private-model','builder','HIGH',['QUALIFIED_WORKER'],'private rationale',score=score,score_components={'task_fit':score})


class Adapter:
    def __init__(self,transform=None):self.contract=None;self.transform=transform
    def dispatch(self,contract):
        self.contract=contract
        data=json.loads(contract['objective'].split('\nINPUT\n')[1])
        profiles=data['eligible_candidates']
        profiles.sort(key=lambda p:p['evidence_score'],reverse=True)
        out={'ranked_handles':[p['handle'] for p in profiles],'needs_owner':False,'reason_codes':['VERIFIED_EVIDENCE']}
        if self.transform:out=self.transform(out)
        return {'status':'COMPLETED','final_message':json.dumps(out),'raw_output':[]}


def test_provider_identity_is_not_in_decision_prompt():
    adapter=Adapter();brain=RouterBrain(adapter)
    ordered,receipt=brain.rank([candidate('codex-cli','openai',1),candidate('longcat','nous',9)],objective='A writing task',task_family='writing',roles=['writer'])
    assert [c.worker_id for c in ordered]==['longcat','codex-cli']
    # Fixed reasoning-model id is a CLI argument; no worker brands are in prompt.
    for word in ('openai','nous','codex-cli','longcat','private-model','private rationale'):
        assert word not in adapter.contract['objective'].lower()
    assert receipt['selection_policy']=='provider_blind_evidence'


def test_openai_can_win_when_its_evidence_is_stronger():
    ordered,_=RouterBrain(Adapter()).rank([candidate('other','vendor',1),candidate('codex-cli','openai',9)],objective='task',task_family='code',roles=['builder'])
    assert ordered[0].worker_id=='codex-cli'


@pytest.mark.parametrize('change',[
    lambda d:{**d,'ranked_handles':['invented-worker']},
    lambda d:{**d,'ranked_handles':d['ranked_handles']*2},
    lambda d:{**d,'needs_owner':'false'},
    lambda d:{**d,'reason_codes':['PREFER_OPENAI']},
    lambda d:{**d,'reason_codes':[]},
    lambda d:{**d,'extra':'hidden'},
    lambda d:{**d,'needs_owner':True},
])
def test_invalid_or_unauthorized_decision_blocks(change):
    with pytest.raises(RouterDecisionError):
        RouterBrain(Adapter(change)).rank([candidate('allowed','vendor',1)],objective='task',task_family='code',roles=[])


def test_empty_eligible_set_does_not_invoke_model():
    adapter=Adapter();result,receipt=RouterBrain(adapter).rank([],objective='task',task_family='code',roles=[])
    assert result==[] and adapter.contract is None and not receipt['provider_call_made']


def test_failure_no_deterministic_or_provider_fallback():
    adapter=SimpleNamespace(dispatch=lambda contract:{'status':'TIMEOUT'})
    with pytest.raises(RouterDecisionError,match='router_cli_failed'):
        RouterBrain(adapter).rank([candidate('allowed','vendor',1)],objective='task',task_family='code',roles=[])


def test_tool_use_fails_closed():
    good=Adapter()
    def dispatch(contract):
        result=good.dispatch(contract);result['raw_output']=[{'type':'item.completed','item':{'type':'command_execution'}}];return result
    with pytest.raises(RouterDecisionError,match='router_used_tool'):
        RouterBrain(SimpleNamespace(dispatch=dispatch)).rank([candidate('allowed','vendor',1)],objective='task',task_family='code',roles=[])


def test_receipt_contains_no_task_or_raw_reasoning(tmp_path):
    adapter=Adapter()
    RouterBrain(adapter,receipt_root=tmp_path).rank([candidate('allowed','vendor',1)],objective='PRIVATE-JD-TEXT',task_family='code',roles=[])
    text=next(tmp_path.glob('*.json')).read_text()
    assert 'PRIVATE-JD-TEXT' not in text and 'objective' not in text
    assert json.loads(text)['status']=='ROUTED'


def test_shadow_order_no_longcat_preference():
    from e3_shadow_orchestrator import E3ShadowOrchestrator
    rows=[candidate('codex-cli','openai',99),candidate('longcat-2.0','longcat',1)]
    assert E3ShadowOrchestrator._apply_owner_route_preference(rows,{},'writing')==rows


def test_cli_router_profile_is_bounded_and_read_only(tmp_path):
    import codex_adapter
    events='\n'.join([json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'{}'}}),json.dumps({'type':'turn.completed'})])
    with patch.object(codex_adapter,'_resolve_codex_executable',return_value=Path('codex')),patch.object(codex_adapter.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=events,stderr='')) as run:
        adapter=codex_adapter.CodexExecutionAdapter('router')
        result=adapter.dispatch({'model':'gpt-6.1-sol','objective':'synthetic','reasoning_effort':'high','working_directory':str(tmp_path),'timeout':15})
        command=run.call_args_list[0].args[0]
        assert command[command.index('--sandbox')+1]=='read-only'
        assert '--ephemeral' in command and '--ignore-user-config' in command
        assert 'shell_tool' in command and 'multi_agent' in command
        assert 'model_reasoning_effort="high"' in command
        assert '--dangerously-bypass-approvals-and-sandbox' not in command
        assert result['status']=='COMPLETED'

def test_fallbacks_follow_evidence_order_not_provider_brand():
    from e3_shadow_orchestrator import E3ShadowOrchestrator as O
    rows=[candidate('vendor-b','b',9),candidate('codex-cli','openai',1)]
    registry=SimpleNamespace(is_routable=lambda wid:wid!='forbidden')
    assert O._approved_fallbacks({},'primary',registry,rows)==['vendor-b','codex-cli']
    assert O._approved_fallbacks({},'primary',registry)==[]


def test_service_filters_permissions_before_brain_and_executes_chosen_worker(tmp_path):
    from e3_service import E3ApplicationService
    allowed=candidate('allowed','vendor',2);forbidden=candidate('forbidden','openai',99)
    worker_calls=[];brain_calls=[]
    adapter=SimpleNamespace(dispatch=lambda contract:worker_calls.append(contract) or {'status':'COMPLETED','content':'ok'})
    registry=SimpleNamespace(is_routable=lambda wid:wid=='allowed',adapter_for=lambda wid:adapter,report_usage=lambda *a:None)
    orch=SimpleNamespace(planner=SimpleNamespace(plan=lambda *a:{'plan_id':'fixture','nodes':[{'node_id':'n','capability_roles':['builder']}]}),router=SimpleNamespace(propose_candidates=lambda *a:[forbidden,allowed]),_apply_owner_route_preference=lambda candidates,*a:candidates)
    def rank(rows,**kwargs):
        brain_calls.append([c.worker_id for c in rows]);return rows,{'status':'ROUTED'}
    with patch('stage2_control.require_enabled',return_value={'allowed_workers':['allowed']}),patch('e3_execution.ExecutionAdapterRegistry',return_value=registry),patch('e3_shadow_orchestrator.E3ShadowOrchestrator',return_value=orch),patch('router_brain.RouterBrain.configured',return_value=SimpleNamespace(rank=rank)):
        result=E3ApplicationService(db_path=tmp_path/'unused.db').execute_chat(messages=[],objective='synthetic',task_family='code')
    assert brain_calls==[['allowed']] and len(worker_calls)==1
    assert result['status']=='COMPLETED' and result['router_decision']['status']=='ROUTED'


def test_service_brain_failure_never_executes_worker(tmp_path):
    from e3_service import E3ApplicationService
    worker_calls=[]
    registry=SimpleNamespace(is_routable=lambda wid:True,adapter_for=lambda wid:worker_calls.append(wid))
    orch=SimpleNamespace(planner=SimpleNamespace(plan=lambda *a:{'plan_id':'fixture','nodes':[{'node_id':'n'}]}),router=SimpleNamespace(propose_candidates=lambda *a:[candidate('eligible','vendor',2)]),_apply_owner_route_preference=lambda rows,*a:rows)
    with patch('stage2_control.require_enabled',return_value={'allowed_workers':['eligible']}),patch('e3_execution.ExecutionAdapterRegistry',return_value=registry),patch('e3_shadow_orchestrator.E3ShadowOrchestrator',return_value=orch),patch('router_brain.RouterBrain.configured',side_effect=RouterDecisionError('router_brain_not_configured')):
        result=E3ApplicationService(db_path=tmp_path/'unused.db').execute_chat(messages=[],objective='synthetic')
    assert result['status']=='FAILED' and result['error']=='router_brain_not_configured' and worker_calls==[]

def test_candidate_filter_uses_actual_task_risk_not_r1():
    from e3_router import E3Router
    seen=[]
    registry=SimpleNamespace(find_eligible_workers=lambda family,role,**kw:seen.append(kw['risk_class']) or [])
    E3Router(registry,worker_registry=SimpleNamespace()).propose_candidates({'capability_roles':['builder']},'code',SimpleNamespace(risk_class='R3'))
    assert seen==['R3']

def test_audit_storage_failure_blocks_a_decision(tmp_path):
    blocked=tmp_path/'not-a-directory';blocked.write_text('preserve')
    with pytest.raises(RouterDecisionError,match='router_receipt_unavailable'):
        RouterBrain(Adapter(),receipt_root=blocked).rank([candidate('allowed','vendor',1)],objective='synthetic',task_family='code',roles=[])
    assert blocked.read_text()=='preserve'
