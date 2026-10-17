#!/usr/bin/env python3
"""Deterministic reader of the owner's Career Ops profile for the job search.

Why this exists
---------------
The job-search workers used to carry their own hardcoded vocabulary: query
strings in ``codex_entry_level_search.py``, entry-level markers, discipline
families. The owner's own facts already live in one place -- the Career Ops
install's ``config/profile.yml`` (``target_roles``, ``location.visa_status``,
``location.clearance_filter``) -- and ``regional_policy.json`` already copies
some of it verbatim. This module makes the profile the single readable source
for the search vocabulary, so a profile edit changes the search and there is no
second copy to drift.

Design rules
------------
* **Read, never assume.** Every value comes from ``config/profile.yml``.
  Nothing here invents an owner fact.
* **Fail closed.** A missing, empty or unparseable profile raises. The search
  must never silently fall back to a stale hardcoded list.
* **Auditable.** ``profile_digest`` returns the sha256 of the exact profile
  bytes a run used, so a run artifact can prove which profile version produced
  it.
* **Parity with the install.** ``target_role_keywords`` mirrors
  ``providers/_profile-keywords.mjs`` in the owner's install
  (``target_roles.primary`` plus ``archetypes[].name``), so the control plane
  and the install read the same profile the same way.

The profile path is resolved from ``regional_profiles.json#career_ops_root`` --
the same config the tracker writer and the regional worker already use. No new
configuration is introduced.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILES_PATH = HERE / "regional_profiles.json"

#: Level words that turn a target-role title into a searchable discipline.
#: Used only to strip the seniority word off the owner's own role names, so
#: "Cybersecurity Intern" yields the discipline "cybersecurity".
LEVEL_SUFFIXES = (
    "internship", "intern", "graduate scheme", "graduate", "junior",
    "trainee", "apprentice", "apprenticeship", "placement", "associate",
    "entry level", "entry-level", "analyst", "scheme", "officer", "engineer",
    "specialist", "assistant", "administrator", "technician",
)

#: Words that mark an entry-level role when they appear in an archetype level
#: string (e.g. "Internship; graduates eligible").
ENTRY_WORDS = (
    "intern", "internship", "graduate", "grad", "junior", "entry level",
    "entry-level", "trainee", "apprentice", "placement", "off-cycle",
    "new grad", "associate",
)


class ProfileUnavailable(RuntimeError):
    """The owner profile is missing, empty or unreadable.

    Raised instead of returning a default: a search running on an invented or
    stale vocabulary is worse than a search that reports it cannot run.
    """


# --------------------------------------------------------------------------- #
# path + load
# --------------------------------------------------------------------------- #

def profiles_config(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or PROFILES_PATH).read_text(encoding="utf-8"))


def profile_path(config: dict | None = None) -> Path:
    """The owner's ``config/profile.yml`` inside the Career Ops install."""
    cfg = config or profiles_config()
    root = cfg.get("career_ops_root")
    if not root:
        raise ProfileUnavailable("regional_profiles.json has no career_ops_root")
    return Path(root) / "config" / "profile.yml"


def profile_bytes(path: str | Path | None = None) -> bytes:
    p = Path(path) if path else profile_path()
    if not p.is_file():
        raise ProfileUnavailable(f"owner profile not found at {p}")
    data = p.read_bytes()
    if not data.strip():
        raise ProfileUnavailable(f"owner profile is empty at {p}")
    return data


def profile_digest(path: str | Path | None = None) -> str:
    """sha256 of the exact profile bytes a run read. Audit provenance."""
    return hashlib.sha256(profile_bytes(path)).hexdigest()


