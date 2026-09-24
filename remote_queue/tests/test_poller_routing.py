#!/usr/bin/env python3
"""Isolated regression tests for poller.handle_task dispatch routing.

Defect covered
--------------
``handle_task`` matched legacy *substring* placeholder routers ('operational',
'bridge-validation', 'e2e-test', 'e2e-final', 'remote-e2e', 'hardened-*')
BEFORE the ``agent-`` dispatch branch. Any genuine agent task whose id happened
to contain one of those substrings was therefore never dispatched to Hermes: it
returned a hardcoded placeholder status instead.

Observed live: ``agent-operational-brief-health-backup-persistence-2026-09-23``
was claimed at 2026-09-24T01:38:05Z and immediately logged
``in progress (attempt 1)`` from the hardcoded handler, leaving the task in
``running/`` with no real execution and no terminal transition.

Isolation contract
------------------
These tests never dispatch to Hermes and never touch the live queue:

* ``dispatch_task`` is monkeypatched with a recording stub,
* every queue path is redirected into a per-test temporary directory,
* the live ``remote-queue/`` directories are never read or written.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import remote_queue.queue_schema as qs
import remote_queue.poller as poller

LIVE_QUEUE_ROOT = REPO_ROOT / "remote-queue"


class TestHandleTaskRouting(unittest.TestCase):
    """Routing contract: agent tasks always reach Hermes dispatch."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hermes-routing-test-"))
        self.queue_root = self.temp_dir / "remote-queue"
        self._orig = {
            "REPO_ROOT": qs.REPO_ROOT,
            "QUEUE_DIR": qs.QUEUE_DIR,
            "PENDING_DIR": qs.PENDING_DIR,
            "RUNNING_DIR": qs.RUNNING_DIR,
            "COMPLETED_DIR": qs.COMPLETED_DIR,
            "BLOCKED_DIR": qs.BLOCKED_DIR,
            "LOG_DIR": qs.LOG_DIR,
        }
        qs.REPO_ROOT = self.temp_dir
        qs.QUEUE_DIR = self.queue_root
        qs.PENDING_DIR = self.queue_root / "pending"
        qs.RUNNING_DIR = self.queue_root / "running"
        qs.COMPLETED_DIR = self.queue_root / "completed"
        qs.BLOCKED_DIR = self.queue_root / "blocked"
        qs.LOG_DIR = self.queue_root / "logs"
        qs.ensure_dirs()

        self.dispatched = []
        self._orig_dispatch = poller.dispatch_task

        def _stub(task, timeout_seconds=None, attempt=1):
            self.dispatched.append((task["task_id"], attempt))
            return {"status": "in_progress", "summary": "stub dispatch"}

        poller.dispatch_task = _stub

    def tearDown(self):
        poller.dispatch_task = self._orig_dispatch
        for key, value in self._orig.items():
            setattr(qs, key, value)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.assertFalse(
            (LIVE_QUEUE_ROOT / ".poller.kill").exists(),
            "routing tests must not touch the live queue",
        )

    def _task(self, task_id):
        return {"task_id": task_id, "objective": "routing probe"}

    def test_agent_task_containing_operational_is_dispatched(self):
        """The live defect: 'operational' must not swallow an agent task."""
        result = poller.handle_task(
            self._task("agent-operational-brief-health-backup-persistence-2026-09-23")
        )
        self.assertEqual(self.dispatched, [
            ("agent-operational-brief-health-backup-persistence-2026-09-23", 1)
        ])
        self.assertEqual(result["status"], "in_progress")

    def test_agent_task_containing_e2e_substring_is_dispatched(self):
        for task_id in (
            "agent-e2e-test-something-2026-09-24",
            "agent-e2e-final-something-2026-09-24",
            "agent-remote-e2e-something-2026-09-24",
            "agent-hardened-regression-something-2026-09-24",
            "agent-bridge-validation-something-2026-09-24",
        ):
            self.dispatched.clear()
            poller.handle_task(self._task(task_id))
            self.assertEqual(self.dispatched, [(task_id, 1)], task_id)

    def test_plain_agent_task_is_dispatched(self):
        poller.handle_task(self._task("agent-plain-work-2026-09-24"))
        self.assertEqual(self.dispatched, [("agent-plain-work-2026-09-24", 1)])

    def test_dispatch_receives_the_attempt_number(self):
        poller.handle_task(self._task("agent-plain-work-2026-09-24"), attempt=2)
        self.assertEqual(self.dispatched, [("agent-plain-work-2026-09-24", 2)])

    def test_non_agent_operational_umbrella_still_uses_placeholder(self):
        result = poller.handle_task(self._task("full-operational-build-2026-09-24"))
        self.assertEqual(self.dispatched, [])
        self.assertEqual(result.get("status"), "in_progress")
        self.assertIn("summary", result)

    def test_non_agent_e2e_placeholder_still_works(self):
        result = poller.handle_task(self._task("remote-e2e-test-001"))
        self.assertEqual(self.dispatched, [])
        self.assertEqual(result.get("status"), "completed")

    def test_unknown_non_agent_task_fails_closed(self):
        with self.assertRaises(ValueError):
            poller.handle_task(self._task("totally-unknown-queue-object"))
        self.assertEqual(self.dispatched, [])

    def test_agent_short_circuit_precedes_placeholder_routes(self):
        """Guard against a future reorder reintroducing the defect."""
        src = (REPO_ROOT / "remote_queue" / "poller.py").read_text(encoding="utf-8")
        agent_idx = src.index('if task_id.startswith("agent-"):')
        operational_idx = src.index('if "full-operational-build" in task_id')
        self.assertLess(
            agent_idx,
            operational_idx,
            "the agent- dispatch branch must precede the placeholder routers",
        )


class TestRoutingIsolation(unittest.TestCase):
    def test_live_kill_switch_absent(self):
        self.assertFalse((LIVE_QUEUE_ROOT / ".poller.kill").exists())


if __name__ == "__main__":
    unittest.main()
