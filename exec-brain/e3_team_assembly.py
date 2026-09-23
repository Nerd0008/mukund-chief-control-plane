#!/usr/bin/env python3
"""E3 Temporary Team Assembly — dynamically assign workers to a plan."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class TeamAssignment:
    """Assignment of a worker to a specific node in a plan."""

    def __init__(self, node_id: str, worker_id: str, role: str,
                 confidence: str, rationale: str):
        self.assignment_id = generate_id("assign")
        self.node_id = node_id
        self.worker_id = worker_id
        self.role = role
        self.confidence = confidence
        self.rationale = rationale
        self.assigned_at = datetime.utcnow().isoformat()


class TeamAssembly:
    """Result of assembling a team for a plan."""

    def __init__(self, plan_id: str):
        self.assembly_id = generate_id("team")
        self.plan_id = plan_id
        self.assignments: List[TeamAssignment] = []
        self.assembled_at = datetime.utcnow().isoformat()
        self.complete = False
        self.issues: List[str] = []

    def add_assignment(self, assignment: TeamAssignment):
        self.assignments.append(assignment)

    def get_workers(self) -> List[str]:
        return [a.worker_id for a in self.assignments]

    def get_roles(self) -> Dict[str, str]:
        return {a.node_id: a.role for a in self.assignments}

    def is_complete(self) -> bool:
        return self.complete

    def has_conflicts(self) -> bool:
        return len(self.issues) > 0


class TeamAssembler:
    """Dynamically assemble teams for execution plans."""

    def __init__(self, capability_registry: Any, router: Any = None):
        self.registry = capability_registry
        self.router = router

    def assemble_team(self, plan: Dict[str, Any],
                      candidates_by_node: Optional[Dict[str, List[Any]]] = None,
                      require_all_nodes: bool = True) -> TeamAssembly:
        """Assemble a team for the given plan using available candidates."""
        assembly = TeamAssembly(plan.get("plan_id", "unknown"))
        nodes = plan.get("nodes", [])
        assigned_workers: Dict[str, str] = {}

        for i, node in enumerate(nodes):
            node_id = node.get("node_id", f"node-{i+1}")
            roles = node.get("capability_roles", ["builder"])
            candidates = candidates_by_node.get(node_id, []) if candidates_by_node is not None else []

            assigned = False
            for candidate in candidates:
                if candidate.worker_id in assigned_workers:
                    assembly.issues.append(
                        f"Worker {candidate.worker_id} assigned to multiple nodes: "
                        f"{assigned_workers[candidate.worker_id]} and {node_id}"
                    )
                    continue

                assignment = TeamAssignment(
                    node_id=node_id,
                    worker_id=candidate.worker_id,
                    role=candidate.role,
                    confidence=candidate.confidence,
                    rationale=candidate.concise_rationale,
                )
                assembly.add_assignment(assignment)
                assigned_workers[candidate.worker_id] = node_id
                assigned = True
                break

            if not assigned:
                assembly.issues.append(f"No candidate available for node {node_id} with roles {roles}")
                if require_all_nodes:
                    assembly.complete = False
                    return assembly

        assembly.complete = len(assembly.assignments) == len(nodes)
        return assembly

    def detect_team_conflicts(self, assembly: TeamAssembly) -> List[Dict[str, Any]]:
        """Detect conflicts in assembled team."""
        conflicts: List[Dict[str, Any]] = []
        worker_roles: Dict[str, List[str]] = {}

        for assignment in assembly.assignments:
            if assignment.worker_id not in worker_roles:
                worker_roles[assignment.worker_id] = []
            worker_roles[assignment.worker_id].append(assignment.role)

        for worker_id, roles in worker_roles.items():
            if "integrator" in roles and "verifier" in roles:
                conflicts.append({
                    "type": "integrator_verifier_same_worker",
                    "worker_id": worker_id,
                    "message": "Integrator cannot independently verify its own output",
                    "severity": "high",
                })

        return conflicts

    def suggest_independent_verifier(self, assembly: TeamAssembly,
                                     available_workers: List[str]) -> Optional[str]:
        """Suggest an independent verifier different from the integrator."""
        integrator_workers = [
            a.worker_id for a in assembly.assignments if a.role == "integrator"
        ]
        for worker_id in available_workers:
            if worker_id not in integrator_workers:
                return worker_id
        return None
