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


class TestLogRotationPolicyReport(TempRoot):
    """The declared policy surface: every live log path, bounded, no stray paths."""

    def _patch_targets(self, ops, paths):
        self._saved = ops.LOG_TARGETS
        ops.LOG_TARGETS = list(paths)
        self.addCleanup(lambda: setattr(ops, "LOG_TARGETS", self._saved))

    def test_every_policy_target_is_declared_and_read_only_plan_changes_nothing(self):
        import operational_services as ops
        big = self.root / "big.log"
        small = self.root / "small.log"
        big.write_text("x" * 100, encoding="utf-8")
        small.write_text("y", encoding="utf-8")
        self._patch_targets(ops, [big, small])
        before = {p: p.stat().st_size for p in (big, small)}
        report = ops.build_log_rotation_report(apply=False, keep=3, max_bytes=10)
        self.assertEqual(report["mode"], "dry-run")
        self.assertFalse(report["live_state_modified"])
        self.assertEqual(report["would_rotate"], [str(big)])
        self.assertEqual(report["rotated"], [])
        self.assertEqual({p: p.stat().st_size for p in (big, small)}, before)
        self.assertEqual(sorted(report["log_paths_covered"]), sorted([str(big), str(small)]))
        self.assertEqual(report["network_calls_spent"], 0)

    def test_apply_rotates_and_prunes_only_inside_the_policy_set(self):
        import operational_services as ops
        big = self.root / "big.log"
        big.write_text("x" * 100, encoding="utf-8")
        outside = self.root / "do-not-touch.log"
        outside.write_text("z" * 100, encoding="utf-8")
        self._patch_targets(ops, [big])
        # Pre-existing stale archives beyond the keep bound, plus one stranger.
        for i in range(4):
            (self.root / f"big.log.20200101T00000{i}Z.1").write_text("old", encoding="utf-8")
        report = ops.build_log_rotation_report(apply=True, keep=2, max_bytes=10)
        self.assertEqual(report["rotated"], [str(big)])
        self.assertTrue(report["live_state_modified"])
        self.assertEqual(big.stat().st_size, 0)
        remaining = sorted(p.name for p in self.root.glob("big.log.*.1"))
        self.assertEqual(len(remaining), 2, remaining)
        self.assertEqual(outside.stat().st_size, 100)  # outside the policy set
        self.assertEqual(report["failure_labels"], [])

    def test_missing_log_is_recorded_not_invented(self):
        import operational_services as ops
        missing = self.root / "absent.log"
        self._patch_targets(ops, [missing])
        report = ops.build_log_rotation_report(apply=False, max_bytes=10)
        self.assertEqual(report["results"][0]["action"], "skip_missing")
        self.assertFalse(report["results"][0]["exists"])

    def test_live_policy_targets_cover_every_declared_hermes_chief_log(self):
        import operational_services as ops
        names = {Path(p).name for p in ops.LOG_TARGETS}
        for expected in ("agent.log", "errors.log", "gateway.log", "gateway-error.log",
                         "gateway-stdio.log", "gateway-exit-diag.log", "update.log",
                         "gateway-starts.log", "queue.log", "operational-services.log"):
            self.assertIn(expected, names)
        # Hermes-managed JSON record stores are recorded out of scope, never pruned.
        scope = {r["path"] for r in ops.LOG_TARGETS_OUT_OF_SCOPE}
        self.assertTrue(any("process-results" in s for s in scope))
        self.assertTrue(all(s not in {str(p) for p in ops.LOG_TARGETS} for s in scope))


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


