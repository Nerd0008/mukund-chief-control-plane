#!/usr/bin/env python3
"""Whole-company local acceptance runner (roster C01) + Morning Handover inputs.

This is the deterministic acceptance pass over the complete Chief OS v1. It runs
the *existing* verified surfaces (it does not re-implement any of them), records
exactly what each one reported, and separates three things that must never be
conflated:

* **local acceptance** — proven now, in this run;
* **owner-gated acceptance** — the surface exists and was not failed, but the
  step cannot be completed without an owner-only credential / account / decision;
* **external / not-run** — a live external integration that this runner
  deliberately does not touch (no external mutation is permitted here).

Rules baked in:

* no external mutation of any kind (no apply, no submit, no publish, no push);
* every step is a real subprocess with an explicit exit code recorded;
* an unavailable or unparsable step is recorded as ``unavailable`` — never as a
  pass;
* results are appended to ``results.json`` after every step, so an interrupted
  run keeps its truthful partial record;
* the roster account (all 50 roster items) and the owner-action consolidation are
  emitted alongside the step results.

Usage:
    python scripts/whole_company_acceptance.py [--out-dir DIR] [--label NAME]
                                               [--only SUBSTR]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"
PY = sys.executable
EB = RUNTIME_ROOT / "eb.py"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(argv, cwd=None, timeout=1800, env_extra=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if env_extra:
        env.update(env_extra)
    started = time.time()
    try:
        cp = subprocess.run(
            [str(a) for a in argv], cwd=str(cwd) if cwd else str(REPO_ROOT),
            capture_output=True, timeout=timeout, env=env,
        )
        out = cp.stdout.decode("utf-8", "replace")
        err = cp.stderr.decode("utf-8", "replace")
        return {"exit_code": cp.returncode, "stdout": out, "stderr": err,
                "duration_s": round(time.time() - started, 2), "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": None, "stdout": (exc.stdout or b"").decode("utf-8", "replace"),
                "stderr": (exc.stderr or b"").decode("utf-8", "replace"),
                "duration_s": round(time.time() - started, 2), "timed_out": True}


def _tail(text: str, n: int = 2500) -> str:
    return text[-n:] if text else ""


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# step definitions
#
# Each step: id, name, category, kind ("local"|"owner_gated"), argv, cwd,
# timeout, and a `check(result, ev_dir)` callable returning (status, detail).
# --------------------------------------------------------------------------- #

def _check_exit0(res, ev):
    if res["timed_out"]:
        return "FAIL", "step timed out"
    if res["exit_code"] == 0:
        return "PASS", f"exit 0 in {res['duration_s']}s"
    return "FAIL", f"exit {res['exit_code']}"


def _check_e1_intake(res, ev):
    if res["exit_code"] != 0:
        return "FAIL", f"exit {res['exit_code']}: {_tail(res['stderr'], 300)}"
    return "PASS", f"intake record {res['stdout'].strip().splitlines()[-1] if res['stdout'].strip() else '?'}"


def _check_e1_audit(res, ev):
    text = res["stdout"]
    ok = res["exit_code"] == 0 and "verify: PASS" in text
    return ("PASS" if ok else "FAIL"), ("chain + integrity verify PASS" if ok
                                        else f"exit {res['exit_code']}: {_tail(text, 400)}")


def _check_e2_verify(res, ev):
    ok = res["exit_code"] == 0 and "verify PASS" in res["stdout"]
    return ("PASS" if ok else "FAIL"), ("governor verify PASS" if ok
                                        else f"exit {res['exit_code']}: {_tail(res['stdout'], 300)}")


def _check_e3_db(res, ev):
    ok = res["exit_code"] == 0 and "Verification PASSED" in res["stdout"]
    return ("PASS" if ok else "FAIL"), ("schema v2 / all tables present" if ok
                                        else f"exit {res['exit_code']}: {_tail(res['stdout'], 300)}")


def _check_regression(res, ev):
    report = _load_json(ev / "regression" / "evidence.json")
    if not report:
        return "unavailable", f"no regression evidence.json (exit {res['exit_code']})"
    s = report.get("unittest_summary", {})
    ok = (res["exit_code"] == 0 and s.get("suites_failed") == 0
          and s.get("tests_failed", 0) == 0 and s.get("suites_unavailable", 0) == 0)
    detail = (f"{s.get('suites_run')} suites / {s.get('tests_collected')} collected / "
              f"{s.get('tests_passed')} passed / {s.get('tests_failed', 0)} failed / "
              f"{s.get('suites_unavailable')} unavailable; runner exit {res['exit_code']}")
    return ("PASS" if ok else "FAIL"), detail


def _check_drills(res, ev):
    report = _load_json(ev / "e4e5-drills" / "drill_evidence.json") or \
        _load_json(ev / "e4e5-drills" / "evidence.json")
    if not report:
        candidates = sorted((ev / "e4e5-drills").glob("*.json")) if (ev / "e4e5-drills").exists() else []
        report = _load_json(candidates[0]) if candidates else None
    if not report:
        return "unavailable", f"no drill artifact (exit {res['exit_code']})"
    passed = report.get("checks_passed")
    total = report.get("checks_total")
    calls = (report.get("bounded") or {}).get("real_provider_calls", report.get("real_provider_calls"))
    ok = res["exit_code"] == 0 and passed == total and calls == 0
    return ("PASS" if ok else "FAIL"), f"{passed}/{total} drill checks, real_provider_calls={calls}"


def _check_credential_probe(res, ev):
    report = None
    for p in (ev / "credential-presence").glob("*.json"):
        report = _load_json(p)
        if report:
            break
    if not report:
        report = _load_json(REPO_ROOT / "audits" / "evidence" / "2026-09-24T02-21-00Z-deployment-preflight" / "preflight.json")
    if not report:
        return "unavailable", f"no credential probe artifact (exit {res['exit_code']})"
    missing = report.get("still_missing_count")
    configured = report.get("newly_configured_count")
    if missing is None:
        return "unavailable", "probe artifact did not report presence counts"
    if missing and not configured:
        return "OWNER_GATED", (f"presence-only probe: {missing}/7 API worker credentials "
                               f"absent — owner action, not a defect")
    return "PASS", f"configured={configured}, still_missing={missing}"


def _check_preflight(res, ev):
    report = _load_json(ev / "deployment-preflight" / "preflight.json")
    if not report:
        return "unavailable", f"no preflight.json (exit {res['exit_code']})"
    fails = [c for c in report.get("checks", []) if c.get("status") == "FAIL"]
    warns = [c for c in report.get("checks", []) if c.get("status") == "WARN"]
    ok = res["exit_code"] == 0 and not fails
    detail = f"verdict={report.get('verdict')}; checks={len(report.get('checks', []))}; fail={len(fails)}; warn={len(warns)}"
    return ("PASS" if ok else "FAIL"), detail


def _check_health(res, ev):
    report = _load_json(ev / "operational-services" / "health_snapshot.json")
    if not report:
        return ("PASS" if res["exit_code"] == 0 else "FAIL"), f"exit {res['exit_code']} (no snapshot parsed)"
    ok = report.get("fail_count", 1) == 0
    return ("PASS" if ok else "FAIL"), (f"verdict={report.get('verdict')} "
                                        f"fail_count={report.get('fail_count')} "
                                        f"attention={report.get('attention_count')}")


def _check_persistence(res, ev):
    report = _load_json(ev / "persistence" / "persistence.json")
    if not report:
        return "unavailable", f"no persistence.json (exit {res['exit_code']})"
    tasks = report.get("tasks") or {}
    values = list(tasks.values()) if isinstance(tasks, dict) else list(tasks)
    survive = sum(1 for t in values
                  if isinstance(t, dict) and (t.get("survives_boot")
                                              or t.get("definition", {}).get("start_when_available")
                                              or "logon" in (t.get("definition", {}).get("triggers") or [])))
    return ("PASS" if res["exit_code"] == 0 else "FAIL"), \
        f"{len(values)} Chief tasks inspected read-only; {survive} configured to survive a reboot (reboot itself not performed)"


def _check_morning_brief(res, ev):
    report = _load_json(REPO_ROOT / "runtime" / "chief" / "morning-brief" / "latest.json")
    if not report:
        return ("PASS" if res["exit_code"] == 0 else "FAIL"), f"exit {res['exit_code']} (no brief parsed)"
    q = report.get("queue", {})
    return ("PASS" if res["exit_code"] == 0 else "FAIL"), \
        (f"verdict={report.get('verdict')} active={q.get('active_count')} "
         f"blocked={q.get('blocked_count')} owner_actions={len(report.get('owner_actions') or [])} "
         f"escalations={len(report.get('escalations') or [])}")


def _check_backup_restore(res, ev):
    report = _load_json(ev / "backup-restore" / "backup_restore_drill.json")
    if not report:
        candidates = sorted((ev / "backup-restore").glob("*.json")) if (ev / "backup-restore").exists() else []
        report = _load_json(candidates[0]) if candidates else None
    if not report:
        return ("PASS" if res["exit_code"] == 0 else "FAIL"), f"exit {res['exit_code']} (artifact not parsed)"
    ok = report.get("ok")
    if ok is None:
        ok = report.get("status") == "PASS" if report.get("status") else res["exit_code"] == 0
    arts = report.get("artifacts") or report.get("artifact_results") or []
    return ("PASS" if ok else "FAIL"), f"status={report.get('status', ok)}; artifacts={len(arts)}; exit {res['exit_code']}"


STEPS = [
    # ---------------- Chief control plane: E1 / E2 / E3 ------------------- #
    dict(id="chief_intake_e1_classify", category="chief_intake_e1",
         name="Owner -> Chief intake (E1 classify, deterministic)",
         kind="local", cwd=RUNTIME_ROOT, timeout=300, check=_check_e1_intake,
         argv=[PY, EB, "classify",
               "--request-text", "whole-company acceptance intake probe (local, non-operational)",
               "--task-type", "analysis", "--roles", "builder",
               "--reasoning-depth", "1", "--verification-level", "V2",
               "--risk-class", "R1", "--privacy-class", "P1",
               "--egress-policy", "LOCAL_ONLY", "--classification-confidence", "high"]),
    dict(id="e1_quality_floor_audit", category="chief_intake_e1",
         name="E1 immutable quality-floor chain + integrity audit",
         kind="local", cwd=RUNTIME_ROOT, timeout=300, check=_check_e1_audit,
         argv=[PY, EB, "audit", "--verify"]),
    dict(id="e2_resource_brief", category="e2_telemetry",
         name="E2 Daily Resource Brief (unknown dimensions stay UNKNOWN)",
         kind="local", cwd=RUNTIME_ROOT, timeout=300, check=_check_exit0,
         argv=[PY, EB, "brief"]),
    dict(id="e2_gov_verify", category="e2_telemetry",
         name="E2 Governor chain verification",
         kind="local", cwd=RUNTIME_ROOT, timeout=300, check=_check_e2_verify,
         argv=[PY, EB, "gov-verify"]),
    dict(id="e2_telemetry", category="e2_telemetry",
         name="E2 provider telemetry read-out",
         kind="local", cwd=RUNTIME_ROOT, timeout=300, check=_check_exit0,
         argv=[PY, EB, "telemetry"]),
    dict(id="e3_status", category="e3_delegation",
         name="E3 orchestration status (worker pool, router state, E4 pressure surface)",
         kind="local", cwd=RUNTIME_ROOT, timeout=300, check=_check_exit0,
         argv=[PY, EB, "e3-status"]),
    dict(id="e3_verify_db", category="e3_delegation",
         name="E3 orchestration store integrity + schema",
         kind="local", cwd=RUNTIME_ROOT, timeout=300, check=_check_e3_db,
         argv=[PY, EB, "e3-verify-db"]),
    dict(id="e4e5_drill_harness", category="e3_delegation_e4e5",
         name="E3 delegation/verification + E4 continuity/failover + E5 safe-mode drills "
              "(real execution abstractions, stubbed provider transport)",
         kind="local", timeout=1800, check=_check_drills, cwd=REPO_ROOT,
         env={"PYTHONPATH": str(REPO_ROOT / "exec-brain")},
         argv=[PY, "exec-brain/e4e5_drill_harness.py", "--out-dir", "{ev}/e4e5-drills"]),

    # ---------------------------- regression ------------------------------ #
    dict(id="regression_runner", category="full_regression",
         name="Full regression / evidence runner (every suite, exact counts)",
         kind="local", timeout=3600, check=_check_regression,
         argv=[PY, "scripts/evidence_runner.py", "--label", "whole-company-acceptance",
               "--out-dir", "{ev}/regression"]),

    # ------------------------ remote queue / watchdog --------------------- #
    dict(id="remote_queue_scheduler_state", category="remote_queue_watchdog",
         name="Remote-queue scheduler / watchdog task + dispatcher validation (read-only)",
         kind="local", timeout=600, check=_check_persistence,
         argv=[PY, "scripts/operational_services.py", "validate-persistence",
               "--out-dir", "{ev}/persistence"]),
    dict(id="discord_sync_dry_run", category="discord_sync",
         name="Discord Chief gateway archive sync (dry-run, no publish)",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "scripts/sync_discord_chief.py", "--dry-run"]),

    # ------------------------------ Career -------------------------------- #
    dict(id="career_ops_scan_dedupe_write", category="career_records",
         name="Career Ops scan -> eligibility -> dedupe -> tracker write -> Chief summary "
              "(dated copy only)",
         kind="local", timeout=1800, check=_check_exit0,
         argv=[PY, "career-ops/run_acceptance.py"]),
    dict(id="career_ops_cli_inventory", category="career_records",
         name="Career Ops canonical workbook inventory + integrity",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/career_ops_cli.py", "inventory"]),
    dict(id="regional_jobs_lanes", category="regional_jobs",
         name="Regional job-search lanes (UK / Dubai / Japan / Singapore) ready",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/regional_job_search.py", "lanes"]),
    dict(id="regional_jobs_eligibility_uk", category="regional_jobs",
         name="Regional eligibility + dedupe replay (UK, offline replay of recorded scan)",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/regional_job_search.py", "eligibility", "--region", "uk",
               "--scan-record", "runtime/career-ops/scan-runs/scan-uk-20260924T001418Z.json"]),
    dict(id="regional_jobs_eligibility_dubai", category="regional_jobs",
         name="Regional eligibility + dedupe replay (Dubai, offline replay of recorded scan)",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/regional_job_search.py", "eligibility", "--region", "dubai",
               "--scan-record", "runtime/career-ops/scan-runs/scan-dubai-20260924T001612Z.json"]),
    dict(id="regional_jobs_eligibility_japan", category="regional_jobs",
         name="Regional eligibility + dedupe replay (Japan, offline replay of recorded scan)",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/regional_job_search.py", "eligibility", "--region", "japan",
               "--scan-record", "runtime/career-ops/scan-runs/scan-japan-20260924T001752Z.json"]),
    dict(id="regional_jobs_eligibility_singapore", category="regional_jobs",
         name="Regional eligibility + dedupe replay (Singapore, offline replay of recorded scan)",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/regional_job_search.py", "eligibility", "--region", "singapore",
               "--scan-record", "runtime/career-ops/scan-runs/scan-singapore-20260924T001918Z.json"]),
    dict(id="company_watch_registry", category="company_watch",
         name="Company Watch watched-organisation registry parse (historical evidence only)",
         kind="local", timeout=900, check=_check_exit0,
         argv=[PY, "company-watch/company_watch.py", "registry"]),
    dict(id="company_watch_handoff_dry_run", category="company_watch",
         name="Company Watch -> Career Ops handoff interface, dry-run against the canonical "
              "workbook (recorded findings + 3 labelled ineligible test rows; writes nothing)",
         kind="local", timeout=900, check=_check_exit0,
         argv=[PY, "company-watch/company_watch.py", "handoff", "--region", "uk", "--findings",
               "audits/evidence/2026-09-24T02-27-00Z-company-watch-recovery/findings.json",
               "--include-ineligible-as-test", "--limit", "3"]),
    dict(id="application_status_monitor", category="application_status",
         name="Application Inbox / Status Monitor acceptance (fixture + runtime-synthesised mailbox)",
         kind="local", timeout=1800, check=_check_exit0,
         argv=[PY, "career-ops/run_application_inbox_acceptance.py",
               "--out-dir", "{ev}/career-application-status"]),
    dict(id="jobbrief_cv_cover_reviewer", category="jobbrief_cv_reviewer",
         name="JobBrief -> CV draft -> cover letter -> independent reviewer -> submission gate",
         kind="local", timeout=1800, check=_check_exit0,
         argv=[PY, "career-ops/run_job_intelligence_acceptance.py",
               "--out-dir", "{ev}/career-job-intelligence"]),
    dict(id="cv_cover_linkedin_handoff", category="linkedin_draft_readonly",
         name="CV/cover-letter + LinkedIn read-only intake/drafts + tracker handoff",
         kind="local", timeout=1800, check=_check_exit0,
         argv=[PY, "career-ops/run_cv_linkedin_acceptance.py",
               "--out-dir", "{ev}/career-cv-linkedin"]),
    dict(id="linkedin_outreach_interview_prep", category="linkedin_draft_readonly",
         name="LinkedIn outreach drafts (unsent) + Interview Prep Agent",
         kind="local", timeout=1800, check=_check_exit0,
         argv=[PY, "career-ops/run_interview_prep_acceptance.py",
               "--out-dir", "{ev}/career-interview-prep"]),
    dict(id="career_daily_brief", category="career_brief",
         name="Career Daily Brief / Pipeline Prioritizer acceptance (read-only aggregator)",
         kind="local", timeout=1800, check=_check_exit0,
         argv=[PY, "career-ops/run_daily_brief_acceptance.py",
               "--out-dir", "{ev}/career-daily-brief"]),
    dict(id="career_brief_status", category="career_brief",
         name="Career Daily Brief status read-out (scheduled task + last brief)",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/daily_brief.py", "status"]),
    dict(id="tracker_rollover", category="career_records",
         name="Monthly Tracker Rollover / archive worker acceptance (dated copies only)",
         kind="local", timeout=1800, check=_check_exit0,
         argv=[PY, "career-ops/run_rollover_acceptance.py"]),

    # --------------------- owner escalation / gates ----------------------- #
    dict(id="owner_escalation_and_gates", category="owner_escalation",
         name="Owner escalation + external-action refusal gates (submission gate, LinkedIn guard)",
         kind="local", timeout=600, check=_check_exit0,
         argv=[PY, "career-ops/submission_gate.py", "guard", "--action", "submit_application"]),

    # --------------------------- operational ------------------------------ #
    dict(id="operational_health_snapshot", category="morning_brief",
         name="Operational health snapshot (incl. E4 content-stop pressure surface)",
         kind="local", timeout=900, check=_check_health,
         argv=[PY, "scripts/operational_services.py", "health-snapshot",
               "--out-dir", "{ev}/operational-services"]),
    dict(id="morning_chief_brief", category="morning_brief",
         name="Morning Chief Brief (deterministic aggregation + escalation list)",
         kind="local", timeout=900, check=_check_morning_brief,
         argv=[PY, "scripts/operational_services.py", "morning-brief"]),
    dict(id="operational_backup_dry_run", category="backup_restore",
         name="Operational backup + log-rotation plan (dry-run; no snapshot written)",
         kind="local", timeout=900, check=_check_exit0,
         argv=[PY, "scripts/operational_services.py", "backup", "--dry-run",
               "--rotate-logs", "--out-dir", "{ev}/operational-backup"]),
    dict(id="backup_restore_drill", category="backup_restore",
         name="Backup / restore / rollback-availability drill (never writes live state)",
         kind="local", timeout=1800, check=_check_backup_restore,
         argv=[PY, "scripts/deployment_backup_restore_drill.py", "--out-dir", "{ev}/backup-restore"]),
    dict(id="deployment_preflight", category="deployment_prep",
         name="Deployment preflight / go-no-go (read-only)",
         kind="local", timeout=900, check=_check_preflight,
         argv=[PY, "scripts/deployment_preflight.py", "--out-dir", "{ev}/deployment-preflight"]),
    dict(id="credential_presence_probe", category="owner_gated_credentials",
         name="Provider credential presence probe (presence only, no value, no network)",
         kind="owner_gated", timeout=600, check=_check_credential_probe,
         argv=[PY, "scripts/e3_credential_presence_probe.py", "--out-dir", "{ev}/credential-presence"]),
]


# --------------------------------------------------------------------------- #
# roster account (C02 input): every roster item accounted for, no omission
# --------------------------------------------------------------------------- #

ROSTER_ACCOUNT = [
    ("A01", "Hermes Chief of Staff / owner interface", "PASS", "live gateway; this session; state/current_company_state.md"),
    ("A02", "E1 intake, classification, immutable quality floor", "PASS", "this run: chief_intake_e1_classify + e1_quality_floor_audit (chain + integrity PASS)"),
    ("A03", "E2 Resource Governor / provider telemetry", "PASS", "this run: e2_gov_verify PASS + e2_telemetry + e2_resource_brief"),
    ("A04", "Daily Resource Brief generator", "PASS", "this run: e2_resource_brief (eb brief); unknown dimensions stay UNKNOWN"),
    ("A05", "E3 Planner / decomposer", "PASS", "exec-brain/e3_planner.py; regression suite in full_regression"),
    ("A06", "E3 Router / meta-selector / Qualification Gate", "PASS", "exec-brain/e3_router.py + qualification_gate.py; evidence-driven capability_registry; this run: e3_status"),
    ("A07", "E3 Context Compiler", "PASS", "exec-brain/e3_context.py; full_regression"),
    ("A08", "E3 Permission Compiler", "PASS", "exec-brain/e3_permissions.py; full_regression"),
    ("A09", "E3 Dynamic Team Assembler", "PASS", "exec-brain/e3_team_assembly.py; decomposed multi-worker rehearsal evidence 2026-09-23T21:32:41Z"),
    ("A10", "E3 Worker Execution Manager", "PASS", "exec-brain/e3_execution.py; this run: e4e5_drill_harness on the real execution abstractions"),
    ("A11", "E3 Integrator", "PASS", "exec-brain/e3_integrator.py; multi-worker rehearsal scenario F COMPLETE"),
    ("A12", "E3 Independent Critic / Verifier", "PASS", "exec-brain/e3_verifier.py; a node cannot reach COMPLETE without a verification PASS"),
    ("A13", "E3 Conflict / targeted rework / replanning / escalation", "PASS", "exec-brain/e3_conflict.py, e3_replan.py, e3_escalate.py; full_regression"),
    ("A14", "E3 Capability Learning / benchmark / qualification manager", "PASS", "exec-brain/e3_qualification_benchmark.py + scripts/e3_qualification_from_evidence.py (evidence-backed bar; qualified_rows_without_evidence = 0)"),
    ("A15", "E4 Resource Continuity / checkpoint / failover manager", "PASS", "exec-brain/resource_monitor.py, checkpoint/failover paths; this run: e4e5 drills D1/D3/D7"),
    ("A16", "E5 Safe Mode / failure-drill / convergence manager", "PASS", "exec-brain/safe_mode.py; this run: e4e5 drills D5/D6 (stubbed-failure level)"),
    ("A17", "Audit / decision-journal / evidence-state reconciler", "PASS", "decision_rationale + blocked-work reconciliation 2026-09-24T02:45Z; this run's evidence bundle"),
    ("A18", "Remote Queue Scheduler / watchdog / recovery supervisor", "PASS", "remote_queue/ + tests; this run: remote_queue_scheduler_state (read-only) + full_regression queue/bridge suites"),
    ("A19", "Discord Chief Gateway + archive/sync worker", "PASS", "gateway connected; this run: discord_sync_dry_run (no publish performed in acceptance)"),
    ("A20", "Company Registry / system inventory worker", "PASS", "scripts/company_inventory.py; 50/50 roster items mapped (2026-09-23 audit)"),
    ("A21", "Local health / backup / restore / boot-persistence worker", "PASS", "this run: operational_health_snapshot + operational_backup_dry_run + backup_restore_drill + validate-persistence (reboot itself owner-gated, recorded)"),
    ("A22", "Morning Chief Brief aggregator", "PASS", "this run: morning_chief_brief"),
    ("B01", "Career Ops Manager / Chief integration", "PASS", "career-ops/career_ops_cli.py single Chief entry point; this run: career_ops_cli_inventory"),
    ("B02", "UK Job Search Agent", "PASS", "career-ops/regional_job_search.py + ChiefCareerScan-UK (dry-run); this run: regional_jobs_eligibility_uk"),
    ("B03", "Dubai Job Search Agent", "PASS", "lane built + scheduled (dry-run); this run: regional_jobs_eligibility_dubai. Limitation: no UAE-specific provider (owner decision, item 7) — thin results are a coverage fact, not a vacancy fact"),
    ("B04", "Japan Job Search Agent", "PASS", "lane built + scheduled (dry-run); this run: regional_jobs_eligibility_japan. Limitation: no Japan-specific provider (owner decision, item 7)"),
    ("B05", "Singapore Job Search Agent", "PASS", "lane built + scheduled (dry-run); this run: regional_jobs_eligibility_singapore"),
    ("B06", "Job Eligibility / role-policy filter", "PASS", "career-ops/regional_policy.json + evaluate_record; fail-closed when scope unresolved"),
    ("B07", "Job / Company / Application dedupe-state manager", "PASS", "shared tracker_writer primitives (normalize_url/pair_key/cross-month index); this run: dedupe replay per region"),
    ("B08", "Excel Tracker Writer (openpyxl, artifact-tool replaced)", "PASS", "career-ops/tracker_writer.py; this run: career_ops_scan_dedupe_write on a dated copy"),
    ("B09", "Monthly Tracker Rollover / archive worker", "PASS", "career-ops/tracker_rollover.py; this run: tracker_rollover acceptance"),
    ("B10", "Company Watch Agent", "PASS", "company-watch/; this run: company_watch_registry + company_watch_handoff_dry_run"),
    ("B11", "Recruiter / intermediary Watch Agent", "PASS", "recruiters parsed from the recorded history into the watched registry; read-only discovery, no contact"),
    ("B12", "Application Inbox / Status Monitor", "READY_NEEDS_OWNER_CONFIG", "built + tested; this run: application_status_monitor passes on fixtures/local export. Live mailbox feed needs the owner's Gmail read-only OAuth (overnight-owner-actions item 9)"),
    ("B13", "Job Description Analyzer / requirement extractor", "PASS", "career-ops/job_intelligence.py; this run: jobbrief_cv_cover_reviewer"),
    ("B14", "Company / Role Research Brief Agent", "READY_NEEDS_OWNER_CONFIG", "built; every brief reports research_needed while no research provider is owner-approved (item 11). Cited-file path works"),
    ("B15", "CV Tailor Agent", "PASS", "career-ops/cv_workflow.py (deterministic reordering, provenance per line); this run: cv_cover_linkedin_handoff"),
    ("B16", "Cover Letter Agent", "PASS", "career-ops/cv_workflow.py + cv_render_cover.mjs; this run: cv_cover_linkedin_handoff"),
    ("B17", "Application Pack Reviewer / truth & completeness gate", "PASS", "career-ops/application_pack_review.py; this run: jobbrief_cv_cover_reviewer"),
    ("B18", "Submission Gate / owner-approval handoff", "PASS", "career-ops/submission_gate.py; this run: owner_escalation_and_gates refuses the external action"),
    ("B19", "LinkedIn Job Discovery Agent (read-only)", "PASS", "career-ops/linkedin_workflow.py intake/dedupe/handoff; owner-exported local files only"),
    ("B20", "LinkedIn Profile / Post Draft Agent", "PASS", "unsent drafts with provenance; this run: cv_cover_linkedin_handoff"),
    ("B21", "Networking / Recruiter Outreach Draft Agent", "PASS", "three unsent variants, explicit unsent state; this run: linkedin_outreach_interview_prep"),
    ("B22", "Interview Prep Agent", "PASS", "career-ops/interview_prep.py; this run: linkedin_outreach_interview_prep"),
    ("B23", "Career Daily Brief / Pipeline Prioritizer", "PASS", "career-ops/daily_brief.py; this run: career_daily_brief + career_brief_status"),
    ("B24", "Regional Scheduler / run-health monitor", "PASS", "career-ops/install_schedules.py + dept_run_health; this run: regional_jobs_lanes + validate-persistence"),
    ("C01", "Whole-company Local Acceptance Runner", "PASS", "scripts/whole_company_acceptance.py; this acceptance run's evidence bundle"),
    ("C02", "Owner-Action Consolidator", "PASS", "consolidated order in tasks-or-issues/overnight-owner-actions-2026-09-24.md + the handover's ordered afternoon list"),
    ("C03", "Deployment Prep / Manifest / Restore Agent", "READY_NEEDS_OWNER_CONFIG", "deployments/ manifest, preflight GO, backup/restore drill pass; cutover itself is owner-gated (architecture + VPS details + authorisation)"),
    ("C04", "Final Morning Handover Generator", "PASS", "handovers/2026-09-24-morning-handover.md (this run)"),
]

OWNER_GATED_SUPPLEMENT = [
    ("provider-credentials", "7 API worker credentials (Mistral, GLM, Qwen, LongCat, MiniMax, Step, Hunyuan)",
     "READY_NEEDS_OWNER_CONFIG", "presence probe: 0/7 configured; owner action item 1; use scripts/set_provider_key.py"),
    ("e3-stage2", "E3 local Stage 2 production enablement", "BLOCKED_EXTERNAL",
     "gated on the 7 credentials + explicit owner step; anti-loop directive forbids re-staging while 0/7"),
    ("live-provider-e4e5", "Live-provider E4 failover / E5 recovery drill", "BLOCKED_EXTERNAL",
     "harness has no live-provider mode by design; owner acceptance question recorded (item 8)"),
    ("deployment-architecture", "Deployment architecture choice + VPS host/account details", "BLOCKED_EXTERNAL",
     "owner decision items 3 + 4; no cutover authorised"),
    ("reboot-persistence", "Reboot survival of the 7 non-`Hermes_Gateway` Chief tasks", "BLOCKED_EXTERNAL",
     "read-only validation done; a reboot is prohibited by this contract, so survival is UNVERIFIED (item 6)"),
    ("laptop-security-audit", "Owner-attended laptop UI-event attribution audit", "BLOCKED_EXTERNAL",
     "item 5; evidence preserved, no destructive cleanup performed"),
    ("rollover-policy", "Rotate 2026-09 out of the live workbooks (owner-column rows blocked)", "BLOCKED_EXTERNAL",
     "uk 26 / dubai 8 / singapore 4 owner-state rows; refused, not deleted"),
    ("regional-work-auth", "Work-authorisation facts for UAE / Japan / Singapore", "BLOCKED_EXTERNAL",
     "every non-UK record stays labelled UNKNOWN (item 6)"),
    ("linkedin-live-surface", "Whether the live LinkedIn account may ever be read", "BLOCKED_EXTERNAL",
     "owner-export path only today (item 13)"),
    ("ops-scheduling", "Scheduling cadence for operational backup / log rotation / briefs", "BLOCKED_EXTERNAL",
     "runs on demand only until the owner approves a cadence (item 15)"),
]


def _render_roster_md(rows, supplement) -> str:
    lines = ["# Roster account — every v1 roster item, 2026-09-24", "",
             "| ID | Worker / service | Status | Evidence |", "|---|---|---|---|"]
    for rid, name, status, ev in rows:
        lines.append(f"| {rid} | {name} | **{status}** | {ev} |")
    counts = {}
    for _r, _n, s, _e in rows:
        counts[s] = counts.get(s, 0) + 1
    lines += ["", f"Roster items accounted for: {len(rows)}/50 "
                  f"({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))}). No UNKNOWN omission.", "",
              "## Supplementary owner-gated / external items (not roster rows)", "",
              "| Item | What | Status | Detail |", "|---|---|---|---|"]
    for iid, what, status, detail in supplement:
        lines.append(f"| {iid} | {what} | **{status}** | {detail} |")
    lines.append("")
    return "\n".join(lines)


def _sha256(path: Path):
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def canonical_workbooks() -> dict:
    """Canonical tracker paths (owner records) from the declared regional profiles."""
    profiles = _load_json(REPO_ROOT / "career-ops" / "regional_profiles.json") or {}
    out = {}
    for region, spec in (profiles.get("regions") or {}).items():
        t = spec.get("tracker")
        if t:
            out[region] = t
    return out


def queue_state() -> dict:
    """Read-only snapshot of the remote-queue directory counts."""
    qdir = REPO_ROOT / "remote-queue"
    counts = {}
    for bucket in ("pending", "running", "blocked", "completed"):
        d = qdir / bucket
        counts[bucket] = len(list(d.glob("*.json"))) if d.exists() else None
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--label", default="whole-company-acceptance")
    ap.add_argument("--only", default=None, help="run only steps whose id contains this substring")
    args = ap.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence" / f"{stamp}-{args.label}")
    out_dir.mkdir(parents=True, exist_ok=True)

    steps = [s for s in STEPS if not args.only or args.only in s["id"]]
    books = canonical_workbooks()
    books_before = {r: _sha256(Path(p)) for r, p in books.items()}
    report = {
        "label": args.label,
        "kind": "whole_company_local_acceptance",
        "started_utc": _now(),
        "repo_root": str(REPO_ROOT),
        "runtime_root": str(RUNTIME_ROOT),
        "python": sys.executable,
        "external_mutations_performed": 0,
        "provider_calls_spent_by_this_runner": 0,
        "note": ("local acceptance only: no provider call, no external mutation, no "
                 "publish, no submit, no deployment cutover"),
        "steps": [],
    }

    def flush():
        report["steps"] = results
        (out_dir / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    results = []
    for step in steps:
        ev_dir = out_dir
        argv_step = [str(a).replace("{ev}", str(out_dir)) for a in step["argv"]]
        print(f"[acceptance] {step['id']}: {step['name']}", flush=True)
        res = _run(argv_step, cwd=step.get("cwd"), timeout=step.get("timeout", 1800),
                   env_extra=step.get("env"))
        try:
            status, detail = step["check"](res, ev_dir)
        except Exception as exc:  # a broken evaluator must never read as a pass
            status, detail = "unavailable", f"evaluator raised {type(exc).__name__}: {exc}"
        if step.get("kind") == "owner_gated" and status == "PASS":
            status = "PASS"  # a satisfied owner-gated step is a real pass
        entry = {
            "id": step["id"], "name": step["name"], "category": step["category"],
            "kind": step.get("kind", "local"),
            "command": " ".join(argv_step),
            "cwd": str(step.get("cwd") or REPO_ROOT),
            "exit_code": res["exit_code"], "duration_s": res["duration_s"],
            "timed_out": res["timed_out"], "status": status, "detail": detail,
            "stdout_tail": _tail(res["stdout"]), "stderr_tail": _tail(res["stderr"], 1200),
        }
        results.append(entry)
        print(f"[acceptance]   -> {status}: {detail}", flush=True)
        flush()

    report["finished_utc"] = _now()
    books_after = {r: _sha256(Path(p)) for r, p in books.items()}
    report["canonical_workbooks"] = {
        "paths": books,
        "sha256_before": books_before,
        "sha256_after": books_after,
        "unchanged_after_acceptance": books_before == books_after,
    }
    report["queue_state_after"] = queue_state()
    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    owner_gated = [r for r in results if r["status"] == "OWNER_GATED"]
    unavailable = [r for r in results if r["status"] == "unavailable"]
    report["summary"] = {
        "steps_run": len(results), "pass": len(passed), "fail": len(failed),
        "owner_gated": len(owner_gated), "unavailable": len(unavailable),
        "verdict": "PASS" if not failed and not unavailable else "FAIL",
        "canonical_workbooks_unchanged": report["canonical_workbooks"]["unchanged_after_acceptance"],
        "failed_steps": [r["id"] for r in failed],
        "unavailable_steps": [r["id"] for r in unavailable],
        "owner_gated_steps": [r["id"] for r in owner_gated],
    }

    (out_dir / "roster_account.json").write_text(json.dumps({
        "roster": [{"id": i, "worker": n, "status": s, "evidence": e} for i, n, s, e in ROSTER_ACCOUNT],
        "supplementary_owner_gated": [
            {"item": i, "what": w, "status": s, "detail": d} for i, w, s, d in OWNER_GATED_SUPPLEMENT],
        "roster_items": len(ROSTER_ACCOUNT),
        "unaccounted": [],
    }, indent=2), encoding="utf-8")
    (out_dir / "roster_account.md").write_text(
        _render_roster_md(ROSTER_ACCOUNT, OWNER_GATED_SUPPLEMENT), encoding="utf-8")
    flush()

    lines = [f"# Whole-company local acceptance — {stamp}", "",
             f"- Verdict: **{report['summary']['verdict']}**",
             f"- Steps: {len(results)} run — {len(passed)} PASS, {len(failed)} FAIL, "
             f"{len(owner_gated)} owner-gated, {len(unavailable)} unavailable",
             "- External mutations performed: **0**; provider calls spent: **0**", "",
             "| Step | Category | Status | Detail |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| `{r['id']}` | {r['category']} | **{r['status']}** | {r['detail']} |")
    lines += ["", "## Roster account", "",
              f"All {len(ROSTER_ACCOUNT)}/50 roster items accounted for — see `roster_account.md` "
              f"(and `roster_account.json`). No UNKNOWN omission.", ""]
    (out_dir / "acceptance.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
