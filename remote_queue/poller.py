#!/usr/bin/env python3
"""Hermes GitHub Remote Queue — poller with single-instance lock and git sync."""

import datetime
import json
import os
import sys
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from remote_queue.queue_schema import (
    ensure_dirs, find_pending_tasks, claim_task, load_task_file,
    validate_task, complete_task, block_task, log_event,
    is_task_running, is_task_completed, is_task_blocked,
    PENDING_DIR, RUNNING_DIR, COMPLETED_DIR, BLOCKED_DIR,
)

LOCK_FILE = REPO_ROOT / "remote_queue" / ".poller.lock"
KILL_SWITCH_FILE = REPO_ROOT / "remote_queue" / ".poller.kill"


def acquire_lock() -> bool:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, "HermesRemoteQueuePoller")
        if mutex == 0:
            return False
        return kernel32.GetLastError() == 0
    except Exception:
        try:
            if LOCK_FILE.exists():
                try:
                    pid = int(LOCK_FILE.read_text().strip())
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(1, False, pid)
                    if handle:
                        kernel32.CloseHandle(handle)
                        return False
                except (ValueError, OSError):
                    pass
                LOCK_FILE.unlink()
            LOCK_FILE.write_text(str(os.getpid()))
            return True
        except Exception:
            return False


def release_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def check_kill_switch() -> bool:
    return KILL_SWITCH_FILE.exists()


def git_pull() -> bool:
    import subprocess
    try:
        result = subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            log_event("git pull: success")
            return True
        else:
            log_event(f"git pull failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        log_event(f"git pull error: {e}")
        return False


def handle_task(task: dict) -> dict:
    task_id = task["task_id"]
    log_event(f"Handling task: {task_id}")

    if "full-operational-build" in task_id or "operational" in task_id.lower():
        return handle_operational_build(task)

    raise ValueError(f"No handler for task: {task_id}")


def handle_operational_build(task: dict) -> dict:
    result = {
        "status": "in_progress",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "summary": "E3 adapter infrastructure complete. 2/10 workers routable (DeepSeek, Gemini). 7 workers awaiting API keys.",
        "completed_steps": [
            "E3 Stage 1 framework",
            "DeepSeek adapter (smoke PASS, routable)",
            "Gemini image adapter (smoke PASS, routable)",
            "Codex CLI adapter (blocked: usage limit)",
            "Generic OpenAI adapter for remaining 7 workers",
        ],
        "blocked_on": ["Mistral/GLM/Qwen/MiniMax/Step/Hunyuan/Nous API keys"],
        "next_unblocked_work": ["E4 resource continuity", "E5 safe mode", "VPS preparation"],
    }
    return result


def run_poll_cycle():
    ensure_dirs()

    if check_kill_switch():
        log_event("Kill switch active")
        return

    git_pull()

    pending = find_pending_tasks()
    if not pending:
        return

    for task_path in pending:
        task, errors = load_task_file(task_path)
        task_id = task_path.stem

        if errors:
            log_event(f"Invalid task {task_id}: {errors}")
            try:
                block_task(task_id, "validation_failed", "Schema validation failed", "Other tasks continue")
                dest = BLOCKED_DIR / f"{task_id}.json"
                if not dest.exists():
                    import shutil
                    shutil.copy2(str(task_path), str(dest))
                    task_path.unlink()
            except Exception as e:
                log_event(f"Failed to block: {e}")
            continue

        if is_task_completed(task_id) or is_task_blocked(task_id):
            task_path.unlink()
            continue
        if is_task_running(task_id):
            continue

        if task.get("requires_owner_approval", False):
            try:
                claim_task(task_path)
                block_task(task_id, "owner_approval_required", "Requires owner approval", "Other tasks continue")
            except Exception as e:
                log_event(f"Error blocking: {e}")
            continue

        if claim_task(task_path):
            log_event(f"Claimed task: {task_id}")
            try:
                result = handle_task(task)
                if result.get("status") == "completed":
                    complete_task(task_id, result)
                elif result.get("status") == "in_progress":
                    log_event(f"Task {task_id} in progress")
                else:
                    complete_task(task_id, result)
            except Exception as e:
                log_event(f"Task {task_id} failed: {e}")
                try:
                    block_task(task_id, "execution_error", str(e), "Other tasks continue")
                except Exception as e2:
                    log_event(f"Failed to block: {e2}")
            return


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Remote Queue Poller")
    parser.add_argument("--once", action="store_true", help="Run one poll cycle")
    parser.add_argument("--status", action="store_true", help="Show queue status")
    parser.add_argument("--kill", action="store_true", help="Activate kill switch")
    parser.add_argument("--resume", action="store_true", help="Deactivate kill switch")
    parser.add_argument("--loop", action="store_true", help="Run continuous loop")
    args = parser.parse_args()

    ensure_dirs()

    if args.kill:
        KILL_SWITCH_FILE.write_text("killed")
        print("Kill switch activated")
        return

    if args.resume:
        if KILL_SWITCH_FILE.exists():
            KILL_SWITCH_FILE.unlink()
        print("Kill switch deactivated")
        return

    if args.status:
        pending = list(PENDING_DIR.glob("*.json"))
        running = list(RUNNING_DIR.glob("*.json"))
        completed = list(COMPLETED_DIR.glob("*.json"))
        blocked = list(BLOCKED_DIR.glob("*.json"))
        print(f"Queue status:")
        print(f"  Pending:   {len(pending)}")
        print(f"  Running:   {len(running)}")
        print(f"  Completed: {len(completed)}")
        print(f"  Blocked:   {len(blocked)}")
        for p in pending:
            try:
                t = json.loads(p.read_text())
                print(f"    [{t.get('priority', '?')}] {p.stem}")
            except Exception:
                print(f"    {p.stem}: <invalid>")
        for b in blocked:
            try:
                t = json.loads(b.read_text())
                blocker = t.get("blocker", {})
                print(f"    BLOCKED {b.stem}: {blocker.get('category', '?')}")
            except Exception:
                print(f"    {b.stem}: <invalid>")
        return

    if args.once:
        if acquire_lock():
            try:
                run_poll_cycle()
            finally:
                release_lock()
        else:
            print("Another poller instance is running")
        return

    if args.loop:
        log_event("Poller starting")
        while True:
            try:
                if not acquire_lock():
                    log_event("Another poller running — exiting")
                    return
                try:
                    run_poll_cycle()
                finally:
                    release_lock()
            except Exception as e:
                log_event(f"Poll error: {e}")
            for _ in range(120):
                if check_kill_switch():
                    return
                time.sleep(1)
        return

    # Default: one-shot
    if acquire_lock():
        try:
            run_poll_cycle()
        finally:
            release_lock()
    else:
        print("Another poller instance is running")


if __name__ == "__main__":
    main()
