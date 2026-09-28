"""Hermes model-provider boundary backed by E3.

Hermes still owns the authenticated session, transcript, tools, skills and
approval loop.  This client only implements the provider transport contract;
E3 chooses the Stage-2 worker/model for each completion.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _text(messages: list[dict[str, Any]]) -> str:
    for row in reversed(messages or []):
        if row.get("role") == "user":
            content = row.get("content", "")
            return content if isinstance(content, str) else str(content)
    return ""


class E3ChatCompletions:
    def __init__(self, service: Any, department_dispatcher: Any = None):
        self.service = service
        self.department_dispatcher = department_dispatcher

    @staticmethod
    def _has_tool_iteration(messages: list[dict[str, Any]]) -> bool:
        return any(row.get("role") == "tool" or row.get("tool_calls")
                   for row in (messages or []) if isinstance(row, dict))

    @staticmethod
    def _usage(result: dict[str, Any]) -> Any:
        usage = result.get("usage")
        if isinstance(usage, dict):
            return SimpleNamespace(**usage)
        return SimpleNamespace(prompt_tokens=0, completion_tokens=0,
                               total_tokens=0)

    def create(self, *, model: str, messages: list[dict[str, Any]], tools=None,
               tool_choice=None, **kwargs: Any) -> Any:
        context = {"hermes_tools_present": bool(tools),
                   "hermes_tool_choice": tool_choice,
                   "hermes_context": messages,
                   "hermes_full_messages": messages,
                   "hermes_tools": tools or []}
        if self._has_tool_iteration(messages):
            result = self.service.execute(
                objective=_text(messages), task_family="other", required_role="builder",
                context=context, dry_run=False)
        else:
            from discord_chief_bridge import dispatch_chief_message
            result = dispatch_chief_message(
                _text(messages), context=context, service=self.service,
                department_dispatcher=self.department_dispatcher, dry_run=False)
        message = {"role": "assistant", "content": result.get("content", "")}
        if result.get("tool_calls"):
            message["tool_calls"] = result["tool_calls"]
        choice = SimpleNamespace(index=0, message=SimpleNamespace(**message),
                                 finish_reason="tool_calls" if result.get("tool_calls") else "stop")
        usage = self._usage(result)
        return SimpleNamespace(id="e3-local", model=result.get("model") or model,
                               choices=[choice], usage=usage,
                               provider=result.get("provider"), worker_id=result.get("worker_id"))


class E3ModelClient:
    def __init__(self, service: Any, department_dispatcher: Any = None):
        self.chat = SimpleNamespace(completions=E3ChatCompletions(
            service, department_dispatcher=department_dispatcher))
