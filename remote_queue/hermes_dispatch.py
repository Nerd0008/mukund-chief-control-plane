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
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from remote_queue.retry_policy import MAX_ATTEMPTS

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


def _task_prompt(task: Dict[str, Any], attempt: int = 1) -> str:
    allowed_scope = "\n".join(f"- {item}" for item in task.get("allowed_scope", []))
    stop_conditions = "\n".join(f"- {item}" for item in task.get("stop_conditions", []))
    notes = task.get("notes") or "(none)"

    retry_context = ""
    if int(attempt or 1) > 1:
        retry_context = f"""
RETRY CONTEXT (attempt {attempt} of {MAX_ATTEMPTS})
An earlier attempt of this same task ended in a recoverable execution failure.
The repository may already contain work that earlier attempt landed.
- Inspect current repository and queue state before changing anything. Commits,
  evidence directories and files produced by earlier attempts are preserved and
  must not be recreated, reverted, duplicated, or redone.
- Resume from the smallest unfinished unit and complete only what is still
  outstanding.
- Do not repeat already-completed work or re-open settled decisions.
- If this failure was in fact a deterministic blocker (missing credential,
  required owner approval, architecture/safety/irreversible-action decision, or
  an unchanged external provider state), report that blocker truthfully instead
  of retrying the same action.
"""

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
{retry_context}

EXECUTION RULES
- Treat the authority file and repository state as source of truth.
- Work only within the allowed scope.
- Make concrete progress using your normal tools; inspect before modifying.
- Preserve existing work and avoid destructive/irreversible operations.
- Respect unresolved owner approval gates. If the authority records a standing conditional approval, apply it only after its recorded objective conditions are verified.
- Treat your own remote-queue/running/{task.get("task_id", "")}.json as immutable execution input; do not rewrite or reinterpret the running task contract while executing it.
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
    """Parse Hermes' final response without persisting raw output on failure.

    Hermes sometimes wraps the requested JSON in a short prose/fenced response
    even in final-only mode. Accept the first embedded JSON object that carries
    a valid task status, while still failing closed for arbitrary prose.
    """
    text = raw.strip()
    result = None

    # Fast path: exact JSON object.
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict):
            result = candidate
    except json.JSONDecodeError:
        pass

    # Tolerate a fenced/embedded JSON object without storing surrounding prose.
    if result is None:
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("status") in {"completed", "blocked"}:
                result = candidate
                break

    if result is None:
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


# ``attempt`` is the 1-based execution attempt used by the bounded
# recoverable-failure retry policy (initial attempt + at most MAX_RETRIES).
# It never mutates the task contract: it only labels the attempt in the visible
# console and adds resume guidance to the generated prompt so work already
# landed by an earlier attempt is preserved instead of redone.
def dispatch_task(
    task: Dict[str, Any],
    timeout_seconds: Optional[int] = None,
    attempt: int = 1,
) -> Dict[str, Any]:
    """Invoke Hermes with bounded hard and no-progress timeouts."""
    attempt = max(1, int(attempt or 1))
    if timeout_seconds is None:
        timeout_seconds = int(os.environ.get("HERMES_REMOTE_TASK_TIMEOUT", "1200"))
    idle_timeout_seconds = int(os.environ.get("HERMES_REMOTE_IDLE_TIMEOUT", "300"))
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

    prompt = _task_prompt(task, attempt=attempt)

    # On Mukund's Windows workstation, remote agent tasks are intentionally
    # visible in their own console. The helper streams Hermes output when
    # available and prints a heartbeat during quiet periods. Set
    # HERMES_REMOTE_VISIBLE=0 to fall back to background capture.
    visible = os.name == "nt" and os.environ.get("HERMES_REMOTE_VISIBLE", "1") != "0"

    if visible:
        helper = REPO_ROOT / "remote_queue" / "visible_worker.py"
        task_id = str(task.get("task_id", "agent-task"))

        try:
            with tempfile.TemporaryDirectory(prefix="hermes-remote-") as temp_dir:
                temp = Path(temp_dir)
                prompt_file = temp / "prompt.txt"
                output_file = temp / "output.txt"
                exit_file = temp / "exit.txt"
                prompt_file.write_text(prompt, encoding="utf-8")

                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                proc = subprocess.Popen(
                    [
                        sys.executable,
                        str(helper),
                        "--hermes", hermes,
                        "--prompt-file", str(prompt_file),
                        "--output-file", str(output_file),
                        "--exit-file", str(exit_file),
                        "--task-id", task_id,
                        "--cwd", str(REPO_ROOT),
                        "--attempt", str(attempt),
                        "--idle-timeout-seconds", str(idle_timeout_seconds),
                    ],
                    cwd=str(REPO_ROOT),
                    creationflags=flags,
                    env=os.environ.copy(),
                )

                try:
                    proc.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    # Terminate the helper and its Hermes child as a process tree.
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
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

                raw = output_file.read_text(encoding="utf-8", errors="replace") if output_file.exists() else ""
                try:
                    hermes_rc = int(exit_file.read_text(encoding="utf-8").strip())
                except Exception:
                    hermes_rc = proc.returncode

                if hermes_rc != 0:
                    timeout_note = (
                        f"Hermes worker hit the {idle_timeout_seconds}s no-progress watchdog"
                        if hermes_rc == 124
                        else f"Hermes CLI exited with code {hermes_rc}"
                    )
                    return {
                        "status": "blocked",
                        "summary": f"{timeout_note} (output_bytes={len(raw.encode('utf-8', errors='replace'))}).",
                        "owner_action_required": None,
                        "blocker_category": "execution_error",
                        "commits": [],
                        "tests": [],
                        "changed_files": [],
                        "remaining": ["Inspect the visible Hermes Remote Worker console and retry"],
                    }

                return _parse_response(raw)

        except Exception as exc:
            return {
                "status": "blocked",
                "summary": f"Visible Hermes dispatch failed before completion: {type(exc).__name__}.",
                "owner_action_required": None,
                "blocker_category": "execution_error",
                "commits": [],
                "tests": [],
                "changed_files": [],
                "remaining": ["Inspect scheduled-task environment and retry"],
            }

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
