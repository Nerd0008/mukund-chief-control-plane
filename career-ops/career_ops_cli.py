#!/usr/bin/env python3
"""Chief <-> Career Ops deterministic interface.

Chief calls this single entry point. Every subcommand prints exactly one JSON
object on stdout, so Chief can consume the result without parsing prose.

Subcommands
-----------
  inventory                       structural facts for every regional workbook
  verify  --region R              integrity verification of a canonical workbook
  dedupe  --region R --manifest F dedupe decisions for a manifest (no writes)
  write   --region R --manifest F [--apply] [--update-existing]
                                  append deduplicated records (dry-run by default)
  rollover --region R [--month YYYY-MM] [--apply] [--archive-only] [--force]
                                  monthly rollover into a per-region archive workbook
                                  (dry-run by default; roster B09)
  run-health [--job J]            deterministic run-health for the Excel workers
  summary --region R              Chief-readable tracker summary
  scan    --region R [--dry-run]  bounded Career Ops scan wrapper (delegates to scan.mjs)
  ledger  --region R              cross-month dedupe index provenance

Safety: no subcommand submits applications, sends messages or contacts employers.
`write` is a dry run unless --apply is passed, and --apply always takes a
hash-verified backup first.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracker_writer import (  # noqa: E402
    build_cross_month_index,
    load_profiles,
    normalize_url,
    region_config,
    sha256_file,
    verify_workbook,
)
import tracker_writer  # noqa: E402
import dept_run_health  # noqa: E402
import tracker_rollover  # noqa: E402

HERE = Path(__file__).resolve().parent
CAREER_OPS_DIR = HERE


def emit(obj) -> None:
    """Print exactly one JSON object, never failing on a non-UTF-8 console.

    Observed defect (2026-09-23): under Windows Task Scheduler stdout is
    redirected to a file whose encoding defaults to the OEM/ANSI code page
    (cp1252 on this host). A scan that had *succeeded* then aborted in this
    function with UnicodeEncodeError while printing non-Latin job titles,
    which made the scheduled run report exit code 1 for completed work and
    left a traceback in the run log instead of a JSON result.

    The contract is unchanged: exactly one JSON object is written to stdout.
    If the console code page cannot encode it, the same object is emitted
    ASCII-escaped instead of raising.
    """
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = json.dumps(obj, indent=2, ensure_ascii=True, default=str)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def cmd_inventory(args) -> int:
    profiles = load_profiles(args.profiles)
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
           "regions": {}}
    for region, cfg in profiles["regions"].items():
        c = dict(cfg)
        c["region"] = region
        path = Path(cfg["tracker"])
        entry = {
            "display_name": cfg["display_name"],
            "tracker": str(path),
            "exists": path.exists(),
            "sheet": cfg["sheet"],
            "table": cfg["table"],
            "header_row": cfg["header_row"],
            "owner_columns": cfg["owner_columns"],
            "dedupe_url_column": cfg["dedupe"]["url_column"],
            "id_style": cfg["id"]["style"],
        }
        if path.exists():
            tr = tracker_writer.Tracker(path, c)
            entry.update({
                "sha256": sha256_file(path),
                "data_rows": tr.last_data_row() - cfg["first_data_row"] + 1,
                "first_data_row": cfg["first_data_row"],
                "last_data_row": tr.last_data_row(),
                "table_ref": tr.table().ref,
                "id_sample": tr.ids()[-3:],
                "sheets": tr.wb.sheetnames,
            })
            tr.wb.close()
        out["regions"][region] = entry
    emit(out)
    return 0


def cmd_verify(args) -> int:
    profiles = load_profiles(args.profiles)
    regions = [args.region] if args.region else list(profiles["regions"])
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
           "results": {}}
    rc = 0
    for region in regions:
        cfg = dict(region_config(profiles, region))
        cfg["region"] = region
        path = Path(args.tracker or cfg["tracker"])
        if not path.exists():
            out["results"][region] = {"ok": False, "problems": ["tracker not found"], "path": str(path)}
            rc = 1
            continue
        res = verify_workbook(path, cfg)
        out["results"][region] = res
        if not res["ok"]:
            rc = 1
    emit(out)
    return rc


def _load_manifest(path: str) -> list:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("records", [])
    return data


def cmd_dedupe(args) -> int:
    profiles = load_profiles(args.profiles)
    cfg = dict(region_config(profiles, args.region))
    cfg["region"] = args.region
    tr = tracker_writer.Tracker(Path(args.tracker or cfg["tracker"]), cfg)
    by_url, by_pair = tr.existing_keys()
    cross = build_cross_month_index(profiles, cfg, args.archive_dir)
    records = _load_manifest(args.manifest)
    decisions = []
    for rec in records:
        u = normalize_url(rec.get("url"))
        p = tracker_writer.pair_key(rec.get("company"), rec.get("title"))
        if not u:
            decisions.append({"company": rec.get("company"), "title": rec.get("title"),
                              "decision": "rejected", "reason": "no usable URL"})
            continue
        if u in by_url:
            d, why = "duplicate", "already in canonical workbook"
        elif p.strip("|") and p in by_pair:
            d, why = "duplicate", "company+title already present"
        elif u in cross["url_keys"]:
            d, why = "duplicate-cross-month", "in archived workbook or region ledger"
        else:
            d, why = "new", "eligible for append"
        decisions.append({"company": rec.get("company"), "title": rec.get("title"),
                          "url": tracker_writer.extract_url(rec.get("url")),
                          "decision": d, "reason": why})
    tr.wb.close()
    emit({
        "region": args.region,
        "tracker": str(args.tracker or cfg["tracker"]),
        "counts": {
            "input": len(records),
            "new": sum(1 for d in decisions if d["decision"] == "new"),
            "duplicate": sum(1 for d in decisions if d["decision"].startswith("duplicate")),
            "rejected": sum(1 for d in decisions if d["decision"] == "rejected"),
        },
        "decisions": decisions,
        "explanations": ["duplicate-cross-month covers previous-month workbooks and the region shortlist ledger"],
    })
    return 0


def _write_run_status(args, result: dict) -> str:
    if not result.get("applied"):
        if result.get("error"):
            return "failed"
        return "dry-run" if not args.apply else "no-op"
    return "ok"


def cmd_write(args) -> int:
    profiles = load_profiles(args.profiles)
    records = _load_manifest(args.manifest)
    result = tracker_writer.write_records(
        profiles, args.region, records,
        apply=args.apply,
        backup_dir=args.backup_dir,
        update_existing=args.update_existing,
        extra_archive_dirs=args.archive_dir,
        tracker_override=args.tracker,
    )
    result["mode"] = "apply" if args.apply else "dry-run"
    result["provenance"] = {"manifest": args.manifest, "writer": "career-ops/tracker_writer.py"}
    # Department run-health: counts/status/hashes only — never workbook content.
    verification = result.get("verification") or result.get("verification_of_temp") or {}
    dept_run_health.record_run(
        "tracker-writer",
        region=args.region,
        status=_write_run_status(args, result),
        mode=result["mode"],
        counts={
            "input": (result.get("counts") or {}).get("input"),
            "appended": (result.get("counts") or {}).get("appended"),
            "duplicates": (result.get("counts") or {}).get("duplicates"),
            "rejected": (result.get("counts") or {}).get("rejected"),
            "refreshed": (result.get("counts") or {}).get("refreshed"),
            "data_rows_before": result.get("pre_data_rows"),
            "data_rows_after": result.get("post_data_rows"),
        },
        extra={
            "tracker_filename": Path(result["tracker"]).name,
            "applied": bool(result.get("applied")),
            "verification_ok": bool(verification.get("ok")),
            "problems": len(verification.get("problems") or []),
            "error": result.get("error"),
        },
        state_dir=getattr(args, "state_dir", None),
    )
    emit(result)
    return 0 if result.get("applied") or not args.apply else 1


def cmd_rollover(args) -> int:
    """Monthly Tracker Rollover / archive worker (roster B09)."""
    profiles = load_profiles(args.profiles)
    result = tracker_rollover.rollover(
        profiles, args.region, args.month or tracker_rollover.previous_month(),
        apply=args.apply,
        archive_only=args.archive_only,
        archive_dir=args.archive_dir,
        tracker_override=args.tracker,
        backup_dir=args.backup_dir,
        force=args.force,
        allow_owner_state_removal=args.allow_owner_state_removal,
        state_dir=getattr(args, "state_dir", None),
    )
    result["provenance"] = {"worker": "career-ops/tracker_rollover.py", "roster": "B09"}
    emit(result)
    return 0 if result.get("status") in ("written", "planned", "unchanged", "no_rows") else 1


def cmd_run_health(args) -> int:
    """Deterministic Chief-readable run-health for the Career Ops Excel workers."""
    emit(dept_run_health.summarise(getattr(args, "state_dir", None), getattr(args, "job", None)))
    return 0


def cmd_summary(args) -> int:
    profiles = load_profiles(args.profiles)
    regions = [args.region] if args.region else list(profiles["regions"])
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
           "regions": {}}
    for region in regions:
        cfg = dict(region_config(profiles, region))
        cfg["region"] = region
        path = Path(cfg["tracker"])
        if not path.exists():
            out["regions"][region] = {"available": False}
            continue
        tr = tracker_writer.Tracker(path, cfg)
        rows = tr.data_rows()
        status_idx = tracker_writer.column_index_from_string(cfg["status_columns"]["application_status"]) - 1
        id_cfg = cfg.get("id")
        id_idx = (tracker_writer.column_index_from_string(id_cfg["column"]) - 1) if id_cfg else None
        # Schemas with no id column are keyed by application URL instead.
        url_idx = tracker_writer.column_index_from_string(cfg["dedupe"]["url_column"]) - 1
        ids = tr.ids()
        from collections import Counter
        statuses = Counter(str(r[status_idx]) for r in rows if r[status_idx] not in (None, ""))
        actionable_states = ("to review", "new", "reviewed", "pending")
        actionable = [str(r[id_idx]) if id_idx is not None else str(r[url_idx])
                      for r in rows
                      if str(r[status_idx]).lower() in actionable_states]
        out["regions"][region] = {
            "available": True,
            "display_name": cfg["display_name"],
            "tracker": str(path),
            "sha256": sha256_file(path),
            "data_rows": len(rows),
            "last_id": ids[-1] if ids else None,
            "status_counts": dict(statuses),
            "actionable_ids": actionable[:25],
            "id_column": bool(id_cfg),
            "owner_columns_untouched_by_automation": cfg["owner_columns"],
            "excel_is_source_of_truth": True,
        }
        tr.wb.close()
    emit(out)
    return 0


def cmd_ledger(args) -> int:
    profiles = load_profiles(args.profiles)
    cfg = dict(region_config(profiles, args.region))
    cfg["region"] = args.region
    cross = build_cross_month_index(profiles, cfg, args.archive_dir)
    emit({
        "region": args.region,
        "cross_month_url_keys": len(cross["url_keys"]),
        "sources": cross["sources"],
        "note": "Index built from rotated/previous-month workbooks plus the region shortlist ledger.",
    })
    return 0


def _load_schedules() -> dict:
    p = CAREER_OPS_DIR / "regional_schedules.json"
    if not p.exists():
        return {"regions": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def resolve_lane(region: str, profiles: dict) -> dict:
    """Resolve the Career Ops lane (portals/pipeline/scan-history) for a region.

    Refuses a region whose lane config is absent instead of silently scanning the
    UK portals.yml under another region's label — that would create wrong-region
    findings, which is exactly the conflicting state this integration must avoid.
    """
    schedules = _load_schedules()
    root = Path(profiles["career_ops_root"])
    spec = schedules.get("regions", {}).get(region, {})
    env = spec.get("career_ops_env", {})
    missing = [str(root / rel) for rel in env.values() if not (root / rel).exists()]
    return {"env": env, "missing": missing, "spec": spec, "ready": not missing}


def cmd_scan(args) -> int:
    """Bounded wrapper around the existing Career Ops scanner.

    Chief does not reimplement scanning; it invokes the maintained Career Ops
    scanner with the region's portals/pipeline/history paths and captures a
    run-health record. Scans are always --dry-run here: this command never
    writes a tracker and never submits anything.
    """
    profiles = load_profiles(args.profiles)
    cfg = dict(region_config(profiles, args.region))
    cfg["region"] = args.region
    root = Path(profiles["career_ops_root"])
    if not root.exists():
        emit({"ok": False, "reason": "career_ops_root not found", "path": str(root)})
        return 1
    scan = root / "scan.mjs"
    if not scan.exists():
        emit({"ok": False, "reason": "scan.mjs not found", "path": str(scan)})
        return 1

    lane = resolve_lane(args.region, profiles)
    started = dt.datetime.now(dt.timezone.utc)
    if not lane["ready"] and not args.force:
        record = {
            "region": args.region,
            "ok": False,
            "refused": True,
            "reason": "regional lane config missing; refusing to scan the UK lane under this region",
            "missing": lane["missing"],
            "started_at": started.replace(microsecond=0).isoformat(),
            "dry_run": True,
        }
        if args.record:
            outdir = Path(args.record)
            outdir.mkdir(parents=True, exist_ok=True)
            fname = outdir / f"scan-{args.region}-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
            fname.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            record["recorded_to"] = str(fname)
        emit(record)
        return 2

    cmd = ["node", "scan.mjs", "--dry-run", "--quiet"]
    if args.company:
        cmd += ["--company", args.company]
    env = dict(os.environ)
    env.update(lane["env"])
    # The scanner prints UTF-8 box-drawing/arrow glyphs. In a Task Scheduler
    # context the default locale encoding is cp1252, which raises
    # UnicodeDecodeError in the reader thread and silently empties stdout — so the
    # encoding is pinned here rather than inherited from the locale.
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=args.timeout, shell=False, env=env)
    finished = dt.datetime.now(dt.timezone.utc)
    record = {
        "region": args.region,
        "command": cmd,
        "cwd": str(root),
        "lane_env": lane["env"],
        "started_at": started.replace(microsecond=0).isoformat(),
        "finished_at": finished.replace(microsecond=0).isoformat(),
        "duration_s": round((finished - started).total_seconds(), 1),
        "exit_code": proc.returncode,
        "dry_run": True,
        "ok": proc.returncode == 0,
        "stdout_capture_ok": bool((proc.stdout or "").strip()),
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }
    if proc.returncode == 0 and not record["stdout_capture_ok"]:
        record["warning"] = ("scan exited 0 but produced no capturable stdout; treat the run as "
                             "unverified rather than successful")
    if args.record:
        outdir = Path(args.record)
        outdir.mkdir(parents=True, exist_ok=True)
        fname = outdir / f"scan-{args.region}-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
        fname.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        record["recorded_to"] = str(fname)
    emit(record)
    return 0 if proc.returncode == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chief <-> Career Ops deterministic interface")
    ap.add_argument("--profiles", default=None, help="path to regional_profiles.json")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inventory"); p.set_defaults(fn=cmd_inventory)

    p = sub.add_parser("verify")
    p.add_argument("--region"); p.add_argument("--tracker")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("dedupe")
    p.add_argument("--region", required=True); p.add_argument("--manifest", required=True)
    p.add_argument("--tracker"); p.add_argument("--archive-dir", action="append")
    p.set_defaults(fn=cmd_dedupe)

    p = sub.add_parser("write")
    p.add_argument("--region", required=True); p.add_argument("--manifest", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--update-existing", action="store_true")
    p.add_argument("--tracker"); p.add_argument("--backup-dir")
    p.add_argument("--archive-dir", action="append")
    p.add_argument("--state-dir", help="run-health directory (default: runtime/career-ops/run-health)")
    p.set_defaults(fn=cmd_write)

    p = sub.add_parser("rollover")
    p.add_argument("--region", required=True)
    p.add_argument("--month", help="YYYY-MM (default: previous calendar month)")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--archive-only", action="store_true",
                   help="write the archive but leave the canonical workbook untouched")
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-owner-state-removal", action="store_true")
    p.add_argument("--tracker"); p.add_argument("--archive-dir")
    p.add_argument("--backup-dir")
    p.add_argument("--state-dir")
    p.set_defaults(fn=cmd_rollover)

    p = sub.add_parser("run-health")
    p.add_argument("--job", choices=sorted(dept_run_health.JOBS))
    p.add_argument("--state-dir")
    p.set_defaults(fn=cmd_run_health)

    p = sub.add_parser("summary")
    p.add_argument("--region")
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("ledger")
    p.add_argument("--region", required=True); p.add_argument("--archive-dir", action="append")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("scan")
    p.add_argument("--region", required=True)
    p.add_argument("--company")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--record")
    p.add_argument("--force", action="store_true",
                   help="run even when the regional lane config is missing (creates wrong-region data; not for scheduled use)")
    p.set_defaults(fn=cmd_scan)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
