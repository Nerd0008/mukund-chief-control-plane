#!/usr/bin/env python3
"""Owner-company PRIORITY WATCHLIST layer (roster B27).

Why this exists
---------------
Everything built so far discovers jobs by *market*: regional scans, Company
Watch's historical registry, the open-web research lane's generated query matrix.
What is still missing is the owner's own short list — "these companies matter to
me" — becoming a first-class discovery source. This module is that layer, and its
whole purpose is that **dropping in a plain list of company names is a DATA step,
not an engineering project**:

    runtime/career-ops/watchlist/company-watchlist.json      <- owner-edited
    career-ops/watchlist/company-watchlist.example.json      <- committed template

An empty list is valid: the infrastructure (identity, careers/ATS resolution, both
query families, the funnel route, the per-company health record and the brief
section) is finished and exercised with zero companies. With a list present, each
name immediately becomes:

  1. a deterministic **company identity** (aliases collapse; distinct companies
     never merge — see :func:`build_identity`);
  2. a resolved **official careers page / ATS surface**, structured where a public
     unauthenticated JSON contract exists, otherwise discovered via the research
     lane — never guessed, never invented;
  3. **two complementary query families** per company: *official-careers/ATS
     discovery* and *company-name + early-career cyber role-family research*;
  4. a `priority_watchlist` provenance flag on every finding, which makes the
     finding prominent in the Chief/Career brief **without** bypassing the
     semantic stage or the deterministic eligibility gates;
  5. a **per-company health record**: last checked, careers source found/not
     found, queries executed, live vacancies observed, candidates after the
     funnel, the access/blocking reason, and the next retry.

Additive, never a replacement
-----------------------------
The watchlist does not narrow the market search and does not get its own
classifier, eligibility engine, dedupe engine or tracker. It builds queries in
the RESEARCH LANE's own query-entry shape, executes them with the research lane's
own providers, and its findings are collected by
:func:`discovery.pipeline.collect_from_priority_watchlist` into the ONE unified
funnel. Broad-market discovery continues unchanged alongside it.

Fail-closed truth rules
-----------------------
* No careers URL is ever fabricated. A surface is recorded as found only when it
  was actually fetched/validated (owner-supplied URL) or actually resolved
  against a public structured ATS endpoint with the company name confirmed.
* A company whose careers infrastructure cannot be reached or attributed is
  labelled ``unavailable``/``unknown`` with the blocking reason — **never**
  "no jobs".
* A slug guess is not attribution. A board that cannot be attributed to the
  company is reported as requiring manual attribution and excluded from handoff.
* No login, account, session, cookie, CAPTCHA, browser/GUI or stealth scraping.
  No application, no employer/recruiter contact, no account mutation, and no
  canonical tracker write anywhere in this path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # career-ops/discovery
CAREER_OPS = HERE.parent                               # career-ops
CONTROL_PLANE = CAREER_OPS.parent
COMPANY_WATCH_DIR = CONTROL_PLANE / "company-watch"
for _p in (str(HERE), str(CAREER_OPS), str(COMPANY_WATCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regional_job_search as rjs  # noqa: E402
import web_research as wr  # noqa: E402
import ats_endpoints as atse  # noqa: E402
import company_registry as creg  # noqa: E402

SCHEMA_VERSION = 1
LANE_KIND = "career-ops.priority-watchlist-lane"

#: The owner-edited input (git-ignored: it names the owner's target companies).
DEFAULT_INPUT = CONTROL_PLANE / "runtime" / "career-ops" / "watchlist" / "company-watchlist.json"
#: The committed template (safe to commit: it holds no company names).
EXAMPLE_INPUT = CAREER_OPS / "watchlist" / "company-watchlist.example.json"
DEFAULT_OUT_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "watchlist"

#: Retry back-off by resolution state (hours). A resolved company is re-checked
#: less often than one whose careers infrastructure was unreachable, because the
#: second case is the one that may change.
RETRY_HOURS = {"found": 24, "unavailable": 6, "unknown": 6}

#: Bounded default role families used for the per-family company research query.
#: Deliberately early-career + cyber-core: graduate/junior intake, analyst, SOC,
#: information security and GRC. The full family list stays available via the
#: watchlist file's own ``role_families`` field.
DEFAULT_COMPANY_ROLE_FAMILIES = (
    "graduate_new_grad", "analyst", "soc_security_operations",
    "information_security", "grc",
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _iso(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def emit(obj) -> None:
    rjs.emit(obj)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# 1. the owner-editable input format
# --------------------------------------------------------------------------- #

INPUT_KIND = "career-ops.company-watchlist"

#: The row schema, published in `policy`/`template` output so the owner can see
#: exactly what may be supplied without reading this module.
ROW_SCHEMA = {
    "company": "required — the company name as the owner writes it",
    "careers_url": "optional — the official careers/ATS URL, when the owner knows it",
    "aliases": "optional — other spellings/legal names that ARE the same company",
    "notes": "optional — free text; recorded as provenance, never parsed for facts",
    "regions": "optional — region codes this company matters in (default: the run's region)",
    "role_families": "optional — override the role families researched for this company",
}

_ACCEPTED_SHAPES = (
    "a list of company names: [\"Acme Ltd\", \"Beta Security\"]",
    "a list of row objects: [{\"company\": \"Acme Ltd\", \"careers_url\": \"https://…\"}]",
    "an object with a `companies` (or `watchlist`) list",
    "an empty list, an empty `companies` list, or no file at all (explicitly valid)",
)


def load_watchlist_input(path: Path | None = None) -> dict:
    """Parse the owner's watchlist file. Missing/empty/no-companies is VALID.

    Nothing is inferred: a row without a ``company`` is reported as malformed
    rather than being skipped silently, and an unrecognised document shape is
    reported as a limitation rather than being guessed at.
    """
    path = Path(path) if path else DEFAULT_INPUT
    out = {
        "path": str(path), "present": path.exists(), "readable": False,
        "doc_kind": None, "regions": [], "role_families": None,
        "companies": [], "empty": True, "malformed_rows": [], "limitation": None,
    }
    if not path.exists():
        out["readable"] = False
        out["limitation"] = ("no watchlist file at this path — this is valid: the lane runs "
                            "with zero watchlist companies until the owner supplies the list")
        return out
    try:
        doc = read_json(path)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        out["limitation"] = f"watchlist file could not be read: {type(exc).__name__}: {exc}"
        return out
    out["readable"] = True

    if isinstance(doc, dict):
        out["doc_kind"] = doc.get("kind")
        rows = doc.get("companies")
        if rows is None:
            rows = doc.get("watchlist")
        if rows is None:
            out["limitation"] = ("watchlist file is an object without a `companies` (or "
                                 "`watchlist`) list — no company was read")
            rows = []
        regions = doc.get("regions")
        if isinstance(regions, list):
            out["regions"] = [str(r).strip() for r in regions if str(r or "").strip()]
        families = doc.get("role_families")
        if isinstance(families, list) and families:
            out["role_families"] = [str(f).strip() for f in families if str(f or "").strip()]
    elif isinstance(doc, list):
        out["doc_kind"] = "plain list"
        rows = doc
    else:
        out["limitation"] = (f"watchlist file shape {type(doc).__name__} is not one of the "
                            f"accepted shapes: " + "; ".join(_ACCEPTED_SHAPES))
        rows = []

    for idx, row in enumerate(rows or []):
        if isinstance(row, str):
            name = row.strip()
            entry = {"company": name}
        elif isinstance(row, dict):
            entry = dict(row)
            name = str(row.get("company") or row.get("name") or "").strip()
            entry["company"] = name
        else:
            out["malformed_rows"].append({"index": idx, "reason":
                                          f"row is {type(row).__name__}, not a name or object"})
            continue
        if not name:
            out["malformed_rows"].append({"index": idx, "reason": "row has no company name"})
            continue
        aliases = entry.get("aliases")
        if isinstance(aliases, str):
            aliases = [aliases]
        entry["aliases"] = [str(a).strip() for a in (aliases or []) if str(a or "").strip()]
        entry["careers_url"] = (str(entry.get("careers_url")).strip()
                                if entry.get("careers_url") else None)
        entry["notes"] = (str(entry.get("notes")).strip() if entry.get("notes") else None)
        entry["regions"] = [str(r).strip() for r in (entry.get("regions") or [])
                            if str(r or "").strip()]
        entry["role_families"] = [str(f).strip() for f in (entry.get("role_families") or [])
                                  if str(f or "").strip()]
        entry["_index"] = idx
        out["companies"].append(entry)

    out["empty"] = not out["companies"]
    if out["empty"] and not out["limitation"]:
        out["limitation"] = ("the watchlist file declares zero companies — valid: the lane's "
                            "identity, resolution, query, funnel and brief paths all run with an "
                            "empty list")
    return out


# --------------------------------------------------------------------------- #
# 2. deterministic company identity (aliases collapse; distinct names don't merge)
# --------------------------------------------------------------------------- #

#: Legal-form tokens only. Trading-name words ("group", "holdings", "technologies",
#: "solutions") are deliberately NOT stripped: two differently-named legal entities
#: could legitimately be "X Group" and "X Technologies", and merging them would be
#: inventing a company relationship the owner never declared.
LEGAL_FORM_TOKENS = frozenset({
    "limited", "ltd", "plc", "llp", "inc", "incorporated", "corp", "corporation",
    "gmbh", "ag", "bv", "nv", "sas", "sarl", "spa", "srl", "pty", "pte", "oy",
    "aps", "kk", "co",
})

#: A stem shorter than this is too weak to merge on (so "AB Ltd" and "AB Group"
#: stay distinct, and a short acronym never becomes a merge key).
MIN_STEM_CHARS = 4


def identity_tokens(value: str) -> list[str]:
    """Tokens of a company name: casefolded, punctuation dropped, ``&`` → ``and``."""
    text = str(value or "").casefold().replace("&", " and ")
    return [t for t in re.split(r"[^0-9a-z]+", text) if t]


def normalise_company_name(value: str) -> str:
    """Casefolded alphanumeric-only form (punctuation and spacing absorbed)."""
    return "".join(identity_tokens(value))


def identity_stem(value: str) -> str:
    """Legal-form-stripped identity key, or ``""`` when the name is unusable.

    Trailing legal-form *tokens* are removed one at a time, and only while at
    least :data:`MIN_STEM_CHARS` characters remain, so ``"Acme Security Ltd"`` and
    ``"ACME Security Limited"`` collapse while ``"BT Group"`` and ``"BT plc"``
    (stem shorter than the minimum) do not.
    """
    tokens = identity_tokens(value)
    while tokens and tokens[-1] in LEGAL_FORM_TOKENS:
        candidate = tokens[:-1]
        if len("".join(candidate)) < MIN_STEM_CHARS:
            break
        tokens = candidate
    stem = "".join(tokens)
    return stem if len(stem) >= MIN_STEM_CHARS else ""


def company_variants(name: str, aliases: list | None = None) -> list[str]:
    """Discriminating name forms used for ATS attribution and page confirmation.

    Includes the normalised full name, the legal-form-stripped stem and every
    declared alias, so a vendor payload saying "Acme Security" attributes to a
    watchlist entry written as "Acme Security Ltd".
    """
    out: list[str] = []
    for candidate in [name, *(aliases or [])]:
        for form in (normalise_company_name(candidate), identity_stem(candidate)):
            if form and form not in out:
                out.append(form)
    return out


class _Union:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> bool:
        a, b = self.find(i), self.find(j)
        if a == b:
            return False
        self.parent[max(a, b)] = min(a, b)
        return True


def _display_name_key(name: str) -> tuple:
    """Deterministic 'most canonical spelling' ranking for a merged company.

    Prefers the spelling with the most words (a legal form such as "Ltd" counts),
    then the longest, then the most title-cased words, then a name that is not ALL
    CAPS, then lexicographic order — so a merged company is always reported under a
    readable spelling and the choice never depends on input order.
    """
    tokens = [t for t in re.split(r"\s+", str(name or "").strip()) if t]
    initial_caps = sum(1 for t in tokens if t[:1].isupper() and t[1:].islower())
    all_caps = bool(name) and name.isupper()
    return (len(tokens), len(str(name or "")), initial_caps, -int(all_caps), str(name or ""))


def build_identity(rows: list, *, generated_at: str | None = None) -> dict:
    """Cluster watchlist rows into companies, collapsing duplicate spellings only.

    Three and only three merge rules fire, each recorded as its own ``basis``:

    ``exact_normalised_name``  the two names are identical once casefolded and
                               stripped of punctuation/spacing
                               (``"Sainsbury's"`` = ``"Sainsburys"``);
    ``legal_form_suffix``      the two names share a legal-form-stripped stem of
                               at least :data:`MIN_STEM_CHARS`
                               (``"Acme Ltd"`` = ``"Acme Limited"``);
    ``declared_alias``         one row's own ``aliases`` entry names the other
                               (an owner declaration, not an inference).

    Anything else stays a distinct company: this function never merges on a
    prefix, a shared word, or a similarity score, because merging two distinct
    companies would attribute one company's vacancies to another.
    """
    rows = list(rows or [])
    union = _Union(len(rows))
    merges: list[dict] = []

    def try_merge(i: int, j: int, basis: str, detail: str) -> None:
        if i == j:
            return
        if union.union(i, j):
            merges.append({"basis": basis, "detail": detail,
                           "companies": [rows[i]["company"], rows[j]["company"]]})

    def alias_forms(row: dict) -> set:
        forms = set()
        for alias in row.get("aliases") or []:
            forms.add(normalise_company_name(alias))
            forms.add(identity_stem(alias))
        forms.discard("")
        return forms

    for i, a in enumerate(rows):
        for j in range(i + 1, len(rows)):
            b = rows[j]
            na, nb = normalise_company_name(a["company"]), normalise_company_name(b["company"])
            if na and na == nb:
                try_merge(i, j, "exact_normalised_name",
                          f"'{a['company']}' and '{b['company']}' normalise identically")
                continue
            sa, sb = identity_stem(a["company"]), identity_stem(b["company"])
            if sa and sb and sa == sb:
                try_merge(i, j, "legal_form_suffix",
                          f"'{a['company']}' and '{b['company']}' share stem '{sa}' after "
                          f"removing a legal-form token")
                continue
            if nb and nb in alias_forms(a):
                try_merge(i, j, "declared_alias",
                          f"'{a['company']}' declares an alias equivalent to '{b['company']}'")
                continue
            if na and na in alias_forms(b):
                try_merge(i, j, "declared_alias",
                          f"'{b['company']}' declares an alias equivalent to '{a['company']}'")

    groups: dict[int, list] = {}
    for i in range(len(rows)):
        groups.setdefault(union.find(i), []).append(i)

    companies = []
    for root in sorted(groups, key=lambda r: min(groups[r])):
        members = [rows[i] for i in groups[root]]
        display = max(members, key=lambda m: _display_name_key(m["company"]))["company"]
        aliases: list[str] = []
        for m in members:
            for form in [m["company"], *(m.get("aliases") or [])]:
                if str(form or "").strip() and form != display and form not in aliases:
                    aliases.append(form)
        careers_urls = [m.get("careers_url") for m in members if m.get("careers_url")]
        notes = [m.get("notes") for m in members if m.get("notes")]
        families: list[str] = []
        for m in members:
            for f in m.get("role_families") or []:
                if f not in families:
                    families.append(f)
        companies.append({
            "company": display,
            "identity_key": identity_stem(display) or normalise_company_name(display),
            "normalised_name": normalise_company_name(display),
            "aliases": aliases,
            "name_variants": company_variants(display, aliases),
            "ats_slug_candidates": _slug_candidates(display, aliases),
            "careers_url": careers_urls[0] if careers_urls else None,
            "careers_url_source": "owner_supplied" if careers_urls else None,
            "notes": notes[0] if notes else None,
            "role_families": families,
            "member_rows": [{"company": m["company"], "input_index": m.get("_index"),
                             "careers_url": m.get("careers_url"), "aliases": m.get("aliases"),
                             "notes": m.get("notes")} for m in members],
            "merged_from": [m["company"] for m in members if m["company"] != display],
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or now_utc(),
        "input_rows": len(rows),
        "canonical_companies": len(companies),
        "duplicate_spellings_collapsed": len(rows) - len(companies),
        "merges": merges,
        "merge_rules": [
            "exact_normalised_name — identical after casefold + punctuation removal",
            f"legal_form_suffix — identical stem (>= {MIN_STEM_CHARS} chars) after removing a "
            "trailing legal-form token (limited/ltd/plc/inc/gmbh/…)",
            "declared_alias — one row's own `aliases` entry names the other",
        ],
        "non_merge_note": ("nothing else merges: no prefix, shared-word or similarity rule exists, "
                           "because merging two distinct companies would attribute one company's "
                           "vacancies to another"),
        "companies": companies,
    }


def _slug_candidates(name: str, aliases: list | None = None) -> list[str]:
    """Deterministic ATS-slug guesses from the name and its aliases.

    Reuses Company Watch's own slug derivation (``company_registry.slug_candidates``)
    so the watchlist lane probes exactly the same board addresses Company Watch
    would, and a slug is still only a *guess*: attribution must be confirmed by
    the vendor payload or the board page before a board is trusted.
    """
    out: list[str] = []
    for candidate in [name, *(aliases or [])]:
        for slug in creg.slug_candidates(candidate):
            if slug and slug not in out:
                out.append(slug)
    return out[:4]


# --------------------------------------------------------------------------- #
# 3. careers / ATS surface families
# --------------------------------------------------------------------------- #

#: Declared ATS/careers families. ``probe`` states how the family may legitimately
#: be resolved in this lane:
#:
#: ``structured``            a public, unauthenticated JSON contract exists and is
#:                           probed by Company Watch's own endpoint code
#:                           (`company-watch/ats_endpoints.py`); attribution must be
#:                           confirmed before the board is trusted
#: ``discovered_url_only``   there is no unauthenticated JSON contract implemented
#:                           here, so the family is only resolved when the open-web
#:                           research lane actually discovers a URL on that host —
#:                           which is exactly why the lane runs a careers/ATS
#:                           discovery query family rather than one board guess
#:
#: ``host_labels`` are matched against whole DNS labels of the result host, not as
#: substrings: ``"lever"`` matches ``jobs.lever.co`` but never ``clever.com``. The
#: ``site_query`` clauses are the real search shapes and are separate from
#: classification, so a family can be searched on its real host and still be
#: recognised on the reserved-TLD hosts the test fixtures use.
ATS_FAMILIES: dict[str, dict] = {
    "greenhouse": {"host_labels": ("greenhouse",), "probe": "structured",
                   "site_query": "site:job-boards.greenhouse.io", "tenant_from_url": False,
                   "note": "public board JSON (boards-api.greenhouse.io)"},
    "lever": {"host_labels": ("lever",), "probe": "structured",
              "site_query": "site:jobs.lever.co", "tenant_from_url": False,
              "note": "public postings JSON (api.lever.co)"},
    "ashby": {"host_labels": ("ashbyhq", "ashby"), "probe": "structured",
              "site_query": "site:jobs.ashbyhq.com", "tenant_from_url": False,
              "note": "public posting-api job board JSON"},
    "workable": {"host_labels": ("workable",), "probe": "structured",
                 "site_query": "site:apply.workable.com", "tenant_from_url": False,
                 "note": "public widget account JSON"},
    "smartrecruiters": {"host_labels": ("smartrecruiters",), "probe": "structured",
                        "site_query": "site:jobs.smartrecruiters.com", "tenant_from_url": False,
                        "note": "public postings API"},
    "workday": {"host_labels": ("myworkdayjobs", "workday"),
                "probe": "discovered_url_only", "site_query": "site:myworkdayjobs.com",
                "tenant_from_url": True,
                "note": ("tenant + site are in the URL (<tenant>.wdN.myworkdayjobs.com/<site>), so "
                         "the board only exists once a URL has been discovered — no tenant is "
                         "guessed")},
    "teamtailor": {"host_labels": ("teamtailor",), "probe": "discovered_url_only",
                   "site_query": "site:teamtailor.com/jobs", "tenant_from_url": False,
                   "region_hint": "Nordics/Europe",
                   "note": "resolved when the research lane discovers the board URL"},
    "icims": {"host_labels": ("icims",), "probe": "discovered_url_only",
              "site_query": "site:icims.com/jobs", "tenant_from_url": False,
              "region_hint": "US/global enterprise",
              "note": "resolved when the research lane discovers the board URL"},
    "bamboohr": {"host_labels": ("bamboohr",), "probe": "discovered_url_only",
                 "site_query": "site:bamboohr.com/careers", "tenant_from_url": False,
                 "note": "resolved when the research lane discovers the board URL"},
    "breezy": {"host_labels": ("breezy",), "probe": "discovered_url_only",
               "site_query": "site:breezy.hr", "tenant_from_url": False,
               "note": "resolved when the research lane discovers the board URL"},
    "jobvite": {"host_labels": ("jobvite",), "probe": "discovered_url_only",
                "site_query": "site:jobs.jobvite.com", "tenant_from_url": False,
                "note": "resolved when the research lane discovers the board URL"},
    "recruitee": {"host_labels": ("recruitee",), "probe": "discovered_url_only",
                  "site_query": "site:recruitee.com", "tenant_from_url": False,
                  "region_hint": "Europe",
                  "note": "resolved when the research lane discovers the board URL"},
    "jobcan_hrmos": {"host_labels": ("jobcan", "hrmos"), "probe": "discovered_url_only",
                     "site_query": "site:hrmos.co", "tenant_from_url": False,
                     "region_hint": "Japan",
                     "note": "region-specific Japanese ATS surface (HRMOS/Jobcan)"},
}

#: The families the structured probe may draw on. Kept identical to the vendors
#: Company Watch implements, so there is one endpoint implementation, not two.
STRUCTURED_VENDORS = tuple(atse.VENDOR_ORDER)


def classify_ats_host(url: str | None) -> dict:
    """Which declared ATS family a URL belongs to, and whether it can be probed.

    Matching is on whole DNS labels (``acme.wd1.myworkdayjobs.com`` → ``workday``),
    never a substring, so an unrelated host that merely contains a family's name
    cannot be mistaken for that family's board. Returns ``{"family": … | None,
    "probe": … | None, "tenant": … | None, "host": …}``; a host matching no declared
    family is reported as ``None`` (an employer's own careers site is not an ATS
    family — see :func:`describe_careers_surface`).
    """
    out: dict[str, object] = {"family": None, "probe": None, "tenant": None, "host": None}
    try:
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").casefold()
    except Exception:  # noqa: BLE001 - an unparseable URL simply has no family
        return out
    if not host:
        return out
    out["host"] = host
    labels = {l for l in host.split(".") if l}
    for family, spec in ATS_FAMILIES.items():
        if labels & set(spec["host_labels"]):
            out["family"] = family
            out["probe"] = spec["probe"]
            if spec.get("tenant_from_url"):
                out["tenant"] = _workday_tenant(host)
            return out
    return out


def _workday_tenant(host: str) -> str | None:
    """``acme.wd1.myworkdayjobs.com`` → ``acme``. Never guessed from a name."""
    labels = [l for l in (host or "").split(".") if l]
    if labels and labels[0] not in ("www", "myworkdayjobs", "workday"):
        return labels[0]
    return None


def describe_careers_surface(url: str | None) -> dict:
    """Human-readable description of a careers URL's family."""
    info = classify_ats_host(url)
    if info["family"]:
        spec = ATS_FAMILIES[info["family"]]
        return {**info, "kind": "ats_board", "description":
                f"{info['family']} ATS board" + (f" (tenant '{info['tenant']}')"
                                                 if info["tenant"] else ""),
                "family_note": spec.get("note"),
                "region_hint": spec.get("region_hint")}
    if info["host"]:
        return {**info, "kind": "employer_careers_site",
                "description": f"employer careers page on {info['host']}"}
    return {**info, "kind": "unknown", "description": None}


