#!/usr/bin/env python3
"""Dispatch approved structured remote-queue tasks into Hermes CLI.

This is the execution bridge between GitHub queue state and the Hermes agent.
It never executes shell text supplied by a queue task. The task is rendered into
an instruction prompt and passed to Hermes' non-interactive one-shot mode.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).parent.parent


def _find_hermes_cli() -> Optional[str]:
    """Locate the Hermes CLI without relying on a single PATH layout."""
    candidates = []

    configured = os.environ.get("HERMES_CLI")
    if configured:
        candidates.append(configured)

    # The scheduled poller runs from Hermes' venv Python. Console entry points
    # installed in the same venv normally live beside python.exe/python.
    exe_dir = Path(sys.executable).parent
    candidates.extend([
        str(exe_dir / "hermes.exe"),
        str(exe_dir / "hermes"),
        str(exe_dir / "hermes.cmd"),
    ])

    on_path = shutil.which("hermes")
    if on_path:
        candidates.append(on_path)

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _task_prompt(task: Dict[str, Any]) -> str:
    allowed_scope = "\n".join(f"- {item}" for item in task.get("allowed_scope", []))
    stop_conditions = "\n".join(f"- {item}" for item in task.get("stop_conditions", []))
    notes = task.get("notes") or "(none)"

    return f"""You are Hermes, receiving a structured task from Mukund's GitHub control plane.

TASK ID
{task.get("task_id", "")}

AUTHORITY
{task.get("authority", "")}

OBJECTIVE
{task.get("objective", "")}

ALLOWED SCOPE
{allowed_scope or "- none supplied"}

STOP CONDITIONS
{stop_conditions or "- none supplied"}

NOTES
{notes}

EXECUTION RULES
- Treat the authority file and repository state as source of truth.
- Work only within the allowed scope.
- Make concrete progress using your normal tools; inspect before modifying.
- Preserve existing work and avoid destructive/irreversible operations.
- Do not bypass owner approval gates, including E3 Stage 2 production approval.
- Do not invent credentials, provider identities, usage, qualification evidence, or deployment facts.
- Never expose or commit secrets, credentials, raw chain-of-thought, or private runtime databases.
- If credentials/account access, explicit owner approval, an irreversible action, or an architecture/safety decision is required, stop that dependency and report it as blocked while preserving completed independent work.
- Commit and push truthful repository changes when appropriate.
- Run relevant tests/audits before claiming completion.

FINAL RESPONSE CONTRACT
Return ONLY one JSON object. No markdown and no prose outside the JSON.
Use exactly this shape:
{{
  "status": "completed" or "blocked",
  "summary": "concise factual result",
  "owner_action_required": null or "exact action Mukund must take",
  "blocker_category": null or "credentials|owner_approval|architecture|safety|irreversible_action|external_provider|execution_error",
  "commits": ["sha or description"],
  "tests": ["test/result"],
  "changed_files": ["path"],
  "remaining": ["next truthful item"]
}}
"""


def _parse_response(raw: str) -> Dict[str, Any]:
    """Parse Hermes' final-only response without ever persisting raw output on failure."""
    text = raw.strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Be conservative: do not write unstructured model output into GitHub.
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        return {
            "status": "blocked",
            "summary": f"Hermes returned an unstructured final response (sha256={digest}, bytes={len(text.encode('utf-8', errors='replace'))}). Inspect locally; raw response was not committed.",
            "owner_action_required": None,
            "blocker_category": "execution_error",
            "commits": [],
            "tests": [],
            "changed_files": [],
            "remaining": ["Inspect local Hermes output and retry with structured final response"],
        }

    if not isinstance(result, dict):
        return {
            "status": "blocked",
            "summary": "Hermes final response was valid JSON but not an object.",
            "owner_action_required": None,
            "blocker_category": "execution_error",
            "commits": [],
            "tests": [],
            "changed_files": [],
            "remaining": ["Retry task"],
        }

    if result.get("status") not in {"completed", "blocked"}:
        result["status"] = "blocked"
        result["blocker_category"] = "execution_error"
        result["owner_action_required"] = None
        result["summary"] = "Hermes response omitted a valid completed/blocked status."
    return result


def dispatch_task(task: Dict[str, Any], timeout_seconds: int = 3600) -> Dict[str, Any]:
    """Invoke Hermes in non-interactive final-response-only mode."""
    hermes = _find_hermes_cli()
    if not hermes:
        return {
            "status": "blocked",
            "summary": "Hermes CLI executable was not found by the scheduled poller.",
            "owner_action_required": "Verify Hermes CLI installation/path or set HERMES_CLI for the scheduled task.",
            "blocker_category": "execution_error",
            "commits": [],
            "tests": [],
            "changed_files": [],
            "remaining": ["Restore CLI dispatch path and retry"],
        }

    prompt = _task_prompt(task)

    try:
        proc = subprocess.run(
            [hermes, "-z", prompt],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "blocked",
            "summary": f"Hermes dispatch exceeded {timeout_seconds} seconds.",
            "owner_action_required": None,
            "blocker_category": "execution_error",
            "commits": [],
            "tests": [],
            "changed_files": [],
            "remaining": ["Inspect local Hermes run and retry or decompose the task"],
        }
    except Exception as exc:
        return {
            "status": "blocked",
            "summary": f"Hermes dispatch failed before completion: {type(exc).__name__}.",
            "owner_action_required": None,
            "blocker_category": "execution_error",
            "commits": [],
            "tests": [],
            "changed_files": [],
            "remaining": ["Inspect scheduled-task environment and retry"],
        }

    if proc.returncode != 0:
        # Do not persist stderr/stdout because provider/CLI failures can contain
        # environment details. Only record return code and lengths.
        return {
            "status": "blocked",
            "summary": f"Hermes CLI exited with code {proc.returncode} (stdout_bytes={len(proc.stdout.encode('utf-8', errors='replace'))}, stderr_bytes={len(proc.stderr.encode('utf-8', errors='replace'))}).",
            "owner_action_required": None,
            "blocker_category": "execution_error",
            "commits": [],
            "tests": [],
            "changed_files": [],
            "remaining": ["Inspect Hermes CLI locally and retry"],
        }

    return _parse_response(proc.stdout)
