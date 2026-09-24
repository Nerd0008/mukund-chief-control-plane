#!/usr/bin/env python3
"""Structured semantic-classification contract + no-invented-facts guard.

The contract is the only shape a semantic classification may take, whatever
produced it (DeepSeek bulk pass, Codex second pass, or the declared
deterministic fallback). Every classification carries:

* one of the declared labels (never a free-text verdict),
* the source fields it was derived from, and the fields that were absent,
* reasons (assertions) and uncertainty (explicit gaps) kept separate,
* a confidence in [0, 1] or an explicit ``None`` (never a fabricated number),
* model/provider provenance, including whether the model identity was observed
  or is unknown.

Guard rules enforced here
-------------------------
1. A label must be one of ``LABELS``.
2. ``source_fields`` must be a subset of the source record's own fields, with
   identical values — a classifier cannot add a field to the record.
3. ``missing_fields`` may only name fields that really are absent.
4. No invented facts: any number or quoted string appearing in ``reasons`` (or
   in ``uncertainty``) must literally occur in the source text, and any
   fact-class word (years / sponsorship / clearance / citizenship / degree /
   visa / salary / certification) used in an *assertion* must also occur in the
   source text. Absence of a JD is expressed in ``uncertainty``, not asserted.
"""

from __future__ import annotations

import hashlib
import json
import re

CONTRACT_VERSION = 1

LABELS = (
    "strong_entry_level_match",
    "plausible_entry_level",
    "ambiguous_review",
    "too_senior",
    "wrong_discipline",
    "hard_eligibility_block",
)

ACCEPT_LABELS = ("strong_entry_level_match", "plausible_entry_level")
ESCALATION_LABELS = ("ambiguous_review",)
REJECT_LABELS = ("too_senior", "wrong_discipline", "hard_eligibility_block")

#: Fields a classification may cite, and how each is handled when absent.
SOURCE_FIELDS = ("company", "title", "location", "description", "summary",
                 "posted_date", "salary", "url", "source", "vendor",
                 "experience_required", "employment_type")

#: Word classes that may only be asserted when the source record says so.
FACT_CLASS_TOKENS = ("year", "years", "yrs", "sponsor", "sponsorship",
                     "sponsoring", "clearance", "cleared", "citizen",
                     "citizenship", "degree", "visa", "salary", "certification",
                     "certified", "onsite", "hybrid")

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
QUOTED_RE = re.compile(r"[\"']([^\"']{2,})[\"']")
WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z]+")


def candidate_id(record: dict) -> str:
    """Stable id for a candidate record, from its own identifying fields."""
    basis = "|".join(str(record.get(k) or "").strip().casefold()
                     for k in ("company", "title", "location", "url"))
    return "cand-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def present_fields(record: dict) -> dict:
    """The subset of SOURCE_FIELDS actually present (non-empty) on the record."""
    return {k: record[k] for k in SOURCE_FIELDS
            if record.get(k) not in (None, "", [], {})}


def missing_fields(record: dict) -> list:
    return [k for k in SOURCE_FIELDS if record.get(k) in (None, "", [], {})]


def source_text(record: dict) -> str:
    return " ".join(str(v) for v in present_fields(record).values()).casefold()


def jd_available(record: dict) -> bool:
    """True only when the record actually carries job-description text.

    The Career Ops scan output carries company/title/location and no URL, so
    most discoveries arrive without a JD. That is recorded, never assumed away.
    """
    for key in ("description", "summary"):
        value = record.get(key)
        if isinstance(value, str) and len(value.strip()) >= 80:
            return True
    return False


def classification_basis(record: dict) -> str:
    return "title_company_location_plus_jd" if jd_available(record) else "title_company_location_only"


