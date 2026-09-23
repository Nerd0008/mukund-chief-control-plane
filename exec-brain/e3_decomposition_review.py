#!/usr/bin/env python3
"""E3 Decomposition Review — hybrid quality gate (Layer 1: deterministic structural checks).

Layer 2 (semantic decomposition review by AI critic) is implemented separately
when a qualified critic worker exists. This module implements Layer 1.
"""

from typing import Any, Dict, List, Optional, Tuple
from execution_dag import ExecutionDAG, DAGNode


class DecompositionReviewResult:
    """Result of decomposition review."""

    def __init__(self, approved: bool, structural_issues: Optional[List[str]] = None,
                 semantic_issues: Optional[List[str]] = None, warnings: Optional[List[str]] = None):
        self.approved = approved
        self.structural_issues = structural_issues if structural_issues is not None else []
        self.semantic_issues = semantic_issues if semantic_issues is not None else []
        self.warnings = warnings if warnings is not None else []

    def __repr__(self):
        status = "APPROVED" if self.approved else "REJECTED"
        return f"DecompositionReviewResult({status}, structural={len(self.structural_issues)}, semantic={len(self.semantic_issues)})"


class DecompositionReview:
    """Layer 1 deterministic structural checks for proposed decomposition."""

    def __init__(self, known_floor_ids: Optional[List[str]] = None):
        self.known_floor_ids = known_floor_ids if known_floor_ids is not None else []

    def review(self, plan: Dict[str, Any], dag: ExecutionDAG) -> DecompositionReviewResult:
        """Run structural checks on proposed decomposition."""
        issues: List[str] = []
        warnings: List[str] = []

        # Check 1: DAG is acyclic
        if not self._check_acyclic(dag):
            issues.append("DAG contains cycle(s)")

        # Check 2: Dependencies valid (all referenced nodes exist)
        dep_issues = self._check_dependencies_valid(dag)
        issues.extend(dep_issues)

        # Check 3: Required node fields present
        field_issues = self._check_required_fields(plan)
        issues.extend(field_issues)

        # Check 4: Referenced floors exist (where specified)
        if self.known_floor_ids:
            floor_issues = self._check_floors_exist(plan)
            issues.extend(floor_issues)

        # Check 5: No unsafe shared-write parallelism
        unsafe_issues = self._check_unsafe_parallelism(dag)
        issues.extend(unsafe_issues)

        # Check 6: Integration node exists when multiple outputs require assembly
        if plan.get("decomposition") and len(plan.get("nodes", [])) > 1:
            has_integrator = any(
                "integrator" in node.get("capability_roles", [])
                for node in plan.get("nodes", [])
            )
            if not has_integrator:
                warnings.append("Multiple outputs but no integrator node")

        # Check 7: Verification method exists where required
        verif_issues = self._check_verification_methods(plan)
        issues.extend(verif_issues)

        # Check 8: No isolated nodes (every node must have deps or be depended upon)
        isolated = self._check_isolated_nodes(dag)
        if isolated:
            warnings.append(f"Isolated nodes found: {isolated}")

        return DecompositionReviewResult(
            approved=len(issues) == 0,
            structural_issues=issues,
            warnings=warnings,
        )

    def _check_acyclic(self, dag: ExecutionDAG) -> bool:
        """Check DAG has no cycles using DFS."""
        visited: set = set()
        rec_stack: set = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            node = dag.get_node(node_id)
            if node:
                for dep_id in node.dependencies:
                    if dep_id not in visited:
                        if has_cycle(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        return True
            rec_stack.discard(node_id)
            return False

        for node_id in dag.nodes:
            if node_id not in visited:
                if has_cycle(node_id):
                    return False
        return True

    def _check_dependencies_valid(self, dag: ExecutionDAG) -> List[str]:
        """Check all dependency references point to existing nodes."""
        issues: List[str] = []
        node_ids = set(dag.nodes.keys())
        for node_id, node in dag.nodes.items():
            for dep_id in node.dependencies:
                if dep_id not in node_ids:
                    issues.append(f"Node {node_id} depends on non-existent node {dep_id}")
        return issues

    def _check_required_fields(self, plan: Dict[str, Any]) -> List[str]:
        """Check all required fields present in each node."""
        issues: List[str] = []
        for i, node in enumerate(plan.get("nodes", [])):
            if not node.get("objective"):
                issues.append(f"Node {i}: missing objective")
            if not node.get("capability_roles"):
                issues.append(f"Node {i}: missing capability_roles")
        return issues

    def _check_floors_exist(self, plan: Dict[str, Any]) -> List[str]:
        """Check referenced floor IDs exist."""
        issues: List[str] = []
        for i, node in enumerate(plan.get("nodes", [])):
            floor_id = node.get("floor_id")
            if floor_id and floor_id not in self.known_floor_ids:
                issues.append(f"Node {i}: floor_id {floor_id} not in known floors")
        return issues

    def _check_unsafe_parallelism(self, dag: ExecutionDAG) -> List[str]:
        """Check for unsafe shared-write parallelism (simplified heuristic)."""
        issues: List[str] = []
        # Two nodes with same role that can run in parallel = potential conflict
        role_groups: Dict[str, List[str]] = {}
        for node_id, node in dag.nodes.items():
            for role in node.capability_roles:
                if role not in role_groups:
                    role_groups[role] = []
                role_groups[role].append(node_id)

        for role, node_ids in role_groups.items():
            if len(node_ids) > 1:
                # Check if any pairs have no ordering between them
                for i, n1 in enumerate(node_ids):
                    for n2 in node_ids[i+1:]:
                        if not self._has_path(dag, n1, n2) and not self._has_path(dag, n2, n1):
                            if role in ("builder", "integrator"):
                                issues.append(
                                    f"Unsafe parallel write: nodes {n1} and {n2} "
                                    f"share role '{role}' with no ordering"
                                )
        return issues

    def _has_path(self, dag: ExecutionDAG, from_id: str, to_id: str) -> bool:
        """Check if there's a path from from_id to to_id via dependencies."""
        visited: set = set()
        stack = [from_id]
        while stack:
            current = stack.pop()
            if current == to_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            node = dag.get_node(current)
            if node:
                stack.extend(node.dependencies)
        return False

    def _check_verification_methods(self, plan: Dict[str, Any]) -> List[str]:
        """Check verification_method is valid."""
        issues: List[str] = []
        valid_methods = ("test", "schema", "comparison", "critic", "owner")
        for i, node in enumerate(plan.get("nodes", [])):
            method = node.get("verification_method", "test")
            if method not in valid_methods:
                issues.append(f"Node {i}: invalid verification_method '{method}'")
        return issues

    def _check_isolated_nodes(self, dag: ExecutionDAG) -> List[str]:
        """Find nodes with no connections."""
        depended_upon: set = set()
        for node in dag.nodes.values():
            for dep_id in node.dependencies:
                depended_upon.add(dep_id)

        isolated: List[str] = []
        for node_id in dag.nodes:
            node = dag.get_node(node_id)
            if node and not node.dependencies and node_id not in depended_upon:
                isolated.append(node_id)
        return isolated
