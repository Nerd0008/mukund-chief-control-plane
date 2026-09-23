#!/usr/bin/env python3
"""E3 Exploration/Shadow Rules — conservative, policy-based worker exploration."""

from typing import Any, Dict, List, Optional
from enum import Enum


class ExplorationPolicy(Enum):
    DISABLED = "disabled"
    CONSERVATIVE = "conservative"
    ENABLED = "enabled"


MAX_EXPLORATION_PER_TASK = 1
EXPLORATION_ELIGIBLE_RISKS = ("R0", "R1")
MAX_EXPLORATION_COST_RATIO = 0.3


class ExplorationRequest:
    def __init__(self, task_id: str, candidate_worker_id: str,
                 primary_worker_id: str, task_family: str,
                 risk_class: str, expected_cost_ratio: float = 1.0):
        self.task_id = task_id
        self.candidate_worker_id = candidate_worker_id
        self.primary_worker_id = primary_worker_id
        self.task_family = task_family
        self.risk_class = risk_class
        self.expected_cost_ratio = expected_cost_ratio


class ExplorationDecision:
    def __init__(self, approved: bool, reason: str,
                 exploration_worker_id: Optional[str] = None):
        self.approved = approved
        self.reason = reason
        self.exploration_worker_id = exploration_worker_id


class ExplorationRules:
    def __init__(self, policy: ExplorationPolicy = ExplorationPolicy.CONSERVATIVE):
        self.policy = policy
        self.exploration_count = 0

    def evaluate(self, request: ExplorationRequest) -> ExplorationDecision:
        if self.policy == ExplorationPolicy.DISABLED:
            return ExplorationDecision(False, "Exploration policy is DISABLED")

        if request.risk_class not in EXPLORATION_ELIGIBLE_RISKS:
            return ExplorationDecision(
                False,
                f"Risk class {request.risk_class} is not eligible for exploration (only {EXPLORATION_ELIGIBLE_RISKS})"
            )

        if request.expected_cost_ratio > (1 + MAX_EXPLORATION_COST_RATIO):
            return ExplorationDecision(
                False,
                f"Expected cost ratio {request.expected_cost_ratio:.2f} exceeds max {1 + MAX_EXPLORATION_COST_RATIO:.2f}"
            )

        if request.candidate_worker_id == request.primary_worker_id:
            return ExplorationDecision(False, "Exploration worker must differ from primary worker")

        self.exploration_count += 1
        return ExplorationDecision(
            True,
            "Exploration approved under conservative policy",
            exploration_worker_id=request.candidate_worker_id,
        )

    def can_explore(self, risk_class: str, current_exploration_count: int = 0) -> bool:
        if self.policy == ExplorationPolicy.DISABLED:
            return False
        if risk_class not in EXPLORATION_ELIGIBLE_RISKS:
            return False
        if current_exploration_count >= MAX_EXPLORATION_PER_TASK:
            return False
        return True


class ShadowEvaluation:
    def __init__(self):
        self.shadow_count = 0

    def can_shadow(self, risk_class: str,
                   has_deterministic_verification: bool = False) -> bool:
        if risk_class not in EXPLORATION_ELIGIBLE_RISKS:
            return False
        if not has_deterministic_verification:
            return False
        return True

    def record_shadow_result(self, worker_id: str, task_id: str,
                             production_output: Any, shadow_output: Any,
                             shadow_correct: bool) -> Dict[str, Any]:
        self.shadow_count += 1
        return {
            "worker_id": worker_id,
            "task_id": task_id,
            "shadow_correct": shadow_correct,
            "production_used": True,
            "shadow_contributed_to_evidence": True,
            "timestamp": shadow_output.get("timestamp") if isinstance(shadow_output, dict) else None,
        }
