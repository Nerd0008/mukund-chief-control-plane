#!/usr/bin/env python3
"""E3 Cold-Start Benchmark / Qualification Harness.

Two harnesses live here and they are NOT interchangeable:

* :class:`EvidenceBackedBenchmark` — the real qualification harness. Every check
  is evaluated against rows that already exist in the E3 orchestration store
  (``performance_evidence``, cross-checked against ``dag_node``). It never
  simulates a provider, and a worker with no recorded execution can never be
  qualified. *Smoke readiness is not qualification.*
* :class:`ColdStartBenchmark` — an offline fixture harness whose bundled
  evaluation functions are deterministic placeholders that do not observe a
  provider. Its results are explicitly **not** qualification evidence: it marks
  every result ``evidence_backed=False`` and can never return ``PASS``.
"""

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

# Qualification bar, applied to RECORDED real executions only. Chosen so that a
# single observation can never qualify a worker, and so a worker that has since
# recovered is not permanently blocked by an earlier failed attempt.
MIN_RECORDED_EXECUTIONS = 2   # recorded real dispatches for (worker, role)
MIN_RECORDED_PASSES = 2       # of those, how many ended verified COMPLETE
MIN_FIRST_PASS_PASSES = 1     # at least one must not have needed a repair

# Provider values that mean "this row is not a real provider execution".
NON_REAL_PROVIDERS = ("shadow", "rehearsal", "simulated", "stub", "fake", "")


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
        # True only when every check was evaluated against recorded real
        # execution evidence. Fixture/synthetic suites leave this False.
        self.evidence_backed = False
        self.evidence_references: List[str] = []
        self.notes: Optional[str] = None
        self.evidence_counts: Dict[str, Any] = {}

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

    def add_check_result(self, check_name: str, state: "QualificationState",
                         details: str = ""):
        """Record a tri-state evidence check.

        ``INSUFFICIENT`` is deliberately not represented as a pass or a failure:
        a check that could not be evaluated from evidence must never be counted
        as a success, and must not be reported as a capability failure either.
        """
        self.test_results.append({
            "test_name": check_name,
            "state": state.value,
            "passed": True if state is QualificationState.PASS else (
                False if state is QualificationState.FAIL else None),
            "details": details,
            "error": "",
        })

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
        # Fixture harness: the bundled evaluation functions above are placeholder
        # strings, not observations of a provider. A synthetic suite therefore
        # never yields a qualification — reading one as evidence would be exactly
        # the "smoke readiness treated as qualification" defect this guards.
        result.evidence_backed = False
        result.overall_state = QualificationState.INCONCLUSIVE
        result.notes = ("fixture harness: the bundled evaluation functions do not "
                        "observe a provider — NOT qualification evidence")
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


# ─── Evidence-backed qualification (the real harness) ───────────────


