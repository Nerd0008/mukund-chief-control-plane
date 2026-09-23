#!/usr/bin/env python3
"""Isolated tests for the Windows console (QuickEdit/Select) hardening.

Root cause reproduced from the live 2026-09-23 incident: a worker window titled
``Select Administrator: Hermes Remote Worker ...`` whose output had frozen past
the nominal 300s idle watchdog. In a classic Windows console, QuickEdit/Select
("mark") mode suspends the process on its next console write. The worker's
no-progress watchdog printed from the same thread, so it was suspended too.

Isolation contract
------------------
* No test touches a real console mode, a global/registry console preference, or
  another process's console: the console API is injected as a fake object, and
  the real api is only checked by source inspection.
* No test launches a real Hermes process (the "Hermes" child is a throwaway
  local python script) and no test waits on the production 300s/1200s bounds.
* The live queue (``remote-queue/``) is never read or written.
"""

import contextlib
import inspect
import io
import subprocess
import sys
import tempfile
import threading
import time as real_time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from remote_queue import visible_worker as vw

# Console input mode bits from wincon.h.
ENABLE_PROCESSED_INPUT = 0x0001
ENABLE_LINE_INPUT = 0x0002
ENABLE_ECHO_INPUT = 0x0004
ENABLE_INSERT_MODE = 0x0020

# A realistic default: quick-edit (and insert mode) enabled.
DEFAULT_MODE = (
    ENABLE_PROCESSED_INPUT
    | ENABLE_LINE_INPUT
    | ENABLE_ECHO_INPUT
    | ENABLE_INSERT_MODE
    | vw.ENABLE_EXTENDED_FLAGS
    | vw.ENABLE_QUICK_EDIT_MODE
)


class _FakeConsoleApi:
    """Stand-in for ``_Win32ConsoleApi`` that records every call."""

    def __init__(self, handle=0x1234, mode=DEFAULT_MODE, get_ok=True, set_ok=True):
        self.handle = handle
        self.mode = mode
        self.get_ok = get_ok
        self.set_ok = set_ok
        self.opened = 0
        self.get_calls = []
        self.set_calls = []
        self.closed = []

    def open_console_input(self):
        self.opened += 1
        return self.handle

    def get_console_mode(self, handle):
        self.get_calls.append(handle)
        if not self.get_ok:
            return None, 5
        return self.mode, 0

    def set_console_mode(self, handle, mode):
        self.set_calls.append((handle, mode))
        if not self.set_ok:
            return False, 87
        self.mode = mode
        return True, 0

    def close(self, handle):
        self.closed.append(handle)


class _NoSleepTime:
    """``time`` proxy that records sleeps instead of performing them."""

    def __init__(self):
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def monotonic(self):
        return real_time.monotonic()

    def __getattr__(self, name):
        return getattr(real_time, name)


class _SubprocessShim:
    def __init__(self, popen=None, run=None):
        self.Popen = popen or subprocess.Popen
        self.run = run or subprocess.run

    def __getattr__(self, name):
        return getattr(subprocess, name)


class TestQuickEditModeBits(unittest.TestCase):
    """The mode transformation must be exactly the documented one."""

    def test_quick_edit_bit_is_cleared_and_extended_flags_is_set(self):
        target = vw._quick_edit_disabled_mode(DEFAULT_MODE)

        self.assertEqual(target & vw.ENABLE_QUICK_EDIT_MODE, 0)
        self.assertEqual(target & vw.ENABLE_EXTENDED_FLAGS, vw.ENABLE_EXTENDED_FLAGS)
        # Unrelated input modes are preserved untouched.
        for bit in (ENABLE_PROCESSED_INPUT, ENABLE_LINE_INPUT, ENABLE_ECHO_INPUT,
                    ENABLE_INSERT_MODE):
            self.assertEqual(target & bit, bit)
        # The transform is idempotent and never disables anything else.
        self.assertEqual(vw._quick_edit_disabled_mode(target), target)


