#!/usr/bin/env python3
"""Bounded-recovery policy for the Hermes GitHub remote queue.

Owner directive (2026-09-24, recorded in
``tasks-or-issues/2026-09-24-full-operational-vps-cutover.md``):

    For a recoverable execution failure the queue must attempt the same task up
    to TWO additional times before finally marking it blocked and advancing.

Rules encoded here
------------------
* Budget: the initial attempt plus at most ``MAX_RETRIES`` (2) retries, i.e. at
  most ``MAX_ATTEMPTS`` (3) executions of one task. The bound is structural:
  there is no input for which ``plan_retry`` returns a retry beyond the budget,
  so an unbounded loop is impossible.
* Only explicitly recoverable outcomes are retried. ``execution_error`` covers
  transient CLI/tool failures, wrapper launch failures, hard-timeout expiry and
  the no-progress watchdog kill.
* Deterministic blockers are parked immediately and never retried while the
  blocking state is unchanged: missing credentials, owner approval,
  architecture/safety decisions, irreversible actions, and unchanged external
  provider blockers. This is what keeps the Stage-2 missing-key anti-loop rule
  intact (0/7 provider keys is a deterministic blocker, not a flaky failure).
* An unknown or missing ``blocker_category`` on a blocked result is NOT treated
  as recoverable: the queue cannot prove it is transient, so it fails closed by
  parking the task rather than retrying it.
"""

from typing import Any, Dict, Optional, Tuple

#: Retries permitted after the initial attempt (owner directive: two).
MAX_RETRIES = 2

#: Total executions permitted for one task (initial attempt + retries).
MAX_ATTEMPTS = MAX_RETRIES + 1

#: Blocker categories that may be retried without owner/external action.
RECOVERABLE_CATEGORIES = frozenset({"execution_error"})

#: Blocker categories that must park immediately (retrying cannot change them).
NON_RETRYABLE_CATEGORIES = frozenset({
    "credentials",
    "owner_approval",
    "architecture",
    "safety",
    "irreversible_action",
    "external_provider",
})


def is_recoverable(result: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Return ``(recoverable, reason)`` for a blocked execution result."""
    result = result or {}

    if result.get("status") != "blocked":
        return False, f"status={result.get('status')!r} is not a blocked execution result"

    category = result.get("blocker_category")
    if category in NON_RETRYABLE_CATEGORIES:
        return False, (
            f"blocker_category={category!r} is deterministic; park until the "
            "blocking state changes"
        )
    if category not in RECOVERABLE_CATEGORIES:
        return False, (
            f"blocker_category={category!r} is not a known recoverable failure; "
            "failing closed instead of retrying"
        )
    return True, f"recoverable execution failure ({category})"


def plan_retry(attempt: int, result: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Decide the next step after *attempt* (1-based) just failed.

    Returns ``(should_retry, reason)``. ``should_retry`` is True only for a
    recoverable failure that still has retry budget left, so the total number of
    executions of one task can never exceed :data:`MAX_ATTEMPTS`.
    """
    recoverable, why = is_recoverable(result)
    if not recoverable:
        return False, why

    attempt = int(attempt or 0)
    if attempt >= MAX_ATTEMPTS:
        return False, (
            f"retry budget exhausted after {attempt} of {MAX_ATTEMPTS} permitted "
            "attempts"
        )

    return True, (
        f"{why}; attempt {attempt} of {MAX_ATTEMPTS} failed, "
        f"retry {attempt} of {MAX_RETRIES} scheduled"
    )


def retry_state(attempts_used: int, result: Optional[Dict[str, Any]], will_retry: bool,
                reason: str = "") -> Dict[str, Any]:
    """Build the auditable retry metadata persisted on the running task record."""
    attempts_used = int(attempts_used or 0)
    result = result or {}
    return {
        "attempts_used": attempts_used,
        "retries_used": max(0, attempts_used - 1),
        "max_attempts": MAX_ATTEMPTS,
        "max_retries": MAX_RETRIES,
        "last_blocker_category": result.get("blocker_category"),
        "last_summary": result.get("summary"),
        "next_action": "retry" if will_retry else "park",
        "reason": reason,
    }


def next_attempt_number(state: Optional[Dict[str, Any]]) -> int:
    """Return the next 1-based attempt number resumed from persisted state.

    ``attempts_used`` is read from the running task record, so a poller restart
    resumes the same bounded count instead of restarting the retry loop.
    """
    state = state or {}
    try:
        used = int(state.get("attempts_used") or 0)
    except (TypeError, ValueError):
        used = 0
    return max(1, used + 1)
