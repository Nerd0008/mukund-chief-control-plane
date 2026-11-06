import json
from types import SimpleNamespace as NS
import pytest
import application_question_recovery as recovery

STALE='Application: OWNER_INPUT_REQUIRED.\nCV: incomplete — need role.\nCover letter: incomplete — need role.'
QUESTION='Tell us what inspired your application to join PA Consulting. In your response explain your motivation. (Max 200-250 words) answer this question'

def test_status_detection_is_scoped():
    assert recovery.stale_status(STALE)
    assert not recovery.stale_status('My CV is incomplete, so I will finish it later.')
    assert not recovery.stale_status('I am drawn to PA Consulting because of its interdisciplinary work.')

def test_only_matching_employer_jd_is_included():
    assert recovery.matching_job(QUESTION,{'intake':{'jd':'PA Consulting: a graduate security role'}})
    assert not recovery.matching_job(QUESTION,{'intake':{'jd':'Other Employer: a graduate role'}})

def test_clean_recovery_uses_full_profile_and_no_stale_history(monkeypatch):
    import hermes_owner_context as owner,hermes_cv_compiler_guard as guard,workflow_routing
    monkeypatch.setattr(owner,'retrieve',lambda *a,**k:('SYNTHETIC VERIFIED PROFILE',[{'complete':True} for _ in owner.FILES]))
    monkeypatch.setattr(guard,'master_tool',lambda *a:json.dumps({'verified_facts':[{'text':'fictional facts'}]}))
    observed=[]
    def route(messages,**kw):
        observed.append((messages,kw))
        return NS(choices=[NS(finish_reason='stop',message=NS(content='A truthful and relevant example answer.'))]),{'fixture':True}
    monkeypatch.setattr(workflow_routing,'complete_text',route)
    answer=recovery.recover(QUESTION,{'intake':{'jd':'PA Consulting: a graduate role'}})
    assert answer=='A truthful and relevant example answer.'
    assert len(observed)==1 and len(observed[0][0])==2
    assert STALE not in json.dumps(observed) and 'SYNTHETIC VERIFIED PROFILE' in json.dumps(observed)

def test_rejects_stale_or_truncated_retry(monkeypatch):
    import hermes_owner_context as owner,hermes_cv_compiler_guard as guard,workflow_routing
    monkeypatch.setattr(owner,'retrieve',lambda *a,**k:('fixture',[{'complete':True} for _ in owner.FILES]))
    monkeypatch.setattr(guard,'master_tool',lambda *a:json.dumps({'verified_facts':[]}))
    monkeypatch.setattr(workflow_routing,'complete_text',lambda *a,**k:(NS(choices=[NS(finish_reason='stop',message=NS(content=STALE))]),{}))
    with pytest.raises(RuntimeError,match='question_answer_invalid'):recovery.recover(QUESTION,{})
