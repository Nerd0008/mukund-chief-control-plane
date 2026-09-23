#!/usr/bin/env python3
"""E5 Safe Mode / Resilience — degraded mode, failure drills, convergence enforcement."""

import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

GOV_DIR = Path(__file__).parent


class SystemMode(Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    SAFE_MODE = "SAFE_MODE"
    HALT = "HALT"


class SafeModeManager:
    """Manage system operating mode."""

    def __init__(self, con):
        self.con = con
        self._mode = SystemMode.NORMAL
        self._failure_counts: Dict[str, int] = {}

    @property
    def mode(self) -> SystemMode:
        return self._mode

    def enter_degraded(self, reason: str) -> Dict[str, Any]:
        """Enter degraded mode."""
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
        """Enter safe mode (more restrictive than degraded)."""
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
        """Halt all execution."""
        self._mode = SystemMode.HALT
        return {
            "mode": "HALT",
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "restrictions": ["All execution stopped"],
        }

    def resume_normal(self) -> Dict[str, Any]:
        """Resume normal operation."""
        self._mode = SystemMode.NORMAL
        return {
            "mode": "NORMAL",
            "timestamp": datetime.utcnow().isoformat(),
        }

    def record_failure(self, worker_id: str, task_family: str) -> int:
        """Record a failure for a worker+task family combination."""
        key = f"{worker_id}:{task_family}"
        if key not in self._failure_counts:
            self._failure_counts[key] = 0
        self._failure_counts[key] += 1
        return self._failure_counts[key]

    def get_failure_count(self, worker_id: str, task_family: str) -> int:
        """Get failure count for a worker+task family."""
        key = f"{worker_id}:{task_family}"
        return self._failure_counts.get(key, 0)

    def reset_failure_count(self, worker_id: str, task_family: str):
        """Reset failure count for a worker+task family."""
        key = f"{worker_id}:{task_family}"
        self._failure_counts[key] = 0


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

    def list_drills(self) -> Dict[str, Dict[str, str]]:
        """List available failure drills."""
        return self.DRILLS

    def run_drill(self, drill_name: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run a failure drill (simulated)."""
        if drill_name not in self.DRILLS:
            return {"error": f"Unknown drill: {drill_name}"}

        drill = self.DRILLS[drill_name]
        return {
            "drill": drill_name,
            "description": drill["description"],
            "severity": drill["severity"],
            "expected_behavior": drill["expected_behavior"],
            "simulated_at": datetime.utcnow().isoformat(),
            "context": context or {},
            "result": "simulated_success",
        }


class ConvergenceEnforcer:
    """Prevent infinite loops and enforce convergence."""

    def __init__(self, max_retries: int = 3, max_replans: int = 2,
                 max_verification_rounds: int = 2):
        self.max_retries = max_retries
        self.max_replans = max_replans
        self.max_verification_rounds = max_verification_rounds
        self._attempt_counts: Dict[str, int] = {}

    def can_retry(self, key: str) -> bool:
        """Check if an operation can be retried."""
        count = self._attempt_counts.get(key, 0)
        return count < self.max_retries

    def can_replan(self, plan_id: str) -> bool:
        """Check if a plan can be replanned."""
        count = self._attempt_counts.get(f"replan:{plan_id}", 0)
        return count < self.max_replans

    def record_attempt(self, key: str) -> int:
        """Record an attempt. Returns new count."""
        if key not in self._attempt_counts:
            self._attempt_counts[key] = 0
        self._attempt_counts[key] += 1
        return self._attempt_counts[key]

    def record_verification(self, node_id: str) -> int:
        """Record a verification round. Returns new count."""
        return self.record_attempt(f"verify:{node_id}")

    def should_stop(self, key: str) -> tuple:
        """Check if operation should stop. Returns (should_stop, reason)."""
        count = self._attempt_counts.get(key, 0)
        if count >= self.max_retries:
            return True, f"Max retries ({self.max_retries}) reached for {key}"
        return False, ""

    def reset(self, key: str):
        """Reset attempt count for a key."""
        self._attempt_counts[key] = 0


class MalformedOutputHandler:
    """Handle malformed output from workers."""

    @staticmethod
    def validate_output(output: Any, expected_schema: Dict[str, Any] = None) -> Dict[str, Any]:
        """Validate worker output against expected schema."""
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
                # Check required fields
                for field in expected_schema.get("required", []):
                    if field not in output:
                        result["errors"].append(f"Missing required field: {field}")
                if result["errors"]:
                    return result
            result["valid"] = True
            return result

        # Unknown type - warning but not necessarily invalid
        result["warnings"].append(f"Unexpected output type: {type(output).__name__}")
        result["valid"] = True
        return result

    @staticmethod
    def sanitize_output(output: Any) -> Any:
        """Sanitize output to remove potential issues."""
        if isinstance(output, str):
            # Remove null bytes, control characters
            sanitized = "".join(c for c in output if c.isprintable() or c in "\n\r\t")
            return sanitized
        return output
