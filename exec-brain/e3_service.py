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


    def execute_chat(self, *, messages: list[dict[str, Any]], objective: str,
                     task_family: str = "other", required_role: str = "builder",
                     risk_class: str = "R1", reasoning_depth: int = 1,
                     timeout: int = 120, dry_run: bool = False) -> Dict[str, Any]:
        """Route one Hermes chat-completions turn through E3 without flattening it.

        This is deliberately separate from execute(). The ordinary execute()
        method is the task/workflow boundary used by Chief departments;
        execute_chat() is the provider-transport boundary used by Hermes'
        native agent/tool loop.
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
        db = self.db_path or (Path(__file__).resolve().parent / "orchestration.db")
        factory = self.orchestrator_factory or E3ShadowOrchestrator
        orch = factory(db_path=db)
        plan = orch.planner.plan(objective, fp)
        nodes = list(plan.get("nodes") or [])
        if not nodes or orch.router is None:
            return {"status": "FAILED", "provider_call_made": False,
                    "error": "e3_chat_route_unavailable",
                    "stage2_allowed_workers": state.get("allowed_workers", [])}

        node = nodes[0]
        proposed = orch.router.propose_candidates(node, fp.task_family, fp)
        candidates = [
            candidate for candidate in proposed
            if registry.is_routable(candidate.worker_id)
        ]
        candidates = orch._apply_owner_route_preference(
            candidates, node, fp.task_family)
        if not candidates:
            return {"status": "FAILED", "provider_call_made": False,
                    "error": "e3_chat_no_eligible_worker",
                    "stage2_allowed_workers": state.get("allowed_workers", [])}

        chosen = candidates[0]
        if dry_run:
            return {"status": "DRY_RUN", "provider_call_made": False,
                    "worker_id": chosen.worker_id, "provider": chosen.provider,
                    "model": chosen.model,
                    "stage2_allowed_workers": state.get("allowed_workers", [])}

        adapter = registry.adapter_for(chosen.worker_id)
        contract = {
            "contract_id": f"chat-{plan.get('plan_id') or 'unknown'}",
            "objective": objective,
            "messages": list(messages or []),
            "timeout": timeout,
            "max_tokens": 1024,
            "temperature": 0.0,
        }
        result = adapter.dispatch(contract)
        e2_linkage = registry.report_usage(chosen.worker_id, result)
        tool_calls = result.get("tool_calls") or []
        content = result.get("content")
        completed = (
            result.get("status") == "COMPLETED"
            and (content is not None or bool(tool_calls))
        )
        if not completed:
            return {"status": "FAILED", "provider_call_made": True,
                    "error": result.get("error") or "e3_chat_execution_incomplete",
                    "worker_id": chosen.worker_id,
                    "provider": result.get("provider") or chosen.provider,
                    "model": result.get("model") or chosen.model,
                    "finish_reason": result.get("finish_reason"),
                    "usage": result.get("usage"),
                    "e2_usage_linkage": e2_linkage,
                    "stage2_allowed_workers": state.get("allowed_workers", [])}

        return {"status": "COMPLETED", "provider_call_made": True,
                "content": content or "", "tool_calls": tool_calls,
                "finish_reason": result.get("finish_reason"),
                "usage": result.get("usage"),
                "worker_id": chosen.worker_id,
                "provider": result.get("provider") or chosen.provider,
                "model": result.get("model") or chosen.model,
                "e2_usage_linkage": e2_linkage,
                "stage2_allowed_workers": state.get("allowed_workers", [])}
