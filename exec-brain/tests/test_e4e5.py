#!/usr/bin/env python3
"""Tests for E4 Resource Continuity and E5 Safe Mode."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Ensure we can import from exec-brain
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestration_db import init_db
from resource_monitor import ResourceMonitor, CheckpointManager, EquivalentFailover
from safe_mode import (
    SafeModeManager,
    FailureDrills,
    ConvergenceEnforcer,
    MalformedOutputHandler,
    SystemMode,
)


class TestOrchestrationDB(unittest.TestCase):
    """Test E4/E5 schema tables are created."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.con = init_db(self.tmp.name)

    def tearDown(self):
        self.con.close()
        os.unlink(self.tmp.name)

    def test_schema_version_2(self):
        """Schema version should be 2 after init."""
        row = self.con.execute("SELECT MAX(version) FROM schema_version").fetchone()
        self.assertEqual(row[0], 2)

    def test_e4_tables_exist(self):
        tables = [r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        self.assertIn("resource_checkpoint", tables)
        self.assertIn("resource_snapshot", tables)

    def test_e5_tables_exist(self):
        tables = [r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        self.assertIn("safe_mode_event", tables)
        self.assertIn("failure_drill_log", tables)
        self.assertIn("convergence_event", tables)

    def test_e4_indexes_exist(self):
        indexes = [r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()]
        self.assertIn("idx_checkpoint_task", indexes)
        self.assertIn("idx_snapshot_provider", indexes)

    def test_e5_indexes_exist(self):
        indexes = [r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()]
        self.assertIn("idx_safemode_severity", indexes)
        self.assertIn("idx_convergence_worker", indexes)


class TestResourceMonitor(unittest.TestCase):
    """Test E4 resource monitoring."""

    def test_init_with_none_gov(self):
        monitor = ResourceMonitor(orchestration_con=None, governor_con=None)
        snapshot = monitor.get_resource_snapshot()
        self.assertIn("timestamp", snapshot)
        self.assertEqual(snapshot["providers"], {})
        self.assertEqual(snapshot["total_requests_today"], 0)

    def test_runway_none_gov(self):
        monitor = ResourceMonitor(orchestration_con=None, governor_con=None)
        runway = monitor.calculate_runway("test", "model")
        self.assertEqual(runway["status"], "unknown")

    def test_predict_exhaustion_none_gov(self):
        monitor = ResourceMonitor(orchestration_con=None, governor_con=None)
        predictions = monitor.predict_exhaustion()
        self.assertEqual(predictions, [])


class TestCheckpointManager(unittest.TestCase):
    """Test E4 checkpoint manager."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.con = init_db(self.tmp.name)

    def tearDown(self):
        self.con.close()
        os.unlink(self.tmp.name)

    def test_save_checkpoint(self):
        mgr = CheckpointManager(self.con)
        ckpt_id = mgr.save_checkpoint("task-1", "node-1", {"step": 5})
        self.assertTrue(ckpt_id.startswith("ckpt-"))

    def test_get_latest_checkpoint(self):
        mgr = CheckpointManager(self.con)
        mgr.save_checkpoint("task-1", "node-1", {"step": 1})
        mgr.save_checkpoint("task-1", "node-1", {"step": 2})
        result = mgr.get_latest_checkpoint("task-1", "node-1")
        self.assertIsNotNone(result)
        self.assertEqual(result["state"]["step"], 2)

    def test_list_checkpoints(self):
        mgr = CheckpointManager(self.con)
        mgr.save_checkpoint("task-1", "node-1", {"step": 1})
        mgr.save_checkpoint("task-1", "node-2", {"step": 2})
        ckpts = mgr.list_checkpoints("task-1")
        self.assertEqual(len(ckpts), 2)


class TestSafeModeManager(unittest.TestCase):
    """Test E5 safe mode manager."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.con = init_db(self.tmp.name)

    def tearDown(self):
        self.con.close()
        os.unlink(self.tmp.name)

    def test_enter_degraded(self):
        mgr = SafeModeManager(self.con)
        result = mgr.enter_degraded("Test degraded")
        self.assertEqual(result["mode"], "DEGRADED")
        self.assertIn("Test degraded", result["reason"])

    def test_enter_safe_mode(self):
        mgr = SafeModeManager(self.con)
        result = mgr.enter_safe_mode("Test safe mode")
        self.assertEqual(result["mode"], "SAFE_MODE")

    def test_enter_halt(self):
        mgr = SafeModeManager(self.con)
        result = mgr.enter_halt("Test halt")
        self.assertEqual(result["mode"], "HALT")

    def test_resume_normal(self):
        mgr = SafeModeManager(self.con)
        mgr.enter_degraded("test")
        result = mgr.resume_normal()
        self.assertEqual(result["mode"], "NORMAL")

    def test_record_failure(self):
        mgr = SafeModeManager(self.con)
        count = mgr.record_failure("worker-1", "text-gen")
        self.assertEqual(count, 1)
        count = mgr.record_failure("worker-1", "text-gen")
        self.assertEqual(count, 2)

    def test_reset_failure_count(self):
        mgr = SafeModeManager(self.con)
        mgr.record_failure("worker-1", "text-gen")
        mgr.reset_failure_count("worker-1", "text-gen")
        self.assertEqual(mgr.get_failure_count("worker-1", "text-gen"), 0)

    def test_record_safe_mode_event_db(self):
        mgr = SafeModeManager(self.con)
        event_id = mgr.record_safe_mode_event(
            "repeated_failure", "degraded", "Test event", ["worker-1"]
        )
        self.assertIsNotNone(event_id)
        events = mgr.get_active_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["trigger_type"], "repeated_failure")

    def test_resolve_event_db(self):
        mgr = SafeModeManager(self.con)
        event_id = mgr.record_safe_mode_event(
            "repeated_failure", "degraded", "Test event"
        )
        mgr.resolve_event(event_id, auto=True)
        events = mgr.get_active_events()
        self.assertEqual(len(events), 0)


class TestFailureDrills(unittest.TestCase):
    """Test E5 failure drills."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.con = init_db(self.tmp.name)

    def tearDown(self):
        self.con.close()
        os.unlink(self.tmp.name)

    def test_list_drills(self):
        drills = FailureDrills()
        drill_list = drills.list_drills()
        self.assertIn("provider_outage", drill_list)
        self.assertIn("repeated_worker_failure", drill_list)
        self.assertIn("rate_limit", drill_list)
        self.assertIn("malformed_output", drill_list)
        self.assertIn("no_equivalent_worker", drill_list)

    def test_run_drill(self):
        drills = FailureDrills()
        result = drills.run_drill("provider_outage")
        self.assertEqual(result["result"], "simulated_success")
        self.assertEqual(result["severity"], "high")

    def test_run_drill_with_db(self):
        drills = FailureDrills(self.con)
        result = drills.run_drill("provider_outage")
        self.assertIn("drill_id", result)

    def test_unknown_drill(self):
        drills = FailureDrills()
        result = drills.run_drill("nonexistent")
        self.assertIn("error", result)


class TestConvergenceEnforcer(unittest.TestCase):
    """Test E5 convergence enforcer."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.con = init_db(self.tmp.name)

    def tearDown(self):
        self.con.close()
        os.unlink(self.tmp.name)

    def test_can_retry(self):
        enforcer = ConvergenceEnforcer()
        self.assertTrue(enforcer.can_retry("task-1"))
        enforcer.record_attempt("task-1")
        enforcer.record_attempt("task-1")
        self.assertTrue(enforcer.can_retry("task-1"))
        enforcer.record_attempt("task-1")
        self.assertFalse(enforcer.can_retry("task-1"))

    def test_should_stop(self):
        enforcer = ConvergenceEnforcer(max_retries=2)
        enforcer.record_attempt("task-1")
        enforcer.record_attempt("task-1")
        should_stop, reason = enforcer.should_stop("task-1")
        self.assertTrue(should_stop)
        self.assertIn("Max retries", reason)

    def test_can_replan(self):
        enforcer = ConvergenceEnforcer()
        self.assertTrue(enforcer.can_replan("plan-1"))
        enforcer.record_attempt("replan:plan-1")
        enforcer.record_attempt("replan:plan-1")
        self.assertFalse(enforcer.can_replan("plan-1"))

    def test_record_convergence_event_db(self):
        enforcer = ConvergenceEnforcer(self.con, max_retries=3)
        result = enforcer.record_convergence_event("worker-1", "text-gen", 3)
        self.assertEqual(result["action_taken"], "quarantine_worker")
        self.assertTrue(result["escalated"])

        escalations = enforcer.get_escalations()
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0]["worker_id"], "worker-1")

    def test_record_convergence_event_warn(self):
        enforcer = ConvergenceEnforcer(self.con, max_retries=3)
        result = enforcer.record_convergence_event("worker-1", "text-gen", 2)
        self.assertEqual(result["action_taken"], "warn_and_reduce_scope")
        self.assertFalse(result["escalated"])

    def test_record_convergence_event_log(self):
        enforcer = ConvergenceEnforcer(self.con, max_retries=3)
        result = enforcer.record_convergence_event("worker-1", "text-gen", 1)
        self.assertEqual(result["action_taken"], "log_and_retry")
        self.assertFalse(result["escalated"])


