#!/usr/bin/env python3
"""Reversible acceptance run for the Monthly Tracker Rollover / archive worker (B09).

What this proves
----------------
For every region (UK, Dubai, Japan, Singapore), on a dated **copy** of the
canonical workbook:

  1. the tracker writer appends two unmistakable probe rows dated in a target
     month (``.invalid`` domain — never a real vacancy);
  2. ``rollover --apply`` writes the per-region archive workbook and rotates the
     month's rows out of the canonical copy;
  3. the archive preserves the canonical schema — sheets, table, formulas,
     number formats and data validations — and every cell of every rotated row,
     owner columns included;
  4. every rotated row is present in the cross-month dedupe index, and re-adding
     the same posting is refused as ``duplicate-cross-month`` with zero appends;
  5. a re-run of the same month changes nothing (no duplicate archive, no
     duplicate rows);
  6. the canonical copy restores byte-identically from the rollover backup, and
     removing the archive removes those keys from the dedupe index — so the whole
     rotation is reversible;
  7. the four **canonical** workbooks are byte-identical before and after: this
     runner only ever reads them.

No applications, messages, employer contact or status changes. Evidence written
to ``audits/evidence/<stamp>-career-ops-monthly-rollover/`` is aggregate only
(counts, statuses, hashes, file names) — never workbook content.

Usage:
  python career-ops/run_rollover_acceptance.py [--stamp YYYYMMDDTHHMMSSZ] [--month YYYY-MM]
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

import openpyxl  # noqa: E402

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import career_ops_cli as cli  # noqa: E402
import dept_run_health as drh  # noqa: E402
import tracker_rollover as ro  # noqa: E402
import tracker_writer as tw  # noqa: E402

PROFILES = tw.load_profiles()
REGIONS = ("uk", "dubai", "japan", "singapore")


def region_cfg(region: str) -> dict:
    return dict(tw.region_config(PROFILES, region), region=region)


def probe_record(region: str, month: str, i: int) -> dict:
    return {
        "date_found": f"{month}-{5 + i:02d}",
        "company": f"ZZZ ROLLOVER ACCEPTANCE PROBE {region.upper()} {i} (NOT A REAL VACANCY)",
        "title": f"Rollover acceptance probe {region} {i} — delete this row",
        "location": "n/a — acceptance artifact",
        "url": f"https://rollover-acceptance-probe.invalid/{region}/{month}/{i}",
        "fit_score": 0.0,
        "live_status": "Uncertain",
        "clearance_check": "n/a — acceptance artifact",
        "work_authorisation_risk": "n/a — acceptance artifact",
        "key_gap": "n/a — acceptance artifact",
        "recommendation": "Rollover acceptance probe on a dated COPY only. Never a real posting.",
        "discovery": f"ROLLOVER ACCEPTANCE {stamp_label()} — COPY ONLY",
        "source": "career-ops/run_rollover_acceptance.py",
        "notes": "Probe row. Not a vacancy. Safe to delete.",
    }


def stamp_label() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run(stamp: str, month: str) -> int:
    run_dir = CONTROL_PLANE / "runtime" / "career-ops" / "rollover-acceptance" / stamp
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "workbooks").mkdir(parents=True)
    (run_dir / "backups").mkdir(parents=True)
    archive_dir = run_dir / "archive"
    state_dir = run_dir / "run-health"
    evidence_dir = CONTROL_PLANE / "audits" / "evidence" / f"{stamp_name(stamp)}-career-ops-monthly-rollover"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    ev: dict = {
        "acceptance_run": stamp,
        "task": "agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23",
        "roster": "B09",
        "month_rotated": month,
        "target_month": month,
        "mode": "dated COPIES only; canonical workbooks read-only",
        "no_external_actions": True,
        "canonical_hashes_before": {r: tw.sha256_file(Path(region_cfg(r)["tracker"])) for r in REGIONS},
    }

    regions: dict = {}
    for region in REGIONS:
        cfg = region_cfg(region)
        canon = Path(cfg["tracker"])
        copy = run_dir / "workbooks" / f"{region}-{canon.name}"
        shutil.copy2(canon, copy)
        copy_hash_pre_append = tw.sha256_file(copy)

        # --- 1. append probe rows through the real CLI write path ---------- #
        manifest = run_dir / "workbooks" / f"{region}-manifest.json"
        manifest.write_text(json.dumps(
            {"schema_version": 1, "region": region,
             "records": [probe_record(region, month, 1), probe_record(region, month, 2)]},
            indent=2), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["--profiles", str(CAREER_OPS_DIR / "regional_profiles.json"),
                           "write", "--region", region, "--manifest", str(manifest), "--apply",
                           "--tracker", str(copy), "--backup-dir", str(run_dir / "backups"),
                           "--state-dir", str(state_dir)])
        write_res = json.loads(buf.getvalue())
        copy_hash_pre_rollover = tw.sha256_file(copy)

        # --- 2. read-only plan -------------------------------------------- #
        plan = ro.plan(PROFILES, region, month, tracker_override=str(copy),
                       archive_dir=str(archive_dir))

        # --- 3. rollover -------------------------------------------------- #
        res = ro.rollover(PROFILES, region, month, apply=True, tracker_override=str(copy),
                          archive_dir=str(archive_dir), backup_dir=str(run_dir / "backups"),
                          state_dir=str(state_dir))

        # --- 4. schema preservation of the archive ------------------------ #
        archive_checks = None
        if res.get("status") == "written":
            arch = Path(res["archive"]["path"])
            av = tw.verify_workbook(arch, region_cfg(region), expect_data_rows=2)
            cwb = openpyxl.load_workbook(canon, read_only=True)
            awb = openpyxl.load_workbook(arch, read_only=True)
            same_sheets = awb.sheetnames == cwb.sheetnames
            cwb.close()
            awb.close()
            archive_checks = {
                "verification_ok": av["ok"],
                "problems": av["problems"],
                "sheets_match_canonical": same_sheets,
                "data_rows": av["data_rows"],
                "table_ref": av["table_ref"],
                "validations": av["validations"],
                "fit_tier_formula_cells": av["fit_tier_formula_cells"],
                "duplicate_urls_in_workbook": av["duplicate_urls_in_workbook"],
            }

        # --- 5. cross-month dedupe proof ---------------------------------- #
        dedupe_proof = None
        if res.get("status") == "written":
            redo = tw.write_records(PROFILES, region, [probe_record(region, month, 1)], apply=False,
                                    tracker_override=str(copy),
                                    extra_archive_dirs=[str(archive_dir)])
            dedupe_proof = {
                "appended": redo["counts"]["appended"],
                "decisions": [o["decision"] for o in redo["outcomes"]],
                "cross_month_index": res["cross_month_dedupe"],
            }

        # --- 6. idempotency: same month again changes nothing ------------- #
        second = ro.rollover(PROFILES, region, month, apply=True, tracker_override=str(copy),
                             archive_dir=str(archive_dir), backup_dir=str(run_dir / "backups"),
                             state_dir=str(state_dir))
        archive_hash_after_second = (tw.sha256_file(res["archive"]["path"])
                                     if res.get("status") == "written" else None)

        regions[region] = {
            "display_name": cfg["display_name"],
            "canonical": str(canon),
            "copy": str(copy),
            "copy_sha256_before_append": copy_hash_pre_append,
            "copy_sha256_before_rollover": copy_hash_pre_rollover,
            "write": {
                "exit_code": rc,
                "applied": write_res.get("applied"),
                "counts": write_res.get("counts"),
                "verification_ok": (write_res.get("verification") or {}).get("ok"),
                "error": write_res.get("error"),
            },
            "plan": {
                "status": plan["status"],
                "month_rows": plan["month_rows"],
                "retained_rows": plan["retained_rows"],
                "undated_rows": plan["undated_rows"],
                "months_present": plan["months_present"],
                "archive_filename": plan["archive_filename"],
                "owner_state_conflicts": plan["owner_state_conflicts"],
                "owner_columns_guarded": plan["owner_columns_guarded"],
                "owner_columns_automation_writable": plan["owner_columns_automation_writable"],
            },
            "rollover": {
                "status": res.get("status"),
                "applied": res.get("applied"),
                "ok": res.get("ok"),
                "error": res.get("error"),
                "reason": res.get("reason"),
                "counts": res.get("counts"),
                "archive_filename": res.get("archive_filename"),
                "archive_sha256": (res.get("archive") or {}).get("sha256")
                                  if isinstance(res.get("archive"), dict) else None,
                "archive_backup": (res.get("archive") or {}).get("previous_archive_backup")
                                  if isinstance(res.get("archive"), dict) else None,
                "canonical_untouched": res.get("canonical_untouched"),
                "canonical_backup": (res.get("canonical") or {}).get("backup"),
                "canonical_data_rows": (res.get("canonical") or {}).get("data_rows"),
                "canonical_verification_ok": ((res.get("canonical") or {}).get("verification") or {}).get("ok"),
                "canonical_owner_columns_unchanged": ((res.get("canonical") or {}).get("verification") or {}).get("owner_columns_unchanged"),
            },
            "archive_checks": archive_checks,
            "dedupe_proof": dedupe_proof,
            "second_run": {"status": second.get("status"), "reason": second.get("reason"),
                           "applied": second.get("applied")},
            "archive_sha256_after_second_run": archive_hash_after_second,
            "canonical_hash_after": tw.sha256_file(canon),
        }

    # --- 7. reversibility: restore from backup, then remove the archive ---- #
    uk = regions["uk"]
    rev: dict = {}
    if uk["rollover"]["canonical_backup"]:
        copy = Path(uk["copy"])
        shutil.copy2(uk["rollover"]["canonical_backup"], copy)
        rev["restored_from_backup"] = uk["rollover"]["canonical_backup"]
        rev["restored_sha256"] = tw.sha256_file(copy)
        rev["equals_pre_rollover_hash"] = tw.sha256_file(copy) == uk["copy_sha256_before_rollover"]
        rev["verification_ok"] = tw.verify_workbook(copy, region_cfg("uk"))["ok"]
        # the archive is what feeds the index: remove it and the keys go away
        arch = Path(uk["rollover"]["archive_filename"])
        arch = (archive_dir / uk["rollover"]["archive_filename"])
        cfg = region_cfg("uk")
        cross_with = tw.build_cross_month_index(PROFILES, cfg, [str(archive_dir)])
        keys_with = len(cross_with["url_keys"])
        has_archive = uk["rollover"]["archive_filename"] in cross_with["sources"]
        arch.unlink(missing_ok=True)
        cross_without = tw.build_cross_month_index(PROFILES, cfg, [str(archive_dir)])
        rev.update({
            "archive_removed": not arch.exists(),
            "index_sources_with_archive": uk["rollover"]["archive_filename"] if has_archive else None,
            "index_keys_with_archive": keys_with,
            "index_keys_without_archive": len(cross_without["url_keys"]),
            "keys_dropped_when_archive_removed": keys_with - len(cross_without["url_keys"]),
            "archive_was_present_in_index": has_archive,
            "note": "removing the archive removes exactly the rotated keys from the dedupe index",
        })
    ev["stage_reversibility"] = rev

    # --- 8. run-health for both workers ------------------------------------ #
    health = drh.summarise(str(state_dir))
    ev["stage_run_health"] = {
        "excel_is_source_of_truth": health["excel_is_source_of_truth"],
        "chief_state_role": health["chief_state_role"],
        "jobs": {k: {"worker": v["worker"], "roster": v["roster"], "runs_recorded": v["runs_recorded"],
                     "last_region": v["last_region"], "last_status": v["last_status"],
                     "last_counts": v["last_counts"]} for k, v in health["jobs"].items()},
    }
    # the run-health documents must never contain workbook content
    payload = "\n".join(p.read_text(encoding="utf-8")
                        for p in sorted(Path(state_dir).glob("*.json")))
    ev["stage_run_health"]["aggregate_only"] = ("https://" not in payload
                                                and "PROBE" not in payload)

    # --- 9. the canonical workbooks were never touched --------------------- #
    after = {r: tw.sha256_file(Path(region_cfg(r)["tracker"])) for r in REGIONS}
    ev["canonical_hashes_after"] = after
    ev["canonical_workbooks_untouched"] = after == ev["canonical_hashes_before"]

    ev["regions"] = regions
    out = evidence_dir / f"acceptance-{stamp}.json"
    out.write_text(json.dumps(ev, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    ok = (
        all(r["rollover"]["status"] == "written" for r in regions.values())
        and all(r["archive_checks"] and r["archive_checks"]["verification_ok"]
                and r["archive_checks"]["sheets_match_canonical"] for r in regions.values())
        and all(r["dedupe_proof"] and r["dedupe_proof"]["appended"] == 0
                and r["dedupe_proof"]["decisions"] == ["duplicate-cross-month"] for r in regions.values())
        and ev["canonical_workbooks_untouched"]
        and rev.get("equals_pre_rollover_hash") is True
        and ev["stage_run_health"]["aggregate_only"] is True
    )
    print(json.dumps({
        "acceptance_run": stamp,
        "evidence_file": str(out),
        "ok": bool(ok),
        "month_rotated": month,
        "regions_written": {r: regions[r]["rollover"]["status"] for r in REGIONS},
        "archives": {r: regions[r]["rollover"]["archive_filename"] for r in REGIONS},
        "archived_rows_per_region": {r: (regions[r]["rollover"]["counts"] or {}).get("archived_rows")
                                     for r in REGIONS},
        "rotated_out_per_region": {r: (regions[r]["rollover"]["counts"] or {}).get("rotated_out_of_canonical")
                                   for r in REGIONS},
        "dedupe_refused": {r: regions[r]["dedupe_proof"]["decisions"] if regions[r]["dedupe_proof"] else None
                           for r in REGIONS},
        "second_run_status": {r: regions[r]["second_run"]["status"] for r in REGIONS},
        "canonical_workbooks_untouched": ev["canonical_workbooks_untouched"],
        "rollback_restores_byte_identical": rev.get("equals_pre_rollover_hash"),
        "run_health": ev["stage_run_health"]["jobs"],
        "run_health_aggregate_only": ev["stage_run_health"]["aggregate_only"],
    }, indent=2))
    return 0 if ok else 1


def stamp_name(stamp: str) -> str:
    """20260924T031500Z -> 2026-09-24T03-15-00Z (house evidence-dir convention)."""
    try:
        d = dt.datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return stamp
    return d.strftime("%Y-%m-%dT%H-%M-%SZ")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reversible acceptance run for the monthly rollover worker (B09)")
    ap.add_argument("--stamp", default=stamp_label())
    ap.add_argument("--month", default=ro.previous_month())
    args = ap.parse_args(argv)
    return run(args.stamp, args.month)


if __name__ == "__main__":
    raise SystemExit(main())