# --------------------------------------------------------------------------- #
# 4. careers / ATS resolution for one company
# --------------------------------------------------------------------------- #

#: A company's careers resolution states. Deliberately never "no jobs": an
#: unreachable or unattributable careers surface is *unknown*, not an empty market.
STATE_FOUND = "found"
STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"


def name_confirmed_in_text(text: str, variants: list, name: str | None = None) -> bool:
    """Company-name confirmation on a fetched page or result title.

    Two rules, in order, and confirmation is deliberately conservative:

    1. Company Watch's own rule (`ats_endpoints.page_confirms_name`): a company
       variant of at least 5 normalised characters appears as a standalone token.
       That covers one-word companies and slug forms, and is reused rather than
       reimplemented — there is one confirmation rule in this repo, not two.
    2. an **ordered token sequence** match on the full company name when the name has
       at least two words: a multi-word page snippet such as "SOC Analyst L1 @ Fixture
       Security Ltd" confirms ``Fixture Security Ltd`` even though the page spells the
       name with spaces rather than as the slug form. Two tokens and five characters
       are the minimum, so a short acronym cannot be "confirmed" by coincidence.
    """
    if atse.page_confirms_name(text, variants):
        return True
    if not name or not text:
        return False
    wanted = _name_tokens(name)
    if len(wanted) < 2 or sum(len(t) for t in wanted) < 5:
        return False
    have = _name_tokens(text)
    for start in range(len(have) - len(wanted) + 1):
        if have[start:start + len(wanted)] == wanted:
            return True
    return False


