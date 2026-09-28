#!/usr/bin/env python3
"""E3 local Stage 2 readiness gate — bounded re-run with executable evidence.

Re-evaluates every recorded local Stage 2 readiness precondition from *current*
state and this run's executable evidence, then applies the enablement rule from
the immutable task contract:

    enable LOCAL E3 Stage 2 / production dispatch ONLY if
      (a) the credential-missing provider credentials are confirmed configured,
      (b) every readiness criterion is objectively satisfied by recorded
          evidence from this run, and
      (c) the authority/contract records explicit owner authorization for
          enablement at that point.

Any missing/ambiguous condition leaves Stage 2 DISABLED and records the exact
remaining condition. This script NEVER enables Stage 2, never spends a provider
call, and never reads or logs a credential value (presence checks only).

Checks performed (all executable, all in-run):

1. credential presence per provider (Windows Credential Manager / env, presence
   only — no value is read into a variable that is printed);
2. regression suites — consumes the JSON emitted by ``scripts/evidence_runner.py``
   (12 isolated suites) and asserts every suite passed with exit 0;
3. real-path production-rehearsal evidence — hashes and re-parses the committed
   multi-worker rehearsal bundle and re-derives its checks (consumed, not
   repeated: the task contract forbids re-running it);
4. Google image worker status — consumes the recorded diagnosis;
5. worker qualification — re-derives capability state from recorded execution
   evidence (read-only) and reads the live capability registry back;
6. rehearsal-evidence isolation — a fresh fail-closed probe plus before/after
   SHA-256 of every production store *including* WAL/SHM sidecars, and a static
   E1/E2 boundary scan;
7. rollback/recovery availability — deploy/restore path, backups, runtime
   deployment state and orchestration schema version.

Usage:
    python scripts/e3_stage2_readiness_gate.py [--regression-evidence PATH]
                                               [--out-dir DIR]
                                               [--activation-pool longcat-text]
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# The deployed runtime is what actually executes; repo is the source of truth.
sys.path.insert(0, str(RUNTIME_ROOT))
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

CREDENTIAL_MISSING_WORKERS = [
    "mistral-small-4", "glm-53-flash", "qwen38-27b", "longcat-2.0",
    "minimax-m3", "step-37-flash", "tencent-hunyuan-hy3",
]
CONFIGURED_WORKERS = ["codex-cli", "google-nano-banana-2", "deepseek-v41-flash"]
ACTIVATION_POOLS = {
    "longcat-text": ("longcat-2.0",),
}
SCOPE_DECISION_PATH = (REPO_ROOT / "tasks-or-issues"
                       / "2026-09-28-owner-decision-google-image-scope.md")

# The authority file and the immutable task contract are the only sources that
# can grant owner authorization for local Stage 2 enablement. The gate verifies
# the authorization is actually recorded there rather than assuming it.
AUTHORITY_PATH = (REPO_ROOT / "tasks-or-issues"
                  / "2026-09-24-full-operational-vps-cutover.md")
TASK_CONTRACT_PATH = (REPO_ROOT / "remote-queue" / "running"
                      / "agent-e3-provider-verification-stage2-closeout-2026-09-24.json")

AUTHORIZATION_MARKERS = [
    (AUTHORITY_PATH,
     "STANDING CONDITIONAL APPROVAL granted 2026-09-23 for local enablement "
     "once objective local readiness gates pass"),
    (AUTHORITY_PATH,
     "After those credentials are configured and truthfully verified, re-run "
     "the complete local Stage 2 readiness gates and complete local Stage 2 if "
     "they pass"),
    (AUTHORITY_PATH,
     "complete local E3 Stage 2 if all gates pass"),
    (TASK_CONTRACT_PATH,
     "Owner authorization for LOCAL E3 Stage 2 is now explicit"),
]

# A live coordinator instruction can forbid enablement for a specific run. When it
# is present it SUPERSEDES any earlier embedded authorization: the gate fails
# closed and will not enable Stage 2 while the override stands.
COORDINATOR_OVERRIDE_MARKERS = [
    (TASK_CONTRACT_PATH,
     "DO NOT enable local E3 Stage 2"),
]


PRODUCTION_STORES = {
    "orchestration": RUNTIME_ROOT / "orchestration.db",
    "governor": RUNTIME_ROOT / "governor.db",
    "exec_brain": RUNTIME_ROOT / "exec_brain.db",
}


def _sha256_file(path: Path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _store_hashes() -> dict:
    """SHA-256 of each production store and its WAL/SHM sidecars."""
    out = {}
    for name, p in PRODUCTION_STORES.items():
        out[name] = {
            "main": _sha256_file(p),
            "wal": _sha256_file(Path(str(p) + "-wal")),
            "shm": _sha256_file(Path(str(p) + "-shm")),
        }
    return out


# ── 1. credentials (presence only) ──────────────────────────────────

def check_credentials(activation_workers=None) -> dict:
    import generic_openai_adapter as goa
    from worker_registry import WorkerRegistry

    roster = WorkerRegistry()

    def probe_generic(worker_id):
        worker = roster.get_worker(worker_id) or {}
        try:
            adapter = goa.get_adapter(worker_id)
            key, source = adapter._resolve_auth()
            present = key is not None
            del key  # never retained beyond the presence test
        except Exception as exc:  # pragma: no cover - defensive
            return {"worker_id": worker_id, "provider": worker.get("provider"),
                    "credential_present": False, "auth_source": "none",
                    "note": type(exc).__name__}
        return {"worker_id": worker_id, "provider": worker.get("provider"),
                "routable": bool(worker.get("routable")),
                "credential_present": present, "auth_source": source}

    def probe_configured(worker_id):
        """Presence-only probe for the workers already in the pool."""
        import gemini_keyaccess as gk
        import deepseek_keyaccess as dk
        worker = roster.get_worker(worker_id) or {}
        if worker.get("interface") == "cli":
            # codex-cli authenticates via the ChatGPT login, not an API key
            return {"worker_id": worker_id, "provider": worker.get("provider"),
                    "credential_present": bool(worker.get("auth_configured")),
                    "auth_source": worker.get("auth_mode") or "none",
                    "probe": "cli_login_state_from_registry"}
        if worker_id == "google-nano-banana-2":
            present = (gk.credential_manager_entry_present()
                       or gk.env_var_present())
            source = ("credential_manager" if gk.credential_manager_entry_present()
                      else ("env" if gk.env_var_present() else "none"))
        elif worker_id == "deepseek-v41-flash":
            present = (dk.credential_manager_entry_present()
                       or dk.env_var_present())
            source = ("credential_manager" if dk.credential_manager_entry_present()
                      else ("env" if dk.env_var_present() else "none"))
        else:  # pragma: no cover - defensive
            return {"worker_id": worker_id, "provider": worker.get("provider"),
                    "credential_present": False, "auth_source": "none",
                    "probe": "unknown_worker"}
        return {"worker_id": worker_id, "provider": worker.get("provider"),
                "routable": bool(worker.get("routable")),
                "credential_present": present, "auth_source": source,
                "probe": "presence_only"}

    missing = [probe_generic(w) for w in CREDENTIAL_MISSING_WORKERS]
    configured = [probe_configured(w) for w in CONFIGURED_WORKERS]
    activation_workers = tuple(activation_workers or CREDENTIAL_MISSING_WORKERS)
    by_worker = {m["worker_id"]: m for m in missing}
    activation = [by_worker[w] for w in activation_workers if w in by_worker]
    return {
        "note": ("presence only — no credential value is read into a printed "
                 "variable, logged or stored; auth source is the store name, "
                 "never the secret"),
        "credential_missing_workers": missing,
        "still_missing_count": sum(1 for m in missing if not m["credential_present"]),
        "still_missing_workers": [m["worker_id"] for m in missing
                                  if not m["credential_present"]],
        "newly_configured_workers": [m["worker_id"] for m in missing
                                     if m["credential_present"]],
        "previously_configured_workers": configured,
        "all_seven_configured": all(m["credential_present"] for m in missing),
        "activation_workers": list(activation_workers),
        "activation_credentials_configured": bool(activation) and all(
            m["credential_present"] for m in activation),
        "activation_credential_workers_missing": [
            m["worker_id"] for m in activation if not m["credential_present"]],
    }


# ── 1b. recorded owner authorization (read, never assumed) ─────────

def check_owner_authorization(activation_pool: str = "longcat-text") -> dict:
    """Verify the owner's Stage 2 authorization is actually recorded.

    The gate never enables Stage 2 on its own authority. It requires the
    authorization to be present in the authority file / immutable task contract,
    and it requires the precondition those documents attach to that
    authorization (all intended provider credentials configured) to hold.
    """
    found = []
    missing = []
    for path, marker in AUTHORIZATION_MARKERS:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if marker in text:
            found.append({"path": str(path.relative_to(REPO_ROOT)),
                          "marker": marker})
        else:
            missing.append({"path": str(path.relative_to(REPO_ROOT)),
                            "marker": marker})
    overrides = []
    for path, marker in COORDINATOR_OVERRIDE_MARKERS:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if marker in text:
            overrides.append({"path": str(path.relative_to(REPO_ROOT)),
                              "marker": marker})
    scope_approved = (activation_pool == "longcat-text"
                      and SCOPE_DECISION_PATH.exists()
                      and "Status: APPROVED" in SCOPE_DECISION_PATH.read_text(encoding="utf-8")
                      and "Initial text Stage-2 allowlist: `longcat-2.0`" in
                      SCOPE_DECISION_PATH.read_text(encoding="utf-8"))
    if scope_approved:
        found.append({"path": str(SCOPE_DECISION_PATH.relative_to(REPO_ROOT)),
                      "marker": "APPROVED LongCat-only text Stage 2 scope"})
    return {
        # The scoped owner decision supersedes the obsolete all-provider
        # contract marker for this activation pool only.
        "authorization_recorded": scope_approved if activation_pool == "longcat-text" else not missing,
        "markers_found": found,
        "markers_missing": missing,
        "coordinator_override_active": bool(overrides),
        "coordinator_override_markers": overrides,
        "note": ("read from the authority file and the immutable task contract; "
                 "the gate does not invent authorization and fails closed if the "
                 "recorded authorization is absent or a live coordinator "
                 "instruction forbids enablement for this run"),
    }


# ── 1c. provider identity + worker execution readiness (post-key) ───

def _latest_evidence_dirs(label: str) -> list:
    base = REPO_ROOT / "audits" / "evidence"
    return sorted(base.glob(f"*-{label}"), reverse=True)


def check_provider_identity_and_readiness(activation_workers=None) -> dict:
    """Consume this task's live-identity and bounded-smoke evidence.

    Identity criterion: every intended provider's configured endpoint + API model
    ID must be backed by evidence — a live ``GET /models`` catalogue where the
    credential is accepted, or the provider's own authoritative documentation
    where it is not. A mapping that exists only because it was typed is a FAIL.

    Readiness criterion: every intended worker is either execution-ready, or its
    non-readiness is recorded as an explicit external blocker with an owner
    action. A silently non-executing worker is a FAIL.
    """
    probe_dirs = _latest_evidence_dirs("e3-provider-live-identity-probe")
    smoke_dirs = _latest_evidence_dirs("e3-provider-bounded-smoke")
    out = {
        "identity_probe_evidence": str(probe_dirs[0]) if probe_dirs else None,
        "bounded_smoke_evidence": str(smoke_dirs[0]) if smoke_dirs else None,
        "found": bool(probe_dirs and smoke_dirs),
    }
    if not out["found"]:
        out.update({"identity_verified": False, "readiness_recorded": False,
                    "note": "no live-identity / bounded-smoke evidence bundle found"})
        return out

    probe = json.loads((probe_dirs[0] / "evidence.json").read_text(encoding="utf-8"))
    smoke = json.loads((smoke_dirs[0] / "evidence.json").read_text(encoding="utf-8"))

    providers = []
    identity_ok = True
    for key, entry in (probe.get("providers") or {}).items():
        live = bool(entry.get("configured_endpoint_reachable")
                    and entry.get("configured_model_observed"))
        doc_backed = entry.get("authoritative_documentation_backed", False)
        ok = live or doc_backed
        identity_ok = identity_ok and ok
        providers.append({
            "provider": key,
            "configured_endpoint": entry.get("configured_models_endpoint"),
            "configured_api_model_id": entry.get("configured_api_model_id"),
            "endpoint_reachable": entry.get("configured_endpoint_reachable"),
            "model_observed_in_live_catalogue": entry.get("configured_model_observed"),
            "documentation_backed": doc_backed,
            "identity_verified": ok,
        })

    activation_workers = tuple(activation_workers or CREDENTIAL_MISSING_WORKERS)
    workers = []
    from worker_registry import WorkerRegistry
    roster = WorkerRegistry()
    readiness_ok = True
    for wid in CREDENTIAL_MISSING_WORKERS:
        w = roster.get_worker(wid) or {}
        v = w.get("verified_2026_09_24") or {}
        recorded = bool(v.get("routable_reason"))
        if wid in activation_workers:
            readiness_ok = readiness_ok and recorded
        workers.append({
            "worker_id": wid,
            "routable": bool(w.get("routable")),
            "smoke_test": w.get("smoke_test"),
            "smoke_http_status": v.get("smoke_http_status"),
            "provider_error": v.get("provider_error"),
            "external_blocker_recorded": recorded,
            "routable_reason": v.get("routable_reason"),
        })

    activation_provider_keys = {
        (roster.get_worker(wid) or {}).get("provider") for wid in activation_workers
    }
    scoped_identity_ok = all(
        p["identity_verified"] for p in providers
        if p["provider"] in activation_provider_keys
    )
    out.update({
        "identity_verified": identity_ok,
        "readiness_recorded": readiness_ok,
        "activation_workers": list(activation_workers),
        "activation_identity_verified": scoped_identity_ok,
        "activation_readiness_recorded": readiness_ok,
        "providers": providers,
        "workers": workers,
        "completed_workers": smoke.get("completed"),
        "failed_workers": smoke.get("failed"),
        "note": ("credential presence alone is never treated as routable or "
                 "qualified: a provider whose credential is rejected is recorded "
                 "as a documentation-backed identity with an external blocker"),
    })
    return out


# ── 2. regression suites (consumes evidence_runner output) ──────────

def check_regression_evidence(path: Path) -> dict:
    if not path.exists():
        return {"found": False, "path": str(path),
                "note": "no evidence_runner bundle found — criterion not evaluated"}
    report = json.loads(path.read_text(encoding="utf-8"))
    suites = report.get("suites", [])
    summary = report.get("unittest_summary", {})
    failing = [s["suite"] for s in suites
               if s.get("status") != "pass" or s.get("exit_code") != 0]
    missing_counts = [s["suite"] for s in suites
                      if s["counts"].get("collected") in (None, 0)]
    return {
        "found": True,
        "path": str(path),
        "evidence_sha256": _sha256_file(path),
        "code_sha": report.get("code_sha"),
        "run_started_utc": report.get("run_started_utc"),
        "python_version": report.get("python_version"),
        "suites_run": summary.get("suites_run"),
        "suites_passed": summary.get("suites_passed"),
        "suites_failed": summary.get("suites_failed"),
        "suites_unavailable": summary.get("suites_unavailable"),
        "tests_collected": summary.get("tests_collected"),
        "tests_passed": summary.get("tests_passed"),
        "suites": [{"suite": s["suite"], "status": s["status"],
                    "ran": s["counts"].get("collected"),
                    "passed": s["counts"].get("passed"),
                    "failed": s["counts"].get("failed"),
                    "error": s["counts"].get("error"),
                    "skipped": s["counts"].get("skipped"),
                    "exit_code": s.get("exit_code")} for s in suites],
        "failing_suites": failing,
        "suites_without_counts": missing_counts,
        "all_suites_pass": (bool(suites) and not failing and not missing_counts
                            and summary.get("suites_failed") == 0
                            and summary.get("suites_unavailable") == 0),
    }


# ── 3. real-path rehearsal evidence (consumed, not repeated) ────────

def check_rehearsal_evidence(evidence_dir: Path) -> dict:
    ev = evidence_dir / "evidence.json"
    if not ev.exists():
        return {"found": False, "path": str(ev),
                "note": "rehearsal evidence bundle not found"}
    report = json.loads(ev.read_text(encoding="utf-8"))
    checks = report.get("checks", {})
    # A check recorded as None belongs to an unrun scenario: it is NOT a pass.
    unmet = [k for k, v in checks.items() if v is False]
    unevaluated = [k for k, v in checks.items() if v is None]
    return {
        "found": True,
        "path": str(ev),
        "evidence_sha256": _sha256_file(ev),
        "run_started_utc": report.get("run_started_utc"),
        "run_finished_utc": report.get("run_finished_utc"),
        "stage_note": report.get("stage"),
        "usage_plan_total_calls": report.get("usage_plan_total_calls"),
        "bounded_usage": report.get("bounded_usage"),
        "usage_plan": report.get("usage_plan"),
        "isolation": report.get("isolation"),
        "live_store_contamination": report.get("live_store_contamination"),
        "e2_linkage": report.get("e2_linkage"),
        "unresolved_recorded_by_that_run": report.get("unresolved"),
        "scenarios_requested": report.get("scenarios_requested"),
        "checks": checks,
        "checks_failed": unmet,
        "checks_not_evaluated": unevaluated,
        "consumed_not_repeated": True,
        "note": ("consumed per the task contract ('do not repeat the "
                 "multi-worker rehearsal already evidenced by the retry task'); "
                 "no real provider call was spent by this gate run"),
    }


# ── 4. Google image worker status (consumes the recorded diagnosis) ─

def check_google_image(evidence_dir: Path) -> dict:
    ev = evidence_dir / "evidence.json"
    out = {"found": ev.exists(), "path": str(ev)}
    if ev.exists():
        out["evidence_sha256"] = _sha256_file(ev)
        report = json.loads(ev.read_text(encoding="utf-8"))
        out["diagnosis"] = {
            "verdict": report.get("verdict"),
            "reproduced": report.get("reproduced"),
            "established": report.get("established"),
            "remaining_unknown": report.get("remaining_unknown")
            or (report.get("diagnosis") or {}).get("remaining_unknown"),
        }
    from worker_registry import WorkerRegistry
    w = WorkerRegistry().get_worker("google-nano-banana-2") or {}
    out.update({
        "worker_id": "google-nano-banana-2",
        "routable": bool(w.get("routable")),
        "smoke_test": w.get("smoke_test"),
        "declared_state": "INTERMITTENT_NOT_SETTLED",
        "note": ("the earlier real-dispatch failure did not reproduce on the "
                 "identical request but the trigger is an open unknown; the "
                 "vision role is qualified only from recorded evidence"),
    })
    return out


# ── 4b. Google image real-dispatch resolution (evidence-derived) ────

GOOGLE_REPEAT_SERIES = (REPO_ROOT / "audits" / "evidence"
                        / "2026-09-24T01-44-32Z-e3-google-image-repeat-series")


def check_google_image_resolution() -> dict:
    """Derive the Google image criterion from recorded evidence.

    Criterion text (unchanged): *Google image worker real-dispatch failure
    resolved (not intermittent)*. The literal reading is used: the criterion is
    satisfied only if the recorded repeat series observed no recurrence.
    """
    ev = GOOGLE_REPEAT_SERIES / "evidence.json"
    if not ev.exists():
        return {"found": False, "path": str(ev),
                "criterion_satisfied": False,
                "note": "repeat-series evidence not found — criterion fails closed"}
    report = json.loads(ev.read_text(encoding="utf-8"))
    summary = report.get("summary") or {}
    outcomes = summary.get("outcome_counts") or {}
    no_image = summary.get("no_image_part_in_response_count")
    if no_image is None:
        no_image = outcomes.get("no_image_part_in_response", 0)
    executed = summary.get("calls_attempted")
    rate = summary.get("no_image_part_in_response_rate") or {}
    if isinstance(rate, dict):
        rate = rate.get("rate")
    finish_reasons = ((report.get("diagnosis") or {})
                      .get("provider_signals_on_recurrence") or {}) \
        .get("finish_reason_counts") or {}
    return {
        "found": True,
        "path": str(ev),
        "evidence_sha256": _sha256_file(ev),
        "dispatches_executed": executed,
        "outcome_counts": outcomes,
        "observed_recurrences": no_image,
        "observed_rate": rate,
        "recurrence_finish_reasons": finish_reasons,
        "root_cause_attributed": bool(finish_reasons),
        "root_cause_note": ("every recurrence carried the provider's own "
                            "finishReason IMAGE_RECITATION with an empty part list "
                            "— a provider content-side stop, not an adapter or "
                            "transport failure"),
        "criterion_text": "Google image worker real-dispatch failure resolved (not intermittent)",
        "criterion_satisfied": no_image == 0,
        "note": ("the literal criterion is NOT satisfied while a recurrence is "
                 "observed. The recurrence is attributed and bounded, the adapter "
                 "request shape is protocol-conformant, and a bounded retry policy "
                 "exists — but 'not intermittent' is a factual claim the evidence "
                 "does not support, so the criterion stays unmet and is reported "
                 "to the owner as a re-scoping question rather than silently "
                 "relaxed."),
    }


# ── 5. worker qualification (evidence-derived, read-only) ───────────

def check_qualification(db_path: Path) -> dict:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        from e3_qualification_benchmark import (
            EvidenceBackedBenchmark, MIN_RECORDED_EXECUTIONS,
            MIN_RECORDED_PASSES, MIN_FIRST_PASS_PASSES, registry_state_for,
        )
        bench = EvidenceBackedBenchmark(con)
        scopes = bench.candidate_scopes()
        evaluations = []
        for scope in scopes:
            res = bench.evaluate(scope["worker_id"], scope["role"],
                                 task_family="code")
            evaluations.append({
                "worker_id": scope["worker_id"],
                "role": scope["role"],
                "overall_state": res.overall_state.value,
                "registry_state": registry_state_for(res),
                "evidence_backed": res.evidence_backed,
                "counts": res.evidence_counts,
            })
        rows = [dict(r) for r in con.execute(
            "SELECT worker_id, task_family, capability_role, state, "
            "evidence_count, first_pass_successes, first_pass_attempts "
            "FROM capability_registry ORDER BY worker_id, capability_role")]
        qualified_without_evidence = con.execute(
            "SELECT COUNT(*) FROM capability_registry WHERE state='QUALIFIED' "
            "AND COALESCE(evidence_count,0)=0").fetchone()[0]
        event_count = con.execute(
            "SELECT COUNT(*) FROM worker_capability_event").fetchone()[0]
        evidence_rows = con.execute(
            "SELECT COUNT(*) FROM performance_evidence").fetchone()[0]
    finally:
        con.close()
    return {
        "bar": {"min_recorded_executions": MIN_RECORDED_EXECUTIONS,
                "min_recorded_passes": MIN_RECORDED_PASSES,
                "min_first_pass_passes": MIN_FIRST_PASS_PASSES},
        "scopes_evaluated": len(evaluations),
        "evaluations": evaluations,
        "capability_registry_rows": rows,
        "worker_capability_event_rows": event_count,
        "performance_evidence_rows": evidence_rows,
        "qualified_rows_without_evidence": qualified_without_evidence,
        "every_qualified_row_has_evidence": qualified_without_evidence == 0,
        "provider_calls_spent": 0,
    }


# ── 6. isolation + E1/E2 boundary ───────────────────────────────────

def check_isolation_and_boundary() -> dict:
    from e3_production_rehearsal import (
        EvidenceIsolationGuard, RehearsalEvidenceSink,
        RehearsalIsolationError, scan_e1_e2_boundary,
    )

    guard = EvidenceIsolationGuard()
    before = _store_hashes()

    refusals = {}
    # a rehearsal-tagged write aimed at each production store must fail closed
    for name, store in PRODUCTION_STORES.items():
        try:
            sink = RehearsalEvidenceSink(store, guard, rehearsal=True)
            sink.persist({"scenario": "stage2-gate-probe", "name": name})
            refusals[name] = False
        except RehearsalIsolationError:
            refusals[name] = True
    try:
        guard.assert_rehearsal_store(PRODUCTION_STORES["orchestration"])
        assert_rehearsal_store_refused = False
    except RehearsalIsolationError:
        assert_rehearsal_store_refused = True

    # an isolated sink outside the production root must succeed
    with tempfile.TemporaryDirectory() as td:
        isolated_store = Path(td) / "rehearsal-evidence.json"
        isolated_outside_production = not guard.is_production_store(isolated_store)
        ok_sink = RehearsalEvidenceSink(isolated_store, guard, rehearsal=True)
        ok_sink.persist({"scenario": "stage2-gate-probe", "isolated": True})
        flushed = ok_sink.flush()
        isolated_written = flushed.exists()

    after = _store_hashes()
    unchanged = {name: before[name] == after[name] for name in before}

    boundary = scan_e1_e2_boundary(REPO_ROOT / "exec-brain")

    return {
        "production_stores": {k: str(v) for k, v in PRODUCTION_STORES.items()},
        "before_hashes": before,
        "after_hashes": after,
        "stores_unchanged_including_wal_sidecars": all(unchanged.values()),
        "unchanged_detail": unchanged,
        "all_production_writes_refused": all(refusals.values()),
        "production_write_refusals": refusals,
        "assert_rehearsal_store_refused_on_production_path":
            assert_rehearsal_store_refused,
        "isolated_store_outside_production": isolated_outside_production,
        "isolated_sink_written": isolated_written,
        "e1_e2_boundary": boundary,
        "e2_public_interface_via_governor_record_request_only": (
            boundary["clean"] and bool(boundary["e2_public_interface_modules"])),
    }


# ── 7. rollback / recovery availability ─────────────────────────────

def check_rollback() -> dict:
    import importlib.util
    deploy_script = REPO_ROOT / "scripts" / "deploy_e3_runtime.py"
    spec = importlib.util.spec_from_file_location("_deploy_mod", deploy_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    backups_dir = RUNTIME_ROOT / "backups"
    backups = sorted(p.name for p in backups_dir.iterdir()
                     if p.is_dir()) if backups_dir.exists() else []
    manifests = [b for b in backups
                 if (backups_dir / b / "manifest.json").exists()]

    e3_modules = list(getattr(mod, "E3_MODULES", []))
    missing_modules = [m for m in e3_modules
                       if not (RUNTIME_ROOT / m).exists()]

    schema_version = None
    db = RUNTIME_ROOT / "orchestration.db"
    if db.exists():
        con = sqlite3.connect(str(db))
        try:
            try:
                row = con.execute(
                    "SELECT MAX(version) FROM schema_version").fetchone()
                schema_version = row[0] if row else None
            except sqlite3.Error:
                schema_version = None
        finally:
            con.close()

    return {
        "deploy_script": str(deploy_script),
        "deploy_script_has_restore": callable(getattr(mod, "restore", None)),
        "deploy_script_has_sha256_manifest": "manifest.json" in deploy_script.read_text(
            encoding="utf-8"),
        "backup_dirs": backups,
        "backup_dirs_with_manifest": manifests,
        "backup_available": len(manifests) > 0,
        "runtime_root": str(RUNTIME_ROOT),
        "e3_modules_required": len(e3_modules),
        "e3_modules_missing": missing_modules,
        "runtime_modules_deployed": not missing_modules,
        "orchestration_schema_version": schema_version,
        "orchestration_db_is_schema_v2": schema_version == 2,
        "rollback_available": (callable(getattr(mod, "restore", None))
                               and len(manifests) > 0),
    }


# ── main ────────────────────────────────────────────────────────────

def _latest_regression_evidence(label: str = "e3-stage2-readiness-gate-rerun"):
    """Newest evidence bundle that actually came from scripts/evidence_runner.py.

    A bundle is accepted only if it carries the runner's ``unittest_summary`` and
    ``suites`` keys, so a gate/verdict artifact stored under a similar name is
    never mistaken for regression evidence (an unparsable bundle must never be
    counted as a pass).
    """
    base = REPO_ROOT / "audits" / "evidence"
    candidates = sorted(base.glob(f"*-{label}"), reverse=True)
    for c in candidates:
        ev = c / "evidence.json"
        if not ev.exists():
            continue
        try:
            data = json.loads(ev.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if "unittest_summary" in data and "suites" in data:
            return ev
    return base / f"(none)-{label}" / "evidence.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regression-evidence", default=None)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--activation-pool", choices=sorted(ACTIVATION_POOLS),
                        default="longcat-text")
    args = parser.parse_args()
    activation_workers = ACTIVATION_POOLS[args.activation_pool]

    started = datetime.now(timezone.utc)
    reg_path = (Path(args.regression_evidence) if args.regression_evidence
                else _latest_regression_evidence())

    credentials = check_credentials(activation_workers)
    authorization = check_owner_authorization(args.activation_pool)
    provider_state = check_provider_identity_and_readiness(activation_workers)
    regression = check_regression_evidence(reg_path)
    rehearsal = check_rehearsal_evidence(
        REPO_ROOT / "audits" / "evidence"
        / "2026-09-23T21-32-41Z-e3-production-execution-rehearsal")
    rehearsal_latest = check_rehearsal_evidence(
        _latest_evidence_dirs("e3-production-execution-rehearsal")[0]
        if _latest_evidence_dirs("e3-production-execution-rehearsal")
        else REPO_ROOT / "audits" / "evidence" / "(none)")
    google = check_google_image(
        REPO_ROOT / "audits" / "evidence"
        / "2026-09-23T21-49-21Z-e3-google-image-diagnosis")
    google_resolution = check_google_image_resolution()
    qualification = check_qualification(RUNTIME_ROOT / "orchestration.db")
    isolation = check_isolation_and_boundary()
    rollback = check_rollback()

    # ── enablement rule (contract §enablement) ──────────────────────
    condition_a = credentials["activation_credentials_configured"]
    # criterion (b): every readiness criterion objectively satisfied by evidence
    # from this run.
    criteria = {
        "E1/E2/E3/E4/E5 + queue/bridge regressions pass": regression["all_suites_pass"],
        "real-path production rehearsal evidenced (multi-worker)":
            rehearsal["found"] and not rehearsal["checks_failed"],
        "latest real-path production rehearsal (this task) has no failed check":
            rehearsal_latest["found"] and not rehearsal_latest["checks_failed"],
        "provider identity verified for every in-scope provider "
        "(live catalogue or authoritative documentation)":
            provider_state.get("activation_identity_verified") is True,
        "in-scope non-executing provider workers recorded as explicit blockers":
            provider_state.get("activation_readiness_recorded") is True,
        "out-of-scope Google image capability remains separately reported":
            args.activation_pool == "longcat-text",
        "no unresolved critical integrity/privacy/safety defect":
            isolation["stores_unchanged_including_wal_sidecars"]
            and isolation["all_production_writes_refused"]
            and isolation["e1_e2_boundary"]["clean"],
        "worker routing/qualification evidence-driven":
            qualification["every_qualified_row_has_evidence"],
        "rollback/recovery available": rollback["rollback_available"],
    }
    condition_b = all(criteria.values())
    # criterion (c): explicit owner authorization for enablement at this point,
    # read from the authority file / immutable task contract (never assumed), and
    # only applicable once the recorded precondition (all intended provider
    # credentials configured) holds.
    condition_c_satisfied = bool(authorization["authorization_recorded"]
                                 and condition_a
                                 and not authorization["coordinator_override_active"])
    condition_c_note = (
        "the authority records the owner's standing conditional approval plus the "
        "instruction to re-run the gates after the credentials are configured and "
        "complete local Stage 2 if they pass, and this task's contract records the "
        "owner authorization for LOCAL E3 Stage 2 as explicit and applicable if and "
        "only if every objective readiness gate passes. "
        "Authorization markers found: " + str(len(authorization["markers_found"])) +
        "/" + str(len(AUTHORIZATION_MARKERS)) + ". Precondition (all intended "
        "provider credentials configured) satisfied: " + str(condition_a) + ". "
        "Live coordinator override forbidding enablement for this run: " +
        str(authorization["coordinator_override_active"]) + ".")
    if authorization["coordinator_override_active"]:
        condition_c_note += (
            " The live coordinator instruction SUPERSEDES the earlier embedded "
            "authorization: this run must not enable local E3 Stage 2 or production "
            "dispatch, and enablement is deferred to the successor task.")
    if authorization["markers_missing"]:
        condition_c_note += (" MISSING MARKERS: " +
                             str(authorization["markers_missing"]))

    enable = bool(condition_a and condition_b and condition_c_satisfied)
    blocked_reasons = []
    if not condition_a:
        blocked_reasons.append(
            "condition (a) failed for " + args.activation_pool + ": " +
            ", ".join(credentials["activation_credential_workers_missing"]))
    if not condition_b:
        unmet = [k for k, v in criteria.items() if not v]
        blocked_reasons.append("condition (b) failed: unmet readiness "
                               "criteria: " + "; ".join(unmet))
    if not condition_c_satisfied:
        blocked_reasons.append("condition (c) not satisfied: " + condition_c_note)
    # Non-gating external provider blockers are recorded even when they do not
    # trip a readiness criterion: they are owner/resolver work, and recording
    # them keeps the surface honest.
    external_blockers = [
        {"worker_id": w["worker_id"], "http_status": w.get("smoke_http_status"),
         "provider_error": w.get("provider_error"),
         "routable_reason": w.get("routable_reason")}
        for w in (provider_state.get("workers") or []) if not w.get("routable")]
    if external_blockers:
        blocked_reasons.append(
            "EXTERNAL PROVIDER BLOCKERS (non-gating readiness findings): " +
            "; ".join(f"{b['worker_id']}: HTTP {b['http_status']} "
                      f"{b['provider_error']}" for b in external_blockers))

    finished = datetime.now(timezone.utc)
    report = {
        "label": "e3-stage2-readiness-gate-verdict",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": finished.isoformat(timespec="seconds"),
        "activation_pool": args.activation_pool,
        "activation_workers": list(activation_workers),
        "stage": ("Local E3 Stage 2 readiness gate re-run — evaluates the "
                  "enablement rule with executable evidence; makes NO provider "
                  "call and does NOT enable Stage 2 itself"),
        "real_provider_calls_spent": 0,
        "runtime_root": str(RUNTIME_ROOT),
        "orchestration_db": str(RUNTIME_ROOT / "orchestration.db"),
        "checks": {
            "credentials": credentials,
            "owner_authorization": authorization,
            "provider_identity_and_readiness": provider_state,
            "regression_suites": regression,
            "production_rehearsal_evidence": rehearsal,
            "latest_production_rehearsal_evidence": rehearsal_latest,
            "google_image_worker": google,
            "google_image_resolution": google_resolution,
            "worker_qualification": qualification,
            "rehearsal_evidence_isolation_and_boundary": isolation,
            "rollback_and_recovery": rollback,
        },
        "enablement_rule": {
            "condition_a_credentials_configured": condition_a,
            "condition_b_all_readiness_criteria_satisfied": condition_b,
            "condition_c_explicit_owner_authorization_for_this_step": condition_c_satisfied,
            "condition_c_note": condition_c_note,
            "criteria": criteria,
        },
        "external_provider_blockers": external_blockers,
        "stage2_enabled": enable,
        "stage2_state": "ENABLED" if enable else "NOT ENABLED",
        "remaining_conditions": blocked_reasons,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-stage2-readiness-gate-verdict")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    (out_dir / "evidence.md").write_text(_render_md(report), encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "stage2_enabled": enable,
        "stage2_state": report["stage2_state"],
        "condition_a_credentials": condition_a,
        "condition_b_criteria": condition_b,
        "condition_c_owner_authorization": condition_c_satisfied,
        "coordinator_override_active":
            authorization["coordinator_override_active"],
        "still_missing_workers": credentials["still_missing_workers"],
        "provider_identity_verified": provider_state.get("identity_verified"),
        "provider_workers_execution_ready": [
            w["worker_id"] for w in (provider_state.get("workers") or [])
            if w.get("routable")],
        "provider_workers_blocked": [
            w["worker_id"] for w in (provider_state.get("workers") or [])
            if not w.get("routable")],
        "google_image_criterion_satisfied":
            google_resolution["criterion_satisfied"],
        "regression_all_pass": regression["all_suites_pass"],
        "remaining_conditions": blocked_reasons,
    }, indent=2))
    return 0 if not enable else 0


def _render_md(report: dict) -> str:
    c = report["checks"]
    cred = c["credentials"]
    reg = c["regression_suites"]
    rh = c["production_rehearsal_evidence"]
    iso = c["rehearsal_evidence_isolation_and_boundary"]
    q = c["worker_qualification"]
    rb = c["rollback_and_recovery"]
    er = report["enablement_rule"]

    lines = [
        "# E3 local Stage 2 readiness gate re-run",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Stage: {report['stage']}",
        f"- Real provider calls spent: {report['real_provider_calls_spent']}",
        f"- Runtime root: `{report['runtime_root']}`",
        "",
        f"## Verdict: Stage 2 **{report['stage2_state']}**",
        "",
        "### Enablement rule",
        "",
        f"- (a) credentials configured: **{er['condition_a_credentials_configured']}**",
        f"- (b) all readiness criteria satisfied: **{er['condition_b_all_readiness_criteria_satisfied']}**",
        f"- (c) explicit owner authorization for this step: **{er['condition_c_explicit_owner_authorization_for_this_step']}**",
        f"  - {er['condition_c_note']}",
        "",
        "### Readiness criteria evaluated this run",
        "",
        "| Criterion | Satisfied |",
        "|---|---|",
    ]
    for k, v in er["criteria"].items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "### Remaining conditions (recorded, not resolved)",
        "",
    ]
    for r in report["remaining_conditions"]:
        lines.append(f"- {r}")

    lines += [
        "",
        "## 1. Credential presence (presence only — no value read or logged)",
        "",
        f"- all seven configured: **{cred['all_seven_configured']}**",
        f"- still missing ({cred['still_missing_count']}/7): "
        + ", ".join(cred["still_missing_workers"] or ["(none)"]),
        "",
        "| Worker | Provider | Credential present | Auth source |",
        "|---|---|---|---|",
    ]
    for m in cred["credential_missing_workers"]:
        lines.append(f"| {m['worker_id']} | {m['provider']} | "
                     f"{m['credential_present']} | {m['auth_source']} |")
    lines += [
        "",
        "| Previously configured worker | Provider | Present | Source |",
        "|---|---|---|---|",
    ]
    for m in cred["previously_configured_workers"]:
        lines.append(f"| {m['worker_id']} | {m.get('provider')} | "
                     f"{m['credential_present']} | {m['auth_source']} |")

    ps = c.get("provider_identity_and_readiness") or {}
    lines += [
        "",
        "## 1b. Provider identity + live execution readiness (post-key)",
        "",
        f"- identity-probe evidence: `{ps.get('identity_probe_evidence')}`",
        f"- bounded-smoke evidence: `{ps.get('bounded_smoke_evidence')}`",
        f"- provider identity verified for every intended provider: "
        f"**{ps.get('identity_verified')}**",
        f"- every non-executing worker recorded as an explicit external blocker: "
        f"**{ps.get('readiness_recorded')}**",
        f"- workers that returned a real completion: `{ps.get('completed_workers')}`",
        f"- workers refused by their provider: `{ps.get('failed_workers')}`",
        "",
        "| Provider | Configured endpoint | Configured API model id | Endpoint reachable | "
        "Model in live catalogue | Documentation-backed | Identity verified |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in ps.get("providers") or []:
        lines.append(f"| {p['provider']} | `{p['configured_endpoint']}` | "
                     f"`{p['configured_api_model_id']}` | {p['endpoint_reachable']} | "
                     f"{p['model_observed_in_live_catalogue']} | "
                     f"{p['documentation_backed']} | {p['identity_verified']} |")
    lines += [
        "",
        "| Worker | Routable | Smoke | HTTP | Provider error | Blocker recorded |",
        "|---|---|---|---|---|---|",
    ]
    for w in ps.get("workers") or []:
        lines.append(f"| {w['worker_id']} | {w['routable']} | {w['smoke_test']} | "
                     f"{w.get('smoke_http_status')} | {w.get('provider_error')} | "
                     f"{w.get('external_blocker_recorded')} |")

    oa = c.get("owner_authorization") or {}
    lines += [
        "",
        "## 1c. Recorded owner authorization (read from the authority, never assumed)",
        "",
        f"- authorization recorded: **{oa.get('authorization_recorded')}**",
        f"- markers found: {len(oa.get('markers_found') or [])} / "
        f"{len(AUTHORIZATION_MARKERS)}",
    ]
    for m in oa.get("markers_found") or []:
        lines.append(f"  - `{m['path']}`: \"{m['marker']}\"")

    gr = c.get("google_image_resolution") or {}
    lines += [
        "",
        "## 1d. Google image real-dispatch resolution (evidence-derived)",
        "",
        f"- evidence: `{gr.get('path')}` (sha256 `{gr.get('evidence_sha256')}`)",
        f"- dispatches executed: {gr.get('dispatches_executed')}; "
        f"outcomes: `{gr.get('outcome_counts')}`",
        f"- observed recurrences: {gr.get('observed_recurrences')} "
        f"(rate {gr.get('observed_rate')})",
        f"- recurrence finish reasons: `{gr.get('recurrence_finish_reasons')}`",
        f"- root cause attributed: **{gr.get('root_cause_attributed')}**",
        f"- criterion `{gr.get('criterion_text')}` satisfied: "
        f"**{gr.get('criterion_satisfied')}**",
        f"- {gr.get('note')}",
    ]

    lines += [
        "",
        "## 2. Regression suites (via scripts/evidence_runner.py)",
        "",
        f"- bundle: `{reg.get('path')}` (sha256 `{reg.get('evidence_sha256')}`)",
        f"- code SHA: `{reg.get('code_sha')}`, python {reg.get('python_version')}",
        f"- suites {reg.get('suites_passed')}/{reg.get('suites_run')} passed, "
        f"failed {reg.get('suites_failed')}, unavailable {reg.get('suites_unavailable')}, "
        f"tests {reg.get('tests_passed')}/{reg.get('tests_collected')}",
        f"- all suites pass: **{reg.get('all_suites_pass')}**",
        "",
        "| Suite | Status | Ran | Passed | Failed | Errors | Skipped | Exit |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in reg.get("suites", []):
        lines.append(f"| {s['suite']} | {s['status']} | {s['ran']} | {s['passed']} | "
                     f"{s['failed']} | {s['error']} | {s['skipped']} | {s['exit_code']} |")

    lines += [
        "",
        "## 3. Real-path production-rehearsal evidence (consumed, not repeated)",
        "",
        f"- bundle: `{rh.get('path')}` (sha256 `{rh.get('evidence_sha256')}`)",
        f"- bounded real provider calls in that run: `{rh.get('usage_plan_total_calls')}` "
        f"(`{rh.get('bounded_usage')}`)",
        f"- checks failed: `{rh.get('checks_failed')}`; "
        f"not evaluated: `{rh.get('checks_not_evaluated')}`",
        f"- scenarios requested: `{rh.get('scenarios_requested')}`",
        "",
        "| Check | Value |",
        "|---|---|",
    ]
    for k, v in (rh.get("checks") or {}).items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## 4. Google image worker status (consumed)",
        "",
        f"- diagnostic bundle: `{c['google_image_worker'].get('path')}`",
        f"- routable: `{c['google_image_worker'].get('routable')}`, "
        f"declared state: `{c['google_image_worker'].get('declared_state')}`",
        f"- {c['google_image_worker'].get('note')}",
        "",
        "## 5. Worker qualification (evidence-derived, read-only)",
        "",
        f"- scopes evaluated: {q['scopes_evaluated']}, provider calls: {q['provider_calls_spent']}",
        f"- `qualified_rows_without_evidence`: {q['qualified_rows_without_evidence']}",
        f"- `worker_capability_event` rows: {q['worker_capability_event_rows']}",
        "",
        "| Worker | Role | Result | Registry state | Recorded | Passes | First-pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in q["evaluations"]:
        cnt = e["counts"]
        lines.append(f"| {e['worker_id']} | {e['role']} | {e['overall_state']} | "
                     f"{e['registry_state']} | {cnt.get('recorded_executions')} | "
                     f"{cnt.get('recorded_passes')} | "
                     f"{cnt.get('recorded_first_pass_passes')} |")

    lines += [
        "",
        "## 6. Rehearsal-evidence isolation + E1/E2 boundary",
        "",
        f"- all production writes refused (fail-closed): "
        f"**{iso['all_production_writes_refused']}**",
        f"- stores unchanged incl. WAL/SHM sidecars: "
        f"**{iso['stores_unchanged_including_wal_sidecars']}**",
        f"- isolated sink outside production root: "
        f"**{iso['isolated_store_outside_production']}** (written: "
        f"{iso['isolated_sink_written']})",
        f"- E1/E2 boundary clean: `{iso['e1_e2_boundary']['clean']}`; "
        f"direct SQL violations: `{iso['e1_e2_boundary']['direct_sql_violations']}`; "
        f"E2 reached only via `governor.record_request()`: "
        f"`{iso['e2_public_interface_via_governor_record_request_only']}`",
        "",
        "## 7. Rollback / recovery availability",
        "",
        f"- deploy script restore path present: `{rb['deploy_script_has_restore']}`",
        f"- backup dirs with manifest: `{len(rb['backup_dirs_with_manifest'])}`",
        f"- runtime E3 modules missing: `{rb['e3_modules_missing']}`",
        f"- orchestration schema version: `{rb['orchestration_schema_version']}` "
        f"(v2: `{rb['orchestration_db_is_schema_v2']}`)",
        f"- rollback available: **{rb['rollback_available']}**",
        "",
        "This gate made no provider call, read no credential value, and did not "
        "enable Stage 2. Stage 2 enablement requires all three conditions above.",
        "",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
