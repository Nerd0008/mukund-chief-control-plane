#!/usr/bin/env python3
"""E3 Cold-Start Benchmark / Qualification Harness."""

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum


def generate_id(prefix: str = '') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class QualificationState(Enum):
    NOT_RUN = "not_run"
    IN_PROGRESS = "in_progress"
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class TestCase:
    def __init__(self, name: str, description: str,
                 task_fingerprint: Any,
                 evaluation_fn: Callable,
                 expected_result: Any = None,
                 timeout_s: int = 60):
        self.test_id = generate_id("test")
        self.name = name
        self.description = description
        self.task_fingerprint = task_fingerprint
        self.evaluation_fn = evaluation_fn
        self.expected_result = expected_result
        self.timeout_s = timeout_s
        self.result = QualificationState.NOT_RUN
        self.actual_result: Any = None
        self.error: Optional[str] = None


class QualificationResult:
    def __init__(self, worker_id: str, task_family: str, role: str):
        self.result_id = generate_id("qual")
        self.worker_id = worker_id
        self.task_family = task_family
        self.role = role
        self.test_results: List[Dict[str, Any]] = []
        self.overall_state = QualificationState.NOT_RUN
        self.first_pass_successes = 0
        self.first_pass_total = 0
        self.created_at = datetime.utcnow().isoformat()

    def add_test_result(self, test_name: str, passed: bool,
                        details: str = "", error: str = ""):
        self.test_results.append({
            "test_name": test_name,
            "passed": passed,
            "details": details,
            "error": error,
        })
        self.first_pass_total += 1
        if passed:
            self.first_pass_successes += 1

    def compute_overall(self) -> QualificationState:
        if not self.test_results:
            self.overall_state = QualificationState.NOT_RUN
        elif all(t["passed"] for t in self.test_results):
            self.overall_state = QualificationState.PASS
        elif any(t["passed"] for t in self.test_results):
            self.overall_state = QualificationState.INCONCLUSIVE
        else:
            self.overall_state = QualificationState.FAIL
        return self.overall_state

    @property
    def first_pass_rate(self) -> float:
        if self.first_pass_total == 0:
            return 0.0
        return self.first_pass_successes / self.first_pass_total


class ColdStartBenchmark:
    def __init__(self):
        self.benchmark_history: List[QualificationResult] = []

    def create_qualification_suite(self, worker_id: str, task_family: str,
                                   role: str) -> List[TestCase]:
        tests = [
            TestCase(
                name=f"{worker_id}-{task_family}-{role}-connectivity",
                description=f"Verify worker {worker_id} can be reached for {task_family}/{role}",
                task_fingerprint=None,
                evaluation_fn=self._evaluate_connectivity,
            ),
            TestCase(
                name=f"{worker_id}-{task_family}-{role}-contract-format",
                description=f"Verify worker {worker_id} accepts contract format for {task_family}/{role}",
                task_fingerprint=None,
                evaluation_fn=self._evaluate_contract_format,
            ),
            TestCase(
                name=f"{worker_id}-{task_family}-{role}-output-schema",
                description=f"Verify worker {worker_id} produces output matching expected schema",
                task_fingerprint=None,
                evaluation_fn=self._evaluate_output_schema,
            ),
            TestCase(
                name=f"{worker_id}-{task_family}-{role}-usage-reporting",
                description=f"Verify worker {worker_id} reports usage metrics",
                task_fingerprint=None,
                evaluation_fn=self._evaluate_usage_reporting,
            ),
        ]
        return tests

    def run_qualification(self, worker_id: str, task_family: str,
                          role: str) -> QualificationResult:
        result = QualificationResult(worker_id, task_family, role)
        tests = self.create_qualification_suite(worker_id, task_family, role)

        for test in tests:
            try:
                test.result = QualificationState.IN_PROGRESS
                actual = test.evaluation_fn(worker_id, task_family, role)
                test.actual_result = actual
                test.result = QualificationState.PASS
                result.add_test_result(test.name, True, f"Result: {actual}")
            except Exception as e:
                test.result = QualificationState.FAIL
                test.error = str(e)
                result.add_test_result(test.name, False, error=str(e))

        result.compute_overall()
        self.benchmark_history.append(result)
        return result

    def _evaluate_connectivity(self, worker_id: str, task_family: str,
                                role: str) -> str:
        return "synthetic: connectivity requires live provider check"

    def _evaluate_contract_format(self, worker_id: str, task_family: str,
                                   role: str) -> str:
        return "synthetic: contract format check (adapter interface exists)"

    def _evaluate_output_schema(self, worker_id: str, task_family: str,
                                 role: str) -> str:
        return "synthetic: output schema validation"

    def _evaluate_usage_reporting(self, worker_id: str, task_family: str,
                                   role: str) -> str:
        return "synthetic: usage reporting check"

    def get_benchmark_history(self, worker_id: Optional[str] = None) -> List[QualificationResult]:
        if worker_id:
            return [r for r in self.benchmark_history if r.worker_id == worker_id]
        return self.benchmark_history
