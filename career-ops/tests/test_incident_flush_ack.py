#!/usr/bin/env python3
"""Offline regression tests for ACK-safe incident flushing."""

from __future__ import annotations

import datetime as dt
import io
import json
import sqlite3
import sys
from pathlib import Path

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import incident_flush as inc  # noqa: E402


JOB_ID = "ebd5d0bcd189"
T0 = dt.datetime(2026, 10, 3, 9, 40, tzinfo=dt.timezone.utc)


def _incident_log(path: Path) -> None:
    row = {
        "at": "2026-10-03T08:30:00+00:00",
        "source": "fixture",
        "summary": "fixture incident",
        "detail": "offline only",
        "severity": "error",
        "channel_id": "1551586416260161699",
        "delivered": False,
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """CREATE TABLE executions (
                 id TEXT PRIMARY KEY,
                 job_id TEXT NOT NULL,
                 status TEXT NOT NULL,
                 claimed_at TEXT NOT NULL,
                 started_at TEXT,
                 finished_at TEXT,
                 delivery_outcome TEXT
               )"""
        )
        conn.commit()
    finally:
        conn.close()


def _insert_execution(
    path: Path, execution_id: str, *,
    status: str = "running", outcome: str | None = None,
    claimed_at: dt.datetime = T0, finished_at: dt.datetime | None = None,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO executions
               (id, job_id, status, claimed_at, started_at, finished_at, delivery_outcome)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                execution_id, JOB_ID, status, claimed_at.isoformat(),
                claimed_at.isoformat(),
                finished_at.isoformat() if finished_at else None,
                outcome,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _finish(
    path: Path, execution_id: str, *,
    status: str = "completed", outcome: str = "delivered",
    finished_at: dt.datetime | None = None,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """UPDATE executions
               SET status=?, delivery_outcome=?, finished_at=?
               WHERE id=?""",
            (
                status, outcome,
                (finished_at or (T0 + dt.timedelta(seconds=5))).isoformat(),
                execution_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _paths(tmp_path: Path):
    log = tmp_path / "incidents.jsonl"
    state = tmp_path / "flush_state.json"
    db = tmp_path / "executions.db"
    _incident_log(log)
    _db(db)
    return log, state, db


def test_grace_period_suppressed_is_empty_and_state_unchanged(tmp_path):
    log, state, db = _paths(tmp_path)
    rows = inc.load_lines(log)
    iid = inc.stable_incident_id(rows[0], 0)
    doc = {
        "version": inc.STATE_VERSION,
        "in_flight": None,
        "last_attempt_at": {iid: inc.iso_utc(T0)},
        "last_attempt_outcome": {iid: "failed"},
    }
    state.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    before = state.read_bytes()
    out = io.StringIO()

    result = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=30), stdout=out,
    )

    assert result["emitted"] == 0
    assert out.getvalue() == ""
    assert state.read_bytes() == before
    assert inc.load_lines(log)[0]["delivered"] is False


def test_eligible_incident_is_emitted_but_not_delivered_yet(tmp_path):
    log, state, db = _paths(tmp_path)
    _insert_execution(db, "exec-1")
    out = io.StringIO()

    result = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0, stdout=out,
    )

    assert result["emitted"] == 1
    assert result["execution_id"] == "exec-1"
    assert "fixture incident" in out.getvalue()
    assert inc.load_lines(log)[0]["delivered"] is False
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["in_flight"]["execution_id"] == "exec-1"


def test_ack_success_marks_exact_incident_delivered(tmp_path):
    log, state, db = _paths(tmp_path)
    _insert_execution(db, "exec-1")
    first = io.StringIO()
    inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0, stdout=first,
    )
    _finish(db, "exec-1", status="completed", outcome="delivered")

    second = io.StringIO()
    result = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=30), stdout=second,
    )

    row = inc.load_lines(log)[0]
    assert result["delivered"] == 1
    assert row["delivered"] is True
    assert row["delivery_ack"]["execution_id"] == "exec-1"
    assert row["delivery_ack"]["delivery_outcome"] == "delivered"
    assert second.getvalue() == ""


def test_delivery_failure_keeps_pending_and_retries_after_grace(tmp_path):
    log, state, db = _paths(tmp_path)
    _insert_execution(db, "exec-1")
    inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0, stdout=io.StringIO(),
    )
    _finish(db, "exec-1", status="completed", outcome="failed")

    suppressed = io.StringIO()
    mid = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=30), stdout=suppressed,
    )
    assert mid["emitted"] == 0
    assert suppressed.getvalue() == ""
    assert inc.load_lines(log)[0]["delivered"] is False

    _insert_execution(
        db, "exec-2", status="running",
        claimed_at=T0 + dt.timedelta(minutes=61),
    )
    retry = io.StringIO()
    later = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=61), stdout=retry,
    )
    assert later["emitted"] == 1
    assert later["execution_id"] == "exec-2"
    assert "fixture incident" in retry.getvalue()
    assert inc.load_lines(log)[0]["delivered"] is False


def test_repeated_run_after_ack_emits_nothing(tmp_path):
    log, state, db = _paths(tmp_path)
    _insert_execution(db, "exec-1")
    inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0, stdout=io.StringIO(),
    )
    _finish(db, "exec-1", status="completed", outcome="delivered")
    inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=30), stdout=io.StringIO(),
    )

    out = io.StringIO()
    result = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=90), stdout=out,
    )
    assert result["emitted"] == 0
    assert out.getvalue() == ""


def test_crash_restart_between_emission_and_ack_is_retry_safe(tmp_path):
    log, state, db = _paths(tmp_path)
    _insert_execution(db, "exec-1")
    inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0, stdout=io.StringIO(),
    )

    # Simulated restart while the exact prior attempt has no terminal ACK yet.
    out = io.StringIO()
    unresolved = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=30), stdout=out,
    )
    assert unresolved["blocked_by_in_flight"] is True
    assert unresolved["emitted"] == 0
    assert out.getvalue() == ""
    assert inc.load_lines(log)[0]["delivered"] is False

    # Once Hermes records the prior exact attempt as delivered, reconciliation
    # completes without another Discord emission.
    _finish(db, "exec-1", status="completed", outcome="delivered")
    final_out = io.StringIO()
    resolved = inc.flush_once(
        incident_log=log, state_file=state, executions_db=db,
        job_id=JOB_ID, now=T0 + dt.timedelta(minutes=31), stdout=final_out,
    )
    assert resolved["delivered"] == 1
    assert final_out.getvalue() == ""
    assert inc.load_lines(log)[0]["delivered"] is True
