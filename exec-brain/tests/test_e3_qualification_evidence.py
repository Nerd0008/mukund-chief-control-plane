#!/usr/bin/env python3
"""Tests for evidence-backed E3 worker qualification.

These tests assert the truth rules of the qualification harness:

* a worker with no recorded execution is never qualified;
* a synthetic/fixture suite can never produce a qualification;
* a single observation never clears the repeatability bar;
* every check reads recorded rows, and a check that cannot be evaluated is
  reported ``INCONCLUSIVE`` — never as a pass;
* the capability registry refuses a QUALIFIED row with zero evidence.

All fixtures are written into a throwaway sqlite file created from the real
schema; no provider is contacted and no live store is touched.
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The repository checkout is the source of truth for E3 source; the deployed
# runtime root is the fallback so the suite is runnable from either location.
for candidate in (REPO_ROOT / "exec-brain", RUNTIME_ROOT):
    if (Path(candidate) / "orchestration_db.py").exists():
        sys.path.insert(0, str(candidate))
        break

from e3_qualification_benchmark import (
    ColdStartBenchmark, EvidenceBackedBenchmark, QualificationState,
    MIN_RECORDED_EXECUTIONS, MIN_RECORDED_PASSES, registry_state_for,
)
from capability_registry import CapabilityRegistry
from orchestration_db import init_db


def _add_node(con, node_id, state="COMPLETE", plan_id="plan-test",
              worker="w1"):
    con.execute(
        "INSERT OR REPLACE INTO dag_node (node_id, plan_id, objective, "
        "capability_roles, dependencies, verification_method, assigned_worker, "
        "state, attempts) VALUES (?,?,?,?,?,?,?,?,?)",
        (node_id, plan_id, "test objective", '["builder"]', "[]", "test",
         worker, state, 1))
    con.commit()


def _add_evidence(con, evidence_id, worker_id, role, final_success=1,
                  first_pass_success=1,
                  verification_outcome: "str | None" = "PASS",
                  provider="deepseek", model="deepseek-flash",
                  dag_node_id="node-1", timestamp=None, retries=0,
                  corrections=0):
    con.execute(
        "INSERT OR REPLACE INTO performance_evidence (evidence_id, worker_id, "
        "task_fingerprint, role, model, provider, first_pass_success, "
        "final_success, verification_outcome, retries, corrections, dag_node_id, "
        "timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, COALESCE(?, datetime('now')))",
        (evidence_id, worker_id, "fp-test", role, model, provider,
         first_pass_success, final_success, verification_outcome, retries,
         corrections, dag_node_id, timestamp))
    con.commit()


class TestEvidenceBackedQualification(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="e3-qual-test-")
        self.db = Path(self.tmp) / "orchestration.db"
        self.con = init_db(self.db)
        self.con.row_factory = sqlite3.Row
        self.bench = EvidenceBackedBenchmark(self.con)

    def tearDown(self):
        self.con.close()

    # ── no evidence ────────────────────────────────────────────────
    def test_no_evidence_is_not_qualified(self):
        result = self.bench.evaluate("w-none", "builder")
        self.assertEqual(result.overall_state, QualificationState.NOT_RUN)
        self.assertEqual(registry_state_for(result), "UNPROVEN")
        self.assertEqual(result.evidence_counts.get("recorded_executions"), 0)
        self.assertTrue(all(t.get("state") == "inconclusive"
                            for t in result.test_results))

    def test_scopes_only_include_workers_with_recorded_evidence(self):
        self.assertEqual(self.bench.candidate_scopes(), [])
        _add_node(self.con, "node-1")
        _add_evidence(self.con, "ev-1", "w1", "builder")
        self.assertEqual(self.bench.candidate_scopes(),
                         [{"worker_id": "w1", "role": "builder"}])

    # ── the repeatability bar ──────────────────────────────────────
    def test_single_observation_never_qualifies(self):
        _add_node(self.con, "node-1")
        _add_evidence(self.con, "ev-1", "w1", "builder")
        result = self.bench.evaluate("w1", "builder")
        self.assertEqual(result.overall_state, QualificationState.INCONCLUSIVE)
        self.assertEqual(registry_state_for(result), "EVALUATING")
        repeat = [t for t in result.test_results
                  if t["test_name"] == "repeatability"][0]
        self.assertEqual(repeat["state"], "inconclusive")
        self.assertIsNone(repeat["passed"])

    def test_two_passes_with_a_first_pass_qualifies(self):
        _add_node(self.con, "node-1")
        _add_node(self.con, "node-2")
        _add_evidence(self.con, "ev-1", "w1", "builder", dag_node_id="node-1")
        _add_evidence(self.con, "ev-2", "w1", "builder", dag_node_id="node-2",
                      first_pass_success=0, retries=1, corrections=1)
        result = self.bench.evaluate("w1", "builder")
        self.assertEqual(result.overall_state, QualificationState.PASS)
        self.assertEqual(registry_state_for(result), "QUALIFIED")
        self.assertEqual(result.evidence_counts["recorded_executions"], 2)
        self.assertEqual(result.evidence_counts["recorded_first_pass_passes"], 1)

    def test_min_bar_constants_are_enforced(self):
        _add_node(self.con, "node-1")
        _add_evidence(self.con, "ev-1", "w1", "builder")
        result = self.bench.evaluate("w1", "builder")
        self.assertLess(result.evidence_counts["recorded_passes"],
                        MIN_RECORDED_PASSES)
        self.assertLess(result.evidence_counts["recorded_executions"],
                        MIN_RECORDED_EXECUTIONS)
        self.assertNotEqual(result.overall_state, QualificationState.PASS)

    # ── bad evidence is caught, never smoothed over ────────────────
    def test_simulated_provider_row_fails_the_evidence_check(self):
        _add_node(self.con, "node-1")
        _add_evidence(self.con, "ev-1", "w1", "builder", provider="stub")
        _add_evidence(self.con, "ev-2", "w1", "builder")
        result = self.bench.evaluate("w1", "builder")
        check = [t for t in result.test_results
                 if t["test_name"] == "recorded-real-execution"][0]
        self.assertEqual(check["state"], "fail")
        self.assertEqual(result.overall_state, QualificationState.FAIL)
        self.assertNotEqual(registry_state_for(result), "QUALIFIED")

    def test_missing_deterministic_verdict_fails_the_gating_check(self):
        _add_node(self.con, "node-1")
        _add_evidence(self.con, "ev-1", "w1", "builder",
                      verification_outcome=None)
        result = self.bench.evaluate("w1", "builder")
        check = [t for t in result.test_results
                 if t["test_name"] == "deterministic-verification-gating"][0]
        self.assertEqual(check["state"], "fail")

    def test_uncorroborated_complete_fails_the_dag_check(self):
        _add_node(self.con, "node-1")
        _add_node(self.con, "node-2", state="FAILED")
        _add_evidence(self.con, "ev-1", "w1", "builder", dag_node_id="node-1")
        _add_evidence(self.con, "ev-2", "w1", "builder", dag_node_id="node-2")
        result = self.bench.evaluate("w1", "builder")
        check = [t for t in result.test_results
                 if t["test_name"] == "dag-state-corroborated"][0]
        self.assertEqual(check["state"], "fail")

    def test_latest_failing_execution_blocks_qualification(self):
        _add_node(self.con, "node-1")
        _add_evidence(self.con, "ev-1", "w1", "builder", dag_node_id="node-1",
                      timestamp="2026-01-01 00:00:00")
        _add_evidence(self.con, "ev-2", "w1", "builder", dag_node_id="node-1",
                      final_success=0, first_pass_success=0,
                      verification_outcome="FAIL",
                      timestamp="2026-01-02 00:00:00")
        result = self.bench.evaluate("w1", "builder")
        check = [t for t in result.test_results
                 if t["test_name"] == "latest-execution-not-failing"][0]
        self.assertEqual(check["state"], "fail")
        self.assertNotEqual(registry_state_for(result), "QUALIFIED")

    # ── the registry refuses an unearned qualification ─────────────
    def test_registry_refuses_qualified_with_zero_evidence(self):
        reg = CapabilityRegistry(self.con)
        with self.assertRaises(ValueError):
            reg.record_qualification(
                worker_id="w1", task_family="code", capability_role="builder",
                state="QUALIFIED", evidence_count=0, first_pass_successes=0,
                first_pass_attempts=0, reason="unearned")

    def test_registry_records_decision_with_audit_event(self):
        reg = CapabilityRegistry(self.con)
        recorded = reg.record_qualification(
            worker_id="w1", task_family="code", capability_role="builder",
            state="EVALUATING", evidence_count=1, first_pass_successes=1,
            first_pass_attempts=1, reason="one recorded execution",
            evidence_references=["ev-1"])
        self.assertEqual(recorded["new_state"], "EVALUATING")
        row = self.con.execute(
            "SELECT state, evidence_count FROM capability_registry "
            "WHERE worker_id='w1' AND capability_role='builder'").fetchone()
        self.assertEqual(row["state"], "EVALUATING")
        self.assertEqual(row["evidence_count"], 1)
        events = self.con.execute(
            "SELECT new_state, actor FROM worker_capability_event").fetchall()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["new_state"], "EVALUATING")

    # ── the fixture harness can never produce a qualification ──────
    def test_fixture_benchmark_is_never_qualification_evidence(self):
        fixture = ColdStartBenchmark()
        result = fixture.run_qualification("w1", "code", "builder")
        self.assertFalse(result.evidence_backed)
        self.assertNotEqual(result.overall_state, QualificationState.PASS)
        self.assertEqual(registry_state_for(result), "UNPROVEN")
        self.assertTrue((result.notes or "").startswith("fixture harness"))

    def test_non_evidence_backed_result_never_maps_to_qualified(self):
        from e3_qualification_benchmark import QualificationResult
        result = QualificationResult("w1", "code", "builder")
        result.overall_state = QualificationState.PASS
        result.evidence_backed = False
        self.assertEqual(registry_state_for(result), "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
