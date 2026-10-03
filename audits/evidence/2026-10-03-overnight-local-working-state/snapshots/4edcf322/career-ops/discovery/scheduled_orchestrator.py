#!/usr/bin/env python3
"""Unified scheduled Career discovery orchestrator (the real scheduled path).

Why this exists
---------------
Before this module the Windows scheduled tasks (`ChiefCareerScan-UK`/`-Dubai`/
`-Japan`/`-Singapore`) ran ``career-ops/regional_job_search.py run --scheduled``
alone. That worker reads the owner's Career Ops lane, whose title filter is the
Intern/Internship-only rule: used as the *sole discovery gate* it returns zero
whenever no internship is posted, which is the false-zero the owner reported.

This orchestrator makes the new research architecture the actual scheduled
behaviour. One bounded, read-only, dry-run pass per region combines:

    structured regional provider scan   (regional_job_search.py, unchanged worker)
    open-web / Codex-style research     (web_research.py query matrix + live provider)
    Company Watch findings              (existing findings export, or a bounded run)
    priority company watchlist findings (watchlist lane export, owner list optional)
    recruiter/intermediary watch export (B11, when present)
    LinkedIn job-discovery export       (B19, when present)

and feeds them into ONE unified funnel (the existing discovery pipeline), then
writes one unified candidate manifest and one unified funnel document.

Non-negotiable truthful behaviour
---------------------------------
* High-recall (``high_recall``) is the production discovery policy. The owner's
  Intern/Internship-only rule is preserved **only** as an explicit diagnostic
  compare mode (``intern_only``) and is never the scheduled discovery gate.
* ``--require-live-web`` (used by the scheduled launcher) refuses to declare the
  lane production-ready when no current-web search mechanism is operational. The
  run still completes truthfully from the non-web sources and exits 3 with the
  blocker recorded; it never silently falls back to fixtures.
* Every configured source class (public LinkedIn Jobs, public Indeed, Google /
  web-indexed discovery, direct ATS/employer careers) is recorded as
  ``reached`` / ``blocked`` / ``unavailable`` / ``not_applicable`` (plus the
  truthful refinement ``searched_no_results``) from real evidence only. A source
  that was inaccessible or blocked is never reported as empty.
* Discovered URLs keep the pipeline's own fetch states, so validated-live,
  discovered-unverified and inaccessible destinations stay separated with live
  verification timestamps.
* Nothing is written outside ``runtime/career-ops/discovery`` (plus the git-ignored
  runtime exports of the lanes it invokes). No canonical tracker write, no
  application, no outreach, no LinkedIn mutation, no login, no browser/GUI.

Usage
-----
  python career-ops/discovery/scheduled_orchestrator.py policy
  python career-ops/discovery/scheduled_orchestrator.py run --region uk --scheduled
  python career-ops/discovery/scheduled_orchestrator.py run-all --scheduled
  python career-ops/discovery/scheduled_orchestrator.py run --region uk --no-live \
      --provider captured --captured <export.json> --no-validate   # offline replay
  python career-ops/discovery/scheduled_orchestrator.py run --region uk \
      --mode intern_only --compare        # diagnostic compare mode only
  python career-ops/discovery/scheduled_orchestrator.py coverage
  python career-ops/discovery/scheduled_orchestrator.py status

Rollback
--------
The previous behaviour is one command and stays available:
  python career-ops/regional_job_search.py run --region <region> --scheduled --timeout 1800 \
      --record runtime/career-ops/scan-runs
and ``run_scheduled_scan.cmd`` documents how to point the launcher back at it.
See ``career-ops/scheduled_orchestrator.md``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

DISCOVERY_DIR = Path(__file__).resolve().parent
CAREER_OPS_DIR = DISCOVERY_DIR.parent
CONTROL_PLANE = CAREER_OPS_DIR.parent

for _p in (str(CAREER_OPS_DIR), str(DISCOVERY_DIR), str(CONTROL_PLANE / "company-watch"),
           str(CONTROL_PLANE / "exec-brain")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pipeline  # noqa: E402
import regional_job_search as rjs  # noqa: E402
import tracker_writer as tw  # noqa: E402
import web_research as wr  # noqa: E402
from funnel import COUNT_KEYS, STAGE_ORDER, Funnel  # noqa: E402

SCHEMA_VERSION = 1
KIND_REGION = "career-ops.unified-scheduled-region-run"
KIND_UNIFIED = "career-ops.unified-scheduled-discovery"
REGION_ORDER = ("uk", "dubai", "japan", "singapore")

#: production discovery policy (the owner's intern-only rule is diagnostic only)
DEFAULT_MODE = "high_recall"
DIAGNOSTIC_MODE = "intern_only"

DEFAULT_RUNTIME_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "discovery"
WEB_RESEARCH_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "web-research"
COMPANY_WATCH_RUNTIME = CONTROL_PLANE / "runtime" / "company-watch"
WATCHLIST_RUNTIME = CONTROL_PLANE / "runtime" / "career-ops" / "watchlist"
RECRUITER_WATCH_RUNTIME = CONTROL_PLANE / "runtime" / "career-ops" / "recruiter-watch"
LINKEDIN_INBOX = CONTROL_PLANE / "runtime" / "linkedin" / "inbox"
LOCK_FILE = DEFAULT_RUNTIME_DIR / "unified-run.lock"
STATE_FILE = DEFAULT_RUNTIME_DIR / "unified-run-state.json"

# --- per-source budgets (bounded so one blocked site cannot eat the whole scan) --- #
DEFAULT_WEB_QUERIES = 8
DEFAULT_LIMIT_PER_QUERY = 5
DEFAULT_MAX_URLS = 24
DEFAULT_PER_QUERY_TIMEOUT = 180
DEFAULT_SCAN_TIMEOUT = 900
DEFAULT_SCAN_MAX_SECONDS = 1020
DEFAULT_WATCHLIST_MAX_COMPANIES = 6
DEFAULT_BUDGET_SECONDS = 2700
DEFAULT_RETRIES = 1
#: Company Watch / watchlist / LinkedIn/recruiter exports older than this are
#: reported as stale, never silently treated as fresh findings.
DEFAULT_INGEST_STALE_HOURS = 48
DEFAULT_SEMANTIC = "auto"
DEFAULT_CODEX_ESCALATION = "off"
DEFAULT_CODEX_BUDGET = 0

# --- the required source classes ------------------------------------------------ #
ATS_SURFACES = tuple(scope for scope, _q in wr.OWNER_ATS_SITE_QUERIES)
SOURCE_CLASSES = (
    ("public_linkedin_jobs", ("linkedin_jobs",),
     "public / indexed LinkedIn Jobs results (no login, no cookies, no browser automation)"),
    ("public_indeed", ("indeed",), "public Indeed results the search engine can reach"),
    ("web_index", ("google_index",), "Google / web-indexed vacancy discovery"),
    ("ats_employer_careers", ATS_SURFACES + ("employer_careers",),
     "direct ATS / employer careers discovery"),
)
CLASS_ORDER = tuple(name for name, _s, _d in SOURCE_CLASSES)

#: explicit evidence rule per recorded state (documented in the policy document)
COVERAGE_STATE_RULES = {
    "reached": "at least one result URL of this class was discovered by an executed "
               "query whose live search was observed",
    "blocked": "the query was executed and a live search observed, but the class's own "
               "destinations were refused by the site (HTTP 401/403/429, robots.txt) "
               "or the search itself was refused — never reported as empty",
    "unavailable": "no live-search mechanism was available for this class's queries in "
                   "this run (provider unavailable / no observed search)",
    "not_applicable": "this class was not attempted in this run by configuration, budget "
                      "or because its data was supplied by another lane",
    "searched_no_results": "the class's queries executed with an observed live search and "
                           "returned no result URL of this class; this is a fact about this "
                           "run's search, not a claim that the source is empty",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def emit(obj) -> None:
    rjs.emit(obj)


def write_json_atomic(path, obj) -> None:
    pipeline.write_json_atomic(Path(path), obj)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_iso(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001 - an unparseable timestamp is simply unknown
        return None


def age_hours(value, now: dt.datetime | None = None):
    stamp = parse_iso(value)
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return round(((now or dt.datetime.now(dt.timezone.utc)) - stamp).total_seconds() / 3600.0, 2)


def surface_class(surface: str | None) -> str | None:
    """Map a discovered surface onto the required source class."""
    for name, surfaces, _desc in SOURCE_CLASSES:
        if surface in surfaces:
            return name
    return None


def select_queries(matrix: list, limit: int) -> list:
    """Pick at most ``limit`` queries, round-robin across surfaces.

    The query matrix lists the broad public surfaces (LinkedIn Jobs, Indeed, open
    web) first and the owner's ATS site patterns next. Round-robin selection means
    a small budget still attempts every required source class before one surface or
    one blocked site can consume the whole scan.
    """
    if limit <= 0:
        return list(matrix)
    groups: dict[str, list] = {}
    order: list[str] = []
    for entry in matrix:
        scope = entry.get("surface_scope") or "unknown"
        if scope not in groups:
            groups[scope] = []
            order.append(scope)
        groups[scope].append(entry)
    out: list = []
    round_index = 0
    while len(out) < limit:
        progressed = False
        for scope in order:
            bucket = groups[scope]
            if round_index < len(bucket):
                out.append(bucket[round_index])
                progressed = True
                if len(out) >= limit:
                    break
        if not progressed:
            break
        round_index += 1
    return out


# --------------------------------------------------------------------------- #
# lane runners
# --------------------------------------------------------------------------- #

def _run_subprocess(cmd: list, *, timeout: int, cwd: Path) -> dict:
    started = time.time()
    out = {"command": cmd, "exit_code": None, "timed_out": False, "stdout_tail": "",
           "stderr_tail": "", "duration_s": None, "error": None}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(cwd), encoding="utf-8", errors="replace")
        out["exit_code"] = proc.returncode
        out["stdout_tail"] = (proc.stdout or "")[-4000:]
        out["stderr_tail"] = (proc.stderr or "")[-2000:]
    except subprocess.TimeoutExpired as exc:
        out["timed_out"] = True
        out["error"] = f"bounded subprocess timeout after {timeout}s"
        out["stdout_tail"] = str(exc.stdout or "")[-2000:]
        out["stderr_tail"] = str(exc.stderr or "")[-1000:]
    except Exception as exc:  # noqa: BLE001 - a launch failure is recorded, not raised
        out["error"] = f"{type(exc).__name__}: {exc}"
    out["duration_s"] = round(time.time() - started, 2)
    return out


def run_regional_scan(region: str, args, *, deadline: float) -> dict:
    """The existing structured regional provider scan, run bounded and dry-run."""
    budget = max(30, int(min(args.scan_timeout, max(30, deadline - time.time()))))
    cmd = [sys.executable, str(CAREER_OPS_DIR / "regional_job_search.py"), "run",
           "--region", region, "--scheduled", "--timeout", str(budget),
           "--record", str(args.scan_records_dir or (CONTROL_PLANE / "runtime" / "career-ops"
                                                     / "scan-runs"))]
    if args.state_file:
        cmd += ["--state-file", str(args.state_file)]
    attempts = []
    run = None
    for _attempt in range(max(1, int(args.retries) + 1)):
        run = _run_subprocess(cmd, timeout=budget + 120, cwd=CONTROL_PLANE)
        attempts.append({"exit_code": run["exit_code"], "timed_out": run["timed_out"],
                         "error": run["error"], "duration_s": run["duration_s"]})
        if not run["timed_out"] and run["exit_code"] == 0:
            break
    health_file = None
    doc: dict | None = None
    if run.get("stdout_tail"):
        try:
            parsed = json.loads(run["stdout_tail"])
        except Exception:  # noqa: BLE001 - stdout may carry the tail of a JSON blob
            parsed = None
        if isinstance(parsed, dict):
            doc = parsed
            health_file = parsed.get("run_health_file")
    block = {"source": pipeline.SOURCE_SCAN_RECORD, "candidates": [],
             "coverage": {"kind": "career-ops lane scan (regional worker, unchanged)",
                          "available": False, "note": ""}}
    if health_file and Path(health_file).exists():
        block = pipeline.collect_from_scan_record(Path(health_file))
        block["source"] = pipeline.SOURCE_SCAN_RECORD
    else:
        block["coverage"]["note"] = ("no regional run-health record was produced, so this "
                                     "source contributed no candidate; the scan failure is "
                                     "recorded above rather than reported as zero vacancies")
    return {
        "lane": "structured_regional_provider_scan",
        "worker": "career-ops/regional_job_search.py (unchanged, dry-run)",
        "attempts": attempts,
        "retries_used": len(attempts) - 1,
        "exit_code": run.get("exit_code"),
        "timed_out": run.get("timed_out"),
        "duration_s": run.get("duration_s"),
        "run_health_file": health_file,
        "scan_ok": (doc or {}).get("status"),
        "error": run.get("error"),
        "block": block,
    }


def run_web_research(region: str, args, *, deadline: float) -> dict:
    """Bounded live (or replayed) open-web research pass for one region."""
    watchlist = wr.load_watchlist(Path(args.watchlist)) if args.watchlist else []
    if not watchlist and WATCHLIST_RUNTIME.joinpath("company-watchlist.json").exists():
        watchlist = wr.load_watchlist(WATCHLIST_RUNTIME / "company-watchlist.json")
    matrix = wr.build_query_matrix(region, include_watchlist=watchlist)
    remaining = max(0.0, deadline - time.time())
    per_query = max(30, min(int(args.per_query_timeout),
                            int(remaining / max(1, args.web_queries)) or 30))
    queries = select_queries(matrix, args.web_queries)
    provider = wr.make_provider(args.provider,
                                captured=Path(args.captured) if args.captured else None,
                                executable=args.executable)
    probe = provider.probe()
    out = {
        "lane": "open_web_research",
        "provider_kind": args.provider,
        "probe": probe,
        "queries_selected": [{"query_id": q["query_id"], "surface_scope": q["surface_scope"],
                              "role_family": q["role_family"]} for q in queries],
        "queries_selected_total": len(queries),
        "matrix_size": len(matrix),
        "watchlist_companies": watchlist,
        "per_query_timeout_s": per_query,
        "export_file": None,
        "limitation": None,
        "block": {"source": pipeline.SOURCE_WEB_RESEARCH, "candidates": [],
                  "coverage": {"kind": "open-web research", "available": False}},
    }
    if args.reuse_web_export:
        path = Path(args.reuse_web_export)
        doc = read_json(path)
        out["export_file"] = str(path)
        out["reused_export"] = True
    else:
        doc = wr.run_research(queries, provider, region=region,
                              limit_per_query=args.limit_per_query, timeout=per_query,
                              validate=(not args.no_validate), max_urls=args.max_urls)
        doc["query_matrix_limited"] = len(queries) < len(matrix)
        doc["query_matrix_size"] = len(queries)
        out_dir = Path(args.web_out_dir) if args.web_out_dir else WEB_RESEARCH_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        export_path = out_dir / f"web-research-{region}-{doc['export_id']}.json"
        write_json_atomic(export_path, doc)
        write_json_atomic(out_dir / f"web-research-{region}-latest.json", doc)
        doc["export_file"] = str(export_path)
        out["export_file"] = str(export_path)
        out["reused_export"] = False
    out["telemetry"] = doc.get("telemetry") or {}
    out["provider"] = doc.get("provider") or {}
    out["queries_run"] = [{"query_id": q.get("query_id"), "query": q.get("query"),
                           "surface_scope": q.get("surface_scope"),
                           "executed": q.get("executed"),
                           "web_search_observed": q.get("web_search_observed"),
                           "results_seen": q.get("results_seen")}
                          for q in (doc.get("queries") or [])]
    out["candidates"] = doc.get("candidates") or []
    if out["export_file"]:
        block = pipeline.collect_from_web_research(Path(out["export_file"]), region)
        block["source"] = pipeline.SOURCE_WEB_RESEARCH
        out["block"] = block
    if not out["provider"].get("available") or not out["provider"].get(
            "web_search_observed_queries", 1 if args.reuse_web_export else 0):
        out["limitation"] = (out["provider"].get("limitation")
                             or "no live web-search mechanism was observed in this run")
    return out


def _ingest_export(path: Path, region: str, collector, *, stale_hours: float,
                   lane: str, note: str) -> dict:
    """Read a lane's own latest export; absent/stale are recorded, never invented."""
    info = {"lane": lane, "path": str(path), "present": path.exists(), "available": False,
            "stale": None, "age_hours": None, "reason": None, "note": note,
            "block": {"source": lane, "candidates": [], "coverage": {}}}
    if not path.exists():
        info["reason"] = ("the lane's own export is not present on this machine, so it "
                          "contributes no candidate in this run (not 'no vacancies')")
        return info
    try:
        doc = read_json(path)
    except Exception as exc:  # noqa: BLE001 - an unreadable export is recorded
        info["reason"] = f"unreadable export: {type(exc).__name__}: {exc}"
        return info
    generated = doc.get("generated_at") or doc.get("finished_at")
    info["generated_at"] = generated
    info["age_hours"] = age_hours(generated)
    info["stale"] = bool(info["age_hours"] is not None and info["age_hours"] > stale_hours)
    block = collector(path, region)
    block["source"] = lane
    block.setdefault("coverage", {})["export_age_hours"] = info["age_hours"]
    block["coverage"]["export_stale"] = info["stale"]
    block["coverage"]["stale_after_hours"] = stale_hours
    info["available"] = True
    info["block"] = block
    if info["stale"]:
        info["reason"] = (f"export is {info['age_hours']}h old (> {stale_hours}h): it is "
                          f"reported and never presented as fresh findings")
    return info


