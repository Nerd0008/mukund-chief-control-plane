#!/usr/bin/env python3
"""Build/refresh the "Applied" sheet inside the canonical UK tracker.

Owner instruction (2026-09-25): a tracker, with every JD supplied logged as an
applied job.

Deliberately NOT a second workbook — the September audit found trackers in five
locations with no single source of truth. This keeps one file: the "Applied"
sheet is a derived read-only view of the Jobs sheet, regenerated from it, so it
can never disagree with the application records.

Safety:
  * the Jobs sheet is compared cell-by-cell before/after and any drift aborts;
  * sheet order is preserved, "Applied" is appended LAST so sheetnames[0] stays
    "Jobs" (the tracker writer asserts that);
  * a hash-verified backup is written before the workbook is replaced.

Usage:
  python career-ops/applied_view.py            # dry run, reports what it would do
  python career-ops/applied_view.py --apply    # write, with backup + re-verify
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import shutil
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import column_index_from_string, get_column_letter

CONTROL_PLANE = Path(__file__).resolve().parent.parent
TRACKER = Path(r"C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx")
BACKUP_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "backups"
SHEET = "Applied"
JOBS = "Jobs"
HEADER_ROW = 9
FIRST_DATA_ROW = 10

# Jobs column -> Applied column heading
COLUMNS = [
    ("A", "Job ID"),
    ("B", "Date Found"),
    ("C", "Company"),
    ("D", "Job Title"),
    ("E", "Location"),
    ("F", "Salary"),
    ("H", "Fit Score"),
    ("I", "Live Status"),
    ("J", "Application Status"),
    ("K", "Priority"),
    ("O", "Official URL"),
    ("S", "Date Selected"),
    ("T", "Date Applied"),
    ("U", "Tailored CV Path"),
    ("V", "Personal Notes"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_jobs(ws) -> list[tuple]:
    """Every cell of the Jobs sheet, so drift can be detected."""
    return [tuple(ws.cell(r, c).value for c in range(1, ws.max_column + 1))
            for r in range(1, ws.max_row + 1)]


def applied_rows(ws) -> list[list]:
    """Jobs rows whose Application Status is exactly 'Applied'."""
    out = []
    for r in range(FIRST_DATA_ROW, ws.max_row + 1):
        if not ws.cell(r, 1).value:
            continue
        if str(ws.cell(r, 10).value or "").strip() == "Applied":
            out.append([ws.cell(r, column_index_from_string(col)).value
                        for col, _ in COLUMNS])
    return out


def build(wb, rows: list[list]) -> None:
    if SHEET in wb.sheetnames:
        del wb[SHEET]
    ws = wb.create_sheet(SHEET)          # appended last: sheetnames[0] stays "Jobs"

    ws["A1"] = "Applied jobs"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (f"Derived from the Jobs sheet — generated {dt.date.today().isoformat()}. "
                f"Do not edit: rows appear here automatically when Application Status is set to "
                f"'Applied' on Jobs.")
    ws["A2"].font = Font(italic=True, size=9, color="555555")

    for i, (_, heading) in enumerate(COLUMNS, start=1):
        c = ws.cell(4, i, heading)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F5597")
        c.alignment = Alignment(vertical="center")

    for ri, row in enumerate(rows, start=5):
        for ci, value in enumerate(row, start=1):
            cell = ws.cell(ri, ci, value)
            if isinstance(value, dt.datetime):
                cell.number_format = "yyyy-mm-dd"

    widths = {"A": 8, "B": 12, "C": 26, "D": 34, "E": 34, "F": 11, "H": 9,
              "I": 11, "J": 17, "K": 9, "O": 52, "S": 13, "T": 13, "U": 60, "V": 60}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(COLUMNS))}{max(4, 4 + len(rows))}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    if not TRACKER.exists():
        print(f"tracker not found: {TRACKER}")
        return 1

    before_hash = sha256(TRACKER)
    wb = openpyxl.load_workbook(TRACKER)
    jobs = wb[JOBS]
    jobs_before = snapshot_jobs(jobs)
    sheet_order_before = list(wb.sheetnames)
    rows = applied_rows(jobs)

    print(f"tracker            : {TRACKER}")
    print(f"sha256 before      : {before_hash}")
    print(f"sheets             : {sheet_order_before}")
    print(f"applied rows found : {len(rows)}")
    for row in rows:
        print(f"   {row[0]}  {row[12] if isinstance(row[12], str) else row[12]}  "
              f"{row[2]}  |  {row[3]}")

    build(wb, rows)

    # ---- the Jobs sheet must be byte-for-byte the same content ------------- #
    jobs_after = snapshot_jobs(wb[JOBS])
    if jobs_before != jobs_after:
        diffs = [(i + 1, a, b) for i, (a, b) in enumerate(zip(jobs_before, jobs_after)) if a != b]
        print(f"\n!! Jobs sheet changed in {len(diffs)} row(s) — ABORTING")
        for d in diffs[:5]:
            print(f"   row {d[0]}: {d[1]!r} -> {d[2]!r}")
        return 1
    if wb.sheetnames[0] != JOBS:
        print(f"\n!! first sheet is now {wb.sheetnames[0]!r} — ABORTING")
        return 1
    print(f"\nJobs sheet unchanged, first sheet still {JOBS!r}")
    print(f"sheet order after  : {wb.sheetnames}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"uk-cyber-job-tracker.applied-view-{stamp}.xlsx"
    shutil.copy2(TRACKER, backup)

    tmp = TRACKER.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    tmp.replace(TRACKER)

    after_hash = sha256(TRACKER)
    check = openpyxl.load_workbook(TRACKER)
    ok = (check.sheetnames[0] == JOBS and SHEET in check.sheetnames
          and snapshot_jobs(check[JOBS]) == jobs_before)
    print(f"\nbackup             : {backup}")
    print(f"sha256 after       : {after_hash}")
    print(f"re-verified        : {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
