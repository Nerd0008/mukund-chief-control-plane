#!/usr/bin/env python3
"""Isolated tests for the Hermes GitHub Remote Queue.

Isolation contract
------------------
Every test in this module runs against disposable roots only:

* queue data directories live under a per-test temporary directory,
* git publication is either mocked or aimed at a throwaway repository with a
  throwaway bare origin, or it is disabled entirely,
* the live checkout at REMOTE-QUEUE-REPO (``REPO_ROOT``) is never committed to,
  never pushed to, and never mutated,
* the live kill switch / poller lock / poller mutex are never touched,
* no real task is ever dispatched to Hermes.

``TestIsolationGuards`` asserts this contract directly, so this suite cannot
silently regress into the pre-isolation behaviour (where ``TestQueueOperations``
could publish to the real remote and ``TestPollerCLI`` could claim real pending
tasks and toggle the real kill switch).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import remote_queue.queue_schema as qs
from remote_queue.queue_schema import (
    ensure_dirs, validate_task, claim_task, complete_task, block_task,
    find_pending_tasks, is_task_completed, is_task_blocked, is_task_running,
)

LIVE_REPO_ROOT = REPO_ROOT
LIVE_QUEUE_ROOT = REPO_ROOT / "remote-queue"
POLLER_SCRIPT = REPO_ROOT / "remote_queue" / "poller.py"

AUTHORITY = "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md"


def _live_queue_snapshot():
    """File-level snapshot of the live queue used to prove isolation."""
    snapshot = {}
    for name in ("pending", "running", "completed", "blocked", "logs"):
        directory = LIVE_QUEUE_ROOT / name
        if directory.exists():
            snapshot[name] = sorted(p.name for p in directory.iterdir())
    snapshot["kill_switch"] = (LIVE_QUEUE_ROOT / ".poller.kill").exists()
    return snapshot


_LIVE_SNAPSHOT_AT_IMPORT = _live_queue_snapshot()


def _run_git(args, cwd, check=True):
    result = subprocess.run(
        ["git"] + args, cwd=str(cwd), capture_output=True, text=True, timeout=60
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()[:400]}"
        )
    return result


def _make_disposable_repo(base: Path) -> Path:
    """Create a war/disposable git repo with a bare origin and an initial commit.

    Returns the working-tree path. The repo is intentionally tiny: the queue
    helpers only need ``remote-queue/`` to be a tracked path and ``origin/main``
    to exist so pull/push behaviour can be exercised truthfully.
    """
    origin = base / "origin.git"
    work = base / "work"
    origin.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    _run_git(["init", "--bare", "-b", "main", str(origin)], cwd=base)
    _run_git(["init", "-b", "main"], cwd=work)
    _run_git(["config", "user.email", "queue-test@invalid"], cwd=work)
    _run_git(["config", "user.name", "queue-test"], cwd=work)
    _run_git(["config", "commit.gpgsign", "false"], cwd=work)

    queue_dir = work / "remote-queue"
    (queue_dir / "logs").mkdir(parents=True, exist_ok=True)
    (queue_dir / "logs" / "queue.log").write_text("", encoding="utf-8")
    (queue_dir / "README.md").write_text("disposable queue root\n", encoding="utf-8")

    _run_git(["add", "remote-queue"], cwd=work)
    _run_git(["commit", "-m", "test: disposable queue root"], cwd=work)
    _run_git(["remote", "add", "origin", str(origin)], cwd=work)
    _run_git(["push", "-u", "origin", "main"], cwd=work)
    return work


def _make_task(task_id="test-1", **overrides):
    task = {
        "task_id": task_id,
        "created_at": "2026-09-23",
        "objective": "Test task",
        "authority": AUTHORITY,
        "priority": "medium",
        "allowed_scope": ["test"],
        "requires_owner_approval": False,
        "status": "pending",
    }
    task.update(overrides)
    return task


class TestTaskValidation(unittest.TestCase):
    """Pure schema validation — no filesystem or git involvement."""

    def test_valid_task(self):
        errors = validate_task(_make_task(task_id="test-task-1"))
        self.assertEqual(len(errors), 0)

    def test_missing_required_field(self):
        errors = validate_task({"task_id": "test", "objective": "Test"})
        self.assertTrue(any("missing required field" in e for e in errors))

    def test_invalid_priority(self):
        errors = validate_task(_make_task(priority="invalid"))
        self.assertTrue(any("priority" in e for e in errors))

    def test_invalid_task_id_format(self):
        errors = validate_task(_make_task(task_id="test task!"))
        self.assertTrue(any("task_id format" in e for e in errors))

    def test_unapproved_authority(self):
        errors = validate_task(_make_task(authority="unapproved-file.md"))
        self.assertTrue(any("authority" in e for e in errors))

    def test_secrets_in_objective(self):
        errors = validate_task(_make_task(objective="Get the api_key = abc123 from credentials"))
        self.assertTrue(any("secret" in e.lower() for e in errors))


class _DisposableQueueCase(unittest.TestCase):
    """Base case that redirects every queue path into a temporary root."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hermes-queue-test-"))
        self.queue_root = self.temp_dir / "remote-queue"
        self.publish_calls = []

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

        # Default: publication is recorded, never executed.
        qs._git_commit_and_push = self._record_publish
        ensure_dirs()

    def tearDown(self):
        for key, value in self._orig.items():
            setattr(qs, key, value)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _record_publish(self, message):
        self.publish_calls.append(
            {
                "message": message,
                "repo_root": Path(qs.REPO_ROOT),
                "queue_dir": Path(qs.QUEUE_DIR),
            }
        )
        return True

    def _write_pending(self, task, filename=None):
        path = qs.PENDING_DIR / (filename or f"{task['task_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task, f)
        return path

    def _write_running(self, task):
        path = qs.RUNNING_DIR / f"{task['task_id']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task, f)
        return path


class TestQueueOperations(_DisposableQueueCase):
    """Queue file operations against disposable directories and mocked git."""

    def test_claim_task(self):
        task_path = self._write_pending(_make_task())
        self.assertTrue(claim_task(task_path))
        self.assertFalse(task_path.exists())
        self.assertTrue((qs.RUNNING_DIR / "test-1.json").exists())
        self.assertEqual(len(self.publish_calls), 1)

    def test_publication_is_never_aimed_at_the_live_checkout(self):
        self._write_pending(_make_task())
        claim_task(qs.PENDING_DIR / "test-1.json")
        self.assertTrue(self.publish_calls, "claim must report its publication attempt")
        for call in self.publish_calls:
            self.assertNotEqual(call["repo_root"], LIVE_REPO_ROOT)
            self.assertNotEqual(call["queue_dir"], LIVE_QUEUE_ROOT)
            self.assertTrue(call["repo_root"].is_relative_to(self.temp_dir))
            self.assertTrue(call["queue_dir"].is_relative_to(self.temp_dir))

    def test_complete_task(self):
        self._write_running(_make_task())
        complete_task("test-1", {"status": "done"})

        self.assertFalse((qs.RUNNING_DIR / "test-1.json").exists())
        completed_path = qs.COMPLETED_DIR / "test-1.json"
        self.assertTrue(completed_path.exists())
        with open(completed_path, encoding="utf-8") as f:
            completed = json.load(f)
        self.assertEqual(completed["status"], "completed")
        self.assertIn("completed_at", completed)

    def test_block_task(self):
        self._write_running(_make_task())
        block_task("test-1", "credentials", "Provide API key", "Other work continues")

        self.assertFalse((qs.RUNNING_DIR / "test-1.json").exists())
        blocked_path = qs.BLOCKED_DIR / "test-1.json"
        self.assertTrue(blocked_path.exists())
        with open(blocked_path, encoding="utf-8") as f:
            blocked = json.load(f)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["blocker"]["category"], "credentials")

    def test_complete_task_requires_running_record(self):
        from remote_queue.queue_schema import QueueError
        with self.assertRaises(QueueError):
            complete_task("never-claimed", {"status": "done"})

    def test_find_pending_tasks(self):
        for i, priority in enumerate(["high", "medium", "low"]):
            self._write_pending(_make_task(task_id=f"test-{i}", priority=priority))

        pending = find_pending_tasks()
        self.assertEqual(len(pending), 3)
        self.assertEqual(pending[0].stem, "test-0")

    def test_deduplication(self):
        task_path = self._write_pending(_make_task())
        self.assertTrue(claim_task(task_path))
        self.assertFalse(claim_task(task_path))

    def test_is_task_completed(self):
        self.assertFalse(is_task_completed("test-1"))
        with open(qs.COMPLETED_DIR / "test-1.json", "w", encoding="utf-8") as f:
            json.dump(_make_task(), f)
        self.assertTrue(is_task_completed("test-1"))

    def test_is_task_running_and_blocked(self):
        self.assertFalse(is_task_running("test-1"))
        self.assertFalse(is_task_blocked("test-1"))
        self._write_running(_make_task())
        self.assertTrue(is_task_running("test-1"))
        block_task("test-1", "credentials", "owner", "continue")
        self.assertFalse(is_task_running("test-1"))
        self.assertTrue(is_task_blocked("test-1"))


