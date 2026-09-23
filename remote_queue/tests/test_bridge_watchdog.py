#!/usr/bin/env python3
"""Isolated tests for the hardened Hermes remote bridge.

Covers the 2026-09-23 bridge hardening commits:

* ``617fd47c`` visible worker no-stream-event watchdog
* ``b83c9ad`` dispatch hard/idle task bounds + frozen running contracts

Isolation contract
------------------
* Every test runs in a per-test temporary directory.
* No real Hermes process is ever launched. The "Hermes" child is either a
  throwaway ``python`` script started in a temp directory, or a fake process
  object that only writes the worker's output/exit files.
* The live queue (``remote-queue/``), kill switch, poller mutex and logs are
  never read or written by this module.
* No test waits for the production 300s/1200s bounds. The watchdog is exercised
  with a 2s test-only bound against a fake child, and the hard bound is checked
  by intercepting the single ``subprocess.run`` call dispatch makes.
"""

import inspect
import io
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time as real_time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from remote_queue import hermes_dispatch as hd
from remote_queue import visible_worker as vw

LIVE_QUEUE_ROOT = REPO_ROOT / "remote-queue"

RESPONSE = {"status": "completed", "summary": "fake bridge response"}


class _FakeProc:
    """Stand-in for the visible worker process launched by dispatch."""

    def __init__(self, returncode=0, pid=4242):
        self.returncode = returncode
        self.pid = pid

    def wait(self, timeout=None):
        return self.returncode


class _NoSleepTime:
    """Proxy for ``time`` that records sleeps instead of performing them.

    The visible worker intentionally holds a failed console open for 90s; the
    test must not. ``monotonic`` is delegated so the real watchdog clock runs.
    """

    def __init__(self):
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def monotonic(self):
        return real_time.monotonic()

    def __getattr__(self, name):
        return getattr(real_time, name)


class _SubprocessShim:
    """Local ``subprocess`` replacement scoped to one worker/dispatch module.

    The worker module is patched (``vw.subprocess``), not the global
    ``subprocess`` module, so nothing else in the test interpreter is affected.
    """

    def __init__(self, popen=None, run=None, completed=None):
        self.Popen = popen or subprocess.Popen
        self.run = run or subprocess.run
        self.completed = completed

    def __getattr__(self, name):
        return getattr(subprocess, name)


