#!/usr/bin/env python3
"""Monthly Tracker Rollover / archive worker (roster B09).

What it does
------------
At the end of a tracking month, one month of records is rotated out of each
canonical regional workbook into a per-region **archive workbook**:

    uk        -> uk-cyber-job-tracker.<YYYY-MM>.xlsx
    dubai     -> Dubai_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx
    japan     -> Japan_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx
    singapore -> Singapore_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx

The archive file name matches the region's archive glob in
``regional_profiles.json`` on purpose: ``tracker_writer.build_cross_month_index``
already unions every non-canonical workbook matching that glob, so **every
rotated row feeds the cross-month dedupe index** and a posting seen in a previous
month can never be appended to a tracker again.

Design rules (the integration contract)
---------------------------------------
* **The canonical workbook stays authoritative.** Rollover keeps it as the live,
  owner-facing record: the rotated rows are moved *into the archive*, never
  dropped. The archive is a full, faithful copy of those rows — every column,
  including the owner columns — under the canonical schema (sheets, table,
  formulas, defaults, number formats and data validations are inherited from a
  copy of the canonical file itself, not re-invented).
* **Dry run by default.** Nothing is written without ``--apply``.
* **Archive before mutation.** On ``--apply`` the archive is written and verified
  *first*; only then is the canonical touched. A canonical write always takes a
  hash-verified backup first, is written to a temp file, re-opened and verified,
  and is only then atomically replaced (the same safety path as
  ``tracker_writer.write_records``).
* **Owners' state is never silently deleted.** Rotation refuses the whole run if
  any row to be rotated carries owner-column content other than the profile's own
  automation defaults (e.g. an ``Applied`` status, a tailored CV path or personal
  notes). Those rows are reported by row/column only — the value itself is never
  read into any output — and the run stops for owner authority
  (``--allow-owner-state-removal`` is required to override).
* **Excel is authoritative.** This worker never invents a job, never submits an
  application, never messages anyone and never changes an application status.
  Its own metadata is orchestration-only run-health (``dept_run_health.py``).
* **Deterministic.** Re-running the same month produces byte-identical archive
  content and reports ``unchanged`` instead of rewriting.

Subcommands
-----------
  plan      --region R [--month YYYY-MM]        read-only: what would rotate
  rollover  --region R [--month YYYY-MM] [--apply] [--archive-only]
            [--force] [--allow-owner-state-removal]
                                                do the rollover (dry-run by default)
  archives  --region R                          the region's archive workbooks

Unknown/limits (stated, not hidden)
-----------------------------------
* A row whose ``date_found`` is not an ISO date or a real date cell (for example
  the free text ``"Posted 30+ days ago"``) is **never rotated** — it is reported
  as ``undated`` and retained in the canonical workbook.
* Derived/overview sheets (for example the UK ``Summary`` sheet) are not
  rewritten. Its formulas use whole-column ranges (``Jobs!$A$10:$A$500``), so they
  recompute correctly over the remaining rows when the workbook is opened; this
  worker does not claim to rewrite any sheet other than the data sheet.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent
sys.path.insert(0, str(HERE))

import openpyxl  # noqa: E402
from openpyxl.utils import column_index_from_string  # noqa: E402

import dept_run_health as drh  # noqa: E402
import tracker_writer as tw  # noqa: E402

JOB = "monthly-rollover"
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_month(text: str) -> str:
    m = MONTH_RE.match(str(text or "").strip())
    if not m:
        raise ValueError(f"month must be YYYY-MM, got {text!r}")
    return f"{m.group(1)}-{m.group(2)}"


def month_of(value) -> str | None:
    """The calendar month of a date cell or ISO date string; None if not a date."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m")
    m = re.match(r"^\s*(\d{4})-(\d{2})-\d{2}", str(value))
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def previous_month(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    first = today.replace(day=1)
    prev = first - dt.timedelta(days=1)
    return prev.strftime("%Y-%m")


def archive_filename(region: str, month: str) -> str:
    """A name that the region's ``default_archive_globs`` already matches."""
    parse_month(month)
    if region == "uk":
        return f"uk-cyber-job-tracker.{month}.xlsx"
    return f"{region.capitalize()}_Cybersecurity_Job_Tracker.{month}.xlsx"


def archive_path(profile: dict, region: str, month: str, archive_dir: str | Path | None = None) -> Path:
    base = Path(archive_dir or profile.get("canonical_dir") or ".")
    return base / archive_filename(region, month)


def _cfg(profile: dict, region: str) -> dict:
    cfg = dict(tw.region_config(profile, region))
    cfg["region"] = region
    return cfg


def _row_values(ws, r: int, ncols: int) -> list:
    return [ws.cell(row=r, column=c).value for c in range(1, ncols + 1)]


def _row_styles(ws, r: int, ncols: int) -> list:
    return [copy.copy(ws.cell(row=r, column=c)._style) for c in range(1, ncols + 1)]


def _scan(tr, cfg: dict, month: str) -> dict:
    """Partition the canonical data rows into the target month and the rest."""
    dcol = column_index_from_string(cfg["field_map"]["date_found"])
    urlcol = column_index_from_string(cfg["dedupe"]["url_column"])
    idcol = (cfg.get("id") or cfg.get("mail_identity") or {}).get("column")
    first, last = cfg["first_data_row"], tr.last_data_row()
    months: dict[str, int] = {}
    rolled, retained = [], []
    for r in range(first, last + 1):
        m = month_of(tr.ws.cell(row=r, column=dcol).value)
        if m is None:
            retained.append(r)
            continue
        months[m] = months.get(m, 0) + 1
        (rolled if m == month else retained).append(r)
    return {
        "months_present": dict(sorted(months.items())),
        "rolled_rows": rolled,
        "retained_rows": retained,
        "rolled_ids": [str(tr.ws[f"{idcol}{r}"].value) if idcol else None for r in rolled],
        "rolled_url_keys": [tw.normalize_url(tr.ws.cell(row=r, column=urlcol).value) for r in rolled],
        "undated_rows": sum(1 for r in retained
                            if month_of(tr.ws.cell(row=r, column=dcol).value) is None),
        "total_data_rows": last - first + 1,
    }


def _allowed_owner_values(cfg: dict) -> dict:
    """Owner-column values that are automation defaults, not owner state."""
    allowed: dict[str, set] = {}
    for key, default in cfg.get("defaults", {}).items():
        col = cfg.get("status_columns", {}).get(key)
        if col and default not in (None, ""):
            allowed.setdefault(col, set()).add(str(default))
    return allowed


def _guarded_owner_columns(cfg: dict) -> tuple[list, list]:
    """Owner columns the rollover must protect, and the ones it cannot.

    A column that the tracker writer itself fills from the manifest's
    ``field_map`` (the regional ``notes`` column Z) is *automation-writable*, so
    its content cannot be attributed to the owner from the data alone. Those
    columns are excluded from the owner-state guard and reported explicitly
    (``owner_columns_automation_writable``) instead of being silently trusted or
    silently ignored. A column that only the owner ever writes (applied date,
    application status, selected flag, CV/cover-letter status) is always guarded.
    """
    automation = set((cfg.get("field_map") or {}).values())
    owner = list(cfg.get("owner_columns", []))
    return ([c for c in owner if c not in automation],
            [c for c in owner if c in automation])


def _owner_state_conflicts(tr, cfg: dict, rows: list[int]) -> tuple[list, dict]:
    """Rows whose owner columns hold real owner state (not an automation default).

    Only the row number and column letter are returned — the value is never read
    into the result, because owner columns can hold private notes.
    """
    allowed = _allowed_owner_values(cfg)
    guarded, _unguarded = _guarded_owner_columns(cfg)
    conflicts = []
    for r in rows:
        for col in guarded:
            v = tr.ws[f"{col}{r}"].value
            if v in (None, ""):
                continue
            if str(v) in allowed.get(col, set()):
                continue
            conflicts.append({"row": r, "column": col})
    return conflicts, {c: sorted(v) for c, v in allowed.items()}


def _archive_rows(path: Path, cfg: dict) -> list[tuple]:
    """Data rows of an archive workbook as tuples (read-only)."""
    wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        ws = wb[cfg["sheet"]]
        ncols = ws.max_column
        idx = column_index_from_string(cfg["dedupe"]["url_column"])
        out = []
        for row in ws.iter_rows(min_row=cfg["first_data_row"], max_col=ncols, values_only=True):
            row = tuple(row) + (None,) * (ncols - len(row))
            if row[idx - 1] not in (None, ""):
                out.append(row[:ncols])
        return out
    finally:
        wb.close()


def _set_table_ref(ws, cfg: dict, data_row_count: int) -> str:
    """Point the table at exactly the archived/retained rows (min one data row)."""
    table = ws.tables[cfg["table"]]
    start_ref = table.ref.split(":")[0]
    start_col = re.sub(r"[0-9]", "", start_ref)
    start_row = int(re.sub(r"[^0-9]", "", start_ref))
    first = cfg["first_data_row"]
    end_row = first + max(data_row_count, 1) - 1
    end_row = max(end_row, start_row + 1)
    end_col = re.sub(r"[0-9]", "", table.ref.split(":")[1])
    table.ref = f"{start_col}{start_row}:{end_col}{end_row}"
    if table.autoFilter is not None:
        table.autoFilter.ref = table.ref
    return table.ref


def _write_rows(ws, cfg: dict, rows: list[list], first: int, styles: list[list] | None = None) -> None:
    """Write raw row values at ``first`` and restore the profile's row-level rules."""
    ncols = ws.max_column
    for i, values in enumerate(rows):
        r = first + i
        for c in range(1, ncols + 1):
            cell = ws.cell(row=r, column=c)
            cell.value = values[c - 1] if c - 1 < len(values) else None
            if styles is not None:
                cell._style = styles[i][c - 1]
        # row-number-dependent formulas are re-templated, never carried as stale text
        for spec in cfg.get("formula_map", {}).values():
            ci = column_index_from_string(spec["column"])
            ws.cell(row=r, column=ci).value = spec["template"].format(row=r)
        for col, fmt in cfg.get("number_formats", {}).items():
            ws[f"{col}{r}"].number_format = fmt


def _clear_block(ws, first: int, last: int, ncols: int) -> None:
    for r in range(first, last + 1):
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).value = None


