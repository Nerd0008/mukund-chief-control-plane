"""Chief intake policy that delegates every AI task to the shared E3 service."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Optional

_IMAGE = re.compile(r"\b(image|picture|photo|draw|illustrat|generate\s+an?\s+image|edit\s+an?\s+image)\b", re.I)
_ENGINEERING = re.compile(r"\b(code|coding|debug|bug|repository|repo|github|git|pull request|test|implement|patch)\b", re.I)
_CAREER = re.compile(r"\b(jobs?|career|application|cv|resume|cover letter|interview|recruiter)\b", re.I)


@dataclass(frozen=True)
class ChiefIntent:
    family: str
    role: str
    reasoning_depth: int
    department: str


class ChiefRouteSelector:
    """Chief's deterministic intake layer; it never sees adapters or providers."""

    def __init__(self, e3_service: Any, *, department_dispatcher: Any = None,
                 context_compiler: Any = None):
        self.e3_service = e3_service
        self.department_dispatcher = department_dispatcher
        if context_compiler is None:
            from chief_context import ChiefContextCompiler
            context_compiler = ChiefContextCompiler()
        self.context_compiler = context_compiler

    @staticmethod
    def intent_for(message: str) -> ChiefIntent:
        if _IMAGE.search(message or ""):
            return ChiefIntent("other", "vision", 1, "chief")
        if _ENGINEERING.search(message or ""):
            return ChiefIntent("code", "builder", 2, "chief")
        if _CAREER.search(message or ""):
            # Career Ops owns deterministic discovery, filtering, tracker and
            # approval workflows. This only describes an AI subtask if one is
            # later needed by that department.
            return ChiefIntent("analysis", "data-analyst", 2, "career-ops")
        return ChiefIntent("other", "builder", 1, "chief")

    def dispatch(self, message: str, *, context: Optional[Dict[str, Any]] = None,
                 dry_run: bool = False) -> Dict[str, Any]:
        intent = self.intent_for(message)
        context = dict(context or {})
        context.setdefault("chief_context", self.context_compiler.compile(message))
        context_warnings = self.context_compiler.validate(context["chief_context"])
        if context_warnings:
            return {"status": "CONTEXT_REJECTED", "provider_call_made": False,
                    "error": "chief_context_invalid", "context_warnings": context_warnings,
                    "chief_department": intent.department, "chief_intent": intent.family}
        # A department owns its deterministic workflow.  Chief must not turn a
        # Career Ops request into a generic E3 completion just because it has
        # classified the message.  The department may call E3 later for a
        # bounded semantic subtask through the same service boundary.
        if intent.department != "chief":
            if self.department_dispatcher is not None:
                result = self.department_dispatcher.dispatch(
                    intent.department, message, context=context, dry_run=dry_run)
            else:
                result = {
                    "status": "DEPARTMENT_OWNER_GATE_REQUIRED",
                    "provider_call_made": False,
                    "error": "department_handler_not_configured",
                }
            result["chief_department"] = intent.department
            result["chief_intent"] = intent.family
            return result
        result = self.e3_service.execute(
            objective=message, task_family=intent.family,
            required_role=intent.role, reasoning_depth=intent.reasoning_depth,
            context=context, dry_run=dry_run)
        result["chief_department"] = intent.department
        result["chief_intent"] = intent.family
        return result
