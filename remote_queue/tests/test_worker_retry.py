#!/usr/bin/env python3
"""Isolated tests for bounded recoverable-failure retry.

Owner directive (2026-09-24, in the active authority file): a recoverable worker
execution failure must be retried **twice** (initial attempt + 2 retries) before
the task is finally marked blocked and the queue advances. Deterministic
owner/external blockers must never be retried (the Stage-2 missing-key gate is
one of these).

Isolation contract
------------------
* Queue data lives in a per-test temporary directory; the live ``remote-queue/``
  is never read, claimed from, blocked in, or written.
* Git publication is replaced by a recorder, so nothing is committed or pushed.
* No real Hermes process is launched: execution is a fake handler.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import remote_queue.queue_schema as qs
import remote_queue.poller as poller
from remote_queue import hermes_dispatch as hd
from remote_queue.retry_policy import (
    MAX_ATTEMPTS, MAX_RETRIES, NON_RETRYABLE_CATEGORIES, RECOVERABLE_CATEGORIES,
    is_recoverable, next_attempt_number, plan_retry, retry_state,
)

LIVE_QUEUE_ROOT = REPO_ROOT / "remote-queue"
AUTHORITY = "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md"


def _make_task(task_id="agent-retry-unit", **overrides):
    task = {
        "task_id": task_id,
        "created_at": "2026-09-24T00:00:00Z",
        "objective": "retry policy unit test",
        "authority": AUTHORITY,
        "priority": "medium",
        "allowed_scope": ["nothing"],
        "requires_owner_approval": False,
        "status": "pending",
    }
    task.update(overrides)
    return task


def _blocked(category, summary="simulated failure"):
    return {
        "status": "blocked",
        "summary": summary,
        "owner_action_required": None,
        "blocker_category": category,
        "commits": [],
        "tests": [],
        "changed_files": [],
        "remaining": ["retry"],
    }


class TestRetryBound(unittest.TestCase):
    """Structural bound: the budget cannot be exceeded for any input."""

    def test_owner_directive_budget_is_two_retries(self):
        self.assertEqual(MAX_RETRIES, 2)
        self.assertEqual(MAX_ATTEMPTS, 3)

    def test_recoverable_failure_retries_then_parks(self):
        decisions = [plan_retry(attempt, _blocked("execution_error"))[0]
                     for attempt in range(1, 6)]
        # attempt 1 -> retry, attempt 2 -> retry, attempt 3+ -> park. Never more.
        self.assertEqual(decisions, [True, True, False, False, False])

    def test_exhausted_budget_reason_is_truthful(self):
        retry, reason = plan_retry(MAX_ATTEMPTS, _blocked("execution_error"))
        self.assertFalse(retry)
        self.assertIn(f"{MAX_ATTEMPTS} of {MAX_ATTEMPTS} permitted attempts", reason)

    def test_only_execution_error_is_recoverable(self):
        self.assertEqual(RECOVERABLE_CATEGORIES, frozenset({"execution_error"}))
        self.assertTrue(is_recoverable(_blocked("execution_error"))[0])

    def test_deterministic_blockers_are_never_recoverable(self):
        for category in NON_RETRYABLE_CATEGORIES:
            with self.subTest(category=category):
                retry, reason = plan_retry(1, _blocked(category))
                self.assertFalse(retry)
                self.assertIn(category, reason)

    def test_unknown_or_missing_category_fails_closed(self):
        for category in (None, "unknown_category", ""):
            with self.subTest(category=category):
                retry, _reason = plan_retry(1, _blocked(category))
                self.assertFalse(retry)

    def test_non_blocked_result_is_not_recoverable(self):
        for status in ("completed", "in_progress", None):
            with self.subTest(status=status):
                retry, _reason = plan_retry(1, {"status": status})
                self.assertFalse(retry)

    def test_state_and_resume_helpers(self):
        state = retry_state(2, _blocked("execution_error"), will_retry=True, reason="r")
        self.assertEqual(state["attempts_used"], 2)
        self.assertEqual(state["retries_used"], 1)
        self.assertEqual(state["max_retries"], 2)
        self.assertEqual(state["max_attempts"], 3)
        self.assertEqual(state["next_action"], "retry")
        self.assertEqual(next_attempt_number(state), 3)
        self.assertEqual(next_attempt_number({}), 1)
        self.assertEqual(next_attempt_number(None), 1)


class TestRetryPromptContract(unittest.TestCase):
    """A retry must tell the agent to preserve landed work."""

    def test_first_attempt_has_no_retry_context(self):
        prompt = hd._task_prompt(_make_task(), attempt=1)
        self.assertNotIn("RETRY CONTEXT", prompt)

    def test_retry_attempt_carries_resume_guidance(self):
        prompt = hd._task_prompt(_make_task(), attempt=2)
        self.assertIn("RETRY CONTEXT (attempt 2 of 3)", prompt)
        self.assertIn("preserved and", prompt)
        self.assertIn("must not be recreated, reverted, duplicated, or redone", prompt)
        self.assertIn("Resume from the smallest unfinished unit", prompt)
        # The contract itself is untouched by retry labelling.
        self.assertIn("Treat your own remote-queue/running/agent-retry-unit.json"
                      " as immutable execution input", prompt)

    def test_dispatch_passes_the_attempt_to_the_visible_worker(self):
        import subprocess

        captured = []
        original = hd.subprocess

        class _Proc:
            returncode = 0
            pid = 1

            def wait(self, timeout=None):
                return 0

        def fake_popen(cmd, **kwargs):
            argv = list(cmd)
            captured.append(argv)
            Path(argv[argv.index("--output-file") + 1]).write_text(
                json.dumps({"status": "completed", "summary": "ok"}), encoding="utf-8"
            )
            Path(argv[argv.index("--exit-file") + 1]).write_text("0", encoding="utf-8")
            return _Proc()

        class _Shim:
            def __init__(self):
                self.Popen = fake_popen

            def __getattr__(self, name):
                return getattr(original, name)

        saved = os.environ.get("HERMES_CLI")
        saved_visible = os.environ.get("HERMES_REMOTE_VISIBLE")
        os.environ["HERMES_CLI"] = sys.executable
        os.environ["HERMES_REMOTE_VISIBLE"] = "1"
        hd.subprocess = _Shim()
        try:
            hd.dispatch_task(_make_task(), attempt=2)
        finally:
            hd.subprocess = original
            for key, value in (("HERMES_CLI", saved), ("HERMES_REMOTE_VISIBLE", saved_visible)):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        argv = captured[-1]
        self.assertEqual(argv[argv.index("--attempt") + 1], "2")


class _RetryHarness(unittest.TestCase):
    """Disposable queue root with a scripted execution handler."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hermes-retry-test-"))
        self.queue_root = self.temp_dir / "remote-queue"
        self.publishes = []
        self.attempts = []
        self.responses = []

        self._orig = {
            "REPO_ROOT": qs.REPO_ROOT,
            "QUEUE_DIR": qs.QUEUE_DIR,
            "PENDING_DIR": qs.PENDING_DIR,
            "RUNNING_DIR": qs.RUNNING_DIR,
            "COMPLETED_DIR": qs.COMPLETED_DIR,
            "BLOCKED_DIR": qs.BLOCKED_DIR,
            "LOG_DIR": qs.LOG_DIR,
            "_git_commit_and_push": qs._git_commit_and_push,
        }

        qs.REPO_ROOT = self.temp_dir
        qs.QUEUE_DIR = self.queue_root
        qs.PENDING_DIR = self.queue_root / "pending"
        qs.RUNNING_DIR = self.queue_root / "running"
        qs.COMPLETED_DIR = self.queue_root / "completed"
        qs.BLOCKED_DIR = self.queue_root / "blocked"
        qs.LOG_DIR = self.queue_root / "logs"
        qs._git_commit_and_push = self._record_publish
        qs.ensure_dirs()

        self._orig_poller = {
            "handle_task": poller.handle_task,
            "git_pull_safely": poller.git_pull_safely,
            "check_kill_switch": poller.check_kill_switch,
            "KILL_SWITCH_FILE": poller.KILL_SWITCH_FILE,
        }
        poller.handle_task = self._handler
        poller.git_pull_safely = lambda: True
        poller.check_kill_switch = lambda: False
        poller.KILL_SWITCH_FILE = self.temp_dir / ".poller.kill"

    def tearDown(self):
        for key, value in self._orig.items():
            setattr(qs, key, value)
        for key, value in self._orig_poller.items():
            setattr(poller, key, value)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _record_publish(self, message):
        self.publishes.append(message)
        return True

    def _handler(self, task, attempt=1):
        self.attempts.append(attempt)
        if attempt <= len(self.responses):
            return self.responses[attempt - 1]
        return self.responses[-1] if self.responses else {"status": "completed"}

    def _write_pending(self, task):
        path = qs.PENDING_DIR / f"{task['task_id']}.json"
        path.write_text(json.dumps(task), encoding="utf-8")
        return path

    def _write_running(self, task, retry_state_value=None, execution_attempts=None):
        record = dict(task)
        record["status"] = "running"
        if retry_state_value is not None:
            record["retry_state"] = retry_state_value
        if execution_attempts is not None:
            record["execution_attempts"] = execution_attempts
        path = qs.RUNNING_DIR / f"{task['task_id']}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    def _running_record(self, task_id):
        return json.loads((qs.RUNNING_DIR / f"{task_id}.json").read_text(encoding="utf-8"))

    def _blocked_record(self, task_id):
        return json.loads((qs.BLOCKED_DIR / f"{task_id}.json").read_text(encoding="utf-8"))

    def _completed_record(self, task_id):
        return json.loads((qs.COMPLETED_DIR / f"{task_id}.json").read_text(encoding="utf-8"))


