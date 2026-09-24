#!/usr/bin/env python3
"""Non-career operational services for the Chief control plane.

Owned by ``agent-operational-brief-health-backup-persistence-2026-09-23``.
This is the *operational* counterpart to the deployment package in
``deployments/`` (which covers the one-shot cutover path). Everything here is
designed to run unattended and repeatedly on the primary node:

Subcommands
-----------
``health-snapshot``
    Deterministic system health snapshot suitable for acceptance testing:
    database integrity, queue state, scheduled-task state, credential presence,
    brief availability and log sizes — aggregate facts only, never raw data.
``morning-brief``
    The Morning Chief Brief: aggregates the health snapshot, E2 resource status,
    active/blocked queue work, career-brief availability, exact owner actions and
    a failure-escalation section, and writes ``runtime/chief/morning-brief/``.
``backup``
    Operational backup of the declared state set with integrity verification and
    a deterministic retention policy. Snapshots are raw databases and therefore
    live **outside** the repository; only the aggregate report is publishable.
``validate-persistence``
    Read-only validation of restart/boot persistence for the Chief scheduled
    tasks, recording verdicts and the exact owner checklist items. It never
    changes a task.

Design rules
------------
* Read-only against live state. ``backup`` reads databases read-only and
  snapshots via the SQLite online backup API; nothing here overwrites live data.
* No provider/network call, no credential *value* ever read: presence and store
  name only (delegated to the existing presence probes).
* UNKNOWN stays UNKNOWN: an unobservable fact is reported as ``unknown`` with a
  reason, never coerced to a healthy default.
* Deterministic: sorted keys, no wall-clock-dependent branching other than the
  recorded timestamps.

Usage:
    python scripts/operational_services.py <subcommand> [--out-dir DIR] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HERMES_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
RUNTIME_ROOT = HERMES_ROOT / "exec-brain"

sys.path.insert(0, str(Path(__file__).resolve().parent))          # scripts/
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))                  # repo modules
sys.path.insert(0, str(RUNTIME_ROOT))                             # live runtime

# The declared operational state set. Kept in sync with
# deployments/01-deployment-manifest.md and scripts/deployment_preflight.py.
OPERATIONAL_DATABASES = [
    ("e1-e2-exec-brain", RUNTIME_ROOT / "exec_brain.db"),
    ("e2-governor", RUNTIME_ROOT / "governor.db"),
    ("e3-orchestration", RUNTIME_ROOT / "orchestration.db"),
    ("hermes-state", HERMES_ROOT / "state.db"),
    ("hermes-kanban", HERMES_ROOT / "kanban.db"),
    ("hermes-shared-state", HERMES_ROOT / "shared-state.db"),
    ("hermes-cron-executions", HERMES_ROOT / "cron" / "executions.db"),
]

OPERATIONAL_JSON_ARTIFACTS = [
    ("e1-chain-head", RUNTIME_ROOT / "chain-head.json"),
    ("e2-gov-chain-head", RUNTIME_ROOT / "gov-chain-head.json"),
]

# The Chief scheduled tasks whose persistence this service validates.
CHIEF_TASKS = [
    "Hermes_Gateway",
    "HermesRemoteQueuePoller",
    "ChiefDiscordSync",
    "ChiefCareerBrief",
    "ChiefCareerScan-UK",
    "ChiefCareerScan-Dubai",
    "ChiefCareerScan-Japan",
    "ChiefCareerScan-Singapore",
]

# Reads-only legacy tasks that must be *recorded*, never silently repaired.
LEGACY_TASKS = ["Mukund Chief of Staff"]

LOG_TARGETS = [
    HERMES_ROOT / "logs" / "agent.log",
    HERMES_ROOT / "logs" / "errors.log",
    HERMES_ROOT / "logs" / "gateway.log",
    HERMES_ROOT / "gateway-starts.log",
    REPO_ROOT / "remote-queue" / "logs" / "queue.log",
]

QUEUE_DIRS = {
    "pending": "pending",
    "running": "running",
    "completed": "completed",
    "blocked": "blocked",
}

OWNER_ACTIONS_FILE = REPO_ROOT / "tasks-or-issues" / "overnight-owner-actions-2026-09-24.md"

DEFAULT_BACKUP_ROOT = HERMES_ROOT / "backups" / "operational"

# Minimum threshold before a log is considered for rotation (bytes).
DEFAULT_LOG_MAX_BYTES = 5_000_000
DEFAULT_LOG_KEEP = 5
DEFAULT_SNAPSHOT_KEEP = 7


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_sha(repo_root: Path = REPO_ROOT) -> str:
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_root),
                              capture_output=True, text=True, timeout=60)
        return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Databases
# --------------------------------------------------------------------------- #

def db_status(db_paths=None) -> list:
    """Integrity + size + hash for each declared DB. Read-only, no contents."""
    db_paths = db_paths if db_paths is not None else OPERATIONAL_DATABASES
    out = []
    for label, path in db_paths:
        rec = {"label": label, "path": str(path), "exists": Path(path).exists()}
        if rec["exists"]:
            try:
                con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                try:
                    rec["integrity_check"] = con.execute(
                        "PRAGMA integrity_check").fetchone()[0]
                    tables = [r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")]
                    rec["table_count"] = len(tables)
                finally:
                    con.close()
                rec["size_bytes"] = Path(path).stat().st_size
                if rec["integrity_check"] == "ok":
                    rec["status"] = "PASS"
                else:
                    rec["status"] = "FAIL"
            except Exception as exc:
                rec["integrity_check"] = f"{type(exc).__name__}: {exc}"
                rec["status"] = "FAIL"
        else:
            rec["status"] = "FAIL"
            rec["reason"] = "missing"
        out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #

def queue_summary(queue_root=None) -> dict:
    """Counts + task ids per queue state. Never reads beyond the task envelope."""
    queue_root = Path(queue_root) if queue_root else (REPO_ROOT / "remote-queue")
    summary = {}
    for state, dirname in QUEUE_DIRS.items():
        d = queue_root / dirname
        entries = []
        if d.exists():
            for p in sorted(d.glob("*.json")):
                rec = {"task_id": p.stem}
                try:
                    data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                    rec["priority"] = data.get("priority")
                    if state == "blocked":
                        blocker = data.get("blocker") or {}
                        rec["blocker_category"] = blocker.get("category")
                except Exception as exc:
                    rec["invalid"] = f"{type(exc).__name__}"
                entries.append(rec)
        summary[state] = {"count": len(entries), "tasks": entries}
    summary["kill_switch"] = (queue_root / ".poller.kill").exists()
    return summary


# --------------------------------------------------------------------------- #
# Scheduled tasks
# --------------------------------------------------------------------------- #

def _default_task_runner(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _parse_task_xml(xml: str) -> dict:
    def tag(pattern):
        m = re.search(pattern, xml, re.S)
        return m.group(1).strip() if m else None

    return {
        "enabled_xml": (tag(r"<Enabled>(true|false)</Enabled>") or "true").lower() == "true",
        "logon_type": tag(r"<LogonType>(.*?)</LogonType>"),
        "run_level": tag(r"<RunLevel>(.*?)</RunLevel>"),
        "triggers": sorted(k for k, t in (
            ("time", "<TimeTrigger>"),
            ("calendar", "<CalendarTrigger>"),
            ("logon", "<LogonTrigger>"),
            ("boot", "<BootTrigger>"),
            ("idle", "<IdleTrigger>"),
        ) if t in xml),
        "restart_on_failure": "<RestartOnFailure>" in xml,
        "start_when_available": "<StartWhenAvailable>true</StartWhenAvailable>" in xml,
        "disallow_on_batteries": "<DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>" in xml,
        "stop_on_batteries": "<StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>" in xml,
        "execution_time_limit": tag(r"<ExecutionTimeLimit>(.*?)</ExecutionTimeLimit>"),
        "start_boundary": tag(r"<StartBoundary>(.*?)</StartBoundary>"),
        "repetition_interval": tag(r"<Interval>(.*?)</Interval>"),
    }


def query_scheduled_task(name: str, runner=None) -> dict:
    """Read-only XML + verbose state for one task. Never changes the task."""
    runner = runner or _default_task_runner
    rec: dict = {"task": name}
    try:
        xml_proc = runner(["schtasks", "/query", "/tn", name, "/xml"])
        if xml_proc.returncode != 0:
            rec["exists"] = False
            rec["error"] = "schtasks query failed (task not found or not readable)"
            return rec
        xml = xml_proc.stdout or ""
        rec["exists"] = True
        rec["definition"] = _parse_task_xml(xml)

        verbose = runner(["schtasks", "/query", "/tn", name, "/fo", "LIST", "/v"])
        vtext = verbose.stdout or ""
        state_m = re.search(r"Scheduled Task State:\s*(\S+)", vtext)
        last_m = re.search(r"Last Result:\s*(\S+)", vtext)
        next_m = re.search(r"Next Run Time:\s*([^\n\r]*)", vtext)
        # Localised headers fall back to the XML Enabled flag.
        rec["state"] = state_m.group(1).strip() if state_m else None
        rec["last_result"] = last_m.group(1).strip() if last_m else None
        rec["next_run_time"] = next_m.group(1).strip() if next_m else None
        if rec["state"] is None:
            rec["state"] = "Enabled" if rec["definition"]["enabled_xml"] else "Disabled"
    except Exception as exc:
        rec["exists"] = False
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec


def collect_tasks(names, runner=None) -> dict:
    return {name: query_scheduled_task(name, runner=runner) for name in names}


# --------------------------------------------------------------------------- #
# Credentials (presence only)
# --------------------------------------------------------------------------- #

# Presence routing by the worker's *declared* adapter file. A worker with a
# dedicated key-access helper must not be probed through the generic adapter
# (which has no mapping for it and would report a false negative for a worker
# that is in fact configured — e.g. DeepSeek, which this very system uses).
_DEDICATED_KEYACCESS = {
    "google": "gemini_keyaccess",
    "deepseek": "deepseek_keyaccess",
}


def _probe_worker_credential(wid: str, worker: dict) -> dict:
    rec = {"worker_id": wid, "provider": worker.get("provider"),
           "interface": worker.get("interface"),
           "routable": bool(worker.get("routable"))}
    if worker.get("interface") != "api":
        rec["credential_present"] = None
        rec["note"] = "non-API interface; credential handled by its own CLI/adapter"
        return rec
    module_name = _DEDICATED_KEYACCESS.get(worker.get("provider"))
    try:
        if module_name:
            import importlib
            ka = importlib.import_module(module_name)
            present = bool(ka.credential_manager_entry_present() or ka.env_var_present())
            rec["credential_present"] = present
            rec["auth_source"] = ("credential-manager" if ka.credential_manager_entry_present()
                                  else ("env" if ka.env_var_present() else "none"))
            rec["resolver"] = f"{module_name}.credential_manager_entry_present/env_var_present"
        else:
            import generic_openai_adapter as goa
            adapter = goa.get_adapter(wid)
            key, source = adapter._resolve_auth()
            rec["credential_present"] = key is not None
            rec["auth_source"] = source
            rec["resolver"] = "generic_openai_adapter._resolve_auth()"
            del key
    except Exception as exc:
        rec["credential_present"] = None
        rec["note"] = f"presence probe unavailable: {type(exc).__name__}"
    return rec


def credential_status(repo_root: Path = REPO_ROOT, runtime_root: Path = RUNTIME_ROOT) -> dict:
    """Presence-only credential report, reusing the live E3 auth resolvers."""
    detail: dict = {"workers": [], "provider_calls_spent": 0, "network_calls_spent": 0}
    try:
        for p in (str(repo_root / "exec-brain"), str(runtime_root)):
            if p not in sys.path:
                sys.path.insert(0, p)
        from worker_registry import WorkerRegistry

        present, absent = [], []
        for wid, worker in WorkerRegistry().get_all_workers().items():
            rec = _probe_worker_credential(wid, worker)
            if rec.get("credential_present") is False:
                absent.append(wid)
            elif rec.get("credential_present") is True:
                present.append(wid)
            detail["workers"].append(rec)
        detail["configured_api_workers"] = present
        detail["credential_missing_api_workers"] = absent
        detail["configured_count"] = len(present)
        detail["missing_count"] = len(absent)
        detail["status"] = "PASS" if not absent else "ATTENTION"
    except Exception as exc:
        detail["status"] = "UNKNOWN"
        detail["error"] = f"{type(exc).__name__}: {exc}"
    return detail


# --------------------------------------------------------------------------- #
# Brief availability
# --------------------------------------------------------------------------- #

def file_freshness(path: Path, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    path = Path(path)
    rec = {"path": str(path), "exists": path.exists()}
    if rec["exists"]:
        st = path.stat()
        rec["size_bytes"] = st.st_size
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        rec["modified_utc"] = mtime.replace(microsecond=0).isoformat()
        rec["age_hours"] = round((now - mtime).total_seconds() / 3600.0, 2)
        rec["stale"] = rec["age_hours"] > 30.0
    return rec


def resource_brief_status(repo_root: Path = REPO_ROOT, runtime_root: Path = RUNTIME_ROOT) -> dict:
    """Availability of the E2 Daily Resource Brief (governor state derived)."""
    rec: dict = {"artifact": "E2 Daily Resource Brief", "source": "governor.db"}
    try:
        import governor  # runtime module
        con = governor.connect_gov()
        try:
            count = con.execute("SELECT COUNT(*) FROM daily_brief_log").fetchone()[0]
            rec["briefs_logged"] = count
            rec["generated"] = count > 0
            # Validate a brief renders from *real* governor state.
            text = governor.generate_brief(con)
            rec["renders"] = bool(text and len(text) > 100)
            rec["unknown_preserved"] = "unknown" in text.lower() or "UNKNOWN" in text
        finally:
            con.close()
        rec["status"] = "PASS" if rec.get("renders") else "FAIL"
    except Exception as exc:
        rec["status"] = "UNKNOWN"
        rec["error"] = f"{type(exc).__name__}: {exc}"
    rec["published_latest"] = file_freshness(repo_root / "resource-status" / "latest-brief.md")
    return rec


def career_brief_status(repo_root: Path = REPO_ROOT) -> dict:
    latest = repo_root / "runtime" / "career-ops" / "daily-brief" / "latest.json"
    rec = {"artifact": "Career Daily Brief", **file_freshness(latest)}
    rec["status"] = "PASS" if rec["exists"] and not rec.get("stale") else (
        "ATTENTION" if rec["exists"] else "UNKNOWN")
    return rec


def log_status(log_paths=None) -> list:
    log_paths = log_paths if log_paths is not None else LOG_TARGETS
    out = []
    for p in log_paths:
        p = Path(p)
        rec = {"path": str(p), "exists": p.exists()}
        if rec["exists"]:
            rec["size_bytes"] = p.stat().st_size
            rec["rotation_configured"] = False  # nothing rotates these today
        out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# E4 recorded provider content-side stop pressure (observation only)
# --------------------------------------------------------------------------- #
#
# The health snapshot / Morning Chief Brief measured capacity and brief
# availability but not *content-side* provider pressure: a provider (or
# provider/model pair) that repeatedly withholds content while still consuming
# prompt tokens looked healthy. This surface carries the E4 resource-continuity
# pressure view (``resource_monitor.build_content_stop_pressure_view``) into the
# owner's operator surfaces.
#
# Rules, identical to the E4 view it delegates to:
# * read-only — the orchestration store is opened ``mode=ro`` and nothing writes;
# * observation only — a flagged group is information for the owner and an
#   explicit E4/owner decision, never an automatic worker swap, re-dispatch,
#   failover, retry or safe-mode entry;
# * no provider/network call and 0 real provider calls — every value comes from
#   rows/artifacts already recorded on disk;
# * no fabricated rate — a rate is reported with its sample size and is
#   ``unknown`` when no classified attempt was recorded (never a rate from zero
#   attempts, and an unclassified sample is never reported as clear).

PRESSURE_CHECK = "resource.content_stop_pressure"
PRESSURE_ESCALATION_CATEGORY = "provider_content_stop_pressure"
PRESSURE_STATUS_UNKNOWN = "UNKNOWN"
PRESSURE_STATUS_ATTENTION = "ATTENTION"
PRESSURE_STATUS_PASS = "PASS"

PRESSURE_DECISION_NOTE = (
    "observation only — no automatic worker swap, re-dispatch, failover, retry "
    "or safe-mode entry; any failover or re-request stays an explicit E4/owner "
    "decision")

# Already-recorded provider series artifacts, consumed verbatim and never
# re-run. Declared so the owner sees the bounded recorded measurement without
# passing a flag; a path that is absent is recorded as a source error and is
# never replaced by an invented sample.
RECORDED_PRESSURE_SERIES = [
    REPO_ROOT / "audits" / "evidence"
    / "2026-09-24T01-44-32Z-e3-google-image-repeat-series" / "observations.json",
]


def _orchestration_store_path(db_paths=None) -> "Path | None":
    """The declared orchestration store path, or ``None`` when not declared."""
    for label, path in (db_paths if db_paths is not None else OPERATIONAL_DATABASES):
        if label == "e3-orchestration":
            return Path(path)
    return None


def _pressure_group_record(source: str, group: dict) -> dict:
    """A flat, operator-readable record of one pressure group (nothing inferred)."""
    return {
        "source": source,
        "worker_id": group.get("worker_id"),
        "provider": group.get("provider"),
        "model": group.get("model"),
        "attempts_observed": group.get("attempts_observed"),
        "attempts_classified": group.get("attempts_classified"),
        "attempts_unclassified": group.get("attempts_unclassified"),
        "content_stops_observed": group.get("content_stops_observed"),
        "sample_size": group.get("sample_size"),
        "content_stop_rate": group.get("content_stop_rate"),
        "content_stop_rate_basis": group.get("content_stop_rate_basis"),
        "content_withheld_at_measurable_rate":
            group.get("content_withheld_at_measurable_rate"),
        "last_finish_reason": group.get("last_finish_reason"),
        "last_stop_at": group.get("last_stop_at"),
        "status": group.get("status"),
    }


def content_stop_pressure_status(*, db_paths=None, pressure_con=None,
                                 series_paths=None) -> dict:
    """Recorded provider content-side stop pressure for the operator surfaces.

    Read-only and observation-only. ``pressure_con`` injects an already-open
    orchestration-store connection (tests); otherwise the declared
    ``e3-orchestration`` database is opened ``mode=ro``. ``series_paths``
    optionally adds recorded provider series artifacts; ``None`` means the
    declared :data:`RECORDED_PRESSURE_SERIES`, ``()`` means none.

    Status vocabulary: ``ATTENTION`` when a provider/model pair's recorded
    content-side stop rate crosses the bounded threshold, ``UNKNOWN`` when no
    classified dispatch attempt was recorded for at least one group (reported
    as unknown, never as clear), ``PASS`` otherwise. Nothing is ever fabricated:
    an unreadable store, a missing series artifact or an unimportable E4 module
    yields ``UNKNOWN`` with an explicit reason.
    """
    rec: dict = {
        "artifact": "E4 provider content-side stop pressure (recorded evidence)",
        "source": "orchestration_store.performance_evidence",
        "observation_only": True,
        "provider_calls_spent": 0,
        "network_calls_spent": 0,
        "live_state_modified": False,
        "decision": PRESSURE_DECISION_NOTE,
        "status": PRESSURE_STATUS_UNKNOWN,
        "detected": None,
        "groups": [],
        "rate_threshold": None,
        "minimum_sample": None,
        "source_errors": [],
        "detail": None,
        "reason": None,
    }
    try:
        from resource_monitor import build_content_stop_pressure_view
    except Exception as exc:  # noqa: BLE001 — report, never invent a view
        rec["reason"] = (f"E4 resource-continuity module not importable "
                         f"({type(exc).__name__}) — pressure unknown, not clear")
        rec["detail"] = rec["reason"]
        return rec

    paths = list(RECORDED_PRESSURE_SERIES if series_paths is None else series_paths)

    con = pressure_con
    owned = False
    if con is None:
        store = _orchestration_store_path(db_paths)
        if store is None:
            rec["reason"] = ("no orchestration store declared in the state set — "
                            "pressure unknown, not clear")
            rec["detail"] = rec["reason"]
            return rec
        if not store.exists():
            rec["reason"] = (f"orchestration store absent ({store.name}) — "
                            "pressure unknown, not clear")
            rec["detail"] = rec["reason"]
            return rec
        try:
            con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
            owned = True
        except Exception as exc:  # noqa: BLE001
            rec["reason"] = (f"orchestration store unreadable "
                            f"({type(exc).__name__}) — pressure unknown, not clear")
            rec["detail"] = rec["reason"]
            return rec

    try:
        view = build_content_stop_pressure_view(con, series_paths=paths)
    except Exception as exc:  # noqa: BLE001
        rec["reason"] = (f"pressure view unavailable ({type(exc).__name__}: {exc}) "
                        "— pressure unknown, not clear")
        rec["detail"] = rec["reason"]
        return rec
    finally:
        if owned:
            con.close()

    groups = []
    for source in view.get("sources") or []:
        for group in source.get("groups") or []:
            groups.append(_pressure_group_record(source.get("source"), group))

    rec["rate_threshold"] = view.get("rate_threshold")
    rec["minimum_sample"] = view.get("minimum_sample")
    rec["detected"] = view.get("content_stop_pressure_detected")
    rec["groups"] = groups
    rec["source_errors"] = [str(e) for e in (view.get("source_errors") or [])]

    flagged = [g for g in groups
               if g["content_withheld_at_measurable_rate"] is True]
    unclassified = [g for g in groups
                    if g["content_withheld_at_measurable_rate"] is None]
    below_bound = [g for g in groups
                   if g["content_stops_observed"]
                   and g["content_withheld_at_measurable_rate"] is False]

    if flagged:
        rec["status"] = PRESSURE_STATUS_ATTENTION
        rec["detail"] = "; ".join(
            f"{g['provider']}/{g['model']} recorded content-side stop rate "
            f"{g['content_stop_rate']:.3f} at sample size {g['sample_size']} "
            f"(threshold {rec['rate_threshold']}, minimum sample "
            f"{rec['minimum_sample']}); last finishReason "
            f"{g['last_finish_reason'] or 'none recorded'}; "
            f"{PRESSURE_DECISION_NOTE}"
            for g in flagged)
    elif not groups:
        rec["reason"] = ("no recorded dispatch-attempt row was readable — "
                        "pressure unknown, not clear")
        rec["detail"] = rec["reason"]
        return rec
    elif unclassified:
        rec["reason"] = (
            f"{len(unclassified)} worker/provider group(s) have no classified "
            "dispatch attempt recorded (pre-classification rows) — reported as "
            "unknown, not clear; no rate is reported from zero attempts")
        rec["detail"] = rec["reason"]
        return rec
    else:
        rec["status"] = PRESSURE_STATUS_PASS
        classified = sum(g["attempts_classified"] or 0 for g in groups)
        detail = (f"no worker/provider pair crossed the bounded content-side stop "
                  f"threshold (threshold {rec['rate_threshold']}, minimum sample "
                  f"{rec['minimum_sample']}) over {classified} classified "
                  f"recorded dispatch attempts")
        if below_bound:
            detail += ("; stops recorded below the bound: " + ", ".join(
                f"{g['provider']}/{g['model']} {g['content_stops_observed']}/"
                f"{g['sample_size']}" for g in below_bound))
        rec["detail"] = detail
    return rec


def pressure_escalations(pressure: dict) -> list:
    """Warning-grade observations for a crossing pressure group (observation only)."""
    items = []
    for group in pressure.get("groups") or []:
        if group["content_withheld_at_measurable_rate"] is not True:
            continue
        items.append({
            "severity": "warning",
            "category": PRESSURE_ESCALATION_CATEGORY,
            "item": (
                "provider content-side stop pressure (recorded evidence, "
                f"observation only): {group['provider']}/{group['model']} "
                f"[worker {group['worker_id']}] stop rate "
                f"{group['content_stop_rate']:.3f} at sample size "
                f"{group['sample_size']} classified recorded dispatch attempts "
                f"(bounds: rate >= {pressure.get('rate_threshold')} AND sample >= "
                f"{pressure.get('minimum_sample')}); last finishReason "
                f"{group['last_finish_reason'] or 'none recorded'}. "
                f"{PRESSURE_DECISION_NOTE}"),
        })
    return items


# --------------------------------------------------------------------------- #
# Health snapshot
# --------------------------------------------------------------------------- #

def build_health_snapshot(*, repo_root: Path = REPO_ROOT,
                          task_runner=None,
                          db_paths=None,
                          queue_root=None,
                          log_paths=None,
                          check_tasks: bool = True,
                          pressure_con=None,
                          pressure_series=None) -> dict:
    started = utc_now()
    dbs = db_status(db_paths)
    queue = queue_summary(queue_root)
    creds = credential_status(repo_root=repo_root)
    res_brief = resource_brief_status(repo_root=repo_root)
    career = career_brief_status(repo_root=repo_root)
    logs = log_status(log_paths)
    pressure = content_stop_pressure_status(
        db_paths=db_paths, pressure_con=pressure_con,
        series_paths=pressure_series)


    tasks = {}
    if check_tasks:
        tasks = collect_tasks(CHIEF_TASKS + LEGACY_TASKS, runner=task_runner)

    checks = []
    for d in dbs:
        checks.append({"check": f"db.{d['label']}", "status": d["status"],
                       "detail": d.get("integrity_check", d.get("reason"))})
    checks.append({"check": "queue.valid", "status": "PASS",
                   "detail": "0 invalid task envelopes"
                   if not any(t.get("invalid") for s in QUEUE_DIRS
                              for t in queue[s]["tasks"]) else "invalid envelopes present"})
    checks.append({"check": "credentials.presence", "status": creds.get("status", "UNKNOWN"),
                   "detail": f"configured={creds.get('configured_count')} "
                             f"missing={creds.get('missing_count')}"})
    checks.append({"check": "brief.resource", "status": res_brief.get("status", "UNKNOWN"),
                   "detail": res_brief.get("error") or "renders from live governor state"})
    checks.append({"check": "brief.career", "status": career.get("status", "UNKNOWN"),
                   "detail": f"latest.json exists={career.get('exists')}"})
    checks.append({"check": PRESSURE_CHECK,
                   "status": pressure.get("status", PRESSURE_STATUS_UNKNOWN),
                   "detail": pressure.get("detail")})
    if check_tasks:
        missing = [n for n, t in tasks.items() if not t.get("exists")]
        checks.append({"check": "tasks.present", "status": "PASS" if not missing else "FAIL",
                       "detail": f"{len(CHIEF_TASKS)} chief tasks; "
                                 f"missing={missing or 'none'}"})

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    attention = sum(1 for c in checks if c["status"] == "ATTENTION")
    unknown = sum(1 for c in checks if c["status"] == "UNKNOWN")

    escalations = []
    for d in dbs:
        if d["status"] == "FAIL":
            escalations.append({"severity": "critical", "category": "integrity",
                                "item": f"database {d['label']} failed integrity/missing"})
    blocked = queue.get("blocked", {}).get("count", 0)
    if blocked:
        cats = sorted({t.get("blocker_category") or "unknown"
                       for t in queue["blocked"]["tasks"]})
        escalations.append({"severity": "info", "category": "queue",
                            "item": f"{blocked} blocked queue task(s): categories={cats}"})
    if creds.get("missing_count"):
        escalations.append({"severity": "owner_action", "category": "credentials",
                            "item": f"{creds['missing_count']} provider credential(s) "
                                    f"absent — owner action (provider keys)"})
    if res_brief.get("status") == "FAIL":
        escalations.append({"severity": "warning", "category": "resource_brief",
                            "item": "E2 Daily Resource Brief did not render"})
    if career.get("status") == "UNKNOWN":
        escalations.append({"severity": "warning", "category": "career_brief",
                            "item": "Career Daily Brief artifact absent"})
    # Provider content-side stop pressure: warning-grade observation only. It
    # never triggers an automatic swap/re-dispatch/failover/retry/safe-mode entry.
    escalations.extend(pressure_escalations(pressure))
    if check_tasks:
        for n, t in tasks.items():
            if not t.get("exists"):
                escalations.append({"severity": "warning", "category": "scheduler",
                                    "item": f"scheduled task missing: {n}"})

    return {
        "artifact": "operational health snapshot",
        "run_started_utc": started,
        "run_finished_utc": utc_now(),
        "repository": str(repo_root),
        "code_sha": git_sha(repo_root),
        "host": {"platform": sys.platform, "python_version": sys.version.split()[0]},
        "provider_calls_spent": 0,
        "network_calls_spent": 0,
        "live_state_modified": False,
        "checks": checks,
        "fail_count": fail_count,
        "attention_count": attention,
        "unknown_count": unknown,
        "verdict": "FAIL" if fail_count else ("ATTENTION" if attention or blocked else "PASS"),
        "escalations": escalations,
        "databases": dbs,
        "queue": queue,
        "credentials": creds,
        "resource_brief": res_brief,
        "content_stop_pressure": pressure,
        "career_brief": career,
        "logs": logs,
        "scheduled_tasks": tasks,
    }


def render_pressure_lines(pressure: "dict | None", prefix: str = "  - ") -> list:
    """Operator lines for the recorded content-side stop pressure (observation only).

    A rate is never printed without its sample size, and a group with no
    classified attempt is printed as ``unknown`` rather than as clear.
    """
    p = pressure or {}
    lines = [f"{prefix}Status: {p.get('status')} — {p.get('detail')}"]
    for g in p.get("groups") or []:
        rate = g.get("content_stop_rate")
        rate_text = ("unknown (sample size 0 — no classified attempt recorded; no "
                     "rate is reported from zero attempts)"
                     if rate is None else
                     f"{rate:.3f} (sample size {g.get('sample_size')} classified "
                     f"attempts; {g.get('content_stop_rate_basis')})")
        flag = g.get("content_withheld_at_measurable_rate")
        flag_text = "unknown" if flag is None else ("yes" if flag else "no")
        lines.append(
            f"{prefix}  {g.get('source')} {g.get('provider')}/{g.get('model')} "
            f"[worker {g.get('worker_id')}]: attempts observed "
            f"{g.get('attempts_observed')} ({g.get('attempts_classified')} classified, "
            f"{g.get('attempts_unclassified')} without the content-stop ledger), "
            f"content-side stops observed {g.get('content_stops_observed')}, stop rate "
            f"{rate_text}, last finishReason "
            f"{g.get('last_finish_reason') or 'none recorded'}, last stop recorded at "
            f"{g.get('last_stop_at') or 'none recorded'}, content withheld at a "
            f"measurable rate: {flag_text} (status {g.get('status')})")
    for err in p.get("source_errors") or []:
        lines.append(f"{prefix}  source error (recorded evidence only): {err}")
    lines.append(f"{prefix}{PRESSURE_DECISION_NOTE}")
    return lines


def render_health_markdown(report: dict) -> str:
    lines = [
        "# Operational health snapshot",
        "",
        f"- Run (UTC): {report['run_started_utc']} -> {report['run_finished_utc']}",
        f"- Code SHA: `{report['code_sha']}`",
        f"- Verdict: **{report['verdict']}** "
        f"(fail={report['fail_count']}, attention={report['attention_count']}, "
        f"unknown={report['unknown_count']})",
        f"- Live state modified: {report['live_state_modified']}",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for c in report["checks"]:
        detail = str(c.get("detail") or "").replace("|", "\\|")
        lines.append(f"| {c['check']} | {c['status']} | {detail} |")
    lines += ["", "## Queue", ""]
    for state in ("pending", "running", "completed", "blocked"):
        q = report["queue"].get(state, {})
        lines.append(f"- {state}: {q.get('count', 0)}")
    lines += ["", "## Escalations", ""]
    if report["escalations"]:
        for e in report["escalations"]:
            lines.append(f"- [{e['severity']}/{e['category']}] {e['item']}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Provider content-side stop pressure (recorded evidence, observation only)",
        "",
    ]
    lines += render_pressure_lines(report.get("content_stop_pressure"),
                                   prefix="- ")
    lines += [
        "",
        "## Safety properties",
        "",
        "- read-only against live state and databases",
        "- no provider/network call; no credential value read (presence + store only)",
        "- does not change scheduled tasks or services",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Owner actions
# --------------------------------------------------------------------------- #

_ACTION_RE = re.compile(r"^###\s+(\d+)\.\s+(.*)$")


def parse_owner_actions(path: Path = OWNER_ACTIONS_FILE) -> list:
    """Parse the owner-action TODO into structured items (title + status line)."""
    path = Path(path)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    items = []
    current = None
    for line in text:
        stripped = line.strip()
        m = _ACTION_RE.match(stripped)
        if m:
            if current:
                items.append(current)
            current = {"number": int(m.group(1)), "title": m.group(2).strip().rstrip("  "),
                       "status": None}
            continue
        if current is not None and current["status"] is None:
            sm = re.search(r"\*\*Status:\*\*\s*(.+)", line)
            if sm:
                current["status"] = sm.group(1).strip()
            continue
        # A wrapped status line (no blank line and no new block yet) continues
        # the status text. Headings, bold fields and bullets end it.
        if (current is not None and current["status"] is not None and stripped
                and not stripped.startswith(("#", "**", "-"))):
            current["status"] = f"{current['status']} {stripped}"
    if current:
        items.append(current)
    return items


# --------------------------------------------------------------------------- #
# Morning Chief Brief
# --------------------------------------------------------------------------- #

def build_morning_brief(*, repo_root: Path = REPO_ROOT,
                        task_runner=None,
                        db_paths=None,
                        queue_root=None,
                        log_paths=None,
                        check_tasks: bool = True,
                        owner_actions_file: Path = OWNER_ACTIONS_FILE,
                        pressure_con=None,
                        pressure_series=None) -> dict:
    health = build_health_snapshot(repo_root=repo_root, task_runner=task_runner,
                                   db_paths=db_paths, queue_root=queue_root,
                                   log_paths=log_paths, check_tasks=check_tasks,
                                   pressure_con=pressure_con,
                                   pressure_series=pressure_series)
    queue = health["queue"]
    owner_actions = parse_owner_actions(owner_actions_file)

    active = [t["task_id"] for t in queue.get("running", {}).get("tasks", [])] + \
             [t["task_id"] for t in queue.get("pending", {}).get("tasks", [])]
    blocked = queue.get("blocked", {}).get("tasks", [])

    # Failure escalation: the exact items the owner/next run must act on.
    escalations = list(health["escalations"])
    for e in escalations:
        e.setdefault("owner_action", e["severity"] in ("critical", "owner_action", "warning"))

    return {
        "artifact": "Morning Chief Brief",
        "generated_utc": utc_now(),
        "code_sha": health["code_sha"],
        "verdict": health["verdict"],
        "resource_status": {
            "brief_status": health["resource_brief"].get("status"),
            "briefs_logged": health["resource_brief"].get("briefs_logged"),
            "renders": health["resource_brief"].get("renders"),
            "unknown_preserved": health["resource_brief"].get("unknown_preserved"),
            # Recorded provider content-side stop pressure next to the E2
            # resource status: observation/warning only, never an automatic action.
            "content_stop_pressure": {
                "status": health["content_stop_pressure"].get("status"),
                "detected": health["content_stop_pressure"].get("detected"),
                "detail": health["content_stop_pressure"].get("detail"),
                "groups": health["content_stop_pressure"].get("groups"),
                "decision": health["content_stop_pressure"].get("decision"),
            },
        },
        "system_health": {
            "verdict": health["verdict"],
            "fail_count": health["fail_count"],
            "attention_count": health["attention_count"],
            "unknown_count": health["unknown_count"],
            "databases": {d["label"]: d["status"] for d in health["databases"]},
            "logs": health["logs"],
        },
        "queue": {
            "active": active,
            "active_count": len(active),
            "blocked": blocked,
            "blocked_count": len(blocked),
            "counts": {s: queue.get(s, {}).get("count", 0)
                       for s in ("pending", "running", "completed", "blocked")},
        },
        "career_brief": health["career_brief"],
        "owner_actions": owner_actions,
        "escalations": escalations,
        "provider_calls_spent": 0,
        "network_calls_spent": 0,
        "live_state_modified": False,
    }


def render_morning_markdown(brief: dict) -> str:
    lines = [
        "# Morning Chief Brief",
        "",
        f"- Generated (UTC): {brief['generated_utc']}",
        f"- Code SHA: `{brief['code_sha']}`",
        f"- Overall verdict: **{brief['verdict']}**",
        "",
        "## Resource status",
        "",
        f"- E2 Daily Resource Brief: {brief['resource_status'].get('brief_status')} "
        f"(renders={brief['resource_status'].get('renders')}, "
        f"logged={brief['resource_status'].get('briefs_logged')})",
        "",
    ]
    lines += render_pressure_lines(
        brief["resource_status"].get("content_stop_pressure"), prefix="- ")
    lines += [
        "",
        "## System health",
        "",
        f"- Verdict: {brief['system_health']['verdict']} "
        f"(fail={brief['system_health']['fail_count']}, "
        f"attention={brief['system_health']['attention_count']}, "
        f"unknown={brief['system_health']['unknown_count']})",
    ]
    for label, status in sorted(brief["system_health"]["databases"].items()):
        lines.append(f"  - db {label}: {status}")
    lines += ["", "## Queue work", "",
              f"- Active: {brief['queue']['active_count']}"]
    for t in brief["queue"]["active"]:
        lines.append(f"  - {t}")
    lines += [f"- Blocked: {brief['queue']['blocked_count']}"]
    for t in brief["queue"]["blocked"]:
        lines.append(f"  - {t.get('task_id')} [{t.get('blocker_category')}]")
    lines += ["", "## Career brief availability", "",
              f"- {brief['career_brief'].get('status')} — "
              f"exists={brief['career_brief'].get('exists')}, "
              f"age_hours={brief['career_brief'].get('age_hours')}"]
    lines += ["", "## Exact owner actions", ""]
    if brief["owner_actions"]:
        for a in brief["owner_actions"]:
            lines.append(f"{a['number']}. {a['title']} — {a.get('status') or 'status unknown'}")
    else:
        lines.append("- none recorded")
    lines += ["", "## Failure escalation", ""]
    if brief["escalations"]:
        for e in brief["escalations"]:
            lines.append(f"- [{e['category']}] {e['item']}")
    else:
        lines.append("- none")
    lines += ["", "## Safety properties", "",
              "- aggregate facts only; no raw database contents",
              "- no provider/network call; no credential value read",
              "", ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Operational backup
# --------------------------------------------------------------------------- #

def _snapshot_sqlite(src: Path, dst: Path) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    return {"integrity_check": integrity, "size_bytes": dst.stat().st_size,
            "sha256": sha256_file(dst)}


def run_operational_backup(*, snapshot_root: Path = None, db_paths=None,
                           json_artifacts=None, keep: int = DEFAULT_SNAPSHOT_KEEP,
                           dry_run: bool = False) -> dict:
    """Snapshot the declared state set, verify, and prune to the retention count."""
    db_paths = db_paths if db_paths is not None else OPERATIONAL_DATABASES
    json_artifacts = json_artifacts if json_artifacts is not None else OPERATIONAL_JSON_ARTIFACTS
    snapshot_root = Path(snapshot_root) if snapshot_root else DEFAULT_BACKUP_ROOT

    stamp = _stamp()
    this_snapshot = snapshot_root / f"snapshot-{stamp}"
    report: dict = {
        "artifact": "operational backup",
        "started_utc": utc_now(),
        "snapshot_root": str(snapshot_root),
        "snapshot_dir": str(this_snapshot),
        "dry_run": bool(dry_run),
        "retention_keep": keep,
        "artifacts": [],
        "pruned": [],
        "live_state_modified": False,
        "network_calls_spent": 0,
        "provider_calls_spent": 0,
    }
    failures = []
    for label, src in db_paths:
        rec = {"label": label, "kind": "sqlite", "source": str(src)}
        if not Path(src).exists():
            rec.update(status="FAIL", reason="source missing")
            failures.append(label)
            report["artifacts"].append(rec)
            continue
        if dry_run:
            rec.update(status="PLANNED", plan="sqlite online backup + integrity_check")
            report["artifacts"].append(rec)
            continue
        try:
            rec["snapshot"] = _snapshot_sqlite(Path(src), this_snapshot / f"{label}.db")
            rec["status"] = "PASS" if rec["snapshot"]["integrity_check"] == "ok" else "FAIL"
            if rec["status"] == "FAIL":
                failures.append(label)
        except Exception as exc:
            rec.update(status="FAIL", reason=f"{type(exc).__name__}: {exc}")
            failures.append(label)
        report["artifacts"].append(rec)

    for label, src in json_artifacts:
        rec = {"label": label, "kind": "json", "source": str(src)}
        if not Path(src).exists():
            rec.update(status="FAIL", reason="source missing")
            failures.append(label)
            report["artifacts"].append(rec)
            continue
        if dry_run:
            rec.update(status="PLANNED", plan="byte copy + sha256")
            report["artifacts"].append(rec)
            continue
        try:
            dst = this_snapshot / f"{label}.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            rec["snapshot"] = {"sha256": sha256_file(dst), "size_bytes": dst.stat().st_size}
            rec["status"] = "PASS"
        except Exception as exc:
            rec.update(status="FAIL", reason=f"{type(exc).__name__}: {exc}")
            failures.append(label)
        report["artifacts"].append(rec)

    if not dry_run and not failures:
        report["pruned"] = prune_snapshots(snapshot_root, keep)

    report["failure_labels"] = failures
    report["status"] = "PASS" if not failures else "FAIL"
    report["finished_utc"] = utc_now()
    return report


def prune_snapshots(snapshot_root: Path, keep: int) -> list:
    """Remove the oldest ``snapshot-*`` directories beyond ``keep``.

    Scoped strictly to directories matching the operational snapshot prefix under
    the given root; it can never touch a live path or an unrelated directory.
    """
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.exists():
        return []
    snapshots = sorted(p for p in snapshot_root.iterdir()
                       if p.is_dir() and p.name.startswith("snapshot-"))
    to_remove = snapshots[:-keep] if keep > 0 else snapshots
    removed = []
    for p in to_remove:
        shutil.rmtree(p, ignore_errors=True)
        removed.append(p.name)
    return removed


def rotate_logs(log_paths=None, *, keep: int = DEFAULT_LOG_KEEP,
                max_bytes: int = DEFAULT_LOG_MAX_BYTES, apply: bool = False) -> list:
    """Archive a log once it passes ``max_bytes``; keep ``keep`` archives.

    Non-destructive: the live log is copied to an archive and only truncated when
    the file can be opened for writing. A locked/held log (a running service) is
    recorded as ``skipped_locked`` rather than forced. ``apply=False`` is a plan.
    """
    log_paths = log_paths if log_paths is not None else LOG_TARGETS
    results = []
    for lp in log_paths:
        lp = Path(lp)
        rec = {"path": str(lp), "exists": lp.exists()}
        if not rec["exists"]:
            rec["action"] = "skip_missing"
            results.append(rec)
            continue
        size = lp.stat().st_size
        rec["size_bytes"] = size
        if size <= max_bytes:
            rec["action"] = "no_rotation_needed"
            results.append(rec)
            continue
        if not apply:
            rec["action"] = "would_rotate"
            results.append(rec)
            continue
        archive = lp.with_suffix(lp.suffix + f".{_stamp()}.1")
        try:
            shutil.copy2(lp, archive)
            try:
                with open(lp, "r+b") as fh:
                    fh.truncate(0)
                rec["action"] = "rotated"
                rec["archive"] = str(archive)
            except Exception as exc:
                rec["action"] = "skipped_locked"
                rec["reason"] = f"{type(exc).__name__}: {exc}"
                if archive.exists():
                    archive.unlink(missing_ok=True)
        except Exception as exc:
            rec["action"] = "error"
            rec["reason"] = f"{type(exc).__name__}: {exc}"
        results.append(rec)

    # Retention over the archives this routine can have created.
    if apply:
        for lp in log_paths:
            lp = Path(lp)
            archives = sorted(lp.parent.glob(lp.name + ".*.1"))
            for old in (archives[:-keep] if keep > 0 else archives):
                old.unlink(missing_ok=True)
    return results


# --------------------------------------------------------------------------- #
# Persistence validation
# --------------------------------------------------------------------------- #

def analyse_persistence(tasks: dict) -> dict:
    """Verdicts + owner checklist for restart/boot persistence. Records only."""
    verdicts = {}
    checklist = []
    for name in CHIEF_TASKS + LEGACY_TASKS:
        rec = tasks.get(name) or {}
        if not rec.get("exists"):
            verdicts[name] = {"exists": False,
                              "survives_boot": "unknown",
                              "reason": "task not found"}
            if name in CHIEF_TASKS:
                checklist.append({
                    "task": name, "action": "investigate",
                    "detail": "task is not registered; re-import from deployments/service-definitions/"})
            continue
        d = rec.get("definition", {})
        triggers = set(d.get("triggers") or [])
        has_boot_trigger = bool(triggers & {"logon", "boot"})
        start_when_available = bool(d.get("start_when_available"))
        survives = "yes" if (has_boot_trigger or start_when_available) else "no"
        reason_bits = []
        if has_boot_trigger:
            reason_bits.append("has boot/logon trigger")
        if start_when_available:
            reason_bits.append("StartWhenAvailable=true")
        if not reason_bits:
            reason_bits.append("no boot/logon trigger and StartWhenAvailable not set")
        verdicts[name] = {
            "exists": True,
            "state": rec.get("state"),
            "triggers": sorted(triggers),
            "logon_type": d.get("logon_type"),
            "start_when_available": start_when_available,
            "restart_on_failure": bool(d.get("restart_on_failure")),
            "disallow_on_batteries": bool(d.get("disallow_on_batteries")),
            "last_result": rec.get("last_result"),
            "next_run_time": rec.get("next_run_time"),
            "survives_boot": survives,
            "reason": "; ".join(reason_bits),
        }
        if name in CHIEF_TASKS:
            if d.get("logon_type") == "InteractiveToken":
                checklist.append({
                    "task": name, "action": "keep_signed_in",
                    "detail": "runs under the interactive user token; it does not run for a "
                              "signed-out user (owner-side precondition for unattended operation)"})
            if d.get("disallow_on_batteries"):
                checklist.append({
                    "task": name, "action": "battery_gating",
                    "detail": "DisallowStartIfOnBatteries=true — will not run on battery; "
                              "owner-aware re-import needed for laptop-primary topology"})
            if survives == "no":
                checklist.append({
                    "task": name, "action": "add_logon_trigger",
                    "detail": "no boot/logon trigger and StartWhenAvailable not set — "
                              "persistence after reboot is unverified; add a logon trigger "
                              "(small, reversible schtasks /Create /XML re-import)"})
    return {"verdicts": verdicts, "owner_checklist": checklist,
            "unverified_after_reboot": [n for n, v in verdicts.items()
                                        if v.get("survives_boot") == "no"]}


def build_persistence_report(*, task_runner=None) -> dict:
    tasks = collect_tasks(CHIEF_TASKS + LEGACY_TASKS, runner=task_runner)
    analysis = analyse_persistence(tasks)
    return {
        "artifact": "restart/boot persistence validation",
        "run_utc": utc_now(),
        "code_sha": git_sha(),
        "changed_tasks": [],
        "live_state_modified": False,
        "network_calls_spent": 0,
        "tasks": tasks,
        **analysis,
    }


def render_persistence_markdown(report: dict) -> str:
    lines = [
        "# Restart / boot persistence validation",
        "",
        f"- Run (UTC): {report['run_utc']}",
        f"- Live state modified: {report['live_state_modified']} (read-only)",
        "",
        "| Task | State | Triggers | StartWhenAvailable | survives boot |",
        "|---|---|---|---|---|",
    ]
    for name, v in report["verdicts"].items():
        lines.append(f"| {name} | {v.get('state')} | {','.join(v.get('triggers') or [])} | "
                     f"{v.get('start_when_available')} | {v.get('survives_boot')} |")
    lines += ["", "## Owner checklist items", ""]
    if report["owner_checklist"]:
        for c in report["owner_checklist"]:
            lines.append(f"- {c['task']} [{c['action']}]: {c['detail']}")
    else:
        lines.append("- none")
    lines += ["", "Recorded only — no scheduled task was created, modified, "
                  "started, stopped or deleted by this run.", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _write_report(out_dir: Path, name: str, report: dict, markdown_fn) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    if markdown_fn:
        (out_dir / f"{name}.md").write_text(markdown_fn(report), encoding="utf-8")
    return out_dir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("health-snapshot")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-tasks", action="store_true",
                   help="skip scheduled-task queries (sandbox/tests)")
    p.add_argument("--pressure-series", action="append", default=None,
                   metavar="OBSERVATIONS_JSON",
                   help="recorded provider series artifact(s) to include in the "
                        "read-only content-side stop pressure view (repeatable; "
                        "defaults to the declared recorded series)")

    p = sub.add_parser("morning-brief")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-tasks", action="store_true")
    p.add_argument("--pressure-series", action="append", default=None,
                   metavar="OBSERVATIONS_JSON",
                   help="recorded provider series artifact(s) to include in the "
                        "read-only content-side stop pressure view (repeatable; "
                        "defaults to the declared recorded series)")

    p = sub.add_parser("backup")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--snapshot-root", default=None)
    p.add_argument("--keep", type=int, default=DEFAULT_SNAPSHOT_KEEP)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rotate-logs", action="store_true",
                   help="also evaluate log rotation/retention (plan only unless --apply-logs)")
    p.add_argument("--apply-logs", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("validate-persistence")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    stamp = _stamp()

    if args.command == "health-snapshot":
        report = build_health_snapshot(check_tasks=not args.no_tasks,
                                       pressure_series=args.pressure_series)
        out_dir = Path(args.out_dir) if args.out_dir else (
            REPO_ROOT / "audits" / "evidence" / f"{stamp}-health-snapshot")
        _write_report(out_dir, "health_snapshot", report, render_health_markdown)
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(json.dumps({"evidence_dir": str(out_dir), "verdict": report["verdict"],
                              "fail_count": report["fail_count"],
                              "attention_count": report["attention_count"],
                              "escalations": report["escalations"]}, indent=2))
        return 0 if report["fail_count"] == 0 else 1

    if args.command == "morning-brief":
        brief = build_morning_brief(check_tasks=not args.no_tasks,
                                    pressure_series=args.pressure_series)
        out_dir = Path(args.out_dir) if args.out_dir else (
            REPO_ROOT / "runtime" / "chief" / "morning-brief")
        _write_report(out_dir, "latest", brief, render_morning_markdown)
        if args.json:
            print(json.dumps(brief, indent=2, default=str))
        else:
            print(json.dumps({"out_dir": str(out_dir), "verdict": brief["verdict"],
                              "active_count": brief["queue"]["active_count"],
                              "blocked_count": brief["queue"]["blocked_count"],
                              "owner_actions": len(brief["owner_actions"]),
                              "escalations": len(brief["escalations"])}, indent=2))
        return 0

    if args.command == "backup":
        snapshot_root = Path(args.snapshot_root) if args.snapshot_root else DEFAULT_BACKUP_ROOT
        report = run_operational_backup(snapshot_root=snapshot_root, keep=args.keep,
                                        dry_run=args.dry_run)
        if args.rotate_logs or args.apply_logs:
            report["log_rotation"] = rotate_logs(apply=args.apply_logs)
        out_dir = Path(args.out_dir) if args.out_dir else (
            REPO_ROOT / "audits" / "evidence" / f"{stamp}-operational-backup")
        _write_report(out_dir, "operational_backup", report, None)
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(json.dumps({"evidence_dir": str(out_dir), "status": report["status"],
                              "snapshot_dir": report["snapshot_dir"],
                              "failure_labels": report["failure_labels"],
                              "pruned": report["pruned"]}, indent=2))
        return 0 if report["status"] == "PASS" else 1

    if args.command == "validate-persistence":
        report = build_persistence_report()
        out_dir = Path(args.out_dir) if args.out_dir else (
            REPO_ROOT / "audits" / "evidence" / f"{stamp}-persistence-validation")
        _write_report(out_dir, "persistence", report, render_persistence_markdown)
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(json.dumps({"evidence_dir": str(out_dir),
                              "unverified_after_reboot": report["unverified_after_reboot"],
                              "owner_checklist_items": len(report["owner_checklist"])},
                             indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
