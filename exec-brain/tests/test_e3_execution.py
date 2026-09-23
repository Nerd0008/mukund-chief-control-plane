#!/usr/bin/env python3
"""Tests for the E3 production execution leg (orchestrator → adapter dispatch).

All provider access is replaced by deterministic in-process test doubles; no
test in this module makes a network or CLI call. The tests assert the truth
rules of the leg: routable-only dispatch, verified-COMPLETE, rejection → repair
→ re-verification, E2 linkage through the public interface, and schema-v2
persistence.
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from e3_execution import (  # noqa: E402
    E3ProductionExecutor, ExecutionAdapterRegistry, OrchestrationStore,
    WorkerNotRoutable, normalize_dispatch_output,
)
from e3_planner import E3Planner  # noqa: E402
from e3_team_assembly import TeamAssembler  # noqa: E402
from e3_shadow_orchestrator import E3ShadowOrchestrator  # noqa: E402
from capability_registry import CapabilityRegistry  # noqa: E402
from orchestration_db import init_db  # noqa: E402
from task_fingerprint import TaskFingerprint  # noqa: E402


class FakeAdapter:
    """Deterministic stand-in for a real ExecutionAdapter."""

    def __init__(self, responses, provider="deepseek", model="fake-flash"):
        self.responses = list(responses)
        self.provider = provider
        self.model = model
        self.calls = []

    def dispatch(self, contract):
        self.calls.append(dict(contract))
        idx = len(self.calls) - 1
        content = self.responses[idx] if idx < len(self.responses) else self.responses[-1]
        return {
            "dispatch_id": f"fake-{idx}",
            "status": "COMPLETED",
            "provider": self.provider,
            "model": self.model,
            "content": content,
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            "error": None,
            "exit_code": 0,
            "runtime_s": 0.01,
        }


class FakeWorkerRegistry:
    def __init__(self, workers):
        self._workers = workers

    def get_worker(self, wid):
        return self._workers.get(wid)

    def get_all_workers(self):
        return dict(self._workers)


def _registry(fake_adapter, workers=None, usage_reporter=None, worker_id="deepseek-v41-flash"):
    workers = workers or {
        worker_id: {"worker_id": worker_id, "provider": "deepseek",
                    "model": "deepseek-flash", "routable": True},
        "mistral-small-4": {"worker_id": "mistral-small-4", "provider": "mistral",
                            "model": "mistral-small-4", "routable": False},
    }
    return ExecutionAdapterRegistry(
        worker_registry=FakeWorkerRegistry(workers),
        adapter_factories={worker_id: lambda: fake_adapter},
        usage_reporters={worker_id: (usage_reporter or (lambda r: "gov-fake-1"))},
    )


def _plan_and_dag(objective="Exec test task", **fp_kw):
    fp_kw.setdefault("task_family", "code")
    fp_kw.setdefault("reasoning_depth", 1)
    fp_kw.setdefault("risk_class", "R1")
    fp_kw.setdefault("required_roles", ["builder"])
    fp_kw.setdefault("verification_type", "deterministic")
    fp = TaskFingerprint(**fp_kw)
    planner = E3Planner()
    plan = planner.plan(objective, fp)
    dag = planner.build_dag(plan)
    return fp, plan, dag


class TestExecutionAdapterRegistry(unittest.TestCase):
    def test_credential_missing_worker_is_never_routable(self):
        reg = _registry(FakeAdapter(["x"]))
        self.assertFalse(reg.is_routable("mistral-small-4"))
        with self.assertRaises(WorkerNotRoutable):
            reg.adapter_for("mistral-small-4")

    def test_routable_worker_resolves_adapter(self):
        reg = _registry(FakeAdapter(["x"]))
        self.assertTrue(reg.is_routable("deepseek-v41-flash"))
        self.assertEqual(reg.routable_worker_ids(), ["deepseek-v41-flash"])
        self.assertIsNotNone(reg.adapter_for("deepseek-v41-flash"))

    def test_real_roster_marks_only_three_workers_routable(self):
        import worker_registry as wr
        reg = ExecutionAdapterRegistry(worker_registry=wr.WorkerRegistry())
        self.assertEqual(reg.routable_worker_ids(),
                         ["codex-cli", "deepseek-v41-flash", "google-nano-banana-2"])

    def test_usage_reporter_failure_never_fabricates_a_request_id(self):
        def boom(_):
            raise RuntimeError("governor unavailable")
        reg = _registry(FakeAdapter(["x"]), usage_reporter=boom)
        rid = reg.report_usage("deepseek-v41-flash", {"usage": None})
        self.assertTrue(rid.startswith("e2_linkage_error:"))


class TestNormalization(unittest.TestCase):
    def test_absent_usage_stays_null(self):
        out = normalize_dispatch_output("deepseek-v41-flash",
                                        {"status": "COMPLETED", "content": "hi",
                                         "usage": None}, "node-1")
        self.assertIsNone(out["usage"])
        self.assertIsNone(out["usage_tokens"])

    def test_provider_usage_is_carried_through(self):
        out = normalize_dispatch_output("deepseek-v41-flash",
                                        {"status": "COMPLETED", "content": "hi",
                                         "usage": {"total_tokens": 42}}, "node-1")
        self.assertEqual(out["usage_tokens"], 42)


class TestExecutorPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="e3-exec-test-"))
        self.db = self.tmp / "orchestration.db"
        init_db(self.db)
        self.store = OrchestrationStore(self.db)

    def tearDown(self):
        self.store.close()

    def _role_by_node(self, plan):
        return {n["node_id"]: (n.get("capability_roles") or ["builder"])[0]
                for n in plan["nodes"]}

    def test_first_pass_pass_completes_and_persists(self):
        adapter = FakeAdapter(["validated"])
        fp, plan, dag = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        assembler = TeamAssembler(None)
        assembly = assembler.assemble_team(plan, candidates_by_node={})
        # route manually (no capability registry in this unit test)
        from e3_team_assembly import TeamAssignment
        assembly.add_assignment(TeamAssignment(node_id, "deepseek-v41-flash",
                                               "builder", "HIGH", "unit-test"))
        assembly.complete = True

        execu = E3ProductionExecutor(self.store, _registry(adapter))
        run = execu.execute_plan(plan, dag, assembly, fp, "task",
                                 verification_test_cases_by_node={
                                     node_id: [{"name": "c", "field": "content",
                                                "expected": "validated"}]},
                                 role_by_node=self._role_by_node(plan))
        self.assertEqual(run["outcome"], "EXECUTION_COMPLETE")
        node = run["nodes"][0]
        self.assertEqual(node["state"], "COMPLETE")
        self.assertEqual(len(node["dispatch_attempts"]), 1)
        self.assertTrue(node["verification_attempts"][0]["passed"])
        self.assertEqual(len(adapter.calls), 1)

        read = self.store.read_back(node_id)
        states = [e["new_state"] for e in read["state_events"]]
        self.assertEqual(states[0], "READY")
        self.assertIn("COMPLETE", states)
        self.assertEqual(read["node"]["state"], "COMPLETE")
        self.assertEqual(read["node"]["assigned_worker"], "deepseek-v41-flash")
        self.assertEqual(len(read["evidence"]), 1)
        self.assertEqual(read["evidence"][0]["final_success"], 1)
        self.assertEqual(read["evidence"][0]["first_pass_success"], 1)

    def test_rejection_triggers_repair_and_reverification(self):
        adapter = FakeAdapter(["not-validated", "validated"])
        fp, plan, dag = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        from e3_team_assembly import TeamAssignment
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.add_assignment(TeamAssignment(node_id, "deepseek-v41-flash",
                                               "builder", "HIGH", "unit-test"))
        assembly.complete = True

        execu = E3ProductionExecutor(self.store, _registry(adapter))
        run = execu.execute_plan(plan, dag, assembly, fp, "task",
                                 verification_test_cases_by_node={
                                     node_id: [{"name": "c", "field": "content",
                                                "expected": "validated"}]},
                                 max_repair_attempts=1,
                                 role_by_node=self._role_by_node(plan))
        node = run["nodes"][0]
        self.assertEqual(run["outcome"], "EXECUTION_COMPLETE")
        self.assertEqual(len(node["rejections"]), 1)
        self.assertEqual(len(node["repairs"]), 1)
        self.assertEqual([v["passed"] for v in node["verification_attempts"]],
                         [False, True])
        self.assertEqual(len(adapter.calls), 2)
        read = self.store.read_back(node_id)
        states = [e["new_state"] for e in read["state_events"]]
        self.assertIn("REWORK", states)
        self.assertEqual(states[-1], "COMPLETE")
        self.assertEqual(read["evidence"][0]["first_pass_success"], 0)
        self.assertEqual(read["evidence"][0]["final_success"], 1)
        self.assertEqual(read["evidence"][0]["corrections"], 1)

    def test_failed_verification_never_reaches_complete(self):
        adapter = FakeAdapter(["bad"])
        fp, plan, dag = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        from e3_team_assembly import TeamAssignment
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.add_assignment(TeamAssignment(node_id, "deepseek-v41-flash",
                                               "builder", "HIGH", "unit-test"))
        assembly.complete = True

        execu = E3ProductionExecutor(self.store, _registry(adapter))
        run = execu.execute_plan(plan, dag, assembly, fp, "task",
                                 verification_test_cases_by_node={
                                     node_id: [{"name": "c", "field": "content",
                                                "expected": "validated"}]},
                                 max_repair_attempts=0,
                                 role_by_node=self._role_by_node(plan))
        node = run["nodes"][0]
        self.assertEqual(node["state"], "FAILED")
        self.assertNotEqual(run["outcome"], "EXECUTION_COMPLETE")
        read = self.store.read_back(node_id)
        self.assertEqual(read["node"]["state"], "FAILED")
        self.assertNotIn("COMPLETE", [e["new_state"] for e in read["state_events"]])

    def test_no_test_cases_blocks_without_dispatching(self):
        adapter = FakeAdapter(["anything"])
        fp, plan, dag = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        from e3_team_assembly import TeamAssignment
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.add_assignment(TeamAssignment(node_id, "deepseek-v41-flash",
                                               "builder", "HIGH", "unit-test"))
        assembly.complete = True
        execu = E3ProductionExecutor(self.store, _registry(adapter))
        run = execu.execute_plan(plan, dag, assembly, fp, "task",
                                 verification_test_cases_by_node={},
                                 role_by_node=self._role_by_node(plan))
        self.assertEqual(run["nodes"][0]["state"], "BLOCKED")
        self.assertEqual(adapter.calls, [])

    def test_non_routable_assignment_blocks_without_dispatching(self):
        adapter = FakeAdapter(["anything"])
        fp, plan, dag = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        from e3_team_assembly import TeamAssignment
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.add_assignment(TeamAssignment(node_id, "mistral-small-4",
                                               "builder", "LOW", "unit-test"))
        assembly.complete = True
        execu = E3ProductionExecutor(self.store, _registry(adapter))
        run = execu.execute_plan(plan, dag, assembly, fp, "task",
                                 verification_test_cases_by_node={
                                     node_id: [{"name": "c", "field": "content",
                                                "expected": "anything"}]},
                                 role_by_node=self._role_by_node(plan))
        self.assertEqual(run["nodes"][0]["state"], "BLOCKED")
        self.assertEqual(run["nodes"][0]["blocking_reason"],
                         "worker_not_routable:mistral-small-4")
        self.assertEqual(adapter.calls, [])

    def test_unassigned_node_is_blocked_not_fabricated(self):
        adapter = FakeAdapter(["anything"])
        fp, plan, dag = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        execu = E3ProductionExecutor(self.store, _registry(adapter))
        run = execu.execute_plan(plan, dag, assembly, fp, "task",
                                 verification_test_cases_by_node={
                                     node_id: [{"name": "c", "field": "content",
                                                "expected": "anything"}]},
                                 role_by_node=self._role_by_node(plan))
        self.assertEqual(run["nodes"][0]["state"], "BLOCKED")
        self.assertEqual(adapter.calls, [])

    def test_e2_linkage_ids_are_recorded(self):
        adapter = FakeAdapter(["validated"])
        fp, plan, dag = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        from e3_team_assembly import TeamAssignment
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.add_assignment(TeamAssignment(node_id, "deepseek-v41-flash",
                                               "builder", "HIGH", "unit-test"))
        assembly.complete = True
        execu = E3ProductionExecutor(self.store, _registry(adapter))
        run = execu.execute_plan(plan, dag, assembly, fp, "task",
                                 verification_test_cases_by_node={
                                     node_id: [{"name": "c", "field": "content",
                                                "expected": "validated"}]},
                                 role_by_node=self._role_by_node(plan))
        self.assertEqual(run["nodes"][0]["e2_request_ids"], ["gov-fake-1"])

    def test_dispatch_objectives_are_hashed_not_stored_raw(self):
        adapter = FakeAdapter(["validated"])
        fp, plan, dag = _plan_and_dag(objective="secret-bearing objective text")
        node_id = plan["nodes"][0]["node_id"]
        from e3_team_assembly import TeamAssignment
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.add_assignment(TeamAssignment(node_id, "deepseek-v41-flash",
                                               "builder", "HIGH", "unit-test"))
        assembly.complete = True
        execu = E3ProductionExecutor(self.store, _registry(adapter))
        execu.execute_plan(plan, dag, assembly, fp, "task",
                           verification_test_cases_by_node={
                               node_id: [{"name": "c", "field": "content",
                                          "expected": "validated"}]},
                           role_by_node=self._role_by_node(plan))
        attempt = json.dumps(self.store.read_back(node_id)["state_events"])
        self.assertNotIn("secret-bearing objective text", attempt)


class TestOrchestratorDispatchWiring(unittest.TestCase):
    """The orchestrator must actually dispatch assembled nodes to adapters."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="e3-orch-exec-"))
        self.db = self.tmp / "orchestration.db"
        init_db(self.db)
        self.adapter = FakeAdapter(["validated"])
        con = sqlite3.connect(str(self.db))
        try:
            reg = CapabilityRegistry(con)
            reg.register_worker("deepseek-v41-flash", "deepseek", "deepseek-flash",
                                roles=["builder"], state="EVALUATING",
                                task_family="code")
        finally:
            con.close()

    def test_orchestrate_and_execute_dispatches_real_adapter(self):
        orch = E3ShadowOrchestrator(db_path=self.db)
        fp, plan, _ = _plan_and_dag()
        node_id = plan["nodes"][0]["node_id"]
        out = orch.orchestrate_and_execute(
            "task", fp, plan=plan,
            verification_test_cases_by_node={
                node_id: [{"name": "c", "field": "content", "expected": "validated"}]},
            adapter_registry=_registry(self.adapter),
        )
        self.assertEqual(out["outcome"], "EXECUTION_COMPLETE")
        self.assertEqual(out["team_complete"], True)
        self.assertEqual([a["worker"] for a in out["team_assignments"]],
                         ["deepseek-v41-flash"])
        self.assertEqual(len(self.adapter.calls), 1)
        store = OrchestrationStore(self.db)
        try:
            read = store.read_back(node_id)
        finally:
            store.close()
        self.assertEqual(read["node"]["state"], "COMPLETE")
        self.assertEqual(read["node"]["assigned_worker"], "deepseek-v41-flash")

    def test_incomplete_team_escalates_without_dispatch(self):
        orch = E3ShadowOrchestrator(db_path=self.db)
        fp = TaskFingerprint(task_family="writing", reasoning_depth=1,
                             risk_class="R1", required_roles=["writer"],
                             verification_type="deterministic")
        out = orch.orchestrate_and_execute("task", fp,
                                           adapter_registry=_registry(self.adapter))
        self.assertEqual(out["outcome"], "TEAM_INCOMPLETE")
        self.assertIn("escalation", out)
        self.assertEqual(self.adapter.calls, [])


class TestE1E2Boundary(unittest.TestCase):
    def test_execution_module_performs_no_direct_e1_e2_writes(self):
        from e3_production_rehearsal import scan_e1_e2_boundary
        report = scan_e1_e2_boundary()
        self.assertEqual(report["direct_sql_violations"], [])
        self.assertTrue(report["clean"])

    def test_execution_module_has_no_direct_e1_e2_connection(self):
        text = (Path(__file__).parent.parent / "e3_execution.py").read_text(
            encoding="utf-8")
        for line in text.splitlines():
            if "sqlite3.connect" in line:
                self.assertNotIn("governor.db", line)
                self.assertNotIn("exec_brain.db", line)


if __name__ == "__main__":
    unittest.main()
