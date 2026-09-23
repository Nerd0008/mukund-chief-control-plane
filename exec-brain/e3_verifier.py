#!/usr/bin/env python3
"""E3 Independent Critic/Verifier — deterministic + AI critic verification path."""

from typing import Any, Dict, List, Optional
from enum import Enum


class VerificationMethod(Enum):
    TEST = "test"
    SCHEMA = "schema"
    COMPARISON = "comparison"
    CRITIC = "critic"
    OWNER = "owner"


class VerificationOutcome(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    UNCERTAIN = "UNCERTAIN"


class VerificationResult:
    def __init__(self, method: VerificationMethod, outcome: VerificationOutcome,
                 issues: Optional[List[str]] = None,
                 suggestions: Optional[List[str]] = None,
                 evidence_references: Optional[List[str]] = None):
        self.method = method
        self.outcome = outcome
        self.issues = issues if issues is not None else []
        self.suggestions = suggestions if suggestions is not None else []
        self.evidence_references = evidence_references if evidence_references is not None else []

    @property
    def passed(self) -> bool:
        return self.outcome == VerificationOutcome.PASS


class IndependentVerifier:
    def __init__(self, expected_schema: Optional[Dict[str, Any]] = None,
                 test_cases: Optional[List[Dict[str, Any]]] = None,
                 comparison_source: Any = None):
        self.expected_schema = expected_schema
        self.test_cases = test_cases if test_cases is not None else []
        self.comparison_source = comparison_source

    def verify(self, output: Any,
               method: VerificationMethod = VerificationMethod.TEST) -> VerificationResult:
        if method == VerificationMethod.TEST:
            return self._verify_by_tests(output)
        elif method == VerificationMethod.SCHEMA:
            return self._verify_by_schema(output)
        elif method == VerificationMethod.COMPARISON:
            return self._verify_by_comparison(output)
        elif method == VerificationMethod.CRITIC:
            return self._verify_by_critic(output)
        else:
            return VerificationResult(
                method=method,
                outcome=VerificationOutcome.UNCERTAIN,
                issues=[f"Verification method {method.value} requires AI critic or owner"],
            )

    def _verify_by_tests(self, output: Any) -> VerificationResult:
        if not self.test_cases:
            return VerificationResult(
                method=VerificationMethod.TEST,
                outcome=VerificationOutcome.UNCERTAIN,
                issues=["No test cases available for verification"],
            )

        failures: List[str] = []
        passes = 0
        for test in self.test_cases:
            test_name = test.get("name", "unnamed")
            expected = test.get("expected")
            field = test.get("field")
            actual = self._extract_field(output, field) if field is not None else output
            if actual == expected:
                passes += 1
            else:
                failures.append(f"Test '{test_name}': expected {expected}, got {actual}")

        if passes == len(self.test_cases):
            outcome = VerificationOutcome.PASS
        elif passes > 0:
            outcome = VerificationOutcome.PARTIAL
        else:
            outcome = VerificationOutcome.FAIL

        return VerificationResult(
            method=VerificationMethod.TEST,
            outcome=outcome,
            issues=failures,
        )

    def _verify_by_schema(self, output: Any) -> VerificationResult:
        if not self.expected_schema:
            return VerificationResult(
                method=VerificationMethod.SCHEMA,
                outcome=VerificationOutcome.UNCERTAIN,
                issues=["No schema defined for verification"],
            )

        if not isinstance(output, dict):
            return VerificationResult(
                method=VerificationMethod.SCHEMA,
                outcome=VerificationOutcome.FAIL,
                issues=[f"Expected dict output, got {type(output).__name__}"],
            )

        missing: List[str] = []
        for field in self.expected_schema.get("required", []):
            if field not in output:
                missing.append(f"Missing required field: {field}")

        if missing:
            return VerificationResult(
                method=VerificationMethod.SCHEMA,
                outcome=VerificationOutcome.FAIL,
                issues=missing,
            )

        return VerificationResult(
            method=VerificationMethod.SCHEMA,
            outcome=VerificationOutcome.PASS,
        )

    def _verify_by_comparison(self, output: Any) -> VerificationResult:
        if self.comparison_source is None:
            return VerificationResult(
                method=VerificationMethod.COMPARISON,
                outcome=VerificationOutcome.UNCERTAIN,
                issues=["No comparison source available"],
            )

        if output == self.comparison_source:
            return VerificationResult(
                method=VerificationMethod.COMPARISON,
                outcome=VerificationOutcome.PASS,
            )
        else:
            return VerificationResult(
                method=VerificationMethod.COMPARISON,
                outcome=VerificationOutcome.FAIL,
                issues=["Output does not match comparison source"],
            )

    def _verify_by_critic(self, output: Any) -> VerificationResult:
        return VerificationResult(
            method=VerificationMethod.CRITIC,
            outcome=VerificationOutcome.UNCERTAIN,
            issues=["AI critic verification requires a qualified critic worker"],
        )

    def _extract_field(self, output: Any, field: str) -> Any:
        if isinstance(output, dict):
            return output.get(field)
        return None


class AICritic:
    def __init__(self, critic_worker_id: Optional[str] = None):
        self.critic_worker_id = critic_worker_id

    def can_criticize(self) -> bool:
        return self.critic_worker_id is not None

    def review(self, objective: str, output: Any,
               contract: Any = None) -> VerificationResult:
        if not self.can_criticize():
            return VerificationResult(
                method=VerificationMethod.CRITIC,
                outcome=VerificationOutcome.UNCERTAIN,
                issues=["No qualified critic worker available"],
            )
        return VerificationResult(
            method=VerificationMethod.CRITIC,
            outcome=VerificationOutcome.UNCERTAIN,
            issues=[f"Critic worker {self.critic_worker_id} would review here"],
        )