def ingest_company_watch(region: str, args) -> dict:
    path = COMPANY_WATCH_RUNTIME / f"findings-{region}-latest.json"
    return _ingest_export(path, region, pipeline.collect_from_company_watch,
                          stale_hours=args.ingest_stale_hours,
                          lane=pipeline.SOURCE_COMPANY_WATCH,
                          note=("Company Watch findings are discovery signals, not "
                                "application records; the watch lane itself is unchanged "
                                "and runs read-only"))


def ingest_priority_watchlist(region: str, args) -> dict:
    path = WATCHLIST_RUNTIME / f"watchlist-{region}-latest.json"
    return _ingest_export(path, region, pipeline.collect_from_priority_watchlist,
                          stale_hours=args.ingest_stale_hours,
                          lane=pipeline.SOURCE_PRIORITY_WATCHLIST,
                          note=("the owner's own company list is additive and optional; an "
                                "absent list is a valid state and is never reported as a "
                                "market fact"))


def ingest_recruiter_watch(region: str, args) -> dict:
    path = RECRUITER_WATCH_RUNTIME / f"recruiter-watch-{region}-latest.json"
    return _ingest_export(path, region, pipeline.collect_from_recruiter_watch,
                          stale_hours=args.ingest_stale_hours,
                          lane=pipeline.SOURCE_RECRUITER_WATCH,
                          note=("read-only intermediary surface; no agency, recruiter or "
                                "employer is contacted"))


