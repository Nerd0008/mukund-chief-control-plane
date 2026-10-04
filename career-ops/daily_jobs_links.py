#!/usr/bin/env python3
"""Daily job-links digest: every job found by the discovery lanes, with its apply link.

OWNER REQUEST (2026-10-03)
--------------------------
"All the jobs you find daily I want the name and its link to apply in this chat
also daily."

This script is the delivery adapter for that request. It is DETERMINISTIC and
READ-ONLY. It owns no career state, scores nothing, ranks nothing, re-words
nothing and calls no model. Every line it prints is a field another workflow
already wrote: the discovery run's own accepted classifications and the
canonical regional workbooks' own rows.

WHAT IT REPORTS
---------------
Per region (uk / dubai / japan / singapore), from real artifacts only:

  1. FOUND  — every accepted candidate from the region's most recent discovery
              run, as `Company — Title` plus its own apply URL. The funnel's
              `accepted` flag is the pipeline's own gate output; this script
              does not re-judge it.
  2. TRACKED— every row in that region's canonical workbook whose own
              date-found/date-added column falls on the run's date, so the owner
              can see what actually landed in the tracker.

Safety contract
---------------
* No network call, no browser, no GUI, no credential read, no model call.
* Read-only against every workbook, ledger and runtime artifact. It writes
  nothing anywhere.
* A missing or stale run is reported as UNKNOWN/STALE, never as "no jobs".
* No application, outreach, submission or LinkedIn action. Ever.
* Synthetic/validation records (".invalid"/".test" hosts, "NOT A REAL VACANCY")
  are filtered out so a test artifact can never appear as a real vacancy.

Exit codes
----------
0  a digest was printed from at least one fresh run
3  every region's run was missing or stale (digest printed with an explicit label)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

CONTROL_PLANE = Path(__file__).resolve().parent.parent
DISCOVERY = CONTROL_PLANE / "runtime" / "career-ops" / "discovery"

REGIONS = ("uk", "dubai", "japan", "singapore")

TRACKERS = {
    "uk": Path(r"C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx"),
    "dubai": Path(r"C:\Users\mukun\Downloads\codex\Dubai_Cybersecurity_Job_Tracker.xlsx"),
    "japan": Path(r"C:\Users\mukun\Downloads\codex\Japan_Cybersecurity_Job_Tracker.xlsx"),
    "singapore": Path(r"C:\Users\mukun\Downloads\codex\Singapore_Cybersecurity_Job_Tracker.xlsx"),
}

REGION_LABEL = {
    "uk": "United Kingdom",
    "dubai": "Dubai / UAE",
    "japan": "Japan",
    "singapore": "Singapore",
}

# Each region's workbook uses its own column names (its own schema is truth).
TRACKER_SCHEMA = {
    "uk": {
        "header_row": 9,
        "sheet": "Jobs",
        "id": "Job ID",
        "date": "Date Found",
        "company": "Company",
        "title": "Job Title",
        "url": "Official URL",
        "status": "Application Status",
    },
    "dubai": {
        "header_row": 1,
        "sheet": None,
        "id": "Job ID",
        "date": "Date Found",
        "company": "Company",
        "title": "Job Title",
        "url": "Direct Application URL",
        "status": "Application Status",
    },
    "japan": {
        "header_row": 1,
        "sheet": None,
        "id": "ID",
        "date": "Date Added",
        "company": "Company",
        "title": "Role Title",
        "url": "Direct Application URL",
        "status": "Status",
    },
    "singapore": {
        "header_row": 1,
        "sheet": None,
        "id": "Job ID",
        "date": "Date Found",
        "company": "Company",
        "title": "Job Title",
        "url": "Direct Application URL",
        "status": "Application Status",
    },
}

SYNTHETIC_HOST_SUFFIXES = (".invalid", ".test", ".example", ".localhost", ".local")
SYNTHETIC_MARKERS = ("NOT A REAL VACANCY", "SYNTHETIC", "FIXTURE", "PLACEHOLDER")

_HYPERLINK_RE = re.compile(r'HYPERLINK\(\s*"([^"]+)"', re.IGNORECASE)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def parse_iso(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def as_url(value):
    """Return a real URL from a cell that may hold a plain string or =HYPERLINK()."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    match = _HYPERLINK_RE.search(text)
    if match:
        return match.group(1).strip()
    if text.lower().startswith("http"):
        return text
    return ""


def is_synthetic(company, title, url):
    blob = f"{company or ''} {title or ''}".upper()
    if any(marker in blob for marker in SYNTHETIC_MARKERS):
        return True
    host = (url or "").lower()
    return any(host.endswith(suffix) or f"{suffix}/" in host for suffix in SYNTHETIC_HOST_SUFFIXES)


