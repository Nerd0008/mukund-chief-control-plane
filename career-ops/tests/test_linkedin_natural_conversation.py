import pytest
import linkedin_approval as approval
from test_linkedin_state import history, BODY


@pytest.mark.parametrize('reply', [
    'Approved', 'Yes', 'Okay', 'Go ahead', 'Looks good', 'Looks great', 'Can you publish it?', '[Replying to: "The post above"]\n\nApproved',
    'Please publish it tomorrow at 8 am, not today. Skip the image.',
    'Publish it tomorrow at 8 am not today Thursday',
    'I approve this version. Please schedule it tomorrow morning without an image. '+('I like how clearly it explains the point. '*8),
])
def test_natural_approval_survives_hash_only_instructions(history, reply):
    db, add = history
    presented = add(BODY+'\nAPPROVE LINKEDIN '+approval.digest(BODY), role='assistant')
    add('The approval system needs one exact short message from you.\n\nSend exactly one of these:\n- approved\n- APPROVE LINKEDIN '+approval.digest(BODY)+'\n\nOnce you send it, I will schedule the post.', role='assistant')
    result = approval.verify_message(add(reply), BODY, db_path=db)
    assert result['ok'], result
    assert result['receipt']['presented_message_id'] == presented


@pytest.mark.parametrize('reply', ['Not approved','Do not publish it','Approved if the checks pass','Approve both posts','It says approved','Why does it say approved?','Approved, but rewrite the ending first.'])
def test_negated_conditional_and_edited_consent_stays_blocked(history, reply):
    db, add = history
    add(BODY, role='assistant')
    assert not approval.verify_message(add(reply), BODY, db_path=db)['ok']


def test_schedule_and_image_preferences_are_derived_from_owner_message(history):
    db, add = history
    add(BODY, role='assistant')
    result = approval.verify_message(add('Please publish it tomorrow at 8 am, not today. Skip the image.'), BODY, db_path=db)
    assert result['ok'], result
    preferences = result['receipt']['preferences']
    assert preferences['skip_image'] is True
    assert preferences['publish_at'].endswith('T08:00:00+01:00')
    assert preferences['publish_now'] is False


def test_natural_override_requires_explicit_acknowledgement(history):
    db, add = history
    add(BODY, role='assistant')
    assert not approval.verify_message(add('Approved'), BODY, db_path=db, require_override=True)['ok']
    result = approval.verify_message(add('I understand the fact-check warning. I approve this exact post despite the warning.'), BODY, db_path=db, require_override=True)
    assert result['ok'], result


def test_revised_post_still_invalidates_older_body(history):
    db, add = history
    add(BODY, role='assistant')
    add('Updated post:\n> This is a different public post.\n> #Synthetic', role='assistant')
    assert not approval.verify_message(add('Approved'), BODY, db_path=db)['ok']


from test_career_workflow_bridge import prepared, opts, action_args
import career_workflow_bridge as bridge
import linkedin_state as state
import json, sqlite3
from datetime import datetime


def test_short_approval_can_skip_image_without_calling_generator(prepared):
    root,jobs,db,add,posts=prepared
    body=posts['thursday']['post_text']
    add(body,role='assistant')
    args=action_args(prepared);args['approval_message_id']=add('Approved, skip the image.')
    def forbidden(body):raise AssertionError('no image requested')
    result=bridge.linkedin(args,**opts(prepared),generator=forbidden)
    path=root/'drafts/approved_20261029_thursday/linkedin_drafts.json'
    assert result['image']['phase']=='IMAGE_SKIPPED'
    assert state.read(path)['image_required'] is False
    assert state.inspect_artifact(path,**opts(prepared))['owner_approved']
    assert not result['publish_performed']


def test_review_failure_preserves_natural_approval_without_arming(prepared):
    root,jobs,db,add,posts=prepared
    path=root/'drafts/approved_20261029_thursday/linkedin_drafts.json'
    source=dict(posts['thursday']);source['personal_fact_gate']={'verdict':'block'}
    path.write_text(json.dumps(source))
    body=source['post_text'];add(body,role='assistant')
    args=action_args(prepared);args['approval_message_id']=add('Approved, skip the image.')
    result=bridge.linkedin(args,**opts(prepared))
    assert result['phase']=='APPROVED_BUT_BLOCKED'
    status=state.inspect_artifact(path,**opts(prepared))
    assert status['owner_approved'] and not status['automatic_publish_armed']
    assert not (root/'drafts/schedule.json').exists()


