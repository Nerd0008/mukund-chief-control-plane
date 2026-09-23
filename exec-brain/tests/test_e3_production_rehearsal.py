#!/usr/bin/env python3
"""Tests for the E3 production rehearsal: real-path evidence, verifier
rejection/repair/re-verification, evidence isolation and the E1/E2 boundary."""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from e3_production_rehearsal import (  # noqa: E402
    E3ProductionRehearsal, EvidenceIsolationGuard, RehearsalEvidenceSink,
    RehearsalIsolationError, RUNTIME_ROOT, scan_e1_e2_boundary,
)


class TestEvidenceIsolationGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="e3-iso-test-"))
        self.guard = EvidenceIsolationGuard({
            "orchestration": RUNTIME_ROOT / "orchestration.db",
            "governor": RUNTIME_ROOT / "governor.db",
            "exec_brain": RUNTIME_ROOT / "exec_brain.db",
        })

    def test_production_stores_classified(self):
        self.assertTrue(self.guard.is_production_store(RUNTIME_ROOT / "orchestration.db"))
        self.assertTrue(self.guard.is_production_store(RUNTIME_ROOT / "governor.db"))
        self.assertTrue(self.guard.is_production_store(RUNTIME_ROOT / "exec_brain.db"))
        # anything else inside the live runtime root is production too
        self.assertTrue(self.guard.is_production_store(RUNTIME_ROOT / "other.db"))

    def test_rehearsal_store_classified(self):
        self.assertFalse(self.guard.is_production_store(self.tmp / "rehearsal.db"))

    def test_guard_write_fails_closed_on_production(self):
        with self.assertRaises(RehearsalIsolationError):
            self.guard.guard_write(RUNTIME_ROOT / "orchestration.db",
                                   rehearsal_evidence=True)

    def test_guard_write_allows_rehearsal_store(self):
        self.guard.guard_write(self.tmp / "rehearsal.db", rehearsal_evidence=True)

    def test_sink_refuses_production_store(self):
        with self.assertRaises(RehearsalIsolationError):
            RehearsalEvidenceSink(RUNTIME_ROOT / "orchestration.db", self.guard,
                                  rehearsal=True)

    def test_sink_refuses_to_persist_rehearsal_evidence_to_production(self):
        sink = RehearsalEvidenceSink(self.tmp / "rehearsal_evidence.json",
                                     self.guard, rehearsal=True)
        sink.persist({"scenario": "x"})
        self.assertEqual(len(sink.records), 1)
        # A rehearsal sink re-pointed at a production store must still fail closed.
        sink.store_path = RUNTIME_ROOT / "orchestration.db"
        with self.assertRaises(RehearsalIsolationError):
            sink.persist({"scenario": "y"})

    def test_capture_and_unchanged(self):
        before = self.guard.capture()
        ok, diffs = self.guard.assert_unchanged()
        self.assertTrue(ok)
        self.assertEqual(diffs, [])
        self.assertIn("orchestration", before)


class TestE1E2BoundaryScan(unittest.TestCase):
    def test_no_direct_sql_writes_to_e1_e2_stores(self):
        report = scan_e1_e2_boundary()
        self.assertEqual(report["direct_sql_violations"], [])
        self.assertTrue(report["clean"])

    def test_adapters_use_public_e2_interface(self):
        report = scan_e1_e2_boundary()
        for module in ("codex_adapter.py", "deepseek_adapter.py",
                       "gemini_adapter.py", "generic_openai_adapter.py"):
            self.assertIn(module, report["e2_public_interface_modules"])


