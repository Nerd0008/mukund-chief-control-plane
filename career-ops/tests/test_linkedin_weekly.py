import json
import pytest
import linkedin_weekly as weekly
from router_brain import RouterDecisionError
from test_linkedin_state import gate,personal


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    root=tmp_path/'linkedin';root.mkdir()
    (root/'topic_registry.json').write_text(json.dumps({'topics':[]}))
    calls=[]
    monkeypatch.setattr(weekly,'retrieve',lambda q:('Complete synthetic professional context',[{'complete':True,'source':'synthetic'}]))
    def research(count,*,category):
        calls.append(('research',category))
        return [{'title':category,'summary':'Synthetic','technical_impact':'Synthetic','non_technical_impact':'Synthetic','sources':['https://synthetic.invalid/article']}]
    def news(topic,**kwargs):
        calls.append(('writing',topic['title']));body='I would check this '+topic['title']+' example. What would you check?'
        return {'post_text':body,'news_fact_gate':gate(body),'blocked':False}
    monkeypatch.setattr(weekly.gen,'research_trending_topics',research)
    monkeypatch.setattr(weekly.gen,'cache_topic_sources',lambda topic:{'cached':topic['sources'],'failed':[]})
    monkeypatch.setattr(weekly.gen,'generate_post_from_topic',news)
    monkeypatch.setattr(weekly.gen,'generate_linkedin_content',lambda *a,**k:'I keep a small question list. Which question would you start with?')
    monkeypatch.setattr(weekly.gen,'factcheck_post',lambda body,sources:gate(body))
    monkeypatch.setattr(weekly.state,'_personal_runner',lambda body,label:personal(body))
    monkeypatch.setattr(weekly.gen,'generate_image_bytes',lambda *a:pytest.fail('unapproved image generated'))
    return root,calls


def test_weekly_mix_has_three_real_stage_contracts_and_no_approval(prepared):
    root,calls=prepared;doc=weekly.prepare('2026-11-02',root=root)
    assert doc['ok'] and doc['ready_count']==3
    assert [p['category'] for p in doc['posts'].values()]==['ai_cyber','ai_noncyber','personal']
    assert all(p['phase']=='AWAITING_OWNER_APPROVAL' and not p['owner_approved'] for p in doc['posts'].values())
    assert not doc['publish_performed'] and doc['images_generated']==0
    assert not (root/'drafts').exists() and not (root/'published').exists()
    assert [c for c in calls if c[0]=='research']==[('research','ai_cyber'),('research','ai_noncyber')]
    assert weekly.render(doc).count('APPROVE LINKEDIN ')==3


def test_weekly_resume_reuses_exact_completed_reviewed_posts(prepared):
    root,calls=prepared;first=weekly.prepare('2026-11-02',root=root);before=list(calls)
    second=weekly.prepare('2026-11-02',root=root)
    assert second['ok'] and second['posts']==first['posts'] and calls==before


def test_weekly_incomplete_profile_stops_before_workers(prepared,monkeypatch):
    root,calls=prepared
    monkeypatch.setattr(weekly,'retrieve',lambda q:('Partial',[{'complete':False}]))
    with pytest.raises(RouterDecisionError,match='linkedin_profile_incomplete'):weekly.prepare('2026-11-02',root=root)
    assert not calls


def test_weekly_quota_failure_retains_completed_slot_and_stops(prepared,monkeypatch):
    root,calls=prepared;original=weekly.gen.research_trending_topics
    def fail(count,*,category):
        if category=='ai_noncyber':raise RouterDecisionError('router_cli_usage_limit')
        return original(count,category=category)
    monkeypatch.setattr(weekly.gen,'research_trending_topics',fail)
    doc=weekly.prepare('2026-11-02',root=root)
    assert not doc['ok'] and doc['ready_count']==1
    assert doc['posts']['tuesday']['phase']=='AWAITING_OWNER_APPROVAL'
    assert doc['posts']['wednesday']['error']=='router_cli_usage_limit'
    assert 'thursday' not in doc['posts']
    assert (root/'review/2026-11-02/weekly.json').exists()


def test_weekly_failed_news_gate_never_reaches_personal_or_approval(prepared,monkeypatch):
    root,calls=prepared
    monkeypatch.setattr(weekly.gen,'generate_post_from_topic',lambda *a,**k:{'post_text':'Unverified','blocked':True})
    doc=weekly.prepare('2026-11-02',root=root)
    assert not doc['ok'] and doc['posts']['tuesday']['phase']=='BLOCKED'
    assert not (root/'drafts').exists()