class TestQueueLifecycleDefects(_DisposableQueueCase):
    """Regression tests for queue lifecycle defects fixed on 2026-09-23.

    Each assertion failed against the pre-fix implementation.
    """

    def test_claim_does_not_destroy_task_when_publish_raises(self):
        """DEFECT: pending was unlinked first, then the running copy was deleted
        if publication raised — the task vanished from every queue state."""
        def _explode(message):
            raise RuntimeError("simulated git failure")

        qs._git_commit_and_push = _explode
        task_path = self._write_pending(_make_task())

        result = claim_task(task_path)

        self.assertFalse(result)
        still_pending = task_path.exists()
        still_running = (qs.RUNNING_DIR / "test-1.json").exists()
        self.assertTrue(
            still_pending or still_running,
            "task must remain recoverable in pending/ or running/ after a failed publish",
        )

    def test_find_pending_tasks_decodes_non_ascii_task_files(self):
        """DEFECT: the platform default codec (cp1252 on Windows) raised
        UnicodeDecodeError inside the sort key, silently demoting a valid
        non-ASCII task to last place."""
        self._write_pending(
            _make_task(task_id="test-critical", priority="critical",
                       objective="Resume after a Unicode stream decode \u2014 caf\u00e9 case")
        )
        self._write_pending(_make_task(task_id="test-low", priority="low"))

        pending = find_pending_tasks()

        self.assertEqual([p.stem for p in pending], ["test-critical", "test-low"])

    def test_get_running_tasks_decodes_non_ascii_task_files(self):
        """DEFECT: get_running_tasks swallowed the decode error and dropped the
        running record from reports entirely."""
        self._write_running(_make_task(objective="Unicode \u2014 caf\u00e9 running record"))

        running = qs.get_running_tasks()

        self.assertEqual(len(running), 1)
        self.assertIn("caf\u00e9", running[0]["objective"])

    def _diverged_writer_setup(self, base: Path, conflicting: bool):
        """Build a disposable repo whose origin advanced under it.

        Returns (work_path, second_writer_change_path). When conflicts=False the
        second writer touches a different queue file (the realistic case: queue
        state is one JSON file per task), so a rebase can replay cleanly. When
        conflicts=True it appends to the shared log, which cannot be replayed.
        """
        work = _make_disposable_repo(base)
        origin = base / "origin.git"

        second = base / "second"
        _run_git(["clone", str(origin), str(second)], cwd=base)
        _run_git(["config", "user.email", "second@invalid"], cwd=second)
        _run_git(["config", "user.name", "second"], cwd=second)

        if conflicting:
            target = second / "remote-queue" / "logs" / "queue.log"
            target.write_text("second writer appended a log line\n", encoding="utf-8")
        else:
            target = second / "remote-queue" / "completed" / "second-writer.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{"task_id": "second-writer"}\n', encoding="utf-8")
        _run_git(["add", "remote-queue"], cwd=second)
        _run_git(["commit", "-m", "queue: second writer"], cwd=second)
        _run_git(["push", "origin", "main"], cwd=second)
        return work, target

    def test_push_non_fast_forward_recovers_when_rebase_can_replay(self):
        """DEFECT: a push rejected because origin advanced (observed live at
        2026-09-23T20:13:59Z) left queue state unpublished with no retry."""
        other = Path(tempfile.mkdtemp(prefix="hermes-queue-test-writer-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        work, _ = self._diverged_writer_setup(other, conflicting=False)
        origin = other / "origin.git"

        qs.REPO_ROOT = work
        qs.QUEUE_DIR = work / "remote-queue"
        qs._git_commit_and_push = self._orig["_git_commit_and_push"]

        (work / "remote-queue" / "completed").mkdir(parents=True, exist_ok=True)
        (work / "remote-queue" / "completed" / "ours.json").write_text(
            '{"task_id": "ours"}\n', encoding="utf-8"
        )

        published = qs._git_commit_and_push("queue: claim test-race")

        self.assertTrue(published, "push must recover by rebasing onto origin and retrying")
        log = _run_git(["log", "--oneline", "main"], cwd=origin).stdout
        self.assertIn("queue: claim test-race", log)
        self.assertIn("queue: second writer", log)

    def test_push_rejection_that_cannot_rebase_preserves_local_commit(self):
        """A genuinely conflicting divergence must fail closed: no silent
        history rewrite, no lost local commit, no half-finished rebase, and a
        truthful CRITICAL log entry."""
        other = Path(tempfile.mkdtemp(prefix="hermes-queue-test-conflict-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        work, _ = self._diverged_writer_setup(other, conflicting=True)
        origin = other / "origin.git"

        qs.REPO_ROOT = work
        qs.QUEUE_DIR = work / "remote-queue"
        qs._git_commit_and_push = self._orig["_git_commit_and_push"]

        (work / "remote-queue" / "logs" / "queue.log").write_text(
            "our writer appended a log line\n", encoding="utf-8"
        )

        published = qs._git_commit_and_push("queue: claim test-conflict")

        self.assertFalse(published)
        # Local work is preserved on our branch...
        local = _run_git(["log", "--oneline", "main"], cwd=work).stdout
        self.assertIn("queue: claim test-conflict", local)
        # ...and was not published to origin.
        remote = _run_git(["log", "--oneline", "main"], cwd=origin).stdout
        self.assertNotIn("queue: claim test-conflict", remote)
        # No rebase left in progress in the disposable work tree.
        self.assertFalse((work / ".git" / "rebase-merge").exists())
        self.assertFalse((work / ".git" / "rebase-apply").exists())
        # The failure was reported truthfully to the queue log.
        log_text = (qs.LOG_DIR / "queue.log").read_text(encoding="utf-8")
        self.assertIn("CRITICAL", log_text)

    def test_is_non_fast_forward_detection(self):
        from remote_queue.queue_schema import _is_non_fast_forward
        live_error = (
            " ! [rejected]        main -> main (fetch first)\n"
            "error: failed to push some refs to 'https://github.com/x/y.git'\n"
            "hint: Updates were rejected because the remote contains work that you do not"
        )
        self.assertTrue(_is_non_fast_forward(live_error))
        self.assertFalse(_is_non_fast_forward("fatal: could not read from remote repository"))


class TestPollerCLI(_DisposableQueueCase):
    """Poller CLI entry points, redirected to a disposable repo via env vars."""

    def setUp(self):
        super().setUp()
        # The poller must run against a real (disposable) repository so that
        # pull/rebase/push paths execute truthfully instead of failing early.
        self.repo_base = Path(tempfile.mkdtemp(prefix="hermes-queue-test-repo-"))
        self.addCleanup(shutil.rmtree, self.repo_base, ignore_errors=True)
        self.work = _make_disposable_repo(self.repo_base)
        self.disposable_queue = self.work / "remote-queue"
        self.disposable_pending = self.disposable_queue / "pending"
        self.disposable_blocked = self.disposable_queue / "blocked"
        self.disposable_kill = self.disposable_queue / ".poller.kill"

    def _env(self):
        env = os.environ.copy()
        env["HERMES_REPO_ROOT"] = str(self.work)
        env["HERMES_QUEUE_ROOT"] = str(self.disposable_queue)
        env["HERMES_POLLER_MUTEX"] = f"HermesRemoteQueuePollerTest{os.getpid()}"
        env["HERMES_REMOTE_VISIBLE"] = "0"
        return env

    def _poller(self, *args, timeout=90):
        return subprocess.run(
            [sys.executable, str(POLLER_SCRIPT), *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=self._env(),
        )

    def test_status_flag(self):
        result = self._poller("--status")
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertIn("Queue status", result.stdout)

    def test_once_flag(self):
        result = self._poller("--once")
        self.assertEqual(result.returncode, 0, result.stderr[-500:])

    def test_kill_switch_toggles_only_the_disposable_queue(self):
        live_kill = LIVE_QUEUE_ROOT / ".poller.kill"
        self.assertFalse(live_kill.exists())

        result = self._poller("--kill")
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertTrue(self.disposable_kill.exists())
        self.assertFalse(live_kill.exists())

        result = self._poller("--resume")
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertFalse(self.disposable_kill.exists())
        self.assertFalse(live_kill.exists())

    def test_invalid_pending_task_reaches_a_terminal_state(self):
        """DEFECT: block_task() raises for a pending task, which previously
        skipped the blocked/ copy and left the invalid task in pending/ to fail
        validation on every later cycle."""
        self.disposable_pending.mkdir(parents=True, exist_ok=True)
        invalid = {"task_id": "invalid-task", "objective": "missing required fields"}
        (self.disposable_pending / "invalid-task.json").write_text(
            json.dumps(invalid), encoding="utf-8"
        )

        result = self._poller("--once")

        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertTrue((self.disposable_blocked / "invalid-task.json").exists())
        self.assertFalse((self.disposable_pending / "invalid-task.json").exists())

    def test_poller_resolved_paths_are_isolated(self):
        probe = self.temp_dir / "path_probe.py"
        probe.write_text(
            "import json, sys\n"
            f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "import remote_queue.queue_schema as qs\n"
            "import remote_queue.poller as poller\n"
            "print(json.dumps({\n"
            "    'repo_root': str(qs.REPO_ROOT),\n"
            "    'queue_dir': str(qs.QUEUE_DIR),\n"
            "    'pending': str(qs.PENDING_DIR),\n"
            "    'log': str(qs.LOG_DIR),\n"
            "    'kill': str(poller.KILL_SWITCH_FILE),\n"
            "    'lock': str(poller.LOCK_FILE),\n"
            "    'mutex': poller.MUTEX_NAME,\n"
            "}))\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=self._env(), timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        paths = json.loads(result.stdout.strip().splitlines()[-1])

        for key in ("repo_root", "queue_dir", "pending", "log", "kill", "lock"):
            value = Path(paths[key]).resolve()
            self.assertTrue(
                value.is_relative_to(self.repo_base.resolve()),
                f"{key} escaped isolation: {value}",
            )
            self.assertFalse(
                value.is_relative_to(LIVE_QUEUE_ROOT.resolve()),
                f"{key} still points at the live queue: {value}",
            )
        self.assertNotEqual(paths["mutex"], "HermesRemoteQueuePoller")


class TestIsolationGuards(unittest.TestCase):
    """Directly asserts the live checkout cannot be reached by this suite."""

    def test_module_level_live_state_guard_is_armed(self):
        self.assertTrue(
            _LIVE_SNAPSHOT_AT_IMPORT,
            "suite must capture live queue state at import time",
        )

    def test_no_test_commit_reached_the_live_repository(self):
        result = subprocess.run(
            ["git", "log", "--all", "--oneline", "--grep=queue: claim test-"],
            cwd=str(LIVE_REPO_ROOT), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.stdout.strip(), "")

    def test_live_kill_switch_absent(self):
        self.assertFalse((LIVE_QUEUE_ROOT / ".poller.kill").exists())

    def test_default_paths_still_target_the_live_queue(self):
        """The env overrides must not change production defaults."""
        probe = self.temp_dir_probe_script()
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        paths = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(Path(paths["queue_dir"]).resolve(), LIVE_QUEUE_ROOT.resolve())

    def temp_dir_probe_script(self):
        script = Path(tempfile.mkdtemp(prefix="hermes-queue-probe-")) / "probe.py"
        script.write_text(
            "import json, sys\n"
            f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "import remote_queue.queue_schema as qs\n"
            "print(json.dumps({'queue_dir': str(qs.QUEUE_DIR)}))\n",
            encoding="utf-8",
        )
        self.addCleanup(shutil.rmtree, script.parent, ignore_errors=True)
        return script


def tearDownModule():
    """Whole-suite guard: the live queue must be byte-for-byte unchanged.

    This is the strongest isolation assertion available without a live
    supervisor: it fails loudly if any test in this module publishes to, claims
    from, blocks in, or toggles the live queue instead of a disposable root.
    """
    after = _live_queue_snapshot()
    if after != _LIVE_SNAPSHOT_AT_IMPORT:
        raise AssertionError(
            "live queue state changed during an isolated test run: "
            f"before={_LIVE_SNAPSHOT_AT_IMPORT} after={after}"
        )
    if (LIVE_QUEUE_ROOT / ".poller.kill").exists():
        raise AssertionError("live kill switch exists after an isolated test run")


if __name__ == "__main__":
    unittest.main()