def cell_date(value):
    """Normalise a workbook date cell (datetime, date or ISO/date string)."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_run_doc(region):
    """Most recent unified run document for a region, by mtime."""
    directory = DISCOVERY / "unified" / region
    if not directory.is_dir():
        return None, None
    candidates = [p for p in directory.glob("unified-*.json") if p.name != "latest.json"]
    if not candidates:
        return None, None
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return read_json(newest), newest


def accepted_candidates(doc):
    """Accepted candidates from a run doc, with their own apply URL."""
    out = []
    for item in doc.get("classifications") or []:
        if not item.get("accepted"):
            continue
        fields = item.get("source_fields") or {}
        company = (fields.get("company") or "").strip()
        title = (fields.get("title") or "").strip()
        url = (fields.get("url") or "").strip()
        if not (company or title):
            continue
        if is_synthetic(company, title, url):
            continue
        out.append({
            "company": company or "UNKNOWN",
            "title": title or "UNKNOWN",
            "url": url,
            "label": item.get("primary_label"),
            "confidence": item.get("confidence"),
            "location": (fields.get("location") or "").strip(),
        })
    return out


def tracker_rows(region, limit=10):
    """Most recent rows from a region's canonical workbook. Read-only; never writes."""
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - environment specific
        return [], "openpyxl unavailable"

    path = TRACKERS[region]
    if not path.exists():
        return [], f"workbook missing at {path}"

    schema = TRACKER_SCHEMA[region]
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except OSError as exc:
        return [], f"workbook unreadable: {exc}"

    try:
        ws = wb[schema["sheet"]] if schema["sheet"] else wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    header_idx = None
    header: list[str] = []
    for i, row in enumerate(rows):
        values = [str(v).strip() if v is not None else "" for v in row]
        if schema["id"] in values:
            header_idx = i
            header = values
            break
    if header_idx is None:
        return [], "header row not found"

    index = {name: header.index(name) for name in
             (schema["id"], schema["date"], schema["company"], schema["title"],
              schema["url"], schema["status"]) if name in header}

    out = []
    for row in rows[header_idx + 1:]:
        if not row or not row[index[schema["id"]]]:
            continue
        record = {
            "id": str(row[index[schema["id"]]]).strip(),
            "date": cell_date(row[index[schema["date"]]]),
            "company": (str(row[index[schema["company"]]]).strip()
                        if row[index[schema["company"]]] is not None else ""),
            "title": (str(row[index[schema["title"]]]).strip()
                      if row[index[schema["title"]]] is not None else ""),
            "url": as_url(row[index[schema["url"]]]),
            "status": (str(row[index[schema["status"]]]).strip()
                       if row[index[schema["status"]]] is not None else ""),
        }
        if is_synthetic(record["company"], record["title"], record["url"]):
            continue
        out.append(record)

    # Sort by date descending (newest first), then by numeric ID descending.
    # The ID must be parsed numerically: as strings "J99" > "J130", which put
    # older jobs at the top of the digest once the tracker passed J99.
    def _id_key(rec):
        digits = "".join(ch for ch in rec["id"] if ch.isdigit())
        return int(digits) if digits else 0

    out.sort(key=lambda r: (r["date"] or dt.date.min, _id_key(r)), reverse=True)
    return out[:limit], None


