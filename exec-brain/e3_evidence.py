#!/usr/bin/env python3
"""E3 Evidence Manager — record performance evidence for each worker assignment."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class FailureAttribution(Enum):
    PLANNING = "planning"
    DECOMPOSITION = "decomposition"
    FACTUAL_ERROR = "factual_error"
    REASONING = "reasoning"
    IMPLEMENTATION = "implementation"
    TOOL_USE = "tool_use"
    CONTEXT = "context"
    INTEGRATION = "integration"
    VERIFICATION_MISS = "verification_miss"
    ENVIRONMENT = "environment"
    EXTERNAL_DEPENDENCY = "external_dependency"


class EvidenceRecord:
    def __init__(self, worker_id: str, task_fingerprint: Any, role: str,
                 provider: str, model: str):
        self.evidence_id = generate_id("evidence")
        self.worker_id = worker_id
        self.task_fingerprint = task_fingerprint
        self.role = role
        self.model = model
        self.provider = provider
        self.reasoning_profile: Optional[str] = None
        self.execution_profile: Optional[str] = None
        self.tools: List[str] = []
        self.first_pass_success: Optional[bool] = None
        self.final_success: Optional[bool] = None
        self.verification_outcome: Optional[str] = None
        self.deterministic_test_results: Optional[Dict] = None
        self.retries: int = 0
        self.corrections: int = 0
        self.correction_severity: Optional[str] = None
        self.failure_attribution: Optional[str] = None
        self.runtime_s: Optional[int] = None
        self.usage_tokens: Optional[int] = None
        self.monetary_cost: Optional[float] = None
        self.floor_id: Optional[str] = None
        self.dag_node_id: Optional[str] = None
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "worker_id": self.worker_id,
            "task_fingerprint": self.task_fingerprint,
            "role": self.role,
            "model": self.model,
            "provider": self.provider,
            "first_pass_success": self.first_pass_success,
            "final_success": self.final_success,
            "verification_outcome": self.verification_outcome,
            "retries": self.retries,
            "corrections": self.corrections,
            "failure_attribution": self.failure_attribution,
            "timestamp": self.created_at,
        }


class E3EvidenceManager:
    def __init__(self, orchestration_con=None):
        self.con = orchestration_con
        self.evidence_cache: List[EvidenceRecord] = []

    def record_evidence(self, evidence: EvidenceRecord) -> str:
        self.evidence_cache.append(evidence)
        return evidence.evidence_id

    def record_outcome(self, evidence_id: str, first_pass_success: bool,
                       final_success: bool, verification_outcome: str,
                       failure_attribution: Optional[str] = None,
                       retries: int = 0, corrections: int = 0):
        for e in self.evidence_cache:
            if e.evidence_id == evidence_id:
                e.first_pass_success = first_pass_success
                e.final_success = final_success
                e.verification_outcome = verification_outcome
                e.failure_attribution = failure_attribution
                e.retries = retries
                e.corrections = corrections
                return

    def get_similar_evidence(self, task_fingerprint: Any,
                             worker_id: Optional[str] = None,
                             limit: int = 10) -> List[EvidenceRecord]:
        results = []
        for e in self.evidence_cache:
            if worker_id and e.worker_id != worker_id:
                continue
            if task_fingerprint and e.task_fingerprint == task_fingerprint:
                results.append(e)
            elif task_fingerprint is None:
                results.append(e)
        return results[:limit]

    def compute_first_pass_rate(self, worker_id: str,
                                task_fingerprint: Any = None) -> float:
        evidence_list = [e for e in self.evidence_cache if e.worker_id == worker_id]
        if task_fingerprint:
            evidence_list = [e for e in evidence_list if e.task_fingerprint == task_fingerprint]
        if not evidence_list:
            return 0.0
        successes = sum(1 for e in evidence_list if e.first_pass_success)
        return successes / len(evidence_list)

    def attribute_failure(self, evidence: EvidenceRecord,
                          category: FailureAttribution,
                          details: str = "") -> Dict[str, Any]:
        return {
            "evidence_id": evidence.evidence_id,
            "worker_id": evidence.worker_id,
            "category": category.value,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }
