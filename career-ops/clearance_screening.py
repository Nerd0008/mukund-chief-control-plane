#!/usr/bin/env python3
"""Canonical clearance/citizenship screening of job-description text.

One implementation, used by every lane that screens a posting:

* ``regional_job_search.evaluate_record`` — the shared filter all four regions call
* ``codex_entry_level_search`` — the UK entry-level search's JD gate
* ``eligibility_sweep`` — re-screening of rows already sitting in a tracker

Why this module exists
----------------------
``codex_entry_level_search`` and ``regional_job_search`` each carried their own
copy of ``CLEARANCE_TOKEN_RE`` with a comment saying they were "kept in sync".
They were byte-identical when this module was extracted, but a hand-maintained
duplicate is a drift hazard: a fix applied to one copy silently leaves the other
stale, and the two lanes then disagree about what is eligible.

Three failure modes, all observed against the live tracker, shaped the rules
below. Each was found by running the sweep, not by reading code.

1. **Markup is matched.** ``\\bSC\\b`` matched the styled-components class in
   ``<div class="sc-129pb7e-1 bh">`` on the Acturis Graduate Technical Business
   Analyst posting — a role that requires no vetting at all.

2. **Bare tokens are matched out of context.** ``SC`` and ``DV`` are also a
   Microsoft certification code (``SC-200``), US state abbreviations
   (``Myrtle Beach, SC``), a company name (``DV Trading``, ``the DV Group``) and
   board chrome. Each produced a false "clearance required" verdict.

3. **Garbled pages are treated as clean.** Two rows fetched as undecodable
   byte soup produced hits on random characters. An unreadable page proves
   nothing, so it is reported as UNSCREENED rather than CLEAR.

Rules
-----
* Run over the page's **visible** text — script bodies, style blocks, comments
  and markup are removed first.
* **Strong phrases** (``security clearance``, ``british citizenship``,
  ``indefinite right to work`` …) are always a hit.
* **Bare tokens** (``SC``, ``DV``, ``CTC``, ``NPPV``, ``UKSV``, ``BPSS``) are a
  hit only when a vetting word appears within ``CONTEXT_CHARS`` of them.
* Text that cannot be decoded is not screened.
"""

import html
import re
import unicodedata

#: Phrases that are unambiguous on their own.
STRONG_PHRASE_RE = re.compile(
    r"security[\s-]clearance"
    r"|national[\s-]security[\s-]clearance"
    r"|police[\s-]clearance"
    r"|personnel[\s-]security[\s-]standard"
    r"|british[\s-]citizen(?:ship)?"
    r"|indefinite[\s-]leave[\s-]to[\s-]remain"
    r"|indefinite[\s-]right[\s-]to[\s-]work"
    r"|long[\s-]uk[\s-]residency",
    re.IGNORECASE,
)

#: Single-letter-ish clearance levels. Ambiguous on their own, so they are only
#: counted alongside vetting context (see :data:`CONTEXT_RE`).
BARE_TOKEN_RE = re.compile(r"\b(?:SC|DV|CTC|NPPV|UKSV|BPSS)\b", re.IGNORECASE)

#: "Security check" is ambiguous too: a role can *perform* security checks
#: (Lloyds, "automate repetitive tasks and security checks") or be *subject to*
#: them (Proact, "HMG Security Check - SC - clearance"). Only vetting context
#: makes it a requirement.
SECURITY_CHECK_RE = re.compile(r"security[\s-]checks?", re.IGNORECASE)

#: What makes a bare token mean a vetting requirement.
CONTEXT_RE = re.compile(
    r"clearance|vetting|vet\b|screening|\bobtain|eligible|eligibility"
    r"|requirement|required|personnel[\s-]security|national[\s-]security"
    r"|right[\s-]to[\s-]work|citizenship|citizen|\bhmg\b|government",
    re.IGNORECASE,
)

#: Stricter context for "security check".
GOVERNMENT_CONTEXT_RE = re.compile(
    r"\bhmg\b|government|clearance|vetting|national[\s-]security"
    r"|\bbpss\b|\bsc\b|\bdv\b|\bctc\b|\buksv\b|\bnppv\b",
    re.IGNORECASE,
)

#: How far from a context-bound token to look for its qualifying context.
CONTEXT_CHARS = 90

