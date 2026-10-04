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
    "Search the live web for entry-level cyber security jobs in {region} for 2026. "
    "I need roles specifically for 0-1 year experience candidates: graduate schemes, "
    "internships, junior roles, trainee roles, entry-level positions.\n\n"
    "Search these queries and return ALL results you actually retrieve:\n{queries}\n\n"
    "For each result return: job_title, company, location, url, experience_requirements.\n\n"
    "Include a result only if it is for someone at the very start of their career: "
    "graduate, intern, internship, junior, entry level, trainee, apprentice, new grad, "
    "or 0-1 year experience.\n"
    "Exclude senior, lead, principal, manager, head of, or any role asking for 3+ years.\n\n"
    "Return ONLY a JSON array. Never invent a result: if you did not retrieve it, omit it."
)

#: A title is entry-level when it carries one of these markers. Deterministic and
#: local — the model's own judgement is not trusted for the accept decision.
ENTRY_MARKERS = (
    "graduate", "intern", "internship", "junior", "entry level", "entry-level",
    "trainee", "apprentice", "apprenticeship", "new grad", "placement",
    "0-1 year", "0 - 1 year", "no experience", "fresher", "associate",
    "analyst", "scheme",
)
#: Hard negatives — a title carrying one of these is never entry-level.
SENIOR_MARKERS = (
    "senior", "lead ", "principal", "manager", "head of", "director",
    "vp ", "chief", "architect", "3+ year", "5+ year", "experienced",
)


def _tracker_columns(ws) -> dict:
    """Map header name -> column index (1-based) from the tracker's header row."""
    for row in ws.iter_rows(min_row=1, max_row=12):
        vals = [(c.value if isinstance(c.value, str) else None) for c in row]
        if vals and vals[0] and "job id" in str(vals[0]).lower():
            return {str(v).strip(): c.column for v, c in zip(vals, row) if v}
    return {}


def read_tracker_urls(path: Path):
    from openpyxl import load_workbook

    wb = load_workbook(path)
    ws = wb.active
    cols = _tracker_columns(ws)
    url_col = cols.get("Official URL") or cols.get("URL")
    urls = set()
    last_row, last_id = 9, None
    for row in ws.iter_rows(min_row=10, values_only=False):
        if row[0].value:
            last_row = row[0].row
            last_id = str(row[0].value)
        if url_col and len(row) >= url_col and row[url_col - 1].value:
            urls.add(str(row[url_col - 1].value).strip().lower().rstrip("/"))
    return urls, ws, wb, cols, last_row, last_id


def is_entry_level(title: str) -> bool:
    t = (title or "").lower()
    if any(m in t for m in SENIOR_MARKERS):
        return False
    return any(m in t for m in ENTRY_MARKERS)


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
    args = ap.parse_args()

    tracker = TRACKERS[args.region]
    if not tracker.exists():
        print(f"ERROR: tracker not found: {tracker}", file=sys.stderr)
        return 2

    batches = QUERY_BATCHES[args.region]
    offset = args.batch_offset
    if offset < 0:
        offset = datetime.now(timezone.utc).toordinal() % len(batches)

    (existing_urls, ws, wb, cols, last_row, last_id) = read_tracker_urls(tracker)
    print(f"Tracker: {tracker.name}")
    print(f"Existing rows: {last_row - 9} (last id {last_id})")
    print(f"Running {args.batches} batch(es) from offset {offset} of {len(batches)}")

    seen = set(existing_urls)
    collected, rejected = [], []
    for n in range(args.batches):
        bi = (offset + n) % len(batches)
        queries = batches[bi]
        qtext = "\n".join(f"{i}. \"{q}\"" for i, q in enumerate(queries, 1))
        prompt = PROMPT_TEMPLATE.format(region=REGION_LABEL[args.region], queries=qtext)
        print(f"\n--- batch {bi}: {len(queries)} queries ---")
        try:
            out = run_codex(prompt, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            print(f"  batch {bi}: TIMEOUT after {args.timeout}s")
            continue
        jobs = parse_jobs(out)
        print(f"  batch {bi}: {len(jobs)} results returned")
        for j in jobs:
            title = str(j.get("job_title") or j.get("title") or "").strip()
            url = str(j.get("url") or "").strip()
            key = url.lower().rstrip("/")
            if not url or not title:
                continue
            if key in seen:
                continue
            if not is_entry_level(title):
                rejected.append((title, url, "not entry-level by title"))
                continue
            seen.add(key)
            collected.append({
                "title": title,
                "company": str(j.get("company") or "").strip() or "Unknown",
                "location": str(j.get("location") or "").strip() or "Unknown",
                "url": url,
            })

    print(f"\n=== {len(collected)} new entry-level roles, "
          f"{len(rejected)} rejected by title filter ===")
    for c in collected:
        print(f"  + {c['company']} | {c['title']} | {c['location']}")
    for t, _u, why in rejected[:10]:
        print(f"  - {t} ({why})")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    if not collected:
        print("\nNo new roles; tracker unchanged.")
        return 0

    from openpyxl import load_workbook  # noqa: F401  (already imported above)

    base = int(str(last_id).lstrip("J") or 0) if last_id else 0
    for i, job in enumerate(collected):
        r = last_row + 1 + i
        ws.cell(row=r, column=1, value=f"J{base + 1 + i}")
        ws.cell(row=r, column=2, value=datetime.now().replace(hour=0, minute=0,
                                                              second=0, microsecond=0))
        ws.cell(row=r, column=3, value=job["company"])
        ws.cell(row=r, column=4, value=job["title"])
        ws.cell(row=r, column=5, value=job["location"])
        ws.cell(row=r, column=9, value="Uncertain")
        ws.cell(row=r, column=10, value="To Review")
        if cols.get("Official URL"):
            ws.cell(row=r, column=cols["Official URL"], value=job["url"])
        if cols.get("Discovery"):
            ws.cell(row=r, column=cols["Discovery"], value="Codex direct search")
    wb.save(tracker)
    print(f"\nWrote {len(collected)} rows; tracker now ends at J{base + len(collected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
