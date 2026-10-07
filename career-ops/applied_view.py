#!/usr/bin/env python3
"""Report the applied jobs from the canonical UK tracker.

Owner instruction (2026-09-25): a tracker, with every JD supplied logged as an
applied job.

Owner instruction (2026-10-07): the UK tracker is now a single "Jobs" sheet with
exactly five fields (Date Found, Company, Role Title, Apply Link, Application
Deadline) plus Status. That schema has no room for a derived "Applied" sheet, so
this tool no longer writes one INTO the canonical workbook — adding a sheet back
would violate the schema the owner defined.

What it does now:
  * prints the applied rows (read-only, always safe);
  * optionally writes them to a SEPARATE workbook outside the canonical file
    (`--out`), for a shareable view;
  * with `--apply`, writes that separate workbook (never the tracker).

The Status column plus the sheet's own auto-filter is the in-workbook view.

Usage:
  python career-ops/applied_view.py                      # report only
  python career-ops/applied_view.py --out <path.xlsx>    # also write the view
  python career-ops/applied_view.py --out <path.xlsx> --apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracker_writer import load_profiles, region_config  # noqa: E402

BACKUP_DIR = REPO / "runtime" / "career-ops" / "backups"
DEFAULT_OUT = REPO / "runtime" / "career-ops" / "uk-applied-view.xlsx"

#: Canonical field -> heading in the derived view.
COLUMNS = [
    ("date_found", "Date Found"),
    ("company", "Company"),
    ("title", "Role Title"),
    ("url", "Apply Link"),
    ("deadline", "Application Deadline"),
    ("_status", "Status"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def applied_rows(ws, cfg: dict) -> list[list]:
    """Rows whose Status is exactly 'Applied' (the profile's own status value)."""
    from openpyxl.utils import column_index_from_string
    wanted = (cfg.get("status_values") or {}).get("applied", "Applied")
    scol = column_index_from_string(cfg["status_columns"]["application_status"])
    fmap = cfg["field_map"]
    out = []
    for r in range(cfg["first_data_row"], ws.max_row + 1):
        if str(ws.cell(row=r, column=scol).value or "").strip() != wanted:
            continue
        row = [ws.cell(row=r, column=column_index_from_string(fmap[key])).value
               if key in fmap else ws.cell(row=r, column=scol).value
               for key, _ in COLUMNS]
        row[-1] = ws.cell(row=r, column=scol).value
        out.append(row)
    return out


def build_view(rows: list[list]) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Applied"
    ws["A1"] = "Applied jobs"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (f"Derived from the canonical tracker's Jobs sheet — generated "
                f"{dt.date.today().isoformat()}. Read-only view; edit Status on the "
                f"tracker itself.")
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

    widths = {"A": 12, "B": 26, "C": 40, "D": 52, "E": 16, "F": 18}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(COLUMNS))}{max(4, 4 + len(rows))}"
    return wb


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="uk")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="separate workbook for the view (never the canonical tracker)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    profiles = load_profiles()
    cfg = dict(region_config(profiles, args.region))
    cfg["_region"] = args.region
    tracker = Path(cfg["tracker"])
    if not tracker.exists():
        print(f"tracker not found: {tracker}")
        return 1

    before_hash = sha256(tracker)
    wb = openpyxl.load_workbook(tracker)
    ws = wb[cfg["sheet"]]
    rows = applied_rows(ws, cfg)
    wb.close()

    if args.json:
        print(json.dumps({
            "tracker": str(tracker),
            "tracker_sha256": before_hash,
            "applied_count": len(rows),
            "rows": [dict(zip([h for _, h in COLUMNS], r)) for r in rows],
        }, indent=2, default=str))
        return 0

    print(f"tracker            : {tracker}")
    print(f"sha256             : {before_hash}")
    print(f"applied rows found : {len(rows)}")
    for row in rows:
        print(f"   {row[0]}  {row[1]}  |  {row[2]}")

    if sha256(tracker) != before_hash:
        print("\n!! tracker changed while reading — ABORTING")
        return 1

    out = Path(args.out)
    if not args.apply:
        print(f"\nDRY RUN — nothing written. Would write the view to {out}.")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    build_view(rows).save(out)
    print(f"\nwrote view         : {out}")
    print(f"tracker untouched  : {sha256(tracker) == before_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