# --------------------------------------------------------------------------- #
# plan (read-only)
# --------------------------------------------------------------------------- #

def plan(profile: dict, region: str, month: str, *, tracker_override: str | None = None,
         archive_dir: str | None = None) -> dict:
    cfg = _cfg(profile, region)
    month = parse_month(month)
    tracker = Path(tracker_override or cfg["tracker"])
    if not tracker.exists():
        return {"region": region, "month": month, "tracker": str(tracker),
                "status": "error", "error": "tracker not found", "ok": False}
    tr = tw.Tracker(tracker, cfg)
    try:
        scan = _scan(tr, cfg, month)
        conflicts, allowed = _owner_state_conflicts(tr, cfg, scan["rolled_rows"])
    finally:
        tr.wb.close()
    arch = archive_path(profile, region, month, archive_dir)
    guarded, automation_writable = _guarded_owner_columns(cfg)
    return {
        "status": "planned",
        "ok": True,
        "region": region,
        "month": month,
        "tracker": str(tracker),
        "tracker_sha256": tw.sha256_file(tracker),
        "data_rows": scan["total_data_rows"],
        "month_rows": len(scan["rolled_rows"]),
        "retained_rows": len(scan["retained_rows"]),
        "undated_rows": scan["undated_rows"],
        "months_present": scan["months_present"],
        "month_row_ids": scan["rolled_ids"],
        "archive": str(arch),
        "archive_filename": arch.name,
        "archive_exists": arch.exists(),
        "owner_state_conflicts": conflicts,
        "owner_defaults_allowed": allowed,
        "owner_columns_guarded": guarded,
        "owner_columns_automation_writable": automation_writable,
        "canonical_authoritative": True,
        "dry_run": True,
    }