def _name_tokens(text: str) -> list:
    """Lower-case alphanumeric tokens of a string (punctuation and case dropped)."""
    return re.findall(r"[0-9a-z]+", str(text or "").casefold())


def resolve_careers_surface(company: dict, *, fetcher=None, page_validator=None,
                            now: dt.datetime | None = None,
                            vendors: tuple = STRUCTURED_VENDORS) -> dict:
    """Resolve ONE company's official careers page / ATS surface.

    Order of evidence:

    1. an **owner-supplied careers URL** is validated by a polite,
       robots-respecting read-only retrieval, and its ATS family is classified
       from the URL host;
    2. otherwise the **public structured ATS endpoints** are probed with the
       company's deterministic slug guesses, exactly as Company Watch does, and a
       board is trusted only when the vendor payload or the board page names the
       company;
    3. otherwise the surface is reported ``unavailable``/``unknown`` with the
       blocking reason, and the careers/ATS *discovery query family* is what a
       research run may still resolve.

    ``page_validator`` defaults to the research lane's
    :func:`web_research.fetch_validate`; tests inject a fake so no test ever
    touches the network.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    page_validator = page_validator or wr.fetch_validate
    fetcher = fetcher if fetcher is not None else atse.Fetcher()
    variants = company.get("name_variants") or company_variants(company["company"],
                                                                company.get("aliases"))
    record = {
        "company": company["company"],
        "identity_key": company.get("identity_key"),
        "state": STATE_UNKNOWN,
        "careers_source_found": False,
        "careers_url": None,
        "careers_source": None,
        "careers_surface": None,
        "ats_family": None,
        "ats_probe_mode": None,
        "attribution_confidence": None,
        "attribution_basis": None,
        "manual_attribution_required": False,
        "careers_page_http_status": None,
        "careers_page_name_confirmed": None,
        "slug_candidates": company.get("ats_slug_candidates") or [],
        "attempts": [],
        "access_blocking_reason": None,
        "last_checked": _iso(now),
        "next_retry_at": None,
        "evidence": [],
        "note": ("a careers surface is recorded as found only when it was actually fetched or "
                 "actually resolved against a public structured endpoint — never guessed"),
    }

    # -- 1. owner-supplied careers URL ------------------------------------- #
    owner_url = company.get("careers_url")
    if owner_url:
        fetch = page_validator(owner_url)
        surface = describe_careers_surface(owner_url)
        confirmed = None
        page_title = fetch.get("page_title")
        if fetch.get("status") == wr.FETCH_VALIDATED_LIVE:
            confirmed = name_confirmed_in_text(" ".join(
                [str(page_title or ""), str(fetch.get("meta_description") or "")]), variants,
                company["company"])
        record["attempts"].append({
            "source": "owner_supplied_careers_url", "url": owner_url,
            "fetch_state": fetch.get("status"), "http_status": fetch.get("http_status"),
            "page_title": page_title, "name_confirmed": confirmed,
            "ats_family": surface.get("family"), "surface_kind": surface.get("kind"),
            "robots": fetch.get("robots"), "error": fetch.get("error"),
        })
        record["careers_page_http_status"] = fetch.get("http_status")
        record["careers_page_name_confirmed"] = confirmed
        if fetch.get("status") == wr.FETCH_VALIDATED_LIVE:
            record.update({
                "state": STATE_FOUND, "careers_source_found": True, "careers_url": owner_url,
                "careers_source": "owner_supplied_careers_url",
                "careers_surface": surface, "ats_family": surface.get("family"),
                "ats_probe_mode": ATS_FAMILIES.get(surface.get("family") or "", {}).get("probe"),
                "attribution_confidence": "high" if confirmed else "owner_declared",
                "attribution_basis": (f"owner-supplied URL validated live"
                                      + ("; page names the company" if confirmed
                                         else "; page title did not confirm the company name")),
                "evidence": [{"kind": "owner_url_validation", "url": owner_url,
                              "fetch_state": fetch.get("status"),
                              "page_title": page_title}],
            })
        else:
            record.update({
                "state": STATE_UNKNOWN,
                "access_blocking_reason": (
                    f"owner-supplied careers URL could not be validated "
                    f"(fetch_state={fetch.get('status')}"
                    + (f", HTTP {fetch.get('http_status')}" if fetch.get("http_status") else "")
                    + (f", robots: {fetch.get('robots')}" if fetch.get("robots") else "")
                    + "); careers infrastructure is UNKNOWN, not 'no jobs'"),
            })

    # -- 2. structured ATS board probe ------------------------------------- #
    if not record["careers_source_found"]:
        probe = atse.resolve_company({"name": company["company"], "name_variants": variants,
                                      "ats_slug_candidates": record["slug_candidates"]},
                                     fetcher, vendors=vendors)
        record["attempts"].append({
            "source": "structured_ats_board_probe",
            "vendors_probed": list(vendors), "probes": len(probe.get("attempts") or []),
            "resolved": probe.get("resolved"),
            "attribution_confidence": probe.get("attribution_confidence"),
            "attribution_basis": probe.get("attribution_basis"),
            "board_url": probe.get("board_url"), "jobs_listed": probe.get("jobs_listed"),
            "probe_detail": [{k: a.get(k) for k in ("vendor", "slug", "status", "jobs", "outcome",
                                                    "attribution_confidence", "error")}
                             for a in probe.get("attempts") or []],
        })
        confidence = probe.get("attribution_confidence")
        record["attribution_confidence"] = confidence
        record["attribution_basis"] = probe.get("attribution_basis")
        record["manual_attribution_required"] = bool(probe.get("manual_attribution_required"))
        if probe.get("resolved") and confidence == "high":
            vendor = probe.get("vendor")
            board_url = None
            spec = atse.VENDORS.get(vendor) or {}
            if spec.get("page_url"):
                board_url = spec["page_url"](probe.get("board_slug"))
            surface = describe_careers_surface(board_url)
            record.update({
                "state": STATE_FOUND, "careers_source_found": True, "careers_url": board_url,
                "careers_source": "structured_ats_board",
                "careers_surface": surface, "ats_family": vendor,
                "ats_probe_mode": ATS_FAMILIES.get(vendor, {}).get("probe", "structured"),
                "careers_page_http_status": probe.get("board_page_http"),
                "evidence": [{"kind": "structured_board", "vendor": vendor,
                              "board_slug": probe.get("board_slug"), "board_url": board_url,
                              "attribution_basis": probe.get("attribution_basis"),
                              "jobs_listed": probe.get("jobs_listed")}],
                "access_blocking_reason": None,
            })
        elif probe.get("resolved"):
            record["state"] = STATE_UNKNOWN
            record["access_blocking_reason"] = (
                "a candidate ATS board exists for a derived slug but the vendor payload/board "
                f"page does not name the company ({probe.get('attribution_basis')}) — manual "
                "attribution required; this is UNKNOWN, not 'no jobs'")
        else:
            record["state"] = STATE_UNAVAILABLE
            record["access_blocking_reason"] = (
                "no structured ATS board was resolved from the deterministic slug guesses "
                f"({probe.get('unresolved_reason')}) — the research lane's careers/ATS discovery "
                "query family is what may still resolve the official careers surface; this is "
                "UNAVAILABLE/UNKNOWN, not 'no jobs'")

    record["next_retry_at"] = _iso(now + dt.timedelta(hours=RETRY_HOURS[record["state"]]))
    return record


# --------------------------------------------------------------------------- #
# 5. the two complementary query families
# --------------------------------------------------------------------------- #

FAMILY_CAREERS = "official_careers_ats"
FAMILY_ROLE = "company_role_family_research"
QUERY_FAMILIES = (FAMILY_CAREERS, FAMILY_ROLE)


def _query_id(query: str, region: str, family: str, scope: str, company_key: str) -> str:
    basis = f"{region}|{family}|{scope}|{company_key}|{query}"
    return "q-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def build_company_queries(company: dict, region: str, *,
                          role_families: list | None = None) -> list:
    """The two query families for one company, in the research lane's query shape.

    ``official_careers_ats`` — find and verify the company's *own* careers page and,
    for every declared ATS family, the board that company actually uses. The owner's
    own ``site:`` ATS query shapes are reused, so the surfaces reached are the ones
    the owner's standalone workflow reached.

    ``company_role_family_research`` — company-name + early-career cyber role-family
    research, i.e. the actual vacancies rather than the board address, using the
    research lane's short measured clause shapes.

    Both families carry ``priority_watchlist: true`` and the canonical company name,
    so a finding is traceable to the owner's list and to the family that found it.
    A single ATS URL is never the whole story: the careers family and the
    role-family family are always both generated.
    """
    if region not in wr.REGION_LOCATIONS:
        raise SystemExit(f"unknown region '{region}'; known: {sorted(wr.REGION_LOCATIONS)}")
    name = company["company"]
    key = company.get("identity_key") or normalise_company_name(name)
    location_clause = "(" + " OR ".join(wr.REGION_LOCATIONS[region]) + ")"
    out: list = []

    def add(family: str, scope: str, query: str, *, role_family: str, provenance: str) -> None:
        out.append({
            "query_id": _query_id(query, region, family, scope, key),
            "query": query,
            "region": region,
            "role_family": role_family,
            "surface_scope": scope,
            "query_provenance": provenance,
            "query_family": family,
            "priority_watchlist": True,
            "watchlist_company": name,
        })

    # family 1 — official careers / ATS discovery
    add(FAMILY_CAREERS, "employer_careers",
        f'"{name}" (careers OR jobs OR vacancies)',
        role_family="watchlist_careers_discovery",
        provenance="owner priority watchlist: official-careers/ATS discovery query family")
    for family_name, spec in ATS_FAMILIES.items():
        site = spec.get("site_query")
        if not site:
            continue
        add(FAMILY_CAREERS, family_name, f'{site} "{name}"',
            role_family="watchlist_ats_discovery",
            provenance=(f"owner priority watchlist × {family_name} ATS surface "
                        f"({'structured board probe available' if spec['probe'] == 'structured' else spec['probe']})"))

    # family 2 — company-name + early-career cyber role-family research
    families = list(role_families or company.get("role_families")
                    or DEFAULT_COMPANY_ROLE_FAMILIES)
    add(FAMILY_ROLE, "employer_careers",
        f'"{name}" {wr.DISCIPLINE_CLAUSE} {wr.ENTRY_CLAUSE} {location_clause}',
        role_family="watchlist_cross_family",
        provenance=("owner priority watchlist: company-name + early-career cyber role-family "
                    "research (cross-family entry clause)"))
    for family in families:
        terms = wr.ROLE_FAMILIES.get(family)
        if not terms:
            raise SystemExit(f"unknown role family '{family}'; known: {sorted(wr.ROLE_FAMILIES)}")
        clause = "(" + " OR ".join(terms) + ")"
        add(FAMILY_ROLE, "employer_careers",
            f'"{name}" {clause} {wr.DISCIPLINE_CLAUSE} {location_clause}',
            role_family=family,
            provenance=("owner priority watchlist: company-name + role-family research "
                        f"({family})"))
    return out


def apply_query_limit(queries: list, limit: int) -> tuple[list, bool]:
    """Bound a company's query budget **without ever dropping a whole family**.

    A watchlist run is allowed to trade breadth for cost (a live research run is one
    provider round-trip per query), but it must never quietly become a single-family
    lane: the allowed scope requires both the official-careers/ATS family and the
    company + role-family family for every company. So a limit is split evenly across
    the families the plan actually uses, in declared order within each family, and any
    remaining room is topped up in declared order.

    Returns ``(queries, truncated)``.
    """
    if not limit or limit >= len(queries):
        return queries, False
    families = list(dict.fromkeys(q.get("query_family") for q in queries))
    per_family = max(1, limit // max(1, len(families)))
    kept, counts = [], {}
    for q in queries:
        fam = q.get("query_family")
        if counts.get(fam, 0) < per_family:
            counts[fam] = counts.get(fam, 0) + 1
            kept.append(q)
    if len(kept) < limit:
        for q in queries:
            if len(kept) >= limit:
                break
            if q not in kept:
                kept.append(q)
    return kept[:limit], True


# --------------------------------------------------------------------------- #
# 6. the lane run
# --------------------------------------------------------------------------- #

LANE_TELEMETRY_KEYS = (
    "companies_in_watchlist", "companies_checked", "companies_with_careers_source",
    "companies_unavailable_or_unknown", "queries_planned", "queries_executed",
    "searches_observed", "results_seen", "candidate_urls", "validated_live",
    "validation_failed", "bot_wall", "duplicates_collapsed", "search_listing_refused",
    "findings", "candidates_after_funnel", "tracker_candidates",
)


def run_lane(companies: list, *, region: str, provider, fetcher=None, page_validator=None,
             resolve_careers: bool = True, limit_queries_per_company: int = 0,
             limit_per_query: int = 5, timeout: int = 240, validate: bool = True,
             max_urls_per_company: int = 20, role_families: list | None = None,
             vendors: tuple = STRUCTURED_VENDORS, validate_fn=None) -> dict:
    """Run the watchlist lane over the canonical companies.

    One company at a time, bounded: resolve the careers/ATS surface, generate both
    query families, execute them through the research lane's own provider, and
    record a per-company health row. Nothing is written to a tracker.
    """
    started = dt.datetime.now(dt.timezone.utc)
    companies = list(companies or [])
    health: list = []
    candidates: list = []
    provider_docs: list = []

    for company in companies:
        careers = (resolve_careers_surface(company, fetcher=fetcher, page_validator=page_validator,
                                          now=started, vendors=vendors)
                   if resolve_careers else
                   {"company": company["company"], "state": STATE_UNKNOWN,
                    "careers_source_found": False, "careers_url": None,
                    "careers_source": None, "ats_family": None,
                    "careers_surface": None, "attribution_confidence": None,
                    "attribution_basis": "careers resolution disabled by the caller",
                    "manual_attribution_required": True, "careers_page_http_status": None,
                    "careers_page_name_confirmed": None,
                    "slug_candidates": company.get("ats_slug_candidates") or [],
                    "attempts": [], "evidence": [],
                    "access_blocking_reason": ("careers resolution disabled by the caller — "
                                               "status is UNKNOWN, not 'no jobs'"),
                    "last_checked": _iso(started),
                    "next_retry_at": _iso(started + dt.timedelta(hours=RETRY_HOURS[STATE_UNKNOWN]))})
        queries = build_company_queries(company, region, role_families=role_families)
        planned = len(queries)
        queries, limited = apply_query_limit(queries, limit_queries_per_company)

        research = wr.run_research(queries, provider, region=region,
                                   limit_per_query=limit_per_query, timeout=timeout,
                                   validate=validate, max_urls=max_urls_per_company,
                                   validate_fn=validate_fn)
        provider_docs.append({k: research["provider"].get(k) for k in
                              ("provider", "available", "limitation", "requests",
                               "cli_version", "resolved_executable", "captured_from",
                               "web_search_observed_queries", "queries_without_observed_search")})
        by_query_id = {q["query_id"]: q for q in queries}
        company_candidates = []
        for cand in research["candidates"]:
            entry = by_query_id.get((cand.get("web_research") or {}).get("query_id")) or {}
            cand["priority_watchlist"] = True
            cand["watchlist_company"] = company["company"]
            cand["watchlist_query_family"] = entry.get("query_family")
            cand["watchlist_role_family"] = entry.get("role_family")
            cand["watchlist_careers_source"] = careers.get("careers_source")
            cand["watchlist_ats_family"] = careers.get("ats_family")
            if isinstance(cand.get("web_research"), dict):
                cand["web_research"]["query_family"] = entry.get("query_family")
                cand["web_research"]["priority_watchlist"] = True
                cand["web_research"]["watchlist_company"] = company["company"]
            company_candidates.append(cand)
        candidates.extend(company_candidates)

        telemetry = research["telemetry"]
        live = telemetry.get("validated_live", 0)
        query_rows = [{"query_id": q.get("query_id"), "query_family": q.get("query_family"),
                       "role_family": q.get("role_family"), "surface_scope": q.get("surface_scope"),
                       "query": q.get("query")} for q in queries]
        blocking = careers.get("access_blocking_reason")
        if not blocking and telemetry.get("queries_executed", 0) and not live:
            blocking = (f"no live vacancy destination was observed for this company in this run "
                        f"(results_seen={telemetry.get('results_seen', 0)}, "
                        f"validation_failed={telemetry.get('validation_failed', 0)}, "
                        f"listing_pages_refused={telemetry.get('search_listing_refused', 0)}) — "
                        f"a zero observed by this run's own queries, not a market fact")
        if not blocking and not telemetry.get("queries_executed", 0):
            limitation = research["provider"].get("limitation") or "the provider did not run"
            blocking = "no watchlist query was executed: " + str(limitation)
        health.append({
            "company": company["company"],
            "identity_key": company.get("identity_key"),
            "aliases": company.get("aliases") or [],
            "merged_from": company.get("merged_from") or [],
            "region": region,
            "last_checked": careers.get("last_checked") or _iso(started),
            "careers_source_found": bool(careers.get("careers_source_found")),
            "careers_state": careers.get("state"),
            "careers_url": careers.get("careers_url"),
            "careers_source": careers.get("careers_source"),
            "ats_family": careers.get("ats_family"),
            "ats_probe_mode": careers.get("ats_probe_mode"),
            "attribution_confidence": careers.get("attribution_confidence"),
            "attribution_basis": careers.get("attribution_basis"),
            "manual_attribution_required": bool(careers.get("manual_attribution_required")),
            "careers_page_http_status": careers.get("careers_page_http_status"),
            "careers_page_name_confirmed": careers.get("careers_page_name_confirmed"),
            "slug_candidates": careers.get("slug_candidates"),
            "careers_attempts": careers.get("attempts"),
            "evidence": careers.get("evidence"),
            "queries_planned": planned,
            "queries_executed": telemetry.get("queries_executed", 0),
            "queries_truncated_by_limit": limited,
            "searches_observed": telemetry.get("queries_executed", 0) - \
                _provider_gap(research["provider"]),
            "queries": query_rows,
            "results_seen": telemetry.get("results_seen", 0),
            "live_vacancies_observed": live,
            "findings": len(company_candidates),
            "listings_refused": sum(
                1 for c in company_candidates
                if c.get("result_kind") == wr.RESULT_KIND_SEARCH_LISTING),
            "destinations_not_validated_live": sum(
                1 for c in company_candidates
                if c.get("fetch_state") not in (wr.FETCH_VALIDATED_LIVE, wr.FETCH_BOT_WALL)),
            "candidates_after_funnel": None,
            "tracker_candidates": None,
            "access_blocking_reason": blocking,
            "next_retry_at": careers.get("next_retry_at"),
            "retry_hours": RETRY_HOURS.get(careers.get("state") or STATE_UNKNOWN),
            "zero_attribution": telemetry.get("zero_attribution"),
            # the research lane's own counters, kept per company so the lane totals
            # are a sum of what was actually observed, never a re-derivation
            "provider_telemetry": {k: telemetry.get(k, 0) for k in
                                   ("results_seen", "candidate_urls", "validated_live",
                                    "validation_failed", "bot_wall", "duplicates_collapsed",
                                    "search_listing_refused")},
        })

    # A careers/ATS surface the research lane itself discovered is promoted here, so a
    # company whose board has no structured probe (Workday, Teamtailor, iCIMS, …) can
    # still end up with a verified official careers surface.
    apply_discovered_careers_surfaces(health, candidates, companies, started)
    lane = _assemble_lane(companies, health, candidates, region, started,
                          provider_doc=(provider_docs[0] if provider_docs else None))
    lane["telemetry"]["companies_checked"] = len(health)
    lane["telemetry"]["companies_with_careers_source"] = sum(
        1 for h in health if h["careers_source_found"])
    lane["telemetry"]["companies_unavailable_or_unknown"] = sum(
        1 for h in health if h["careers_state"] != STATE_FOUND)
    return lane


def _provider_gap(provider_doc: dict) -> int:
    """Queries the provider could not prove a live search for (anti-fabrication gap)."""
    return int(provider_doc.get("queries_without_observed_search") or 0)


def apply_discovered_careers_surfaces(health: list, candidates: list, companies: list,
                                      now: dt.datetime | None = None) -> None:
    """Promote a careers/ATS surface the RESEARCH LANE actually discovered.

    The deterministic resolution covers companies whose board can be reached through
    a public structured endpoint. For every other ATS family (Workday, Teamtailor,
    iCIMS, BambooHR, Breezy, Jobvite, Recruitee and the region-specific Japanese
    HRMOS/Jobcan surface) — and for an employer's own careers page — the only honest
    route is the careers/ATS *discovery query family*: a surface is promoted to
    "found" only when a careers-family result was validated live, was not a
    search/listing page, and the fetched page or observed result title actually names
    the company. A discovered-but-unconfirmed surface is recorded as evidence and
    left UNKNOWN, never trusted.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    variants_by_company = {c["company"]: (c.get("name_variants") or
                                          company_variants(c["company"], c.get("aliases")))
                           for c in companies}
    by_company: dict = {}
    for cand in candidates:
        if cand.get("watchlist_query_family") != FAMILY_CAREERS:
            continue
        if cand.get("fetch_state") not in (wr.FETCH_VALIDATED_LIVE, wr.FETCH_BOT_WALL):
            continue
        if cand.get("result_kind") == wr.RESULT_KIND_SEARCH_LISTING:
            continue
        by_company.setdefault(cand.get("watchlist_company"), []).append(cand)

    for h in health:
        found = by_company.get(h["company"]) or []
        entries = []
        for cand in found:
            url = cand.get("url")
            surface = describe_careers_surface(url)
            observed = (cand.get("web_research") or {}).get("observed") or {}
            blob = " ".join(str(x or "") for x in (observed.get("page_title"),
                                                   observed.get("result_title"),
                                                   cand.get("title")))
            confirmed = name_confirmed_in_text(blob, variants_by_company.get(h["company"], []),
                                               h["company"])
            entries.append({
                "url": url,
                "ats_family": surface.get("family"),
                "surface_kind": surface.get("kind"),
                "surface_description": surface.get("description"),
                "name_confirmed": confirmed,
                "attribution": ("the page/result names the company" if confirmed else
                                "the page/result does NOT confirm the company name — manual "
                                "attribution required, not trusted"),
                "discovered_via_query": (cand.get("web_research") or {}).get("search_query"),
            })
        if entries:
            h["discovered_careers_surfaces"] = entries
        confirmed_entries = [e for e in entries if e["name_confirmed"]]
        if not confirmed_entries:
            if entries and not h["careers_source_found"]:
                h["access_blocking_reason"] = (
                    "a careers-family search returned "
                    f"{entries[0]['url']} but the page did not confirm the company name — manual "
                    "attribution required; careers infrastructure stays UNKNOWN, not 'no jobs'")
            continue
        # Prefer a discovered ATS board over a generic careers page (it is the surface
        # the vacancies actually live on), then the first confirmed entry.
        pick = next((e for e in confirmed_entries if e["ats_family"]), confirmed_entries[0])
        if not h["careers_source_found"]:
            h.update({
                "careers_source_found": True,
                "careers_state": STATE_FOUND,
                "careers_url": pick["url"],
                "careers_source": "discovered_via_research_lane",
                "ats_family": pick["ats_family"],
                "ats_probe_mode": ATS_FAMILIES.get(pick["ats_family"] or "", {}).get("probe"),
                "attribution_confidence": "high",
                "attribution_basis": (f"research lane validated {pick['url']} live and the page/"
                                      f"result names the company"),
                "manual_attribution_required": False,
                "access_blocking_reason": None,
                "next_retry_at": _iso(now + dt.timedelta(hours=RETRY_HOURS[STATE_FOUND])),
                "evidence": list(h.get("evidence") or []) + [{
                    "kind": "discovered_careers_surface", "url": pick["url"],
                    "ats_family": pick["ats_family"],
                    "discovered_via_query": pick["discovered_via_query"]}],
            })