def ingest_linkedin(region: str, args) -> dict:
    path = LINKEDIN_INBOX / f"linkedin-jobs-{region}.json"
    return _ingest_export(path, region, pipeline.collect_from_linkedin,
                          stale_hours=args.ingest_stale_hours,
                          lane=pipeline.SOURCE_LINKEDIN_EXPORT,
                          note=("owner-exported discovery file only; no login, cookie, "
                                "session, browser automation or LinkedIn mutation"))


# --------------------------------------------------------------------------- #
# source coverage matrix
# --------------------------------------------------------------------------- #

def _blocking_evidence(fetch: dict | None) -> str | None:
    """Evidence that a destination refused us (never an 'empty source')."""
    if not fetch:
        return None
    status = fetch.get("http_status")
    if status in (401, 402, 403, 407, 429, 451):
        return f"HTTP {status}"
    robots = str(fetch.get("robots") or "")
    if "disallows" in robots or "disallow" in robots:
        return f"robots.txt: {robots}"
    return None


def build_source_coverage(web: dict, *, provider_available: bool) -> dict:
    """Per-source-class coverage from real evidence only (no inference)."""
    queries = web.get("queries_run") or []
    candidates = web.get("candidates") or []
    classes: dict = {}
    for name, surfaces, description in SOURCE_CLASSES:
        q_all = [q for q in queries if q.get("surface_scope") in surfaces]
        q_exec = [q for q in q_all if q.get("executed")]
        q_searched = [q for q in q_exec if q.get("web_search_observed")]
        owned = [c for c in candidates
                 if (c.get("web_research") or {}).get("discovery_surface") in surfaces]
        postings = [c for c in owned if c.get("result_kind") == wr.RESULT_KIND_POSTING]
        validated = [c for c in owned if c.get("fetch_state") == wr.FETCH_VALIDATED_LIVE]
        failed = [c for c in owned if c.get("fetch_state") == wr.FETCH_VALIDATION_FAILED]
        listings = [c for c in owned if c.get("result_kind") == wr.RESULT_KIND_SEARCH_LISTING]
        blocking = sorted(x for x in
                          {_blocking_evidence((c.get("web_research") or {}).get("fetch"))
                           for c in owned} if x)
        entry = {
            "class": name,
            "description": description,
            "surfaces": list(surfaces),
            "queries_targeting": len(q_all),
            "queries_executed": len(q_exec),
            "queries_with_observed_live_search": len(q_searched),
            "result_urls_discovered": len(owned),
            "job_posting_urls": len(postings),
            "search_listing_urls": len(listings),
            "validated_live": len(validated),
            "validation_failed": len(failed),
            "blocking_evidence": blocking,
            "search_mechanism_available": bool(provider_available),
            "state": None,
            "state_rule": None,
        }
        if not q_all:
            entry["state"] = "not_applicable"
            entry["reason"] = ("no query in this run targets this class (budget, "
                               "configuration, or the data arrived through another lane)")
        elif not q_searched:
            entry["state"] = "unavailable"
            entry["reason"] = ("no live-search mechanism was available for this class's "
                               "queries in this run (provider unavailable or no search "
                               "event observed) — this is NOT evidence the source is empty")
        elif validated:
            entry["state"] = "reached"
            entry["reason"] = (f"{len(owned)} result URL(s) of this class discovered; "
                               f"{len(validated)} validated live, {len(failed)} could not be "
                               f"validated")
        elif blocking or failed:
            entry["state"] = "blocked"
            if blocking:
                entry["reason"] = ("the search ran but this class's destinations refused "
                                   f"retrieval ({', '.join(blocking)}) — recorded as blocked, "
                                   "never as empty")
            else:
                entry["reason"] = ("result URLs of this class were discovered but none could "
                                   "be retrieved (validation failed) — recorded as blocked, "
                                   "never as empty")
        elif owned:
            entry["state"] = "reached"
            entry["reason"] = (f"{len(owned)} result URL(s) of this class discovered by an "
                               "executed query with an observed live search; none was "
                               "validated live in this run (discovered_unverified, not "
                               "validated-live evidence)")
        else:
            entry["state"] = "searched_no_results"
            entry["reason"] = ("the class's queries executed with an observed live search and "
                               "returned no result URL of this class; a fact about this run's "
                               "search, not a claim that the source is empty")
        entry["state_rule"] = COVERAGE_STATE_RULES[entry["state"]]
        classes[name] = entry
    return {
        "classes": classes,
        "order": list(CLASS_ORDER),
        "states_vocabulary": dict(COVERAGE_STATE_RULES),
        "note": ("states are derived from this run's own query/result/validation evidence. A "
                 "source class that was inaccessible or blocked is never called empty."),
    }


