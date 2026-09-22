#!/usr/bin/env python3
"""E3 Qualification Gate — deterministic worker proposal validation."""

from enum import Enum

class GateResult(Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    EVALUATION_ONLY = "EVALUATION_ONLY"
    OWNER_APPROVAL_REQUIRED = "OWNER_APPROVAL_REQUIRED"

class RejectionReason(Enum):
    FLOOR_REASONING_TOO_LOW = "FLOOR_REASONING_TOO_LOW"
    FLOOR_VERIFICATION_TOO_LOW = "FLOOR_VERIFICATION_TOO_LOW"
    WORKER_SUSPENDED = "WORKER_SUSPENDED"
    WORKER_UNPROVEN_ON_HIGH_RISK = "WORKER_UNPROVEN_ON_HIGH_RISK"
    PROVIDER_NOT_ROUTABLE = "PROVIDER_NOT_ROUTABLE"
    PROVIDER_CAPACITY_UNKNOWN = "PROVIDER_CAPACITY_UNKNOWN"
    EGRESS_VIOLATION = "EGRESS_VIOLATION"
    TOOL_SUPPORT_INSUFFICIENT = "TOOL_SUPPORT_INSUFFICIENT"
    CONTEXT_WINDOW_INSUFFICIENT = "CONTEXT_WINDOW_INSUFFICIENT"
    OWNER_POLICY_REJECTION = "OWNER_POLICY_REJECTION"


class QualificationGate:
    """Validates worker proposals against the frozen floor."""

    def __init__(self, capability_registry, e2_provider_state=None):
        self.registry = capability_registry
        self.e2_state = e2_provider_state or {}

    def validate_proposal(self, proposal, floor, risk_class='R0'):
        """Validate a worker proposal against the floor.
        
        Returns (GateResult, list_of_reasons).
        """
        reasons = []

        # Check worker capability state
        worker_id = proposal.get('worker_id')
        role = proposal.get('role', 'builder')
        task_family = floor.get('task_family', 'general')

        capability = self.registry.get_capability(worker_id, task_family, role)
        state = capability['state']

        if state == 'SUSPENDED':
            reasons.append(RejectionReason.WORKER_SUSPENDED.value)

        elif state == 'UNPROVEN' and risk_class in ('R2', 'R3'):
            reasons.append(RejectionReason.WORKER_UNPROVEN_ON_HIGH_RISK.value)

        elif state == 'UNPROVEN' and risk_class in ('R0', 'R1'):
            # Allow evaluation-only for low-risk
            pass

        # Check provider routable state
        provider = proposal.get('provider')
        if provider and not self._is_provider_routable(provider):
            reasons.append(RejectionReason.PROVIDER_NOT_ROUTABLE.value)

        # Check E2 capacity state
        capacity_confidence = self._get_capacity_confidence(provider)
        if capacity_confidence == 'UNKNOWN' and risk_class in ('R2', 'R3'):
            reasons.append(RejectionReason.PROVIDER_CAPACITY_UNKNOWN.value)

        # Check reasoning depth
        min_reasoning = floor.get('min_reasoning_depth', 0)
        worker_reasoning = proposal.get('reasoning_level', 0)
        if isinstance(worker_reasoning, int) and worker_reasoning < min_reasoning:
            reasons.append(RejectionReason.FLOOR_REASONING_TOO_LOW.value)

        # Check verification level
        min_verification = floor.get('min_verification', 'V0')
        # Simplified check - in real impl would compare V-levels

        # Check tool support
        required_tools = floor.get('required_tools', [])
        supported_tools = proposal.get('supported_tools', [])
        missing = [t for t in required_tools if t not in supported_tools]
        if missing:
            reasons.append(RejectionReason.TOOL_SUPPORT_INSUFFICIENT.value)

        # Determine result
        if reasons:
            return GateResult.REJECT, reasons
        elif state == 'UNPROVEN':
            return GateResult.EVALUATION_ONLY, []
        else:
            return GateResult.ACCEPT, []

    def _is_provider_routable(self, provider):
        """Check if a provider is currently routable."""
        # In real impl, would check E2 telemetry
        return provider in self.e2_state

    def _get_capacity_confidence(self, provider):
        """Get capacity confidence for a provider."""
        if not provider:
            return 'UNKNOWN'
        return self.e2_state.get(provider, {}).get('capacity_confidence', 'UNKNOWN')