def load_profile(path: str | Path | None = None) -> dict:
    """Parse the owner profile. Fails closed on missing/empty/unparseable."""
    import yaml  # local import so --help works without PyYAML

    p = Path(path) if path else profile_path()
    data = profile_bytes(p)
    try:
        parsed = yaml.safe_load(data.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is fatal here
        raise ProfileUnavailable(f"owner profile is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ProfileUnavailable(f"owner profile parsed to {type(parsed).__name__}, not a mapping")
    return parsed


# --------------------------------------------------------------------------- #
# target roles
# --------------------------------------------------------------------------- #

def _clean(items) -> list[str]:
    """Strings only, trimmed and deduped. A non-list yields nothing.

    A bare scalar is rejected rather than iterated: iterating the string
    "Cybersecurity Intern" would yield its characters, silently turning one
    role into 20 single-letter keywords.
    """
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in out:
            out.append(text)
    return out


def primary_roles(profile: dict) -> list[str]:
    """``target_roles.primary`` only -- the short, quotable role names."""
    roles = profile.get("target_roles")
    if not isinstance(roles, dict):
        return []
    return _clean(roles.get("primary"))


def target_role_keywords(profile: dict) -> list[str]:
    """The owner's target roles, in the install's own shape.

    Mirrors ``profileTargetKeywords`` in the install's
    ``providers/_profile-keywords.mjs``: ``target_roles.primary`` plus every
    ``archetypes[].name``, deduped and trimmed, strings only.
    """
    roles = profile.get("target_roles")
    if not isinstance(roles, dict):
        return []
    archetypes = roles.get("archetypes")
    names = []
    if isinstance(archetypes, list):
        for a in archetypes:
            if isinstance(a, dict):
                names.append(a.get("name"))
    # Pass the raw value through: ``_clean`` rejects a non-list, so a scalar
    # ``primary`` is dropped rather than iterated into single characters.
    return _clean(roles.get("primary")) + _clean(names)


def discipline_terms(profile: dict) -> list[str]:
    """Disciplines implied by the owner's target roles.

    "Cybersecurity Intern" -> "cybersecurity"; "IT Support Intern" -> "it
    support". Derived, not invented: the words come from the owner's own role
    names with only the level word removed.
    """
    out = []
    for role in target_role_keywords(profile):
        low = role.lower().strip()
        for suffix in LEVEL_SUFFIXES:
            if low.endswith(" " + suffix):
                low = low[: -(len(suffix) + 1)].strip()
                break
            if low == suffix:
                low = ""
                break
        low = re.sub(r"\s+", " ", low).strip(" -/,")
        if low and low not in out:
            out.append(low)
    return out


def entry_level_terms(profile: dict) -> list[str]:
    """Entry-level vocabulary the profile itself states.

    Read from the owner's target roles and the ``archetypes[].level`` strings
    ("Internship; graduates eligible"), so the search's entry-level test uses
    the owner's own words rather than a separate hardcoded list.
    """
    out = []
    blob_parts = list(target_role_keywords(profile))
    archetypes = (profile.get("target_roles") or {}).get("archetypes")
    if isinstance(archetypes, list):
        for a in archetypes:
            if isinstance(a, dict) and a.get("level"):
                blob_parts.append(str(a["level"]))
    blob = " ".join(blob_parts).lower()
    for word in ENTRY_WORDS:
        if word in blob and word not in out:
            out.append(word)
    return out


# --------------------------------------------------------------------------- #
# eligibility facts
# --------------------------------------------------------------------------- #

def location_facts(profile: dict) -> dict:
    loc = profile.get("location")
    if not isinstance(loc, dict):
        return {}
    return {
        "country": loc.get("country"),
        "city": loc.get("city"),
        "target_market": loc.get("target_market"),
        "relocation_targets": _clean(loc.get("relocation_targets")),
        "visa_status": loc.get("visa_status"),
        "authorized_in": _clean(loc.get("authorized_in")),
        "needs_sponsorship": loc.get("needs_sponsorship"),
        "onsite_availability": loc.get("onsite_availability"),
        "clearance_filter": loc.get("clearance_filter"),
    }


def clearance_text(profile: dict) -> str:
    """The owner's clearance/citizenship exclusion, verbatim from the profile."""
    return str(location_facts(profile).get("clearance_filter") or "")


#: The clearance acronyms the owner's sentence is known to name. Read as a
#: fixed vocabulary so "UK" inside "long-UK-residency" is not mistaken for a
#: clearance token. A token the profile names but this list does not is still
#: caught by the phrase pass below, and the matcher itself lives in
#: ``regional_job_search.clearance_hits``.
CLEARANCE_ACRONYMS = ("SC", "DV", "CTC", "NPPV", "UKSV", "BPSS")

#: Named phrases the owner may write out in full, with the profile's own
#: hyphenated spelling normalised to spaces for comparison.
CLEARANCE_PHRASES = (
    "security clearance",
    "national security clearance",
    "police clearance",
    "british citizenship",
    "long uk residency",
    "indefinite right to work",
    "indefinite leave to remain",
)


def clearance_terms(profile: dict) -> list[str]:
    """Clearance/citizenship terms named in the owner's clearance_filter.

    Extracted from the owner's own sentence; nothing is added. The regex in
    ``regional_job_search.clearance_hits`` stays the single matcher -- this is
    for provenance and for the drift test against ``regional_policy.json``.
    """
    text = clearance_text(profile)
    if not text:
        return []
    normalised = text.lower().replace("-", " ")
    out = []
    for token in CLEARANCE_ACRONYMS:
        if re.search(r"\b" + token.lower() + r"\b", normalised):
            out.append(token)
    for phrase in CLEARANCE_PHRASES:
        if phrase in normalised and phrase not in out:
            out.append(phrase)
    return out


def work_authorisation(profile: dict) -> dict:
    """Current work permission as the profile states it. Never upgraded."""
    loc = location_facts(profile)
    return {
        "status": "authorised" if loc.get("authorized_in") else "UNKNOWN",
        "authorized_in": loc.get("authorized_in") or [],
        "visa_status": loc.get("visa_status"),
        "needs_sponsorship_now": loc.get("needs_sponsorship"),
        "basis": "config/profile.yml#location",
    }


# --------------------------------------------------------------------------- #
# search queries
# --------------------------------------------------------------------------- #

#: Words kept short on purpose: a measured pass on 2026-09-24 showed the native
#: search tool returns zero results for very long compound queries, while a
#: short shape returns live results on every ATS surface.
def search_queries(profile: dict, region_label: str, *, year: int | None = None,
                   limit: int = 14) -> list[str]:
    """Deterministic search queries built from the owner's target roles.

    One query per primary target role, then one per derived discipline paired
    with the owner's own entry-level word. The long archetype names are used
    for the *keyword* fallback (as the install does) but not as quoted search
    strings, because a 5-word quoted phrase returns nothing from the search
    tool. Bounded by ``limit`` so a long target list cannot produce an
    unbounded query set.
    """
    if year is None:
        import datetime as _dt
        year = _dt.date.today().year
    queries: list[str] = []
    for role in primary_roles(profile):
        q = f'"{role}" {region_label} {year}'
        if q not in queries:
            queries.append(q)
    entry = entry_level_terms(profile) or ["internship"]
    level = entry[0]
    for disc in discipline_terms(profile):
        q = f"{disc} {level} {region_label} {year}"
        if q not in queries:
            queries.append(q)
    return queries[:limit]


# --------------------------------------------------------------------------- #
# snapshot
# --------------------------------------------------------------------------- #

def snapshot(path: str | Path | None = None) -> dict:
    """The resolved profile-driven search block, with provenance."""
    p = Path(path) if path else profile_path()
    profile = load_profile(p)
    return {
        "profile_path": str(p),
        "profile_sha256": profile_digest(p),
        "candidate_name": (profile.get("candidate") or {}).get("full_name"),
        "target_roles": target_role_keywords(profile),
        "disciplines": discipline_terms(profile),
        "entry_level_terms": entry_level_terms(profile),
        "clearance_text": clearance_text(profile),
        "clearance_terms": clearance_terms(profile),
        "work_authorisation": work_authorisation(profile),
        "location": location_facts(profile),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", help="override the profile path")
    ap.add_argument("--queries", action="store_true",
                    help="also print the generated UK search queries")
    args = ap.parse_args()
    try:
        snap = snapshot(args.profile)
    except ProfileUnavailable as exc:
        print(f"owner profile unavailable: {exc}")
        return 2
    if args.queries:
        snap["uk_queries"] = search_queries(load_profile(args.profile), "UK")
    print(json.dumps(snap, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
