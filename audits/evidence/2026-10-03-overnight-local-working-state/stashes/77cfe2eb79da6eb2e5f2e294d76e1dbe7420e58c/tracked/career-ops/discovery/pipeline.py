#!/usr/bin/env python3
"""Multi-stage high-recall discovery pipeline (control-plane, non-destructive).

One funnel for every read-only discovery surface:

    broad collection (Career Ops lanes, Company Watch, recruiter/intermediary
      watch, LinkedIn owner exports, …)
      -> cross-source canonical collapse (one vacancy -> one candidate, provenance kept)
      -> light deterministic prefilter (two-tier title policy)
      -> DeepSeek bulk semantic triage (structured contract)
      -> bounded Codex second pass (ambiguous / high-value only)
      -> deterministic eligibility gates (region, work authorisation, clearance,
         mandatory experience, application URL) — authoritative, never overridden
      -> shared dedupe (career-ops/tracker_writer.py, the same code Career Ops uses)
      -> tracker manifest / Chief brief handoff

Subcommands
-----------
  policy                         the two-tier title policy, the semantic contract,
                                 the source registry and the source contract
  selftest                       run the regression fixtures (positive + negative)
  run        --region R [--records F | --scan-record F | --company-watch F |
                         --recruiter-watch F | --linkedin F]
                                 one bounded funnel run; writes only run evidence
  compare-modes --region R ...   old strict intern-only policy vs the new
                                 high-recall pipeline over the SAME candidate set

Adding a read-only discovery surface means adding one collector to
``SOURCE_REGISTRY`` that returns the same collection-block shape — never a second
classifier, eligibility rule set or dedupe engine.

Safety
------
* A run never writes a canonical workbook: dedupe is a probe and the handoff is
  a manifest. Applying stays the explicit ``career_ops_cli.py write --apply``.
* Codex escalation is capped by ``--codex-budget`` (default 8) and only fires on
  the deterministic conditions in ``classifiers.escalation_reason``.
* Nothing here submits an application, contacts an employer, an agency or an
  intermediary, opens a browser, uses an account/session or scrapes a site.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAREER_OPS = HERE.parent
CONTROL_PLANE = CAREER_OPS.parent
for _p in (str(HERE), str(CAREER_OPS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regional_job_search as rjs  # noqa: E402
import tracker_writer as tw  # noqa: E402
from classifiers import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_CODEX_BUDGET,
    DEFAULT_MAX_TOKENS,
    codex_escalate,
    deepseek_bulk_classify,
    deepseek_probe,
    deterministic_classify,
)
from funnel import Funnel  # noqa: E402
from semantic_contract import (  # noqa: E402
    ACCEPT_LABELS,
    contract_document,
    dumps as contract_dumps,
    candidate_id,
    jd_available,
)
from title_policy import (  # noqa: E402
    DEFAULT_MODE,
    MODES,
    MODE_HIGH_RECALL,
    MODE_INTERN_ONLY,
    policy_document,
    tier_b_hits,
    title_decision,
)

SCHEMA_VERSION = 1
DEFAULT_SEMANTIC = "auto"          # auto -> deepseek when healthy, else deterministic
DEFAULT_RUNTIME_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "discovery"

#: source label used for explicitly supplied candidate records
SOURCE_EXPLICIT = "explicit records file"
SOURCE_SCAN_RECORD = "regional run-health scan record"
SOURCE_COMPANY_WATCH = "company-watch findings"
SOURCE_RECRUITER_WATCH = "recruiter/intermediary watch findings"
SOURCE_LINKEDIN_EXPORT = "linkedin job-discovery export"
SOURCE_WEB_RESEARCH = "open-web research (codex-style)"
#: The owner's own company short list, resolved to careers/ATS surfaces and
#: researched by company name. It is an ADDITIVE surface: broad-market discovery
#: continues unchanged alongside it.
SOURCE_PRIORITY_WATCHLIST = "owner priority watchlist (company careers/ATS + role-family research)"

#: Every read-only discovery surface routes through the SAME funnel. Adding a
#: source means adding one collector here — never a second classifier, a second
#: eligibility rule set or a second dedupe engine.
SOURCE_REGISTRY = {
    SOURCE_EXPLICIT: "collect_from_records",
    SOURCE_SCAN_RECORD: "collect_from_scan_record",
    SOURCE_COMPANY_WATCH: "collect_from_company_watch",
    SOURCE_RECRUITER_WATCH: "collect_from_recruiter_watch",
    SOURCE_LINKEDIN_EXPORT: "collect_from_linkedin",
    SOURCE_WEB_RESEARCH: "collect_from_web_research",
    SOURCE_PRIORITY_WATCHLIST: "collect_from_priority_watchlist",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def emit(obj) -> None:
    rjs.emit(obj)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #

CANDIDATE_FIELDS = ("company", "title", "location", "url", "description", "summary",
                    "posted_date", "salary", "experience_required", "employment_type",
                    "vendor", "intermediary", "source_detail", "fetch_state", "result_kind")


def normalise_candidate(raw: dict, source: str) -> dict:
    rec = {k: raw.get(k) for k in CANDIDATE_FIELDS if raw.get(k) not in (None, "")}
    rec["source"] = raw.get("source") or source
    rec["_collection_source"] = source
    rec["_declared_source"] = raw.get("source") or None
    rec["needs_url_resolution"] = not bool(tw.extract_url(rec.get("url")))
    return rec


def collect_from_records(path: Path) -> dict:
    data = read_json(path)
    if isinstance(data, dict):
        rows = data.get("records") or data.get("candidates") or []
    else:
        rows = data
    return {"available": True, "path": str(path), "candidates":
            [normalise_candidate(r, SOURCE_EXPLICIT) for r in rows if isinstance(r, dict)],
            "coverage": {"kind": "explicit candidate records",
                         "note": "supplied by the caller; this pipeline did not collect them"}}


def collect_from_scan_record(path: Path) -> dict:
    """Candidates from a regional run-health record (offers + scan counters)."""
    doc = read_json(path)
    scan = doc.get("scan") or {}
    offers = doc.get("scan_offers")
    if offers is None:
        offers = rjs.parse_scan_offers(scan.get("stdout_tail") or "")
    candidates = []
    for offer in offers or []:
        rec = normalise_candidate(offer, SOURCE_SCAN_RECORD)
        rec["needs_url_resolution"] = True   # scan offers never carry a URL
        candidates.append(rec)
    counters = scan.get("counters") or rjs.parse_scan_counters(scan.get("stdout_tail") or "")
    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "career-ops lane scan (offers block)",
            "region": doc.get("region"),
            "run_id": doc.get("run_id"),
            "scan_ok": scan.get("ok"),
            "scan_refused": bool(scan.get("refused")),
            "scan_reason": scan.get("warning") or (doc.get("status")),
            "counters": counters,
            "note": ("offers carry company/title/location only: no posting URL and no "
                     "description text, so they cannot become tracker rows on their own and "
                     "any semantic label for them is not JD analysis"),
        },
    }


def collect_from_company_watch(path: Path, region: str) -> dict:
    doc = read_json(path)
    findings = doc.get("findings") or []
    candidates, excluded = [], Counter()
    for f in findings:
        reason = f.get("decision") or "unknown"
        if f.get("region_route") not in (None, region):
            excluded[f"routed_other_region:{f.get('region_route')}"] += 1
            continue
        if reason != "new":
            excluded[f"company_watch_decision:{reason}"] += 1
            continue
        rec = normalise_candidate(f, SOURCE_COMPANY_WATCH)
        rec["company_watch"] = {
            "decision": reason,
            "decision_reason": f.get("decision_reason"),
            "owner_filter_eligible": f.get("owner_filter_eligible"),
            "title_rule_pass": f.get("title_rule_pass"),
            "link_engine_eligible": f.get("tracker_eligible"),
            "attribution_confidence": f.get("attribution_confidence"),
            "url_quality": f.get("url_quality"),
        }
        candidates.append(rec)
    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "company-watch findings",
            "findings_total": len(findings),
            "findings_entering_this_funnel": len(candidates),
            "findings_excluded_before_the_funnel": dict(sorted(excluded.items())),
            "generated_at": doc.get("generated_at"),
            "region": doc.get("region"),
            "note": ("findings excluded before the funnel are counted with their own Company "
                     "Watch reason, so a 'new' finding can never silently become zero jobs"),
        },
    }


CONTENT_FIELD_ORDER = ("description", "summary")


def collect_from_recruiter_watch(path: Path, region: str) -> dict:
    """Recruiter / intermediary watch findings (roster B11) as candidates.

    The watch is a read-only discovery surface: it records what an agency or
    intermediary advertised, and — when the employer is named — the employer.
    Nothing here contacts an agency, an intermediary or an employer.

    The accepted export shape is declared, not guessed::

        {"generated_at": ..., "region": ..., "findings": [
           {"intermediary": ..., "employer": ..., "company": ...,
            "title": ..., "location": ..., "url": ...,
            "decision": "new"|"duplicate"|"rejected",
            "decision_reason": ..., "region_route": ...,
            "attribution_confidence": ...}, ...]}

    Findings the watch itself excluded (routed to another region, or already
    known) are counted with their own watch reason, so they cannot silently
    become "0 jobs".
    """
    doc = read_json(path)
    findings = doc.get("findings") or doc.get("records") or []
    candidates, excluded = [], Counter()
    for f in findings:
        if not isinstance(f, dict):
            excluded["malformed_finding"] += 1
            continue
        reason = f.get("decision") or "unknown"
        if f.get("region_route") not in (None, region):
            excluded[f"routed_other_region:{f.get('region_route')}"] += 1
            continue
        if reason != "new":
            excluded[f"recruiter_watch_decision:{reason}"] += 1
            continue
        rec = normalise_candidate(f, SOURCE_RECRUITER_WATCH)
        rec["intermediary"] = f.get("intermediary") or f.get("agency")
        rec["company"] = f.get("company") or f.get("employer")
        rec["recruiter_watch"] = {
            "intermediary": f.get("intermediary") or f.get("agency"),
            "employer_named": bool(f.get("employer") or f.get("company")),
            "decision": reason,
            "decision_reason": f.get("decision_reason"),
            "attribution_confidence": f.get("attribution_confidence"),
            "region_route": f.get("region_route"),
        }
        candidates.append(rec)
    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "recruiter/intermediary watch findings",
            "findings_total": len(findings),
            "findings_entering_this_funnel": len(candidates),
            "findings_excluded_before_the_funnel": dict(sorted(excluded.items())),
            "generated_at": doc.get("generated_at"),
            "region": doc.get("region"),
            "note": ("read-only intermediary surface: an employer named by the intermediary is "
                     "the candidate's company, and an unnamed employer stays unnamed. No agency "
                     "or employer is contacted and no account is used."),
            "match_basis": ("company + title + location + posting URL; the same posting seen "
                            "through an agency collapses to the same canonical candidate as the "
                            "employer's own posting"),
        },
    }


def collect_from_linkedin(path: Path, region: str) -> dict:
    """LinkedIn read-only / owner-exported job discoveries (roster B19).

    Only an owner-exported local file is read; the existing read-only LinkedIn
    intake parser does the parsing, so there is exactly one LinkedIn export
    parser. There is no login, no API session, no scraping, no browser control,
    no posting, no messaging and no application anywhere in this path.

    Company-only signals and lines without a URL are reported as coverage, not
    guessed into postings.
    """
    signals, unsupported = [], []
    try:
        import linkedin_workflow as lw  # noqa: PLC0415 - existing read-only intake
        cfg = lw.load_config()
        parsed = lw.parse_inbox_file(Path(path), cfg)
        unsupported = list(parsed.get("unclassified") or [])
        # the existing read-only classifier labels each signal (job_signal /
        # company_signal / unclassified); this does no network access
        classified = [lw.classify(s) for s in (parsed.get("signals") or [])]
        signals = [s for s in classified if s.get("signal_kind") == "job_signal"]
        company_signals = [s for s in classified
                           if s.get("signal_kind") == "company_signal"]
        other_signals = [s for s in classified
                         if s.get("signal_kind") not in ("job_signal", "company_signal")]
        file_sha = parsed.get("sha256")
        skipped = parsed.get("skipped")
    except Exception as exc:  # noqa: BLE001 - reported as a limitation, never fatal
        return {
            "available": False,
            "path": str(path),
            "candidates": [],
            "coverage": {"kind": "linkedin job-discovery export",
                         "limitation": f"linkedin export could not be read: {type(exc).__name__}: {exc}",
                         "note": ("the LinkedIn surface is read-only; a file that cannot be "
                                  "parsed contributes zero candidates and is recorded as such "
                                  "rather than being guessed")},
        }

    candidates = []
    for sig in signals:
        # A missing company/title stays missing: the parser already refused to guess.
        rec = normalise_candidate(sig, SOURCE_LINKEDIN_EXPORT)
        rec["source_detail"] = sig.get("source_detail") or sig.get("source")
        if rec.get("posted_at") and not rec.get("posted_date"):
            rec["posted_date"] = rec.pop("posted_at")
        candidates.append(rec)

    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "linkedin job-discovery export (owner-exported local file)",
            "file_sha256": file_sha,
            "skipped": skipped,
            "job_signals_entering_this_funnel": len(candidates),
            "company_signals_not_job_candidates": len(company_signals),
            "unclassified_signals_not_job_candidates": len(other_signals),
            "lines_without_a_url": len(unsupported),
            "unclassified": unsupported[:20],
            "note": ("read-only owner export only: no login, API, scraping, browser, posting, "
                     "messaging, connection request or application. Company-only signals stay "
                     "company signals and never become vacancy candidates."),
            "match_basis": ("posting URL (tracking parameters removed) where present, else "
                            "company + title; the same posting re-shared with a utm parameter "
                            "collapses to one canonical candidate"),
        },
    }


def collect_from_web_research(path: Path, region: str) -> dict:
    """Open-web research discoveries (roster B26) as candidates.

    Reads a web-research export produced by ``career-ops/discovery/web_research.py``
    — the result of an *active* query-matrix search, not a static provider scan.
    Every result keeps its provenance (search query, discovery surface, result URL,
    canonical URL, observed fields, fetch/validation state, source timestamp and
    missing fields) and enters the SAME funnel as every other surface.

    A destination that could not be validated live is kept as a candidate but
    labelled with its ``fetch_state``; the deterministic gates refuse tracker
    handoff for anything that is not ``validated_live`` (fail-closed).
    """
    try:
        doc = read_json(path)
    except Exception as exc:  # noqa: BLE001 - reported as a limitation, never fatal
        return {
            "available": False, "path": str(path), "candidates": [],
            "coverage": {"kind": "open-web research export",
                         "limitation": f"export could not be read: {type(exc).__name__}: {exc}",
                         "note": ("an unreadable research export contributes zero candidates and "
                                  "is recorded as such rather than being guessed")},
        }

    telemetry = doc.get("telemetry") or {}
    candidates, excluded = [], Counter()
    undeclared_kind = 0
    for raw in (doc.get("candidates") or []):
        if not isinstance(raw, dict):
            excluded["malformed_candidate"] += 1
            continue
        fetch_state = raw.get("fetch_state") or "discovered_unverified"
        result_kind = raw.get("result_kind") or (raw.get("web_research") or {}).get("result_kind")
        if not result_kind:
            # Never guessed: an export that predates the result-kind contract keeps
            # its candidates unclassified, and the coverage block says so.
            undeclared_kind += 1
        rec = normalise_candidate(raw, SOURCE_WEB_RESEARCH)
        rec["fetch_state"] = fetch_state
        rec["result_kind"] = result_kind
        wr = raw.get("web_research") or {}
        rec["web_research"] = {
            "discovery_surface": wr.get("discovery_surface"),
            "search_query": wr.get("search_query"),
            "query_id": wr.get("query_id"),
            "role_family": wr.get("role_family"),
            "region": wr.get("region"),
            "result_url": wr.get("result_url") or raw.get("url"),
            "canonical_url": wr.get("canonical_url"),
            "observed": wr.get("observed"),
            "title_source": wr.get("title_source"),
            "source_timestamp": wr.get("source_timestamp"),
            "fetch_state": fetch_state,
            "result_kind": result_kind,
            "result_kind_reason": wr.get("result_kind_reason"),
            "missing_fields": wr.get("missing_fields"),
        }
        if fetch_state == "validation_failed":
            excluded["destination_not_validated_live"] += 1
        elif fetch_state == "discovered_unverified":
            excluded["destination_not_verified"] += 1
        if result_kind == "search_listing":
            excluded["search_listing_page_not_a_vacancy"] += 1
        candidates.append(rec)

    provider = doc.get("provider") or {}
    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "open-web research export (codex-style active search)",
            "export_id": doc.get("export_id"),
            "region": doc.get("region"),
            "provider": provider.get("provider"),
            "provider_available": provider.get("available"),
            "provider_limitation": provider.get("limitation"),
            "queries_executed": telemetry.get("queries_executed"),
            "results_seen": telemetry.get("results_seen"),
            "candidate_urls": telemetry.get("candidate_urls"),
            "validated_live": telemetry.get("validated_live"),
            "validation_failed": telemetry.get("validation_failed"),
            "duplicates_collapsed": telemetry.get("duplicates_collapsed"),
            "search_listing_refused": telemetry.get("search_listing_refused"),
            "fetch_states": telemetry.get("fetch_states"),
            "rejections_by_reason": telemetry.get("rejections_by_reason"),
            "zero_attribution": telemetry.get("zero_attribution"),
            "candidates_entering_this_funnel": len(candidates),
            "candidates_excluded_before_the_funnel": dict(sorted(excluded.items())),
            "candidates_without_a_declared_result_kind": undeclared_kind,
            "result_kind_note": (
                "the search/listing-page guard applies only to candidates whose result_kind "
                "this surface declared; an export that predates the result-kind contract keeps "
                "its candidates unclassified and is counted above rather than guessed"
                if undeclared_kind else
                "every candidate carries the result_kind this surface declared"),
            "note": ("active open-web research (a generated query matrix, not a static provider "
                     "scan). Public/search-index discovery only: no login, no account, no "
                     "cookie or session, no CAPTCHA, no browser or GUI, and no scraping behind "
                     "authentication. A result is only accepted when the research worker proves "
                     "a live search happened."),
            "match_basis": ("posting URL (tracking parameters removed) where present, else "
                            "company + title; the same vacancy found by search, on an ATS board "
                            "and in another surface collapses to one canonical candidate"),
        },
    }


def collect_from_priority_watchlist(path: Path, region: str) -> dict:
    """Owner priority-watchlist findings as candidates (roster B27).

    Reads a lane export produced by ``career-ops/discovery/watchlist.py``: for each
    company on the owner's own list, the resolved official careers/ATS surface plus
    the findings of two query families (official-careers/ATS discovery and
    company-name + early-career cyber role-family research).

    Every candidate keeps the ``priority_watchlist`` flag and its watchlist
    provenance, and enters the SAME prefilter, semantic stage, deterministic gates
    and shared dedupe as every other surface. The flag makes a finding prominent;
    it never bypasses a gate, so a watchlist finding that fails the gates is
    rejected exactly like any other.

    A company whose careers infrastructure could not be resolved is reported in the
    coverage block as ``unavailable``/``unknown`` with its blocking reason — never
    as "no jobs".
    """
    try:
        doc = read_json(path)
    except Exception as exc:  # noqa: BLE001 - reported as a limitation, never fatal
        return {
            "available": False, "path": str(path), "candidates": [],
            "coverage": {"kind": "priority watchlist lane export",
                         "watchlist_present": False,
                         "limitation": f"export could not be read: {type(exc).__name__}: {exc}",
                         "note": ("an unreadable watchlist export contributes zero candidates and "
                                  "is recorded as such rather than being guessed")},
        }

    raw_candidates = doc.get("candidates") or []
    health = doc.get("companies") or []
    health_by_company = {h.get("company"): h for h in health if isinstance(h, dict)}
    candidates, excluded = [], Counter()
    per_company: dict = {}
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            excluded["malformed_candidate"] += 1
            continue
        fetch_state = raw.get("fetch_state") or "discovered_unverified"
        result_kind = raw.get("result_kind") or (raw.get("web_research") or {}).get("result_kind")
        rec = normalise_candidate(raw, SOURCE_PRIORITY_WATCHLIST)
        rec["priority_watchlist"] = True
        # The collection source is the watchlist LANE; the ATS/board the finding came from
        # stays in `discovery_surface`, so provenance is not flattened into one field.
        rec["discovery_surface"] = (raw.get("discovery_surface")
                                    or (raw.get("web_research") or {}).get("discovery_surface"))
        rec["source"] = SOURCE_PRIORITY_WATCHLIST
        rec["fetch_state"] = fetch_state
        rec["result_kind"] = result_kind
        name = raw.get("watchlist_company") or raw.get("company")
        rec["watchlist_company"] = name
        wr_block = raw.get("web_research") or {}
        rec["web_research"] = {
            "discovery_surface": wr_block.get("discovery_surface"),
            "search_query": wr_block.get("search_query"),
            "query_id": wr_block.get("query_id"),
            "query_family": wr_block.get("query_family") or raw.get("watchlist_query_family"),
            "role_family": wr_block.get("role_family"),
            "region": wr_block.get("region"),
            "result_url": wr_block.get("result_url") or raw.get("url"),
            "canonical_url": wr_block.get("canonical_url"),
            "observed": wr_block.get("observed"),
            "title_source": wr_block.get("title_source"),
            "source_timestamp": wr_block.get("source_timestamp"),
            "fetch_state": fetch_state,
            "result_kind": result_kind,
            "result_kind_reason": wr_block.get("result_kind_reason"),
            "missing_fields": wr_block.get("missing_fields"),
            "priority_watchlist": True,
            "watchlist_company": name,
        }
        rec["watchlist"] = {
            "company": name,
            "query_family": raw.get("watchlist_query_family"),
            "role_family": raw.get("watchlist_role_family"),
            "careers_source": raw.get("watchlist_careers_source"),
            "ats_family": raw.get("watchlist_ats_family"),
            "careers_url": (health_by_company.get(name) or {}).get("careers_url"),
            "careers_state": (health_by_company.get(name) or {}).get("careers_state"),
            "priority_watchlist": True,
        }
        per_company[name] = per_company.get(name, 0) + 1
        if fetch_state == "validation_failed":
            excluded["destination_not_validated_live"] += 1
        elif fetch_state == "discovered_unverified":
            excluded["destination_not_verified"] += 1
        if result_kind == "search_listing":
            excluded["search_listing_page_not_a_vacancy"] += 1
        candidates.append(rec)

    unavailable = [{"company": h.get("company"), "state": h.get("careers_state"),
                    "reason": h.get("access_blocking_reason")}
                   for h in health if h.get("careers_state") != "found"]
    findings_by_company = [{"company": h.get("company"),
                            "careers_source_found": h.get("careers_source_found"),
                            "careers_state": h.get("careers_state"),
                            "careers_url": h.get("careers_url"),
                            "ats_family": h.get("ats_family"),
                            "attribution_basis": h.get("attribution_basis"),
                            "queries_executed": h.get("queries_executed"),
                            "live_vacancies_observed": h.get("live_vacancies_observed"),
                            "findings": h.get("findings"),
                            "candidates_after_funnel": h.get("candidates_after_funnel"),
                            "access_blocking_reason": h.get("access_blocking_reason"),
                            "next_retry_at": h.get("next_retry_at"),
                            "last_checked": h.get("last_checked")}
                           for h in health]
    telemetry = doc.get("telemetry") or {}
    zero_note = None
    if not candidates and health:
        zero_note = ("zero watchlist findings in this lane export: every company's own state and "
                     "blocking reason is listed above, so the zero is attributable to the company "
                     "or the run rather than being read as 'no jobs exist'")
    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "owner priority watchlist lane export",
            "watchlist_present": True,
            "lane_id": doc.get("lane_id"),
            "region": doc.get("region"),
            "watchlist_empty": (doc.get("watchlist") or {}).get("empty"),
            "companies_in_watchlist": telemetry.get("companies_in_watchlist"),
            "companies_checked": telemetry.get("companies_checked"),
            "companies_with_careers_source": telemetry.get("companies_with_careers_source"),
            "companies_unavailable_or_unknown": telemetry.get("companies_unavailable_or_unknown"),
            "duplicate_spellings_collapsed": (doc.get("watchlist") or {}).get(
                "duplicate_spellings_collapsed"),
            "queries_executed": telemetry.get("queries_executed"),
            "live_vacancies_observed": telemetry.get("validated_live"),
            "findings_total": len(raw_candidates),
            "findings_entering_this_funnel": len(candidates),
            "findings_by_company": dict(sorted(per_company.items())),
            "findings_excluded_before_the_funnel": dict(sorted(excluded.items())),
            "companies_with_findings": findings_by_company,
            "companies_unavailable_or_unknown_detail": unavailable,
            "zero_attribution": zero_note or telemetry.get("zero_attribution"),
            "provider": doc.get("provider"),
            "note": ("the owner's own company list, resolved to careers/ATS surfaces and researched "
                     "by company name. It is ADDITIVE to broad-market discovery, never a "
                     "replacement. The priority_watchlist flag is provenance for prominence in the "
                     "brief; it never bypasses the semantic stage or the deterministic gates, and "
                     "an unresolved careers surface is reported unavailable/unknown, never "
                     "'no jobs'."),
            "match_basis": ("posting URL (tracking parameters removed) where present, else "
                            "company + title; the same vacancy found by the watchlist AND by "
                            "Company Watch or the open-web research lane collapses to one "
                            "canonical candidate carrying all surfaces' provenance"),
        },
    }


# --------------------------------------------------------------------------- #
# cross-source canonical collapse (one vacancy -> one candidate)
# --------------------------------------------------------------------------- #

def canonical_key(rec: dict) -> tuple:
    """Stable cross-source identity for a vacancy.

    Prefers the normalised posting URL (the same code the tracker dedupe uses,
    so tracking parameters cannot split a posting). Falls back to
    company + title when no URL was supplied — and then only when both are
    present, so two URL-less records are never merged on an empty key.
    """
    url = tw.normalize_url(rec.get("url"))
    if url:
        return ("url", url)
    company = tw.key_text(rec.get("company"))
    title = tw.key_text(rec.get("title"))
    if company and title:
        return ("pair", company, title)
    return ("unkeyed", candidate_id(rec))


def _field_count(rec: dict) -> int:
    return sum(1 for k in CANDIDATE_FIELDS if rec.get(k) not in (None, ""))


def collapse_candidates(candidates: list) -> dict:
    """Collapse the same vacancy discovered by several sources into one candidate.

    The canonical candidate is the richest record (most populated fields,
    earliest discovery as the tie-break); missing fields are filled from the
    other copies; and every discovery is preserved in ``provenance`` with its
    own collection surface, declared source, file and index. Nothing is
    overwritten and no field is invented.
    """
    groups: dict[tuple, list] = {}
    order: list = []
    for idx, rec in enumerate(candidates):
        key = canonical_key(rec)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((idx, rec))

    canonical, collapsed = [], []
    for key in order:
        members = groups[key]
        members_sorted = sorted(members, key=lambda t: (-_field_count(t[1]), t[0]))
        base_idx, base = members_sorted[0]
        out = {k: v for k, v in base.items()}
        out.pop("_collection_source", None)
        for _idx, other in members_sorted[1:]:
            for field in CANDIDATE_FIELDS:
                if out.get(field) in (None, "") and other.get(field) not in (None, ""):
                    out[field] = other[field]

        sources, provenance = [], []
        for idx, rec in sorted(members, key=lambda t: t[0]):
            collection_source = rec.get("_collection_source") or SOURCE_EXPLICIT
            if collection_source not in sources:
                sources.append(collection_source)
            entry = {
                "collection_source": collection_source,
                "declared_source": rec.get("_declared_source"),
                "source_detail": rec.get("source_detail"),
                "candidate_id": candidate_id(rec),
                "raw_index": idx,
            }
            if entry not in provenance:
                provenance.append(entry)
        out["sources"] = sources
        out["provenance"] = provenance
        out["duplicate_discoveries"] = len(members) - 1
        out["source"] = sources[0]
        # The owner-priority-watchlist flag survives the collapse in either
        # direction: whether the watchlist record was the richest copy or the
        # thinner one, the merged vacancy stays flagged and keeps every watchlist
        # discovery in its provenance (so a vacancy found by Company Watch AND by
        # the watchlist is one candidate that is still visibly on the owner's list).
        out["priority_watchlist"] = bool(
            base.get("priority_watchlist")
            or any(o.get("priority_watchlist") for _i, o in members_sorted[1:]))
        wl_companies = [o.get("watchlist_company") for _i, o in members_sorted
                        if o.get("watchlist_company")]
        out["watchlist_company"] = base.get("watchlist_company") or (
            wl_companies[0] if wl_companies else None)
        wl_families: list = []
        for _i, o in members_sorted:
            family = o.get("watchlist_query_family") or (o.get("web_research") or {}).get(
                "query_family")
            if o.get("priority_watchlist") and family and family not in wl_families:
                wl_families.append(family)
        if out["priority_watchlist"]:
            out["watchlist_query_families"] = wl_families
            out["priority_watchlist_provenance"] = [
                e for e in provenance if e["collection_source"] == SOURCE_PRIORITY_WATCHLIST]
        out["canonical_key"] = list(key)
        out["candidate_id"] = candidate_id(out)
        canonical.append(out)
        if len(members) > 1:
            collapsed.append({"canonical_key": list(key), "candidate_id": out["candidate_id"],
                              "company": out.get("company"), "title": out.get("title"),
                              "url": tw.extract_url(out.get("url")),
                              "discoveries": len(members), "sources": sources,
                              "duplicate_discoveries": len(members) - 1,
                              "priority_watchlist": bool(out.get("priority_watchlist")),
                              "watchlist_company": out.get("watchlist_company")})

    shared_by_source: dict = {}
    for entry in collapsed:
        for source in entry["sources"]:
            bucket = shared_by_source.setdefault(source, {"candidate_ids": [], "shared_with": {}})
            bucket["candidate_ids"].append(entry["candidate_id"])
            for other in entry["sources"]:
                if other == source:
                    continue
                bucket["shared_with"][other] = bucket["shared_with"].get(other, 0) + 1

    return {
        "engine": "discovery.pipeline.collapse_candidates (URL-normalised, then company+title)",
        "counts": {
            "raw_discoveries": len(candidates),
            "canonical_candidates": len(canonical),
            "cross_source_duplicates_removed": len(candidates) - len(canonical),
            "multi_source_canonical_candidates": len(collapsed),
        },
        "collapsed": collapsed,
        "by_source": {k: {"candidate_ids": v["candidate_ids"],
                          "shared_with": dict(sorted(v["shared_with"].items()))}
                      for k, v in sorted(shared_by_source.items())},
        "candidates": canonical,
        "note": ("one vacancy is one canonical candidate whatever combination of regional scan, "
                 "Company Watch, recruiter/intermediary watch and LinkedIn export discovered it; "
                 "every discovery is preserved in the candidate's provenance. De-duplication "
                 "here is in-run identity only and does not replace the shared tracker dedupe."),
    }


def source_contract_document() -> dict:
    """The declared contract every read-only discovery surface must satisfy."""
    return {
        "contract_version": SCHEMA_VERSION,
        "sources": dict(SOURCE_REGISTRY),
        "candidate_fields": list(CANDIDATE_FIELDS),
        "canonical_identity": [
            "normalised posting URL where one is present (tracking parameters removed by "
            "tracker_writer.normalize_url, the same code the tracker dedupe uses)",
            "company + title when no URL is present; a record with neither is never merged",
        ],
        "provenance": ("every discovery keeps its collection surface, declared source, source "
                       "detail and raw index; merging fills a missing field and never invents "
                       "or overwrites one"),
        "rules": [
            "every read-only discovery surface normalises into the one candidate schema and "
            "runs the same prefilter, semantic triage, deterministic eligibility gates and "
            "shared dedupe — no source gets its own classifier or its own eligibility rules",
            "read-only only: no login, no account/session access, no scraping, no browser or GUI "
            "automation, no posting, no messaging, no connection request, no application",
            "the same vacancy seen through several surfaces collapses to one canonical candidate, "
            "and the collapse count is reported separately from any market fact",
            "every source carries its own funnel counters, rejection reasons and first zero",
        ],
    }


def jd_gap_report(candidates: list) -> dict:
    with_jd = [c for c in candidates if jd_available(c)]
    return {
        "candidates": len(candidates),
        "with_job_description_text": len(with_jd),
        "without_job_description_text": len(candidates) - len(with_jd),
        "limitation": ("no candidate carried a job-description body, so classifications are "
                       "derived from title/company/location (and any other supplied fields) only "
                       "and are explicitly NOT semantic JD analysis"
                       if candidates and not with_jd else None),
    }


# --------------------------------------------------------------------------- #
# stage 2 — light deterministic prefilter
# --------------------------------------------------------------------------- #

def prefilter(candidates: list, *, mode: str, funnel: Funnel) -> dict:
    kept, decisions = [], []
    for rec in candidates:
        sources = rec.get("sources") or [rec.get("_collection_source") or SOURCE_EXPLICIT]
        decision = title_decision(str(rec.get("title") or ""), mode)
        entry = {"candidate_id": candidate_id(rec), "company": rec.get("company"),
                 "title": rec.get("title"), "location": rec.get("location"),
                 "mode": mode, "decision": decision["decision"], "tier": decision.get("tier"),
                 "reason": decision["reason"], "signals": decision.get("signals"),
                 "sources": sources}
        decisions.append(entry)
        if decision["decision"] == "pass":
            kept.append(rec)
            funnel.source_stages(sources, "after_hard_negative_prefilter")
        else:
            reason = (("tier_b_hard_negative: " if decision.get("tier") == "B"
                       else "tier_a_no_recall_signal: ") + decision["reason"])
            funnel.reject(reason, sources=sources)
    funnel.set("after_hard_negative_prefilter", len(kept))
    return {"mode": mode, "counts": {"input": len(candidates), "kept": len(kept),
                                     "removed": len(candidates) - len(kept)},
            "decisions": decisions}


# --------------------------------------------------------------------------- #
# stage 5 — deterministic eligibility gates (authoritative)
# --------------------------------------------------------------------------- #

def deterministic_gates(region: str, rec: dict, policy: dict, scope: dict) -> dict:
    """Region/location, work authorisation, clearance, experience and URL validity.

    These gates run AFTER semantic classification and cannot be overridden by a
    model: a title/AI verdict never substitutes for them.
    """
    rp = rjs.region_policy(region, policy)
    reasons: list = []
    flags: list = []

    url = tw.extract_url(rec.get("url"))
    if not url or not url.lower().startswith(("http://", "https://")):
        reasons.append("no usable application URL — a posting without a URL is not writable state")
    else:
        flags.append("application URL present")

    # Fail-closed validation gate (source-agnostic): a surface that declares a
    # fetch/validation state may only reach the tracker when its destination was
    # actually validated live. A surface that declares no fetch_state (the
    # regional scan, Company Watch, …) is unaffected.
    fetch_state = rec.get("fetch_state")
    if fetch_state and fetch_state != "validated_live":
        reasons.append(f"source URL not validated live (fetch_state={fetch_state}) — a "
                       f"discovered-but-unverified or failed destination is never written")

    # Fail-closed result-kind gate (source-agnostic): a discovery result that a
    # surface declares to be a search/listing page is not a vacancy posting, so it
    # can never be written as one. A surface that declares no result_kind is
    # unaffected.
    if rec.get("result_kind") == "search_listing":
        reasons.append("discovery result is a search/listing page, not a vacancy posting — "
                       "a search result page is never written as a job")

    hits = tier_b_hits(str(rec.get("title") or ""))
    if hits:
        reasons.append(f"tier B hard negative re-check: {', '.join(hits)}")

    if not scope:
        reasons.append("region location scope unavailable (lane config missing) — refusing to "
                       "accept records that cannot be region-checked")
        return {"decision": "rejected", "reasons": reasons, "flags": flags,
                "work_authorisation": rjs._work_auth_block(rp)}

    ok, why = rjs.location_matches(scope, rec.get("location"), rec.get("title"), url,
                                   require_explicit_region=(region != "uk"))
    if ok:
        flags.append(why)
    else:
        reasons.append(why)

    blob = " ".join(str(rec.get(k) or "") for k in
                    ("title", "company", "location", "summary", "description"))
    clearance = rjs.clearance_hits(blob)
    if clearance:
        reasons.append(f"clearance/citizenship requirement stated: {', '.join(clearance)}")

    exp = rec.get("experience_required")
    if isinstance(exp, (int, float)) and exp >= 2:
        reasons.append(f"states {exp} years of required experience; owner targets entry level")
    elif isinstance(exp, str) and rjs.re.search(r"\b([2-9]|1[0-9])\+?\s*(?:years|yrs)\b", exp,
                                                rjs.re.IGNORECASE):
        reasons.append(f"states a multi-year experience requirement ('{exp}')")

    work_auth = rjs._work_auth_block(rp)
    if work_auth["status"] == "UNKNOWN":
        flags.append(f"work authorisation for {rp['display_name']} is UNKNOWN — no owner-stated "
                     "right to work; visa pathway must be verified by the owner")
    return {"decision": "rejected" if reasons else "accepted", "reasons": reasons,
            "flags": flags, "work_authorisation": work_auth}


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def _semantic_stage(candidates: list, *, semantic: str, deepseek_model: str,
                    batch_size: int, timeout: int, mode: str,
                    max_tokens: int | None = None,
                    deepseek_adapter=None) -> dict:
    max_tokens = max_tokens or DEFAULT_MAX_TOKENS
    if semantic == "off":
        return {"provider": "none", "requested": "off",
                "limitation": "semantic stage disabled by the caller",
                "classifications": {}, "probe": None}
    if semantic in ("auto", "deepseek"):
        probe = deepseek_probe(deepseek_model)
        if probe["available"]:
            doc = deepseek_bulk_classify(candidates, model=deepseek_model,
                                         batch_size=batch_size, timeout=timeout,
                                         max_tokens=max_tokens,
                                         adapter=deepseek_adapter, mode=mode)
            doc["requested"] = semantic
            doc["probe"] = probe
            if doc.get("classifications"):
                return doc
            fallback = {candidate_id(c): deterministic_classify(c, mode=mode) for c in candidates}
            return {"provider": "none", "requested": semantic, "probe": probe,
                    "classifications": fallback,
                    "limitation": ("deepseek answered but produced no usable classifications; "
                                   "the declared deterministic rule classifier was used "
                                   "instead — this is NOT a model pass"),
                    "deepseek_attempt": {k: doc.get(k) for k in
                                         ("requests", "errors", "limitation", "usage")}}
        if semantic == "deepseek":
            raise SystemExit("--semantic deepseek requested but the provider is not healthy: "
                             + str(probe.get("reason")))
        fallback = {candidate_id(c): deterministic_classify(c, mode=mode) for c in candidates}
        return {"provider": "none", "requested": semantic, "probe": probe,
                "classifications": fallback,
                "limitation": (f"deepseek unavailable ({probe.get('status')}: "
                               f"{probe.get('reason')}); the declared deterministic rule "
                               "classifier was used instead — this is NOT a model pass")}
    if semantic == "deterministic":
        return {"provider": "none", "requested": semantic, "probe": None,
                "limitation": "deterministic rule classifier selected by the caller",
                "classifications": {candidate_id(c): deterministic_classify(c, mode=mode)
                                    for c in candidates}}
    raise SystemExit(f"unknown semantic provider '{semantic}'")


def run_funnel(candidates: list, *, region: str, mode: str, semantic: str,
               deepseek_model: str, batch_size: int, codex_budget: int,
               codex_enabled: bool, timeout: int, run_id: str,
               max_tokens: int | None = None,
               deepseek_adapter=None, codex_adapter=None,
               codex_workdir: str | None = None,
               collection: list | None = None) -> dict:
    policy = rjs.load_policy()
    schedules = rjs.load_schedules()
    profiles = tw.load_profiles()
    funnel = Funnel()
    for src, n in _source_counts(collection or []).items():
        funnel.discover(src, n)

    for note in _coverage_notes(collection or []):
        funnel.note(note)

    # 0. cross-source canonical collapse ----------------------------------- #
    # The same vacancy discovered by several read-only surfaces is ONE candidate
    # before anything else runs. Raw discovery counts stay raw (each source's own
    # count), and the collapse is reported separately so a de-duplication is never
    # presented as a market fact.
    collapse = collapse_candidates(candidates)
    canonical = collapse["candidates"]
    funnel.set("canonical_candidates", collapse["counts"]["canonical_candidates"])
    funnel.set("cross_source_duplicates_removed",
               collapse["counts"]["cross_source_duplicates_removed"])
    funnel.shared_candidates = {k: v for k, v in collapse.items()
                               if k in ("counts", "collapsed", "by_source")}
    if collapse["counts"]["cross_source_duplicates_removed"]:
        funnel.note(f"cross-source collapse: {collapse['counts']['raw_discoveries']} raw "
                    f"discoveries -> {collapse['counts']['canonical_candidates']} canonical "
                    f"candidates ({collapse['counts']['cross_source_duplicates_removed']} "
                    f"duplicate discoveries of an already-canonical vacancy)")
    candidates = canonical
    for rec in candidates:
        funnel.source_stages(rec.get("sources"), "canonical")

    # 1. prefilter --------------------------------------------------------- #
    pre = prefilter(candidates, mode=mode, funnel=funnel)
    kept = [c for c, d in zip(candidates, pre["decisions"]) if d["decision"] == "pass"]

    # 2. semantic ----------------------------------------------------------- #
    semantic_doc = _semantic_stage(kept, semantic=semantic, deepseek_model=deepseek_model,
                                   batch_size=batch_size, timeout=timeout, mode=mode,
                                   max_tokens=max_tokens, deepseek_adapter=deepseek_adapter)
    classifications = semantic_doc.get("classifications") or {}
    funnel.set("semantically_reviewed", len(classifications))
    for rec in kept:
        funnel.source_stages(rec.get("sources"), "semantically_reviewed")
    for cls in classifications.values():
        if not cls.get("valid"):
            funnel.reject("semantic_contract_guard_rejected: "
                          + "; ".join(cls.get("guard", {}).get("violations", [])[:2]))
    if semantic_doc.get("requested") == "off":
        # No semantic triage was requested: the prefiltred candidates go straight to the
        # deterministic gates, and the semantic counters are marked not-applicable rather
        # than reported as the place the funnel died.
        accepted = list(kept)
        funnel.skip("semantically_reviewed",
                    "semantic stage disabled by the caller (--semantic off)")
        funnel.skip("deepseek_accept",
                    "semantic stage disabled by the caller (--semantic off)")
        funnel.set("deepseek_accept", 0)
        funnel.source_skip("semantically_reviewed",
                           "semantic stage disabled by the caller (--semantic off)")
        funnel.source_skip("semantic_accept",
                           "semantic stage disabled by the caller (--semantic off)")
    else:
        accepted = [c for c in kept if classifications.get(candidate_id(c), {}).get("accepted")]
        if semantic_doc.get("provider") == "deepseek":
            funnel.set("deepseek_accept", len(accepted))
        else:
            funnel.set("deepseek_accept", 0)
            funnel.skip("deepseek_accept",
                        f"no DeepSeek pass was made in this run (provider: "
                        f"{semantic_doc.get('provider')}); the declared deterministic rule "
                        "classifier or an explicit provider choice was used instead")

    # 3. bounded Codex second pass ------------------------------------------ #
    codex_doc = {"provider": "openai-codex-cli", "requested": codex_enabled, "requests": 0,
                 "classifications": {}, "limitation": "codex escalation disabled by the caller",
                 "escalated": [], "dropped_due_to_budget": []}
    if codex_enabled:
        codex_doc = codex_escalate(kept, classifications, budget=codex_budget,
                                   timeout=timeout, adapter=codex_adapter,
                                   workdir=codex_workdir)
        codex_cls = codex_doc.get("classifications") or {}
        effective = dict(classifications)
        effective.update(codex_cls)
        classifications = effective
        accepted = [c for c in kept if classifications.get(candidate_id(c), {}).get("accepted")]
    funnel.set("codex_escalated", len(codex_doc.get("escalated") or []))
    funnel.set("codex_accept", sum(1 for c in accepted
                                   if classifications.get(candidate_id(c), {}).get("classifier")
                                   == "codex_second_pass"))
    if not codex_enabled:
        funnel.skip("codex_escalated", "Codex escalation disabled by the caller (--codex off)")
        funnel.skip("codex_accept", "Codex escalation disabled by the caller (--codex off)")
    elif not codex_doc.get("eligible_for_escalation"):
        funnel.skip("codex_escalated",
                    "no candidate met the deterministic escalation conditions, so no Codex "
                    "call was made (see codex.limitation)")
        funnel.skip("codex_accept", "no Codex second pass was run in this run")
    for rec in accepted:
        funnel.source_stages(rec.get("sources"), "semantic_accept")

    # 4. deterministic gates ------------------------------------------------ #
    scope = rjs.lane_scope(region, schedules["regions"][region])
    if semantic_doc.get("requested") != "off":
        for rec in kept:
            cls = classifications.get(candidate_id(rec)) or {}
            if not cls.get("accepted"):
                funnel.reject(f"semantic_label: {cls.get('primary_label') or 'unclassified'}"
                              f" ({cls.get('classifier') or 'no classifier'})",
                              sources=rec.get("sources"))
    if not accepted:
        funnel.explain(
            "deterministic_eligibility_pass",
            "no candidate was left accepted by the semantic stage (DeepSeek bulk pass, plus any "
            "Codex second pass) — so no candidate reached the deterministic gates; see the "
            "classification labels and rejections_by_reason for the per-candidate reason")
    gated = []
    for rec in accepted:
        verdict = deterministic_gates(region, rec, policy, scope)
        sources = rec.get("sources")
        entry = {"candidate_id": candidate_id(rec), "company": rec.get("company"),
                 "title": rec.get("title"), "location": rec.get("location"),
                 "url": rec.get("url"), "sources": sources, "semantic_label":
                     classifications.get(candidate_id(rec), {}).get("primary_label"),
                 "priority_watchlist": bool(rec.get("priority_watchlist")),
                 "watchlist_company": rec.get("watchlist_company"),
                 **verdict}
        gated.append(entry)
        if verdict["decision"] != "accepted":
            for reason in verdict["reasons"]:
                funnel.reject("deterministic_gate: " + reason, sources=sources)
        else:
            funnel.source_stages(sources, "deterministic_eligibility_pass")
    passed = [g for g in gated if g["decision"] == "accepted"]
    funnel.set("deterministic_eligibility_pass", len(passed))

    # 5. shared dedupe ------------------------------------------------------ #
    records = []
    for entry in passed:
        rec = next((c for c in accepted if candidate_id(c) == entry["candidate_id"]), None)
        if rec is None:
            continue
        records.append(rjs.build_record(region, rec, policy, run_id, {"stage": "discovery"}))
    probe = tw.write_records(profiles, region, records, apply=False) if records else (
        {"tracker": str(tw.region_config(profiles, region)["tracker"]), "counts": {},
         "cross_month_index": {}, "outcomes": [], "applied": False})
    counts = probe.get("counts") or {}
    duplicates = sum(v for k, v in counts.items() if k in ("duplicates", "duplicate",
                                                           "duplicate-cross-month"))
    funnel.set("duplicates_removed", int(duplicates or 0))
    new_rows = [o for o in probe.get("outcomes", []) if o.get("decision") == "appended"]
    funnel.set("tracker_candidates", len(new_rows))
    outcome_sources = {e["candidate_id"]: e.get("sources") for e in passed}
    src_by_url = {tw.normalize_url(e.get("url")): e.get("sources") for e in passed
                  if tw.normalize_url(e.get("url"))}
    src_by_pair = {tw.pair_key(e.get("company"), e.get("title")): e.get("sources")
                   for e in passed if str(tw.pair_key(e.get("company"), e.get("title"))).strip("|")}

    def _outcome_sources(outcome: dict):
        url_key = tw.normalize_url(outcome.get("url"))
        if url_key and url_key in src_by_url:
            return src_by_url[url_key]
        return src_by_pair.get(tw.pair_key(outcome.get("company"), outcome.get("title"))) \
            or outcome_sources.get(outcome.get("candidate_id"))

    for outcome in probe.get("outcomes", []):
        sources_for_outcome = _outcome_sources(outcome)
        if outcome.get("decision") != "appended":
            funnel.reject("dedupe: " + str(outcome.get("reason") or outcome.get("decision")),
                          sources=sources_for_outcome)
        else:
            funnel.source_stages(sources_for_outcome, "tracker_candidates")

    return {
        "run_id": run_id,
        "region": region,
        "title_policy_mode": mode,
        "semantic": {k: v for k, v in semantic_doc.items() if k != "classifications"},
        "codex": {k: v for k, v in codex_doc.items() if k != "classifications"},
        "prefilter": {"counts": pre["counts"], "mode": pre["mode"]},
        "cross_source_dedupe": {
            "engine": collapse["engine"],
            "counts": collapse["counts"],
            "collapsed": collapse["collapsed"],
            "by_source": collapse["by_source"],
            "note": collapse["note"],
        },
        "canonical_candidates": [
            {k: c.get(k) for k in ("candidate_id", "company", "title", "location", "url",
                                   "source", "sources", "duplicate_discoveries",
                                   "canonical_key", "provenance", "fetch_state", "result_kind",
                                   "priority_watchlist", "watchlist_company",
                                   "watchlist_query_families")}
            for c in candidates
        ],
        "priority_watchlist": priority_watchlist_block(candidates, passed),
        "source_registry": dict(SOURCE_REGISTRY),
        "classifications": [classifications[candidate_id(c)] for c in kept
                            if candidate_id(c) in classifications],
        "eligibility": {"input": len(accepted), "decisions": gated,
                        "passed": len(passed)},
        "dedupe": {"engine": "career-ops/tracker_writer.py (shared with Career Ops)",
                   "tracker": probe.get("tracker"), "counts": counts,
                   "cross_month_index": probe.get("cross_month_index"),
                   "outcomes": probe.get("outcomes", [])[:25], "applied": False},
        "funnel": funnel.document(),
        "jd_gap": jd_gap_report(candidates),
        "collection": collection or [],
        "safety": {
            "canonical_workbook_written": False,
            "applications_submitted": 0,
            "employer_contacts": 0,
            "browser_used": False,
            "handoff": "manifest only; applying stays career_ops_cli.py write --apply",
        },
    }


def _source_counts(collection: list) -> Counter:
    out: Counter = Counter()
    for block in collection:
        out[block.get("source") or "unknown"] += len(block.get("candidates") or [])
    return out


def _coverage_notes(collection: list) -> list:
    notes = []
    for block in collection:
        cov = block.get("coverage") or {}
        notes.append(f"source {block.get('source')}: {json.dumps(cov, ensure_ascii=False)}")
    return notes


def priority_watchlist_block(candidates: list, passed: list) -> dict:
    """The owner-priority-watchlist view of a funnel run.

    Deliberately a *report*, not an override: it lists which canonical candidates
    came from the owner's own company list, whether each one survived the
    deterministic gates, and how the flag behaved through the cross-source collapse.
    The flag grants prominence in the Chief/Career brief and nothing else — no
    candidate is accepted, promoted or written because it is on the watchlist.
    """
    flagged = [c for c in candidates if c.get("priority_watchlist")]
    passed_ids = {e["candidate_id"] for e in passed}
    accepted = [e for e in passed if e.get("priority_watchlist")]
    merged = [c for c in flagged if c.get("duplicate_discoveries")]
    return {
        "declared": bool(flagged),
        "counts": {
            "canonical_candidates": len(flagged),
            "deterministic_eligibility_pass": len(accepted),
            "also_found_by_another_surface": len(merged),
        },
        "companies": sorted({c.get("watchlist_company") for c in flagged
                             if c.get("watchlist_company")}),
        "query_families": sorted({f for c in flagged
                                  for f in (c.get("watchlist_query_families") or [])}),
        "candidates": [{
            "candidate_id": c.get("candidate_id"), "company": c.get("company"),
            "title": c.get("title"), "location": c.get("location"), "url": c.get("url"),
            "watchlist_company": c.get("watchlist_company"),
            "sources": c.get("sources"),
            "duplicate_discoveries": c.get("duplicate_discoveries"),
            "threshold_passed": c.get("candidate_id") in passed_ids,
            "state": ("reached the deterministic gates" if c.get("candidate_id") in passed_ids
                      else "did not reach the deterministic gates (see the funnel counters and "
                           "rejections_by_reason for the stage that refused it)"),
        } for c in flagged],
        "note": ("the priority_watchlist flag is provenance from the owner's own company list. It "
                 "makes a finding prominent in the brief and it NEVER bypasses the semantic stage "
                 "or the deterministic eligibility gates; an absent block means the owner's "
                 "watchlist did not run in this funnel, which is not a statement about the market"),
    }


# --------------------------------------------------------------------------- #
# compare modes
# --------------------------------------------------------------------------- #

def compare_modes(candidates: list, *, region: str, semantic: str,
                  deepseek_model: str, batch_size: int, timeout: int,
                  deepseek_adapter=None) -> dict:
    """Old strict intern-only policy vs the new high-recall pipeline.

    Runs over the SAME candidate set. Never writes a canonical tracker: no
    manifest, no dedupe probe, no workbook access beyond reading the region
    config for scope.
    """
    policy = rjs.load_policy()
    schedules = rjs.load_schedules()
    scope = rjs.lane_scope(region, schedules["regions"][region])
    results = {}
    for mode in (MODE_INTERN_ONLY, MODE_HIGH_RECALL):
        rows = []
        for rec in candidates:
            title_gate = title_decision(str(rec.get("title") or ""), mode)
            gates = deterministic_gates(region, rec, policy, scope)
            rows.append({
                "candidate_id": candidate_id(rec), "company": rec.get("company"),
                "title": rec.get("title"), "location": rec.get("location"),
                "title_decision": title_gate["decision"], "title_tier": title_gate.get("tier"),
                "title_reason": title_gate["reason"],
                "deterministic_decision": gates["decision"], "gate_reasons": gates["reasons"],
                "would_reach_tracker": bool(title_gate["decision"] == "pass"
                                            and gates["decision"] == "accepted"),
            })
        results[mode] = {
            "title_pass": sum(1 for r in rows if r["title_decision"] == "pass"),
            "title_reject": sum(1 for r in rows if r["title_decision"] != "pass"),
            "would_reach_tracker": sum(1 for r in rows if r["would_reach_tracker"]),
            "rows": rows,
        }

    old, new = results[MODE_INTERN_ONLY], results[MODE_HIGH_RECALL]
    old_pass = {r["candidate_id"] for r in old["rows"] if r["title_decision"] == "pass"}
    new_pass = {r["candidate_id"] for r in new["rows"] if r["title_decision"] == "pass"}
    regained = [r for r in new["rows"]
                if r["candidate_id"] in (new_pass - old_pass)]
    regressed = [r for r in new["rows"]
                 if r["candidate_id"] in (old_pass - new_pass)]
    delta = {
        "title_pass_delta": new["title_pass"] - old["title_pass"],
        "tracker_candidate_delta": (new["would_reach_tracker"] - old["would_reach_tracker"]),
        "recall_regained_titles": [{"candidate_id": r["candidate_id"], "company": r["company"],
                                    "title": r["title"],
                                    "deterministic_decision": r["deterministic_decision"],
                                    "gate_reasons": r["gate_reasons"]} for r in regained],
        "recall_lost_titles": [{"candidate_id": r["candidate_id"], "title": r["title"],
                                "reason": r["title_reason"]} for r in regressed],
        "note": ("titles regained by high-recall are only 'recall' if the deterministic gates "
                 "also pass; both counts are reported separately so a title-policy delta is "
                 "never presented as a tracker delta"),
    }

    semantic_doc = {"requested": semantic}
    if semantic in ("deepseek", "auto"):
        doc = _semantic_stage([r for r in candidates
                               if title_decision(str(r.get("title") or ""),
                                                 MODE_HIGH_RECALL)["decision"] == "pass"],
                              semantic="auto" if semantic == "auto" else "deepseek",
                              deepseek_model=deepseek_model, batch_size=batch_size,
                              timeout=timeout, mode=MODE_HIGH_RECALL,
                              deepseek_adapter=deepseek_adapter)
        semantic_doc = {k: v for k, v in doc.items() if k != "classifications"}
        semantic_doc["labels"] = dict(Counter(
            c.get("primary_label") for c in (doc.get("classifications") or {}).values()))

    return {
        "region": region,
        "candidate_set": {"candidates": len(candidates)},
        "modes": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in results.items()},
        "recall_delta": delta,
        "semantic": semantic_doc,
        "safety": {"canonical_workbook_written": False, "manifest_written": False,
                   "tracker_probe_run": False, "applications_submitted": 0},
    }


# --------------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------------- #

FIXTURE_PATH = CAREER_OPS / "tests" / "fixtures" / "discovery" / "title-fixtures.json"


def load_fixtures(path: Path | None = None) -> dict:
    return read_json(Path(path or FIXTURE_PATH))


def selftest(path: Path | None = None) -> dict:
    fixtures = load_fixtures(path)
    rows, failures = [], []
    for entry in fixtures["titles"]:
        decision = title_decision(entry["title"], entry["mode"] if "mode" in entry
                                  else MODE_HIGH_RECALL)
        expected = entry["expect"]
        ok = decision["decision"] == expected
        rows.append({"title": entry["title"], "expected": expected,
                     "decision": decision["decision"], "tier": decision.get("tier"),
                     "reason": decision["reason"], "family": entry.get("family"),
                     "ok": ok})
        if not ok:
            failures.append({"title": entry["title"], "expected": expected,
                             "got": decision["decision"], "reason": decision["reason"]})
    return {"fixtures": str(path or FIXTURE_PATH), "counts": {"total": len(rows),
                                                             "passed": len(rows) - len(failures),
                                                             "failed": len(failures)},
            "failures": failures, "rows": rows, "ok": not failures}


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_policy(args) -> int:
    emit({"generated_at": now_utc(), "title_policy": policy_document(),
          "semantic_contract": contract_document(),
          "codex_budget_default": DEFAULT_CODEX_BUDGET,
          "deepseek_batch_size_default": DEFAULT_BATCH_SIZE,
          "source_registry": dict(SOURCE_REGISTRY),
          "source_contract": source_contract_document(),
          "deepseek_probe": deepseek_probe(args.model)})
    return 0


def cmd_selftest(args) -> int:
    doc = selftest(args.fixtures)
    emit(doc)
    return 0 if doc["ok"] else 1


MAX_CLASSIFICATIONS_IN_RUN = 200


def collect_sources(args) -> list:
    """Build the ordered collection blocks for one run from the CLI sources.

    Every read-only discovery surface is collected through the same normaliser
    and the same declared collection-block shape, so the rest of the funnel does
    not need to know which surface produced a candidate.
    """
    collection: list = []
    if getattr(args, "records", None):
        block = collect_from_records(Path(args.records))
        block["source"] = SOURCE_EXPLICIT
        collection.append(block)
    if getattr(args, "scan_record", None):
        block = collect_from_scan_record(Path(args.scan_record))
        block["source"] = SOURCE_SCAN_RECORD
        collection.append(block)
    if getattr(args, "company_watch", None):
        block = collect_from_company_watch(Path(args.company_watch), args.region)
        block["source"] = SOURCE_COMPANY_WATCH
        collection.append(block)
    if getattr(args, "recruiter_watch", None):
        block = collect_from_recruiter_watch(Path(args.recruiter_watch), args.region)
        block["source"] = SOURCE_RECRUITER_WATCH
        collection.append(block)
    if getattr(args, "linkedin", None):
        block = collect_from_linkedin(Path(args.linkedin), args.region)
        block["source"] = SOURCE_LINKEDIN_EXPORT
        collection.append(block)
    if getattr(args, "web_research", None):
        block = collect_from_web_research(Path(args.web_research), args.region)
        block["source"] = SOURCE_WEB_RESEARCH
        collection.append(block)
    if getattr(args, "priority_watchlist", None):
        block = collect_from_priority_watchlist(Path(args.priority_watchlist), args.region)
        block["source"] = SOURCE_PRIORITY_WATCHLIST
        collection.append(block)
    return collection


def cmd_run(args) -> int:
    run_id = f"discovery-{args.region}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    collection = collect_sources(args)
    candidates = [c for b in collection for c in b["candidates"]]
    if not collection:
        emit({"ok": False, "reason": "no candidate source supplied; pass --records, "
                                     "--scan-record, --company-watch, --recruiter-watch, "
                                     "--linkedin, --web-research or --priority-watchlist",
              "run_id": run_id, "region": args.region})
        return 2

    total_candidates = sum(len(b["candidates"]) for b in collection)
    if total_candidates > args.max_candidates:
        remaining = args.max_candidates
        for block in collection:
            block.setdefault("coverage", {})["candidates_before_max_candidate_limit"] = len(block["candidates"])
            block["candidates"] = block["candidates"][:max(0, remaining)]
            remaining -= len(block["candidates"])
        candidates = [c for b in collection for c in b["candidates"]]
        collection.append({"source": "run limits", "candidates": [],
                           "coverage": {"max_candidates": args.max_candidates,
                                        "candidates_before_limit": total_candidates,
                                        "candidates_after_limit": len(candidates),
                                        "note": ("the funnel counters below describe the limited "
                                                 "candidate set actually processed; the pre-limit "
                                                 "count is recorded here so a limit is never "
                                                 "presented as a market fact")}})

    doc = run_funnel(candidates, region=args.region, mode=args.title_mode,
                     semantic=args.semantic, deepseek_model=args.model,
                     batch_size=args.batch_size, codex_budget=args.codex_budget,
                     codex_enabled=(args.codex != "off"), timeout=args.timeout,
                     run_id=run_id, codex_workdir=str(args.workdir or CONTROL_PLANE),
                     max_tokens=args.max_tokens, collection=collection)
    doc["schema_version"] = SCHEMA_VERSION
    doc["started_at"] = None
    doc["finished_at"] = now_utc()
    doc["policy_sha256"] = policy_document()["policy_sha256"]
    doc["contract_version"] = contract_document()["contract_version"]
    doc["summary_line"] = _summary_line(doc)
    if len(doc["classifications"]) > MAX_CLASSIFICATIONS_IN_RUN:
        doc["classifications_truncated"] = len(doc["classifications"])
        doc["classifications"] = doc["classifications"][:MAX_CLASSIFICATIONS_IN_RUN]
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_RUNTIME_DIR
    health_path = out_dir / f"{run_id}.json"
    latest = out_dir / "latest.json"
    write_json_atomic(health_path, doc)
    write_json_atomic(latest, doc)
    doc["run_health_file"] = str(health_path)
    if args.manifest_out:
        records = [rjs.build_record(args.region, c, rjs.load_policy(), run_id,
                                    {"stage": "discovery-manifest"})
                   for c in candidates
                   if c.get("url") and candidate_id(c) in
                   {d["candidate_id"] for d in doc["eligibility"]["decisions"]
                    if d["decision"] == "accepted"}]
        write_json_atomic(Path(args.manifest_out),
                          {"schema_version": 1, "generated_at": now_utc(),
                           "region": args.region, "run_id": run_id,
                           "records": records})
        doc["manifest_written_to"] = str(args.manifest_out)
    emit(doc)
    return 0


def _summary_line(doc: dict) -> str:
    c = doc["funnel"]["counts"]
    head = (f"discovered_raw={c['discovered_raw']} "
            f"canonical_candidates={c['canonical_candidates']} "
            f"cross_source_duplicates_removed={c['cross_source_duplicates_removed']} "
            f"after_hard_negative_prefilter={c['after_hard_negative_prefilter']} "
            f"semantically_reviewed={c['semantically_reviewed']} "
            f"deepseek_accept={c['deepseek_accept']} "
            f"codex_escalated={c['codex_escalated']} codex_accept={c['codex_accept']} "
            f"deterministic_eligibility_pass={c['deterministic_eligibility_pass']} "
            f"duplicates_removed={c['duplicates_removed']} "
            f"tracker_candidates={c['tracker_candidates']}")
    zeros = [f"{src}:{entry['zero_attribution']['first_zero_stage']}"
             for src, entry in sorted((doc["funnel"].get("by_source") or {}).items())
             if entry["zero_attribution"].get("first_zero_stage")]
    per_source = (" :: per-source zeroes " + ", ".join(zeros)) if zeros else ""
    z = doc["funnel"]["zero_attribution"]
    if z.get("first_zero_stage"):
        return (f"{head}{per_source} :: funnel first reached zero at "
                f"{z['first_zero_stage']} ({z['reason']})")
    return head + per_source


def cmd_compare(args) -> int:
    candidates = [c for b in collect_sources(args) for c in b["candidates"]]
    if not candidates:
        emit({"ok": False, "reason": "no candidate source supplied"})
        return 2
    doc = compare_modes(candidates, region=args.region,
                        semantic=("none" if args.semantic == "off" else args.semantic),
                        deepseek_model=args.model, batch_size=args.batch_size,
                        timeout=args.timeout)
    doc["generated_at"] = now_utc()
    if args.out_dir:
        write_json_atomic(Path(args.out_dir) / "compare-modes-latest.json", doc)
    emit(doc)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="High-recall multi-stage Career discovery pipeline")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("policy")
    p.add_argument("--model", default="deepseek-flash")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("selftest")
    p.add_argument("--fixtures")
    p.set_defaults(fn=cmd_selftest)

    p = sub.add_parser("run")
    p.add_argument("--region", required=True)
    p.add_argument("--records")
    p.add_argument("--scan-record")
    p.add_argument("--company-watch")
    p.add_argument("--recruiter-watch",
                   help="read-only recruiter/intermediary watch findings export (B11)")
    p.add_argument("--linkedin",
                   help="read-only owner-exported LinkedIn job-discovery file (B19)")
    p.add_argument("--web-research",
                   help="open-web research export from discovery/web_research.py (B26)")
    p.add_argument("--priority-watchlist",
                   help=("owner priority watchlist lane export from "
                         "discovery/watchlist.py (B27) — additive to the market search"))
    p.add_argument("--title-mode", choices=list(MODES), default=DEFAULT_MODE)
    p.add_argument("--semantic", choices=("auto", "deepseek", "deterministic", "off"),
                   default=DEFAULT_SEMANTIC)
    p.add_argument("--codex", choices=("on", "off"), default="on")
    p.add_argument("--codex-budget", type=int, default=DEFAULT_CODEX_BUDGET)
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                   help="completion budget per bulk request (a reasoning model can otherwise "
                        "return an empty response after spending the whole budget on reasoning)")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--max-candidates", type=int, default=400)
    p.add_argument("--out-dir")
    p.add_argument("--manifest-out")
    p.add_argument("--workdir")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("compare-modes")
    p.add_argument("--region", required=True)
    p.add_argument("--records")
    p.add_argument("--scan-record")
    p.add_argument("--company-watch")
    p.add_argument("--recruiter-watch")
    p.add_argument("--linkedin")
    p.add_argument("--web-research")
    p.add_argument("--priority-watchlist")
    p.add_argument("--semantic", choices=("off", "auto", "deepseek"), default="off")
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_compare)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
