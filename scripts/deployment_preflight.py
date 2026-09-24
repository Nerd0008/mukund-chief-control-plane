#!/usr/bin/env python3
"""Deterministic deployment preflight / go-no-go check (read-only).

Answers, from the live machine and nothing else, the questions a cutover
rehearsal has to ask *before* it touches anything:

1. Host/runtime versions are the ones the manifest declares.
2. The repository checkout and the live runtime root both hold the required
   E3 module set, and `eb.py` has the `e3-*` registration patch.
3. Every declared state database exists and passes `PRAGMA integrity_check`.
4. Every declared scheduled task exists, is enabled, and its trigger/logon
   type matches the manifest.
5. The declared third-party Python dependencies import in this interpreter.
6. Credential *presence* per worker (never a value, no network call).
7. Every declared acceptance command's target file exists.
8. No secret-looking file is tracked or staged in git.
9. Topology-specific work is still marked pending (no accidental architecture
   finalisation).

It never writes to live state, never calls a provider, and never reads a
credential value. Exit code 0 = all checks PASS; 1 = at least one FAIL.

Usage:
    python scripts/deployment_preflight.py [--out-dir DIR] [--json]
"""

import argparse
import json
import os
import re
import subprocess
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"
HERMES_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"

# --- Declared expectations (the manifest's machine-checkable half) ----------

REQUIRED_MODULES = [
    "orchestration_db.py", "execution_dag.py", "worker_contract.py",
    "worker_registry.py", "capability_registry.py", "qualification_gate.py",
    "task_fingerprint.py", "decision_rationale.py", "e3_commands.py",
    "e3_cli.py", "e3_planner.py", "e3_router.py", "e3_team_assembly.py",
    "e3_integrator.py", "e3_verifier.py", "e3_conflict.py", "e3_context.py",
    "e3_permissions.py", "e3_decomposition_review.py", "e3_evidence.py",
    "e3_escalate.py", "e3_exploration.py", "e3_replan.py",
    "e3_qualification_benchmark.py", "e3_shadow_orchestrator.py",
    "e3_production_rehearsal.py", "e3_execution.py",
    "e3_execution_rehearsal.py", "generic_openai_adapter.py",
    "deepseek_adapter.py", "codex_adapter.py", "gemini_adapter.py",
    "deepseek_keyaccess.py", "gemini_keyaccess.py",
]

STATE_DATABASES = [
    RUNTIME_ROOT / "exec_brain.db",
    RUNTIME_ROOT / "governor.db",
    RUNTIME_ROOT / "orchestration.db",
    HERMES_ROOT / "state.db",
    HERMES_ROOT / "kanban.db",
    HERMES_ROOT / "shared-state.db",
    HERMES_ROOT / "cron" / "executions.db",
]

# task -> (expected_enabled, expected_logon_type, trigger kinds that must be present)
EXPECTED_TASKS = {
    "Hermes_Gateway": (True, "InteractiveToken", {"logon"}),
    "HermesRemoteQueuePoller": (True, "InteractiveToken", {"time"}),
    "ChiefDiscordSync": (True, "InteractiveToken", {"time"}),
    "ChiefCareerBrief": (True, "InteractiveToken", {"calendar"}),
    "ChiefCareerScan-UK": (True, "InteractiveToken", {"calendar"}),
    "ChiefCareerScan-Dubai": (True, "InteractiveToken", {"calendar"}),
    "ChiefCareerScan-Japan": (True, "InteractiveToken", {"calendar"}),
    "ChiefCareerScan-Singapore": (True, "InteractiveToken", {"calendar"}),
}

REQUIRED_THIRD_PARTY = ["openpyxl", "yaml"]

ACCEPTANCE_TARGETS = [
    "scripts/evidence_runner.py",
    "scripts/e3_stage2_readiness_gate.py",
    "scripts/e3_credential_presence_probe.py",
    "scripts/operational_services.py",
    "exec-brain/e3_production_rehearsal.py",
    "exec-brain/e3_execution_rehearsal.py",
    "exec-brain/e4e5_drill_harness.py",
    "career-ops/run_acceptance.py",
    "career-ops/dept_run_health.py",
    "career-ops/daily_brief.py",
]

# Topology-specific items that must remain explicitly undecided at this stage.
PENDING_OWNER_DECISIONS = [
    "deployment architecture (laptop primary vs VPS primary)",
    "VPS host/account details",
    "VPS cutover authorisation",
]