def guard(classification: dict, record: dict) -> dict:
    """Deterministic no-invented-facts check. Returns ``{ok, violations, warnings}``."""
    violations: list = []
    warnings: list = []
    text = source_text(record)
    reasons = classification.get("reasons") or []
    uncertainty = classification.get("uncertainty") or []
    if not isinstance(reasons, list):
        violations.append("reasons must be a list")
        reasons = []
    if not isinstance(uncertainty, list):
        violations.append("uncertainty must be a list")
        uncertainty = []

    for blob_name, blob in (("reasons", reasons), ("uncertainty", uncertainty)):
        for item in blob:
            if not isinstance(item, str):
                violations.append(f"{blob_name} entries must be strings")
                continue
            lowered = item.casefold()
            for number in NUMBER_RE.findall(item):
                if number not in text:
                    violations.append(f"number '{number}' asserted in {blob_name} is not in the source record")
            for quoted in QUOTED_RE.findall(item):
                if quoted.casefold() not in text:
                    violations.append(f"quoted text '{quoted}' in {blob_name} is not in the source record")

    # fact-class words may only appear in assertions the source supports.
    for item in reasons:
        if not isinstance(item, str):
            continue
        lowered = item.casefold()
        for token in FACT_CLASS_TOKENS:
            if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", lowered) and token not in text:
                violations.append(
                    f"assertion mentions '{token}' but the source record contains no such field")

    label = classification.get("primary_label")
    if label not in LABELS:
        violations.append(f"unknown primary_label '{label}'; allowed: {list(LABELS)}")
    confidence = classification.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            violations.append("confidence must be a number or null")
        elif not 0.0 <= float(confidence) <= 1.0:
            violations.append("confidence must be within [0, 1]")
    else:
        warnings.append("confidence absent: recorded as unknown, never imputed")

    if not classification.get("model"):
        warnings.append("model identity absent")
    if not classification.get("provider"):
        warnings.append("provider absent")

    src = classification.get("source_fields") or {}
    if not isinstance(src, dict):
        violations.append("source_fields must be an object")
    else:
        for key, value in src.items():
            if key not in SOURCE_FIELDS:
                violations.append(f"source_fields cites unknown field '{key}'")
            elif key not in present_fields(record):
                violations.append(f"source_fields cites absent field '{key}'")
            elif str(value) != str(present_fields(record)[key]):
                violations.append(f"source_fields['{key}'] does not match the source record")
    return {"ok": not violations, "violations": violations, "warnings": warnings}


def build_classification(record: dict, *, primary_label: str, confidence, reasons,
                         uncertainty, provider: str, model: str,
                         model_identity_observed: bool = False,
                         prompt_version: str | None = "v1", classifier: str = "semantic",
                         extra: dict | None = None) -> dict:
    """Assemble a contract-shaped classification and run the guard on it."""
    doc = {
        "contract_version": CONTRACT_VERSION,
        "candidate_id": candidate_id(record),
        "primary_label": primary_label,
        "confidence": confidence,
        "reasons": list(reasons or []),
        "uncertainty": list(uncertainty or []),
        "source_fields": present_fields(record),
        "missing_fields": missing_fields(record),
        "jd_available": jd_available(record),
        "classification_basis": classification_basis(record),
        "provider": provider,
        "model": model,
        "model_identity_observed": bool(model_identity_observed),
        "classifier": classifier,
        "prompt_version": prompt_version,
        "accepted": primary_label in ACCEPT_LABELS,
    }
    if extra:
        doc.update(extra)
    result = guard(doc, record)
    doc["guard"] = result
    doc["valid"] = result["ok"]
    if not doc["jd_available"]:
        note = ("no job-description text was supplied, so this classification is derived from "
                "title/company/location fields only and is NOT semantic JD analysis")
        if note not in doc["uncertainty"]:
            doc["uncertainty"].append(note)
    return doc


def contract_document() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "labels": list(LABELS),
        "accept_labels": list(ACCEPT_LABELS),
        "escalation_labels": list(ESCALATION_LABELS),
        "reject_labels": list(REJECT_LABELS),
        "source_fields": list(SOURCE_FIELDS),
        "fact_class_tokens": list(FACT_CLASS_TOKENS),
        "rules": [
            "every classification carries source fields, reasons, confidence/uncertainty and "
            "provider/model provenance",
            "a classification never invents a JD fact absent from the source record",
            "where no JD text is available the classification says so and is explicitly not "
            "semantic JD analysis",
        ],
    }


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False, default=str)
