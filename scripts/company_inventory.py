#!/usr/bin/env python3
"""Chief Company Registry / system-inventory worker (roster A20).

Deterministic, zero-LLM, read-only. Reconciles the *actual* local machine
organisation against ``state/v1-agent-roster.md``:

* Windows scheduled tasks that belong to Mukund's digital organisation
* Hermes skills / hooks / cron (the management layer's own capability surface)
* remote-queue state counts (pending / running / blocked / completed)
* legacy donor systems and canonical career resources (existence only)
* the declared roster->work coverage map, so unmapped roster items and locally
  discovered owner-relevant services that are absent from the roster are both
  reported instead of silently omitted

It mutates nothing, reads no secret and prints no database content: only
existence, sizes, task state and declared mappings.

Usage::

    python scripts/company_inventory.py [--json OUT] [--repo ROOT]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_DEFAULT = Path(__file__).resolve().parent.parent

# Scheduled tasks owned by Mukund's digital organisation. Anything else on the
# machine is out of scope and is not reported.
OWNED_TASK_PREFIXES = ("Chief", "Hermes")

# Roster id -> the pending/running/completed work that covers it, or a state
# fact. Declared here on purpose: the reconciliation is auditable and a missing
# entry shows up as "unmapped" rather than as an implicit assumption.
ROSTER_COVERAGE = {
    "A01": {"state": "active", "evidence": "Hermes gateway + Discord live (gateway_state.json)"},
    "A02": {"state": "active", "evidence": "eb.py audit --verify PASS"},
    "A03": {"state": "active", "evidence": "eb.py gov-verify PASS"},
    "A04": {"state": "active", "evidence": "eb.py brief (deterministic daily resource brief)"},
    "A05": {"state": "built+evidenced", "evidence": "e3_planner.py; 21:32:41Z rehearsal"},
    "A06": {"state": "built+evidenced", "evidence": "e3_router.py + qualification_gate.py"},
    "A07": {"state": "built+tested", "evidence": "e3_context.py"},
    "A08": {"state": "built+tested", "evidence": "e3_permissions.py"},
    "A09": {"state": "built+evidenced", "evidence": "e3_team_assembly.py; multi-worker rehearsal"},
    "A10": {"state": "built+evidenced", "evidence": "e3_execution.py E3ProductionExecutor"},
    "A11": {"state": "built+evidenced", "evidence": "e3_integrator.py"},
    "A12": {"state": "built+evidenced", "evidence": "e3_verifier.py (independent critic)"},
    "A13": {"state": "built+tested", "evidence": "e3_conflict.py / e3_replan.py / e3_escalate.py"},
    "A14": {"state": "built+partially qualified", "evidence": "e3_qualification_benchmark.py EvidenceBackedBenchmark"},
    "A15": {"state": "built, drill evidenced (stubbed provider failures, isolated db; live drill pending Stage 2)",
            "evidence": "exec-brain/e4e5_drill_harness.py D1/D2 (checkpoint, equivalent failover, handover, no-equivalent escalation); 33/33 checks, 0 provider calls",
            "task": "agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23"},
    "A16": {"state": "built, drill evidenced (stubbed provider failures, isolated db; live drill pending Stage 2)",
            "evidence": "exec-brain/e4e5_drill_harness.py D3/D4/D5/D6 (outage, malformed output, convergence cap, safe mode, owner override audit, recovery); 33/33 checks, 0 provider calls",
            "task": "agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23"},
    "A17": {"state": "built", "evidence": "decision_rationale.py + eb.py audit + e3 evidence views"},
    "A18": {"state": "active", "evidence": "HermesRemoteQueuePoller (2-min cadence, task Running)"},
    "A19": {"state": "active", "evidence": "Hermes_Gateway (at logon) + ChiefDiscordSync (30 min) + hook discord-chief-archive"},
    "A20": {"state": "built", "evidence": "scripts/company_inventory.py (this worker)"},
    "A21": {"state": "pending task", "task": "agent-operational-brief-health-backup-persistence-2026-09-23"},
    "A22": {"state": "pending task", "task": "agent-operational-brief-health-backup-persistence-2026-09-23"},
    "B01": {"state": "partially built, successor required", "task": "agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23"},
    "B02": {"state": "pending task", "task": "agent-regional-job-search-agents-and-schedulers-2026-09-23"},
    "B03": {"state": "pending task", "task": "agent-regional-job-search-agents-and-schedulers-2026-09-23"},
    "B04": {"state": "pending task", "task": "agent-regional-job-search-agents-and-schedulers-2026-09-23"},
    "B05": {"state": "pending task", "task": "agent-regional-job-search-agents-and-schedulers-2026-09-23"},
    "B06": {"state": "pending task", "task": "agent-regional-job-search-agents-and-schedulers-2026-09-23"},
    "B07": {"state": "pending task", "task": "agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23"},
    "B08": {"state": "built (uncommitted before this task)", "evidence": "career-ops/tracker_writer.py + tests"},
    "B09": {"state": "missing", "task": "agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23"},
    "B10": {"state": "pending task", "task": "agent-company-watch-job-search-integration-2026-09-23"},
    "B11": {"state": "pending task", "task": "agent-company-watch-job-search-integration-2026-09-23"},
    "B12": {"state": "pending task", "task": "agent-application-inbox-status-monitor-2026-09-23"},
    "B13": {"state": "built+evidenced", "evidence": "career-ops/job_intelligence.py + job_brief_schema.json; extractive JobBrief, verbatim lines with source_line; 2026-09-24T00:50:49Z acceptance 42/42"},
    "B14": {"state": "built+evidenced (research sources owner-gated)", "evidence": "job_intelligence.research_brief(); cited-only facts, uncited rejected, no provider -> research_needed; http/browser providers disabled, never launched"},
    "B15": {"state": "pending task", "task": "agent-cv-cover-letter-linkedin-workflows-2026-09-23"},
    "B16": {"state": "pending task", "task": "agent-cv-cover-letter-linkedin-workflows-2026-09-23"},
    "B17": {"state": "built+evidenced", "evidence": "career-ops/application_pack_review.py; independent re-derivation, blocks a tampered pack"},
    "B18": {"state": "built+evidenced (no autonomous submit)", "evidence": "career-ops/submission_gate.py; every external action refused, owner approval required and pack-bound, external_action_performed=false"},
    "B19": {"state": "pending task", "task": "agent-cv-cover-letter-linkedin-workflows-2026-09-23"},
    "B20": {"state": "pending task", "task": "agent-cv-cover-letter-linkedin-workflows-2026-09-23"},
    "B21": {"state": "pending task", "task": "agent-linkedin-networking-interview-support-2026-09-23"},
    "B22": {"state": "pending task", "task": "agent-linkedin-networking-interview-support-2026-09-23"},
    "B23": {"state": "pending task", "task": "agent-career-daily-brief-and-pipeline-prioritizer-2026-09-23"},
    "B24": {"state": "partially built", "task": "agent-regional-job-search-agents-and-schedulers-2026-09-23"},
    "C01": {"state": "pending task", "task": "agent-whole-company-local-acceptance-and-morning-handover-2026-09-23"},
    "C02": {"state": "active", "evidence": "tasks-or-issues/overnight-owner-actions-2026-09-24.md"},
    "C03": {"state": "pending task", "task": "agent-deployment-prep-manifest-and-owner-admin-checklist-2026-09-23"},
    "C04": {"state": "pending task", "task": "agent-whole-company-local-acceptance-and-morning-handover-2026-09-23"},
}

# Locally discovered, owner-relevant services/workflows and how they map to the
# roster. Anything discovered on the machine that is NOT listed here is surfaced
# as unmapped, so no workflow disappears silently.
LOCAL_SERVICE_MAP = {
    "Hermes_Gateway": {"roster": "A19", "state": "active", "kind": "windows_task"},
    "ChiefDiscordSync": {"roster": "A19", "state": "active", "kind": "windows_task"},
    "HermesRemoteQueuePoller": {"roster": "A18", "state": "active", "kind": "windows_task"},
    "ChiefCareerScan-UK": {"roster": "B02", "state": "active-registered", "kind": "windows_task"},
    "ChiefCareerScan-Dubai": {"roster": "B03", "state": "registered-refuses-no-lane-config", "kind": "windows_task"},
    "ChiefCareerScan-Japan": {"roster": "B04", "state": "registered-refuses-no-lane-config", "kind": "windows_task"},
    "ChiefCareerScan-Singapore": {"roster": "B05", "state": "registered-refuses-no-lane-config", "kind": "windows_task"},
    "Mukund Chief of Staff": {
        "roster": None,
        "state": "superseded-donor (legacy new-custom-Chief startup task; last result -1073741510; "
                 "Hermes supersedes it as the Chief layer; NOT disabled - awaits owner decision)",
        "kind": "windows_task",
    },
    "hook:discord-chief-archive": {"roster": "A19", "state": "active", "kind": "hermes_hook"},
}

LEGACY_SYSTEMS = {
    "career_ops_install": r"C:\Users\mukun\Documents\ChatGPT\CV customizer\career-ops-career-ops-v1.29.0",
    "july_chief": r"C:\Users\mukun\Documents\Codex\2026-07-27\okay-this-is-my-current-project\outputs\mukund-chief-of-staff",
    "mukund_os": r"C:\Users\mukun\Documents\Chief of staff",
    "custom_new_chief": r"C:\Users\mukun\Documents\ChatGPT\CV customizer\mukund-chief-of-staff",
}

CANONICAL_RESOURCES = {
    "uk_tracker": r"C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx",
    "dubai_tracker": r"C:\Users\mukun\Downloads\codex\Dubai_Cybersecurity_Job_Tracker.xlsx",
    "japan_tracker": r"C:\Users\mukun\Downloads\codex\Japan_Cybersecurity_Job_Tracker.xlsx",
    "singapore_tracker": r"C:\Users\mukun\Downloads\codex\Singapore_Cybersecurity_Job_Tracker.xlsx",
    "discord_archive_dir": r"C:\Users\mukun\DiscordArchive\chief",
    "hermes_home": os.path.expandvars(r"%LOCALAPPDATA%\hermes"),
}


def parse_roster_ids(repo: Path) -> list[dict]:
    """Extract the roster table rows (ID + worker/service + mode) from the master roster."""
    path = repo / "state" / "v1-agent-roster.md"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([ABC]\d{2})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            rows.append({"id": m.group(1), "worker": m.group(2), "mode": m.group(3)})
    return rows


def owned_scheduled_tasks() -> list[dict]:
    """Read every scheduled task and keep only the ones this organisation owns."""
    try:
        proc = subprocess.run(
            ["schtasks", "/query", "/fo", "CSV", "/v"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    except Exception as exc:  # pragma: no cover - environment specific
        return [{"error": str(exc)}]
    if proc.returncode != 0:
        return [{"error": f"schtasks exit {proc.returncode}"}]

    reader = csv.DictReader(io.StringIO(proc.stdout))
    out = []
    for row in reader:
        name = (row.get("TaskName") or "").strip().lstrip("\\")
        if not name or not name.startswith(OWNED_TASK_PREFIXES):
            continue
        out.append({
            "task_name": name,
            "status": (row.get("Status") or "").strip(),
            "last_run": (row.get("Last Run Time") or "").strip(),
            "last_result": (row.get("Last Result") or "").strip(),
            "next_run": (row.get("Next Run Time") or "").strip(),
            "logon_mode": (row.get("Logon Mode") or "").strip(),
            "schedule_type": (row.get("Schedule Type") or "").strip(),
            "scheduled_task_state": (row.get("Scheduled Task State") or "").strip(),
            "task_to_run": (row.get("Task To Run") or "").strip()[:200],
        })
    return sorted(out, key=lambda r: r["task_name"])


def hermes_surface(hermes_home: Path) -> dict:
    skills_dir = hermes_home / "skills"
    skills = sorted(
        str(p.parent.relative_to(skills_dir)).replace("\\", "/")
        for p in skills_dir.rglob("SKILL.md")
    ) if skills_dir.is_dir() else []
    hooks_dir = hermes_home / "hooks"
    hooks = sorted(p.name for p in hooks_dir.iterdir() if p.is_dir()) if hooks_dir.is_dir() else []
    cron_dir = hermes_home / "cron"
    cron_jobs = sorted(p.name for p in cron_dir.glob("*.json")) if cron_dir.is_dir() else []
    return {"skills": skills, "skill_count": len(skills), "hooks": hooks, "cron_job_files": cron_jobs}


def queue_state(repo: Path) -> dict:
    base = repo / "remote-queue"
    state = {}
    for name in ("pending", "running", "blocked", "completed"):
        d = base / name
        state[name] = sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []
    state["counts"] = {k: len(v) for k, v in state.items() if isinstance(v, list)}
    return state


def path_facts(paths: dict[str, str]) -> dict[str, dict]:
    out = {}
    for key, raw in paths.items():
        p = Path(raw)
        rec = {"path": raw, "exists": p.exists(), "is_dir": p.is_dir() if p.exists() else None}
        if p.exists():
            try:
                rec["mtime"] = dt.datetime.fromtimestamp(p.stat().st_mtime).replace(microsecond=0).isoformat()
            except OSError:  # pragma: no cover
                pass
            if p.is_dir():
                try:
                    rec["entries"] = len(list(p.iterdir()))
                except OSError:  # pragma: no cover
                    pass
        out[key] = rec
    return out


def gateway_state(hermes_home: Path) -> dict:
    f = hermes_home / "gateway_state.json"
    if not f.is_file():
        return {"present": False}
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        return {"present": True, "parse_error": str(exc)}
    # Report only liveness fields - never the writer argv or any secret material.
    return {
        "present": True,
        "pid": raw.get("pid"),
        "gateway_state": raw.get("gateway_state"),
        "platforms": {k: v.get("state") for k, v in (raw.get("platforms") or {}).items()},
        "updated_at": raw.get("updated_at"),
        "code_version": raw.get("code_version"),
    }


def build_inventory(repo: Path) -> dict:
    hermes_home = Path(os.path.expandvars(r"%LOCALAPPDATA%\hermes"))
    roster = parse_roster_ids(repo)
    tasks = owned_scheduled_tasks()
    task_names = [t["task_name"] for t in tasks if t.get("task_name")]
    mapped = {t: LOCAL_SERVICE_MAP.get(t) for t in task_names}
    unmapped_tasks = [t for t in task_names if mapped.get(t) is None]

    roster_ids = [r["id"] for r in roster]
    coverage = ROSTER_COVERAGE
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "repo": str(repo),
        "roster": {
            "items": roster,
            "count": len(roster),
            "unmapped_ids": [i for i in roster_ids if i not in coverage],
            "coverage": {i: coverage[i] for i in roster_ids if i in coverage},
            "coverage_entries_without_roster_item": sorted(set(coverage) - set(roster_ids)),
        },
        "scheduled_tasks": tasks,
        "scheduled_task_mapping": mapped,
        "unmapped_owned_tasks": unmapped_tasks,
        "hermes_surface": hermes_surface(hermes_home),
        "hermes_gateway_state": gateway_state(hermes_home),
        "remote_queue": queue_state(repo),
        "legacy_donor_systems": path_facts(LEGACY_SYSTEMS),
        "canonical_resources": path_facts(CANONICAL_RESOURCES),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chief Company Registry / system inventory (read-only).")
    ap.add_argument("--repo", default=str(REPO_DEFAULT))
    ap.add_argument("--json", help="write the inventory JSON to this path")
    args = ap.parse_args(argv)

    inv = build_inventory(Path(args.repo).resolve())
    text = json.dumps(inv, indent=2, ensure_ascii=False, default=str)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")

    r = inv["roster"]
    print(
        f"roster items: {r['count']} | unmapped roster ids: {len(r['unmapped_ids'])} "
        f"| owned scheduled tasks: {len(inv['scheduled_tasks'])} "
        f"| unmapped owned tasks: {len(inv['unmapped_owned_tasks'])} "
        f"| queue pending/running/blocked/completed: "
        f"{inv['remote_queue']['counts'].get('pending', 0)}/"
        f"{inv['remote_queue']['counts'].get('running', 0)}/"
        f"{inv['remote_queue']['counts'].get('blocked', 0)}/"
        f"{inv['remote_queue']['counts'].get('completed', 0)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