class TestBoundedRetryInPoller(_RetryHarness):
    """End-to-end queue-cycle behaviour with the scripted handler."""

    def test_recoverable_failure_is_retried_twice_then_blocked(self):
        task = _make_task()
        self.responses = [_blocked("execution_error")]
        self._write_pending(task)

        poller.run_poll_cycle()

        self.assertEqual(self.attempts, [1, 2, 3], "exactly initial + 2 retries")
        self.assertFalse((qs.RUNNING_DIR / f"{task['task_id']}.json").exists())
        blocked = self._blocked_record(task["task_id"])
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["blocker"]["category"], "execution_error")
        self.assertEqual(len(blocked["execution_attempts"]), 3)
        self.assertEqual(blocked["retry_state"]["attempts_used"], 3)
        self.assertEqual(blocked["retry_state"]["retries_used"], 2)
        self.assertEqual(blocked["retry_state"]["next_action"], "park")
        self.assertTrue(all(a["will_retry"] is False
                            for a in blocked["execution_attempts"][-1:]))
        self.assertTrue(any(p.startswith(f"queue: attempt 1/{MAX_ATTEMPTS}") for p in self.publishes))
        self.assertTrue(any(p.startswith(f"queue: attempt 3/{MAX_ATTEMPTS}") for p in self.publishes))
        self.assertTrue(any(p.startswith(f"queue: block {task['task_id']}") for p in self.publishes))

    def test_success_on_the_second_attempt_completes_without_further_retries(self):
        task = _make_task()
        self.responses = [
            _blocked("execution_error"),
            {"status": "completed", "summary": "done on retry"},
        ]
        self._write_pending(task)

        poller.run_poll_cycle()

        self.assertEqual(self.attempts, [1, 2])
        completed = self._completed_record(task["task_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(len(completed["execution_attempts"]), 1)
        self.assertEqual(completed["retry_state"]["retries_used"], 0)
        self.assertFalse((qs.BLOCKED_DIR / f"{task['task_id']}.json").exists())

    def test_success_on_the_last_permitted_attempt_is_accepted(self):
        task = _make_task()
        self.responses = [
            _blocked("execution_error"),
            _blocked("execution_error"),
            {"status": "completed", "summary": "done on final attempt"},
        ]
        self._write_pending(task)

        poller.run_poll_cycle()

        self.assertEqual(self.attempts, [1, 2, 3])
        self.assertTrue((qs.COMPLETED_DIR / f"{task['task_id']}.json").exists())
        self.assertFalse((qs.BLOCKED_DIR / f"{task['task_id']}.json").exists())

    def test_deterministic_blockers_park_on_the_first_attempt(self):
        for index, category in enumerate(sorted(NON_RETRYABLE_CATEGORIES)):
            with self.subTest(category=category):
                task = _make_task(task_id=f"agent-{category.replace('_', '-')}-{index}")
                self.attempts = []
                self.responses = [_blocked(category, summary=f"{category} blocker")]
                self._write_pending(task)

                poller.run_poll_cycle()

                self.assertEqual(self.attempts, [1], f"{category} must not be retried")
                blocked = self._blocked_record(task["task_id"])
                self.assertEqual(blocked["blocker"]["category"], category)
                self.assertEqual(blocked["retry_state"]["retries_used"], 0)
                self.assertEqual(blocked["retry_state"]["next_action"], "park")

    def test_stage2_missing_key_gate_is_not_retried(self):
        """0/7 provider keys is deterministic: the anti-loop directive still holds."""
        task = _make_task(task_id="agent-e3-stage2-readiness-gate-after-provider-keys-retry-3-2026-09-24")
        self.responses = [_blocked(
            "credentials",
            summary="Seven owner-local provider credentials remain absent (0/7).",
        )]
        self._write_pending(task)

        poller.run_poll_cycle()

        self.assertEqual(self.attempts, [1])
        blocked = self._blocked_record(task["task_id"])
        self.assertEqual(blocked["blocker"]["category"], "credentials")
        self.assertIn("absent", blocked["blocker"]["owner_action_required"])

    def test_unknown_blocker_category_parks_immediately(self):
        task = _make_task()
        self.responses = [{"status": "blocked", "summary": "unclassified failure"}]
        self._write_pending(task)

        poller.run_poll_cycle()

        self.assertEqual(self.attempts, [1])
        blocked = self._blocked_record(task["task_id"])
        self.assertEqual(blocked["blocker"]["category"], "execution_error")
        self.assertEqual(blocked["retry_state"]["retries_used"], 0)

    def test_handler_exception_is_retried_then_blocked(self):
        task = _make_task()

        def exploding_handler(_task, attempt=1):
            self.attempts.append(attempt)
            raise RuntimeError("simulated wrapper crash")

        poller.handle_task = exploding_handler
        self._write_pending(task)

        poller.run_poll_cycle()

        self.assertEqual(self.attempts, [1, 2, 3])
        blocked = self._blocked_record(task["task_id"])
        self.assertEqual(blocked["blocker"]["category"], "execution_error")
        self.assertIn("simulated wrapper crash", blocked["blocker"]["owner_action_required"])

    def test_invalid_status_is_treated_as_a_recoverable_execution_error(self):
        task = _make_task()
        self.responses = [{"status": "nonsense", "summary": "bad status"}]
        self._write_pending(task)

        poller.run_poll_cycle()

        self.assertEqual(self.attempts, [1, 2, 3])
        self.assertTrue((qs.BLOCKED_DIR / f"{task['task_id']}.json").exists())


class TestResumeUsesThePersistedBudget(_RetryHarness):
    """A restart must resume the bounded count, never restart the loop."""

    def test_resume_continues_from_persisted_attempt_count(self):
        task = _make_task()
        self.responses = [_blocked("execution_error")]
        self._write_running(
            task,
            retry_state_value=retry_state(1, _blocked("execution_error"), True, "resume"),
            execution_attempts=[{"attempt": 1, "will_retry": True}],
        )

        poller._run_task_with_bounded_retry(task["task_id"], task)

        self.assertEqual(self.attempts, [2, 3], "resume must not restart from attempt 1")
        blocked = self._blocked_record(task["task_id"])
        self.assertEqual(len(blocked["execution_attempts"]), 3)

    def test_exhausted_persisted_budget_is_not_re_executed(self):
        task = _make_task()
        self.responses = [_blocked("execution_error")]
        self._write_running(
            task,
            retry_state_value=retry_state(3, _blocked("execution_error"), False, "exhausted"),
            execution_attempts=[{"attempt": 1}, {"attempt": 2}, {"attempt": 3}],
        )

        poller._run_task_with_bounded_retry(task["task_id"], task)

        self.assertEqual(self.attempts, [], "an exhausted budget must not re-run the task")
        blocked = self._blocked_record(task["task_id"])
        self.assertEqual(blocked["blocker"]["category"], "execution_error")


class TestRetryRecordPersistence(_RetryHarness):
    """Attempt metadata must be written before the next attempt runs."""

    def test_attempt_is_persisted_on_the_running_record(self):
        task = _make_task()
        self._write_running(task)

        state = qs.record_execution_attempt(
            task["task_id"], 1, _blocked("execution_error"), True, "unit test"
        )

        self.assertEqual(state["attempts_used"], 1)
        self.assertEqual(state["next_action"], "retry")
        self.assertEqual(qs.read_retry_state(task["task_id"])["attempts_used"], 1)
        record = self._running_record(task["task_id"])
        self.assertEqual(len(record["execution_attempts"]), 1)
        self.assertEqual(record["execution_attempts"][0]["blocker_category"], "execution_error")

    def test_record_requires_a_running_task(self):
        with self.assertRaises(qs.QueueError):
            qs.record_execution_attempt("never-claimed", 1, _blocked("execution_error"), True)


class TestIsolationGuards(unittest.TestCase):
    """The live queue must not be reachable from this suite."""

    def test_live_queue_is_not_touched(self):
        self.assertFalse((LIVE_QUEUE_ROOT / ".poller.kill").exists())
        for name in ("pending", "running", "completed", "blocked"):
            directory = LIVE_QUEUE_ROOT / name
            if directory.exists():
                for path in directory.glob("agent-retry-unit*.json"):
                    self.fail(f"test artifact leaked into the live queue: {path}")


if __name__ == "__main__":
    unittest.main()
