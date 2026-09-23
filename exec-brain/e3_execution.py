#!/usr/bin/env python3
"""E3 Production Execution Leg — orchestrator → worker ExecutionAdapter dispatch.

This module is the missing production leg of the E3 orchestration path. Once a
temporary team has been assembled it dispatches each ready DAG node to the
*assigned worker's* real ``ExecutionAdapter``, persists node state transitions
and performance evidence in ``orchestration.db`` (schema v2), and requires
deterministic verification before a node may reach ``COMPLETE``.

Truth rules enforced here
-------------------------
* Only workers whose registry entry says ``routable=True`` (smoke PASS + E2
  usage linkage) may be dispatched. A non-routable worker raises
  :class:`WorkerNotRoutable`; the leg never falls back to a credential-missing
  worker and never invents an assignment.
* A node reaches ``COMPLETE`` only after an independent deterministic
  verification returns PASS. No verification PASS, no COMPLETE.
* Provider usage/model identity is taken from the provider response only and is
  never estimated or fabricated. Absent usage is recorded as NULL.
* E1/E2 integration happens only through the public
  ``governor.record_request()`` interface exposed by the adapters. This module
  never opens the E1/E2 stores.
"""

import importlib
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from e3_verifier import IndependentVerifier, VerificationMethod, VerificationOutcome


# ─── Worker → ExecutionAdapter binding ─────────────────────────────

# Only workers that are truthfully routable have an execution binding. The
# adapter modules are imported lazily so that importing this module never
# touches a CLI, a credential or the network.
ADAPTER_MODULES: Dict[str, Dict[str, Any]] = {
    "codex-cli": {
        "module": "codex_adapter",
        "class": "CodexExecutionAdapter",
        "provider": "openai",
        "kwargs": {},
    },
    "deepseek-v41-flash": {
        "module": "deepseek_adapter",
        "class": "DeepSeekExecutionAdapter",
        "provider": "deepseek",
        "kwargs": {"model": "deepseek-flash"},
    },
    "google-nano-banana-2": {
        "module": "gemini_adapter",
        "class": "GeminiImageExecutionAdapter",
        "provider": "google",
        "kwargs": {},
    },
}


class WorkerNotRoutable(Exception):
    """Raised when dispatch is attempted for a worker that is not routable."""


def _default_adapter_factory(spec: Dict[str, Any]) -> Callable[[], Any]:
    def _build():
        module = importlib.import_module(spec["module"])
        cls = getattr(module, spec["class"])
        return cls(**spec.get("kwargs", {}))

    return _build


def _default_usage_reporter(spec: Dict[str, Any]) -> Callable[[Dict[str, Any]], Optional[str]]:
    def _report(result: Dict[str, Any]) -> Optional[str]:
        module = importlib.import_module(spec["module"])
        return module.report_usage_to_e2(result)

    return _report