def live_mechanism_summary(web: dict) -> dict:
    provider = web.get("provider") or {}
    probe = web.get("probe") or {}
    observed = int(provider.get("web_search_observed_queries") or 0)
    reused = bool(web.get("reused_export"))
    out = {
        "mechanism": (f"replayed capture ({web.get('export_file')})" if reused
                      else provider.get("provider")),
        "probe_available": probe.get("available"),
        "live_search_queries_observed": 0 if reused else observed,
        "requests": 0 if reused else provider.get("requests"),
        "cli_version": provider.get("cli_version"),
        "resolved_executable": provider.get("resolved_executable"),
        "limitation": provider.get("limitation") or web.get("limitation"),
        "operational": bool(observed > 0) and not reused,
        "provenance": ("this run executed the queries live" if not reused else
                       "the export was replayed; its provider counters describe the original "
                       "capture, not this run"),
        "note": ("operational = at least one query in THIS run produced a proven live web "
                 "search; a replayed capture or a fixture can never satisfy this"),
    }
    if reused:
        out["limitation"] = ("this run replayed a captured export; it is not live proof and "
                             "cannot satisfy --require-live-web")
    return out


# --------------------------------------------------------------------------- #
# one region
# --------------------------------------------------------------------------- #

def run_region(region: str, args, *, deadline: float | None = None,
               lock_already_checked: bool = False) -> dict:
    deadline = deadline or (time.time() + max(60, args.budget_seconds))
    started = now_utc()
    run_id = f"unified-{region}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    live = not args.no_live
    provider_kind = args.provider if args.provider != "auto" else "codex"
    if not live and not args.reuse_web_export:
        provider_kind = "none" if args.provider == "auto" else args.provider

    collection: list = []
    lanes: dict = {}

    # 1. structured regional provider scan (unchanged worker, dry-run)
    if args.skip_regional_scan:
        lanes["regional_scan"] = {
            "lane": "structured_regional_provider_scan", "skipped": True,
            "reason": ("skipped by the caller (bounded diagnostic/acceptance run); the "
                       "scheduled path does not skip it"),
            "block": {"source": pipeline.SOURCE_SCAN_RECORD, "candidates": [],
                      "coverage": {"kind": "career-ops lane scan",
                                   "available": False,
                                   "note": "skipped by the caller, not an empty lane"}}}
    else:
        lanes["regional_scan"] = run_regional_scan(region, args, deadline=deadline)
    collection.append(lanes["regional_scan"]["block"])

    # 2. open-web / Codex-style research
    args_web = argparse.Namespace(**vars(args))
    args_web.provider = provider_kind
    lanes["web_research"] = run_web_research(region, args_web, deadline=deadline)
    collection.append(lanes["web_research"]["block"])
    coverage = build_source_coverage(
        lanes["web_research"],
        provider_available=bool((lanes["web_research"].get("provider") or {}).get("available"))
        and not lanes["web_research"].get("reused_export"))
    lanes["web_research"]["source_coverage"] = coverage

    # 3-6. the other lanes: ingests (their own exporters are unchanged/read-only)
    for key, fn in (("company_watch", ingest_company_watch),
                    ("priority_watchlist", ingest_priority_watchlist),
                    ("recruiter_watch", ingest_recruiter_watch),
                    ("linkedin_export", ingest_linkedin)):
        lane = fn(region, args)
        lanes[key] = lane
        collection.append(lane["block"])

    candidates = [c for b in collection for c in b["candidates"]]
    mode = args.mode
    funnel_doc = pipeline.run_funnel(
        candidates, region=region, mode=mode, semantic=args.semantic,
        deepseek_model=args.model, batch_size=args.batch_size,
        codex_budget=args.codex_budget, codex_enabled=(args.codex == "on"),
        timeout=args.per_query_timeout, run_id=run_id,
        max_tokens=args.max_tokens, collection=collection,
        codex_model=getattr(args, "codex_model", None))

    mechanism = live_mechanism_summary(lanes["web_research"])
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_RUNTIME_DIR
    region_dir = out_dir / "unified" / region
    doc = {
        **funnel_doc,
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_REGION,
        "generated_at": started,
        "finished_at": now_utc(),
        "scheduled_run": bool(args.scheduled),
        "live": live,
        "discovery_mode": mode,
        "production_discovery_policy": DEFAULT_MODE,
        "diagnostic_mode": mode == DIAGNOSTIC_MODE,
        "budget": {"overall_seconds": args.budget_seconds,
                   "elapsed_seconds": round(time.time() - (deadline - args.budget_seconds), 2),
                   "web_queries": args.web_queries, "limit_per_query": args.limit_per_query,
                   "max_urls": args.max_urls, "per_query_timeout_s": args.per_query_timeout,
                   "scan_timeout_s": args.scan_timeout, "retries": args.retries},
        "lanes": lanes,
        "source_coverage": coverage,
        "live_research": mechanism,
        "read_only": True,
        "safety": {**funnel_doc["safety"], "canonical_workbook_written": False,
                   "browser_or_gui_used": False, "login_or_account_used": False,
                   "cookies_or_session_used": False},
    }
    doc["summary_line"] = pipeline._summary_line(doc)

    # unified manifest: only candidates that passed the deterministic gates
    accepted_ids = {d["candidate_id"] for d in doc["eligibility"]["decisions"]
                    if d["decision"] == "accepted"}
    records = [rjs.build_record(region, c, rjs.load_policy(), run_id,
                                {"stage": "unified-scheduled-discovery"})
               for c in doc["canonical_candidates"]
               if c.get("url") and c["candidate_id"] in accepted_ids]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "career-ops.unified-candidate-manifest",
        "generated_at": now_utc(), "region": region, "run_id": run_id,
        "read_only": True, "canonical_workbook_written": False,
        "counts": {"candidates": len(doc["canonical_candidates"]),
                   "tracker_candidates": doc["funnel"]["counts"]["tracker_candidates"],
                   "manifest_records": len(records)},
        "records": records,
        "attribution": {src: entry["zero_attribution"]
                        for src, entry in (doc["funnel"].get("by_source") or {}).items()},
        "note": ("applying a manifest stays the explicit, separately approved step "
                 "(career_ops_cli.py write --apply). Nothing here writes a tracker."),
    }

    # idempotency
    key_basis = json.dumps({"region": region, "mode": mode,
                            "candidates": sorted(f"{c.get('company')}|{c.get('title')}|"
                                                 f"{c.get('url')}"
                                                 for c in doc["canonical_candidates"]),
                            "coverage": {k: v["state"] for k, v in coverage["classes"].items()}},
                           sort_keys=True, ensure_ascii=False)
    run_key = hashlib.sha256(key_basis.encode("utf-8")).hexdigest()[:16]
    state_path = Path(args.state_file_out) if getattr(args, "state_file_out", None) else STATE_FILE
    state = read_json(state_path) if state_path.exists() else {"schema_version": 1, "regions": {}}
    prev = (state.get("regions") or {}).get(region) or {}
    replay = bool(prev.get("last_run_key")) and prev.get("last_run_key") == run_key
    doc["idempotency"] = {
        "run_key": run_key, "previous_run_key": prev.get("last_run_key"),
        "idempotent_replay": replay, "state_file": str(state_path),
        "note": ("a replayed key means the same candidate set and the same coverage states "
                 "were produced before; this run is still a dry run and writes nothing"),
    }
    state.setdefault("regions", {})[region] = {
        "last_run_id": run_id, "last_run_key": run_key, "last_run_at": doc["finished_at"],
        "last_mode": mode, "last_live": live,
        "last_live_mechanism_operational": mechanism["operational"],
        "last_counts": doc["funnel"]["counts"], "runs": int(prev.get("runs") or 0) + 1,
    }
    state["schema_version"] = 1
    state["updated_at"] = doc["finished_at"]

    region_dir.mkdir(parents=True, exist_ok=True)
    health_file = region_dir / f"{run_id}.json"
    manifest_file = region_dir / f"manifest-{run_id}.json"
    write_json_atomic(health_file, doc)
    write_json_atomic(manifest_file, manifest)
    write_json_atomic(region_dir / "latest.json", doc)
    write_json_atomic(region_dir / "manifest-latest.json", manifest)
    write_json_atomic(state_path, state)
    doc["run_health_file"] = str(health_file)
    doc["manifest_file"] = str(manifest_file)
    doc["region_dir"] = str(region_dir)
    doc["manifest"] = manifest["counts"]

    # requirement: refuse to call the lane production-ready without a live mechanism
    doc["production_ready"] = bool(mechanism["operational"])
    if not doc["production_ready"]:
        doc["no_go"] = ("no functioning current-web search mechanism was proven in this run; "
                        "the live research lane is NOT production-ready and the schedule must "
                        "not be treated as cut over (recorded blocker, no fixture fallback)")
    return doc