# --------------------------------------------------------------------------- #
# rollover
# --------------------------------------------------------------------------- #

def rollover(profile: dict, region: str, month: str, *, apply: bool = False,
             archive_only: bool = False, archive_dir: str | None = None,
             tracker_override: str | None = None, backup_dir: str | None = None,
             force: bool = False, allow_owner_state_removal: bool = False,
             state_dir: str | None = None, record: bool = True) -> dict:
    cfg = _cfg(profile, region)
    month = parse_month(month)
    tracker_path = Path(tracker_override or cfg["tracker"])
    adir = Path(archive_dir or profile.get("canonical_dir") or tracker_path.parent)

    def finish(res: dict) -> dict:
        res.setdefault("region", region)
        res.setdefault("month", month)
        res.setdefault("mode", "apply" if apply else "dry-run")
        if record:
            arch_obj = res.get("archive")
            arch_name = (arch_obj.get("filename") if isinstance(arch_obj, dict)
                         else res.get("archive_filename"))
            drh.record_run(
                JOB, region=region, status=res.get("status", "error"),
                counts=res.get("counts", {}), mode=res.get("mode"),
                extra={"month": month, "archive_filename": arch_name,
                       "archive_only": bool(archive_only),
                       "reason": res.get("reason")},
                state_dir=state_dir)
        return res

    if not tracker_path.exists():
        return finish({"status": "error", "error": "tracker not found",
                       "tracker": str(tracker_path), "applied": False, "ok": False})

    before_hash = tw.sha256_file(tracker_path)
    arch = adir / archive_filename(region, month)

    tr = tw.Tracker(tracker_path, cfg)
    try:
        scan = _scan(tr, cfg, month)
        ncols = tr.ws.max_column
        rolled_values = [_row_values(tr.ws, r, ncols) for r in scan["rolled_rows"]]
        kept_values = [_row_values(tr.ws, r, ncols) for r in scan["retained_rows"]]
        conflicts, allowed = _owner_state_conflicts(tr, cfg, scan["rolled_rows"])
    finally:
        tr.wb.close()

    res = {
        "status": "planned",
        "ok": True,
        "tracker": str(tracker_path),
        "archive": str(arch),
        "archive_filename": arch.name,
        "archive_dir": str(adir),
        "archive_exists": arch.exists(),
        "rolled_ids": scan["rolled_ids"],
        "counts": {
            "data_rows": scan["total_data_rows"],
            "month_rows": len(scan["rolled_rows"]),
            "retained_rows": len(scan["retained_rows"]),
            "undated_rows": scan["undated_rows"],
            "archived_rows": 0,
            "rotated_out_of_canonical": 0,
        },
        "months_present": scan["months_present"],
        "owner_state_conflicts": conflicts,
        "owner_defaults_allowed": allowed,
        "owner_columns_guarded": _guarded_owner_columns(cfg)[0],
        "owner_columns_automation_writable": _guarded_owner_columns(cfg)[1],
        "canonical_authoritative": True,
        "canonical_sha256_before": before_hash,
        "canonical_write": archive_only,
        "archive_only": bool(archive_only),
    }

    if not scan["rolled_rows"]:
        res.update({"status": "no_rows", "applied": False,
                    "reason": f"no canonical data row has date_found in {month}"})
        return finish(res)

    if conflicts and not allow_owner_state_removal:
        res.update({
            "status": "refused", "applied": False, "owner_action_required": True,
            "reason": (f"{len(conflicts)} row(s) due to rotate carry owner-column state that is not an "
                       "automation default; rotation would delete owner records. Re-run with "
                       "--allow-owner-state-removal only after owner approval."),
            "refused_rows": conflicts[:50],
        })
        return finish(res)

    if not apply:
        res.update({"status": "planned", "applied": False, "dry_run": True,
                    "reason": "dry run: pass --apply to write the archive"
                              + ("" if archive_only else " and rotate the rows out of the canonical workbook")})
        return finish(res)

    # ---- 1. write + verify the archive (before touching the canonical) ---- #
    adir.mkdir(parents=True, exist_ok=True)
    archive_backup = None
    if arch.exists():
        existing = _archive_rows(arch, cfg)
        wanted = [tuple(v) for v in rolled_values]
        if existing == wanted:
            res.update({"status": "unchanged", "applied": False,
                        "reason": "archive already holds exactly these rows; nothing rewritten",
                        "counts": {**res["counts"], "archived_rows": len(existing)}})
            return finish(res)
        if not force:
            res.update({"status": "refused", "applied": False,
                        "reason": (f"archive {arch.name} exists with different content; pass --force to "
                                   "replace it (a hash-verified backup is taken first)")})
            return finish(res)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_backup = arch.with_name(f"{arch.stem}.pre-{stamp}.xlsx")
        shutil.copy2(arch, archive_backup)
        existing_hash = tw.sha256_file(archive_backup)
        if existing_hash != tw.sha256_file(arch):
            res.update({"status": "error", "applied": False,
                        "error": "archive backup hash mismatch; nothing written"})
            return finish(res)

    tmp = arch.with_name(arch.stem + ".write-tmp.xlsx")
    shutil.copy2(tracker_path, tmp)  # inherit sheets, table, formulas, validations
    wb = openpyxl.load_workbook(tmp, data_only=False)
    ws = wb[cfg["sheet"]]
    ncols = ws.max_column
    _clear_block(ws, cfg["first_data_row"], ws.max_row, ncols)
    _write_rows(ws, cfg, rolled_values, cfg["first_data_row"])
    table_ref = _set_table_ref(ws, cfg, len(rolled_values))
    wb.save(tmp)
    wb.close()

    archive_verification = tw.verify_workbook(tmp, cfg, expect_data_rows=len(rolled_values))
    if not archive_verification["ok"]:
        tmp.unlink(missing_ok=True)
        res.update({"status": "error", "applied": False,
                    "error": "archive verification failed; canonical workbook untouched",
                    "archive_verification": archive_verification})
        return finish(res)

    tmp.replace(arch)
    archive_after = tw.verify_workbook(arch, cfg, expect_data_rows=len(rolled_values))
    res["counts"]["archived_rows"] = len(rolled_values)
    res["archive"] = {
        "path": str(arch),
        "filename": arch.name,
        "sha256": tw.sha256_file(arch),
        "data_rows": archive_after["data_rows"],
        "table_ref": archive_after["table_ref"],
        "format_version_ok": archive_after["ok"],
        "headers_unchanged": True,
        "validations": archive_after["validations"],
        "fit_tier_formula_cells": archive_after["fit_tier_formula_cells"],
        "verification": archive_after,
        "previous_archive_backup": str(archive_backup) if archive_backup else None,
    }
    res["archive_table_ref"] = table_ref

    # ---- 2. rotate the rows out of the canonical workbook ---------------- #
    if not archive_only and kept_values is not None:
        if tw.sha256_file(tracker_path) != before_hash:
            res.update({"status": "error", "applied": True,
                        "error": "canonical workbook changed during rollover; archive written, canonical "
                                 "left untouched — retry from the latest file"})
            return finish(res)

        bdir = Path(backup_dir or profile.get("backup_dir") or tracker_path.parent)
        bdir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        canonical_backup = bdir / f"{tracker_path.stem}.pre-rollover-{stamp}.xlsx"
        shutil.copy2(tracker_path, canonical_backup)
        if tw.sha256_file(canonical_backup) != before_hash:
            res.update({"status": "error", "applied": True,
                        "error": "canonical backup hash mismatch; canonical left untouched"})
            return finish(res)

        first = cfg["first_data_row"]
        owner_cols = cfg.get("owner_columns", [])
        pre_owned = {
            first + i: {c: values[column_index_from_string(c) - 1] for c in owner_cols}
            for i, values in enumerate(kept_values)
        }
        tmpc = tracker_path.with_name(tracker_path.stem + ".rollover-tmp.xlsx")
        wb = openpyxl.load_workbook(tracker_path, data_only=False)
        ws = wb[cfg["sheet"]]
        ncols = ws.max_column
        biggest = max([cfg["first_data_row"] - 1] + scan["rolled_rows"] + scan["retained_rows"])
        styles = [_row_styles(ws, r, ncols) for r in scan["retained_rows"]]
        _clear_block(ws, cfg["first_data_row"], biggest, ncols)
        _write_rows(ws, cfg, kept_values, cfg["first_data_row"], styles=styles)
        _set_table_ref(ws, cfg, len(kept_values))
        wb.save(tmpc)
        wb.close()

        canonical_verification = tw.verify_workbook(
            tmpc, cfg, expect_data_rows=len(kept_values), pre_owned=pre_owned)
        if not canonical_verification["ok"]:
            tmpc.unlink(missing_ok=True)
            res.update({"status": "error", "applied": True,
                        "error": "canonical post-rotation verification failed; canonical untouched",
                        "canonical_verification": canonical_verification})
            return finish(res)
        if tw.sha256_file(tracker_path) != before_hash:
            tmpc.unlink(missing_ok=True)
            res.update({"status": "error", "applied": True,
                        "error": "canonical workbook changed during rollover; retry from the latest file"})
            return finish(res)

        tmpc.replace(tracker_path)
        after = tw.verify_workbook(tracker_path, cfg, expect_data_rows=len(kept_values),
                                   pre_owned=pre_owned)
        res["counts"]["rotated_out_of_canonical"] = len(rolled_values)
        res["canonical"] = {
            "path": str(tracker_path),
            "sha256_before": before_hash,
            "sha256_after": tw.sha256_file(tracker_path),
            "backup": str(canonical_backup),
            "data_rows": after["data_rows"],
            "expected_data_rows": len(kept_values),
            "verification": after,
        }
        if not after["ok"]:
            res.update({"status": "error", "applied": False,
                        "error": "post-rotation verification of the canonical workbook failed"})
            return finish(res)

    # ---- 3. feed the rotated rows into the cross-month dedupe index ------- #
    cross = tw.build_cross_month_index(profile, cfg, [str(adir)])
    rotated_keys = sorted({k for k in scan["rolled_url_keys"] if k})
    indexed = [k for k in rotated_keys if k in cross["url_keys"]]
    res["cross_month_dedupe"] = {
        "rotated_url_keys": len(rotated_keys),
        "rotated_url_keys_indexed": len(indexed),
        "all_rotated_rows_indexed": len(indexed) == len(rotated_keys),
        "index_keys_total": len(cross["url_keys"]),
        "index_sources": cross["sources"],
        "archive_in_index_sources": arch.name in cross["sources"],
    }

    # functional proof: the same posting must be refused, not appended
    probes = [{"url": tw.extract_url(v), "company": row[column_index_from_string(cfg["dedupe"]["company_column"]) - 1],
               "title": row[column_index_from_string(cfg["dedupe"]["title_column"]) - 1]}
              for v, row in zip(scan["rolled_url_keys"], rolled_values) if v]
    probe = tw.write_records(profile, region, probes, apply=False,
                             tracker_override=str(tracker_path),
                             extra_archive_dirs=[str(adir)])
    decisions: dict[str, int] = {}
    for outcome in probe["outcomes"]:
        decisions[outcome["decision"]] = decisions.get(outcome["decision"], 0) + 1
    res["dedupe_proof"] = {
        "records_tested": len(probes),
        "decisions": decisions,
        "appended": probe["counts"]["appended"],
        "refused_as_duplicate": probe["counts"]["appended"] == 0,
    }

    res["canonical_untouched"] = tw.sha256_file(tracker_path) == before_hash
    res["canonical_rows_rotated_out"] = res["counts"]["rotated_out_of_canonical"]
    res["status"] = "written"
    res["applied"] = True
    res["ok"] = res["dedupe_proof"]["refused_as_duplicate"]
    return finish(res)


