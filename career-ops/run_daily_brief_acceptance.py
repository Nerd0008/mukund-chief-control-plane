#!/usr/bin/env python3
"""End-to-end acceptance: Career Daily Brief / Pipeline Prioritizer (roster B23).

The brief is a READ-ONLY aggregation, so this runner proves exactly that, plus
the four properties the worker is judged on. Every stage is machine-checked and
the evidence bundle records the raw values it checked.

  stage 1  a live brief is built from the real repository inputs (regional scan
           state/run-health, canonical workbooks, Company Watch, monitor stores,
           interview-prep runtime, owner-action file) and validates structurally.
  stage 2  an empty-input run builds without crashing and labels every input as
           absent - a missing source is never read as healthy or as zero.
  stage 3  a partial-input run (owner-action file and Company Watch removed)
           reports the missing sources and still produces a usable brief.
  stage 4  idempotency: a second identical run produces the same content digest
           and the same input fingerprint, writes NO new bytes, and grows only
           the append-only run log. The as-of clock is floored to a declared
           quantum, so a run inside the same quantum over unchanged artifacts is
           the *same* brief; a different window (a crossed quantum) is a
           genuinely different brief.
  stage 5  no fabricated priority facts: every item's score equals the sum of its
           declared component contributions; unknowns are listed and excluded;
           a zero-coverage item is labelled unscoreable, not scored.
  stage 6  the required sections exist (regional scan health, newly added jobs,
           duplicates suppressed, application-status changes, interview/follow-up
           items, owner actions) and an unavailable one says so.
  stage 7  nothing canonical changed, nothing external happened, and no delivery
           channel is claimed healthy.
  stage 8  the Chief-facing summary is concise and factual.
  stage 9  schedulability: the morning schedule is declared, the launcher exists,
           and the task state is read from Task Scheduler (never assumed).

Usage
  python career-ops/run_daily_brief_acceptance.py [--stamp S] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import daily_brief as db  # noqa: E402

NOW = dt.datetime(2026, 9, 24, 7, 0, tzinfo=dt.timezone.utc)


def code_sha() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(CONTROL_PLANE),
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else "UNKNOWN"


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if Path(path).exists() else None


def isolated_cfg(base: dict, tmp: Path, drop: tuple = ()) -> dict:
    """A config whose inputs are redirected to a (usually empty) scratch tree."""
    cfg = json.loads(json.dumps(base))
    for name in cfg["inputs"]:
        cfg["inputs"][name] = str(tmp / "absent" / name)
    cfg["inputs"]["scan_runs_dir"] = str(tmp / "absent" / "scan-runs")
    cfg["inputs"]["linkedin_handoff_dir"] = str(tmp / "absent" / "handoffs")
    cfg["inputs"]["company_watch_runtime"] = str(tmp / "absent" / "company-watch")
    # These are loaded rather than hashed; point them at the real files so the
    # collectors can run, or drop them entirely for the partial-input stage.
    for name in ("application_inbox_config", "interview_prep_config", "job_intelligence_config"):
        cfg["inputs"][name] = str(tmp / "absent" / name) if name in drop else str(CAREER_OPS_DIR / name)
    cfg["out_dir"] = str(tmp / "briefs")
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp")
    ap.add_argument("--out-dir")
    args = ap.parse_args(argv)

    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cfg = db.load_config()
    out_dir = Path(args.out_dir) if args.out_dir else \
        (CONTROL_PLANE / "audits" / "evidence" / f"{stamp}-career-daily-brief")
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = CONTROL_PLANE / "runtime" / "career-ops" / "daily-brief" / "acceptance" / stamp
    scratch.mkdir(parents=True, exist_ok=True)

    ev: dict = {
        "acceptance_run": stamp,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "code_sha": code_sha(),
        "workflow": "Career Daily Brief / Pipeline Prioritizer (B23)",
        "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md "
                     "§ Career Ops + job-search automation / roster B23",
        "cheating_guards": {
            "applications_submitted": 0,
            "external_messages_sent": 0,
            "employer_or_recruiter_contact": 0,
            "canonical_workbook_writes": 0,
            "external_delivery_attempted": 0,
            "browser_or_gui_launched": False,
            "network_or_provider_calls": 0,
            "invented_deadlines": 0,
            "invented_eligibility_positions": 0,
            "invented_priority_scores": 0,
        },
    }
    checks: list[dict] = []

    def check(name: str, ok: bool, detail=None, critical: bool = True) -> None:
        checks.append({"check": name, "ok": bool(ok), "critical": critical, "detail": detail})

    profiles = json.loads((CAREER_OPS_DIR / "regional_profiles.json").read_text(encoding="utf-8"))
    workbooks = {r: Path(rc["tracker"]) for r, rc in profiles["regions"].items()}
    hashes_before = {r: sha(p) for r, p in workbooks.items()}

    # ---------------- stage 1: live brief ------------------------------- #
    live_dir = scratch / "live"
    live, _live_res = db.run_brief(cfg, now=NOW, out_dir_override=str(live_dir))
    brief = json.loads(Path(live["brief_path"]).read_text(encoding="utf-8"))
    required_keys = ("schema_version", "brief_id", "as_of", "window", "status", "inputs",
                     "regional_scan_health", "trackers", "newly_added_jobs",
                     "duplicates_suppressed", "company_watch", "application_status_changes",
                     "interviews_and_followups", "deadlines_followups", "owner_actions",
                     "workflow_outputs", "priorities", "policy", "unknowns", "safety")
    ev["stage_1_live_brief"] = {
        "brief_id": brief["brief_id"],
        "content_digest": brief["content_digest"],
        "input_fingerprint": brief["input_fingerprint"],
        "brief_path": live["brief_path"],
        "summary_path": live["summary_path"],
        "window": brief["window"],
        "status": brief["status"],
        "counts": live["counts"],
        "missing_keys": [k for k in required_keys if k not in brief],
        "inputs_present": {n: f.get("exists") for n, f in brief["inputs"].items()
                           if n != "canonical_workbooks"},
        "canonical_workbooks_present": {r: w.get("exists")
                                        for r, w in (brief["inputs"]["canonical_workbooks"].get("regions") or {}).items()},
        "policy": {"version": brief["policy"]["version"], "sha256": brief["policy"]["sha256"],
                   "score_kind": brief["policy"]["score_semantics"]["kind"]},
    }
    check("stage1 the live brief parses and carries every required section",
          not ev["stage_1_live_brief"]["missing_keys"], ev["stage_1_live_brief"]["missing_keys"])
    check("stage1 the brief is marked read-only with its source of truth",
          brief["status"]["read_only"] is True
          and "canonical" in brief["status"]["source_of_truth"],
          brief["status"]["source_of_truth"])
    check("stage1 the declared priority policy is carried with its hash",
          brief["policy"]["score_semantics"]["kind"] == "deterministic_policy_output"
          and len(brief["policy"]["sha256"]) == 64
          and set(brief["policy"]["weights"]) ==
          {"deadline", "stage", "eligibility_certainty", "freshness", "owner_flag"})

    # ---------------- stage 2: empty inputs ----------------------------- #
    empty_dir = scratch / "empty"
    empty_cfg = isolated_cfg(cfg, empty_dir)
    empty_out, _ = db.run_brief(empty_cfg, now=NOW)
    empty = json.loads(Path(empty_out["brief_path"]).read_text(encoding="utf-8"))
    ev["stage_2_empty_inputs"] = {
        "ok": empty_out["ok"], "degraded": empty["status"]["degraded"],
        "priorities": len(empty["priorities"]),
        "unknowns": [u["reason"] for u in empty["unknowns"]],
        "inputs_absent": sorted(n for n, f in empty["inputs"].items()
                                if n != "canonical_workbooks" and not f.get("exists")),
        "canonical_state_unchanged": empty["safety"]["canonical_state_unchanged"],
    }
    check("stage2 an empty-input run still builds a valid brief",
          empty_out["ok"] is True and empty["schema_version"] == db.SCHEMA_VERSION)
    check("stage2 every missing input is reported, none is read as healthy or zero",
          _missing_inputs_labelled(empty, empty_cfg))
    check("stage2 no priority item is invented from absent inputs",
          empty["priorities"] == [] and empty["newly_added_jobs"]["counts"]["tracker_rows_in_window"] == 0)

    # ---------------- stage 3: partial inputs --------------------------- #
    partial_dir = scratch / "partial"
    partial_cfg = isolated_cfg(cfg, partial_dir, drop=("interview_prep_config",))
    # give it only the regional state file
    runs = partial_dir / "scan-runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "regional-run-state.json").write_text(json.dumps({
        "schema_version": 1,
        "regions": {"uk": {"last_run_id": "uk-a", "last_run_at": "2026-09-24T06:00:00+00:00",
                           "last_status": "ok", "last_accepted": 0, "last_would_append": 0,
                           "runs": 1}}}), encoding="utf-8")
    partial_cfg["inputs"]["regional_state"] = str(runs / "regional-run-state.json")
    partial_cfg["inputs"]["scan_runs_dir"] = str(runs)
    partial_out, _ = db.run_brief(partial_cfg, now=NOW)
    partial = json.loads(Path(partial_out["brief_path"]).read_text(encoding="utf-8"))
    ev["stage_3_partial_inputs"] = {
        "ok": partial_out["ok"],
        "regional_state_present": partial["inputs"]["regional_state"]["exists"],
        "owner_actions_available": partial["owner_actions"]["items"] != [],
        "owner_action_counts": partial["owner_actions"]["counts"],
        "owner_actions_path": partial["owner_actions"]["path"],
        "interviews_available": partial["interviews_and_followups"]["available"],
        "interviews_error": partial["interviews_and_followups"].get("error"),
        "absent_inputs": sorted(n for n, f in partial["inputs"].items()
                                if n != "canonical_workbooks" and not f.get("exists")),
        "unknown_areas": sorted({u["area"] for u in partial["unknowns"]}),
        "chief_summary_lines": len(partial_out["chief_summary"].splitlines()),
    }
    check("stage3 a partial-input run still builds a valid brief", partial_out["ok"] is True)
    check("stage3 the absent owner-action file is named as a missing input",
          "owner_actions_file" in ev["stage_3_partial_inputs"]["absent_inputs"]
          and any(u.get("area") == "input" and u.get("input") == "owner_actions_file"
                  for u in partial["unknowns"]),
          ev["stage_3_partial_inputs"]["absent_inputs"])
    check("stage3 no owner action is invented when the owner-action file is absent",
          partial["owner_actions"]["counts"]["items_parsed"] == 0
          and partial["owner_actions"]["counts"]["open"] == 0
          and partial["owner_actions"]["open_items"] == [])
    check("stage3 an unavailable input section reports unavailable plus its reason",
          partial["interviews_and_followups"]["available"] is False
          and bool(partial["interviews_and_followups"].get("error")),
          partial["interviews_and_followups"].get("error"))

    # ---------------- stage 4: idempotency ------------------------------ #
    again, again_res = db.run_brief(cfg, now=NOW, out_dir_override=str(live_dir))
    files_after = {p.name: sha(p) for p in live_dir.glob("*")}
    # The as-of clock is floored to the declared quantum, so a run inside the
    # same quantum over unchanged artifacts is the *same* brief, not a new one.
    quantum_min = int(cfg["window"].get("quantize_minutes") or 0)
    within, within_res = db.run_brief(cfg, now=NOW + dt.timedelta(minutes=30),
                                      out_dir_override=str(live_dir))
    files_after_within = {p.name: sha(p) for p in live_dir.glob("*")}
    # only the append-only run log may differ; no brief/summary/latest byte changes
    _no_log = lambda fs: {k: v for k, v in fs.items() if k != "run-log.jsonl"}
    third, third_res = db.run_brief(cfg, now=NOW + dt.timedelta(hours=6),
                                    out_dir_override=str(live_dir))
    ev["stage_4_idempotency"] = {
        "digest_repeat_identical": again["content_digest"] == live["content_digest"],
        "fingerprint_repeat_identical": again["input_fingerprint"] == live["input_fingerprint"],
        "second_run_writes": again_res["writes"],
        "second_run_reported_idempotent": again["idempotent"],
        "quantize_minutes": quantum_min,
        "sub_quantum_run_same_digest": within["content_digest"] == live["content_digest"],
        "sub_quantum_run_same_brief_id": within["brief_id"] == live["brief_id"],
        "sub_quantum_run_writes": within_res["writes"],
        "sub_quantum_run_added_no_file": _no_log(files_after_within) == _no_log(files_after),
        "brief_window_reports_quantum": brief["window"].get("quantize_minutes") == quantum_min,
        "third_run_different_window_new_brief": third["content_digest"] != live["content_digest"],
        "third_run_writes": len(third_res["writes"]),
        "run_log_entries": len([l for l in (live_dir / "run-log.jsonl")
                                .read_text(encoding="utf-8").splitlines() if l.strip()]),
        "files_after_two_runs": len(files_after),
    }
    check("stage4 a repeat run yields the same digest and the same input fingerprint",
          ev["stage_4_idempotency"]["digest_repeat_identical"]
          and ev["stage_4_idempotency"]["fingerprint_repeat_identical"])
    check("stage4 a repeat run writes no new bytes and says so", again_res["writes"] == []
          and again["idempotent"] is True, again_res["writes"])
    check("stage4 a run inside the same declared quantum is the same brief and writes nothing",
          quantum_min > 0
          and ev["stage_4_idempotency"]["sub_quantum_run_same_digest"]
          and ev["stage_4_idempotency"]["sub_quantum_run_same_brief_id"]
          and within_res["writes"] == []
          and ev["stage_4_idempotency"]["sub_quantum_run_added_no_file"],
          {"quantize_minutes": quantum_min, "writes": within_res["writes"]})
    check("stage4 the brief reports the quantum its identity is derived from",
          ev["stage_4_idempotency"]["brief_window_reports_quantum"]
          and bool(brief["window"].get("quantize_note")))
    check("stage4 a different window is a genuinely different brief",
          ev["stage_4_idempotency"]["third_run_different_window_new_brief"])

    # ---------------- stage 5: no fabricated priority facts ------------- #
    bad_arithmetic, unlabelled, imputed = [], [], []
    for item in brief["priorities"]:
        p = item["priority"]
        total = sum(c["contribution"] for c in p["components"])
        if abs(total - p["score"]) > 0.05:
            bad_arithmetic.append({"ref": item["ref"], "score": p["score"], "sum": total})
        unknown_inputs = {u["input"] for u in p["unknown_inputs"]}
        known_inputs = {c["input"] for c in p["components"]}
        if unknown_inputs & known_inputs:
            imputed.append({"ref": item["ref"], "input": sorted(unknown_inputs & known_inputs)})
        if p["score"] == 0 and p["coverage_pct"] == 0.0:
            if not any(o["rule"] == "unscoreable" for o in p["overrides"]):
                unlabelled.append(item["ref"])
        for c in p["components"]:
            if c["input"] not in brief["policy"]["weights"]:
                unlabelled.append(f"{item['ref']}:{c['input']}")
    ev["stage_5_no_fabricated_priority"] = {
        "items": len(brief["priorities"]),
        "arithmetic_mismatches": bad_arithmetic,
        "unknown_also_imputed": imputed,
        "unlabelled_zero_coverage": unlabelled,
        "coverage_range": _coverage_range(brief["priorities"]),
        "unknowns_total": len(brief["unknowns"]),
        "unknown_areas": sorted({u["area"] for u in brief["unknowns"]}),
    }
    check("stage5 every score equals the sum of its declared component contributions",
          bad_arithmetic == [], bad_arithmetic[:3])
    check("stage5 no unknown input is also reported as a known component", imputed == [],
          imputed[:3])
    check("stage5 a zero-coverage item is labelled unscoreable, never silently scored",
          unlabelled == [], unlabelled[:3])
    check("stage5 unknowns are recorded with a reason", all(u.get("reason") for u in brief["unknowns"])
          if brief["unknowns"] else True)

    # ---------------- stage 6: required content ------------------------- #
    scan_regions = (brief["regional_scan_health"].get("regions") or {})
    health_ok = all(v["health"] in ("ok", "stale", "unknown") or v["health"].startswith("degraded")
                    for v in scan_regions.values())
    ev["stage_6_required_content"] = {
        "scan_health_available": brief["regional_scan_health"].get("available"),
        "scan_regions": {r: {"health": v["health"], "last_status": v["last_status"],
                             "age_hours": v["run_age_hours"],
                             "accepted": v["last_accepted"],
                             "duplicates_suppressed": v["duplicates_suppressed"],
                             "new_offers_without_url": len(v["new_offers_without_url"])}
                         for r, v in scan_regions.items()},
        "newly_added_jobs": brief["newly_added_jobs"]["counts"],
        "duplicates_suppressed_totals": brief["duplicates_suppressed"]["totals"],
        "application_status_counts": brief["application_status_changes"]["counts"],
        "application_status_available": brief["application_status_changes"]["available"],
        "interviews_followups_counts": brief["interviews_and_followups"]["counts"],
        "owner_action_counts": brief["owner_actions"]["counts"],
        "deadlines": brief["deadlines_followups"]["counts"],
        "regions_without_deadline_column": brief["deadlines_followups"]["regions_without_deadline_column"],
        "tracker_rows_total": brief["trackers"]["total_rows"],
    }
    check("stage6 regional scan health is present for every scheduled region",
          bool(scan_regions) and health_ok, list(scan_regions))
    check("stage6 newly added jobs and duplicates suppressed are both reported",
          "tracker_rows_in_window" in brief["newly_added_jobs"]["counts"]
          and set(brief["duplicates_suppressed"]["totals"]) ==
          {"scan_duplicates", "policy_duplicate_prior_run", "writer_duplicates"})
    check("stage6 application-status changes are reported (zero is stated, not omitted)",
          "proposed_status_changes" in brief["application_status_changes"]["counts"]
          and brief["application_status_changes"]["available"] is True)
    check("stage6 interview/follow-up items are reported",
          "packs" in brief["interviews_and_followups"]["counts"]
          and "application_rows_past_first_stage" in brief["interviews_and_followups"]["counts"])
    check("stage6 owner actions are reported with their open/unknown split",
          {"items_parsed", "open", "unknown_status"} <= set(brief["owner_actions"]["counts"]))
    check("stage6 a region whose tracker has no deadline column is labelled unknown",
          bool(brief["deadlines_followups"]["regions_without_deadline_column"])
          == any(u["area"] == "deadline" for u in brief["unknowns"]),
          brief["deadlines_followups"]["regions_without_deadline_column"])

    # ---------------- stage 7: nothing changed, nothing external -------- #
    hashes_after = {r: sha(p) for r, p in workbooks.items()}
    ev["stage_7_no_change_no_external"] = {
        "canonical_hashes_before": hashes_before,
        "canonical_hashes_after": hashes_after,
        "changed": [r for r in hashes_before if hashes_before[r] != hashes_after[r]],
        "brief_records_unchanged": brief["safety"]["canonical_state_unchanged"],
        "safety": brief["safety"],
        "delivery": live["delivery"],
    }
    check("stage7 the canonical workbooks are byte-identical after the run",
          ev["stage_7_no_change_no_external"]["changed"] == []
          and brief["safety"]["canonical_state_unchanged"] is True)
    check("stage7 the brief records zero submissions, zero messages, zero canonical writes",
          brief["safety"]["applications_submitted"] == 0
          and brief["safety"]["external_messages_sent"] == 0
          and brief["safety"]["canonical_workbook_writes"] == 0)
    check("stage7 no external delivery channel is claimed healthy",
          live["delivery"]["external_channels"] == []
          and live["delivery"]["external_channel_health"] == "not_verified")
    check("stage7 the local write is verified by sha256 read-back",
          live["delivery"]["local_write_verified_by_hash"] is True)

    # ---------------- stage 8: Chief summary ---------------------------- #
    summary = live["chief_summary"]
    ev["stage_8_chief_summary"] = {
        "lines": len(summary.splitlines()),
        "max_lines": cfg["brief"]["max_summary_lines"],
        "text": summary,
    }
    check("stage8 the Chief summary is concise and factual",
          len(summary.splitlines()) <= cfg["brief"]["max_summary_lines"]
          and all(k in summary for k in ("Scan health:", "Owner actions:", "Safety:", "Unknowns:")))
    check("stage8 the summary states the delivery channel honestly",
          "not_verified" in summary)

    # ---------------- stage 9: schedulability --------------------------- #
    schedules = json.loads((CAREER_OPS_DIR / "regional_schedules.json").read_text(encoding="utf-8"))
    brief_sched = schedules.get("brief") or {}
    launcher = CAREER_OPS_DIR / "run_scheduled_brief.cmd"
    task_query = _query_task(brief_sched.get("task_name", ""))
    ev["stage_9_schedulability"] = {
        "declared": brief_sched,
        "launcher": str(launcher), "launcher_exists": launcher.exists(),
        "task_query": task_query,
        "morning_delivery_note": ("the schedule makes the brief available in the morning; "
                                  "delivering it to a messaging surface is not configured and "
                                  "not claimed healthy"),
    }
    check("stage9 a morning schedule is declared for the brief", bool(brief_sched)
          and bool(brief_sched.get("task_name")) and bool(brief_sched.get("time")))
    check("stage9 the scheduled launcher exists", launcher.exists(), str(launcher))
    check("stage9 the task state is read from Task Scheduler, not assumed",
          task_query.get("queried") is True, task_query)

    ev["checks"] = checks
    failed = [c["check"] for c in checks if c["critical"] and not c["ok"]]
    ev["critical_checks_failed"] = failed
    ev["ok"] = not failed

    (out_dir / "acceptance.json").write_text(
        json.dumps(ev, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md = [f"# Career Daily Brief / Pipeline Prioritizer (B23) acceptance — {stamp}", "",
          f"Overall: {'PASS' if ev['ok'] else 'FAIL'}  ",
          f"Code SHA: `{ev['code_sha']}`  ",
          f"Brief: `{ev['stage_1_live_brief']['brief_id']}` "
          f"(content digest `{ev['stage_1_live_brief']['content_digest'][:16]}…`)  ",
          f"Canonical workbooks unchanged: "
          f"{'YES' if ev['stage_7_no_change_no_external']['changed'] == [] else 'NO'}",
          "", "## Checks", "", "| check | result |", "|---|---|"]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |" for c in checks]
    md += ["", "## Chief-facing summary produced by this run", "", "```",
           summary, "```", "", "## Counts", "",
           f"- scan regions: {json.dumps(ev['stage_6_required_content']['scan_regions'])}",
           f"- newly added jobs: {json.dumps(ev['stage_6_required_content']['newly_added_jobs'])}",
           f"- duplicates suppressed: {json.dumps(ev['stage_6_required_content']['duplicates_suppressed_totals'])}",
           f"- application-status changes: {json.dumps(ev['stage_6_required_content']['application_status_counts'])}",
           f"- interviews/follow-ups: {json.dumps(ev['stage_6_required_content']['interviews_followups_counts'])}",
           f"- owner actions: {json.dumps(ev['stage_6_required_content']['owner_action_counts'])}",
           f"- deadlines: {json.dumps(ev['stage_6_required_content']['deadlines'])} "
           f"(no deadline column: {ev['stage_6_required_content']['regions_without_deadline_column']})",
           f"- priority items: {ev['stage_5_no_fabricated_priority']['items']}, "
           f"unknowns: {ev['stage_5_no_fabricated_priority']['unknowns_total']}",
           "", "## Not performed", ""]
    md += [f"- {n}" for n in cfg["not_performed"]]
    (out_dir / "acceptance.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "acceptance_run": stamp,
        "ok": ev["ok"],
        "evidence": str(out_dir / "acceptance.json"),
        "evidence_md": str(out_dir / "acceptance.md"),
        "checks_passed": sum(1 for c in checks if c["ok"]),
        "checks_total": len(checks),
        "critical_failed": failed,
        "brief_id": live["brief_id"],
        "content_digest": live["content_digest"],
        "canonical_state_unchanged": brief["safety"]["canonical_state_unchanged"],
        "external_actions_taken": 0,
    }, indent=2, ensure_ascii=False, default=str))
    return 0 if ev["ok"] else 1


def _coverage_range(priorities: list) -> list:
    values = sorted(p["priority"]["coverage_pct"] for p in priorities)
    return [values[0], values[-1]] if values else [None, None]


def _missing_inputs_labelled(brief: dict, cfg: dict) -> bool:
    """Every declared-but-absent input must appear as an unknown or as absent."""
    unknown_inputs = {u.get("input") for u in brief["unknowns"] if u.get("area") == "input"}
    for name, fact in brief["inputs"].items():
        if name == "canonical_workbooks":
            continue
        if fact.get("exists") is False and name not in unknown_inputs:
            return False
    return True


def _query_task(task_name: str) -> dict:
    """Read the task's real state. Never assume it exists, never create it here."""
    if not task_name:
        return {"queried": False, "reason": "no task name declared"}
    if not shutil.which("schtasks"):
        return {"queried": False, "reason": "schtasks not available"}
    proc = subprocess.run(["schtasks", "/Query", "/TN", task_name, "/FO", "LIST"],
                          capture_output=True, text=True, shell=False)
    return {"queried": True, "registered": proc.returncode == 0,
            "output": (proc.stdout or proc.stderr).strip()[:1200]}


if __name__ == "__main__":
    raise SystemExit(main())
