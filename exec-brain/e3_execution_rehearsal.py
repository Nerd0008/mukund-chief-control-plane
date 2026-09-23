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
    def run(self, include_codex: bool = True, include_google: bool = False) -> Dict[str, Any]:
        started = datetime.now(timezone.utc)
        deployment = self.runtime_deployment_facts()
        before = self.orchestration_db_facts()

        self.scenario_repair_cycle()
        self.scenario_first_pass()
        if include_codex:
            self.scenario_codex_cli()
        if include_google:
            self.scenario_google_image()
        self.scenario_non_routable_refusal()

        after = self.orchestration_db_facts()

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
            "bounded_usage": {
                "real_provider_calls": len(real_calls),
                "calls_by_provider": by_provider,
                "usage_exposed_calls": sum(1 for c in real_calls if c["usage_exposed"]),
                "usage_missing_calls": sum(1 for c in real_calls if not c["usage_exposed"]),
                "note": ("Minimum deterministic calls needed to evidence the path. "
                         "Usage is recorded only when the provider returned it."),
            },
            "checks": self.checks(),
            "unresolved": [
                {
                    "scenario": s["scenario"],
                    "worker": s["assigned_worker"],
                    "node_state": s["node_state"],
                    "blocking_reason": s["blocking_reason"],
                    "failure_attribution": s["failure_attribution"],
                    "provider_errors": [a.get("error") for a in s["dispatch_attempts"]
                                        if a.get("error")],
                    "expected_block": s["scenario"] == "E_non_routable_refusal",
                }
                for s in self.scenarios if s["node_state"] != "COMPLETE"
            ],
        }

    def checks(self) -> Dict[str, Any]:
        by_name = {s["scenario"]: s for s in self.scenarios}
        repair = by_name.get("A_repair_cycle_deepseek", {})
        first = by_name.get("B_first_pass_deepseek", {})
        codex = by_name.get("C_codex_cli_dispatch")
        google = by_name.get("D_google_image_dispatch")
        refusal = by_name.get("E_non_routable_refusal", {})

        def _real(scenario: Optional[Dict[str, Any]]) -> bool:
            if not scenario:
                return True  # not requested in this run
            return scenario["node_state"] == "COMPLETE"

        return {
            "repair_cycle_rejected_then_repaired": (
                len(repair.get("rejections", [])) >= 1
                and len(repair.get("repairs", [])) >= 1
                and repair.get("node_state") == "COMPLETE"
                and [v["passed"] for v in repair.get("verification_attempts", [])][-1:] == [True]
            ),
            "first_pass_complete": first.get("node_state") == "COMPLETE",
            "codex_cli_complete": _real(codex),
            "google_image_complete": _real(google),
            "non_routable_refused_without_dispatch": refusal.get("refusal_honoured") is True,
            "complete_requires_verification": all(
                s["node_state"] != "COMPLETE"
                or (s["final_verification"] == "PASS")
                for s in self.scenarios
            ),
            "dag_state_and_evidence_persisted": all(
                s["persisted_node_state"] == s["node_state"]
                and len(s["persisted_state_events"]) > 0
                for s in self.scenarios
            ),
            "e2_linkage_recorded": any(
                rid and not str(rid).startswith("e2_linkage_error:")
                for s in self.scenarios for rid in s["e2_request_ids"]
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
    parser.add_argument("--db-path", default=None,
                        help="override the orchestration db (testing only)")
    args = parser.parse_args(argv)

    rehearsal = E3ExecutionRehearsal(
        db_path=Path(args.db_path) if args.db_path else None)
    report = rehearsal.run(include_codex=not args.no_codex,
                           include_google=args.include_google)

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
        f"{report['bounded_usage']['calls_by_provider']}",
        "",
        "| Scenario | Worker | Node state | Dispatches | Verifications | Rejections | Repairs | Outcome |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in report["scenarios"]:
        lines.append(
            f"| {s['scenario']} | {s['assigned_worker']} | {s['node_state']} | "
            f"{len(s['dispatch_attempts'])} | {len(s['verification_attempts'])} | "
            f"{len(s['rejections'])} | {len(s['repairs'])} | {s['run_outcome']} |"
        )
    lines += ["", "## Checks", ""]
    for k, v in report["checks"].items():
        lines.append(f"- {k}: {v}")
    if report["runtime_deployment"]["missing_modules"]:
        lines += ["", "Missing runtime modules: "
                  + ", ".join(report["runtime_deployment"]["missing_modules"])]
    (out_dir / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(report["checks"], indent=2))
    print(json.dumps(report["bounded_usage"], indent=2))
    print(f"evidence written to {out_dir}")
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