class TestQuickEditApplication(unittest.TestCase):
    """``disable_quick_edit_for_this_console`` scope and fail-closed behaviour."""

    def test_disables_quick_edit_on_this_console_only(self):
        api = _FakeConsoleApi()

        status = vw.disable_quick_edit_for_this_console(api)

        self.assertTrue(status["applied"])
        self.assertTrue(status["changed"])
        self.assertEqual(status["mode_before"], DEFAULT_MODE)
        self.assertFalse(status["quick_edit_after"])
        self.assertEqual(status["scope"], "this-process-console-only")
        # Exactly one write, to the handle this process opened, with the exact
        # target mode, and the handle is closed again (no leaked handle).
        self.assertEqual(len(api.set_calls), 1)
        handle, mode = api.set_calls[0]
        self.assertEqual(handle, api.handle)
        self.assertEqual(mode, vw._quick_edit_disabled_mode(DEFAULT_MODE))
        self.assertEqual(api.closed, [api.handle])

    def test_console_without_quick_edit_is_read_but_not_rewritten(self):
        already_clean = (DEFAULT_MODE | vw.ENABLE_EXTENDED_FLAGS) & ~vw.ENABLE_QUICK_EDIT_MODE
        api = _FakeConsoleApi(mode=already_clean)

        status = vw.disable_quick_edit_for_this_console(api)

        self.assertTrue(status["applied"])
        self.assertFalse(status["changed"])
        self.assertEqual(api.set_calls, [])
        self.assertFalse(status["quick_edit_before"])

    def test_no_console_attached_reports_the_limitation_without_changing_anything(self):
        api = _FakeConsoleApi(handle=0)

        status = vw.disable_quick_edit_for_this_console(api)

        self.assertFalse(status["applied"])
        self.assertEqual(status["reason"], "no-console-attached")
        self.assertEqual(api.set_calls, [])
        self.assertEqual(status["mode_after"], None)

    def test_read_failure_fails_closed(self):
        api = _FakeConsoleApi(get_ok=False)

        status = vw.disable_quick_edit_for_this_console(api)

        self.assertFalse(status["applied"])
        self.assertIn("GetConsoleMode-failed", status["reason"])
        self.assertEqual(api.set_calls, [])

    def test_write_failure_fails_closed_and_reports_the_win_error(self):
        api = _FakeConsoleApi(set_ok=False)

        status = vw.disable_quick_edit_for_this_console(api)

        self.assertFalse(status["applied"])
        self.assertIn("SetConsoleMode-failed", status["reason"])
        self.assertIn("87", status["reason"])

    def test_api_construction_failure_is_reported_not_raised(self):
        class Boom:
            def __init__(self):
                raise OSError("no windll")

        original = vw._Win32ConsoleApi
        vw._Win32ConsoleApi = Boom
        try:
            status = vw.disable_quick_edit_for_this_console()
        finally:
            vw._Win32ConsoleApi = original

        self.assertFalse(status["applied"])
        self.assertIn("console-api-unavailable", status["reason"])

    def test_real_api_is_scoped_to_this_process_console(self):
        source = inspect.getsource(vw)

        # The console input buffer is opened for this process only.
        self.assertIn('"CONIN$"', source)
        self.assertIn("SetConsoleMode", source)
        # Nothing may attach to, allocate, free or enumerate consoles, mutate a
        # global/registry console preference, or use a launcher-wide window API.
        for forbidden in ("AttachConsole", "AllocConsole", "FreeConsole",
                          "GetConsoleProcessList", "winreg", "reg add",
                          "HKEY_CURRENT_USER", "Console\\QuickEdit",
                          "taskkill\", \"/IM", "/IM"):
            self.assertNotIn(forbidden, source)
        # The real api only ever opens this process's own console handle.
        api_source = inspect.getsource(vw._Win32ConsoleApi)
        self.assertIn("open_console_input", api_source)
        self.assertNotIn("GetConsoleWindow", api_source)


