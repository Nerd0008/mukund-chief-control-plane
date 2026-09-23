#!/usr/bin/env python3
"""E3 Router — deterministic meta-selector + AI team assembly advisory.

Router is a capability role (D-AI-2). A worker may be selected as router
if qualified for the 'router' role. Proposals are advisory; the
Qualification Gate decides.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from capability_registry import CapabilityRegistry
from decision_rationale import DecisionRationale


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class RouterCandidate:
    """A candidate worker proposal for a node."""

    def __init__(self, worker_id: str, provider: str, model: str,
                 role: str, confidence: str, reasoning_codes: Optional[List[str]],
                 concise_rationale: str, evidence_references: Optional[List[str]] = None):
        self.worker_id = worker_id
        self.provider = provider
        self.model = model
        self.role = role
        self.confidence = confidence
        self.reasoning_codes = reasoning_codes if reasoning_codes is not None else []
        self.concise_rationale = concise_rationale
        self.evidence_references = evidence_references if evidence_references is not None else []


class MetaSelector:
    """Deterministic meta-selector: chooses which worker acts as router."""

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def select_router(self, task_family: str, required_role: str = "router") -> Optional[str]:
        """Select a qualified router worker. Returns worker_id or None."""
        qualified = self.registry.find_qualified_workers(task_family, required_role)
        if qualified:
            return qualified[0]
        return None


class E3Router:
    """Propose candidate workers for each node in a plan."""

    def __init__(self, registry: CapabilityRegistry, worker_registry: Any = None,
                 e2_provider_state: Optional[Dict] = None):
        self.registry = registry
        self.worker_registry = worker_registry
        self.e2_state = e2_provider_state if e2_provider_state is not None else {}
        self.meta_selector = MetaSelector(registry)

    def propose_candidates(self, node: Dict[str, Any], task_family: str,
                          task_fingerprint: Any = None,
                          historical_evidence: Optional[List[Dict]] = None) -> List[RouterCandidate]:
        """Generate multiple candidate worker proposals for a node."""
        candidates: List[RouterCandidate] = []
        required_roles = node.get("capability_roles", ["builder"])
        historical_evidence = historical_evidence if historical_evidence is not None else []

        for role in required_roles:
            eligible = self.registry.find_eligible_workers(task_family, role, risk_class="R1")
            for entry in eligible:
                wid = entry["worker_id"]
                state = entry["state"]
                confidence = self._compute_confidence(wid, task_family, state, historical_evidence)
                reasoning_codes = self._build_reasoning_codes(wid, task_family, state, historical_evidence)
                rationale = self._build_rationale(wid, task_family, state, historical_evidence)
                evidence_refs = [e.get("evidence_id", "") for e in historical_evidence if e.get("worker_id") == wid]

                candidates.append(RouterCandidate(
                    worker_id=wid,
                    provider=self._get_provider(wid),
                    model=self._get_model(wid),
                    role=role,
                    confidence=confidence,
                    reasoning_codes=reasoning_codes,
                    concise_rationale=rationale,
                    evidence_references=evidence_refs,
                ))

        confidence_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        candidates.sort(key=lambda c: confidence_order.get(c.confidence, 3))
        return candidates

    def _compute_confidence(self, worker_id: str, task_family: str,
                            state: str, historical: List[Dict]) -> str:
        if state == "QUALIFIED":
            relevant = [e for e in historical if e.get("worker_id") == worker_id and e.get("first_pass_success")]
            if relevant:
                return "HIGH"
            return "MEDIUM"
        elif state == "EVALUATING":
            return "LOW"
        return "LOW"

    def _build_reasoning_codes(self, worker_id: str, task_family: str,
                               state: str, historical: List[Dict]) -> List[str]:
        codes: List[str] = []
        if state == "QUALIFIED":
            codes.append("QUALIFIED_WORKER")
        elif state == "EVALUATING":
            codes.append("EVALUATION_ONLY")

        relevant = [e for e in historical if e.get("worker_id") == worker_id]
        if relevant:
            success_rate = sum(1 for e in relevant if e.get("first_pass_success")) / len(relevant)
            if success_rate >= 0.8:
                codes.append("STRONG_EVIDENCE")
            elif success_rate >= 0.5:
                codes.append("MODERATE_EVIDENCE")
            else:
                codes.append("WEAK_EVIDENCE")

        provider = self._get_provider(worker_id)
        if provider and provider in self.e2_state:
            provider_state = self.e2_state[provider]
            if provider_state.get("capacity_confidence") == "HEALTHY":
                codes.append("PROVIDER_HEALTHY")
            elif provider_state.get("capacity_confidence") == "UNKNOWN":
                codes.append("PROVIDER_UNKNOWN")
        return codes

    def _build_rationale(self, worker_id: str, task_family: str,
                         state: str, historical: List[Dict]) -> str:
        parts: List[str] = []
        if state == "QUALIFIED":
            parts.append(f"Worker {worker_id} is QUALIFIED for {task_family}")
        elif state == "EVALUATING":
            parts.append(f"Worker {worker_id} is EVALUATING for {task_family}")

        relevant = [e for e in historical if e.get("worker_id") == worker_id]
        if relevant:
            successes = sum(1 for e in relevant if e.get("first_pass_success"))
            parts.append(f"Evidence: {successes}/{len(relevant)} first-pass successes")
        return "; ".join(parts)

    def _get_provider(self, worker_id: str) -> str:
        return "unknown"

    def _get_model(self, worker_id: str) -> str:
        return "unknown"

    def create_router_decision(self, plan_id: str, node_id: str,
                               candidate: RouterCandidate) -> Dict[str, Any]:
        """Create a router decision record."""
        return {
            "decision_id": generate_id("router-dec"),
            "plan_id": plan_id,
            "node_id": node_id,
            "proposed_worker": candidate.worker_id,
            "proposed_role": candidate.role,
            "confidence": candidate.confidence,
            "reasoning_codes": candidate.reasoning_codes,
            "evidence_references": candidate.evidence_references,
            "concise_rationale": candidate.concise_rationale,
            "gate_decision": None,
            "gate_reasons": None,
            "actual_outcome": None,
            "outcome_matches_proposal": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
