"""Auditable local E3 Stage 2 enablement state.

The state is machine-local and contains no credentials. Production dispatch uses
this module to fail closed until an explicitly confirmed owner-authorized enablement
has been recorded.
"""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"
STATE_FILE = RUNTIME_ROOT / "e3-stage2-state.json"

def read_state(path: Path | None = None) -> dict:
    path = path or STATE_FILE
    if not path.exists():
        return {"enabled": False, "reason": "no enablement record"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "reason": "unreadable enablement record"}
    return data if data.get("enabled") is True else {"enabled": False, "reason": "disabled enablement record"}

def require_enabled(path: Path | None = None) -> dict:
    state = read_state(path)
    if not state.get("enabled"):
        raise RuntimeError("E3 Stage 2 is disabled; use e3-stage2-enable with a recorded owner authorization and --confirm")
    return state

def enable(*, approval_record: str, regression_evidence: str, allowed_workers: list[str], path: Path | None = None) -> dict:
    path = path or STATE_FILE
    record = {
        "enabled": True,
        "enabled_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approval_record": approval_record,
        "regression_evidence": regression_evidence,
        "allowed_workers": sorted(set(allowed_workers)),
        "note": "Provider-deferred workers remain non-routable and cannot be selected for dispatch.",
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record
