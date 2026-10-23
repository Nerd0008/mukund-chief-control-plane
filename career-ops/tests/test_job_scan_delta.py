"""Tests for job_scan_delta - the every-2-hours "only what is new" job scan.

The failure this suite exists to prevent: the ledger wrapper being read as if it
were the seen-mapping, which made EVERY role in the tracker look new and posted
the owner's whole 74-role list on every cycle.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
MOD_PATH = HERE.parent / 'job_scan_delta.py'

_spec = importlib.util.spec_from_file_location('jsd', MOD_PATH)
jsd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jsd)


def test_load_ledger_returns_the_seen_mapping_not_the_wrapper(tmp_path):
    """The regression: reading the wrapper makes every role look new."""
    p = tmp_path / 'scan-seen.json'
    p.write_text(json.dumps({'updated_at': 'x', 'count': 2,
                             'seen': {'https://a/1': 't', 'https://b/2': 't'}}),
                 encoding='utf-8')
    seen = jsd.load_ledger(p)
    assert set(seen) == {'https://a/1', 'https://b/2'}
    assert 'seen' not in seen and 'count' not in seen


def test_load_ledger_missing_file_is_empty(tmp_path):
    assert jsd.load_ledger(tmp_path / 'nope.json') == {}


def test_load_ledger_survives_corrupt_json(tmp_path):
    p = tmp_path / 'scan-seen.json'
    p.write_text('{not json', encoding='utf-8')
    assert jsd.load_ledger(p) == {}


def test_save_then_load_round_trips(tmp_path):
    p = tmp_path / 'scan-seen.json'
    jsd.save_ledger(p, {'https://a/1': '2026-01-01T00:00:00+00:00'})
    assert set(jsd.load_ledger(p)) == {'https://a/1'}
    payload = json.loads(p.read_text(encoding='utf-8'))
    assert payload['count'] == 1


def test_save_ledger_leaves_no_temp_file(tmp_path):
    p = tmp_path / 'scan-seen.json'
    jsd.save_ledger(p, {'https://a/1': 't'})
    assert not list(tmp_path.glob('*.tmp'))


def test_posting_key_ignores_tracking_params():
    """Two URLs for the same posting must collapse to one ledger key."""
    a = jsd.posting_key('https://x.example/job/1?utm_source=news&gh_src=Simplify')
    b = jsd.posting_key('https://x.example/job/1')
    assert a == b and a != ''


def test_search_found_reads_canonical_append_outcomes():
    stdout = 'SEARCH_RECONCILIATION ' + json.dumps({"canonical_outcomes": [
        {"company": "Acme", "title": "SOC Analyst", "url": "https://a/1", "decision": "appended"},
        {"company": "Known", "title": "SOC Analyst", "url": "https://b/2", "decision": "duplicate"}]})
    assert [f['url'] for f in jsd.search_found(stdout)] == ['https://a/1']


def test_search_found_without_the_tag_is_empty():
    assert jsd.search_found('nothing machine readable here') == []


def test_write_ok_detects_a_blocked_write():
    ok, why = jsd.write_ok('', 'TRACKER_WRITE_BLOCKED PermissionError', 2)
    assert ok is False and 'locked' in why


def test_write_ok_detects_an_unconfirmed_append():
    stdout = 'TRACKER_WRITE_RESULT {"applied": false, "error": "integrity failed"}\n'
    ok, why = jsd.write_ok(stdout, '', 2)
    assert ok is False and 'integrity failed' in why


def test_write_ok_accepts_a_confirmed_append():
    stdout = 'TRACKER_WRITE_RESULT {"applied": true, "counts": {"appended": 2}}\n'
    assert jsd.write_ok(stdout, '', 0)[0] is True


def test_write_ok_treats_no_candidates_as_a_clean_no_op():
    """A run that found nothing writes no result line - that is not a failure."""
    assert jsd.write_ok('No new roles; tracker unchanged.', '', 0)[0] is True


def test_write_ok_treats_a_duplicate_no_op_as_success():
    """The regression: `applied: false` on a no-op is NOT a failed write.

    It made a healthy cycle print "close Excel and re-run the scan" when nothing
    had been blocked, and reported a role as unsaved when the writer had simply
    recognised it as a duplicate.
    """
    stdout = ('TRACKER_WRITE_RESULT {"applied": false, "result": "no-op", '
              '"error": null, "problems": 0, "counts": {"input": 1, "appended": 0, '
              '"duplicates": 1}}\n')
    assert jsd.write_ok(stdout, '', 0) == (True, '')


def test_write_ok_still_flags_rows_that_needed_appending_but_did_not_land():
    stdout = ('TRACKER_WRITE_RESULT {"applied": false, "result": "partial", '
              '"error": null, "problems": 0, "counts": {"appended": 2}}\n')
    ok, why = jsd.write_ok(stdout, '', 0)
    assert ok is False and 'did not confirm' in why


def test_write_ok_flags_workbook_problems():
    stdout = ('TRACKER_WRITE_RESULT {"applied": true, "error": null, '
              '"problems": 3, "counts": {"appended": 1}}\n')
    ok, why = jsd.write_ok(stdout, '', 0)
    assert ok is False and 'problem' in why


def test_ct_key_matches_across_ats_and_aggregator_urls():
    """The G-Research case: same role, aggregator URL in the tracker, ATS URL found."""
    k = jsd.ct_key('G-Research', 'Security Operations Placement Year')
    assert k == 'ct:g research|security operations placement year'


def test_unknown_legacy_title_identity_does_not_hide_new_requisition():
    seen = {jsd.ct_key('G-Research', 'Security Operations Placement Year'): 't'}
    assert not jsd.already_seen('G-Research', 'Security Operations Placement Year',
        'https://gresearch.wd103.myworkdayjobs.com/x/Security-Operations-Placement-Year_R3795', seen)


def test_already_seen_is_false_for_a_genuinely_new_role():
    seen = {jsd.ct_key('Acme', 'Graduate SOC Analyst'): 't'}
    assert jsd.already_seen('Beta', 'Cyber Internship', 'https://beta.example/1',
                            seen) is False


def test_already_seen_matches_on_the_url_alone():
    seen = {jsd.posting_key('https://x.example/job/1'): 't'}
    assert jsd.already_seen('Unknown', '', 'https://x.example/job/1?utm_source=a',
                            seen) is True


def test_role_keys_carries_both_identities():
    keys = jsd.role_keys('Acme', 'Graduate SOC Analyst', 'https://acme.example/jobs/12345678')
    assert jsd.posting_key('https://acme.example/jobs/12345678') in keys
    assert 'req:acme:12345678' in keys
    assert jsd.ct_key('Acme', 'Graduate SOC Analyst') not in keys


def test_ct_key_is_empty_when_the_role_is_unnamed():
    assert jsd.ct_key('Acme', '') == ''
    assert jsd.ct_key('', 'Graduate SOC Analyst') == ''


def test_batch_result_counts_parses_the_searches_own_lines():
    out = ('Search coverage: 2 distinct batches\n'
           '--- batch 0: 6 queries ---\n  batch 0: 7 results returned\n'
           '--- batch 1: 6 queries ---\n  batch 1: 0 results returned\n')
    assert jsd.batch_result_counts(out) == [7, 0]


def test_search_failed_flags_a_search_that_returned_nothing_at_all():
    """The outage that hides as 'no new jobs': every batch empty."""
    out = ('--- batch 0: 6 queries ---\n  batch 0: 0 results returned\n'
           '--- batch 1: 6 queries ---\n  batch 1: 0 results returned\n')
    reason = jsd.search_failed(out)
    assert reason and '2 batch(es) returned 0 results' in reason


def test_search_failed_is_quiet_when_any_batch_returned_results():
    """Real results that were all duplicates is a HEALTHY empty cycle."""
    out = ('  batch 0: 5 results returned\n  batch 1: 0 results returned\n')
    assert jsd.search_failed(out) == ''


def test_search_failed_flags_timeouts_with_no_results():
    out = '--- batch 0: 6 queries ---\n  batch 0: TIMEOUT after 600s\n'
    reason = jsd.search_failed(out)
    assert reason and 'timed out' in reason


def test_search_failed_ignores_a_timeout_alongside_real_results():
    out = ('  batch 0: 4 results returned\n'
           '  batch 1: TIMEOUT after 600s\n')
    assert jsd.search_failed(out) == ''


def test_search_failed_is_quiet_on_output_with_no_batch_lines():
    """A run that never reached a batch is caught by write_ok, not here."""
    assert jsd.search_failed('no batches ran') == ''


def test_digest_gives_every_role_a_link_and_ends_with_a_summary():
    import datetime as dt
    items = [
        {'company': 'Acme', 'title': 'Graduate SOC Analyst',
         'url': 'https://acme.example/1', 'deadline': '2026-11-01'},
        {'company': 'Beta', 'title': 'Cyber Internship',
         'url': 'https://beta.example/2', 'deadline': ''},
    ]
    text = jsd.build_digest(items, dt.datetime(2026, 10, 21, 23, 0))
    assert 'https://acme.example/1' in text
    assert 'https://beta.example/2' in text
    assert 'Graduate SOC Analyst' in text and 'Cyber Internship' in text
    assert text.rstrip().splitlines()[-1].startswith('Summary: 2 new role(s) - ')
    assert 'Acme' in text.rstrip().splitlines()[-1]


def test_digest_falls_back_to_the_title_when_the_company_is_unknown():
    import datetime as dt
    text = jsd.build_digest([{'company': 'Unknown', 'title': 'Security Intern',
                              'url': 'https://x/1', 'deadline': ''}],
                            dt.datetime(2026, 10, 21, 23, 0))
    assert 'Security Intern' in text


def test_digest_counts_match_the_roles_listed():
    import datetime as dt
    items = [{'company': f'C{i}', 'title': f'Role {i}', 'url': f'https://x/{i}',
              'deadline': ''} for i in range(3)]
    text = jsd.build_digest(items, dt.datetime(2026, 10, 21, 23, 0))
    assert '3 new role(s) found' in text


def test_slot_advances_one_batch_every_two_hours():
    """The search's own default rotates by DAY, which would repeat all day."""
    assert jsd.SLOT_SECONDS == 7200


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
