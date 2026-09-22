#!/usr/bin/env python3
"""E3 Execution DAG — dependency graph for complex work."""

import uuid
from datetime import datetime

NODE_STATES = [
    'PLANNED', 'BLOCKED', 'READY', 'RUNNING', 'VERIFYING',
    'REWORK', 'COMPLETE', 'FAILED', 'PAUSED', 'CANCELLED'
]


def generate_id(prefix=''):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class DAGNode:
    """Represents a node in the execution DAG."""

    def __init__(self, objective, capability_roles=None, dependencies=None,
                 inputs=None, expected_outputs=None, floor_id=None,
                 allowed_tools=None, permissions=None, node_id=None):
        self.node_id = node_id or generate_id('node')
        self.objective = objective
        self.capability_roles = capability_roles or []
        self.dependencies = dependencies or []
        self.inputs = inputs or {}
        self.expected_outputs = expected_outputs or {}
        self.floor_id = floor_id
        self.allowed_tools = allowed_tools or []
        self.permissions = permissions or {}
        self.verification_method = 'test'
        self.assigned_worker = None
        self.fallback_candidates = []
        self.state = 'PLANNED'
        self.attempts = 0
        self.defect_attempts = {}
        self.created_at = datetime.utcnow().isoformat()
        self.updated_at = self.created_at

    def to_dict(self):
        return {
            'node_id': self.node_id,
            'objective': self.objective,
            'capability_roles': self.capability_roles,
            'dependencies': self.dependencies,
            'state': self.state,
            'attempts': self.attempts,
            'assigned_worker': self.assigned_worker
        }


class ExecutionDAG:
    """Represents a dependency graph of work to be executed."""

    def __init__(self, plan_id=None):
        self.plan_id = plan_id or generate_id('plan')
        self.nodes = {}
        self.created_at = datetime.utcnow().isoformat()

    def add_node(self, node):
        """Add a node to the DAG."""
        self.nodes[node.node_id] = node
        return node.node_id

    def get_node(self, node_id):
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_ready_nodes(self):
        """Get all nodes whose dependencies are satisfied."""
        ready = []
        for node_id, node in self.nodes.items():
            if node.state == 'BLOCKED':
                if all(
                    self.nodes.get(dep_id, DAGNode('')).state == 'COMPLETE'
                    for dep_id in node.dependencies
                ):
                    ready.append(node_id)
        return ready

    def get_next_plan_version(self, trigger, parent_plan_id=None):
        """Create a new plan version for replanning."""
        return {
            'plan_id': generate_id('plan'),
            'parent_plan_id': parent_plan_id or self.plan_id,
            'trigger': trigger,
            'dag_nodes': {nid: n.to_dict() for nid, n in self.nodes.items()},
            'created_at': datetime.utcnow().isoformat()
        }

    def is_complete(self):
        """Check if all nodes are complete."""
        return all(n.state == 'COMPLETE' for n in self.nodes.values())

    def is_failed(self):
        """Check if any node has failed."""
        return any(n.state == 'FAILED' for n in self.nodes.values())

    def to_dict(self):
        return {
            'plan_id': self.plan_id,
            'node_count': len(self.nodes),
            'nodes': {nid: n.to_dict() for nid, n in self.nodes.items()},
            'is_complete': self.is_complete(),
            'is_failed': self.is_failed()
        }
