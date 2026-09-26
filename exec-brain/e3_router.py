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
                 concise_rationale: str, evidence_references: Optional[List[str]] = None,
                 score: float = 0.0, score_components: Optional[Dict[str, float]] = None):
        self.worker_id = worker_id
        self.provider = provider
        self.model = model
        self.role = role
        self.confidence = confidence
        self.reasoning_codes = reasoning_codes if reasoning_codes is not None else []
        self.concise_rationale = concise_rationale
        self.evidence_references = evidence_references if evidence_references is not None else []
        self.score = float(score)
        self.score_components = dict(score_components or {})


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
                # A capability row alone is not enough for production routing:
                # the static worker registry remains the execution-readiness source.
                worker = self._worker_record(wid)
                if worker is not None and not worker.get("routable", False):
                    continue

                confidence = self._compute_confidence(wid, task_family, state, historical_evidence)
                reasoning_codes = self._build_reasoning_codes(wid, task_family, state, historical_evidence)
                evidence_refs = [e.get("evidence_id", "") for e in historical_evidence if e.get("worker_id") == wid]
                score, components = self._score_candidate(
                    wid, task_family, role, state, historical_evidence)
                rationale = self._build_rationale(
                    wid, task_family, state, historical_evidence,
                    score=score, score_components=components)

                candidates.append(RouterCandidate(
                    worker_id=wid,
                    provider=self._get_provider(wid),
                    model=self._get_model(wid),
                    role=role,
                    confidence=confidence,
                    reasoning_codes=reasoning_codes,
                    concise_rationale=rationale,
                    evidence_references=evidence_refs,
                    score=score,
                    score_components=components,
                ))

        # Deterministic evidence/task-fit ordering.  Worker id is only the final
        # tie-break so insertion/SQL row order can never make one model "sticky".
        candidates.sort(key=lambda c: (-c.score, c.worker_id, c.role))
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

    def _worker_record(self, worker_id: str) -> Optional[Dict[str, Any]]:
        if self.worker_registry is None:
            return None
        try:
            return self.worker_registry.get_worker(worker_id)
        except Exception:
            return None

    @staticmethod
    def _fit_terms(task_family: str, role: str) -> List[str]:
        family_terms = {
            "code": ["coding", "repository", "debugging", "implementation", "reasoning"],
            "review": ["debugging", "reasoning", "coding"],
            "research": ["reasoning", "long-context", "agents"],
            "analysis": ["reasoning", "long-context", "data-analyst"],
            "writing": ["reasoning", "long-context", "writer"],
            "data-processing": ["data-analyst", "reasoning", "coding"],
            "ops": ["agents", "tool-use", "reasoning", "coding"],
            "monitoring": ["agents", "high-volume", "fast"],
            "decision-support": ["reasoning", "long-context"],
            "extraction": ["long-context", "reasoning", "vision"],
            "summarization": ["long-context", "reasoning"],
            "verification": ["critic", "debugging", "reasoning"],
            "other": ["reasoning", "agents"],
        }
        role_terms = {
            "builder": ["coding", "implementation", "reasoning", "agents"],
            "writer": ["writer", "reasoning", "long-context"],
            "researcher": ["reasoning", "long-context", "agents"],
            "critic": ["critic", "debugging", "reasoning"],
            "verifier": ["critic", "debugging", "reasoning"],
            "vision": ["vision", "image-generation", "image-editing", "multimodal"],
            "data-analyst": ["data-analyst", "reasoning"],
            "integrator": ["reasoning", "long-context", "agents"],
            "router": ["reasoning", "agents", "fast"],
        }
        return list(dict.fromkeys(
            family_terms.get(task_family, ["reasoning"]) +
            role_terms.get(role, ["reasoning"])
        ))

    def _score_candidate(self, worker_id: str, task_family: str, role: str,
                         state: str, historical: List[Dict]) -> Tuple[float, Dict[str, float]]:
        worker = self._worker_record(worker_id) or {}
        hints = set(worker.get("capability_hints") or [])
        wanted = self._fit_terms(task_family, role)

        state_score = {"QUALIFIED": 40.0, "EVALUATING": 18.0}.get(state, 0.0)
        readiness_score = 20.0 if worker.get("routable") else 0.0
        fit_matches = sum(1 for term in wanted if term in hints)
        fit_score = min(24.0, float(fit_matches * 6))

        relevant = [e for e in historical if e.get("worker_id") == worker_id]
        evidence_score = 0.0
        if relevant:
            first_pass = sum(1 for e in relevant if e.get("first_pass_success"))
            evidence_score = min(10.0, 10.0 * first_pass / len(relevant))

        health_score = 0.0
        provider = self._get_provider(worker_id)
        pstate = self.e2_state.get(provider, {}) if provider else {}
        health = pstate.get("capacity_confidence") or pstate.get("status")
        if health in ("HEALTHY", "healthy", "READY", "ready"):
            health_score = 6.0
        elif health in ("DEGRADED", "degraded"):
            health_score = -4.0
        elif health in ("BLOCKED", "blocked", "UNHEALTHY", "unhealthy"):
            health_score = -20.0

        components = {
            "capability_state": state_score,
            "execution_readiness": readiness_score,
            "task_fit": fit_score,
            "historical_evidence": evidence_score,
            "provider_health": health_score,
        }
        return sum(components.values()), components

    def _build_rationale(self, worker_id: str, task_family: str,
                         state: str, historical: List[Dict],
                         score: Optional[float] = None,
                         score_components: Optional[Dict[str, float]] = None) -> str:
        parts: List[str] = []
        if state == "QUALIFIED":
            parts.append(f"Worker {worker_id} is QUALIFIED for {task_family}")
        elif state == "EVALUATING":
            parts.append(f"Worker {worker_id} is EVALUATING for {task_family}")

        worker = self._worker_record(worker_id) or {}
        hints = worker.get("capability_hints") or []
        if hints:
            parts.append("hints=" + ",".join(sorted(hints)))

        relevant = [e for e in historical if e.get("worker_id") == worker_id]
        if relevant:
            successes = sum(1 for e in relevant if e.get("first_pass_success"))
            parts.append(f"evidence={successes}/{len(relevant)} first-pass")
        if score is not None:
            parts.append(f"score={score:.1f}")
        if score_components:
            parts.append("components=" + ",".join(
                f"{k}:{v:.1f}" for k, v in sorted(score_components.items())))
        return "; ".join(parts)

    def _get_provider(self, worker_id: str) -> str:
        worker = self._worker_record(worker_id)
        return str(worker.get("provider")) if worker and worker.get("provider") else "unknown"

    def _get_model(self, worker_id: str) -> str:
        worker = self._worker_record(worker_id)
        if not worker:
            return "unknown"
        return str(worker.get("api_model_id") or worker.get("model") or "unknown")

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