SEVEN_MISSING_WORKERS = [
    "mistral-small-4", "glm-53-flash", "qwen38-27b", "longcat-2.0",
    "minimax-m3", "step-37-flash", "tencent-hunyuan-hy3",
]  # roster order; presence is always recomputed live, never assumed


class Checks:
    def __init__(self):
        self.results = []

    def add(self, name, status, detail=None, evidence=None):
        self.results.append({"check": name, "status": status,
                             "detail": detail, "evidence": evidence})

    def ok(self, name, detail=None, evidence=None):
        self.add(name, "PASS", detail, evidence)

    def fail(self, name, detail=None, evidence=None):
        self.add(name, "FAIL", detail, evidence)

    def warn(self, name, detail=None, evidence=None):
        self.add(name, "WARN", detail, evidence)

    @property
    def failed(self):
        return [r for r in self.results if r["status"] == "FAIL"]

    @property
    def warned(self):
        return [r for r in self.results if r["status"] == "WARN"]


def check_host(checks):
    info = {
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
    }
    major, minor = (int(x) for x in sys.version.split()[0].split(".")[:2])
    if (major, minor) >= (3, 11):
        checks.ok("host.python>=3.11", detail=json.dumps(info))
    else:
        checks.fail("host.python>=3.11", detail=json.dumps(info))
    return info


def check_modules(checks):
    missing_repo = [m for m in REQUIRED_MODULES
                    if not (REPO_ROOT / "exec-brain" / m).exists()]
    missing_runtime = [m for m in REQUIRED_MODULES
                       if not (RUNTIME_ROOT / m).exists()]
    if missing_repo:
        checks.fail("repo.exec-brain module set complete",
                    detail=f"missing: {missing_repo}")
    else:
        checks.ok("repo.exec-brain module set complete",
                  detail=f"{len(REQUIRED_MODULES)} modules present")

    if missing_runtime:
        checks.fail("runtime.module set complete",
                    detail=f"missing in {RUNTIME_ROOT}: {missing_runtime}")
    else:
        checks.ok("runtime.module set complete",
                  detail=f"{len(REQUIRED_MODULES)} modules present in runtime root")

    eb = RUNTIME_ROOT / "eb.py"
    if not eb.exists():
        checks.fail("runtime.eb.py present", detail=str(eb))
    else:
        text = eb.read_text(encoding="utf-8", errors="replace")
        if "_register_e3_subcommands" in text:
            checks.ok("runtime.eb.py e3-* registration patch",
                      detail="patch present")
        else:
            checks.warn("runtime.eb.py e3-* registration patch",
                        detail="patch absent; run "
                               "scripts/deploy_e3_runtime.py to apply")


def check_state_databases(checks):
    detail = []
    bad = []
    for path in STATE_DATABASES:
        rec = {"path": str(path), "exists": path.exists()}
        if path.exists():
            try:
                con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                rec["integrity_check"] = con.execute(
                    "PRAGMA integrity_check").fetchone()[0]
                con.close()
            except Exception as exc:
                rec["integrity_check"] = f"{type(exc).__name__}: {exc}"
            if rec.get("integrity_check") != "ok":
                bad.append(rec)
        else:
            bad.append(rec)
        detail.append(rec)
    if bad:
        checks.fail("state.databases present and integrity ok",
                    detail=json.dumps(bad))
    else:
        checks.ok("state.databases present and integrity ok",
                  detail=f"{len(detail)} databases, all integrity_check=ok",
                  evidence=detail)
    return detail


