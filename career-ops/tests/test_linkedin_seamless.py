import json,hashlib
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
import pytest
import linkedin_state as state
import linkedin_approval as consent
from linkedin_conversation import interpret
import career_workflow_bridge as bridge
import hermes_owner_context as owner
from test_career_workflow_bridge import prepared,opts,action_args,WEEK
from test_linkedin_state import history

@pytest.mark.parametrize('text',['publish','Publish it','post','please publish','wtf publish man skip the image'])
def test_simple_publish_is_natural_immediate_consent(text):
    parsed=interpret(text)
    assert parsed['approved'] and parsed['publish_now'] and not parsed['override']

@pytest.mark.parametrize('text',['do not publish','publish if the checks pass','Why publish?','write a post','publish both posts'])
def test_unconditional_scope_is_preserved(text):
    assert not interpret(text)['approved']


def test_publish_approval_and_text_only_execute_once(prepared,monkeypatch):
    root,jobs,db,add,posts=prepared;body=posts['thursday']['post_text']
    weekly=root/'review/2026-10-26/weekly.json';data=state.read(weekly)
    data['posts']['thursday']['image_required']=False;weekly.write_text(json.dumps(data))
    add(body,role='assistant');mid=add('publish')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2026,10,29,12,tzinfo=state.LONDON)
    monkeypatch.setattr(bridge,'datetime',Clock)
    calls=[]
    def publish(command,**kw):
        calls.append(command);ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(json.dumps({'result':'published','body_sha256':consent.digest(body)})+'\n')
        return NS(returncode=0,stdout=json.dumps({'performed':True,'post_urn':'urn:test:one'}))
    args=action_args(prepared,action='publish');args['approval_message_id']=mid
    contract={'workflow':'linkedin','action':'PUBLISH_NOW','latest_human_message':'publish','session_key':hashlib.sha256(b'owner').hexdigest(),'turn_origin':'human_text'}
    with owner.dispatch_context('',[],contract):
        result=bridge.linkedin(args,**opts(prepared),runner=publish)
        assert result['publish_performed'] and len(calls)==1
        assert bridge.linkedin(args,**opts(prepared),runner=publish)['phase']=='ALREADY_PUBLISHED'
    assert len(calls)==1 and not (root/'drafts/schedule.json').exists()


def test_image_block_is_not_a_schedule_circularity(prepared):
    root,jobs,db,add,posts=prepared;body=posts['thursday']['post_text'];add(body,role='assistant');mid=add('Approved')
    path=Path(state.capture(body,'2026-10-29',mid,root=root,db_path=db,replace=True)['artifact'])
    doc=state.read(path);doc.update(news_fact_gate=posts['thursday']['news_fact_gate'],personal_fact_gate=posts['thursday']['personal_fact_gate'],image_required=True)
    path.write_text(json.dumps(doc))
    result=state.inspect_artifact(path,**opts(prepared))
    assert result['reviews_ready'] and result['content_blockers']==['required_image_unavailable']
    with pytest.raises(ValueError,match='required_image_unavailable'):state.plan_slot(path,'2026-10-29',**opts(prepared))
    doc['image_required']=False;path.write_text(json.dumps(doc))
    assert state.inspect_artifact(path,**opts(prepared))['content_ready']
    assert not state.inspect_artifact(path,**opts(prepared))['slot_matches']


def test_scratch_script_filename_cannot_bypass_stage_guard():
    with owner.dispatch_context('',[],{'workflow':'linkedin','action':'APPROVAL'}):
        for command in ['python /tmp/write_gates2.py','python helper.py','cat > /tmp/fix.py <<EOF','powershell -c Set-Content artifact.json data']:
            assert bridge.guard('terminal',{'command':command})['action']=='block'
        assert bridge.guard('terminal',{'command':'cat career-ops/linkedin_state.py'}) is None


def test_completed_fact_decision_is_reused_and_new_evidence_rechecks(tmp_path,monkeypatch):
    import linkedin_factcheck as fc
    monkeypatch.setattr(fc,'__file__',str(tmp_path/'career-ops/linkedin_factcheck.py'))
    count=[]
    def judge(body,source,**kw):
        count.append(source)
        return {'used':True,'complete':True,'claims':[{'claim':'A factual claim.','verdict':'unsupported'}],
                'source_chars_fed':len(source),'section_coverage':[],'runs_used':3,'runs_requested':3}
    monkeypatch.setattr(fc,'llm_verify_claims',judge)
    url='https://synthetic.invalid/source'
    a=fc.verify_post('A factual claim.',[url],source_texts={url:'First evidence.'},api_key='test')
    assert a['verdict']=='block'
    b=fc.verify_post('A factual claim.',[url],source_texts={url:'First evidence.'},api_key='test')
    assert b['review_reused'] and len(count)==1 and b['verdict']=='block'
    fc.verify_post('A factual claim.',[url],source_texts={url:'New evidence.'},api_key='test')
    assert len(count)==2


def test_quoted_image_prompt_does_not_invalidate_the_public_post(history):
    db,add=history;body='The public post. #Security'
    add(body,role='assistant')
    add('Image generation is blocked by billing.\n\nThe prompt I would have used:\n> Visual medium: analogue photograph\n> A locked door.\n\nPublish the text-only post instead.',role='assistant')
    result=consent.verify_message(add('wtf publish man skip the image'),body,db_path=db)
    assert result['ok'] and result['receipt']['preferences']['skip_image']


@pytest.mark.parametrize('phrase',['Override fact check','skip fact check'])
def test_natural_override_needs_the_exact_post_and_warning(history,phrase):
    db,add=history;body='A public post.'
    add(body,role='assistant')
    assert not consent.verify_message(add(phrase),body,db_path=db,require_override=True)['ok']
    add('The fact-check blocked this post because a historical claim needs a source.',role='assistant')
    assert consent.verify_message(add(phrase),body,db_path=db,require_override=True)['ok']
