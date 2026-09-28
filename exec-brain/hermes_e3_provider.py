"""Hermes model-provider boundary backed by E3.

Hermes owns authentication, session state, transcript, tools, skills and
approval. E3 owns worker selection. This module preserves the chat/tool
transport contract between them instead of flattening Hermes turns into an E3
workflow objective.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any


def _text(messages: list[dict[str, Any]]) -> str:
    for row in reversed(messages or []):
        if row.get("role") == "user":
            content = row.get("content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def _tool_name(tool_call: Any) -> str:
    fn = getattr(tool_call, "function", None)
    if fn is not None:
        name = getattr(fn, "name", "")
        return name.strip() if isinstance(name, str) else ""
    if isinstance(tool_call, dict):
        raw_fn = tool_call.get("function") or {}
        name = raw_fn.get("name") if isinstance(raw_fn, dict) else ""
        return name.strip() if isinstance(name, str) else ""
    return ""


def _offered_tool_names(tools: Any) -> set[str]:
    names: set[str] = set()
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") or {}
        name = fn.get("name") if isinstance(fn, dict) else None
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


_LONGCAT_TOOL_BLOCK = re.compile(
    r"<longcat_tool_call>\s*(\{.*?\})\s*</longcat_tool_call>",
    re.DOTALL | re.IGNORECASE,
)


def _normalize_longcat_tool_markup(text: str) -> str:
    """Translate LongCat's documented XML tool shape to Hermes' standard bridge.

    LongCat emits:
      <longcat_tool_call>{"name": "...", "arguments": {...}}</longcat_tool_call>

    Hermes' existing ACP bridge expects an OpenAI-shaped object inside
    <tool_call> tags. Only syntactically valid LongCat blocks are rewritten;
    malformed blocks remain ordinary non-executable text.
    """
    if not isinstance(text, str) or "<longcat_tool_call" not in text.lower():
        return text

    ordinal = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal ordinal
        raw = match.group(1)
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            return match.group(0)
        if not isinstance(obj, dict):
            return match.group(0)
        name = obj.get("name")
        arguments = obj.get("arguments", {})
        if not isinstance(name, str) or not name.strip():
            return match.group(0)
        if isinstance(arguments, str):
            try:
                json.loads(arguments)
                arguments_json = arguments
            except (TypeError, ValueError):
                return match.group(0)
        else:
            try:
                arguments_json = json.dumps(arguments, ensure_ascii=False)
            except (TypeError, ValueError):
                return match.group(0)

        ordinal += 1
        payload = {
            "id": f"longcat_call_{ordinal}",
            "type": "function",
            "function": {
                "name": name.strip(),
                "arguments": arguments_json,
            },
        }
        return (
            "<tool_call>\n" +
            json.dumps(payload, ensure_ascii=False) +
            "\n</tool_call>"
        )

    return _LONGCAT_TOOL_BLOCK.sub(_replace, text)


def _serialize_existing_tool_calls(calls: Any) -> str:
    blocks: list[str] = []
    for call in calls or []:
        if isinstance(call, dict):
            call_id = call.get("id") or ""
            fn = call.get("function") or {}
            name = fn.get("name") if isinstance(fn, dict) else ""
            args = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
        else:
            call_id = getattr(call, "id", "") or ""
            fn = getattr(call, "function", None)
            name = getattr(fn, "name", "") if fn is not None else ""
            args = getattr(fn, "arguments", "{}") if fn is not None else "{}"
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        payload = {
            "id": call_id,
            "type": "function",
            "function": {"name": name.strip(), "arguments": args},
        }
        blocks.append(
            "<tool_call>\n" + json.dumps(payload, ensure_ascii=False) +
            "\n</tool_call>")
    return "\n".join(blocks)


def _bridge_messages(messages: list[dict[str, Any]], tools: Any,
                     tool_choice: Any, chief_context: Any) -> list[dict[str, Any]]:
    """Translate Hermes' native tool rows to Hermes' existing text-tool bridge."""
    try:
        from agent.acp_openai_bridge import render_tool_bridge_sections
    except ModuleNotFoundError:
        # Source-tree tests do not install the Hermes agent package.  The
        # bundled compatibility module has the same narrow bridge contract;
        # the live Hermes runtime continues to use its native implementation.
        from acp_openai_bridge import render_tool_bridge_sections

    bridged: list[dict[str, Any]] = []
    sections = render_tool_bridge_sections(tools or [], tool_choice)
    if sections:
        bridged.append({"role": "system", "content": "\n\n".join(sections)})
    if chief_context:
        bridged.append({
            "role": "system",
            "content": "Chief retrieved context (bounded, provenance-aware):\n" +
                       json.dumps(chief_context, ensure_ascii=False, default=str),
        })

    for row in messages or []:
        if not isinstance(row, dict):
            continue
        role = row.get("role") or "user"
        raw_content = row.get("content")
        if isinstance(raw_content, str):
            text = raw_content
        elif raw_content is None:
            text = ""
        else:
            text = json.dumps(raw_content, ensure_ascii=False, default=str)

        if role == "assistant" and row.get("tool_calls"):
            blocks = _serialize_existing_tool_calls(row.get("tool_calls"))
            combined = "\n".join(part for part in (text, blocks) if part)
            bridged.append({"role": "assistant", "content": combined})
            continue

        if role == "tool":
            payload = {
                "tool_call_id": row.get("tool_call_id") or "",
                "name": row.get("name") or "",
                "content": text,
            }
            bridged.append({
                "role": "user",
                "content": "<tool_response>\n" +
                           json.dumps(payload, ensure_ascii=False, default=str) +
                           "\n</tool_response>",
            })
            continue

        bridged.append({"role": role, "content": text})
    return bridged


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

    def _chat_result(self, *, text: str, messages: list[dict[str, Any]],
                     tools: Any, tool_choice: Any, intent: Any) -> dict[str, Any]:
        from chief_context import ChiefContextCompiler

        compiler = ChiefContextCompiler()
        chief_context = compiler.compile(text)
        warnings = compiler.validate(chief_context)
        if warnings:
            return {"status": "FAILED", "provider_call_made": False,
                    "error": "chief_context_invalid",
                    "context_warnings": warnings, "content": ""}

        wire_messages = _bridge_messages(
            messages, tools, tool_choice, chief_context)
        return self.service.execute_chat(
            messages=wire_messages,
            objective=text,
            task_family=intent.family,
            required_role=intent.role,
            reasoning_depth=intent.reasoning_depth,
            dry_run=False,
        )

    def create(self, *, model: str, messages: list[dict[str, Any]], tools=None,
               tool_choice=None, **kwargs: Any) -> Any:
        from chief_routing import ChiefRouteSelector

        text = _text(messages)
        intent = ChiefRouteSelector.intent_for(text)
        tool_iteration = self._has_tool_iteration(messages)

        # Deterministic departments keep ownership of the first human turn.
        if not tool_iteration and intent.department != "chief":
            from discord_chief_bridge import dispatch_chief_message
            context = {
                "hermes_tools_present": bool(tools),
                "hermes_tool_choice": tool_choice,
                "hermes_context": messages,
                "hermes_full_messages": messages,
                "hermes_tools": tools or [],
            }
            result = dispatch_chief_message(
                text, context=context, service=self.service,
                department_dispatcher=self.department_dispatcher, dry_run=False)
        # Any tool-capable Chief turn, plus every post-tool iteration, uses the
        # chat transport so Hermes' conversation/tool protocol is preserved.
        elif tools or tool_iteration:
            result = self._chat_result(
                text=text, messages=messages, tools=tools,
                tool_choice=tool_choice, intent=intent)
        else:
            from discord_chief_bridge import dispatch_chief_message
            result = dispatch_chief_message(
                text, context={"hermes_full_messages": messages},
                service=self.service,
                department_dispatcher=self.department_dispatcher, dry_run=False)

        content = result.get("content", "") or ""
        tool_calls = list(result.get("tool_calls") or [])

        # LongCat may serialize Hermes' text-tool bridge in assistant content.
        # Reuse Hermes' own parser and only accept tools that were actually
        # offered on this request.
        if tools and not tool_calls and content:
            try:
                from agent.acp_openai_bridge import extract_tool_calls_from_text
            except ModuleNotFoundError:
                from acp_openai_bridge import extract_tool_calls_from_text
            normalized = _normalize_longcat_tool_markup(content)
            extracted, cleaned = extract_tool_calls_from_text(normalized)
            if extracted:
                allowed = _offered_tool_names(tools)
                if all(_tool_name(call) in allowed for call in extracted):
                    tool_calls = extracted
                    content = cleaned

        message = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls

        finish_reason = (
            "tool_calls" if tool_calls
            else (result.get("finish_reason") or "stop")
        )
        choice = SimpleNamespace(
            index=0, message=SimpleNamespace(**message),
            finish_reason=finish_reason)
        usage = self._usage(result)
        return SimpleNamespace(
            id="e3-local", model=result.get("model") or model,
            choices=[choice], usage=usage,
            provider=result.get("provider"),
            worker_id=result.get("worker_id"))


class E3ModelClient:
    def __init__(self, service: Any, department_dispatcher: Any = None,
                 api_key: str = "e3", base_url: str = "e3://local"):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = SimpleNamespace(completions=E3ChatCompletions(
            service, department_dispatcher=department_dispatcher))