def aggregate(region_docs: dict, args) -> dict:
    """One unified whole-company document (and one manifest) across all regions."""
    agg = Funnel()
    merged_rejections: dict = {}
    not_applicable_sets = []
    merged_notes: list = []
    classifications: list = []
    decisions: list = []
    canonical: list = []
    collection: list = []
    watchlist_candidates: list = []
    watchlist_companies: set = set()
    watchlist_families: set = set()
    watchlist_counts: dict = {"canonical_candidates": 0, "deterministic_eligibility_pass": 0,
                              "also_found_by_another_surface": 0}
    wl_declared = False
    counts = {}

    for region, doc in region_docs.items():
        # region docs carry their own funnel by region; aggregation is by addition and
        # the cross-region overlap note below says so explicitly
        for key, value in (doc["funnel"]["counts"] or {}).items():
            if isinstance(value, int):
                counts[key] = counts.get(key, 0) + value
        for reason, n in (doc["funnel"].get("rejections_by_reason") or {}).items():
            merged_rejections[reason] = merged_rejections.get(reason, 0) + n
        not_applicable_sets.append(set((doc["funnel"].get("not_applicable_stages") or {}).keys()))
        for note in (doc["funnel"].get("notes") or [])[:40]:
            merged_notes.append(f"[{region}] {note}")
        classifications.extend(doc.get("classifications") or [])
        decisions.extend((doc.get("eligibility") or {}).get("decisions") or [])
        canonical.extend(doc.get("canonical_candidates") or [])
        for block in doc.get("collection") or []:
            entry = dict(block)
            cov = dict(entry.get("coverage") or {})
            cov.setdefault("region", region)
            entry["coverage"] = cov
            collection.append(entry)
        wl = doc.get("priority_watchlist") or {}
        wl_declared = wl_declared or bool(wl.get("declared"))
        for c in wl.get("candidates") or []:
            watchlist_candidates.append({**c, "region": region, "priority_watchlist": True})
        for company in wl.get("companies") or []:
            if company:
                watchlist_companies.add(company)
        for family in wl.get("query_families") or []:
            if family:
                watchlist_families.add(family)
        for key in ("canonical_candidates", "deterministic_eligibility_pass",
                    "also_found_by_another_surface"):
            watchlist_counts[key] = watchlist_counts.get(key, 0) + int(
                (wl.get("counts") or {}).get(key) or 0)
        for src, entry in (doc["funnel"].get("by_source") or {}).items():
            sc = agg.source_counts.setdefault(src, Counter())
            for k, v in (entry.get("counts") or {}).items():
                sc[k] += v
                if k == "discovered":
                    agg.discovered_by_source[src] += v
            sr = agg.source_rejections.setdefault(src, Counter())
            for k, v in (entry.get("rejections_by_reason") or {}).items():
                sr[k] += v

    agg.counts = dict(counts)
    for key in COUNT_KEYS:
        agg.counts.setdefault(key, 0)
    agg.rejections = Counter(merged_rejections)
    common_na = set.intersection(*not_applicable_sets) if not_applicable_sets else set()
    for key in common_na:
        first = next((d["funnel"].get("not_applicable_stages", {}).get(key)
                      for d in region_docs.values()
                      if d["funnel"].get("not_applicable_stages", {}).get(key)), None)
        if first:
            agg.skip(key, first)
    agg.notes = merged_notes[:80]
    agg.explain(
        "tracker_candidates",
        "no candidate across any region survived every stage to a tracker candidate; see the "
        "per-region funnels and per-source zero attribution")
    funnel_doc = agg.document()

    mechanisms = {r: (d.get("live_research") or {}) for r, d in region_docs.items()}
    operational = [r for r, m in mechanisms.items() if m.get("operational")]
    unified = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_UNIFIED,
        "run_id": "unified-all-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "region": "all",
        "regions_covered": sorted(region_docs),
        "generated_at": now_utc(),
        "finished_at": now_utc(),
        "title_policy_mode": args.mode,
        "production_discovery_policy": DEFAULT_MODE,
        "scheduled_run": bool(args.scheduled),
        "live": not args.no_live,
        "funnel": funnel_doc,
        "collection": collection,
        "classifications": classifications[:200],
        "eligibility": {"input": len(decisions), "decisions": decisions[:400],
                        "passed": sum(1 for d in decisions if d.get("decision") == "accepted")},
        "canonical_candidates": canonical[:400],
        "priority_watchlist": {
            "declared": wl_declared,
            "counts": watchlist_counts,
            "companies": sorted(watchlist_companies),
            "query_families": sorted(watchlist_families),
            "candidates": watchlist_candidates,
            "note": ("the owner priority watchlist view across regions; merged from each "
                     "region's own block. The flag gives prominence only and never bypasses a "
                     "semantic or deterministic gate."),
        },
        "source_registry": dict(pipeline.SOURCE_REGISTRY),
        "dedupe": {"engine": "career-ops/tracker_writer.py (shared)",
                   "applied": False,
                   "note": ("each region's own dedupe probe ran against that region's "
                            "canonical workbook, read-only; counters per region are in "
                            "regions.<region>.funnel")},
        "jd_gap": pipeline.jd_gap_report(canonical),
        "semantic": {r: (d.get("semantic") or {}) for r, d in region_docs.items()},
        "codex": {"escalation": {r: (d.get("codex") or {}) for r, d in region_docs.items()},
                  "research_provider": mechanisms},
        "source_coverage": {r: (d.get("source_coverage") or {}) for r, d in region_docs.items()},
        "live_research": {
            "regions_operational": sorted(operational),
            "regions_without_an_operational_mechanism": sorted(set(region_docs) - set(operational)),
            "operational": bool(operational),
            "note": ("operational = at least one region's bounded live pass proved a real "
                     "current-web search in this run"),
        },
        "regions": {r: {"run_id": d.get("run_id"), "run_health_file": d.get("run_health_file"),
                        "manifest_file": d.get("manifest_file"),
                        "funnel": {"counts": d["funnel"]["counts"],
                                   "zero_attribution": d["funnel"]["zero_attribution"]},
                        "counts": d["funnel"]["counts"],
                        "zero_attribution": d["funnel"]["zero_attribution"],
                        "live_research": d.get("live_research"),
                        "production_ready": d.get("production_ready"),
                        "no_go": d.get("no_go")} for r, d in region_docs.items()},
        "aggregation_note": ("counters are the SUM of the per-region funnels; a vacancy "
                            "discovered in two regions is counted once per region by design, "
                            "so the total is not a number of distinct vacancies"),
        "read_only": True,
        "safety": {
            "canonical_workbook_written": False, "applications_submitted": 0,
            "employer_contacts": 0, "linkedin_mutation": False, "browser_or_gui_used": False,
            "login_or_account_used": False, "cookies_or_session_used": False,
            "handoff": "manifest only; applying stays career_ops_cli.py write --apply",
        },
    }
    unified["summary_line"] = pipeline._summary_line(unified)
    unified["production_ready"] = bool(operational)
    if not unified["production_ready"]:
        unified["no_go"] = ("no region proved a functioning current-web search mechanism, so "
                            "the live research lane is NOT production-ready and no cutover is "
                            "claimed")
    return unified


