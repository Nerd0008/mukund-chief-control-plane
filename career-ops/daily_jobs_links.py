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


def tracker_rows(region, want_date=None):
    """Rows from a region's canonical workbook. Read-only; never writes."""
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
        if want_date is not None and record["date"] != want_date:
            continue
        out.append(record)
    return out, None


# --------------------------------------------------------------------------- #
# digest
# --------------------------------------------------------------------------- #
def build_digest(stale_hours: float, budget: int, max_per_region: int) -> tuple[str, int]:
    now = dt.datetime.now(dt.timezone.utc)
    blocks = []
    fresh_regions = 0
    total_jobs = 0
    overall_notes = []

    for region in REGIONS:
        doc, path = latest_run_doc(region)
        label = REGION_LABEL[region]

        if doc is None:
            blocks.append(f"**{label}** — UNKNOWN\nNo discovery run artifact found. "
                          f"Nothing is invented to fill the gap.")
            overall_notes.append(f"{region}: no run artifact")
            continue

        generated = parse_iso(doc.get("generated_at"))
        age_h = (now - generated).total_seconds() / 3600.0 if generated else None
        stale = age_h is None or age_h > stale_hours

        run_date = generated.date() if generated else None
        accepted = accepted_candidates(doc)
        tracked, tracker_error = tracker_rows(region, want_date=run_date)

        lines = [f"**{label}** — {len(accepted)} job(s) found"
                 + (f", {len(tracked)} added to tracker" if tracked else "")]

        if stale:
            age_text = f"{age_h:.1f}h old" if age_h is not None else "no readable timestamp"
            lines.append(f"  ⚠️ STALE/UNKNOWN — run is {age_text} (threshold {stale_hours}h). "
                         f"NOT today's state.")
        else:
            fresh_regions += 1

        if tracker_error:
            lines.append(f"  (tracker not read: {tracker_error})")

        if not accepted:
            lines.append("  No accepted job in this run's own funnel output.")
            zero = (doc.get("funnel") or {}).get("zero_attribution") or {}
            first_zero = zero.get("first_zero_stage")
            if first_zero:
                lines.append(f"  First zero stage: {first_zero} — {zero.get('reason', '')}")
        else:
            tracked_urls = {r["url"] for r in tracked if r["url"]}
            tracked_by_url = {r["url"]: r for r in tracked if r["url"]}
            shown = accepted[:max_per_region]
            for i, job in enumerate(shown, 1):
                in_tracker = job["url"] and job["url"] in tracked_urls
                tag = ""
                if in_tracker:
                    tag = f"  [tracker {tracked_by_url[job['url']]['id']}]"
                elif tracked_by_url:
                    tag = "  [not yet in tracker]"
                lines.append(f"  {i}. {job['company']} — {job['title']}{tag}")
                lines.append(f"     {job['url'] or 'URL: not stated by the source'}")
            if len(accepted) > len(shown):
                lines.append(f"  … {len(accepted) - len(shown)} more in this run "
                             f"(see the run artifact).")
            total_jobs += len(accepted)

        blocks.append("\n".join(lines))

    header = [
        "**Jobs found — with apply links**",
        f"As of: {now.isoformat(timespec='seconds')}",
    ]
    if fresh_regions == 0:
        header.append("⚠️ No region produced a fresh discovery run — this digest is "
                      "UNKNOWN, not 'no jobs'.")

    tail = [
        "",
        "Read-only: no application, no submission, no outreach, no tracker write.",
        "Links are the source's own URL; a pre-screened vacancy is not re-verified live.",
    ]

    text = "\n".join(header + [""] + blocks + tail)

    if len(text) > budget:
        # Drop per-region blocks from the bottom up, then trim job lines inside the
        # last surviving block, always saying what was omitted. Never silently
        # exceed the budget: a truncated message loses jobs without telling anyone.
        omitted = 0
        while len(text) > budget and len(blocks) > 1:
            blocks.pop()
            omitted += 1
            text = "\n".join(
                header
                + [f"… {omitted} region block(s) omitted to fit the message limit."]
                + [""] + blocks + tail
            )
        while len(text) > budget and blocks:
            lines = blocks[-1].split("\n")
            # Drop the last line (a URL) together with its preceding job line.
            if len(lines) <= 1:
                break
            lines.pop()
            blocks[-1] = "\n".join(lines)
            text = "\n".join(
                header
                + [f"… {omitted} region block(s) omitted to fit the message limit."
                   if omitted else
                   "… some job lines omitted to fit the message limit."]
                + [""] + blocks + tail
            )

    code = 0 if fresh_regions > 0 else 3
    return text, code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale-hours", type=float, default=26.0)
    parser.add_argument("--budget", type=int, default=1850,
                        help="max characters to print (Discord message safety)")
    parser.add_argument("--max-per-region", type=int, default=25,
                        help="max jobs listed per region before summarising the rest")
    args = parser.parse_args()

    text, code = build_digest(args.stale_hours, args.budget, args.max_per_region)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
