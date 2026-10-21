#!/usr/bin/env python3
"""Canonical prior-experience screening of job-description text.

One implementation, used by every lane that screens a posting:

* ``regional_job_search.evaluate_record`` — the shared filter all four regions call
* ``codex_entry_level_search`` — the UK entry-level search's JD gate
* ``experience_sweep`` — re-screening of rows already sitting in a tracker

Why this module exists
----------------------
``codex_entry_level_search.is_entry_level`` reads the **title only**::

    def is_entry_level(title, entry_markers=None):
        t = (title or "").lower()
        if any(m in t for m in SENIOR_MARKERS):
            return False
        return any(m in t for m in (entry_markers or ENTRY_MARKERS))

A vacancy advertised as "IT Support Analyst" or "Cyber Security Analyst" passes
that gate whether it wants a new graduate or five years in a service desk. The
JD is already fetched at the point of decision — it is used for the closed/filled
check and for clearance screening — but it was never read for experience. This is
the same failure the clearance gate had, and it is fixed the same way.

Rules
-----
* Run over the page's **visible** text — markup is stripped first, so a styled
  class name cannot be mistaken for a requirement.
* A **numeric requirement** (``2+ years``, ``minimum of 3 years``, ``two years``)
  is a hit only when an experience word sits within ``CONTEXT_CHARS`` of it. This
  keeps "we have served clients for 2+ years" out of the results.
* A **strong phrase** (``proven track record``, ``prior experience``,
  ``commercial experience`` …) is a hit on its own.
* Requirements below ``MIN_YEARS`` (``0-1 years``, ``1 year``, ``up to 2 years``
  phrased as a range starting at 0 or 1) are entry-level and are not hits.
* Text that cannot be decoded is not screened; the caller treats it as UNSCREENED.
"""

import re

from clearance_screening import is_readable, visible_text

#: Years at or above this are not an entry-level requirement.
MIN_YEARS = 2

#: Phrases that state a requirement on their own.
STRONG_PHRASE_RE = re.compile(
    r"proven\s+(?:track\s+record|experience)"
    r"|(?:prior|previous|existing|relevant)\s+(?:work\s+)?experience"
    r"|(?:commercial|industrial|industry|professional|corporate)\s+experience"
    r"|experience\s+in\s+a\s+similar\s+role"
    r"|demonstrable\s+experience"
    r"|(?:minimum|at\s+least)\s+of?\s*\d{1,2}\s*years?"
    r"|\d{1,2}\s*\+\s*years?\s*(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+)?experience",
    re.IGNORECASE,
)

#: A number followed by "year(s)", with an optional range and an optional plus.
_YEARS_RE = re.compile(
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(?:\+|\bplus\b)?\s*(?:-|\u2013|\u2014|to)?\s*(\d{1,2})?\s*\+?\s*"
    r"years?\b",
    re.IGNORECASE,
)

#: A number that must be near a year phrase to count as an experience requirement.
_EXPERIENCE_WORD_RE = re.compile(
    r"experience|working|worked|industry|commercial|professional|"
    r"track\s+record|background|career|employment|hands[\s-]on",
    re.IGNORECASE,
)

#: "2 years" in these contexts describes study, not employment.
_STUDY_YEAR_RE = re.compile(
    r"(?:penultimate|final|first|second|third|fourth)\s+year"
    r"|year\s+(?:of\s+study|of\s+the\s+degree|of\s+your\s+degree|undergraduate)"
    r"|years?\s+(?:of\s+)?(?:study|academic\s+study|university|education)"
    r"|(?:degree|bachelor|master|bsc|msc|phd)\s+.{0,20}?\d{1,2}\s*years?",
    re.IGNORECASE,
)

#: How far from a year phrase an experience word may sit and still count.
CONTEXT_CHARS = 90

#: "No prior experience needed" states the opposite of a requirement. The guard
#: only looks immediately before the phrase, so "no" elsewhere in the advert
#: cannot suppress a genuine requirement.
_NEGATION_RE = re.compile(
    r"\b(?:no|not|without|none|never|n't|does\s+not|do\s+not|"
    r"need\s+not|no\s+need\s+for|not\s+required|is\s+not|are\s+not)\b"
    r"[^.;]{0,30}$",
    re.IGNORECASE,
)

