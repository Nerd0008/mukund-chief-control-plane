#!/usr/bin/env python3
"""Operator surface for the provider content-side stop terminal path.

The execution leg persists an unrecovered provider content-side stop in the
existing schema-v2 columns (node ``BLOCKED``, DAG transition cause
``provider_content_stop_unrecovered:<finishReason>``, evidence
``failure_attribution=provider_content_stop``). These tests drive that real code
path with a deterministic stub adapter (0 real provider calls, no credential,
no network) and then assert that the operator-facing surfaces
(``e3-status`` / ``e3-trace`` / ``e3-why``) read the attribution and the provider
finishReason back out for the operator.

Nothing here writes a new store schema and nothing here weakens a verification
criterion: the stub output fails the declared deterministic contract exactly as
the recorded provider behaviour did.
"""

import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from e3_commands import (  # noqa: E402
    E3Commands, finish_reason_from_cause, node_failure_view,
)
from e3_execution import (  # noqa: E402
    DEFAULT_MAX_CONTENT_STOP_RETRIES, E3ProductionExecutor,
    ExecutionAdapterRegistry, OrchestrationStore,
)
from e3_planner import E3Planner  # noqa: E402
from e3_team_assembly import TeamAssembly, TeamAssignment  # noqa: E402
from task_fingerprint import TaskFingerprint  # noqa: E402
from worker_registry import WorkerRegistry  # noqa: E402

GOOGLE_WORKER = "google-nano-banana-2"
FINISH_REASON = "IMAGE_RECITATION"
TERMINAL_CAUSE = f"provider_content_stop_unrecovered:{FINISH_REASON}"


class ContentStopAdapter:
    """Deterministic stub reproducing the recorded provider content-side stop.

    Mirrors the recorded provider-returned values (``finishReason`` +
    ``promptFeedback`` only, empty response part list, no image, 0 candidate
    tokens). No network call, no credential.
    """

    def __init__(self):
        self.calls = 0
        self.contracts = []

    def dispatch(self, contract):
        self.calls += 1
        self.contracts.append(dict(contract))
        return {
            "dispatch_id": f"stub-content-stop-{self.calls}",
            "status": "FAILED", "provider": "google",
            "model": "gemini-3.1-flash-image",
            "requested_model": "gemini-3.1-flash-image",
            "content": None, "image_b64": None, "image_mime": None,
            "image_size_bytes": None, "image_dims": None,
            "image_decode_ok": False, "finish_reason": FINISH_REASON,
            "candidate_count": 1,
            "candidate_finish_reasons": [FINISH_REASON],
            "response_part_kinds": [], "response_text_chars": None,
            "response_text_excerpt": None,
            "usage": {"promptTokenCount": 17, "totalTokenCount": 17},
            "prompt_feedback": None, "error": "no_image_part_in_response",
            "exit_code": 200, "runtime_s": 5.8,
        }


class PassingAdapter:
    """Deterministic stub delivering a well-formed output that verifies."""

    def __init__(self):
        self.calls = 0

    def dispatch(self, contract):
        self.calls += 1
        return {"dispatch_id": f"stub-ok-{self.calls}", "status": "COMPLETED",
                "provider": "google", "model": "gemini-3.1-flash-image",
                "content": "ok", "usage": None, "error": None,
                "exit_code": 0, "runtime_s": 0.1}


def _plan(plan_id, node_id, role):
    return {
        "plan_id": plan_id, "decomposition": False, "reason": "test",
        "nodes": [{
            "node_id": node_id, "objective": "operator surface test",
            "capability_roles": [role], "dependencies": [], "inputs": {},
            "expected_outputs": {}, "verification_method": "test",
            "floor_id": None, "allowed_tools": [], "permissions": {},
            "fallback_candidates": [],
        }],
    }


def _run_execution(db_path, adapter, plan_id, node_id):
    plan = _plan(plan_id, node_id, "vision")
    store = OrchestrationStore(db_path)
    registry = ExecutionAdapterRegistry(
        worker_registry=WorkerRegistry(),
        adapter_factories={GOOGLE_WORKER: lambda: adapter},
        usage_reporters={GOOGLE_WORKER: lambda r: None},
    )
    assembly = TeamAssembly(plan_id)
    assembly.assignments = [
        TeamAssignment(node_id, GOOGLE_WORKER, "vision", "HIGH", "test")]
    assembly.issues = []
    assembly.complete = True
    fingerprint = TaskFingerprint(
        task_family="code", reasoning_depth=1, risk_class="R1",
        required_roles=["vision"], verification_type="deterministic")
    dag = E3Planner().build_dag(plan)
    try:
        executor = E3ProductionExecutor(store, registry)
        return executor.execute_plan(
            plan, dag, assembly, fingerprint, "operator surface test",
            verification_test_cases_by_node={node_id: [
                {"name": "dispatch completed", "field": "status",
                 "expected": "COMPLETED"}]},
            max_repair_attempts=0, dispatch_timeout=5,
            role_by_node={node_id: "vision"})
    finally:
        store.close()


class _CommandCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "orchestration.db"

    def _commands(self):
        cmd = E3Commands(self.db_path)
        self.addCleanup(lambda: cmd.con is not None and cmd.con.close())
        return cmd

    def _capture(self, fn):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        return buf.getvalue()