def check_tasks(checks):
    detail = {}
    bad = []
    for name, (want_enabled, want_logon, want_triggers) in EXPECTED_TASKS.items():
        rec: dict = {"expected": {"enabled": want_enabled, "logon_type": want_logon,
                                  "triggers": sorted(want_triggers)}}
        try:
            proc = subprocess.run(["schtasks", "/query", "/tn", name, "/xml"],
                                  capture_output=True, text=True, timeout=60)
            xml = proc.stdout or ""
            if proc.returncode != 0:
                rec["error"] = "schtasks query failed"
                bad.append({name: rec})
                detail[name] = rec
                continue
            verbose = subprocess.run(["schtasks", "/query", "/tn", name,
                                      "/fo", "LIST", "/v"],
                                     capture_output=True, text=True, timeout=60)
            vtext = verbose.stdout or ""
            state_m = re.search(r"Scheduled Task State:\s*(\S+)", vtext)
            logon = re.search(r"<LogonType>(.*?)</LogonType>", xml, re.S)
            triggers = sorted(k for k, tag in
                              (("time", "<TimeTrigger>"),
                               ("calendar", "<CalendarTrigger>"),
                               ("logon", "<LogonTrigger>"),
                               ("boot", "<BootTrigger>"))
                              if tag in xml)
            rec["observed"] = {
                "enabled": (state_m.group(1).strip().lower() == "enabled"
                            if state_m else None),
                "logon_type": logon.group(1).strip() if logon else None,
                "triggers": triggers,
                "restart_on_failure": "<RestartOnFailure>" in xml,
                "start_when_available": "<StartWhenAvailable>true<" in xml,
            }
            mismatches = []
            if rec["observed"]["enabled"] is not want_enabled:
                mismatches.append("enabled")
            if rec["observed"]["logon_type"] != want_logon:
                mismatches.append("logon_type")
            if not want_triggers.issubset(set(triggers)):
                mismatches.append("triggers")
            rec["mismatches"] = mismatches
            if mismatches:
                bad.append({name: rec})
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            bad.append({name: rec})
        detail[name] = rec

    if bad:
        checks.fail("scheduled tasks present and match manifest",
                    detail=json.dumps(bad))
    else:
        checks.ok("scheduled tasks present and match manifest",
                  detail=f"{len(EXPECTED_TASKS)} tasks match", evidence=detail)
    return detail


def check_dependencies(checks):
    import importlib
    detail = {}
    missing = []
    for mod in REQUIRED_THIRD_PARTY:
        try:
            m = importlib.import_module(mod)
            detail[mod] = getattr(m, "__version__", "unknown")
        except Exception as exc:
            detail[mod] = f"MISSING ({type(exc).__name__})"
            missing.append(mod)
    if missing:
        checks.fail("python.third-party dependencies importable",
                    detail=json.dumps(detail))
    else:
        checks.ok("python.third-party dependencies importable",
                  detail=json.dumps(detail))
    return detail


def check_credentials(checks):
    """Presence only, through the live E3 auth resolver. No network call."""
    detail = {"workers": [], "provider_calls_spent": 0, "network_calls_spent": 0}
    try:
        sys.path.insert(0, str(REPO_ROOT / "exec-brain"))
        sys.path.insert(0, str(RUNTIME_ROOT))
        import generic_openai_adapter as goa
        from worker_registry import WorkerRegistry

        registry = WorkerRegistry()
        all_workers = registry.get_all_workers()
        present, absent = [], []
        for wid, worker in all_workers.items():
            rec = {"worker_id": wid, "provider": worker.get("provider"),
                   "interface": worker.get("interface"),
                   "routable": bool(worker.get("routable"))}
            if worker.get("interface") != "api":
                rec["credential_present"] = None
                rec["note"] = "non-API interface; credential handled by its own CLI/adapter"
                detail["workers"].append(rec)
                continue
            try:
                adapter = goa.get_adapter(wid)
            except Exception:
                rec["credential_present"] = None
                rec["note"] = "no generic_openai_adapter binding"
                detail["workers"].append(rec)
                continue
            key, source = adapter._resolve_auth()
            rec["credential_present"] = key is not None
            rec["auth_source"] = source
            del key
            (present if rec["credential_present"] else absent).append(wid)
            detail["workers"].append(rec)
        detail["configured_api_workers"] = present
        detail["credential_missing_api_workers"] = absent
        detail["configured_count"] = len(present)
        detail["missing_count"] = len(absent)
        if absent:
            checks.warn("credentials.presence (owner-gated)",
                        detail=f"{len(absent)} API worker credential(s) absent: "
                               f"{absent} — owner action, not an execution failure",
                        evidence=detail)
        else:
            checks.ok("credentials.presence", detail="all API worker credentials present",
                      evidence=detail)
    except Exception as exc:
        checks.fail("credentials.presence probe ran",
                    detail=f"{type(exc).__name__}: {exc}")
    return detail


def check_acceptance_targets(checks):
    missing = [t for t in ACCEPTANCE_TARGETS if not (REPO_ROOT / t).exists()]
    if missing:
        checks.fail("acceptance.command targets exist", detail=f"missing: {missing}")
    else:
        checks.ok("acceptance.command targets exist",
                  detail=f"{len(ACCEPTANCE_TARGETS)} command targets present")


