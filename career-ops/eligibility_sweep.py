#!/usr/bin/env python3
"""Re-screen tracker rows against the clearance/citizenship gate.

The gate is applied at **discovery time only**. In ``codex_entry_level_search``
the JD is fetched and ``clearance_hits`` runs on each candidate a run retrieves;
``regional_job_search.evaluate_record`` does the same on the record blob. Nothing
walks the URLs already sitting in the tracker, so a row written before the gate
existed — or by a path that never called it — stays indefinitely. That is why a
tracker can still hold roles that require SC clearance or British citizenship.

This sweep closes that gap:

    tracker -> each stored URL -> fetch the JD -> same gate -> report

It fails **closed**. A JD that cannot be read (blocked, empty, error) is reported
as ``UNSCREENED`` — never as "clear". An unreadable page cannot prove a role has
no barrier, and treating it as clean is how a clearance role slips in unnoticed.

Modes
-----
``--report`` (default)
    Read-only. Writes a JSON report plus a Markdown summary. Never touches the
    workbook.

``--apply``
    Same screening, then flags the confirmed rows in the Status column and
    re-saves through the same integrity machinery the other writers use
    (lock -> backup -> ``bind_links`` -> ``assert_valid`` -> atomic replace).
    Rows whose status is not ``Not Applied`` are never touched: an Applied or
    Rejected row is the owner's history, not a candidate to re-judge.

    The flag is a **label, not a deletion** — the row and its URL are preserved
    and the reason is auditable.
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

from clearance_screening import clearance_evidence, clearance_hits, is_readable  # noqa: E402
from jd_fetcher import fetch_jd  # noqa: E402
import tracker_writer as tw  # noqa: E402
from tracker_integrity import assert_valid, bind_links  # noqa: E402

DEFAULT_PROFILE = str(HERE.parent / "config" / "profile.yml")
DEFAULT_BACKUP_DIR = HERE / "runtime" / "career-ops" / "backups"

#: Status value written for a confirmed clearance/citizenship barrier.
FLAGGED_STATUS = "Not Eligible - clearance/citizenship required"

#: Status values the sweep is allowed to modify.
SCREENABLE = ("not applied",)


def _tracker_rows(ws, first_data_row: int):
    """Yield ``(row, company, title, url, status)`` for every populated row."""
    for r in range(first_data_row, ws.max_row + 1):
        company = ws.cell(r, 2).value
        title = ws.cell(r, 3).value
        url = ws.cell(r, 4).value
        status = ws.cell(r, 6).value
        if not any((company, title, url)):
            continue
        yield r, str(company or ""), str(title or ""), str(url or ""), str(status or "")


def screen_rows(path, *, timeout: int = 15, limit: int = 0,
                budget_seconds: int = 0, cache_path=None, progress=None):
    """Fetch each stored URL's JD and apply the clearance gate.

    Returns ``(rows, meta)``. ``rows`` is a list of dicts with the screening
    outcome; ``meta`` records what was attempted and how much of it succeeded.
    """
    started = dt.datetime.now(dt.timezone.utc)
    deadline = started.timestamp() + budget_seconds if budget_seconds else None

    wb = openpyxl.load_workbook(path)
    cfg = {"first_data_row": 3, "sheet": "Jobs"}
    ws = wb[cfg["sheet"]]
    candidates = [r for r in _tracker_rows(ws, cfg["first_data_row"])
                  if r[4].strip().lower() in SCREENABLE]
    wb.close()

    if limit:
        candidates = candidates[:limit]

    cache = {}
    if cache_path and pathlib.Path(cache_path).exists():
        try:
            cache = json.loads(pathlib.Path(cache_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}

    rows = []
    fetched = unscreened = flagged = 0
    for r, company, title, url, status in candidates:
        if deadline and dt.datetime.now(dt.timezone.utc).timestamp() > deadline:
            rows.append({"row": r, "company": company, "title": title, "url": url,
                         "status": status, "outcome": "BUDGET_REACHED"})
            continue
        entry = {"row": r, "company": company, "title": title, "url": url,
                 "status": status}
        try:
            jd = fetch_jd(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - a failed fetch is data, not a crash
            entry.update(outcome="UNSCREENED",
                         reason=f"JD fetch raised {type(exc).__name__}")
            unscreened += 1
            rows.append(entry)
            continue

        text = jd.get("text") if isinstance(jd, dict) else None
        if not isinstance(text, str) or not text.strip() or not is_readable(text):
            # Fail closed: no readable text is no evidence of eligibility.
            entry.update(outcome="UNSCREENED",
                         reason="JD returned no readable text",
                         fetch_state=(jd or {}).get("fetch_state"),
                         status_code=(jd or {}).get("status"),
                         is_closed=(jd or {}).get("is_closed"))
            unscreened += 1
            rows.append(entry)
            continue

        fetched += 1
        entry["is_closed"] = bool(jd.get("is_closed"))
        hits = clearance_hits(text)
        if hits:
            flagged += 1
            entry.update(outcome="FLAGGED", hits=hits,
                         evidence=clearance_evidence(text))
        else:
            entry["outcome"] = "CLEAR"

        if cache_path:
            cache[url] = {"outcome": entry["outcome"], "hits": entry.get("hits"),
                          "is_closed": entry.get("is_closed"),
                          "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}

        rows.append(entry)
        if progress:
            progress(entry)

    if cache_path:
        p = pathlib.Path(cache_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    meta = {
        "region_rows": len(candidates),
        "jd_fetched": fetched,
        "unscreened": unscreened,
        "flagged": flagged,
        "started_at": started.isoformat(),
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    return rows, meta


def apply_flags(path, rows, *, profiles, backup_dir=None, dry_run=False):
    """Write ``FLAGGED_STATUS`` onto confirmed rows through the integrity path.

    Mirrors the staged-write pattern of ``tracker_repair``: take the lock, copy a
    backup, ``bind_links`` + ``assert_valid``, save to a temp file and atomically
    replace. A row that no longer reads ``Not Applied`` is skipped.
    """
    flagged = [r for r in rows if r.get("outcome") == "FLAGGED"]
    if not flagged:
        return {"applied": False, "reason": "nothing flagged", "flagged": 0}

    path = pathlib.Path(path)
    cfg = dict(tw.region_config(profiles, "uk"))
    if cfg.get("column_ceiling") != 6:
        raise ValueError("Unexpected UK layout")

    backup_dir = pathlib.Path(backup_dir or DEFAULT_BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".career-mail.lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    staged = path.with_name(path.stem + ".sweep-" + uuid.uuid4().hex + ".xlsx")
    try:
        before = tw.sha256_file(path)
        wb = openpyxl.load_workbook(path)
        ws = wb[cfg["sheet"]]
        target = {r["row"] for r in flagged}
        changed = []
        for r in sorted(target):
            current = str(ws.cell(r, 6).value or "")
            if current.strip().lower() not in SCREENABLE:
                changed.append({"row": r, "skipped": f"status is {current!r}"})
                continue
            ws.cell(r, 6).value = FLAGGED_STATUS
            changed.append({"row": r, "company": ws.cell(r, 2).value,
                            "title": ws.cell(r, 3).value})

        if dry_run:
            wb.close()
            return {"applied": False, "dry_run": True, "would_flag": len(changed),
                    "changes": changed}

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"{path.stem}.pre-sweep-{stamp}.xlsx"
        shutil.copy2(path, backup)
        assert tw.sha256_file(backup) == before, "backup hash mismatch"

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
        return {"applied": True, "backup": str(backup), "flagged": len(changed),
                "changes": changed, "verification": after}
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tracker", required=True)
    ap.add_argument("--profiles", default=DEFAULT_PROFILE)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--limit", type=int, default=0,
                    help="screen only the first N candidates (diagnostics)")
    ap.add_argument("--budget-seconds", type=int, default=0)
    ap.add_argument("--cache", default=None, help="JSON file to cache per-URL results")
    ap.add_argument("--report", default=None, help="write the JSON report here")
    ap.add_argument("--markdown", default=None, help="write the Markdown summary here")
    ap.add_argument("--apply", action="store_true",
                    help="flag confirmed rows in the Status column")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup-dir", default=None)
    args = ap.parse_args(argv)

    rows, meta = screen_rows(args.tracker, timeout=args.timeout, limit=args.limit,
                             budget_seconds=args.budget_seconds, cache_path=args.cache)

    report = {"tracker": args.tracker, "meta": meta, "rows": rows}
    if args.report:
        p = pathlib.Path(args.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.markdown:
        write_markdown(args.markdown, rows, meta)

    print(json.dumps({"meta": meta,
                      "flagged": [f"{r['row']} {r['company']} | {r['title']}"
                                  for r in rows if r["outcome"] == "FLAGGED"],
                      "unscreened": [f"{r['row']} {r['company']} | {r['title']}"
                                     for r in rows if r["outcome"] == "UNSCREENED"]},
                     indent=2))

    if args.apply:
        profiles = tw.load_profiles(args.profiles)
        result = apply_flags(args.tracker, rows, profiles=profiles,
                             backup_dir=args.backup_dir, dry_run=args.dry_run)
        print("APPLY " + json.dumps(result, indent=2))
        return 0 if (result.get("applied") or result.get("dry_run")
                     or result.get("reason")) else 1
    return 0


def write_markdown(path, rows, meta):
    lines = [
        "# Eligibility sweep",
        "",
        f"- candidates screened: **{meta['region_rows']}**",
        f"- job descriptions read: **{meta['jd_fetched']}**",
        f"- unreadable (UNSCREENED): **{meta['unscreened']}**",
        f"- clearance/citizenship barrier found: **{meta['flagged']}**",
        f"- run: {meta['started_at']} → {meta['finished_at']}",
        "",
        "## Confirmed barriers",
        "",
    ]
    flagged = [r for r in rows if r["outcome"] == "FLAGGED"]
    if not flagged:
        lines.append("_None._")
    for r in flagged:
        lines.append(f"### Row {r['row']} — {r['company']} — {r['title']}")
        lines.append("")
        lines.append(f"- URL: {r['url']}")
        lines.append(f"- hits: {', '.join(r['hits'])}")
        lines.append(f"- closed: {r.get('is_closed')}")
        for ev in (r.get("evidence") or [])[:3]:
            lines.append(f"  - `{ev['token']}` — …{ev['context']}…")
        lines.append("")
    unscreened = [r for r in rows if r["outcome"] == "UNSCREENED"]
    lines += ["", "## Unscreened — no readable JD", ""]
    if not unscreened:
        lines.append("_None._")
    for r in unscreened:
        lines.append(f"- Row {r['row']} — {r['company']} — {r['title']} — {r.get('reason')}")
    pathlib.Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
