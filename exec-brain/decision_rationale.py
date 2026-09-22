#!/usr/bin/env python3
"""E3 Decision Rationale — append-only decision audit trail."""

import uuid
from datetime import datetime

DECISION_TYPES = [
    'decomposition', 'decomposition_rejection', 'router_team_selection',
    'worker_selection', 'integration_decision', 'conflict_resolution',
    'targeted_rework', 'replanning', 'critic_conclusion',
    'verifier_conclusion', 'escalation'
]

CONFIDENCE_LEVELS = ['HIGH', 'MEDIUM', 'LOW']

GATE_RESULTS = ['ACCEPT', 'REJECT', 'EVALUATION_ONLY', 'OWNER_APPROVAL_REQUIRED']


def generate_id(prefix=''):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class DecisionRationale:
    """Represents a structured decision rationale record."""

    def __init__(self, task_id, decision_type, decision_actor,
                 objective, chosen_action, plan_id=None, node_id=None,
                 provider=None, model=None, model_identity=None):
        self.rationale_id = generate_id('rationale')
        self.task_id = task_id
        self.plan_id = plan_id
        self.node_id = node_id
        self.decision_type = decision_type
        self.decision_actor = decision_actor
        self.provider = provider or 'unknown'
        self.model = model or 'unknown'
        self.model_identity = model_identity
        self.timestamp = datetime.utcnow().isoformat()
        self.objective = objective
        self.chosen_action = chosen_action
        self.alternatives_considered = []
        self.alternative_rejections = []
        self.decisive_factors = {}
        self.evidence_references = []
        self.assumptions = []
        self.uncertainties = []
        self.confidence = 'MEDIUM'
        self.confidence_justification = ''
        self.expected_tradeoffs = {}
        self.gate_result = 'ACCEPT'
        self.next_verification = ''
        self.rationale_codes = []
        self.concise_rationale = ''

    def to_dict(self):
        return {
            'rationale_id': self.rationale_id,
            'task_id': self.task_id,
            'plan_id': self.plan_id,
            'node_id': self.node_id,
            'decision_type': self.decision_type,
            'decision_actor': self.decision_actor,
            'provider': self.provider,
            'model': self.model,
            'model_identity': self.model_identity,
            'timestamp': self.timestamp,
            'objective': self.objective,
            'chosen_action': self.chosen_action,
            'alternatives_considered': self.alternatives_considered,
            'alternative_rejections': self.alternative_rejections,
            'decisive_factors': self.decisive_factors,
            'evidence_references': self.evidence_references,
            'assumptions': self.assumptions,
            'uncertainties': self.uncertainties,
            'confidence': self.confidence,
            'confidence_justification': self.confidence_justification,
            'expected_tradeoffs': self.expected_tradeoffs,
            'gate_result': self.gate_result,
            'next_verification': self.next_verification,
            'rationale_codes': self.rationale_codes,
            'concise_rationale': self.concise_rationale
        }

    def validate(self):
        errors = []
        if self.decision_type not in DECISION_TYPES:
            errors.append(f"Invalid decision_type: {self.decision_type}")
        if self.confidence not in CONFIDENCE_LEVELS:
            errors.append(f"Invalid confidence: {self.confidence}")
        if self.gate_result not in GATE_RESULTS:
            errors.append(f"Invalid gate_result: {self.gate_result}")
        if not self.objective:
            errors.append("objective is required")
        if not self.chosen_action:
            errors.append("chosen_action is required")
        if not self.concise_rationale:
            errors.append("concise_rationale is required (A7 privacy)")
        return errors


class DecisionOutcomeReview:
    """Represents an after-the-fact outcome review."""

    def __init__(self, rationale_id, plan_id=None, node_id=None):
        self.review_id = generate_id('review')
        self.rationale_id = rationale_id
        self.plan_id = plan_id
        self.node_id = node_id
        self.actual_outcome = None
        self.first_pass_success = None
        self.verification_result = None
        self.corrections_required = 0
        self.failure_attribution = None
        self.decision_quality = None
        self.lessons = ''
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            'review_id': self.review_id,
            'rationale_id': self.rationale_id,
            'plan_id': self.plan_id,
            'node_id': self.node_id,
            'actual_outcome': self.actual_outcome,
            'first_pass_success': self.first_pass_success,
            'verification_result': self.verification_result,
            'corrections_required': self.corrections_required,
            'failure_attribution': self.failure_attribution,
            'decision_quality': self.decision_quality,
            'lessons': self.lessons,
            'timestamp': self.timestamp
        }
