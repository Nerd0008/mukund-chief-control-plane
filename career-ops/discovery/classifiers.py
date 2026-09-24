#!/usr/bin/env python3
"""Semantic classifiers for the discovery funnel.

Three providers, one contract
-----------------------------
``deterministic``  declared rule output (title/company/location signals). Used
                   when no model provider is reachable, and always labelled as
                   NOT semantic JD analysis. Never claims to be a model pass.
``deepseek``       the bulk semantic classifier for the whole candidate pool
                   (batched chat completions through the existing
                   ``exec-brain/deepseek_adapter.py``).
``codex``          a bounded second pass over ambiguous / high-value candidates
                   only (existing ``exec-brain/codex_adapter.py``). Codex is
                   never called for every scanned posting: escalation is decided
                   by the deterministic conditions in :func:`escalation_reason`
                   and capped by ``codex_budget``.

Nothing here writes a tracker, submits anything or contacts anyone. Provider
credentials are read by reference in the existing adapters (never printed).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent.parent
EXEC_BRAIN = CONTROL_PLANE / "exec-brain"

from semantic_contract import (  # noqa: E402
    ACCEPT_LABELS,
    FACT_CLASS_TOKENS,
    LABELS,
    build_classification,
    candidate_id,
    jd_available,
    present_fields,
)
from title_policy import MODE_HIGH_RECALL, title_decision  # noqa: E402

PROMPT_VERSION = "discovery-semantic-v1"

#: default ceiling on Codex escalations per run (the owner's bounded budget).
DEFAULT_CODEX_BUDGET = 8

#: DeepSeek: how many candidates go into one bulk request.
DEFAULT_BATCH_SIZE = 12

#: escalation thresholds (deterministic, declared).
CONFIDENCE_ESCALATE_BELOW = 0.60
HIGH_VALUE_GAP_CONFIDENCE_BELOW = 0.80


def _exec_brain_on_path() -> None:
    if str(EXEC_BRAIN) not in sys.path:
        sys.path.insert(0, str(EXEC_BRAIN))


# --------------------------------------------------------------------------- #
# prompt construction
# --------------------------------------------------------------------------- #

SYSTEM_RULES = (
    "You are a classifier inside a job-discovery funnel. Classify ONLY from the fields "
    "supplied for each candidate. Never invent a job-description fact, requirement, "
    "employer claim, salary, clearance, sponsorship, citizenship, degree or year of "
    "experience. If a field is absent, say so in 'uncertainty' instead of asserting "
    "anything about it. Choose exactly one label per candidate from: "
    + ", ".join(LABELS) + ". "
    "Label meanings: strong_entry_level_match = the supplied text clearly describes an "
    "early-career cyber/IT-security role; plausible_entry_level = consistent with an "
    "early-career role but not certain; ambiguous_review = cannot be decided from the "
    "supplied fields; too_senior = clearly beyond entry level; wrong_discipline = not a "
    "cyber/IT-security/technology-risk role; hard_eligibility_block = an explicit "
    "mandatory requirement stated in the record that the candidate cannot meet "
    "(clearance/citizenship/mandatory multi-year experience). "
    "Reply with ONLY a JSON array, one object per candidate, each: "
    '{"candidate_id": str, "primary_label": str, "confidence": number between 0 and 1, '
    '"reasons": [str], "uncertainty": [str]}. '
    "Keep reasons short and grounded in the supplied fields."
)


def _candidate_payload(record: dict) -> dict:
    payload = {"candidate_id": candidate_id(record)}
    payload.update(present_fields(record))
    return payload


def build_bulk_prompt(records: list) -> str:
    body = json.dumps([_candidate_payload(r) for r in records], ensure_ascii=False, indent=1)
    return (SYSTEM_RULES + "\n\nCandidates:\n" + body)


def build_escalation_prompt(records: list, classifications: list) -> str:
    items = []
    for rec, cls in zip(records, classifications):
        items.append({
            "candidate": _candidate_payload(rec),
            "first_pass": {
                "primary_label": cls.get("primary_label"),
                "confidence": cls.get("confidence"),
                "reasons": cls.get("reasons"),
            },
        })
    return (
        SYSTEM_RULES
        + "\nThis is a SECOND-PASS review of a small bounded set. Re-decide each candidate. "
          "Do not read or write files, do not run commands, and use no tools."
        + "\n\nCandidates:\n"
        + json.dumps(items, ensure_ascii=False, indent=1)
    )


# --------------------------------------------------------------------------- #
# JSON parsing
# --------------------------------------------------------------------------- #

FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_payload(text: str):
    """Extract the first JSON array/object from a model reply (tolerantly)."""
    if not isinstance(text, str) or not text.strip():
        return None, "empty response"
    candidates = []
    fence = FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    for blob in candidates:
        blob = blob.strip()
        for opener in ("[", "{"):
            start = blob.find(opener)
            if start < 0:
                continue
            for closer in ("]", "}") if opener == "[" else ("}",):
                end = blob.rfind(closer)
                if end <= start:
                    continue
                try:
                    return json.loads(blob[start:end + 1]), None
                except json.JSONDecodeError:
                    continue
    return None, "no parseable JSON in response"


# --------------------------------------------------------------------------- #
# deterministic (declared fallback) classification
# --------------------------------------------------------------------------- #

def deterministic_classify(record: dict, *, mode: str = MODE_HIGH_RECALL) -> dict:
    """Rule-only classification. Explicitly NOT a model judgement."""
    decision = title_decision(str(record.get("title") or ""), mode)
    if decision["decision"] == "pass":
        label = "plausible_entry_level"
        reason = f"deterministic title policy ({mode}): {decision['reason']}"
    elif decision.get("tier") == "B":
        label = "too_senior"
        reason = f"deterministic title policy ({mode}): {decision['reason']}"
    else:
        label = "wrong_discipline"
        reason = f"deterministic title policy ({mode}): {decision['reason']}"
    uncertainty = [
        "deterministic rule output, not a model judgement; no semantic reasoning was applied",
    ]
    if not jd_available(record):
        uncertainty.append("no job-description text is present in the record")
    doc = build_classification(
        record, primary_label=label, confidence=None, reasons=[reason],
        uncertainty=uncertainty, provider="none", model="deterministic-title-policy-v1",
        model_identity_observed=False, prompt_version=None,
        classifier="deterministic")
    doc["escalation_eligible"] = False
    doc["escalation_blocked_reason"] = "deterministic fallback: no model pass to review"
    return doc


# --------------------------------------------------------------------------- #
# DeepSeek bulk classification
# --------------------------------------------------------------------------- #

def _deepseek_adapter(model: str):
    _exec_brain_on_path()
    import deepseek_adapter  # noqa: PLC0415
    return deepseek_adapter.DeepSeekExecutionAdapter(model=model)


def deepseek_probe(model: str = "deepseek-flash") -> dict:
    """Credential/reachability probe. Never returns or logs the key."""
    try:
        adapter = _deepseek_adapter(model)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}",
                "auth_source": None, "observed_models": [], "resolved_model": None}
    health = adapter.check_health()
    identity = adapter.get_identity() if health.get("status") == "healthy" else {}
    observed = [m.get("id") for m in (identity.get("observed_models") or []) if m.get("id")]
    resolved = model if model in observed else (observed[0] if observed else model)
    return {
        "available": health.get("status") == "healthy",
        "status": health.get("status"),
        "reason": health.get("reason"),
        "auth_source": health.get("auth_source"),
        "observed_models": observed,
        "model_requested": model,
        "resolved_model": resolved,
        "model_resolution": ("requested model observed at the provider" if resolved == model
                             else "requested model not observed; using the first provider-observed id"
                             if observed else "no model list observed; using the requested id"),
    }


def deepseek_bulk_classify(records: list, *, model: str = "deepseek-flash",
                           batch_size: int = DEFAULT_BATCH_SIZE, timeout: int = 120,
                           adapter=None, mode: str = MODE_HIGH_RECALL) -> dict:
    """Classify the candidate pool with DeepSeek in bounded batches."""
    out = {
        "provider": "deepseek",
        "model_requested": model,
        "model_observed": None,
        "model_identity_observed": False,
        "auth_source": None,
        "prompt_version": PROMPT_VERSION,
        "batch_size": batch_size,
        "requests": 0,
        "batches": 0,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "usage_reported_by_provider": True,
        "errors": [],
        "raw_responses": 0,
        "classifications": {},
        "limitation": None,
    }
    if adapter is None:
        try:
            adapter = _deepseek_adapter(model)
        except Exception as exc:  # noqa: BLE001
            out["limitation"] = f"deepseek adapter unavailable: {type(exc).__name__}: {exc}"
            return out
    health = adapter.check_health()
    out["auth_source"] = health.get("auth_source")
    if health.get("status") != "healthy":
        out["limitation"] = (f"deepseek not healthy ({health.get('status')}: "
                             f"{health.get('reason')}); no model pass was made")
        return out
    identity = adapter.get_identity()
    observed = [m.get("id") for m in (identity.get("observed_models") or []) if m.get("id")]
    resolved = model if model in observed else (observed[0] if observed else model)
    out["model_observed"] = resolved
    out["model_identity_observed"] = bool(observed)
    out["model_resolution"] = ("requested model observed at the provider" if resolved == model
                               else "requested model not observed; used first provider-observed id"
                               if observed else "model list not observed; requested id used unverified")

    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        out["batches"] += 1
        result = adapter.dispatch({
            "contract_id": "discovery-bulk-semantic",
            "objective": build_bulk_prompt(batch),
            "model": resolved,
            "timeout": timeout,
            "max_tokens": 4096,
            "temperature": 0.0,
        })
        out["requests"] += 1
        usage = result.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if isinstance(usage.get(key), int):
                out["usage"][key] = (out["usage"].get(key) or 0) + usage[key]
        if result.get("status") != "COMPLETED":
            out["errors"].append({"batch": out["batches"], "error": result.get("error"),
                                  "exit_code": result.get("exit_code")})
            continue
        payload, err = parse_json_payload(result.get("content") or "")
        if err:
            out["errors"].append({"batch": out["batches"], "error": err})
            continue
        if isinstance(payload, dict) and isinstance(payload.get("classifications"), list):
            payload = payload["classifications"]
        if not isinstance(payload, list):
            out["errors"].append({"batch": out["batches"], "error": "payload was not a list"})
            continue
        out["raw_responses"] += 1
        by_id = {str(item.get("candidate_id")): item for item in payload
                 if isinstance(item, dict) and item.get("candidate_id")}
        for rec in batch:
            cid = candidate_id(rec)
            item = by_id.get(cid)
            if item is None:
                out["errors"].append({"batch": out["batches"], "candidate_id": cid,
                                      "error": "no classification returned for this candidate"})
                out["classifications"][cid] = _unclassified(rec, "model returned no label for this candidate")
                continue
            doc = build_classification(
                rec,
                primary_label=item.get("primary_label"),
                confidence=item.get("confidence") if isinstance(item.get("confidence"), (int, float)) else None,
                reasons=item.get("reasons") if isinstance(item.get("reasons"), list) else [],
                uncertainty=item.get("uncertainty") if isinstance(item.get("uncertainty"), list) else [],
                provider="deepseek", model=resolved,
                model_identity_observed=bool(observed), prompt_version=PROMPT_VERSION,
                classifier="deepseek_bulk")
            doc["rejected_by_guard"] = not doc["valid"]
            out["classifications"][cid] = doc
    if not out["classifications"]:
        out["limitation"] = ("the deepseek pass produced no usable classifications; the funnel "
                            "records this instead of treating the pool as empty")
    return out


def _unclassified(record: dict, reason: str) -> dict:
    doc = build_classification(
        record, primary_label="ambiguous_review", confidence=None,
        reasons=[], uncertainty=[reason],
        provider="deepseek", model="unreported", model_identity_observed=False,
        prompt_version=PROMPT_VERSION, classifier="deepseek_bulk")
    doc["escalation_eligible"] = False
    doc["escalation_blocked_reason"] = "no usable first-pass classification"
    return doc


# --------------------------------------------------------------------------- #
# deterministic escalation + bounded Codex second pass
# --------------------------------------------------------------------------- #

def escalation_reason(classification: dict) -> str | None:
    """Deterministic escalation conditions. ``None`` means: do not spend Codex."""
    if classification.get("escalation_eligible") is False:
        return None
    if classification.get("classifier") != "deepseek_bulk":
        return None
    label = classification.get("primary_label")
    confidence = classification.get("confidence")
    if label in ("ambiguous_review",) or label not in LABELS:
        return "deepseek_label_ambiguous_review"
    if confidence is None:
        return "deepseek_confidence_missing"
    if float(confidence) < CONFIDENCE_ESCALATE_BELOW:
        return f"deepseek_confidence_below_{CONFIDENCE_ESCALATE_BELOW}"
    if (label == "plausible_entry_level" and not classification.get("jd_available")
            and float(confidence) < HIGH_VALUE_GAP_CONFIDENCE_BELOW):
        return "high_value_plausible_without_jd_text"
    return None


def priority_key(classification: dict) -> tuple:
    """Deterministic escalation order, then stable tie-breaks."""
    label_rank = {"ambiguous_review": 0, "plausible_entry_level": 1,
                  "strong_entry_level_match": 2, "hard_eligibility_block": 3,
                  "too_senior": 4, "wrong_discipline": 5}
    confidence = classification.get("confidence")
    confidence = 1.0 if confidence is None else float(confidence)
    return (label_rank.get(classification.get("primary_label"), 9), confidence,
            classification.get("candidate_id") or "")


def select_escalations(records: list, classifications: dict, *, budget: int) -> dict:
    """Choose which candidates Codex reviews. Budget is a hard per-run cap."""
    ranked, skipped = [], []
    for rec in records:
        cid = candidate_id(rec)
        cls = classifications.get(cid)
        if cls is None:
            continue
        reason = escalation_reason(cls)
        if reason:
            ranked.append((priority_key(cls), rec, cls, reason))
    ranked.sort(key=lambda t: t[0])
    selected = ranked[:max(0, budget)]
    for _key, _rec, cls, reason in ranked[max(0, budget):]:
        skipped.append({"candidate_id": cls["candidate_id"], "reason": reason,
                        "dropped": "codex_budget_exhausted"})
    return {"selected": [{"candidate_id": c["candidate_id"], "reason": r} for _k, _r, c, r in selected],
            "selected_pairs": [(rec, cls, reason) for _k, rec, cls, reason in selected],
            "dropped_due_to_budget": skipped,
            "eligible_for_escalation": len(ranked)}


def codex_escalate(records, classifications, *, budget: int = DEFAULT_CODEX_BUDGET,
                   timeout: int = 300, adapter=None, workdir: str | None = None) -> dict:
    """Bounded Codex second pass. Never called for the whole raw scan."""
    out = {
        "provider": "openai-codex-cli",
        "budget": int(budget),
        "requests": 0,
        "cli_version": None,
        "resolved_executable": None,
        "usage_tokens_total": 0,
        "errors": [],
        "classifications": {},
        "escalated": [],
        "dropped_due_to_budget": [],
        "limitation": None,
    }
    plan = select_escalations(records, classifications, budget=budget)
    out["eligible_for_escalation"] = plan["eligible_for_escalation"]
    out["dropped_due_to_budget"] = plan["dropped_due_to_budget"]
    pairs = plan["selected_pairs"]
    if not pairs:
        out["limitation"] = "no candidate met the deterministic escalation conditions"
        return out
    if adapter is None:
        try:
            _exec_brain_on_path()
            import codex_adapter  # noqa: PLC0415
            adapter = codex_adapter.CodexExecutionAdapter()
        except Exception as exc:  # noqa: BLE001
            out["limitation"] = f"codex CLI unavailable: {type(exc).__name__}: {exc}"
            out["escalated"] = [{"candidate_id": c["candidate_id"], "reason": r, "result": "not_run"}
                                for _rec, c, r in pairs]
            return out
    try:
        health = adapter.check_health()
        out["cli_version"] = health.get("version")
        out["resolved_executable"] = str(getattr(adapter, "executable", "")) or None
    except Exception as exc:  # noqa: BLE001
        out["errors"].append({"batch": 0, "error": f"{type(exc).__name__}: {exc}"})

    batch_size = 4
    for start in range(0, len(pairs), batch_size):
        chunk = pairs[start:start + batch_size]
        prompt = build_escalation_prompt([rec for rec, _c, _r in chunk],
                                         [c for _rec, c, _r in chunk])
        contract = {"contract_id": "discovery-codex-second-pass", "objective": prompt,
                    "timeout": timeout}
        if workdir:
            contract["working_directory"] = workdir
        result = adapter.dispatch(contract)
        out["requests"] += 1
        usage = result.get("usage_tokens") or {}
        for value in usage.values():
            if isinstance(value, int):
                out["usage_tokens_total"] += value
        if result.get("status") != "COMPLETED":
            out["errors"].append({"batch": start // batch_size + 1, "error": result.get("error"),
                                  "exit_code": result.get("exit_code")})
            for _rec, cls, reason in chunk:
                out["escalated"].append({"candidate_id": cls["candidate_id"], "reason": reason,
                                         "result": "failed"})
            continue
        payload, err = parse_json_payload(result.get("final_message") or "")
        if err:
            out["errors"].append({"batch": start // batch_size + 1, "error": err})
        by_id = {}
        if isinstance(payload, list):
            by_id = {str(i.get("candidate_id")): i for i in payload
                     if isinstance(i, dict) and i.get("candidate_id")}
        elif isinstance(payload, dict) and isinstance(payload.get("classifications"), list):
            by_id = {str(i.get("candidate_id")): i for i in payload["classifications"]
                     if isinstance(i, dict) and i.get("candidate_id")}
        for rec, cls, reason in chunk:
            cid = cls["candidate_id"]
            item = by_id.get(cid)
            out["escalated"].append({"candidate_id": cid, "reason": reason,
                                     "result": "reviewed" if item else "no label returned"})
            if not item:
                continue
            doc = build_classification(
                rec,
                primary_label=item.get("primary_label"),
                confidence=item.get("confidence") if isinstance(item.get("confidence"), (int, float)) else None,
                reasons=item.get("reasons") if isinstance(item.get("reasons"), list) else [],
                uncertainty=item.get("uncertainty") if isinstance(item.get("uncertainty"), list) else [],
                provider="openai-codex-cli", model=(out.get("cli_version") or "unknown"),
                model_identity_observed=False, prompt_version=PROMPT_VERSION,
                classifier="codex_second_pass",
                extra={"escalation_reason": reason,
                       "reviewed_first_pass": {"primary_label": cls.get("primary_label"),
                                               "confidence": cls.get("confidence")}})
            out["classifications"][cid] = doc
    return out
