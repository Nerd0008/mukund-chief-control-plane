#!/usr/bin/env python3
"""Capture the E4 provider content-side stop pressure view as an operator sees it.

Builds an isolated orchestration store by running the real E3 execution leg with
a deterministic stub adapter (0 real provider calls, no credential, no network),
then prints ``e3-status`` for that store with and without the recorded provider
series artifact
(``audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/observations.json``).

Optionally (``--live-db PATH``) it also reads an existing orchestration store
**read-only** and prints the same pressure view over its recorded rows, so the
recorded state of a real store is visible without modifying it.

Usage:
    python operator_pressure_demo.py [--out PATH] [--live-db PATH]
"""

import argparse
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

from e3_commands import E3Commands  # noqa: E402
from e3_execution import (  # noqa: E402
    E3ProductionExecutor, ExecutionAdapterRegistry, OrchestrationStore,
)
from e3_planner import E3Planner  # noqa: E402
from e3_team_assembly import TeamAssembly, TeamAssignment  # noqa: E402
from resource_monitor import (  # noqa: E402
    build_content_stop_pressure_view, render_content_stop_pressure,
)
from task_fingerprint import TaskFingerprint  # noqa: E402
from worker_registry import WorkerRegistry  # noqa: E402

GOOGLE_WORKER = "google-nano-banana-2"
FINISH_REASON = "IMAGE_RECITATION"
PLAN_ID = "plan-pressure-demo"
NODE_ID = "node-pressure-demo"
RECORDED_SERIES = (REPO_ROOT / "audits" / "evidence"
                   / "2026-09-24T01-44-32Z-e3-google-image-repeat-series"
                   / "observations.json")


class ContentStopAdapter:
    """Deterministic stub reproducing the recorded provider content-side stop."""

    def __init__(self):
        self.calls = 0

    def dispatch(self, contract):
        self.calls += 1
        return {
            "dispatch_id": f"stub-content-stop-{self.calls}",
            "status": "FAILED", "provider": "google",
            "model": "gemini-3.1-flash-image",
            "content": None, "image_dims": None, "image_decode_ok": False,
            "finish_reason": FINISH_REASON, "candidate_count": 1,
            "candidate_finish_reasons": [FINISH_REASON],
            "response_part_kinds": [],
            "usage": {"promptTokenCount": 17, "totalTokenCount": 17},
            "prompt_feedback": None, "error": "no_image_part_in_response",
            "exit_code": 200, "runtime_s": 5.8,
        }


def _build_store(db_path):
    plan = {
        "plan_id": PLAN_ID, "decomposition": False, "reason": "demo",
        "nodes": [{
            "node_id": NODE_ID, "objective": "pressure demo",
            "capability_roles": ["vision"], "dependencies": [], "inputs": {},
            "expected_outputs": {}, "verification_method": "test",
            "floor_id": None, "allowed_tools": [], "permissions": {},
            "fallback_candidates": [],
        }],
    }
    adapter = ContentStopAdapter()
    registry = ExecutionAdapterRegistry(
        worker_registry=WorkerRegistry(),
        adapter_factories={GOOGLE_WORKER: lambda: adapter},
        usage_reporters={GOOGLE_WORKER: lambda r: None},
    )
    assembly = TeamAssembly(PLAN_ID)
    assembly.assignments = [
        TeamAssignment(NODE_ID, GOOGLE_WORKER, "vision", "HIGH", "demo")]
    assembly.issues = []
    assembly.complete = True
    fingerprint = TaskFingerprint(
        task_family="code", reasoning_depth=1, risk_class="R1",
        required_roles=["vision"], verification_type="deterministic")
    store = OrchestrationStore(db_path)
    try:
        executor = E3ProductionExecutor(store, registry)
        run = executor.execute_plan(
            plan, E3Planner().build_dag(plan), assembly, fingerprint,
            "pressure demo",
            verification_test_cases_by_node={NODE_ID: [
                {"name": "dispatch completed", "field": "status",
                 "expected": "COMPLETED"}]},
            max_repair_attempts=0, dispatch_timeout=5,
            role_by_node={NODE_ID: "vision"})
    finally:
        store.close()
    return run, adapter


