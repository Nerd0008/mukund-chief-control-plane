#!/usr/bin/env python3
"""Google image request-protocol conformance + repeat-series accounting tests.

All offline: the adapter's HTTP layer is monkeypatched and every executor test
uses a deterministic stub adapter registry, so no provider call is spent and no
credential is required.

Covered:

* the image adapter's request shape is contract-declared with the production
  default preserved (``responseModalities=['IMAGE']``, no ``imageConfig``);
* a declared ``['TEXT','IMAGE']`` shape and a declared ``imageConfig`` reach the
  provider payload verbatim and are echoed back on the result;
* the request shape and the sanitized provider response diagnostics survive into
  the persisted dispatch attempt / DAG state / evidence rows;
* a dispatch that returns no image part is recorded as a verification FAIL under
  the declared deterministic contract (never as a pass), and the requested
  output size is never promoted to a pass by any code path;
* the repeat-series accounting derives its rate from counts over executed calls.
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import gemini_adapter  # noqa: E402
from e3_execution import (  # noqa: E402
    E3ProductionExecutor, OrchestrationStore, normalize_dispatch_output,
)

# A minimal valid 1x1 PNG (used only as provider-returned bytes).
PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _image_response_body(width=1024, height=1024, b64=None):
    import base64
    data = b64 or base64.b64encode(PNG_1x1).decode()
    return json.dumps({
        "modelVersion": "gemini-3.1-flash-image",
        "candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [{"inlineData": {"mimeType": "image/jpeg",
                                                  "data": data}}]},
        }],
        "usageMetadata": {"promptTokenCount": 17, "candidatesTokenCount": 1383,
                          "totalTokenCount": 1400,
                          "candidatesTokensDetails": [{"modality": "IMAGE",
                                                       "tokenCount": 1120}]},
    })


class _CaptureHttp:
    """Records the payload the adapter would send; returns a canned response."""

    def __init__(self, body=None):
        self.payloads = []
        self.headers = []
        self.body = body or _image_response_body()

    def __call__(self, url, payload, headers, timeout):
        self.payloads.append(json.loads(json.dumps(payload)))
        self.headers.append(dict(headers))
        return 200, self.body, {"content-type": "application/json"}


class RequestShapeTests(unittest.TestCase):
    def setUp(self):
        self._orig = gemini_adapter._http_post_json
        self.http = _CaptureHttp()
        gemini_adapter._http_post_json = self.http
        self._orig_key = gemini_adapter.gk.get_gemini_key
        gemini_adapter.gk.get_gemini_key = lambda: "test-key-not-real"
        self.addCleanup(self._restore)

    def _restore(self):
        gemini_adapter._http_post_json = self._orig
        gemini_adapter.gk.get_gemini_key = self._orig_key

    def test_default_shape_is_image_only_without_image_config(self):
        adapter = gemini_adapter.GeminiImageExecutionAdapter()
        result = adapter.dispatch({"contract_id": "c1", "objective": "a square",
                                   "timeout": 5})
        gc = self.http.payloads[0]["generationConfig"]
        self.assertEqual(gc, {"responseModalities": ["IMAGE"]})
        self.assertEqual(result["requested_response_modalities"], ["IMAGE"])
        self.assertIsNone(result["requested_image_config"])
        self.assertEqual(result["dispatch_metadata"]["response_modalities"],
                         ["IMAGE"])
        self.assertIsNone(result["dispatch_metadata"]["image_config"])

    def test_declared_text_image_shape_reaches_the_payload(self):
        adapter = gemini_adapter.GeminiImageExecutionAdapter()
        result = adapter.dispatch({"contract_id": "c2", "objective": "a square",
                                   "timeout": 5,
                                   "response_modalities": ["TEXT", "IMAGE"]})
        gc = self.http.payloads[0]["generationConfig"]
        self.assertEqual(gc["responseModalities"], ["TEXT", "IMAGE"])
        self.assertNotIn("imageConfig", gc)
        self.assertEqual(result["requested_response_modalities"],
                         ["TEXT", "IMAGE"])
        self.assertIsNone(result["requested_image_config"])

    def test_declared_image_config_reaches_the_payload_and_is_echoed(self):
        adapter = gemini_adapter.GeminiImageExecutionAdapter()
        result = adapter.dispatch({
            "contract_id": "c3", "objective": "a square", "timeout": 5,
            "response_modalities": ["TEXT", "IMAGE"],
            "image_config": {"imageSize": "512"},
        })
        gc = self.http.payloads[0]["generationConfig"]
        self.assertEqual(gc["imageConfig"], {"imageSize": "512"})
        self.assertEqual(result["requested_image_config"], {"imageSize": "512"})
        self.assertEqual(result["dispatch_metadata"]["image_config"],
                         {"imageSize": "512"})

    def test_response_diagnostics_are_recorded_from_the_provider_body(self):
        adapter = gemini_adapter.GeminiImageExecutionAdapter()
        result = adapter.dispatch({"contract_id": "c4", "objective": "a square",
                                   "timeout": 5})
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["finish_reason"], "STOP")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["response_part_kinds"],
                         ["inlineData:image/jpeg"])
        self.assertTrue(result["image_decode_ok"])
        self.assertEqual(list(result["image_dims"]), [1, 1])  # PNG_1x1 header
        self.assertEqual(result["usage"]["candidatesTokenCount"], 1383)

    def test_no_image_part_is_recorded_as_a_failure_not_a_pass(self):
        self.http.body = json.dumps({
            "modelVersion": "gemini-3.1-flash-image",
            "candidates": [{"finishReason": "STOP", "content": {"parts": []}}],
            "usageMetadata": {"promptTokenCount": 17, "totalTokenCount": 17},
        })
        adapter = gemini_adapter.GeminiImageExecutionAdapter()
        result = adapter.dispatch({"contract_id": "c5", "objective": "a square",
                                   "timeout": 5})
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"], "no_image_part_in_response")
        self.assertFalse(result["image_decode_ok"])
        self.assertIsNone(result["image_dims"])
        # the request shape is still recorded, so the failure is attributable
        self.assertEqual(result["requested_response_modalities"], ["IMAGE"])

    def test_adapter_default_model_is_the_confirmed_roster_model(self):
        self.assertEqual(gemini_adapter.DEFAULT_IMAGE_MODEL,
                         "gemini-3.1-flash-image")


def _plan(response_modalities=None, image_config=None):
    node = {
        "node_id": "node-proto-1", "objective": "make a square",
        "capability_roles": ["vision"], "dependencies": [], "inputs": {},
        "expected_outputs": {}, "verification_method": "test", "floor_id": None,
        "allowed_tools": [], "permissions": {},
    }
    if response_modalities:
        node["response_modalities"] = list(response_modalities)
    if image_config:
        node["image_config"] = dict(image_config)
    return {"plan_id": "proto-1", "decomposition": False, "reason": "test",
            "nodes": [node]}


class _StubAdapter:
    def __init__(self, status="COMPLETED", decode_ok=True,
                 error=None, dims=None):
        self.contracts = []
        self.status = status
        self.decode_ok = decode_ok
        self.error = error
        self.dims = dims

    def dispatch(self, contract):
        self.contracts.append(dict(contract))
        return {
            "dispatch_id": "stub-dispatch-1", "status": self.status,
            "provider": "google", "model": "gemini-3.1-flash-image",
            "requested_model": "gemini-3.1-flash-image",
            "content": None, "image_b64": "AAAA", "image_mime": "image/jpeg",
            "image_size_bytes": 3, "image_dims": self.dims,
            "image_decode_ok": self.decode_ok, "finish_reason": "STOP",
            "candidate_count": 1, "candidate_finish_reasons": ["STOP"],
            "response_part_kinds": ["inlineData:image/jpeg"],
            "response_text_chars": None, "response_text_excerpt": None,
            "usage": None, "prompt_feedback": None, "error": self.error,
            "exit_code": 0, "runtime_s": 0.1,
            "requested_response_modalities": contract.get("response_modalities"),
            "requested_image_config": contract.get("image_config"),
        }


class _StubRegistry:
    def __init__(self, adapter):
        self.adapter = adapter
        self.reported = []

    def is_routable(self, worker_id):
        return True

    def adapter_for(self, worker_id):
        return self.adapter

    def report_usage(self, worker_id, result):
        self.reported.append(worker_id)
        return "obs-stub-1"


def _assembly(plan, worker_id, role):
    from e3_team_assembly import TeamAssembly, TeamAssignment
    assembly = TeamAssembly(plan.get("plan_id", "unknown"))
    assembly.assignments = [TeamAssignment("node-proto-1", worker_id, role,
                                           "HIGH", "test")]
    assembly.issues = []
    assembly.complete = True
    return assembly


class ExecutionPathShapeTests(unittest.TestCase):
    """The declared shape must survive into the persisted attempt record."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "orch.db"
        self.addCleanup(self.tmp.cleanup)
        from e3_planner import E3Planner
        from task_fingerprint import TaskFingerprint
        self.planner = E3Planner()
        self.fingerprint = TaskFingerprint(
            task_family="code", reasoning_depth=1, risk_class="R1",
            required_roles=["vision"], verification_type="deterministic")

    def _execute(self, adapter, plan):
        store = OrchestrationStore(self.db_path)
        registry = _StubRegistry(adapter)
        try:
            dag = self.planner.build_dag(plan)
            executor = E3ProductionExecutor(store, registry)
            run = executor.execute_plan(
                plan, dag, _assembly(plan, "google-nano-banana-2", "vision"),
                self.fingerprint, "make a square",
                verification_test_cases_by_node={"node-proto-1": [
                    {"name": "dispatch completed", "field": "status",
                     "expected": "COMPLETED"},
                    {"name": "image decoded", "field": "image_decode_ok",
                     "expected": True}]},
                max_repair_attempts=0, dispatch_timeout=5,
                role_by_node={"node-proto-1": "vision"})
            read_back = store.read_back("node-proto-1")
        finally:
            store.close()
        return run, read_back, registry

    def test_node_declared_shape_reaches_the_adapter_contract(self):
        adapter = _StubAdapter(dims=[1024, 1024])
        plan = _plan(response_modalities=["TEXT", "IMAGE"],
                     image_config={"imageSize": "512"})
        run, read_back, _ = self._execute(adapter, plan)
        contract = adapter.contracts[0]
        self.assertEqual(contract["response_modalities"], ["TEXT", "IMAGE"])
        self.assertEqual(contract["image_config"], {"imageSize": "512"})
        attempt = run["nodes"][0]["dispatch_attempts"][0]
        self.assertEqual(attempt["requested_response_modalities"],
                         ["TEXT", "IMAGE"])
        self.assertEqual(attempt["requested_image_config"],
                         {"imageSize": "512"})

    def test_default_dispatch_sends_no_shape_override(self):
        adapter = _StubAdapter(dims=[1024, 1024])
        run, _, _ = self._execute(adapter, _plan())
        contract = adapter.contracts[0]
        self.assertNotIn("response_modalities", contract)
        self.assertNotIn("image_config", contract)
        attempt = run["nodes"][0]["dispatch_attempts"][0]
        self.assertIsNone(attempt["requested_response_modalities"])

    def test_persisted_rows_exist_for_a_verified_image_dispatch(self):
        adapter = _StubAdapter(dims=[1024, 1024])
        run, read_back, _ = self._execute(adapter, _plan())
        self.assertEqual(run["nodes"][0]["state"], "COMPLETE")
        self.assertEqual(read_back["node"]["state"], "COMPLETE")
        self.assertTrue(read_back["evidence"])
        con = sqlite3.connect(str(self.db_path))
        try:
            n_nodes = con.execute("SELECT COUNT(*) FROM dag_node").fetchone()[0]
            n_events = con.execute(
                "SELECT COUNT(*) FROM dag_state_event").fetchone()[0]
            n_ev = con.execute(
                "SELECT COUNT(*) FROM performance_evidence").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n_nodes, 1)
        self.assertGreater(n_events, 0)
        self.assertEqual(n_ev, 1)

    def test_no_image_response_fails_verification_and_is_never_a_pass(self):
        adapter = _StubAdapter(status="FAILED", decode_ok=False, dims=None,
                               error="no_image_part_in_response")
        run, read_back, _ = self._execute(adapter, _plan())
        node = run["nodes"][0]
        self.assertEqual(node["state"], "FAILED")
        self.assertEqual(node["final_verification"], "FAIL")
        self.assertEqual(node["failure_attribution"], "verification_fail")
        con = sqlite3.connect(str(self.db_path))
        try:
            row = con.execute("SELECT final_success, verification_outcome "
                              "FROM performance_evidence").fetchone()
        finally:
            con.close()
        self.assertEqual(row[0], 0)
        self.assertEqual(row[1], "FAIL")

    def test_normalize_dispatch_output_carries_shape_and_diagnostics(self):
        out = normalize_dispatch_output("google-nano-banana-2", {
            "status": "FAILED", "provider": "google", "dispatch_id": "d1",
            "error": "no_image_part_in_response",
            "requested_response_modalities": ["IMAGE"],
            "requested_image_config": None,
            "candidate_count": 1, "candidate_finish_reasons": ["STOP"],
            "response_part_kinds": [], "response_text_chars": None,
            "response_text_excerpt": None,
        }, "node-x")
        self.assertEqual(out["requested_response_modalities"], ["IMAGE"])
        self.assertEqual(out["candidate_finish_reasons"], ["STOP"])
        self.assertEqual(out["response_part_kinds"], [])


