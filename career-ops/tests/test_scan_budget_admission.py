"""Replay the 28 October failure without providers or owner workbook writes."""
import json
from contextlib import contextmanager
import pytest
import job_scan_delta as delta
import codex_entry_level_search as direct
import web_research as web


def test_optional_third_batch_cannot_shrink_worker_budget(monkeypatch, tmp_path):
    clock = [0.0]
    calls = []
    monkeypatch.setattr(delta.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(delta, 'CURSOR', tmp_path / 'cursor.json')
    def search(offset, timeout, **kwargs):
        calls.append((offset, timeout))
        clock[0] += [420, 280, 203][len(calls)-1]
        return 0, 'SEARCH_COVERAGE {"coverage_complete": true}', ''
    monkeypatch.setattr(delta, 'run_search', search)
    code, out, err, coverage = delta.run_searches(4, 600, max_batches=3,
        budget_seconds=1200, pool_size=16)
    # One complete batch consumed 420s: only 780s remains, less than
    # the full 600s search plus 300s child grace. Defer, do not squeeze.
    assert calls == [(4, 600)]
    assert code == 0 and coverage['coverage_complete'] is True
    assert coverage['next_offset'] == 5
    assert coverage['stop_reason'] == 'insufficient_budget_for_full_batch'
    assert coverage['deferred_batches'] == 2
    assert json.loads(delta.CURSOR.read_text())['next_offset'] == 5


def test_insufficient_first_batch_is_not_claimed_success(monkeypatch):
    monkeypatch.setattr(delta, 'run_search', lambda *a, **k: pytest.fail('short worker launched'))
    code, out, err, coverage = delta.run_searches(6, 600, dry_run=True,
        budget_seconds=500, pool_size=16)
    assert code != 0 and coverage['coverage_complete'] is False
    assert coverage['batches_attempted'] == 0 and coverage['next_offset'] == 6


def test_full_batches_still_use_spare_capacity(monkeypatch):
    calls = []
    monkeypatch.setattr(delta, 'run_search', lambda offset, timeout, **kw:
        (calls.append((offset, timeout)) or (0, 'SEARCH_COVERAGE {"coverage_complete": true}', '')))
    code, out, err, coverage = delta.run_searches(4, 600, dry_run=True,
        budget_seconds=1200, max_batches=3, pool_size=16)
    assert code == 0 and calls == [(4, 600), (5, 600), (6, 600)]
    assert coverage['deferred_batches'] == 0


def test_worker_slice_does_not_shrink_after_timeout(monkeypatch):
    clock = [0.0]
    calls = []
    monkeypatch.setattr(direct.time, 'monotonic', lambda: clock[0])
    class Provider:
        def __init__(self, **kw): pass
        def resolve(self): return 'fixture'
        @contextmanager
        def authorize_batch(self, *args):
            clock[0] += 20  # real router authorization consumes the batch budget
            yield
        def _run_one(self, exe, query, **kw):
            calls.append(kw['timeout'])
            clock[0] += kw['timeout'] + 0.1
            return {'web_search_observed': False, 'results': [], 'error': 'timeout'}
    monkeypatch.setattr(web, 'CodexWebSearchProvider', Provider)
    with pytest.raises(direct.SearchUnavailable) as failed:
        direct.run_codex('1. "one"\n2. "two"\n3. "three"', timeout=320)
    assert calls == [100, 100]
    assert failed.value.evidence['query_receipts'][-1]['error'] == 'batch elapsed budget exhausted'


def test_timeout_alert_is_specific_and_never_exposes_command():
    errors = ['TimeoutExpired: Command PRIVATE timed out after 30.0 seconds'] * 5
    coverage = {'batches':[{'coverage':{'query_receipts':[{'query_receipts':
        [{'complete':True}]*13 + [{'complete':False,'error':e} for e in errors]}]}}]}
    summary = delta.failure_summary(coverage)
    assert '13/18 queries completed' in summary
    assert 'search_worker_timeout=5' in summary
    assert 'PRIVATE' not in summary and 'search_worker_failed' not in summary


@pytest.mark.parametrize('confirmed', [True, False])
def test_later_failure_reports_only_earlier_confirmed_appends(monkeypatch, tmp_path, capsys, confirmed):
    import sys
    import owner_search_profile
    ledger = tmp_path / 'seen.json'
    delta.save_ledger(ledger, {'existing': 'before'})
    tracker = tmp_path / 'tracker.xlsx'
    tracker.touch()  # No workbook read: the existing ledger is already initialized.
    cursor = tmp_path / 'cursor.json'
    cursor.write_text('{"next_offset":6}')
    for name, value in {'LEDGER':ledger, 'CURSOR':cursor, 'RUNS':tmp_path/'runs',
                        'SEARCH_LOG':tmp_path/'search.log'}.items():
        monkeypatch.setattr(delta, name, value)
    monkeypatch.setattr(delta, 'acquire_run_lock', lambda *a: object())
    monkeypatch.setattr(owner_search_profile, 'load_profile', lambda: {})
    row = {'company':'Example', 'title':'Cyber Security Graduate',
           'url':'https://jobs.example/jobs/12345678', 'decision':'appended'}
    out = 'TRACKER_WRITE_RESULT ' + json.dumps({'applied':confirmed, 'outcomes':[row]})
    coverage = {'batches':[{'coverage':{'query_receipts':[{'query_receipts':
                [{'complete':False,'error':'TimeoutExpired: private'}]}]}}]}
    monkeypatch.setattr(delta, 'run_searches', lambda *a, **k: (2, out, '', coverage))
    monkeypatch.setattr(sys, 'argv', ['scan','--tracker',str(tracker)])
    assert delta.main() == 3  # Failure remains a failure, even if a prior batch wrote.
    text = capsys.readouterr().out
    assert 'Job scan FAILED' in text and 'search_worker_timeout=1' in text
    assert ('Cyber Security Graduate' in text) is confirmed
    assert (delta.posting_key(row['url']) in delta.load_ledger(ledger)) is confirmed
    assert json.loads(cursor.read_text())['next_offset'] == 6
