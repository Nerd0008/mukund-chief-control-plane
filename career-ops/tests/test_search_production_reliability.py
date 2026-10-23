"""Debugger reproductions of the 23 October production discovery failures."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
import regional_job_search as regional
import experience_screening as experience
import job_scan_delta as delta
import codex_entry_level_search as direct
import web_research as web
from posting_identity import identity_keys

UK = {"always_allow": ["UK", "United Kingdom"],
      "allow": ["UK", "United Kingdom", "England", "Scotland", "Wales"],
      "block": ["United States", "Canada", "India"]}


@pytest.mark.parametrize("location", ["London, hybrid", "Manchester", "Bristol"])
def test_confirmed_uk_country_metadata_rescues_city_only_locations(location):
    accepted, reason = regional.location_matches(UK, location, "Cyber Security Intern",
            "https://careers.example/jobs/10001", country_hint="GB")
    assert accepted, reason


def test_city_without_country_evidence_remains_ambiguous():
    accepted, reason = regional.location_matches(UK, "London, hybrid", "Cyber Security Intern",
            "https://careers.example/jobs/10001")
    assert not accepted
    assert "unresolved" in reason.lower()


def test_foreign_city_is_not_rescued_by_stale_uk_hint():
    assert not regional.location_matches(UK, "London, Ontario, Canada", "Cyber Security Intern",
            "https://careers.example/jobs/10001", country_hint="GB")[0]


@pytest.mark.parametrize("bio", [
    "We have a proven track record supporting businesses, not-for-profits and individuals.",
    "Our firm has extensive professional experience supporting clients.",
    "About us: Our team has a proven track record in security."])
def test_employer_biography_does_not_become_an_applicant_requirement(bio):
    assert experience.experience_hits(bio) == []


def test_employer_bio_does_not_hide_later_candidate_requirement():
    text = "We have a proven track record supporting businesses. You must have three years of professional experience."
    assert experience.experience_hits(text)


def test_numeric_candidate_requirement_still_rejects():
    assert experience.experience_hits("You must have three years of professional experience.")


def test_distinct_requisition_is_not_hidden_by_legacy_title_ledger():
    company, title = "Acme", "Security Engineer Intern"
    old = "https://job-boards.greenhouse.io/acme/jobs/1234567"
    fresh = "https://job-boards.greenhouse.io/acme/jobs/7654321"
    seen = {delta.ct_key(company, title): "old", delta.posting_key(old): "old"}
    assert not delta.already_seen(company, title, fresh, seen)


def test_reporter_collapses_same_requisition_across_official_hosts():
    company = "Acme"
    first = "https://careers.acme.com/job/12345678"
    second = "https://acme.fa.oraclecloud.com/jobs/job/12345678"
    seen = {key: "old" for key in delta.role_keys(company, "Security Intern", first)}
    assert delta.already_seen(company, "Renamed Security Internship", second, seen)


def test_six_requested_queries_execute_six_separate_observed_workers(monkeypatch):
    calls = []
    class Provider:
        def __init__(self, **kwargs): pass
        def resolve(self): return "fixture"
        def _run_one(self, exe, query, **kwargs):
            calls.append(query)
            return {"web_search_observed": True, "executed_queries": [query],
                    "results": [], "raw_events": 2, "error": None}
    monkeypatch.setattr(web, "CodexWebSearchProvider", Provider)
    queries = [f"cyber internship UK query{i}" for i in range(6)]
    prompt = 'Search these queries:\n' + '\n'.join(f'{i}. "{q}"' for i, q in enumerate(queries, 1))
    result = direct.run_codex(prompt, timeout=60)
    assert calls == queries
    assert result.evidence["queries_requested"] == 6
    assert result.evidence["queries_completed"] == 6
    assert result.evidence["coverage_complete"] is True


def test_partial_query_execution_cannot_be_healthy_empty(monkeypatch):
    calls = []
    class Provider:
        def __init__(self, **kwargs): pass
        def resolve(self): return "fixture"
        def _run_one(self, exe, query, **kwargs):
            calls.append(query)
            return {"web_search_observed": len(calls) == 1, "executed_queries": [query] if len(calls) == 1 else [],
                    "results": [], "raw_events": 2, "error": None if len(calls) == 1 else "timeout"}
    monkeypatch.setattr(web, "CodexWebSearchProvider", Provider)
    result = direct.run_codex('1. "cyber internship UK"\n2. "GRC internship UK"', timeout=60)
    assert result.evidence["coverage_complete"] is False
    assert result.evidence["queries_completed"] == 1


def test_only_current_writer_appends_are_reported_as_this_runs_roles():
    writer = {"applied": True, "counts": {"appended": 1}, "outcomes": [
        {"company": "New Employer", "title": "Cyber Intern", "url": "https://jobs.example/1", "decision": "appended"},
        {"company": "Known Employer", "title": "Cyber Intern", "url": "https://jobs.example/2", "decision": "duplicate"}]}
    output = 'TRACKER_WRITE_RESULT ' + json.dumps(writer)
    assert [r["company"] for r in delta.current_run_roles(output)] == ["New Employer"]
    assert delta.current_run_roles('No new roles; tracker unchanged.') == []


def test_outer_dry_run_reaches_the_actual_child(monkeypatch):
    captured = []
    def run(cmd, **kwargs):
        captured.append(cmd)
        class Result:
            returncode = 0
            stdout = ''
            stderr = ''
        return Result()
    monkeypatch.setattr(delta.subprocess, "run", run)
    delta.run_search(0, 60, dry_run=True)
    assert '--dry-run' in captured[0]


def batch_output(*, appended=False, complete=True):
    outcome = {"company": "Acme", "title": "Cyber Security Intern", "url": "https://jobs.example/jobs/12345678", "decision": "appended"}
    return ('SEARCH_COVERAGE ' + json.dumps({"coverage_complete": complete}) + '\n' +
            'SEARCH_RECONCILIATION ' + json.dumps({"canonical_outcomes": [outcome] if appended else []}) + '\n' +
            'TRACKER_WRITE_RESULT ' + json.dumps({"applied": appended, "counts": {"appended": int(appended)}, "outcomes": [outcome] if appended else []}) + '\n' +
            'SEARCH_PROPOSALS ' + json.dumps({'records': [dict(outcome, availability={'state':'OPEN'})] if appended else []}))


def test_duplicate_only_batch_advances_to_another_batch(monkeypatch):
    calls = []
    def search(offset, timeout, **kwargs):
        calls.append((offset, kwargs))
        return 0, batch_output(appended=offset == 1), ''
    monkeypatch.setattr(delta, 'run_search', search)
    code, out, err, coverage = delta.run_searches(0, 60, dry_run=True, max_batches=3, pool_size=3)
    assert code == 0
    assert [c[0] for c in calls] == [0, 1]
    assert all(c[1]['dry_run'] for c in calls)
    assert coverage['batches_attempted'] == 2
    assert len(delta.current_run_roles(out, dry_run=True)) == 1


def test_partial_batch_does_not_advance_successful_cursor(monkeypatch, tmp_path):
    cursor = tmp_path / 'cursor.json'
    monkeypatch.setattr(delta, 'CURSOR', cursor)
    def search(offset, timeout, **kwargs):
        return (0, batch_output(), '') if offset == 0 else (2, batch_output(complete=False), 'timeout')
    monkeypatch.setattr(delta, 'run_search', search)
    code, out, err, coverage = delta.run_searches(0, 60, max_batches=3, pool_size=3)
    assert code != 0
    assert coverage['next_offset'] == 1
    assert json.loads(cursor.read_text())['next_offset'] == 1


def test_budget_exhaustion_never_reports_complete_coverage():
    code, out, err, coverage = delta.run_searches(0, 60, dry_run=True, budget_seconds=0)
    assert code != 0 and coverage['coverage_complete'] is False
    assert coverage['market_exhausted'] is False


def test_nightly_requires_all_requested_query_receipts():
    from scheduled_orchestrator import live_mechanism_summary
    lane = {'queries_selected_total': 6, 'provider': {'provider': 'fixture', 'web_search_observed_queries': 2,
        'queries': [{'executed': True, 'web_search_observed': True, 'error': None}] * 2}}
    summary = live_mechanism_summary(lane)
    assert summary['operational'] is True
    assert summary['coverage_complete'] is False
    assert summary['queries_requested'] == 6 and summary['queries_completed'] == 2


def test_country_metadata_survives_jsonld_extraction():
    import application_links as links
    job = {'@type': 'JobPosting', 'title': 'Cyber Security Intern', 'hiringOrganization': {'name': 'Acme'},
           'jobLocation': {'address': {'addressLocality': 'London', 'addressCountry': 'GB'}}}
    html = '<h1>Cyber Security Intern</h1><script type="application/ld+json">' + json.dumps(job) + '</script>'
    identity = links.page_identity(html, 'https://careers.example/jobs/12345678')
    assert identity['country'] == 'GB'
    assert regional.location_matches(UK, identity['location'], identity['title'], 'https://careers.example/jobs/12345678', country_hint=identity['country'])[0]


@pytest.mark.parametrize('text', [
    'We are looking for someone with three years of professional experience.',
    'Our team is hiring candidates with prior professional experience.',
    'We have a role requiring three years of professional experience.'])
def test_hiring_language_is_not_confused_with_company_biography(text):
    assert experience.experience_hits(text)


def test_direct_and_shared_worker_agree_for_same_grad_vacancy():
    from pipeline import deterministic_gates
    policy = regional.load_policy()
    rec = {'company': 'Acme', 'title': 'Graduate SOC Analyst', 'location': 'London, United Kingdom',
           'url': 'https://careers.example/jobs/12345678', 'jd_text': 'No prior experience required.'}
    regional_result = regional.evaluate_record('uk', rec, policy, {'positive': ['Intern']}, UK)
    unified_result = deterministic_gates('uk', rec, policy, UK)
    assert regional_result['decision'] == unified_result['decision'] == 'accepted'
    rec['jd_text'] = 'You must have three years of professional experience.'
    assert regional.evaluate_record('uk', rec, policy, {'positive': ['Intern']}, UK)['decision'] == 'rejected'
    assert deterministic_gates('uk', rec, policy, UK)['decision'] == 'rejected'


def test_country_hint_alone_cannot_admit_foreign_vacancy():
    assert not regional.location_matches(UK, '', 'Cyber Security Intern', '', country_hint='India')[0]


def test_complete_empty_query_is_not_a_dead_search_warning():
    assert delta.search_failed('batch 0: 0 results returned\nSEARCH_COVERAGE {"coverage_complete": true}') == ''



@pytest.mark.parametrize('publisher', ['MyInternshipAbroad', 'My Internship Abroad'])
def test_live_publisher_is_not_treated_as_the_actual_employer(publisher):
    from application_links import identity_review_reason
    assert 'review-only' in identity_review_reason(publisher, 'Information Security Internship')


def test_current_student_requirement_cannot_be_called_eligible_without_confirmation():
    from pipeline import deterministic_gates
    rec = {'company': 'Acme', 'title': 'Cyber Security Intern', 'location': 'London, UK',
           'url': 'https://careers.example/jobs/12345678',
           'jd_text': 'Applicants must be in the penultimate year of an undergraduate degree.'}
    result = deterministic_gates('uk', rec, regional.load_policy(), UK)
    assert result['decision'] != 'accepted'
    assert any('student' in why.lower() for why in result['reasons'])


def test_technical_project_exposure_is_not_automatically_professional_history():
    assert experience.experience_hits('Proven experience using Python or AI tooling in personal projects.') == []



def test_collection_overlay_uses_shared_scope_without_changing_owner_filters():
    from effective_search_policy import discovery_portals
    original = {'title_filter': {'positive': ['Intern'], 'negative': ['Senior']},
                'location_filter': {'allow': ['UK'], 'block': ['Canada']}}
    overlay = discovery_portals(original, 'uk')
    assert 'graduate' in overlay['title_filter']['positive']
    assert overlay['title_filter']['negative'] == ['Senior']
    assert overlay['location_filter']['allow'] == []
    assert overlay['location_filter']['block'] == ['Canada']
    assert original['title_filter']['positive'] == ['Intern']


def test_summer_vacation_scheme_reaches_evidence_screening():
    from effective_search_policy import role_decision
    assert role_decision('uk', 'Risk & Controls Consulting - Cyber Summer Vacation Scheme 2027')[0]


def test_confirmed_current_student_is_not_rejected_as_unconfirmed(monkeypatch):
    import student_eligibility as student
    monkeypatch.setattr(student, 'current_student_confirmed', lambda: True)
    assert not student.student_requirement('Applicants must be in the penultimate year of university.')


def test_explicit_graduate_alternative_is_preserved(monkeypatch):
    import student_eligibility as student
    monkeypatch.setattr(student, 'current_student_confirmed', lambda: False)
    assert not student.student_requirement('Applicants must be currently studying or recent graduates.')



def test_missing_country_and_location_are_not_positive_uk_evidence():
    accepted, reason = regional.location_matches(UK, '', 'Cyber Security Intern', 'https://careers.example/vacancy')
    assert not accepted and 'unresolved' in reason.lower()


def test_unverified_new_lead_does_not_stop_bounded_discovery(monkeypatch):
    calls = []
    def search(offset, timeout, **kwargs):
        calls.append(offset)
        text = batch_output(appended=True).replace('"state": "OPEN"', '"state": "UNKNOWN"')
        return 0, text, ''
    monkeypatch.setattr(delta, 'run_search', search)
    delta.run_searches(0, 60, dry_run=True, max_batches=3, pool_size=3)
    assert calls == [0, 1, 2]


def test_source_overlay_cleanup_and_owner_file_preservation(monkeypatch, tmp_path):
    import effective_search_policy as policy
    import yaml
    original = tmp_path/'install/portals.yml'
    original.parent.mkdir()
    original.write_text('title_filter:\n  positive: [Intern]\nlocation_filter:\n  allow: [UK]\n  block: [Canada]\n')
    original_bytes = original.read_bytes()
    effective = policy.effective_policy('uk')
    monkeypatch.setattr(policy, 'effective_policy', lambda region: effective)
    monkeypatch.setattr(policy, 'HERE', tmp_path/'control/career-ops')
    with policy.discovery_environment('uk', {'CAREER_OPS_PORTALS': 'portals.yml'}, original.parent) as env:
        generated = Path(env['CAREER_OPS_PORTALS'])
        assert generated.exists()
        config = yaml.safe_load(generated.read_text())
        assert 'graduate' in config['title_filter']['positive']
    assert not generated.exists() and original.read_bytes() == original_bytes



def test_scheme_length_is_not_required_employment_tenure():
    text = 'Start date - September 2027. Scheme length - 3 years. Our graduate career pathways build professional skills.'
    assert experience.experience_hits(text) == []


def test_scheme_duration_does_not_hide_candidate_years_in_next_clause():
    text = 'Scheme length - 3 years. You must have three years of professional experience.'
    assert experience.experience_hits(text)


def test_private_evidence_retains_full_input_without_credentials(tmp_path, monkeypatch):
    import verification_evidence as evidence
    import hashlib
    monkeypatch.setattr(evidence, 'ROOT', tmp_path)
    text = 'Public source. ' * 2000 + 'Important late passage.'
    path = evidence.save_evidence({'company':'Acme','title':'Cyber Intern','url':'https://careers.example/jobs/12345678'},
                                  {'text':text,'api_key':'DO-NOT-STORE','status':200})
    saved = json.loads(Path(path).read_text())
    assert saved['text'] == text
    assert saved['text_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert 'DO-NOT-STORE' not in Path(path).read_text()



def test_non_uk_query_scope_remains_inherited():
    from career_search_recall import query_batches
    queries = [query for group in query_batches({}, 'Dubai', [], 2026) for query in group]
    assert any('apprentice' in query for query in queries)


def test_parent_timeout_grace_fits_inside_total_scan_budget(monkeypatch):
    elapsed = [0.0]
    monkeypatch.setattr(delta.time, 'monotonic', lambda: elapsed[0])
    def search(offset, timeout, **kwargs):
        elapsed[0] += timeout + 300  # the child's documented hard timeout
        return 0, batch_output(), ''
    monkeypatch.setattr(delta, 'run_search', search)
    code, out, err, summary = delta.run_searches(0, 600, dry_run=True, max_batches=3, budget_seconds=1200, pool_size=3)
    assert elapsed[0] <= 1200
    assert summary['market_exhausted'] is False


def test_live_partial_search_cannot_write_or_advance_cursor(tmp_path, monkeypatch):
    import openpyxl, sys, tracker_writer
    path = tmp_path / 'tracker.xlsx'
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Jobs'
    ws.append(['UK jobs'])
    ws.append(['Date Found','Company','Role Title','Apply Link','Application Deadline','Status'])
    wb.save(path); wb.close()
    monkeypatch.setitem(direct.TRACKERS, 'uk', path)
    monkeypatch.setattr(direct, 'SEARCH_STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr(direct.osp, 'load_profile', lambda: {})
    monkeypatch.setattr(direct, '_profile_terms', lambda: (direct.ENTRY_MARKERS, (), None))
    rows = [{'company':'Acme','job_title':'Cyber Intern','location':'London, UK','url':'https://employer.com/partial'}]
    monkeypatch.setattr(direct, 'run_codex', lambda *a, **k: direct.SearchResponse(json.dumps(rows), {'coverage_complete':False}))
    monkeypatch.setattr(direct, 'fetch_jd', lambda url: {'text':'Cyber security internship. No prior experience required.', 'vacancy_status':{'state':'OPEN','evidence':'active vacancy fixture'}})
    real_write = tracker_writer.write_records
    applied = []
    def writer(*args, **kwargs):
        if kwargs.get('apply'):
            applied.append(True)
        return real_write(*args, **kwargs)
    monkeypatch.setattr(tracker_writer, 'write_records', writer)
    monkeypatch.setattr(sys, 'argv', ['search', '--batches', '1'])
    before = path.read_bytes()
    assert direct.main() != 0
    assert not applied
    assert path.read_bytes() == before
    assert not direct.cursor_file('uk', path).exists()
