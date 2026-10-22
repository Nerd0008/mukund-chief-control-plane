#!/usr/bin/env python3
"""Tests for deadline capture, liveness check, and entry-level filter tightening.

Offline and read-only: no network calls, no workbook writes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import jd_fetcher as jf  # noqa: E402
import codex_entry_level_search as ces  # noqa: E402
from daily_jobs_links import tracker_rows  # noqa: E402


# ---------------------------------------------------------------------------
# jd_fetcher deadline extraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Applications close on 15 November 2026.", "2026-11-15"),
    ("Closing date: 31 December 2026", "2026-12-31"),
    ("Apply by 1st January 2027", "2027-01-01"),
    ("Deadline: 30/06/2026", "2026-06-30"),
    ("No deadline stated here", None),
    ("Applications are reviewed on a rolling basis", None),
])
def test_extract_deadline(text, expected):
    assert jf.extract_deadline(text) == expected


def test_extract_deadline_ignores_past_dates():
    """A closing date without a year remains unknown rather than inventing one."""
    result = jf.extract_deadline("Applications close 15 November")
    assert result is None  # Missing year is UNKNOWN; never invent a closing date.


# ---------------------------------------------------------------------------
# jd_fetcher liveness check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("This position has been filled.", True),
    ("Applications are now closed.", True),
    ("We are no longer accepting applications.", True),
    ("The deadline has passed.", True),
    ("Join our team as a Security Analyst.", False),
    ("We are looking for a talented engineer.", False),
    ("Applications reviewed on a rolling basis.", False),
])
def test_is_job_closed(text, expected):
    assert jf.is_job_closed(text) is expected


# ---------------------------------------------------------------------------
# supported neutral titles reach JD screening; this is not final eligibility
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Cyber Security Intern", True),
    ("Graduate Security Analyst", True),
    ("Junior SOC Analyst", True),
    ("Security Analyst", True),
    ("Software Engineer", False),
    ("Service Desk Analyst", True),
    ("IT Support Engineer", True),
    ("Trainee SOC Analyst", True),
    ("Information Security Intern", True),
    ("Security Engineer, Cloud", True),
])
def test_is_entry_level(title, expected):
    assert ces.is_entry_level(title, ces.ENTRY_MARKERS) is expected


# ---------------------------------------------------------------------------
# digest age labeling
# ---------------------------------------------------------------------------

def test_writer_rejects_url_only_rows_without_identity(tmp_path, monkeypatch):
    """A URL-only row must be rejected by the integrity guard.

    Codex's tracker_integrity.py catches rows that have a URL but no
    company or title. This test proves the guard works.
    """
    import openpyxl
    import tracker_integrity as ti
    from tracker_writer import write_records

    tracker = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.cell(row=1, column=1, value="Date Found")
    ws.cell(row=1, column=2, value="Company")
    ws.cell(row=1, column=3, value="Role Title")
    ws.cell(row=1, column=4, value="Apply Link")
    ws.cell(row=1, column=5, value="Application Deadline")
    ws.cell(row=1, column=6, value="Status")
    # Row 2: URL only, no company/title — should be rejected
    ws.cell(row=2, column=4, value="https://example.com/job")
    wb.save(tracker)

    cfg = {
        "tracker": str(tracker),
        "sheet": "Jobs",
        "header_row": 1,
        "first_data_row": 2,
        "dedupe": {"url_column": "D"},
        "field_map": {"company": "B", "title": "C"},
    }

    ws2 = openpyxl.load_workbook(tracker).active
    with pytest.raises(ValueError, match="URL-only row"):
        ti.assert_valid(ws2, cfg)


def test_tracker_rows_age_label(tmp_path, monkeypatch):
    """tracker_rows labels jobs by age."""
    import openpyxl
    import datetime as dt

    tracker = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.cell(row=1, column=1, value="Date Found")
    ws.cell(row=1, column=2, value="Company")
    ws.cell(row=1, column=3, value="Role Title")
    ws.cell(row=1, column=4, value="Apply Link")
    today = dt.date.today()
    for i, days_ago in enumerate([0, 1, 3, 10, 30], start=2):
        ws.cell(row=i, column=1, value=today - dt.timedelta(days=days_ago))
        ws.cell(row=i, column=2, value=f"Company {i}")
        ws.cell(row=i, column=3, value=f"Intern {i}")
        ws.cell(row=i, column=4, value=f"https://example.com/job{i}")
    wb.save(tracker)

    # Point the digest at our temp tracker
    import daily_jobs_links as djl
    monkeypatch.setitem(djl.TRACKERS, "uk", tracker)

    rows, err = tracker_rows("uk")
    assert err is None
    assert len(rows) == 5

    labels = [r.get("age_label", "") for r in rows]
    assert labels[0] == "today"
    assert labels[1] == "yesterday"
    assert "3 days ago" in labels[2]
    assert "10 days old" in labels[3]
    assert "30 days old" in labels[4]
