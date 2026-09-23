#!/usr/bin/env python3
"""Tests for the E4/E5 real-path drill harness and the E5 recovery/override path.

No test in this module makes a provider call: the harness itself replaces provider
transport with a recorded in-process stub, and the assertions below pin the
truthfulness rules of the drills — that a stubbed failure is never reported as
real provider evidence, that a node only reaches COMPLETE after a verification
PASS, that failover is never fabricated, that the convergence cap is bounded, and
that safe-mode recovery requires both a healthy probe and a recorded owner
override for owner-only triggers.
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from e4e5_drill_harness import (  # noqa: E402
    EVIDENCE_KIND, E4E5DrillHarness, StubProviderAdapter, hash_live_stores,
    write_evidence,
)
from orchestration_db import init_db  # noqa: E402
from safe_mode import (  # noqa: E402
    OWNER_ONLY_TRIGGERS, SafeModeManager, SafeModeRecovery,
    record_owner_override,
)


class HarnessFixture(unittest.TestCase):
    """Runs the whole drill set once per class and shares the report."""

    report = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="e4e5-drill-tests-")
        cls.harness = E4E5DrillHarness(scratch_root=Path(cls._tmp.name))
        cls.before = hash_live_stores(cls.harness.runtime_root)
        cls.report = cls.harness.run()
        cls.after = hash_live_stores(cls.harness.runtime_root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestDrillTruthRules(HarnessFixture):

    def test_all_checks_pass(self):
        failed = [k for k, v in self.report["checks"].items() if not v]
        self.assertEqual(failed, [], f"failed drill checks: {failed}")
        self.assertEqual(self.report["checks_passed"],
                         self.report["checks_total"])

    def test_evidence_is_labelled_as_stubbed_not_real_provider_evidence(self):
        self.assertEqual(self.report["evidence_kind"], EVIDENCE_KIND)
        self.assertIn("NOT real external provider evidence",
                      self.report["evidence_kind_note"])

    def test_no_real_provider_call_is_made(self):
        self.assertEqual(self.report["real_provider_calls"], 0)
        self.assertGreater(self.report["stub_dispatches"], 0)

    def test_stage2_not_enabled_and_no_deployment(self):
        self.assertFalse(self.report["stage2_enabled"])
        self.assertFalse(self.report["deployment_performed"])

    def test_live_stores_untouched_by_the_drills(self):
        self.assertEqual(self.report["isolation"]["live_stores_changed"], [])
        self.assertEqual(self.before, self.after)
        self.assertTrue(self.report["isolation"]["isolated_db_exists"])

    def test_live_registry_is_read_from_a_snapshot_not_the_live_file(self):
        source = self.report["drills"]["D1"]["live_registry_read_only"]["source"]
        self.assertIn(source, ("live_registry_read_only_snapshot",
                               "live_registry_absent"))
        if source == "live_registry_read_only_snapshot":
            self.assertTrue(
                self.report["drills"]["D1"]["live_registry_read_only"]
                ["live_file_untouched"])

    def test_no_live_e2_row_written(self):
        self.assertEqual(self.report["isolation"]["e2_rows_written"], 0)
        self.assertIn("stub", self.report["isolation"]["e2_linkage_kind"])

    def test_every_stub_dispatch_is_marked_as_a_stub(self):
        self.assertTrue(self.report["adapter_call_log"])
        self.assertTrue(all("objective_hash" in entry
                            for entry in self.report["adapter_call_log"]))


class TestCheckpointFailoverDrill(HarnessFixture):

    def test_checkpoint_created_and_restored_exactly(self):
        cp = self.report["drills"]["D1"]["checkpoint"]
        self.assertTrue(cp["checkpoint_id"].startswith("ckpt-"))
        self.assertEqual(len(cp["checkpoints_for_task"]), 1)
        self.assertTrue(cp["restore_matches_saved"])
        self.assertEqual(cp["restored"]["state"], cp["state_saved"])

    def test_primary_worker_failed_honestly(self):
        primary = self.report["drills"]["D1"]["primary_dispatch"]
        self.assertEqual(primary["node_state"], "FAILED")
        self.assertTrue(primary["dispatch_attempts"][0]["error"])
        self.assertNotEqual(primary["node_state"], "COMPLETE")

    def test_equivalent_worker_selected_from_registry(self):
        eq = self.report["drills"]["D1"]["equivalent_selection"]
        self.assertIsNotNone(eq)
        self.assertEqual(eq["worker_id"], "codex-cli")
        self.assertEqual(eq["role"], "builder")

    def test_handover_state_reached_the_replacement_worker(self):
        d1 = self.report["drills"]["D1"]
        self.assertTrue(d1["handover_objective_delivered_to_replacement"])
        self.assertEqual(d1["handover"]["restored_checkpoint_id"],
                         d1["checkpoint"]["checkpoint_id"])

    def test_replacement_completed_only_after_verification_pass(self):
        repl = self.report["drills"]["D1"]["replacement_dispatch"]
        self.assertEqual(repl["node_state"], "COMPLETE")
        self.assertEqual(repl["final_verification"], "PASS")
        self.assertEqual(repl["verification_attempts"][-1]["passed"], True)

    def test_failover_is_not_fabricated(self):
        d1 = self.report["drills"]["D1"]
        # The replacement is a *stub* dispatch with a real verification PASS; the
        # drill must not present it as real-provider failover evidence.
        self.assertEqual(self.report["evidence_kind"], EVIDENCE_KIND)
        self.assertTrue(d1["failover_log_shows_failed_then_complete"])


class TestEscalationAndOutageDrills(HarnessFixture):

    def test_no_equivalent_worker_returns_none_and_escalates(self):
        d2 = self.report["drills"]["D2"]
        self.assertIsNone(d2["equivalent_found"])
        self.assertEqual(d2["escalation"]["trigger"], "no_qualified_worker")
        self.assertFalse(d2["quality_floor_lowered"])
        self.assertEqual(d2["gate_result"], "OWNER_APPROVAL_REQUIRED")
        self.assertTrue(d2["rationale_id"].startswith("rationale-"))

    def test_provider_outage_fails_the_node_both_ways(self):
        variants = self.report["drills"]["D3"]["variants"]
        self.assertEqual(variants["reported_provider_error"]["node_state"], "FAILED")
        self.assertEqual(variants["raised_transport_error"]["node_state"], "FAILED")
        self.assertTrue(self.report["drills"]["D3"]["no_node_reached_complete"])

    def test_outage_errors_are_recorded_verbatim(self):
        errors = self.report["drills"]["D3"]["errors_recorded_verbatim"]
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(errors))

    def test_no_failover_claimed_for_a_pure_outage(self):
        self.assertFalse(self.report["drills"]["D3"]["failover_claimed"])


class TestMalformedOutputDrill(HarnessFixture):

    def test_structural_malformation_is_flagged(self):
        v = self.report["drills"]["D4"]["validator"]
        self.assertTrue(v["flags_structural_malformation"])
        for case in ("none", "empty_string", "missing_required_field"):
            self.assertFalse(v["cases"][case]["valid"])

    def test_shallow_precheck_limitation_is_recorded_not_hidden(self):
        v = self.report["drills"]["D4"]["validator"]
        self.assertTrue(v["shallow_precheck_passes_garbage_string"])
        self.assertIn("deterministic verifier", v["authority"])

    def test_sanitizer_strips_non_printables(self):
        v = self.report["drills"]["D4"]["validator"]
        self.assertTrue(v["sanitizer_removed_non_printables"])

    def test_malformed_output_is_never_accepted(self):
        d4 = self.report["drills"]["D4"]
        self.assertEqual(d4["no_repair_budget"]["node_state"], "FAILED")
        self.assertTrue(d4["no_repair_budget"]["rejections"])

    def test_repair_path_converges_to_a_verified_complete(self):
        d4 = self.report["drills"]["D4"]["with_repair_budget"]
        self.assertEqual(d4["node_state"], "COMPLETE")
        self.assertEqual(d4["final_verification"], "PASS")
        self.assertEqual(d4["dispatch_count"], 2)
        states = [e["new_state"] for e in d4["state_log"]]
        self.assertIn("REWORK", states)


class TestConvergenceDrill(HarnessFixture):

    def test_cap_is_bounded_and_the_loop_terminates(self):
        d5 = self.report["drills"]["D5"]
        self.assertTrue(d5["loop_terminated_by_cap"])
        self.assertTrue(d5["iterations_bounded"])
        self.assertEqual(d5["stop_markers"], 1)
        self.assertEqual(d5["iterations_total"], d5["cap"] + 1)

    def test_dispatches_match_the_cap_not_the_overshoot(self):
        d5 = self.report["drills"]["D5"]
        self.assertEqual(d5["dispatches_performed"], d5["cap"])

    def test_worker_is_quarantined_and_escalated(self):
        d5 = self.report["drills"]["D5"]
        self.assertTrue(d5["quarantine_recorded"])
        self.assertTrue(d5["escalations"])
        self.assertEqual(d5["escalations"][0]["action_taken"], "quarantine_worker")

    def test_system_enters_safe_mode(self):
        d5 = self.report["drills"]["D5"]
        self.assertEqual(d5["system_mode"], "SAFE_MODE")
        self.assertTrue(d5["active_safe_mode_events"])


class TestSafeModeRecoveryDrill(HarnessFixture):

    def test_recovery_refused_without_owner_override(self):
        refused = self.report["drills"]["D6"]["recovery_refused_without_override"]
        self.assertFalse(refused["recovered"])
        self.assertTrue(refused["owner_only_event_ids"])
        self.assertTrue(any("owner override" in r
                            for r in refused["refusal_reasons"]))

    def test_recovery_refused_when_the_probe_is_unhealthy(self):
        refused = self.report["drills"]["D6"]["recovery_refused_when_unhealthy"]
        self.assertFalse(refused["recovered"])
        self.assertTrue(any("not healthy" in r for r in refused["refusal_reasons"]))

    def test_owner_override_is_audited_in_both_trails(self):
        d6 = self.report["drills"]["D6"]
        self.assertEqual(d6["owner_override"]["trigger_type"], "owner_override")
        rows = d6["owner_override_audit_rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision_actor"], "owner")
        self.assertEqual(rows[0]["gate_result"], "OWNER_APPROVAL_REQUIRED")
        self.assertIn("Mukund", rows[0]["concise_rationale"])

    def test_recovery_succeeds_after_override_and_returns_to_normal(self):
        d6 = self.report["drills"]["D6"]
        self.assertTrue(d6["recovery"]["recovered"])
        self.assertEqual(d6["final_mode"], "NORMAL")
        self.assertEqual(d6["active_events_after_recovery"], [])

    def test_owner_only_triggers_are_not_auto_resolved(self):
        d6 = self.report["drills"]["D6"]
        owner_only = [r for r in d6["resolved_event_rows"]
                      if r["trigger_type"] in OWNER_ONLY_TRIGGERS]
        self.assertTrue(owner_only)
        for row in owner_only:
            self.assertEqual(row["auto_resolved"], 0)
        auto = [r for r in d6["resolved_event_rows"]
                if r["trigger_type"] not in OWNER_ONLY_TRIGGERS
                and r["trigger_type"] != "owner_override"]
        for row in auto:
            self.assertEqual(row["auto_resolved"], 1)

    def test_provider_health_verification_is_not_claimed(self):
        d6 = self.report["drills"]["D6"]
        self.assertFalse(d6["provider_health_verified"])
        self.assertIn("owner-gated", d6["provider_health_note"])


class TestEvidenceWriter(HarnessFixture):

    def test_writes_evidence_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            out = write_evidence(self.report, Path(td))
            data = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(data["checks_passed"], data["checks_total"])
            md = (out / "evidence.md").read_text(encoding="utf-8")
            self.assertIn("E4/E5 real-path drill evidence", md)
            self.assertIn("| Check | Result |", md)


class TestSafeModeRecoveryUnit(unittest.TestCase):
    """Direct unit coverage of the E5 recovery/override additions."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.con = init_db(self.tmp.name)

    def tearDown(self):
        self.con.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    @staticmethod
    def _healthy():
        return {"healthy": True, "source": "unit_probe", "detail": "ok"}

    @staticmethod
    def _unhealthy():
        return {"healthy": False, "source": "unit_probe", "detail": "down"}

    def test_recovery_on_auto_resolvable_trigger_needs_no_override(self):
        manager = SafeModeManager(self.con)
        manager.enter_degraded("provider rate limit")
        manager.record_safe_mode_event("rate_limit", "low", "429 from provider")
        recovery = SafeModeRecovery(manager, self.con)
        result = recovery.attempt_recovery(self._healthy)
        self.assertTrue(result["recovered"])
        self.assertEqual(result["mode"], "NORMAL")
        self.assertEqual(manager.get_active_events(), [])
        self.assertEqual(result["resolved_events"][0]["auto_resolved"], True)

    def test_owner_only_trigger_blocks_recovery_until_overridden(self):
        manager = SafeModeManager(self.con)
        manager.enter_safe_mode("no equivalent worker")
        manager.record_safe_mode_event("no_equivalent_worker", "high", "none")
        recovery = SafeModeRecovery(manager, self.con)

        blocked = recovery.attempt_recovery(self._healthy)
        self.assertFalse(blocked["recovered"])
        self.assertEqual(blocked["mode"], "SAFE_MODE")

        record_owner_override(self.con, "Mukund", "supplied an equivalent worker",
                              "safe_mode_recovery")
        self.assertTrue(recovery.owner_override_present())
        ok = recovery.attempt_recovery(self._healthy)
        self.assertTrue(ok["recovered"])
        self.assertEqual(manager.mode.value, "NORMAL")
        owner_only = [e for e in ok["resolved_events"]
                      if e["trigger_type"] == "no_equivalent_worker"]
        self.assertEqual(owner_only[0]["auto_resolved"], False)

    def test_unhealthy_probe_blocks_recovery_even_with_override(self):
        manager = SafeModeManager(self.con)
        manager.enter_safe_mode("no equivalent worker")
        manager.record_safe_mode_event("no_equivalent_worker", "high", "none")
        record_owner_override(self.con, "Mukund", "reason", "safe_mode_recovery")
        recovery = SafeModeRecovery(manager, self.con)
        blocked = recovery.attempt_recovery(self._unhealthy)
        self.assertFalse(blocked["recovered"])
        self.assertTrue(blocked["gate"]["refusal_reasons"])

    def test_owner_override_writes_both_audit_trails(self):
        record = record_owner_override(self.con, "Mukund", "drill reason",
                                       "safe_mode_recovery")
        event = self.con.execute(
            "SELECT trigger_type, description FROM safe_mode_event WHERE event_id=?",
            (record["event_id"],)).fetchone()
        self.assertEqual(event[0], "owner_override")
        self.assertIn("Mukund", event[1])
        rationale = self.con.execute(
            """SELECT decision_type, decision_actor, gate_result
               FROM decision_rationale_event WHERE rationale_id=?""",
            (record["rationale_id"],)).fetchone()
        self.assertEqual(rationale[0], "escalation")
        self.assertEqual(rationale[1], "owner")
        self.assertEqual(rationale[2], "OWNER_APPROVAL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