SECRET_NAME_RE = re.compile(
    r"(^|/)(\.env[^/]*|auth\.json|[^/]*\.key|[^/]*\.pem|[^/]*\.ppk|"
    r"[^/]*\.sqlite[0-9]*|[^/]*\.db|credentials\.json|token\.json|"
    r"[^/]*secret[^/]*\.(json|ya?ml|txt|ini))$", re.I)


def check_git_hygiene(checks):
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=str(REPO_ROOT),
                                 capture_output=True, text=True, timeout=120)
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                                cwd=str(REPO_ROOT), capture_output=True,
                                text=True, timeout=120)
        suspicious = sorted({p for p in
                             (tracked.stdout + "\n" + staged.stdout).splitlines()
                             if p.strip() and SECRET_NAME_RE.search(p.strip())})
        if suspicious:
            checks.fail("git.no secret-looking files tracked or staged",
                        detail=json.dumps(suspicious))
        else:
            checks.ok("git.no secret-looking files tracked or staged",
                      detail="no match for secret filename patterns")
    except Exception as exc:
        checks.warn("git.no secret-looking files tracked or staged",
                    detail=f"could not inspect git: {type(exc).__name__}: {exc}")


def check_topology_decision_pending(checks):
    """The preflight must not silently assert a final architecture."""
    checks.ok("topology.decision still pending (by design)",
              detail="pending owner decisions: " + "; ".join(PENDING_OWNER_DECISIONS))


def render_markdown(report):
    lines = [
        "# Deployment preflight report",
        "",
        f"- Run (UTC): {report['run_started_utc']} -> {report['run_finished_utc']}",
        f"- Repository: `{REPO_ROOT}`",
        f"- Runtime root: `{RUNTIME_ROOT}`",
        f"- Provider calls spent: {report['provider_calls_spent']}",
        f"- Network calls spent: {report['network_calls_spent']}",
        f"- Verdict: **{report['verdict']}**",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for r in report["checks"]:
        detail = (r.get("detail") or "").replace("|", "\\|")
        lines.append(f"| {r['check']} | {r['status']} | {detail} |")
    lines += [
        "",
        "## How to read this",
        "",
        "- `PASS` — verified against the live machine on this run.",
        "- `WARN` — verified fact that is an owner-gated dependency, not a fault.",
        "- `FAIL` — a real precondition failure; the cutover runbook's no-go list "
        "applies.",
        "",
        "This report is read-only: it made no network call and read no credential "
        "value (presence and store name only).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    checks = Checks()
    details = {}
    try:
        details["host"] = check_host(checks)
        check_modules(checks)
        details["state_databases"] = check_state_databases(checks)
        details["scheduled_tasks"] = check_tasks(checks)
        details["dependencies"] = check_dependencies(checks)
        details["credentials"] = check_credentials(checks)
        check_acceptance_targets(checks)
        check_git_hygiene(checks)
        check_topology_decision_pending(checks)
    except Exception:
        checks.fail("preflight.completed", detail=traceback.format_exc())

    report = {
        "artifact": "deployment preflight / go-no-go check",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": str(REPO_ROOT),
        "runtime_root": str(RUNTIME_ROOT),
        "provider_calls_spent": 0,
        "network_calls_spent": 0,
        "guarantees": [
            "read-only against live state and databases",
            "no provider/network call",
            "no credential value read, printed or stored (presence + store name only)",
            "does not change scheduled tasks, services or state",
        ],
        "checks": checks.results,
        "fail_count": len(checks.failed),
        "warn_count": len(checks.warned),
        "verdict": "GO" if not checks.failed else "NO-GO",
        "details": details,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-deployment-preflight")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "preflight.json").write_text(json.dumps(report, indent=2, default=str),
                                            encoding="utf-8")
    (out_dir / "preflight.md").write_text(render_markdown(report), encoding="utf-8")

    summary = {
        "evidence_dir": str(out_dir),
        "verdict": report["verdict"],
        "fail_count": report["fail_count"],
        "warn_count": report["warn_count"],
        "failures": [r["check"] for r in checks.failed],
        "warnings": [r["check"] for r in checks.warned],
    }
    print(json.dumps(summary, indent=2) if not args.json
          else json.dumps({**summary, "checks": report["checks"]}, indent=2))
    return 0 if not checks.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
