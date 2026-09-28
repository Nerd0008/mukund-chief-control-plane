"""Deterministic Chief department handoff adapters.

Departments keep ownership of business workflows. This module deliberately has
no provider or E3 imports: a department decides whether a later semantic subtask
is needed and calls the E3 application service from its own bounded operation.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class DefaultDepartmentDispatcher:
    """Safe default for Chief departments not yet bound to a live workflow."""

    def dispatch(self, department: str, message: str, *, context: Optional[Dict[str, Any]] = None,
                 dry_run: bool = False) -> Dict[str, Any]:
        if department == "career-ops":
            return {
                "status": "DEPARTMENT_HANDOFF_REQUIRED",
                "provider_call_made": False,
                "content": (
                    "Career Ops owns job discovery and application workflows. "
                    "Please include the target region and whether you want a status, "
                    "a read-only search, or an approved application workflow."
                ),
                "department": department,
            }
        return {
            "status": "DEPARTMENT_HANDOFF_REQUIRED",
            "provider_call_made": False,
            "content": f"{department} needs a configured workflow handler.",
            "department": department,
        }
