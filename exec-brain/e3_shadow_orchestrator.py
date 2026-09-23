#!/usr/bin/env python3
"""E3 Shadow Orchestrator — composes E3 components into a rehearsal pipeline.

SHADOW ONLY: No production dispatch. All outputs are advisory.
Stage 2 production enablement requires explicit owner approval.
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Component imports
from e3_planner import E3Planner
from e3_decomposition_review import DecompositionReview
from e3_router import E3Router, RouterCandidate
from e3_context import ContextCompiler
from e3_permissions import PermissionCompiler
from e3_team_assembly import TeamAssembler, TeamAssembly
from e3_integrator import E3Integrator
from e3_verifier import IndependentVerifier, VerificationMethod, VerificationOutcome
from e3_conflict import ConflictHandler
from e3_evidence import E3EvidenceManager, EvidenceRecord
from e3_escalate import E3Escalator
from e3_exploration import ExplorationRules, ShadowEvaluation, ExplorationPolicy, ExplorationRequest
from e3_qualification_benchmark import ColdStartBenchmark
from e3_replan import E3Replanner, ReplanTrigger

from capability_registry import CapabilityRegistry
from worker_registry import WorkerRegistry
from task_fingerprint import TaskFingerprint
from execution_dag import ExecutionDAG
from worker_contract import WorkerContract
from orchestration_db import init_db


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ShadowRehearsalResult:
    """Result of a shadow rehearsal run."""

    def __init__(self, rehearsal_id: str, task_objective: str):
        self.rehearsal_id = rehearsal_id
        self.task_objective = task_objective
        self.plan: Optional[Dict[str, Any]] = None
        self.dag: Optional[ExecutionDAG] = None
        self.decomposition_review: Optional[Any] = None
        self.candidates_by_node: Dict[str, List[RouterCandidate]] = {}
        self.context_packages: Dict[str, Dict[str, Any]] = {}
        self.permission_packages: Dict[str, Dict[str, Any]] = {}
        self.team_assembly: Optional[TeamAssembly] = None
        self.verification_results: Dict[str, Any] = {}
        self.conflicts_detected: List[Dict[str, Any]] = []
        self.evidence_records: List[str] = []
        self.escalations: List[str] = []
        self.exploration_decisions: List[Dict[str, Any]] = []
        self.replan_history: List[str] = []
        self.warnings: List[str] = []
        self.outcome: str = "PENDING"
        self.created_at = datetime.utcnow().isoformat()
        self.completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rehearsal_id": self.rehearsal_id,
            "task_objective": self.task_objective,
            "plan_id": self.plan.get("plan_id") if self.plan else None,
            "decomposition": self.plan.get("decomposition") if self.plan else None,
            "node_count": len(self.dag.nodes) if self.dag else 0,
            "decomposition_approved": self.decomposition_review.approved if self.decomposition_review else None,
            "structural_issues": self.decomposition_review.structural_issues if self.decomposition_review else [],
            "candidates_found": sum(len(c) for c in self.candidates_by_node.values()),
            "team_complete": self.team_assembly.complete if self.team_assembly else False,
            "team_issues": self.team_assembly.issues if self.team_assembly else [],
            "verification_count": len(self.verification_results),
            "conflicts_detected": len(self.conflicts_detected),
            "evidence_recorded": len(self.evidence_records),
            "escalations": len(self.escalations),
            "warnings": self.warnings,
            "outcome": self.outcome,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class E3ShadowOrchestrator:
    """Shadow-only rehearsal pipeline composing E3 orchestration components.

    This orchestrator rehearses a task through the full E3 pipeline without
    dispatching any production work. All outputs are advisory.
    """

    def __init__(self, db_path: Optional[Path] = None,
                 exploration_policy: ExplorationPolicy = ExplorationPolicy.CONSERVATIVE):
        self.db_path = db_path
        self.con: Optional[sqlite3.Connection] = None

        # Core components
        self.planner = E3Planner()
        self.decomposition_reviewer = DecompositionReview()
        self.context_compiler = ContextCompiler()
        self.permission_compiler = PermissionCompiler()
        self.integrator = E3Integrator()
        self.verifier = IndependentVerifier()
        self.conflict_handler = ConflictHandler()
        self.evidence_manager = E3EvidenceManager()
        self.escalator = E3Escalator()
        self.exploration_rules = ExplorationRules(policy=exploration_policy)
        self.shadow_evaluator = ShadowEvaluation()
        self.cold_start_benchmark = ColdStartBenchmark()
        self.replanner = E3Replanner()

        # Registries
        self.capability_registry: Optional[CapabilityRegistry] = None
        self.worker_registry = WorkerRegistry()
        self.router: Optional[E3Router] = None

        if db_path:
            self._connect()
            self.capability_registry = CapabilityRegistry(self.con)
            self.router = E3Router(self.capability_registry)

    def _connect(self):
        """Connect to orchestration DB."""
        if self.con is None and self.db_path:
            init_db(self.db_path)
            self.con = sqlite3.connect(str(self.db_path))
            self.con.row_factory = sqlite3.Row

    def rehearse(self, objective: str, fingerprint: TaskFingerprint,
                 simulate_outputs: Optional[Dict[str, Any]] = None) -> ShadowRehearsalResult:
        """Run a shadow rehearsal for the given task.

        Composes: planner → decomposition review → router → context compiler
        → permission compiler → team assembly → integrator → verifier
        → conflict handler → evidence manager → escalator.

        All steps are advisory. No production dispatch occurs.
        """
        rehearsal_id = generate_id("rehearsal")
        result = ShadowRehearsalResult(rehearsal_id, objective)

        # Step 1: Plan
        plan = self.planner.plan(objective, fingerprint)
        result.plan = plan

        # Step 2: Build DAG
        dag = self.planner.build_dag(plan)
        result.dag = dag

        # Step 3: Decomposition review
        review = self.decomposition_reviewer.review(plan, dag)
        result.decomposition_review = review

        if not review.approved:
            result.warnings.append(
                f"Decomposition rejected: {review.structural_issues}"
            )
            result.outcome = "REJECTED_DECOMPOSITION"
            result.completed_at = datetime.utcnow().isoformat()
            return result

        # Step 4: Route — propose candidates for each node
        if self.router:
            for node in plan["nodes"]:
                node_id = node.get("node_id", f"node-{plan['nodes'].index(node)}")
                candidates = self.router.propose_candidates(
                    node, fingerprint.task_family, fingerprint
                )
                result.candidates_by_node[node_id] = candidates

        # Step 5: Compile context packages
        contract = WorkerContract(
            objective=objective,
            verification_method=fingerprint.verification_type or "test",
        )
        for i, node in enumerate(plan["nodes"]):
            node_id = node.get("node_id", f"node-{i+1}")
            upstream = None
            if i > 0:
                prev_node_id = plan["nodes"][i-1].get("node_id", f"node-{i}")
                upstream = {prev_node_id: {"artifact": f"output-{prev_node_id}"}}

            ctx = self.context_compiler.compile(
                node["objective"],
                contract,
                upstream_outputs=upstream,
                constraints=[f"risk_class={fingerprint.risk_class}"] if fingerprint.risk_class else [],
            )
            result.context_packages[node_id] = ctx

        # Step 6: Compile permission packages
        for i, node in enumerate(plan["nodes"]):
            node_id = node.get("node_id", f"node-{i+1}")
            roles = node.get("capability_roles", ["builder"])
            perms = self.permission_compiler.compile_permissions(roles)
            result.permission_packages[node_id] = perms

        # Step 7: Assemble team
        if self.capability_registry:
            assembler = TeamAssembler(self.capability_registry, self.router)
            assembly = assembler.assemble_team(
                plan,
                candidates_by_node=result.candidates_by_node,
                require_all_nodes=True,
            )
            result.team_assembly = assembly

            if not assembly.complete:
                result.warnings.append(
                    f"Team incomplete: {assembly.issues}"
                )

        # Step 8: Simulate outputs (shadow)
        simulated = simulate_outputs or self._simulate_outputs(plan, dag)

        # Step 9: Integrate
        integration_result = self.integrator.integrate(
            objective,
            simulated,
            original_requirements={"expected_outputs": {"status": "", "artifact": ""}},
        )

        if integration_result.has_blocking_issues():
            result.warnings.append(
                f"Integration blocking issues: {[i.description for i in integration_result.issues if i.severity == 'high']}"
            )

        # Step 10: Verify
        if fingerprint.verification_type:
            try:
                method = VerificationMethod(fingerprint.verification_type)
            except ValueError:
                method = VerificationMethod.TEST
        else:
            method = VerificationMethod.TEST

        verification = self.verifier.verify(
            integration_result.integrated_output or {},
            method=method,
        )
        result.verification_results["integration"] = {
            "method": verification.method.value,
            "outcome": verification.outcome.value,
            "issues": verification.issues,
            "passed": verification.passed,
        }

        # Step 11: Conflict detection
        simulated_items = list(simulated.items())
        for i, (key_a, val_a) in enumerate(simulated_items):
            for key_b, val_b in simulated_items[i+1:]:
                conflict = self.conflict_handler.detect_conflict(
                    key_a, val_a, key_b, val_b
                )
                if conflict:
                    result.conflicts_detected.append({
                        "conflict_id": conflict.conflict_id,
                        "type": conflict.conflict_type,
                        "node_a": conflict.node_a,
                        "node_b": conflict.node_b,
                        "disputed_claim": conflict.disputed_claim,
                    })

        # Step 12: Evidence recording
        for i, node in enumerate(plan["nodes"]):
            node_id = node.get("node_id", f"node-{i+1}")
            roles = node.get("capability_roles", ["builder"])
            worker_id = "unassigned"
            if result.team_assembly:
                for a in result.team_assembly.assignments:
                    if a.node_id == node_id:
                        worker_id = a.worker_id
                        break

            evidence = EvidenceRecord(
                worker_id=worker_id,
                task_fingerprint=fingerprint,
                role=roles[0] if roles else "builder",
                provider="shadow",
                model="shadow-rehearsal",
            )
            evidence.first_pass_success = verification.passed
            evidence.final_success = verification.passed
            evidence.verification_outcome = verification.outcome.value
            evidence_id = self.evidence_manager.record_evidence(evidence)
            result.evidence_records.append(evidence_id)

        # Step 13: Exploration evaluation (shadow rules)
        if fingerprint.risk_class and fingerprint.risk_class in ("R0", "R1"):
            explore_req = ExplorationRequest(
                task_id=result.rehearsal_id,
                candidate_worker_id="explorer-shadow",
                primary_worker_id="primary-shadow",
                task_family=fingerprint.task_family,
                risk_class=fingerprint.risk_class,
                expected_cost_ratio=1.1,
            )
            explore_decision = self.exploration_rules.evaluate(explore_req)
            result.exploration_decisions.append({
                "approved": explore_decision.approved,
                "reason": explore_decision.reason,
            })

        # Step 14: Shadow evaluation check
        if fingerprint.verification_type == "deterministic":
            can_shadow = self.shadow_evaluator.can_shadow(
                fingerprint.risk_class or "R1",
                has_deterministic_verification=True,
            )
            result.exploration_decisions.append({
                "shadow_eligible": can_shadow,
                "reason": "Deterministic verification available" if can_shadow else "No deterministic verification",
            })

        # Step 15: Replan check
        if verification.outcome == VerificationOutcome.FAIL:
            if self.replanner.can_replan():
                replan_record = self.replanner.replan(
                    dag,
                    ReplanTrigger.ASSUMPTION_INVALIDATED,
                    "Shadow rehearsal verification failed — replan suggested",
                )
                if replan_record:
                    result.replan_history.append(replan_record.record_id)
                    result.warnings.append("Replanner suggested a new plan (shadow)")
            else:
                result.warnings.append("Replan depth exhausted (shadow)")

        # Final outcome
        if result.conflicts_detected:
            result.outcome = "REHEARSAL_CONFLICTS"
        elif not result.verification_results.get("integration", {}).get("passed", False):
            result.outcome = "REHEARSAL_VERIFICATION_FAILED"
        elif result.team_assembly and not result.team_assembly.complete:
            result.outcome = "REHEARSAL_TEAM_INCOMPLETE"
        else:
            result.outcome = "REHEARSAL_PASSED"

        result.completed_at = datetime.utcnow().isoformat()
        return result

    def _simulate_outputs(self, plan: Dict[str, Any], dag: ExecutionDAG) -> Dict[str, Any]:
        """Generate synthetic outputs for shadow rehearsal."""
        outputs = {}
        for node in plan["nodes"]:
            node_id = node.get("node_id", "unknown")
            objective = node.get("objective", "")
            outputs[node_id] = {
                "status": "simulated",
                "artifact": f"shadow-{node_id}",
                "objective": objective,
                "timestamp": datetime.utcnow().isoformat(),
            }
        return outputs

    def get_readiness_report(self) -> Dict[str, Any]:
        """Get a readiness report for all workers."""
        workers = self.worker_registry.get_all_workers()
        readiness = {}
        for wid, w in workers.items():
            cap_state = "UNPROVEN"
            if self.capability_registry:
                cap = self.capability_registry.get_capability(wid, w["provider"], "builder")
                cap_state = cap["state"]
            readiness[wid] = {
                "provider": w["provider"],
                "model": w["model"],
                "routable": w.get("routable", False),
                "capability_state": cap_state,
                "smoke_test": w.get("smoke_test", "NOT_RUN"),
                "pool_status": w.get("pool_status", "UNKNOWN"),
            }
        return readiness
