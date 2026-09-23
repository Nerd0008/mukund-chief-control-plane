#!/usr/bin/env python3
"""E3 Replanner — versioned logical replanning."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from execution_dag import ExecutionDAG, DAGNode


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ReplanTrigger:
    HIDDEN_DEPENDENCY = "hidden_dependency"
    ASSUMPTION_INVALIDATED = "assumption_invalidated"
    NEW_REQUIRED_WORK = "new_required_work"
    UPSTREAM_CHANGE = "upstream_change"
    FUNDAMENTAL_FLAW = "fundamental_flaw"
    NO_QUALIFIED_ROUTE = "no_qualified_route"


class ReplanRecord:
    def __init__(self, plan_id: str, trigger: str, reason: str):
        self.record_id = generate_id("replan")
        self.plan_id = plan_id
        self.trigger = trigger
        self.reason = reason
        self.created_at = datetime.utcnow().isoformat()
        self.parent_plan_id = plan_id
        self.new_plan_id: Optional[str] = None
        self.nodes_preserved: List[str] = []
        self.nodes_cancelled: List[str] = []
        self.nodes_added: List[str] = []


class E3Replanner:
    def __init__(self, max_replan_depth: int = 3):
        self.max_replan_depth = max_replan_depth
        self.replan_count = 0
        self.replan_history: List[ReplanRecord] = []

    def should_replan(self, dag: ExecutionDAG, trigger: str) -> bool:
        if self.replan_count >= self.max_replan_depth:
            return False
        return True

    def replan(self, dag: ExecutionDAG, trigger: str, reason: str,
               affected_node_ids: Optional[List[str]] = None,
               preserved_node_ids: Optional[List[str]] = None) -> Optional[ReplanRecord]:
        if not self.should_replan(dag, trigger):
            return None

        self.replan_count += 1
        record = ReplanRecord(
            plan_id=dag.plan_id,
            trigger=trigger,
            reason=reason,
        )

        preserved = preserved_node_ids if preserved_node_ids is not None else []
        for node_id, node in dag.nodes.items():
            if node_id not in (affected_node_ids or []) and node.state == "COMPLETE":
                if node_id not in preserved:
                    preserved.append(node_id)
        record.nodes_preserved = preserved

        for node_id in affected_node_ids or []:
            node = dag.get_node(node_id)
            if node and node.state != "COMPLETE":
                record.nodes_cancelled.append(node_id)
                node.state = "CANCELLED"

        self.replan_history.append(record)
        return record

    def get_replan_history(self, plan_id: Optional[str] = None) -> List[ReplanRecord]:
        if plan_id:
            return [r for r in self.replan_history if r.plan_id == plan_id]
        return self.replan_history

    def can_replan(self) -> bool:
        return self.replan_count < self.max_replan_depth