class _WorkerCase(unittest.TestCase):
    """Harness that runs ``visible_worker.main()`` in-process."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hermes-console-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.temp_dir, ignore_errors=True))
        self.prompt_file = self.temp_dir / "prompt.txt"
        self.prompt_file.write_text("isolated console test prompt", encoding="utf-8")
        self.output_file = self.temp_dir / "output.txt"
        self.exit_file = self.temp_dir / "exit.txt"
        self._restore = []

    def tearDown(self):
        for obj, name, value in self._restore:
            setattr(obj, name, value)

    def _patch(self, obj, name, value):
        self._restore.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def _run_worker(self, chat_child_cmd, idle_timeout, task_id="test-console"):
        real_popen = subprocess.Popen
        spawned = {}

        def fake_popen(cmd, **kwargs):
            argv = list(cmd)
            if len(argv) > 1 and argv[1] == "chat":
                proc = real_popen(list(chat_child_cmd), **kwargs)
                spawned["proc"] = proc
                return proc
            return real_popen(argv, **kwargs)

        self._patch(vw, "subprocess", _SubprocessShim(popen=fake_popen))
        self._patch(vw, "time", _NoSleepTime())
        saved_argv = sys.argv
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
            sys.argv = saved_argv

        self.assertIn("proc", spawned, "the fake Hermes chat child was never launched")
        return rc, buffer.getvalue(), spawned["proc"]

    def _write_script(self, name, body):
        path = self.temp_dir / name
        path.write_text(body, encoding="utf-8")
        return path


QUICK_CHILD = (
    "import json, sys\n"
    "print(json.dumps({'type': 'tool_use', 'name': 'terminal'}), flush=True)\n"
    "print(json.dumps({'type': 'result', 'text': "
    "'{\"status\": \"completed\", \"summary\": \"fake\"}', "
    "'exit_code': 0, 'duration_ms': 5, 'tokens': {'total': 3}}), flush=True)\n"
)


class TestWorkerConsoleReporting(_WorkerCase):
    """The worker applies the hardening and reports its outcome truthfully."""

    def test_worker_applies_hardening_before_launching_hermes(self):
        api = _FakeConsoleApi()
        self._patch(vw, "_Win32ConsoleApi", lambda: api)
        child = self._write_script("quick_child.py", QUICK_CHILD)

        rc, output, _proc = self._run_worker([sys.executable, str(child)], idle_timeout=5)

        self.assertEqual(rc, 0)
        self.assertIn("Console QuickEdit hardening: applied", output)
        self.assertIn("quick_edit_after=False", output)
        self.assertFalse(api.mode & vw.ENABLE_QUICK_EDIT_MODE)

        # Applied before the first progress line and before the child launch.
        source = inspect.getsource(vw.main)
        self.assertLess(
            source.index("disable_quick_edit_for_this_console()"),
            source.index("subprocess.Popen("),
        )

    def test_worker_reports_the_exact_limitation_when_no_console_exists(self):
        api = _FakeConsoleApi(handle=0)
        self._patch(vw, "_Win32ConsoleApi", lambda: api)
        child = self._write_script("quick_child2.py", QUICK_CHILD)

        rc, output, _proc = self._run_worker([sys.executable, str(child)], idle_timeout=5)

        self.assertEqual(rc, 0, "a console limitation must not stop the worker")
        self.assertIn("Console QuickEdit hardening: UNAVAILABLE", output)
        self.assertIn("no-console-attached", output)
        self.assertIn("global console settings left unchanged", output)
        self.assertEqual(api.set_calls, [])


class TestConsoleStallCannotPauseTheWatchdog(_WorkerCase):
    """The headline regression: a select-mode console must not freeze the worker."""

    def test_watchdog_still_fires_and_records_124_while_console_writes_block(self):
        release = threading.Event()
        self.addCleanup(release.set)
        entered = threading.Event()

        def blocked_write(_text):
            entered.set()
            release.wait(30)

        self._patch(vw, "_console_write", blocked_write)
        self._patch(vw, "CONSOLE_DRAIN_TIMEOUT", 0.2)

        silent = self._write_script("silent_child.py", "import time\ntime.sleep(600)\n")

        started = real_time.monotonic()
        rc, _output, child = self._run_worker(
            [sys.executable, str(silent)], idle_timeout=2
        )
        elapsed = real_time.monotonic() - started

        # The console was genuinely stalled for the whole run...
        self.assertTrue(entered.wait(5), "the blocking console sink was never used")
        # ...yet the watchdog still failed the task closed.
        self.assertEqual(rc, 124)
        self.assertEqual(self.exit_file.read_text(encoding="utf-8").strip(), "124")
        self.assertEqual(self.output_file.read_text(encoding="utf-8"), "")
        self.assertIsNotNone(child.poll(), "the Hermes child survived a watchdog kill")
        # The worker itself must not have been suspended waiting on the console.
        self.assertLess(
            elapsed, 15,
            "a stalled console delayed the worker's exit path instead of only its console lines",
        )

    def test_console_writer_never_blocks_its_caller_and_counts_drops(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def blocked_write(_text):
            release.wait(30)

        writer = vw._ConsoleWriter(write=blocked_write, maxlen=2)

        started = real_time.monotonic()
        for index in range(50):
            writer.say(f"line {index}")
        elapsed = real_time.monotonic() - started

        self.assertLess(elapsed, 2, "say() blocked on a stalled console")
        drained = writer.flush(0.2)
        self.assertGreaterEqual(drained["dropped"], 1, "drops must be counted, not hidden")
        # A bounded drain must return even though the writer thread is stuck.
        self.assertGreater(drained["pending"], 0)


if __name__ == "__main__":
    unittest.main()
