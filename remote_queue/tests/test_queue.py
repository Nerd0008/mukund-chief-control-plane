#!/usr/bin/env python3
"""Tests for Hermes GitHub Remote Queue poller."""

import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import remote_queue.queue_schema as qs
from remote_queue.queue_schema import (
    ensure_dirs, validate_task, claim_task, complete_task, block_task,
    find_pending_tasks, is_task_completed, is_task_blocked, is_task_running,
)


class TestTaskValidation(unittest.TestCase):
    """Test task schema validation."""

    def test_valid_task(self):
        task = {
            "task_id": "test-task-1",
            "created_at": "2026-09-23",
            "objective": "Test objective",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "priority": "critical",
            "allowed_scope": ["test"],
            "requires_owner_approval": False,
            "status": "pending",
        }
        errors = validate_task(task)
        self.assertEqual(len(errors), 0)

    def test_missing_required_field(self):
        task = {"task_id": "test", "objective": "Test"}
        errors = validate_task(task)
        self.assertTrue(any("missing required field" in e for e in errors))

    def test_invalid_priority(self):
        task = {
            "task_id": "test",
            "created_at": "2026-09-23",
            "objective": "Test",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "priority": "invalid",
            "allowed_scope": ["test"],
            "requires_owner_approval": False,
            "status": "pending",
        }
        errors = validate_task(task)
        self.assertTrue(any("priority" in e for e in errors))

    def test_invalid_task_id_format(self):
        task = {
            "task_id": "test task!",
            "created_at": "2026-09-23",
            "objective": "Test",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "priority": "medium",
            "allowed_scope": ["test"],
            "requires_owner_approval": False,
            "status": "pending",
        }
        errors = validate_task(task)
        self.assertTrue(any("task_id format" in e for e in errors))

    def test_unapproved_authority(self):
        task = {
            "task_id": "test",
            "created_at": "2026-09-23",
            "objective": "Test",
            "authority": "unapproved-file.md",
            "priority": "medium",
            "allowed_scope": ["test"],
            "requires_owner_approval": False,
            "status": "pending",
        }
        errors = validate_task(task)
        self.assertTrue(any("authority" in e for e in errors))

    def test_secrets_in_objective(self):
        task = {
            "task_id": "test",
            "created_at": "2026-09-23",
            "objective": "Get the api_key = abc123 from credentials",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "priority": "medium",
            "allowed_scope": ["test"],
            "requires_owner_approval": False,
            "status": "pending",
        }
        errors = validate_task(task)
        self.assertTrue(any("secret" in e.lower() for e in errors))


