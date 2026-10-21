"""The four owner decisions, applied in one verified rewrite.

The failure this pins: a vacancy reachable by two rows survived as two rows, and
applications confirmed by employer email sat as "Not Applied". These tests pin
the shape of the rewrite, not the current contents of the tracker.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tracker_apply_decisions as tad  # noqa: E402


def row(n, company, status, title='Role'):
    return {
        'row': n,
        'values': ['2026-10-01', company, title, f'https://x/{n}', None, status],
        'formats': ['yyyy-mm-dd', 'General', 'General', 'General', 'General', 'General'],
        'url': f'https://x/{n}',
        'link_target': f'https://x/{n}',
    }


def fixture():
    rows = [row(n, f'Co{n}', 'Not Applied') for n in range(3, 20)]
    rows.append(row(tad.GHD_ROW, 'GHD Advisory', 'Not Applied'))
    rows.append(row(tad.FTI_KEEP_ROW, 'FTI Consulting', 'Not Applied'))
    rows.append(row(tad.FTI_DROP_ROW, 'FTI Consulting', 'Not Applied'))
    return rows


def test_the_duplicate_row_is_dropped():
    out = tad.build(fixture())
    assert tad.FTI_DROP_ROW not in [r['row'] for r in out]


def test_ghd_and_fti_take_their_new_statuses():
    out = {r['row']: r for r in tad.build(fixture())}
    assert out[tad.GHD_ROW]['values'][5] == 'Applied'
    assert out[tad.FTI_KEEP_ROW]['values'][5] == 'Rejected'


def test_both_new_applications_are_added_as_applied():
    out = tad.build(fixture())
    added = {r['values'][1]: r['values'][5] for r in out
             if r['values'][1] in ('Accenture', 'Shell')}
    assert added == {'Accenture': 'Applied', 'Shell': 'Applied'}


def test_new_rows_carry_a_real_employer_link():
    out = tad.build(fixture())
    for r in out:
        if r['values'][1] in ('Accenture', 'Shell'):
            assert r['values'][3].startswith('https://')
            assert 'myworkdayjobs.com' in r['values'][3]


def test_row_count_moves_by_one():
    """One duplicate out, two applications in."""
    before = len(fixture())
    after = len(tad.build(fixture()))
    assert after == before + 1


def test_order_is_open_then_applied_then_rejected():
    out = tad.build(fixture())
    buckets = [tad.sort_key(r)[0] for r in out]
    assert buckets == sorted(buckets), 'rows must be grouped open -> applied -> rejected'
    assert buckets[0] == 0 and buckets[-1] == 2


def test_existing_rows_keep_their_relative_order():
    out = tad.build(fixture())
    untouched = [r['row'] for r in out if r['row'] < tad.GHD_ROW]
    assert untouched == sorted(untouched)
