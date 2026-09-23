#!/usr/bin/env python3
"""E3 production execution rehearsal — real worker execution on the local path.

Unlike ``e3_production_rehearsal`` (Stage-1 shadow rehearsal with simulated
specialist outputs and strict evidence isolation), this driver exercises the
**production execution leg**: the E3 orchestrator dispatches assembled DAG nodes
to the real ``ExecutionAdapter`` of a truthfully routable worker, persists
schema-v2 DAG state and performance evidence in the live ``orchestration.db``,
and requires deterministic verification before a node reaches ``COMPLETE``.

Real-path facts recorded (never fabricated):

* which runtime root / orchestration db was used and its schema version;
* per scenario: the assigned worker, the provider-reported dispatch result
  (status, provider-reported model identity, provider-returned usage when the
  provider exposes it, E2 request id from the public ``governor.record_request``
  interface), the deterministic verification attempts, the state transitions
  read back out of ``orchestration.db``, and the evidence row;
* the exact bounded number of real provider calls spent (and why);
* that a credential-missing (non-routable) worker is refused without any
  provider call.

Provider usage is only ever what the provider returned. Where a provider does
not expose usage, the field is recorded as null.

Bounded usage: each scenario spends a fixed, minimal number of calls; the
default set is 4 real calls (3 text + 1 CLI), plus 1 image call only when
``--include-google`` is passed.

This module does NOT enable Stage 2 and does NOT perform any deployment.
"""

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# Deterministic exact tokens. Each is a literal the worker is asked to return;
# nothing here depends on model judgement.
TOKEN_REPAIR = "READY-7391"      # scenario A (repair-cycle target)
TOKEN_FIRSTPASS = "ACK-2049"     # scenario B (first-pass target)
TOKEN_CODEX = "CODEX-OK-317"     # scenario C (codex CLI target)
TOKEN_NODE_BUILDER = "BUILD-5510"     # scenario F node 1 (builder)
TOKEN_NODE_INTEGRATOR = "INTEG-8842"  # scenario F node 2 (integrator)

# Scenario F: one worker per role, both truthfully routable (routable=true),
# so the decomposed plan is dispatched to two *different* real adapters.
MULTI_NODE_WORKERS = {
    "builder": "deepseek-v41-flash",
    "integrator": "codex-cli",
}

# Real provider calls each scenario needs, and why. Printed before the run so
# the bound is stated up front rather than discovered afterwards.
USAGE_PLAN = [
    {"scenario": "A_repair_cycle_deepseek", "worker": "deepseek-v41-flash",
     "calls": 2,
     "why": "1 deliberately under-specified dispatch (deterministic verifier "
            "must reject it) + 1 targeted repair re-dispatch that must pass."},
    {"scenario": "B_first_pass_deepseek", "worker": "deepseek-v41-flash",
     "calls": 1, "why": "single bounded call; deterministic first-pass PASS."},
    {"scenario": "C_codex_cli_dispatch", "worker": "codex-cli",
     "calls": 1, "why": "single non-interactive CLI dispatch in a scratch dir."},
    {"scenario": "F_decomposed_multi_worker", "worker": "deepseek-v41-flash + codex-cli",
     "calls": 3,
     "why": "2-node decomposed plan: node 1 (builder/deepseek) needs a rejected "
            "first attempt plus its targeted repair, node 2 "
            "(integrator/codex-cli) is a single first-pass dispatch. This is the "
            "minimum that exercises per-node deterministic verification on a "
            "multi-worker real plan."},
    {"scenario": "E_non_routable_refusal", "worker": "mistral-small-4",
     "calls": 0, "why": "credential-missing worker must be refused pre-dispatch."},
]
USAGE_PLAN_TOTAL = sum(s["calls"] for s in USAGE_PLAN)

# Modules that must exist in the live runtime root for E3 to be drivable there.
REQUIRED_RUNTIME_MODULES = [
    "e3_planner.py", "e3_router.py", "e3_team_assembly.py", "e3_integrator.py",
    "e3_verifier.py", "e3_shadow_orchestrator.py", "e3_conflict.py",
    "e3_replan.py", "e3_escalate.py", "e3_evidence.py", "e3_context.py",
    "e3_permissions.py", "e3_decomposition_review.py", "e3_exploration.py",
    "e3_qualification_benchmark.py", "e3_execution.py", "e3_commands.py",
    "e3_cli.py", "execution_dag.py", "orchestration_db.py",
    "worker_registry.py", "capability_registry.py", "task_fingerprint.py",
    "worker_contract.py", "decision_rationale.py",
    "codex_adapter.py", "deepseek_adapter.py", "gemini_adapter.py",
    "generic_openai_adapter.py",
]


def _store_file_hashes(stores: Dict[str, Path]) -> Dict[str, Dict[str, Any]]:
    """SHA-256 of each store plus its WAL/SHM sidecars (when present).

    A SQLite store can absorb a write into the ``-wal`` file without the main
    database file changing, so an isolation claim based on the main file alone
    would be weaker than it looks.
    """
    import hashlib

    out: Dict[str, Dict[str, Any]] = {}
    for name, path in stores.items():
        entries: Dict[str, Any] = {}
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(path) + suffix)
            if not p.exists():
                entries[suffix or "main"] = None
                continue
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            entries[suffix or "main"] = h.hexdigest()
        out[name] = entries
    return out


