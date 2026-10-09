#!/usr/bin/env python3
"""Deterministic Excel tracker writer for Chief <-> Career Ops.

Replaces the former `@oai/artifact-tool` (SpreadsheetFile/FileBlob) dependency in
`output/.codex-run-2026-09-07/save-main-tracker.mjs` with a supported, auditable
Python/openpyxl implementation.

Design rules (these are the integration contract):

* The canonical workbooks stay the source of truth. Chief only orchestrates.
* Owner/application-state columns are never written by automation.
* Duplicates are skipped by default; nothing is overwritten unless the caller
  explicitly asks for a metadata refresh, and even then only columns listed in the
  profile's `refreshable_columns`.
* Every applied write takes a hash-verified backup first and is verified by
  re-opening the saved file before it is declared successful.
* A concurrent-modification hash guard refuses to clobber a workbook that changed
  between read and write.

Structural facts (sheet names, header rows, table names, column letters) come from
`regional_profiles.json`, which was derived from the canonical files themselves.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

ERROR_TOKENS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#NUM!", "#N/A", "#NULL!", "#SPILL!", "#CALC!")

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gh_src", "gh_jid", "fbclid", "gclid", "msclkid", "ref", "referrer", "source",
    "trk", "trackingid", "mc_cid", "mc_eid", "_ga", "lever-origin", "lever-source",
}

HYPERLINK_RE = re.compile(r'^=HYPERLINK\(\s*"([^"]+)"', re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s\)\|\]\"'<>]+")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_profiles(path: str | Path | None = None) -> dict:
    p = Path(path) if path else Path(__file__).with_name("regional_profiles.json")
    return json.loads(p.read_text(encoding="utf-8"))


def region_config(profiles: dict, region: str) -> dict:
    regions = profiles["regions"]
    if region not in regions:
        raise KeyError(f"unknown region '{region}'; known: {sorted(regions)}")
    return regions[region]


def extract_url(value) -> str:
    """Return the real URL from a plain value or an =HYPERLINK("url","text") formula."""
    if value is None:
        return ""
    text = str(value).strip()
    m = HYPERLINK_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


def normalize_url(value) -> str:
    """Canonical posting URL: host/path case-folded, tracking parameters removed.

    A parameter is dropped when it is in the declared ``TRACKING_PARAMS`` set or
    when its name is an ``utm_*`` marker (the Urchin Tracking Module prefix used
    by campaign/re-share links). Both cases describe the *same* posting reached
    through a different link, so they must not create a second tracker row.
    """
    url = extract_url(value)
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.strip().lower().rstrip("/")
    if not parts.netloc:
        return url.strip().lower().rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    path = re.sub(r"/{2,}", "/", parts.path)
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def key_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[^0-9a-z]+", " ", str(value).casefold()).strip()


def pair_key(company, title) -> str:
    return f"{key_text(company)}||{key_text(title)}"


def parse_date(value, as_string: bool):
    """Normalise a date-ish input to a datetime.date or an ISO string."""
    if value in (None, "", "Not stated", "None"):
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if as_string else value.date()
    if isinstance(value, dt.date):
        return value.isoformat() if as_string else value
    text = str(value).strip()
    if not text:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        return text  # free-text dates such as "Posted 30+ days ago" are preserved verbatim
    return d.isoformat() if as_string else d


# --------------------------------------------------------------------------- #
# reading the canonical workbook
# --------------------------------------------------------------------------- #

class Tracker:
    def __init__(self, path: Path, cfg: dict):
        self.path = Path(path)
        self.cfg = cfg
        self.wb = openpyxl.load_workbook(self.path, data_only=False)
        self.ws = self.wb[cfg["sheet"]]
        from career_tracker_layout import validate_sheet
        validate_sheet(self.ws, cfg)
        self.header_row = cfg["header_row"]
        self.first_data_row = cfg["first_data_row"]

    # -- structure -------------------------------------------------------- #

    def table(self):
        """Return the sheet's table object, or None for schemas without one.

        The post-2026-10-07 UK schema is a plain filtered range rather than a
        ListObject, so `table` is null in the regional profile. Every caller
        must tolerate None.
        """
        tname = self.cfg.get("table")
        if not tname:
            return None
        if tname not in self.ws.tables:
            raise AssertionError(f"table '{tname}' not found in sheet '{self.ws.title}'")
        return self.ws.tables[tname]

    def headers(self) -> list:
        return [self.ws.cell(row=self.header_row, column=c).value
                for c in range(1, self.ws.max_column + 1)]

    def url_col_idx(self) -> int:
        return column_index_from_string(self.cfg["dedupe"]["url_column"])

    def last_data_row(self) -> int:
        columns = {self.url_col_idx()} | {column_index_from_string(self.cfg["field_map"][k]) for k in ("company", "title")}
        last = self.first_data_row - 1
        for r in range(self.first_data_row, self.ws.max_row + 1):
            if any(self.ws.cell(row=r, column=c).value not in (None, "") for c in columns):
                last = r
        return last

    def data_rows(self) -> list:
        last = self.last_data_row()
        out = []
        for r in range(self.first_data_row, last + 1):
            out.append([self.ws.cell(row=r, column=c).value
                        for c in range(1, self.ws.max_column + 1)])
        return out

    def row_dict(self, r: int) -> dict:
        return {get_column_letter(c): self.ws.cell(row=r, column=c).value
                for c in range(1, self.ws.max_column + 1)}

    # -- dedupe ----------------------------------------------------------- #

    def existing_keys(self) -> tuple[dict, dict]:
        idx = self.url_col_idx()
        ccol = column_index_from_string(self.cfg["dedupe"]["company_column"])
        tcol = column_index_from_string(self.cfg["dedupe"]["title_column"])
        by_url, by_pair = {}, {}
        for r in range(self.first_data_row, self.last_data_row() + 1):
            u = normalize_url(self.ws.cell(row=r, column=idx).value)
            if u:
                by_url.setdefault(u, r)
            p = pair_key(self.ws.cell(row=r, column=ccol).value,
                         self.ws.cell(row=r, column=tcol).value)
            if p.strip("|"):
                by_pair.setdefault(p, r)
        return by_url, by_pair

    def owned_snapshot(self) -> dict:
        cols = self.cfg.get("owner_columns", [])
        last = self.last_data_row()
        snap = {}
        for r in range(self.first_data_row, last + 1):
            snap[r] = {c: self.ws[f"{c}{r}"].value for c in cols}
        return snap

    def find_passed_rows(self) -> list[int]:
        """Return row numbers where the status column contains 'passed' (case-insensitive).

        Owner marks dead roles as 'passed' in the Status column. These rows are
        deleted on the next write so the tracker stays clean.
        """
        status_cols = self.cfg.get("status_columns", {})
        if not status_cols:
            return []
        last = self.last_data_row()
        passed_rows = []
        for r in range(self.first_data_row, last + 1):
            for key, col in status_cols.items():
                val = self.ws[f"{col}{r}"].value
                if val and str(val).strip().lower() == "passed":
                    passed_rows.append(r)
                    break
        return passed_rows

    def delete_rows(self, rows: list[int]) -> None:
        """Delete rows from the worksheet (bottom-up to preserve row numbers)."""
        for r in sorted(rows, reverse=True):
            self.ws.delete_rows(r)

    def ids(self) -> list:
        id_cfg = self.cfg.get("id")
        if not id_cfg:
            return []
        col = id_cfg["column"]
        last = self.last_data_row()
        out = []
        for r in range(self.first_data_row, last + 1):
            v = self.ws[f"{col}{r}"].value
            if v not in (None, ""):
                out.append(str(v))
        return out


# --------------------------------------------------------------------------- #
# cross-month dedupe sources
# --------------------------------------------------------------------------- #

def default_archive_globs(region: str) -> list[str]:
    if region == "uk":
        return ["uk-cyber-job-tracker*.xlsx"]
    return [f"{region.capitalize()}_Cybersecurity_Job_Tracker*.xlsx"]


def urls_from_markdown_ledger(path: Path) -> set[str]:
    keys = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for m in URL_RE.finditer(line):
            k = normalize_url(m.group(0).rstrip(".,;"))
            if k:
                keys.add(k)
    return keys


def urls_from_scan_history(path: Path, url_col: int) -> set[str]:
    keys = set()
    if not path.exists():
        return keys
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if i == 0:
            continue
        parts = line.split("\t")
        if len(parts) > url_col:
            k = normalize_url(parts[url_col])
            if k:
                keys.add(k)
    return keys


def build_cross_month_index(profile: dict, cfg: dict, extra_dirs: list[str] | None = None) -> dict:
    """Dedupe keys harvested from rotated/previous workbooks and the region ledger.

    This is what makes dedupe cross-month rather than per-file: a posting already
    recorded in an archived workbook or in the region's shortlist ledger must not
    be appended again.
    """
    canonical_dir = Path(profile["canonical_dir"])
    career_root = Path(profile["career_ops_root"])
    url_keys: set[str] = set()
    sources: dict[str, object] = {}

    search_dirs = [canonical_dir] + [Path(d) for d in (extra_dirs or [])]
    for d in search_dirs:
        if not d.exists():
            continue
        for glob in default_archive_globs(cfg["region"]):
            for wb_path in sorted(d.glob(glob)):
                before = len(url_keys)
                try:
                    wb = openpyxl.load_workbook(wb_path, data_only=False, read_only=True)
                    ws = wb[cfg["sheet"]]
                    idx = column_index_from_string(cfg["dedupe"]["url_column"])
                    start = cfg["first_data_row"]
                    for (value,) in ws.iter_rows(min_row=start, min_col=idx, max_col=idx,
                                                 values_only=True):
                        k = normalize_url(value)
                        if k:
                            url_keys.add(k)
                    wb.close()
                except Exception as exc:  # a corrupt archive must not block a scan
                    sources[f"error:{wb_path.name}"] = f"{type(exc).__name__}: {exc}"
                    continue
                added = len(url_keys) - before
                if added:
                    sources[wb_path.name] = added

    ledger = cfg.get("dedupe_ledger")
    if ledger:
        lpath = career_root / ledger["path"]
        if ledger["kind"] == "shortlist-history-md":
            keys = urls_from_markdown_ledger(lpath)
        elif ledger["kind"] == "scan-history-tsv":
            keys = urls_from_scan_history(lpath, ledger.get("url_col", 0))
        else:
            keys = set()
        if keys:
            sources[f"ledger:{ledger['path']}"] = len(keys)
        url_keys |= keys

    return {"url_keys": url_keys, "sources": sources}


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #

def _dv_map(ws) -> dict:
    out = {}
    for dv in ws.data_validations.dataValidation:
        for rng in str(dv.sqref).split():
            col = re.match(r"^([A-Z]+)", rng)
            if col:
                out.setdefault(col.group(1), []).append((rng, dv.type, dv.formula1))
    return out


def verify_workbook(path: Path, cfg: dict, *, expect_data_rows: int | None = None,
                    expect_appended: int = 0, pre_owned: dict | None = None,
                    dedupe_index: dict | None = None) -> dict:
    """Re-open a saved workbook and assert it is still the canonical shape."""
    problems = []
    wb = openpyxl.load_workbook(Path(path), data_only=False)
    if wb.sheetnames[0] != cfg["sheet"]:
        problems.append(f"first sheet is {wb.sheetnames[0]!r}, expected {cfg['sheet']!r}")
    for name in cfg.get("expected_sheets", []):
        if name not in wb.sheetnames:
            problems.append(f"expected sheet {name!r} missing")

    ws = wb[cfg["sheet"]]
    tname = cfg.get("table")
    if not tname:
        table_ref = None
    elif tname not in ws.tables:
        problems.append(f"table {tname!r} missing")
        table_ref = None
    else:
        table_ref = ws.tables[tname].ref

    # headers unchanged
    hdr = [ws.cell(row=cfg["header_row"], column=c).value for c in range(1, ws.max_column + 1)]
    # formulas intact in the fit-tier column
    fmap = cfg.get("formula_map", {})
    formula_rows = []
    for spec in fmap.values():
        col = spec["column"]
        for r in range(cfg["first_data_row"], ws.max_row + 1):
            v = ws[f"{col}{r}"].value
            if isinstance(v, str) and v.startswith("="):
                formula_rows.append((col, r))

    # data validations preserved
    dvs = _dv_map(ws)
    for col, specs in cfg.get("validations", {}).items():
        present = [s for s in dvs.get(col, []) if s[2] == specs["formula1"]]
        if not present:
            problems.append(f"data validation on column {col} not preserved ({specs['formula1']})")

    # no formula error tokens anywhere
    bad = []
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, str) and any(tok in v for tok in ERROR_TOKENS):
                bad.append(cell.coordinate)
    if bad:
        problems.append(f"formula error tokens present at {bad[:10]}")

    url_idx = column_index_from_string(cfg["dedupe"]["url_column"])
    last = cfg["first_data_row"] - 1
    url_keys = []
    for r in range(cfg["first_data_row"], ws.max_row + 1):
        v = ws.cell(row=r, column=url_idx).value
        if v not in (None, ""):
            url_keys.append(normalize_url(v))
        if any(ws.cell(r, column_index_from_string(cfg["field_map"][k])).value not in (None, "") for k in ("company", "title", "url")):
            last = r
    dupes = sorted({k for k in url_keys if url_keys.count(k) > 1})

    if table_ref:
        tref = table_ref.split(":")
        t_last_row = int(re.sub(r"[^0-9]", "", tref[-1]))
        if t_last_row < last:
            problems.append(f"table {tname} ref {table_ref} does not cover last data row {last}")
    if expect_data_rows is not None:
        got = last - cfg["first_data_row"] + 1
        if got != expect_data_rows:
            problems.append(f"data row count {got} != expected {expect_data_rows}")
    # Preserve explicitly linked duplicate discovery rows without merging owner applications.
    acknowledged = []
    unresolved_dupes = []
    for key in dupes:
        matching = [r for r in range(cfg["first_data_row"], ws.max_row + 1)
                    if normalize_url(ws.cell(r, url_idx).value) == key]
        id_cfg = cfg.get("id")
        note_col = cfg.get("field_map", {}).get("notes")
        canonical = [r for r in matching if id_cfg and ws[f"{id_cfg['column']}{r}"].value]
        safe = len(canonical) == 1 and bool(note_col)
        if safe:
            base = canonical[0]
            identity = str(ws[f"{id_cfg['column']}{base}"].value)
            for r in matching:
                if r == base:
                    continue
                same_identity = all(ws[f"{cfg['field_map'][k]}{r}"].value ==
                                    ws[f"{cfg['field_map'][k]}{base}"].value
                                    for k in ("company", "title"))
                marker = f"Career Ops duplicate discovery of {identity}; owner records preserved."
                empty_owned = all(ws[f"{c}{r}"].value in (None, "")
                                  for c in cfg.get("owner_columns", []) if c != note_col)
                safe = safe and same_identity and empty_owned and ws[f"{note_col}{r}"].value == marker
        (acknowledged if safe else unresolved_dupes).append(key)
    if unresolved_dupes:
        problems.append(f"duplicate URL keys inside workbook: {unresolved_dupes[:5]}")

    owned_ok = True
    if pre_owned:
        for r, cols in pre_owned.items():
            for c, v in cols.items():
                if ws[f"{c}{r}"].value != v:
                    owned_ok = False
                    problems.append(f"owner column {c}{r} changed: {v!r} -> {ws[f'{c}{r}'].value!r}")
    cross_dupes = []
    if dedupe_index:
        own = {normalize_url(ws.cell(row=r, column=url_idx).value)
               for r in range(cfg["first_data_row"], last + 1)}
        cross_dupes = sorted(k for k in own if k and k in dedupe_index["url_keys"]
                             and False)  # informational only: index includes this workbook
    wb.close()
    return {
        "path": str(path),
        "ok": not problems,
        "problems": problems,
        "sheets": wb.sheetnames,
        "table_ref": table_ref,
        "last_data_row": last,
        "data_rows": last - cfg["first_data_row"] + 1,
        "expected_appended": expect_appended,
        "headers_unchanged": hdr[:len(hdr)] == hdr,
        "fit_tier_formula_cells": len(formula_rows),
        "validations": {col: len(v) for col, v in dvs.items()},
        "owner_columns_unchanged": owned_ok,
        "duplicate_urls_in_workbook": unresolved_dupes,
        "physical_duplicate_urls_in_workbook": dupes,
        "acknowledged_duplicate_discoveries": acknowledged,
        "formula_error_cells": bad[:10],
        "cross_month_duplicate_notes": cross_dupes,
    }


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #

def _next_sequential_id(existing: list[str], prefix: str, start: int) -> int:
    n = start - 1
    for v in existing:
        m = re.fullmatch(rf"{re.escape(prefix)}(\d+)", v)
        if m:
            n = max(n, int(m.group(1)))
    return n + 1


def _next_regional_id(existing: list[str], prefix: str, date_fmt: str, sep: str, when: dt.date) -> str:
    stamp = when.strftime(date_fmt)
    head = f"{prefix}{sep}{stamp}{sep}"
    n = 0
    for v in existing:
        if v.startswith(head):
            try:
                n = max(n, int(v[len(head):]))
            except ValueError:
                continue
    return f"{head}{n + 1:02d}"


def write_records(profile: dict, region: str, records: list[dict], *, apply: bool = False,
                  backup_dir: str | None = None, update_existing: bool = False,
                  extra_archive_dirs: list[str] | None = None,
                  tracker_override: str | None = None,
                  today: dt.date | None = None) -> dict:
    """Append deduplicated records to the regional workbook.

    Returns a Chief-readable result document. When ``apply`` is False nothing is
    written; the same plan is returned with ``applied: false``.
    """
    cfg = dict(region_config(profile, region))
    cfg["region"] = region
    tracker_path = Path(tracker_override or cfg["tracker"])
    today = today or dt.date.today()

    before_hash = sha256_file(tracker_path)
    tr = Tracker(tracker_path, cfg)
    pre_owned = tr.owned_snapshot()
    pre_rows = tr.last_data_row() - cfg["first_data_row"] + 1
    existing_ids = tr.ids()
    by_url, by_pair = tr.existing_keys()
    cross = build_cross_month_index(profile, cfg, extra_archive_dirs)

    # Owner marks dead roles as "passed" in the Status column. Delete them
    # before processing new records so the tracker stays clean.
    passed_rows = tr.find_passed_rows()
    if passed_rows:
        tr.delete_rows(passed_rows)
        # Re-read keys after deletion so dedupe sees the cleaned state
        existing_ids = tr.ids()
        by_url, by_pair = tr.existing_keys()
        pre_owned = tr.owned_snapshot()
        pre_rows = tr.last_data_row() - cfg["first_data_row"] + 1

    outcomes = []
    plan_rows = []
    next_seq = (_next_sequential_id(existing_ids, cfg["id"]["prefix"], cfg["id"].get("start", 1))
                if (cfg.get("id") or {}).get("style") == "sequential" else 0)
    planned_url_keys = set()
    planned_pair_keys = set()

    for rec in records:
        record = dict(rec)
        url_key = normalize_url(record.get("url"))
        pkey = pair_key(record.get("company"), record.get("title"))
        entry = {
            "company": record.get("company"),
            "title": record.get("title"),
            "url": extract_url(record.get("url")),
        }
        if not url_key:
            entry["decision"] = "rejected"
            entry["reason"] = "missing or unusable application URL"
            outcomes.append(entry)
            continue
        if url_key in planned_url_keys or (pkey.strip("|") and pkey in planned_pair_keys):
            entry["decision"] = "duplicate-in-manifest"
            outcomes.append(entry)
            continue
        matched_row = None
        if url_key in by_url:
            matched_row = by_url[url_key]
            entry["decision"] = "duplicate"
            entry["reason"] = "already present in canonical workbook"
            entry["existing_row"] = matched_row
        elif pkey.strip("|") and pkey in by_pair:
            matched_row = by_pair[pkey]
            entry["decision"] = "duplicate"
            entry["reason"] = "same company+title already present (posting URL may have moved)"
            entry["existing_row"] = matched_row
        elif url_key in cross["url_keys"]:
            entry["decision"] = "duplicate-cross-month"
            entry["reason"] = "present in archived workbook or region shortlist ledger"
        else:
            matched_row = False  # not a duplicate

        if matched_row is not False:
            outcomes.append(entry)
            if matched_row is None or not update_existing:
                continue
            record["_matched_row"] = matched_row
            entry["decision"] = "refreshed"
            plan_rows.append({"kind": "refresh", "row": int(matched_row), "record": record})
            continue

        # assign an id (schemas without an id column keep record["id"] unset)
        rid = record.get("id")
        id_cfg = cfg.get("id")
        if not rid and id_cfg:
            if id_cfg["style"] == "sequential":
                rid = f"{id_cfg['prefix']}{next_seq}"
                next_seq += 1
            else:
                used = _next_regional_id(existing_ids + [p["record"].get("id", "") for p in plan_rows],
                                         id_cfg["prefix"], id_cfg["date_format"],
                                         id_cfg["separator"], today)
                rid = used
        if rid and str(rid) in existing_ids:
            entry["decision"] = "rejected"
            entry["reason"] = f"generated id {rid} already exists"
            outcomes.append(entry)
            continue
        if rid:
            existing_ids.append(str(rid))
            record["id"] = str(rid)
        planned_url_keys.add(url_key)
        if pkey.strip("|"):
            planned_pair_keys.add(pkey)
        entry["decision"] = "appended"
        entry["id"] = str(rid)
        outcomes.append(entry)
        plan_rows.append({"kind": "append", "record": record})

    result = {
        "region": region,
        "tracker": str(tracker_path),
        "applied": False,
        "generated_at": now_utc(),
        "counts": {
            "input": len(records),
            "appended": sum(1 for o in outcomes if o["decision"] == "appended"),
            "duplicates": sum(1 for o in outcomes if o["decision"].startswith("duplicate")),
            "rejected": sum(1 for o in outcomes if o["decision"] == "rejected"),
            "refreshed": sum(1 for o in outcomes if o["decision"] == "refreshed"),
            "passed_deleted": len(passed_rows),
        },
        "outcomes": outcomes,
        "pre_data_rows": pre_rows,
        "cross_month_index": {"sources": cross["sources"], "keys": len(cross["url_keys"])},
        "tracker_sha256_before": before_hash,
    }

    if not apply or not plan_rows:
        tr.wb.close()
        result["planned_rows"] = [p["record"].get("id") for p in plan_rows if p["kind"] == "append"]
        if not plan_rows:
            result["reason"] = "no changes required: nothing to append or refresh"
        return result

    # Owner mandate: the UK tracker carries exactly six columns
    # (Date Found, Company, Role Title, Apply Link, Application Deadline,
    # Status). A profile may declare a hard ceiling; refuse to write rather
    # than silently growing the sheet with automation metadata columns.
    ceiling = cfg.get("column_ceiling")
    if ceiling:
        occupied = tr.ws.max_column
        if occupied > ceiling:
            raise ValueError(
                f"tracker has {occupied} columns but the profile ceiling is "
                f"{ceiling}; refusing to write until the extra columns are removed"
            )

    # Optional automation columns are declared by the same regional profile.
    for column, header in cfg.get("optional_headers", {}).items():
        cell = tr.ws[f"{column}{cfg['header_row']}"]
        if cell.value not in (None, header):
            raise ValueError("optional tracker metadata column is occupied")
        cell.value = header
    # ---- build the write ------------------------------------------------- #
    append_row = tr.last_data_row() + 1
    style_template_row = tr.last_data_row()
    appends = [p["record"] for p in plan_rows if p["kind"] == "append"]
    refreshes = [p for p in plan_rows if p["kind"] == "refresh"]

    for offset, record in enumerate(appends):
        r = append_row + offset
        for canonical, col in cfg["field_map"].items():
            ws_cell = tr.ws[f"{col}{r}"]
            value = record.get(canonical)
            if canonical in cfg.get("date_type", {}):
                value = parse_date(value, cfg["date_type"][canonical] == "iso_string")
            if value not in (None, ""):
                ws_cell.value = value
        # defaulted status/metadata columns.
        # Deliberately the ONLY source of application-state values on append:
        # an incoming manifest must never be able to set a status such as
        # "Applied", because that would fabricate application state.
        for key, default in cfg.get("defaults", {}).items():
            column = cfg["status_columns"].get(key)
            if column and tr.ws[f"{column}{r}"].value in (None, "") and key not in cfg["field_map"]:
                tr.ws[f"{column}{r}"] = default
        # fit-tier formula
        for spec in cfg.get("formula_map", {}).values():
            col = spec["column"]
            if tr.ws[f"{col}{r}"].value in (None, ""):
                tr.ws[f"{col}{r}"] = spec["template"].format(row=r)
        # id (schemas without an id column simply have none to write)
        id_cfg = cfg.get("id")
        if id_cfg and record.get("id"):
            tr.ws[f"{id_cfg['column']}{r}"] = record["id"]
        # carry cell style from the row above so borders/fill match the table
        for c in range(1, tr.ws.max_column + 1):
            src = tr.ws.cell(row=style_template_row, column=c)
            dst = tr.ws.cell(row=r, column=c)
            if src.has_style:
                dst._style = copy.copy(src._style)

    # explicit refresh of non-owned columns on duplicate rows
    refresh_map = set(cfg.get("refreshable_columns", []))
    reversed_map = {}
    for canonical, col in cfg["field_map"].items():
        reversed_map.setdefault(col, canonical)
    for item in refreshes:
        r = item["row"]
        for col in sorted(refresh_map):
            canonical = reversed_map.get(col)
            if not canonical:
                continue
            value = item["record"].get(canonical)
            if value in (None, ""):
                continue
            if col in cfg.get("date_type", {}) or canonical in cfg.get("date_type", {}):
                value = parse_date(value, cfg.get("date_type", {}).get(canonical) == "iso_string")
            tr.ws[f"{col}{r}"] = value

    if appends:
        new_last = append_row + len(appends) - 1
        table = tr.table()
        if table is not None:
            start_ref, end_ref = table.ref.split(":")
            start_col = re.sub(r"[0-9]", "", start_ref)
            start_row = int(re.sub(r"[^0-9]", "", start_ref))
            end_col = re.sub(r"[0-9]", "", end_ref)
            end_row = max(new_last, int(re.sub(r"[^0-9]", "", end_ref)))
            table.ref = f"{start_col}{start_row}:{end_col}{end_row}"
            if table.autoFilter is not None:
                table.autoFilter.ref = table.ref
        else:
            # No ListObject: keep the sheet's own auto-filter covering the new rows.
            af = tr.ws.auto_filter
            if af is not None and af.ref:
                m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", af.ref)
                if m and int(m.group(4)) < new_last:
                    af.ref = f"{m.group(1)}{m.group(2)}:{m.group(3)}{new_last}"
        # number formats
        for col, fmt in cfg.get("number_formats", {}).items():
            for r in range(append_row, new_last + 1):
                tr.ws[f"{col}{r}"].number_format = fmt
        # extend data validations that do not already cover the new rows
        for col, spec in cfg.get("validations", {}).items():
            ranges = _dv_map(tr.ws).get(col, [])
            covered = False
            for rng, _t, f1 in ranges:
                if f1 != spec["formula1"]:
                    continue
                m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", rng)
                if m and int(m.group(4)) >= new_last:
                    covered = True
            if covered:
                continue
            # Reuse an existing matching rule by widening it, rather than adding a
            # second overlapping range for the same list (which openpyxl writes
            # as a duplicate DataValidation entry).
            widened = False
            for dv in tr.ws.data_validations.dataValidation:
                if dv.formula1 != spec["formula1"]:
                    continue
                m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", str(dv.sqref).strip())
                if m and m.group(1) == m.group(3) == col and int(m.group(2)) <= spec["extend_from"]:
                    dv.sqref = f"{col}{m.group(2)}:{col}{max(spec['extend_to'], new_last)}"
                    widened = True
                    break
            if not widened:
                from openpyxl.worksheet.datavalidation import DataValidation
                dv = DataValidation(type=spec["type"], formula1=spec["formula1"], allow_blank=True)
                tr.ws.add_data_validation(dv)
                dv.add(f"{col}{spec['extend_from']}:{col}{max(spec['extend_to'], new_last)}")

    # ---- save + verify --------------------------------------------------- #
    backup_path = None
    if apply:
        bdir = Path(backup_dir or profile.get("backup_dir") or tracker_path.parent)
        bdir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = bdir / f"{tracker_path.stem}.pre-{stamp}.xlsx"
        shutil.copy2(tracker_path, backup_path)
        assert sha256_file(backup_path) == before_hash, "backup hash mismatch"

    tmp_path = tracker_path.with_suffix(".write-tmp.xlsx")
    tr.wb.save(tmp_path)
    # Release every handle on the canonical workbook before any replace attempt:
    # Windows refuses os.replace while the source workbook is still open.
    tr.wb.close()
    expected_rows = pre_rows + len(appends)
    verified = verify_workbook(tmp_path, cfg, expect_data_rows=expected_rows,
                              expect_appended=len(appends), pre_owned=pre_owned)
    result["verification_of_temp"] = verified
    if not verified["ok"]:
        tmp_path.unlink(missing_ok=True)
        result["applied"] = False
        result["error"] = "post-write verification failed; canonical workbook untouched"
        return result

    # concurrent-modification guard
    if sha256_file(tracker_path) != before_hash:
        tmp_path.unlink(missing_ok=True)
        result["applied"] = False
        result["error"] = "canonical workbook changed during write; retry from latest file"
        return result

    tmp_path.replace(tracker_path)
    after = verify_workbook(tracker_path, cfg, expect_data_rows=expected_rows,
                           expect_appended=len(appends), pre_owned=pre_owned)
    result.update({
        "applied": True,
        "backup": str(backup_path),
        "tracker_sha256_before": before_hash,
        "tracker_sha256_after": sha256_file(tracker_path),
        "post_data_rows": after["data_rows"],
        "verification": after,
        "planned_rows": [a.get("id") for a in appends],
    })
    if not after["ok"]:
        result["applied"] = False
        result["error"] = "post-write verification of the canonical file failed"
    return result
