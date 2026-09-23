#!/usr/bin/env python3
"""E3 Planner — deterministic task planning and decomposition.

Consumes task fingerprint + E1 classification context to decide whether
a task should be executed as a single node or decomposed into a DAG.
All decomposition output is advisory; the Qualification Gate decides.
"""

from typing import Any, Dict, List, Optional
from execution_dag import ExecutionDAG, DAGNode, NODE_STATES
from task_fingerprint import TaskFingerprint


class E3Planner:
    """Deterministic task planner — shadow only until Stage 2 approved."""

    # Thresholds for decomposition
    REASONING_DEPTH_THRESHOLD = 3  # reasoning_depth >= 3 triggers decomposition
    MULTI_ROLE_THRESHOLD = 2       # >= 2 required roles triggers decomposition
    INTEGRATION_COMPLEXITY_THRESHOLD = "medium"  # integration complexity triggers integrator node

    # TaskFingerprint.verification_type ('deterministic', 'critic', 'owner') is
    # not the node-level verification_method vocabulary
    # ('test', 'schema', 'comparison', 'critic', 'owner'). Map it explicitly so
    # a deterministic-verification task does not fail decomposition review.
    VERIFICATION_TYPE_TO_METHOD = {
        "deterministic": "test",
        "critic": "critic",
        "owner": "owner",
        "test": "test",
        "schema": "schema",
        "comparison": "comparison",
    }

    @classmethod
    def verification_method_for(cls, fp: TaskFingerprint) -> str:
        """Node-level verification method for a fingerprint's verification type."""
        vt = getattr(fp, "verification_type", None)
        if not vt:
            return "test"
        return cls.VERIFICATION_TYPE_TO_METHOD.get(vt, "test")

    def __init__(self):
        self.plan_counter = 0

    def _next_plan_id(self) -> str:
        self.plan_counter += 1
        return f"plan-{self.plan_counter:04d}"

    def plan(self, objective: str, fingerprint: TaskFingerprint) -> Dict[str, Any]:
        """Produce a plan: either single-node or multi-node decomposition.

        Returns a dict with:
        - plan_id
        - decomposition: bool
        - reason: why this plan shape was chosen
        - nodes: list of proposed DAGNode specs
        """
        should_decompose, reason = self._should_decompose(fingerprint, objective)

        if not should_decompose:
            return self._single_node_plan(objective, fingerprint)
        else:
            return self._decomposed_plan(objective, fingerprint, reason)

    def _should_decompose(self, fp: TaskFingerprint, objective: str) -> tuple:
        """Decide whether decomposition is warranted."""
        if fp.reasoning_depth is not None and fp.reasoning_depth >= self.REASONING_DEPTH_THRESHOLD:
            return True, f"reasoning_depth={fp.reasoning_depth} >= threshold {self.REASONING_DEPTH_THRESHOLD}"

        if fp.required_roles and len(fp.required_roles) >= self.MULTI_ROLE_THRESHOLD:
            return True, f"required_roles={fp.required_roles} (count >= {self.MULTI_ROLE_THRESHOLD})"

        if fp.integration_complexity and fp.integration_complexity in ("medium", "high"):
            return True, f"integration_complexity={fp.integration_complexity}"

        return False, "Task is simple enough for single-node execution"

    def _single_node_plan(self, objective: str, fp: TaskFingerprint) -> Dict[str, Any]:
        """Create a single-node plan."""
        plan_id = self._next_plan_id()
        node_id = f"node-{plan_id}-1"
        return {
            "plan_id": plan_id,
            "decomposition": False,
            "reason": "Single-node execution",
            "nodes": [
                {
                    "node_id": node_id,
                    "objective": objective,
                    "capability_roles": fp.required_roles or ["builder"],
                    "dependencies": [],
                    "verification_method": self.verification_method_for(fp),
                    "floor_id": None,
                    "allowed_tools": [],
                    "permissions": {},
                    "inputs": {},
                    "expected_outputs": {},
                }
            ],
        }

    def _decomposed_plan(self, objective: str, fp: TaskFingerprint, reason: str) -> Dict[str, Any]:
        """Create a multi-node decomposed plan based on required roles."""
        plan_id = self._next_plan_id()
        nodes = []
        roles = fp.required_roles or ["builder"]

        # Build a node per required role, chained sequentially by default
        prev_node_id = None
        for i, role in enumerate(roles):
            node_id = f"node-{plan_id}-{i+1}"
            deps = [prev_node_id] if prev_node_id else []
            node = {
                "node_id": node_id,
                "objective": f"[{role.capitalize()}] {objective}",
                "capability_roles": [role],
                "dependencies": deps,
                "verification_method": self.verification_method_for(fp),
                "floor_id": None,
                "allowed_tools": [],
                "permissions": {},
                "inputs": {} if not prev_node_id else {"upstream_output": f"output-{prev_node_id}"},
                "expected_outputs": {"artifact": f"output-{node_id}"},
            }
            nodes.append(node)
            prev_node_id = node_id

        # Add integrator node if multiple outputs require assembly
        if fp.integration_complexity and fp.integration_complexity in ("medium", "high") and len(roles) > 1:
            integrator_node = {
                "node_id": f"node-{plan_id}-{len(nodes)+1}",
                "objective": f"[Integrate] Assemble and reconcile outputs for: {objective}",
                "capability_roles": ["integrator"],
                "dependencies": [prev_node_id] if prev_node_id else [],
                "verification_method": self.verification_method_for(fp),
                "floor_id": None,
                "allowed_tools": [],
                "permissions": {"read_only": True},
                "inputs": {"upstream_outputs": [f"output-{n.get('node_id', '')}" for n in nodes]},
                "expected_outputs": {"final_artifact": f"output-{plan_id}-final"},
            }
            nodes.append(integrator_node)

        return {
            "plan_id": plan_id,
            "decomposition": True,
            "reason": reason,
            "nodes": nodes,
        }

    def build_dag(self, plan: Dict[str, Any]) -> ExecutionDAG:
        """Convert a plan dict into an ExecutionDAG."""
        dag = ExecutionDAG(plan_id=plan["plan_id"])
        node_id_map = {}  # map node index to actual node_id

        # First pass: create all nodes
        for i, node_spec in enumerate(plan["nodes"]):
            node = DAGNode(
                objective=node_spec["objective"],
                capability_roles=node_spec["capability_roles"],
                inputs=node_spec.get("inputs", {}),
                expected_outputs=node_spec.get("expected_outputs", {}),
                floor_id=node_spec.get("floor_id"),
                allowed_tools=node_spec.get("allowed_tools", []),
                permissions=node_spec.get("permissions", {}),
                node_id=node_spec.get("node_id"),
            )
            node.verification_method = node_spec.get("verification_method", "test")
            dag.add_node(node)
            node_id_map[i] = node.node_id

        # Second pass: wire up dependencies
        for i, node_spec in enumerate(plan["nodes"]):
            node = dag.get_node(node_id_map[i])
            for dep_index in range(len(node_spec.get("dependencies", []))):
                if dep_index < i:
                    node.dependencies.append(node_id_map[dep_index])

        return dag
