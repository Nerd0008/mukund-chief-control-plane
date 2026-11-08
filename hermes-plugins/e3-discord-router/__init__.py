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


def _reply_target(source) -> Tuple[str, Dict[str, str]]:
    """Return the Hermes Discord destination without guessing thread routing.

    Hermes supplies ``chat_id`` for ordinary channels and existing threads.  A
    channel message that Hermes will auto-thread carries
    ``prospective_thread_id`` instead, while an existing Discord thread carries
    ``thread_id``.  Discord's adapter documents ``metadata['thread_id']`` as
    the authoritative target, so preserve either value when present.
    """
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = (getattr(source, "thread_id", None)
                 or getattr(source, "prospective_thread_id", None))
    metadata = {"thread_id": str(thread_id)} if thread_id else {}
    return chat_id, metadata


async def _send_reply(adapter, source, event, content: str) -> bool:
    """Best-effort delivery which never re-opens native Hermes dispatch."""
    chat_id, metadata = _reply_target(source)
    if not chat_id:
        log.error("E3 bridge: Discord source has no chat_id")
        return False
    try:
        sent = await adapter.send(
            chat_id,
            content,
            reply_to=getattr(event, "message_id", None),
            metadata=metadata or None,
        )
    except Exception as exc:
        # Provider/runtime exception strings can contain sensitive diagnostic
        # values.  Keep only their type in bridge logs.
        log.error("E3 bridge Discord send raised (%s)", type(exc).__name__)
        return False
    if getattr(sent, "success", True) is False:
        log.error("E3 bridge Discord send failed: %s", getattr(sent, "error", "unknown"))
        return False
    return True


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
    except Exception as exc:
        log.error("E3 bridge could not verify Discord authorization (%s)", type(exc).__name__)
        return None

    try:
        adapter = (getattr(gateway, "adapters", {}) or {}).get(platform)
    except Exception as exc:
        log.error("E3 bridge could not resolve Discord adapter (%s)", type(exc).__name__)
        adapter = None
    if adapter is None:
        log.error("E3 bridge: no Discord adapter for source platform")
        # This is an E3-owned authorized turn.  Suppress native MoA/OpenRouter
        # even when delivery infrastructure is unavailable, rather than
        # accidentally duplicating or changing the selected execution path.
        return {"action": "skip", "reason": "e3-adapter-unavailable"}

    # Preserve conversation continuity because returning "skip" prevents the
    # normal Hermes agent path from writing this turn.
    entry = None
    history = []
    try:
        entry = session_store.get_or_create_session(source)
        history = session_store.load_transcript(entry.session_id) or []
    except Exception as exc:
        log.error("E3 bridge could not load session transcript (%s)", type(exc).__name__)

    context = _recent_context(history)

    try:
        result = await asyncio.to_thread(_run_e3_sync, text, context)
    except Exception as exc:
        log.error("E3 bridge execution failed (%s)", type(exc).__name__)
        # Exception strings may contain provider or runtime details.  Keep
        # those in local logs and return a stable, non-sensitive user notice.
        await _send_reply(
            adapter, source, event,
            "⚠️ E3 routing is temporarily unavailable. Please try again shortly.",
        )
        return {"action": "skip", "reason": "e3-routing-error"}

    if not result.get("ok"):
        workers = ", ".join(
            str(worker) for worker in (result.get("allowed_workers") or []) if worker
        ) or "none"
        message = f"⚠️ E3 could not complete this request. Stage 2 workers: {workers}."
        await _send_reply(adapter, source, event, message)
        return {"action": "skip", "reason": "e3-execution-incomplete"}

    content = result.get("content")
    if not isinstance(content, str) or not content.strip():
        log.error("E3 bridge rejected empty verified content")
        await _send_reply(
            adapter, source, event,
            "⚠️ E3 could not complete this request. No verified response was available.",
        )
        return {"action": "skip", "reason": "e3-empty-verified-content"}

    worker_text = ", ".join(
        str(worker) for worker in (result.get("workers") or []) if worker
    ) or "unknown"
    # Keep the worker visible during acceptance. Once the bridge is proven, this
    # footer can be made optional without changing routing behavior.
    reply = f"{content}\n\n_E3 worker: {worker_text}_"

    if not await _send_reply(adapter, source, event, reply):
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
        except Exception as exc:
            log.error("E3 bridge could not append transcript (%s)", type(exc).__name__)

    log.info(
        "E3 Discord dispatch complete family=%s role=%s workers=%s",
        result.get("family"), result.get("role"), worker_text,
    )
    return {"action": "skip", "reason": "handled-by-e3"}


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", _handle_gateway_message)
