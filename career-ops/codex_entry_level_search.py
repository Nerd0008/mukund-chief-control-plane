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
from career_search_recall import posting_key, query_batches
from posting_identity import identity_keys
from application_deadlines import deadline_from_value, deadline_label, deadline_priority

CODEX_EXE = Path(os.environ.get(
    "CAREER_OPS_CODEX_EXE",
    r"C:\Users\mukun\AppData\Local\hermes\node\codex.cmd"))
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
    "For each result return: job_title, company, location, url, experience_requirements.\n\n"
    "Resolve the original employer/ATS individual vacancy URL by following the advert's Apply link. "
    "Prefer that verified original destination in url, with the discovery page in source_url. "
    "Check the employer, role and intake agree across both pages. Never use a category/search page "
    "as an individual job URL or associate an adjacent listing's employer with the role. "
    "If only a specific aggregator advert can be retrieved, retain its real URL for local resolution; "
    "never guess an employer URL or claim a blocked destination is open.\n\n"
    "Include a result only if it is for someone at the very start of their career: "
    "graduate, intern, internship, junior, entry level, trainee, apprentice, new grad, "
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
    return any(m in t for m in (entry_markers or ENTRY_MARKERS))


def run_codex(prompt: str, timeout: int = 600) -> str:
    """Run one Codex live-web search and return its raw stdout."""
    proc = subprocess.run(  # noqa: S603
        [str(CODEX_EXE), "exec", "-m", CODEX_MODEL, "--sandbox", "read-only", "-"],
        input=prompt, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    return (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")


def parse_jobs(text: str) -> list:
    """Pull every JSON job array out of a Codex transcript; return the largest."""
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
    return max(arrays, key=len)


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

    entry_terms, _clearance_terms, profile_sha = _profile_terms()
    try:profile = osp.load_profile()
    except osp.ProfileUnavailable:profile = {}
    batches = query_batches(profile, REGION_LABEL[args.region], QUERY_BATCHES[args.region], datetime.now().year)
    offset=args.batch_offset
    if offset<0:offset=datetime.now(timezone.utc).toordinal()%len(batches)
    offset%=len(batches)
    batch_count=min(max(0,args.batches),len(batches))
    selected_batches=([0] if batch_count else [])
    for i in range(len(batches)):
        candidate=(offset+i)%len(batches)
        if candidate not in selected_batches and len(selected_batches)<batch_count:
            selected_batches.append(candidate)
    print(f"Search coverage: {batch_count} distinct batches; current/next-year and year-free queries")

    (existing_urls, existing_identities, ws, wb, cols, last_row, last_id) = read_tracker_urls(tracker)
    print(f"Tracker: {tracker.name}")
    print(f"Existing rows: {last_row - 1} (last id {last_id})")
    print(f"Running {batch_count} batch(es) from offset {offset} of {len(batches)}")

    existing_urls={posting_key(u) for u in existing_urls if posting_key(u)}
    seen = set()
    seen_identities = set()
    collected, rejected, decisions = [], [], []
    counts={'retrieved_records':0,'already_tracked':0,'repeated_in_run':0,'invalid_records':0,'timeouts':0,'review_only':0}
    for bi in selected_batches:
        queries = batches[bi]
        qtext = "\n".join(f"{i}. \"{q}\"" for i, q in enumerate(queries, 1))
        prompt = PROMPT_TEMPLATE.format(region=REGION_LABEL[args.region], queries=qtext)
        print(f"\n--- batch {bi}: {len(queries)} queries ---")
        try:
            out = run_codex(prompt, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            counts["timeouts"]+=1
            print(f"  batch {bi}: TIMEOUT after {args.timeout}s")
            continue
        jobs = parse_jobs(out)
        print(f"  batch {bi}: {len(jobs)} results returned")
        counts["retrieved_records"]+=len(jobs)
        for j in jobs:
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
            # Fetch full JD and check clearance/citizenship + liveness
            jd = fetch_jd(url)
            jd_text = jd.get("text") or ""
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
                counts['review_only']+=1
                decisions.append({'title':title,'url':url,'reason':'availability unverified; review-only lead','verification':verified})
                continue
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
            collected.append({
                "title": title,
                "company": str(j.get("company") or "").strip() or "Unknown",
                "location": str(j.get("location") or "").strip() or "Unknown",
                "url": url,
                "source_url": source_url,
                "application_resolution": jd.get('application_resolution'),
                "deadline": deadline or "",
                "deadline_info": jd.get("deadline_info") or deadline_from_value(deadline),
            })

    collected.sort(key=deadline_priority)
    print(f"\n=== {len(collected)} new entry-level roles, "
          f"{len(rejected)} rejected by eligibility/liveness/title checks ===")
    for c in collected:
        print(f"  + {c['company']} | {c['title']} | {c['location']} | Deadline: {deadline_label(c['deadline_info'])}")
    for t, _u, why in rejected[:10]:
        print(f"  - {t} ({why})")

    counts.update({'new_candidates':len(collected),'rejected':len(rejected),'distinct_query_batches':batch_count})
    decisions.extend({'title':t,'url':u,'reason':why} for t,u,why in rejected)
    decisions.extend({'title':j['title'],'url':j['url'],'source_url':j['source_url'],'application_resolution':j['application_resolution'],'reason':'new candidate','deadline_info':j['deadline_info']} for j in collected)
    print('SEARCH_RECONCILIATION '+json.dumps({'counts':counts,'decisions':decisions,'query_batches':[batches[i] for i in selected_batches],'profile_sha256':profile_sha},ensure_ascii=True))
    if not collected:
        print('No NEW eligible candidates; this does not mean no jobs were retrieved. See reconciliation counts.')
    if args.dry_run:
        wb.close()
        print("\n--dry-run: nothing written")
        return 0
    if not collected:
        wb.close()
        print("\nNo new roles; tracker unchanged.")
        return 0

    # The shared writer owns every append, lock, backup, fingerprint and verification.
    # Do not delete unrelated existing tracker rows during direct-search delivery.
    wb.close()
    import tracker_writer as tw
    profiles=tw.load_profiles()
    records=[{'company':job['company'],'title':job['title'],'location':job['location'],
              'url':job['url'],'date_found':datetime.now().date().isoformat(),
              'deadline':deadline_label(job['deadline_info']),
              'source':'Codex direct entry-level search'} for job in collected]
    canonical=Path(tw.region_config(profiles,args.region)['tracker'])
    backup_dir=profiles.get('backup_dir') if canonical.resolve()==tracker.resolve() else str(tracker.parent/'backups')
    try:
        result=tw.write_records(profiles,args.region,records,apply=True,
            tracker_override=str(tracker),backup_dir=backup_dir,cleanup_existing=False)
    except (ValueError,OSError) as exc:
        print('TRACKER_WRITE_BLOCKED '+str(exc),file=sys.stderr)
        return 2
    print('TRACKER_WRITE_RESULT '+json.dumps(result,default=str,ensure_ascii=True))
    if result.get('error'):
        print('Tracker write failed verification; no successful append claimed.',file=sys.stderr)
        return 2
    count=(result.get('counts') or {}).get('appended',0) if result.get('applied') else 0
    print(f"Guarded writer appended {count} rows; duplicates: {(result.get('counts') or {}).get('duplicates',0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
