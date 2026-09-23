#!/usr/bin/env python3
"""End-to-end acceptance: scan -> eligible leads -> dedupe -> workbook write -> Chief summary.

Truthfulness rules baked into this runner:

  * It never writes a canonical tracker. Every workbook write happens against a
    dated COPY under runtime/career-ops/acceptance/<stamp>/.
  * The "eligibility" step is an explicit DETERMINISTIC PRE-SCREEN
    (score threshold + title policy + location policy). It is not a claim that a
    vacancy is live: live verification is a separate, external step and is
    reported as not-performed here.
  * No applications, emails, messages or employer contact of any kind.

Usage:
  python career-ops/run_acceptance.py [--stamp YYYYMMDDTHHMMSSZ]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import tracker_writer as tw  # noqa: E402
import career_ops_cli as cli  # noqa: E402

PROFILES = tw.load_profiles()

# Deterministic pre-screen policy (documented, not a live-availability claim).
MIN_SCORE = 3.5
UK_SIGNALS = ("united kingdom", "uk", "london", "england", "scotland", "wales",
              "northern ireland", "remote")
NEGATIVE_TITLE_TOKENS = ("senior", "principal", "lead ", "manager", "director",
                         "head of", "vice president", "vp ", "staff security")

ENTRY_RE = re.compile(r"^- \[ \] (\S+)\s*\|([^\n]*)$")
SCORE_RE = re.compile(r"score:\s*([0-9.]+)")


def _int_after(text: str, label: str):
    m = re.search(re.escape(label) + r"\s*([0-9]+)", text)
    return int(m.group(1)) if m else None


def parse_pipeline(path: Path) -> list[dict]:
    """Parse the existing Career Ops pipeline.md (Pendientes entries)."""
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ENTRY_RE.match(line.strip())
        if not m:
            continue
        url = m.group(1).strip()
        rest = [p.strip() for p in m.group(2).split("|")]
        company = rest[0] if len(rest) > 0 else ""
        title = rest[1] if len(rest) > 1 else ""
        location = rest[2] if len(rest) > 2 else ""
        tail = " | ".join(rest[3:]) if len(rest) > 3 else ""
        sm = SCORE_RE.search(tail)
        out.append({
            "url": url,
            "company": company,
            "title": title,
            "location": location,
            "score": float(sm.group(1)) if sm else None,
            "tail": tail,
            "raw": line.strip(),
        })
    return out


def pre_screen(entries: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Deterministically pre-screen pipeline leads.

    Returns (scored_eligible, unscored_eligible, dropped). Unscored leads that
    satisfy the title and location policy are kept in their own bucket because
    they are genuine new candidates from the scanner that simply have not been
    evaluated yet — dropping them would hide real discovery output.
    """
    scored, unscored, dropped = [], [], []
    for e in entries:
        hard_reasons = []
        tl = e["title"].casefold()
        for tok in NEGATIVE_TITLE_TOKENS:
            if tok in tl:
                hard_reasons.append(f"title policy excludes '{tok.strip()}'")
                break
        loc = (e["location"] or "").casefold()
        if not any(sig in loc for sig in UK_SIGNALS):
            hard_reasons.append(f"location '{e['location']}' not in the UK allow-list")
        if hard_reasons:
            dropped.append({**e, "reasons": hard_reasons})
            continue
        if e["score"] is None:
            unscored.append({**e, "reasons": ["no published score yet; needs evaluation"]})
        elif e["score"] < MIN_SCORE:
            dropped.append({**e, "reasons": [f"score {e['score']} below {MIN_SCORE}"]})
        else:
            scored.append(e)
    return scored, unscored, dropped