class TestMalformedOutputHandler(unittest.TestCase):
    """Test E5 malformed output handling."""

    def test_validate_output_none(self):
        result = MalformedOutputHandler.validate_output(None)
        self.assertFalse(result["valid"])
        self.assertIn("Output is None", result["errors"])

    def test_validate_output_empty(self):
        result = MalformedOutputHandler.validate_output("")
        self.assertFalse(result["valid"])
        self.assertIn("Output is empty", result["errors"])

    def test_validate_output_valid_string(self):
        result = MalformedOutputHandler.validate_output("Hello world")
        self.assertTrue(result["valid"])

    def test_validate_output_dict_with_schema(self):
        output = {"status": "ok", "data": "test"}
        schema = {"required": ["status", "data"]}
        result = MalformedOutputHandler.validate_output(output, schema)
        self.assertTrue(result["valid"])

    def test_validate_output_dict_missing_field(self):
        output = {"status": "ok"}
        schema = {"required": ["status", "data"]}
        result = MalformedOutputHandler.validate_output(output, schema)
        self.assertFalse(result["valid"])

    def test_sanitize_output(self):
        dirty = "Hello\x00World\x01Test"
        clean = MalformedOutputHandler.sanitize_output(dirty)
        self.assertNotIn("\x00", clean)
        self.assertNotIn("\x01", clean)

    def test_handle_malformed_recoverable(self):
        result = MalformedOutputHandler.handle_malformed(
            "worker-1", "task-1", None, "Output is None"
        )
        self.assertTrue(result["is_recoverable"])
        self.assertEqual(result["action"], "retry_with_correction")

    def test_handle_malformed_unrecoverable(self):
        result = MalformedOutputHandler.handle_malformed(
            "worker-1", "task-1", None, "security_violation detected"
        )
        self.assertFalse(result["is_recoverable"])
        self.assertEqual(result["action"], "escalate_to_owner")


if __name__ == "__main__":
    unittest.main()