def _write_script(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


class _WorkerCase(unittest.TestCase):
    """Shared harness for running ``visible_worker.main()`` in-process."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hermes-bridge-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.temp_dir, ignore_errors=True))
        self.prompt_file = self.temp_dir / "prompt.txt"
        self.prompt_file.write_text("isolated bridge test prompt", encoding="utf-8")
        self.output_file = self.temp_dir / "output.txt"
        self.exit_file = self.temp_dir / "exit.txt"

    def _run_worker(self, chat_child_cmd, idle_timeout, task_id="test-bridge"):
        """Run the worker with a fake 'hermes' whose ``chat`` invocation is swapped."""
        real_popen = subprocess.Popen
        spawned = {}

        def fake_popen(cmd, **kwargs):
            argv = list(cmd)
            if len(argv) > 1 and argv[1] == "chat":
                proc = real_popen(list(chat_child_cmd), **kwargs)
                spawned["proc"] = proc
                return proc
            return real_popen(argv, **kwargs)

        fake_time = _NoSleepTime()
        original = {
            "subprocess": vw.subprocess,
            "time": vw.time,
            "argv": sys.argv,
        }
        vw.subprocess = _SubprocessShim(popen=fake_popen)
        vw.time = fake_time
        sys.argv = [
            "visible_worker.py",
            "--hermes", sys.executable,
            "--prompt-file", str(self.prompt_file),
            "--output-file", str(self.output_file),
            "--exit-file", str(self.exit_file),
            "--task-id", task_id,
            "--cwd", str(self.temp_dir),
            "--idle-timeout-seconds", str(idle_timeout),
        ]

        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                rc = vw.main()
        finally:
            vw.subprocess = original["subprocess"]
            vw.time = original["time"]
            sys.argv = original["argv"]

        self.assertIn("proc", spawned, "the fake Hermes chat child was never launched")
        return rc, buffer.getvalue(), spawned["proc"], fake_time


class TestVisibleWorkerWatchdog(_WorkerCase):
    """The no-stream-event watchdog must fail closed with exit code 124."""

    def test_silent_child_trips_watchdog_with_124_and_targeted_termination(self):
        sleeper = _write_script(
            self.temp_dir, "sleeper.py", "import time\ntime.sleep(600)\n"
        )

        rc, output, child, fake_time = self._run_worker(
            [sys.executable, str(sleeper)], idle_timeout=2
        )

        self.assertIn("WATCHDOG TIMEOUT", output)
        self.assertIn("Terminating only this Hermes child tree", output)
        # The watchdog bound is surfaced as a truthfully failed execution.
        self.assertEqual(rc, 124)
        self.assertEqual(self.exit_file.read_text(encoding="utf-8").strip(), "124")
        # No fabricated final response is written for a watchdog kill.
        self.assertEqual(self.output_file.read_text(encoding="utf-8"), "")
        # Status line must not claim completion.
        self.assertIn("Status: FAILED", output)
        # Only the worker's own child tree was terminated.
        self.assertIsNotNone(child.poll(), "the fake Hermes child was left running")

    def test_working_child_keeps_the_stream_alive_and_completes(self):
        chatter = _write_script(
            self.temp_dir,
            "chatter.py",
            "import json, sys, time\n"
            "for _ in range(8):\n"
            "    print(json.dumps({'type': 'tool_use', 'name': 'terminal'}), flush=True)\n"
            "    time.sleep(0.25)\n"
            "print(json.dumps({'type': 'result', 'text': "
            "'{\"status\": \"completed\", \"summary\": \"fake\"}', "
            "'exit_code': 0, 'duration_ms': 2000, 'tokens': {'total': 11}}), flush=True)\n",
        )

        rc, output, child, _ = self._run_worker(
            [sys.executable, str(chatter)], idle_timeout=3
        )

        self.assertNotIn("WATCHDOG TIMEOUT", output)
        self.assertEqual(rc, 0)
        self.assertEqual(self.exit_file.read_text(encoding="utf-8").strip(), "0")
        self.assertIn('"status": "completed"', self.output_file.read_text(encoding="utf-8"))
        self.assertIn("Status: COMPLETED", output)

    def test_watchdog_default_is_300_and_env_override_is_supported(self):
        source = inspect.getsource(vw)
        self.assertIn('os.environ.get("HERMES_REMOTE_IDLE_TIMEOUT", "300")', source)
        self.assertIn("args.idle_timeout_seconds > 0", source)
        self.assertIn("quiet_for >= args.idle_timeout_seconds", source)

    def test_a_non_positive_bound_disables_the_watchdog(self):
        """--idle-timeout-seconds 0 must disable, never invert, the watchdog."""
        slow_but_healthy = _write_script(
            self.temp_dir,
            "slow_healthy.py",
            "import json, time\n"
            "time.sleep(2)\n"
            "print(json.dumps({'type': 'result', 'text': "
            "'{\"status\": \"completed\"}', 'exit_code': 0}), flush=True)\n",
        )

        rc, output, _child, _ = self._run_worker(
            [sys.executable, str(slow_but_healthy)], idle_timeout=0
        )

        self.assertNotIn("WATCHDOG TIMEOUT", output)
        self.assertEqual(rc, 0)
        self.assertEqual(self.exit_file.read_text(encoding="utf-8").strip(), "0")

    def test_termination_is_scoped_to_the_child_pid_only(self):
        worker_source = inspect.getsource(vw)
        self.assertIn('["taskkill", "/PID", str(proc.pid), "/T", "/F"]', worker_source)
        self.assertNotIn('"/IM"', worker_source)
        self.assertNotIn("taskkill /IM", worker_source)


class _DispatchCase(unittest.TestCase):
    """Shared harness for dispatch-level bound checks."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hermes-dispatch-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.temp_dir, ignore_errors=True))
        self.original_subprocess = hd.subprocess
        self.saved_env = {
            key: os.environ.get(key)
            for key in ("HERMES_CLI", "HERMES_REMOTE_VISIBLE",
                        "HERMES_REMOTE_IDLE_TIMEOUT", "HERMES_REMOTE_TASK_TIMEOUT")
        }
        os.environ["HERMES_CLI"] = sys.executable

    def tearDown(self):
        hd.subprocess = self.original_subprocess
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @staticmethod
    def _task():
        return {
            "task_id": "unit-bridge-task",
            "objective": "unit",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "allowed_scope": ["nothing"],
            "stop_conditions": ["nothing"],
        }

    def _fake_visible_popen(self, exit_code, captured):
        def fake_popen(cmd, **kwargs):
            argv = list(cmd)
            captured.append(argv)
            out = Path(argv[argv.index("--output-file") + 1])
            ex = Path(argv[argv.index("--exit-file") + 1])
            out.write_text(
                "" if exit_code != 0 else json.dumps(RESPONSE), encoding="utf-8"
            )
            ex.write_text(str(exit_code), encoding="utf-8")
            return _FakeProc(returncode=0)

        hd.subprocess = _SubprocessShim(popen=fake_popen)


class TestDispatchBounds(_DispatchCase):
    """Hard task bound and idle bound must be bounded and env-configurable."""

    def test_watchdog_exit_code_124_is_execution_error_not_completion(self):
        captured = []
        self._fake_visible_popen(124, captured)

        result = hd.dispatch_task(self._task())

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocker_category"], "execution_error")
        self.assertIn("watchdog", result["summary"])
        self.assertIn("300", result["summary"])
        self.assertNotEqual(result["status"], "completed")

    def test_visible_worker_receives_the_idle_bound(self):
        os.environ.pop("HERMES_REMOTE_IDLE_TIMEOUT", None)
        captured = []
        self._fake_visible_popen(0, captured)
        result = hd.dispatch_task(self._task())
        self.assertEqual(result["status"], "completed")
        argv = captured[-1]
        self.assertEqual(argv[argv.index("--idle-timeout-seconds") + 1], "300")

        os.environ["HERMES_REMOTE_IDLE_TIMEOUT"] = "45"
        captured = []
        self._fake_visible_popen(0, captured)
        hd.dispatch_task(self._task())
        argv = captured[-1]
        self.assertEqual(argv[argv.index("--idle-timeout-seconds") + 1], "45")

    def test_hard_task_timeout_defaults_to_1200_and_is_configurable(self):
        os.environ["HERMES_REMOTE_VISIBLE"] = "0"
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps(RESPONSE), stderr=""
            )

        hd.subprocess = _SubprocessShim(run=fake_run)

        os.environ.pop("HERMES_REMOTE_TASK_TIMEOUT", None)
        self.assertEqual(hd.dispatch_task(self._task())["status"], "completed")
        self.assertEqual(seen["timeout"], 1200)

        os.environ["HERMES_REMOTE_TASK_TIMEOUT"] = "137"
        self.assertEqual(hd.dispatch_task(self._task())["status"], "completed")
        self.assertEqual(seen["timeout"], 137)

    def test_hard_timeout_expiry_blocks_with_execution_error(self):
        os.environ["HERMES_REMOTE_VISIBLE"] = "0"
        os.environ["HERMES_REMOTE_TASK_TIMEOUT"] = "9"

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

        hd.subprocess = _SubprocessShim(run=fake_run)

        result = hd.dispatch_task(self._task())

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocker_category"], "execution_error")
        self.assertIn("9 seconds", result["summary"])


