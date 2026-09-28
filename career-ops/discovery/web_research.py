#!/usr/bin/env python3
"""Bounded, read-only open-web job research lane (roster B26).

Why this exists
---------------
The owner's successful standalone Codex workflow did not merely scan a fixed
provider list: it *actively researched the open web*. The owner's own Career Ops
install documents that in two places, inspected read-only: ``portals.yml``
declares a ``search_queries`` list of ``site:`` WebSearch queries per ATS portal,
and ``modes/scan.md`` describes the Level-3 agent workflow — for each
``search_queries`` entry with ``enabled: true``, "Execute WebSearch with the
defined ``query``", with every Level-3 hit treated as *unverified* until liveness
is confirmed and title/company extracted from the result title with a documented
regex.

This module adds exactly that behaviour back, as one more read-only discovery
surface feeding the SAME unified funnel (``discovery.pipeline``): the query
matrix is generated, a research worker runs the searches, the destinations are
optionally validated with a polite HTTP retrieval, and every finding is
normalised into the one candidate schema with full provenance. It does **not**
create a second tracker, classifier or eligibility engine.

What it is not
--------------
* No login, no account, no cookies/session, no scraping behind auth, no CAPTCHA,
  no browser and no GUI automation, no stealth/evasion. Public/search-index
  discovery only, plus robots-respecting HTTP retrieval for validation.
* No application, no employer/recruiter outreach, no posting or messaging.
* Nothing here writes a canonical workbook; the handoff is a candidate manifest.

Providers
---------
``codex-web-search``
    The research worker. Codex CLI is invoked non-interactively and asked to run
    a query with its native ``web_search`` tool. **Results are only accepted when
    the runtime proves a live search happened**: the JSONL event stream must
    contain a ``web_search`` item for that query. If the CLI/runtime cannot
    search, the provider reports that truthfully and contributes nothing — it is
    never reported as a search that did not occur.

``captured``
    Reads a previously captured search-result document (the same shape the Codex
    provider emits). This is the offline/test provider and the declared fallback
    when Codex web search is unavailable.

``none``
    No provider: zero results, with the reason recorded (a declared zero, never a
    market fact).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # career-ops/discovery
CAREER_OPS = HERE.parent                               # career-ops
CONTROL_PLANE = CAREER_OPS.parent
EXEC_BRAIN = CONTROL_PLANE / "exec-brain"
for _p in (str(HERE), str(CAREER_OPS), str(EXEC_BRAIN)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regional_job_search as rjs  # noqa: E402
import tracker_writer as tw  # noqa: E402

SCHEMA_VERSION = 1
EXPORT_KIND = "career-ops.web-research-export"
DEFAULT_OUT_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "web-research"
DEFAULT_CAPTURED = CAREER_OPS / "tests" / "fixtures" / "discovery" / "web-research" / \
    "captured-codex-search.json"
DEFAULT_WATCHLIST = CONTROL_PLANE / "runtime" / "career-ops" / "web-research" / \
    "company-watchlist.json"

#: retrieval policy for URL validation.
USER_AGENT = "MukundCareerOpsBot/1.0 (+read-only job-posting liveness check)"
MAX_BODY_BYTES = 200_000
ROBOTS_TIMEOUT = 8
FETCH_TIMEOUT = 12

#: fetch states a discovered result can carry.
FETCH_VALIDATED_LIVE = "validated_live"
FETCH_DISCOVERED_UNVERIFIED = "discovered_unverified"
FETCH_VALIDATION_FAILED = "validation_failed"
FETCH_NOT_ATTEMPTED = "not_attempted"
FETCH_STATES = (FETCH_VALIDATED_LIVE, FETCH_DISCOVERED_UNVERIFIED,
                FETCH_VALIDATION_FAILED, FETCH_NOT_ATTEMPTED)

# --------------------------------------------------------------------------- #
# surfaces — which discovery surface a result URL belongs to
# --------------------------------------------------------------------------- #

#: Ordered surface definitions. The first whose token occurs in the URL host
#: wins, so "google" results that link to an ATS are classified by the ATS host
#: they link to (the link is resolved per-result), not by the search engine.
SURFACE_DEFINITIONS = (
    ("linkedin_jobs", ("linkedin.",), "public LinkedIn Jobs result"),
    ("indeed", ("indeed.",), "public Indeed result"),
    ("greenhouse", ("greenhouse.io",), "employer Greenhouse board"),
    ("lever", ("lever.co",), "employer Lever board"),
    ("workday", ("myworkdayjobs.com", "workday.com"), "employer Workday board"),
    ("ashby", ("ashbyhq.com",), "employer Ashby board"),
    ("smartrecruiters", ("smartrecruiters.com",), "employer SmartRecruiters board"),
    ("teamtailor", ("teamtailor.com",), "employer Teamtailor board"),
    ("workable", ("workable.com",), "employer Workable board"),
    ("icims", ("icims.com",), "employer iCIMS board"),
    ("bamboohr", ("bamboohr.com",), "employer BambooHR board"),
    ("breezy", ("breezy.hr",), "employer Breezy board"),
    ("jobvite", ("jobvite.com",), "employer Jobvite board"),
    ("recruitee", ("recruitee.com",), "employer Recruitee board"),
    ("jobcan_hrmos", ("jobcan.com", "hrmos.co"), "employer HRMOS/Jobcan board"),
    ("google_index", ("google.",), "Google-indexed job page/result"),
    ("employer_careers", (), "direct employer careers page"),
)

SURFACES = tuple(name for name, _t, _d in SURFACE_DEFINITIONS)


def classify_surface(url: str | None) -> str:
    """Which discovery surface a result URL belongs to.

    Matching is on a domain token (``linkedin.``, ``greenhouse.io``, …) so the
    synthetic ``.invalid`` hosts used by the test fixtures classify identically
    to the real hostnames. A URL whose host matches nothing is an
    ``employer_careers`` page (the default the owner's own workflow used).
    """
    host = ""
    try:
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").casefold()
    except Exception:  # noqa: BLE001 - a malformed URL is simply unclassified
        host = ""
    if not host:
        return "employer_careers"
    for name, tokens, _desc in SURFACE_DEFINITIONS:
        for token in tokens:
            if token in host:
                return name
    return "employer_careers"


def surface_description(name: str) -> str | None:
    for surface, _t, desc in SURFACE_DEFINITIONS:
        if surface == name:
            return desc
    return None


# --------------------------------------------------------------------------- #
# result kind — is a discovered URL a vacancy posting or a search/listing page?
# --------------------------------------------------------------------------- #

#: A search-result *listing* page (``site:linkedin.com/jobs <keywords>`` returns
#: LinkedIn's own search page, ``uk.indeed.com/q-…`` is Indeed's results page, a
#: Google result page is a search page) is **not a vacancy**. Treating one as a
#: vacancy would invent a posting from a search snippet, so these are classified
#: explicitly and the deterministic gate refuses them tracker handoff.
RESULT_KIND_POSTING = "job_posting"
RESULT_KIND_SEARCH_LISTING = "search_listing"
RESULT_KIND_UNKNOWN = "unknown"
RESULT_KINDS = (RESULT_KIND_POSTING, RESULT_KIND_SEARCH_LISTING, RESULT_KIND_UNKNOWN)

_LISTING_QUERY_KEYS = ("keywords", "q", "searchterm", "search", "query", "keywords_input")
_POSTING_PATH_TOKENS = ("/jobs/view", "/viewjob", "/job/", "/rc/clk", "/pagead/clk",
                        "/jobs/apply", "/o/", "/j/")


def classify_result_kind(url: str | None) -> tuple:
    """``(kind, reason)`` for a discovered result URL.

    Conservative: only a clearly-shaped search/listing page is refused, and only a
    clearly-shaped posting is asserted as one. Anything else stays ``unknown`` and
    is handled by the liveness gate instead. Nothing here is inferred from a title
    or a snippet — only the URL itself.
    """
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
    except Exception:  # noqa: BLE001 - an unparseable URL is simply unknown
        return RESULT_KIND_UNKNOWN, "URL could not be parsed"
    host = (parsed.hostname or "").casefold()
    path = (parsed.path or "").casefold()
    query = (parsed.query or "").casefold()
    if not host:
        return RESULT_KIND_UNKNOWN, "no host in the result URL"
    surface = classify_surface(url)

    if surface == "linkedin_jobs":
        if path.startswith("/jobs/view") or "/jobs/view/" in path:
            return RESULT_KIND_POSTING, "LinkedIn job view path"
        if path.startswith("/jobs/search") or path.startswith("/jobs/collections"):
            return RESULT_KIND_SEARCH_LISTING, "LinkedIn job search/collection page"
        if re.match(r"^/jobs/[^/]+/?$", path):
            return RESULT_KIND_SEARCH_LISTING, "LinkedIn /jobs/<keywords> search page"
        return RESULT_KIND_UNKNOWN, "unrecognised LinkedIn path"

    if surface == "indeed":
        if path.startswith("/viewjob") or "/clk" in path:
            return RESULT_KIND_POSTING, "Indeed viewjob/click-through path"
        if path.startswith("/q-") or path.startswith("/m/jobs") or path.startswith("/jobs"):
            return RESULT_KIND_SEARCH_LISTING, "Indeed query results page"
        return RESULT_KIND_UNKNOWN, "unrecognised Indeed path"

    if surface == "google_index":
        return RESULT_KIND_SEARCH_LISTING, "Google search-result page (a search page is not a vacancy)"

    if surface != "employer_careers" and surface != "linkedin_jobs" and surface != "indeed":
        # any other classified surface is an employer ATS board: its URL is a posting
        return RESULT_KIND_POSTING, f"{surface_description(surface) or surface} posting path"

    if host == "reed.co.uk" or host.endswith(".reed.co.uk"):
        segments = [s for s in path.split("/") if s]
        if segments and segments[-1].isdigit():
            return RESULT_KIND_POSTING, "Reed posting id path"
        if re.search(r"-jobs(-in-[^/]*)?/?$", path):
            return RESULT_KIND_SEARCH_LISTING, "Reed keyword-listing page"
        return RESULT_KIND_UNKNOWN, "unrecognised Reed path"

    if path.startswith("/jobs/search") or (
            "/search" in path and any(k in query for k in _LISTING_QUERY_KEYS)):
        return RESULT_KIND_SEARCH_LISTING, "search/listing path with a query term"

    # keyword-listing slugs ("…-jobs", "…-jobs-in-<place>") used by Reed-style and
    # other keyword boards to address a search rather than a single posting
    if re.search(r"-jobs(-in-[^/]*)?/?$", path):
        return RESULT_KIND_SEARCH_LISTING, "keyword-listing slug path"

    if any(token in path for token in _POSTING_PATH_TOKENS):
        return RESULT_KIND_POSTING, "posting-shaped path"

    return RESULT_KIND_UNKNOWN, "no search/listing or posting shape detected"



# --------------------------------------------------------------------------- #
# role families and regions — the query matrix inputs
# --------------------------------------------------------------------------- #

#: Role families named in the task's allowed scope.
ROLE_FAMILIES = {
    "graduate_new_grad": ["graduate", "new grad", "new graduate", "graduate scheme"],
    "junior_associate": ["junior", "associate", "entry level"],
    "analyst": ["analyst"],
    "l1_tier1": ["L1", "\"level 1\""],
    "soc_security_operations": ["SOC", "security operations", "blue team"],
    "grc": ["GRC", "governance risk compliance"],
    "iam": ["IAM", "identity and access management"],
    "technology_risk": ["technology risk", "cyber risk", "IT risk"],
    "information_security": ["information security", "infosec", "IT security"],
    "cybersecurity": ["cybersecurity", "cyber security"],
}

#: Discipline clause reused across the family queries. Deliberately SHORT: a
#: measured live pass on 2026-09-24 showed the native search tool returns zero
#: results for a very long compound ``site:`` query (a 9-way discipline OR plus a
#: 6-way level OR plus a 3-way location OR returned ``[]``), while the owner's own
#: shorter shape (a few ORs per clause) returns live results on every ATS surface.
DISCIPLINE_CLAUSE = ('("cyber security" OR cybersecurity OR "information security" OR SOC)')

#: The owner's own query shape used "a few ORs per clause"; the entry clause keeps
#: to the three levels that actually surface early-career postings.
ENTRY_TERMS_SHORT = ("graduate", "junior", "analyst")
ENTRY_CLAUSE = "(" + " OR ".join(ENTRY_TERMS_SHORT) + ")"

#: Level terms that need their own bounded query because they are not in
#: ``ENTRY_CLAUSE``; one query per region covers graduate/new-grad/associate/L1.
LEVEL_COVERAGE_TERMS = ("new grad", "associate", "L1", "entry level")
LEVEL_COVERAGE_CLAUSE = "(" + " OR ".join(LEVEL_COVERAGE_TERMS) + ")"

#: Region location clauses. UK is the owner's authorised region; the others are
#: searched because the owner has regional trackers, with work authorisation
#: recorded as UNKNOWN by the downstream eligibility gates.
REGION_LOCATIONS = {
    "uk": ["UK", "\"United Kingdom\"", "London"],
    "dubai": ["Dubai", "UAE", "\"United Arab Emirates\""],
    "japan": ["Japan", "Tokyo"],
    "singapore": ["Singapore"],
}

#: The owner's existing ``portals.yml`` ``search_queries`` site: patterns, kept
#: so the useful query shapes are preserved rather than guessed. Each entry is
#: (surface_scope, site: clause). Documented source: the Career Ops install's
#: ``portals.yml#search_queries``.
OWNER_ATS_SITE_QUERIES = (
    ("greenhouse", "site:job-boards.greenhouse.io"),
    ("lever", "site:jobs.lever.co"),
    ("ashby", "site:jobs.ashbyhq.com"),
    ("workday", "site:myworkdayjobs.com"),
    ("workable", "site:apply.workable.com"),
    ("smartrecruiters", "site:jobs.smartrecruiters.com"),
    ("icims", "site:icims.com/jobs"),
    ("teamtailor", "site:teamtailor.com/jobs"),
)

#: Broad public search surfaces added on top of the owner's ATS site queries.
BROAD_SURFACES = (
    ("linkedin_jobs", "site:linkedin.com/jobs"),
    ("indeed", "site:uk.indeed.com OR site:indeed.com"),
    ("google_index", None),   # no site: filter — plain open-web discovery
)


def _query_id(query: str, region: str, family: str, scope: str) -> str:
    basis = f"{region}|{family}|{scope}|{query}"
    return "q-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def build_query_matrix(region: str, *, families: tuple = tuple(ROLE_FAMILIES),
                       include_watchlist: list | None = None,
                       aqs_only: bool = False) -> list:
    """Generate the query matrix for one region.

    Every entry carries its own provenance so a discovered vacancy can be traced
    back to the exact query, role family, region and surface that surfaced it.
    """
    locations = REGION_LOCATIONS.get(region)
    if not locations:
        raise SystemExit(f"unknown region '{region}'; known: {sorted(REGION_LOCATIONS)}")
    location_clause = "(" + " OR ".join(locations) + ")"
    out: list = []

    def add(family: str, scope: str, query: str, *, provenance: str) -> None:
        out.append({
            "query_id": _query_id(query, region, family, scope),
            "query": query,
            "region": region,
            "role_family": family,
            "surface_scope": scope,
            "query_provenance": provenance,
        })

    if not aqs_only:
        # 1. broad public job surfaces first (LinkedIn Jobs, Indeed, open-web index):
        #    these are the surfaces the owner's Codex workflow reached, and a bounded
        #    live pass should exercise them before the long tail of ATS queries.
        for scope, site in BROAD_SURFACES:
            prefix = f"{site} " if site else ""
            add("cross_family_entry", scope,
                f"{prefix}{ENTRY_CLAUSE} {DISCIPLINE_CLAUSE} {location_clause}",
                provenance=("broad public job-result surface added for the Codex-style "
                            "open-web research lane"))

        # 2. the owner's own ATS site queries, per ATS, in the owner's query shape
        for scope, site in OWNER_ATS_SITE_QUERIES:
            query = f"{site} {ENTRY_CLAUSE} {DISCIPLINE_CLAUSE} {location_clause}"
            add("cross_family_entry", scope, query,
                provenance="owner portals.yml search_queries (site: pattern preserved)")

        # 3. per-family open-web query (the discipline coverage)
        for family in families:
            terms = ROLE_FAMILIES.get(family)
            if not terms:
                raise SystemExit(f"unknown role family '{family}'")
            family_clause = "(" + " OR ".join(terms) + ")"
            add(family, "employer_careers",
                f"{family_clause} {DISCIPLINE_CLAUSE} {location_clause}",
                provenance="role-family matrix (allowed scope)")

        # 4. level coverage for the level terms not in the entry clause
        add("level_coverage", "employer_careers",
            f"{LEVEL_COVERAGE_CLAUSE} {DISCIPLINE_CLAUSE} {location_clause}",
            provenance="level-term coverage (new grad / associate / L1 / entry level)")

    # 4. company watchlist hooks (optional — the generic search works without it)
    for company in (include_watchlist or []):
        name = str(company or "").strip()
        if not name:
            continue
        add("watchlist", "employer_careers",
            f'"{name}" {DISCIPLINE_CLAUSE} {ENTRY_CLAUSE} {location_clause}',
            provenance="owner-provided company watchlist hook")
        for scope, site in OWNER_ATS_SITE_QUERIES:
            add("watchlist", scope, f'{site} "{name}"', provenance="owner company watchlist × ATS")
    return out


def load_watchlist(path: Path | None) -> list:
    """Owner-provided company list. Absent file -> no watchlist queries (not an error)."""
    if not path or not Path(path).exists():
        return []
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc, dict):
        rows = doc.get("companies") or doc.get("watchlist") or []
    else:
        rows = doc
    names = []
    for row in rows:
        name = row.get("company") if isinstance(row, dict) else row
        if name and str(name).strip():
            names.append(str(name).strip())
    return names


# --------------------------------------------------------------------------- #
# research providers (the worker interface)
# --------------------------------------------------------------------------- #

class ResearchProvider:
    """Provider interface: probe availability, then research queries."""

    name = "abstract"

    def probe(self) -> dict:
        raise NotImplementedError

    def research(self, queries: list, *, limit_per_query: int = 5,
                 timeout: int = 240) -> dict:
        raise NotImplementedError


CODEX_RESEARCH_PROMPT = (
    "You are a read-only job-discovery research worker. Use the web search tool to run "
    "EXACTLY this query:\n\n{query}\n\n"
    "Then reply with ONLY a JSON array of up to {limit} results that you actually "
    "retrieved from the live web, each object: "
    '{{"title": str, "url": str, "snippet": str}}. '
    "Rules: never guess, invent or recall a result from memory; only report results the "
    "web search tool returned. If the web search tool is unavailable or returns nothing, "
    "reply with exactly []. Do not write any files and do not run shell commands."
)


class CodexWebSearchProvider(ResearchProvider):
    """Research worker backed by the Codex CLI's native ``web_search`` tool.

    Results are accepted ONLY when the execution's JSONL event stream contains a
    ``web_search`` item for the query — i.e. the runtime proves a live search
    happened. Otherwise the query is recorded as ``web_search_not_observed`` and
    contributes zero results, so a memory recall can never be mistaken for a
    search result.
    """

    name = "codex-web-search"

    def __init__(self, executable: str | Path | None = None, *, sandbox: str = "read-only",
                 workdir: str | Path | None = None, e3_service=None):
        self._executable_override = executable
        self.sandbox = sandbox
        self.workdir = str(workdir) if workdir else str(CONTROL_PLANE)
        self._resolved = None
        if e3_service is None:
            if str(EXEC_BRAIN) not in sys.path:
                sys.path.insert(0, str(EXEC_BRAIN))
            from e3_service import E3ApplicationService
            e3_service = E3ApplicationService()
        self._e3_service = e3_service

    def resolve(self):
        if self._resolved is not None:
            return self._resolved
        # The historical constructor argument is retained for CLI compatibility
        # but ignored: Career Ops no longer resolves or invokes Codex itself.
        self._resolved = "e3-service"
        return self._resolved

    def probe(self, *, timeout: int = 240) -> dict:
        """Explicitly test whether the installed runtime can perform a live web search."""
        out = {"provider": self.name, "available": False, "web_search_observed": False,
               "cli_version": None, "resolved_executable": None, "reason": None,
               "executed_queries": []}
        try:
            exe = self.resolve()
        except Exception as exc:  # noqa: BLE001
            out["reason"] = f"Codex CLI unavailable: {type(exc).__name__}: {exc}"
            return out
        out["resolved_executable"] = str(exe)
        probe_query = "site:job-boards.greenhouse.io cyber security graduate London"
        result = self._run_one(exe, probe_query, limit=1, timeout=timeout)
        out["cli_version"] = result.get("cli_version")
        out["web_search_observed"] = bool(result.get("web_search_observed"))
        out["executed_queries"] = result.get("executed_queries") or []
        out["available"] = bool(result.get("web_search_observed") and not result.get("error"))
        if not out["available"]:
            out["reason"] = result.get("error") or (
                "no web_search tool event was observed in the Codex execution stream, so the "
                "installed runtime cannot be shown to perform live web research")
        return out

    def _run_one(self, exe, query: str, *, limit: int, timeout: int) -> dict:
        prompt = CODEX_RESEARCH_PROMPT.format(query=query, limit=limit)
        out = {"query": query, "results": [], "web_search_observed": False,
               "executed_queries": [], "cli_version": None, "error": None,
               "raw_events": 0, "elapsed_s": None}
        try:
            result = self._e3_service.execute(
                objective=prompt, task_family="research", required_role="researcher",
                timeout=timeout, context={"working_directory": self.workdir,
                                           "requires_live_web_evidence": True})
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"{type(exc).__name__}: {exc}"
            return out
        if result.get("status") != "COMPLETED":
            out["error"] = result.get("error") or "E3 research execution failed"
            return out
        # E3's generic text contract does not yet expose a provider-observed
        # web-search event.  Do not treat generated JSON as live research until
        # that evidence is part of the E3 contract.
        out["error"] = "E3 response lacked provider-observed web-search evidence"
        return out

    def research(self, queries: list, *, limit_per_query: int = 5,
                 timeout: int = 240) -> dict:
        doc = {"provider": self.name, "available": False, "cli_version": None,
               "resolved_executable": None, "queries": [], "limitation": None,
               "requests": 0, "web_search_observed_queries": 0,
               "queries_without_observed_search": 0}
        try:
            exe = self.resolve()
        except Exception as exc:  # noqa: BLE001
            doc["limitation"] = f"Codex CLI unavailable: {type(exc).__name__}: {exc}"
            for q in queries:
                doc["queries"].append({"query_id": q.get("query_id"), "query": q["query"],
                                       "executed": False, "web_search_observed": False,
                                       "results": [], "error": doc["limitation"]})
            return doc
        doc["resolved_executable"] = str(exe)
        for q in queries:
            res = self._run_one(exe, q["query"], limit=limit_per_query, timeout=timeout)
            doc["requests"] += 1
            doc["cli_version"] = res.get("cli_version") or doc["cli_version"]
            entry = dict(q)
            entry.update({
                "executed": True,
                "web_search_observed": bool(res["web_search_observed"]),
                "executed_queries": res.get("executed_queries") or [],
                "results": res.get("results") or [],
                "error": res.get("error"),
            })
            if res["web_search_observed"]:
                doc["web_search_observed_queries"] += 1
            else:
                doc["queries_without_observed_search"] += 1
                entry["results"] = []
            doc["queries"].append(entry)
        doc["available"] = doc["web_search_observed_queries"] > 0
        if not doc["available"]:
            doc["limitation"] = ("no query produced a web_search tool event; the installed "
                                 "Codex runtime could not be shown to perform live web research")
        return doc


class CapturedResultsProvider(ResearchProvider):
    """Replays a previously captured search-result document (offline/fallback).

    The document is exactly the shape :class:`CodexWebSearchProvider` produces, so
    the capture is a first-class research input rather than a test-only shortcut.
    """

    name = "captured"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict:
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        if doc.get("kind") not in (EXPORT_KIND, None) and "queries" not in doc:
            raise SystemExit(f"{self.path} is not a captured search-result document")
        return doc

    def probe(self) -> dict:
        try:
            doc = self._load()
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.name, "available": False, "reason":
                    f"capture not readable: {type(exc).__name__}: {exc}",
                    "path": str(self.path), "captured_from": None, "captured_at": None}
        return {"provider": self.name, "available": True, "path": str(self.path),
                "captured_from": doc.get("captured_from"),
                "captured_at": doc.get("captured_at"),
                "queries": len(doc.get("queries") or []),
                "reason": None}

    def research(self, queries: list, *, limit_per_query: int = 5,
                 timeout: int = 240) -> dict:
        doc = self._load()
        captured = {q.get("query_id"): q for q in (doc.get("queries") or [])}
        by_query = {q.get("query"): q for q in (doc.get("queries") or [])}
        out = {"provider": self.name, "available": True, "path": str(self.path),
               "captured_from": doc.get("captured_from"),
               "captured_at": doc.get("captured_at"),
               "queries": [], "limitation": None, "requests": 0,
               "web_search_observed_queries": 0, "queries_without_observed_search": 0,
               "cli_version": None, "resolved_executable": None}
        for q in queries:
            match = captured.get(q.get("query_id")) or by_query.get(q.get("query"))
            entry = dict(q)
            if match is None:
                entry.update({"executed": False, "web_search_observed": False,
                              "results": [], "error": "not present in the capture"})
                out["queries_without_observed_search"] += 1
            else:
                entry.update({
                    "executed": True,
                    "web_search_observed": bool(match.get("web_search_observed", True)),
                    "executed_queries": match.get("executed_queries") or [match.get("query")],
                    "results": match.get("results") or [],
                    "error": match.get("error"),
                })
                if entry["web_search_observed"]:
                    out["web_search_observed_queries"] += 1
                else:
                    out["queries_without_observed_search"] += 1
            out["queries"].append(entry)
        out["available"] = out["web_search_observed_queries"] > 0
        if not out["available"]:
            out["limitation"] = ("none of the requested queries is present in the capture as a "
                                 "performed search")
        return out


class NullProvider(ResearchProvider):
    """Declared no-provider: zero results with the reason recorded."""

    name = "none"

    def probe(self) -> dict:
        return {"provider": self.name, "available": False,
                "reason": "no research provider selected; zero queries were executed"}

    def research(self, queries: list, *, limit_per_query: int = 5, timeout: int = 240) -> dict:
        return {"provider": self.name, "available": False, "queries": [
            dict(q, executed=False, web_search_observed=False, results=[],
                 error="no research provider selected") for q in queries],
            "limitation": "no research provider selected; zero queries were executed",
            "requests": 0, "web_search_observed_queries": 0,
            "queries_without_observed_search": len(queries)}


def make_provider(kind: str, *, captured: Path | None = None,
                  executable: str | None = None):
    if kind == "codex":
        return CodexWebSearchProvider(executable=executable)
    if kind == "captured":
        return CapturedResultsProvider(captured or DEFAULT_CAPTURED)
    if kind == "none":
        return NullProvider()
    raise SystemExit(f"unknown provider '{kind}'; known: codex, captured, none")


def _parse_json_array(text: str):
    """Extract the first JSON array from a model reply (tolerantly)."""
    if not isinstance(text, str) or not text.strip():
        return None, "empty response"
    blobs = []
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        blobs.append(fence.group(1))
    blobs.append(text)
    for blob in blobs:
        start = blob.find("[")
        end = blob.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(blob[start:end + 1]), None
            except json.JSONDecodeError:
                continue
    return None, "no parseable JSON array in the response"


# --------------------------------------------------------------------------- #
# liveness validation (polite, robots-respecting, read-only)
# --------------------------------------------------------------------------- #

def canonical_url(url: str | None) -> str | None:
    """Canonical form of a result URL (tracking parameters removed)."""
    norm = tw.normalize_url(url)
    if not norm:
        return None
    parsed = urllib.parse.urlsplit(norm)
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((parsed.scheme or "https", netloc, path, parsed.query, ""))


def _robots_allows(scheme: str, host: str, path: str) -> tuple[bool, str]:
    """Conservative robots.txt check for our user agent. Unknown -> allowed."""
    robots_url = f"{scheme}://{host}/robots.txt"
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=ROBOTS_TIMEOUT) as resp:  # noqa: S310
            if resp.status != 200:
                return True, f"robots.txt status {resp.status}"
            text = resp.read(100_000).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return True, f"robots.txt not retrievable ({type(exc).__name__}); allowed by default"
    disallow: list[str] = []
    applies = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().casefold(), value.strip()
        if field == "user-agent":
            applies = value == "*" or value.casefold() in USER_AGENT.casefold()
        elif field == "disallow" and applies and value:
            disallow.append(value)
    for rule in disallow:
        if rule == "/" or path.startswith(rule):
            return False, f"robots.txt disallows {rule!r} for this agent"
    return True, "robots.txt allows this path"


TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', re.IGNORECASE)
META_DESC_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']description["\']', re.IGNORECASE)
EXPIRED_MARKERS = ("no longer available", "no longer open", "position has been filled",
                   "this job has expired", "job has expired", "page not found",
                   "job not found", "vacancy has closed")


def fetch_validate(url: str, *, timeout: int = FETCH_TIMEOUT,
                   respect_robots: bool = True) -> dict:
    """Safe read-only retrieval of a discovered destination.

    Returns a fetch record — never a fabricated one. ``status`` is
    ``validated_live`` (2xx), ``validation_failed`` (non-2xx, dead link, DNS or
    timeout) or ``not_attempted`` (non-http scheme / robots refusal recorded
    separately). Only source-supported fields are extracted: the page ``<title>``
    and meta description.
    """
    record = {"url": url, "canonical_url": canonical_url(url), "status": FETCH_NOT_ATTEMPTED,
              "http_status": None, "final_url": None, "page_title": None,
              "meta_description": None, "content_chars": 0, "robots": None,
              "expired_marker": None, "error": None, "fetched_at": now_utc()}
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"unparseable URL: {exc}"
        return record
    scheme = (parsed.scheme or "").casefold()
    if scheme not in ("http", "https"):
        record["error"] = f"refusing non-http(s) scheme '{scheme}'"
        record["status"] = FETCH_VALIDATION_FAILED
        return record
    host = parsed.hostname or ""
    if respect_robots:
        allowed, why = _robots_allows(scheme, host, parsed.path or "/")
        record["robots"] = why
        if not allowed:
            record["error"] = why
            record["status"] = FETCH_VALIDATION_FAILED
            return record
    try:
        req = urllib.request.Request(str(url), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            record["http_status"] = resp.status
            record["final_url"] = resp.geturl()
            ctype = (resp.headers.get("Content-Type") or "").casefold()
            body = resp.read(MAX_BODY_BYTES)
        record["content_chars"] = len(body)
        if "html" in ctype or "<html" in body[:2048].decode("utf-8", "replace").casefold():
            text = body.decode("utf-8", "replace")
            title = TITLE_RE.search(text)
            if title:
                record["page_title"] = re.sub(r"\s+", " ", title.group(1)).strip()[:300]
            desc = META_DESC_RE.search(text) or META_DESC_RE_ALT.search(text)
            if desc:
                record["meta_description"] = re.sub(r"\s+", " ", desc.group(1)).strip()[:500]
            lowered = text.casefold()
            for marker in EXPIRED_MARKERS:
                if marker in lowered:
                    record["expired_marker"] = marker
                    break
        if 200 <= int(record["http_status"]) < 300 and not record["expired_marker"]:
            record["status"] = FETCH_VALIDATED_LIVE
        else:
            record["status"] = FETCH_VALIDATION_FAILED
            if record["expired_marker"]:
                record["error"] = f"page states the posting is closed: {record['expired_marker']}"
    except urllib.error.HTTPError as exc:
        record["http_status"] = exc.code
        record["status"] = FETCH_VALIDATION_FAILED
        record["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        record["status"] = FETCH_VALIDATION_FAILED
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


# --------------------------------------------------------------------------- #
# normalisation: one search result -> one canonical-schema candidate
# --------------------------------------------------------------------------- #

#: the owner's documented WebSearch title/company extraction (modes/scan.md).
RESULT_TITLE_COMPANY_RE = re.compile(r"^(.+?)(?:\s*[@|—–]\s*|\s+at\s+)(.+?)$")


def parse_result_title(title: str | None) -> tuple:
    """``"Job Title @ Company"`` / ``"Job Title | Company"`` -> (title, company).

    Returns ``(title, None)`` when no separator is present: the company is left
    missing rather than guessed.
    """
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    if not text:
        return None, None
    match = RESULT_TITLE_COMPANY_RE.match(text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text, None


def normalise_result(*, result: dict, query_entry: dict, fetch: dict | None,
                     source_timestamp: str) -> dict:
    """Normalise one discovered search result into the unified candidate schema.

    Nothing is invented: ``title``/``company`` come from the fetched page when it
    was retrieved, otherwise from the search-result title as *observed*, and a
    field that cannot be determined is listed in ``missing_fields``.
    """
    raw_url = str(result.get("url") or "").strip()
    surface = classify_surface(raw_url)
    result_kind, kind_reason = classify_result_kind(raw_url)
    fetch = fetch or {"status": FETCH_DISCOVERED_UNVERIFIED, "url": raw_url,
                      "canonical_url": canonical_url(raw_url)}
    fetch_state = fetch.get("status") or FETCH_DISCOVERED_UNVERIFIED
    if fetch_state == FETCH_NOT_ATTEMPTED:
        fetch_state = FETCH_DISCOVERED_UNVERIFIED

    page_title = fetch.get("page_title")
    snippet_title, snippet_company = parse_result_title(result.get("title"))
    if page_title:
        title, company = parse_result_title(page_title)
        title_source = "fetched_page_title"
        if company is None:
            company = snippet_company
    else:
        title, company = snippet_title, snippet_company
        title_source = "search_result_title"

    location = result.get("location") or None
    if location is None and fetch.get("meta_description"):
        location = None  # never inferred from a description

    observed = {
        "title": title, "company": company, "location": location,
        "result_title": result.get("title"), "snippet": result.get("snippet"),
        "page_title": page_title, "page_description": fetch.get("meta_description"),
    }
    present = [k for k in ("title", "company", "location", "url") if observed.get(k)
               or (k == "url" and raw_url)]
    missing = [k for k in ("title", "company", "location", "description", "posted_date",
                           "salary", "employment_type") if not observed.get(k)]

    return {
        "company": company,
        "title": title,
        "location": location,
        "url": raw_url,
        "description": fetch.get("meta_description"),
        "source": query_entry.get("surface_scope") or surface,
        "fetch_state": fetch_state,
        "result_kind": result_kind,
        "_collection_source": "web research",
        "web_research": {
            "discovery_surface": surface,
            "surface_description": surface_description(surface),
            "search_query": query_entry.get("query"),
            "query_id": query_entry.get("query_id"),
            "query_provenance": query_entry.get("query_provenance"),
            "role_family": query_entry.get("role_family"),
            "region": query_entry.get("region"),
            "result_url": raw_url,
            "canonical_url": fetch.get("canonical_url") or canonical_url(raw_url),
            "observed": observed,
            "title_source": title_source,
            "source_timestamp": source_timestamp,
            "fetch": fetch,
            "result_kind": result_kind,
            "result_kind_reason": kind_reason,
            "missing_fields": missing,
            "present_fields": present,
        },
    }


# --------------------------------------------------------------------------- #
# the research run
# --------------------------------------------------------------------------- #

TELEMETRY_KEYS = ("queries_executed", "results_seen", "candidate_urls", "validated_live",
                  "validation_failed", "duplicates_collapsed", "search_listing_refused",
                  "semantically_reviewed", "deterministic_eligibility_pass", "tracker_candidates")


def run_research(queries: list, provider, *, region: str, limit_per_query: int = 5,
                 timeout: int = 240, validate: bool = True,
                 respect_robots: bool = True, max_urls: int = 40,
                 validate_fn=None) -> dict:
    """Execute the matrix through a provider and normalise + validate the results."""
    started = now_utc()
    provider_doc = provider.research(queries, limit_per_query=limit_per_query, timeout=timeout)
    validate_fn = validate_fn or fetch_validate

    telemetry = {k: 0 for k in TELEMETRY_KEYS}
    rejections: dict = {}
    zero_reasons: dict = {}
    candidates: list = []
    query_rows: list = []
    urls_seen: list = []
    validation_budget = max_urls

    for entry in provider_doc.get("queries") or []:
        row = {"query_id": entry.get("query_id"), "query": entry.get("query"),
               "region": entry.get("region"), "role_family": entry.get("role_family"),
               "surface_scope": entry.get("surface_scope"),
               "query_provenance": entry.get("query_provenance"),
               "executed": bool(entry.get("executed")),
               "web_search_observed": bool(entry.get("web_search_observed")),
               "executed_queries": entry.get("executed_queries") or [],
               "results_seen": 0, "error": entry.get("error"), "results": []}
        if row["executed"]:
            telemetry["queries_executed"] += 1
        if not row["web_search_observed"]:
            reason = "search_not_observed" if row["executed"] else "query_not_executed"
            rejections[reason] = rejections.get(reason, 0) + 1
            zero_reasons.setdefault(
                "search", "no live search was observed for the query, so no result from it is "
                          "accepted (a memory recall is never treated as a search result)")
            query_rows.append(row)
            continue
        results = [r for r in (entry.get("results") or [])
                   if isinstance(r, dict) and str(r.get("url") or "").startswith(("http://", "https://"))]
        row["results_seen"] = len(results)
        telemetry["results_seen"] += len(results)
        for result in results:
            url = str(result.get("url") or "").strip()
            if url in urls_seen:
                telemetry["duplicates_collapsed"] += 1
                row["results"].append({"url": url, "duplicate": True})
                continue
            urls_seen.append(url)
            telemetry["candidate_urls"] += 1
            fetch = None
            if validate and validation_budget > 0:
                validation_budget -= 1
                fetch = validate_fn(url, respect_robots=respect_robots)
            candidate = normalise_result(result=result, query_entry=row, fetch=fetch,
                                         source_timestamp=started)
            state = candidate["fetch_state"]
            if state == FETCH_VALIDATED_LIVE:
                telemetry["validated_live"] += 1
            elif state == FETCH_VALIDATION_FAILED:
                telemetry["validation_failed"] += 1
                rejections.setdefault("validation_failed", 0)
                rejections["validation_failed"] += 1
            else:
                telemetry[FETCH_DISCOVERED_UNVERIFIED] = \
                    telemetry.get(FETCH_DISCOVERED_UNVERIFIED, 0) + 1
            if candidate.get("result_kind") == RESULT_KIND_SEARCH_LISTING:
                # A search/listing page is not a vacancy: it is kept with its
                # provenance but the deterministic gate refuses it tracker handoff.
                telemetry["search_listing_refused"] += 1
                rejections["search_result_listing_page"] = \
                    rejections.get("search_result_listing_page", 0) + 1
            if not candidate.get("url"):
                rejections["no_url"] = rejections.get("no_url", 0) + 1
            candidates.append(candidate)
            row["results"].append({"url": url, "fetch_state": state,
                                   "result_kind": candidate.get("result_kind"),
                                   "canonical_url": candidate["web_research"]["canonical_url"]})
        query_rows.append(row)

    if telemetry["queries_executed"] == 0:
        zero_reasons.setdefault("queries", "no query was executed")
    if telemetry["results_seen"] == 0 and telemetry["queries_executed"]:
        zero_reasons.setdefault("results", "the executed queries returned no accessible results")
    if telemetry["validated_live"] == 0 and telemetry["candidate_urls"] and validate:
        zero_reasons.setdefault("validation", "no discovered destination validated as live")
    if telemetry["search_listing_refused"] and \
            telemetry["search_listing_refused"] == len(candidates):
        zero_reasons.setdefault(
            "vacancy_posting",
            "every discovered URL was a search/listing page rather than a vacancy posting, so "
            "none of them can become a tracker candidate")
    if not candidates:
        zero_reasons.setdefault("candidate_urls", "no candidate URL was discovered")

    fetch_states = {state: sum(1 for c in candidates if c["fetch_state"] == state)
                    for state in FETCH_STATES}
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPORT_KIND,
        "generated_at": started,
        "region": region,
        "provider": {k: provider_doc.get(k) for k in
                     ("provider", "available", "limitation", "requests", "cli_version",
                      "resolved_executable", "captured_from", "captured_at",
                      "web_search_observed_queries", "queries_without_observed_search")},
        "queries": query_rows,
        "candidates": candidates,
        "telemetry": dict(telemetry, fetch_states=fetch_states,
                          rejections_by_reason=dict(sorted(rejections.items())),
                          zero_attribution=zero_reasons),
        "safety": {
            "read_only": True,
            "login_or_account_used": False,
            "cookies_or_session_used": False,
            "browser_or_gui_used": False,
            "scraping_behind_auth": False,
            "captcha_bypassed": False,
            "applications_submitted": 0,
            "employer_or_recruiter_contacts": 0,
            "canonical_workbook_written": False,
        },
        "privacy_note": ("result URLs and observed fields are owner-private job-search data; "
                         "only aggregate counters and hashes are committed"),
    }
    doc["export_id"] = "webresearch-" + hashlib.sha256(
        json.dumps({"region": region, "queries": [q["query"] for q in query_rows],
                    "urls": sorted(urls_seen)}, sort_keys=True,
                   ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return doc


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


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


def policy_document() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "lane": "web research (Codex-style open-web job discovery)",
        "primary_behaviour": "active research over a generated query matrix, not a static scan",
        "role_families": ROLE_FAMILIES,
        "entry_terms_short": list(ENTRY_TERMS_SHORT),
        "level_coverage_terms": list(LEVEL_COVERAGE_TERMS),
        "discipline_clause": DISCIPLINE_CLAUSE,
        "query_shape_note": ("clauses are deliberately short: a measured live pass on 2026-09-24 "
                             "found the native search tool returns no results for a very long "
                             "compound site: query, while the owner's shorter shape returns live "
                             "results on every surface"),
        "regions": REGION_LOCATIONS,
        "owner_ats_site_queries": [{"surface": s, "site_clause": q}
                                   for s, q in OWNER_ATS_SITE_QUERIES],
        "broad_surfaces": [{"surface": s, "site_clause": q} for s, q in BROAD_SURFACES],
        "surfaces": [{"surface": n, "host_tokens": list(t), "description": d}
                     for n, t, d in SURFACE_DEFINITIONS],
        "providers": {
            "codex-web-search": ("Codex CLI native web_search tool; a result is accepted only "
                                 "when the execution stream proves a live search occurred"),
            "captured": "replay a previously captured search-result document",
            "none": "declared zero",
        },
        "fetch_states": list(FETCH_STATES),
        "result_kinds": list(RESULT_KINDS),
        "rules": [
            "never invent a vacancy from a search snippet: title/company come from the "
            "retrieved page or the observed result title, and unknown fields stay missing",
            "a result is only accepted when the research worker proves a live search happened",
            "a search/listing page (LinkedIn /jobs/<keywords>, Indeed /q-..., a Google result "
            "page) is labelled search_listing and never written as a vacancy",
            "destinations are validated with a polite, robots-respecting read-only retrieval; "
            "a posting that cannot be validated stays labelled and is refused tracker handoff",
            "no login, account, cookie/session, CAPTCHA, browser, GUI or stealth scraping",
            "the lane feeds the shared discovery funnel; it is not a second tracker/classifier",
        ],
        "watchlist_hook": ("an owner-provided company list adds company × role-family and "
                           "company × ATS queries; the generic search works without it"),
    }


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_policy(args) -> int:
    emit({"generated_at": now_utc(), **policy_document()})
    return 0


def cmd_matrix(args) -> int:
    watchlist = load_watchlist(Path(args.watchlist)) if args.watchlist else []
    matrix = build_query_matrix(args.region, include_watchlist=watchlist)
    emit({"generated_at": now_utc(), "region": args.region, "watchlist": watchlist,
          "counts": {"queries": len(matrix),
                     "by_surface": _count_by(matrix, "surface_scope"),
                     "by_family": _count_by(matrix, "role_family")},
          "matrix": matrix})
    return 0


def _count_by(rows: list, key: str) -> dict:
    out: dict = {}
    for row in rows:
        out[row.get(key)] = out.get(row.get(key), 0) + 1
    return dict(sorted(out.items()))


def cmd_probe(args) -> int:
    provider = make_provider(args.provider if args.provider != "auto" else "codex",
                             captured=Path(args.captured) if args.captured else None,
                             executable=args.executable)
    doc = provider.probe()
    doc["generated_at"] = now_utc()
    doc["capability_note"] = ("a PASS here proves the research worker can perform a live web "
                             "search in this runtime; it is not a claim about any vacancy")
    emit(doc)
    return 0 if doc.get("available") else 1


def cmd_run(args) -> int:
    watchlist = load_watchlist(Path(args.watchlist)) if args.watchlist else []
    matrix = build_query_matrix(args.region, include_watchlist=watchlist)
    provider_kind = args.provider
    provider = make_provider(provider_kind,
                             captured=Path(args.captured) if args.captured else None,
                             executable=args.executable)
    if args.limit_queries and args.limit_queries < len(matrix):
        matrix = matrix[:args.limit_queries]
        limited = True
    else:
        limited = False
    doc = run_research(matrix, provider, region=args.region,
                       limit_per_query=args.limit_per_query, timeout=args.timeout,
                       validate=(not args.no_validate), max_urls=args.max_urls)
    doc["watchlist"] = watchlist
    doc["query_matrix_limited"] = limited
    doc["query_matrix_size"] = len(matrix)
    doc["limit_note"] = ("the query matrix was truncated by --limit-queries; the counters below "
                         "describe the queries actually executed, never the market"
                         if limited else None)

    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    export_path = out_dir / f"web-research-{args.region}-{doc['export_id']}.json"
    write_json_atomic(export_path, doc)
    latest = out_dir / f"web-research-{args.region}-latest.json"
    write_json_atomic(latest, doc)
    doc["export_file"] = str(export_path)
    doc["latest_file"] = str(latest)

    if args.with_funnel:
        import pipeline  # noqa: PLC0415 - imported lazily to avoid a circular import
        collection = pipeline.collect_from_web_research(export_path, args.region)
        block = dict(collection)
        block["source"] = pipeline.SOURCE_WEB_RESEARCH
        run_id = f"webresearch-funnel-{args.region}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        funnel_doc = pipeline.run_funnel(
            list(collection["candidates"]), region=args.region,
            mode="high_recall",
            semantic=args.semantic, deepseek_model=args.model,
            batch_size=8, codex_budget=args.codex_budget,
            codex_enabled=(args.codex != "off"), timeout=args.timeout,
            run_id=run_id, collection=[block])
        counts = funnel_doc["funnel"]["counts"]
        doc["telemetry"]["semantically_reviewed"] = counts.get("semantically_reviewed", 0)
        doc["telemetry"]["deterministic_eligibility_pass"] = \
            counts.get("deterministic_eligibility_pass", 0)
        doc["telemetry"]["tracker_candidates"] = counts.get("tracker_candidates", 0)
        doc["funnel"] = {
            "run_id": run_id,
            "counts": counts,
            "zero_attribution": funnel_doc["funnel"]["zero_attribution"],
            "by_source": funnel_doc["funnel"]["by_source"],
            "safety": funnel_doc["safety"],
            "summary_line": funnel_doc.get("summary_line"),
        }
        if args.manifest_out:
            write_json_atomic(Path(args.manifest_out), {
                "schema_version": 1, "generated_at": now_utc(), "region": args.region,
                "run_id": run_id,
                "records": [rjs.build_record(args.region, c, rjs.load_policy(), run_id,
                                             {"stage": "web-research-manifest"})
                            for c in funnel_doc["canonical_candidates"]
                            if c.get("url") and c["candidate_id"] in
                            {d["candidate_id"] for d in funnel_doc["eligibility"]["decisions"]
                             if d["decision"] == "accepted"}]})
            doc["manifest_written_to"] = str(args.manifest_out)
        write_json_atomic(export_path, doc)
        write_json_atomic(latest, doc)

    emit(doc)
    return 0


def cmd_summary(args) -> int:
    doc = read_json(Path(args.export))
    telemetry = doc.get("telemetry") or {}
    emit({"generated_at": now_utc(), "export_id": doc.get("export_id"),
          "region": doc.get("region"), "provider": doc.get("provider"),
          "counts": {k: telemetry.get(k) for k in TELEMETRY_KEYS},
          "fetch_states": telemetry.get("fetch_states"),
          "rejections_by_reason": telemetry.get("rejections_by_reason"),
          "zero_attribution": telemetry.get("zero_attribution"),
          "safety": doc.get("safety")})
    return 0


def cmd_status(args) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    latest = sorted(out_dir.glob("web-research-*-latest.json")) if out_dir.exists() else []
    emit({"generated_at": now_utc(), "out_dir": str(out_dir), "latest_exports": [
        {"file": str(p), "region": p.name.split("-")[2]} for p in latest],
        "watchlist_file": str(DEFAULT_WATCHLIST),
        "watchlist_present": DEFAULT_WATCHLIST.exists(),
        "policy": policy_document()["rules"]})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bounded read-only open-web job research lane")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("policy")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("matrix")
    p.add_argument("--region", required=True)
    p.add_argument("--watchlist")
    p.set_defaults(fn=cmd_matrix)

    p = sub.add_parser("probe")
    p.add_argument("--provider", choices=("auto", "codex", "captured", "none"), default="auto")
    p.add_argument("--captured")
    p.add_argument("--executable")
    p.set_defaults(fn=cmd_probe)

    p = sub.add_parser("run")
    p.add_argument("--region", required=True)
    p.add_argument("--provider", choices=("codex", "captured", "none"), default="codex")
    p.add_argument("--captured")
    p.add_argument("--executable")
    p.add_argument("--watchlist")
    p.add_argument("--limit-queries", type=int, default=0)
    p.add_argument("--limit-per-query", type=int, default=5)
    p.add_argument("--max-urls", type=int, default=40)
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--timeout", type=int, default=240)
    p.add_argument("--out-dir")
    p.add_argument("--with-funnel", action="store_true")
    p.add_argument("--semantic", choices=("auto", "deepseek", "deterministic", "off"),
                   default="auto")
    p.add_argument("--codex", choices=("on", "off"), default="off")
    p.add_argument("--codex-budget", type=int, default=4)
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--manifest-out")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("summary")
    p.add_argument("--export", required=True)
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("status")
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
