"""Offline Chief router used by the Hermes E3 model-provider seam.

The live gateway is not intercepted: Hermes invokes its normal agent loop and
the installed ``e3`` ProviderProfile calls this boundary for each completion.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, Optional


def dispatch_chief_message(message: str, *, context: Optional[Dict[str, Any]] = None,
                           dry_run: bool = False, service: Any = None,
                           department_dispatcher: Any = None) -> Dict[str, Any]:
    """Run after Hermes authentication/session intake; never use native MoA routing."""
    if service is None:
        from e3_service import E3ApplicationService
        service = E3ApplicationService()
    if department_dispatcher is None:
        from department_dispatch import CareerOpsDepartment, DefaultDepartmentDispatcher
        # The gateway bridge is called directly for authenticated Discord turns,
        # so it must bind Career Ops to the active checkout rather than relying
        # on the runtime directory's parent or an incomplete sibling checkout.
        runtime = Path(__file__).resolve().parent
        configured = os.environ.get("MUKUND_CHIEF_REPO_ROOT", "").strip()
        candidates = ([Path(configured).expanduser()] if configured else []) + [
            Path.home() / "Documents" / "mukund-chief-control-plane",
            Path.home() / "Documents" / "Codex" / "mukund-chief-control-plane-owner-decisions",
            runtime.parent,
        ]
        repo_root = next((candidate for candidate in candidates
                          if (candidate / "career-ops" / "career_ops_cli.py").is_file()
                          and (candidate / "career-ops" / "discovery" / "scheduled_orchestrator.py").is_file()), runtime.parent)
        department_dispatcher = DefaultDepartmentDispatcher(
            career_ops=CareerOpsDepartment(repo_root=repo_root, allow_external=True))
    from chief_routing import ChiefRouteSelector
    return ChiefRouteSelector(service, department_dispatcher=department_dispatcher).dispatch(
        message, context=context, dry_run=dry_run)
