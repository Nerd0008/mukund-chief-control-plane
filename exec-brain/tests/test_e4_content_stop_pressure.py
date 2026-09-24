#!/usr/bin/env python3
"""E4 resource continuity: recorded provider content-side stop pressure.

The E4 resource-continuity surface measured only tokens, cost and
time-to-exhaustion, so a provider (or provider/model pair) that repeatedly
withholds content while still consuming prompt tokens was reported as healthy
capacity. These tests cover the added pressure view.

Everything here is offline and spends **zero** real provider calls:

* the store-side fixtures are produced by the *real* E3 execution leg driven by
  deterministic stub adapters on an isolated scratch db (the same pattern as
  ``test_e3_operator_surface.py``), so the rows the view reads are genuinely the
  rows the leg persists;
* the recorded-series side consumes the already-recorded artifact
  ``audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/``
  verbatim (2 of 9 identical single-image requests returned
  ``finishReason=IMAGE_RECITATION``) and re-runs nothing.

What is asserted:

* a clean provider reports no pressure (rate 0.0 over a stated sample size);
* a provider whose recorded attempts include content-side stops reports the
  truthful rate, sample size, last observed finishReason and last stop time;
* a provider with zero (or unclassified) attempts reports ``unknown`` — never a
  fabricated rate, and never healthy capacity;
* every rate is reported with its sample size, and no rate is reported from zero
  attempts;
* the view is an observation: it writes nothing, swaps no worker, re-dispatches
  nothing and enters neither safe mode nor Stage 2.
"""

import argparse
import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

from e3_commands import E3Commands, content_stop_pressure_lines  # noqa: E402
from e3_execution import (  # noqa: E402
    DEFAULT_MAX_CONTENT_STOP_RETRIES, E3ProductionExecutor,
    ExecutionAdapterRegistry, OrchestrationStore,
)
from e3_planner import E3Planner  # noqa: E402
from e3_team_assembly import TeamAssembly, TeamAssignment  # noqa: E402
from resource_monitor import (  # noqa: E402
    MEASURABLE_CONTENT_STOP_MIN_SAMPLE, MEASURABLE_CONTENT_STOP_RATE,
    PRESSURE_STATUS_CLEAN, PRESSURE_STATUS_PRESSURED,
    PRESSURE_STATUS_STOPS_RECORDED_BELOW_BOUND, PRESSURE_STATUS_UNKNOWN,
    ResourceMonitor, build_content_stop_pressure_view, content_stop_pressure,
    evidence_row_ledgers, recorded_series_ledger, render_content_stop_pressure,
)
from task_fingerprint import TaskFingerprint  # noqa: E402
from worker_registry import WorkerRegistry  # noqa: E402

GOOGLE_WORKER = "google-nano-banana-2"
GOOGLE_PROVIDER = "google"
GOOGLE_MODEL = "gemini-3.1-flash-image"
FINISH_REASON = "IMAGE_RECITATION"

RECORDED_SERIES_PATH = (
    REPO_ROOT / "audits" / "evidence"
    / "2026-09-24T01-44-32Z-e3-google-image-repeat-series" / "observations.json")


# ─── stub adapters (deterministic; no credential, no network) ────────

class ContentStopAdapter:
    """Reproduces the recorded provider content-side stop, call for call."""

    def __init__(self):
        self.calls = 0

    def dispatch(self, contract):
        self.calls += 1
        return {
            "dispatch_id": f"stub-content-stop-{self.calls}",
            "status": "FAILED", "provider": GOOGLE_PROVIDER,
            "model": GOOGLE_MODEL, "requested_model": GOOGLE_MODEL,
            "content": None, "image_dims": None, "image_decode_ok": False,
            "finish_reason": FINISH_REASON, "candidate_count": 1,
            "candidate_finish_reasons": [FINISH_REASON],
            "response_part_kinds": [],
            "usage": {"promptTokenCount": 17, "totalTokenCount": 17},
            "prompt_feedback": None, "error": "no_image_part_in_response",
            "exit_code": 200, "runtime_s": 5.8,
        }


class PassingAdapter:
    """Deterministic stub delivering a well-formed, verifying output."""

    def __init__(self):
        self.calls = 0

    def dispatch(self, contract):
        self.calls += 1
        return {"dispatch_id": f"stub-ok-{self.calls}", "status": "COMPLETED",
                "provider": GOOGLE_PROVIDER, "model": GOOGLE_MODEL,
                "content": "ok", "usage": None, "error": None,
                "exit_code": 0, "runtime_s": 0.1}