class RepeatSeriesAccountingTests(unittest.TestCase):
    """The recurrence rate must be counts over executed calls, nothing more."""

    def _mod(self):
        import e3_google_image_repeat_series as mod
        # The driver puts the *deployed* runtime root first on sys.path (that is
        # the path under test when it runs for real). This suite must exercise
        # the repository sources, consistent with every other E3 suite, so the
        # runtime-root entry is dropped again after import.
        rt = str(mod.RUNTIME_ROOT)
        while rt in sys.path:
            sys.path.remove(rt)
        return mod

    def test_classification_labels(self):
        mod = self._mod()
        self.assertEqual(mod._classify(None), "no_attempt_recorded")
        self.assertEqual(mod._classify({"image_decode_ok": True}),
                         "image_decoded")
        self.assertEqual(
            mod._classify({"image_decode_ok": False,
                           "error": "no_image_part_in_response"}),
            "no_image_part_in_response")
        self.assertEqual(mod._classify({"image_decode_ok": False,
                                        "error": "http_429"}),
                         "error:http_429")

    def test_rate_is_reported_as_counts_over_executed_calls(self):
        mod = self._mod()
        progress = {"calls_attempted": 6, "observations": [
            {"executed": True, "classification": "image_decoded",
             "shape_label": "IMAGE-only", "image_dims": [1024, 1024],
             "finish_reason": "STOP", "error": None},
            {"executed": True, "classification": "image_decoded",
             "shape_label": "IMAGE-only", "image_dims": [1024, 1024],
             "finish_reason": "STOP", "error": None},
            {"executed": True, "classification": "no_image_part_in_response",
             "shape_label": "IMAGE-only", "image_dims": None,
             "finish_reason": "STOP", "error": "no_image_part_in_response"},
        ]}
        summary = mod._summarise(progress)
        self.assertEqual(summary["calls_completed"], 3)
        self.assertEqual(summary["no_image_part_in_response_count"], 1)
        self.assertEqual(summary["no_image_part_in_response_rate"],
                         {"numerator": 1, "denominator": 3,
                          "rate": 1 / 3})
        self.assertEqual(summary["per_shape"]["IMAGE-only"]["executed_calls"], 3)
        self.assertEqual(summary["per_shape"]["IMAGE-only"]["image_decoded"], 2)

    def test_size_verdict_never_claims_a_honoured_size_when_ignored(self):
        mod = self._mod()
        progress = {"calls_attempted": 2, "observations": [
            {"executed": True, "classification": "image_decoded",
             "shape_label": "IMAGE-only", "image_dims": [1024, 1024],
             "finish_reason": "STOP", "error": None},
            {"executed": True, "classification": "image_decoded",
             "shape_label": "IMAGE-only", "image_dims": [1024, 1024],
             "finish_reason": "STOP", "error": None},
        ]}
        verdict = mod._size_verdict(mod._summarise(progress), progress)
        self.assertFalse(verdict["prompt_stated_size_honoured_in_series"])
        self.assertEqual(verdict["verdict"], "PROMPT_STATED_SIZE_IGNORED")

    def test_size_verdict_is_undetermined_without_an_observed_image(self):
        mod = self._mod()
        progress = {"calls_attempted": 1, "observations": [
            {"executed": True, "classification": "no_image_part_in_response",
             "shape_label": "IMAGE-only", "image_dims": None,
             "finish_reason": "STOP", "error": "no_image_part_in_response"},
        ]}
        verdict = mod._size_verdict(mod._summarise(progress), progress)
        self.assertEqual(verdict["verdict"],
                         "NO_IMAGE_OBSERVED_SO_SIZE_UNDETERMINED")

    def test_stated_budget_is_single_digit_and_matches_the_call_list(self):
        mod = self._mod()
        self.assertLess(mod.TOTAL_PLANNED_CALLS, 10)
        self.assertEqual(
            mod.TOTAL_PLANNED_CALLS,
            mod.IMAGE_ONLY_REPEATS + mod.TEXT_IMAGE_REPEATS
            + mod.SIZE_PROBE_CALLS)

    def test_diagnosis_records_finish_reason_of_every_recurrence(self):
        mod = self._mod()
        obs = [
            {"executed": True, "classification": "image_decoded",
             "shape_label": "IMAGE-only", "image_dims": [1024, 1024],
             "finish_reason": "STOP", "error": None,
             "response_part_kinds": ["inlineData:image/jpeg"]},
            {"executed": True, "classification": "no_image_part_in_response",
             "shape_label": "IMAGE-only", "image_dims": None,
             "finish_reason": "IMAGE_RECITATION",
             "error": "no_image_part_in_response", "response_part_kinds": []},
        ]
        diag = mod._diagnose(mod._summarise({"calls_attempted": 2,
                                             "observations": obs}), obs)
        self.assertEqual(
            diag["provider_signals_on_recurrence"]["finish_reason_counts"],
            {"IMAGE_RECITATION": 1})
        self.assertEqual(diag["measured_rate"]["no_image_part_in_response"], 1)
        self.assertEqual(diag["measured_rate"]["executed_calls"], 2)
        # the series must not be described as stable/broken
        joined = " ".join(diag["not_supported_by_this_series"]).lower()
        self.assertIn("stability claim", joined)
        self.assertIn("breakage claim", joined)
        self.assertTrue(diag["remaining_unknown"])

    def test_rederivation_path_spends_no_provider_call(self):
        mod = self._mod()
        import inspect
        src = inspect.getsource(mod._from_evidence)
        # the re-derivation entry point must not be able to dispatch
        self.assertNotIn("_run_image_call", src)
        self.assertNotIn("E3ProductionExecutor", src)


if __name__ == "__main__":
    unittest.main()