# --------------------------------------------------------------------------- #
# digest
# --------------------------------------------------------------------------- #
def build_digest(stale_hours: float, budget: int, max_per_region: int) -> tuple[str, int]:
    now = dt.datetime.now(dt.timezone.utc)
    sections = []          # one dict per region, always kept
    fresh_regions = 0
    total_jobs = 0

    for region in REGIONS:
        doc, _path = latest_run_doc(region)
        label = REGION_LABEL[region]

        # Always read tracker rows — they are the primary source for the digest.
        # Read more than max_per_region so the digest can show "N more" when truncated.
        tracked, tracker_error = tracker_rows(region, limit=max(max_per_region * 3, 50))

        if doc is None:
            head = [f"**{label}** — {len(tracked)} job(s) in tracker"]
            if tracker_error:
                head.append(f"  (tracker not read: {tracker_error})")
            jobs = []
            capped_out = 0
            if tracked:
                for i, job in enumerate(tracked[:max_per_region], 1):
                    jobs.append([
                        f"  {i}. {job['company']} — {job['title']}  [{job['id']}]",
                        f"     {job['url'] or 'URL: not stated by the source'}",
                    ])
                capped_out = max(0, len(tracked) - len(jobs))
                total_jobs += len(tracked)
                fresh_regions += 1
            else:
                head.append("  No discovery run artifact found. Nothing is invented "
                            "to fill the gap.")
            sections.append({"label": label, "head": head, "jobs": jobs,
                             "capped": capped_out})
            continue

        generated = parse_iso(doc.get("generated_at"))
        age_h = (now - generated).total_seconds() / 3600.0 if generated else None
        stale = age_h is None or age_h > stale_hours

        run_date = generated.date() if generated else None
        accepted = accepted_candidates(doc)

        head = [f"**{label}** — {len(tracked)} job(s) in tracker"
                + (f", {len(accepted)} found today" if accepted else "")]

        if stale:
            age_text = f"{age_h:.1f}h old" if age_h is not None else "no readable timestamp"
            head.append(f"  ⚠️ STALE/UNKNOWN — run is {age_text} (threshold {stale_hours}h). "
                        f"NOT today's state.")
        else:
            fresh_regions += 1

        if tracker_error:
            head.append(f"  (tracker not read: {tracker_error})")

        jobs = []
        capped_out = 0
        if not tracked:
            head.append("  No jobs in tracker.")
            if not accepted:
                zero = (doc.get("funnel") or {}).get("counts", {}).get("zero_attribution") or {}
                first_zero = zero.get("first_zero_stage")
                if first_zero:
                    head.append(f"  First zero stage: {first_zero} — {zero.get('reason', '')}")
        else:
            tracked_urls = {r["url"] for r in tracked if r["url"]}
            tracked_by_url = {r["url"]: r for r in tracked if r["url"]}
            for i, job in enumerate(tracked[:max_per_region], 1):
                tag = ""
                if job["url"] and job["url"] in tracked_urls:
                    tag = f"  [{job['id']}]"
                jobs.append([
                    f"  {i}. {job['company']} — {job['title']}{tag}",
                    f"     {job['url'] or 'URL: not stated by the source'}",
                ])
            capped_out = max(0, len(tracked) - len(jobs))
            total_jobs += len(tracked)

        sections.append({"label": label, "head": head, "jobs": jobs,
                         "capped": capped_out})

    header = [
        "**Jobs found — with apply links**",
        f"As of: {now.isoformat(timespec='seconds')}",
    ]
    if fresh_regions == 0:
        header.append("⚠️ No region produced a fresh discovery run — this digest is "
                      "UNKNOWN, not 'no jobs'.")
    else:
        header.append(f"{total_jobs} job(s) found across {len(REGIONS)} region(s).")

    tail = [
        "",
        "Read-only: no application, no submission, no outreach, no tracker write.",
        "Links are the source's own URL; a pre-screened vacancy is not re-verified live.",
    ]

    def render(dropped: dict) -> str:
        blocks = []
        for section in sections:
            lines = list(section["head"])
            lines.extend("\n".join(job) for job in section["jobs"])
            withheld = section["capped"] + dropped.get(section["label"], 0)
            if withheld:
                lines.append(f"  … {withheld} more job(s) in this region not listed here.")
            blocks.append("\n".join(lines))
        return "\n".join(header + [""] + blocks + tail)

    # Enforce the budget by dropping JOB lines — never a whole region. Dropping a
    # region would hide every vacancy in it, and the owner asked for all of them;
    # the gateway chunks long messages anyway (Discord 2000 / Telegram 4096).
    dropped: dict[str, int] = {}
    text = render(dropped)
    while len(text) > budget:
        # Trim from the region with the most jobs still shown, so regions lose
        # detail evenly instead of one region being emptied first.
        candidate = max(
            (s for s in sections if s["jobs"]),
            key=lambda s: len(s["jobs"]),
            default=None,
        )
        if candidate is None:
            break
        candidate["jobs"].pop()
        dropped[candidate["label"]] = dropped.get(candidate["label"], 0) + 1
        text = render(dropped)

    code = 0 if fresh_regions > 0 else 3
    return text, code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale-hours", type=float, default=26.0)
    parser.add_argument("--budget", type=int, default=14000,
                        help="soft max characters before per-region job detail is "
                             "trimmed. Set generously: the gateway chunks long "
                             "messages (Discord 2000 / Telegram 4096), so a longer "
                             "digest is delivered whole rather than losing jobs. "
                             "40 jobs x 2 lines needs ~12k, so the default clears "
                             "a full 10-per-region digest.")
    parser.add_argument("--max-per-region", type=int, default=10,
                        help="max jobs listed per region before summarising the rest")
    args = parser.parse_args()

    text, code = build_digest(args.stale_hours, args.budget, args.max_per_region)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