def _run_execution(db_path, adapter, plan_id, node_id):
    """Drive the real execution leg on an isolated db with a stub adapter."""
    plan = {
        "plan_id": plan_id, "decomposition": False, "reason": "pressure test",
        "nodes": [{
            "node_id": node_id, "objective": "content-stop pressure test",
            "capability_roles": ["vision"], "dependencies": [], "inputs": {},
            "expected_outputs": {}, "verification_method": "test",
            "floor_id": None, "allowed_tools": [], "permissions": {},
            "fallback_candidates": [],
        }],
    }
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
    try:
        executor = E3ProductionExecutor(store, registry)
        return executor.execute_plan(
            plan, E3Planner().build_dag(plan), assembly, fingerprint,
            "content-stop pressure test",
            verification_test_cases_by_node={node_id: [
                {"name": "dispatch completed", "field": "status",
                 "expected": "COMPLETED"}]},
            max_repair_attempts=0, dispatch_timeout=5,
            role_by_node={node_id: "vision"})
    finally:
        store.close()


def _ledger(worker_id=GOOGLE_WORKER, provider=GOOGLE_PROVIDER,
            model=GOOGLE_MODEL, attempts: Optional[int] = 6, stops=0, reasons=(),
            timestamp="2026-09-24 01:44:32", source="test_source"):
    """A hand-built attempt ledger summary (pure-function fixtures only)."""
    return {
        "source": source, "worker_id": worker_id, "provider": provider,
        "model": model, "attempts_recorded": attempts,
        "attempts_classified": attempts if attempts is not None else 0,
        "content_stops_observed": stops, "finish_reasons": list(reasons),
        "ledger_readable": True, "content_stop_ledger_recorded": True,
        "failure_attribution": None, "timestamp": timestamp, "dag_node_id": None,
    }


class _IsolatedStoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "orchestration.db"

    def _store(self):
        return OrchestrationStore(self.db_path)

    def _monitor(self, con=None):
        return ResourceMonitor(orchestration_con=con, governor_con=None)

    def _view(self, series_paths=()):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            return self._monitor(con).get_content_stop_pressure(
                series_paths=series_paths)
        finally:
            con.close()

    def _group(self, view, source="orchestration_store.performance_evidence",
               provider=GOOGLE_PROVIDER) -> Any:
        for src in view["sources"]:
            if src["source"] != source:
                continue
            for group in src["groups"]:
                if group["provider"] == provider:
                    return group
        return None


# ─── pure aggregation ───────────────────────────────────────────────

