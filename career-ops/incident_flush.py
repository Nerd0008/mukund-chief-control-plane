#!/usr/bin/env python3
"""Flush pending Career Ops incidents through Hermes no-agent cron, ACK-safely.

The script's stdout is the existing Hermes delivery surface. Because Discord
delivery happens after this process exits, emitting stdout is not an ACK.

Two-phase state:
  pending -> in_flight (bound to the exact Hermes execution id) -> delivered

On the next invocation we inspect Hermes' durable cron executions ledger. Only
an exact prior execution whose delivery_outcome is "delivered" may mark that
batch delivered. Failed, unknown, queued, suppressed, or missing evidence never
clears an incident. The historical 60-minute re-alert grace remains.

No Discord API call lives here and the existing no_agent cron mechanism is
unchanged.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import TextIO

CONTROL_PLANE = Path(__file__).resolve().parent.parent
INCIDENT_LOG = CONTROL_PLANE / "runtime" / "incidents" / "incidents.jsonl"
FLUSH_STATE = CONTROL_PLANE / "runtime" / "incidents" / "flush_state.json"

HERMES_HOME = Path(
    os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")
).expanduser()
EXECUTIONS_DB = HERMES_HOME / "cron" / "executions.db"

INCIDENT_CRON_JOB_ID = os.environ.get(
    "CHIEF_INCIDENT_CRON_JOB_ID", "ebd5d0bcd189"
).strip()

REALERT_AFTER_MINUTES = 60
MAX_PER_FLUSH = 5
STATE_VERSION = 2
_TERMINAL_EXECUTION_STATES = frozenset({"completed", "failed", "unknown"})


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_time(raw: object) -> dt.datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def load_lines(path: Path = INCIDENT_LOG) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_lines(rows: list[dict], path: Path = INCIDENT_LOG) -> None:
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    _atomic_write_text(path, body)


def stable_incident_id(row: dict, index: int) -> str:
    """Stable id for legacy rows that predate explicit incident IDs."""
    existing = row.get("incident_id") or row.get("id")
    if existing:
        return str(existing)
    immutable = {
        key: value for key, value in row.items()
        if key not in {
            "incident_id", "id", "delivered", "delivered_at",
            "delivery", "delivery_ack", "log",
        }
    }
    payload = json.dumps(
        {"index": index, "record": immutable},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return "legacy-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _blank_state() -> dict:
    return {
        "version": STATE_VERSION,
        "in_flight": None,
        "last_attempt_at": {},
        "last_attempt_outcome": {},
    }


def load_state(path: Path, rows: list[dict]) -> tuple[dict, bool]:
    """Load v2 state; migrate the old {row-index: timestamp} grace map in memory."""
    if not path.exists():
        return _blank_state(), False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _blank_state(), False
    if not isinstance(raw, dict):
        return _blank_state(), False
    if raw.get("version") == STATE_VERSION:
        state = _blank_state()
        state.update(raw)
        if not isinstance(state.get("last_attempt_at"), dict):
            state["last_attempt_at"] = {}
        if not isinstance(state.get("last_attempt_outcome"), dict):
            state["last_attempt_outcome"] = {}
        if state.get("in_flight") is not None and not isinstance(state["in_flight"], dict):
            state["in_flight"] = None
        return state, False

    state = _blank_state()
    for key, stamp in raw.items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(rows) and parse_time(stamp) is not None:
            state["last_attempt_at"][stable_incident_id(rows[idx], idx)] = stamp
    return state, True


def save_state(state: dict, path: Path = FLUSH_STATE) -> None:
    _atomic_write_text(
        path, json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True)
    )


def _read_execution(db_path: Path, execution_id: str) -> dict | None:
    if not execution_id or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT id, job_id, status, claimed_at, started_at, finished_at,
                          delivery_outcome
                   FROM executions WHERE id=?""",
                (execution_id,),
            ).fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return None
    return dict(row) if row is not None else None


