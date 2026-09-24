#!/usr/bin/env python3
"""Tests for the E3 production-execution rehearsal driver.

The real driver spends real provider calls. These tests drive the same code path
with injected deterministic adapter doubles and an isolated orchestration DB, so
the driver's plumbing (scenario construction, persistence read-back, bounded-usage
accounting, refusal handling, the decomposed multi-worker plan and the
rehearsal-evidence isolation proof) is regression-covered without any provider
call.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import e3_execution  # noqa: E402
from e3_execution_rehearsal import (  # noqa: E402
    REQUIRED_RUNTIME_MODULES, STUB_ONLY_SCENARIOS, TOKEN_CODEX, TOKEN_FIRSTPASS,
    TOKEN_NODE_BUILDER, TOKEN_NODE_INTEGRATOR, TOKEN_REPAIR,
    E3ExecutionRehearsal, normalized_scenario_nodes,
)

TOKENS = (TOKEN_REPAIR, TOKEN_FIRSTPASS, TOKEN_CODEX,
          TOKEN_NODE_BUILDER, TOKEN_NODE_INTEGRATOR)


class StubAdapter:
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.calls = []

    def dispatch(self, contract):
        self.calls.append(contract)
        objective = contract["objective"]
        token = next((t for t in TOKENS if t in objective), None)
        if self.worker_id == "google-nano-banana-2":
            return {"dispatch_id": "gem-1", "status": "COMPLETED",
                    "provider": "google", "model": "gemini-3.1-flash-image",
                    "content": None, "image_size_bytes": 128,
                    "image_decode_ok": True, "usage": {"totalTokenCount": 10},
                    "error": None, "exit_code": 0, "runtime_s": 1.0}
        # deepseek: the first call of the whole run deliberately never matches,
        # so the repair cycle is exercised.
        if self.worker_id == "deepseek-v41-flash" and len(self.calls) == 1:
            content = "I am an assistant."
        else:
            content = token or ""
        return {"dispatch_id": f"stub-{len(self.calls)}", "status": "COMPLETED",
                "provider": "openai" if self.worker_id == "codex-cli" else "deepseek",
                "model": "stub-model", "content": content,
                "usage": {"total_tokens": 11}, "error": None, "exit_code": 0,
                "runtime_s": 0.1}


class RehearsalDriverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_factory = e3_execution._default_adapter_factory
        cls._saved_reporter = e3_execution._default_usage_reporter
        cls._adapters = {}

        def factory(spec):
            key = spec["class"]
            worker_id = {"DeepSeekExecutionAdapter": "deepseek-v41-flash",
                         "CodexExecutionAdapter": "codex-cli",
                         "GeminiImageExecutionAdapter": "google-nano-banana-2",
                         }.get(key, key)

            def build():
                if key not in cls._adapters:
                    cls._adapters[key] = StubAdapter(worker_id)
                return cls._adapters[key]
            return build

        e3_execution._default_adapter_factory = factory
        e3_execution._default_usage_reporter = (
            lambda spec: (lambda result: "gov-stub-1"))

        cls.tmp = Path(tempfile.mkdtemp(prefix="e3-exec-reh-test-"))
        cls.rehearsal = E3ExecutionRehearsal(
            db_path=cls.tmp / "orchestration.db",
            scratch_root=cls.tmp / "scratch")
        cls.report = cls.rehearsal.run(include_codex=True, include_google=True)
        cls.by_name = {s["scenario"]: s for s in cls.report["scenarios"]}
        cls.multi = cls.by_name["F_decomposed_multi_worker"]

    @classmethod
    def tearDownClass(cls):
        e3_execution._default_adapter_factory = cls._saved_factory
        e3_execution._default_usage_reporter = cls._saved_reporter

    def test_all_real_path_checks_pass(self):
        checks = self.report["checks"]
        for name, value in checks.items():
            if name in ("runtime_modules_deployed", "orchestration_db_is_schema_v2"):
                continue  # environment-dependent; asserted in the real rehearsal
            if value is None:
                continue  # scenario not part of this run: not evaluated
            self.assertTrue(value, msg=f"{name}={value!r}")
        for name in ("A_repair_cycle_deepseek", "B_first_pass_deepseek",
                     "C_codex_cli_dispatch", "F_decomposed_multi_worker",
                     "E_non_routable_refusal"):
            self.assertIn(name, self.by_name)

    def test_repair_cycle_rejects_then_repairs(self):
        s = self.by_name["A_repair_cycle_deepseek"]
        self.assertEqual(len(s["rejections"]), 1)
        self.assertEqual(len(s["repairs"]), 1)
        self.assertEqual([v["passed"] for v in s["verification_attempts"]],
                         [False, True])
        self.assertEqual(s["node_state"], "COMPLETE")
        self.assertEqual(s["persisted_node_state"], "COMPLETE")
        states = [e["new"] for e in s["persisted_state_events"]]
        self.assertIn("REWORK", states)
        self.assertEqual(states[-1], "COMPLETE")

    def test_first_pass_scenario_uses_one_dispatch(self):
        s = self.by_name["B_first_pass_deepseek"]
        self.assertEqual(len(s["dispatch_attempts"]), 1)
        self.assertEqual(s["node_state"], "COMPLETE")

    def test_refusal_scenario_spends_no_dispatch(self):
        s = self.by_name["E_non_routable_refusal"]
        self.assertEqual(s["node_state"], "BLOCKED")
        self.assertEqual(s["dispatch_attempts"], [])
        self.assertTrue(s["refusal_honoured"])
        self.assertEqual(s["stub_dispatch_calls"], 0)

    def test_blocked_node_is_persisted_as_blocked(self):
        s = self.by_name["E_non_routable_refusal"]
        self.assertEqual(s["persisted_node_state"], "BLOCKED")

    # ── provider content-side stop terminal path (stub providers only) ──
    def test_content_stop_terminal_scenario_is_recorded(self):
        s = self.by_name["G_content_stop_terminal"]
        self.assertTrue(s["content_stop_terminal_path_recorded"])
        self.assertEqual(s["content_stop_finish_reason"], "IMAGE_RECITATION")
        self.assertEqual(s["node_state"], "BLOCKED")
        self.assertEqual(s["run_outcome"], "EXECUTION_BLOCKED")
        self.assertEqual(s["failure_attribution"], "provider_content_stop")
        self.assertEqual(s["blocking_reason"],
                         "provider_content_stop_unrecovered:IMAGE_RECITATION")

    def test_content_stop_retry_accounting_is_bounded_and_identical(self):
        s = self.by_name["G_content_stop_terminal"]
        self.assertEqual(s["content_stop_retry_budget"], 2)
        self.assertEqual(s["content_stop_retry_count"], 2)
        # initial dispatch + exactly the bounded retries, no more
        self.assertEqual(s["stub_dispatch_calls"], 1 + s["content_stop_retry_budget"])
        self.assertEqual(len(s["dispatch_attempts"]), s["stub_dispatch_calls"])
        # every attempt was the identical request (never a reworded repair)
        self.assertTrue(s["content_stop_retries_are_identical_requests"])
        self.assertTrue(all(r.get("kind") == "same_request_retry"
                            for r in s["repairs"]))

    def test_content_stop_terminal_path_is_persisted_and_escalated(self):
        s = self.by_name["G_content_stop_terminal"]
        self.assertEqual(s["persisted_node_state"], "BLOCKED")
        causes = [e["cause"] for e in s["persisted_state_events"]]
        self.assertIn("provider_content_stop_unrecovered:IMAGE_RECITATION", causes)
        self.assertEqual(s["persisted_evidence"][0]["failure_attribution"],
                         "provider_content_stop")
        self.assertEqual(s["persisted_evidence"][0]["final_success"], 0)
        escalation = s["content_stop_escalation"]
        self.assertIsNotNone(escalation)
        self.assertEqual(escalation["trigger"], "provider_content_stop")
        self.assertEqual(escalation["finish_reason"], "IMAGE_RECITATION")

    def test_content_stop_scenario_spends_no_real_provider_call(self):
        usage = self.report["bounded_usage"]
        self.assertIn("G_content_stop_terminal", usage["stub_only_scenarios"])
        self.assertTrue(self.report["checks"]
                        ["content_stop_terminal_path_recorded"])

    def test_bounded_usage_counts_real_dispatches_only(self):
        usage = self.report["bounded_usage"]
        real = [c for c in self.rehearsal.adapter_call_log
                if c["scenario"] not in STUB_ONLY_SCENARIOS]
        stub = [c for c in self.rehearsal.adapter_call_log
                if c["scenario"] in STUB_ONLY_SCENARIOS]
        # Stub-only scenarios exercise the real code path but spend no provider
        # call, so they are excluded from the bounded real-call accounting.
        self.assertEqual(usage["real_provider_calls"], len(real))
        self.assertGreater(usage["real_provider_calls"], 0)
        self.assertEqual(usage["stub_only_dispatch_count"], len(stub))
        self.assertGreater(usage["stub_only_dispatch_count"], 0)
        # The stated plan covers exactly the real scenarios.
        planned = sum(s["calls"] for s in self.report["usage_plan"]
                      if s["scenario"] not in STUB_ONLY_SCENARIOS)
        self.assertEqual(usage["planned_calls"], planned)

    def test_no_node_completes_without_a_verification_pass(self):
        for s in self.report["scenarios"]:
            for n in normalized_scenario_nodes(s):
                if n["state"] == "COMPLETE":
                    self.assertEqual(n["final_verification"], "PASS")

    def test_evidence_rows_persisted_per_dispatched_node(self):
        for s in self.report["scenarios"]:
            if s.get("nodes"):
                for n in s["nodes"]:
                    if n["dispatch_count"]:
                        self.assertEqual(len(n["persisted_evidence"]), 1)
                        self.assertEqual(
                            n["persisted_evidence"][0]["final_success"],
                            1 if n["state"] == "COMPLETE" else 0)
                continue
            if s["dispatch_attempts"]:
                self.assertEqual(len(s["persisted_evidence"]), 1)

    def test_orchestration_db_upgraded_to_schema_v2(self):
        self.assertEqual(self.report["orchestration_db_after"]["schema_version"], 2)

    def test_required_module_list_is_declared(self):
        self.assertIn("e3_execution.py", REQUIRED_RUNTIME_MODULES)
        self.assertIn("e3_cli.py", REQUIRED_RUNTIME_MODULES)

    # ── decomposed multi-worker plan ────────────────────────────────
    def test_multi_node_plan_is_decomposed_with_two_nodes(self):
        self.assertTrue(self.multi["plan_decomposition"])
        self.assertGreaterEqual(self.multi["node_count"], 2)
        roles = [r for n in self.multi["plan_nodes"] for r in n["roles"]]
        self.assertIn("builder", roles)
        self.assertIn("integrator", roles)

    def test_multi_node_dispatches_to_two_distinct_workers(self):
        workers = self.multi["distinct_workers_dispatched"]
        self.assertEqual(len(workers), 2)
        self.assertTrue(all(a["worker_routable"] for a in self.multi["assignments"]))

    def test_multi_node_every_node_completes_only_after_its_own_verification(self):
        self.assertEqual(self.multi["nodes_complete"], self.multi["node_count"])
        for n in self.multi["nodes"]:
            self.assertEqual(n["state"], "COMPLETE")
            self.assertEqual(n["final_verification"], "PASS")
            self.assertTrue(n["verification_attempts"])

    def test_multi_node_exercises_rejection_repair_and_reverify(self):
        repaired = [n for n in self.multi["nodes"] if n["rejections"] and n["repairs"]]
        self.assertTrue(repaired)
        for n in repaired:
            self.assertEqual([v["passed"] for v in n["verification_attempts"]],
                             [False, True])
            self.assertEqual(n["state"], "COMPLETE")

    def test_multi_node_dependency_gate_is_ordered(self):
        log = self.multi["persisted_plan_state_log"]
        self.assertTrue(log)
        deps = self.multi["dag_dependencies"]
        order = {(e["node_id"], e["new_state"]): i for i, e in enumerate(log)}
        checked = 0
        for node_id, node_deps in deps.items():
            for dep in node_deps:
                self.assertLess(order[(dep, "COMPLETE")], order[(node_id, "READY")])
                checked += 1
        self.assertGreater(checked, 0)

    def test_multi_node_dag_state_and_evidence_persisted(self):
        for n in self.multi["nodes"]:
            self.assertEqual(n["persisted_node_state"], n["state"])
            self.assertEqual(n["persisted_assigned_worker"], n["worker_id"])
            self.assertEqual(len(n["persisted_evidence"]), 1)

    # ── isolation / boundary ────────────────────────────────────────
    def test_rehearsal_evidence_isolation_proof(self):
        iso = self.report["isolation"]
        self.assertTrue(iso["all_production_writes_refused"])
        self.assertTrue(iso["stores_unchanged"])
        self.assertTrue(iso["isolated_store_outside_production"])
        self.assertEqual(iso["diffs"], [])
        self.assertTrue(Path(iso["isolated_rehearsal_store"]).exists())
        self.assertEqual(iso["before_sha256"], iso["after_sha256"])

    def test_simulated_evidence_absent_from_live_store(self):
        c = self.report["live_store_contamination"]
        self.assertTrue(c["simulated_evidence_absent"])
        self.assertTrue(c["no_unearned_qualification"])
        self.assertEqual(c["simulated_or_shadow_evidence_rows"], 0)

    def test_e1_e2_boundary_scan_is_clean(self):
        self.assertTrue(self.report["isolation"]["boundary_scan"]["clean"])


class NotRequestedScenarioReportingTest(unittest.TestCase):
    """An unrun optional scenario must report as not-evaluated, never as a pass."""

    @classmethod
    def setUpClass(cls):
        cls._saved_factory = e3_execution._default_adapter_factory
        cls._saved_reporter = e3_execution._default_usage_reporter
        adapters = {}

        def factory(spec):
            key = spec["class"]
            worker_id = {"DeepSeekExecutionAdapter": "deepseek-v41-flash",
                         "CodexExecutionAdapter": "codex-cli",
                         "GeminiImageExecutionAdapter": "google-nano-banana-2",
                         }.get(key, key)

            def build():
                if key not in adapters:
                    adapters[key] = StubAdapter(worker_id)
                return adapters[key]
            return build

        e3_execution._default_adapter_factory = factory
        e3_execution._default_usage_reporter = (
            lambda spec: (lambda result: "gov-stub-1"))
        tmp = Path(tempfile.mkdtemp(prefix="e3-exec-reh-skip-"))
        cls.report = E3ExecutionRehearsal(
            db_path=tmp / "orchestration.db",
            scratch_root=tmp / "scratch").run(include_google=False)

    @classmethod
    def tearDownClass(cls):
        e3_execution._default_adapter_factory = cls._saved_factory
        e3_execution._default_usage_reporter = cls._saved_reporter

    def test_google_check_is_not_evaluated_when_not_requested(self):
        self.assertIsNone(self.report["checks"]["google_image_complete"])
        self.assertFalse(self.report["scenarios_requested"]["google_image"])

    def test_google_scenario_is_absent_from_the_run(self):
        names = [s["scenario"] for s in self.report["scenarios"]]
        self.assertNotIn("D_google_image_dispatch", names)
        self.assertNotIn("google", self.report["bounded_usage"]["calls_by_provider"])

    def test_planned_call_bound_matches_the_plan(self):
        self.assertEqual(self.report["bounded_usage"]["planned_calls"],
                         sum(s["calls"] for s in self.report["usage_plan"]))


if __name__ == "__main__":
    unittest.main()
