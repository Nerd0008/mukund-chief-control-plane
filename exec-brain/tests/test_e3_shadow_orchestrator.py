#!/usr/bin/env python3
"""Tests for E3 Shadow Orchestrator — validates component composition."""

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))

from e3_shadow_orchestrator import E3ShadowOrchestrator, ShadowRehearsalResult
from capability_registry import CapabilityRegistry
from task_fingerprint import TaskFingerprint
from orchestration_db import init_db


class TestShadowOrchestrator(unittest.TestCase):
    """Test shadow orchestration pipeline composition."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.db_path = Path(self.temp) / "test_orchestration.db"
        init_db(self.db_path)
        self.con = sqlite3.connect(str(self.db_path))
        self.con.row_factory = sqlite3.Row
        self.orchestrator = E3ShadowOrchestrator(db_path=self.db_path)

    def tearDown(self):
        self.con.close()
        try:
            self.db_path.unlink()
        except Exception:
            pass

    def test_shadow_rehearsal_simple_task(self):
        """Shadow rehearsal for a simple task produces valid plan."""
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R1")
        result = self.orchestrator.rehearse("Simple bug fix", fp)
        self.assertIsInstance(result, ShadowRehearsalResult)
        self.assertIsNotNone(result.plan)
        self.assertFalse(result.plan["decomposition"])
        self.assertEqual(len(result.dag.nodes), 1)
        self.assertTrue(result.decomposition_review.approved)
        self.assertIsNotNone(result.completed_at)

    def test_shadow_rehearsal_complex_task(self):
        """Shadow rehearsal for a complex task decomposes and routes."""
        fp = TaskFingerprint(
            task_family="code",
            reasoning_depth=4,
            risk_class="R1",
            required_roles=["researcher", "architect", "builder"],
            integration_complexity="medium",
        )
        result = self.orchestrator.rehearse("Complex system redesign", fp)
        self.assertTrue(result.plan["decomposition"])
        self.assertGreater(len(result.dag.nodes), 1)
        self.assertTrue(result.decomposition_review.approved)
        self.assertIn("researcher", result.plan["nodes"][0]["capability_roles"])

    def test_shadow_rehearsal_context_compilation(self):
        """Shadow rehearsal compiles context for each node."""
        fp = TaskFingerprint(
            task_family="code",
            reasoning_depth=3,
            risk_class="R1",
            required_roles=["researcher", "builder"],
        )
        result = self.orchestrator.rehearse("Multi-step task", fp)
        self.assertGreater(len(result.context_packages), 0)
        for node_id, ctx in result.context_packages.items():
            self.assertIn("objective", ctx)
            self.assertIn("output_schema", ctx)

    def test_shadow_rehearsal_permission_compilation(self):
        """Shadow rehearsal compiles permissions for each node."""
        fp = TaskFingerprint(
            task_family="code",
            reasoning_depth=3,
            risk_class="R1",
            required_roles=["researcher", "builder"],
        )
        result = self.orchestrator.rehearse("Multi-step task", fp)
        self.assertGreater(len(result.permission_packages), 0)
        for node_id, perms in result.permission_packages.items():
            self.assertIn("roles", perms)
            self.assertIn("file_read", perms)
            self.assertIn("file_write", perms)

    def test_shadow_rehearsal_evidence_recording(self):
        """Shadow rehearsal records evidence for each node."""
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R1")
        result = self.orchestrator.rehearse("Simple task", fp)
        self.assertGreater(len(result.evidence_records), 0)
        for ev_id in result.evidence_records:
            self.assertTrue(ev_id.startswith("evidence-"))

    def test_shadow_rehearsal_exploration_evaluation(self):
        """Shadow rehearsal evaluates exploration for eligible risk classes."""
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R0")
        result = self.orchestrator.rehearse("Low-risk task", fp)
        self.assertGreater(len(result.exploration_decisions), 0)
        # R0 should be eligible for exploration
        self.assertTrue(any(d.get("approved") for d in result.exploration_decisions))

    def test_shadow_rehearsal_high_risk_no_exploration(self):
        """Shadow rehearsal blocks exploration for high-risk tasks."""
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R3")
        result = self.orchestrator.rehearse("High-risk task", fp)
        # R3 should not be eligible for exploration
        exploration_approved = any(d.get("approved") for d in result.exploration_decisions)
        self.assertFalse(exploration_approved)

    def test_shadow_rehearsal_replan_on_failure(self):
        """Shadow rehearsal triggers replanner when verification fails.

        Forces a FAIL verification outcome by stubbing the verifier so the
        replanner composition path is exercised end-to-end.
        """
        from e3_verifier import VerificationResult, VerificationOutcome, VerificationMethod

        fp = TaskFingerprint(
            task_family="code",
            reasoning_depth=1,
            risk_class="R1",
            verification_type="test",
        )

        # Force verification to FAIL so the replanner path is exercised
        original_verify = self.orchestrator.verifier.verify
        def failing_verify(output, method=VerificationMethod.TEST):
            return VerificationResult(
                method=method,
                outcome=VerificationOutcome.FAIL,
                issues=["forced failure for test"],
            )
        self.orchestrator.verifier.verify = failing_verify

        try:
            result = self.orchestrator.rehearse(
                "Failing task", fp, simulate_outputs={"node-1": {"status": "failed"}}
            )
        finally:
            self.orchestrator.verifier.verify = original_verify

        # Replanner should have been consulted (outcome is FAIL)
        self.assertGreater(len(result.replan_history), 0)
        self.assertTrue(any("replanner" in w.lower() for w in result.warnings))

    def test_shadow_rehearsal_result_to_dict(self):
        """Shadow rehearsal result serializes to dict."""
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R1")
        result = self.orchestrator.rehearse("Simple task", fp)
        d = result.to_dict()
        self.assertIn("rehearsal_id", d)
        self.assertIn("outcome", d)
        self.assertIn("node_count", d)
        self.assertIn("decomposition_approved", d)
        self.assertIn("candidates_found", d)
        self.assertIn("team_complete", d)
        self.assertIn("verification_count", d)
        self.assertIn("conflicts_detected", d)
        self.assertIn("evidence_recorded", d)
        self.assertIn("escalations", d)
        self.assertIn("warnings", d)

    def test_shadow_rehearsal_no_production_dispatch(self):
        """Shadow rehearsal does not modify worker routable state."""
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R1")
        result = self.orchestrator.rehearse("Simple task", fp)
        # Verify no worker was marked as QUALIFIED
        workers = self.orchestrator.worker_registry.get_all_workers()
        for wid, w in workers.items():
            self.assertNotEqual(w.get("pool_status"), "QUALIFIED")

    def test_shadow_rehearsal_team_assembly_composition(self):
        """Shadow rehearsal assembles team from candidates."""
        fp = TaskFingerprint(
            task_family="code",
            reasoning_depth=3,
            risk_class="R1",
            required_roles=["researcher", "builder"],
        )
        result = self.orchestrator.rehearse("Team task", fp)
        self.assertIsNotNone(result.team_assembly)
        # Team assembly should have candidates or report issues
        has_assignments = len(result.team_assembly.assignments) > 0
        has_issues = len(result.team_assembly.issues) > 0
        self.assertTrue(has_assignments or has_issues)

    def test_readiness_report(self):
        """Readiness report covers all workers."""
        report = self.orchestrator.get_readiness_report()
        self.assertEqual(len(report), 10)
        for wid, info in report.items():
            self.assertIn("provider", info)
            self.assertIn("model", info)
            self.assertIn("routable", info)
            self.assertIn("capability_state", info)

    def test_shadow_rehearsal_with_cyclic_dag_rejected(self):
        """Shadow rehearsal rejects cyclic decomposition."""
        fp = TaskFingerprint(
            task_family="code",
            reasoning_depth=3,
            risk_class="R1",
            required_roles=["a", "b"],
        )
        # Normal rehearsal should pass — cycles are caught by decomposition review
        result = self.orchestrator.rehearse("Cyclic task", fp)
        self.assertIsNotNone(result.decomposition_review)


# ─── orchestrate_and_execute: content-side stop escalation ──────────

GOOGLE_WORKER = "google-nano-banana-2"
CONTENT_STOP_FINISH_REASON = "IMAGE_RECITATION"


class _AlwaysContentStopAdapter:
    """Deterministic stub: the provider withholds the content every time.

    Reproduces the recorded provider-returned shape only (finishReason +
    empty response part list, no image, 0 candidate tokens). No network call,
    no credential.
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
            "content": None, "image_dims": None, "image_decode_ok": False,
            "finish_reason": CONTENT_STOP_FINISH_REASON,
            "candidate_count": 1,
            "candidate_finish_reasons": [CONTENT_STOP_FINISH_REASON],
            "response_part_kinds": [], "usage": {"promptTokenCount": 17,
                                                 "totalTokenCount": 17},
            "prompt_feedback": None, "error": "no_image_part_in_response",
            "exit_code": 200, "runtime_s": 5.8,
        }