class TestDispatchPromptContract(unittest.TestCase):
    """The generated prompt must freeze the running contract and honour approvals."""

    def setUp(self):
        self.prompt = hd._task_prompt(
            {
                "task_id": "agent-bridge-watchdog-validation-2026-09-23",
                "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
                "objective": "objective text",
                "allowed_scope": ["scope item"],
                "stop_conditions": ["stop item"],
                "notes": "notes text",
            }
        )

    def test_running_task_record_is_immutable_and_task_id_is_interpolated(self):
        self.assertIn(
            "Treat your own remote-queue/running/agent-bridge-watchdog-validation-2026-09-23.json"
            " as immutable execution input",
            self.prompt,
        )
        self.assertNotIn("{task.get(", self.prompt)

    def test_standing_conditional_approval_is_respected_not_reinvented(self):
        self.assertIn(
            "Respect unresolved owner approval gates. If the authority records a "
            "standing conditional approval, apply it only after its recorded "
            "objective conditions are verified.",
            self.prompt,
        )

    def test_final_response_contract_and_stop_conditions_present(self):
        self.assertIn("FINAL RESPONSE CONTRACT", self.prompt)
        self.assertIn("Return ONLY one JSON object", self.prompt)
        self.assertIn("stop item", self.prompt)
        self.assertIn("blocker_category", self.prompt)


if __name__ == "__main__":
    unittest.main()