def lane_zero_attribution(health: list, candidates: list, provider_doc: dict | None) -> dict:
    """Where a lane that found nothing actually stopped (anti-fabrication).

    A watchlist run may legitimately find nothing for many reasons — the owner's list
    is empty, a company's careers infrastructure could not be reached, the provider
    could not prove it searched, or the searches simply returned no validated-live
    destination. What a zero may never be read as is "no such jobs exist", so the
    first stage that reached zero is named, per company, and the provider gap (queries
    the provider could not prove a live search for) is carried with it.
    """
    gap = _provider_gap(provider_doc or {})
    planned = sum(int(h.get("queries_planned") or 0) for h in health)
    executed = sum(int(h.get("queries_executed") or 0) for h in health)
    live = sum(int(h.get("live_vacancies_observed") or 0) for h in health)
    if candidates:
        return {"first_zero_stage": None,
                "reason": "not a zero lane: findings reached the funnel",
                "provider_gap": {"queries_without_observed_search": gap}}
    if not health:
        stage = "no_company_in_watchlist"
        reason = ("the owner's company list is empty (or was not present) — a valid state and a "
                  "statement about the owner's input, not about the market")
    elif not planned:
        stage = "no_query_planned"
        reason = "no query family produced a query for any watchlist company"
    elif not executed:
        stage = "no_query_executed"
        reason = "queries were planned but none was executed by the provider"
    elif gap >= executed:
        stage = "provider_did_not_prove_a_live_search"
        reason = (f"{gap} of {executed} executed quer(ies) had no observed live web search — the "
                  f"results cannot be attributed to a real search")
    elif not live:
        stage = "no_destination_validated_live"
        reason = ("every executed search produced no destination that could be fetched and "
                  "validated live; each company's own state and blocking reason is recorded above")
    else:
        stage = "no_finding_reached_the_funnel"
        reason = ("destinations validated live but no candidate was recorded — see the per-company "
                  "blocking reasons")
    return {
        "first_zero_stage": stage,
        "reason": reason,
        "companies_without_a_careers_source": [h.get("company") for h in health
                                                if not h.get("careers_source_found")],
        "companies_without_a_live_destination": [h.get("company") for h in health
                                                 if not h.get("live_vacancies_observed")],
        "per_company_blocking_reason": {h.get("company"): h.get("access_blocking_reason")
                                        for h in health if h.get("access_blocking_reason")},
        "provider_gap": {"queries_without_observed_search": gap,
                         "queries_executed": executed, "queries_planned": planned},
        "note": ("a zero is attributable to the owner's list, a company's own careers "
                 "infrastructure, or the run's searches — never to the market"),
    }


