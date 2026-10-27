import json
import pytest
import workflow_routing as wr
from workflow_control import run_stage
from router_brain import RouterDecisionError

@pytest.fixture(autouse=True)
def isolated_receipts(tmp_path,monkeypatch):
    monkeypatch.setattr(wr,'RECEIPT_ROOT',tmp_path/'receipts')
    wr._cache.clear()

def test_stage_handoff_requires_real_receipt_and_exact_research():
    topic={'title':'Synthetic topic','url':'https://example.invalid/source'}
    _,receipt=run_stage('fixture','research',{},lambda:[topic],lambda v:True)
    written,child=run_stage('fixture','writing',{'prompt':'synthetic'},lambda:'draft',lambda v:True,
                             upstream=receipt,handoff=topic)
    assert child['upstream_call_id']==receipt['call_id'] and written=='draft'
    for supplied in (dict(topic,title='Tampered'),{'unknown':'not in research'}):
        with pytest.raises(RouterDecisionError,match='stage_handoff_changed'):
            run_stage('fixture','writing',{},lambda:pytest.fail('writer ran'),lambda v:True,
                      upstream=receipt,handoff=supplied)

def test_invented_stage_and_worker_failure_never_pass():
    with pytest.raises(RouterDecisionError,match='stage_handoff_unverified'):
        run_stage('fixture','writing',{},lambda:pytest.fail('writer ran'),lambda v:True,
                  upstream={'call_id':'invented'})
    def failed():raise RouterDecisionError('router_cli_usage_limit')
    with pytest.raises(RouterDecisionError):run_stage('fixture','research',{},failed,lambda v:True)
    records=[json.loads(p.read_text()) for p in wr.RECEIPT_ROOT.glob('*.json')]
    assert all(r['status']=='STAGE_FAILED' for r in records)

def test_empty_output_and_failed_review_are_not_success():
    with pytest.raises(RouterDecisionError,match='stage_validation_failed'):
        run_stage('fixture','writing',{},lambda:'',bool)
    with pytest.raises(RouterDecisionError,match='stage_validation_failed'):
        run_stage('fixture','review',{},lambda:{'verdict':'fail'},lambda v:v['verdict']=='pass')
    assert all(json.loads(p.read_text())['status']=='STAGE_FAILED' for p in wr.RECEIPT_ROOT.glob('*.json'))

def test_linkedin_codex_research_uses_search_adapter_not_google_tools(monkeypatch):
    import linkedin_stage_workflow as li
    from discovery.web_research import CodexWebSearchProvider
    topic={'title':'Synthetic','summary':'Synthetic summary','technical_impact':'Impact',
           'non_technical_impact':'Impact','url':'https://example.invalid/source',
           'sources':['https://example.invalid/source']}
    route={'selected_provider':'openai','selected_model':'gpt-6.1-sol'}
    monkeypatch.setattr(li,'select',lambda workflow,offers,**k:('codex',route))
    monkeypatch.setattr(CodexWebSearchProvider,'resolve',lambda self:'never-executed')
    for observed in (False,True):
        monkeypatch.setattr(CodexWebSearchProvider,'_run_one',lambda *a,**k:{'web_search_observed':observed,'results':[topic]})
        if not observed:
            with pytest.raises(RouterDecisionError,match='search_not_verified'):
                li.research('Synthetic research',1,client=None,parse=lambda *a:[],worker='codex')
        else:
            result=li.research('Synthetic research',1,client=None,parse=lambda *a:[],worker='codex')
            assert result[0]['research_receipt']['status']=='STAGE_VALIDATED'

def test_post_fact_failure_stays_quarantined(monkeypatch):
    import linkedin_content_gen as li
    monkeypatch.setattr(li,'cache_topic_sources',lambda t:{'cached':t['sources'],'failed':[]})
    monkeypatch.setattr(li,'generate_linkedin_content',lambda *a,**k:'Synthetic draft')
    monkeypatch.setattr(li,'factcheck_post',lambda *a:{'verdict':'fail','reason':'unsupported'})
    monkeypatch.setattr(li,'report_problem',lambda *a,**k:None)
    topic={k:'Synthetic' for k in ('title','summary','technical_impact','non_technical_impact')}
    result=li.generate_post_from_topic(dict(topic,sources=['https://example.invalid/source']))
    assert result['blocked'] and result['gate_verdict']=='fail'
    records=[json.loads(p.read_text()) for p in wr.RECEIPT_ROOT.glob('*.json')]
    assert any(r['stage']=='factual-review' and r['status']=='STAGE_FAILED' for r in records)

def test_public_persona_uses_authoritative_sources(monkeypatch):
    import linkedin_content_gen as li
    import hermes_owner_context as owner
    monkeypatch.setattr(owner,'retrieve',lambda q:('AUTHORITATIVE_CURRENT_CONTEXT',[{'complete':True}]))
    assert li._load_persona_block()=='AUTHORITATIVE_CURRENT_CONTEXT'
    assert li.review_linkedin_draft('Synthetic')['scoring_performed'] is False


def test_fact_judge_routes_as_verification_not_writing(monkeypatch):
    from types import SimpleNamespace as NS
    selected=[]
    monkeypatch.setattr(wr,'select',lambda workflow,offers,**kw:(selected.append((workflow,kw['family'])) or ('native',{})))
    sdk=NS(models=NS(generate_content=lambda **kw:NS(text='verified')))
    client=wr.RoutedGenAIClient(sdk,workflow='career.linkedin.factcheck',family='verification')
    assert client.models.generate_content(model='fixture',contents='Check this claim').text=='verified'
    assert selected==[('career.linkedin.factcheck','verification')]


def test_reused_topic_is_blocked_before_source_fetch_and_writer(tmp_path,monkeypatch):
    import linkedin_content_gen as li
    monkeypatch.setattr(li,'CONTROL_PLANE',tmp_path)
    registry=tmp_path/'runtime/linkedin/topic_registry.json';registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({'topics':[{'topic':'Already covered','status':'used','strict':True,'signals':['fictional used topic']}]}))
    monkeypatch.setattr(li,'cache_topic_sources',lambda *a:pytest.fail('Source fetch ran for duplicate'))
    monkeypatch.setattr(li,'generate_linkedin_content',lambda *a,**k:pytest.fail('Writer ran for duplicate'))
    topic={k:'fictional used topic' for k in ('title','summary','technical_impact','non_technical_impact')}
    with pytest.raises(RouterDecisionError,match='linkedin_topic_reused'):
        li.generate_post_from_topic(dict(topic,sources=[]))


def test_research_receives_current_used_topic_exclusions(tmp_path,monkeypatch):
    import linkedin_content_gen as li
    import linkedin_stage_workflow as stage
    monkeypatch.setattr(li,'CONTROL_PLANE',tmp_path)
    monkeypatch.setattr(li,'_get_gemini_client',lambda:None)
    registry=tmp_path/'runtime/linkedin/topic_registry.json';registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({'topics':[{'topic':'Fictional excluded topic','status':'used','strict':True,'signals':['one special signal']}]}))
    seen=[]
    monkeypatch.setattr(stage,'research',lambda prompt,*a,**kw:seen.append(prompt) or [])
    li.research_trending_topics(3)
    assert 'Fictional excluded topic' in seen[0] and 'one special signal' in seen[0]
    assert 'physical world' in seen[0]
