#!/usr/bin/env python3
"""E3 Escalation — structured ask-owner when E3 cannot proceed."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class EscalationTrigger(Enum):
    STUCK = "stuck"
    UNEXPLAINED_ERROR = "unexplained_error"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    REPEATED_FAILURE = "repeated_failure"
    BROKEN_DEPENDENCY = "broken_dependency"
    CANNOT_MEET_FLOOR = "cannot_meet_floor"
    REQUIRES_OWNER_DECISION = "requires_owner_decision"
    NO_QUALIFIED_WORKER = "no_qualified_worker"
    CONVERGENCE_LIMIT = "convergence_limit"
    REPLAN_DEPTH_EXHAUSTED = "replan_depth_exhausted"


class EscalationRecord:
    def __init__(self, trigger: str, context: str,
                 proposals_considered: Optional[List[str]] = None,
                 why_each_failed: Optional[List[str]] = None,
                 owner_decision_needed: str = ""):
        self.escalation_id = generate_id("escalate")
        self.trigger = trigger
        self.context = context
        self.proposals_considered = proposals_considered if proposals_considered is not None else []
        self.why_each_failed = why_each_failed if why_each_failed is not None else []
        self.owner_decision_needed = owner_decision_needed
        self.recommended_action: Optional[str] = None
        self.resolved = False
        self.resolution: Optional[str] = None
        self.created_at = datetime.utcnow().isoformat()

    def resolve(self, resolution: str):
        self.resolution = resolution
        self.resolved = True


class E3Escalator:
    def __init__(self):
        self.escalation_history: List[EscalationRecord] = []

    def escalate(self, trigger: str, context: str,
                 proposals_considered: Optional[List[str]] = None,
                 why_each_failed: Optional[List[str]] = None,
                 owner_decision_needed: str = "",
                 recommended_action: str = "") -> EscalationRecord:
        record = EscalationRecord(
            trigger=trigger,
            context=context,
            proposals_considered=proposals_considered,
            why_each_failed=why_each_failed,
            owner_decision_needed=owner_decision_needed,
        )
        record.recommended_action = recommended_action
        self.escalation_history.append(record)
        return record

    def get_active_escalations(self) -> List[EscalationRecord]:
        return [e for e in self.escalation_history if not e.resolved]

    def resolve_escalation(self, escalation_id: str, resolution: str):
        for e in self.escalation_history:
            if e.escalation_id == escalation_id:
                e.resolve(resolution)
                return
