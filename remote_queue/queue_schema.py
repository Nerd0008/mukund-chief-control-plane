#!/usr/bin/env python3
"""Hermes GitHub Remote Queue — JSON schema validation and atomic claiming."""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
PENDING_DIR = REPO_ROOT / "remote_queue" / "pending"
RUNNING_DIR = REPO_ROOT / "remote_queue" / "running"
COMPLETED_DIR = REPO_ROOT / "remote_queue" / "completed"
BLOCKED_DIR = REPO_ROOT / "remote_queue" / "blocked"
LOG_DIR = REPO_ROOT / "remote_queue" / "logs"

REQUIRED_FIELDS = ["task_id", "created_at", "objective", "authority", "priority", "allowed_scope", "requires_owner_approval", "status"]
VALID_PRIORITIES = {"critical", "high", "medium", "low"}
VALID_STATUSES = {"pending", "running", "completed", "blocked"}

APPROVED_AUTHORITIES = {
    "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
    "tasks-or-issues/hermes-github-remote-queue.md",
    "tasks-or-issues/2026-09-22-e3-model-roster-handover.md",
    "approved-architecture/executive-brain-v2.md",
    "handovers/2026-09-22-e3-model-roster-handover.md",
}


class ValidationError(Exception):
    pass


class QueueError(Exception):
    pass


def ensure_dirs():
    for d in [PENDING_DIR, RUNNING_DIR, COMPLETED_DIR, BLOCKED_DIR, LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def validate_task(task: Dict[str, Any]) -> List[str]:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in task:
            errors.append(f"missing required field: {field}")

    if "task_id" in task and not isinstance(task.get("task_id"), str):
        errors.append("task_id must be string")
    if "objective" in task and not isinstance(task.get("objective"), str):
        errors.append("objective must be string")
    if "authority" in task and not isinstance(task.get("authority"), str):
        errors.append("authority must be string")
    if "priority" in task and task.get("priority") not in VALID_PRIORITIES:
        errors.append(f"priority must be one of {VALID_PRIORITIES}")
    if "status" in task and task.get("status") not in VALID_STATUSES:
        errors.append(f"status must be one of {VALID_STATUSES}")
    if "requires_owner_approval" in task and not isinstance(task.get("requires_owner_approval"), bool):
        errors.append("requires_owner_approval must be boolean")
    if "allowed_scope" in task and not isinstance(task.get("allowed_scope"), list):
        errors.append("allowed_scope must be list")

    authority = task.get("authority", "")
    if authority and authority not in APPROVED_AUTHORITIES:
        errors.append(f"authority not in approved list: {authority}")

    task_id = task.get("task_id", "")
    if task_id and not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$', task_id):
        errors.append(f"invalid task_id format: {task_id}")

    objective = task.get("objective", "")
    if re.search(r'(password|secret|api[ _]?key|token)\s*[:=]\s*\S+', objective, re.IGNORECASE):
        errors.append("objective must not contain secrets/credentials")

    return errors


def load_task_file(path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            task = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"invalid JSON: {e}"]
    except Exception as e:
        return None, [f"read error: {e}"]

    errors = validate_task(task)
    return task, errors


def find_pending_tasks() -> List[Path]:
    if not PENDING_DIR.exists():
        return []

    files = list(PENDING_DIR.glob("*.json"))
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def sort_key(path: Path):
        try:
            with open(path, 'r') as f:
                task = json.load(f)
            pri = task.get("priority", "low")
            return (priority_order.get(pri, 99), task.get("created_at", ""), path.name)
        except Exception:
            return (99, "", path.name)

    return sorted(files, key=sort_key)


def claim_task(task_path: Path) -> bool:
    ensure_dirs()
    task_id = task_path.stem
    dest = RUNNING_DIR / f"{task_id}.json"

    try:
        if dest.exists():
            return False

        shutil.copy2(str(task_path), str(dest))
        task_path.unlink()
        return True
    except Exception:
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        return False


def complete_task(task_id: str, result: Dict[str, Any]):
    ensure_dirs()
    src = RUNNING_DIR / f"{task_id}.json"
    dest = COMPLETED_DIR / f"{task_id}.json"

    if not src.exists():
        raise QueueError(f"Task not in running: {task_id}")

    with open(src, 'r', encoding='utf-8') as f:
        task = json.load(f)

    task["status"] = "completed"
    task["completed_at"] = datetime.utcnow().isoformat() + "Z"
    task["result"] = result

    with open(dest, 'w', encoding='utf-8') as f:
        json.dump(task, f, indent=2)

    src.unlink()


def block_task(task_id: str, blocker_category: str, owner_action: str, continue_work: str):
    ensure_dirs()
    src = RUNNING_DIR / f"{task_id}.json"
    dest = BLOCKED_DIR / f"{task_id}.json"

    if not src.exists():
        raise QueueError(f"Task not in running: {task_id}")

    with open(src, 'r', encoding='utf-8') as f:
        task = json.load(f)

    task["status"] = "blocked"
    task["blocked_at"] = datetime.utcnow().isoformat() + "Z"
    task["blocker"] = {
        "category": blocker_category,
        "owner_action_required": owner_action,
        "continue_without": continue_work,
    }

    with open(dest, 'w', encoding='utf-8') as f:
        json.dump(task, f, indent=2)

    src.unlink()


def log_event(message: str):
    ensure_dirs()
    log_file = LOG_DIR / "queue.log"
    timestamp = datetime.utcnow().isoformat() + "Z"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")


def get_running_tasks() -> List[Dict[str, Any]]:
    if not RUNNING_DIR.exists():
        return []
    tasks = []
    for path in RUNNING_DIR.glob("*.json"):
        try:
            with open(path, 'r') as f:
                tasks.append(json.load(f))
        except Exception:
            pass
    return tasks


def is_task_completed(task_id: str) -> bool:
    return (COMPLETED_DIR / f"{task_id}.json").exists()


def is_task_blocked(task_id: str) -> bool:
    return (BLOCKED_DIR / f"{task_id}.json").exists()


def is_task_running(task_id: str) -> bool:
    return (RUNNING_DIR / f"{task_id}.json").exists()