#: Contexts where a year phrase describes the employer, the website or an
#: eligibility CAP — never the candidate. Each pattern below was a real false
#: positive against the live tracker, not a hypothetical.
_NOT_CANDIDATE_RE = re.compile(
    # the employer's own history
    r"our\s+history|founded|established\s+in|since\s+\d{4}"
    r"|we(?:'ve|\s+have)\s+been|over\s+the\s+past|past\s+\w+\s+years"
    r"|working\s+with\s+the\s+team\s+over"
    # website chrome, including the cookie banner
    r"|cookies?|your\s+preferences|this\s+website|browser"
    # an upper bound is the opposite of a requirement
    r"|fewer\s+than|less\s+than|no\s+more\s+than|maximum\s+of"
    # a degree awarded recently is an eligibility rule, not experience
    r"|\b(?:achieved|completed|awarded|graduated|finished)\s+"
    r"(?:within|in)\s+the\s+last\b"
    # inclusive phrasing: the experience is optional, not required
    r"|could\s+also\s+be|also\s+consider|would\s+also|also\s+welcome"
    r"|also\s+open\s+to|equally\s+consider|or\s+a\s+graduate",
    re.IGNORECASE,
)

#: A duration attached to a programme, scheme or contract describes the training,
#: not the candidate's history.
_DURATION_RE = re.compile(
    r"\b\w+[\s-]years?[\s-](?:programme|scheme|contract|training|degree|course|placement)"
    r"|\b(?:programme|scheme|contract|training)\s+(?:is|will|runs|lasts|over)"
    r"|\bover\s+\w+\s+years\b|\bduring\s+the\s+\w+\s+years\b"
    r"|\b\d[\s-]year\s+(?:programme|scheme|contract|training)\b"
    # the employer's own "40-year track record" — a bare "proven track record"
    # is a requirement on the candidate and must survive
    r"|\b\w+[\s-]years?[\s-]track\s+record",
    re.IGNORECASE,
)

#: Verbs describing what the role GIVES the candidate — "gain industry
#: experience" is an offer, not a requirement.
_BENEFIT_RE = re.compile(
    r"\b(?:gain|build|develop|learn|acquire|broaden|exposure\s+to|"
    r"opportunity\s+to)\b",
    re.IGNORECASE,
)

#: A range whose lower bound is in months is entry-level: "6 months to 2 years".
_MONTH_FLOOR_RE = re.compile(r"\b\d{1,2}\s*months?\s*(?:-|\u2013|\u2014|to)\s*$",
                             re.IGNORECASE)

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _to_int(token):
    if token is None:
        return None
    token = str(token).strip().lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def _negated(text, start):
    """True when the phrase at ``start`` is introduced by a negation."""
    return bool(_NEGATION_RE.search(text[max(0, start - 45):start]))


def _context_ok(text, start, end):
    """True when a year phrase is a requirement on the candidate.

    Each disqualifier here answers a false positive observed on the live tracker:
    the employer's track record, a programme's duration, a cookie banner, an
    eligibility cap, and a range that starts in months.
    """
    lo = max(0, start - CONTEXT_CHARS)
    hi = min(len(text), end + CONTEXT_CHARS)
    window = text[lo:hi]

    if not _EXPERIENCE_WORD_RE.search(window):
        return False
    if _STUDY_YEAR_RE.search(window):
        return False
    if _NOT_CANDIDATE_RE.search(window):
        return False
    if _DURATION_RE.search(window):
        return False
    if _MONTH_FLOOR_RE.search(text[max(0, start - 20):start]):
        return False
    # "gain industry experience" offers experience; it does not require it.
    if _BENEFIT_RE.search(text[max(0, start - 40):start]):
        return False
    return True


def experience_hits(text, min_years: int = MIN_YEARS) -> list:
    """Return the prior-experience requirements found in a job description.

    An empty list means no requirement at or above ``min_years`` was found — it
    does not prove the role is entry-level, only that nothing said otherwise.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    if not is_readable(text):
        return []

    t = visible_text(text)
    hits = []

    for m in _YEARS_RE.finditer(t):
        low = _to_int(m.group(1))
        high = _to_int(m.group(2))
        floor = low if low is not None else high
        if floor is None or floor < min_years:
            continue
        if not _context_ok(t, m.start(), m.end()):
            continue
        if _negated(t, m.start()):
            continue
        span = t[max(0, m.start() - 40):m.end() + 40].strip()
        snippet = " ".join(span.split())
        if snippet not in hits:
            hits.append(snippet)

    for m in STRONG_PHRASE_RE.finditer(t):
        if _negated(t, m.start()):
            continue
        window = t[max(0, m.start() - CONTEXT_CHARS):m.end() + CONTEXT_CHARS]
        if _STUDY_YEAR_RE.search(window):
            continue
        if _NOT_CANDIDATE_RE.search(window):
            continue
        if _DURATION_RE.search(window):
            continue
        if _BENEFIT_RE.search(t[max(0, m.start() - 40):m.start()]):
            continue
        snippet = " ".join(t[max(0, m.start() - 30):m.end() + 30].split())
        if snippet not in hits:
            hits.append(snippet)

    return hits


def experience_evidence(text, context: int = 110) -> list:
    """Return ``[{phrase, snippet}]`` for a human-readable report."""
    out = []
    for hit in experience_hits(text):
        out.append({"phrase": hit, "snippet": hit[:context]})
    return out
