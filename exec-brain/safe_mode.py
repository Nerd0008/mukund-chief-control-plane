#!/usr/bin/env python3
"""E5 Safe Mode / Resilience — degraded mode, failure drills, convergence enforcement.

Integrates with E4 resource_monitor for runway-based triggers.
DB-backed via orchestration_db safe_mode_event, failure_drill_log, convergence_event tables.
"""

import json
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SystemMode(Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    SAFE_MODE = "SAFE_MODE"
    HALT = "HALT"


class SafeModeManager:
    """Manage system operating mode with DB persistence."""

    def __init__(self, con):
        self.con = con
        self._mode = SystemMode.NORMAL
        self._failure_counts: Dict[str, int] = {}

    @property
    def mode(self) -> SystemMode:
        return self._mode

    def enter_degraded(self, reason: str) -> Dict[str, Any]:
        self._mode = SystemMode.DEGRADED
        return {
            "mode": "DEGRADED",
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "restrictions": [
                "No high-risk tasks accepted",
                "Use only qualified workers",
                "Reduced parallelism",
            ],
        }

    def enter_safe_mode(self, reason: str) -> Dict[str, Any]:
        self._mode = SystemMode.SAFE_MODE
        return {
            "mode": "SAFE_MODE",
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "restrictions": [
                "No new tasks accepted",
                "Complete in-flight tasks only",
                "No worker failover (insufficient confidence)",
            ],
        }

    def enter_halt(self, reason: str) -> Dict[str, Any]:
        self._mode = SystemMode.HALT
        return {
            "mode": "HALT",
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "restrictions": ["All execution stopped"],
        }

    def resume_normal(self) -> Dict[str, Any]:
        self._mode = SystemMode.NORMAL
        return {
            "mode": "NORMAL",
            "timestamp": datetime.utcnow().isoformat(),
        }

    def record_failure(self, worker_id: str, task_family: str) -> int:
        key = f"{worker_id}:{task_family}"
        if key not in self._failure_counts:
            self._failure_counts[key] = 0
        self._failure_counts[key] += 1
        return self._failure_counts[key]

    def get_failure_count(self, worker_id: str, task_family: str) -> int:
        key = f"{worker_id}:{task_family}"
        return self._failure_counts.get(key, 0)

    def reset_failure_count(self, worker_id: str, task_family: str):
        key = f"{worker_id}:{task_family}"
        self._failure_counts[key] = 0

    def record_safe_mode_event(
        self, trigger_type: str, severity: str, description: str,
        affected_workers: List[str] = None
    ) -> int:
        """Persist safe mode event to DB."""
        ts = datetime.utcnow().isoformat()
        cur = self.con.execute(
            """INSERT INTO safe_mode_event 
               (trigger_type, severity, description, affected_workers, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (trigger_type, severity, description,
             json.dumps(affected_workers or []), ts),
        )
        self.con.commit()
        return cur.lastrowid

    def resolve_event(self, event_id: int, auto: bool = False):
        """Mark event as resolved."""
        ts = datetime.utcnow().isoformat()
        self.con.execute(
            """UPDATE safe_mode_event 
               SET auto_resolved = ?, resolved_at = ?
               WHERE event_id = ?""",
            (1 if auto else 0, ts, event_id),
        )
        self.con.commit()

    def get_active_events(self) -> List[Dict[str, Any]]:
        """Get all unresolved events from DB."""
        rows = self.con.execute(
            """SELECT event_id, trigger_type, severity, description, 
                      affected_workers, created_at
               FROM safe_mode_event 
               WHERE resolved_at IS NULL
               ORDER BY created_at DESC"""
        ).fetchall()
        return [
            {
                "event_id": r[0],
                "trigger_type": r[1],
                "severity": r[2],
                "description": r[3],
                "affected_workers": json.loads(r[4]) if r[4] else [],
                "created_at": r[5],
            }
            for r in rows
        ]


class FailureDrills:
    """Predefined failure scenarios for testing resilience."""

    DRILLS = {
        "provider_outage": {
            "description": "Simulate a provider being unavailable",
            "severity": "high",
            "expected_behavior": "Failover to equivalent worker or escalate",
        },
        "repeated_worker_failure": {
            "description": "Same worker fails repeatedly on same task family",
            "severity": "medium",
            "expected_behavior": "Suspend worker after N failures, failover",
        },
        "rate_limit": {
            "description": "Provider returns 429 rate limit",
            "severity": "low",
            "expected_behavior": "Back off and retry with different worker",
        },
        "malformed_output": {
            "description": "Worker returns malformed/unexpected output",
            "severity": "medium",
            "expected_behavior": "Reject output, retry with same or different worker",
        },
        "no_equivalent_worker": {
            "description": "Worker fails and no qualified equivalent exists",
            "severity": "high",
            "expected_behavior": "Escalate to owner, do not silently degrade",
        },
    }

    def __init__(self, con=None):
        self.con = con

    def list_drills(self) -> Dict[str, Dict[str, str]]:
        return self.DRILLS

    def run_drill(self, drill_name: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if drill_name not in self.DRILLS:
            return {"error": f"Unknown drill: {drill_name}"}

        drill = self.DRILLS[drill_name]
        result = {
            "drill": drill_name,
            "description": drill["description"],
            "severity": drill["severity"],
            "expected_behavior": drill["expected_behavior"],
            "simulated_at": datetime.utcnow().isoformat(),
            "context": context or {},
            "result": "simulated_success",
        }

        # Persist to DB if available
        if self.con:
            import uuid
            drill_id = f"drill-{uuid.uuid4().hex[:12]}"
            self.con.execute(
                """INSERT INTO failure_drill_log 
                   (drill_id, scenario, injected_failure, safe_mode_triggered, success, details, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (drill_id, drill_name, drill_name,
                 drill["severity"] == "high", True,
                 json.dumps(result), datetime.utcnow().isoformat()),
            )
            self.con.commit()
            result["drill_id"] = drill_id

        return result


class ConvergenceEnforcer:
    """Prevent infinite loops and enforce convergence."""

    def __init__(self, con=None, max_retries: int = 3, max_replans: int = 2,
                 max_verification_rounds: int = 2):
        self.con = con
        self.max_retries = max_retries
        self.max_replans = max_replans
        self.max_verification_rounds = max_verification_rounds
        self._attempt_counts: Dict[str, int] = {}

    def can_retry(self, key: str) -> bool:
        count = self._attempt_counts.get(key, 0)
        return count < self.max_retries

    def can_replan(self, plan_id: str) -> bool:
        count = self._attempt_counts.get(f"replan:{plan_id}", 0)
        return count < self.max_replans

    def record_attempt(self, key: str) -> int:
        if key not in self._attempt_counts:
            self._attempt_counts[key] = 0
        self._attempt_counts[key] += 1
        return self._attempt_counts[key]

    def record_verification(self, node_id: str) -> int:
        return self.record_attempt(f"verify:{node_id}")

    def should_stop(self, key: str) -> tuple:
        count = self._attempt_counts.get(key, 0)
        if count >= self.max_retries:
            return True, f"Max retries ({self.max_retries}) reached for {key}"
        return False, ""

    def reset(self, key: str):
        self._attempt_counts[key] = 0

    def record_convergence_event(
        self, worker_id: str, task_family: str, failure_count: int
    ) -> Dict[str, Any]:
        """Record convergence event to DB."""
        ts = datetime.utcnow().isoformat()
        threshold = self.max_retries

        if failure_count >= threshold:
            action = "quarantine_worker"
            escalated = True
        elif failure_count == threshold - 1:
            action = "warn_and_reduce_scope"
            escalated = False
        else:
            action = "log_and_retry"
            escalated = False

        self.con.execute(
            """INSERT INTO convergence_event 
               (worker_id, task_family, failure_count, action_taken, escalated, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (worker_id, task_family, failure_count, action, escalated, ts),
        )
        self.con.commit()

        return {
            "worker_id": worker_id,
            "task_family": task_family,
            "failure_count": failure_count,
            "action_taken": action,
            "escalated": escalated,
            "timestamp": ts,
        }

    def get_escalations(self) -> List[Dict[str, Any]]:
        """Get all escalated convergence events."""
        rows = self.con.execute(
            """SELECT event_id, worker_id, task_family, failure_count, 
                      action_taken, created_at
               FROM convergence_event 
               WHERE escalated = 1
               ORDER BY created_at DESC"""
        ).fetchall()
        return [
            {
                "event_id": r[0],
                "worker_id": r[1],
                "task_family": r[2],
                "failure_count": r[3],
                "action_taken": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]


class MalformedOutputHandler:
    """Handle malformed output from workers."""

    @staticmethod
    def validate_output(output: Any, expected_schema: Dict[str, Any] = None) -> Dict[str, Any]:
        result = {
            "valid": False,
            "errors": [],
            "warnings": [],
        }

        if output is None:
            result["errors"].append("Output is None")
            return result

        if isinstance(output, str):
            if len(output.strip()) == 0:
                result["errors"].append("Output is empty")
                return result
            result["valid"] = True
            return result

        if isinstance(output, dict):
            if expected_schema:
                for field in expected_schema.get("required", []):
                    if field not in output:
                        result["errors"].append(f"Missing required field: {field}")
                if result["errors"]:
                    return result
            result["valid"] = True
            return result

        result["warnings"].append(f"Unexpected output type: {type(output).__name__}")
        result["valid"] = True
        return result

    @staticmethod
    def sanitize_output(output: Any) -> Any:
        if isinstance(output, str):
            sanitized = "".join(c for c in output if c.isprintable() or c in "\n\r\t")
            return sanitized
        return output

    @staticmethod
    def handle_malformed(
        worker_id: str, task_id: str, output: Any, validation_error: str
    ) -> Dict[str, Any]:
        """Process malformed output and determine next action."""
        is_recoverable = True

        unrecoverable_patterns = [
            "security_violation",
            "unauthorized_action",
            "data_exfiltration",
        ]
        for pattern in unrecoverable_patterns:
            if pattern in validation_error.lower():
                is_recoverable = False
                break

        result = {
            "worker_id": worker_id,
            "task_id": task_id,
            "validation_error": validation_error,
            "is_recoverable": is_recoverable,
            "action": "retry_with_correction" if is_recoverable else "escalate_to_owner",
            "output_preview": str(output)[:200] if output else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return result
