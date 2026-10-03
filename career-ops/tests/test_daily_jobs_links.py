#!/usr/bin/env python3
"""Tests for the daily job-links digest (owner request 2026-10-03).

Offline and non-destructive. Nothing here writes to a canonical workbook, opens
a network connection, starts a browser, or contacts an employer/recruiter.

The contracts pinned here:

1. **Read-only** - every canonical workbook is byte-identical before/after.
2. **No fabrication** - a missing run is UNKNOWN, never "no jobs"; a job's URL is
   the source's own URL and is never invented.
3. **Synthetic guard** - validation/fixture records never surface as real jobs.
4. **Stale honesty** - an old run is labelled STALE and the exit code says so.
5. **Acceptance gate is the pipeline's own** - only `accepted` classifications
   are listed; this script does not re-judge the funnel.

Run:  python -m pytest career-ops/tests/test_daily_jobs_links.py -v
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import daily_jobs_links as djl  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_run(tmp_path: Path, region: str, *, generated: dt.datetime,
              accepted: list[dict], first_zero: str | None = None) -> Path:
    """Write a minimal unified run document the way the pipeline writes one."""
    directory = tmp_path / "discovery" / "unified" / region
    directory.mkdir(parents=True, exist_ok=True)
    classifications = []
    for item in accepted:
        classifications.append({
            "accepted": True,
            "primary_label": item.get("label", "strong_entry_level_match"),
            "confidence": item.get("confidence", 0.9),
            "source_fields": {
                "company": item.get("company"),
                "title": item.get("title"),
                "url": item.get("url"),
                "location": item.get("location", ""),
            },
        })
    # one rejected record proves the gate is respected
    classifications.append({
        "accepted": False,
        "primary_label": "not_relevant",
        "confidence": 0.2,
        "source_fields": {"company": "Rejected Co", "title": "Senior Architect",
                          "url": "https://example.com/rejected"},
    })
    doc = {
        "schema_version": 1,
        "run_id": f"unified-{region}-TEST",
        "region": region,
        "generated_at": generated.isoformat(),
        "classifications": classifications,
        "funnel": {"counts": {"tracker_candidates": 0},
                   "zero_attribution": {"first_zero_stage": first_zero,
                                        "reason": "test fixture"}},
    }
    path = directory / f"unified-{region}-TEST.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point the digest at an empty discovery root and no real workbooks."""
    monkeypatch.setattr(djl, "DISCOVERY", tmp_path / "discovery")
    monkeypatch.setattr(djl, "TRACKERS", {r: tmp_path / f"{r}.xlsx" for r in djl.REGIONS})
    return tmp_path


def test_missing_run_is_unknown_never_no_jobs(isolated):
    text, code = djl.build_digest(26.0, 100_000, 25)
    assert code == 3
    assert "UNKNOWN" in text
    assert "no discovery run artifact" in text.lower() or "No discovery run artifact" in text
    # The one thing it must never claim:
    assert "0 job(s) found" not in text


def test_accepted_listed_with_source_url_and_rejected_excluded(isolated):
    write_run(isolated, "uk", generated=NOW, accepted=[
        {"company": "Hoxhunt", "title": "Junior Security Engineer, GRC",
         "url": "https://jobs.ashbyhq.com/hoxhunt/abc"},
        {"company": "PA Consulting", "title": "Graduate Cyber Analyst",
         "url": "https://www.consultancy.uk/jobs/49848/pa"},
    ])
    text, code = djl.build_digest(26.0, 100_000, 25)
    assert code == 0
    assert "Hoxhunt — Junior Security Engineer, GRC" in text
    assert "https://jobs.ashbyhq.com/hoxhunt/abc" in text
    assert "PA Consulting — Graduate Cyber Analyst" in text
    assert "Rejected Co" not in text
    assert "Senior Architect" not in text


def test_synthetic_records_never_surface(isolated):
    write_run(isolated, "uk", generated=NOW, accepted=[
        {"company": "NOT A REAL VACANCY", "title": "Validation",
         "url": "https://example.invalid/job"},
        {"company": "Real Co", "title": "SOC Analyst", "url": "https://real.example.org/j"},
    ])
    text, _ = djl.build_digest(26.0, 100_000, 25)
    assert "Real Co" in text
    assert "NOT A REAL VACANCY" not in text
    assert ".invalid" not in text


def test_stale_run_is_labelled_and_exit_code_signals_it(isolated):
    old = NOW - dt.timedelta(hours=200)
    write_run(isolated, "uk", generated=old, accepted=[
        {"company": "Old Co", "title": "Old Role", "url": "https://old.example.org/j"}])
    text, code = djl.build_digest(26.0, 100_000, 25)
    assert "STALE/UNKNOWN" in text
    assert "NOT today's state" in text
    # A stale run still prints its own truth, but the digest is not fresh: a
    # stale-only digest must exit non-zero so a watchdog can tell the difference.
    assert "Old Co" in text
    assert code == 3


def test_all_regions_stale_yields_exit_3(isolated):
    old = NOW - dt.timedelta(hours=500)
    for region in djl.REGIONS:
        write_run(isolated, region, generated=old, accepted=[])
    text, code = djl.build_digest(26.0, 100_000, 25)
    assert "No region produced a fresh discovery run" in text
    assert code == 3


def test_zero_stage_is_reported_not_hidden(isolated):
    write_run(isolated, "dubai", generated=NOW, accepted=[], first_zero="discovered_raw")
    text, _ = djl.build_digest(26.0, 100_000, 25)
    assert "First zero stage: discovered_raw" in text


def test_url_extraction_from_hyperlink_formula():
    assert djl.as_url('=HYPERLINK("https://pwc.wd3.myworkdayjobs.com/en-US/x","Apply")') \
        == "https://pwc.wd3.myworkdayjobs.com/en-US/x"
    assert djl.as_url("https://plain.example.org/job") == "https://plain.example.org/job"
    assert djl.as_url("Not stated") == ""
    assert djl.as_url(None) == ""


def test_tracker_write_never_happens_real_workbooks_unchanged():
    """The digest must be byte-for-byte read-only against the real workbooks."""
    before = {}
    for region, path in djl.TRACKERS.items():
        if path.exists():
            before[region] = sha256(path)
    if not before:
        pytest.skip("no canonical workbooks present on this machine")
    djl.build_digest(26.0, 100_000, 25)
    for region, digest in before.items():
        assert sha256(djl.TRACKERS[region]) == digest, f"{region} workbook was modified"


def test_budget_truncation_says_what_it_dropped(isolated):
    for region in djl.REGIONS:
        write_run(isolated, region, generated=NOW, accepted=[
            {"company": f"Co {i}", "title": f"Role {i}", "url": f"https://c{i}.example.org/j"}
            for i in range(10)])
    text, _ = djl.build_digest(26.0, 700, 25)
    assert "omitted to fit the message limit" in text
    assert len(text) <= 900  # budget honoured (with the omission note)


def test_max_per_region_summarises_the_rest(isolated):
    write_run(isolated, "uk", generated=NOW, accepted=[
        {"company": f"Co {i}", "title": f"Role {i}", "url": f"https://c{i}.example.org/j"}
        for i in range(8)])
    text, _ = djl.build_digest(26.0, 100_000, 3)
    assert "more in this run" in text
    assert "Co 3" not in text
