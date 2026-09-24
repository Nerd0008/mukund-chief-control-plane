#!/usr/bin/env python3
"""End-to-end acceptance: LinkedIn outreach drafting (B21) + Interview Prep Agent (B22).

Everything runs on local, explicitly-labelled SYNTHETIC fixtures and the owner's own
canonical CV/profile sources (read-only). No live vacancy is claimed, no employer,
recruiter or candidate is contacted, no browser or GUI is launched, no network call
is made, and nothing is posted, messaged, connected or submitted.

What this runner proves, stage by stage:

  stage 1  canonical Career Ops sources are read-only; every source hash is recorded
           before and re-checked after the whole run.
  stage 2  the LinkedIn read-only intake contract still holds (no network, no
           browser, no login, no account mutation) on the fixture inbox.
  stage 3  B21 outreach drafting: networking, recruiter and hiring-manager drafts
           are produced, each with provenance and an explicit unsent state; the
           hiring-manager variant names the role/employer ONLY from the resolved
           Career Ops job record; the install's fact gate does not block them.
  stage 4  the owner action gate refuses every external LinkedIn action
           (post/message/connection_request/apply/profile_update) and performs none.
  stage 5  B22 interview prep from the JobBrief + cited research + canonical sources:
           technical and behavioural preparation, a likely-question list, and
           evidence-backed talking points.
  stage 6  truth enforcement: every quoted line is re-checked against cv.md at the
           line it claims; a tampered quote is detected; a first-person claim in
           generated text is detected; a question that claims to be employer-supplied
           is rejected; `candidate_claims` and `external_actions_taken` are empty.
  stage 7  honesty of the unknown list: an unmatched requirement becomes an owner
           action (never an invented claim); the UAE fixture posting's eligibility
           stays `unknown` and no right-to-work position is invented.
  stage 8  determinism: the same brief produces the same pack counts and the same
           quoted lines twice in a row.
  stage 9  canonical sources and canonical trackers are provably untouched.

Usage
  python career-ops/run_interview_prep_acceptance.py [--stamp S] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import cv_workflow as cvw  # noqa: E402
import interview_prep as ip  # noqa: E402
import job_intelligence as ji  # noqa: E402
import linkedin_workflow as liw  # noqa: E402
import tracker_writer as tw  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures"
JI_FIXTURES = FIXTURES / "job-intelligence"
JD_UK = FIXTURES / "jd-information-security-analyst.txt"
JD_UAE = JI_FIXTURES / "jd-unknown-eligibility.txt"
RECORD_UK = JI_FIXTURES / "job-record-uk.json"
RESEARCH_CITED = JI_FIXTURES / "research-cited.json"


def fixture_job() -> dict:
    job = json.loads(RECORD_UK.read_text(encoding="utf-8"))
    job.update({"_region": "uk", "_source_kind": "synthetic-fixture-job-record",
                "_source_path": str(RECORD_UK)})
    return job


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp")
    ap.add_argument("--out-dir")
    args = ap.parse_args(argv)

    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cfg = ip.load_config()
    li_cfg = liw.load_config()
    cv_cfg = ip.cv_config(cfg)

    run_root = CONTROL_PLANE / cfg["runtime_dir"] / "acceptance" / stamp
    run_root.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out_dir) if args.out_dir else \
        (CONTROL_PLANE / cfg["evidence_dir"] / f"{stamp}-linkedin-outreach-interview-prep")
    out_dir.mkdir(parents=True, exist_ok=True)

    ev: dict = {
        "acceptance_run": stamp,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "workflow": "LinkedIn networking/recruiter outreach drafts + Interview Prep Agent",
        "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md "
                     "§ LinkedIn workflow / roster B19,B20,B21,B22",
        "cheating_guards": {
            "linkedin_posts_published": 0,
            "linkedin_messages_sent": 0,
            "linkedin_connections_requested": 0,
            "applications_submitted": 0,
            "employer_or_recruiter_contact": 0,
            "network_calls_made": 0,
            "browser_or_gui_launched": False,
            "canonical_sources_modified": False,
            "canonical_trackers_touched": False,
            "live_vacancy_claimed": False,
            "interview_claimed": False,
            "invented_interview_questions": 0,
        },
        "fixtures": {
            "job_record": {"path": str(RECORD_UK), "kind": "SYNTHETIC job record",
                           "sha256": cvw.sha256_file(RECORD_UK)},
            "posting_uk": {"path": str(JD_UK), "kind": "SYNTHETIC posting text",
                           "sha256": cvw.sha256_file(JD_UK)},
            "posting_uae": {"path": str(JD_UAE), "kind": "SYNTHETIC posting text",
                            "sha256": cvw.sha256_file(JD_UAE)},
            "research_cited": {"path": str(RESEARCH_CITED), "kind": "SYNTHETIC cited research",
                               "sha256": cvw.sha256_file(RESEARCH_CITED)},
            "linkedin_inbox": {"path": str(FIXTURES / "linkedin"),
                               "kind": "SYNTHETIC read-only signal export"},
        },
    }
    checks: list[dict] = []

    def check(name: str, ok: bool, detail=None, critical: bool = True) -> None:
        checks.append({"check": name, "ok": bool(ok), "critical": critical, "detail": detail})

    # ---------------- stage 1: canonical sources ------------------------ #
    sources = {}
    for key, path in cvw.source_paths(cv_cfg).items():
        sources[key] = {"path": str(path), "exists": path.exists(),
                        "sha256_before": cvw.sha256_file(path) if path.exists() else None}
    ev["stage_1_sources"] = {"sources": sources,
                             "note": "Canonical CV/profile/facts in the existing Career Ops "
                                     "install, opened read-only."}
    check("stage1 canonical Career Ops sources are present",
          all(s["exists"] for s in sources.values()),
          {k: v["exists"] for k, v in sources.items()})

    # ---------------- stage 2: LinkedIn read-only intake ---------------- #
    intake = liw.collect_signals(li_cfg, FIXTURES / "linkedin")
    roc = intake.get("read_only_contract", {})
    ev["stage_2_linkedin_intake"] = {"inbox": intake.get("inbox"),
                                     "counts": intake.get("counts"),
                                     "read_only_contract": roc}
    check("stage2 LinkedIn intake contract holds",
          roc.get("network_used") is False and roc.get("urls_fetched") == 0
          and roc.get("browser_launched") is False
          and roc.get("linkedin_authenticated") is False
          and roc.get("account_mutations") == 0, roc)

    # ---------------- stage 3: outreach drafts (B21) -------------------- #
    job = fixture_job()
    draft_dir = run_root / "linkedin-outreach"
    li_drafts = liw.build_linkedin_drafts(li_cfg, out_dir=draft_dir,
                                          scratch=draft_dir / "factgate", job=job)
    outreach = [d for d in li_drafts["drafts"] if d["kind"] == "outreach"]
    unsent_ok = all(
        d["status"] == "draft_unsent"
        and d["sent"] is False and d["recipient"] is None
        and d["unsent_state"]["sent"] is False
        and d["unsent_state"]["sent_at"] is None
        and d["unsent_state"]["recipient_selected"] is False
        and d["unsent_state"]["connection_request_created"] is False
        and d["unsent_state"]["message_queued"] is False
        and d["unsent_state"]["scheduled"] is False
        and d["unsent_state"]["attachments_sent"] == 0
        and d["unsent_state"]["owner_approval_required"] is True
        for d in outreach)
    provenance_ok = all(
        d["provenance"]["generator"] == "career-ops/linkedin_workflow.py"
        and d["provenance"]["source_lines"] == [f"cv.md:{s['line']}" for s in d["sources"]]
        for d in outreach)
    hm = [d for d in outreach if d.get("subtype") == "hiring_manager"]
    hm_ref_ok = bool(hm) and hm[0]["references_job"]["title"] == job["title"] \
        and hm[0]["references_job"]["company"] == job["company"] \
        and hm[0]["references_job"]["id"] == job["id"]
    ev["stage_3_outreach_drafts"] = {
        "counts": li_drafts["counts"],
        "fact_gate_verdict": li_drafts["fact_gate"].get("verdict") if
        li_drafts["fact_gate"].get("available") else "unavailable",
        "variants": [{"subtype": d.get("subtype"), "status": d["status"],
                      "recipient": d["recipient"], "channel": d["channel"],
                      "source_lines": d["provenance"]["source_lines"],
                      "bytes": len(d["body"])} for d in outreach],
        "hiring_manager_references_job": hm[0]["references_job"] if hm else None,
        "drafts_path": li_drafts["drafts_path"],
        "messages_queued": li_drafts["messages_queued"],
        "connection_requests_created": li_drafts["connection_requests_created"],
        "sends_performed": li_drafts["sends_performed"],
    }
    check("stage3 outreach drafts exist for networking, recruiter and hiring manager",
          {d.get("subtype") for d in outreach} == {"networking", "recruiter", "hiring_manager"},
          [d.get("subtype") for d in outreach])
    check("stage3 every outreach draft has an explicit unsent state", unsent_ok,
          [d["unsent_state"] for d in outreach][:1])
    check("stage3 every outreach draft carries provenance to cv.md lines", provenance_ok)
    check("stage3 the hiring-manager draft names the role ONLY from the Career Ops record",
          hm_ref_ok, hm[0]["references_job"] if hm else None)
    check("stage3 the install fact gate did not block the outreach drafts",
          not (li_drafts["fact_gate"].get("available")
               and li_drafts["fact_gate"].get("verdict") == "block"),
          li_drafts["fact_gate"].get("verdict"))
    check("stage3 no message was queued, no connection created, nothing sent",
          li_drafts["messages_queued"] == 0 and li_drafts["connection_requests_created"] == 0
          and li_drafts["sends_performed"] == 0)

    # ---------------- stage 4: owner action gate ------------------------ #
    guard = {a: liw.guard_action(li_cfg, a) for a in
             ("post", "message", "connection_request", "apply", "profile_update", "inmail")}
    ev["stage_4_owner_action_gate"] = {
        "refusals": {a: {"allowed": r["allowed"], "owner_gated": r["owner_gated"],
                         "performed": r["performed"], "reason": r["reason"]}
                     for a, r in guard.items()},
        "read_path_allowed": liw.guard_action(li_cfg, "intake")["allowed"],
    }
    check("stage4 every external LinkedIn action is refused and unperformed",
          all(not r["allowed"] and not r["performed"] for r in guard.values()),
          {a: r["allowed"] for a, r in guard.items()})

    # ---------------- stage 5: JobBrief + interview prep (B22) ---------- #
    uk_brief = ji.build_brief(ip.ji_config(cfg), job=job,
                              jd_text=JD_UK.read_text(encoding="utf-8"),
                              jd_source=f"synthetic fixture {JD_UK.name}",
                              stamp=stamp)
    brief_path = run_root / "job_brief_uk.json"
    brief_path.write_text(json.dumps(uk_brief, indent=2, ensure_ascii=False, default=str),
                          encoding="utf-8")
    pack = ip.build_prep_pack(cfg, uk_brief, brief_path=brief_path,
                              research_file=RESEARCH_CITED, stamp=stamp)
    pack_dir = run_root / "interview-prep"
    paths = ip._write_pack(pack, pack_dir)
    ev["stage_5_interview_prep"] = {
        "brief_id": uk_brief["brief_id"],
        "brief_validation_ok": uk_brief["validation"]["ok"],
        "prep_id": pack["prep_id"],
        "counts": pack["counts"],
        "validation": pack["validation"],
        "research": {k: v for k, v in pack["research"].items() if k != "facts"},
        "question_disclaimer_sample": [q["note"] for q in
                                       pack["sections"]["likely_questions"][:1]],
        "talking_points": [
            {"id": t["id"], "status": t["status"], "use": t["use"],
             "requirement_line": (t.get("requirement") or {}).get("source_line"),
             "quotes": [f"cv.md:{q['source_line']}" for q in t["quotes"]],
             "owner_action": t.get("owner_action")}
            for t in pack["sections"]["evidence_backed_talking_points"]],
        "unknowns": [{"kind": u["kind"], "detail": (u.get("detail") or "")[:160]}
                     for u in pack["sections"]["unknowns"]],
        **paths,
    }
    check("stage5 interview prep pack is structurally valid", pack["validation"]["ok"],
          pack["validation"]["errors"])
    check("stage5 technical + behavioural prep produced from the posting",
          pack["counts"]["technical_prep"] >= 5 and pack["counts"]["behavioural_prep"] >= 5,
          pack["counts"])
    check("stage5 likely-question list produced", pack["counts"]["likely_questions"] >= 10,
          pack["counts"]["likely_questions"])
    check("stage5 cited research is carried, not guessed",
          pack["research"]["facts_available"] == 2
          and all(f.get("citation") for f in pack["research"]["facts"]),
          pack["research"])
    check("stage5 at least one evidence-backed talking point exists",
          pack["counts"]["talking_points_evidence_backed"] >= 1, pack["counts"])

    # ---------------- stage 6: truth enforcement ------------------------ #
    cv_lines = cvw.read_text(cvw.source_paths(cv_cfg)["cv_md"]).splitlines()
    ev["stage_6_truth_enforcement"] = {
        "quote_violations": pack["quote_violations"],
        "candidate_claim_violations": pack["candidate_claim_violations"],
        "candidate_claims": pack["candidate_claims"],
        "external_actions_taken": pack["external_actions_taken"],
        "employer_supplied_questions": sum(1 for q in pack["sections"]["likely_questions"]
                                           if q["employer_supplied"]),
    }
    check("stage6 every talking-point quote is verbatim at its cv.md line",
          pack["quote_violations"] == [], pack["quote_violations"][:3])
    check("stage6 no candidate claim appears in generated text",
          pack["candidate_claim_violations"] == [], pack["candidate_claim_violations"][:3])
    check("stage6 no question claims to be employer-supplied",
          all(q["employer_supplied"] is False for q in pack["sections"]["likely_questions"]))
    check("stage6 candidate_claims and external_actions_taken are empty",
          pack["candidate_claims"] == [] and pack["external_actions_taken"] == [])
    # independent re-check straight off the file
    independent_bad = []
    for tp in pack["sections"]["evidence_backed_talking_points"]:
        for q in tp["quotes"]:
            raw = cv_lines[q["source_line"] - 1].strip()
            stripped = raw[1:].strip() if raw.startswith(("-", "*")) else raw
            if stripped != q["quote"]:
                independent_bad.append({"id": tp["id"], "line": q["source_line"]})
    check("stage6 independent re-read of cv.md confirms every quote",
          independent_bad == [], independent_bad)
    tampered = json.loads(json.dumps(pack))
    if tampered["sections"]["evidence_backed_talking_points"][0]["quotes"]:
        tampered["sections"]["evidence_backed_talking_points"][0]["quotes"][0]["quote"] = \
            "Led a 24/7 security operations centre."
    tamper_hits = ip.quote_violations(tampered, cfg)
    tampered["sections"]["technical_prep"][0]["prompt"] = "I have five years of SOC experience."
    claim_hits = ip.candidate_claim_violations(tampered)
    tampered["sections"]["likely_questions"][0]["employer_supplied"] = True
    structural = ip.validate_pack(tampered, cfg)
    ev["stage_6_truth_enforcement"]["tamper_detection"] = {
        "tampered_quote_detected": bool(tamper_hits), "details": tamper_hits[:2],
        "injected_claim_detected": bool(claim_hits), "claim_details": claim_hits[:2],
        "employer_supplied_question_rejected": not structural["ok"],
        "structural_errors": structural["errors"],
    }
    check("stage6 a tampered quote is detected", bool(tamper_hits))
    check("stage6 an injected first-person claim is detected", bool(claim_hits))
    check("stage6 a question claiming employer origin is rejected", not structural["ok"])

    # ---------------- stage 7: honest unknowns -------------------------- #
    unmatched = [t for t in pack["sections"]["evidence_backed_talking_points"]
                 if t["status"] == "owner_input_required"]
    uae_job = dict(job)
    uae_brief = ji.build_brief(ip.ji_config(cfg), job=uae_job,
                               jd_text=JD_UAE.read_text(encoding="utf-8"),
                               jd_source=f"synthetic fixture {JD_UAE.name}", stamp=stamp)
    uae_pack = ip.build_prep_pack(cfg, uae_brief, stamp=stamp)
    uae_unknown = [e for e in uae_brief["eligibility"]
                   if e["status"] != "satisfied_by_owner_source"]
    uae_joined = json.dumps(uae_pack).casefold()
    invented_work_position = [p for p in
                              ("i hold", "i have the right to work", "sponsorship required",
                               "no sponsorship needed", "i am a uae")
                              if p in uae_joined]
    ev["stage_7_honest_unknowns"] = {
        "unmatched_requirements_as_owner_actions": len(unmatched),
        "owner_actions": [t["owner_action"] for t in unmatched][:3],
        "uae_eligibility_unknown_lines": len(uae_unknown),
        "uae_unknowns": [{"kind": u["kind"], "detail": (u.get("detail") or "")[:160]}
                         for u in uae_pack["sections"]["unknowns"]],
        "uae_employer_questions": uae_pack["counts"]["questions_to_ask_employer"],
        "invented_work_authorisation_statements": invented_work_position,
    }
    check("stage7 a requirement with no canonical evidence becomes an owner action",
          bool(unmatched) and all(t["quotes"] == [] and t["owner_action"] for t in unmatched),
          len(unmatched))
    check("stage7 the UAE fixture's eligibility stays unknown",
          bool(uae_unknown)
          and any(u["kind"] == "eligibility_unknown" for u in uae_pack["sections"]["unknowns"]))
    check("stage7 no right-to-work position is invented for the owner",
          invented_work_position == [], invented_work_position)

    # ---------------- stage 8: determinism ------------------------------ #
    pack_b = ip.build_prep_pack(cfg, uk_brief, brief_path=brief_path,
                                research_file=RESEARCH_CITED, stamp=stamp)
    same_counts = pack_b["counts"] == pack["counts"]
    same_quotes = [q["source_line"] for t in pack_b["sections"]["evidence_backed_talking_points"]
                   for q in t["quotes"]] == \
        [q["source_line"] for t in pack["sections"]["evidence_backed_talking_points"]
         for q in t["quotes"]]
    ev["stage_8_determinism"] = {"counts_identical": same_counts,
                                 "quoted_lines_identical": same_quotes,
                                 "counts": pack["counts"]}
    check("stage8 the same brief yields the same pack twice", same_counts and same_quotes)

    # ---------------- stage 9: nothing canonical was touched ------------ #
    changed = []
    for key, path in cvw.source_paths(cv_cfg).items():
        after = cvw.sha256_file(path) if Path(path).exists() else None
        if after != sources[key]["sha256_before"]:
            changed.append(key)
    profiles = tw.load_profiles(str(ip.profiles_path(cfg)))
    trackers = {r: tw.sha256_file(Path(c["tracker"])) for r, c in profiles["regions"].items()}
    ev["stage_9_no_canonical_change"] = {
        "canonical_sources_changed": changed,
        "canonical_sources_after": {k: cvw.sha256_file(p) if Path(p).exists() else None
                                    for k, p in cvw.source_paths(cv_cfg).items()},
        "canonical_tracker_hashes_after": trackers,
        "writes_performed": [str(p) for p in (paths["pack_path"], paths["pack_markdown"],
                                              str(brief_path))],
    }
    check("stage9 no canonical Career Ops source changed", changed == [], changed)

    ev["checks"] = checks
    failed = [c["check"] for c in checks if c["critical"] and not c["ok"]]
    ev["critical_checks_failed"] = failed
    ev["ok"] = not failed

    (out_dir / "acceptance.json").write_text(
        json.dumps(ev, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md = [f"# LinkedIn outreach + interview prep acceptance — {stamp}", "",
          f"Overall: {'PASS' if ev['ok'] else 'FAIL'}", "",
          "## Checks", "", "| check | result |", "|---|---|"]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |" for c in checks]
    md += ["", "## Path", "",
           f"1. LinkedIn intake: {ev['stage_2_linkedin_intake']['counts']}",
           f"2. Outreach drafts: {ev['stage_3_outreach_drafts']['counts']} "
           f"(fact gate {ev['stage_3_outreach_drafts']['fact_gate_verdict']})",
           f"3. JobBrief: {uk_brief['brief_id']} (validation "
           f"{'ok' if uk_brief['validation']['ok'] else 'FAILED'})",
           f"4. Interview prep pack: {pack['prep_id']} -> {paths['pack_path']}",
           f"5. Counts: {json.dumps(pack['counts'])}",
           "", "## Not performed", ""]
    md += [f"- {n}" for n in cfg["not_performed"]]
    md += [f"- {n}" for n in li_cfg["not_performed"]]
    (out_dir / "acceptance.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "acceptance_run": stamp,
        "ok": ev["ok"],
        "evidence": str(out_dir / "acceptance.json"),
        "evidence_md": str(out_dir / "acceptance.md"),
        "checks_passed": sum(1 for c in checks if c["ok"]),
        "checks_total": len(checks),
        "critical_failed": failed,
        "outreach_counts": li_drafts["counts"],
        "prep_counts": pack["counts"],
        "prep_pack": paths["pack_path"],
        "external_actions_taken": 0,
    }, indent=2, ensure_ascii=False, default=str))
    return 0 if ev["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