def _capture(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


def _summarise(view):
    """Key fields only — the operator view, not a data dump."""
    lines = []
    for source in view["sources"]:
        lines.append(f"source={source['source']} attempts_observed="
                     f"{source['attempts_observed']} "
                     f"classified={source['attempts_classified']} "
                     f"content_side_stops={source['content_stops_observed']}")
        for group in source["groups"]:
            rate = group["content_stop_rate"]
            lines.append(
                f"  {group['worker_id']} ({group['provider']}/{group['model']}) "
                f"attempts={group['attempts_observed']} "
                f"classified={group['attempts_classified']} "
                f"stops={group['content_stops_observed']} "
                f"rate={'unknown' if rate is None else format(rate, '.3f')} "
                f"sample_size={group['sample_size']} "
                f"last_finish_reason={group['last_finish_reason']} "
                f"last_stop_at={group['last_stop_at']} "
                f"flag={group['content_withheld_at_measurable_rate']} "
                f"status={group['status']}")
    lines.append(f"content_stop_pressure_detected="
                 f"{view['content_stop_pressure_detected']} "
                 f"rate_threshold={view['rate_threshold']} "
                 f"minimum_sample={view['minimum_sample']}")
    for error in view.get("source_errors") or []:
        lines.append(f"source_error={error}")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    parser.add_argument("--live-db", default=None,
                        help="existing orchestration store to read READ-ONLY")
    args = parser.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="e4-pressure-demo-"))
    db_path = tmp / "orchestration.db"
    run, adapter = _build_store(db_path)

    cmd = E3Commands(db_path)
    status_store_only = _capture(
        lambda: cmd.status(argparse.Namespace()))
    status_with_series = _capture(lambda: cmd.status(
        argparse.Namespace(pressure_series=[str(RECORDED_SERIES)])))
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    view_both = build_content_stop_pressure_view(
        con, series_paths=[RECORDED_SERIES])
    con.close()
    cmd.con.close()

    sections = [
        ("run_outcome", run["outcome"]),
        ("node_state", run["nodes"][0]["state"]),
        ("stub_dispatch_calls", adapter.calls),
        ("recorded_series_artifact", str(RECORDED_SERIES)),
        ("e3-status (store source only)", status_store_only),
        ("e3-status --pressure-series <recorded series>", status_with_series),
        ("pressure view (store + recorded series), key fields",
         "\n".join(_summarise(view_both))),
    ]

    if args.live_db:
        live_path = Path(args.live_db)
        live = sqlite3.connect(
            "file:%s?mode=ro" % str(live_path).replace("\\", "/").replace("?", "%3f"),
            uri=True)
        live.row_factory = sqlite3.Row
        try:
            live_view = build_content_stop_pressure_view(live)
        finally:
            live.close()
        sections.append((
            f"recorded rows of a real store, read-only ({live_path})",
            "\n".join(_summarise(live_view))))
        sections.append(("real-store operator lines (read-only)",
                         "\n".join(render_content_stop_pressure(live_view))))

    sections.append(("note", "Stub adapter only: 0 real provider calls, no "
                             "credential read, no network use. The store is an "
                             "isolated scratch DB. The recorded provider series "
                             "artifact is consumed verbatim; it was never re-run."))

    text = []
    for key, value in sections:
        if "\n" in str(value):
            text.append(f"===== {key} =====\n{value}")
        else:
            text.append(f"{key}: {value}")
    out_text = "\n".join(text) + "\n"
    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "operator_pressure_output.txt")
    out_path.write_text(out_text, encoding="utf-8")
    print(out_text)
    print(f"written to {out_path}")

    ok = (run["nodes"][0]["state"] == "BLOCKED"
          and "E4 Resource Continuity: provider content-side stop pressure"
          in status_store_only
          and "content-side stops observed: 3" in status_store_only
          and "stop rate: 1.000" in status_store_only
          and "sample size 3" in status_store_only
          and FINISH_REASON in status_store_only
          and "decision: observation only" in status_store_only
          and "stop rate: 0.222" in status_with_series
          and "sample size 9" in status_with_series
          and "content withheld at a measurable rate: yes" in status_with_series
          and view_both["content_stop_pressure_detected"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
