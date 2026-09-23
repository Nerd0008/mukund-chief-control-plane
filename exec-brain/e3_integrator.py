#!/usr/bin/env python3
"""E3 Integrator — combine specialist outputs into unified deliverables."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class IntegrationIssue:
    def __init__(self, issue_type: str, description: str, severity: str,
                 affected_nodes: Optional[List[str]] = None):
        self.issue_type = issue_type
        self.description = description
        self.severity = severity
        self.affected_nodes = affected_nodes if affected_nodes is not None else []
        self.detected_at = datetime.utcnow().isoformat()


class IntegrationResult:
    def __init__(self, plan_id: str, integrated_output: Any = None):
        self.result_id = generate_id("integrate")
        self.plan_id = plan_id
        self.integrated_output = integrated_output
        self.issues: List[IntegrationIssue] = []
        self.missing_pieces: List[str] = []
        self.contradictions: List[Dict[str, Any]] = []
        self.created_at = datetime.utcnow().isoformat()
        self.complete = False

    def has_blocking_issues(self) -> bool:
        return any(i.severity == "high" for i in self.issues)

    def add_issue(self, issue: IntegrationIssue):
        self.issues.append(issue)


class E3Integrator:
    def __init__(self):
        self.integration_count = 0

    def integrate(self, objective: str, specialist_outputs: Dict[str, Any],
                  original_requirements: Optional[Dict[str, Any]] = None) -> IntegrationResult:
        result = IntegrationResult(plan_id="current")

        if not specialist_outputs:
            result.add_issue(IntegrationIssue(
                issue_type="no_outputs",
                description="No specialist outputs provided for integration",
                severity="high",
            ))
            return result

        if original_requirements:
            required_keys = set(original_requirements.get("expected_outputs", {}).keys())
            provided_keys = set()
            for output in specialist_outputs.values():
                if isinstance(output, dict):
                    provided_keys.update(output.keys())

            missing = required_keys - provided_keys
            if missing:
                result.missing_pieces = list(missing)
                result.add_issue(IntegrationIssue(
                    issue_type="missing_deliverables",
                    description=f"Missing expected outputs: {missing}",
                    severity="medium",
                ))

        contradictions = self._detect_contradictions(specialist_outputs)
        if contradictions:
            result.contradictions = contradictions
            for c in contradictions:
                result.add_issue(IntegrationIssue(
                    issue_type="contradiction",
                    description=c.get("description", "Contradiction detected"),
                    severity="high",
                    affected_nodes=c.get("nodes", []),
                ))

        combined = self._combine_outputs(specialist_outputs)
        result.integrated_output = combined
        result.complete = not result.has_blocking_issues()
        return result

    def _detect_contradictions(self, outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        contradictions = []
        output_items = list(outputs.items())

        for i, (key1, val1) in enumerate(output_items):
            for key2, val2 in output_items[i+1:]:
                if isinstance(val1, dict) and isinstance(val2, dict):
                    common_keys = set(val1.keys()) & set(val2.keys())
                    for ck in sorted(common_keys):  # deterministic ordering
                        if val1[ck] != val2[ck]:
                            contradictions.append({
                                "key": ck,
                                "nodes": [key1, key2],
                                "values": [val1[ck], val2[ck]],
                                "description": f"Conflicting values for '{ck}': {val1[ck]} vs {val2[ck]}",
                            })
        return contradictions

    def _combine_outputs(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        combined: Dict[str, Any] = {}
        for source, output in outputs.items():
            if isinstance(output, dict):
                for key, value in output.items():
                    if key not in combined:
                        combined[key] = value
                    elif combined[key] != value:
                        existing = combined[key]
                        if isinstance(existing, list):
                            if value not in existing:
                                existing.append(value)
                        else:
                            combined[key] = [existing, value]
            else:
                combined[source] = output
        return combined

    def identify_duplication(self, specialist_outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        duplications = []
        output_items = list(specialist_outputs.items())

        for i, (key1, val1) in enumerate(output_items):
            for key2, val2 in output_items[i+1:]:
                if self._outputs_similar(val1, val2):
                    duplications.append({
                        "nodes": [key1, key2],
                        "similarity": "high",
                        "description": f"Outputs from {key1} and {key2} appear duplicative",
                    })
        return duplications

    def _outputs_similar(self, val1: Any, val2: Any) -> bool:
        if val1 == val2:
            return True
        if isinstance(val1, str) and isinstance(val2, str):
            words1 = set(val1.lower().split())
            words2 = set(val2.lower().split())
            if words1 and words2:
                overlap = len(words1 & words2) / max(len(words1), len(words2))
                return overlap > 0.7
        return False
