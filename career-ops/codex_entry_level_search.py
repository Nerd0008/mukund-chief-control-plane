#!/usr/bin/env python3
"""Codex direct entry-level job search -> UK tracker.

Why this exists
---------------
The bounded discovery pipeline (``discovery/scheduled_orchestrator.py``) is a
high-recall *funnel*: it collects every posting at watched companies and lets a
classifier sort them. That is the right shape for coverage, but it is a poor
shape for *volume of genuinely entry-level vacancies*, because most of what it
collects is mid-level noise and the queries it runs must satisfy a strict
site/level/discipline grammar.

The owner's own working method was simpler and more productive: ask the model to
search the live web for the specific roles wanted, and read the list back. This
script does exactly that, in a bounded, read-only, no-fabrication way:

  1. Ask the Codex CLI (live web search) for entry-level UK cyber vacancies
     across a rotating set of query batches.
  2. Parse the JSON array the model returns.
  3. Drop anything already in the tracker (by URL) and anything that does not
     look entry-level by title.
  4. Append the survivors to the canonical UK tracker workbook.

Nothing is invented: a row is written only when the model returned a URL, and the
title filter is a deterministic local check, not a model claim.

Usage
-----
    python codex_entry_level_search.py --region uk
    python codex_entry_level_search.py --region uk --batches 3 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent

# JD fetcher for clearance/eligibility checks against full job descriptions
sys.path.insert(0, str(HERE))
from jd_fetcher import fetch_jd
from job_liveness import record_verification

# Owner profile: the search vocabulary and eligibility facts come from the
# owner's own Career Ops config/profile.yml, not a hardcoded list here.
import owner_search_profile as osp
from career_search_recall import posting_key, query_batches, select_batches
from posting_identity import identity_keys
from application_deadlines import deadline_from_value, deadline_label, deadline_priority

CODEX_EXE = Path(os.environ.get(
    "CAREER_OPS_CODEX_EXE",
    r"C:\Users\mukun\AppData\Local\hermes\node\codex.cmd"))
SEARCH_STATE_DIR = Path(os.environ.get('LOCALAPPDATA', str(CONTROL_PLANE / 'runtime'))) / 'hermes/runtime/career-ops/direct-search'

CODEX_MODEL = os.environ.get("CAREER_OPS_CODEX_MODEL", "gpt-6-sol")

TRACKER_DIR = Path(r"C:\Users\mukun\Downloads\codex")
TRACKERS = {
    "uk": TRACKER_DIR / "uk-cyber-job-tracker.xlsx",
    "dubai": TRACKER_DIR / "Dubai_Cybersecurity_Job_Tracker.xlsx",
    "japan": TRACKER_DIR / "Japan_Cybersecurity_Job_Tracker.xlsx",
    "singapore": TRACKER_DIR / "Singapore_Cybersecurity_Job_Tracker.xlsx",
}

REGION_LABEL = {
    "uk": "the UK",
    "dubai": "Dubai / the UAE",
    "japan": "Japan",
    "singapore": "Singapore",
}

#: Query batches, rotated per run so repeated runs cover different ground.
#: Every batch targets 0-1 year experience: graduate schemes, internships,
#: junior/trainee/entry-level roles.
QUERY_BATCHES: dict[str, list[list[str]]] = {
    "uk": [
        [
            "cyber security graduate jobs UK 2026",
            "cyber security internship UK 2026",
            "junior cyber security analyst UK",
            "entry level information security jobs UK",
            "cyber security graduate scheme London 2026",
            "SOC analyst entry level UK 2026",
        ],
        [
            "graduate scheme cyber security UK 2026",
            "junior security analyst UK 2026",
            "cyber security internship London 2026",
            "entry level SOC analyst UK",
            "information security graduate programme UK 2026",
            "cyber security trainee UK 2026",
            "GRC graduate UK 2026",
        ],
        [
            "cyber security graduate scheme 2026 UK",
            "information security internship 2026 UK",
            "junior cyber security engineer UK 2026",
            "entry level cyber security consultant UK",
            "cyber security apprenticeship UK 2026",
            "graduate security analyst UK 2026",
            "junior GRC analyst UK 2026",
        ],
        [
            "graduate cyber security analyst UK 2026",
            "junior penetration tester UK 2026",
            "security operations centre analyst graduate UK",
            "IAM graduate programme UK 2026",
            "cyber security industrial placement UK 2026",
            "information security analyst entry level UK 2026",
            "cyber risk graduate UK 2026",
        ],
        [
            "cyber security summer internship UK 2026",
            "graduate technology risk UK 2026",
            "junior SOC analyst London 2026",
            "cyber security analyst no experience UK",
            "digital forensics graduate UK 2026",
            "security engineer graduate UK 2026",
            "cyber security 12 month placement UK 2026",
        ],
    ],
    "dubai": [
        [
            "cyber security graduate jobs Dubai 2026",
            "cyber security internship Dubai 2026",
            "junior cyber security analyst Dubai",
            "entry level information security jobs UAE",
            "cyber security graduate programme UAE 2026",
        ],
        [
            "SOC analyst entry level Dubai 2026",
            "cyber security trainee UAE 2026",
            "graduate security analyst Dubai 2026",
            "information security internship Abu Dhabi 2026",
            "cyber security fresher jobs Dubai",
        ],
    ],
    "japan": [
        [
            "cyber security graduate jobs Japan 2026",
            "cyber security internship Tokyo 2026",
            "junior cyber security analyst Tokyo",
            "entry level information security jobs Japan",
            "cyber security new graduate Japan 2026",
        ],
        [
            "SOC analyst entry level Tokyo 2026",
            "cyber security trainee Japan 2026",
            "graduate security analyst Tokyo 2026",
            "information security internship Japan 2026",
            "cyber security fresher jobs Tokyo",
        ],
    ],
    "singapore": [
        [
            "cyber security graduate jobs Singapore 2026",
            "cyber security internship Singapore 2026",
            "junior cyber security analyst Singapore",
            "entry level information security jobs Singapore",
            "cyber security graduate programme Singapore 2026",
        ],
        [
            "SOC analyst entry level Singapore 2026",
            "cyber security trainee Singapore 2026",
            "graduate security analyst Singapore 2026",
            "information security internship Singapore 2026",
            "cyber security fresher jobs Singapore",
        ],
    ],
}

PROMPT_TEMPLATE = (
    "Search the live web for entry-level cyber security jobs in {region} for current and upcoming intakes. "
    "I need roles specifically for 0-1 year experience candidates: graduate schemes, "
    "internships, junior roles, trainee roles, entry-level positions.\n\n"
    "Search these queries and return ALL results you actually retrieve:\n{queries}\n\n"
    "For each result return: job_title, company, location, country, url, experience_requirements. Country must come from the vacancy evidence; use null when unknown, never infer it from the search query.\n\n"
    "Resolve the original employer/ATS individual vacancy URL by following the advert's Apply link. "
    "Prefer that verified original destination in url, with the discovery page in source_url. "
    "Check the employer, role and intake agree across both pages. Never use a category/search page "
    "as an individual job URL or associate an adjacent listing's employer with the role. "
    "If only a specific aggregator advert can be retrieved, retain its real URL for local resolution; "
    "never guess an employer URL or claim a blocked destination is open.\n\n"
    "Include a result only if it is for someone at the very start of their career: "
    "graduate, intern, internship, junior, entry level, trainee, new grad, "
    "or 0-1 year experience.\n"
    "Exclude senior, lead, principal, manager, head of, or any role asking for 3+ years.\n\n"
    "Return ONLY a JSON array. Never invent a result: if you did not retrieve it, omit it."
)

#: A title is entry-level when it carries one of these markers. Deterministic and
#: local — the model's own judgement is not trusted for the accept decision.
#: This is the fallback list; the live vocabulary comes from the owner profile
#: (``owner_search_profile.entry_level_terms``) so a profile edit changes the
#: search. Kept as the floor so a profile with no readable entry words still
#: gates on the known-good terms rather than accepting everything.
ENTRY_MARKERS = (
    "graduate", "intern", "internship", "junior", "entry level", "entry-level",
    "trainee", "apprentice", "apprenticeship", "new grad", "placement",
    "0-1 year", "0 - 1 year", "no experience", "fresher", "associate",
    "scheme",
)
# Removed: "analyst", "engineer" — these matched mid-level roles like
# "Security Analyst" and "Software Engineer" that are not internships.
# A title must carry an explicit early-career signal; a job title that only
# says "analyst" or "engineer" is not entry-level.
#: Hard negatives — a title carrying one of these is never entry-level.
SENIOR_MARKERS = (
    "senior", "lead ", "principal", "manager", "head of", "director",
    "vp ", "chief", "architect", "3+ year", "5+ year", "experienced",
)

#: Clearance/citizenship tokens — checked against the FULL JD text, not just
#: the title. A job requiring SC/DV/CTC or British citizenship is not eligible
#: for the owner (Indian citizen on UK Graduate visa). Phrases allow a hyphen
#: or space so the owner's own hyphenated spelling matches an advert's spaced
#: one.
#:
#: The canonical implementation lives in ``clearance_screening``; this lane no
#: longer keeps its own copy of the regex.
from clearance_screening import (  # noqa: E402
    clearance_evidence,
    clearance_hits,
)
from experience_screening import experience_hits  # noqa: E402


def _profile_terms():
    """Live entry-level vocabulary from the owner profile; fallback on failure.

    Returns ``(entry_terms, clearance_terms, profile_sha256)``. A profile that
    cannot be read is reported on stderr and the known-good fallback is used —
    the run continues, but the artifact records that it was not profile-driven.
    """
    try:
        profile = osp.load_profile()
        entry = tuple(dict.fromkeys((*ENTRY_MARKERS, 'off-cycle', *osp.entry_level_terms(profile))))
        clearance = tuple(osp.clearance_terms(profile))
        return entry, clearance, osp.profile_digest()
    except osp.ProfileUnavailable as exc:
        print(f"[profile] owner profile unavailable ({exc}); "
              f"using the built-in entry-level vocabulary", file=sys.stderr)
        return ENTRY_MARKERS, (), None


def _tracker_columns(ws) -> dict:
    """Map header name -> column index (1-based) from the tracker's header row.

    The UK tracker has a title row at row 1 and headers at row 2.
    Regional trackers have headers at row 1. We scan for the row that
    contains 'Company' and ('Job Title' or 'Role Title').
    """
    for row in ws.iter_rows(min_row=1, max_row=12):
        vals = [(c.value if isinstance(c.value, str) else None) for c in row]
        joined = " ".join(v.lower() for v in vals if v)
        if "company" in joined and ("job title" in joined or "role title" in joined):
            return {str(v).strip(): c.column for v, c in zip(vals, row) if v}
    return {}


def read_tracker_urls(path: Path):
    from openpyxl import load_workbook

    wb = load_workbook(path)
    ws = wb.active
    cols = _tracker_columns(ws)

    # URL column: UK uses "Apply Link", others use "Direct Application URL"
    url_col = (cols.get("Apply Link") or cols.get("Official URL")
               or cols.get("Direct Application URL") or cols.get("URL"))

    # ID column: UK tracker no longer has one
    id_col = cols.get("Job ID")

    urls = set()
    identities = set()
    company_col = cols.get("Company")
    last_row, last_id = 1, None
    for row in ws.iter_rows(min_row=2, values_only=False):
        # Track the last row that has any data in column A
        if row[0].value:
            last_row = row[0].row
            if id_col and len(row) >= id_col and row[id_col - 1].value:
                last_id = str(row[id_col - 1].value)
        if url_col and len(row) >= url_col and row[url_col - 1].value:
            value = row[url_col - 1].value
            urls.add(posting_key(value))
            # Requisition-scoped identity: the same vacancy reached through an
            # employer ATS URL and an aggregator URL must not become two rows.
            company = row[company_col - 1].value if company_col and len(row) >= company_col else None
            identities |= identity_keys(company, value)
    return urls, identities, ws, wb, cols, last_row, last_id


def is_entry_level(title: str, entry_markers=None) -> bool:
    t = (title or "").lower()
    if any(m in t for m in SENIOR_MARKERS):
        return False
    if any(m in t for m in (entry_markers or ENTRY_MARKERS)):return True
    sys.path.insert(0,str(HERE/'discovery'))
    from title_policy import tier_a_signals
    return bool(re.search(r'\b(?:analyst|technician|engineer|helpdesk|service desk|support|administrator)\b',t)
                and tier_a_signals(title)['discipline_families'])


class SearchUnavailable(RuntimeError):
    def __init__(self, evidence):
        super().__init__('search unavailable or live web_search not observed')
        self.evidence = evidence


class SearchResponse(str):
    def __new__(cls,text,evidence):
        response=super().__new__(cls,text);response.evidence=evidence;return response


def run_codex(prompt: str, timeout: int = 600, *, progress_path=None, persist_progress=True) -> str:
    """Run each requested query in its own observed worker within one budget.

    A search event from one query cannot certify the other five queries. Keep
    partial discoveries and their coverage receipt, but never call a partial
    batch complete or write its candidates automatically.
    """
    sys.path.insert(0, str(HERE / 'discovery'))
    from web_research import CodexWebSearchProvider
    provider = CodexWebSearchProvider(executable=CODEX_EXE, model=CODEX_MODEL)
    executable = provider.resolve()
    query_pattern = r'^\d+\.\s+"([^"\n]+)"\s*$'
    queries = re.findall(query_pattern, prompt, re.M)
    single_legacy_call = not queries
    queries = queries or ['bounded direct career search']
    started = time.monotonic()
    from contextlib import nullcontext
    import query_progress
    from router_brain import RouterDecisionError
    key = query_progress.signature(prompt, CODEX_MODEL)
    saved = query_progress.load(progress_path, key, queries)
    results, receipts = [], []
    batch = provider.authorize_batch(executable, queries, timeout) if hasattr(provider, 'authorize_batch') else nullcontext()
    try:
        with batch:
            pending = sum(q not in saved for q in queries)
            available = timeout - (time.monotonic() - started)
            # Allocate once after router authorization. Process overhead or an
            # earlier timeout must not progressively shrink later worker budgets.
            per_query = max(1, int(available / max(1, pending)))
            for index, query in enumerate(queries):
                resumed = query in saved
                remaining = timeout - (time.monotonic() - started)
                if not resumed and remaining < per_query:
                    receipts.append({'requested_query': query, 'complete': False,
                        'error': 'batch elapsed budget exhausted', 'executed_queries': []})
                    continue
                worker_prompt = prompt
                if not single_legacy_call:
                    worker_prompt = re.sub(query_pattern,
                        lambda match: f'1. "{query}"' if match.group(1) == query else '', prompt, flags=re.M)
                    worker_prompt += '\nExecute EXACTLY this one query: ' + query + '\n'
                result = saved[query] if resumed else provider._run_one(executable, query, limit=100,
                    timeout=per_query, prompt=worker_prompt)
                complete = bool(result.get('web_search_observed')) and not result.get('error')
                receipts.append({'requested_query': query, 'complete': complete, 'resumed': resumed,
                    'observed_at': result.get('observed_at'),
                    'web_search_observed': bool(result.get('web_search_observed')),
                    'executed_queries': result.get('executed_queries') or [],
                    'raw_events': result.get('raw_events', 0), 'error': result.get('error'),
                    'results_returned': len(result.get('results') or [])})
                print(f"  query {index + 1}/{len(queries)}: {'complete' if complete else 'INCOMPLETE'}; {len(result.get('results') or [])} records", flush=True)
                if complete:
                    results.extend(result.get('results') or [])
                    if not resumed:
                        saved[query] = {k: result.get(k) for k in ('results','web_search_observed','executed_queries','raw_events')}
                        saved[query]['observed_at'] = time.time()
                        receipts[-1]['observed_at'] = saved[query]['observed_at']
                        if persist_progress:
                            query_progress.save(progress_path, key, saved)
                if result.get('routing_blocked'):
                    receipts.extend({'requested_query': q, 'complete': False,
                        'error': 'not_attempted_after_routing_block', 'executed_queries': []} for q in queries[index+1:])
                    break
    except RouterDecisionError as exc:
        receipts = [{'requested_query': q, 'complete': False, 'error': str(exc),
                     'executed_queries': []} for q in queries]
    completed = sum(receipt['complete'] for receipt in receipts)
    evidence = {'web_search_observed': bool(completed), 'queries_requested': len(queries),
                'queries_completed': completed, 'coverage_complete': completed == len(queries),
                'query_receipts': receipts, 'retrieved_records': results,
                'executed_queries': [q for r in receipts for q in r.get('executed_queries', [])],
                'raw_events': sum(r.get('raw_events') or 0 for r in receipts),
                'elapsed_s': round(time.monotonic() - started, 2)}
    if not completed:
        raise SearchUnavailable(evidence)
    return SearchResponse(json.dumps(results, ensure_ascii=True), evidence)


def parse_jobs(text: str) -> list:
    """Pull every JSON job array out of a Codex transcript; combine unique records."""
    dec = json.JSONDecoder()
    arrays, idx = [], 0
    while True:
        start = text.find("[", idx)
        if start < 0:
            break
        try:
            obj, end = dec.raw_decode(text[start:])
            if (isinstance(obj, list) and obj and isinstance(obj[0], dict)
                    and any(k in obj[0] for k in ("job_title", "title"))):
                arrays.append(obj)
            idx = start + end
        except Exception:  # noqa: BLE001 - not a JSON array here; keep scanning
            idx = start + 1
    if not arrays:
        return []
    merged=[];seen=set()
    for array in arrays:
        for record in array:
            key=json.dumps(record,sort_keys=True)
            if key not in seen: merged.append(record);seen.add(key)
    return merged


def writer_records(collected):
    return [{'company':job['company'],'title':job['title'],'location':job['location'],
             'url':job['url'],'date_found':datetime.now().date().isoformat(),
             'deadline':deadline_label(job['deadline_info']),'availability':job['availability'],
             'source':'Codex direct entry-level search'} for job in collected]


def retry_country_records(pending, fresh):
    """Restore source-backed country only for the exact same posting/company/title.

    A fresh explicit country always wins, including a conflicting foreign one.
    No employer, title, region, deadline or availability is inferred here.
    """
    def key(row):
        return (posting_key(row.get('url')), str(row.get('company') or '').strip().casefold(),
                str(row.get('job_title') or row.get('title') or '').strip().casefold())
    prior = {key(row): row for row in pending if isinstance(row, dict)}
    result = []
    for source in fresh:
        row = dict(source)
        previous = prior.get(key(row), {})
        if not row.get('country') and not row.get('country_code'):
            row.update({field: previous[field] for field in ('country','country_code')
                        if isinstance(previous.get(field), str) and previous[field].strip()})
        result.append(row)
    return result


def retain_candidates(region, collected, reason):
    """Atomic private retry queue; never replay saved eligibility as authority."""
    import uuid
    SEARCH_STATE_DIR.mkdir(parents=True,exist_ok=True)
    path=SEARCH_STATE_DIR/(region+'-blocked-candidates.json')
    try:old=json.loads(path.read_text(encoding='utf-8')).get('records',[])
    except (OSError,ValueError,TypeError):old=[]
    records={posting_key(r.get('url')):r for r in old if isinstance(r,dict) and posting_key(r.get('url'))}
    for original, record in zip(collected, writer_records(collected)):
        # Private retry provenance is richer than the six-column writer input.
        record.update({k: original[k] for k in ('country','country_code') if original.get(k)})
        records[posting_key(record['url'])] = record
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps({'records':list(records.values()),'created_at':datetime.now(timezone.utc).isoformat(),
            'requires_fresh_verification':True,'reason':reason},ensure_ascii=True),encoding='utf-8')
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
    return path


def canonical_plan(region, tracker, collected):
    import tracker_writer as tw
    return tw.write_records(tw.load_profiles(),region,writer_records(collected),apply=False,
                            tracker_override=str(tracker),cleanup_existing=False)


def cursor_file(region, tracker):
    import hashlib
    key=hashlib.sha256(str(tracker.resolve()).encode()).hexdigest()[:12]
    return SEARCH_STATE_DIR / f'{region}-{key}.json'


def read_cursor(path, fallback):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))['next_offset']
        return value if isinstance(value,int) and value>=0 else fallback
    except (OSError,ValueError,KeyError,TypeError):return fallback


def save_cursor(path, offset):
    import uuid
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps({'next_offset':offset,'updated_at':datetime.now(timezone.utc).isoformat()}),encoding='utf-8')
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="uk", choices=sorted(TRACKERS))
    ap.add_argument("--batches", type=int, default=1,
                    help="how many query batches to run this invocation")
    ap.add_argument("--batch-offset", type=int, default=-1,
                    help="start at this batch index (-1 = rotate by day)")
    ap.add_argument("--timeout", type=int, default=600, help="per-batch Codex timeout")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be added; write nothing")
    ap.add_argument("--show-profile", action="store_true",
                    help="print the resolved profile-driven search block and exit")
    args = ap.parse_args()
    run_deadline = time.time() + max(1, args.timeout * max(1, args.batches)) + 180

    if args.show_profile:
        import json as _json
        try:
            snap = osp.snapshot()
            snap["queries"] = osp.search_queries(
                osp.load_profile(), REGION_LABEL[args.region])
        except osp.ProfileUnavailable as exc:
            print(f"owner profile unavailable: {exc}", file=sys.stderr)
            return 2
        print(_json.dumps(snap, indent=2, ensure_ascii=False))
        return 0

    tracker = TRACKERS[args.region]
    if not tracker.exists():
        print(f"ERROR: tracker not found: {tracker}", file=sys.stderr)
        return 2

    from effective_search_policy import effective_policy, role_decision
    resolved_policy = effective_policy(args.region)
    print("EFFECTIVE_SEARCH_POLICY " + json.dumps(resolved_policy, ensure_ascii=True))
    entry_terms, _clearance_terms, profile_sha = _profile_terms()
    try:profile = osp.load_profile()
    except osp.ProfileUnavailable:profile = {}
    batches = query_batches(profile, REGION_LABEL[args.region], QUERY_BATCHES[args.region], datetime.now().year)
    offset=args.batch_offset
    cursor=cursor_file(args.region,tracker)
    if offset<0:offset=read_cursor(cursor,datetime.now(timezone.utc).toordinal()%len(batches))
    offset%=len(batches)
    batch_count=min(max(0,args.batches),len(batches))
    selected_batches=select_batches(len(batches),batch_count,offset)
    print(f"Search coverage: {batch_count} distinct batches; current/next-year and year-free queries")

    (existing_urls, existing_identities, ws, wb, cols, last_row, last_id) = read_tracker_urls(tracker)
    print(f"Tracker: {tracker.name}")
    print(f"Existing rows: {last_row - 1} (last id {last_id})")
    print(f"Running {batch_count} batch(es) from offset {offset} of {len(batches)}")

    existing_urls={posting_key(u) for u in existing_urls if posting_key(u)}
    seen = set()
    seen_identities = set()
    collected, rejected, decisions = [], [], []
    evidence_files = []
    counts={'retrieved_records':0,'already_tracked':0,'repeated_in_run':0,'invalid_records':0,'timeouts':0,'review_only':0,'incomplete_batches':0,'verification_budget_exhausted':0}
    sys.path.insert(0,str(HERE/'discovery'))
    import pipeline as shared_pipeline, regional_job_search as rjs
    from title_policy import tier_a_signals
    from posting_resolution import PostingResolver
    from web_research import CodexWebSearchProvider
    resolver=PostingResolver(CodexWebSearchProvider(executable=CODEX_EXE,model=CODEX_MODEL),
        state_path=SEARCH_STATE_DIR/(args.region+'-posting-recovery.json'), deadline=run_deadline)
    policy=rjs.load_policy();scope=rjs.lane_scope(args.region,rjs.load_schedules()['regions'][args.region])
    rate_limited_hosts=set()
    completed_batches=[]
    execution_evidence=[]
    pending_path=SEARCH_STATE_DIR/(args.region+'-blocked-candidates.json')
    try:
        pending_records=json.loads(pending_path.read_text(encoding='utf-8')).get('records',[])
        if not isinstance(pending_records,list):pending_records=[]
    except (OSError,ValueError,TypeError):pending_records=[]
    # Retry retained discoveries through ALL current checks, never replay old
    # OPEN/deadline claims or write a saved manifest blindly.
    # Fresh source metadata takes precedence over a retained copy of the same posting.
    work_batches=selected_batches+([-1] if pending_records else [])
    for bi in work_batches:
        queries = batches[bi] if bi>=0 else []
        qtext = "\n".join(f"{i}. \"{q}\"" for i, q in enumerate(queries, 1))
        prompt = PROMPT_TEMPLATE.format(region=REGION_LABEL[args.region], queries=qtext)
        print(f"\n--- batch {bi}: {len(queries)} queries ---")
        try:
            progress_path = SEARCH_STATE_DIR / f'{args.region}-query-progress-{bi}.json'
            out = run_codex(prompt, timeout=args.timeout, progress_path=progress_path,
                            persist_progress=not args.dry_run) if bi>=0 else json.dumps(pending_records)
        except (RuntimeError,OSError) as exc:
            if isinstance(exc, SearchUnavailable):
                print('SEARCH_COVERAGE ' + json.dumps({'coverage_complete':False,
                    'query_receipts':[{'batch':bi, **exc.evidence}], 'market_exhausted':False}))
            print('SEARCH_FAILED '+str(exc),file=sys.stderr)
            return 2
        except subprocess.TimeoutExpired:
            counts["timeouts"]+=1
            print(f"  batch {bi}: TIMEOUT after {args.timeout}s")
            continue
        if bi>=0:
            completed_batches.append(bi)
            execution_evidence.append({"batch":bi,**(getattr(out,"evidence",None) or {"web_search_observed":None,"note":"execution evidence not supplied by injected worker"})})
        if getattr(out, "evidence", {}).get("coverage_complete") is False:
            counts["incomplete_batches"] += 1
        jobs = retry_country_records(pending_records, parse_jobs(out)) if bi >= 0 else parse_jobs(out)
        print(f"  batch {bi}: {len(jobs)} results returned")
        counts["retrieved_records"]+=len(jobs)
        for j in jobs:
            if time.time() >= run_deadline:
                counts["verification_budget_exhausted"] += 1
                break
            title = str(j.get("job_title") or j.get("title") or "").strip()
            url = str(j.get("url") or "").strip()
            key = posting_key(url)
            if not key or not title:
                counts['invalid_records']+=1
                decisions.append({'title':title,'reason':'invalid title or posting URL'})
                continue
            job_identities = identity_keys(j.get("company"), url)
            if key in existing_urls:
                counts['already_tracked']+=1
                decisions.append({'title':title,'url':url,'reason':'already tracked'})
                continue
            if job_identities & existing_identities:
                # A different URL naming the same ATS requisition: already applied for.
                counts['already_tracked']+=1
                decisions.append({'title':title,'url':url,
                                  'reason':'already tracked (same requisition, different URL)'})
                continue
            if key in seen or (job_identities & seen_identities):
                counts['repeated_in_run']+=1
                decisions.append({'title':title,'url':url,'reason':'repeated in this run'})
                continue
            seen.add(key)
            seen_identities |= job_identities
            if not is_entry_level(title, entry_terms):
                rejected.append((title, url, "not entry-level by title"))
                continue
            role_ok, role_reason = role_decision(args.region, title)
            if not role_ok:
                rejected.append((title, url, role_reason))
                continue
            title_signals=tier_a_signals(title)
            if title_signals['non_cyber'] and not title_signals['strong_cyber']:
                rejected.append((title,url,'non-cyber role title'))
                continue
            # Fetch full JD and check clearance/citizenship + liveness
            from urllib.parse import urlsplit
            from application_links import canonical_posting_url
            host=urlsplit(canonical_posting_url(url)).hostname
            if host in rate_limited_hosts:
                jd={'text':'','vacancy_status':{'state':'UNKNOWN','evidence':'rate limit backoff'}}
            else:
                jd = fetch_jd(url)
                if jd.get('status')==429:rate_limited_hosts.add(host)
            identity=jd.get('posting_identity') or jd.get('discovered_posting') or {}
            candidate={'company':identity.get('company') or j.get('company'),
                'title':identity.get('title') or title,'location':identity.get('location') or j.get('location'),
                'country':identity.get('country') or j.get('country'),
                'country_code':identity.get('country_code') or j.get('country_code'),
                'posting_identity':identity, 'url':url}
            if (jd.get('vacancy_status') or {}).get('state')=='UNKNOWN':
                recovered=resolver(candidate,jd)
                if recovered:jd=recovered
            jd_text = jd.get("text") or ""
            from verification_evidence import save_evidence
            evidence_files.append({"title": title, "url": url,
                                   "path": save_evidence(candidate, jd)})
            verified=record_verification({'company':j.get('company') or 'Unknown','title':title,'url':url},jd)
            if jd.get("is_closed") or verified['state']=='CLOSED':
                rejected.append((title, url, "job page says position is closed/filled"))
                continue
            deadline = jd.get("deadline")
            if deadline:
                import datetime as _dt
                try:
                    dl = _dt.date.fromisoformat(deadline)
                    if dl < _dt.date.today():
                        rejected.append((title, url, f"deadline passed ({deadline})"))
                        continue
                except ValueError:
                    pass
            if verified['state']!='OPEN':
                counts['unverified_candidates']=counts.get('unverified_candidates',0)+1
                decisions.append({'title':title,'url':url,'reason':'availability UNVERIFIED; retained as flagged lead','verification':verified})
            source_url=url
            url=verified.get('resolved_url') or url
            resolved_key=posting_key(url)
            resolved_identities=identity_keys(j.get("company"), source_url, url)
            if url!=source_url and (resolved_key in existing_urls
                                    or resolved_identities & existing_identities):
                counts['already_tracked']+=1
                decisions.append({'title':title,'url':url,'source_url':source_url,'reason':'resolved employer posting already tracked'})
                continue
            if url!=source_url and (resolved_key in seen
                                    or resolved_identities & seen_identities):
                counts['repeated_in_run']+=1
                decisions.append({'title':title,'url':url,'source_url':source_url,'reason':'resolved employer posting repeated in this run'})
                continue
            seen.add(resolved_key)
            seen_identities |= resolved_identities
            if url!=source_url:
                record_verification({'company':j.get('company') or 'Unknown','title':title,'url':url},jd)
            clearance = clearance_hits(jd_text)
            if clearance:
                rejected.append((title, url, f"clearance/citizenship required: {', '.join(clearance)}"))
                continue
            # A title says nothing about the experience a role wants. "IT Support
            # Analyst" and "Cyber Security Analyst" pass the title gate whether
            # they want a graduate or five years on a service desk.
            experience = experience_hits(jd_text)
            if experience:
                rejected.append((title, url, f"prior experience required: {experience[0][:100]}"))
                continue
            identity=verified.get("posting_identity") or jd.get('discovered_posting') or {}
            candidate.update({k:v for k,v in identity.items() if k in ('company','title','location','country','country_code') and v})
            signals=tier_a_signals(' '.join((candidate.get('title') or '',jd_text)))
            if not signals['discipline_families']:
                rejected.append((title,url,'no supported cyber/IT discipline evidence'))
                continue
            candidate.update(jd_text=jd_text,vacancy_status=verified,jd_is_closed=jd.get('is_closed'),
                             deadline_info=jd.get('deadline_info'))
            gate=shared_pipeline.deterministic_gates(args.region,candidate,policy,scope)
            if gate['decision']!='accepted':
                rejected.append((title,url,'; '.join(gate['reasons'])))
                continue
            collected.append({
                "title": identity.get("title") or title,
                "company": identity.get("company") or str(j.get("company") or "").strip() or "Unknown",
                "location": identity.get("location") or str(j.get("location") or "").strip() or "Unknown",
                "country": candidate.get("country"),
                "country_code": candidate.get("country_code"),
                "url": url,
                "source_url": source_url,
                "availability": verified,
                "application_resolution": jd.get('application_resolution'),
                "deadline": deadline or "",
                "deadline_info": jd.get("deadline_info") or deadline_from_value(deadline),
            })

    collected.sort(key=deadline_priority)
    print(f"\n=== {len(collected)} eligible discoveries BEFORE canonical reconciliation, "
          f"{len(rejected)} rejected by eligibility/liveness/title checks ===")
    for c in collected:
        print(f"  + {c['company']} | {c['title']} | {c['location']} | Deadline: {deadline_label(c['deadline_info'])}")
    for t, _u, why in rejected[:10]:
        print(f"  - {t} ({why})")

    wb.close()
    try:
        probe=canonical_plan(args.region,tracker,collected) if collected else {'counts':{},'outcomes':[]}
    except (ValueError,OSError) as exc:
        if not args.dry_run:retain_candidates(args.region,collected,'canonical reconciliation unavailable')
        print('CANONICAL_RECONCILIATION_BLOCKED '+str(exc),file=sys.stderr)
        return 2
    if probe.get('error'):
        if not args.dry_run:retain_candidates(args.region,collected,'canonical reconciliation failed')
        print('CANONICAL_RECONCILIATION_BLOCKED '+str(probe['error']),file=sys.stderr)
        return 2
    canonical_counts=probe.get('counts') or {}
    duplicates=canonical_counts.get('duplicates',0)
    counts['already_tracked']+=duplicates
    counts['canonical_duplicates']=duplicates
    counts['review_only']=sum(job['availability']['state']!='OPEN' for job in collected)
    counts['eligible_candidates_before_canonical_dedupe']=len(collected)
    counts.update({'new_candidates':canonical_counts.get('appended',0),'rejected':len(rejected),'distinct_query_batches':batch_count})
    decisions.extend({'title':t,'url':u,'reason':why} for t,u,why in rejected)
    decisions.extend({'title':j['title'],'url':j['url'],'source_url':j['source_url'],'application_resolution':j['application_resolution'],'reason':'eligible discovery; see canonical outcome','deadline_info':j['deadline_info']} for j in collected)
    print('SEARCH_RECONCILIATION '+json.dumps({'counts':counts,'decisions':decisions,'query_batches':[batches[i] for i in selected_batches],'profile_sha256':profile_sha,'selected_batch_indices':selected_batches,'execution_evidence':execution_evidence,'canonical_outcomes':probe.get('outcomes',[]),'candidate_evidence':evidence_files},ensure_ascii=True))
    print(f"Canonical plan: {counts['new_candidates']} proposed NEW rows; {duplicates} duplicate rows avoided.")
    def advance():
        for batch_id in completed_batches:
            (SEARCH_STATE_DIR / f'{args.region}-query-progress-{batch_id}.json').unlink(missing_ok=True)
        if args.batch_offset<0 and completed_batches:
            save_cursor(cursor,(completed_batches[-1]+1)%len(batches))
    if not collected:
        print('No NEW eligible candidates; this does not mean no jobs were retrieved. See reconciliation counts.')
    coverage = {"requested_batches": batch_count, "query_pool_batches": len(batches),
                "completed_batches": len(completed_batches) - counts.get("incomplete_batches", 0),
                "coverage_complete": not counts["timeouts"] and not counts.get("incomplete_batches") and not counts.get("verification_budget_exhausted"),
                "query_receipts": execution_evidence,
                "market_exhausted": False}
    proposed_urls = {posting_key(row.get("url")) for row in probe.get("outcomes", []) if row.get("decision") == "appended"}
    proposals = [row for row in writer_records(collected) if posting_key(row.get("url")) in proposed_urls]
    print("SEARCH_PROPOSALS " + json.dumps({"records": proposals,
        "confirmed_open_proposals": sum(row["availability"]["state"] == "OPEN" for row in proposals),
        "availability_unverified_proposals": sum(row["availability"]["state"] != "OPEN" for row in proposals)}, ensure_ascii=True))
    print("SEARCH_COVERAGE " + json.dumps(coverage, ensure_ascii=True))
    if args.dry_run:
        print("\n--dry-run: tracker unchanged; no cursor advancement")
        return 2 if counts["timeouts"] or counts.get("incomplete_batches") or counts.get("verification_budget_exhausted") else 0
    if not coverage['coverage_complete']:
        retain_candidates(args.region,collected,'partial search or verification; retry with fresh verification')
        return 2
    if not counts['new_candidates']:
        if counts['timeouts']:return 2
        pending_path.unlink(missing_ok=True)
        advance()
        print("\nNo new roles; tracker unchanged.")
        return 0

    # The shared writer owns every append, lock, backup, fingerprint and verification.
    # Do not delete unrelated existing tracker rows during direct-search delivery.
    wb.close()
    import tracker_writer as tw
    profiles=tw.load_profiles()
    records=writer_records(collected)
    canonical=Path(tw.region_config(profiles,args.region)['tracker'])
    backup_dir=profiles.get('backup_dir') if canonical.resolve()==tracker.resolve() else str(tracker.parent/'backups')
    try:
        from tracker_delivery import write_or_defer
        result,deferred=write_or_defer(
            lambda: tw.write_records(profiles,args.region,records,apply=True,
                tracker_override=str(tracker),backup_dir=backup_dir,cleanup_existing=False),
            tracker,collected,
            lambda rows: retain_candidates(args.region,rows,'workbook in use; delivery deferred'),advance)
        if deferred:
            deferred['proposed_new_rows']=counts['new_candidates']
            print('TRACKER_WRITE_DEFERRED '+json.dumps(deferred,ensure_ascii=True))
            return 0
    except (ValueError,OSError) as exc:
        retain_candidates(args.region,collected,'writer unavailable')
        print('TRACKER_WRITE_FAILED '+json.dumps({'stage':'tracker_commit','applied':False,'error_type':type(exc).__name__,'winerror':getattr(exc,'winerror',None),'errno':getattr(exc,'errno',None)}))
        print('TRACKER_WRITE_BLOCKED '+str(exc),file=sys.stderr)
        return 2
    print('TRACKER_WRITE_RESULT '+json.dumps(result,default=str,ensure_ascii=True))
    appended_urls = {posting_key(row.get("url")) for row in result.get("outcomes", [])
                     if row.get("decision") == "appended"} if result.get("applied") and not result.get("error") else set()
    print("SEARCH_DELIVERY " + json.dumps({"records": [row for row in writer_records(collected)
          if posting_key(row.get("url")) in appended_urls]}, default=str, ensure_ascii=True))
    if result.get('error'):
        pending=retain_candidates(args.region,collected,'writer failed')
        print('Candidates retained for verified retry: '+str(pending))
        print('Tracker write failed verification; no successful append claimed.',file=sys.stderr)
        return 2
    count=(result.get('counts') or {}).get('appended',0) if result.get('applied') else 0
    if counts["timeouts"]:
        print("SEARCH_PARTIAL: one or more batches timed out",file=sys.stderr)
        return 2
    pending_path.unlink(missing_ok=True)
    advance()
    print(f"Guarded writer appended {count} rows; duplicates: {(result.get('counts') or {}).get('duplicates',0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
