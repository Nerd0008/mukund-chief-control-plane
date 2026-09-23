#!/usr/bin/env python3
"""Visible console wrapper for remotely-dispatched Hermes tasks.

The worker uses Hermes stream-json mode so Mukund can see real execution
progress (model/session, tool starts/completions, failures) in a dedicated
Windows console while the parent bridge still receives only the final response
text for strict JSON parsing. Raw tool output is not committed to Git.
"""

import argparse
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _safe_text(value, limit=220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--exit-file", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument(
        "--idle-timeout-seconds",
        type=int,
        default=int(os.environ.get("HERMES_REMOTE_IDLE_TIMEOUT", "300")),
        help="Fail closed if Hermes emits no stream event for this many seconds.",
    )
    args = parser.parse_args()

    task_id = args.task_id
    try:
        if os.name == "nt":
            os.system(f"title Hermes Remote Worker - {task_id}")
    except Exception:
        pass

    print("=" * 78, flush=True)
    print("HERMES REMOTE WORKER - LIVE EXECUTION", flush=True)
    print(f"Task: {task_id}", flush=True)
    print(f"Started: {datetime.now().isoformat(timespec='seconds')}", flush=True)
    print(f"Hermes executable: {args.hermes}", flush=True)
    print(f"Working directory: {args.cwd}", flush=True)
    print("Mode: stream-json (live tool activity; final response captured separately)", flush=True)
    print(f"Idle watchdog: {args.idle_timeout_seconds}s without a stream event", flush=True)
    print("=" * 78, flush=True)

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
            print(f"[{_stamp()}] Hermes version: {_safe_text(version_text)}", flush=True)
    except Exception as exc:
        print(f"[{_stamp()}] Hermes version check unavailable: {type(exc).__name__}", flush=True)

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
        print(msg, flush=True)
        output_path.write_text(msg, encoding="utf-8")
        exit_path.write_text("127", encoding="utf-8")
        print("Window remains open for 90 seconds for diagnosis.", flush=True)
        time.sleep(90)
        return 127

    reader_errors = []
    watchdog_fired = False
    active_tool = None

    def _terminate_child_tree() -> None:
        """Terminate only this worker's Hermes child/process tree."""
        if proc.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                )
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

    def reader():
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
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

    last_activity = time.monotonic()
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

            last_activity = time.monotonic()
            line = item.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Diagnostics remain local to the visible console.
                print(f"[{_stamp()}] CLI: {_safe_text(line, 500)}", flush=True)
                continue

            etype = event.get("type")

            if etype == "system":
                model = event.get("model") or "UNKNOWN"
                sid = event.get("session_id") or "UNKNOWN"
                print(f"[{_stamp()}] SESSION START  model={model}  session={sid}", flush=True)

            elif etype == "tool_use":
                name = event.get("name") or "unknown"
                active_tool = name
                print(f"[{_stamp()}] >>> TOOL START: {name}", flush=True)

            elif etype == "tool_result":
                name = event.get("name") or "unknown"
                active_tool = None
                duration = event.get("duration_ms")
                status = "ERROR" if event.get("is_error") else "OK"
                dur_text = f"  {duration}ms" if duration is not None else ""
                print(f"[{_stamp()}] <<< TOOL {status}: {name}{dur_text}", flush=True)

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
                print(
                    f"[{_stamp()}] RESULT  exit={result_exit_code}  "
                    f"duration_ms={duration}  tokens={tokens.get('total', 'UNKNOWN')}",
                    flush=True,
                )
                if err:
                    print(f"[{_stamp()}] RESULT ERROR: {_safe_text(err, 500)}", flush=True)

            else:
                print(f"[{_stamp()}] EVENT: {etype or 'unknown'}", flush=True)

        except queue.Empty:
            pass

        if finished_stream and proc.poll() is None and reader_errors:
            print(
                f"[{_stamp()}] STREAM READER FAILED: {_safe_text(reader_errors[-1], 500)}",
                flush=True,
            )
            print(f"[{_stamp()}] Terminating Hermes child to avoid an invisible hang.", flush=True)
            _terminate_child_tree()

        now = time.monotonic()
        quiet_for = int(now - last_activity)
        if (
            proc.poll() is None
            and args.idle_timeout_seconds > 0
            and quiet_for >= args.idle_timeout_seconds
        ):
            watchdog_fired = True
            tool_text = active_tool or "no active tool reported"
            print(
                f"[{_stamp()}] WATCHDOG TIMEOUT: no stream event for {quiet_for}s "
                f"(active={tool_text}).",
                flush=True,
            )
            print(
                f"[{_stamp()}] Terminating only this Hermes child tree so the queue can recover.",
                flush=True,
            )
            _terminate_child_tree()

        if proc.poll() is None and now - last_heartbeat >= 5:
            print(f"[{_stamp()}] Hermes is working... ({quiet_for}s since last event)", flush=True)
            last_heartbeat = now

        if proc.poll() is not None and finished_stream:
            break

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
            print(f"[{_stamp()}] CLI: {_safe_text(item, 500)}", flush=True)
            continue
        if event.get("type") == "result":
            saw_result = True
            final_text = event.get("text") or final_text
            result_exit_code = event.get("exit_code")
        elif event.get("type") == "text" and isinstance(event.get("text"), str):
            text_chunks.append(event["text"])

    rc = proc.wait()
    if watchdog_fired:
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

    print("", flush=True)
    print("=" * 78, flush=True)
    print(f"Status: {'COMPLETED' if rc == 0 else 'FAILED'}", flush=True)
    print(f"Exit code: {rc}", flush=True)
    print(f"Result event observed: {saw_result}", flush=True)
    print(f"Final response bytes: {len(final_text.encode('utf-8', errors='replace'))}", flush=True)
    print(f"Finished: {datetime.now().isoformat(timespec='seconds')}", flush=True)
    if rc == 0:
        print("Window will close in 15 seconds.", flush=True)
        hold = 15
    else:
        print("FAILED: window will remain open for 90 seconds so the error is visible.", flush=True)
        hold = 90
    print("=" * 78, flush=True)
    time.sleep(hold)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
