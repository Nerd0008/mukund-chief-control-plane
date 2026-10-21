"""Tests for tracker_add_rejected_rows.

The nine rows are the rejections the 60-day Gmail sweep found that had no tracker
row at all. What must never regress: the role wording comes from the employer's
own email, the link is the employer's own application page (never an aggregator),
the sort order is preserved, and no pre-existing row is altered or dropped.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
MOD_PATH = HERE.parent / 'tracker_add_rejected_rows.py'

_spec = importlib.util.spec_from_file_location('tar', MOD_PATH)
tar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tar)


def _rows(n):
    rows = []
    for i in range(n):
        sheet_row = i + 3
        rows.append({
            'row': sheet_row,
            'values': ['2026-09-01', f'Company {i}', f'Role {i}',
                       f'https://example.invalid/{i}', None, 'Not Applied'],
            'formats': ['@', '@', '@', '@', '@', '@'],
        })
    return rows


def test_nine_rows_are_declared():
    assert len(tar.NEW_ROWS) == 9


def test_every_new_row_is_rejected_with_an_employer_link():
    for spec in tar.NEW_ROWS:
        assert spec['status'] == 'Rejected'
        assert spec['url'].startswith('http')
        assert ' ' not in spec['url']
        assert spec['date_found'].count('-') == 2
        assert spec['company'] and spec['title']


def test_links_are_employer_pages_not_aggregators():
    blocked = ('indeed.com', 'linkedin.com/jobs', 'glassdoor', 'indeed',
               'simplyhired', 'talent.com', 'cv-library', 'totaljobs',
               'reed.co.uk', 'adzuna', 'hays', 'michaelpage')
    for spec in tar.NEW_ROWS:
        low = spec['url'].lower()
        for b in blocked:
            assert b not in low, f'{spec["company"]} link looks like an aggregator: {spec["url"]}'


def test_build_appends_and_keeps_every_input_row():
    rows = _rows(112)
    kept = tar.build(rows)
    assert len(kept) == 121
    # every original row survives unchanged
    by_row = {r['row']: r for r in kept}
    for r in rows:
        assert by_row[r['row']]['values'] == r['values']


def test_build_orders_open_then_applied_then_rejected():
    rows = _rows(5)
    rows[0]['values'][5] = 'Applied'
    rows[1]['values'][5] = 'Rejected'
    kept = tar.build(rows)
    statuses = [r['values'][5] for r in kept]
    assert statuses == sorted(statuses, key=lambda s: 0 if s == 'Not Applied'
                              else (1 if s == 'Applied' else 2))


def test_new_rows_carry_a_link_target_for_hyperlink_binding():
    kept = tar.build(_rows(3))
    added = [r for r in kept if r['row'] > 5]
    assert len(added) == 9
    for r in added:
        assert r['link_target'] == r['url']
        assert r['values'][3] == r['url']


def test_margo_role_is_recorded_as_unknown_not_guessed():
    """The employer named no role in either email; the row must say so."""
    margo = [s for s in tar.NEW_ROWS if s['company'] == 'Margo Group']
    assert len(margo) == 1
    assert 'not named' in margo[0]['title'].lower()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
