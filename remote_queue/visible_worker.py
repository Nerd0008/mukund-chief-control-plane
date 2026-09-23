#!/usr/bin/env python3
"""Visible console wrapper for a remotely-dispatched Hermes task.

Runs in its own Windows console, streams Hermes output when available, emits a
heartbeat during quiet periods, and writes the raw final output to a local temp
file for the parent dispatcher to parse. Nothing here is committed to Git.
"""

import argparse
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--exit-file", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--cwd", required=True)
    args = parser.parse_args()

    task_id = args.task_id
    try:
        if os.name == "nt":
            os.system(f"title Hermes Remote Worker - {task_id}")
    except Exception:
        pass

    print("=" * 72, flush=True)
    print("HERMES REMOTE WORKER", flush=True)
    print(f"Task: {task_id}", flush=True)
    print(f"Started: {datetime.now().isoformat(timespec='seconds')}", flush=True)
    print("Status: RUNNING", flush=True)
    print("This window is separate from your manual Hermes session.", flush=True)
    print("=" * 72, flush=True)

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    output_path = Path(args.output_file)
    exit_path = Path(args.exit_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    q: queue.Queue[str] = queue.Queue()

    try:
        proc = subprocess.Popen(
            [args.hermes, "-z", prompt],
            cwd=args.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
    except Exception as exc:
        msg = f"Failed to launch Hermes: {type(exc).__name__}: {exc}"
        print(msg, flush=True)
        output_path.write_text(msg, encoding="utf-8")
        exit_path.write_text("127", encoding="utf-8")
        time.sleep(5)
        return 127

    def reader():
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                q.put(line)
        finally:
            q.put("")

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    last_output = time.monotonic()
    last_heartbeat = time.monotonic()
    finished_stream = False

    with output_path.open("w", encoding="utf-8", errors="replace") as out:
        while proc.poll() is None or not finished_stream:
            try:
                item = q.get(timeout=1.0)
                if item == "":
                    finished_stream = True
                else:
                    print(item, end="", flush=True)
                    out.write(item)
                    out.flush()
                    last_output = time.monotonic()
            except queue.Empty:
                pass

            now = time.monotonic()
            if proc.poll() is None and now - last_heartbeat >= 5:
                quiet_for = int(now - last_output)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Hermes is working..."
                    f" ({quiet_for}s since last output)",
                    flush=True,
                )
                last_heartbeat = now

            if proc.poll() is not None and finished_stream:
                break

        # Drain anything queued at process exit.
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if item:
                print(item, end="", flush=True)
                out.write(item)

    rc = proc.wait()
    exit_path.write_text(str(rc), encoding="utf-8")

    print("", flush=True)
    print("=" * 72, flush=True)
    print(f"Status: {'COMPLETED' if rc == 0 else 'FAILED'}", flush=True)
    print(f"Exit code: {rc}", flush=True)
    print(f"Finished: {datetime.now().isoformat(timespec='seconds')}", flush=True)
    print("Window will close in 5 seconds.", flush=True)
    print("=" * 72, flush=True)
    time.sleep(5)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