class TestQueueOperations(unittest.TestCase):
    """Test queue file operations using temp dirs."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.orig_pending = qs.PENDING_DIR
        self.orig_running = qs.RUNNING_DIR
        self.orig_completed = qs.COMPLETED_DIR
        self.orig_blocked = qs.BLOCKED_DIR
        self.orig_log = qs.LOG_DIR
        qs.PENDING_DIR = self.root / "pending"
        qs.RUNNING_DIR = self.root / "running"
        qs.COMPLETED_DIR = self.root / "completed"
        qs.BLOCKED_DIR = self.root / "blocked"
        qs.LOG_DIR = self.root / "logs"
        # Queue transitions normally commit and push remote-queue/. Tests must
        # never write to or push from the real checkout.
        self.git_patch = patch.object(qs, "_git_commit_and_push", return_value=True)
        self.mock_git_commit_and_push = self.git_patch.start()

    def tearDown(self):
        qs.PENDING_DIR = self.orig_pending
        qs.RUNNING_DIR = self.orig_running
        qs.COMPLETED_DIR = self.orig_completed
        qs.BLOCKED_DIR = self.orig_blocked
        qs.LOG_DIR = self.orig_log
        self.git_patch.stop()
        self.temp_dir.cleanup()

    def _make_task(self, task_id="test-1", **overrides):
        task = {
            "task_id": task_id,
            "created_at": "2026-09-23",
            "objective": "Test task",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "priority": "medium",
            "allowed_scope": ["test"],
            "requires_owner_approval": False,
            "status": "pending",
        }
        task.update(overrides)
        return task

    def test_claim_task(self):
        ensure_dirs()
        task = self._make_task()
        task_path = qs.PENDING_DIR / "test-1.json"
        with open(task_path, 'w') as f:
            json.dump(task, f)

        self.assertTrue(claim_task(task_path))
        self.assertFalse(task_path.exists())
        self.assertTrue((qs.RUNNING_DIR / "test-1.json").exists())
        self.mock_git_commit_and_push.assert_called_once_with("queue: claim test-1")

    def test_complete_task(self):
        ensure_dirs()
        task = self._make_task()
        running_path = qs.RUNNING_DIR / "test-1.json"
        with open(running_path, 'w') as f:
            json.dump(task, f)

        complete_task("test-1", {"status": "done"})

        self.assertFalse(running_path.exists())
        completed_path = qs.COMPLETED_DIR / "test-1.json"
        self.assertTrue(completed_path.exists())
        with open(completed_path) as f:
            completed = json.load(f)
        self.assertEqual(completed["status"], "completed")
        self.assertIn("completed_at", completed)

    def test_block_task(self):
        ensure_dirs()
        task = self._make_task()
        running_path = qs.RUNNING_DIR / "test-1.json"
        with open(running_path, 'w') as f:
            json.dump(task, f)

        block_task("test-1", "credentials", "Provide API key", "Other work continues")

        self.assertFalse(running_path.exists())
        blocked_path = qs.BLOCKED_DIR / "test-1.json"
        self.assertTrue(blocked_path.exists())
        with open(blocked_path) as f:
            blocked = json.load(f)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["blocker"]["category"], "credentials")

    def test_find_pending_tasks(self):
        ensure_dirs()
        for i in range(3):
            task = self._make_task(task_id=f"test-{i}",
                                   priority=["high", "medium", "low"][i])
            with open(qs.PENDING_DIR / f"test-{i}.json", 'w') as f:
                json.dump(task, f)

        pending = find_pending_tasks()
        self.assertEqual(len(pending), 3)
        self.assertEqual(pending[0].stem, "test-0")

    def test_deduplication(self):
        ensure_dirs()
        task = self._make_task()
        task_path = qs.PENDING_DIR / "test-1.json"
        with open(task_path, 'w') as f:
            json.dump(task, f)

        self.assertTrue(claim_task(task_path))
        self.assertFalse(claim_task(task_path))

    def test_is_task_completed(self):
        ensure_dirs()
        self.assertFalse(is_task_completed("test-1"))
        with open(qs.COMPLETED_DIR / "test-1.json", 'w') as f:
            json.dump(self._make_task(), f)
        self.assertTrue(is_task_completed("test-1"))


class TestPollerCLI(unittest.TestCase):
    """Test CLI entry points against temporary queue state only."""

    def setUp(self):
        import remote_queue.poller as poller_mod

        self.poller = poller_mod
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original = {
            "pending": qs.PENDING_DIR,
            "running": qs.RUNNING_DIR,
            "completed": qs.COMPLETED_DIR,
            "blocked": qs.BLOCKED_DIR,
            "logs": qs.LOG_DIR,
            "kill": poller_mod.KILL_SWITCH_FILE,
            "lock": poller_mod.LOCK_FILE,
        }
        self.original_pending_files = {
            path.name: path.read_bytes()
            for path in self.original["pending"].glob("*.json")
        } if self.original["pending"].exists() else {}
        self.original_kill_bytes = (
            self.original["kill"].read_bytes() if self.original["kill"].exists() else None
        )
        self.original_lock_bytes = (
            self.original["lock"].read_bytes() if self.original["lock"].exists() else None
        )
        qs.PENDING_DIR = self.root / "pending"
        qs.RUNNING_DIR = self.root / "running"
        qs.COMPLETED_DIR = self.root / "completed"
        qs.BLOCKED_DIR = self.root / "blocked"
        qs.LOG_DIR = self.root / "logs"
        poller_mod.PENDING_DIR = qs.PENDING_DIR
        poller_mod.RUNNING_DIR = qs.RUNNING_DIR
        poller_mod.COMPLETED_DIR = qs.COMPLETED_DIR
        poller_mod.BLOCKED_DIR = qs.BLOCKED_DIR
        poller_mod.KILL_SWITCH_FILE = self.root / ".poller.kill"
        poller_mod.LOCK_FILE = self.root / ".poller.lock"

        self.git_patch = patch.object(qs, "_git_commit_and_push", return_value=True)
        self.mock_git_commit_and_push = self.git_patch.start()
        self.acquire_lock_patch = patch.object(poller_mod, "acquire_lock", return_value=True)
        self.acquire_lock_patch.start()
        self.release_lock_patch = patch.object(poller_mod, "release_lock")
        self.release_lock_patch.start()
        self.pull_patch = patch.object(poller_mod, "git_pull_safely", return_value=True)
        self.pull_patch.start()

    def tearDown(self):
        self.pull_patch.stop()
        self.release_lock_patch.stop()
        self.acquire_lock_patch.stop()
        self.git_patch.stop()
        qs.PENDING_DIR = self.original["pending"]
        qs.RUNNING_DIR = self.original["running"]
        qs.COMPLETED_DIR = self.original["completed"]
        qs.BLOCKED_DIR = self.original["blocked"]
        qs.LOG_DIR = self.original["logs"]
        self.poller.PENDING_DIR = self.original["pending"]
        self.poller.RUNNING_DIR = self.original["running"]
        self.poller.COMPLETED_DIR = self.original["completed"]
        self.poller.BLOCKED_DIR = self.original["blocked"]
        self.poller.KILL_SWITCH_FILE = self.original["kill"]
        self.poller.LOCK_FILE = self.original["lock"]
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["poller.py", *args]), redirect_stdout(output):
            self.poller.main()
        return output.getvalue()

    def assert_original_state_unchanged(self):
        pending = self.original["pending"]
        actual_pending = {
            path.name: path.read_bytes() for path in pending.glob("*.json")
        } if pending.exists() else {}
        self.assertEqual(actual_pending, self.original_pending_files)
        self.assertEqual(
            self.original["kill"].read_bytes() if self.original["kill"].exists() else None,
            self.original_kill_bytes,
        )
        self.assertEqual(
            self.original["lock"].read_bytes() if self.original["lock"].exists() else None,
            self.original_lock_bytes,
        )

    def test_status_flag(self):
        output = self.run_cli("--status")
        self.assertIn("Queue status", output)

    def test_once_flag(self):
        task = {
            "task_id": "agent-isolated-test",
            "created_at": "2026-09-23",
            "objective": "Isolated poller CLI test",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "priority": "medium",
            "allowed_scope": ["test"],
            "requires_owner_approval": False,
            "status": "pending",
        }
        ensure_dirs()
        (qs.PENDING_DIR / "agent-isolated-test.json").write_text(json.dumps(task), encoding="utf-8")
        with patch.object(self.poller, "handle_task", return_value={"status": "completed"}):
            self.run_cli("--once")
        self.assertTrue((qs.COMPLETED_DIR / "agent-isolated-test.json").exists())
        self.assertFalse((qs.PENDING_DIR / "agent-isolated-test.json").exists())
        self.assertFalse((qs.RUNNING_DIR / "agent-isolated-test.json").exists())
        self.assertEqual(self.mock_git_commit_and_push.call_count, 2)
        self.assert_original_state_unchanged()

    def test_kill_switch(self):
        kf = self.poller.KILL_SWITCH_FILE
        self.run_cli("--kill")
        self.assertTrue(kf.exists())
        self.assert_original_state_unchanged()
        self.run_cli("--resume")
        self.assertFalse(kf.exists())
        self.assert_original_state_unchanged()


if __name__ == '__main__':
    unittest.main()