def unified_manifest(region_docs: dict, unified: dict, *, args) -> dict:
    records = []
    for region, doc in region_docs.items():
        path = Path(doc.get("manifest_file")) if doc.get("manifest_file") else None
        if path and path.exists():
            for rec in (read_json(path).get("records") or []):
                records.append({**rec, "region": region})
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "career-ops.unified-nightly-candidate-manifest",
        "generated_at": now_utc(), "run_id": unified["run_id"],
        "regions": sorted(region_docs), "read_only": True,
        "canonical_workbook_written": False,
        "counts": {"records": len(records),
                   "tracker_candidates": unified["funnel"]["counts"].get("tracker_candidates", 0)},
        "records": records,
        "attribution": {r: (d["funnel"].get("by_source") or {}) for r, d in region_docs.items()},
        "note": ("one unified nightly candidate manifest with source/funnel attribution; no "
                 "tracker write and no application action is performed by this manifest"),
    }


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def policy_document() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "worker": "career-ops/discovery/scheduled_orchestrator.py",
        "production_discovery_policy": DEFAULT_MODE,
        "diagnostic_modes": {DIAGNOSTIC_MODE: ("the owner's own Intern/Internship title filter "
                                              "(title_policy.py) kept for diagnostic/compare "
                                              "runs only; it is never the scheduled discovery "
                                              "gate")},
        "sources": [{"source": name, "surfaces": list(surfaces), "description": desc,
                     "states": dict(COVERAGE_STATE_RULES)}
                    for name, surfaces, desc in SOURCE_CLASSES],
        "lanes": {
            "structured_regional_provider_scan": "regional_job_search.py run --scheduled (dry-run)",
            "open_web_research": "web_research.py query matrix + live provider",
            "company_watch": f"findings export at {COMPANY_WATCH_RUNTIME}\\findings-<region>-latest.json",
            "priority_watchlist": f"watchlist lane export at {WATCHLIST_RUNTIME}\\watchlist-<region>-latest.json",
            "recruiter_watch": f"export at {RECRUITER_WATCH_RUNTIME}\\recruiter-watch-<region>-latest.json",
            "linkedin_export": f"owner-exported discovery file at {LINKEDIN_INBOX}\\linkedin-jobs-<region>.json",
        },
        "budgets": {
            "overall_seconds": DEFAULT_BUDGET_SECONDS,
            "web_queries_per_region": DEFAULT_WEB_QUERIES,
            "limit_per_query": DEFAULT_LIMIT_PER_QUERY,
            "max_urls_validated_per_region": DEFAULT_MAX_URLS,
            "per_query_timeout_s": DEFAULT_PER_QUERY_TIMEOUT,
            "regional_scan_timeout_s": DEFAULT_SCAN_TIMEOUT,
            "retries": DEFAULT_RETRIES,
            "ingest_stale_after_hours": DEFAULT_INGEST_STALE_HOURS,
            "note": ("every lane has its own bound; a blocked site or a slow provider consumes "
                     "its own budget only and the run continues to the next source"),
        },
        "concurrency": {
            "staggered_times": {"uk": "23:45", "dubai": "23:50", "japan": "23:55",
                                "singapore": "00:00"},
            "lock_file": str(LOCK_FILE),
            "note": ("scheduled regions are staggered and each run takes a lock; a second "
                     "instance that finds a fresh lock exits without running"),
        },
        "writing": {
            "region_dir": str(DEFAULT_RUNTIME_DIR / "unified" / "<region>"),
            "unified_latest": str(DEFAULT_RUNTIME_DIR / "latest.json"),
            "manifest": "unified-manifest-latest.json",
            "canonical_workbook": "NEVER written by this worker",
        },
        "no_go_criteria": [
            "no current-web search mechanism is operational (launcher exits 3; no fixture "
            "fallback is accepted as proof)",
            "a canonical workbook hash changed during a scheduled run",
            "the run cannot bound itself (budget/lock missing) ",
            "an application, outreach, LinkedIn mutation, login or browser action would be "
            "required",
        ],
        "rollback": {
            "previous_launcher_command": (
                "\"%PY%\" \"%CP%\\career-ops\\regional_job_search.py\" run --region %REGION% "
                "--scheduled --timeout 1800 --record \"%LOGDIR%\""),
            "how": ("restore the one-line invocation inside career-ops/run_scheduled_scan.cmd "
                    "(the previous body is kept verbatim in career-ops/"
                    "scheduled_orchestrator.md); no task re-registration is needed because "
                    "the launcher path is unchanged"),
            "old_worker_intact": str(CAREER_OPS_DIR / "regional_job_search.py"),
        },
        "run_commands": [
            "python career-ops/discovery/scheduled_orchestrator.py run --region uk --scheduled",
            "python career-ops/discovery/scheduled_orchestrator.py run-all --scheduled",
            "python career-ops/discovery/scheduled_orchestrator.py coverage",
            "python career-ops/discovery/scheduled_orchestrator.py status",
        ],
        "safety": {
            "read_only": True, "canonical_workbook_written": False, "applications_submitted": 0,
            "linkedin_mutation": False, "login_or_account_used": False,
            "browser_or_gui_used": False, "cookies_or_session_used": False,
        },
    }