def test_personal_correction_reruns_news_and_binds_new_body(prepared,monkeypatch):
    root,calls=prepared
    old='I would review this wording.';new='I would ask a clearer question.'
    reviews=iter([{'available':True,'verdict':'block','unsupportedFacts':[{'value':'unverified tool'}],'exit_code':1},personal(new)])
    monkeypatch.setattr(weekly.state,'_personal_runner',lambda *a:next(reviews))
    monkeypatch.setattr(weekly.gen,'generate_linkedin_content',lambda *a,**k:new)
    judged=[]
    monkeypatch.setattr(weekly.gen,'factcheck_post',lambda body,sources:judged.append(body) or gate(body))
    result=weekly.complete_reviews({'post_text':old,'news_fact_gate':gate(old)},label='synthetic',context_hash='profile')
    assert result['post_text']==new and judged==[new]
    assert result['news_fact_gate']['body_sha256']==weekly.fc.sha256_text(weekly.fc.post_prose(new))
    assert [r['verdict'] for r in result['personal_review_attempts']]==['block','pass']
    assert 'owner_approval' not in result


def test_existing_blocked_approval_is_preserved_without_claiming_ready(prepared,monkeypatch):
    root,calls=prepared
    path=root/'drafts/approved_20261103_tuesday/linkedin_drafts.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'post_text':'Existing approved text'}))
    monkeypatch.setattr(weekly.state,'inspect_artifact',lambda *a,**k:{'owner_approved':True,'content_ready':False,'body_sha256':'real-sha','phase':'APPROVED_BUT_BLOCKED'})
    doc=weekly.prepare('2026-11-02',root=root)
    assert doc['posts']['tuesday']['owner_approved'] and doc['ready_count']==2 and not doc['ok']
    output=weekly.render(doc)
    assert 'Existing exact owner approval preserved.' in output and 'APPROVE LINKEDIN real-sha' not in output
    assert ('research','ai_cyber') not in calls


def test_authoritative_registry_blocks_exhausted_safepaste_narrative():
    registry=weekly.REPO/'runtime/linkedin/topic_registry.json'
    report=weekly.check_text('I use pattern matching in my SafePaste project.',registry_path=registry)
    assert report['blocked']
    assert any(m['status']=='retired' for m in report['matches'])


def test_source_less_claim_correction_preserves_failure_evidence(prepared,monkeypatch):
    root,calls=prepared
    bodies=iter(['A general assertion about the world.','I would start by asking a question.'])
    monkeypatch.setattr(weekly.gen,'generate_linkedin_content',lambda *a,**k:next(bodies))
    gates=iter([{'verdict':'ungated','llm_used':True,'world_claims':[{'claim':'A general assertion about the world.'}]},gate('I would start by asking a question.')])
    monkeypatch.setattr(weekly.gen,'factcheck_post',lambda *a:next(gates))
    recorded=[];result=weekly.personal_reflection('Exhausted angle',record=recorded.append)
    assert not result['blocked'] and len(result['reflection_attempts'])==2
    assert any(r.get('news_fact_gate',{}).get('world_claims') for r in recorded)
    assert result['reflection_attempts'][0]['post_text']=='A general assertion about the world.'
    assert result['reflection_attempts'][0]['news_fact_gate']['world_claims']


def test_source_less_judge_outage_is_not_retried(prepared,monkeypatch):
    root,calls=prepared;written=[];recorded=[]
    monkeypatch.setattr(weekly.gen,'generate_linkedin_content',lambda *a,**k:written.append(a) or 'Synthetic opinion')
    monkeypatch.setattr(weekly.gen,'factcheck_post',lambda *a:{'verdict':'ungated','llm_used':False,'available':False})
    with pytest.raises(RouterDecisionError,match='linkedin_reflection_review_blocked'):
        weekly.personal_reflection('Exhausted angle',record=recorded.append)
    assert len(written)==1 and recorded[-1]['news_fact_gate']['available'] is False


def test_blocked_phase_cannot_reuse_stale_passing_receipts():
    body='I would ask a question.'
    post={'post_text':body,'news_fact_gate':gate(body),'personal_fact_gate':personal(body),'blocked':False,'phase':'BLOCKED','error':'router_cli_usage_limit'}
    assert not weekly.accepted(post)