class TestContentStopPressureSurface(TempRoot):
    """The recorded content-side stop pressure view on the operator surfaces.

    Offline and read-only: every store is a disposable temp database and every
    "provider series" is a hand-written recorded artifact. No provider call, no
    live store, no automatic action — the view is an observation only.
    """

    CLEAN_LEDGER = {"attempts": [{"attempt": i + 1} for i in range(5)],
                    "content_stop_stops": 0, "content_stop_finish_reasons": []}
    LEGACY_LEDGER = {"attempts": [{"attempt": 1, "outcome": "FAIL"}],
                     "rejections": 1, "repairs": 0}
    ZERO_ATTEMPT_LEDGER = {"attempts": [], "content_stop_stops": 0,
                           "content_stop_finish_reasons": []}

    def _store(self, name="orchestration.db", rows=()):
        """A disposable store holding exactly the columns the view reads."""
        p = self.root / name
        con = sqlite3.connect(str(p))
        con.execute(
            "CREATE TABLE performance_evidence (evidence_id TEXT PRIMARY KEY, "
            "worker_id TEXT, provider TEXT, model TEXT, "
            "deterministic_test_results TEXT, failure_attribution TEXT, "
            "retries INTEGER, timestamp TEXT, dag_node_id TEXT)")
        con.executemany(
            "INSERT INTO performance_evidence VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
        con.close()
        return p

    @staticmethod
    def _row(evidence_id, ledger, worker_id="fixture-worker", provider="fixture",
             model="fixture-model", timestamp="2026-09-24 01:44:32"):
        return (evidence_id, worker_id, provider, model, json.dumps(ledger),
                None, 0, timestamp, None)

    def _series(self, stops=2, total=9, label="fixture-series"):
        """A recorded provider series artifact (never produced by a provider here)."""
        d = self.root / "series" / label
        d.mkdir(parents=True, exist_ok=True)
        observations = [
            {"executed": True, "requested_model": "fixture-model",
             "finish_reason": "IMAGE_RECITATION" if i < stops else "STOP",
             "candidate_finish_reasons": []}
            for i in range(total)
        ]
        path = d / "observations.json"
        path.write_text(json.dumps({
            "worker_id": "fixture-worker", "label": label,
            "run_started_utc": "2026-09-24T01:44:32+00:00",
            "observations": observations}), encoding="utf-8")
        return path

    def _status(self, db, series=()):
        import operational_services as ops
        return ops.content_stop_pressure_status(
            db_paths=[("e3-orchestration", db)], series_paths=series)

    def _snapshot(self, db, series=()):
        import operational_services as ops
        return ops.build_health_snapshot(
            repo_root=self.root, db_paths=[("e3-orchestration", db)],
            queue_root=self.root / "remote-queue", log_paths=[],
            check_tasks=False, pressure_series=series)

    def test_clean_provider_raises_no_warning(self):
        import operational_services as ops
        db = self._store(rows=[self._row("ev-clean", self.CLEAN_LEDGER)])
        rec = self._status(db)
        group = rec["groups"][0]
        self.assertEqual(group["attempts_classified"], 5)
        self.assertEqual(group["sample_size"], 5)
        self.assertEqual(group["content_stops_observed"], 0)
        self.assertEqual(group["content_stop_rate"], 0.0)
        self.assertFalse(group["content_withheld_at_measurable_rate"])
        self.assertFalse(rec["detected"])
        self.assertEqual(rec["status"], ops.PRESSURE_STATUS_PASS)
        self.assertEqual(ops.pressure_escalations(rec), [])

        snap = self._snapshot(db)
        check = [c for c in snap["checks"] if c["check"] == ops.PRESSURE_CHECK][0]
        self.assertEqual(check["status"], "PASS")
        self.assertEqual([e for e in snap["escalations"]
                          if e["category"] == ops.PRESSURE_ESCALATION_CATEGORY], [])

    def test_pre_classification_store_reports_unknown_not_clear(self):
        """A row recorded before the content-stop classification carries no count."""
        import operational_services as ops
        db = self._store(rows=[self._row("ev-legacy", self.LEGACY_LEDGER)])
        rec = self._status(db)
        group = rec["groups"][0]
        self.assertEqual(group["attempts_observed"], 1)
        self.assertEqual(group["attempts_classified"], 0)
        self.assertEqual(group["attempts_unclassified"], 1)
        self.assertIsNone(group["content_stop_rate"])
        self.assertIsNone(group["content_withheld_at_measurable_rate"])
        self.assertEqual(group["status"], "unknown")
        self.assertEqual(rec["status"], ops.PRESSURE_STATUS_UNKNOWN)
        self.assertFalse(rec["detected"])
        self.assertIn("unknown, not clear", rec["detail"])
        self.assertEqual(ops.pressure_escalations(rec), [])
        # The operator surface reports UNKNOWN, never PASS/"clear".
        snap = self._snapshot(db)
        check = [c for c in snap["checks"] if c["check"] == ops.PRESSURE_CHECK][0]
        self.assertEqual(check["status"], "UNKNOWN")

    def test_zero_attempts_never_yield_a_fabricated_rate(self):
        import operational_services as ops
        db = self._store(rows=[self._row("ev-zero", self.ZERO_ATTEMPT_LEDGER)])
        rec = self._status(db)
        group = rec["groups"][0]
        self.assertEqual(group["attempts_observed"], 0)
        self.assertEqual(group["sample_size"], 0)
        self.assertIsNone(group["content_stop_rate"])
        self.assertIsNone(group["content_withheld_at_measurable_rate"])
        self.assertEqual(rec["status"], ops.PRESSURE_STATUS_UNKNOWN)
        rendered = "\n".join(ops.render_pressure_lines(rec))
        self.assertIn("no rate is reported from zero attempts", rendered)
        self.assertIn("unknown", rendered)
        self.assertNotIn("stop rate 0", rendered)
        self.assertEqual(ops.pressure_escalations(rec), [])

    def test_a_crossing_recorded_rate_is_a_warning_grade_observation(self):
        import operational_services as ops
        series = self._series(stops=2, total=9)
        db = self._store()
        rec = self._status(db, series=[series])
        self.assertTrue(rec["detected"])
        self.assertEqual(rec["status"], ops.PRESSURE_STATUS_ATTENTION)
        flagged = [g for g in rec["groups"]
                   if g["content_withheld_at_measurable_rate"]]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["attempts_classified"], 9)
        self.assertEqual(flagged[0]["sample_size"], 9)
        self.assertEqual(flagged[0]["content_stops_observed"], 2)
        self.assertAlmostEqual(flagged[0]["content_stop_rate"], 2 / 9)
        self.assertEqual(flagged[0]["last_finish_reason"], "IMAGE_RECITATION")

        escalations = ops.pressure_escalations(rec)
        self.assertEqual(len(escalations), 1)
        item = escalations[0]
        self.assertEqual(item["severity"], "warning")
        self.assertEqual(item["category"], ops.PRESSURE_ESCALATION_CATEGORY)
        self.assertIn("0.222", item["item"])
        self.assertIn("sample size 9", item["item"])
        self.assertIn("IMAGE_RECITATION", item["item"])
        self.assertIn("no automatic worker swap", item["item"])
        self.assertIn("explicit E4/owner decision", item["item"])

    def test_health_snapshot_escalation_list_carries_the_crossing_group(self):
        import operational_services as ops
        series = self._series(stops=2, total=9)
        db = self._store()
        snap = self._snapshot(db, series=[series])
        check = [c for c in snap["checks"] if c["check"] == ops.PRESSURE_CHECK][0]
        self.assertEqual(check["status"], "ATTENTION")
        self.assertEqual(snap["fail_count"], 0)
        pressure_escalations_ = [e for e in snap["escalations"]
                                 if e["category"] == ops.PRESSURE_ESCALATION_CATEGORY]
        self.assertEqual(len(pressure_escalations_), 1)
        self.assertEqual(pressure_escalations_[0]["severity"], "warning")
        md = ops.render_health_markdown(snap)
        self.assertIn("Provider content-side stop pressure", md)
        self.assertIn("content withheld at a measurable rate: yes", md)
        self.assertIn("sample size 9", md)

    def test_morning_brief_carries_and_renders_the_pressure_view(self):
        import operational_services as ops
        series = self._series(stops=2, total=9)
        db = self._store()
        brief = ops.build_morning_brief(
            repo_root=self.root, db_paths=[("e3-orchestration", db)],
            queue_root=self.root / "remote-queue", log_paths=[],
            check_tasks=False, pressure_series=[series],
            owner_actions_file=self.root / "absent-actions.md")
        pressure = brief["resource_status"]["content_stop_pressure"]
        self.assertEqual(pressure["status"], "ATTENTION")
        self.assertTrue(pressure["detected"])
        self.assertIn("no automatic worker swap", pressure["decision"])
        self.assertEqual([e["category"] for e in brief["escalations"]
                          if e["category"] == ops.PRESSURE_ESCALATION_CATEGORY],
                         [ops.PRESSURE_ESCALATION_CATEGORY])
        md = ops.render_morning_markdown(brief)
        self.assertIn("content withheld at a measurable rate: yes", md)
        self.assertIn("IMAGE_RECITATION", md)

    def test_the_pressure_view_never_writes_the_store(self):
        import operational_services as ops
        db = self._store(rows=[self._row("ev-readonly", self.CLEAN_LEDGER)])
        before = ops.sha256_file(db)
        rec = self._status(db)
        self.assertEqual(ops.sha256_file(db), before)
        self.assertFalse((self.root / "orchestration.db-journal").exists())
        self.assertFalse((self.root / "orchestration.db-wal").exists())
        self.assertTrue(rec["observation_only"])
        self.assertEqual(rec["provider_calls_spent"], 0)
        self.assertEqual(rec["network_calls_spent"], 0)
        self.assertFalse(rec["live_state_modified"])
        self.assertIn("no automatic worker swap", rec["decision"])

    def test_an_absent_or_undeclared_store_reports_unknown(self):
        import operational_services as ops
        rec = ops.content_stop_pressure_status(
            db_paths=[("other", self.root / "t.db")], series_paths=())
        self.assertEqual(rec["status"], ops.PRESSURE_STATUS_UNKNOWN)
        self.assertIn("no orchestration store declared", rec["detail"])
        self.assertEqual(ops.pressure_escalations(rec), [])

        missing = self.root / "absent.db"
        rec2 = ops.content_stop_pressure_status(
            db_paths=[("e3-orchestration", missing)], series_paths=())
        self.assertEqual(rec2["status"], ops.PRESSURE_STATUS_UNKNOWN)
        self.assertIn("absent", rec2["detail"])

    def test_declared_recorded_series_is_consumed_by_default(self):
        """The default path consumes the declared recorded artifact (never re-run)."""
        import operational_services as ops
        series = self._series(stops=2, total=9)
        original = ops.RECORDED_PRESSURE_SERIES
        ops.RECORDED_PRESSURE_SERIES = [series]
        self.addCleanup(setattr, ops, "RECORDED_PRESSURE_SERIES", original)
        db = self._store()
        rec = ops.content_stop_pressure_status(
            db_paths=[("e3-orchestration", db)])
        self.assertEqual(rec["status"], ops.PRESSURE_STATUS_ATTENTION)
        self.assertEqual(rec["source_errors"], [])
        self.assertTrue(any(g["content_stops_observed"] == 2 for g in rec["groups"]))

    def test_unreadable_series_artifact_is_recorded_not_fabricated(self):
        import operational_services as ops
        db = self._store(rows=[self._row("ev-clean", self.CLEAN_LEDGER)])
        rec = self._status(db, series=[self.root / "gone" / "observations.json"])
        self.assertTrue(rec["source_errors"])
        self.assertIn("gone", rec["source_errors"][0])
        # The readable store row is still reported; nothing is invented for the
        # unreadable artifact.
        self.assertEqual(len(rec["groups"]), 1)
        self.assertEqual(rec["groups"][0]["sample_size"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
