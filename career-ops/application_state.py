#!/usr/bin/env python3
"""Owner-state writer for a canonical job tracker row.

Why this exists
---------------
`career-ops/tracker_writer.py` deliberately refuses to set application state:
"a manifest cannot set application state ... fabricating an application is the
single worst failure mode here". That is correct for the automated scan path.

This script is the *owner-instructed* counterpart. It is only ever run on an
explicit instruction from Mukund (for example: "for every CV generated and JD
given consider the job applied"), and it records the fact in the owner columns
that the automated scan is forbidden to touch:

    J  Application Status
    K  Priority
    S  Date Selected
    T  Date Applied
    U  Tailored CV Path
    V  Personal Notes

Discipline enforced here
------------------------
* Owner columns only. It refuses to write any automation-owned column, with one
  explicitly-flagged exception: `--fit-score` writes column H (Fit Score), which
  is an assessment value rather than owner state. It is written only when the
  caller passes it, and it is reported separately in the output.
* Refuses to invent state: --status must be one of the workbook's own
  validation list, and a date must be supplied for Applied-like statuses.
* Hash-verified backup before the write, re-open verification after it.
* Every run prints one JSON object (same contract as `career_ops_cli.py`).
* Idempotent: re-running with identical values is a no-op and reports so.

Usage
-----
    python career-ops/application_state.py --region uk --id J35 \
        --status Applied --date-applied 2026-09-25 \
        --cv-path career-ops/applications/<pkg>/cv_....pdf \
        --notes "..." --apply

Without --apply nothing is written and the planned change is printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string

REPO = Path(__file__).resolve().parent.parent
PROFILES = REPO / "career-ops" / "regional_profiles.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tracker_writer import normalize_url  # noqa: E402

# Legacy regional write columns (dubai/japan/singapore keep the wide schema).
# The UK schema is profile-driven via `write_columns`; see `write_columns()`.
OWNER_WRITE_COLUMNS = {
    "application_status": "J",
    "priority": "K",
    "date_selected": "S",
    "date_applied": "T",
    "cv_path": "U",
    "notes": "V",
}

VALID_PRIORITY = {"High", "Medium", "Low"}

#: Fields the new UK schema has no column for. Requesting one is an error, not a
#: silent drop: application provenance must never be discarded quietly.
UK_UNSUPPORTED_FIELDS = ("priority", "date_selected", "date_applied", "cv_path", "notes")


def write_columns(cfg: dict) -> dict:
    """Field key -> column letter for the columns this region may write."""
    explicit = cfg.get("write_columns")
    if explicit:
        return dict(explicit)
    if cfg.get("_region") == "uk":
        return {"application_status": cfg["status_columns"]["application_status"]}
    return dict(OWNER_WRITE_COLUMNS)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_region(region: str) -> dict:
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    regions = profiles["regions"]
    if region not in regions:
        raise SystemExit(f"unknown region {region!r}; known: {sorted(regions)}")
    cfg = dict(regions[region])
    cfg["_profiles"] = profiles
    cfg["_region"] = region
    return cfg


def allowed_statuses(ws, cfg: dict) -> list[str]:
    """Read the workbook's own Application Status validation list.

    openpyxl stores data validations on the worksheet, not the cell, so scan
    `ws.data_validations.dataValidation` (which may be absent entirely).
    """
    col = cfg["status_columns"]["application_status"]
    dvs = getattr(ws.data_validations, "dataValidation", None) or []
    for dv in dvs:
        if not dv.formula1:
            continue
        if str(dv.sqref) == col or col in str(dv.sqref):
            return [s.strip() for s in dv.formula1.strip('"').split(",") if s.strip()]
    return []


def find_row(ws, cfg: dict, job_id: str, *, by_url: str | None = None) -> int | None:
    """Locate a job row.

    Wide regional schemas identify a row by its job id in column A. The new UK
    schema has no id column, so rows are addressed by application URL instead
    (`--url`), which is the schema's own dedupe key.

    The regional profile's `last_data_row` is a structural baseline that goes
    stale as soon as the workbook grows, so search to the sheet's real extent.
    """
    id_col = cfg.get("id")
    end = max(int(cfg.get("last_data_row") or 0), ws.max_row)
    if by_url:
        ucol = column_index_from_string(cfg["dedupe"]["url_column"])
        target = normalize_url(by_url)
        for row in range(cfg["first_data_row"], end + 1):
            if normalize_url(ws.cell(row=row, column=ucol).value) == target:
                return row
        return None
    if not id_col:
        return None
    col = column_index_from_string(id_col["column"])
    for row in range(cfg["first_data_row"], end + 1):
        if str(ws.cell(row=row, column=col).value or "").strip() == job_id:
            return row
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--id", help="Job ID, e.g. J35 (wide regional schemas)")
    ap.add_argument("--url", help="Application URL (schemas with no id column, e.g. UK)")
    ap.add_argument("--status", required=True, help="Application Status value")
    ap.add_argument("--priority")
    ap.add_argument("--date-selected")
    ap.add_argument("--date-applied")
    ap.add_argument("--cv-path")
    ap.add_argument("--notes")
    ap.add_argument("--fit-score", type=float, help="Chief assessment; writes column H")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup-dir")
    args = ap.parse_args(argv)

    cfg = load_region(args.region)
    tracker = Path(cfg["tracker"])
    if not tracker.exists():
        raise SystemExit(f"tracker not found: {tracker}")

    backup_dir = Path(args.backup_dir) if args.backup_dir else REPO / "runtime" / "career-ops" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    sha_before = sha256_file(tracker)
    wb = openpyxl.load_workbook(tracker)
    if cfg["sheet"] not in wb.sheetnames:
        raise SystemExit(f"sheet {cfg['sheet']!r} missing from {tracker}")
    ws = wb[cfg["sheet"]]

    statuses = allowed_statuses(ws, cfg)
    if statuses and args.status not in statuses:
        wb.close()
        raise SystemExit(f"--status {args.status!r} is not in the workbook's list: {statuses}")
    if args.priority and args.priority not in VALID_PRIORITY:
        wb.close()
        raise SystemExit(f"--priority must be one of {sorted(VALID_PRIORITY)}")

    wcols = write_columns(cfg)
    if cfg.get("_region") == "uk":
        unsupported = [f for f in UK_UNSUPPORTED_FIELDS
                       if f not in wcols and getattr(args, f) is not None]
        if unsupported:
            wb.close()
            flags = ", ".join("--" + f.replace("_", "-") for f in unsupported)
            raise SystemExit(
                f"the UK schema has no column for {flags}. "
                "Record those details in the application package README instead of the tracker; "
                "the schema is owner-defined (2026-10-07).")
    elif args.status in {"Applied", "Interview", "Offer", "Hired"} and not args.date_applied:
        wb.close()
        raise SystemExit(f"--status {args.status} requires --date-applied (no invented application dates)")

    if not args.id and not args.url:
        wb.close()
        raise SystemExit("one of --id or --url is required to locate the row")
    row = find_row(ws, cfg, args.id, by_url=args.url)
    if row is None:
        wb.close()
        raise SystemExit(f"job row not found in {tracker} (id={args.id!r} url={args.url!r})")

    def cell(col_key: str):
        return ws.cell(row=row, column=column_index_from_string(wcols[col_key]))

    planned = {}
    changes = {}

    def stage(col_key, value):
        if value is None or col_key not in wcols:
            return
        if col_key == "date_applied" or col_key == "date_selected":
            value = dt.datetime.fromisoformat(value).date()
        c = cell(col_key)
        current = c.value
        # compare like-for-like: openpyxl returns datetime for date-formatted cells
        current_cmp = current.date() if isinstance(current, dt.datetime) else current
        planned[wcols[col_key]] = {
            "before": current.isoformat() if isinstance(current, (dt.date, dt.datetime)) else current,
            "after": value.isoformat() if isinstance(value, (dt.date, dt.datetime)) else value,
        }
        if current_cmp != value:
            changes[col_key] = value
        c.value = value

    stage("application_status", args.status)
    stage("priority", args.priority)
    stage("date_selected", args.date_selected)
    stage("date_applied", args.date_applied)
    stage("cv_path", args.cv_path)
    stage("notes", args.notes)

    ucol = column_index_from_string(cfg["dedupe"]["url_column"])
    row_snapshot = {
        "job_id": args.id,
        "company": ws.cell(row=row, column=column_index_from_string(cfg["dedupe"]["company_column"])).value,
        "title": ws.cell(row=row, column=column_index_from_string(cfg["dedupe"]["title_column"])).value,
        "url": ws.cell(row=row, column=ucol).value,
        "row": row,
    }

    fit_score_note = None
    if args.fit_score is not None:
        fcol = cfg.get("fit_score_column")
        if fcol:
            h = ws.cell(row=row, column=column_index_from_string(fcol))
            if h.value != args.fit_score:
                fit_score_note = {"column": fcol, "before": h.value, "after": args.fit_score}
                h.value = args.fit_score
                changes["fit_score"] = args.fit_score

    if not changes:
        wb.close()
        print(json.dumps({"region": args.region, "applied": False, "changed": False,
                          "reason": "owner columns already hold these values",
                          "row": row_snapshot, "planned": planned}, indent=2))
        return 0

    if not args.apply:
        wb.close()
        print(json.dumps({"region": args.region, "applied": False, "changed": False,
                          "mode": "dry-run", "row": row_snapshot,
                          "planned": planned, "changes": sorted(changes)}, indent=2))
        return 0

    backup = backup_dir / f"{tracker.stem}.owner-state-{dt.datetime.now():%Y%m%d-%H%M%S}.xlsx"
    shutil.copy2(tracker, backup)
    if sha256_file(backup) != sha_before:
        wb.close()
        raise SystemExit("backup hash mismatch — refusing to write")
    if sha256_file(tracker) != sha_before:
        wb.close()
        raise SystemExit("tracker changed since read — refusing to clobber")

    wb.save(tracker)
    wb.close()

    # verify by re-opening
    wb2 = openpyxl.load_workbook(tracker)
    ws2 = wb2[cfg["sheet"]]
    problems = []
    id_col2 = cfg.get("id")
    if id_col2 and args.id and str(ws2.cell(row=row, column=column_index_from_string(id_col2["column"])).value) != args.id:
        problems.append("job id moved on re-open")
    scol = column_index_from_string(wcols["application_status"])
    if ws2.cell(row=row, column=scol).value != args.status:
        problems.append("application status not persisted")
    if args.url and cfg.get("id") is None:
        if normalize_url(ws2.cell(row=row, column=ucol).value) != normalize_url(args.url):
            problems.append("url moved on re-open")
    if args.date_applied and "date_applied" in wcols:
        got = ws2.cell(row=row, column=column_index_from_string(wcols["date_applied"])).value
        if not isinstance(got, (dt.date, dt.datetime)) or got.strftime("%Y-%m-%d") != args.date_applied:
            problems.append(f"date applied not persisted (got {got!r})")
    sheets_ok = all(s in ws2.parent.sheetnames for s in cfg["expected_sheets"])
    if not sheets_ok:
        problems.append("sheet set changed")
    wb2.close()

    result = {
        "region": args.region,
        "applied": True,
        "changed": True,
        "row": row_snapshot,
        "planned": planned,
        "backup": str(backup),
        "tracker_sha256_before": sha_before,
        "tracker_sha256_after": sha256_file(tracker),
        "verification": {"ok": not problems, "problems": problems, "sheets_ok": sheets_ok},
        "provenance": {"writer": "career-ops/application_state.py",
                       "authority": "owner instruction"},
    }
    print(json.dumps(result, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