def _assemble_lane(companies: list, health: list, candidates: list,
                   region: str, started: dt.datetime, provider_doc: dict | None = None) -> dict:
    telemetry = {k: 0 for k in LANE_TELEMETRY_KEYS}
    telemetry["companies_in_watchlist"] = len(companies)
    telemetry["findings"] = len(candidates)
    for h in health:
        for key in ("queries_planned", "queries_executed", "searches_observed"):
            telemetry[key] = telemetry.get(key, 0) + (h.get(key) or 0)
    # the research lane's own counters, summed from the per-company observations
    for key in ("results_seen", "candidate_urls", "validated_live", "validation_failed",
                "bot_wall", "duplicates_collapsed", "search_listing_refused"):
        telemetry[key] = sum((h.get("provider_telemetry", {}) or {}).get(key, 0) for h in health)
    lane = {
        "schema_version": SCHEMA_VERSION,
        "kind": LANE_KIND,
        "generated_at": _iso(started),
        "region": region,
        "watchlist": {
            "companies_in_watchlist": len(companies),
            "duplicate_spellings_collapsed": sum(len(c.get("merged_from") or [])
                                                 for c in companies),
            "empty": not companies,
        },
        "provider": provider_doc,
        "companies": health,
        "candidates": candidates,
        "telemetry": {**telemetry,
                      "zero_attribution": lane_zero_attribution(health, candidates, provider_doc)},
        "safety": {
            "read_only": True,
            "login_or_account_used": False,
            "cookies_or_session_used": False,
            "browser_or_gui_used": False,
            "captcha_bypassed": False,
            "scraping_behind_auth": False,
            "applications_submitted": 0,
            "employer_or_recruiter_contacts": 0,
            "canonical_workbook_written": False,
            "note": ("the watchlist is an additive discovery source: it never replaces the "
                     "broad-market search and never writes a canonical tracker"),
        },
        "privacy_note": ("the watchlist names the owner's target companies and the discovered "
                         "careers URLs/vacancies are owner-private; they stay under the "
                         "git-ignored runtime path"),
    }
    lane["lane_id"] = "watchlist-" + hashlib.sha256(
        json.dumps({"region": region,
                    "companies": sorted(c["company"] for c in companies),
                    "queries": sorted({q.get("query_id") for h in health
                                       for q in h.get("queries") or []})},
                   sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return lane


def attach_funnel_results(lane: dict, funnel_doc: dict) -> dict:
    """Attach the funnel outcome to the lane, per company.

    ``candidates_after_funnel`` counts the canonical candidates that carry this
    company and passed the DETERMINISTIC eligibility gates — the watchlist flag
    never bypasses them, so this can legitimately be lower than the findings count
    (and the funnel's own counters, kept intact, say where the rest stopped).
    """
    canonical = funnel_doc.get("canonical_candidates") or []
    decisions = ((funnel_doc.get("eligibility") or {}).get("decisions") or [])
    accepted = [d for d in decisions if d.get("decision") == "accepted"]
    by_company_canonical: dict = {}
    by_company_findings: dict = {}
    for c in canonical:
        if not c.get("priority_watchlist"):
            continue
        name = c.get("watchlist_company") or (c.get("web_research") or {}).get("watchlist_company")
        by_company_canonical[name] = by_company_canonical.get(name, 0) + 1
    for c in lane.get("candidates") or []:
        name = c.get("watchlist_company")
        by_company_findings[name] = by_company_findings.get(name, 0) + 1
    accepted_by_company: dict = {}
    for d in accepted:
        name = d.get("watchlist_company")
        if name:
            accepted_by_company[name] = accepted_by_company.get(name, 0) + 1
    rejected_by_company: dict = {}
    for d in decisions:
        if d.get("decision") == "accepted" or not d.get("watchlist_company"):
            continue
        key = d["watchlist_company"]
        rejected_by_company[key] = rejected_by_company.get(key, 0) + 1

    for h in lane.get("companies") or []:
        name = h["company"]
        h["candidates_after_funnel"] = accepted_by_company.get(name, 0)
        h["canonical_candidates_in_funnel"] = by_company_canonical.get(name, 0)
        h["findings_at_or_above_canonical"] = by_company_findings.get(name, 0)
        h["candidates_rejected_by_the_funnel"] = rejected_by_company.get(name, 0)
        if h["candidates_after_funnel"] == 0 and not h.get("access_blocking_reason"):
            h["access_blocking_reason"] = (
                "no watchlist finding for this company survived the funnel's own gates — see the "
                "pipeline's by_source rejections for this source; this is not 'no jobs exist'")

    lane["telemetry"]["candidates_after_funnel"] = len(
        [d for d in accepted if d.get("watchlist_company")])
    lane["telemetry"]["tracker_candidates"] = int(
        ((funnel_doc.get("funnel") or {}).get("counts") or {}).get("tracker_candidates") or 0)
    lane["funnel"] = {
        "run_id": funnel_doc.get("run_id"),
        "region": funnel_doc.get("region"),
        "counts": (funnel_doc.get("funnel") or {}).get("counts"),
        "zero_attribution": (funnel_doc.get("funnel") or {}).get("zero_attribution"),
        "by_source": ((funnel_doc.get("funnel") or {}).get("by_source") or {}).get(
            "owner priority watchlist (company careers/ATS + role-family research)"),
        "priority_watchlist": funnel_doc.get("priority_watchlist"),
        "note": ("the funnel counters are the pipeline's own; a zero after the funnel is "
                 "attributed to the stage that produced it, never to the market"),
    }
    return lane


# --------------------------------------------------------------------------- #
# 7. documents / policy
# --------------------------------------------------------------------------- #

POLICY_KIND = "career-ops.priority-watchlist-policy"


def policy_document() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": POLICY_KIND,
        "lane": "owner-company priority watchlist",
        "purpose": ("a plain list of company names becomes a first-class discovery source; adding "
                    "the list is a data step, not an engineering project"),
        "writes": {
            "canonical_tracker": False,
            "owner_watchlist_input": "read-only",
            "manifest": "read-only",
            "note": ("this lane produces a read-only lane export and a brief section; applying "
                     "anything to a canonical tracker stays the existing writer's job"),
        },
        "input": {
            "path": str(DEFAULT_INPUT),
            "template": str(EXAMPLE_INPUT),
            "kind": INPUT_KIND,
            "row_schema": ROW_SCHEMA,
            "accepted_shapes": list(_ACCEPTED_SHAPES),
            "empty_is_valid": True,
        },
        "identity": {
            "merge_rules": ["exact_normalised_name", "legal_form_suffix", "declared_alias"],
            "min_stem_chars": MIN_STEM_CHARS,
            "legal_form_tokens": sorted(LEGAL_FORM_TOKENS),
            "note": ("no prefix/shared-word/similarity rule exists: merging two distinct companies "
                     "would attribute one company's vacancies to another"),
        },
        "ats_families": {name: {k: v for k, v in spec.items()} for name, spec in ATS_FAMILIES.items()},
        "careers_resolution_order": [
            "owner-supplied careers URL, validated with a polite robots-respecting read-only "
            "retrieval (never trusted unvalidated)",
            "public structured ATS board JSON probed with deterministic slug guesses, trusted "
            "only with name confirmation (Company Watch's own endpoint code)",
            "otherwise unavailable/unknown with the blocking reason — never 'no jobs'",
        ],
        "query_families": {
            FAMILY_CAREERS: ("the company's own careers page and the ATS board it actually uses — "
                             "one query per declared ATS family plus a general careers query"),
            FAMILY_ROLE: ("company-name + early-career cyber role-family research — the actual "
                          "vacancies, using the research lane's measured short clause shapes"),
        },
        "role_families_default": list(DEFAULT_COMPANY_ROLE_FAMILIES),
        "gates": [
            "every finding carries priority_watchlist provenance and enters the SAME unified "
            "funnel (prefilter -> semantic -> deterministic eligibility -> shared dedupe)",
            "the watchlist flag NEVER bypasses the semantic stage or the deterministic gates",
            "no careers URL or vacancy is fabricated; unreachable careers infrastructure is "
            "labelled unavailable/unknown",
            "no canonical tracker write in this lane; the handoff is a read-only manifest",
        ],
        "retry_hours": dict(RETRY_HOURS),
        "per_company_health_fields": [
            "last_checked", "careers_source_found", "careers_state", "careers_url",
            "careers_source", "ats_family", "attribution_basis", "queries_planned",
            "queries_executed", "searches_observed", "live_vacancies_observed", "findings",
            "candidates_after_funnel", "access_blocking_reason", "next_retry_at",
        ],
        "not_performed": [
            "no employer/recruiter contact, application, account or profile mutation",
            "no login, cookie/session, CAPTCHA, browser or GUI automation",
            "no canonical tracker or workbook write",
        ],
        "prohibited": [
            "employer, recruiter or agency contact of any kind",
            "submitting an application or mutating any account, profile or ATS record",
            "browser/GUI automation, signed-in sessions, cookies or CAPTCHA bypass",
            "inventing or guessing a careers URL, an ATS tenant or a vacancy",
        ],
    }


def template_document() -> dict:
    """The committed template: a valid, EMPTY watchlist plus the documented shape."""
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": INPUT_KIND,
        "_readme": ("Copy this file to runtime/career-ops/watchlist/company-watchlist.json and put "
                    "your company names in `companies`. An empty list is valid: the watchlist "
                    "layer's identity, careers/ATS resolution, query families, funnel route and "
                    "brief section all run with zero companies, so adding names later is a data "
                    "edit only."),
        "_row_schema": ROW_SCHEMA,
        "_example_row": {
            "company": "NOT A COMPANY — example shape only, not read by the loader",
            "careers_url": "https://example.invalid/careers",
            "aliases": ["Example Group Ltd", "Example Group Limited"],
            "notes": "why this company matters to me (recorded as provenance only)",
            "regions": ["uk"],
            "role_families": ["graduate_new_grad", "soc_security_operations"],
        },
        "regions": ["uk"],
        "role_families": list(DEFAULT_COMPANY_ROLE_FAMILIES),
        "companies": [],
    }


