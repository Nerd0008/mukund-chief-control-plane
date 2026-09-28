"""Small source-tree fallback for Hermes' text tool bridge.

The installed Hermes agent supplies the full implementation at runtime.  This
module keeps E3's provider tests hermetic when that optional package is absent.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

_BLOCK = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def render_tool_bridge_sections(tools: list[dict[str, Any]] | None,
                                tool_choice: Any = None) -> list[str]:
    specs = []
    for item in tools or []:
        fn = item.get("function") if isinstance(item, dict) else None
        if not isinstance(fn, dict) or not str(fn.get("name") or "").strip():
            continue
        specs.append({"name": fn["name"].strip(),
                      "description": fn.get("description", ""),
                      "parameters": fn.get("parameters", {})})
    sections = []
    if specs:
        sections.append(
            "Available tools (OpenAI function schema). When using a tool, emit "
            "ONLY <tool_call>{...}</tool_call> with one JSON object containing "
            "id/type/function{name,arguments}. arguments must be a JSON string.\n"
            + json.dumps(specs, ensure_ascii=False))
    if tool_choice is not None:
        sections.append(f"Tool choice hint: {json.dumps(tool_choice, ensure_ascii=False)}")
    return sections


def extract_tool_calls_from_text(text: str):
    if not isinstance(text, str) or not text.strip():
        return [], ""
    calls, spans = [], []
    for match in _BLOCK.finditer(text):
        try:
            obj = json.loads(match.group(1))
            fn = obj.get("function") or {}
            name = str(fn.get("name") or "").strip()
            if not name:
                continue
            args = fn.get("arguments", "{}")
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            call_id = str(obj.get("id") or f"acp_call_{len(calls) + 1}")
            calls.append(SimpleNamespace(
                id=call_id, call_id=call_id, type="function",
                function=SimpleNamespace(name=name, arguments=args)))
            spans.append((match.start(), match.end()))
        except (TypeError, ValueError):
            continue
    if not spans:
        return [], text.strip()
    cleaned = text
    for start, end in reversed(spans):
        cleaned = cleaned[:start] + cleaned[end:]
    return calls, cleaned.strip()
