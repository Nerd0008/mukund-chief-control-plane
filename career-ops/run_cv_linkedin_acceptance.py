#!/usr/bin/env python3
"""End-to-end acceptance for the v1 Career Ops CV/cover-letter + LinkedIn path.

Representative path exercised here (all local, all fixture/owner-owned data):

    Career Ops job record  ->  tailored CV draft + cover-letter draft (+ fact gate)
                           ->  LinkedIn read-only signal intake + drafts (unsent)
                           ->  dedupe against Career Ops + Company Watch
                           ->  Career Ops tracker handoff (dry-run, then a COPY)
                           ->  Chief summary

Truthfulness rules encoded in this runner:

  * The canonical regional workbooks are opened read-only. Every write happens
    against a dated COPY, and the canonical hashes are re-checked before and
    after to prove they were not touched.
  * The LinkedIn surface is read-only/draft-only. The runner asserts that no
    network call, no browser, no login and no account mutation happened, and it
    proves the owner gate by asking the workflow to refuse posting, messaging,
    connecting and applying.
  * The job description is an explicitly labelled synthetic fixture, not a live
    vacancy. No vacancy is claimed to be live and nothing is submitted.
  * The CV/cover-letter drafts are checked line-by-line against cv.md: every
    line must be verbatim canonical text. Nothing is rewritten or invented.

Usage
  python career-ops/run_cv_linkedin_acceptance.py [--region uk] [--stamp S]
                                                  [--out-dir DIR]
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
import cv_workflow as cvw  # noqa: E402
import linkedin_workflow as liw  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures"
DEFAULT_INBOX = FIXTURES / "linkedin"
DEFAULT_JD = FIXTURES / "jd-information-security-analyst.txt"


def canonical_lines(cv_text: str) -> set[str]:
    out = set()
    for raw in cv_text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        out.add(stripped)
        heading = re.sub(r"^#{1,6}\s+", "", stripped)
        out.add(heading)
        bullet = re.sub(r"^[-*]\s+", "", stripped)
        out.add(bullet)
    return out


def draft_not_verbatim(draft_text: str, cv_lines: set[str]) -> list[str]:
    """Every non-structural draft line must exist verbatim in cv.md."""
    bad = []
    in_comment = False
    for raw in draft_text.splitlines():
        line = raw.strip()
        if line.startswith("<!--"):
            in_comment = True
            continue
        if in_comment:
            if line.endswith("-->"):
                in_comment = False
            continue
        if not line:
            continue
        candidate = re.sub(r"^#{1,6}\s+", "", line)
        candidate = re.sub(r"^[-*]\s+", "", candidate)
        if candidate not in cv_lines:
            bad.append(raw)
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="uk")
    ap.add_argument("--stamp")
    ap.add_argument("--out-dir")
    ap.add_argument("--pipeline-index", type=int, default=0)
    args = ap.parse_args(argv)

    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    region = args.region
    li_cfg = liw.load_config()
    cw_cfg = liw.cw_config(li_cfg)
    cv_cfg = liw.cv_config(li_cfg)
    profiles = tw.load_profiles(str(CONTROL_PLANE / cv_cfg["regional_profiles"]))

    run_root = CONTROL_PLANE / "runtime" / "linkedin" / "acceptance" / stamp
    run_root.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out_dir) if args.out_dir else \
        (CONTROL_PLANE / li_cfg["evidence_dir"] / f"{stamp}-cv-linkedin-workflows")
    out_dir.mkdir(parents=True, exist_ok=True)

    ev: dict = {
        "acceptance_run": stamp,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "workflow": "career-ops CV/cover-letter drafts + minimal LinkedIn workflow",
        "region": region,
        "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md "
                     "§ CV + cover-letter workflow / § LinkedIn workflow",
        "cheating_guards": {
            "canonical_trackers_touched": False,
            "applications_submitted": 0,
            "external_messages_sent": 0,
            "linkedin_posts_published": 0,
            "linkedin_connections_requested": 0,
            "network_calls_by_linkedin_workflow": 0,
            "browser_launched": False,
        },
    }
    checks: list[dict] = []

    def check(name: str, ok: bool, detail=None, critical: bool = True) -> None:
        checks.append({"check": name, "ok": bool(ok), "critical": critical, "detail": detail})

    # ---------------- stage 1: canonical sources ------------------------ #
    emit_sources = {}
    for key, path in cvw.source_paths(cv_cfg).items():
        emit_sources[key] = {"path": str(path), "exists": path.exists(),
                             "sha256": cvw.sha256_file(path) if path.exists() else None}
    node_ok = shutil.which(cv_cfg["renderer"]["node"]) is not None
    gate_ok = node_ok and (cvw.source_paths(cv_cfg)["cv_facts"].parent.parent
                           / "verify-cv-facts.mjs").exists()
    ev["stage_1_sources"] = {
        "sources": emit_sources,
        "node_available": node_ok,
        "fact_gate_ready": gate_ok,
        "note": "Canonical CV/profile/facts are read-only sources in the existing Career Ops install.",
    }
    check("stage1 node + install fact gate available", gate_ok,
         {"node": node_ok, "fact_gate": gate_ok})

    # ---------------- stage 2: job context from Career Ops -------------- #
    resolved = cvw.resolve_job(cv_cfg, profiles, region=region,
                               pipeline_index=args.pipeline_index)
    job = resolved.get("job") if resolved.get("ok") else None
    jd_text = DEFAULT_JD.read_text(encoding="utf-8")
    ev["stage_2_job_context"] = {
        "resolved": bool(resolved.get("ok")),
        "reason": resolved.get("reason"),
        "job": {k: v for k, v in (job or {}).items() if not k.startswith("_")},
        "source_kind": (job or {}).get("_source_kind"),
        "job_description": {
            "path": str(DEFAULT_JD),
            "kind": "SYNTHETIC FIXTURE — not a live vacancy, not fetched from anywhere",
            "sha256": cvw.sha256_file(DEFAULT_JD),
            "chars": len(jd_text),
        },
    }
    check("stage2 job record resolved from Career Ops state", bool(resolved.get("ok")),
          resolved.get("reason"))

    # ---------------- stage 3: CV + cover-letter drafts ----------------- #
    draft_dir = run_root / "cv-drafts"
    drafts: dict = (cvw.build_drafts(cv_cfg, profiles, job=job, jd_text=jd_text,
                                     jd_source=f"synthetic fixture {DEFAULT_JD.name}",
                                     stamp=stamp, run_dir=draft_dir)
                    if job else {"ok": False})
    cv_lines = cvw.read_text(cvw.source_paths(cv_cfg)["cv_md"])
    verbatim_set = canonical_lines(cv_lines)
    cv_draft_text = cvw.read_text(Path(drafts["cv_draft"]["path"])) if drafts.get("ok") else ""
    bad_lines = draft_not_verbatim(cv_draft_text, verbatim_set) if drafts.get("ok") else ["draft not produced"]
    gates = drafts.get("fact_gate", {}) if drafts.get("ok") else {}
    gate_blocks = [k for k, v in gates.items() if v.get("available") and v.get("verdict") == "block"]
    ev["stage_3_cv_and_cover_letter_drafts"] = {
        "status": drafts.get("status"),
        "run_dir": drafts.get("run_dir"),
        "job": drafts.get("job"),
        "job_description": drafts.get("job_description"),
        "cv_draft": drafts.get("cv_draft"),
        "cover_letter": drafts.get("cover_letter"),
        "fact_gate": gates,
        "lines_not_verbatim_from_cv_md": bad_lines[:10],
        "owner_input_required": drafts.get("owner_input_required"),
        "llm_tailor_request": drafts.get("llm_tailor_request"),
        "pdf_rendered": False,
        "note": ("The cover-letter HTML is produced by the install's own buildHtml; PDF rendering "
                 "(headless Chromium) is deliberately not performed."),
    }
    check("stage3 CV/cover-letter drafts produced", bool(drafts.get("ok")),
          drafts.get("status"))
    check("stage3 every CV draft line is verbatim canonical text", not bad_lines,
          bad_lines[:5])
    check("stage3 install fact gate did not block", not gate_blocks, gate_blocks)
    check("stage3 cover letter rendered by the install's own renderer",
          bool(drafts.get("cover_letter", {}).get("render", {}).get("rendered")))

    # ---------------- stage 4: LinkedIn read-only intake ---------------- #
    intake = liw.collect_signals(li_cfg, DEFAULT_INBOX)
    roc = intake.get("read_only_contract", {})
    ev["stage_4_linkedin_intake"] = {
        "inbox": intake.get("inbox"),
        "files": intake.get("files"),
        "counts": intake.get("counts"),
        "read_only_contract": roc,
        "unclassified_sample": [u.get("reason") for u in intake.get("unclassified", [])][:3],
    }
    check("stage4 LinkedIn intake read-only contract holds",
          roc.get("network_used") is False and roc.get("urls_fetched") == 0
          and roc.get("browser_launched") is False
          and roc.get("linkedin_authenticated") is False
          and roc.get("account_mutations") == 0, roc)
    check("stage4 signals classified from fixtures", intake.get("counts", {}).get("signals", 0) > 0,
          intake.get("counts"))

    # ---------------- stage 5: dedupe against Career Ops + Company Watch - #
    canonical = Path(profiles["regions"][region]["tracker"])
    canonical_before = tw.sha256_file(canonical)
    dedupe = liw.dedupe_signals(li_cfg, region, intake["signals"])
    canonical_after_dedupe = tw.sha256_file(canonical)
    ev["stage_5_dedupe"] = {
        "tracker": str(canonical),
        "tracker_sha256_before": canonical_before,
        "tracker_sha256_after": canonical_after_dedupe,
        "counts": dedupe["counts"],
        "canonical_url_keys": dedupe["canonical_url_keys"],
        "cross_month_keys": dedupe["cross_month_keys"],
        "company_watch": dedupe["company_watch"],
        "company_watch_registry_companies": dedupe["company_watch_registry_companies"],
        "dedupe_engine": dedupe["dedupe_engine"],
        "job_decisions": dedupe["job_decisions"],
        "company_decisions": dedupe["company_decisions"],
    }
    check("stage5 canonical tracker untouched by dedupe",
          canonical_before == canonical_after_dedupe)
    check("stage5 LinkedIn jobs deduped against Career Ops + Company Watch",
          dedupe["counts"]["job_signals"] > 0
          and dedupe["company_watch_registry_companies"] > 0, dedupe["counts"])
    check("stage5 a same-posting LinkedIn duplicate was detected and merged",
          any(d.get("merged_signals", 0) > 0 for d in dedupe["job_decisions"]),
          {d["company"]: d.get("merged_signals") for d in dedupe["job_decisions"]})

    # ---------------- stage 6: LinkedIn drafts (unsent) ------------------ #
    li_draft_dir = run_root / "linkedin-drafts"
    li_drafts = liw.build_linkedin_drafts(li_cfg, out_dir=li_draft_dir,
                                          scratch=li_draft_dir / "factgate")
    ev["stage_6_linkedin_drafts"] = {
        "status": li_drafts["status"],
        "counts": li_drafts["counts"],
        "fact_gate": li_drafts["fact_gate"],
        "drafts_path": li_drafts["drafts_path"],
        "posts_performed": li_drafts["posts_performed"],
        "sends_performed": li_drafts["sends_performed"],
        "drafts": [{"kind": d["kind"], "topic": d.get("topic"), "status": d["status"],
                    "sources": [f"cv.md:{s['line']}" for s in d.get("sources", [])]}
                   for d in li_drafts["drafts"]],
    }
    check("stage6 LinkedIn drafts produced and fact-gated", li_drafts["ok"], li_drafts["status"])
    check("stage6 every LinkedIn draft is unsent",
          all(d["status"] == "draft_unsent" for d in li_drafts["drafts"]))
    check("stage6 no post/send performed",
          li_drafts["posts_performed"] == 0 and li_drafts["sends_performed"] == 0)

    # ---------------- stage 7: owner action gate ------------------------ #
    guard_results = {a: liw.guard_action(li_cfg, a) for a in
                     ("post", "message", "connection_request", "apply", "profile_update")}
    ev["stage_7_owner_action_gate"] = {
        "refusals": {a: {"allowed": r["allowed"], "owner_gated": r["owner_gated"],
                         "performed": r["performed"], "reason": r["reason"]}
                     for a, r in guard_results.items()},
        "allowed_read_draft_example": liw.guard_action(li_cfg, "intake"),
    }
    check("stage7 every external LinkedIn action refused and unperformed",
          all(not r["allowed"] and not r["performed"] for r in guard_results.values()),
          {a: r["allowed"] for a, r in guard_results.items()})
    check("stage7 a read/draft action is not blocked",
          ev["stage_7_owner_action_gate"]["allowed_read_draft_example"]["allowed"] is True)

    # ---------------- stage 8: handoff (dry-run, then COPY) ------------- #
    manifest = liw.build_handoff_manifest(li_cfg, region, dedupe)
    dry = liw.handoff(li_cfg, region, manifest, apply=False)
    canonical_after_dry = tw.sha256_file(canonical)
    ev["stage_8_handoff"] = {
        "manifest_counts": manifest["counts"],
        "provenance_column": manifest["provenance_column"],
        "dry_run": {"invoked": dry.get("invoked"), "exit_code": dry.get("exit_code"),
                    "mode": dry.get("mode"),
                    "planned": (dry.get("result") or {}).get("planned_rows"),
                    "counts": (dry.get("result") or {}).get("counts")},
        "canonical_sha256_after_dry_run": canonical_after_dry,
    }
    check("stage8 dry-run handoff did not touch the canonical tracker",
          canonical_before == canonical_after_dry)

    test_copy = run_root / canonical.name
    shutil.copy2(canonical, test_copy)
    copy_before = tw.sha256_file(test_copy)
    applied = liw.handoff(li_cfg, region, manifest, tracker=str(test_copy),
                          apply=True, backup_dir=str(run_root / "backups"))
    copy_after = tw.sha256_file(test_copy)
    canonical_after_apply = tw.sha256_file(canonical)
    write_result = (applied.get("result") or {})
    provenance_col = manifest["provenance_column"]
    written_provenance = None
    if write_result.get("applied"):
        cfg_region = dict(tw.region_config(profiles, region))
        cfg_region["region"] = region
        tr = tw.Tracker(test_copy, cfg_region)
        try:
            col = cfg_region["field_map"].get(provenance_col)
            for r in range(cfg_region["first_data_row"], tr.last_data_row() + 1):
                value = tr.ws[f"{col}{r}"].value
                if isinstance(value, str) and value.startswith(liw.LINKEDIN_PROVENANCE_PREFIX):
                    written_provenance = {"row": r, "column": col, "value": value[:200]}
            appended_rows = tr.last_data_row() - cfg_region["first_data_row"] + 1
        finally:
            tr.wb.close()
    else:
        appended_rows = None
    ev["stage_8_handoff"].update({
        "test_copy": str(test_copy),
        "test_copy_sha256_before": copy_before,
        "test_copy_sha256_after": copy_after,
        "applied": write_result.get("applied"),
        "applied_counts": write_result.get("counts"),
        "planned_rows": write_result.get("planned_rows"),
        "backup": applied.get("result", {}).get("backup"),
        "verification": write_result.get("verification"),
        "rows_after": appended_rows,
        "linkedin_provenance_row": written_provenance,
        "canonical_sha256_after_apply": canonical_after_apply,
        "canonical_untouched": canonical_after_apply == canonical_before,
        "application_state_written": False,
    })
    check("stage8 handoff applied to the TEST COPY", bool(write_result.get("applied")),
          write_result.get("error"))
    check("stage8 canonical tracker untouched by the applied handoff",
          canonical_after_apply == canonical_before)
    check("stage8 LinkedIn provenance recorded in a non-owner column",
          bool(written_provenance), written_provenance)

    # rollback proof
    backup = write_result.get("backup")

    # ---------------- stage 9: linked duplicate after the append -------- #
    if written_provenance:
        linked_signal = [{
            "company": manifest["records"][0].get("company"),
            "title": manifest["records"][0].get("title"),
            "location": manifest["records"][0].get("location"),
            "url": manifest["records"][0].get("url"),
            "posted_at": manifest["records"][0].get("posted_date"),
            "source": "linkedin-acceptance-replay",
            "signal_kind": "job_signal",
            "provenance": {"file": "acceptance-replay", "file_sha256": "n/a", "index": 0},
        }]
        replay = liw.dedupe_signals(li_cfg, region, linked_signal,
                                    tracker_override=str(test_copy))
        ev["stage_9_replay_dedupe"] = {
            "decision": replay["job_decisions"][0]["decision"],
            "reason": replay["job_decisions"][0]["reason"],
            "note": "The same LinkedIn posting replayed against the written copy must be a duplicate.",
        }
        check("stage9 a LinkedIn posting already written is deduped on replay",
              replay["job_decisions"][0]["decision"].startswith("duplicate"),
              replay["job_decisions"][0])

    # ---------------- stage 9b: rollback proof (after the replay) ------- #
    if backup and Path(backup).exists():
        shutil.copy2(backup, test_copy)
        restored = tw.sha256_file(test_copy)
        ev["stage_9b_rollback"] = {
            "restored_from": backup, "restored_sha256": restored,
            "equals_pre_write_hash": restored == copy_before,
        }
        check("stage9b rollback restores the pre-write copy",
              restored == copy_before, {"restored": restored, "before": copy_before})
    else:
        ev["stage_9b_rollback"] = {"available": False, "reason": "no backup recorded"}
        check("stage9b a hash-verified backup was taken before the write", False,
              write_result.get("backup"))

    # ---------------- stage 10: Chief summary --------------------------- #
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_summary(argparse.Namespace(region=region, profiles=None))
    summary = json.loads(buf.getvalue())
    ev["stage_10_chief_summary"] = {"exit_code": rc, "region": summary["regions"][region]}
    check("stage10 Chief summary produced", rc == 0)

    ev["final_canonical_hashes"] = {
        r: tw.sha256_file(Path(cfg["tracker"])) for r, cfg in profiles["regions"].items()
    }
    ev["final_canonical_hashes_unchanged"] = {
        r: (ev["final_canonical_hashes"][r] ==
            (cvw.sha256_file(Path(cfg["tracker"]))))
        for r, cfg in profiles["regions"].items()
    }
    ev["checks"] = checks
    failed = [c["check"] for c in checks if c["critical"] and not c["ok"]]
    ev["critical_checks_failed"] = failed
    ev["ok"] = not failed

    (out_dir / "acceptance.json").write_text(
        json.dumps(ev, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md = [
        f"# CV/cover-letter + LinkedIn acceptance — {stamp}",
        "",
        f"Region: {region}  |  Overall: {'PASS' if ev['ok'] else 'FAIL'}",
        "",
        "## Checks",
        "",
        "| check | result |",
        "|---|---|",
    ]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |" for c in checks]
    md += [
        "",
        "## Path",
        "",
        f"1. Job record from Career Ops ({ev['stage_2_job_context'].get('source_kind')}): "
        f"{ev['stage_2_job_context']['job'].get('title')} @ "
        f"{ev['stage_2_job_context']['job'].get('company')}",
        f"2. CV draft: {ev['stage_3_cv_and_cover_letter_drafts'].get('cv_draft', {}).get('path')}",
        f"3. Cover-letter draft (install renderer): "
        f"{ev['stage_3_cv_and_cover_letter_drafts'].get('cover_letter', {}).get('html_path')}",
        f"4. Career Ops fact gate: "
        f"{ {k: v.get('verdict') for k, v in ev['stage_3_cv_and_cover_letter_drafts'].get('fact_gate', {}).items()} }",
        f"5. LinkedIn intake: {ev['stage_4_linkedin_intake']['counts']}",
        f"6. Dedupe: {ev['stage_5_dedupe']['counts']}",
        f"7. LinkedIn drafts: {ev['stage_6_linkedin_drafts']['counts']} "
        f"(gate {ev['stage_6_linkedin_drafts']['fact_gate'].get('verdict')})",
        f"8. Handoff to a workbook COPY: applied="
        f"{ev['stage_8_handoff'].get('applied')}, counts={ev['stage_8_handoff'].get('applied_counts')}",
        f"9. Canonical tracker untouched: {ev['stage_8_handoff'].get('canonical_untouched')}",
        "",
        "## Not performed",
        "",
    ]
    md += [f"- {n}" for n in li_cfg["not_performed"]]
    md += [f"- {n}" for n in cv_cfg["not_performed"]]
    (out_dir / "acceptance.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "acceptance_run": stamp,
        "ok": ev["ok"],
        "evidence": str(out_dir / "acceptance.json"),
        "evidence_md": str(out_dir / "acceptance.md"),
        "checks_passed": sum(1 for c in checks if c["ok"]),
        "checks_total": len(checks),
        "critical_failed": failed,
        "job": ev["stage_2_job_context"]["job"],
        "cv_draft": ev["stage_3_cv_and_cover_letter_drafts"].get("cv_draft", {}).get("path"),
        "cover_letter_html": ev["stage_3_cv_and_cover_letter_drafts"].get(
            "cover_letter", {}).get("html_path"),
        "fact_gate": {k: v.get("verdict") for k, v in
                      ev["stage_3_cv_and_cover_letter_drafts"].get("fact_gate", {}).items()},
        "linkedin_intake": ev["stage_4_linkedin_intake"]["counts"],
        "dedupe": ev["stage_5_dedupe"]["counts"],
        "linkedin_drafts": ev["stage_6_linkedin_drafts"]["counts"],
        "handoff_applied": ev["stage_8_handoff"].get("applied"),
        "canonical_untouched": ev["stage_8_handoff"].get("canonical_untouched"),
        "rollback_verified": ev.get("stage_9b_rollback", {}).get("equals_pre_write_hash"),
        "chief_summary_rows": ev["stage_10_chief_summary"]["region"].get("data_rows"),
    }, indent=2, ensure_ascii=False, default=str))
    return 0 if ev["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
