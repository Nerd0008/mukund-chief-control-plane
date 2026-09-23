#!/usr/bin/env python3
"""Tests for Hermes GitHub Remote Queue poller."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.temp_dir = tempfile.mkdtemp()
        self.orig_pending = qs.PENDING_DIR
        self.orig_running = qs.RUNNING_DIR
        self.orig_completed = qs.COMPLETED_DIR
        self.orig_blocked = qs.BLOCKED_DIR
        self.orig_log = qs.LOG_DIR
        qs.PENDING_DIR = Path(self.temp_dir) / "pending"
        qs.RUNNING_DIR = Path(self.temp_dir) / "running"
        qs.COMPLETED_DIR = Path(self.temp_dir) / "completed"
        qs.BLOCKED_DIR = Path(self.temp_dir) / "blocked"
        qs.LOG_DIR = Path(self.temp_dir) / "logs"

    def tearDown(self):
        qs.PENDING_DIR = self.orig_pending
        qs.RUNNING_DIR = self.orig_running
        qs.COMPLETED_DIR = self.orig_completed
        qs.BLOCKED_DIR = self.orig_blocked
        qs.LOG_DIR = self.orig_log
        shutil.rmtree(self.temp_dir, ignore_errors=True)

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
    """Test poller CLI entry points."""

    def test_status_flag(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "remote_queue/poller.py", "--status"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Queue status", result.stdout)

    def test_once_flag(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "remote_queue/poller.py", "--once"],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)

    def test_kill_switch(self):
        import subprocess
        import remote_queue.poller as poller_mod

        kf = poller_mod.KILL_SWITCH_FILE

        if kf.exists():
            kf.unlink()

        result = subprocess.run(
            [sys.executable, "remote_queue/poller.py", "--kill"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(kf.exists())

        result = subprocess.run(
            [sys.executable, "remote_queue/poller.py", "--resume"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(kf.exists())


if __name__ == '__main__':
    unittest.main()