def cmd_policy(args) -> int:
    emit({"generated_at": now_utc(), "pipeline": pipeline.policy_document(),
          **policy_document()})
    return 0


def _acquire_lock(args) -> dict:
    if args.no_lock:
        return {"acquired": True, "lock_file": None, "reason": "locking disabled by the caller"}
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fresh_after = max(60, int(args.budget_seconds))
    stale_replaced = False
    if LOCK_FILE.exists():
        try:
            held = read_json(LOCK_FILE)
            if not isinstance(held, dict):
                held = {}
        except Exception:  # noqa: BLE001 - an unreadable lock is treated as held
            held = {}
        age = age_hours(held.get("started_at"))
        age_s = None if age is None else age * 3600.0
        if age_s is not None and age_s < fresh_after:
            return {"acquired": False, "lock_file": str(LOCK_FILE),
                    "reason": (f"another unified run holds the lock ({age_s:.0f}s old, "
                               f"pid {held.get('pid')}); this instance exits without running")}
        # a stale lock (older than the run budget) is reported and replaced
        stale_replaced = True
    LOCK_FILE.write_text(json.dumps({"pid": os.getpid(), "started_at": now_utc()}, indent=2),
                         encoding="utf-8")
    return {"acquired": True, "lock_file": str(LOCK_FILE), "reason": None,
            "stale_replaced": stale_replaced}


def _release_lock(info) -> None:
    if info.get("lock_file") and LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass


def cmd_run(args) -> int:
    lock = _acquire_lock(args)
    if not lock["acquired"]:
        emit({"ok": True, "status": "overlap_skipped", "region": args.region,
              "generated_at": now_utc(), "lock": lock,
              "note": ("a concurrent unified run is in progress; nothing was executed, so the "
                       "scheduled run cannot duplicate work or race another region")})
        return 0
    try:
        doc = run_region(args.region, args, lock_already_checked=True)
    finally:
        _release_lock(lock)
    emit(doc)
    if args.require_live_web and not doc["production_ready"]:
        return 3
    return 0


def cmd_run_all(args) -> int:
    lock = _acquire_lock(args)
    if not lock["acquired"]:
        emit({"ok": True, "status": "overlap_skipped", "generated_at": now_utc(), "lock": lock})
        return 0
    region_docs = {}
    try:
        for region in (args.regions or REGION_ORDER):
            ns = argparse.Namespace(**vars(args))
            ns.region = region
            region_docs[region] = run_region(region, ns, lock_already_checked=True)
    finally:
        _release_lock(lock)
    unified = aggregate(region_docs, args)
    manifest = unified_manifest(region_docs, unified, args=args)
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_RUNTIME_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    health = out_dir / f"unified-run-all-{stamp}.json"
    write_json_atomic(health, unified)
    write_json_atomic(out_dir / "unified-latest.json", unified)
    write_json_atomic(out_dir / "unified-manifest-latest.json", manifest)
    # the Career Daily Brief reads this path; it is the ONE unified nightly manifest
    write_json_atomic(out_dir / "latest.json", unified)
    unified["run_health_file"] = str(health)
    unified["manifest_file"] = str(out_dir / "unified-manifest-latest.json")
    unified["manifest_counts"] = manifest["counts"]
    emit(unified)
    if args.require_live_web and not unified["production_ready"]:
        return 3
    return 0


def cmd_coverage(args) -> int:
    state = read_json(STATE_FILE) if STATE_FILE.exists() else {}
    latest = Path(args.out_dir or DEFAULT_RUNTIME_DIR) / "unified-latest.json"
    doc = read_json(latest) if latest.exists() else None
    per_region = {r: {k: v.get("state") for k, v in (c.get("classes") or {}).items()}
                  for r, c in ((doc or {}).get("source_coverage") or {}).items()}
    emit({"generated_at": now_utc(), "latest": str(latest), "present": doc is not None,
          "region_states": per_region,
          "states_vocabulary": COVERAGE_STATE_RULES,
          "measured": {r: {"last_live_mechanism_operational":
                           (v or {}).get("last_live_mechanism_operational"),
                           "last_run_at": (v or {}).get("last_run_at")}
                       for r, v in (state.get("regions") or {}).items()},
          "note": ("states are recorded per run from real evidence; this view never upgrades a "
                   "blocked or unavailable source to 'empty'")})
    return 0


