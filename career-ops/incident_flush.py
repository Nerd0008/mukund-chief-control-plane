#!/usr/bin/env python3
"""Flush undelivered incidents to the Discord #incidents channel.

Runs as a no_agent cron job: its stdout IS the alert, delivered by the cron
delivery path to #incidents. Empty stdout sends nothing (the watchdog pattern).

Design note: an incident is marked flushed only AFTER it has been handed to the
delivery path. Because a no_agent script cannot confirm delivery, incidents are
marked with the flush timestamp and re-flushed only if they are still
un-delivered after a grace period, so a lost alert comes back rather than
disappearing silently.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

CONTROL_PLANE = Path(__file__).resolve().parent.parent
INCIDENT_LOG = CONTROL_PLANE / "runtime" / "incidents" / "incidents.jsonl"
FLUSH_STATE = CONTROL_PLANE / "runtime" / "incidents" / "flush_state.json"

# Re-alert an incident that was handed off but never confirmed within this many
# minutes, so a delivery failure does not swallow the alert forever.
REALERT_AFTER_MINUTES = 60
MAX_PER_FLUSH = 5


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_lines() -> list[dict]:
    if not INCIDENT_LOG.exists():
        return []
    rows = []
    for line in INCIDENT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main() -> int:
    rows = load_lines()
    if not rows:
        return 0

    state = {}
    if FLUSH_STATE.exists():
        try:
            state = json.loads(FLUSH_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}

    now = dt.datetime.now(dt.timezone.utc)
    pending = []
    for idx, row in enumerate(rows):
        if row.get("delivered"):
            continue
        key = str(idx)
        last = state.get(key)
        if last:
            try:
                when = dt.datetime.fromisoformat(last)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=dt.timezone.utc)
                if (now - when).total_seconds() < REALERT_AFTER_MINUTES * 60:
                    continue
            except ValueError:
                pass
        pending.append((key, row))

    if not pending:
        return 0

    pending = pending[:MAX_PER_FLUSH]
    lines = ["**Chief incident report**", ""]
    for key, row in pending:
        lines.append(f"**[{str(row.get('severity', 'error')).upper()}] "
                     f"{row.get('source', 'unknown')}**")
        lines.append(str(row.get("summary", "")).strip())
        detail = str(row.get("detail", "")).strip()
        if detail:
            lines.append(f"```{detail[:600]}```")
        lines.append("")
        state[key] = now_utc()

    # Print for the cron delivery path. stdout is the alert.
    print("\n".join(lines))

    FLUSH_STATE.parent.mkdir(parents=True, exist_ok=True)
    FLUSH_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