def cmd_policy(args) -> int:
    emit({"generated_at": now_utc(), **policy_document()})
    return 0


def cmd_template(args) -> int:
    doc = template_document()
    target = Path(args.out) if args.out else EXAMPLE_INPUT
    if target.exists() and not args.force:
        emit({"generated_at": now_utc(), "written": False, "path": str(target),
              "reason": "target exists; pass --force to overwrite"})
        return 1
    write_json_atomic(target, doc)
    emit({"generated_at": now_utc(), "written": True, "path": str(target),
          "companies": len(doc["companies"])})
    return 0


def cmd_identity(args) -> int:
    loaded = load_watchlist_input(Path(args.watchlist) if args.watchlist else None)
    identity = build_identity(loaded["companies"])
    emit({"generated_at": now_utc(), "watchlist": {k: v for k, v in loaded.items()
                                                   if k != "companies"},
          "input_rows": identity["input_rows"],
          "canonical_companies": identity["canonical_companies"],
          "duplicate_spellings_collapsed": identity["duplicate_spellings_collapsed"],
          "merges": identity["merges"], "merge_rules": identity["merge_rules"],
          "companies": [{k: c[k] for k in ("company", "identity_key", "aliases",
                                           "ats_slug_candidates", "merged_from",
                                           "careers_url", "notes")}
                        for c in identity["companies"]]})
    return 0


