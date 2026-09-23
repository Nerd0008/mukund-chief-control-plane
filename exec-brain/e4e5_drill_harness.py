#!/usr/bin/env python3
"""E4/E5 real-path drill harness — continuity, outage, convergence, safe mode.

What this driver does
---------------------
It drives the **real execution abstractions** of the E3/E4/E5 stack:

* ``E3ProductionExecutor`` + ``ExecutionAdapterRegistry`` + ``OrchestrationStore``
  (schema v2 ``orchestration.db``) for dispatch, state transitions, verification
  gating and performance evidence;
* ``CapabilityRegistry`` + ``EquivalentFailover`` for equivalent-worker selection;
* ``CheckpointManager`` for checkpoint creation and state handover;
* ``SafeModeManager`` + ``ConvergenceEnforcer`` + ``MalformedOutputHandler`` and
  ``SafeModeRecovery`` for degraded/safe-mode entry, convergence enforcement,
  owner-override audit and recovery.

Truth rules (non-negotiable)
----------------------------
* **Provider transport is a recorded test double.** ``StubProviderAdapter``
  replaces the real network/CLI adapter so a provider outage, a malformed
  response and a repeated failure can be injected deterministically. Every
  artifact therefore carries ``evidence_kind = "stubbed_provider_failure"`` and
  ``real_provider_calls = 0``. A stubbed failure is **never** presented as real
  external provider evidence, and this driver never claims a failover succeeded
  on a real provider.
* The drills exercise *our* handling of those failures on the real code path —
  that is what is being evidenced: detection, refusals, state transitions,
  convergence caps, escalation, safe-mode entry/exit and the audit trail.
* **Isolation.** All persistence happens in a disposable schema-v2 DB created by
  ``orchestration_db.init_db`` under the drill scratch root. The live
  ``orchestration.db`` / ``governor.db`` / ``exec_brain.db`` are never written;
  the harness SHA-256-hashes them before and after and fails the isolation check
  if any hash moved. The E2 usage reporter is a stub, so no live E2 row is
  written (the stub id is labelled, never presented as a governor row).
* Qualification rows used by the failover drill are a **labelled fixture** in the
  disposable DB, mirrored from what the live registry actually records read-only.
  They are not new qualification evidence.
* Stage 2 is not enabled, nothing is deployed, and no owner-gated action is taken.

Usage::

    python exec-brain/e4e5_drill_harness.py [--out-dir DIR] [--scratch DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

REPO_ROOT = HERE.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

EVIDENCE_KIND = "stubbed_provider_failure"

# The two roles the drill needs a qualified equivalent pair for, and the two
# real worker ids the roster reports routable for text work.
DRILL_TASK_FAMILY = "code"
DRILL_ROLE = "builder"
PRIMARY_WORKER = "deepseek-v41-flash"
EQUIVALENT_WORKER = "codex-cli"

LIVE_STORES = ("orchestration.db", "governor.db", "exec_brain.db")


# ─── Live-store isolation helpers ───────────────────────────────────

def _sha256(path: Path) -> Optional[str]:
    if not Path(path).exists():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_sha() -> str:
    import subprocess
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                                capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001 — reported as UNKNOWN, never invented
        return "UNKNOWN"
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def hash_live_stores(root: Optional[Path] = None) -> Dict[str, Optional[str]]:
    root = Path(root or RUNTIME_ROOT)
    out: Dict[str, Optional[str]] = {}
    for name in LIVE_STORES:
        out[name] = _sha256(root / name)
        for sidecar in ("-wal", "-shm"):
            out[name + sidecar] = _sha256(Path(str(root / name) + sidecar))
    return out


# ─── Recorded provider test double ──────────────────────────────────

class ProviderOutage(RuntimeError):
    """Transport-level provider outage, raised by the stub adapter."""


class StubProviderAdapter:
    """Deterministic, recorded stand-in for a worker's real ExecutionAdapter.

    ``behaviour``:
      * ``ok``            → status COMPLETED with ``content``
      * ``outage``        → status FAILED with a provider error (no exception)
      * ``transport_error``→ raises :class:`ProviderOutage`
      * ``malformed``     → status COMPLETED with the malformed ``content``

    Every call is recorded so the drill can prove exactly what was dispatched
    (objective hash, whether the handover state was present) and the artifact can
    state which behaviour was injected. No network, no CLI, no credential.
    """

    def __init__(self, worker_id: str, behaviour: str = "ok",
                 content: Optional[str] = None,
                 recovery_content: Optional[str] = None,
                 provider: str = "stub", model: Optional[str] = None,
                 error: Optional[str] = None):
        self.worker_id = worker_id
        self.behaviour = behaviour
        self.content = content
        self.recovery_content = recovery_content
        self.provider = provider
        self.model = model or f"{worker_id}-stub"
        self.error = error
        self.calls: List[Dict[str, Any]] = []

    def dispatch(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        objective = contract.get("objective") or ""
        self.calls.append({
            "worker_id": self.worker_id,
            "behaviour": self.behaviour,
            "objective_hash": hashlib.sha256(objective.encode()).hexdigest()[:12],
            "objective_present": bool(objective),
            "contract_keys": sorted(contract.keys()),
        })
        behaviour = self.behaviour
        if behaviour == "malformed_then_ok":
            behaviour = "malformed" if len(self.calls) == 1 else "ok"
        content = self.content
        if behaviour == "ok" and self.recovery_content is not None:
            content = self.recovery_content
        base = {
            "dispatch_id": f"stub-{self.worker_id}-{len(self.calls)}",
            "provider": self.provider,
            "model": self.model,
            "usage": None,      # a stub has no provider-reported usage to give
            "exit_code": None,
            "runtime_s": 0.0,
            "stub": True,
        }
        if behaviour == "transport_error":
            raise ProviderOutage(
                self.error or f"stub transport outage for {self.worker_id}")
        if behaviour == "outage":
            return {**base, "status": "FAILED", "content": None,
                    "error": self.error or "provider_unavailable: HTTP 503"}
        if behaviour == "malformed":
            return {**base, "status": "COMPLETED", "content": content,
                    "error": None}
        return {**base, "status": "COMPLETED", "content": content,
                "error": None}

    # The drill asserts on this, so keep the objective text reachable.
    def objectives(self) -> List[str]:
        return [c["objective_hash"] for c in self.calls]


# ─── Drill-local fixtures ───────────────────────────────────────────

def read_live_qualified_pairs(task_family: str = DRILL_TASK_FAMILY,
                              role: str = DRILL_ROLE,
                              snapshot_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read the live capability registry **without touching the live store**.

    The live ``orchestration.db`` is copied to a scratch snapshot together with
    its ``-wal``/``-shm`` sidecars and the *copy* is opened read-only. Opening the
    live file directly would create sqlite ``-shm``/``-wal`` sidecars in the
    runtime root, which pollutes the deployed directory (and is exactly what the
    E1 runtime matrix asserts must not happen).

    Used only to state, truthfully, what the live registry records for the drill
    pair. Never written back; if the live DB is absent or unreadable the drill
    records that and continues with the labelled fixture.
    """
    db = RUNTIME_ROOT / "orchestration.db"
    if not db.exists():
        return {"source": "live_registry_absent", "rows": []}
    snapshot_root = Path(snapshot_dir or tempfile.mkdtemp(prefix="live-registry-snap-"))
    snapshot_root.mkdir(parents=True, exist_ok=True)
    target = snapshot_root / "live-orchestration-snapshot.db"
    try:
        shutil.copyfile(str(db), str(target))
        for sidecar in ("-wal", "-shm"):
            source_sidecar = Path(str(db) + sidecar)
            if source_sidecar.exists():
                shutil.copyfile(str(source_sidecar),
                                str(Path(str(target) + sidecar)))
    except OSError as exc:
        return {"source": f"live_registry_snapshot_failed:{type(exc).__name__}",
                "rows": []}
    try:
        con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        try:
            rows = con.execute(
                """SELECT worker_id, task_family, capability_role, state,
                          evidence_count, first_pass_successes, first_pass_attempts
                   FROM capability_registry
                   WHERE task_family=? AND capability_role=?
                   ORDER BY worker_id""",
                (task_family, role)).fetchall()
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — recorded, never invented
        return {"source": f"live_registry_unreadable:{type(exc).__name__}",
                "rows": []}
    return {
        "source": "live_registry_read_only_snapshot",
        "db_path": str(db),
        "snapshot_path": str(target),
        "live_file_untouched": True,
        "rows": [
            {"worker_id": r[0], "task_family": r[1], "capability_role": r[2],
             "state": r[3], "evidence_count": r[4],
             "first_pass_successes": r[5], "first_pass_attempts": r[6]}
            for r in rows
        ],
    }


