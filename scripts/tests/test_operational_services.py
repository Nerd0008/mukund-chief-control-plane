#!/usr/bin/env python3
"""Deterministic, isolated tests for scripts/operational_services.py.

Every test uses disposable roots and injected inputs: no live queue, no live
database, no scheduled task, no network call is touched. This is what makes the
suite safe to run under the evidence runner alongside the live system.
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


class TempRoot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ops-services-test-")
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make_db(self, name="t.db", rows=3):
        p = self.root / name
        con = sqlite3.connect(str(p))
        con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO t (v) VALUES (?)", [(f"r{i}",) for i in range(rows)])
        con.commit()
        con.close()
        return p


class TestDatabaseStatus(TempRoot):
    def test_missing_db_is_fail_not_pass(self):
        import operational_services as ops
        recs = ops.db_status([("missing", self.root / "nope.db")])
        self.assertEqual(recs[0]["status"], "FAIL")
        self.assertEqual(recs[0]["reason"], "missing")

    def test_healthy_db_passes_integrity(self):
        import operational_services as ops
        db = self.make_db()
        recs = ops.db_status([("good", db)])
        self.assertEqual(recs[0]["status"], "PASS")
        self.assertEqual(recs[0]["integrity_check"], "ok")
        self.assertEqual(recs[0]["table_count"], 1)


class TestQueueSummary(TempRoot):
    def test_counts_and_blocker_category(self):
        import operational_services as ops
        q = self.root / "remote-queue"
        (q / "blocked").mkdir(parents=True)
        (q / "pending").mkdir(parents=True)
        (q / "running").mkdir(parents=True)
        (q / "completed").mkdir(parents=True)
        (q / "pending" / "agent-a.json").write_text(json.dumps(
            {"task_id": "agent-a", "priority": "high"}), encoding="utf-8")
        (q / "running" / "agent-b.json").write_text(json.dumps(
            {"task_id": "agent-b", "priority": "critical"}), encoding="utf-8")
        (q / "blocked" / "agent-c.json").write_text(json.dumps(
            {"task_id": "agent-c", "blocker": {"category": "credentials"}}), encoding="utf-8")
        s = ops.queue_summary(q)
        self.assertEqual(s["pending"]["count"], 1)
        self.assertEqual(s["running"]["count"], 1)
        self.assertEqual(s["blocked"]["count"], 1)
        self.assertEqual(s["blocked"]["tasks"][0]["blocker_category"], "credentials")
        self.assertFalse(s["kill_switch"])

    def test_invalid_envelope_is_recorded_not_hidden(self):
        import operational_services as ops
        q = self.root / "remote-queue"
        (q / "pending").mkdir(parents=True)
        (q / "pending" / "bad.json").write_text("{not json", encoding="utf-8")
        s = ops.queue_summary(q)
        self.assertTrue(s["pending"]["tasks"][0].get("invalid"))


class TestTaskParsingAndPersistence(unittest.TestCase):
    XML = (
        "<Task><Settings><Enabled>true</Enabled>"
        "<StartWhenAvailable>true</StartWhenAvailable>"
        "<DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>"
        "</Settings><Triggers><LogonTrigger></LogonTrigger></Triggers>"
        "<Principals><LogonType>InteractiveToken</LogonType></Principals></Task>"
    )

    def test_parse_xml(self):
        import operational_services as ops
        d = ops._parse_task_xml(self.XML)
        self.assertEqual(d["triggers"], ["logon"])
        self.assertTrue(d["start_when_available"])
        self.assertTrue(d["disallow_on_batteries"])
        self.assertEqual(d["logon_type"], "InteractiveToken")

    def test_analyse_persistence_verdicts_and_checklist(self):
        import operational_services as ops
        tasks = {
            "Hermes_Gateway": {"exists": True, "state": "Enabled", "last_result": "0",
                               "definition": {"triggers": ["logon"], "logon_type": "InteractiveToken",
                                              "start_when_available": True, "restart_on_failure": True,
                                              "disallow_on_batteries": False}},
            "HermesRemoteQueuePoller": {"exists": True, "state": "Enabled",
                                        "definition": {"triggers": ["time"], "logon_type": "InteractiveToken",
                                                       "start_when_available": False,
                                                       "restart_on_failure": False,
                                                       "disallow_on_batteries": True}},
        }
        a = ops.analyse_persistence(tasks)
        self.assertEqual(a["verdicts"]["Hermes_Gateway"]["survives_boot"], "yes")
        self.assertEqual(a["verdicts"]["HermesRemoteQueuePoller"]["survives_boot"], "no")
        self.assertIn("HermesRemoteQueuePoller", a["unverified_after_reboot"])
        actions = {c["action"] for c in a["owner_checklist"]}
        self.assertIn("add_logon_trigger", actions)
        self.assertIn("battery_gating", actions)

    def test_missing_task_is_unknown_never_healthy(self):
        import operational_services as ops
        a = ops.analyse_persistence({"HermesRemoteQueuePoller": {"exists": False}})
        v = a["verdicts"]["HermesRemoteQueuePoller"]
        self.assertEqual(v["survives_boot"], "unknown")


class TestOperationalBackup(TempRoot):
    def test_backup_round_trip_and_integrity(self):
        import operational_services as ops
        db = self.make_db("state.db")
        chain = self.root / "chain-head.json"
        chain.write_text(json.dumps({"seq": 4}), encoding="utf-8")
        snap_root = self.root / "snapshots"
        report = ops.run_operational_backup(
            snapshot_root=snap_root,
            db_paths=[("state", db)],
            json_artifacts=[("chain", chain)],
            keep=7,
        )
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["live_state_modified"])
        snap = Path(report["snapshot_dir"])
        self.assertTrue((snap / "state.db").exists())
        self.assertTrue((snap / "chain.json").exists())
        self.assertEqual(report["artifacts"][0]["snapshot"]["integrity_check"], "ok")

    def test_missing_source_fails(self):
        import operational_services as ops
        report = ops.run_operational_backup(
            snapshot_root=self.root / "snapshots",
            db_paths=[("gone", self.root / "gone.db")],
            json_artifacts=[],
            keep=7,
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["failure_labels"], ["gone"])

    def test_retention_prunes_oldest_only_in_scope(self):
        import operational_services as ops
        snap_root = self.root / "snapshots"
        for name in ("snapshot-20260101T000000Z", "snapshot-20260102T000000Z",
                     "snapshot-20260103T000000Z"):
            (snap_root / name).mkdir(parents=True)
        outside = self.root / "unrelated"
        outside.mkdir()
        removed = ops.prune_snapshots(snap_root, keep=2)
        self.assertEqual(removed, ["snapshot-20260101T000000Z"])
        self.assertTrue((snap_root / "snapshot-20260102T000000Z").exists())
        self.assertTrue((snap_root / "snapshot-20260103T000000Z").exists())
        self.assertTrue(outside.exists(), "out-of-scope directory must never be touched")

    def test_dry_run_writes_nothing(self):
        import operational_services as ops
        db = self.make_db()
        snap_root = self.root / "snapshots"
        report = ops.run_operational_backup(snapshot_root=snap_root,
                                            db_paths=[("state", db)],
                                            json_artifacts=[], dry_run=True)
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(snap_root.exists())


class TestLogRotation(TempRoot):
    def test_plan_does_not_touch_log(self):
        import operational_services as ops
        log = self.root / "big.log"
        log.write_text("x" * 100, encoding="utf-8")
        res = ops.rotate_logs([log], max_bytes=10, apply=False)
        self.assertEqual(res[0]["action"], "would_rotate")
        self.assertEqual(log.stat().st_size, 100)

    def test_apply_archives_and_truncates_with_retention(self):
        import operational_services as ops
        log = self.root / "big.log"
        log.write_text("y" * 100, encoding="utf-8")
        res = ops.rotate_logs([log], max_bytes=10, keep=5, apply=True)
        self.assertEqual(res[0]["action"], "rotated")
        self.assertTrue(Path(res[0]["archive"]).exists())
        self.assertEqual(log.stat().st_size, 0)

    def test_small_log_not_rotated(self):
        import operational_services as ops
        log = self.root / "small.log"
        log.write_text("z", encoding="utf-8")
        res = ops.rotate_logs([log], max_bytes=10, apply=False)
        self.assertEqual(res[0]["action"], "no_rotation_needed")


class TestOwnerActionsAndBriefs(TempRoot):
    def test_parse_owner_actions(self):
        import operational_services as ops
        md = self.root / "actions.md"
        md.write_text(
            "# Overnight Owner-Action TODO\n\n"
            "### 1. Configure all remaining provider credentials\n"
            "**Status:** PENDING — OWNER PLANS TO DO THIS\n\n"
            "some prose\n\n"
            "### 2. Complete E3 Stage 2\n"
            "**Status:** DEFERRED UNTIL AFTER KEY CONFIGURATION\n"
            "owner will configure keys first\n\n"
            "## Next section\n"
            "- a bullet that must not be swallowed\n",
            encoding="utf-8")
        items = ops.parse_owner_actions(md)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["number"], 1)
        self.assertTrue(items[0]["status"].startswith("PENDING"))
        self.assertEqual(items[1]["number"], 2)
        self.assertIn("owner will configure keys first", items[1]["status"])
        self.assertNotIn("Next section", items[1]["status"])

    def test_snapshot_is_deterministic_and_never_coerces_unknown(self):
        import operational_services as ops
        db = self.make_db("ok.db")
        brief_dir = self.root / "runtime" / "career-ops" / "daily-brief"
        brief_dir.mkdir(parents=True)
        (brief_dir / "latest.json").write_text("{}", encoding="utf-8")
        r1 = ops.build_health_snapshot(
            repo_root=self.root,
            db_paths=[("ok", db), ("gone", self.root / "gone.db")],
            queue_root=self.root / "remote-queue",
            log_paths=[self.root / "none.log"],
            check_tasks=False,
            task_runner=lambda *a, **k: None,
        )
        # A missing database must fail the snapshot, not be reported healthy.
        self.assertEqual(r1["fail_count"], 1)
        self.assertEqual(r1["verdict"], "FAIL")
        keys = sorted(r1.keys())
        self.assertEqual(keys, sorted(ops.build_health_snapshot(
            repo_root=self.root,
            db_paths=[("ok", db), ("gone", self.root / "gone.db")],
            queue_root=self.root / "remote-queue",
            log_paths=[self.root / "none.log"],
            check_tasks=False,
        ).keys()))
        self.assertIn("escalations", r1)
        self.assertTrue(any(e["category"] == "integrity" for e in r1["escalations"]))

    def test_render_markdown_functions(self):
        import operational_services as ops
        snapshot = {
            "run_started_utc": "2026-09-24T00:00:00+00:00",
            "run_finished_utc": "2026-09-24T00:00:01+00:00",
            "code_sha": "deadbeef", "verdict": "PASS", "fail_count": 0,
            "attention_count": 0, "unknown_count": 0, "live_state_modified": False,
            "checks": [{"check": "db.ok", "status": "PASS", "detail": "ok"}],
            "queue": {s: {"count": 0, "tasks": []} for s in
                      ("pending", "running", "completed", "blocked")},
            "escalations": [],
        }
        self.assertIn("Operational health snapshot", ops.render_health_markdown(snapshot))


if __name__ == "__main__":
    unittest.main(verbosity=2)