def cmd_matrix(args) -> int:
    loaded = load_watchlist_input(Path(args.watchlist) if args.watchlist else None)
    identity = build_identity(loaded["companies"])
    matrix = [q for c in identity["companies"]
              for q in build_company_queries(c, args.region,
                                             role_families=(loaded.get("role_families")
                                                            or args.role_families))]
    by_family: dict = {}
    for q in matrix:
        by_family[q["query_family"]] = by_family.get(q["query_family"], 0) + 1
    emit({"generated_at": now_utc(), "region": args.region,
          "watchlist_present": loaded["present"], "watchlist_empty": loaded["empty"],
          "canonical_companies": identity["canonical_companies"],
          "counts": {"queries": len(matrix), "by_query_family": dict(sorted(by_family.items()))},
          "matrix": matrix})
    return 0


def cmd_resolve(args) -> int:
    loaded = load_watchlist_input(Path(args.watchlist) if args.watchlist else None)
    identity = build_identity(loaded["companies"])
    companies = identity["companies"]
    if args.limit:
        companies = companies[:args.limit]
    resolutions = [resolve_careers_surface(c, fetcher=None) for c in companies]
    emit({"generated_at": now_utc(), "region": args.region,
          "companies_checked": len(resolutions),
          "companies_with_careers_source": sum(1 for r in resolutions
                                               if r["careers_source_found"]),
          "companies_unavailable_or_unknown": sum(1 for r in resolutions
                                                  if r["state"] != STATE_FOUND),
          "resolutions": resolutions,
          "safety": {"read_only": True, "canonical_workbook_written": False,
                     "browser_or_gui_used": False, "login_or_account_used": False}})
    return 0


