"""Owner's 25 October scope must agree in both production evidence gates."""
import pytest
import regional_job_search as regional
from pipeline import deterministic_gates


@pytest.fixture
def legacy_scope(monkeypatch):
    """Historical strict policy remains testable; current rule has its own matrix."""
    import copy
    import effective_search_policy as policy
    original = policy.effective_policy
    def configured(region='uk', **kwargs):
        result = copy.deepcopy(original(region, **kwargs))
        if region == 'uk' and not kwargs.get('path'):
            result['rejection_policy'] = {}
            result.setdefault('owner_scope', {}).setdefault('junior_it', {})['require_jd_evidence'] = True
        return result
    monkeypatch.setattr(policy, 'effective_policy', configured)

SCOPE = {'always_allow':['UK','United Kingdom'], 'allow':['UK','United Kingdom'], 'block':['Canada','India']}


@pytest.mark.parametrize('worker', ['regional', 'unified'])
@pytest.mark.parametrize('title,jd,accepted', [
    ('Cyber Security Internship', 'Cyber security projects.', True),
    ('Graduate SOC Analyst', 'Security monitoring and incident triage.', True),
    ('Junior IT Support Analyst', 'No previous work experience is required.', True),
    ('Junior SOC Analyst', 'Previous experience is not required. Training is provided.', True),
    ('Junior IT Support Analyst', 'Internship experience is accepted for this role.', True),
    ('Junior SOC Analyst', 'This role is suitable for recent graduates.', True),
    ('Junior SOC Analyst', 'Graduate-level experience is sufficient for this role.', True),
    ('IT Support Analyst', '0-1 years of work experience. Training is provided.', True),
    ('Junior IT Support Analyst', 'You will support our Windows users.', False),
    ('Junior SOC Analyst', '', False),
    ('Junior IT Support Analyst', 'Our company runs internships. Relevant experience required.', False),
    ('Junior SOC Analyst', 'Internship experience is not accepted.', False),
    ('Junior SOC Analyst', 'This role is not suitable for recent graduates.', False),
    ('Junior SOC Analyst', 'Internships do not count as relevant experience.', False),
    ('Junior SOC Analyst', 'You must have three years of professional experience. Internship experience is accepted.', False),
    ('Graduate SOC Analyst', 'You must have three years of professional experience.', False),
    ('Cyber Security Apprentice', 'No prior experience required.', False),
])
def test_confirmed_owner_scope(worker, title, jd, accepted, legacy_scope):
    rec = {'company':'Acme','title':title,'location':'London, UK',
           'url':'https://careers.example/jobs/12345678','jd_text':jd}
    if worker == 'unified':
        result = deterministic_gates('uk', rec, regional.load_policy(), SCOPE)
    else:
        result = regional.evaluate_record('uk', rec, regional.load_policy(), {'positive':['Intern']}, SCOPE)
    assert (result['decision'] == 'accepted') is accepted, result
    if not accepted and title in ('Junior SOC Analyst','Junior IT Support Analyst') and 'three years' not in jd:
        assert any('review-only' in reason for reason in result['reasons'])


def test_scope_reads_canonical_owner_policy_and_tracks_its_hash(tmp_path):
    import json
    from effective_search_policy import effective_policy
    owner = tmp_path / 'owner-policy.yaml'
    owner.write_text('role_scope:\n  junior_it:\n    require_jd_evidence: true\n', encoding='utf-8')
    config = tmp_path / 'search-policy.json'
    config.write_text(json.dumps({'schema_version':1,'regions':{'uk':{'mode':'high_recall','owner_policy_path':str(owner)}}}), encoding='utf-8')
    before = effective_policy('uk', path=config)
    assert before['owner_scope']['junior_it']['require_jd_evidence'] is True
    assert before['legacy_policy_conflicts'] == []
    owner.write_text('role_scope:\n  junior_it:\n    require_jd_evidence: false\n', encoding='utf-8')
    after = effective_policy('uk', path=config)
    assert after['owner_scope']['junior_it']['require_jd_evidence'] is False
    assert after['owner_policy_sha256'] != before['owner_policy_sha256']


def test_confirmed_uk_scope_does_not_change_other_regions():
    from effective_search_policy import scope_evidence_decision
    assert scope_evidence_decision('dubai', 'Junior IT Analyst', '')[0]