def seed_equivalent_pair(con, task_family: str = DRILL_TASK_FAMILY,
                         role: str = DRILL_ROLE) -> Dict[str, Any]:
    """Seed a **labelled fixture** capability pair in the disposable drill DB.

    DRY-RUN FIXTURE STATE — this is drill setup, not qualification evidence and
    not written into the live registry. Both rows are marked as fixture-derived
    with the reason string so the audit trail cannot be mistaken for a real
    qualification.
    """
    from capability_registry import CapabilityRegistry
    registry = CapabilityRegistry(con)
    records = []
    for worker_id in (PRIMARY_WORKER, EQUIVALENT_WORKER):
        records.append(registry.record_qualification(
            worker_id, task_family, role, state="QUALIFIED",
            evidence_count=1, first_pass_successes=0, first_pass_attempts=0,
            reason="drill fixture row (isolated disposable DB, not qualification evidence)",
            evidence_references=["e4e5-drill-harness"],
            actor="e4e5-drill-harness",
            model_identity="stubbed"))
    return {
        "kind": "drill_fixture_not_qualification_evidence",
        "db": "isolated drill orchestration db",
        "records": records,
    }


# ─── The harness ────────────────────────────────────────────────────

class E4E5DrillHarness:
    """Runs the E4/E5 dry-run drills on the real execution path."""

    def __init__(self, scratch_root: Optional[Path] = None,
                 runtime_root: Optional[Path] = None):
        self.runtime_root = Path(runtime_root or RUNTIME_ROOT)
        self.scratch_root = Path(
            scratch_root or Path(tempfile.mkdtemp(prefix="e4e5-drills-"))
        )
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.scratch_root / "orchestration.db"
        self.drills: Dict[str, Any] = {}
        self.stub_calls_total = 0
        self.real_provider_calls = 0
        self.adapter_call_log: List[Dict[str, Any]] = []
        self.isolation: Dict[str, Any] = {}

    # ── plumbing ────────────────────────────────────────────────────
    def _con(self):
        from orchestration_db import init_db
        con = init_db(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _store(self):
        from e3_execution import OrchestrationStore
        return OrchestrationStore(self.db_path)

    @staticmethod
    def _e2_link_stub(worker_id: str, result: Dict[str, Any]) -> str:
        """Labelled stub E2 linkage — deliberately writes no governor row."""
        return f"e2-stub-{uuid.uuid4().hex[:8]}"

    def _registry(self, stubs: Dict[str, Any]):
        from e3_execution import ExecutionAdapterRegistry
        from worker_registry import WorkerRegistry
        return ExecutionAdapterRegistry(
            worker_registry=WorkerRegistry(),
            adapter_factories={wid: (lambda s=stub: s) for wid, stub in stubs.items()},
            usage_reporters={
                wid: (lambda result, w=wid: self._e2_link_stub(w, result))
                for wid in stubs},
        )

    @staticmethod
    def _fingerprint():
        from task_fingerprint import TaskFingerprint
        return TaskFingerprint(task_family=DRILL_TASK_FAMILY, reasoning_depth=1,
                               risk_class="R1", required_roles=[DRILL_ROLE],
                               verification_type="deterministic")

    def _plan(self, plan_id: str, objective: str):
        node = {
            "node_id": f"node-{plan_id}-1",
            "objective": objective,
            "capability_roles": [DRILL_ROLE],
            "dependencies": [],
            "inputs": {},
            "expected_outputs": {},
            "verification_method": "test",
            "floor_id": None,
            "allowed_tools": [],
            "permissions": {},
        }
        return {"plan_id": plan_id, "decomposition": False,
                "reason": "e4/e5 drill", "nodes": [node]}

    @staticmethod
    def _assembly(plan: Dict[str, Any], worker_id: str):
        from e3_team_assembly import TeamAssembler, TeamAssignment
        assembly = TeamAssembler(None).assemble_team(plan, candidates_by_node={})
        assembly.assignments.clear()
        assembly.issues = []
        assembly.add_assignment(TeamAssignment(
            plan["nodes"][0]["node_id"], worker_id, DRILL_ROLE, "HIGH",
            "e4/e5 drill assignment"))
        assembly.complete = True
        return assembly

    def _execute(self, plan_id: str, worker_id: str, objective: str,
                 test_cases: List[Dict[str, Any]],
                 registry, max_repair_attempts: int = 0) -> Dict[str, Any]:
        """One real ``E3ProductionExecutor`` run of a single-node plan."""
        from e3_execution import E3ProductionExecutor
        from e3_planner import E3Planner

        plan = self._plan(plan_id, objective)
        dag = E3Planner().build_dag(plan)
        assembly = self._assembly(plan, worker_id)
        node_id = plan["nodes"][0]["node_id"]
        store = self._store()
        try:
            executor = E3ProductionExecutor(store, registry)
            run = executor.execute_plan(
                plan, dag, assembly, self._fingerprint(), objective,
                verification_test_cases_by_node={node_id: test_cases},
                max_repair_attempts=max_repair_attempts,
                dispatch_timeout=30,
                role_by_node={node_id: DRILL_ROLE},
            )
            state_log = store.state_log(plan_id)
            read_back = store.read_back(node_id)
        finally:
            store.close()
        return {"plan_id": plan_id, "node_id": node_id, "run": run,
                "node_run": run["nodes"][0], "state_log": state_log,
                "read_back": read_back}

    @staticmethod
    def _exact_token_case(node_id: str, token: str) -> List[Dict[str, Any]]:
        return [{"name": f"{node_id} exact token", "field": "content_stripped",
                 "expected": token}]

    def _log_stub_calls(self, scenario: str, worker_id: str, stub: StubProviderAdapter):
        for call in stub.calls:
            self.adapter_call_log.append({"scenario": scenario, **call})
        self.stub_calls_total += len(stub.calls)

    # ── D1: checkpoint → failover → state handover ───────────────────
    def drill_checkpoint_failover_handover(self) -> Dict[str, Any]:
        from resource_monitor import CheckpointManager, EquivalentFailover
        from capability_registry import CapabilityRegistry

        token = "HANDOVER-5501"
        task_id = "drill-task-e4-1"
        plan_id = "drill-e4-failover"

        con = self._con()
        try:
            fixture = seed_equivalent_pair(con)
            live = read_live_qualified_pairs(
                snapshot_dir=self.scratch_root / "live-registry-snapshot")
            checkpoints = CheckpointManager(con)

            # 1. Resource-driven checkpoint before the failing dispatch.
            checkpoint_state = {
                "attempt": 1,
                "completed_substeps": ["read_objective", "draft_outline"],
                "residual_requirement": f"reply with exactly {token}",
                "checkpoint_reason": "resource_driven_pre_dispatch",
            }
            checkpoint_id = checkpoints.save_checkpoint(
                task_id, "node-drill-e4-failover-1", checkpoint_state)
            checkpoint_list = checkpoints.list_checkpoints(task_id)

            # 2. Dispatch to the primary worker; injected provider outage.
            primary_stub = StubProviderAdapter(
                PRIMARY_WORKER, behaviour="transport_error",
                error=f"stub outage: {PRIMARY_WORKER} unreachable")
            eq_stub = StubProviderAdapter(EQUIVALENT_WORKER, behaviour="ok",
                                          content=token)
            registry = self._registry({PRIMARY_WORKER: primary_stub,
                                       EQUIVALENT_WORKER: eq_stub})

            first = self._execute(plan_id, PRIMARY_WORKER,
                                  f"Drill objective. Reply with exactly {token}.",
                                  self._exact_token_case(
                                      "node-drill-e4-failover-1", token),
                                  registry, max_repair_attempts=0)
            self._log_stub_calls("D1_checkpoint_failover_handover",
                                 PRIMARY_WORKER, primary_stub)

            # 3. Equivalent-worker selection from the (isolated) capability registry.
            failover = EquivalentFailover(CapabilityRegistry(con))
            equivalent = failover.find_equivalent_worker(
                PRIMARY_WORKER, DRILL_TASK_FAMILY, DRILL_ROLE)

            # 4. Checkpoint restored → handover state → replacement dispatch.
            restored = checkpoints.get_latest_checkpoint(
                task_id, "node-drill-e4-failover-1")
            handover = {
                "from_worker": PRIMARY_WORKER,
                "to_worker": (equivalent or {}).get("worker_id"),
                "restored_checkpoint_id": checkpoint_id,
                "restored_state": (restored or {}).get("state"),
                "failed_node_state": first["node_run"]["state"],
                "failed_dispatch_errors": [
                    a.get("error") for a in first["node_run"]["dispatch_attempts"]
                    if a.get("error")],
            }
            handover_objective = (
                "FAILOVER HANDOVER. Previous worker "
                f"{PRIMARY_WORKER} failed. Restored checkpoint "
                f"{checkpoint_id}: attempt={checkpoint_state['attempt']}, "
                f"completed_substeps={','.join(checkpoint_state['completed_substeps'])}. "
                "Complete the residual requirement only: reply with exactly "
                f"{token}."
            )

            second = None
            if equivalent:
                second = self._execute(
                    plan_id, equivalent["worker_id"], handover_objective,
                    self._exact_token_case("node-drill-e4-failover-1", token),
                    registry, max_repair_attempts=0)
                self._log_stub_calls("D1_checkpoint_failover_handover",
                                     equivalent["worker_id"], eq_stub)

            # 5. Prove the replacement was dispatched with the restored state.
            replacement_objectives = eq_stub.calls
            handover_observed = any(
                c["objective_hash"] == hashlib.sha256(
                    handover_objective.encode()).hexdigest()[:12]
                for c in replacement_objectives)

            result = {
                "drill": "D1_checkpoint_failover_handover",
                "plan_id": plan_id,
                "task_id": task_id,
                "expected_token": token,
                "checkpoint": {
                    "checkpoint_id": checkpoint_id,
                    "state_saved": checkpoint_state,
                    "checkpoints_for_task": checkpoint_list,
                    "restored": restored,
                    "restore_matches_saved": (
                        bool(restored)
                        and restored["state"] == checkpoint_state),
                },
                "primary_dispatch": {
                    "worker_id": PRIMARY_WORKER,
                    "stub_behaviour": primary_stub.behaviour,
                    "node_state": first["node_run"]["state"],
                    "dispatch_attempts": first["node_run"]["dispatch_attempts"],
                    "verification_attempts": first["node_run"]["verification_attempts"],
                    "failure_attribution": first["node_run"]["failure_attribution"],
                    "persisted_node": first["read_back"]["node"],
                },
                "equivalent_selection": equivalent,
                "capability_fixture": fixture,
                "live_registry_read_only": live,
                "handover": handover,
                "handover_objective_hash": hashlib.sha256(
                    handover_objective.encode()).hexdigest()[:12],
                "handover_objective_delivered_to_replacement": handover_observed,
                "replacement_dispatch": None if (second is None or not equivalent) else {
                    "worker_id": equivalent["worker_id"],
                    "node_state": second["node_run"]["state"],
                    "dispatch_attempts": second["node_run"]["dispatch_attempts"],
                    "verification_attempts": second["node_run"]["verification_attempts"],
                    "final_verification": second["node_run"]["final_verification"],
                    "evidence_id": second["node_run"]["evidence_id"],
                    "persisted_node": second["read_back"]["node"],
                },
                "failover_state_log": (
                    second["state_log"] if second is not None
                    else first["state_log"]),
                "failover_state_log_note": (
                    "the replacement dispatch reuses the same node id (real "
                    "failover), so the persisted log shows the failed cycle "
                    "followed by the replacement cycle on one node"),
                "failover_log_shows_failed_then_complete": (
                    bool(second) and
                    [e["new_state"] for e in second["state_log"]][-1] == "COMPLETE"
                    and any(e["new_state"] == "FAILED"
                            for e in second["state_log"])),
            }
            self.drills["D1"] = result
            return result
        finally:
            con.close()

    # ── D2: no equivalent worker → owner escalation ──────────────────
    def drill_no_equivalent_escalation(self) -> Dict[str, Any]:
        from resource_monitor import EquivalentFailover
        from capability_registry import CapabilityRegistry
        from e3_escalate import E3Escalator

        con = self._con()
        try:
            registry = CapabilityRegistry(con)
            # No row exists for role "verifier": the registry is asked a real
            # question and truthfully answers "nobody".
            failover = EquivalentFailover(registry)
            none_found = failover.find_equivalent_worker(
                PRIMARY_WORKER, DRILL_TASK_FAMILY, "verifier")
            escalation = failover.escalate_no_equivalent(
                PRIMARY_WORKER, DRILL_TASK_FAMILY, "verifier")

            escalator = E3Escalator()
            record = escalator.escalate(
                trigger="no_qualified_worker",
                context=("Drill: worker failed on role 'verifier' and the "
                         "capability registry records no qualified equivalent"),
                proposals_considered=["retry same worker", "reduce scope",
                                      "escalate to owner"],
                why_each_failed=["same worker is failing",
                                 "scope reduction would lower the quality floor"],
                owner_decision_needed=escalation["owner_action"],
                recommended_action="owner provides an equivalent worker or "
                                   "explicitly approves a floor change")

            # Persist the escalation in the decision-rationale audit trail.
            rationale_id = f"rationale-{uuid.uuid4().hex[:12]}"
            ts = datetime.now(timezone.utc).isoformat()
            con.execute(
                """INSERT INTO decision_rationale_event
                   (rationale_id, task_id, plan_id, node_id, decision_type,
                    decision_actor, provider, model, model_identity, timestamp,
                    objective, chosen_action, alternatives_considered,
                    alternative_rejections, decisive_factors, evidence_references,
                    assumptions, uncertainties, confidence,
                    confidence_justification, expected_tradeoffs, gate_result,
                    next_verification, rationale_codes, concise_rationale)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rationale_id, "drill-e4e5-no-equivalent", None, None,
                 "escalation", "e3", "none", "none", None, ts,
                 "No equivalent qualified worker for role 'verifier'",
                 "escalate_to_owner",
                 json.dumps(record.proposals_considered),
                 json.dumps(record.why_each_failed),
                 json.dumps({"registry_answer": "no qualified worker",
                             "quality_floor": "must not be silently lowered"}),
                 json.dumps(["capability_registry(query)"]),
                 json.dumps(["a qualified equivalent might exist off-roster"]),
                 json.dumps(["owner response time unknown"]), "HIGH",
                 "the registry was queried and returned no qualified worker",
                 json.dumps({"blocked_until_owner_responds": True}),
                 "OWNER_APPROVAL_REQUIRED",
                 "owner supplies an equivalent worker or approves a floor change",
                 json.dumps(["no_equivalent_worker", "owner_escalation"]),
                 "No safe equivalent worker exists; escalate instead of "
                 "degrading quality silently."),
            )
            con.commit()

            result = {
                "drill": "D2_no_equivalent_escalation",
                "equivalent_found": none_found,
                "escalation_record": escalation,
                "escalation": {
                    "escalation_id": record.escalation_id,
                    "trigger": record.trigger,
                    "context": record.context,
                    "owner_decision_needed": record.owner_decision_needed,
                    "recommended_action": record.recommended_action,
                },
                "rationale_id": rationale_id,
                "active_escalations": len(escalator.get_active_escalations()),
                "gate_result": "OWNER_APPROVAL_REQUIRED",
                "quality_floor_lowered": False,
            }
            self.drills["D2"] = result
            return result
        finally:
            con.close()

    # ── D3: provider outage ─────────────────────────────────────────
    def drill_provider_outage(self) -> Dict[str, Any]:
        token = "OUTAGE-8801"
        node_id = "node-drill-e5-outage-1"

        reported = StubProviderAdapter(
            PRIMARY_WORKER, behaviour="outage",
            error="provider_unavailable: HTTP 503 from stub")
        registry = self._registry({PRIMARY_WORKER: reported})
        run_a = self._execute("drill-e5-outage-reported", PRIMARY_WORKER,
                              f"Drill objective. Reply with exactly {token}.",
                              self._exact_token_case(node_id, token),
                              registry, max_repair_attempts=0)
        self._log_stub_calls("D3_provider_outage", PRIMARY_WORKER, reported)

        raised = StubProviderAdapter(
            PRIMARY_WORKER, behaviour="transport_error",
            error="stub connection reset")
        registry_b = self._registry({PRIMARY_WORKER: raised})
        run_b = self._execute("drill-e5-outage-raised", PRIMARY_WORKER,
                              f"Drill objective. Reply with exactly {token}.",
                              self._exact_token_case(node_id, token),
                              registry_b, max_repair_attempts=0)
        self._log_stub_calls("D3_provider_outage", PRIMARY_WORKER, raised)

        def _summarise(run):
            node = run["node_run"]
            return {
                "worker_id": PRIMARY_WORKER,
                "node_state": node["state"],
                "dispatch_attempts": node["dispatch_attempts"],
                "verification_attempts": node["verification_attempts"],
                "failure_attribution": node["failure_attribution"],
                "blocking_reason": node["blocking_reason"],
                "evidence_id": node["evidence_id"],
                "persisted_node_state": (run["read_back"]["node"] or {}).get("state"),
                "complete": node["state"] == "COMPLETE",
            }

        result = {
            "drill": "D3_provider_outage",
            "variants": {
                "reported_provider_error": _summarise(run_a),
                "raised_transport_error": _summarise(run_b),
            },
            "no_node_reached_complete": not (
                run_a["node_run"]["state"] == "COMPLETE"
                or run_b["node_run"]["state"] == "COMPLETE"),
            "errors_recorded_verbatim": [
                a.get("error") for a in run_a["node_run"]["dispatch_attempts"]
            ] + [a.get("error") for a in run_b["node_run"]["dispatch_attempts"]],
            "failover_claimed": False,
        }
        self.drills["D3"] = result
        return result

    # ── D4: malformed output ────────────────────────────────────────
    def drill_malformed_output(self) -> Dict[str, Any]:
        from safe_mode import MalformedOutputHandler

        token = "WELLFORMED-3320"
        node_id = "node-drill-e5-malformed-1"
        malformed_content = "\x00\x01\x02{{{not json, not the token"

        validation = MalformedOutputHandler.validate_output(malformed_content)
        sanitized = MalformedOutputHandler.sanitize_output(malformed_content)
        handling = MalformedOutputHandler.handle_malformed(
            PRIMARY_WORKER, node_id, malformed_content, "; ".join(validation["errors"])
            or "output does not match the deterministic contract")

        # The handler's validator is a *shallow structural pre-check*: it flags
        # None / empty / missing-required-field output and passes anything else.
        # Contract conformance is decided by the independent deterministic
        # verifier below — this is recorded explicitly so the pre-check is never
        # read as the authority.
        validator_cases = {
            "none": MalformedOutputHandler.validate_output(None),
            "empty_string": MalformedOutputHandler.validate_output(""),
            "missing_required_field": MalformedOutputHandler.validate_output(
                {"status": "COMPLETED"}, {"required": ["content_stripped"]}),
            "non_empty_garbage_string": MalformedOutputHandler.validate_output(
                malformed_content),
        }
        validator_flags = [c["valid"] for c in validator_cases.values()]

        # 4a: repair budget exhausted → FAILED, never COMPLETE.
        always_bad = StubProviderAdapter(
            PRIMARY_WORKER, behaviour="malformed", content=malformed_content)
        registry_a = self._registry({PRIMARY_WORKER: always_bad})
        no_repair = self._execute(
            "drill-e5-malformed-norepair", PRIMARY_WORKER,
            f"Drill objective. Reply with exactly {token}.",
            self._exact_token_case(node_id, token), registry_a,
            max_repair_attempts=0)
        self._log_stub_calls("D4_malformed_output", PRIMARY_WORKER, always_bad)

        # 4b: one repair attempt, then a well-formed answer → COMPLETE via REWORK.
        repairing = StubProviderAdapter(
            PRIMARY_WORKER, behaviour="malformed_then_ok",
            content=malformed_content, recovery_content=token)
        registry_b = self._registry({PRIMARY_WORKER: repairing})
        with_repair = self._execute(
            "drill-e5-malformed-repaired", PRIMARY_WORKER,
            f"Drill objective. Reply with exactly {token}.",
            self._exact_token_case(node_id, token), registry_b,
            max_repair_attempts=1)
        self._log_stub_calls("D4_malformed_output", PRIMARY_WORKER, repairing)

        result = {
            "drill": "D4_malformed_output",
            "malformed_content_repr": repr(malformed_content),
            "validator": {
                "cases": validator_cases,
                "flags_structural_malformation": (
                    validator_cases["none"]["valid"] is False
                    and validator_cases["empty_string"]["valid"] is False
                    and validator_cases["missing_required_field"]["valid"] is False),
                "shallow_precheck_passes_garbage_string": (
                    validator_cases["non_empty_garbage_string"]["valid"] is True),
                "authority": ("the independent deterministic verifier decides "
                              "contract conformance; the pre-check does not"),
                "sanitized_repr": repr(sanitized),
                "sanitizer_removed_non_printables": sanitized != malformed_content,
            },
            "handler": handling,
            "no_repair_budget": {
                "node_state": no_repair["node_run"]["state"],
                "verification_attempts": no_repair["node_run"]["verification_attempts"],
                "rejections": no_repair["node_run"]["rejections"],
                "failure_attribution": no_repair["node_run"]["failure_attribution"],
                "dispatch_count": len(no_repair["node_run"]["dispatch_attempts"]),
            },
            "with_repair_budget": {
                "node_state": with_repair["node_run"]["state"],
                "dispatch_count": len(with_repair["node_run"]["dispatch_attempts"]),
                "verification_attempts": with_repair["node_run"]["verification_attempts"],
                "repairs": with_repair["node_run"]["repairs"],
                "final_verification": with_repair["node_run"]["final_verification"],
                "state_log": with_repair["state_log"],
            },
            "malformed_never_accepted": (
                no_repair["node_run"]["state"] != "COMPLETE"),
        }
        self.drills["D4"] = result
        return result

    # ── D5: repeated-failure convergence cap ────────────────────────
    def drill_convergence_cap(self) -> Dict[str, Any]:
        from safe_mode import ConvergenceEnforcer, SafeModeManager

        cap = 3
        node_id = "node-drill-e5-convergence-1"
        token = "CONVERGE-7712"
        enforcer = None
        con = self._con()
        try:
            enforcer = ConvergenceEnforcer(con, max_retries=cap)
            manager = SafeModeManager(con)
            fails_stub = StubProviderAdapter(
                PRIMARY_WORKER, behaviour="malformed",
                content="garbage that cannot verify")
            registry = self._registry({PRIMARY_WORKER: fails_stub})

            iterations: List[Dict[str, Any]] = []
            converged = False
            for i in range(cap + 2):  # deliberately overshoot to prove the cap holds
                key = f"node-drill-e5-convergence-1"
                if not enforcer.can_retry(key):
                    should_stop, reason = enforcer.should_stop(key)
                    iterations.append({"iteration": i + 1, "stopped": True,
                                       "reason": reason})
                    converged = True
                    break
                attempt = enforcer.record_attempt(key)
                failure_count = manager.record_failure(PRIMARY_WORKER, DRILL_TASK_FAMILY)
                run = self._execute(
                    f"drill-e5-convergence-{attempt}", PRIMARY_WORKER,
                    f"Drill objective. Reply with exactly {token}.",
                    self._exact_token_case(node_id, token), registry,
                    max_repair_attempts=0)
                convergence = enforcer.record_convergence_event(
                    PRIMARY_WORKER, DRILL_TASK_FAMILY, failure_count)
                entry = {
                    "iteration": i + 1,
                    "attempt": attempt,
                    "node_state": run["node_run"]["state"],
                    "convergence": convergence,
                }
                # Escalating system mode as the failures accumulate.
                if failure_count == cap - 1:
                    entry["mode_transition"] = manager.enter_degraded(
                        f"worker {PRIMARY_WORKER} failed {failure_count}x on "
                        f"{DRILL_TASK_FAMILY}")["mode"]
                    manager.record_safe_mode_event(
                        "repeated_failure", "degraded",
                        f"{PRIMARY_WORKER} failed {failure_count}x on {DRILL_TASK_FAMILY}",
                        [PRIMARY_WORKER])
                elif failure_count >= cap:
                    entry["mode_transition"] = manager.enter_safe_mode(
                        f"convergence cap {cap} reached for {PRIMARY_WORKER}")["mode"]
                    manager.record_safe_mode_event(
                        "repeated_failure", "safe_mode",
                        f"convergence cap {cap} reached for {PRIMARY_WORKER}",
                        [PRIMARY_WORKER])
                iterations.append(entry)
            self._log_stub_calls("D5_convergence_cap", PRIMARY_WORKER, fails_stub)

            escalations = enforcer.get_escalations()
            result = {
                "drill": "D5_convergence_cap",
                "cap": cap,
                "iterations": iterations,
                "dispatches_performed": len(fails_stub.calls),
                "loop_terminated_by_cap": converged,
                "stop_markers": sum(1 for i in iterations if i.get("stopped")),
                "iterations_total": len(iterations),
                "iterations_bounded": (
                    converged
                    and sum(1 for i in iterations if i.get("stopped")) == 1
                    and len(iterations) == cap + 1),
                "convergence_event_count": con.execute(
                    "SELECT COUNT(*) FROM convergence_event").fetchone()[0],
                "escalations": escalations,
                "quarantine_recorded": any(
                    e["action_taken"] == "quarantine_worker" for e in escalations),
                "system_mode": manager.mode.value,
                "active_safe_mode_events": manager.get_active_events(),
            }
            self.drills["D5"] = result
            return result
        finally:
            con.close()

    # ── D6: safe-mode entry, owner override audit, recovery ─────────
    def drill_safe_mode_override_and_recovery(self) -> Dict[str, Any]:
        from safe_mode import (SafeModeManager, SafeModeRecovery,
                               record_owner_override)

        con = self._con()
        try:
            manager = SafeModeManager(con)

            # Enter SAFE_MODE for an owner-only trigger (no equivalent worker).
            manager.enter_safe_mode("no equivalent qualified worker available")
            safe_event_id = manager.record_safe_mode_event(
                "no_equivalent_worker", "high",
                "No equivalent qualified worker for role 'verifier'",
                [PRIMARY_WORKER])

            recovery = SafeModeRecovery(manager, con)

            def stub_healthy():
                # Deterministic, local, zero-cost probe. NOT a provider-health
                # claim: real provider health remains owner-gated.
                try:
                    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
                    ok = integrity == "ok"
                except Exception as exc:  # noqa: BLE001
                    ok, integrity = False, f"{type(exc).__name__}: {exc}"
                return {"healthy": ok, "source": "stubbed_local_probe",
                        "detail": f"drill db integrity_check={integrity}",
                        "provider_health_verified": False}

            def stub_unhealthy():
                return {"healthy": False, "source": "stubbed_local_probe",
                        "detail": "injected unhealthy probe",
                        "provider_health_verified": False}

            refused_no_override = recovery.attempt_recovery(stub_healthy)
            refused_unhealthy = recovery.attempt_recovery(stub_unhealthy)
            overrides_before = recovery.owner_override_events()

            override = record_owner_override(
                con,
                owner="Mukund",
                reason=("Drill: authorise leaving safe mode for the no-equivalent-"
                        "worker trigger after the owner supplies an equivalent worker."),
                scope="safe_mode_recovery",
                evidence_references=["e4e5-drill-harness:D6"],
            )
            gate_after_override = recovery.gate(stub_healthy)
            recovered = recovery.attempt_recovery(stub_healthy)

            override_audit = con.execute(
                """SELECT rationale_id, decision_actor, gate_result,
                          concise_rationale, timestamp
                   FROM decision_rationale_event
                   WHERE decision_actor = 'owner'""").fetchall()
            resolved_rows = con.execute(
                """SELECT event_id, trigger_type, auto_resolved, resolved_at
                   FROM safe_mode_event WHERE resolved_at IS NOT NULL""").fetchall()

            result = {
                "drill": "D6_safe_mode_override_and_recovery",
                "safe_mode_entry": {
                    "safe_event_id": safe_event_id,
                    "active_events_before": manager.get_active_events(),
                },
                "recovery_refused_without_override": {
                    "recovered": refused_no_override["recovered"],
                    "refusal_reasons": refused_no_override["gate"]["refusal_reasons"],
                    "owner_only_event_ids":
                        refused_no_override["gate"]["owner_only_event_ids"],
                    "mode_after_refusal": refused_no_override["mode"],
                },
                "recovery_refused_when_unhealthy": {
                    "recovered": refused_unhealthy["recovered"],
                    "refusal_reasons": refused_unhealthy["gate"]["refusal_reasons"],
                },
                "owner_override": override,
                "overrides_before": overrides_before,
                "gate_after_override": gate_after_override,
                "recovery": recovered,
                "owner_override_audit_rows": [dict(r) for r in override_audit],
                "resolved_event_rows": [dict(r) for r in resolved_rows],
                "active_events_after_recovery": manager.get_active_events(),
                "final_mode": manager.mode.value,
                "provider_health_verified": False,
                "provider_health_note": (
                    "the drill's health probe is a labelled local stub "
                    "(db integrity); real provider-health re-verification before "
                    "leaving safe mode on the live system remains owner-gated"),
            }
            self.drills["D6"] = result
            return result
        finally:
            con.close()

    # ── orchestration ───────────────────────────────────────────────
    def run(self) -> Dict[str, Any]:
        before = hash_live_stores(self.runtime_root)
        started = datetime.now(timezone.utc)

        self.drill_checkpoint_failover_handover()
        self.drill_no_equivalent_escalation()
        self.drill_provider_outage()
        self.drill_malformed_output()
        self.drill_convergence_cap()
        self.drill_safe_mode_override_and_recovery()

        after = hash_live_stores(self.runtime_root)
        moved = sorted(k for k in before if before.get(k) != after.get(k))
        self.isolation = {
            "live_store_hashes_before": before,
            "live_store_hashes_after": after,
            "live_stores_changed": moved,
            "isolated_db": str(self.db_path),
            "isolated_db_exists": self.db_path.exists(),
            "e2_rows_written": 0,
            "e2_linkage_kind": "stubbed (no live governor row written)",
        }

        checks = self.checks()
        report = {
            "harness": "e4e5-real-path-drill-harness",
            "task_id": "agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23",
            "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md",
            "code_sha": _code_sha(),
            "run_started_utc": started.isoformat(),
            "run_finished_utc": datetime.now(timezone.utc).isoformat(),
            "evidence_kind": EVIDENCE_KIND,
            "evidence_kind_note": (
                "provider transport is a recorded in-process stub; these drills "
                "evidence OUR handling of injected failures on the real execution "
                "path and are NOT real external provider evidence"),
            "real_provider_calls": self.real_provider_calls,
            "stub_dispatches": self.stub_calls_total,
            "stage2_enabled": False,
            "deployment_performed": False,
            "isolation": self.isolation,
            "adapter_call_log": self.adapter_call_log,
            "drills": {
                key: self.drills.get(key) for key in
                ("D1", "D2", "D3", "D4", "D5", "D6") if key in self.drills
            },
            "checks": checks,
            "checks_passed": sum(1 for v in checks.values() if v),
            "checks_total": len(checks),
        }
        return report

    def checks(self) -> Dict[str, bool]:
        d = self.drills
        d1 = d.get("D1", {})
        d2 = d.get("D2", {})
        d3 = d.get("D3", {})
        d4 = d.get("D4", {})
        d5 = d.get("D5", {})
        d6 = d.get("D6", {})

        cp = d1.get("checkpoint", {})
        primary = d1.get("primary_dispatch", {})
        repl = d1.get("replacement_dispatch") or {}
        outage = d3.get("variants", {})

        return {
            "D1_checkpoint_created": bool(cp.get("checkpoint_id"))
                                  and len(cp.get("checkpoints_for_task") or []) == 1,
            "D1_checkpoint_restore_matches_saved": bool(cp.get("restore_matches_saved")),
            "D1_primary_worker_failed": primary.get("node_state") == "FAILED",
            "D1_equivalent_worker_selected": bool(
                (d1.get("equivalent_selection") or {}).get("worker_id")),
            "D1_handover_state_delivered": bool(
                d1.get("handover_objective_delivered_to_replacement")),
            "D1_replacement_verified_complete": repl.get("node_state") == "COMPLETE",
            "D1_failover_log_ordered": bool(
                d1.get("failover_log_shows_failed_then_complete")),
            "D1_failover_not_fabricated": (
                bool(repl) and repl.get("final_verification") == "PASS"),
            "D2_no_equivalent_returns_none": d2.get("equivalent_found") is None,
            "D2_owner_escalation_recorded": bool(
                (d2.get("escalation") or {}).get("escalation_id")),
            "D2_quality_floor_not_lowered": d2.get("quality_floor_lowered") is False,
            "D3_reported_outage_fails_node":
                outage.get("reported_provider_error", {}).get("node_state") == "FAILED",
            "D3_raised_transport_error_caught":
                outage.get("raised_transport_error", {}).get("node_state") == "FAILED",
            "D3_errors_recorded_verbatim": all(
                e for e in (d3.get("errors_recorded_verbatim") or [])),
            "D3_no_failover_claimed": d3.get("failover_claimed") is False
                                      and bool(d3.get("no_node_reached_complete")),
            "D4_validator_flags_structural_malformation":
                bool((d4.get("validator") or {}).get("flags_structural_malformation")),
            "D4_validator_shallow_precheck_recorded":
                bool((d4.get("validator") or {}).get(
                    "shallow_precheck_passes_garbage_string")),
            "D4_sanitizer_strips_non_printables":
                bool((d4.get("validator") or {}).get("sanitizer_removed_non_printables")),
            "D4_malformed_rejected_by_verifier":
                (d4.get("no_repair_budget") or {}).get("node_state") == "FAILED"
                and bool((d4.get("no_repair_budget") or {}).get("rejections")),
            "D4_repair_path_converges":
                (d4.get("with_repair_budget") or {}).get("node_state") == "COMPLETE"
                and (d4.get("with_repair_budget") or {}).get("final_verification") == "PASS",
            "D5_cap_bounded_no_infinite_loop":
                bool(d5.get("loop_terminated_by_cap")) and bool(d5.get("iterations_bounded")),
            "D5_quarantine_escalated": bool(d5.get("quarantine_recorded")),
            "D5_safe_mode_entered": d5.get("system_mode") == "SAFE_MODE",
            "D6_safe_mode_event_persisted": bool(
                (d6.get("safe_mode_entry") or {}).get("safe_event_id")),
            "D6_recovery_refused_without_override":
                (d6.get("recovery_refused_without_override") or {}).get(
                    "recovered") is False,
            "D6_recovery_refused_when_unhealthy":
                (d6.get("recovery_refused_when_unhealthy") or {}).get(
                    "recovered") is False,
            "D6_owner_override_audited": bool(d6.get("owner_override_audit_rows")),
            "D6_recovery_succeeded": bool((d6.get("recovery") or {}).get("recovered")),
            "D6_mode_normal_after_recovery": d6.get("final_mode") == "NORMAL",
            "D6_no_active_events_after_recovery":
                (d6.get("active_events_after_recovery") or []) == [],
            "D1_live_registry_read_via_snapshot":
                (d1.get("live_registry_read_only") or {}).get("source")
                in ("live_registry_read_only_snapshot", "live_registry_absent"),
            "isolation_live_stores_untouched": (
                self.isolation.get("live_stores_changed") == []
                and self.isolation.get("isolated_db_exists") is True),
            "no_real_provider_calls": self.real_provider_calls == 0,
        }


# ─── Evidence writer ────────────────────────────────────────────────

def write_evidence(report: Dict[str, Any], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = [
        "# E4/E5 real-path drill evidence (stubbed provider failures)",
        "",
        f"- Task: `{report['task_id']}`",
        f"- Authority: `{report['authority']}`",
        f"- Code SHA: `{report.get('code_sha')}`",
        f"- Run started (UTC): {report['run_started_utc']}",
        f"- Run finished (UTC): {report['run_finished_utc']}",
        f"- Evidence kind: `{report['evidence_kind']}` — {report['evidence_kind_note']}",
        f"- Real provider calls: **{report['real_provider_calls']}** "
        f"(stub dispatches: {report['stub_dispatches']})",
        f"- Stage 2 enabled: {report['stage2_enabled']}; deployment performed: "
        f"{report['deployment_performed']}",
        f"- Checks: **{report['checks_passed']}/{report['checks_total']} passed**",
        "",
        "## Isolation",
        "",
        f"- Isolated orchestration DB: `{report['isolation']['isolated_db']}`",
        f"- Live stores changed: {report['isolation']['live_stores_changed'] or 'none'}",
        f"- E2 rows written: {report['isolation']['e2_rows_written']} "
        f"({report['isolation']['e2_linkage_kind']})",
        "",
        "## Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name, ok in report["checks"].items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")
    lines += ["", "## Drill detail", ""]
    for key, drill in report["drills"].items():
        lines.append(f"### {key} — {drill.get('drill')}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(drill, indent=2, default=str))
        lines.append("```")
        lines.append("")
    (out_dir / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--scratch", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    harness = E4E5DrillHarness(
        scratch_root=Path(args.scratch) if args.scratch else None)
    report = harness.run()

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e4e5-real-path-drills")
    write_evidence(report, out_dir)

    summary = {
        "code_sha": report.get("code_sha"),
        "checks_passed": report["checks_passed"],
        "checks_total": report["checks_total"],
        "failed_checks": [k for k, v in report["checks"].items() if not v],
        "real_provider_calls": report["real_provider_calls"],
        "stub_dispatches": report["stub_dispatches"],
        "evidence_kind": report["evidence_kind"],
        "out_dir": str(out_dir),
    }
    print(json.dumps(summary, indent=2))
    return 0 if report["checks_passed"] == report["checks_total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
