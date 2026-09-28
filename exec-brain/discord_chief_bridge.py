"""Source-controlled bridge from an authenticated Chief turn to its owner layer."""
from __future__ import annotations
from typing import Any, Dict, Optional


def dispatch_chief_message(message: str, *, context: Optional[Dict[str, Any]] = None,
                           dry_run: bool = False, service: Any = None,
                           department_dispatcher: Any = None) -> Dict[str, Any]:
    """Run after Hermes authentication/session intake; never use native MoA routing."""
    if service is None:
        from e3_service import E3ApplicationService
        service = E3ApplicationService()
    if department_dispatcher is None:
        from department_dispatch import DefaultDepartmentDispatcher
        department_dispatcher = DefaultDepartmentDispatcher()
    from chief_routing import ChiefRouteSelector
    return ChiefRouteSelector(service, department_dispatcher=department_dispatcher).dispatch(
        message, context=context, dry_run=dry_run)
