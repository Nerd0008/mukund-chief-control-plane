#!/usr/bin/env python3
"""Visible console wrapper for remotely-dispatched Hermes tasks.

The worker uses Hermes stream-json mode so Mukund can see real execution
progress (model/session, tool starts/completions, failures) in a dedicated
Windows console while the parent bridge still receives only the final response
text for strict JSON parsing. Raw tool output is not committed to Git.

Windows console hardening (2026-09-24)
--------------------------------------
Observed live on 2026-09-23: a worker window titled
``Select Administrator: Hermes Remote Worker ...`` whose output had frozen past
the nominal 300s idle watchdog, while the dispatched task had already landed its
commit. ``Select``/``Administrator:`` is the classic console mark/QuickEdit
title prefix: once a stray mouse click or drag puts a classic console into
select (mark) mode, the next write to that console suspends the process until
the user presses a key -- and because the no-progress watchdog printed from the
same thread, the watchdog itself was suspended too.

Two contained fixes, both scoped to this worker:

1. ``ENABLE_QUICK_EDIT_MODE`` is cleared for **this process's own console
   only**, via ``SetConsoleMode`` on a console input handle this process opens
   itself (``CONIN$``). No global/registry console preference and no other
   process's console is touched, the window stays visible, and when the mode
   cannot be changed the exact limitation is reported and left as-is.
2. Console output is serialised through a bounded writer thread that can never
   block the control loop, and the no-progress watchdog runs in its own thread
   and terminates the Hermes child *before* it announces anything. A jammed
   console therefore can no longer stall the worker's control path, its exit
   bookkeeping, or its watchdog.
"""

import argparse
import ctypes
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

# Console input modes (wincon.h). ENABLE_EXTENDED_FLAGS must be set for the
# quick-edit bit to be honoured.
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080

# Windows CreateFile access/share/disposition constants for opening CONIN$.
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3

