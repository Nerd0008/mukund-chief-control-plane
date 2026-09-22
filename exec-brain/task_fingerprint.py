#!/usr/bin/env python3
"""E3 Task Fingerprinting — machine-readable task characterization."""

import hashlib
import json
from datetime import datetime


TASK_FAMILIES = [
    'code', 'review', 'research', 'analysis', 'writing',
    'data-processing', 'ops', 'monitoring', 'decision-support',
    'extraction', 'summarization', 'verification', 'other'
]

REASONING_DEPTHS = [0, 1, 2, 3, 4]

AMBIGUITY_LEVELS = ['low', 'medium', 'high']

TOOL_INTENSITY_LEVELS = ['none', 'light', 'heavy']

RISK_CLASSES = ['R0', 'R1', 'R2', 'R3']

PRIVACY_CLASSES = ['P0', 'P1', 'P2', 'P3']

VERIFICATION_TYPES = ['deterministic', 'critic', 'owner']

FRESHNESS_LEVELS = ['stale-tolerant', 'current-required']

INTEGRITY_LEVELS = ['none', 'low', 'medium', 'high']


class TaskFingerprint:
    """Represents a machine-readable task fingerprint."""

    def __init__(self, task_family, domain=None, language=None,
                 artifact_type=None, repository_size=None, context_size=None,
                 reasoning_depth=None, ambiguity=None, tool_intensity=None,
                 required_roles=None, security_privacy_class=None,
                 risk_class=None, verification_type=None,
                 research_freshness=None, integration_complexity=None):
        self.task_family = task_family
        self.domain = domain
        self.language = language
        self.artifact_type = artifact_type
        self.repository_size = repository_size
        self.context_size = context_size
        self.reasoning_depth = reasoning_depth
        self.ambiguity = ambiguity
        self.tool_intensity = tool_intensity
        self.required_roles = required_roles or []
        self.security_privacy_class = security_privacy_class
        self.risk_class = risk_class
        self.verification_type = verification_type
        self.research_freshness = research_freshness
        self.integration_complexity = integration_complexity

    def to_dict(self):
        """Convert fingerprint to dictionary."""
        return {
            'task_family': self.task_family,
            'domain': self.domain,
            'language': self.language,
            'artifact_type': self.artifact_type,
            'repository_size': self.repository_size,
            'context_size': self.context_size,
            'reasoning_depth': self.reasoning_depth,
            'ambiguity': self.ambiguity,
            'tool_intensity': self.tool_intensity,
            'required_roles': self.required_roles,
            'security_privacy_class': self.security_privacy_class,
            'risk_class': self.risk_class,
            'verification_type': self.verification_type,
            'research_freshness': self.research_freshness,
            'integration_complexity': self.integration_complexity
        }

    def to_json(self):
        """Convert fingerprint to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    def compute_hash(self):
        """Compute a stable hash of this fingerprint."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    def validate(self):
        """Validate fingerprint fields."""
        errors = []
        if self.task_family and self.task_family not in TASK_FAMILIES:
            errors.append(f"Invalid task_family: {self.task_family}")
        if self.reasoning_depth is not None and self.reasoning_depth not in REASONING_DEPTHS:
            errors.append(f"Invalid reasoning_depth: {self.reasoning_depth}")
        if self.ambiguity and self.ambiguity not in AMBIGUITY_LEVELS:
            errors.append(f"Invalid ambiguity: {self.ambiguity}")
        if self.tool_intensity and self.tool_intensity not in TOOL_INTENSITY_LEVELS:
            errors.append(f"Invalid tool_intensity: {self.tool_intensity}")
        if self.risk_class and self.risk_class not in RISK_CLASSES:
            errors.append(f"Invalid risk_class: {self.risk_class}")
        if self.security_privacy_class and self.security_privacy_class not in PRIVACY_CLASSES:
            errors.append(f"Invalid security_privacy_class: {self.security_privacy_class}")
        if self.verification_type and self.verification_type not in VERIFICATION_TYPES:
            errors.append(f"Invalid verification_type: {self.verification_type}")
        if self.research_freshness and self.research_freshness not in FRESHNESS_LEVELS:
            errors.append(f"Invalid research_freshness: {self.research_freshness}")
        if self.integration_complexity and self.integration_complexity not in INTEGRITY_LEVELS:
            errors.append(f"Invalid integration_complexity: {self.integration_complexity}")
        return errors


def compute_similarity(fp1, fp2):
    """Compute similarity score between two fingerprints.
    
    Returns a score between 0.0 (completely different) and 1.0 (identical).
    Uses weighted dimension matching.
    """
    score = 0.0
    max_score = 0.0

    # Task family (weight: 3) — always compared
    max_score += 3
    if fp1.task_family == fp2.task_family:
        score += 3

    # Reasoning depth (weight: 2, partial match for adjacent)
    if fp1.reasoning_depth is not None or fp2.reasoning_depth is not None:
        max_score += 2
        if fp1.reasoning_depth is not None and fp2.reasoning_depth is not None:
            if fp1.reasoning_depth == fp2.reasoning_depth:
                score += 2
            elif abs(fp1.reasoning_depth - fp2.reasoning_depth) == 1:
                score += 1

    # Tool intensity (weight: 2) — only if at least one has value
    if fp1.tool_intensity or fp2.tool_intensity:
        max_score += 2
        if fp1.tool_intensity and fp2.tool_intensity:
            if fp1.tool_intensity == fp2.tool_intensity:
                score += 2
            elif (fp1.tool_intensity == 'light' and fp2.tool_intensity == 'heavy') or \
                 (fp1.tool_intensity == 'heavy' and fp2.tool_intensity == 'light'):
                score += 1

    # Risk class (weight: 2, partial for adjacent) — only if at least one has value
    if fp1.risk_class or fp2.risk_class:
        max_score += 2
        if fp1.risk_class and fp2.risk_class:
            r1 = RISK_CLASSES.index(fp1.risk_class) if fp1.risk_class in RISK_CLASSES else -1
            r2 = RISK_CLASSES.index(fp2.risk_class) if fp2.risk_class in RISK_CLASSES else -1
            if r1 == r2:
                score += 2
            elif abs(r1 - r2) == 1:
                score += 1

    # Ambiguity (weight: 1) — only if at least one has value
    if fp1.ambiguity or fp2.ambiguity:
        max_score += 1
        if fp1.ambiguity == fp2.ambiguity:
            score += 1

    # Required roles overlap (weight: 3) — only if at least one has value
    if fp1.required_roles or fp2.required_roles:
        max_score += 3
        set1 = set(fp1.required_roles) if fp1.required_roles else set()
        set2 = set(fp2.required_roles) if fp2.required_roles else set()
        if set1 or set2:
            overlap = len(set1 & set2)
            union = len(set1 | set2)
            if union > 0:
                score += 3 * (overlap / union)

    if max_score == 0:
        return 0.0
    return score / max_score