#: KNOWN LIMITATION — aggregator pages embed other employers' listings, and the
#: quoted requirement can belong to a different role (observed on the Zeriq row:
#: "Blue Cross and Blue Shield of Nebraska Omaha, NE 1 week ago Cyber Security
#: Analyst - 306211 with Security Clearance"). It is *not* filtered here: a window
#: tight enough to catch it also taints a genuine requirement quoted a few
#: sentences later, and silently dropping a real requirement is the worse error.
#: The sweep reports the surrounding sentence as evidence so a reviewer can see
#: the contamination.

_SCRIPT_RE = re.compile(r"(?is)<script[^>]*>.*?</script>")
_STYLE_RE = re.compile(r"(?is)<style[^>]*>.*?</style>")
_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_TAG_RE = re.compile(r"(?s)<[^>]*>")
_NBSP_RE = re.compile(r"&(?:nbsp|#160|#xa0);", re.IGNORECASE)

#: Ratio of undecodable characters above which a page is treated as unreadable.
#: Whitespace is excluded — a page with line breaks in it is not garbled.
GARBLED_RATIO = 0.05


def visible_text(text) -> str:
    """Return the readable text of a fetched job description.

    Markup is removed so a clearance token cannot match a class attribute, a CSS
    rule or a script body. Non-string input yields ``""``.
    """
    if not isinstance(text, str):
        return ""
    t = _SCRIPT_RE.sub(" ", text)
    t = _STYLE_RE.sub(" ", t)
    t = _COMMENT_RE.sub(" ", t)
    t = _TAG_RE.sub(" ", t)
    t = _NBSP_RE.sub(" ", t)
    return html.unescape(t)


def is_readable(text) -> bool:
    """False when a fetched page is byte soup rather than prose.

    A page that cannot be decoded cannot prove a role has no barrier, so the
    sweep reports it as UNSCREENED instead of CLEAR. Ordinary whitespace does
    not count — counting ``\\n`` as garbling rejected every normal multi-line
    job description.
    """
    t = visible_text(text)
    if not t.strip():
        return False
    bad = 0
    for ch in t:
        if ch in "\n\r\t":
            continue
        if ch == "\ufffd":
            bad += 1
            continue
        if unicodedata.category(ch) in ("Cc", "Cs", "Co", "Cn"):
            bad += 1
    return (bad / len(t)) < GARBLED_RATIO


def clearance_hits(text) -> list:
    """Return sorted unique clearance/citizenship tokens in the visible text."""
    return sorted(set(_hit_tokens(text)))


def _context_ok(t, start, end, pattern):
    """True when ``pattern`` appears within ``CONTEXT_CHARS`` of the match."""
    lo = max(0, start - CONTEXT_CHARS)
    hi = min(len(t), end + CONTEXT_CHARS)
    return bool(pattern.search(t[lo:hi]))


def _hit_tokens(text) -> list:
    t = visible_text(text)
    if not t.strip() or not is_readable(t):
        return []
    hits = [m.group(0).strip().lower() for m in STRONG_PHRASE_RE.finditer(t)]
    for m in BARE_TOKEN_RE.finditer(t):
        if _context_ok(t, m.start(), m.end(), CONTEXT_RE):
            hits.append(m.group(0).strip().lower())
    for m in SECURITY_CHECK_RE.finditer(t):
        if _context_ok(t, m.start(), m.end(), GOVERNMENT_CONTEXT_RE):
            hits.append(m.group(0).strip().lower())
    return hits


def clearance_evidence(text, context: int = 120) -> list:
    """Return each hit with the surrounding visible text, for reporting.

    Evidence, not just a token list: a reviewer can see the sentence that made a
    role ineligible instead of inferring it from ``['sc']``.
    """
    t = visible_text(text)
    if not t.strip() or not is_readable(t):
        return []
    out = [_evidence(t, m.group(0), m.start(), m.end(), context)
           for m in STRONG_PHRASE_RE.finditer(t)]
    for m in BARE_TOKEN_RE.finditer(t):
        if _context_ok(t, m.start(), m.end(), CONTEXT_RE):
            out.append(_evidence(t, m.group(0), m.start(), m.end(), context))
    for m in SECURITY_CHECK_RE.finditer(t):
        if _context_ok(t, m.start(), m.end(), GOVERNMENT_CONTEXT_RE):
            out.append(_evidence(t, m.group(0), m.start(), m.end(), context))
    return out


def _evidence(text, token, start, end, context):
    s = max(0, start - context)
    e = min(len(text), end + context)
    return {"token": token.strip().lower(),
            "context": " ".join(text[s:e].split())}