def cmd_run(args) -> int:
    loaded = load_watchlist_input(Path(args.watchlist) if args.watchlist else None)
    identity = build_identity(loaded["companies"])
    companies = identity["companies"]
    if args.limit_companies:
        companies = companies[:args.limit_companies]
    provider = wr.make_provider(args.provider,
                               captured=Path(args.captured) if args.captured else None,
                               executable=args.executable)
    lane = run_lane(companies, region=args.region, provider=provider,
                    resolve_careers=(not args.no_resolve),
                    limit_queries_per_company=args.limit_queries_per_company,
                    limit_per_query=args.limit_per_query, timeout=args.timeout,
                    validate=(not args.no_validate),
                    max_urls_per_company=args.max_urls_per_company,
                    role_families=(loaded.get("role_families") or None),
                    validate_fn=None)
    lane["watchlist"].update({"path": loaded["path"], "present": loaded["present"],
                              "readable": loaded["readable"],
                              "malformed_rows": loaded["malformed_rows"],
                              "limitation": loaded["limitation"],
                              "identity": {"merges": identity["merges"],
                                           "duplicate_spellings_collapsed":
                                               identity["duplicate_spellings_collapsed"],
                                           "merge_rules": identity["merge_rules"]}})

    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    export_path = out_dir / f"watchlist-{args.region}-{lane['lane_id']}.json"
    latest = out_dir / f"watchlist-{args.region}-latest.json"
    lane["export_file"] = str(export_path)
    lane["latest_file"] = str(latest)

    if args.with_funnel:
        import pipeline  # noqa: PLC0415 - lazy import avoids a circular import
        funnel_path = Path(args.funnel_out) if args.funnel_out else (
            out_dir / f"funnel-{args.region}-{lane['lane_id']}.json")
        # the lane export must exist before the pipeline collector reads it
        write_json_atomic(export_path, lane)
        write_json_atomic(latest, lane)
        collection = pipeline.collect_from_priority_watchlist(export_path, args.region)
        collection["source"] = pipeline.SOURCE_PRIORITY_WATCHLIST
        run_id = (f"discovery-watchlist-{args.region}-"
                  f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        funnel_doc = pipeline.run_funnel(
            list(collection["candidates"]), region=args.region, mode="high_recall",
            semantic=args.semantic, deepseek_model=args.model, batch_size=8,
            codex_budget=args.codex_budget, codex_enabled=(args.codex != "off"),
            timeout=args.timeout, run_id=run_id, collection=[collection])
        funnel_doc["schema_version"] = pipeline.SCHEMA_VERSION
        funnel_doc["finished_at"] = now_utc()
        funnel_doc["summary_line"] = pipeline._summary_line(funnel_doc)
        write_json_atomic(funnel_path, funnel_doc)
        attach_funnel_results(lane, funnel_doc)
        lane["funnel_file"] = str(funnel_path)
        lane["collection_coverage"] = collection["coverage"]
        if args.manifest_out:
            write_json_atomic(Path(args.manifest_out), read_only_manifest(lane, funnel_doc,
                                                                         args.region))
            lane["manifest_written_to"] = str(args.manifest_out)

    write_json_atomic(export_path, lane)
    write_json_atomic(latest, lane)
    emit(lane)
    return 0


def read_only_manifest(lane: dict, funnel_doc: dict | None = None, region: str | None = None) -> dict:
    """A read-only candidate manifest. Never a tracker write.

    Only candidates that actually passed the deterministic gates are listed with
    their application URL; every watchlist finding is listed with its state so a
    refused finding is visible rather than dropped.
    """
    accepted_ids = set()
    decisions = ((funnel_doc or {}).get("eligibility") or {}).get("decisions") or []
    for d in decisions:
        if d.get("decision") == "accepted":
            accepted_ids.add(d["candidate_id"])
    records, refused = [], []
    for c in lane.get("candidates") or []:
        row = {"company": c.get("company"), "title": c.get("title"), "location": c.get("location"),
               "url": c.get("url"), "fetch_state": c.get("fetch_state"),
               "result_kind": c.get("result_kind"), "watchlist_company": c.get("watchlist_company"),
               "watchlist_query_family": c.get("watchlist_query_family"),
               "priority_watchlist": True}
        cid = None
        for d in decisions:
            if d.get("company") == c.get("company") and d.get("title") == c.get("title") \
                    and d.get("url") == c.get("url"):
                cid = d.get("candidate_id")
                row["decision"] = d.get("decision")
                row["reasons"] = d.get("reasons")
                break
        (records if (cid in accepted_ids if cid else False) else refused).append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc(),
        "kind": "career-ops.priority-watchlist-manifest",
        "region": region or lane.get("region"),
        "lane_id": lane.get("lane_id"),
        "read_only": True,
        "canonical_workbook_written": False,
        "accepted": records,
        "rejected_or_unverified": refused,
        "companies": [{k: h.get(k) for k in
                       ("company", "careers_source_found", "careers_state", "careers_url",
                        "ats_family", "live_vacancies_observed", "findings",
                        "candidates_after_funnel", "access_blocking_reason", "next_retry_at",
                        "last_checked")}
                      for h in lane.get("companies") or []],
        "note": ("applying a manifest stays an explicit, separate step; nothing here writes a "
                 "canonical tracker"),
    }


def cmd_status(args) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    latest = sorted(out_dir.glob("watchlist-*-latest.json")) if out_dir.exists() else []
    loaded = load_watchlist_input(Path(args.watchlist) if args.watchlist else None)
    emit({"generated_at": now_utc(), "out_dir": str(out_dir),
          "input_path": str(loaded["path"]), "input_present": loaded["present"],
          "input_companies": len(loaded["companies"]), "empty_is_valid": True,
          "latest_exports": [p.name for p in latest],
          "template": str(EXAMPLE_INPUT), "template_present": EXAMPLE_INPUT.exists(),
          "policy": policy_document()["gates"]})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Owner-company priority watchlist lane (additive discovery source)")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("policy")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("template")
    p.add_argument("--out")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_template)

    p = sub.add_parser("identity")
    p.add_argument("--watchlist")
    p.set_defaults(fn=cmd_identity)

    p = sub.add_parser("matrix")
    p.add_argument("--region", required=True)
    p.add_argument("--watchlist")
    p.add_argument("--role-families", nargs="*")
    p.set_defaults(fn=cmd_matrix)

    p = sub.add_parser("resolve")
    p.add_argument("--region", default="uk")
    p.add_argument("--watchlist")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_resolve)

    p = sub.add_parser("run")
    p.add_argument("--region", required=True)
    p.add_argument("--provider", choices=("codex", "captured", "none"), default="codex")
    p.add_argument("--captured")
    p.add_argument("--executable")
    p.add_argument("--watchlist")
    p.add_argument("--limit-companies", type=int, default=0)
    p.add_argument("--limit-queries-per-company", type=int, default=0)
    p.add_argument("--limit-per-query", type=int, default=5)
    p.add_argument("--max-urls-per-company", type=int, default=20)
    p.add_argument("--no-resolve", action="store_true",
                   help="skip careers/ATS resolution (status becomes UNKNOWN, never 'no jobs')")
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--timeout", type=int, default=240)
    p.add_argument("--out-dir")
    p.add_argument("--with-funnel", action="store_true")
    p.add_argument("--funnel-out")
    p.add_argument("--semantic", choices=("auto", "deepseek", "deterministic", "off"),
                   default="off")
    p.add_argument("--codex", choices=("on", "off"), default="off")
    p.add_argument("--codex-budget", type=int, default=4)
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--manifest-out")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("status")
    p.add_argument("--out-dir")
    p.add_argument("--watchlist")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
