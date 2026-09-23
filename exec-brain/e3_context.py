#!/usr/bin/env python3
"""E3 Context Compiler — build minimum sufficient context for each worker.

Prefer deterministic context packaging. Do NOT dump complete chat history,
whole repositories, or irrelevant outputs.
"""

from typing import Any, Dict, List, Optional, Set


class ContextCompiler:
    """Build context packages for workers."""

    MAX_FILES_DEFAULT = 20
    MAX_LINES_PER_FILE_DEFAULT = 200

    def __init__(self, max_files: int = MAX_FILES_DEFAULT,
                 max_lines_per_file: int = MAX_LINES_PER_FILE_DEFAULT):
        self.max_files = max_files
        self.max_lines_per_file = max_lines_per_file

    def compile(self, objective: str, contract: Any,
                upstream_outputs: Optional[Dict[str, Any]] = None,
                file_references: Optional[List[str]] = None,
                relevant_decisions: Optional[List[Dict]] = None,
                constraints: Optional[List[str]] = None) -> Dict[str, Any]:
        """Build minimum sufficient context package."""
        context: Dict[str, Any] = {
            "objective": objective,
            "output_schema": getattr(contract, 'required_output_schema', {}),
            "definition_of_done": getattr(contract, 'definition_of_done', ''),
            "constraints": constraints if constraints is not None else [],
        }

        if upstream_outputs is not None:
            context["upstream_outputs"] = self._filter_relevant_outputs(
                upstream_outputs, objective
            )

        if file_references is not None:
            context["file_references"] = file_references[:self.max_files]

        if relevant_decisions is not None:
            context["decisions"] = [
                d for d in relevant_decisions
                if d.get("node_id") != "current"
            ]

        return context

    def _filter_relevant_outputs(self, outputs: Dict[str, Any],
                                 objective: str) -> Dict[str, Any]:
        """Filter upstream outputs to those relevant to objective."""
        if len(outputs) <= 3:
            return outputs

        obj_lower = objective.lower()
        relevant: Dict[str, Any] = {}
        for key, value in outputs.items():
            key_lower = key.lower()
            if key_lower in obj_lower or any(word in key_lower for word in obj_lower.split()[:5]):
                relevant[key] = value

        return relevant if relevant else dict(list(outputs.items())[:3])

    def validate_context(self, context: Dict[str, Any]) -> List[str]:
        """Validate context package for size and safety."""
        warnings: List[str] = []
        total_size = len(str(context))

        if total_size > 100000:
            warnings.append(f"Context size {total_size} bytes exceeds 100KB limit")

        file_refs = context.get("file_references", [])
        if len(file_refs) > self.max_files:
            warnings.append(f"Too many file references: {len(file_refs)} > {self.max_files}")

        context_str = str(context)
        suspicious_patterns = ["password", "secret", "api_key", "token", "credential"]
        for pattern in suspicious_patterns:
            if pattern in context_str.lower():
                warnings.append(f"Context may contain sensitive pattern: {pattern}")

        return warnings
