#!/usr/bin/env python3
"""E3 Conflict Handler — detect and resolve conflicts between specialist outputs."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ConflictType(Enum):
    FACTUAL_DISAGREEMENT = "factual_disagreement"
    CONTRADICTORY_RECOMMENDATIONS = "contradictory_recommendations"
    INCOMPATIBLE_OUTPUTS = "incompatible_outputs"
    DIFFERENT_PRIORITIES = "different_priorities"
    ASSUMPTION_CONFLICT = "assumption_conflict"


class ConflictRecord:
    def __init__(self, conflict_type: str, node_a: str, node_b: str,
                 disputed_claim: str, context: str = ""):
        self.conflict_id = generate_id("conflict")
        self.conflict_type = conflict_type
        self.node_a = node_a
        self.node_b = node_b
        self.disputed_claim = disputed_claim
        self.context = context
        self.resolution: Optional[str] = None
        self.resolved_by: Optional[str] = None
        self.created_at = datetime.utcnow().isoformat()
        self.resolved = False

    def resolve(self, resolution: str, resolved_by: str):
        self.resolution = resolution
        self.resolved_by = resolved_by
        self.resolved = True


class ConflictHandler:
    def __init__(self):
        self.conflict_history: List[ConflictRecord] = []

    def detect_conflict(self, node_a_id: str, output_a: Any,
                        node_b_id: str, output_b: Any) -> Optional[ConflictRecord]:
        if isinstance(output_a, dict) and isinstance(output_b, dict):
            common_keys = set(output_a.keys()) & set(output_b.keys())
            for key in common_keys:
                if output_a[key] != output_b[key]:
                    return ConflictRecord(
                        conflict_type=ConflictType.FACTUAL_DISAGREEMENT.value,
                        node_a=node_a_id,
                        node_b=node_b_id,
                        disputed_claim=f"Key '{key}': {output_a[key]} vs {output_b[key]}",
                    )
        return None

    def resolve_conflict(self, conflict: ConflictRecord,
                         resolution: str, resolver: str) -> bool:
        conflict.resolve(resolution, resolver)
        self.conflict_history.append(conflict)
        return True

    def escalate_conflict(self, conflict: ConflictRecord,
                          reason: str = "unresolvable") -> Dict[str, Any]:
        return {
            "escalation_type": "conflict_unresolved",
            "conflict_id": conflict.conflict_id,
            "node_a": conflict.node_a,
            "node_b": conflict.node_b,
            "disputed_claim": conflict.disputed_claim,
            "reason": reason,
            "owner_decision_required": True,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_unresolved_conflicts(self) -> List[ConflictRecord]:
        return [c for c in self.conflict_history if not c.resolved]

    def get_conflict_history(self, node_id: Optional[str] = None) -> List[ConflictRecord]:
        if node_id:
            return [c for c in self.conflict_history if c.node_a == node_id or c.node_b == node_id]
        return self.conflict_history