class ContentStopOperatorSurfaceTests(_CommandCase):
    """A BLOCKED content-stop node must be visible to the operator."""

    PLAN_ID = "plan-operator-1"
    NODE_ID = "node-operator-1"

    def setUp(self):
        super().setUp()
        self.adapter = ContentStopAdapter()
        self.execution = _run_execution(self.db_path, self.adapter,
                                        self.PLAN_ID, self.NODE_ID)

    def test_the_real_path_really_reached_the_terminal_stop(self):
        node = self.execution["nodes"][0]
        self.assertEqual(node["state"], "BLOCKED")
        self.assertEqual(node["failure_attribution"], "provider_content_stop")
        self.assertEqual(node["failure_finish_reason"], FINISH_REASON)
        self.assertEqual(self.execution["outcome"], "EXECUTION_BLOCKED")
        self.assertEqual(self.adapter.calls,
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)

    def test_failure_view_reads_attribution_and_finish_reason(self):
        view = node_failure_view(self._commands()._connect(), self.NODE_ID)
        self.assertEqual(view["state"], "BLOCKED")
        self.assertEqual(view["failure_attribution"], "provider_content_stop")
        self.assertEqual(view["provider_finish_reason"], FINISH_REASON)
        self.assertEqual(view["content_stop_retries"],
                         DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(view["terminal_cause"], TERMINAL_CAUSE)
        self.assertEqual(view["assigned_worker"], GOOGLE_WORKER)
        self.assertTrue(view["content_stop"])

    def test_status_exposes_the_content_stop_attribution(self):
        out = self._capture(
            lambda: self._commands().status(argparse.Namespace()))
        self.assertIn("Node Failure Attribution", out)
        self.assertIn(self.NODE_ID, out)
        self.assertIn("provider_content_stop", out)
        self.assertIn(FINISH_REASON, out)
        self.assertIn(TERMINAL_CAUSE, out)

    def test_trace_exposes_the_content_stop_attribution_by_plan(self):
        out = self._capture(lambda: self._commands().trace(
            argparse.Namespace(task_id=self.PLAN_ID)))
        self.assertIn("Node failure attribution", out)
        self.assertIn("provider_content_stop", out)
        self.assertIn(FINISH_REASON, out)

    def test_trace_exposes_the_content_stop_attribution_by_node(self):
        out = self._capture(lambda: self._commands().trace(
            argparse.Namespace(task_id=self.NODE_ID)))
        self.assertIn("provider_content_stop", out)
        self.assertIn(FINISH_REASON, out)

    def test_why_exposes_the_content_stop_attribution(self):
        out = self._capture(lambda: self._commands().why(
            argparse.Namespace(node_id=self.NODE_ID)))
        self.assertIn("Persisted failure attribution", out)
        self.assertIn("provider_content_stop", out)
        self.assertIn(FINISH_REASON, out)
        self.assertIn(TERMINAL_CAUSE, out)

    def test_unknown_node_is_reported_as_unknown(self):
        out = self._capture(lambda: self._commands().why(
            argparse.Namespace(node_id="node-does-not-exist")))
        self.assertIn("No decision found for node", out)
        self.assertNotIn("provider_content_stop", out)


class CompleteNodeOperatorSurfaceTests(_CommandCase):
    """A verified COMPLETE node must never be reported as an attributed failure."""

    def test_complete_node_has_no_attribution(self):
        run = _run_execution(self.db_path, PassingAdapter(),
                             "plan-operator-2", "node-operator-2")
        self.assertEqual(run["nodes"][0]["state"], "COMPLETE")
        view = node_failure_view(self._commands()._connect(), "node-operator-2")
        self.assertEqual(view["state"], "COMPLETE")
        self.assertIsNone(view["failure_attribution"])
        self.assertIsNone(view["provider_finish_reason"])
        self.assertIsNone(view["terminal_cause"])
        self.assertFalse(view["content_stop"])

    def test_status_reports_no_attribution_for_a_complete_node(self):
        _run_execution(self.db_path, PassingAdapter(),
                       "plan-operator-3", "node-operator-3")
        out = self._capture(
            lambda: self._commands().status(argparse.Namespace()))
        self.assertIn("Node Failure Attribution", out)
        self.assertNotIn("provider_content_stop", out)
        self.assertNotIn("IMAGE_RECITATION", out)


class FinishReasonParsingTests(unittest.TestCase):
    """Parsing is limited to causes the execution leg actually writes."""

    def test_unrecovered_terminal_cause(self):
        self.assertEqual(
            finish_reason_from_cause("provider_content_stop_unrecovered:SAFETY"),
            "SAFETY")

    def test_same_request_retry_cause(self):
        self.assertEqual(
            finish_reason_from_cause(
                "content_stop_same_request_retry_2_after_IMAGE_RECITATION"),
            "IMAGE_RECITATION")

    def test_unrelated_cause_is_never_inferred(self):
        for cause in ("dispatch_attempt_1", "verified_pass_attempt_1",
                      "dependency_incomplete", None, ""):
            self.assertIsNone(finish_reason_from_cause(cause))

    def test_cause_without_a_finish_reason_is_none(self):
        self.assertIsNone(
            finish_reason_from_cause("provider_content_stop_unrecovered:"))
        self.assertIsNone(
            finish_reason_from_cause("content_stop_same_request_retry_1"))


if __name__ == "__main__":
    unittest.main()