def test_date_only_followup_preserves_approval_and_skipped_image(prepared):
    root,jobs,db,add,posts=prepared
    body=posts['thursday']['post_text'];add(body,role='assistant')
    args=action_args(prepared);args['approval_message_id']=add('Approved, skip the image.')
    bridge.linkedin(args,**opts(prepared))
    old_receipt=state.read(root/'drafts/approved_20261029_thursday/linkedin_drafts.json')['owner_approval']
    args['approval_message_id']=mid=add('Tomorrow at 9 am, please.')
    with sqlite3.connect(db) as c:c.execute('UPDATE messages SET timestamp=? WHERE id=?',(datetime(2026,10,28,12,tzinfo=state.LONDON).timestamp(),mid))
    result=bridge.linkedin(args,**opts(prepared),generator=lambda body:pytest.fail('skipped image must stay skipped'),now=datetime(2026,10,28,12,tzinfo=state.LONDON))
    assert result['plan']['slot']['publish_at']=='2026-10-29T09:00:00+00:00'
    doc=state.read(root/'drafts/approved_20261029_thursday/linkedin_drafts.json')
    assert doc['owner_approval']['hermes_message_id']==old_receipt['hermes_message_id']
    assert doc['image_required'] is False


def test_multiple_visible_posts_need_a_natural_day_reference(history):
    db,add=history
    add('Wednesday 2026-10-28 — ready\n\n'+BODY+'\n\nThursday 2026-10-29 — ready\n\nA different post.',role='assistant')
    assert not approval.verify_message(add('Approved'),BODY,db_path=db)['ok']
    assert approval.verify_message(add('Approve the Wednesday post.'),BODY,db_path=db)['ok']
    assert not approval.verify_message(add('Approve the Thursday post.'),BODY,db_path=db)['ok']


def test_report_metrics_are_not_candidate_achievements():
    import linkedin_personal_review as personal
    body='Both numbers come from an independent annual index of AI progress. In controlled simulation, robotic manipulation succeeds 89.4% of the time. On real household tasks, it succeeds 12%.'
    assert personal.personal_text(body)==''
    mixed=body+'\n\nI achieved 89.4% in my own project.'
    assert personal.personal_text(mixed)==mixed


@pytest.mark.parametrize('message', ['Approved','Okay','Please publish it tomorrow at 8 am, not today.','Skip the image.','Tomorrow at 9 am, please.'])
def test_natural_phrases_reach_the_bounded_workflow(message):
    assert bridge.intent(message,'linkedin')=='APPROVAL'



def test_short_publish_anyway_requires_a_real_warning_context(history):
    db,add=history
    add(BODY,role='assistant')
    assert not approval.verify_message(add('Publish it anyway'),BODY,db_path=db,require_override=True)['ok']
    add('The fact-check blocked this exact post because a factual claim is unsupported.',role='assistant')
    assert approval.verify_message(add('Publish it anyway'),BODY,db_path=db,require_override=True)['ok']


def test_rescheduling_never_silently_replaces_another_post(prepared):
    root,jobs,db,add,posts=prepared
    body=posts['wednesday']['post_text'];add(body,role='assistant')
    args=action_args(prepared);args.update(day='wednesday',body_sha256=approval.digest(body),approval_message_id=add('Approve the Wednesday post for Thursday at 8 am, skip the image.'))
    competing=root/'drafts/approved_20261029_thursday/linkedin_drafts.json'
    before=competing.read_bytes()
    result=bridge.linkedin(args,**opts(prepared))
    assert result['phase']=='SCHEDULE_CONFLICT'
    assert competing.read_bytes()==before
    assert not (root/'drafts/schedule.json').exists()