def normalized_scenario_nodes(scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise a scenario record to a uniform per-node outcome list.

    Single-node scenarios keep the node fields at the top level; the decomposed
    scenario lists them under ``nodes``. Both are reduced to the same keys so
    check logic never has to special-case one shape.
    """
    if scenario.get("nodes"):
        return [{
            "node_id": n.get("node_id"),
            "worker_id": n.get("worker_id"),
            "state": n.get("state"),
            "dispatch_count": n.get("dispatch_count", len(n.get("dispatch_attempts") or [])),
            "final_verification": n.get("final_verification"),
            "blocking_reason": n.get("blocking_reason"),
            "failure_attribution": n.get("failure_attribution"),
            "persisted_node_state": n.get("persisted_node_state"),
            "e2_request_ids": n.get("e2_request_ids") or [],
            "provider_errors": [a.get("error") for a in (n.get("dispatch_attempts") or [])
                                if a.get("error")],
        } for n in scenario["nodes"]]
    if "node_state" in scenario:
        return [{
            "node_id": scenario.get("node_id"),
            "worker_id": scenario.get("assigned_worker"),
            "state": scenario.get("node_state"),
            "dispatch_count": len(scenario.get("dispatch_attempts") or []),
            "final_verification": scenario.get("final_verification"),
            "blocking_reason": scenario.get("blocking_reason"),
            "failure_attribution": scenario.get("failure_attribution"),
            "persisted_node_state": scenario.get("persisted_node_state"),
            "e2_request_ids": scenario.get("e2_request_ids") or [],
            "provider_errors": [a.get("error")
                                for a in (scenario.get("dispatch_attempts") or [])
                                if a.get("error")],
        }]
    return []


def _dependency_gate_ordered(multi: Dict[str, Any]) -> bool:
    """Prove from the persisted log that a dependent node only reached READY
    after the node it depends on was persisted COMPLETE."""
    log = multi.get("persisted_plan_state_log") or []
    deps = multi.get("dag_dependencies") or {}
    if not log:
        return False
    index = {(e["node_id"], e["new_state"]): i for i, e in enumerate(log)}
    for node_id, node_deps in deps.items():
        if not node_deps:
            continue
        ready_at = index.get((node_id, "READY"))
        if ready_at is None:
            return False
        for dep in node_deps:
            complete_at = index.get((dep, "COMPLETE"))
            if complete_at is None or complete_at > ready_at:
                return False
    return True


class CountingAdapterStub:
    """Deterministic stub used to prove a refusal spends no provider call."""

    def __init__(self):
        self.calls = 0

    def dispatch(self, contract):  # pragma: no cover - must never be reached
        self.calls += 1
        raise AssertionError("a non-routable worker must never be dispatched")


class E3ExecutionRehearsal:
    """Drives the real E3 production execution path and records evidence."""

    def __init__(self, runtime_root: Optional[Path] = None,
                 scratch_root: Optional[Path] = None,
                 db_path: Optional[Path] = None):
        self.runtime_root = Path(runtime_root or RUNTIME_ROOT)
        self.db_path = Path(db_path) if db_path else self.runtime_root / "orchestration.db"
        self.scratch_root = Path(
            scratch_root or Path(tempfile.mkdtemp(prefix="e3-exec-rehearsal-"))
        )
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        self.scenarios: List[Dict[str, Any]] = []
        self.adapter_call_log: List[Dict[str, Any]] = []
        # Filled by run(); kept on the instance so checks() can read them.
        self.isolation: Dict[str, Any] = {}
        self.live_store_contamination: Dict[str, Any] = {}
        # Which real-path scenarios this run actually attempted. A scenario that
        # was deliberately not requested is reported as "not evaluated" (None)
        # rather than as a pass — an unrun scenario is not a success.
        self.scenarios_requested: Dict[str, bool] = {
            "codex_cli": True, "multi_node": True, "google_image": False,
        }

    # ── helpers ─────────────────────────────────────────────────────
    def _single_node_plan(self, plan_id: str, objective: str, role: str,
                          expected_exact: Optional[str]) -> Dict[str, Any]:
        node = {
            "node_id": f"node-{plan_id}-1",
            "objective": objective,
            "capability_roles": [role],
            "dependencies": [],
            "inputs": {},
            "expected_outputs": ({"exact_content": expected_exact}
                                 if expected_exact else {}),
            "verification_method": "test",
            "floor_id": None,
            "allowed_tools": [],
            "permissions": {},
        }
        if role == "builder-cli":
            node["capability_roles"] = ["builder"]
            node["working_directory"] = str(self.scratch_root)
        return {"plan_id": plan_id, "decomposition": False,
                "reason": "execution-leg rehearsal", "nodes": [node]}

    @staticmethod
    def _assembly(plan: Dict[str, Any], worker_id: str, role: str):
        from e3_team_assembly import TeamAssembler
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        from e3_team_assembly import TeamAssignment
        assembly.assignments.clear()
        assembly.issues = []
        assembly.add_assignment(TeamAssignment(plan["nodes"][0]["node_id"],
                                               worker_id, role, "HIGH",
                                               "execution-leg rehearsal"))
        assembly.complete = True
        return assembly

    def _store(self):
        from e3_execution import OrchestrationStore
        return OrchestrationStore(self.db_path)

    def _fingerprint(self):
        from task_fingerprint import TaskFingerprint
        return TaskFingerprint(task_family="code", reasoning_depth=1,
                               risk_class="R1", required_roles=["builder"],
                               verification_type="deterministic")

    def _multi_fingerprint(self):
        """Fingerprint that makes the real planner decompose into 2 nodes.

        ``required_roles`` of length >= 2 crosses the planner's multi-role
        threshold, so the plan shape is decided by the planner, not by this
        rehearsal.
        """
        from task_fingerprint import TaskFingerprint
        return TaskFingerprint(task_family="code", reasoning_depth=1,
                               risk_class="R1",
                               required_roles=["builder", "integrator"],
                               verification_type="deterministic")

    def multi_node_plan(self):
        """A decomposed plan produced by the real planner, with a deterministic
        per-node contract added for verification.

        The shape (node count, roles, dependency chain) comes from
        ``E3Planner.plan``. This method only annotates each node with the exact
        literal its output must equal (the deterministic contract) and, for the
        builder node, leaves attempt 1 genuinely under-specified so the
        independent verifier rejects it and the targeted repair path runs.
        """
        from e3_planner import E3Planner
        objective = "Rehearsal (execution leg): decomposed multi-worker plan"
        plan = E3Planner().plan(objective, self._multi_fingerprint())
        tokens: Dict[str, str] = {}
        for node in plan["nodes"]:
            role = (node.get("capability_roles") or ["builder"])[0]
            token = (TOKEN_NODE_INTEGRATOR if role == "integrator"
                     else TOKEN_NODE_BUILDER)
            tokens[node["node_id"]] = token
            expected = dict(node.get("expected_outputs") or {})
            expected["exact_content"] = token
            node["expected_outputs"] = expected
            if role == "integrator":
                node["objective"] = (
                    f"{node['objective']}\n\nReply with exactly {token} and "
                    "nothing else.")
                node["working_directory"] = str(self.scratch_root)
            else:
                node["objective"] = (
                    f"{node['objective']}\n\nIn one short sentence, tell the "
                    "operator what you are.")
        return plan, tokens, objective

    def _run_scenario(self, name: str, objective: str, worker_id: str, role: str,
                      test_cases: List[Dict[str, Any]],
                      expected_exact: Optional[str] = None,
                      max_repair_attempts: int = 1,
                      dispatch_timeout: int = 120,
                      adapter_registry: Any = None,
                      require_real_worker: bool = True,
                      notes: str = "") -> Dict[str, Any]:
        from e3_execution import E3ProductionExecutor
        from execution_dag import ExecutionDAG
        from e3_planner import E3Planner

        plan_id = f"execleg-{name}"
        plan = self._single_node_plan(plan_id, objective, role, expected_exact)
        dag = E3Planner().build_dag(plan)
        assembly = self._assembly(plan, worker_id, plan["nodes"][0]["capability_roles"][0])
        node_id = plan["nodes"][0]["node_id"]

        if adapter_registry is None:
            from e3_execution import ExecutionAdapterRegistry
            adapter_registry = ExecutionAdapterRegistry()

        store = self._store()
        try:
            executor = E3ProductionExecutor(store, adapter_registry)
            run = executor.execute_plan(
                plan, dag, assembly, self._fingerprint(), objective,
                verification_test_cases_by_node={node_id: test_cases},
                max_repair_attempts=max_repair_attempts,
                dispatch_timeout=dispatch_timeout,
                role_by_node={node_id: plan["nodes"][0]["capability_roles"][0]},
            )
            read_back = store.read_back(node_id)
        finally:
            store.close()

        node_run = run["nodes"][0]
        scenario = {
            "scenario": name,
            "notes": notes,
            "plan_id": plan_id,
            "node_id": node_id,
            "objective": objective,
            "assigned_worker": worker_id,
            "role": plan["nodes"][0]["capability_roles"][0],
            "real_worker_required": require_real_worker,
            "worker_routable": adapter_registry.is_routable(worker_id),
            "expected_exact_content": expected_exact,
            "verification_test_cases": test_cases,
            "max_repair_attempts": max_repair_attempts,
            "run_outcome": run["outcome"],
            "node_state": node_run["state"],
            "dispatch_attempts": node_run["dispatch_attempts"],
            "verification_attempts": node_run["verification_attempts"],
            "rejections": node_run["rejections"],
            "repairs": node_run["repairs"],
            "final_verification": node_run["final_verification"],
            "blocking_reason": node_run["blocking_reason"],
            "failure_attribution": node_run["failure_attribution"],
            "e2_request_ids": node_run["e2_request_ids"],
            "evidence_id": node_run["evidence_id"],
            "persisted_node_state": (read_back["node"] or {}).get("state"),
            "persisted_assigned_worker": (read_back["node"] or {}).get("assigned_worker"),
            "persisted_state_events": [
                {"previous": e["previous_state"], "new": e["new_state"],
                 "cause": e["cause"]}
                for e in read_back["state_events"]
            ],
            "persisted_evidence": read_back["evidence"],
        }
        for attempt in node_run["dispatch_attempts"]:
            self.adapter_call_log.append({
                "scenario": name, "worker_id": worker_id,
                "dispatch_id": attempt["dispatch_id"],
                "status": attempt["status"],
                "provider": attempt["provider"],
                "model": attempt["model"],
                "usage_exposed": attempt["usage_exposed"],
                "usage": attempt["usage"],
                "e2_request_id": attempt["e2_request_id"],
                "objective_hash": attempt["objective_hash"],
                "runtime_s": attempt["runtime_s"],
            })
        self.scenarios.append(scenario)
        return scenario

    # ── scenarios ───────────────────────────────────────────────────
    def scenario_repair_cycle(self) -> Dict[str, Any]:
        """Real deepseek dispatch → genuine deterministic rejection → targeted
        repair re-dispatch → successful re-verification → COMPLETE."""
        objective = ("Rehearsal (execution leg): in one short sentence, tell the "
                     "operator what you are.")
        return self._run_scenario(
            "A_repair_cycle_deepseek",
            objective, "deepseek-v41-flash", "builder",
            test_cases=[{"name": "exact rehearsal token", "field": "content_stripped",
                         "expected": TOKEN_REPAIR}],
            expected_exact=TOKEN_REPAIR,
            max_repair_attempts=1,
            notes=("Attempt 1 is a genuinely under-specified instruction: the real "
                   "response cannot equal the declared token, so the deterministic "
                   "verifier rejects it. The targeted repair re-dispatches with the "
                   "plan's declared exact content."),
        )

    def scenario_first_pass(self) -> Dict[str, Any]:
        """Real deepseek dispatch that satisfies deterministic verification on the
        first attempt → COMPLETE with exactly one provider call."""
        objective = (f"Rehearsal (execution leg): reply with exactly {TOKEN_FIRSTPASS} "
                     "and nothing else.")
        return self._run_scenario(
            "B_first_pass_deepseek",
            objective, "deepseek-v41-flash", "builder",
            test_cases=[{"name": "exact rehearsal token", "field": "content_stripped",
                         "expected": TOKEN_FIRSTPASS}],
            expected_exact=TOKEN_FIRSTPASS,
            max_repair_attempts=0,
            notes="One bounded call; deterministic first-pass PASS expected.",
        )

    def scenario_codex_cli(self) -> Dict[str, Any]:
        """Real Codex CLI execution through its own ExecutionAdapter."""
        objective = (f"Reply with exactly this text and nothing else: {TOKEN_CODEX}")
        return self._run_scenario(
            "C_codex_cli_dispatch",
            objective, "codex-cli", "builder-cli",
            test_cases=[{"name": "exact rehearsal token", "field": "content_stripped",
                         "expected": TOKEN_CODEX}],
            expected_exact=TOKEN_CODEX,
            max_repair_attempts=0,
            dispatch_timeout=240,
            notes=("One bounded non-interactive Codex CLI call in a scratch working "
                   "directory; no repository change requested."),
        )

    def scenario_decomposed_multi_worker(self) -> Dict[str, Any]:
        """Scenario F — the decomposed multi-worker real dispatch.

        A planner-produced 2-node plan (builder -> integrator) is dispatched to
        two *different* real worker ExecutionAdapters. Node 1's first attempt is
        genuinely rejected by the deterministic verifier, moves to REWORK and is
        repaired into a PASS; node 2 is dependency-gated, so it is only dispatched
        after node 1 is persisted COMPLETE. Every node is independently verified
        before it can reach COMPLETE.
        """
        from e3_execution import E3ProductionExecutor, ExecutionAdapterRegistry
        from e3_team_assembly import TeamAssembler, TeamAssignment
        from e3_planner import E3Planner

        plan, tokens, objective = self.multi_node_plan()
        plan_id = plan["plan_id"]
        nodes = plan["nodes"]
        dag = E3Planner().build_dag(plan)

        registry = ExecutionAdapterRegistry()
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.assignments.clear()
        assembly.issues = []
        role_by_node: Dict[str, str] = {}
        assignments: List[Dict[str, Any]] = []
        for node in nodes:
            role = (node.get("capability_roles") or ["builder"])[0]
            worker_id = MULTI_NODE_WORKERS.get(role, "deepseek-v41-flash")
            role_by_node[node["node_id"]] = role
            assembly.add_assignment(TeamAssignment(
                node["node_id"], worker_id, role, "HIGH",
                "decomposed multi-worker rehearsal assignment"))
            assignments.append({"node_id": node["node_id"], "role": role,
                                "worker_id": worker_id,
                                "worker_routable": registry.is_routable(worker_id)})
        assembly.complete = True

        test_cases_by_node = {
            node["node_id"]: [{
                "name": f"{node['node_id']} exact token",
                "field": "content_stripped",
                "expected": tokens[node["node_id"]],
            }]
            for node in nodes
        }

        store = self._store()
        try:
            executor = E3ProductionExecutor(store, registry)
            run = executor.execute_plan(
                plan, dag, assembly, self._multi_fingerprint(), objective,
                verification_test_cases_by_node=test_cases_by_node,
                max_repair_attempts=1,
                dispatch_timeout=300,
                role_by_node=role_by_node,
            )
            plan_state_log = store.state_log(plan_id)
            read_back = {n["node_id"]: store.read_back(n["node_id"])
                         for n in nodes}
        finally:
            store.close()

        node_detail = []
        for node_run in run["nodes"]:
            nid = node_run["node_id"]
            node_detail.append({
                "node_id": nid,
                "role": role_by_node.get(nid),
                "worker_id": node_run["worker_id"],
                "state": node_run["state"],
                "dispatch_count": len(node_run["dispatch_attempts"]),
                "dispatch_attempts": node_run["dispatch_attempts"],
                "verification_attempts": node_run["verification_attempts"],
                "rejections": node_run["rejections"],
                "repairs": node_run["repairs"],
                "final_verification": node_run["final_verification"],
                "blocking_reason": node_run["blocking_reason"],
                "failure_attribution": node_run["failure_attribution"],
                "e2_request_ids": node_run["e2_request_ids"],
                "evidence_id": node_run["evidence_id"],
                "persisted_node_state": (read_back[nid]["node"] or {}).get("state"),
                "persisted_assigned_worker": (read_back[nid]["node"] or {}).get("assigned_worker"),
                "persisted_evidence": read_back[nid]["evidence"],
            })

        for node_run in run["nodes"]:
            for attempt in node_run["dispatch_attempts"]:
                self.adapter_call_log.append({
                    "scenario": "F_decomposed_multi_worker",
                    "worker_id": node_run["worker_id"],
                    "node_id": node_run["node_id"],
                    "dispatch_id": attempt["dispatch_id"],
                    "status": attempt["status"],
                    "provider": attempt["provider"],
                    "model": attempt["model"],
                    "usage_exposed": attempt["usage_exposed"],
                    "usage": attempt["usage"],
                    "e2_request_id": attempt["e2_request_id"],
                    "objective_hash": attempt["objective_hash"],
                    "runtime_s": attempt["runtime_s"],
                })

        scenario = {
            "scenario": "F_decomposed_multi_worker",
            "notes": ("Decomposed multi-worker plan on the real path: the plan shape "
                      "comes from E3Planner (multi-role threshold), each node is "
                      "annotated with a deterministic exact-content contract, and "
                      "each node is dispatched to its own real worker adapter."),
            "plan_id": plan_id,
            "objective": objective,
            "plan_decomposition": plan.get("decomposition"),
            "plan_reason": plan.get("reason"),
            "node_count": len(nodes),
            "plan_nodes": [{"node_id": n["node_id"],
                            "roles": n.get("capability_roles"),
                            "dependencies": n.get("dependencies")}
                           for n in nodes],
            "dag_dependencies": {nid: (list(node.dependencies) if node else [])
                                 for nid, node in dag.nodes.items()},
            "assignments": assignments,
            "distinct_workers_dispatched": sorted({a["worker_id"] for a in assignments}),
            "expected_exact_content_by_node": tokens,
            "verification_test_cases_by_node": test_cases_by_node,
            "run_outcome": run["outcome"],
            "nodes_complete": run["nodes_complete"],
            "nodes": node_detail,
            "persisted_plan_state_log": plan_state_log,
        }
        self.scenarios.append(scenario)
        return scenario

    def scenario_google_image(self) -> Dict[str, Any]:
        """Real Google image worker dispatch through the image ExecutionAdapter."""
        objective = ("Generate a small solid white square image, 64 by 64 pixels.")
        return self._run_scenario(
            "D_google_image_dispatch",
            objective, "google-nano-banana-2", "vision",
            test_cases=[
                {"name": "dispatch completed", "field": "status", "expected": "COMPLETED"},
                {"name": "image decoded", "field": "image_decode_ok", "expected": True},
            ],
            expected_exact=None,
            max_repair_attempts=0,
            dispatch_timeout=120,
            notes=("One bounded image call. Verification is the real decoded-image "
                   "check (inline image part present and header-decodable)."),
        )

    def scenario_non_routable_refusal(self) -> Dict[str, Any]:
        """A credential-missing worker must be refused with zero provider calls."""
        stub = CountingAdapterStub()
        from e3_execution import ExecutionAdapterRegistry
        from worker_registry import WorkerRegistry
        registry = ExecutionAdapterRegistry(
            worker_registry=WorkerRegistry(),
            adapter_factories={"mistral-small-4": lambda: stub},
            usage_reporters={"mistral-small-4": lambda r: None},
        )
        result = self._run_scenario(
            "E_non_routable_refusal",
            "Rehearsal (execution leg): this must never be dispatched.",
            "mistral-small-4", "builder",
            test_cases=[{"name": "never verified", "field": "content_stripped",
                         "expected": "anything"}],
            max_repair_attempts=0,
            adapter_registry=registry,
            require_real_worker=False,
            notes=("Credential-missing worker (routable=false). The node must be "
                   "recorded BLOCKED and the adapter must never be called."),
        )
        result["stub_dispatch_calls"] = stub.calls
        result["refusal_honoured"] = (
            stub.calls == 0 and result["node_state"] == "BLOCKED"
            and result["blocking_reason"] == "worker_not_routable:mistral-small-4"
            and result["dispatch_attempts"] == []
        )
        return result

    # ── isolation / boundary evidence ───────────────────────────────
    def isolation_proof(self) -> Dict[str, Any]:
        """Re-prove that rehearsal/simulated evidence cannot reach the
        qualification or production evidence stores.

        Two independent parts:
        1. fail-closed guard: a rehearsal-tagged write aimed at each live
           production store must be REFUSED (exception), not written;
        2. before/after content hashes: the simulated-evidence path (isolated
           sink in the scratch root) leaves every production store byte
           identical.

        The stores hashed here are the live E3/E1/E2 stores. The real-execution
        phase of this rehearsal legitimately appends *real* execution rows to the
        E3 store afterwards; that is measured separately by
        ``live_store_contamination_check`` (which asserts no simulated/shadow
        row and no QUALIFIED claim ever appears).
        """
        from e3_production_rehearsal import (
            EvidenceIsolationGuard, RehearsalEvidenceSink, RehearsalIsolationError,
            _sha256_file, scan_e1_e2_boundary,
        )

        guard = EvidenceIsolationGuard()
        before = guard.capture()
        # WAL sidecars are hashed too: a store can receive a write that only
        # lands in the -wal file before a checkpoint, so hashing the main file
        # alone would understate the claim.
        before_all = _store_file_hashes(guard.production_stores)
        # Part 1 — fail closed on every production store.
        refusals = []
        for name, path in guard.production_stores.items():
            try:
                guard.guard_write(path, rehearsal_evidence=True)
                refusals.append({"store": name, "path": str(path),
                                 "refused": False})
            except RehearsalIsolationError as exc:
                refusals.append({"store": name, "path": str(path),
                                 "refused": True, "error": type(exc).__name__})
        # Part 2 — simulated evidence bundle goes to the isolated scratch store.
        isolated = Path(self.scratch_root) / "rehearsal_evidence_isolation" / "rehearsal_evidence.json"
        sink = RehearsalEvidenceSink(isolated, guard, rehearsal=True)
        sink.persist({"scenario": "isolation_probe", "simulated": True,
                      "note": "simulated evidence must never be loaded into a "
                              "qualification or production evidence store"})
        sink_path = sink.flush()

        unchanged, diffs = guard.assert_unchanged()
        after = {name: _sha256_file(p) for name, p in guard.production_stores.items()}
        after_all = _store_file_hashes(guard.production_stores)
        return {
            "production_stores": {k: str(v) for k, v in guard.production_stores.items()},
            "before_sha256": before,
            "after_sha256": after,
            "stores_unchanged": unchanged,
            "diffs": diffs,
            "before_sha256_including_wal_sidecars": before_all,
            "after_sha256_including_wal_sidecars": after_all,
            "stores_unchanged_including_wal_sidecars": before_all == after_all,
            "rehearsal_write_refusals": refusals,
            "all_production_writes_refused": all(r["refused"] for r in refusals),
            "isolated_rehearsal_store": str(sink_path),
            "isolated_store_outside_production": not guard.is_production_store(sink_path),
            "boundary_scan": scan_e1_e2_boundary(),
        }

    def live_store_contamination_check(self) -> Dict[str, Any]:
        """Assert the live stores contain no simulated/shadow evidence and no
        unearned QUALIFICATION.

        The real-execution phase writes real execution rows into the live E3
        store, so "unchanged" cannot be asserted for it. What must hold is that
        nothing simulated and no fabricated qualification landed there.
        """
        out: Dict[str, Any] = {"orchestration_db": str(self.db_path)}
        if not Path(self.db_path).exists():
            out["exists"] = False
            return out
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            out["performance_evidence_by_execution_profile"] = {
                str(r["execution_profile"]): r["n"] for r in con.execute(
                    "SELECT execution_profile, COUNT(*) AS n FROM performance_evidence "
                    "GROUP BY execution_profile").fetchall()}
            out["performance_evidence_by_provider"] = {
                str(r["provider"]): r["n"] for r in con.execute(
                    "SELECT provider, COUNT(*) AS n FROM performance_evidence "
                    "GROUP BY provider").fetchall()}
            out["simulated_or_shadow_evidence_rows"] = con.execute(
                "SELECT COUNT(*) FROM performance_evidence WHERE "
                "LOWER(COALESCE(provider,'')) IN ('shadow','rehearsal','simulated') "
                "OR LOWER(COALESCE(execution_profile,'')) IN ('shadow','simulated')"
            ).fetchone()[0]
            out["qualified_rows_without_evidence"] = con.execute(
                "SELECT COUNT(*) FROM capability_registry WHERE state='QUALIFIED' "
                "AND COALESCE(evidence_count,0)=0").fetchone()[0]
            out["capability_state_counts"] = {
                str(r["state"]): r["n"] for r in con.execute(
                    "SELECT state, COUNT(*) AS n FROM capability_registry GROUP BY state")
                .fetchall()}
            out["dag_node_state_counts"] = {
                str(r["state"]): r["n"] for r in con.execute(
                    "SELECT state, COUNT(*) AS n FROM dag_node GROUP BY state").fetchall()}
            out["dag_state_event_count"] = con.execute(
                "SELECT COUNT(*) FROM dag_state_event").fetchone()[0]
            out["performance_evidence_count"] = con.execute(
                "SELECT COUNT(*) FROM performance_evidence").fetchone()[0]
        finally:
            con.close()
        out["simulated_evidence_absent"] = out["simulated_or_shadow_evidence_rows"] == 0
        out["no_unearned_qualification"] = out["qualified_rows_without_evidence"] == 0
        return out

    def e2_linkage_audit(self) -> Dict[str, Any]:
        """Confirm E2 telemetry from this run exists as rows in the live governor
        store written through the public ``governor.record_request()`` interface."""
        gov_db = self.runtime_root / "governor.db"
        if not gov_db.exists():
            return {"available": False, "path": str(gov_db)}
        ids = [rid for rid in self._e2_request_ids() if rid]
        con = sqlite3.connect(str(gov_db))
        con.row_factory = sqlite3.Row
        try:
            rows = []
            for rid in ids:
                row = con.execute(
                    "SELECT request_id, provider, model, input_tokens, output_tokens, "
                    "status FROM observed_request WHERE request_id=?",
                    (rid,)).fetchone()
                rows.append(dict(row) if row else {"request_id": rid,
                                                   "found": False})
        finally:
            con.close()
        return {"available": True, "path": str(gov_db),
                "requested_ids": ids, "rows_read_back": rows,
                "all_found": all("found" not in r for r in rows) and bool(rows)}

    def _e2_request_ids(self) -> List[str]:
        ids: List[str] = []
        for s in self.scenarios:
            ids.extend(s.get("e2_request_ids") or [])
            for node in s.get("nodes") or []:
                ids.extend(node.get("e2_request_ids") or [])
        return ids

    # ── deployment facts ────────────────────────────────────────────
    def runtime_deployment_facts(self) -> Dict[str, Any]:
        present = {m: (self.runtime_root / m).exists() for m in REQUIRED_RUNTIME_MODULES}
        cli_bindings = self._runtime_cli_bindings()
        return {
            "runtime_root": str(self.runtime_root),
            "required_modules": present,
            "missing_modules": sorted(m for m, ok in present.items() if not ok),
            "e3_cli_bindings_present": cli_bindings,
        }

    def _runtime_cli_bindings(self) -> List[str]:
        """Report which `e3-*` bindings are actually wired into the runtime.

        The runtime `eb.py` registers the whole `e3-*` set through one hook, so
        presence is proven by the hook in `eb.py` plus the declared command names
        in the deployed `e3_cli.py`.
        """
        eb = self.runtime_root / "eb.py"
        cli = self.runtime_root / "e3_cli.py"
        if not (eb.exists() and cli.exists()):
            return []
        if "_register_e3_subcommands" not in eb.read_text(encoding="utf-8",
                                                          errors="replace"):
            return []
        cli_text = cli.read_text(encoding="utf-8", errors="replace")
        return sorted(name for name in
                      ("e3-init", "e3-register-workers", "e3-status", "e3-plan",
                       "e3-route", "e3-rationale", "e3-trace", "e3-why",
                       "e3-verify-db", "e3-execute")
                      if f'"{name}"' in cli_text)

    def orchestration_db_facts(self) -> Dict[str, Any]:
        if not self.db_path.exists():
            return {"db_path": str(self.db_path), "exists": False}
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            version = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            counts = {}
            for table in ("dag_node", "dag_state_event", "performance_evidence",
                          "router_decision", "capability_registry"):
                try:
                    counts[table] = con.execute(
                        f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.Error:
                    counts[table] = None
        finally:
            con.close()
        return {"db_path": str(self.db_path), "exists": True,
                "schema_version": version, "row_counts": counts}

    # ── main ────────────────────────────────────────────────────────
    def run(self, include_codex: bool = True, include_google: bool = False,
            include_multi_node: bool = True) -> Dict[str, Any]:
        started = datetime.now(timezone.utc)
        deployment = self.runtime_deployment_facts()
        before = self.orchestration_db_facts()

        # Isolation / boundary evidence is captured *before* the real dispatch
        # phase, so the simulated-evidence path is proven not to touch the live
        # stores independently of the real execution rows this run will add.
        self.isolation = self.isolation_proof()
        self.scenarios_requested = {
            "codex_cli": bool(include_codex),
            "multi_node": bool(include_multi_node),
            "google_image": bool(include_google),
        }

        self.scenario_repair_cycle()
        self.scenario_first_pass()
        if include_codex:
            self.scenario_codex_cli()
        if include_multi_node:
            self.scenario_decomposed_multi_worker()
        if include_google:
            self.scenario_google_image()
        self.scenario_non_routable_refusal()

        after = self.orchestration_db_facts()
        self.live_store_contamination = self.live_store_contamination_check()
        e2_linkage = self.e2_linkage_audit()

        real_calls = [c for c in self.adapter_call_log if c["scenario"] != "E_non_routable_refusal"]
        by_provider: Dict[str, int] = {}
        for c in real_calls:
            key = c["provider"] or "unknown"
            by_provider[key] = by_provider.get(key, 0) + 1

        return {
            "label": "e3-production-execution-rehearsal",
            "run_started_utc": started.isoformat(timespec="seconds"),
            "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": ("E3 production execution leg rehearsal — real worker execution "
                      "on the local orchestration path; Stage 2 NOT enabled by this run"),
            "runtime_root": str(self.runtime_root),
            "scratch_root": str(self.scratch_root),
            "runtime_deployment": deployment,
            "orchestration_db_before": before,
            "orchestration_db_after": after,
            "scenarios": self.scenarios,
            "real_dispatch_log": self.adapter_call_log,
            "usage_plan": USAGE_PLAN,
            "usage_plan_total_calls": USAGE_PLAN_TOTAL,
            "bounded_usage": {
                "real_provider_calls": len(real_calls),
                "planned_calls": USAGE_PLAN_TOTAL,
                "calls_by_provider": by_provider,
                "usage_exposed_calls": sum(1 for c in real_calls if c["usage_exposed"]),
                "usage_missing_calls": sum(1 for c in real_calls if not c["usage_exposed"]),
                "note": ("Minimum deterministic calls needed to evidence the path, "
                         "stated up front in usage_plan. Usage is recorded only when "
                         "the provider returned it."),
            },
            "isolation": self.isolation,
            "live_store_contamination": self.live_store_contamination,
            "e2_linkage": e2_linkage,
            "scenarios_requested": self.scenarios_requested,
            "checks": self.checks(),
            "unresolved": [
                {
                    "scenario": s["scenario"],
                    "node": n["node_id"],
                    "worker": n["worker_id"],
                    "node_state": n["state"],
                    "blocking_reason": n["blocking_reason"],
                    "failure_attribution": n["failure_attribution"],
                    "provider_errors": n["provider_errors"],
                    "expected_block": s["scenario"] == "E_non_routable_refusal",
                }
                for s in self.scenarios for n in normalized_scenario_nodes(s)
                if n["state"] != "COMPLETE"
            ],
        }

    def checks(self) -> Dict[str, Any]:
        by_name = {s["scenario"]: s for s in self.scenarios}
        repair = by_name.get("A_repair_cycle_deepseek", {})
        first = by_name.get("B_first_pass_deepseek", {})
        codex = by_name.get("C_codex_cli_dispatch")
        multi = by_name.get("F_decomposed_multi_worker")
        google = by_name.get("D_google_image_dispatch")
        refusal = by_name.get("E_non_routable_refusal", {})

        def _real(scenario: Optional[Dict[str, Any]], requested: bool):
            """Completeness of an optional real-path scenario.

            None means the scenario was deliberately not part of this run; an
            unrun scenario must never be reported as passing.
            """
            if not requested:
                return None
            if not scenario:
                return False
            return all(n["state"] == "COMPLETE"
                       for n in normalized_scenario_nodes(scenario))

        req = self.scenarios_requested

        def _gated(name: str, value: Any) -> Any:
            """Return None for a check whose scenario was not requested."""
            return value if req.get(name) else None

        def _persisted(scenario: Dict[str, Any]) -> bool:
            nodes = normalized_scenario_nodes(scenario)
            if not nodes:
                return False
            if not all(n["persisted_node_state"] == n["state"] for n in nodes):
                return False
            if scenario.get("nodes"):  # decomposed scenario
                return bool(scenario.get("persisted_plan_state_log"))
            return bool(scenario.get("persisted_state_events"))

        return {
            "repair_cycle_rejected_then_repaired": (
                len(repair.get("rejections", [])) >= 1
                and len(repair.get("repairs", [])) >= 1
                and repair.get("node_state") == "COMPLETE"
                and [v["passed"] for v in repair.get("verification_attempts", [])][-1:] == [True]
            ),
            "first_pass_complete": first.get("node_state") == "COMPLETE",
            "codex_cli_complete": _real(codex, req.get("codex_cli", False)),
            "multi_node_plan_is_decomposed": _gated("multi_node", bool(
                multi and multi.get("plan_decomposition") is True
                and multi.get("node_count", 0) >= 2)),
            "multi_node_all_nodes_complete": _gated("multi_node", bool(
                multi and multi.get("nodes")
                and all(n["state"] == "COMPLETE" for n in multi["nodes"])
                and multi.get("nodes_complete") == multi.get("node_count"))),
            "multi_worker_two_distinct_routable_workers": _gated("multi_node", bool(
                multi and len(multi.get("distinct_workers_dispatched") or []) >= 2
                and all(a["worker_routable"] for a in multi.get("assignments", [])))),
            "multi_node_per_node_deterministic_verification": _gated("multi_node", bool(
                multi and all(n["final_verification"] == "PASS"
                              and n["verification_attempts"]
                              for n in multi.get("nodes", []))
                and len(multi.get("verification_test_cases_by_node", {})) == multi.get("node_count"))),
            "multi_node_rejection_then_repair": _gated("multi_node", bool(
                multi and any(n["rejections"] and n["repairs"]
                              and n["state"] == "COMPLETE"
                              for n in multi.get("nodes", [])))),
            "multi_node_dependency_gate_observed": _gated(
                "multi_node", _dependency_gate_ordered(multi or {})),
            "multi_node_dag_state_and_evidence_persisted": _gated("multi_node", bool(
                multi and all(n["persisted_node_state"] == n["state"]
                              and n["persisted_evidence"] for n in multi["nodes"])
                and multi.get("persisted_plan_state_log"))),
            "google_image_complete": _real(google, req.get("google_image", False)),
            "non_routable_refused_without_dispatch": refusal.get("refusal_honoured") is True,
            "complete_requires_verification": all(
                n["state"] != "COMPLETE" or n["final_verification"] == "PASS"
                for s in self.scenarios for n in normalized_scenario_nodes(s)
            ),
            "dag_state_and_evidence_persisted": all(
                _persisted(s) for s in self.scenarios
            ),
            "e2_linkage_recorded": any(
                rid and not str(rid).startswith("e2_linkage_error:")
                for s in self.scenarios
                for rid in (s.get("e2_request_ids") or [])
            ) or any(
                rid and not str(rid).startswith("e2_linkage_error:")
                for s in self.scenarios for n in (s.get("nodes") or [])
                for rid in (n.get("e2_request_ids") or [])
            ),
            "rehearsal_evidence_isolated_from_production_stores": (
                self.isolation.get("stores_unchanged") is True
                and self.isolation.get("stores_unchanged_including_wal_sidecars") is True
                and self.isolation.get("all_production_writes_refused") is True
                and self.isolation.get("isolated_store_outside_production") is True
            ),
            "no_simulated_evidence_in_live_stores": (
                self.live_store_contamination.get("simulated_evidence_absent") is True
                and self.live_store_contamination.get("no_unearned_qualification") is True
            ),
            "e1_e2_boundary_clean": (
                self.isolation.get("boundary_scan", {}).get("clean") is True
            ),
            "runtime_modules_deployed": not self.runtime_deployment_facts()["missing_modules"],
            "orchestration_db_is_schema_v2": (
                self.orchestration_db_facts().get("schema_version") == 2
            ),
        }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="E3 production execution rehearsal")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--no-codex", action="store_true",
                        help="skip the real Codex CLI dispatch scenario")
    parser.add_argument("--include-google", action="store_true",
                        help="also spend one real Google image call")
    parser.add_argument("--no-multi-node", action="store_true",
                        help="skip the decomposed multi-worker plan scenario")
    parser.add_argument("--db-path", default=None,
                        help="override the orchestration db (testing only)")
    args = parser.parse_args(argv)

    # State the provider-call bound up front, before anything is spent.
    print("Bounded real provider usage plan (deterministic single-shot prompts, "
          "max_tokens=256, temperature=0):")
    for entry in USAGE_PLAN:
        print(f"  - {entry['scenario']} ({entry['worker']}): {entry['calls']} call(s) "
              f"-- {entry['why']}")
    print(f"  TOTAL planned: {USAGE_PLAN_TOTAL} real provider calls"
          + (" (+1 optional Google image call)" if args.include_google else ""))

    rehearsal = E3ExecutionRehearsal(
        db_path=Path(args.db_path) if args.db_path else None)
    report = rehearsal.run(include_codex=not args.no_codex,
                           include_google=args.include_google,
                           include_multi_node=not args.no_multi_node)

    out_dir = (Path(args.out_dir) if args.out_dir else
               REPO_ROOT / "audits" / "evidence" /
               f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}"
               "-e3-production-execution-rehearsal")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")

    lines = [
        "# E3 production execution leg rehearsal",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Stage: {report['stage']}",
        f"- Runtime root: `{report['runtime_root']}`",
        f"- Orchestration DB: `{report['orchestration_db_after'].get('db_path')}` "
        f"(schema v{report['orchestration_db_after'].get('schema_version')})",
        f"- Real provider calls: {report['bounded_usage']['real_provider_calls']} "
        f"{report['bounded_usage']['calls_by_provider']} "
        f"(planned {report['bounded_usage']['planned_calls']})",
        f"- Rehearsal-evidence isolation from production stores: "
        f"{report['isolation'].get('stores_unchanged')} "
        f"(all production writes refused: "
        f"{report['isolation'].get('all_production_writes_refused')})",
        f"- E1/E2 boundary clean: "
        f"{report['isolation'].get('boundary_scan', {}).get('clean')}",
        "",
        "| Scenario | Node | Worker | Node state | Dispatches | Verifications | Rejections | Repairs |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in report["scenarios"]:
        for n in normalized_scenario_nodes(s):
            dispatch_count = len(s.get("dispatch_attempts") or [])
            node_row = next((x for x in (s.get("nodes") or [])
                             if x.get("node_id") == n["node_id"]), {})
            if node_row:
                dispatch_count = node_row.get("dispatch_count", dispatch_count)
                verifications = len(node_row.get("verification_attempts") or [])
                rejections = len(node_row.get("rejections") or [])
                repairs = len(node_row.get("repairs") or [])
            else:
                verifications = len(s.get("verification_attempts") or [])
                rejections = len(s.get("rejections") or [])
                repairs = len(s.get("repairs") or [])
            lines.append(
                f"| {s['scenario']} | {n['node_id']} | {n['worker_id']} | "
                f"{n['state']} | {dispatch_count} | {verifications} | "
                f"{rejections} | {repairs} |"
            )
    lines += ["", "## Checks", "",
              "A check reported as `None` belongs to a scenario that was not part "
              "of this run and is therefore not evaluated (an unrun scenario is "
              "never counted as a pass)."]
    for k, v in report["checks"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Scenarios requested", ""]
    for k, v in report.get("scenarios_requested", {}).items():
        lines.append(f"- {k}: {v}")
    if report["runtime_deployment"]["missing_modules"]:
        lines += ["", "Missing runtime modules: "
                  + ", ".join(report["runtime_deployment"]["missing_modules"])]
    (out_dir / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(report["checks"], indent=2))
    print(json.dumps(report["bounded_usage"], indent=2))
    print(f"evidence written to {out_dir}")
    evaluated = {k: v for k, v in report["checks"].items() if v is not None}
    return 0 if all(evaluated.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
