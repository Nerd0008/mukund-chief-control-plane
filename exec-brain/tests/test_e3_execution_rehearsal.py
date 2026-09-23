#!/usr/bin/env python3
"""Tests for the E3 production-execution rehearsal driver.

The real driver spends real provider calls. These tests drive the same code path
with injected deterministic adapter doubles and an isolated orchestration DB, so
the driver's plumbing (scenario construction, persistence read-back, bounded-usage
accounting, refusal handling) is regression-covered without any provider call.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import e3_execution  # noqa: E402
from e3_execution_rehearsal import (  # noqa: E402
    REQUIRED_RUNTIME_MODULES, TOKEN_CODEX, TOKEN_FIRSTPASS, TOKEN_REPAIR,
    E3ExecutionRehearsal,
)

TOKENS = (TOKEN_REPAIR, TOKEN_FIRSTPASS, TOKEN_CODEX)


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
        # deepseek: first attempt never matches; repaired attempts do.
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

    @classmethod
    def tearDownClass(cls):
        e3_execution._default_adapter_factory = cls._saved_factory
        e3_execution._default_usage_reporter = cls._saved_reporter

    def test_all_real_path_checks_pass(self):
        checks = self.report["checks"]
        for name, value in checks.items():
            if name in ("runtime_modules_deployed", "orchestration_db_is_schema_v2"):
                continue  # environment-dependent; asserted in the real rehearsal
            self.assertTrue(value, msg=f"{name}={value!r}")

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

    def test_bounded_usage_counts_real_dispatches_only(self):
        usage = self.report["bounded_usage"]
        expected = sum(len(s["dispatch_attempts"]) for s in self.report["scenarios"])
        self.assertEqual(usage["real_provider_calls"], expected)
        self.assertGreater(usage["real_provider_calls"], 0)

    def test_no_node_completes_without_a_verification_pass(self):
        for s in self.report["scenarios"]:
            if s["node_state"] == "COMPLETE":
                self.assertEqual(s["final_verification"], "PASS")

    def test_evidence_rows_persisted_per_dispatched_node(self):
        for s in self.report["scenarios"]:
            if s["dispatch_attempts"]:
                self.assertEqual(len(s["persisted_evidence"]), 1)
                self.assertEqual(s["persisted_evidence"][0]["final_success"],
                                 1 if s["node_state"] == "COMPLETE" else 0)

    def test_orchestration_db_upgraded_to_schema_v2(self):
        self.assertEqual(self.report["orchestration_db_after"]["schema_version"], 2)

    def test_required_module_list_is_declared(self):
        self.assertIn("e3_execution.py", REQUIRED_RUNTIME_MODULES)
        self.assertIn("e3_cli.py", REQUIRED_RUNTIME_MODULES)


if __name__ == "__main__":
    unittest.main()
