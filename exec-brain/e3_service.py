"""Application-facing E3 dispatch boundary.

Business modules declare what work needs AI assistance; they never select a
provider, model, or adapter.  This module is the only supported bridge from a
Chief department or scheduled workflow into the E3 execution leg.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


class E3ApplicationService:
    """Execute one verified E3 application request, fail-closed at Stage 2."""

    def __init__(self, *, db_path: Optional[Path] = None,
                 orchestrator_factory: Any = None):
        self.db_path = db_path
        self.orchestrator_factory = orchestrator_factory

    def execute(self, *, objective: str, task_family: str,
                required_role: str, risk_class: str = "R1",
                reasoning_depth: int = 1, context: Optional[Dict[str, Any]] = None,
                timeout: int = 120, dry_run: bool = False) -> Dict[str, Any]:
        """Run a caller-declared task through E3, or inspect it without a call.

        ``dry_run`` performs the same Stage-2/routability preparation but never
        dispatches a provider.  Returned errors are stable categories rather
        than adapter exception text, so callers cannot leak credentials.
        """
        from stage2_control import require_enabled
        from task_fingerprint import TaskFingerprint
        from e3_execution import ExecutionAdapterRegistry
        from e3_shadow_orchestrator import E3ShadowOrchestrator

        state = require_enabled()
        registry = ExecutionAdapterRegistry(
            allowed_workers=state.get("allowed_workers", []))
        fp = TaskFingerprint(task_family=task_family,
                             reasoning_depth=reasoning_depth,
                             risk_class=risk_class,
                             required_roles=[required_role],
                             verification_type="deterministic")
        objective_with_context = objective
        if context:
            # Context is supplied as explicit caller data, never as a model or
            # provider selection channel.
            objective_with_context = f"{objective}\n\nCaller context: {context!r}"
        db = self.db_path or (Path(__file__).resolve().parent / "orchestration.db")
        factory = self.orchestrator_factory or E3ShadowOrchestrator
        orch = factory(db_path=db)
        plan = orch.planner.plan(objective_with_context, fp)
        assignments = []
        if dry_run:
            return {"status": "DRY_RUN", "provider_call_made": False,
                    "routable_workers": registry.routable_worker_ids(),
                    "plan_id": plan.get("plan_id"), "task_family": task_family,
                    "required_role": required_role}
        cases = {node["node_id"]: [{"name": "non-empty verified AI output",
                                     "field": "content_present", "expected": True}]
                 for node in plan.get("nodes", [])}
        out = orch.orchestrate_and_execute(
            objective_with_context, fp, plan=plan,
            verification_test_cases_by_node=cases, max_repair_attempts=0,
            dispatch_timeout=timeout, adapter_registry=registry,
            return_verified_content=True)
        assignments = out.get("team_assignments") or []
        verified = (out.get("execution") or {}).get("verified_outputs") or []
        first = verified[0] if verified else {}
        if out.get("outcome") != "EXECUTION_COMPLETE" or not first.get("content"):
            return {"status": "FAILED", "provider_call_made": bool(assignments),
                    "error": "e3_execution_incomplete", "assignments": assignments,
                    "stage2_allowed_workers": state.get("allowed_workers", [])}
        return {"status": "COMPLETED", "provider_call_made": True,
                "content": first["content"], "worker_id": first.get("worker_id"),
                "provider": first.get("provider"), "model": first.get("model"),
                "assignments": assignments,
                "stage2_allowed_workers": state.get("allowed_workers", [])}
