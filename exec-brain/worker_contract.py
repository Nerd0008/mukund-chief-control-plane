#!/usr/bin/env python3
"""E3 Worker Contract — structured worker assignments."""

import uuid
from datetime import datetime


def generate_id(prefix=''):
    """Generate a unique ID."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class WorkerContract:
    """Structured contract for worker assignments."""

    def __init__(self, objective, relevant_inputs=None,
                 required_output_schema=None, constraints=None,
                 quality_floor_reference=None, allowed_tools=None,
                 permission_scope=None, verification_method=None,
                 definition_of_done=None):
        self.contract_id = generate_id('contract')
        self.objective = objective
        self.relevant_inputs = relevant_inputs or {}
        self.required_output_schema = required_output_schema or {}
        self.constraints = constraints or []
        self.quality_floor_reference = quality_floor_reference
        self.allowed_tools = allowed_tools or []
        self.permission_scope = permission_scope or {}
        self.verification_method = verification_method or 'test'
        self.definition_of_done = definition_of_done or ''
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self):
        """Convert contract to dictionary."""
        return {
            'contract_id': self.contract_id,
            'objective': self.objective,
            'relevant_inputs': self.relevant_inputs,
            'required_output_schema': self.required_output_schema,
            'constraints': self.constraints,
            'quality_floor_reference': self.quality_floor_reference,
            'allowed_tools': self.allowed_tools,
            'permission_scope': self.permission_scope,
            'verification_method': self.verification_method,
            'definition_of_done': self.definition_of_done,
            'created_at': self.created_at
        }

    def validate(self):
        """Validate the contract has required fields."""
        errors = []
        if not self.objective:
            errors.append("objective is required")
        if self.verification_method not in ('test', 'schema', 'comparison', 'critic', 'owner'):
            errors.append(f"Invalid verification_method: {self.verification_method}")
        return errors
