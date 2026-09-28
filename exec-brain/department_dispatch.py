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

    def __init__(self, *, repo_root: Optional[Path] = None, allow_external: bool = False,
                 orchestrator: Any = None):
        self.repo_root = Path(repo_root or Path(__file__).resolve().parents[1])
        self.career_root = self.repo_root / "career-ops"
        self.allow_external = allow_external
        self.orchestrator = orchestrator

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
        if self.allow_external and not dry_run:
            try:
                if self.orchestrator is not None:
                    result = self.orchestrator.run_all(regions=regions, requested_count=count,
                                                      dry_run=False)
                else:
                    result = self._run_unified_orchestrator(regions, count)
                if not isinstance(result, dict):
                    raise TypeError("unified orchestrator returned a non-object result")
                candidates = result.get("canonical_candidates") or result.get("records") or []
                bounded = candidates[: count * len(regions)]
                result["canonical_candidates"] = bounded
                result["requested_count"] = count
                result["regions_requested"] = regions
                return {"status": "DEPARTMENT_COMPLETED", "department": "career-ops",
                        "workflow": plan["workflow"], "operation": operation,
                        "regions": regions, "requested_count": count,
                        "provider_call_made": bool(result.get("provider_call_made", False)),
                        "read_only": bool(result.get("read_only", True)),
                        "executed": True, "result": result,
                        "content": json.dumps({"workflow": plan["workflow"],
                                               "regions": regions,
                                               "results": len(bounded)}, sort_keys=True)}
            except Exception as exc:  # truthful per-dispatch failure, no generic E3 prose
                return {"status": "DEPARTMENT_FAILED", "department": "career-ops",
                        "workflow": plan["workflow"], "regions": regions,
                        "requested_count": count, "provider_call_made": False,
                        "read_only": True, "executed": True,
                        "error": f"{type(exc).__name__}: {exc}",
                        "content": "Career Ops discovery failed; see structured error."}
        return {"status": "DEPARTMENT_COMPLETED", "department": "career-ops",
                "workflow": plan["workflow"], "operation": operation,
                "regions": regions, "requested_count": count, "provider_call_made": False,
                "read_only": True, "result": plan,
                "content": (f"Career Ops read-only discovery planned for {', '.join(regions)} "
                             f"with up to {count} results per region.")}

    def _run_unified_orchestrator(self, regions: list[str], count: int) -> dict:
        """Execute the existing run-all command with its safety gates intact."""
        import argparse
        import io
        from contextlib import redirect_stdout
        if str(self.career_root / "discovery") not in sys.path:
            sys.path.insert(0, str(self.career_root / "discovery"))
        import scheduled_orchestrator as orchestrator  # type: ignore
        args = argparse.Namespace(
            regions=regions, region="all", scheduled=False, no_live=False,
            provider="auto", executable=None, reuse_web_export=None, watchlist=None,
            web_queries=orchestrator.DEFAULT_WEB_QUERIES,
            limit_per_query=min(orchestrator.DEFAULT_LIMIT_PER_QUERY, count),
            max_urls=orchestrator.DEFAULT_MAX_URLS,
            per_query_timeout=orchestrator.DEFAULT_PER_QUERY_TIMEOUT,
            scan_timeout=orchestrator.DEFAULT_SCAN_TIMEOUT, skip_regional_scan=False,
            scan_records_dir=None, no_validate=False,
            budget_seconds=orchestrator.DEFAULT_BUDGET_SECONDS, retries=orchestrator.DEFAULT_RETRIES,
            ingest_stale_hours=orchestrator.DEFAULT_INGEST_STALE_HOURS,
            semantic="deterministic", model="", batch_size=8, max_tokens=None,
            codex="off", codex_budget=0, out_dir=None, web_out_dir=None,
            state_file=None, state_file_out=None, no_lock=True,
            mode=orchestrator.DEFAULT_MODE, compare=False, require_live_web=False,
        )
        out = io.StringIO()
        with redirect_stdout(out):
            rc = orchestrator.cmd_run_all(args)
        lines = [line for line in out.getvalue().splitlines() if line.strip()]
        result = json.loads(lines[-1]) if lines else {}
        result["orchestrator_exit_code"] = rc
        return result


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
