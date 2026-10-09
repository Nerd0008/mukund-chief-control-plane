#!/usr/bin/env python3
"""Two-tier title policy for high-recall early-career discovery.

Why this exists
---------------
The owner's own Career Ops ``portals.yml`` title filter is
``positive = [Intern, Internship]``. That is a *precision* filter: used as a
required discovery gate it returns zero whenever no internship is posted, which
is exactly the false-zero the owner reported (Company Watch found 19 new
postings, 0 tracker-eligible).

This module keeps that rule available — unchanged, as ``intern_only`` mode —
and adds a default ``high_recall`` mode built from two independent signals:

    Tier A (recall)  accept when a title carries BOTH
                       * a LEVEL signal  (graduate / junior / analyst / intern /
                         trainee / associate / L1 / apprentice / ...), and
                       * a DISCIPLINE signal (SOC / cyber security / information
                         security / GRC / IAM / vulnerability / technology risk /
                         security consulting / IT support / ...),
                     and carries no NON-CYBER signal (physical security, sales,
                     marketing, ...). "Security" alone is never sufficient.

    Tier B (hard negatives)  reject clearly senior/leadership titles. The
                     owner's own negative list is kept verbatim and matched with
                     the owner's substring semantics; a small, explicitly listed
                     set of extra leadership terms is added on top.

Title matching here is a *prefilter only*. It is not the eligibility decision:
the authoritative gates (region/location, work authorisation, clearance,
explicit mandatory experience, URL validity) run after semantic classification
and cannot be overridden by a title match. See ``pipeline.deterministic_gates``.

Keyword matching mirrors ``scan.mjs``/``title-keywords.mjs`` in the Career Ops
install: short (*2-3 char, letters-only*) keywords match on word boundaries so
``SOC`` cannot match ``Sociedad``; phrases and longer words keep permissive
substring matching so ``analyst`` still matches ``Analysts``.
"""

from __future__ import annotations

import hashlib
import json
import re

MODE_HIGH_RECALL = "high_recall"
MODE_INTERN_ONLY = "intern_only"
MODES = (MODE_HIGH_RECALL, MODE_INTERN_ONLY)
DEFAULT_MODE = MODE_HIGH_RECALL

#: The owner's own ``title_filter.positive`` — kept byte-for-byte for narrow mode.
OWNER_POSITIVE = ["Intern", "Internship"]

#: The owner's own ``title_filter.negative`` — kept byte-for-byte.
OWNER_NEGATIVE = ["Senior", "Principal", "Lead ", "Manager", "Director",
                  "Head of", "Vice President", "VP ", "Staff Security"]

#: Tier B additions. Deliberately small and explicit: each one is a leadership
#: word that the owner's list does not already catch as a substring. Matched on
#: word boundaries so "Chief" does not fire inside an unrelated word.
TIER_B_EXTRA_NEGATIVES = ["chief", "ciso", "executive", "team lead",
                          "technical lead", "group manager"]

# --------------------------------------------------------------------------- #
# Tier A signals
# --------------------------------------------------------------------------- #

#: Seniority / early-career level signals.
LEVEL_TERMS = [
    "intern", "internship", "placement", "industrial placement", "off-cycle",
    "spring week", "spring insight", "apprentice", "apprenticeship",
    "graduate", "grad", "new grad", "new graduate", "graduate scheme",
    "junior", "entry level", "entry-level", "trainee", "associate",
    "analyst", "l1", "level 1", "level one",
    "officer", "specialist", "engineer", "technician", "administrator",
    "assistant",
]