# --------------------------------------------------------------------------- #
# archive inventory
# --------------------------------------------------------------------------- #

def archives(profile: dict, region: str, *, archive_dir: str | None = None) -> dict:
    cfg = _cfg(profile, region)
    base = Path(archive_dir or profile.get("canonical_dir"))
    out = []
    for name in sorted(set(tw.default_archive_globs(region))):
        for p in sorted(base.glob(name)):
            entry = {"filename": p.name, "sha256": tw.sha256_file(p),
                     "size_bytes": p.stat().st_size}
            try:
                entry["data_rows"] = len(_archive_rows(p, cfg))
            except Exception as exc:  # a corrupt archive must not abort the inventory
                entry["error"] = f"{type(exc).__name__}: {exc}"
            out.append(entry)
    return {"region": region, "archive_dir": str(base), "count": len(out), "archives": out}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def emit(obj) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = json.dumps(obj, indent=2, ensure_ascii=True, default=str)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Monthly tracker rollover / archive worker (B09)")
    ap.add_argument("--profiles")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--region", required=True)
    p.add_argument("--month")
    p.add_argument("--tracker")
    p.add_argument("--archive-dir")
    p.set_defaults(fn=lambda a: (emit(plan(tw.load_profiles(a.profiles), a.region,
                                           a.month or previous_month(),
                                           tracker_override=a.tracker,
                                           archive_dir=a.archive_dir)), 0)[1])

    p = sub.add_parser("rollover")
    p.add_argument("--region", required=True)
    p.add_argument("--month")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--archive-only", action="store_true",
                   help="write the archive but leave the canonical workbook untouched")
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-owner-state-removal", action="store_true")
    p.add_argument("--tracker")
    p.add_argument("--archive-dir")
    p.add_argument("--backup-dir")
    p.add_argument("--state-dir")
    p.add_argument("--no-record", action="store_true")
    p.set_defaults(fn=lambda a: (lambda r: (emit(r), 0 if r.get("status") in
                                            ("written", "planned", "unchanged", "no_rows") else 1)[1])(
        rollover(tw.load_profiles(a.profiles), a.region, a.month or previous_month(),
                 apply=a.apply, archive_only=a.archive_only, archive_dir=a.archive_dir,
                 tracker_override=a.tracker, backup_dir=a.backup_dir, force=a.force,
                 allow_owner_state_removal=a.allow_owner_state_removal,
                 state_dir=a.state_dir, record=not a.no_record)))

    p = sub.add_parser("archives")
    p.add_argument("--region", required=True)
    p.add_argument("--archive-dir")
    p.set_defaults(fn=lambda a: (emit(archives(tw.load_profiles(a.profiles), a.region,
                                               archive_dir=a.archive_dir)), 0)[1])

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