class ExecutionAdapterRegistry:
    """Resolves ``worker_id`` → live ``ExecutionAdapter`` for routable workers.

    ``adapter_factories`` / ``usage_reporters`` allow deterministic test doubles
    to be injected; the production rehearsal uses the real adapters.
    """

    def __init__(self, worker_registry: Any = None,
                 adapter_factories: Optional[Dict[str, Callable[[], Any]]] = None,
                 usage_reporters: Optional[Dict[str, Callable[[Dict[str, Any]], Optional[str]]]] = None,
                 bindings: Optional[Dict[str, Dict[str, Any]]] = None):
        if worker_registry is None:
            from worker_registry import WorkerRegistry
            worker_registry = WorkerRegistry()
        self.worker_registry = worker_registry
        self.bindings = bindings if bindings is not None else ADAPTER_MODULES
        self._factories = dict(adapter_factories or {})
        self._usage_reporters = dict(usage_reporters or {})
        self._instances: Dict[str, Any] = {}

    # ── routing truth ───────────────────────────────────────────────
    def is_routable(self, worker_id: str) -> bool:
        """True only for workers the registry reports routable AND that have a
        real execution binding (smoke PASS + E2 linkage + adapter)."""
        worker = self.worker_registry.get_worker(worker_id)
        if not worker:
            return False
        if not worker.get("routable"):
            return False
        return worker_id in self._factories or worker_id in self.bindings

    def routable_worker_ids(self) -> List[str]:
        return sorted(w for w in self.worker_registry.get_all_workers()
                      if self.is_routable(w))

    def adapter_for(self, worker_id: str) -> Any:
        """Instantiate (and cache) the real ExecutionAdapter for a worker."""
        if worker_id in self._instances:
            return self._instances[worker_id]
        if not self.is_routable(worker_id):
            raise WorkerNotRoutable(
                f"worker {worker_id!r} is not routable "
                f"(registry routable={bool((self.worker_registry.get_worker(worker_id) or {}).get('routable'))}); "
                "credential-missing workers are never dispatched"
            )
        factory = self._factories.get(worker_id)
        if factory is None:
            factory = _default_adapter_factory(self.bindings[worker_id])
        adapter = factory()
        self._instances[worker_id] = adapter
        return adapter

    def report_usage(self, worker_id: str, result: Dict[str, Any]) -> Optional[str]:
        """Report observed provider usage through the public E2 interface."""
        reporter = self._usage_reporters.get(worker_id)
        if reporter is None:
            if worker_id not in self.bindings:
                return None
            reporter = _default_usage_reporter(self.bindings[worker_id])
        try:
            return reporter(result)
        except Exception as exc:  # noqa: BLE001 — reported, never fabricated
            return f"e2_linkage_error:{type(exc).__name__}"


# ─── orchestration.db persistence (E3's own store) ─────────────────

def _json(value: Any) -> str:
    return json.dumps(value, default=str)


