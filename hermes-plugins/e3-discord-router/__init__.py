"""Hermes gateway bridge: Discord -> E3 Stage 2 -> verified reply.

This plugin intercepts *authorized* Discord text messages before Hermes' native
model/MoA dispatch, routes them through the local E3 execution brain, sends the
verified provider response back to the same Discord chat, then returns
{"action": "skip"} so native Hermes does not also process the message.

Slash commands and non-Discord traffic are intentionally left to Hermes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

log = logging.getLogger("e3-discord-router")


def _runtime_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"


def _ensure_runtime_imports() -> Path:
    root = _runtime_root()
    if not root.is_dir():
        raise RuntimeError(f"E3 runtime root missing: {root}")
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root


def _classify_text(text: str) -> Tuple[str, str, int]:
    """Small deterministic intake classifier; never spends an LLM call."""
    t = (text or "").lower()

    rules = [
        (("code", "python", "powershell", "script", "bug", "debug", "repo", "github", "api", "function", "class "),
         ("code", "builder", 2)),
        (("review", "audit", "critique", "check this code", "security review"),
         ("review", "critic", 2)),
        (("research", "find out", "look up", "investigate", "compare sources"),
         ("research", "researcher", 2)),
        (("analyse", "analyze", "compare", "why is", "explain the difference"),
         ("analysis", "data-analyst", 2)),
        (("summarise", "summarize", "summary", "tl;dr"),
         ("summarization", "writer", 1)),
        (("write ", "draft ", "rewrite", "email", "cover letter", "post "),
         ("writing", "writer", 1)),
        (("verify", "validate", "prove", "confirm whether"),
         ("verification", "verifier", 2)),
        (("excel", "csv", "spreadsheet", "dataset", "data processing"),
         ("data-processing", "data-analyst", 2)),
        (("deploy", "service", "gateway", "restart", "scheduled task", "powershell"),
         ("ops", "builder", 2)),
    ]
    for needles, result in rules:
        if any(n in t for n in needles):
            return result
    return ("other", "builder", 1)


def _recent_context(messages: Iterable[Dict[str, Any]], max_messages: int = 12,
                    max_chars: int = 12000) -> str:
    rows: List[str] = []
    for msg in list(messages or [])[-max_messages:]:
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        rows.append(f"{role.upper()}: {content}")
    joined = "\n".join(rows)
    return joined[-max_chars:]


def _run_e3_sync(text: str, recent_context: str) -> Dict[str, Any]:
    root = _ensure_runtime_imports()

    from stage2_control import require_enabled
    from task_fingerprint import TaskFingerprint
    from e3_shadow_orchestrator import E3ShadowOrchestrator

    stage2 = require_enabled()
    family, role, reasoning = _classify_text(text)

    objective = text
    if recent_context:
        objective = (
            "Use the recent conversation context only when relevant. "
            "Answer the latest user message directly.\n\n"
            f"Recent conversation:\n{recent_context}\n\n"
            f"Latest user message:\n{text}"
        )

    fp = TaskFingerprint(
        task_family=family,
        reasoning_depth=reasoning,
        risk_class="R1",
        required_roles=[role],
        verification_type="deterministic",
    )

    db = root / "orchestration.db"
    orch = E3ShadowOrchestrator(db_path=db)
    plan = orch.planner.plan(objective, fp)
    node_ids = [n["node_id"] for n in plan["nodes"]]
    test_cases = {
        nid: [{
            "name": "provider returned non-empty content",
            "field": "content_present",
            "expected": True,
        }]
        for nid in node_ids
    }

    out = orch.orchestrate_and_execute(
        objective,
        fp,
        plan=plan,
        verification_test_cases_by_node=test_cases,
        max_repair_attempts=0,
        dispatch_timeout=90,
        return_verified_content=True,
    )

    execution = out.get("execution") or {}
    verified = execution.get("verified_outputs") or []
    contents = [
        str(item.get("content")).strip()
        for item in verified
        if isinstance(item.get("content"), str) and item.get("content").strip()
    ]
    assignments = out.get("team_assignments") or []
    rankings = out.get("candidate_rankings") or {}

    if out.get("outcome") != "EXECUTION_COMPLETE" or not contents:
        return {
            "ok": False,
            "error": out.get("outcome") or execution.get("outcome") or "E3 execution incomplete",
            "assignments": assignments,
            "candidate_rankings": rankings,
            "allowed_workers": stage2.get("allowed_workers") or [],
        }

    workers = [a.get("worker") for a in assignments if a.get("worker")]
    return {
        "ok": True,
        "content": "\n\n".join(contents),
        "workers": workers,
        "assignments": assignments,
        "candidate_rankings": rankings,
        "allowed_workers": stage2.get("allowed_workers") or [],
        "family": family,
        "role": role,
    }


async def _handle_gateway_message(event, gateway, session_store, **kwargs):
    del kwargs

    source = getattr(event, "source", None)
    if source is None:
        return None

    platform = getattr(source, "platform", None)
    platform_name = getattr(platform, "value", str(platform or "")).lower()
    if platform_name != "discord":
        return None

    text = str(getattr(event, "text", "") or "").strip()
    if not text or text.startswith("/"):
        return None

    # pre_gateway_dispatch fires before Hermes' built-in auth gate. Never
    # intercept unless the existing gateway authorization check says this source
    # is already authorized. On uncertainty, fall through to native Hermes.
    try:
        if not gateway._is_user_authorized_for_source(source):
            return None
    except Exception:
        log.exception("E3 bridge could not verify Discord authorization")
        return None

    adapter = gateway.adapters.get(platform)
    if adapter is None:
        log.error("E3 bridge: no Discord adapter for source platform")
        return None

    # Preserve conversation continuity because returning "skip" prevents the
    # normal Hermes agent path from writing this turn.
    entry = None
    history = []
    try:
        entry = session_store.get_or_create_session(source)
        history = session_store.load_transcript(entry.session_id) or []
    except Exception:
        log.exception("E3 bridge could not load session transcript")

    context = _recent_context(history)

    try:
        result = await asyncio.to_thread(_run_e3_sync, text, context)
    except Exception as exc:
        log.exception("E3 bridge execution failed")
        message = f"⚠️ E3 routing failed before native Hermes dispatch: {type(exc).__name__}: {exc}"
        await adapter.send(source.chat_id, message, reply_to=getattr(event, "message_id", None))
        return {"action": "skip", "reason": "e3-routing-error"}

    if not result.get("ok"):
        workers = ", ".join(result.get("allowed_workers") or []) or "none"
        message = (
            "⚠️ E3 could not complete this request. "
            f"Outcome: {result.get('error')}. Stage 2 workers: {workers}."
        )
        await adapter.send(source.chat_id, message, reply_to=getattr(event, "message_id", None))
        return {"action": "skip", "reason": "e3-execution-incomplete"}

    content = result["content"]
    worker_text = ", ".join(result.get("workers") or []) or "unknown"
    # Keep the worker visible during acceptance. Once the bridge is proven, this
    # footer can be made optional without changing routing behavior.
    reply = f"{content}\n\n_E3 worker: {worker_text}_"

    send_result = await adapter.send(
        source.chat_id,
        reply,
        reply_to=getattr(event, "message_id", None),
    )
    if getattr(send_result, "success", True) is False:
        log.error("E3 bridge Discord send failed: %s", getattr(send_result, "error", "unknown"))
        return {"action": "skip", "reason": "e3-discord-send-failed"}

    if entry is not None:
        try:
            session_store.append_to_transcript(
                entry.session_id,
                {"role": "user", "content": text, "message_id": getattr(event, "message_id", None)},
            )
            session_store.append_to_transcript(
                entry.session_id,
                {"role": "assistant", "content": content},
            )
        except Exception:
            log.exception("E3 bridge could not append transcript")

    log.info(
        "E3 Discord dispatch complete family=%s role=%s workers=%s",
        result.get("family"), result.get("role"), worker_text,
    )
    return {"action": "skip", "reason": "handled-by-e3"}


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", _handle_gateway_message)