class PurePressureAggregationTests(unittest.TestCase):
    """The aggregation itself: no store, no artifact, no provider."""

    def test_clean_provider_reports_no_pressure(self):
        view = content_stop_pressure([_ledger(attempts=6, stops=0)])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["attempts_observed"], 6)
        self.assertEqual(group["content_stops_observed"], 0)
        self.assertEqual(group["content_stop_rate"], 0.0)
        self.assertEqual(group["sample_size"], 6)
        self.assertFalse(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_CLEAN)
        self.assertFalse(view["content_stop_pressure_detected"])
        self.assertIsNone(group["last_finish_reason"])

    def test_recorded_stops_report_the_truthful_rate_and_reason(self):
        view = content_stop_pressure([
            _ledger(attempts=9, stops=2, reasons=[FINISH_REASON])])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["content_stops_observed"], 2)
        self.assertEqual(group["sample_size"], 9)
        self.assertAlmostEqual(group["content_stop_rate"], 2 / 9)
        self.assertTrue(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_PRESSURED)
        self.assertEqual(group["last_finish_reason"], FINISH_REASON)
        self.assertEqual(group["last_stop_at"], "2026-09-24 01:44:32")
        self.assertTrue(view["content_stop_pressure_detected"])

    def test_stops_below_the_minimum_sample_are_not_flagged_but_still_reported(self):
        view = content_stop_pressure([_ledger(attempts=3, stops=3,
                                              reasons=[FINISH_REASON])])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["content_stop_rate"], 1.0)
        self.assertEqual(group["sample_size"], 3)
        self.assertFalse(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_STOPS_RECORDED_BELOW_BOUND)
        self.assertFalse(view["content_stop_pressure_detected"])

    def test_zero_attempts_report_unknown_never_a_rate(self):
        view = content_stop_pressure([_ledger(attempts=0, stops=0)])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["attempts_observed"], 0)
        self.assertEqual(group["sample_size"], 0)
        self.assertIsNone(group["content_stop_rate"])
        self.assertIsNone(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_UNKNOWN)
        rendered = "\n".join(render_content_stop_pressure(view))
        self.assertIn("stop rate: unknown", rendered)
        self.assertNotIn("stop rate: 0", rendered)

    def test_unclassified_ledger_reports_unknown_not_clean(self):
        ledger = _ledger(attempts=None, stops=0)
        ledger["ledger_readable"] = True
        ledger["content_stop_ledger_recorded"] = False
        ledger["attempts_classified"] = 0
        view = content_stop_pressure([ledger])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["attempts_observed"], 0)
        self.assertEqual(group["rows_without_readable_ledger"], 1)
        self.assertEqual(group["status"], PRESSURE_STATUS_UNKNOWN)
        self.assertIsNone(group["content_stop_rate"])

    def test_attempts_without_the_content_stop_ledger_are_counted_but_unclassified(self):
        ledger = _ledger(attempts=11, stops=0)
        ledger["attempts_classified"] = 0
        view = content_stop_pressure([ledger])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["attempts_observed"], 11)
        self.assertEqual(group["attempts_classified"], 0)
        self.assertEqual(group["attempts_unclassified"], 11)
        self.assertIsNone(group["content_stop_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_UNKNOWN)

    def test_boundaries_are_reported_with_every_view(self):
        view = content_stop_pressure([_ledger(attempts=6, stops=0)])
        self.assertEqual(view["rate_threshold"], MEASURABLE_CONTENT_STOP_RATE)
        self.assertEqual(view["minimum_sample"], MEASURABLE_CONTENT_STOP_MIN_SAMPLE)
        self.assertTrue(view["observation_only"])
        self.assertIn("no automatic worker swap", view["decision"])
        rendered = "\n".join(render_content_stop_pressure(view))
        self.assertIn(f"rate >= {MEASURABLE_CONTENT_STOP_RATE}", rendered)
        self.assertIn(f"sample >= {MEASURABLE_CONTENT_STOP_MIN_SAMPLE}", rendered)

    def test_every_reported_rate_carries_its_sample_size(self):
        view = content_stop_pressure([_ledger(attempts=9, stops=2,
                                             reasons=[FINISH_REASON])])
        rendered = "\n".join(render_content_stop_pressure(view))
        self.assertIn("stop rate: 0.222 (sample size 9 classified attempts; "
                      "2/9 classified recorded dispatch attempts)", rendered)

    def test_sources_are_never_merged(self):
        view = content_stop_pressure([
            _ledger(attempts=4, stops=0, source="a_source"),
            _ledger(attempts=9, stops=2, reasons=[FINISH_REASON],
                    source="b_source"),
        ])
        self.assertEqual([s["source"] for s in view["sources"]],
                         ["a_source", "b_source"])
        self.assertEqual([s["content_stops_observed"] for s in view["sources"]],
                         [0, 2])


# ─── recorded provider series artifact ──────────────────────────────

class RecordedSeriesTests(unittest.TestCase):
    """The recorded IMAGE_RECITATION series is consumed verbatim."""

    def test_recorded_series_is_present_in_the_repo(self):
        self.assertTrue(RECORDED_SERIES_PATH.exists(),
                        f"recorded series artifact missing: {RECORDED_SERIES_PATH}")

    def test_recorded_series_reports_its_recorded_stop_rate(self):
        ledger = recorded_series_ledger(RECORDED_SERIES_PATH)
        self.assertEqual(ledger["attempts_recorded"], 9)
        self.assertEqual(ledger["content_stops_observed"], 2)
        self.assertEqual(ledger["finish_reasons"], [FINISH_REASON])
        self.assertEqual(ledger["provider"], GOOGLE_PROVIDER)
        self.assertEqual(ledger["model"], GOOGLE_MODEL)
        self.assertEqual(ledger["worker_id"], GOOGLE_WORKER)

        view = content_stop_pressure([ledger])
        group = view["sources"][0]["groups"][0]
        self.assertAlmostEqual(group["content_stop_rate"], 2 / 9)
        self.assertEqual(group["sample_size"], 9)
        self.assertTrue(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_PRESSURED)
        self.assertEqual(group["last_finish_reason"], FINISH_REASON)
        self.assertTrue(view["content_stop_pressure_detected"])
        rendered = "\n".join(render_content_stop_pressure(view))
        self.assertIn(FINISH_REASON, rendered)
        self.assertIn("content withheld at a measurable rate: yes", rendered)

    def test_reading_the_recorded_series_does_not_modify_it(self):
        before = hashlib.sha256(RECORDED_SERIES_PATH.read_bytes()).hexdigest()
        recorded_series_ledger(RECORDED_SERIES_PATH)
        after = hashlib.sha256(RECORDED_SERIES_PATH.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_a_clean_recorded_series_reports_no_stops(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "observations.json"
        path.write_text(json.dumps({
            "label": "clean-series", "worker_id": GOOGLE_WORKER,
            "provider_calls_planned": 6, "calls_attempted": 6,
            "observations": [
                {"index": i, "executed": True, "finish_reason": "STOP",
                 "candidate_finish_reasons": ["STOP"],
                 "classification": "image_decoded",
                 "requested_model": GOOGLE_MODEL}
                for i in range(1, 7)],
        }), encoding="utf-8")
        ledger = recorded_series_ledger(path)
        self.assertEqual(ledger["attempts_recorded"], 6)
        self.assertEqual(ledger["content_stops_observed"], 0)
        view = content_stop_pressure([ledger])
        self.assertEqual(view["sources"][0]["groups"][0]["status"],
                         PRESSURE_STATUS_CLEAN)

    def test_two_recorded_series_never_merge_into_one_sample(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        paths = []
        for label, stops in (("series-a", 2), ("series-b", 1)):
            path = Path(tmp.name) / f"{label}.json"
            path.write_text(json.dumps({
                "label": label, "worker_id": GOOGLE_WORKER,
                "observations": [
                    {"index": i, "executed": True,
                     "finish_reason": FINISH_REASON if i <= stops else "STOP",
                     "candidate_finish_reasons": [],
                     "requested_model": GOOGLE_MODEL}
                    for i in range(1, 7)],
            }), encoding="utf-8")
            paths.append(path)
        view = content_stop_pressure([recorded_series_ledger(p) for p in paths])
        self.assertEqual(len(view["sources"]), 2)
        self.assertEqual([s["content_stops_observed"] for s in view["sources"]],
                         [2, 1])
        self.assertAlmostEqual(view["sources"][0]["groups"][0]["content_stop_rate"],
                               2 / 6)

    def test_an_empty_recorded_series_is_unknown_not_clean(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "observations.json"
        path.write_text(json.dumps({"label": "empty", "worker_id": GOOGLE_WORKER,
                                    "observations": []}), encoding="utf-8")
        view = content_stop_pressure([recorded_series_ledger(path)])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["attempts_observed"], 0)
        self.assertEqual(group["status"], PRESSURE_STATUS_UNKNOWN)
        self.assertIsNone(group["content_stop_rate"])


# ─── store rows produced by the real execution leg ──────────────────

class StoreBackedPressureTests(_IsolatedStoreCase):
    def test_clean_provider_group_reports_no_pressure(self):
        run = _run_execution(self.db_path, PassingAdapter(),
                             "plan-pressure-clean", "node-pressure-clean")
        self.assertEqual(run["nodes"][0]["state"], "COMPLETE")
        group = self._group(self._view())
        self.assertIsNotNone(group)
        self.assertEqual(group["attempts_observed"], 1)
        self.assertEqual(group["attempts_classified"], 1)
        self.assertEqual(group["content_stops_observed"], 0)
        self.assertEqual(group["content_stop_rate"], 0.0)
        self.assertEqual(group["sample_size"], 1)
        self.assertFalse(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_CLEAN)

    def test_content_stop_rows_report_the_truthful_rate_and_finish_reason(self):
        adapter = ContentStopAdapter()
        run = _run_execution(self.db_path, adapter,
                             "plan-pressure-stop", "node-pressure-stop")
        self.assertEqual(run["nodes"][0]["state"], "BLOCKED")
        self.assertEqual(adapter.calls, 1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)

        group = self._group(self._view())
        self.assertEqual(group["attempts_observed"],
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(group["attempts_classified"],
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(group["content_stops_observed"],
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(group["content_stop_rate"], 1.0)
        self.assertEqual(group["sample_size"],
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(group["last_finish_reason"], FINISH_REASON)
        self.assertIsNotNone(group["last_stop_at"])
        # Below the stated minimum sample the bounded flag stays off, while the
        # raw rate and reason remain visible.
        self.assertFalse(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"],
                         PRESSURE_STATUS_STOPS_RECORDED_BELOW_BOUND)

    def test_repeated_stops_across_nodes_flag_the_measurable_rate(self):
        for index in (1, 2):
            _run_execution(self.db_path, ContentStopAdapter(),
                           f"plan-pressure-repeat-{index}",
                           f"node-pressure-repeat-{index}")
        group = self._group(self._view())
        self.assertEqual(group["attempts_classified"],
                         2 * (1 + DEFAULT_MAX_CONTENT_STOP_RETRIES))
        self.assertEqual(group["content_stops_observed"],
                         2 * (1 + DEFAULT_MAX_CONTENT_STOP_RETRIES))
        self.assertTrue(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_PRESSURED)
        self.assertTrue(self._view()["content_stop_pressure_detected"])

    def test_a_row_without_the_content_stop_ledger_is_unknown_not_clean(self):
        """A row recorded before the classification existed holds no stop count."""
        store = self._store()
        try:
            store.record_evidence({
                "evidence_id": "evidence-legacy-1",
                "worker_id": GOOGLE_WORKER, "provider": GOOGLE_PROVIDER,
                "model": GOOGLE_MODEL, "role": "vision",
                "verification_outcome": "FAIL", "final_success": False,
                "failure_attribution": "verification_fail",
                # the pre-attribution shape: attempts/rejections/repairs only
                "deterministic_test_results": {
                    "attempts": [{"attempt": 1, "outcome": "FAIL"}],
                    "rejections": 1, "repairs": 0},
                "dag_node_id": "node-legacy-1",
            })
        finally:
            store.close()

        group = self._group(self._view())
        self.assertEqual(group["attempts_observed"], 1)
        self.assertEqual(group["attempts_classified"], 0)
        self.assertEqual(group["content_stops_observed"], 0)
        self.assertIsNone(group["content_stop_rate"])
        self.assertIsNone(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], PRESSURE_STATUS_UNKNOWN)

    def test_an_empty_store_reports_unknown_not_clear(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("SELECT 1")  # store created lazily by the monitor below
        finally:
            con.close()
        # A store whose tables do not exist yet must not fabricate a view.
        view = self._view()
        self.assertEqual(view["sources"], [])
        self.assertFalse(view["content_stop_pressure_detected"])
        rendered = "\n".join(render_content_stop_pressure(view))
        self.assertIn("pressure unknown, not clear", rendered)

    def test_the_view_writes_nothing_and_acts_on_nothing(self):
        _run_execution(self.db_path, ContentStopAdapter(),
                       "plan-pressure-readonly", "node-pressure-readonly")
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        before = {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("performance_evidence", "dag_node", "dag_state_event",
                          "safe_mode_event", "resource_checkpoint",
                          "resource_snapshot", "convergence_event")
        }
        view = self._monitor(con).get_content_stop_pressure()
        after = {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        con.close()
        self.assertEqual(before, after)
        self.assertTrue(view["observation_only"])
        self.assertIn("no automatic worker swap", view["decision"])
        # The stop is reported, never auto-acted on.
        group = self._group(view)
        self.assertEqual(group["status"],
                         PRESSURE_STATUS_STOPS_RECORDED_BELOW_BOUND)
        self.assertNotIn("failover", group["status"])
        self.assertNotIn("swapped", group["status"])

    def test_evidence_row_ledgers_reads_the_persisted_columns(self):
        _run_execution(self.db_path, ContentStopAdapter(),
                       "plan-pressure-ledger", "node-pressure-ledger")
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            ledgers = evidence_row_ledgers(con)
        finally:
            con.close()
        self.assertEqual(len(ledgers), 1)
        ledger = ledgers[0]
        self.assertEqual(ledger["worker_id"], GOOGLE_WORKER)
        self.assertEqual(ledger["provider"], GOOGLE_PROVIDER)
        self.assertEqual(ledger["model"], GOOGLE_MODEL)
        self.assertEqual(ledger["attempts_recorded"],
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(ledger["attempts_classified"],
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(ledger["content_stops_observed"],
                         1 + DEFAULT_MAX_CONTENT_STOP_RETRIES)
        self.assertEqual(ledger["finish_reasons"], [FINISH_REASON])
        self.assertTrue(ledger["content_stop_ledger_recorded"])


# ─── operator-facing surface ────────────────────────────────────────

class OperatorSurfacePressureTests(_IsolatedStoreCase):
    def _commands(self):
        cmd = E3Commands(self.db_path)
        self.addCleanup(lambda: cmd.con is not None and cmd.con.close())
        return cmd

    def _capture(self, fn):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn()
        return buf.getvalue()

    def test_e3_status_exposes_the_pressure_section(self):
        _run_execution(self.db_path, ContentStopAdapter(),
                       "plan-pressure-surface", "node-pressure-surface")
        out = self._capture(lambda: self._commands().status(argparse.Namespace()))
        self.assertIn("E4 Resource Continuity: provider content-side stop "
                      "pressure", out)
        self.assertIn("content-side stops observed", out)
        self.assertIn("stop rate: 1.000", out)
        self.assertIn("sample size", out)
        self.assertIn(FINISH_REASON, out)
        self.assertIn("decision: observation only", out)
        self.assertIn("no automatic worker swap", out)

    def test_e3_status_includes_a_recorded_series_source_when_given(self):
        _run_execution(self.db_path, ContentStopAdapter(),
                       "plan-pressure-surface-2", "node-pressure-surface-2")
        out = self._capture(lambda: self._commands().status(
            argparse.Namespace(pressure_series=[str(RECORDED_SERIES_PATH)])))
        self.assertIn("source: recorded_provider_series", out)
        self.assertIn("stop rate: 0.222", out)
        self.assertIn("(sample size 9 classified attempts", out)
        self.assertIn("content withheld at a measurable rate: yes", out)
        self.assertIn("content_stop_pressure_detected: yes", out)

    def test_e3_status_reports_unknown_rather_than_clear_with_no_rows(self):
        out = self._capture(lambda: self._commands().status(argparse.Namespace()))
        self.assertIn("pressure unknown, not clear", out)
        self.assertIn("content_stop_pressure_detected: no", out)

    def test_pressure_lines_are_available_without_a_store_connection(self):
        lines = content_stop_pressure_lines(None)
        self.assertIsNotNone(lines)
        rendered = "\n".join(lines)
        self.assertIn("pressure unknown, not clear", rendered)

    def test_a_missing_series_artifact_is_reported_not_invented(self):
        _run_execution(self.db_path, PassingAdapter(),
                       "plan-pressure-missing", "node-pressure-missing")
        out = self._capture(lambda: self._commands().status(
            argparse.Namespace(pressure_series=["does-not-exist.json"])))
        self.assertIn("source error (recorded evidence only)", out)

    def test_cli_parser_exposes_the_pressure_series_option(self):
        from e3_cli import register
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd")
        register(sub)
        args = parser.parse_args(["e3-status", "--pressure-series", "a.json",
                                  "--pressure-series", "b.json"])
        self.assertEqual(args.pressure_series, ["a.json", "b.json"])
        args = parser.parse_args(["e3-status"])
        self.assertIsNone(args.pressure_series)


class MonitorApiTests(unittest.TestCase):
    """The E4 surface exposes the view through ResourceMonitor itself."""

    def test_resource_monitor_without_connections_reports_unknown(self):
        view = ResourceMonitor(None, None).get_content_stop_pressure()
        self.assertEqual(view["sources"], [])
        self.assertTrue(view["observation_only"])

    def test_resource_monitor_accepts_recorded_series_paths(self):
        view = ResourceMonitor(None, None).get_content_stop_pressure(
            series_paths=[RECORDED_SERIES_PATH])
        group = view["sources"][0]["groups"][0]
        self.assertEqual(group["worker_id"], GOOGLE_WORKER)
        self.assertAlmostEqual(group["content_stop_rate"], 2 / 9)
        self.assertTrue(group["content_withheld_at_measurable_rate"])

    def test_builder_never_returns_a_rate_without_a_sample(self):
        view = build_content_stop_pressure_view(None)
        self.assertEqual(view["sources"], [])
        self.assertIsNone(view.get("content_stop_rate"))


if __name__ == "__main__":
    unittest.main()