def test_named_post_can_be_approved_from_legacy_multiple_hash_presentations(history):
    db,add=history
    other='A different public post.'
    add('Wednesday 2026-10-28 — ready\n\n'+BODY+'\nAPPROVE LINKEDIN '+approval.digest(BODY)+'\n\nThursday 2026-10-29 — ready\n\n'+other+'\nAPPROVE LINKEDIN '+approval.digest(other),role='assistant')
    assert not approval.verify_message(add('Approved'),BODY,db_path=db)['ok']
    assert approval.verify_message(add('Approve the Wednesday post.'),BODY,db_path=db)['ok']


def test_override_receipt_survives_plain_reapproval_and_cannot_be_forged(prepared):
    root,jobs,db,add,posts=prepared
    body=posts['thursday']['post_text'];add(body,role='assistant')
    add('The fact-check blocked this exact post because a claim is unsupported.',role='assistant')
    override=approval.verify_message(add('Publish it anyway, skip the image.'),body,db_path=db,require_override=True)
    assert override['ok']
    plain=approval.verify_message(add('Approved for Thursday at 8 am, skip the image.'),body,db_path=db)
    doc={'post_text':body,'owner_approval':plain['receipt'],'news_fact_gate':{'verdict':'block'},
         'personal_fact_gate':posts['thursday']['personal_fact_gate'],
         'owner_override':{'body_sha256':approval.digest(body),'reason':'Explicit owner decision','receipt':override['receipt']}}
    assert state.review_state(doc,body,db_path=db)['reviews_ready']
    doc['owner_override']['receipt']=plain['receipt']
    assert not state.review_state(doc,body,db_path=db)['reviews_ready']
    doc['owner_override']['receipt']=override['receipt']
    doc['owner_override']['body_sha256']=approval.digest(body+'changed')
    assert not state.review_state(doc,body,db_path=db)['reviews_ready']


def test_blocked_post_natural_override_then_schedule_and_execute(prepared,monkeypatch):
    from types import SimpleNamespace
    import linkedin_scheduled as scheduled
    import linkedin_publish as publisher
    root,jobs,db,add,posts=prepared
    body=posts['thursday']['post_text']
    source=root/'review/2026-10-26/weekly.json'
    weekly=state.read(source)
    weekly['posts']['thursday']['news_fact_gate']={'verdict':'block','body_sha256':approval.digest(body)}
    source.write_text(json.dumps(weekly))
    (root/'drafts/approved_20261029_thursday/linkedin_drafts.json').write_text(json.dumps(weekly['posts']['thursday']))
    add(body,role='assistant')
    add('The fact-check blocked this exact post because a claim is unsupported.',role='assistant')
    args=action_args(prepared)
    args['approval_message_id']=add('I understand the fact-check warning. I approve this post despite the warning. Skip the image.')
    result=bridge.linkedin(args,**opts(prepared),now=datetime(2026,10,27,12,tzinfo=state.LONDON))
    assert result['plan']['planned']
    path=root/'drafts/approved_20261029_thursday/linkedin_drafts.json'
    original=state.read(path)['owner_override']['receipt']
    args['approval_message_id']=add('Approved for Thursday at 8 am, skip the image.')
    bridge.linkedin(args,**opts(prepared),now=datetime(2026,10,27,12,tzinfo=state.LONDON))
    doc=state.read(path)
    assert doc['owner_override']['receipt']==original
    monkeypatch.setattr(publisher,'APPROVAL_DB',db)
    assert publisher._override_ok(doc,body)[0]
    calls=[]
    def endpoint(command,**kwargs):
        calls.append(command)
        ledger=root/'published/posts.jsonl';ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(json.dumps({'body_sha256':approval.digest(body),'result':'published','post_urn':'urn:test:isolated'})+'\n')
        return SimpleNamespace(returncode=0,stdout=json.dumps({'performed':True,'post_urn':'urn:test:isolated','network_calls_spent':1}))
    when=datetime(2026,10,29,8,tzinfo=state.LONDON)
    code,result=scheduled.run_day('thursday',root=root,db_path=db,jobs_path=jobs,now=when,dry_run=False,runner=endpoint)
    assert code==0 and result['publish_performed'] and len(calls)==1
    code,repeated=scheduled.run_day('thursday',root=root,db_path=db,jobs_path=jobs,now=when,dry_run=False,runner=endpoint)
    assert code==0 and not repeated['publish_performed'] and len(calls)==1