#: Discipline signals: the cyber / IT-security / technology-risk families the
#: owner's target roles live in. The generic word "security" is NOT here on
#: purpose — a title must name an actual discipline, not just the word security.
DISCIPLINE_FAMILIES = {
    "soc_security_operations": [
        "soc", "security operations", "security operation centre",
        "security operation center", "blue team", "incident response",
        "threat intelligence", "threat hunting", "siem", "triage analyst",
        "detection and response", "cyber defence", "cyber defense",
        "phishing",
    ],
    "infosec_cybersecurity": [
        "cyber security", "cybersecurity", "cyber", "information security",
        "infosec", "it security", "network security", "application security",
        "cloud security", "data security", "security analyst",
        "security engineer", "security specialist", "security consultant",
        "security administrator", "security operations", "security assurance",
        "security analysis", "dlp", "data loss prevention", "cryptography",
    ],
    "grc_governance_risk_compliance": [
        "grc", "governance risk", "governance, risk", "risk and compliance",
        "security compliance", "security governance", "iso 27001",
        "compliance analyst", "audit analyst",
        "digital forensics", "forensics", "security management",
    ],
    "iam_identity": [
        "iam", "identity and access", "identity & access", "access management",
        "privileged access", "identity analyst", "identity engineer",
        "identity management", "directory services",
    ],
    "vulnerability": [
        "vulnerability", "penetration test", "penetration tester", "pentest",
        "pen test", "security testing", "red team", "exploit",
    ],
    "technology_risk": [
        "technology risk", "tech risk", "it risk", "cyber risk",
        "information risk", "third party risk", "third-party risk",
        "operational risk", "risk analyst", "risk consultant",
        "risk and control", "controls assurance",
    ],
    "security_consulting_entry": [
        "security consulting", "cyber consulting", "security advisory",
        "cyber advisory", "security transformation",
    ],
    "it_support_security_adjacent": [
        "it support", "service desk", "helpdesk", "help desk",
        "desktop support", "application support", "technical support",
        "it operations", "it analyst", "systems administrator",
        "endpoint", "it infrastructure",
    ],
}

#: Strong cyber terms. When one of these is present, the generic
#: physical-security exclusions below are skipped (an "Information Security
#: Officer" is not a gate guard).
STRONG_CYBER_TERMS = [
    "cyber", "information security", "infosec", "it security", "soc",
    "grc", "iam", "vulnerability", "penetration", "incident response",
    "siem", "security operations", "network security", "application security",
    "cloud security", "threat intelligence", "technology risk", "cyber risk",
]

#: Non-cyber signals. Each entry is ``(term, exempt_when_strong_cyber)``.
NON_CYBER_SIGNALS = [
    ("physical security", True),
    ("security guard", True),
    ("security officer", True),
    ("event security", True),
    ("retail security", True),
    ("loss prevention", False),
    ("security sales", False),
    ("sales", False),
    ("account executive", False),
    ("business development", False),
    ("marketing", False),
    ("recruitment", False),
    ("close protection", False),
    ("credit risk", False),
    ("market risk", False),
]


def _compile_keyword(keyword: str):
    """Mirror of the Career Ops install's title-keyword matcher.

    * 2-3 char all-letter keywords (``soc``, ``iam``, ``grc``) match on word
      boundaries, so ``SOC`` cannot match ``Sociedad``.
    * everything else (phrases, longer words, anything with a digit) keeps
      permissive substring matching, so ``analyst`` still matches ``Analysts``
      and ``l1`` still matches ``L1``.
    """
    kw = keyword.strip().lower()
    if kw and len(kw) <= 3 and kw.isalpha():
        rx = re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])")
        return lambda lower: bool(rx.search(lower))
    return lambda lower: kw in lower


_DISCIPLINE_COMPILED = {
    family: [(t, _compile_keyword(t)) for t in terms]
    for family, terms in DISCIPLINE_FAMILIES.items()
}
_LEVEL_COMPILED = [(t, _compile_keyword(t)) for t in LEVEL_TERMS]
_STRONG_COMPILED = [(t, _compile_keyword(t)) for t in STRONG_CYBER_TERMS]
_NON_CYBER_COMPILED = [(t, _compile_keyword(t), exempt) for t, exempt in NON_CYBER_SIGNALS]
_OWNER_NEGATIVE_LOWER = [n.lower() for n in OWNER_NEGATIVE]
_TIER_B_EXTRA_COMPILED = [(t, _compile_keyword(t)) for t in TIER_B_EXTRA_NEGATIVES]


def tier_b_hits(title: str) -> list:
    """Senior/leadership signals in a title (owner list verbatim + additions)."""
    lower = (title or "").lower()
    hits = [n for n in _OWNER_NEGATIVE_LOWER if n in lower]
    hits += [t for t, m in _TIER_B_EXTRA_COMPILED if m(lower)]
    return sorted({h.strip() for h in hits if h.strip()})


def tier_a_signals(title: str) -> dict:
    """Level / discipline / non-cyber signals found in a title."""
    lower = (title or "").lower()
    level = [t for t, m in _LEVEL_COMPILED if m(lower)]
    families = {}
    for family, terms in _DISCIPLINE_COMPILED.items():
        matched = [t for t, m in terms if m(lower)]
        if matched:
            families[family] = matched
    strong = [t for t, m in _STRONG_COMPILED if m(lower)]
    non_cyber = []
    for term, matcher, exempt in _NON_CYBER_COMPILED:
        if not matcher(lower):
            continue
        if exempt and strong:
            continue
        non_cyber.append(term)
    return {"level": sorted(set(level)), "discipline_families": families,
            "strong_cyber": sorted(set(strong)), "non_cyber": sorted(set(non_cyber))}


