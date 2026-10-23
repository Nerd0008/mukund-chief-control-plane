"""Conservative personal-claim scope; no network or account access."""
import hashlib
import pytest
import linkedin_personal_review as scope

@pytest.mark.parametrize('body',[
    'I supported 500 million active users.',
    'Supported 500 million users. A vendor reports 500 million users.',
    'Built SafePaste. SafePaste reports 500 million users.',
    'We learned from a breach. A vendor reports 500 million users.',
    'According to a report, I supported 500 million users.',
    'Mukund supported 500 million active users.',
    'My project processes 500 million users.',
])
def test_personal_or_mixed_content_is_never_projected_away(body):
    assert scope.personal_text(body)==body


def test_only_clearly_attributed_nonpersonal_clauses_are_excluded():
    assert scope.personal_text('A vendor reports 500 million active users.')==''
    ambiguous='The system serves 500 million users.'
    assert scope.personal_text(ambiguous)==ambiguous


def test_scope_receipt_is_bound_to_both_body_and_reviewed_text(tmp_path,monkeypatch):
    import cv_workflow
    checked=[]
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda cfg,text,**kw:checked.append(text) or {'available':True,'verdict':'pass','exit_code':0})
    body='A vendor reports 500 million active users.'
    gate=scope.review({},body,label='fixture',scratch=tmp_path)
    assert checked==['']
    assert gate['body_sha256']==hashlib.sha256(body.encode()).hexdigest()
    assert scope.scope_matches(gate,body)
    assert not scope.scope_matches(gate,'I supported 500 million active users.')
    gate['scope_version']=999
    assert not scope.scope_matches(gate,body)


def test_actual_local_cv_verifier_distinguishes_attributed_news_from_personal_claim(tmp_path):
    import cv_workflow,linkedin_workflow
    cfg=linkedin_workflow.cv_config(linkedin_workflow.load_config())
    first=scope.review(cfg,'A vendor reports 500 million active users.',label='news',scratch=tmp_path)
    if not first.get('available'):pytest.skip('local verifier install unavailable')
    second=scope.review(cfg,'I supported 500 million active users.',label='personal',scratch=tmp_path)
    assert first['verdict']=='pass'
    assert second['verdict']=='block' and second['exit_code']!=0