# Bounded console-output buffering: the writer thread may block on a jammed
# console, so the queue is capped and further lines are dropped and counted
# rather than being allowed to stall execution.
CONSOLE_WRITE_QUEUE_MAX = int(os.environ.get("HERMES_REMOTE_CONSOLE_QUEUE_MAX", "512"))
CONSOLE_DRAIN_TIMEOUT = float(os.environ.get("HERMES_REMOTE_CONSOLE_DRAIN_TIMEOUT", "10"))


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _safe_text(value, limit=220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


# --------------------------------------------------------------------------
# Per-console QuickEdit hardening
# --------------------------------------------------------------------------


class _Win32ConsoleApi:
    """Minimal Win32 console API surface for THIS process's own console.

    The console input buffer is opened directly through ``CONIN$`` so the mode
    change is applied to the console this process is attached to, regardless of
    what standard handles were inherited from the launcher. Nothing here
    enumerates, attaches to, or mutates another process's console, and no
    global/registry console preference is read or written.
    """

    def __init__(self):
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ]
        kernel32.GetConsoleMode.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
        ]
        kernel32.GetConsoleMode.restype = ctypes.c_int
        kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.SetConsoleMode.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        self._kernel32 = kernel32
        self._invalid = ctypes.c_void_p(-1).value

    def open_console_input(self) -> int:
        handle = self._kernel32.CreateFileW(
            "CONIN$",
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if not handle or handle == self._invalid:
            return 0
        return int(handle)

    def get_console_mode(self, handle: int):
        mode = ctypes.c_uint32()
        if not self._kernel32.GetConsoleMode(
            ctypes.c_void_p(handle), ctypes.byref(mode)
        ):
            return None, int(self._kernel32.GetLastError())
        return int(mode.value), 0

    def set_console_mode(self, handle: int, mode: int):
        if not self._kernel32.SetConsoleMode(
            ctypes.c_void_p(handle), ctypes.c_uint32(mode)
        ):
            return False, int(self._kernel32.GetLastError())
        return True, 0

    def close(self, handle: int) -> None:
        try:
            self._kernel32.CloseHandle(ctypes.c_void_p(handle))
        except Exception:
            pass


def _quick_edit_disabled_mode(mode: int) -> int:
    """Return a console input mode with QuickEdit/Select mode disabled.

    Standard Windows rules: ``ENABLE_EXTENDED_FLAGS`` must be present for the
    console to honour the absence of ``ENABLE_QUICK_EDIT_MODE``.
    """
    return (int(mode) | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE


def disable_quick_edit_for_this_console(api=None) -> dict:
    """Disable QuickEdit/Select mode for this worker's own console only.

    Returns a truthful result record. ``applied`` is True only when the console
    input mode was read and (when needed) written successfully. On any failure
    the exact limitation is returned in ``reason`` and nothing else is changed:
    global console settings are never touched.
    """
    result = {
        "applied": False,
        "changed": False,
        "reason": "not-attempted",
        "mode_before": None,
        "mode_after": None,
        "quick_edit_before": None,
        "quick_edit_after": None,
        "scope": "this-process-console-only",
    }

    if api is None:
        if os.name != "nt":
            result["reason"] = "not-windows"
            return result
        try:
            api = _Win32ConsoleApi()
        except Exception as exc:
            result["reason"] = f"console-api-unavailable:{type(exc).__name__}"
            return result

    try:
        handle = api.open_console_input()
    except Exception as exc:
        result["reason"] = f"console-open-failed:{type(exc).__name__}"
        return result

    if not handle:
        result["reason"] = "no-console-attached"
        return result

    try:
        mode, err = api.get_console_mode(handle)
        if mode is None:
            result["reason"] = f"GetConsoleMode-failed:win_error={err}"
            return result

        result["mode_before"] = mode
        result["quick_edit_before"] = bool(mode & ENABLE_QUICK_EDIT_MODE)

        target = _quick_edit_disabled_mode(mode)
        if target != mode:
            ok, err = api.set_console_mode(handle, target)
            if not ok:
                result["reason"] = f"SetConsoleMode-failed:win_error={err}"
                return result
            result["changed"] = True

        verify, verify_err = api.get_console_mode(handle)
        final = mode if verify is None else verify
        result["mode_after"] = final
        result["quick_edit_after"] = bool(final & ENABLE_QUICK_EDIT_MODE)
        result["applied"] = True
        result["reason"] = "ok" if verify is not None else f"applied-unverified:win_error={verify_err}"
        return result
    except Exception as exc:
        result["reason"] = f"console-mode-error:{type(exc).__name__}"
        return result
    finally:
        try:
            api.close(handle)
        except Exception:
            pass


# --------------------------------------------------------------------------
# Non-blocking console output
# --------------------------------------------------------------------------


def _console_write(text: str) -> None:
    """Default console sink: one flushed line. Replaceable for tests."""
    print(text, flush=True)


class _ConsoleWriter:
    """Serialise console output through a bounded queue.

    Only this writer thread can block on a console write. The control loop, the
    stream reader and the watchdog keep running, and once the bounded queue is
    full further lines are dropped and counted instead of stalling execution.
    """

    def __init__(self, write=None, maxlen=CONSOLE_WRITE_QUEUE_MAX):
        self._write = write or _console_write
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=maxlen)
        self._dropped = 0
        self._write_errors = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name="console-writer", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            try:
                self._write(item)
            except Exception:
                with self._lock:
                    self._write_errors += 1
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass

    def say(self, text: str) -> None:
        """Enqueue one line. Never blocks and never raises."""
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            with self._lock:
                self._dropped += 1
        except Exception:
            pass

    def flush(self, timeout: float) -> dict:
        """Wait (bounded) for queued lines to be written. Never blocks forever."""
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if not self._queue.unfinished_tasks:
                break
            time.sleep(0.05)
        with self._lock:
            return {
                "pending": self._queue.unfinished_tasks,
                "dropped": self._dropped,
                "write_errors": self._write_errors,
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--exit-file", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument(
        "--attempt",
        type=int,
        default=1,
        help="1-based execution attempt number (bounded retry metadata).",
    )
    parser.add_argument(
        "--idle-timeout-seconds",
        type=int,
        default=int(os.environ.get("HERMES_REMOTE_IDLE_TIMEOUT", "300")),
        help="Fail closed if Hermes emits no stream event for this many seconds.",
    )
    args = parser.parse_args()

    task_id = args.task_id

    # Harden this console before the first progress line: a select/mark click
    # must not be able to freeze the worker from its first write onwards.
    console_status = disable_quick_edit_for_this_console()

    writer = _ConsoleWriter()
    say = writer.say

    try:
        if os.name == "nt":
            os.system(f"title Hermes Remote Worker - {task_id}")
    except Exception:
        pass

    say("=" * 78)
    say("HERMES REMOTE WORKER - LIVE EXECUTION")
    say(f"Task: {task_id}")
    say(f"Attempt: {args.attempt}")
    say(f"Started: {datetime.now().isoformat(timespec='seconds')}")
    say(f"Hermes executable: {args.hermes}")
    say(f"Working directory: {args.cwd}")
    say("Mode: stream-json (live tool activity; final response captured separately)")
    say(f"Idle watchdog: {args.idle_timeout_seconds}s without a stream event")
    if console_status["applied"]:
        say(
            "Console QuickEdit hardening: applied to this worker console only "
            f"(mode {console_status['mode_before']} -> {console_status['mode_after']}, "
            f"quick_edit_after={console_status['quick_edit_after']}, {console_status['reason']})"
        )
    else:
        say(
            "Console QuickEdit hardening: UNAVAILABLE "
            f"({console_status['reason']}); global console settings left unchanged "
            "and the worker window stays visible."
        )
    say("=" * 78)

    # Show installed Hermes version without mutating state.
    try:
        version_env = os.environ.copy()
        version_env["PYTHONUTF8"] = "1"
        version_env["PYTHONIOENCODING"] = "utf-8"
        version = subprocess.run(
            [args.hermes, "--version"],
            cwd=args.cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=version_env,
        )
        version_text = (version.stdout or version.stderr or "").strip()
        if version_text:
            say(f"[{_stamp()}] Hermes version: {_safe_text(version_text)}")
    except Exception as exc:
        say(f"[{_stamp()}] Hermes version check unavailable: {type(exc).__name__}")

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    output_path = Path(args.output_file)
    exit_path = Path(args.exit_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    q: queue.Queue[str] = queue.Queue()

    # stream-json is intentionally used instead of -z.  -z suppresses tool
    # previews and makes a healthy long-running task look idle to the owner.
    command = [args.hermes, "chat", "-q", prompt, "--format", "stream-json"]

    try:
        child_env = os.environ.copy()
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen(
            command,
            cwd=args.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=child_env,
        )
    except Exception as exc:
        msg = f"Failed to launch Hermes: {type(exc).__name__}: {exc}"
        say(msg)
        output_path.write_text(msg, encoding="utf-8")
        exit_path.write_text("127", encoding="utf-8")
        say("Window remains open for 90 seconds for diagnosis.")
        writer.flush(CONSOLE_DRAIN_TIMEOUT)
        time.sleep(90)
        return 127

    reader_errors = []
    active_tool = None

    # Shared, lock-guarded runtime state. The reader records stream activity, so
    # the watchdog measures stream silence rather than how quickly the (possibly
    # stalled) console consumer happens to keep up.
    runtime = {"last_activity": time.monotonic(), "watchdog_fired": False}
    fire_lock = threading.Lock()

    def note_activity() -> None:
        runtime["last_activity"] = time.monotonic()

    def _terminate_child_tree() -> None:
        """Terminate only this worker's Hermes child/process tree."""
        if proc.poll() is not None:
            return
        if os.name == "nt":
            try:
                taskkill = subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                )
                # ``taskkill`` can return nonzero (for example when the
                # process has exited between poll and termination, or when a
                # constrained console cannot terminate its child).  Only a
                # confirmed zero result may suppress the direct-process
                # fallback below; returning on any result leaks the child and
                # defeats the watchdog.
                if taskkill.returncode == 0:
                    return
            except Exception:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def fire_watchdog(quiet_for: int) -> None:
        """Fail closed once per run. Terminates the child BEFORE announcing."""
        with fire_lock:
            if runtime["watchdog_fired"]:
                return
            runtime["watchdog_fired"] = True
        tool_text = active_tool or "no active tool reported"
        # Kill first: the announcement below is a console write and could itself
        # be blocked by a jammed console, and the child must not survive that.
        _terminate_child_tree()
        say(
            f"[{_stamp()}] WATCHDOG TIMEOUT: no stream event for {quiet_for}s "
            f"(active={tool_text})."
        )
        say(
            f"[{_stamp()}] Terminating only this Hermes child tree so the queue can recover."
        )

    def reader():
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                note_activity()
                q.put(line)
        except Exception as exc:
            # Never let an output-decoding/pipe problem silently strand the
            # parent in a heartbeat loop. UTF-8 + errors=replace above should
            # handle malformed bytes; this is a final fail-closed guard.
            reader_errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            q.put("")

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    # Independent watchdog thread: this is what keeps the no-progress bound
    # fail-closed when console writes are suspended (classic QuickEdit/Select
    # mode, a wedged terminal, a hidden window). The in-loop check below is
    # retained as a second, fail-closed backstop.
    watchdog_stop = threading.Event()

    def watchdog_loop() -> None:
        if args.idle_timeout_seconds <= 0:
            interval = 0.5
        else:
            interval = max(0.25, min(1.0, args.idle_timeout_seconds / 4.0))
        while not watchdog_stop.wait(interval):
            if proc.poll() is not None:
                return
            if args.idle_timeout_seconds <= 0:
                continue
            quiet = int(time.monotonic() - runtime["last_activity"])
            if quiet >= args.idle_timeout_seconds:
                fire_watchdog(quiet)
                return

    watchdog_thread = threading.Thread(
        target=watchdog_loop, name="idle-watchdog", daemon=True
    )
    watchdog_thread.start()

    last_heartbeat = time.monotonic()
    finished_stream = False
    final_text = ""
    text_chunks = []
    result_exit_code = None
    saw_result = False

    while proc.poll() is None or not finished_stream:
        try:
            item = q.get(timeout=1.0)
            if item == "":
                finished_stream = True
                continue

            note_activity()
            line = item.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Diagnostics remain local to the visible console.
                say(f"[{_stamp()}] CLI: {_safe_text(line, 500)}")
                continue

            etype = event.get("type")

            if etype == "system":
                model = event.get("model") or "UNKNOWN"
                sid = event.get("session_id") or "UNKNOWN"
                say(f"[{_stamp()}] SESSION START  model={model}  session={sid}")

            elif etype == "tool_use":
                name = event.get("name") or "unknown"
                active_tool = name
                say(f"[{_stamp()}] >>> TOOL START: {name}")

            elif etype == "tool_result":
                name = event.get("name") or "unknown"
                active_tool = None
                duration = event.get("duration_ms")
                status = "ERROR" if event.get("is_error") else "OK"
                dur_text = f"  {duration}ms" if duration is not None else ""
                say(f"[{_stamp()}] <<< TOOL {status}: {name}{dur_text}")

            elif etype == "text":
                # Do not stream arbitrary model prose; tool activity is enough
                # for live observability and avoids accidental sensitive text.
                chunk = event.get("text")
                if isinstance(chunk, str):
                    text_chunks.append(chunk)

            elif etype == "result":
                saw_result = True
                final_text = event.get("text") or ""
                result_exit_code = event.get("exit_code")
                duration = event.get("duration_ms")
                tokens = event.get("tokens") or {}
                err = event.get("error")
                say(
                    f"[{_stamp()}] RESULT  exit={result_exit_code}  "
                    f"duration_ms={duration}  tokens={tokens.get('total', 'UNKNOWN')}"
                )
                if err:
                    say(f"[{_stamp()}] RESULT ERROR: {_safe_text(err, 500)}")

            else:
                say(f"[{_stamp()}] EVENT: {etype or 'unknown'}")

        except queue.Empty:
            pass

        if finished_stream and proc.poll() is None and reader_errors:
            say(
                f"[{_stamp()}] STREAM READER FAILED: {_safe_text(reader_errors[-1], 500)}"
            )
            say(f"[{_stamp()}] Terminating Hermes child to avoid an invisible hang.")
            _terminate_child_tree()

        now = time.monotonic()
        quiet_for = int(now - runtime["last_activity"])
        # Fail-closed backstop in case the watchdog thread never ran.
        if (
            proc.poll() is None
            and args.idle_timeout_seconds > 0
            and quiet_for >= args.idle_timeout_seconds
        ):
            fire_watchdog(quiet_for)

        if proc.poll() is None and now - last_heartbeat >= 5:
            say(f"[{_stamp()}] Hermes is working... ({quiet_for}s since last event)")
            last_heartbeat = now

        if proc.poll() is not None and finished_stream:
            break

    watchdog_stop.set()

    # Drain any final queued events.
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        if not item.strip():
            continue
        try:
            event = json.loads(item)
        except Exception:
            say(f"[{_stamp()}] CLI: {_safe_text(item, 500)}")
            continue
        if event.get("type") == "result":
            saw_result = True
            final_text = event.get("text") or final_text
            result_exit_code = event.get("exit_code")
        elif event.get("type") == "text" and isinstance(event.get("text"), str):
            text_chunks.append(event["text"])

    rc = proc.wait()
    if runtime["watchdog_fired"]:
        rc = 124
    elif result_exit_code is not None:
        try:
            rc = int(result_exit_code)
        except Exception:
            pass

    # Some Hermes versions may omit result.text but emit text deltas.
    if not final_text and text_chunks:
        final_text = "".join(text_chunks)

    output_path.write_text(final_text, encoding="utf-8", errors="replace")
    exit_path.write_text(str(rc), encoding="utf-8")

    say("")
    say("=" * 78)
    say(f"Status: {'COMPLETED' if rc == 0 else 'FAILED'}")
    say(f"Exit code: {rc}")
    say(f"Result event observed: {saw_result}")
    say(f"Final response bytes: {len(final_text.encode('utf-8', errors='replace'))}")
    say(f"Finished: {datetime.now().isoformat(timespec='seconds')}")
    if rc == 0:
        say("Window will close in 15 seconds.")
        hold = 15
    else:
        say("FAILED: window will remain open for 90 seconds so the error is visible.")
        hold = 90
    say("=" * 78)

    drained = writer.flush(CONSOLE_DRAIN_TIMEOUT)
    if drained["dropped"] or drained["write_errors"] or drained["pending"]:
        # Truthful console telemetry; never allowed to block the exit path.
        writer.say(
            f"[{_stamp()}] CONSOLE OUTPUT NOTE: dropped={drained['dropped']} "
            f"write_errors={drained['write_errors']} undrained={drained['pending']} "
            "(a jammed console only ever costs console lines, never progress)."
        )
        writer.flush(min(2.0, CONSOLE_DRAIN_TIMEOUT))

    time.sleep(hold)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