class EvidenceBackedBenchmark:
    """Cold-start qualification evaluated against RECORDED execution evidence.

    Every check reads rows that already exist in the E3 orchestration store:

    * ``performance_evidence`` — one row per real dispatch, written by
      ``E3ProductionExecutor`` only after deterministic verification;
    * ``dag_node`` — cross-checked so a claimed COMPLETE is corroborated by the
      persisted node state.

    There is no synthetic evaluator and no provider call. A check that cannot be
    evaluated from evidence returns ``INSUFFICIENT`` (never a pass), a worker with
    no recorded execution is ``NOT_RUN``, and a worker is only ``QUALIFIED`` when
    the recorded evidence clears every bar in :data:`MIN_RECORDED_EXECUTIONS` /
    :data:`MIN_RECORDED_PASSES` / :data:`MIN_FIRST_PASS_PASSES`.
    """

    CHECKS = (
        "recorded-real-execution",
        "deterministic-verification-gating",
        "dag-state-corroborated",
        "capability-demonstrated",
        "repeatability",
        "latest-execution-not-failing",
    )

    def __init__(self, con):
        self.con = con

    # ── evidence source ─────────────────────────────────────────────
    def load_evidence(self, worker_id: str, role: str) -> List[Dict[str, Any]]:
        rows = self.con.execute(
            "SELECT evidence_id, worker_id, task_fingerprint, role, model, "
            "provider, first_pass_success, final_success, verification_outcome, "
            "retries, corrections, failure_attribution, dag_node_id, timestamp "
            "FROM performance_evidence WHERE worker_id=? AND role=? "
            "ORDER BY timestamp, evidence_id",
            (worker_id, role)).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            node = self.con.execute(
                "SELECT state, plan_id FROM dag_node WHERE node_id=?",
                (entry.get("dag_node_id"),)).fetchone()
            entry["dag_node_state"] = node["state"] if node else None
            entry["dag_node_plan_id"] = node["plan_id"] if node else None
            out.append(entry)
        return out

    def candidate_scopes(self) -> List[Dict[str, str]]:
        """Every (worker, role) pair that has any recorded execution evidence."""
        rows = self.con.execute(
            "SELECT DISTINCT worker_id, role FROM performance_evidence "
            "ORDER BY worker_id, role").fetchall()
        return [{"worker_id": r["worker_id"], "role": r["role"]} for r in rows]

    # ── evaluation ──────────────────────────────────────────────────
    def evaluate(self, worker_id: str, role: str,
                 task_family: str = "code") -> QualificationResult:
        evidence = self.load_evidence(worker_id, role)
        result = QualificationResult(worker_id, task_family, role)
        result.evidence_backed = True
        result.evidence_references = [e["evidence_id"] for e in evidence]

        passes = [e for e in evidence
                  if e.get("final_success") == 1
                  and e.get("verification_outcome") == "PASS"]
        first_passes = [e for e in passes if e.get("first_pass_success") == 1]
        counts = {
            "recorded_executions": len(evidence),
            "recorded_passes": len(passes),
            "recorded_first_pass_passes": len(first_passes),
            "rejected_then_repaired_passes": len(passes) - len(first_passes),
            "recorded_failures": len(evidence) - len(passes),
            "dag_node_ids": [e.get("dag_node_id") for e in evidence],
            "distinct_dag_node_ids": sorted({str(e.get("dag_node_id"))
                                             for e in evidence
                                             if e.get("dag_node_id")}),
            "recorded_runs_by_timestamp": sorted(
                {str(e.get("timestamp")) for e in evidence if e.get("timestamp")}),
            "task_fingerprints": sorted(
                {str(e.get("task_fingerprint")) for e in evidence
                 if e.get("task_fingerprint")}),
        }
        result.evidence_counts = counts

        def _check(name, state, details):
            result.add_check_result(name, state, details)

        if not evidence:
            for name in self.CHECKS:
                _check(name, QualificationState.INCONCLUSIVE,
                       "no recorded execution evidence for this worker/role")
            result.compute_overall()
            result.overall_state = QualificationState.NOT_RUN
            result.notes = "no recorded execution evidence — nothing to qualify"
            return result

        # 1. real provider execution, persisted with a DAG node reference
        bad = [e["evidence_id"] for e in evidence
               if (e.get("provider") or "").lower() in NON_REAL_PROVIDERS
               or not e.get("dag_node_id")]
        _check("recorded-real-execution",
               QualificationState.PASS if not bad else QualificationState.FAIL,
               f"{len(evidence)} recorded row(s); "
               f"{len(bad)} without a real provider / DAG node reference")

        # 2. a deterministic verification actually gated every execution
        ungraded = [e["evidence_id"] for e in evidence
                    if e.get("verification_outcome") not in ("PASS", "FAIL")]
        _check("deterministic-verification-gating",
               QualificationState.PASS if not ungraded else QualificationState.FAIL,
               f"{len(ungraded)} row(s) with no recorded deterministic verdict")

        # 3. a claimed COMPLETE must be corroborated by the persisted node state
        uncorroborated = [e["evidence_id"] for e in passes
                          if e.get("dag_node_state") != "COMPLETE"]
        _check("dag-state-corroborated",
               QualificationState.PASS if not uncorroborated else QualificationState.FAIL,
               f"{len(uncorroborated)} verified pass(es) not corroborated by "
               f"COMPLETE in dag_node")

        # 4. the capability was actually demonstrated: a verified COMPLETE
        _check("capability-demonstrated",
               QualificationState.PASS if passes else QualificationState.FAIL,
               f"{len(passes)} verified COMPLETE execution(s) recorded")

        # 5. repeatability — a single observation never qualifies
        _check("repeatability",
               QualificationState.PASS if (len(passes) >= MIN_RECORDED_PASSES
                                          and len(evidence) >= MIN_RECORDED_EXECUTIONS
                                          and len(first_passes) >= MIN_FIRST_PASS_PASSES)
               else QualificationState.INCONCLUSIVE,
               f"{len(passes)} verified pass(es) over {len(evidence)} recorded "
               f"execution(s); bar is >= {MIN_RECORDED_PASSES} passes over "
               f">= {MIN_RECORDED_EXECUTIONS} executions with "
               f">= {MIN_FIRST_PASS_PASSES} first-pass pass(es)")

        # 6. the worker's most recent recorded execution is not a failure
        latest = evidence[-1]
        latest_ok = (latest.get("final_success") == 1
                     and latest.get("verification_outcome") == "PASS")
        _check("latest-execution-not-failing",
               QualificationState.PASS if latest_ok else QualificationState.FAIL,
               f"latest recorded execution {latest.get('evidence_id')} -> "
               f"final_success={latest.get('final_success')}, "
               f"verification={latest.get('verification_outcome')}")

        result.compute_overall()
        result.overall_state = self._overall(result)
        result.notes = (
            "evidence-backed qualification from recorded real executions; "
            "smoke readiness is not qualification")
        return result

    @staticmethod
    def _overall(result: QualificationResult) -> QualificationState:
        states = [t.get("state") for t in result.test_results]
        if any(s == QualificationState.FAIL.value for s in states):
            return QualificationState.FAIL
        if any(s == QualificationState.INCONCLUSIVE.value for s in states):
            return QualificationState.INCONCLUSIVE
        if all(s == QualificationState.PASS.value for s in states):
            return QualificationState.PASS
        return QualificationState.NOT_RUN


# Capability-registry state a qualification result may justify. Anything that is
# not a PASS maps to a non-qualified state — never to QUALIFIED.
QUALIFICATION_TO_REGISTRY_STATE = {
    QualificationState.PASS: "QUALIFIED",
    QualificationState.INCONCLUSIVE: "EVALUATING",
    QualificationState.FAIL: "UNPROVEN",
    QualificationState.NOT_RUN: "UNPROVEN",
    QualificationState.IN_PROGRESS: "UNPROVEN",
}


def registry_state_for(result: QualificationResult) -> str:
    """Registry state justified by a qualification result.

    A result that is not evidence-backed can never map to QUALIFIED.
    """
    if not result.evidence_backed:
        return "UNPROVEN"
    return QUALIFICATION_TO_REGISTRY_STATE[result.overall_state]