class TestPlannerNodeIds(unittest.TestCase):
    """The planner must emit stable node ids shared by DAG, router and assembly."""

    def _plan(self, **kw):
        from e3_planner import E3Planner
        from task_fingerprint import TaskFingerprint
        fp = TaskFingerprint(**kw)
        return fp, E3Planner().plan("node id test", fp)

    def test_single_node_plan_has_node_id(self):
        _, plan = self._plan(task_family="code", reasoning_depth=1,
                             risk_class="R1", required_roles=["builder"])
        self.assertEqual(len(plan["nodes"]), 1)
        self.assertTrue(plan["nodes"][0]["node_id"])

    def test_decomposed_plan_node_ids_are_unique(self):
        _, plan = self._plan(task_family="code", reasoning_depth=4, risk_class="R1",
                             required_roles=["builder", "vision"],
                             integration_complexity="medium")
        ids = [n["node_id"] for n in plan["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ids))

    def test_dag_node_ids_match_plan_node_ids(self):
        from e3_planner import E3Planner
        fp, plan = self._plan(task_family="code", reasoning_depth=4, risk_class="R1",
                              required_roles=["builder", "vision"],
                              integration_complexity="medium")
        dag = E3Planner().build_dag(plan)
        self.assertEqual(set(dag.nodes.keys()),
                         {n["node_id"] for n in plan["nodes"]})

    def test_deterministic_verification_type_maps_to_valid_method(self):
        from e3_planner import E3Planner
        from task_fingerprint import TaskFingerprint
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R1",
                             required_roles=["builder"], verification_type="deterministic")
        self.assertEqual(E3Planner.verification_method_for(fp), "test")
        plan = E3Planner().plan("deterministic task", fp)
        for node in plan["nodes"]:
            self.assertIn(node["verification_method"],
                          ("test", "schema", "comparison", "critic", "owner"))


class TestProductionRehearsalRun(unittest.TestCase):
    """One real rehearsal run, asserted scenario by scenario."""

    @classmethod
    def setUpClass(cls):
        cls.rehearsal = E3ProductionRehearsal()
        cls.report = cls.rehearsal.run(include_e2=True)
        cls.by_objective = {s.get("task_objective"): s
                            for s in cls.report["scenarios"]}

    def test_five_scenarios_recorded(self):
        self.assertEqual(len(self.report["scenarios"]), 5)

    def test_rejection_then_targeted_repair_then_reverify_passes(self):
        s = self.by_objective["Rehearsal: deterministic validation task"]
        self.assertEqual(s["verifier_rejections"], 1)
        self.assertEqual(s["repair_attempts"], 1)
        self.assertEqual(s["verification_attempts"], 2)
        first, second = s["verification_attempts_detail"]
        self.assertEqual(first["outcome"], "FAIL")
        self.assertEqual(second["outcome"], "PASS")
        self.assertTrue(s["verification_results"]["integration"]["passed"])
        self.assertFalse(s["verification_results"]["integration"]["first_attempt_passed"])
        self.assertTrue(s["verification_results"]["integration"]["repaired"])
        self.assertEqual(s["outcome"], "REHEARSAL_PASSED")

    def test_rejection_without_repair_replans_and_escalates(self):
        s = self.by_objective["Rehearsal: unrepaired rejection task"]
        self.assertFalse(s["verification_results"]["integration"]["passed"])
        self.assertGreaterEqual(len(s["replan_history"]), 1)
        self.assertIsNotNone(s["escalation"])
        self.assertEqual(s["escalation"]["trigger"], "repeated_failure")

    def test_no_qualified_route_is_never_fabricated(self):
        s = self.by_objective["Rehearsal: task family with no seeded worker"]
        self.assertEqual(s["candidates_found"], 0)
        self.assertFalse(s["team_complete"])
        self.assertIsNotNone(s["escalation"])
        self.assertEqual(s["escalation"]["trigger"], "no_qualified_worker")

    def test_decomposed_run_routes_real_workers_and_has_integrator_node(self):
        s = self.by_objective["Rehearsal: decomposed multi-node task"]
        self.assertTrue(s["decomposition"])
        self.assertTrue(s["integrator_node_present"])
        self.assertEqual(s["node_count"], 3)
        assigned = {a["worker"] for a in s["team_assignments"]}
        self.assertIn("codex-cli", assigned)
        self.assertIn("google-nano-banana-2", assigned)
        self.assertTrue(s["verification_results"]["integration"]["passed"])

    def test_conflict_scenario_detects_real_contradiction(self):
        s = self.by_objective["Rehearsal: contradictory multi-node task"]
        detail = s.get("conflicts_detected_detail") or []
        claims = [c.get("disputed_claim", "") for c in detail]
        self.assertTrue(any("value-A vs value-B" in c for c in claims),
                        msg=f"claims={claims!r} detail={detail!r}")
        self.assertEqual(s["outcome"], "REHEARSAL_CONFLICTS")

    def test_evidence_is_sealed_to_the_rehearsal_store(self):
        store = Path(self.report["rehearsal_evidence_store"])
        self.assertTrue(store.exists())
        payload = json.loads(store.read_text(encoding="utf-8"))
        self.assertEqual(payload["store"], "rehearsal")
        self.assertTrue(payload["simulated"])
        self.assertGreater(len(payload["records"]), 0)

    def test_production_stores_unchanged_by_rehearsal(self):
        iso = self.report["isolation"]
        self.assertTrue(iso["production_stores_unchanged"])
        self.assertEqual(iso["diffs"], [])

    def test_rehearsal_store_is_not_a_production_store(self):
        guard = EvidenceIsolationGuard()
        self.assertFalse(guard.is_production_store(self.report["rehearsal_orchestration_db"]))

    def test_no_worker_marked_qualified(self):
        db = self.report["rehearsal_orchestration_db"]
        con = sqlite3.connect(db)
        try:
            states = [r[0] for r in con.execute(
                "SELECT DISTINCT state FROM capability_registry").fetchall()]
        finally:
            con.close()
        self.assertIn("EVALUATING", states)
        self.assertNotIn("QUALIFIED", states)

    def test_e2_public_interface_isolated(self):
        e2 = self.report["e2_public_interface"]
        self.assertTrue(e2["available"])
        self.assertEqual(e2["interface"], "governor.record_request")
        guard = EvidenceIsolationGuard()
        self.assertFalse(guard.is_production_store(e2["isolated_store"]))
        self.assertEqual(e2["row_readback"][1], "rehearsal")


if __name__ == "__main__":
    unittest.main()