class OrchestrationStore:
    """Schema-v2 DAG state + performance evidence persistence."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.con: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self.con is None:
            from orchestration_db import init_db
            init_db(self.db_path)
            self.con = sqlite3.connect(str(self.db_path))
            self.con.row_factory = sqlite3.Row
        return self.con

    def close(self):
        if self.con is not None:
            self.con.close()
            self.con = None

    # ── DAG nodes ───────────────────────────────────────────────────
    def upsert_node(self, plan_id: str, node: Dict[str, Any],
                    assigned_worker: Optional[str]) -> None:
        con = self.connect()
        con.execute(
            """INSERT INTO dag_node
               (node_id, plan_id, objective, capability_roles, dependencies,
                inputs, expected_outputs, floor_id, allowed_tools, permissions,
                verification_method, assigned_worker, fallback_candidates,
                state, attempts, defect_attempts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(node_id) DO UPDATE SET
                 assigned_worker=excluded.assigned_worker,
                 state=excluded.state,
                 updated_at=datetime('now')""",
            (
                node["node_id"], plan_id, node.get("objective", ""),
                _json(node.get("capability_roles", [])),
                _json(node.get("dependencies", [])),
                _json(node.get("inputs", {})),
                _json(node.get("expected_outputs", {})),
                node.get("floor_id"), _json(node.get("allowed_tools", [])),
                _json(node.get("permissions", {})),
                node.get("verification_method", "test"),
                assigned_worker,
                _json(node.get("fallback_candidates", [])),
                node.get("state", "PLANNED"),
                int(node.get("attempts", 0)),
                _json(node.get("defect_attempts", {})),
            ),
        )
        con.commit()

    def set_node_state(self, node_id: str, plan_id: str, new_state: str,
                       cause: str, dispatch_reference: Optional[str] = None,
                       verification_reference: Optional[str] = None,
                       attempts: Optional[int] = None) -> Dict[str, Any]:
        """Atomically move a node state and record the transition event."""
        con = self.connect()
        row = con.execute("SELECT state, attempts FROM dag_node WHERE node_id=?",
                          (node_id,)).fetchone()
        previous = row["state"] if row else None
        if attempts is None:
            attempts = (row["attempts"] if row else 0) or 0
        con.execute(
            """UPDATE dag_node SET state=?, attempts=?, updated_at=datetime('now')
               WHERE node_id=?""",
            (new_state, attempts, node_id),
        )
        event_id = f"dagstate-{uuid.uuid4().hex[:12]}"
        con.execute(
            """INSERT INTO dag_state_event
               (event_id, node_id, plan_id, previous_state, new_state, cause,
                dispatch_reference, verification_reference)
               VALUES (?,?,?,?,?,?,?,?)""",
            (event_id, node_id, plan_id, previous, new_state, cause,
             dispatch_reference, verification_reference),
        )
        con.commit()
        return {"event_id": event_id, "node_id": node_id,
                "previous_state": previous, "new_state": new_state,
                "cause": cause}

    # ── performance evidence ────────────────────────────────────────
    def record_evidence(self, evidence: Dict[str, Any]) -> str:
        con = self.connect()
        eid = evidence.get("evidence_id") or f"evidence-{uuid.uuid4().hex[:12]}"
        con.execute(
            """INSERT OR REPLACE INTO performance_evidence
               (evidence_id, worker_id, task_fingerprint, role, model, provider,
                reasoning_profile, execution_profile, tools, first_pass_success,
                final_success, verification_outcome, deterministic_test_results,
                retries, corrections, correction_severity, failure_attribution,
                runtime_s, usage_tokens, monetary_cost, floor_id, dag_node_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                eid, evidence.get("worker_id", "unassigned"),
                evidence.get("task_fingerprint", ""), evidence.get("role", ""),
                evidence.get("model") or "unknown",
                evidence.get("provider") or "unknown",
                evidence.get("reasoning_profile"), evidence.get("execution_profile"),
                _json(evidence.get("tools", [])),
                _bool_int(evidence.get("first_pass_success")),
                _bool_int(evidence.get("final_success")),
                evidence.get("verification_outcome"),
                _json(evidence.get("deterministic_test_results")) if evidence.get("deterministic_test_results") is not None else None,
                int(evidence.get("retries", 0) or 0),
                int(evidence.get("corrections", 0) or 0),
                evidence.get("correction_severity"),
                evidence.get("failure_attribution"),
                int(evidence.get("runtime_s") or 0),
                evidence.get("usage_tokens"),
                evidence.get("monetary_cost"),
                evidence.get("floor_id"), evidence.get("dag_node_id"),
            ),
        )
        con.commit()
        return eid

    def record_router_decision(self, plan_id: str, node_id: str,
                               candidate: Any, gate_decision: str = "ACCEPT") -> str:
        con = self.connect()
        did = f"router-dec-{uuid.uuid4().hex[:12]}"
        con.execute(
            """INSERT INTO router_decision
               (decision_id, plan_id, node_id, proposed_worker, proposed_role,
                confidence, reasoning, gate_decision, gate_reasons)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (did, plan_id, node_id, getattr(candidate, "worker_id", "unknown"),
             getattr(candidate, "role", "unknown"),
             getattr(candidate, "confidence", "LOW"),
             getattr(candidate, "concise_rationale", ""), gate_decision, None),
        )
        con.commit()
        return did

    def read_back(self, node_id: str) -> Dict[str, Any]:
        """Read a node + its transition/evidence rows back out of the store."""
        con = self.connect()
        node = con.execute("SELECT * FROM dag_node WHERE node_id=?",
                           (node_id,)).fetchone()
        events = con.execute(
            "SELECT previous_state, new_state, cause, dispatch_reference, "
            "verification_reference FROM dag_state_event WHERE node_id=? "
            "ORDER BY rowid", (node_id,)).fetchall()
        evidence = con.execute(
            "SELECT evidence_id, first_pass_success, final_success, "
            "verification_outcome, retries, corrections, failure_attribution "
            "FROM performance_evidence WHERE dag_node_id=?", (node_id,)).fetchall()
        return {
            "node": dict(node) if node else None,
            "state_events": [dict(e) for e in events],
            "evidence": [dict(e) for e in evidence],
        }


def _bool_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return 1 if value else 0


# ─── Node execution ─────────────────────────────────────────────────

class NodeExecutionResult:
    """Outcome of dispatching and verifying one DAG node on the real path."""

    def __init__(self, node_id: str, worker_id: str, role: str):
        self.node_id = node_id
        self.worker_id = worker_id
        self.role = role
        self.state = "PLANNED"
        self.dispatch_attempts: List[Dict[str, Any]] = []
        self.verification_attempts: List[Dict[str, Any]] = []
        self.rejections: List[Dict[str, Any]] = []
        self.repairs: List[Dict[str, Any]] = []
        self.output: Optional[Dict[str, Any]] = None
        self.final_verification: Optional[str] = None
        self.failure_attribution: Optional[str] = None
        self.e2_request_ids: List[Optional[str]] = []
        self.evidence_id: Optional[str] = None
        self.blocking_reason: Optional[str] = None

    @property
    def complete(self) -> bool:
        return self.state == "COMPLETE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "worker_id": self.worker_id,
            "role": self.role,
            "state": self.state,
            "dispatch_attempts": self.dispatch_attempts,
            "verification_attempts": self.verification_attempts,
            "rejections": self.rejections,
            "repairs": self.repairs,
            "final_verification": self.final_verification,
            "failure_attribution": self.failure_attribution,
            "e2_request_ids": self.e2_request_ids,
            "evidence_id": self.evidence_id,
            "blocking_reason": self.blocking_reason,
        }


def normalize_dispatch_output(worker_id: str, result: Dict[str, Any],
                              node_id: str) -> Dict[str, Any]:
    """Normalize a provider dispatch result into a verifiable node output.

    Only provider-returned values are carried through; absent fields stay None.
    """
    provider = result.get("provider")
    usage = result.get("usage")
    usage_tokens = None
    if isinstance(usage, dict):
        for key in ("total_tokens", "totalTokenCount", "total"):
            if isinstance(usage.get(key), int):
                usage_tokens = usage[key]
                break
    elif isinstance(result.get("usage_tokens"), dict):
        usage = result["usage_tokens"]
        if isinstance(usage.get("output_tokens"), int):
            usage_tokens = usage.get("output_tokens")

    content = result.get("content")
    if content is None and result.get("final_message") is not None:
        content = result.get("final_message")

    # Derived view of the provider text (whitespace-stripped only). This is a
    # normalization of provider output, never a substitute for it.
    content_stripped = content.strip() if isinstance(content, str) else None

    output = {
        "node_id": node_id,
        "worker_id": worker_id,
        "status": result.get("status"),
        "artifact": result.get("dispatch_id"),
        "dispatch_id": result.get("dispatch_id"),
        "provider": provider,
        "model": result.get("model"),
        "content": content,
        "content_stripped": content_stripped,
        "content_present": bool(content_stripped),
        "image_size_bytes": result.get("image_size_bytes"),
        "image_decode_ok": result.get("image_decode_ok"),
        "usage": usage,
        "usage_tokens": usage_tokens,
        "exit_code": result.get("exit_code"),
        "error": result.get("error"),
        "runtime_s": result.get("runtime_s"),
        "e2_usage_linkage": result.get("e2_usage_linkage"),
        "timestamp": datetime.utcnow().isoformat(),
    }
    return output


class E3ProductionExecutor:
    """Dispatches ready DAG nodes to real worker adapters and verifies them.

    Deterministic verification gates every node: a node is only marked
    ``COMPLETE`` after an independent verification PASS. A genuine rejection
    triggers at most ``max_repair_attempts`` targeted repair dispatches
    (rework), each followed by re-verification.
    """

    def __init__(self, store: OrchestrationStore,
                 adapter_registry: ExecutionAdapterRegistry,
                 repair_objective_builder: Optional[Callable[[Dict[str, Any], Any, Dict[str, Any]], str]] = None):
        self.store = store
        self.registry = adapter_registry
        self.repair_objective_builder = (repair_objective_builder
                                         or default_repair_objective)

    # ── verification ────────────────────────────────────────────────
    @staticmethod
    def _verification_method(node: Dict[str, Any]) -> VerificationMethod:
        raw = node.get("verification_method", "test")
        try:
            return VerificationMethod(raw)
        except ValueError:
            return VerificationMethod.TEST

    def _verify(self, node: Dict[str, Any], output: Dict[str, Any],
                test_cases: Optional[List[Dict[str, Any]]]):
        verifier = IndependentVerifier(test_cases=list(test_cases or []))
        if not test_cases:
            # No deterministic cases configured: verification cannot pass.
            return verifier.verify(output, method=VerificationMethod.TEST)
        return verifier.verify(output, method=self._verification_method(node))

    # ── dispatch ────────────────────────────────────────────────────
    def _dispatch(self, node: Dict[str, Any], worker_id: str, objective: str,
                  timeout: int) -> Dict[str, Any]:
        adapter = self.registry.adapter_for(worker_id)
        contract = {
            "contract_id": f"contract-{node['node_id']}",
            "objective": objective,
            "timeout": timeout,
            "max_tokens": 256,
            "temperature": 0.0,
        }
        working_directory = node.get("working_directory")
        if working_directory:
            contract["working_directory"] = working_directory
        result = adapter.dispatch(contract)
        return result

    def _reuse_readonly_dependency_check(self, dag: Any, node: Dict[str, Any]) -> bool:
        if dag is None:
            return True
        for dep in node.get("dependencies", []) or []:
            dep_node = dag.get_node(dep) if hasattr(dag, "get_node") else None
            if dep_node is None:
                return False
            if getattr(dep_node, "state", None) != "COMPLETE":
                return False
        return True

    # ── main entry point ────────────────────────────────────────────
    def execute_plan(self, plan: Dict[str, Any], dag: Any,
                     team_assembly: Any, fingerprint: Any, objective: str,
                     verification_test_cases_by_node: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                     max_repair_attempts: int = 1,
                     dispatch_timeout: int = 120,
                     role_by_node: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute every node of an assembled plan on the real execution path."""
        plan_id = plan.get("plan_id", "unknown")
        test_cases_by_node = verification_test_cases_by_node or {}
        assignment_by_node: Dict[str, Any] = {}
        if team_assembly is not None:
            for a in team_assembly.assignments:
                assignment_by_node.setdefault(a.node_id, a)

        results: List[NodeExecutionResult] = []
        for node in plan.get("nodes", []):
            node_id = node["node_id"]
            assignment = assignment_by_node.get(node_id)
            role = (role_by_node or {}).get(node_id) or (
                assignment.role if assignment else (node.get("capability_roles") or ["builder"])[0]
            )
            worker_id = assignment.worker_id if assignment else "unassigned"

            result = NodeExecutionResult(node_id, worker_id, role)
            results.append(result)

            # Persist the node + its assignment before any dispatch.
            self.store.upsert_node(plan_id, node, worker_id)

            if assignment is None:
                self.store.set_node_state(node_id, plan_id, "BLOCKED",
                                          "no_team_assignment")
                result.state = "BLOCKED"
                result.blocking_reason = "no_team_assignment"
                continue

            if not self.registry.is_routable(worker_id):
                self.store.set_node_state(
                    node_id, plan_id, "BLOCKED",
                    f"worker_not_routable:{worker_id}")
                result.state = "BLOCKED"
                result.blocking_reason = f"worker_not_routable:{worker_id}"
                continue

            if not self._reuse_readonly_dependency_check(dag, node):
                self.store.set_node_state(node_id, plan_id, "BLOCKED",
                                          "dependency_incomplete")
                result.state = "BLOCKED"
                result.blocking_reason = "dependency_incomplete"
                continue

            node_test_cases = test_cases_by_node.get(node_id)
            if not node_test_cases:
                # A node without deterministic verification cases can never be
                # proven complete. Refuse to spend a provider call on it rather
                # than dispatch and then fail it.
                self.store.set_node_state(
                    node_id, plan_id, "BLOCKED",
                    "no_deterministic_verification_configured")
                result.state = "BLOCKED"
                result.blocking_reason = "no_deterministic_verification_configured"
                continue

            self.store.set_node_state(node_id, plan_id, "READY", "dependencies_satisfied")
            self._execute_node(plan_id, node, worker_id, role, result,
                               node_test_cases,
                               max_repair_attempts, dispatch_timeout,
                               fingerprint)

        complete = all(r.complete for r in results) and bool(results)
        outcome = "EXECUTION_COMPLETE" if complete else "EXECUTION_INCOMPLETE"
        if any(r.state == "BLOCKED" for r in results):
            outcome = "EXECUTION_BLOCKED"
        elif any(r.state == "FAILED" for r in results):
            outcome = "EXECUTION_FAILED"

        return {
            "plan_id": plan_id,
            "objective": objective,
            "outcome": outcome,
            "node_count": len(results),
            "nodes_complete": sum(1 for r in results if r.complete),
            "nodes": [r.to_dict() for r in results],
        }

    def _execute_node(self, plan_id: str, node: Dict[str, Any], worker_id: str,
                      role: str, result: NodeExecutionResult,
                      test_cases: Optional[List[Dict[str, Any]]],
                      max_repair_attempts: int, dispatch_timeout: int,
                      fingerprint: Any) -> None:
        node_id = node["node_id"]
        objective = node.get("objective", "")
        attempts = 0
        first_pass_success: Optional[bool] = None
        verification_outcome: Optional[str] = None
        final_success = False
        corrections = 0

        while True:
            attempts += 1
            result.state = "RUNNING"
            self.store.set_node_state(node_id, plan_id, "RUNNING",
                                      f"dispatch_attempt_{attempts}",
                                      attempts=attempts)

            if attempts == 1:
                dispatch_objective = objective
            else:
                dispatch_objective = self.repair_objective_builder(
                    node, result.verification_attempts[-1], result.output or {})

            try:
                dispatch_result = self._dispatch(node, worker_id, dispatch_objective,
                                                 dispatch_timeout)
            except WorkerNotRoutable as exc:
                self.store.set_node_state(node_id, plan_id, "BLOCKED",
                                          f"dispatch_refused:{exc}")
                result.state = "BLOCKED"
                result.blocking_reason = str(exc)
                return
            except Exception as exc:  # noqa: BLE001 — adapter failure is evidence
                dispatch_result = {
                    "dispatch_id": None, "status": "FAILED",
                    "provider": None, "model": None, "content": None,
                    "usage": None, "error": f"{type(exc).__name__}: {exc}",
                    "exit_code": -1, "runtime_s": 0.0,
                }

            e2_id = self.registry.report_usage(worker_id, dispatch_result)
            result.e2_request_ids.append(e2_id)

            output = normalize_dispatch_output(worker_id, dispatch_result, node_id)
            result.output = output
            result.dispatch_attempts.append({
                "attempt": attempts,
                "dispatch_id": dispatch_result.get("dispatch_id"),
                "status": dispatch_result.get("status"),
                "provider": dispatch_result.get("provider"),
                "model": dispatch_result.get("model"),
                "error": dispatch_result.get("error"),
                "runtime_s": dispatch_result.get("runtime_s"),
                "usage": dispatch_result.get("usage"),
                "usage_exposed": dispatch_result.get("usage") is not None,
                "objective_hash": _objective_hash(dispatch_objective),
                "e2_request_id": e2_id,
            })

            self.store.set_node_state(node_id, plan_id, "VERIFYING",
                                      f"verify_attempt_{attempts}",
                                      dispatch_reference=dispatch_result.get("dispatch_id"),
                                      attempts=attempts)

            verification = self._verify(node, output, test_cases)
            verification_outcome = verification.outcome.value
            result.verification_attempts.append({
                "attempt": attempts,
                "method": verification.method.value,
                "outcome": verification.outcome.value,
                "passed": verification.passed,
                "issues": list(verification.issues),
            })
            result.final_verification = verification.outcome.value

            if attempts == 1:
                first_pass_success = verification.passed

            if verification.passed:
                self.store.set_node_state(
                    node_id, plan_id, "COMPLETE",
                    f"verified_pass_attempt_{attempts}",
                    verification_reference=f"verify-{node_id}-{attempts}",
                    attempts=attempts)
                result.state = "COMPLETE"
                final_success = True
                break

            # Genuine rejection.
            result.rejections.append({
                "attempt": attempts,
                "outcome": verification.outcome.value,
                "issues": list(verification.issues),
            })

            if len(result.repairs) >= max_repair_attempts:
                self.store.set_node_state(
                    node_id, plan_id, "FAILED",
                    f"verification_failed_no_repair_budget_attempt_{attempts}",
                    verification_reference=f"verify-{node_id}-{attempts}",
                    attempts=attempts)
                result.state = "FAILED"
                result.failure_attribution = "verification_fail"
                break

            corrections += 1
            result.repairs.append({"attempt": attempts, "issues": list(verification.issues)})
            self.store.set_node_state(node_id, plan_id, "REWORK",
                                      f"targeted_repair_after_attempt_{attempts}",
                                      verification_reference=f"verify-{node_id}-{attempts}",
                                      attempts=attempts)

        if not final_success and result.state not in ("FAILED", "BLOCKED"):
            result.state = "FAILED"

        evidence_id = self.store.record_evidence({
            "evidence_id": None,
            "worker_id": worker_id,
            "task_fingerprint": _fingerprint_repr(fingerprint),
            "role": role,
            "model": result.output.get("model") if result.output else None,
            "provider": result.output.get("provider") if result.output else None,
            "execution_profile": "production-execution-leg",
            "first_pass_success": first_pass_success,
            "final_success": final_success,
            "verification_outcome": verification_outcome,
            "deterministic_test_results": {
                "attempts": result.verification_attempts,
                "rejections": len(result.rejections),
                "repairs": len(result.repairs),
            },
            "retries": attempts - 1,
            "corrections": corrections,
            "failure_attribution": result.failure_attribution,
            "runtime_s": int(sum((a.get("runtime_s") or 0)
                                 for a in result.dispatch_attempts)),
            "usage_tokens": (result.output or {}).get("usage_tokens"),
            "monetary_cost": None,
            "floor_id": node.get("floor_id"),
            "dag_node_id": node_id,
        })
        result.evidence_id = evidence_id


def _objective_hash(objective: str) -> str:
    import hashlib
    return hashlib.sha256(objective.encode()).hexdigest()[:12]


def _fingerprint_repr(fingerprint: Any) -> str:
    if fingerprint is None:
        return ""
    for attr in ("compute_hash", "hash"):
        fn = getattr(fingerprint, attr, None)
        if callable(fn):
            try:
                return str(fn())
            except Exception:  # noqa: BLE001
                pass
    return str(fingerprint)


def default_repair_objective(node: Dict[str, Any], last_verification: Dict[str, Any],
                             previous_output: Dict[str, Any]) -> str:
    """Deterministic targeted repair objective.

    Restates the node objective with the verifier's exact requirement appended,
    including the node's declared exact expected content when the plan specifies
    one. No provider call is made here; the executor re-dispatches the produced
    objective to the same worker.
    """
    issues = last_verification.get("issues") or []
    requirement = ("; ".join(str(i) for i in issues) if issues
                   else "satisfy the declared output requirements")
    exact = (node.get("expected_outputs") or {}).get("exact_content")
    if exact is not None:
        requirement = (
            f"{requirement}. Respond with only the following exact text on a "
            "single line, with no quotes, labels, preamble or extra "
            f"punctuation: {exact}"
        )
    return (
        f"{node.get('objective', '')}\n\n"
        "Your previous response did not satisfy the deterministic verification "
        f"requirement: {requirement}"
    )
