#!/usr/bin/env python3
"""Qualify E3 workers from RECORDED execution evidence (no provider calls).

Runs the evidence-backed cold-start harness
(``e3_qualification_benchmark.EvidenceBackedBenchmark``) over every
``(worker_id, capability_role)`` pair that has real rows in the live E3
``orchestration.db``, then records the resulting capability state through
``CapabilityRegistry.record_qualification`` (E3's own store, with an audit event
per decision).

Truth rules:

* no provider call is made — the evidence already exists in the store;
* a worker with no recorded execution is reported ``NOT_RUN`` and left
  ``UNPROVEN``; smoke readiness is never read as qualification;
* anything that is not a full evidence-backed PASS maps to a non-QUALIFIED
  state, and ``record_qualification`` refuses a QUALIFIED row with zero evidence;
* nothing is written to ``exec_brain.db`` (E1) or ``governor.db`` (E2) — E2
  telemetry is only ever reported through ``governor.record_request()``, which
  this script does not call at all.

Usage:
    python scripts/e3_qualification_from_evidence.py [--out-dir DIR] [--dry-run]
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# Uses the *deployed* modules: E3 runs there, so deployment facts must match.
sys.path.insert(0, str(RUNTIME_ROOT))

TASK_FAMILY = "code"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="evaluate and report without writing capability rows")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    db_path = RUNTIME_ROOT / "orchestration.db"

    from e3_qualification_benchmark import (
        EvidenceBackedBenchmark, MIN_RECORDED_EXECUTIONS, MIN_RECORDED_PASSES,
        MIN_FIRST_PASS_PASSES, registry_state_for,
    )
    from capability_registry import CapabilityRegistry
    from worker_registry import WorkerRegistry

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    workers = WorkerRegistry()

    benchmark = EvidenceBackedBenchmark(con)
    scopes = benchmark.candidate_scopes()

    evaluations = []
    decisions = []
    try:
        for scope in scopes:
            worker_id, role = scope["worker_id"], scope["role"]
            result = benchmark.evaluate(worker_id, role, task_family=TASK_FAMILY)
            worker = workers.get_worker(worker_id) or {}
            state = registry_state_for(result)
            counts = result.evidence_counts
            evaluations.append({
                "worker_id": worker_id,
                "role": role,
                "task_family": TASK_FAMILY,
                "worker_routable": bool(worker.get("routable")),
                "provider": worker.get("provider"),
                "model": (result.worker_id and worker.get("model")),
                "evidence_backed": result.evidence_backed,
                "overall_state": result.overall_state.value,
                "registry_state_justified": state,
                "evidence_counts": counts,
                "evidence_references": result.evidence_references,
                "checks": result.test_results,
                "empty_counts": counts.get("recorded_executions") == 0,
                "notes": result.notes,
            })

            reason = (
                f"evidence-backed cold-start qualification: "
                f"{counts.get('recorded_executions', 0)} recorded execution(s), "
                f"{counts.get('recorded_passes', 0)} verified pass(es), "
                f"{counts.get('recorded_first_pass_passes', 0)} first-pass pass(es), "
                f"{counts.get('recorded_failures', 0)} recorded failure(s); "
                f"result={result.overall_state.value}"
            )
            if args.dry_run:
                decisions.append({"worker_id": worker_id, "role": role,
                                  "would_record_state": state, "reason": reason,
                                  "written": False})
                continue

            capability = CapabilityRegistry(con)
            recorded = capability.record_qualification(
                worker_id=worker_id,
                task_family=TASK_FAMILY,
                capability_role=role,
                state=state,
                evidence_count=counts.get("recorded_executions", 0),
                first_pass_successes=counts.get("recorded_first_pass_passes", 0),
                first_pass_attempts=counts.get("recorded_executions", 0),
                reason=reason,
                evidence_references=result.evidence_references,
                actor="e3-qualification-from-evidence",
                model_identity=worker.get("model"),
            )
            decisions.append({**recorded, "written": True,
                              "worker_routable": bool(worker.get("routable"))})
    finally:
        con.close()

    # Read the resulting store state back — the report must reflect the store,
    # not the intent.
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        capability_rows = [dict(r) for r in con.execute(
            "SELECT worker_id, task_family, capability_role, state, evidence_count, "
            "first_pass_successes, first_pass_attempts, last_qualified_at "
            "FROM capability_registry ORDER BY worker_id, capability_role")]
        event_rows = [dict(r) for r in con.execute(
            "SELECT event_id, worker_id, capability_role, previous_state, new_state, "
            "actor, timestamp FROM worker_capability_event ORDER BY timestamp")]
        qualified_without_evidence = con.execute(
            "SELECT COUNT(*) FROM capability_registry WHERE state='QUALIFIED' "
            "AND COALESCE(evidence_count,0)=0").fetchone()[0]
        capability_scope_count = con.execute(
            "SELECT COUNT(*) FROM performance_evidence WHERE role IS NULL "
            "OR provider IS NULL").fetchone()[0]
    finally:
        con.close()

    report = {
        "label": "e3-qualification-from-evidence",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": ("Evidence-backed worker capability qualification from recorded "
                  "real executions. No provider call is spent. Stage 2 NOT "
                  "enabled by this run."),
        "runtime_root": str(RUNTIME_ROOT),
        "orchestration_db": str(db_path),
        "harness": "exec-brain/e3_qualification_benchmark.py::EvidenceBackedBenchmark",
        "qualification_bar": {
            "min_recorded_executions": MIN_RECORDED_EXECUTIONS,
            "min_recorded_passes": MIN_RECORDED_PASSES,
            "min_first_pass_passes": MIN_FIRST_PASS_PASSES,
            "why": ("a single observation cannot distinguish a capability from a "
                    "lucky first attempt, and a worker that has since recovered "
                    "must not be permanently blocked by an earlier failed "
                    "attempt"),
        },
        "real_provider_calls_spent": 0,
        "dry_run": bool(args.dry_run),
        "scopes_evaluated": len(scopes),
        "evidence_accounting_note": (
            "One performance_evidence row is one recorded execution outcome "
            "(including a dispatch sequence that needed a repair). Rehearsal "
            "plans reuse node ids, and dag_node is upserted, so several evidence "
            "rows can share a dag_node_id; the row count is therefore the number "
            "of recorded execution outcomes, not a count of distinct DAG nodes. "
            "Both figures are reported so the strength of the evidence is not "
            "overstated."),
        "evaluations": evaluations,
        "decisions": decisions,
        "store_state_after": {
            "capability_registry": capability_rows,
            "worker_capability_event": event_rows,
            "qualified_rows_without_evidence": qualified_without_evidence,
            "evidence_rows_missing_provider_or_role": capability_scope_count,
        },
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-qualification-from-evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")

    md = [
        "# E3 worker qualification from recorded execution evidence",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Harness: `{report['harness']}`",
        f"- Orchestration DB: `{db_path}`",
        f"- Real provider calls spent: 0 (evaluates evidence already recorded)",
        f"- Bar: >= {MIN_RECORDED_PASSES} verified passes over "
        f">= {MIN_RECORDED_EXECUTIONS} recorded executions, with "
        f">= {MIN_FIRST_PASS_PASSES} first-pass pass",
        "",
        "| Worker | Role | Recorded | Verified passes | First-pass passes | "
        "Failures | Result | Registry state |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in evaluations:
        c = e["evidence_counts"]
        md.append(
            f"| {e['worker_id']} | {e['role']} | {c.get('recorded_executions')} | "
            f"{c.get('recorded_passes')} | {c.get('recorded_first_pass_passes')} | "
            f"{c.get('recorded_failures')} | {e['overall_state']} | "
            f"{e['registry_state_justified']} |")
    md += ["", "## Per-check detail", ""]
    for e in evaluations:
        md.append(f"### {e['worker_id']} / {e['role']} — {e['overall_state']}")
        md.append("")
        for chk in e["checks"]:
            md.append(f"- {chk['test_name']}: `{chk.get('state')}` — {chk['details']}")
        md += [
            "",
            f"- evidence references: `{e['evidence_references']}`",
            f"- evidence-backed: `{e['evidence_backed']}` "
            f"(a result that is not evidence-backed can never map to QUALIFIED)",
            "",
        ]
    md += ["## Store state after", ""]
    md.append(f"- `qualified_rows_without_evidence`: {qualified_without_evidence}")
    for row in capability_rows:
        md.append(f"- capability_registry: `{json.dumps(row)}`")
    for ev in event_rows:
        md.append(f"- worker_capability_event: `{json.dumps(ev)}`")
    md += [
        "",
        "Smoke readiness is not qualification. No worker is marked QUALIFIED here "
        "unless the record above shows it cleared every evidence check, and no "
        "provider call was spent to produce these decisions.",
        "",
    ]
    (out_dir / "evidence.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "scopes_evaluated": len(scopes),
        "results": [{"worker_id": e["worker_id"], "role": e["role"],
                     "state": e["overall_state"],
                     "registry_state": e["registry_state_justified"],
                     "counts": e["evidence_counts"]} for e in evaluations],
        "store": {"capability_registry": capability_rows,
                  "qualified_rows_without_evidence": qualified_without_evidence},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
