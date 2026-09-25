"""Executive Brain E1 test suite — rev 3 test matrix (28 tests).

Runs against a THROWAWAY database via EB_HOME env var. Never touches the
live exec_brain.db unless EB_TEST_LIVE=1. Uses unittest; no external deps.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EB = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "exec-brain" / "eb.py"
TEST_HOME = Path(tempfile.mkdtemp(prefix="eb-test-"))


def run(*args, home=None):
    env = dict(os.environ)
    env["EB_HOME"] = str(home or TEST_HOME)
    r = subprocess.run([sys.executable, str(EB), *args], capture_output=True,
                       text=True, env=env, timeout=60)
    return r


class EBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = run("init")
        assert r.returncode == 0, r.stderr

    def a(self, *args, expect=0):
        r = run(*args)
        self.assertEqual(r.returncode, expect, f"args={args}\nout={r.stdout}\nerr={r.stderr}")
        return r

    def new_task(self, **kw):
        args = ["classify", "--request-text", kw.get("text", "test request"),
                "--task-type", kw.get("tt", "code"), "--roles", kw.get("roles", "builder"),
                "--reasoning-depth", str(kw.get("rd", 1)),
                "--verification-level", kw.get("v", "V1"), "--risk-class", kw.get("r", "R1"),
                "--privacy-class", kw.get("p", "P1"), "--egress-policy", kw.get("e", "EXTERNAL_ALLOWED"),
                "--classification-confidence", kw.get("c", "high")]
        for k, flag in (("source_system", "--source-system"), ("source_event_id", "--source-event-id"),
                        ("supersedes", "--supersedes"), ("reason", "--reason")):
            if kw.get(k):
                args += [flag, kw[k]]
        r = self.a(*args)
        return r.stdout.strip()

    def new_floor(self, task_id, **kw):
        args = ["freeze", "--task-id", task_id, "--roles", kw.get("roles", "builder"),
                "--min-reasoning-depth", str(kw.get("rd", 1)),
                "--min-verification", kw.get("v", "V1")]
        if kw.get("subtask"):
            args += ["--subtask-id", kw["subtask"]]
        if kw.get("egress"):
            args += ["--egress-constraints", kw["egress"]]
        if kw.get("risk"):
            args += ["--risk-constraints", kw["risk"]]
        if kw.get("strategy"):
            args += ["--strategy-constraints", kw["strategy"]]
        return self.a(*args).stdout.strip()

    def route(self, floor_id, **kw):
        args = ["route", "--floor-id", floor_id, "--strategy", kw.get("s", "3"),
                "--reasoning", str(kw.get("rd", 1)), "--verification", kw.get("v", "V1"),
                "--scope", kw.get("scope", "local"), "--egress", kw.get("egress", "EXTERNAL_ALLOWED"),
                "--roles", kw.get("roles", "builder")]
        for k, flag in (("cls", "--chosen-class"), ("worker", "--chosen-worker"),
                        ("override", "--override-id"), ("approval", "--risk-approval")):
            if kw.get(k):
                args += [flag, kw[k]]
        return run(*args)


class TestMatrix(EBTest):
    # T1
    def test_t1_classify_valid(self):
        tid = self.new_task()
        self.assertTrue(tid.startswith("eb-"))

    # T2
    def test_t2_classify_invalid_enum(self):
        self.a("classify", "--request-text", "x", "--task-type", "bogus",
               "--roles", "builder", "--reasoning-depth", "1",
               "--verification-level", "V1", "--risk-class", "R1",
               "--privacy-class", "P1", "--egress-policy", "EXTERNAL_ALLOWED",
               "--classification-confidence", "high", expect=1)

    # T3
    def test_t3_decompose_before_classify(self):
        self.a("decompose", "--task-id", "eb-nonexistent", "--title", "x",
               "--order-index", "0", expect=1)

    # T4
    def test_t4_freeze_extends_chain(self):
        tid = self.new_task()
        fid = self.new_floor(tid)
        self.assertTrue(fid.startswith("fl-"))

    # T5 duplicate task-level freeze (subtask NULL)
    def test_t5_duplicate_task_freeze_refused(self):
        tid = self.new_task()
        self.new_floor(tid)
        self.a("freeze", "--task-id", tid, "--roles", "builder",
               "--min-reasoning-depth", "1", "--min-verification", "V1", expect=1)

    # T5a reclassification lineage
    def test_t5a_reclassification_new_lineage(self):
        t1 = self.new_task()
        f1 = self.new_floor(t1)
        t2 = self.new_task(supersedes=t1, reason="understanding changed")
        f2 = self.new_floor(t2)
        con = sqlite3.connect(str(TEST_HOME / "exec_brain.db"))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM task_record WHERE task_id=?", (t1,)).fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM quality_floor WHERE task_id IN (?,?)", (t1, t2)).fetchone()[0], 2)
        self.assertEqual(con.execute("SELECT supersedes_task_id FROM task_record WHERE task_id=?", (t2,)).fetchone()[0], t1)
        con.close()

    # T5b duplicate subtask freeze
    def test_t5b_duplicate_subtask_freeze_refused(self):
        tid = self.new_task()
        st = self.a("decompose", "--task-id", tid, "--title", "s1",
                    "--order-index", "0").stdout.strip()
        self.new_floor(tid, subtask=st)
        self.a("freeze", "--task-id", tid, "--subtask-id", st, "--roles", "builder",
               "--min-reasoning-depth", "1", "--min-verification", "V1", expect=1)

    # T6 route without freeze
    def test_t6_route_without_freeze(self):
        tid = self.new_task()
        r = self.route("fl-nonexistent")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FLOOR REQUIRED", r.stderr)

    # T7 route after freeze
    def test_t7_route_after_freeze(self):
        tid = self.new_task()
        fid = self.new_floor(tid)
        r = self.route(fid)
        self.assertEqual(r.returncode, 0)
        self.assertIn("gate=accept", r.stdout)

    # T8 sub-floor route without override
    def test_t8_subfloor_route_refused(self):
        tid = self.new_task()
        fid = self.new_floor(tid, rd=2)
        r = self.route(fid, rd=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("reasoning", r.stderr)

    # T9 override with empty warning
    def test_t9_override_empty_warning(self):
        tid = self.new_task()
        fid = self.new_floor(tid)
        self.a("override", "--floor-id", fid, "--strategy", "3", "--reasoning", "1",
               "--verification", "V1", "--scope", "local", "--egress", "EXTERNAL_ALLOWED",
               "--roles", "builder", "--route-description", "x", "--warning", " ",
               "--confirmation", "owner said ok", expect=1)

    # T10 matching override accepted
    def test_t10_override_exact_match(self):
        tid = self.new_task()
        fid = self.new_floor(tid, rd=2)
        ov = self.a("override", "--floor-id", fid, "--strategy", "3",
                    "--chosen-class", "nous", "--chosen-worker", "longcat",
                    "--reasoning", "1", "--verification", "V1", "--scope", "local",
                    "--egress", "EXTERNAL_ALLOWED", "--roles", "builder",
                    "--route-description", "cheap local run",
                    "--warning", "below floor", "--confirmation", "owner approved msg 123").stdout.strip()
        r = self.route(fid, rd=1, cls="nous", worker="longcat", override=ov)
        self.assertEqual(r.returncode, 0)
        self.assertIn("gate=accept", r.stdout)

    # T10a changed route does not reuse override
    def test_t10a_override_fingerprint_mismatch(self):
        tid = self.new_task()
        fid = self.new_floor(tid, rd=2)
        ov = self.a("override", "--floor-id", fid, "--strategy", "3",
                    "--chosen-class", "nous", "--chosen-worker", "longcat",
                    "--reasoning", "1", "--verification", "V1", "--scope", "local",
                    "--egress", "EXTERNAL_ALLOWED", "--roles", "builder",
                    "--route-description", "cheap local run",
                    "--warning", "below floor", "--confirmation", "owner ok").stdout.strip()
        r = self.route(fid, rd=1, cls="nous", worker="OTHER-MODEL", override=ov)
        self.assertEqual(r.returncode, 1)
        self.assertIn("fingerprint mismatch", r.stderr)

    # T10b same source_event_id retried -> no duplicate
    def test_t10b_idempotent_classify(self):
        a = self.new_task(source_system="discord", source_event_id="msg-999")
        b = self.new_task(source_system="discord", source_event_id="msg-999")
        self.assertTrue(b.startswith("existing:"), f"retry did not reuse: {b}")
        self.assertIn(a, b)
        con = sqlite3.connect(str(TEST_HOME / "exec_brain.db"))
        n = con.execute("SELECT COUNT(*) FROM task_record WHERE source_event_id='msg-999'").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)

    # T10c different source_event_id -> new task
    def test_t10c_different_source_new_task(self):
        a = self.new_task(source_system="discord", source_event_id="msg-A")
        b = self.new_task(source_system="discord", source_event_id="msg-B")
        self.assertNotEqual(a, b)

    # T11/T11a/T11b direct SQL tamper rejected by triggers
    def _tamper(self, sql):
        con = sqlite3.connect(str(TEST_HOME / "exec_brain.db"))
        try:
            con.execute(sql)
            con.commit()
            return False  # no abort = FAIL
        except sqlite3.DatabaseError:
            return True
        finally:
            con.close()

    def test_t11_update_floor_rejected(self):
        self.assertTrue(self._tamper("UPDATE quality_floor SET min_reasoning_depth=0"))

    def test_t11a_delete_floor_rejected(self):
        self.assertTrue(self._tamper("DELETE FROM quality_floor"))

    def test_t11b_all_tables_protected(self):
        # ensure every table has at least one row (row-level triggers do not
        # fire on empty tables)
        tid = self.new_task()
        st = self.a("decompose", "--task-id", tid, "--title", "s",
                    "--order-index", "0").stdout.strip()
        fid = self.new_floor(tid, subtask=st)
        self.route(fid)
        self.a("override", "--floor-id", fid, "--strategy", "3", "--reasoning", "1",
               "--verification", "V1", "--scope", "local", "--egress", "EXTERNAL_ALLOWED",
               "--roles", "builder", "--route-description", "x", "--warning", "w",
               "--confirmation", "c")
        for t in ("task_record", "subtask_record", "strategy_decision",
                  "override_record", "audit_log"):
            self.assertTrue(self._tamper(f"UPDATE {t} SET schema_version=2"), t)
            self.assertTrue(self._tamper(f"DELETE FROM {t}"), t)

    # T11c tail deletion with triggers dropped -> head anchor mismatch
    def test_t11c_tail_deletion_anchor(self):
        import tempfile
        iso = Path(tempfile.mkdtemp(prefix="eb-iso-"))
        try:
            r = run("init", home=iso); self.assertEqual(r.returncode, 0)
            r = run("classify", "--request-text", "iso", "--task-type", "code",
                    "--roles", "builder", "--reasoning-depth", "1",
                    "--verification-level", "V1", "--risk-class", "R1",
                    "--privacy-class", "P1", "--egress-policy", "EXTERNAL_ALLOWED",
                    "--classification-confidence", "high", home=iso)
            tid = r.stdout.strip()
            r = run("freeze", "--task-id", tid, "--roles", "builder",
                    "--min-reasoning-depth", "1", "--min-verification", "V1", home=iso)
            fid = r.stdout.strip()
            r = run("audit", "--verify", home=iso)
            self.assertEqual(r.returncode, 0)
            con = sqlite3.connect(str(iso / "exec_brain.db"))
            con.executescript("DROP TRIGGER trg_quality_floor_no_delete;")
            con.execute("DELETE FROM quality_floor WHERE floor_id=?", (fid,))
            con.commit()
            con.close()
            r = run("audit", home=iso)
            self.assertEqual(r.returncode, 1)
            self.assertIn("anchor MISMATCH", r.stdout)
        finally:
            shutil.rmtree(iso, ignore_errors=True)

    # T12 two independent classifies both succeed
    def test_t12_independent_concurrent(self):
        import threading
        results = []
        def go():
            results.append(run("classify", "--request-text", "c", "--task-type", "code",
                               "--roles", "builder", "--reasoning-depth", "1",
                               "--verification-level", "V1", "--risk-class", "R1",
                               "--privacy-class", "P1", "--egress-policy", "EXTERNAL_ALLOWED",
                               "--classification-confidence", "high"))
        ts = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(1 for r in results if r.returncode == 0), 2)

    # T12a duplicate same source_event_id concurrently -> exactly one
    def test_t12a_duplicate_concurrent_one_record(self):
        import threading
        results = []
        def go():
            results.append(run("classify", "--request-text", "d", "--task-type", "code",
                               "--roles", "builder", "--reasoning-depth", "1",
                               "--verification-level", "V1", "--risk-class", "R1",
                               "--privacy-class", "P1", "--egress-policy", "EXTERNAL_ALLOWED",
                               "--classification-confidence", "high",
                               "--source-system", "discord", "--source-event-id", "msg-RACE"))
        ts = [threading.Thread(target=go) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        con = sqlite3.connect(str(TEST_HOME / "exec_brain.db"))
        n = con.execute("SELECT COUNT(*) FROM task_record WHERE source_event_id='msg-RACE'").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)

    # T13 regression: live systems untouched (static check)
    # Updated for E2: allows governor.db, adapters.py, governor.py, test_governor.py
    # Updated for E3: allows the deployed E3 orchestration module set and the
    # e3-* CLI bindings (deployed by scripts/deploy_e3_runtime.py).
    def test_t13_no_gateway_modification(self):
        hooks = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "hooks"
        self.assertTrue((hooks / "discord-chief-archive" / "handler.py").exists())
        # E1 + E2 + E3 files under exec-brain
        eb_dir = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "exec-brain"
        allowed = ("eb.py", "exec_brain.db", "tests", "chain-head.json",
                   "backups", "governor.db", "adapters.py", "governor.py",
                   "test_governor.py", "gov-chain-head.json", "telemetry.log",
                   "telemetry.lock", "prune.log", "deepseek-config.json",
                   "capability_registry.py", "task_fingerprint.py",
                   "decision_rationale.py", "execution_dag.py",
                   "worker_contract.py", "worker_registry.py",
                   "qualification_gate.py", "e3_commands.py",
                   "orchestration_db.py", "test_e3.py",
                   "codex_adapter.py", "exec_adapters.py",
                   "deepseek_adapter.py", "deepseek_keyaccess.py",
                   "gemini_adapter.py", "gemini_keyaccess.py",
                   "generic_openai_adapter.py",
                   "orchestration.db", "e3-stage2-state.json",
                   # E3 orchestration modules + CLI bindings (deployed)
                   "e3_cli.py", "e3_planner.py", "e3_router.py",
                   "e3_team_assembly.py", "e3_integrator.py", "e3_verifier.py",
                   "e3_conflict.py", "e3_context.py", "e3_permissions.py",
                   "e3_decomposition_review.py", "e3_evidence.py",
                   "e3_escalate.py", "e3_exploration.py", "e3_replan.py",
                   "e3_qualification_benchmark.py", "e3_shadow_orchestrator.py",
                   "e3_production_rehearsal.py", "e3_execution.py",
                   "e3_execution_rehearsal.py",
                   # E4 resource continuity, deployed because the deployed
                   # e3-status surface imports it for the recorded provider
                   # content-side stop pressure view (see
                   # scripts/deploy_e3_runtime.py). Every other unexpected file
                   # still fails this check.
                   "resource_monitor.py",
                   "__pycache__")
        # SQLite WAL sidecars are runtime artifacts of an ALREADY-allowed
        # project database, not newly deployed files. They are created and
        # left behind whenever a process opens one of these dbs in WAL mode
        # and exits uncleanly (a killed/timed-out worker), so enumerating only
        # the db basename made this static check fail on normal runtime debris
        # rather than on a real live-system modification. Accept exactly the
        # sidecars of allowed databases; every other unexpected file still
        # fails the check.
        sidecars = {
            f"{name}-wal" for name in allowed if name.endswith(".db")
        } | {
            f"{name}-shm" for name in allowed if name.endswith(".db")
        }
        allowed_names = set(allowed) | sidecars
        for f in eb_dir.iterdir():
            self.assertIn(f.name, allowed_names, f"unexpected file {f}")

    # T14 curated summary excludes raw text
    def test_t14_summary_no_raw_text(self):
        tid = self.new_task(text="SECRETISH raw request text P2")
        self.new_floor(tid)
        r = self.a("summary")
        self.assertNotIn("SECRETISH", r.stdout)

    # T15 full pipeline
    def test_t15_full_pipeline(self):
        tid = self.new_task()
        st = self.a("decompose", "--task-id", tid, "--title", "impl",
                    "--order-index", "0").stdout.strip()
        fid = self.new_floor(tid, subtask=st)
        r = self.route(fid)
        self.assertEqual(r.returncode, 0)
        r = self.a("audit")
        self.assertEqual(r.returncode, 0)

    # T16 reasoning below floor
    def test_t16_reasoning_below_floor(self):
        tid = self.new_task()
        fid = self.new_floor(tid, rd=3)
        r = self.route(fid, rd=2)
        self.assertEqual(r.returncode, 1)
        self.assertIn("reasoning", r.stderr)

    # T17 verification below floor
    def test_t17_verification_below_floor(self):
        tid = self.new_task()
        fid = self.new_floor(tid, v="V2")
        r = self.route(fid, v="V1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("verification", r.stderr)

    # T18 LOCAL_ONLY -> external
    def test_t18_local_only_external_refused(self):
        tid = self.new_task()
        fid = self.new_floor(tid, egress="LOCAL_ONLY")
        r = self.route(fid, scope="external")
        self.assertEqual(r.returncode, 1)
        self.assertIn("LOCAL_ONLY", r.stderr)

    # T19 low confidence blocks routing
    def test_t19_low_confidence_blocks(self):
        tid = self.new_task(c="low")
        fid = self.new_floor(tid)
        r = self.route(fid)
        self.assertEqual(r.returncode, 1)
        self.assertIn("low", r.stderr)

    # T20 FK violation rejected
    def test_t20_fk_violation(self):
        con = sqlite3.connect(str(TEST_HOME / "exec_brain.db"))
        con.execute("PRAGMA foreign_keys = ON")
        try:
            con.execute("INSERT INTO strategy_decision (decision_id,floor_id,decided_at,"
                        "strategy,proposed_reasoning_depth,proposed_verification,"
                        "execution_scope,proposed_egress,claimed_roles,"
                        "qualification_evidence,gate_result) "
                        "VALUES ('sd-x','fl-nonexistent','2026','3',1,'V1','local','X','[]','UNPROVEN','accept')")
            con.commit()
            self.fail("FK violation was accepted")
        except sqlite3.IntegrityError:
            pass
        finally:
            con.close()

    # T21 backup + restore
    def test_t21_backup_restore(self):
        tid = self.new_task()
        self.new_floor(tid)
        r = self.a("backup")
        bfile = Path(r.stdout.strip().replace("backup: ", ""))
        bdir = bfile.parent
        r2 = self.a("restore", "--backup-dir", str(bdir))
        self.assertEqual(r2.returncode, 0)
        r3 = run("audit")
        self.assertEqual(r3.returncode, 0)

    # T22 strategy constraint violation
    def test_t22_strategy_constraint(self):
        tid = self.new_task()
        fid = self.new_floor(tid, strategy="1,2")
        r = self.route(fid, s="3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("strategy", r.stderr)

    # T23 missing required role
    def test_t23_missing_role(self):
        tid = self.new_task()
        fid = self.new_floor(tid, roles="builder,critic")
        r = self.route(fid, roles="builder")
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing required roles", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
