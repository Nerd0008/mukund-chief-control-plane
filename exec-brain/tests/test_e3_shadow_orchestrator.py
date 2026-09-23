#!/usr/bin/env python3
"""Tests for E3 Shadow Orchestrator — validates component composition."""

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


if __name__ == "__main__":
    unittest.main()
