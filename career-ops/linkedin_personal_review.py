"""Exact-body personal review with conservative, reproducible news attribution.

The CV verifier is subject-blind. It must not compare explicitly attributed
third-party metrics against candidate achievements. Only clear reporting clauses
in an entirely non-personal post are excluded; mixed/implicit/ambiguous career
content is reviewed in full. The independent news gate remains mandatory.
"""
import hashlib
import re

SCOPE_VERSION = 1
PERSONAL = re.compile(r"\b(?:I|me|my|mine|we|our|ours|Mukund|Didwania)\b", re.I)
IMPLICIT = re.compile(r"^\s*(?:[-*•]\s*)?(?:[a-z]+ed|built|led|ran|wrote|grew|taught|held|oversaw|won|made|hold|responsible|proficient|skilled|education|employment|experience|projects|certifications|as an?)\b", re.I)
ATTRIBUTED = re.compile(
    r"^\s*(?:According to\b|(?:A|An|The)\s+(?:vendor|company|report|study|researcher|researchers|agency|team)\s+"
    r"(?:reports?|reported|announces?|announced|states?|stated|found|finds|estimates?|estimated)\b|"
    r"[A-Z][\w.-]*(?:\s+[A-Z][\w.-]*){0,5}\s+(?:reports?|reported|announces?|announced|states?|stated)\b)"
)


def personal_text(body):
    body = body.strip()
    clauses = re.split(r"(?<=[.!?])\s+|\n+", body)
    if PERSONAL.search(body) or any(IMPLICIT.search(c) for c in clauses):
        return body  # never infer ownership away from a mixed or career post
    return "\n".join(c for c in clauses if not ATTRIBUTED.search(c))


def review(cfg, body, *, label, scratch):
    import cv_workflow
    body = body.strip()
    checked = personal_text(body)
    result = cv_workflow.fact_gate(cfg, checked, label=label, scratch=scratch)
    return {**result, "gate_name": "verify-cv-facts", "scope_version": SCOPE_VERSION,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "reviewed_text_sha256": hashlib.sha256(checked.encode("utf-8")).hexdigest()}


def scope_matches(gate, body):
    if "scope_version" not in gate:
        # Older exact-body receipts reviewed the entire text. No omission is
        # inferred from their missing scope metadata.
        return "reviewed_text_sha256" not in gate
    return (gate.get("scope_version") == SCOPE_VERSION
            and gate.get("reviewed_text_sha256") == hashlib.sha256(
                personal_text(body).encode("utf-8")).hexdigest())