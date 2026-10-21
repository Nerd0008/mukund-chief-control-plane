#!/usr/bin/env python3
"""Remove expired and clearance/citizenship-requiring rows from the UK tracker.

Owner instruction (2026-10-21, verbatim): "go through each job in the tracker
remove the jobs which have expired and require any clearance or citizenship. Only
keep jobs and internships which I have already applied and are open keep the open
ones on top"

What that means here:

* **Remove** a row when its job description states a security-clearance or
  citizenship requirement (SC/DV/CTC/NPPV/UKSV/BPSS, British citizenship,
  indefinite leave to remain, long UK residency). Requirement text lives in the
  **JD**, never the title — so the title alone can never decide this.
* **Remove** a row when the posting is expired: the page says closed/filled, or
  the stored application deadline has passed.
* **Keep** everything else. Applied and Rejected rows are the owner's own history
  and are never removed, even when the posting has since closed.
* **Order** the survivors with the open roles on top, then Applied, then
  Rejected. The owner asked for the open ones on top; applied rows stay above the
  rejected tail so his history stays readable.

Failing closed
--------------
A row whose JD cannot be fetched is **kept**, never removed. An unreadable page
cannot prove a role is expired or that it has no vetting bar, and removing a job
the owner could have applied to is the worse error. The report lists every row
that could not be checked so nothing is silently skipped.

Row values, per-row number formats and the status dropdown are carried through
unchanged. The write follows the integrity path the other writers use: lock ->
backup -> ``bind_links`` -> ``assert_valid`` -> atomic replace.
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys
import uuid

import openpyxl

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from application_deadlines import deadline_from_value, deadline_priority  # noqa: E402
from clearance_screening import clearance_hits, is_readable  # noqa: E402
from jd_fetcher import fetch_jd  # noqa: E402
import tracker_writer as tw  # noqa: E402
from tracker_integrity import assert_valid, bind_links  # noqa: E402

DEFAULT_CACHE = HERE.parent / "runtime" / "career-ops" / "prune-uk-cache.json"
DEFAULT_BACKUP_DIR = HERE.parent / "runtime" / "career-ops" / "backups"

FIRST_DATA_ROW = 3
LAST_COL = 6
#: Statuses that are the owner's own history and are never removed.
HISTORY_STATUSES = ("applied", "rejected")


def read_rows(path):
    """Return every data row as a dict of values, formats and hyperlink."""
    wb = openpyxl.load_workbook(path)
    ws = wb["Jobs"]
    out = []
    for r in range(FIRST_DATA_ROW, ws.max_row + 1):
        values = [ws.cell(r, c).value for c in range(1, LAST_COL + 1)]
        if not any(values):
            continue
        formats = [ws.cell(r, c).number_format for c in range(1, LAST_COL + 1)]
        link = ws.cell(r, 4).hyperlink
        out.append({
            "row": r,
            "values": values,
            "formats": formats,
            "url": values[3],
            "link_target": link.target if link else None,
        })
    wb.close()
    return out


def screen(url, timeout, cache):
    """Fetch a posting and return ``(clearance_hits, expired, readable)``."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return [], False, False
    if url in cache:
        c = cache[url]
        return c.get("hits") or [], bool(c.get("closed")), bool(c.get("readable"))
    try:
        jd = fetch_jd(url, timeout=timeout)
    except Exception:  # noqa: BLE001 - a failed fetch is data, not a crash
        return [], False, False
    text = jd.get("text") if isinstance(jd, dict) else None
    readable = isinstance(text, str) and bool(text.strip()) and is_readable(text)
    hits = clearance_hits(text) if readable else []
    closed = bool(jd.get("is_closed")) if isinstance(jd, dict) else False
    cache[url] = {"hits": hits, "closed": closed, "readable": readable,
                  "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    return hits, closed, readable


def deadline_passed(value, today=None):
    """True when the stored application deadline is in the past."""
    info = deadline_from_value(value)
    if not info or not info.get("date"):
        return False
    try:
        return deadline_priority({"deadline_info": info}, today)[0] == 4
    except Exception:  # noqa: BLE001
        return False


def classify(rows, cache, timeout):
    """Attach a keep/remove decision and an ordering bucket to every row."""
    today = dt.date.today()
    for r in rows:
        status = str(r["values"][5] or "").strip().lower()
        r["status"] = status
        r["hits"], closed, r["readable"] = screen(r["url"], timeout, cache)
        r["deadline_passed"] = deadline_passed(r["values"][4], today)
        r["expired"] = closed or r["deadline_passed"]

        if r["hits"]:
            r["decision"] = "remove"
            r["reason"] = "clearance/citizenship: " + ", ".join(r["hits"])
            r["bucket"] = None
        elif r["expired"] and status not in HISTORY_STATUSES:
            r["decision"] = "remove"
            r["reason"] = ("deadline passed" if r["deadline_passed"]
                           else "posting closed/filled")
            r["bucket"] = None
        else:
            r["decision"] = "keep"
            r["reason"] = ""
            if not r["expired"]:
                r["bucket"] = 0          # open, on top
            elif status in HISTORY_STATUSES:
                r["bucket"] = 1          # applied / rejected history
            else:
                r["bucket"] = 2          # kept but unverifiable
    return rows


def order(rows):
    """Open roles on top, then applied history, then rejected.

    Unverifiable Not-Applied rows sit directly under the verified-open block:
    they are still candidates to look at, and the report lists them by row so
    nothing is hidden. Rejected stays at the tail.
    """
    def key(r):
        s = r["status"]
        if s in HISTORY_STATUSES:
            return (2 if s == "applied" else 3, r["row"])
        return (0 if not r["expired"] else 1, r["row"])

    kept = [r for r in rows if r["decision"] == "keep"]
    kept.sort(key=key)
    return kept


def apply_prune(path, rows, kept, *, profiles, backup_dir=None, dry_run=False):
    """Rewrite the data area in the new order, preserving values and formats."""
    path = pathlib.Path(path)
    cfg = dict(tw.region_config(profiles, "uk"))
    if cfg.get("column_ceiling") != 6:
        raise ValueError("Unexpected UK layout")

    backup_dir = pathlib.Path(backup_dir or DEFAULT_BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".career-mail.lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    staged = path.with_name(path.stem + ".prune-" + uuid.uuid4().hex + ".xlsx")
    try:
        before = tw.sha256_file(path)
        wb = openpyxl.load_workbook(path)
        ws = wb["Jobs"]
        max_row = ws.max_row

        if dry_run:
            wb.close()
            return {"applied": False, "dry_run": True, "kept": len(kept),
                    "removed": len(rows) - len(kept)}

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"{path.stem}.pre-prune-{stamp}.xlsx"
        shutil.copy2(path, backup)
        assert tw.sha256_file(backup) == before, "backup hash mismatch"

        # Capture the data-validation rule so it can be re-pointed at the new end.
        dv_spec = None
        for dv in ws.data_validations.dataValidation:
            dv_spec = {"type": dv.type, "formula1": dv.formula1,
                       "extend_from": FIRST_DATA_ROW}
            break

        new_last = FIRST_DATA_ROW + len(kept) - 1
        for i, r in enumerate(kept):
            target = FIRST_DATA_ROW + i
            for c in range(1, LAST_COL + 1):
                cell = ws.cell(target, c)
                cell.value = r["values"][c - 1]
                cell.number_format = r["formats"][c - 1]
        for r in range(new_last + 1, max_row + 1):
            for c in range(1, LAST_COL + 1):
                cell = ws.cell(r, c)
                cell.value = None
                cell.hyperlink = None

        if dv_spec:
            for dv in list(ws.data_validations.dataValidation):
                ws.data_validations.dataValidation.remove(dv)
            from openpyxl.worksheet.datavalidation import DataValidation
            dv = DataValidation(type=dv_spec["type"], formula1=dv_spec["formula1"],
                                allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"F{FIRST_DATA_ROW}:F{max(new_last, FIRST_DATA_ROW)}")

        bind_links(ws, cfg)
        assert_valid(ws, cfg)
        wb.save(staged)
        wb.close()
        verified = tw.verify_workbook(staged, cfg)
        if not verified["ok"]:
            staged.unlink(missing_ok=True)
            return {"applied": False, "error": "post-write verification failed",
                    "verification": verified}
        if tw.sha256_file(path) != before:
            staged.unlink(missing_ok=True)
            return {"applied": False,
                    "error": "canonical workbook changed during write; retry"}
        staged.replace(path)
        after = tw.verify_workbook(path, cfg)
        return {"applied": True, "backup": str(backup), "kept": len(kept),
                "removed": len(rows) - len(kept), "verification": after}
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tracker", required=True)
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--profiles", default=None,
                    help="profiles JSON (defaults to the Career Ops install's)")
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--report", default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup-dir", default=None)
    args = ap.parse_args(argv)

    cache = {}
    if pathlib.Path(args.cache).exists():
        try:
            cache = json.loads(pathlib.Path(args.cache).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    pathlib.Path(args.cache).parent.mkdir(parents=True, exist_ok=True)

    rows = classify(read_rows(args.tracker), cache, args.timeout)
    kept = order(rows)
    pathlib.Path(args.cache).write_text(json.dumps(cache, indent=2), encoding="utf-8")

    removed = [r for r in rows if r["decision"] == "remove"]
    unverified = [r for r in rows if r["decision"] == "keep" and not r["readable"]]
    report = {
        "tracker": args.tracker,
        "data_rows": len(rows),
        "kept": len(kept),
        "removed": len(removed),
        "unverified_kept": len(unverified),
        "removed_rows": [{"row": r["row"], "company": r["values"][1],
                          "title": r["values"][2], "reason": r["reason"]}
                         for r in removed],
        "unverified_rows": [{"row": r["row"], "company": r["values"][1],
                             "title": r["values"][2], "status": r["status"]}
                            for r in unverified],
    }
    if args.report:
        p = pathlib.Path(args.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({"data_rows": len(rows), "kept": len(kept),
                      "removed": len(removed),
                      "unverified_kept": len(unverified)}, indent=2))
    for r in removed:
        print(f"  - row {r['row']:>4} {str(r['values'][1])[:32]:<32} | "
              f"{str(r['values'][2])[:44]:<44} | {r['reason']}")

    if args.apply:
        profiles = (tw.load_profiles(args.profiles) if args.profiles
                    else tw.load_profiles())
        result = apply_prune(args.tracker, rows, kept, profiles=profiles,
                             backup_dir=args.backup_dir, dry_run=args.dry_run)
        print("APPLY " + json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
