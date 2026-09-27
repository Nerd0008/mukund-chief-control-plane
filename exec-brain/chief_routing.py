#!/usr/bin/env python3
"""Deterministic E3 routing for normal Chief messages.

This is deliberately a small, auditable policy layer.  It has no credentials,
does not mutate provider state, and dispatches only through E3 execution
adapters.  A failure from an eligible provider is recorded and the next
eligible worker is tried; inactive providers never enter a route.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Optional


PRIMARY = "longcat-2.0"
SECONDARY = "deepseek-v41-flash"
CODEX = "codex-cli"
GOOGLE = "google-nano-banana-2"

DISABLED_WORKERS = frozenset({
    "mistral-small-4", "qwen38-27b", "glm-53-flash", "minimax-m3",
    "step-37-flash", "tencent-hunyuan-hy3",
})

_IMAGE = re.compile(r"\b(image|picture|photo|draw|illustrat|generate\s+an?\s+image|edit\s+an?\s+image)\b", re.I)
_ENGINEERING = re.compile(r"\b(code|coding|debug|bug|repository|repo|github|git|pull request|test|implement|patch)\b", re.I)
_PROVIDER_FAILURE = re.compile(
    r"\b(401|402|403|429|quota|rate[ -]?limit|insufficient balance|credit|authentication|unauthori[sz]ed|forbidden)\b",
    re.I,
)


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    candidates: List[str]
    skipped: Dict[str, str]


class ChiefRouteSelector:
    """Select and dispatch one bounded E3 Chief response."""

    def __init__(self, worker_registry: Any, adapter_registry: Any,
                 allowed_workers: Optional[Iterable[str]] = None):
        self.worker_registry = worker_registry
        self.adapter_registry = adapter_registry
        self.allowed_workers = set(allowed_workers) if allowed_workers is not None else None

    @staticmethod
    def intent_for(message: str) -> str:
        if _IMAGE.search(message or ""):
            return "image"
        if _ENGINEERING.search(message or ""):
            return "engineering"
        return "general"

    @staticmethod
    def policy_chain(intent: str) -> List[str]:
        if intent == "image":
            return [GOOGLE]
        if intent == "engineering":
            return [CODEX, PRIMARY, SECONDARY]
        return [PRIMARY, SECONDARY, CODEX]

    def select(self, message: str) -> RouteDecision:
        intent = self.intent_for(message)
        candidates, skipped = [], {}
        for worker_id in self.policy_chain(intent):
            if worker_id in DISABLED_WORKERS:
                skipped[worker_id] = "disabled_by_owner_policy"
                continue
            if self.allowed_workers is not None and worker_id not in self.allowed_workers:
                skipped[worker_id] = "not_allowed_by_stage2"
                continue
            worker = self.worker_registry.get_worker(worker_id) or {}
            if not worker.get("routable"):
                skipped[worker_id] = "not_currently_routable"
                continue
            if not self.adapter_registry.is_routable(worker_id):
                skipped[worker_id] = "adapter_unavailable"
                continue
            candidates.append(worker_id)
        return RouteDecision(intent=intent, candidates=candidates, skipped=skipped)

    @staticmethod
    def _failed(result: Dict[str, Any]) -> bool:
        if result.get("status") != "COMPLETED" or not result.get("content"):
            return True
        return False

    def dispatch(self, message: str, *, timeout: int = 120,
                 max_tokens: int = 512) -> Dict[str, Any]:
        decision = self.select(message)
        attempts = []
        for worker_id in decision.candidates:
            contract = {
                "contract_id": "chief-message",
                "objective": message,
                "timeout": timeout,
                "max_tokens": max_tokens,
                "temperature": 0.0,
            }
            try:
                result = self.adapter_registry.adapter_for(worker_id).dispatch(contract)
            except Exception as exc:  # adapter crash is a provider attempt failure
                attempts.append({"worker_id": worker_id, "error": type(exc).__name__})
                continue
            if not self._failed(result):
                self.adapter_registry.report_usage(worker_id, result)
                return {
                    "status": "COMPLETED", "worker_id": worker_id,
                    "provider": result.get("provider"), "model": result.get("model"),
                    "content": result.get("content"), "intent": decision.intent,
                    "attempts": attempts, "skipped": decision.skipped,
                }
            error = str(result.get("error") or result.get("exit_code") or "provider_failed")
            attempts.append({"worker_id": worker_id, "error": error,
                             "provider_failure": bool(_PROVIDER_FAILURE.search(error))})
            self.adapter_registry.report_usage(worker_id, result)
        return {"status": "FAILED", "intent": decision.intent,
                "attempts": attempts, "skipped": decision.skipped,
                "error": "no_eligible_provider_completed"}
