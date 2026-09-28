"""Deterministic Chief department handoff adapters.

Departments keep ownership of business workflows. This module deliberately has
no provider or E3 imports: a department decides whether a later semantic subtask
is needed and calls the E3 application service from its own bounded operation.
"""
from __future__ import annotations

import json
import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, Optional


_REGIONS = ("uk", "dubai", "japan", "singapore")
_REGION_ALIASES = {"united kingdom": "uk", "england": "uk", "uae": "dubai"}
_COUNT = re.compile(r"\b(\d{1,3})\b")


class CareerOpsDepartment:
    """Adapter for the existing deterministic Career Ops workflows.

    The adapter owns no provider choice.  Offline dispatch returns a truthful
    bounded plan and reads local run-health/tracker state; live discovery is an
    explicit activation-only operation delegated to the unified orchestrator.
    """

    def __init__(self, *, repo_root: Optional[Path] = None, allow_external: bool = False):
        self.repo_root = Path(repo_root or Path(__file__).resolve().parents[1])
        self.career_root = self.repo_root / "career-ops"
        self.allow_external = allow_external

    def _imports(self):
        root = str(self.career_root)
        if root not in sys.path:
            sys.path.insert(0, root)
        import career_ops_cli  # type: ignore
        import dept_run_health  # type: ignore
        import regional_job_search  # type: ignore
        return career_ops_cli, dept_run_health, regional_job_search

    @staticmethod
    def _request(message: str) -> tuple[list[str], int, str]:
        lower = (message or "").casefold()
        regions = []
        for raw, region in _REGION_ALIASES.items():
            if raw in lower:
                regions.append(region)
        for region in _REGIONS:
            if region in lower and region not in regions:
                regions.append(region)
        if not regions or any(word in lower for word in ("all", "every", "each")):
            regions = list(_REGIONS)
        match = _COUNT.search(lower)
        count = max(1, min(int(match.group(1)), 100)) if match else 10
        if "status" in lower or "health" in lower:
            operation = "run-health"
        elif "summary" in lower or "tracker" in lower or "manifest" in lower:
            operation = "summary"
        else:
            operation = "read-only-discovery"
        return regions, count, operation

    def dispatch(self, message: str, *, context: Optional[Dict[str, Any]] = None,
                 dry_run: bool = False) -> Dict[str, Any]:
        regions, count, operation = self._request(message)
        career_ops_cli, health, rjs = self._imports()
        if operation == "run-health":
            state = health.summarise(None, None)
            return {"status": "DEPARTMENT_COMPLETED", "department": "career-ops",
                    "workflow": "career_ops_cli.run-health", "operation": operation,
                    "regions": regions, "requested_count": count, "provider_call_made": False,
                    "read_only": True, "result": state,
                    "content": json.dumps(state, sort_keys=True)}
        if operation == "summary":
            # The CLI's summary implementation is the source of truth.  Keep
            # the call read-only and avoid subprocess/provider activity.
            class Args: pass
            args = Args(); args.region = None if len(regions) == len(_REGIONS) else regions[0]
            args.profiles = None
            out = io.StringIO()
            with redirect_stdout(out):
                career_ops_cli.cmd_summary(args)
            result = json.loads(out.getvalue())
            return {"status": "DEPARTMENT_COMPLETED", "department": "career-ops",
                    "workflow": "career_ops_cli.summary", "operation": operation,
                    "regions": regions, "requested_count": count, "provider_call_made": False,
                    "read_only": True, "result": result,
                    "content": "Career Ops tracker summary completed."}
        plan = {
            "workflow": "discovery.scheduled_orchestrator",
            "worker": "career-ops/discovery/scheduled_orchestrator.py",
            "regions": regions,
            "requested_count": count,
            "read_only": True,
            "dedupe_policy": "existing discovery pipeline and tracker ledger",
            "mutation": "none; tracker writes and applications require separate owner-gated commands",
            "semantic_subtasks": "E3ApplicationService only",
            "provider_call_made": False,
            "mode": "offline-plan" if (dry_run or not self.allow_external) else "live-activation-required",
        }
        return {"status": "DEPARTMENT_COMPLETED", "department": "career-ops",
                "workflow": plan["workflow"], "operation": operation,
                "regions": regions, "requested_count": count, "provider_call_made": False,
                "read_only": True, "result": plan,
                "content": (f"Career Ops read-only discovery planned for {', '.join(regions)} "
                             f"with up to {count} results per region.")}


class DefaultDepartmentDispatcher:
    """Safe default for Chief departments not yet bound to a live workflow."""

    def __init__(self, *, career_ops: Optional[CareerOpsDepartment] = None):
        self.career_ops = career_ops or CareerOpsDepartment()

    def dispatch(self, department: str, message: str, *, context: Optional[Dict[str, Any]] = None,
                 dry_run: bool = False) -> Dict[str, Any]:
        if department == "career-ops":
            return self.career_ops.dispatch(message, context=context, dry_run=dry_run)
        return {
            "status": "DEPARTMENT_OWNER_GATE_REQUIRED",
            "provider_call_made": False,
            "content": f"{department} needs a configured workflow handler.",
            "department": department,
        }