def _current_execution_id(db_path: Path, job_id: str) -> str | None:
    """Return this job's newest live Hermes execution, if observable."""
    if not job_id or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT id FROM executions
                   WHERE job_id=? AND status IN ('claimed','running')
                   ORDER BY claimed_at DESC, id DESC LIMIT 1""",
                (job_id,),
            ).fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return None
    return str(row["id"]) if row is not None else None


def _mark_batch_delivered(
    rows: list[dict], incident_ids: set[str], *,
    delivered_at: str, execution_id: str,
) -> int:
    changed = 0
    for idx, row in enumerate(rows):
        iid = stable_incident_id(row, idx)
        if iid not in incident_ids or row.get("delivered") is True:
            continue
        row["incident_id"] = iid
        row["delivered"] = True
        row["delivered_at"] = delivered_at
        row["delivery_ack"] = {
            "source": "hermes-cron-execution-ledger",
            "execution_id": execution_id,
            "delivery_outcome": "delivered",
        }
        changed += 1
    return changed


def reconcile_in_flight(
    rows: list[dict], state: dict, *,
    incident_log: Path, executions_db: Path, now: dt.datetime,
) -> dict:
    """Resolve a prior emitted batch against its exact Hermes execution."""
    batch = state.get("in_flight")
    result = {"resolved": False, "delivered": 0, "outcome": None}
    if not isinstance(batch, dict):
        return result

    execution_id = str(batch.get("execution_id") or "")
    emitted_at = parse_time(batch.get("emitted_at"))
    execution = _read_execution(executions_db, execution_id) if execution_id else None

    if execution is None:
        if emitted_at is not None and (
            now - emitted_at
        ).total_seconds() >= REALERT_AFTER_MINUTES * 60:
            state["in_flight"] = None
            result.update({"resolved": True, "outcome": "no_execution_evidence"})
        return result

    status = str(execution.get("status") or "")
    if status not in _TERMINAL_EXECUTION_STATES:
        return result

    outcome = str(execution.get("delivery_outcome") or "")
    ids = {str(i) for i in batch.get("incident_ids") or [] if str(i)}
    result.update({"resolved": True, "outcome": outcome or status})

    if status == "completed" and outcome == "delivered":
        delivered_at = str(execution.get("finished_at") or iso_utc(now))
        changed = _mark_batch_delivered(
            rows, ids, delivered_at=delivered_at, execution_id=execution_id
        )
        if changed:
            write_lines(rows, incident_log)
        result["delivered"] = changed
        for iid in ids:
            state["last_attempt_at"].pop(iid, None)
            state["last_attempt_outcome"].pop(iid, None)
    else:
        for iid in ids:
            state["last_attempt_outcome"][iid] = outcome or status or "unknown"

    state["in_flight"] = None
    return result


def _eligible_pending(
    rows: list[dict], state: dict, now: dt.datetime,
) -> list[tuple[int, str, dict]]:
    pending: list[tuple[int, str, dict]] = []
    for idx, row in enumerate(rows):
        if row.get("delivered") is True:
            continue
        iid = stable_incident_id(row, idx)
        last = parse_time(state["last_attempt_at"].get(iid))
        if last is not None and (
            now - last
        ).total_seconds() < REALERT_AFTER_MINUTES * 60:
            continue
        pending.append((idx, iid, row))
    return pending[:MAX_PER_FLUSH]


def _format_batch(pending: list[tuple[int, str, dict]]) -> str:
    lines = ["**Chief incident report**", ""]
    for _idx, _iid, row in pending:
        lines.append(
            f"**[{str(row.get('severity', 'error')).upper()}] "
            f"{row.get('source', 'unknown')}**"
        )
        lines.append(str(row.get("summary", "")).strip())
        detail = str(row.get("detail", "")).strip()
        if detail:
            lines.append("~~~" + detail[:600] + "~~~")
        lines.append("")
    return "\n".join(lines)


def flush_once(
    *, incident_log: Path = INCIDENT_LOG, state_file: Path = FLUSH_STATE,
    executions_db: Path = EXECUTIONS_DB, job_id: str = INCIDENT_CRON_JOB_ID,
    now: dt.datetime | None = None, stdout: TextIO | None = None,
) -> dict:
    """Run one deterministic flush iteration. Returns bookkeeping for tests."""
    now = now or now_utc()
    stdout = stdout or sys.stdout
    rows = load_lines(incident_log)
    state, migrated = load_state(state_file, rows)
    state_changed = migrated

    reconciliation = reconcile_in_flight(
        rows, state, incident_log=incident_log, executions_db=executions_db, now=now
    )
    state_changed = state_changed or reconciliation["resolved"]

    if state.get("in_flight") is not None:
        if state_changed:
            save_state(state, state_file)
        return {
            "emitted": 0, "delivered": reconciliation["delivered"],
            "reconciliation": reconciliation, "blocked_by_in_flight": True,
        }

    pending = _eligible_pending(rows, state, now)
    if not pending:
        if state_changed:
            save_state(state, state_file)
        return {
            "emitted": 0, "delivered": reconciliation["delivered"],
            "reconciliation": reconciliation, "blocked_by_in_flight": False,
        }

    execution_id = _current_execution_id(executions_db, job_id)
    emitted_at = iso_utc(now)
    incident_ids = [iid for _idx, iid, _row in pending]
    batch_seed = "|".join([execution_id or "unbound", emitted_at, *incident_ids])
    batch_id = hashlib.sha256(batch_seed.encode("utf-8")).hexdigest()[:24]

    state["in_flight"] = {
        "batch_id": batch_id,
        "incident_ids": incident_ids,
        "emitted_at": emitted_at,
        "execution_id": execution_id,
        "job_id": job_id,
    }
    for iid in incident_ids:
        state["last_attempt_at"][iid] = emitted_at
        state["last_attempt_outcome"].pop(iid, None)
    save_state(state, state_file)

    stdout.write(_format_batch(pending) + "\n")
    return {
        "emitted": len(pending),
        "delivered": reconciliation["delivered"],
        "batch_id": batch_id,
        "execution_id": execution_id,
        "reconciliation": reconciliation,
        "blocked_by_in_flight": False,
    }


def main() -> int:
    flush_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
