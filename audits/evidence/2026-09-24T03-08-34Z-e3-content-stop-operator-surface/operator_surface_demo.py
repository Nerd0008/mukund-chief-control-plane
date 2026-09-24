#!/usr/bin/env python3
"""Capture the operator surface for a persisted content-side stop terminal path.

Builds an isolated orchestration store by running the real E3 execution leg with
a deterministic stub adapter (0 real provider calls, no credential, no network),
then prints ``e3-status`` / ``e3-trace`` / ``e3-why`` for that store so the
attribution and the provider finishReason are observable exactly as an operator
would see them.

Usage: python operator_surface_demo.py [--out PATH]
"""

import argparse
import contextlib
import io
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
from task_fingerprint import TaskFingerprint  # noqa: E402
from worker_registry import WorkerRegistry  # noqa: E402

GOOGLE_WORKER = "google-nano-banana-2"
FINISH_REASON = "IMAGE_RECITATION"
PLAN_ID = "plan-operator-demo"
NODE_ID = "node-operator-demo"


class ContentStopAdapter:
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
            "node_id": NODE_ID, "objective": "operator surface demo",
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
            "operator surface demo",
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="e3-operator-demo-"))
    db_path = tmp / "orchestration.db"
    run, adapter = _build_store(db_path)

    cmd = E3Commands(db_path)
    sections = {
        "run_outcome": run["outcome"],
        "node_state": run["nodes"][0]["state"],
        "failure_attribution": run["nodes"][0]["failure_attribution"],
        "failure_finish_reason": run["nodes"][0]["failure_finish_reason"],
        "stub_dispatch_calls": adapter.calls,
        "e3-status": _capture(lambda: cmd.status(argparse.Namespace())),
        "e3-trace": _capture(
            lambda: cmd.trace(argparse.Namespace(task_id=PLAN_ID))),
        "e3-why": _capture(
            lambda: cmd.why(argparse.Namespace(node_id=NODE_ID))),
        "note": ("Stub adapter only: 0 real provider calls, no credential read, "
                 "no network use. The store is an isolated scratch DB."),
    }
    cmd.con.close()

    text = []
    for key, value in sections.items():
        if "\n" in str(value):
            text.append(f"===== {key} =====\n{value}")
        else:
            text.append(f"{key}: {value}")
    out_text = "\n".join(text) + "\n"
    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "operator_surface_output.txt")
    out_path.write_text(out_text, encoding="utf-8")
    print(out_text)
    print(f"written to {out_path}")
    ok = (sections["node_state"] == "BLOCKED"
          and sections["failure_attribution"] == "provider_content_stop"
          and sections["failure_finish_reason"] == FINISH_REASON
          and "provider_content_stop" in sections["e3-status"]
          and FINISH_REASON in sections["e3-status"]
          and "provider_content_stop" in sections["e3-trace"]
          and FINISH_REASON in sections["e3-why"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