def to_record(e: dict, today: str) -> dict:
    return {
        "date_found": today,
        "company": e["company"],
        "title": e["title"],
        "location": e["location"],
        "url": e["url"],
        "fit_score": e["score"],
        "live_status": "Uncertain",
        "clearance_check": "Pass — no clearance stated",
        "work_authorisation_risk": "Not verified in this run",
        "key_gap": "Live vacancy not re-verified in this acceptance run",
        "recommendation": ("Carried from the existing Career Ops pipeline; pre-screened by score, "
                           "title policy and UK location. Live verification still outstanding."),
        "discovery": f"ACCEPTANCE RUN {today} (pre-screen only; live verification outstanding)",
        "source": "Career Ops data/pipeline.md",
        "notes": "Acceptance-run record created on a TEST COPY; no application created.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp")
    args = ap.parse_args(argv)

    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    today = dt.date.today().isoformat()
    run_dir = CONTROL_PLANE / "runtime" / "career-ops" / "acceptance" / stamp
    (run_dir / "backups").mkdir(parents=True, exist_ok=True)
    evidence_dir = CAREER_OPS_DIR / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    ev: dict = {
        "acceptance_run": stamp,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "canonical_trackers_touched": False,
        "applications_submitted": 0,
        "external_messages_sent": 0,
        "note": "Pre-screen only. Live vacancy verification not performed in this run.",
    }

    # ---------------- stage 1: scan evidence --------------------------- #
    scan_runs = CONTROL_PLANE / "runtime" / "career-ops" / "scan-runs"
    latest = None
    if scan_runs.exists():
        cands = sorted(scan_runs.glob("scan-*.json"), key=lambda p: p.stat().st_mtime)
        uk_ok = [p for p in cands if p.name.startswith("scan-uk-")]
        latest = (uk_ok or cands)[-1] if cands else None
    if latest:
        data = json.loads(latest.read_text(encoding="utf-8"))
        ev["stage_1_scan"] = {
            "run_health_file": str(latest),
            "region": data.get("region"),
            "dry_run": data.get("dry_run"),
            "exit_code": data.get("exit_code"),
            "ok": data.get("ok"),
            "duration_s": data.get("duration_s"),
            "stdout_tail_last_lines": (data.get("stdout_tail") or "").strip().splitlines()[-25:],
        }
        scanned = None
        tail = data.get("stdout_tail") or ""
        for pat in (r"Total jobs found:\s*([0-9]+)", r"Jobs found:\s*([0-9]+)"):
            m = re.search(pat, tail)
            if m:
                scanned = int(m.group(1))
                break
        ev["stage_1_scan"]["jobs_reported_scanned"] = scanned
        ev["stage_1_scan"]["new_offers_added_reported"] = _int_after(tail, "New offers added:")
        ev["stage_1_scan"]["duplicates_reported"] = _int_after(tail, "Duplicates:")
        ev["stage_1_scan"]["errors_reported"] = _int_after(tail, "Errors:")
    else:
        ev["stage_1_scan"] = {"status": "no scan run-health file found; run "
                                        "career_ops_cli.py scan --region uk --record <dir> first"}

    # ---------------- stage 2: deterministic pre-screen ---------------- #
    pipeline = Path(PROFILES["career_ops_root"]) / "data" / "pipeline.md"
    entries = parse_pipeline(pipeline)
    scored, unscored, dropped = pre_screen(entries)
    records = [to_record(k, today) for k in scored] + [
        {**to_record(k, today),
         "fit_score": None,
         "live_status": "Uncertain",
         "recommendation": ("Fresh Career Ops pipeline lead; not yet evaluated. Pre-screened only by "
                            "title and location policy. Evaluation and live verification outstanding."),
         "key_gap": "Not yet evaluated or live-verified"}
        for k in unscored
    ]
    ev["stage_2_eligible_pre_screen"] = {
        "source": str(pipeline),
        "pipeline_entries_parsed": len(entries),
        "scored_eligible": len(scored),
        "unscored_eligible_needs_evaluation": len(unscored),
        "dropped": len(dropped),
        "records_built": len(records),
        "policy": {"min_score": MIN_SCORE, "negative_title_tokens": list(NEGATIVE_TITLE_TOKENS),
                   "uk_location_signals": list(UK_SIGNALS)},
        "scored_sample": [{"company": k["company"], "title": k["title"], "score": k["score"]} for k in scored[:4]],
        "unscored_sample": [{"company": k["company"], "title": k["title"]} for k in unscored[:6]],
        "dropped_sample": [{"company": d["company"], "reasons": d["reasons"]} for d in dropped[:4]],
        "live_verification_performed": False,
    }

    # ---------------- stage 3: dedupe on the canonical workbook -------- #
    uk_cfg = dict(tw.region_config(PROFILES, "uk"))
    uk_cfg["region"] = "uk"
    canonical = Path(uk_cfg["tracker"])
    before_hash = tw.sha256_file(canonical)
    dedupe_probe = tw.write_records(PROFILES, "uk", records, apply=False,
                                    tracker_override=str(canonical))
    ev["stage_3_dedupe"] = {
        "canonical_tracker": str(canonical),
        "canonical_sha256_before": before_hash,
        "counts": dedupe_probe["counts"],
        "cross_month_index_sources": dedupe_probe["cross_month_index"]["sources"],
        "cross_month_index_keys": dedupe_probe["cross_month_index"]["keys"],
        "decisions_sample": dedupe_probe["outcomes"][:8],
    }
    assert tw.sha256_file(canonical) == before_hash, "dry-run must not touch the canonical workbook"

    # ---------------- stage 4: reversible write on a TEST COPY -------- #
    test_copy = run_dir / canonical.name
    shutil.copy2(canonical, test_copy)
    copy_hash_before = tw.sha256_file(test_copy)

    # Append probes exist purely to exercise the append path on the test copy.
    # They are unmistakably labelled and use a reserved .invalid domain so they
    # can never be confused with a real vacancy or a real application.
    probe_records = [
        {
            "date_found": today,
            "company": "ZZZ ACCEPTANCE PROBE (NOT A REAL VACANCY)",
            "title": f"Write-path acceptance probe {i} — delete this row",
            "location": "n/a — acceptance artifact",
            "url": f"https://acceptance-probe.invalid/uk/{stamp}/{i}",
            "fit_score": 0.0,
            "live_status": "Uncertain",
            "clearance_check": "n/a — acceptance artifact",
            "work_authorisation_risk": "n/a — acceptance artifact",
            "key_gap": "n/a — acceptance artifact",
            "recommendation": "Acceptance probe on a TEST COPY only. Never a real posting; never applied to.",
            "discovery": f"ACCEPTANCE RUN {stamp} — TEST COPY ONLY",
            "source": "career-ops/run_acceptance.py probe",
            "notes": "Probe row: proves the append path. Not a vacancy. Safe to delete.",
        }
        for i in (1, 2)
    ]
    all_records = records + probe_records
    write_res = tw.write_records(PROFILES, "uk", all_records, apply=True,
                                 tracker_override=str(test_copy),
                                 backup_dir=str(run_dir / "backups"))
    ev["stage_4_workbook_write_test_copy"] = {
        "test_copy": str(test_copy),
        "test_copy_sha256_before": copy_hash_before,
        "test_copy_sha256_after": tw.sha256_file(test_copy),
        "real_pipeline_records": len(records),
        "acceptance_probe_records": len(probe_records),
        "backup": write_res.get("backup"),
        "backup_exists": bool(write_res.get("backup") and Path(write_res["backup"]).exists()),
        "applied": write_res.get("applied"),
        "counts": write_res.get("counts"),
        "planned_ids": write_res.get("planned_rows"),
        "probe_ids_written": [i for i in (write_res.get("planned_rows") or [])],
        "verification": write_res.get("verification"),
        "error": write_res.get("error"),
        "canonical_untouched": tw.sha256_file(canonical) == before_hash,
        "note": ("Probe rows are labelled 'NOT A REAL VACANCY' and use the reserved .invalid domain; "
                 "they exist only in this test copy."),
    }

    # ---------------- stage 5: Chief-readable summary ------------------ #
    sum_args = argparse.Namespace(region=None, profiles=None)
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_summary(sum_args)
    summary = json.loads(buf.getvalue())
    ev["stage_5_chief_summary"] = {"exit_code": rc, "regions": summary["regions"]}

    # ---------------- stage 6: rollback proof -------------------------- #
    backup = write_res.get("backup")
    if backup:
        shutil.copy2(backup, test_copy)
        ev["stage_6_rollback"] = {
            "restored_from": backup,
            "restored_sha256": tw.sha256_file(test_copy),
            "equals_pre_write_hash": tw.sha256_file(test_copy) == copy_hash_before,
        }

    # ---------------- stage 7: cross-month dedupe on real ledgers ------ #
    regional = {}
    for region in ("dubai", "japan", "singapore"):
        cfg = dict(tw.region_config(PROFILES, region))
        cfg["region"] = region
        cross = tw.build_cross_month_index(PROFILES, cfg)
        tr = tw.Tracker(Path(cfg["tracker"]), cfg)
        in_book = {tw.normalize_url(r[tw.column_index_from_string(cfg["dedupe"]["url_column"]) - 1])
                   for r in tr.data_rows()}
        tr.wb.close()
        regional[region] = {
            "tracker": cfg["tracker"],
            "cross_month_keys": len(cross["url_keys"]),
            "keys_in_workbook": len(in_book),
            "keys_from_ledger_or_archive_only": len(cross["url_keys"] - in_book),
            "sources": cross["sources"],
            "lane_status": cli.resolve_lane(region, PROFILES)["ready"],
            "lane_missing": cli.resolve_lane(region, PROFILES)["missing"],
        }
    ev["stage_7_regional_cross_month_dedupe"] = regional

    ev["final_canonical_hashes"] = {
        region: tw.sha256_file(Path(cfg["tracker"]))
        for region, cfg in PROFILES["regions"].items()
    }

    out = evidence_dir / f"acceptance-{stamp}.json"
    out.write_text(json.dumps(ev, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    ok = bool(ev["stage_4_workbook_write_test_copy"].get("applied")) and \
        ev["stage_4_workbook_write_test_copy"]["canonical_untouched"] and \
        bool(ev.get("stage_6_rollback", {}).get("equals_pre_write_hash"))
    print(json.dumps({
        "acceptance_run": stamp,
        "evidence_file": str(out),
        "ok": ok,
        "appended": ev["stage_4_workbook_write_test_copy"]["counts"]["appended"],
        "duplicates": ev["stage_4_workbook_write_test_copy"]["counts"]["duplicates"],
        "canonical_untouched": ev["stage_4_workbook_write_test_copy"]["canonical_untouched"],
        "rollback_verified": ev.get("stage_6_rollback", {}).get("equals_pre_write_hash"),
        "scan_ok": ev["stage_1_scan"].get("ok"),
        "scan_jobs_reported": ev["stage_1_scan"].get("jobs_reported_scanned"),
        "eligible_scored": ev["stage_2_eligible_pre_screen"]["scored_eligible"],
        "eligible_unscored": ev["stage_2_eligible_pre_screen"]["unscored_eligible_needs_evaluation"],
        "dropped_by_policy": ev["stage_2_eligible_pre_screen"]["dropped"],
    }, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