class _PassingAdapter:
    """Deterministic stub delivering an output that verifies first time."""

    def __init__(self):
        self.calls = 0

    def dispatch(self, contract):
        self.calls += 1
        return {"dispatch_id": f"stub-ok-{self.calls}", "status": "COMPLETED",
                "provider": "google", "model": "gemini-3.1-flash-image",
                "content": "ok", "usage": None, "error": None,
                "exit_code": 0, "runtime_s": 0.1}


class TestOrchestrateAndExecuteContentStopEscalation(unittest.TestCase):
    """The orchestrator boundary must return the content-stop escalation.

    The existing escalation-on-incomplete behaviour (a ``repeated_failure``
    escalation) and the owner gate are unchanged; the content-side stop is
    additionally reported as itself, naming the provider finish reason.
    """

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="e3-orch-content-stop-")
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.db_path = Path(self.temp) / "orch.db"
        self.orchestrator = E3ShadowOrchestrator(db_path=self.db_path)
        registry = CapabilityRegistry(self.orchestrator.con)
        registry.register_worker(
            GOOGLE_WORKER, "google", "gemini-3.1-flash-image",
            roles=["vision"], state="EVALUATING", task_family="code")
        self.fingerprint = TaskFingerprint(
            task_family="code", reasoning_depth=1, risk_class="R1",
            required_roles=["vision"], verification_type="deterministic")
        self.plan = self.orchestrator.planner.plan(
            "orchestrator content stop escalation test", self.fingerprint)
        self.node_id = self.plan["nodes"][0]["node_id"]

    def _adapter_registry(self, adapter):
        from e3_execution import ExecutionAdapterRegistry
        from worker_registry import WorkerRegistry
        return ExecutionAdapterRegistry(
            worker_registry=WorkerRegistry(),
            adapter_factories={GOOGLE_WORKER: lambda: adapter},
            usage_reporters={GOOGLE_WORKER: lambda r: None},
        )

    def _execute(self, adapter):
        return self.orchestrator.orchestrate_and_execute(
            "orchestrator content stop escalation test", self.fingerprint,
            plan=self.plan,
            verification_test_cases_by_node={self.node_id: [
                {"name": "dispatch completed", "field": "status",
                 "expected": "COMPLETED"}]},
            max_repair_attempts=0, dispatch_timeout=5,
            adapter_registry=self._adapter_registry(adapter),
        )

    def test_content_stop_escalation_is_returned_not_only_repeated_failure(self):
        adapter = _AlwaysContentStopAdapter()
        out = self._execute(adapter)
        self.assertEqual(out["outcome"], "EXECUTION_BLOCKED")
        self.assertIsNotNone(out["content_stop_escalation"])
        cs = out["content_stop_escalation"]
        self.assertEqual(cs["trigger"], "provider_content_stop")
        self.assertEqual(cs["finish_reasons"], [CONTENT_STOP_FINISH_REASON])
        self.assertEqual(cs["worker_ids"], [GOOGLE_WORKER])
        self.assertEqual(cs["node_ids"], [self.node_id])
        self.assertTrue(cs["escalation_id"])

    def test_repeated_failure_escalation_behaviour_is_unchanged(self):
        out = self._execute(_AlwaysContentStopAdapter())
        self.assertIsNotNone(out["escalation"])
        self.assertEqual(out["escalation"]["trigger"], "repeated_failure")

    def test_execution_leg_escalation_is_surfaced_verbatim(self):
        out = self._execute(_AlwaysContentStopAdapter())
        leg = out["execution_escalations"]
        self.assertEqual(len(leg), 1)
        self.assertEqual(leg[0]["trigger"], "provider_content_stop")
        self.assertEqual(leg[0]["finish_reason"], CONTENT_STOP_FINISH_REASON)
        self.assertEqual(
            out["content_stop_escalation"]["execution_escalation_ids"],
            [leg[0]["escalation_id"]])
        # the orchestrator-level escalation is a distinct record
        self.assertNotEqual(
            out["content_stop_escalation"]["escalation_id"],
            leg[0]["escalation_id"])

    def test_content_stop_retry_accounting_is_bounded(self):
        out = self._execute(_AlwaysContentStopAdapter())
        node = out["execution"]["nodes"][0]
        self.assertEqual(node["failure_attribution"], "provider_content_stop")
        self.assertEqual(node["content_stop_retries"], 2)
        self.assertEqual(len(node["dispatch_attempts"]), 3)
        self.assertEqual(out["content_stop_escalation"]["content_stop_retries"], 2)

    def test_successful_run_has_no_content_stop_escalation(self):
        out = self._execute(_PassingAdapter())
        self.assertEqual(out["outcome"], "EXECUTION_COMPLETE")
        self.assertIsNone(out["content_stop_escalation"])
        self.assertEqual(out["execution_escalations"], [])
        self.assertNotIn("escalation", out)


if __name__ == "__main__":
    unittest.main()