def cmd_status(args) -> int:
    state = read_json(STATE_FILE) if STATE_FILE.exists() else {"regions": {}}
    out_dir = Path(args.out_dir or DEFAULT_RUNTIME_DIR)
    regions = {}
    for region in REGION_ORDER:
        st = (state.get("regions") or {}).get(region) or {}
        latest = out_dir / "unified" / region / "latest.json"
        regions[region] = {
            "last_run_at": st.get("last_run_at"), "last_mode": st.get("last_mode"),
            "last_live_mechanism_operational": st.get("last_live_mechanism_operational"),
            "runs": st.get("runs", 0),
            "latest_file": str(latest), "latest_present": latest.exists(),
            "scheduled_task": (rjs.load_schedules()["regions"].get(region) or {}).get("task_name"),
            "scheduled_time": (rjs.load_schedules()["regions"].get(region) or {}).get("time"),
        }
    emit({"generated_at": now_utc(), "state_file": str(STATE_FILE), "regions": regions,
          "rollback": policy_document()["rollback"],
          "note": ("all runs are read-only dry runs; no tracker write and no application "
                   "action happens on this path")})
    return 0


def cmd_selftest(args) -> int:
    checks = []
    policy = policy_document()
    checks.append({"check": "default_mode_is_high_recall",
                   "ok": DEFAULT_MODE == "high_recall", "detail": DEFAULT_MODE})
    checks.append({"check": "owner_intern_rule_is_diagnostic_only",
                   "ok": DIAGNOSTIC_MODE == "intern_only"
                   and DIAGNOSTIC_MODE != DEFAULT_MODE,
                   "detail": f"{DIAGNOSTIC_MODE} present, {DEFAULT_MODE} is the policy"})
    surfaces_all = {s for _n, surfaces, _d in SOURCE_CLASSES for s in surfaces}
    checks.append({"check": "every_required_source_class_is_declared",
                   "ok": all(name in CLASS_ORDER for name in
                             ("public_linkedin_jobs", "public_indeed", "web_index",
                              "ats_employer_careers")),
                   "detail": list(CLASS_ORDER)})
    checks.append({"check": "owner_ats_surfaces_are_mapped",
                   "ok": all(s in surfaces_all for s in ATS_SURFACES),
                   "detail": list(ATS_SURFACES)})
    checks.append({"check": "run_commands_present", "ok": bool(policy["run_commands"]),
                   "detail": policy["run_commands"]})
    checks.append({"check": "rollback_documented", "ok": bool(policy["rollback"]["how"]),
                   "detail": policy["rollback"]["previous_launcher_command"]})
    ok = all(c["ok"] for c in checks)
    emit({"generated_at": now_utc(), "ok": ok, "checks": checks,
          "counts": {"checks": len(checks), "passed": sum(1 for c in checks if c["ok"])}})
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unified scheduled Career discovery orchestrator")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("policy")
    p.set_defaults(fn=cmd_policy)

    def add_run_args(sp):
        sp.add_argument("--region", default="uk")
        sp.add_argument("--regions", nargs="*")
        sp.add_argument("--scheduled", action="store_true",
                        help="scheduled mode: read-only dry run (no tracker write ever)")
        sp.add_argument("--mode", choices=(DEFAULT_MODE, DIAGNOSTIC_MODE), default=DEFAULT_MODE,
                        help=("production discovery policy is high_recall; intern_only is an "
                              "explicit diagnostic compare mode"))
        sp.add_argument("--compare", action="store_true",
                        help="explicit acknowledgement of a diagnostic (non-production) mode")
        sp.add_argument("--require-live-web", action="store_true",
                        help=("refuse to declare production readiness without a proven live "
                              "current-web search; exits 3 with the blocker recorded"))
        sp.add_argument("--no-live", action="store_true",
                        help="no live research pass (offline replay only)")
        sp.add_argument("--provider", choices=("auto", "codex", "captured", "none"),
                        default="auto")
        sp.add_argument("--captured")
        sp.add_argument("--executable")
        sp.add_argument("--reuse-web-export")
        sp.add_argument("--watchlist")
        sp.add_argument("--web-queries", type=int, default=DEFAULT_WEB_QUERIES)
        sp.add_argument("--limit-per-query", type=int, default=DEFAULT_LIMIT_PER_QUERY)
        sp.add_argument("--max-urls", type=int, default=DEFAULT_MAX_URLS)
        sp.add_argument("--per-query-timeout", type=int, default=DEFAULT_PER_QUERY_TIMEOUT)
        sp.add_argument("--scan-timeout", type=int, default=DEFAULT_SCAN_TIMEOUT)
        sp.add_argument("--skip-regional-scan", action="store_true")
        sp.add_argument("--scan-records-dir")
        sp.add_argument("--no-validate", action="store_true")
        sp.add_argument("--budget-seconds", type=int, default=DEFAULT_BUDGET_SECONDS)
        sp.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
        sp.add_argument("--ingest-stale-hours", type=float, default=DEFAULT_INGEST_STALE_HOURS)
        sp.add_argument("--semantic", choices=("auto", "deepseek", "codex", "deterministic", "off"),
                        default=DEFAULT_SEMANTIC)
        sp.add_argument("--model", default="deepseek-flash")
        sp.add_argument("--codex-model", default=None,
                        help="model slug for the Codex CLI semantic pass "
                             "(default: the discovery default)")
        sp.add_argument("--batch-size", type=int, default=8)
        sp.add_argument("--max-tokens", type=int, default=None)
        sp.add_argument("--codex", choices=("on", "off"), default=DEFAULT_CODEX_ESCALATION)
        sp.add_argument("--codex-budget", type=int, default=DEFAULT_CODEX_BUDGET)
        sp.add_argument("--out-dir")
        sp.add_argument("--web-out-dir")
        sp.add_argument("--state-file")
        sp.add_argument("--state-file-out")
        sp.add_argument("--no-lock", action="store_true")

    p = sub.add_parser("run")
    add_run_args(p)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("run-all")
    add_run_args(p)
    p.set_defaults(fn=cmd_run_all)

    p = sub.add_parser("coverage")
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_coverage)

    p = sub.add_parser("status")
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("selftest")
    p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    if getattr(args, "mode", DEFAULT_MODE) == DIAGNOSTIC_MODE and not getattr(args, "compare",
                                                                              False):
        emit({"ok": False, "status": "refused",
              "reason": ("intern_only is a diagnostic compare mode; pass --compare to run it "
                         f"explicitly. The production discovery policy is {DEFAULT_MODE}.")})
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
