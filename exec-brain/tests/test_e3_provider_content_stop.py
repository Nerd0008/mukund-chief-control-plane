#!/usr/bin/env python3
"""Provider content-side stop: truthful attribution, bounded recovery, terminal.

Everything here is offline and spends **zero** real provider calls. The provider
responses used as fixtures are reconstructed from the recorded, provider-returned
values of the bounded repeat series
``audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/`` (see
``observations.json``): the two ``IMAGE_RECITATION`` recurrences (index 2 and 3)
and the successful ``STOP`` image responses (index 1, 4-8). The adapter's HTTP
layer is monkeypatched, so only the recorded response *shape and values* are
exercised — no network and no credential.

What is asserted:

* the fixture faithfully reproduces the recorded provider-returned diagnostics
  (finishReason, candidate count, empty part list, 0 candidate tokens);
* a provider content-side stop gets its own attribution
  (``provider_content_stop``) and records the provider finishReason, separate
  from a provider/transport error (``provider_error``) and from a contract
  failure (``verification_fail``);
* the recovery is a **bounded, identical, single-shot same-request retry** with a
  stated reason, never a reworded request and never unbounded;
* an unrecovered content-side stop terminates non-silently (BLOCKED + escalation
  naming the finish reason), never as a pass and never as a silent
  verification failure;
* the deterministic verification contract is not weakened: only a real PASS
  reaches COMPLETE, and a delivered-but-non-conforming output is still
  ``verification_fail``;
* worker identity is never switched silently, so E4 equivalent-worker failover
  stays an explicit decision;
* the terminal outcome is observable to E5 repeated-failure convergence.
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

import gemini_adapter  # noqa: E402
from e3_execution import (  # noqa: E402
    DEFAULT_MAX_CONTENT_STOP_RETRIES, FAILURE_PROVIDER_CONTENT_STOP,
    FAILURE_PROVIDER_ERROR, FAILURE_VERIFICATION_FAIL,
    E3ProductionExecutor, OrchestrationStore, classify_dispatch_failure,
    content_side_stop_reason, normalize_dispatch_output,
)
from orchestration_db import init_db  # noqa: E402

# ─── Recorded provider responses (rebuilt from provider-returned values) ─────
#
# See observations.json index 2/3 (IMAGE_RECITATION, empty part list, 17 prompt
# / 0 candidate tokens) and index 1/4-8 (STOP + inlineData image, 17 prompt /
# 1322 candidate tokens). The image payload itself is a minimal valid PNG — the
# recorded responses carried real JPEG bytes that are not reproduced here; only
# the shape/values that drive attribution are used.
PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

RECORDED_IMAGE_RECITATION_BODY = json.dumps({
    "modelVersion": "gemini-3.1-flash-image",
    "candidates": [{
        "finishReason": "IMAGE_RECITATION",
        "content": {"parts": []},
    }],
    "usageMetadata": {
        "promptTokenCount": 17,
        "totalTokenCount": 17,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}],
        "serviceTier": "standard",
    },
})


def _recorded_image_body():
    import base64
    return json.dumps({
        "modelVersion": "gemini-3.1-flash-image",
        "candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [{"inlineData": {
                "mimeType": "image/jpeg",
                "data": base64.b64encode(PNG_1x1).decode()}}]},
        }],
        "usageMetadata": {
            "promptTokenCount": 17,
            "candidatesTokenCount": 1322,
            "totalTokenCount": 1339,
            "candidatesTokensDetail": [{"modality": "IMAGE",
                                        "tokenCount": 1120}],
            "serviceTier": "standard",
        },
    })


class _CaptureHttp:
    """Stubbed transport: records the payload, returns a canned provider body."""

    def __init__(self, body):
        self.payloads = []
        self.body = body

    def __call__(self, url, payload, headers, timeout):
        self.payloads.append(json.loads(json.dumps(payload)))
        return 200, self.body, {"content-type": "application/json"}


class RecordedFixtureFidelityTests(unittest.TestCase):
    """The fixtures must reproduce the recorded provider-returned values."""

    def setUp(self):
        self._orig = gemini_adapter._http_post_json
        self._orig_key = gemini_adapter.gk.get_gemini_key
        gemini_adapter.gk.get_gemini_key = lambda: "test-key-not-real"
        self.addCleanup(self._restore)

    def _restore(self):
        gemini_adapter._http_post_json = self._orig
        gemini_adapter.gk.get_gemini_key = self._orig_key

    def _dispatch(self, body):
        gemini_adapter._http_post_json = _CaptureHttp(body)
        adapter = gemini_adapter.GeminiImageExecutionAdapter()
        return adapter.dispatch({"contract_id": "c-fixture", "objective": "x",
                                 "timeout": 5})

    def test_recitation_fixture_matches_recorded_completion(self):
        result = self._dispatch(RECORDED_IMAGE_RECITATION_BODY)
        # Recorded: status FAILED, error no_image_part_in_response,
        # finish_reason IMAGE_RECITATION, candidate_count 1, part list empty.
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"], "no_image_part_in_response")
        self.assertEqual(result["finish_reason"], "IMAGE_RECITATION")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidate_finish_reasons"],
                         ["IMAGE_RECITATION"])
        self.assertEqual(result["response_part_kinds"], [])
        self.assertFalse(result["image_decode_ok"])
        self.assertIsNone(result["image_dims"])
        # 0 candidate tokens: the recorded usage carries no candidatesTokenCount
        self.assertNotIn("candidatesTokenCount", result["usage"])
        self.assertEqual(result["usage"]["promptTokenCount"], 17)

    def test_image_fixture_matches_recorded_completion(self):
        result = self._dispatch(_recorded_image_body())
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["finish_reason"], "STOP")
        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(result["image_decode_ok"])
        self.assertEqual(list(result["image_dims"]), [1, 1])

    def test_content_stop_is_attributed_from_the_provider_finish_reason(self):
        result = self._dispatch(RECORDED_IMAGE_RECITATION_BODY)
        out = normalize_dispatch_output("google-nano-banana-2", result, "n1")
        self.assertEqual(content_side_stop_reason(out), "IMAGE_RECITATION")
        self.assertEqual(classify_dispatch_failure(out),
                         FAILURE_PROVIDER_CONTENT_STOP)
        self.assertEqual(out["requested_response_modalities"], ["IMAGE"])

    def test_image_fixture_is_not_a_content_stop(self):
        result = self._dispatch(_recorded_image_body())
        out = normalize_dispatch_output("google-nano-banana-2", result, "n1")
        self.assertIsNone(content_side_stop_reason(out))


class ClassificationTests(unittest.TestCase):
    """Three genuinely different causes must never be conflated."""

    def _out(self, **kw):
        base = {"status": "FAILED", "error": None, "finish_reason": None,
                "candidate_finish_reasons": [], "prompt_feedback": None}
        base.update(kw)
        return normalize_dispatch_output("w", base, "n")

    def test_content_stop_is_its_own_class(self):
        out = self._out(error="no_image_part_in_response",
                        finish_reason="IMAGE_RECITATION",
                        candidate_finish_reasons=["IMAGE_RECITATION"])
        self.assertEqual(classify_dispatch_failure(out),
                         FAILURE_PROVIDER_CONTENT_STOP)

    def test_prompt_level_block_is_a_content_stop(self):
        out = self._out(status="FAILED", error="no_candidates_returned",
                        prompt_feedback={"blockReason": "SAFETY"})
        self.assertEqual(content_side_stop_reason(out), "SAFETY")
        self.assertEqual(classify_dispatch_failure(out),
                         FAILURE_PROVIDER_CONTENT_STOP)

    def test_transport_error_is_a_provider_error(self):
        out = self._out(error="http_503")
        self.assertEqual(classify_dispatch_failure(out),
                         FAILURE_PROVIDER_ERROR)
        out2 = self._out(status="FAILED",
                         error="ProviderOutage: stub connection reset")
        self.assertEqual(classify_dispatch_failure(out2),
                         FAILURE_PROVIDER_ERROR)

    def test_no_image_without_a_content_stop_reason_is_a_provider_error(self):
        out = self._out(error="no_image_part_in_response",
                        finish_reason="STOP")
        self.assertEqual(classify_dispatch_failure(out),
                         FAILURE_PROVIDER_ERROR)

    def test_delivered_output_that_fails_contract_is_verification_fail(self):
        out = self._out(status="COMPLETED", error=None, content="wrong",
                        content_stripped="wrong")
        self.assertEqual(classify_dispatch_failure(out),
                         FAILURE_VERIFICATION_FAIL)

    def test_absent_finish_reason_is_never_inferred_as_a_content_stop(self):
        self.assertIsNone(content_side_stop_reason(self._out(error="http_429")))


# ─── Executor path ──────────────────────────────────────────────────────────

GOOGLE_WORKER = "google-nano-banana-2"


class _ContentStopAdapter:
    """Deterministic stub adapter reproducing the recorded provider behaviour.

    ``recitations`` = how many leading dispatches return the recorded
    ``IMAGE_RECITATION`` response before one returns a recorded image response.
    ``always`` = every dispatch is a content-side stop.
    """

    def __init__(self, recitations=0, always=False):
        self.recitations = recitations
        self.always = always
        self.contracts = []

    def dispatch(self, contract):
        self.contracts.append(dict(contract))
        idx = len(self.contracts) - 1
        recite = self.always or idx < self.recitations
        if recite:
            return {
                "dispatch_id": f"stub-recite-{idx}",
                "status": "FAILED", "provider": "google",
                "model": "gemini-3.1-flash-image",
                "requested_model": "gemini-3.1-flash-image",
                "content": None, "image_b64": None, "image_mime": None,
                "image_size_bytes": None, "image_dims": None,
                "image_decode_ok": False, "finish_reason": "IMAGE_RECITATION",
                "candidate_count": 1,
                "candidate_finish_reasons": ["IMAGE_RECITATION"],
                "response_part_kinds": [], "response_text_chars": None,
                "response_text_excerpt": None,
                "usage": {"promptTokenCount": 17, "totalTokenCount": 17},
                "prompt_feedback": None,
                "error": "no_image_part_in_response", "exit_code": 200,
                "runtime_s": 5.8,
                "requested_response_modalities": ["IMAGE"],
                "requested_image_config": None,
            }
        return {
            "dispatch_id": f"stub-image-{idx}",
            "status": "COMPLETED", "provider": "google",
            "model": "gemini-3.1-flash-image",
            "requested_model": "gemini-3.1-flash-image",
            "content": None, "image_b64": "AAAA", "image_mime": "image/jpeg",
            "image_size_bytes": 3, "image_dims": [1024, 1024],
            "image_decode_ok": True, "finish_reason": "STOP",
            "candidate_count": 1, "candidate_finish_reasons": ["STOP"],
            "response_part_kinds": ["inlineData:image/jpeg"],
            "response_text_chars": None, "response_text_excerpt": None,
            "usage": {"promptTokenCount": 17, "candidatesTokenCount": 1322,
                      "totalTokenCount": 1339},
            "prompt_feedback": None, "error": None, "exit_code": 0,
            "runtime_s": 6.5,
            "requested_response_modalities": ["IMAGE"],
            "requested_image_config": None,
        }


class _WrongDimsAdapter(_ContentStopAdapter):
    """A delivered image whose dimensions fail the declared contract."""

    def dispatch(self, contract):
        result = super().dispatch(contract)
        result.update({"image_dims": [64, 64]})  # contract expects 1024x1024
        return result


class _StubRegistry:
    def __init__(self, adapters):
        self.adapters = adapters         # worker_id -> adapter
        self.dispatched = []

    def is_routable(self, worker_id):
        return worker_id in self.adapters

    def adapter_for(self, worker_id):
        return self.adapters[worker_id]

    def report_usage(self, worker_id, result):
        return "obs-stub-1"


def _plan():
    node = {
        "node_id": "node-stop-1", "objective": "make a square",
        "capability_roles": ["vision"], "dependencies": [], "inputs": {},
        "expected_outputs": {}, "verification_method": "test", "floor_id": None,
        "allowed_tools": [], "permissions": {},
        "fallback_candidates": [],
    }
    return {"plan_id": "stop-1", "decomposition": False, "reason": "test",
            "nodes": [node]}


def _image_cases():
    return [
        {"name": "dispatch completed", "field": "status",
         "expected": "COMPLETED"},
        {"name": "image decoded", "field": "image_decode_ok", "expected": True},
    ]


class _ExecutorCase(unittest.TestCase):
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

    def _execute(self, adapters, cases=None, max_repair_attempts=0,
                 max_content_stop_retries=DEFAULT_MAX_CONTENT_STOP_RETRIES,
                 worker=GOOGLE_WORKER, escalation_fn=None):
        from e3_team_assembly import TeamAssembly, TeamAssignment
        plan = _plan()
        store = OrchestrationStore(self.db_path)
        registry = _StubRegistry(adapters)
        assembly = TeamAssembly(plan["plan_id"])
        assembly.assignments = [TeamAssignment("node-stop-1", worker, "vision",
                                               "HIGH", "test")]
        assembly.issues = []
        assembly.complete = True
        try:
            dag = self.planner.build_dag(plan)
            executor = E3ProductionExecutor(
                store, registry,
                escalator=(escalation_fn() if escalation_fn else None))
            run = executor.execute_plan(
                plan, dag, assembly, self.fingerprint, "make a square",
                verification_test_cases_by_node={
                    "node-stop-1": cases or _image_cases()},
                max_repair_attempts=max_repair_attempts,
                max_content_stop_retries=max_content_stop_retries,
                dispatch_timeout=5, role_by_node={"node-stop-1": "vision"})
            read_back = store.read_back("node-stop-1")
        finally:
            store.close()
        return run, read_back, registry


class ContentStopRecoveryTests(_ExecutorCase):
    """A bounded, identical, single-shot same-request retry is the recovery."""

    def test_budget_is_single_digit_and_two_retries(self):
        self.assertLess(DEFAULT_MAX_CONTENT_STOP_RETRIES, 10)
        self.assertEqual(DEFAULT_MAX_CONTENT_STOP_RETRIES, 2)

    def test_a_stop_followed_by_the_identical_request_recovers(self):
        # Recorded cluster: two consecutive stops then a success. A budget of 2
        # recovers exactly that shape.
        adapter = _ContentStopAdapter(recitations=2)
        run, read_back, _ = self._execute({GOOGLE_WORKER: adapter})
        node = run["nodes"][0]
        self.assertEqual(node["state"], "COMPLETE")
        self.assertEqual(run["outcome"], "EXECUTION_COMPLETE")
        self.assertEqual(node["content_stop_retries"], 2)
        self.assertEqual(len(adapter.contracts), 3)
        self.assertIsNone(node["failure_attribution"])

    def test_the_retry_is_the_identical_request_not_a_reworded_one(self):
        adapter = _ContentStopAdapter(recitations=1)
        _, _, _ = self._execute({GOOGLE_WORKER: adapter})
        objectives = [c["objective"] for c in adapter.contracts]
        self.assertEqual(objectives, ["make a square", "make a square"])
        # every attempt used the production shape, unchanged
        for contract in adapter.contracts:
            self.assertNotIn("response_modalities", contract)
            self.assertNotIn("image_config", contract)

    def test_unrecovered_stop_is_bounded_never_infinite(self):
        adapter = _ContentStopAdapter(always=True)
        run, read_back, _ = self._execute({GOOGLE_WORKER: adapter})
        node = run["nodes"][0]
        # initial dispatch + exactly DEFAULT_MAX_CONTENT_STOP_RETRIES retries
        self.assertEqual(len(adapter.contracts),
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(len(node["dispatch_attempts"]),
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(node["content_stop_retries"],
                         DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertNotEqual(node["state"], "COMPLETE")

    def test_zero_retry_budget_dispatch_once_then_terminate(self):
        adapter = _ContentStopAdapter(always=True)
        run, _, _ = self._execute({GOOGLE_WORKER: adapter},
                                  max_content_stop_retries=0)
        self.assertEqual(len(adapter.contracts), 1)
        self.assertEqual(run["nodes"][0]["state"], "BLOCKED")

    def test_repair_budget_cannot_be_spent_on_a_content_stop(self):
        # Even with a repair budget, a content stop uses same-request retries
        # (recorded as such) and never a reworded repair objective.
        adapter = _ContentStopAdapter(always=True)
        run, _, _ = self._execute({GOOGLE_WORKER: adapter},
                                  max_repair_attempts=1)
        node = run["nodes"][0]
        self.assertTrue(all(r.get("kind") == "same_request_retry"
                            for r in node["repairs"]))
        self.assertEqual(node["state"], "BLOCKED")


class ContentStopTerminalPathTests(_ExecutorCase):
    """The unrecovered stop must be attributed truthfully and escalate."""

    def test_terminal_attribution_is_provider_content_stop(self):
        adapter = _ContentStopAdapter(always=True)
        run, read_back, _ = self._execute({GOOGLE_WORKER: adapter})
        node = run["nodes"][0]
        self.assertEqual(node["state"], "BLOCKED")
        self.assertEqual(node["final_verification"], "FAIL")
        self.assertEqual(node["failure_attribution"],
                         FAILURE_PROVIDER_CONTENT_STOP)
        self.assertEqual(node["failure_finish_reason"], "IMAGE_RECITATION")
        self.assertIn("IMAGE_RECITATION", node["blocking_reason"])
        self.assertEqual(read_back["node"]["state"], "BLOCKED")
        self.assertEqual(read_back["evidence"][0]["final_success"], 0)
        self.assertEqual(read_back["evidence"][0]["failure_attribution"],
                         FAILURE_PROVIDER_CONTENT_STOP)

    def test_terminal_state_explains_why_no_image_arrived(self):
        adapter = _ContentStopAdapter(always=True)
        run, read_back, _ = self._execute({GOOGLE_WORKER: adapter})
        causes = [e["cause"] for e in read_back["state_events"]]
        self.assertTrue(any(
            c == "provider_content_stop_unrecovered:IMAGE_RECITATION"
            for c in causes), msg=causes)
        # and the reason is recorded on every stop attempt
        reasons = [a["finish_reason"] for a in run["nodes"][0]["dispatch_attempts"]]
        self.assertEqual(reasons, ["IMAGE_RECITATION"] * (1 + 2))

    def test_terminal_path_escalates_non_silently(self):
        from e3_escalate import E3Escalator
        escalator = E3Escalator()
        adapter = _ContentStopAdapter(always=True)
        run, _, _ = self._execute({GOOGLE_WORKER: adapter},
                                  escalation_fn=lambda: escalator)
        self.assertTrue(run["escalations"])
        esc = run["escalations"][0]
        self.assertEqual(esc["trigger"], "provider_content_stop")
        self.assertEqual(esc["finish_reason"], "IMAGE_RECITATION")
        active = escalator.get_active_escalations()
        self.assertEqual(len(active), 1)
        self.assertIn("IMAGE_RECITATION", active[0].context)
        self.assertTrue(active[0].owner_decision_needed)

    def test_never_a_pass_and_never_a_silent_verification_failure(self):
        adapter = _ContentStopAdapter(always=True)
        run, _, _ = self._execute({GOOGLE_WORKER: adapter})
        self.assertNotEqual(run["outcome"], "EXECUTION_COMPLETE")
        self.assertEqual(run["outcome"], "EXECUTION_BLOCKED")
        self.assertNotEqual(run["nodes"][0]["failure_attribution"],
                            FAILURE_VERIFICATION_FAIL)

    def test_content_stop_retries_and_finish_reason_reach_the_evidence_row(self):
        adapter = _ContentStopAdapter(always=True)
        _, read_back, _ = self._execute({GOOGLE_WORKER: adapter})
        row = read_back["evidence"][0]
        self.assertEqual(row["verification_outcome"], "FAIL")
        con = sqlite3.connect(str(self.db_path))
        try:
            det = con.execute(
                "SELECT deterministic_test_results FROM performance_evidence"
            ).fetchone()[0]
        finally:
            con.close()
        det = json.loads(det)
        self.assertEqual(det["content_stop_retries"],
                         DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(det["content_stop_finish_reasons"],
                         ["IMAGE_RECITATION"])
        self.assertEqual(det["failure_classes"], [FAILURE_PROVIDER_CONTENT_STOP])


class ContractIntegrityTests(_ExecutorCase):
    """The deterministic verification contract is not weakened."""

    def test_only_a_real_pass_reaches_complete(self):
        adapter = _ContentStopAdapter(recitations=1)
        run, _, _ = self._execute({GOOGLE_WORKER: adapter})
        node = run["nodes"][0]
        self.assertEqual(node["state"], "COMPLETE")
        self.assertEqual(node["final_verification"], "PASS")
        self.assertTrue(node["verification_attempts"][-1]["passed"])

    def test_delivered_image_that_fails_the_contract_is_verification_fail(self):
        # The contract case requires 1024x1024; the adapter delivers 64x64.
        cases = _image_cases() + [{"name": "dims", "field": "image_dims",
                                   "expected": [1024, 1024]}]
        adapter = _WrongDimsAdapter(always=False)
        run, _, _ = self._execute({GOOGLE_WORKER: adapter}, cases=cases)
        node = run["nodes"][0]
        self.assertEqual(node["state"], "FAILED")
        self.assertEqual(node["failure_attribution"], FAILURE_VERIFICATION_FAIL)
        self.assertEqual(node["content_stop_retries"], 0)


class WorkerIdentityAndE4E5Tests(_ExecutorCase):
    """No silent worker switch; the outcome is visible to E5 convergence."""

    def test_content_stop_never_silently_switches_worker(self):
        adapter = _ContentStopAdapter(always=True)
        other = _ContentStopAdapter(recitations=0)
        run, _, registry = self._execute({GOOGLE_WORKER: adapter,
                                          "equivalent-worker": other})
        node = run["nodes"][0]
        self.assertEqual(node["worker_id"], GOOGLE_WORKER)
        # the designated-but-not-auto-selected equivalent was never dispatched
        self.assertEqual([c["objective"] for c in other.contracts], [])
        self.assertEqual(node["state"], "BLOCKED")  # escalation, not a silent swap
        self.assertTrue(run["escalations"][0]["escalation_id"])

    def test_e5_repeated_failure_convergence_observes_the_outcome(self):
        from safe_mode import ConvergenceEnforcer, SafeModeManager
        init_con = init_db(self.db_path)
        init_con.close()
        con = sqlite3.connect(str(self.db_path))
        try:
            enforcer = ConvergenceEnforcer(con, max_retries=2)
            manager = SafeModeManager(con)
            adapter = _ContentStopAdapter(always=True)
            attributions = []
            events = []
            for _ in range(3):
                run, _, _ = self._execute({GOOGLE_WORKER: adapter})
                attributions.append(run["nodes"][0]["failure_attribution"])
                count = manager.record_failure(GOOGLE_WORKER, "code")
                events.append(enforcer.record_convergence_event(
                    GOOGLE_WORKER, "code", count))
            # every repeat was truthfully attributed, so convergence never sees
            # an unattributed "pass"
            self.assertEqual(attributions,
                             [FAILURE_PROVIDER_CONTENT_STOP] * 3)
            self.assertEqual([e["action_taken"] for e in events],
                             ["warn_and_reduce_scope", "quarantine_worker",
                              "quarantine_worker"])
            self.assertTrue(events[1]["escalated"])
            # convergence still caps retries exactly as before
            self.assertTrue(enforcer.can_retry("node-stop-1"))
            enforcer.record_attempt("node-stop-1")
            enforcer.record_attempt("node-stop-1")
            self.assertFalse(enforcer.can_retry("node-stop-1"))
            should_stop, reason = enforcer.should_stop("node-stop-1")
            self.assertTrue(should_stop)
            self.assertIn("Max retries", reason)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