def intern_only_decision(title: str) -> dict:
    """The owner's original rule, unchanged: positive terms are required."""
    lower = (title or "").lower()
    for kw in _OWNER_NEGATIVE_LOWER:
        if kw in lower:
            return {"mode": MODE_INTERN_ONLY, "decision": "reject", "tier": "B",
                    "reason": f"title policy excludes '{kw.strip()}'",
                    "signals": {"hard_negative": [kw.strip()]}}
    if not any(kw.lower() in lower for kw in OWNER_POSITIVE):
        return {"mode": MODE_INTERN_ONLY, "decision": "reject", "tier": "A",
                "reason": f"title matches none of the owner's positive terms {OWNER_POSITIVE}",
                "signals": {"level": [], "discipline_families": {}}}
    return {"mode": MODE_INTERN_ONLY, "decision": "pass", "tier": "A",
            "reason": "title passes the owner's intern/internship title policy",
            "signals": {"level": ["intern"], "discipline_families": {}}}


def high_recall_decision(title: str) -> dict:
    """Tier B negatives first, then the Tier A level+discipline rule."""
    hits = tier_b_hits(title)
    if hits:
        return {"mode": MODE_HIGH_RECALL, "decision": "reject", "tier": "B",
                "reason": f"senior/leadership title signal: {', '.join(hits)}",
                "signals": {"hard_negative": hits}}
    sig = tier_a_signals(title)
    if sig["non_cyber"]:
        return {"mode": MODE_HIGH_RECALL, "decision": "reject", "tier": "A",
                "reason": f"non-cyber title signal: {', '.join(sig['non_cyber'])}",
                "signals": sig}
    families = sorted(sig["discipline_families"])
    if not sig["level"]:
        return {"mode": MODE_HIGH_RECALL, "decision": "reject", "tier": "A",
                "reason": "no early-career level signal (graduate/junior/analyst/L1/...) in the title",
                "signals": sig}
    if not families:
        return {"mode": MODE_HIGH_RECALL, "decision": "reject", "tier": "A",
                "reason": ("no cyber/IT-security/technology-risk discipline signal in the title "
                           "(the generic word 'security' alone is not sufficient)"),
                "signals": sig}
    return {"mode": MODE_HIGH_RECALL, "decision": "pass", "tier": "A",
            "reason": (f"early-career level signal {sig['level']} plus discipline family "
                       f"{families}"),
            "signals": sig}


def title_decision(title: str, mode: str = DEFAULT_MODE) -> dict:
    """Apply the title policy for ``mode``. Prefilter only — never final eligibility."""
    if mode == MODE_INTERN_ONLY:
        return intern_only_decision(title)
    if mode != MODE_HIGH_RECALL:
        raise ValueError(f"unknown title policy mode '{mode}'; known: {MODES}")
    return high_recall_decision(title)


def policy_document() -> dict:
    """The full policy as data, with a stable hash for run evidence."""
    doc = {
        "default_mode": DEFAULT_MODE,
        "modes": list(MODES),
        "mode_semantics": {
            MODE_HIGH_RECALL: ("Tier A accepts an early-career level signal PLUS a cyber/IT "
                               "discipline signal and rejects non-cyber signals; Tier B rejects "
                               "senior/leadership titles first"),
            MODE_INTERN_ONLY: ("the owner's original portals.yml title_filter, unchanged: "
                               "positive terms are required"),
        },
        "owner_positive": OWNER_POSITIVE,
        "owner_negative": OWNER_NEGATIVE,
        "tier_b_extra_negatives": TIER_B_EXTRA_NEGATIVES,
        "level_terms": LEVEL_TERMS,
        "discipline_families": DISCIPLINE_FAMILIES,
        "strong_cyber_terms": STRONG_CYBER_TERMS,
        "non_cyber_signals": [{"term": t, "exempt_when_strong_cyber": e}
                              for t, e in NON_CYBER_SIGNALS],
        "boundary": ("prefilter only: region/location, work authorisation, clearance, explicit "
                     "mandatory experience requirements and application-URL validity remain "
                     "authoritative and are applied after semantic classification"),
    }
    doc["policy_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in doc.items() if k != "policy_sha256"},
                   sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return doc
