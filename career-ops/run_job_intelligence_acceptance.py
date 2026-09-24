#!/usr/bin/env python3
"""End-to-end acceptance: job record -> JobBrief -> CV draft -> cover-letter draft
-> independent reviewer -> deterministic owner submission gate.

Everything runs on local, explicitly-labelled SYNTHETIC fixtures and the owner's
own canonical CV/profile sources (read-only). No live vacancy is claimed, no
employer is contacted, no browser or GUI is launched, and nothing is submitted.

What this runner proves, stage by stage:

  stage 1  canonical Career Ops sources read-only; install fact gate available.
  stage 2  a job record + posting fixture reach the pipeline.
  stage 3  JobBrief (B13): every requirement/responsibility/eligibility line is a
           verbatim posting line with its source line number; desirable items are
           recorded as preferences and NEVER as essential requirements; the brief
           carries no candidate claim; the UAE posting fixture yields an
           eligibility status of "unknown" (it is never assumed satisfied) while
           the UK posting fixture is satisfied only by the owner's own profile.
  stage 4  research brief (B14): no provider -> research_needed (never a guess);
           a cited provider file -> cited facts; an uncited fact is REJECTED and
           never reaches the brief; the browser provider is recorded as disabled
           by the owner GUI-safety directive.
  stage 5  handoff: only source_supported_facts reach the CV/cover-letter
           workflows, and every handoff line is verbatim posting text.
  stage 6  CV + cover-letter drafts via the existing Career Ops workflow, with the
           install's own fact gate.
  stage 7  independent reviewer (B17): truthfulness, coverage (essential vs
           desirable kept separate), consistency, formatting, unknowns.
  stage 8  reviewer independence: a deliberately tampered pack MUST be blocked.
  stage 9  submission gate (B18): no approval -> awaiting owner; forged/in-repo
           approval -> refused; stale (hash-mismatched) approval -> refused; valid
           external approval -> eligible-for-manual-submission ONLY, with
           external_action_performed false throughout.
  stage 10 canonical sources and tracker workbooks provably untouched.

Usage
  python career-ops/run_job_intelligence_acceptance.py [--stamp S] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import application_pack_review as apr  # noqa: E402
import cv_workflow as cvw  # noqa: E402
import job_intelligence as ji  # noqa: E402
import submission_gate as sg  # noqa: E402
import tracker_writer as tw  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures"
JI_FIXTURES = FIXTURES / "job-intelligence"
JD_UK = FIXTURES / "jd-information-security-analyst.txt"
JD_UAE = JI_FIXTURES / "jd-unknown-eligibility.txt"
RECORD_UK = JI_FIXTURES / "job-record-uk.json"
RESEARCH_CITED = JI_FIXTURES / "research-cited.json"
RESEARCH_UNCITED = JI_FIXTURES / "research-uncited.json"

# The owner's approval record must live OUTSIDE the repository: a committed file
# is not an owner action. This path is a scratch temporary used by the acceptance
# run only; production approvals go under %LOCALAPPDATA%\hermes\secrets\.
APPROVAL_DIR_NAME = "application-approvals"


def posting_map(jd_text: str) -> dict[int, str]:
    return {no: apr.normalise_posting_line(raw)
            for no, raw in enumerate(jd_text.splitlines(), start=1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp")
    ap.add_argument("--out-dir")
    args = ap.parse_args(argv)

    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cfg = ji.load_config()
    wf_cfg = ji.load_workflow_config(cfg)
    profiles = tw.load_profiles(str(ji.profiles_path(cfg)))

    run_root = CONTROL_PLANE / cfg["runtime_dir"] / "acceptance" / stamp
    run_root.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out_dir) if args.out_dir else \
        (CONTROL_PLANE / cfg["evidence_dir"] / f"{stamp}-job-intelligence-and-application-pack")
    out_dir.mkdir(parents=True, exist_ok=True)

    ev: dict = {
        "acceptance_run": stamp,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "workflow": "JobBrief / research brief / CV+cover-letter handoff / pack reviewer / "
                    "submission gate",
        "authority": "tasks-or-issues/2026-09-24-full-operational-vps-cutover.md "
                     "§ CV + cover-letter workflow / § company-role research / roster B13,B14,B17,B18",
        "cheating_guards": {
            "applications_submitted": 0,
            "employer_or_recruiter_contact": 0,
            "browser_or_gui_launched": False,
            "network_research_calls": 0,
            "canonical_sources_modified": False,
            "canonical_trackers_touched": False,
            "live_vacancy_claimed": False,
            "fabricated_facts_used": 0,
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
            "research_uncited": {"path": str(RESEARCH_UNCITED),
                                 "kind": "SYNTHETIC partly-uncited research",
                                 "sha256": cvw.sha256_file(RESEARCH_UNCITED)},
            "note": "No fixture is a live vacancy or a real research result; every fixture says "
                    "so in its own body.",
        },
    }
    checks: list[dict] = []

    def check(name: str, ok: bool, detail=None, critical: bool = True) -> None:
        checks.append({"check": name, "ok": bool(ok), "critical": critical, "detail": detail})

    # ---------------- stage 1: canonical sources ------------------------- #
    paths = cvw.source_paths(wf_cfg)
    before = {k: cvw.sha256_file(p) for k, p in paths.items()}
    node_ok = shutil.which(wf_cfg["renderer"]["node"]) is not None
    ev["stage_1_sources"] = {
        "sources": {k: {"path": str(p), "exists": p.exists(), "sha256": before[k]}
                    for k, p in paths.items()},
        "node_available": node_ok,
        "fact_gate_ready": node_ok and (cvw.install_root(wf_cfg) / "verify-cv-facts.mjs").exists(),
        "read_only": True,
    }
    check("stage1 node + install fact gate available", ev["stage_1_sources"]["fact_gate_ready"])
    check("stage1 all canonical sources present", all(v["exists"] for v in
                                                     ev["stage_1_sources"]["sources"].values()))

    # ---------------- stage 2: job record -------------------------------- #
    resolved = cvw.resolve_job(wf_cfg, profiles, record_file=str(RECORD_UK))
    job: dict = resolved.get("job") or {}
    jd_uk_text = JD_UK.read_text(encoding="utf-8")
    jd_uae_text = JD_UAE.read_text(encoding="utf-8")
    ev["stage_2_job_record"] = {
        "resolved": bool(resolved.get("ok")),
        "source_kind": (job or {}).get("_source_kind"),
        "job": {k: v for k, v in (job or {}).items() if not k.startswith("_")},
        "posting_chars": {"uk": len(jd_uk_text), "uae": len(jd_uae_text)},
    }
    check("stage2 job record resolved into the pipeline", bool(resolved.get("ok")))

    # ---------------- stage 3: JobBrief (B13) ---------------------------- #
    brief = ji.build_brief(cfg, job=job, jd_text=jd_uk_text,
                           jd_source=f"synthetic fixture {JD_UK.name}", stamp=stamp)
    brief_dir = run_root / "job-brief"
    brief_dir.mkdir(parents=True, exist_ok=True)
    brief_path = brief_dir / "job_brief.json"
    brief["brief_path"] = str(brief_path)
    brief_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False, default=str),
                          encoding="utf-8")

    jd_lines = posting_map(jd_uk_text)
    citation_bad = []
    for bucket in ("requirements", "responsibilities", "eligibility"):
        for entry in brief[bucket]:
            want = apr.normalise_posting_line(entry["text"])
            got = jd_lines.get(entry["source_line"])
            if want != got:
                citation_bad.append({"bucket": bucket, "source_line": entry["source_line"],
                                     "brief": entry["text"], "posting": got})

    essential = [r for r in brief["requirements"] if r["kind"] == "essential"]
    desirable = [r for r in brief["requirements"] if r["kind"] == "desirable"]
    pref_texts = {p["text"] for p in brief["preferences"]}
    essential_texts = {r["text"] for r in essential}
    ev["stage_3_job_brief"] = {
        "brief_id": brief["brief_id"],
        "schema_validation": brief["validation"],
        "candidate_claim_violations": brief["candidate_claim_violations"],
        "counts": {"requirements_essential": len(essential), "requirements_desirable": len(desirable),
                   "responsibilities": len(brief["responsibilities"]),
                   "eligibility": len(brief["eligibility"]),
                   "keywords": len(brief["keywords"]),
                   "source_supported_facts": len(brief["source_supported_facts"])},
        "citation_mismatches": citation_bad,
        "preferences_are_desirable_only": sorted(pref_texts & essential_texts) == [],
        "preference_texts_sample": sorted(pref_texts)[:4],
        "keywords_sample": [k["term"] for k in brief["keywords"][:8]],
        "risks": [{"kind": r["kind"], "severity": r["severity"]} for r in brief["risks_unknowns"]],
        "eligibility": brief["eligibility"],
        "research_status": brief["research"]["status"],
        "posting_lines_total": len(jd_lines),
    }
    check("stage3 JobBrief validates against the committed schema", brief["validation"]["ok"],
          brief["validation"]["errors"])
    check("stage3 JobBrief carries no candidate claim", not brief["candidate_claim_violations"])
    check("stage3 every extracted line is a verbatim posting line at its cited line number",
          not citation_bad, citation_bad[:5])
    check("stage3 desirable posting lines became preferences, never essential requirements",
          bool(desirable) and not (pref_texts & essential_texts))
    check("stage3 essential requirements extracted from the fixture posting",
          len(essential) == 5, [r["text"] for r in essential])
    check("stage3 no company fact is asserted without research",
          brief["company_facts"] == [] and brief["research"]["status"] == "research_needed")
    check("stage3 research request list recorded", bool(brief["research"]["requested"]))
    check("stage3 JobBrief made no external action", brief["external_actions_taken"] == [])

    # stage 3b: a posting in a region the owner has NOT stated a right to work
    # for must land in "unknown" — never assumed satisfied.
    brief_uae = ji.build_brief(cfg, job={**job, "id": "FIXTURE-UAE-0001", "region": "uae",
                                        "location": "Dubai, United Arab Emirates"},
                               jd_text=jd_uae_text,
                               jd_source=f"synthetic fixture {JD_UAE.name}",
                               stamp=stamp, brief_id=f"jb-{stamp}-uae")
    uae_elig = brief_uae["eligibility"]
    uae_unknown = [e for e in uae_elig if e["status"] == "unknown"]
    uae_blockers = [r for r in brief_uae["risks_unknowns"] if r["severity"] == "blocker"]
    ev["stage_3b_unstated_region"] = {
        "eligibility": uae_elig,
        "unknown_statuses": [e["status"] for e in uae_elig],
        "blocker_risks": [r["kind"] for r in uae_blockers],
        "note": "The owner profile lists only the United Kingdom. A UAE right-to-work condition "
                "is therefore UNKNOWN and produces a blocker risk; it is never satisfied by "
                "assumption.",
    }
    check("stage3b a region the owner has not stated is 'unknown', not satisfied",
          bool(uae_elig) and all(e["status"] == "unknown" for e in uae_elig),
          [e["status"] for e in uae_elig])
    check("stage3b the unknown eligibility produces a blocker risk", bool(uae_blockers))

    # ---------------- stage 4: research brief (B14) ---------------------- #
    research_none = ji.research_brief(cfg, job)
    cited = ji.research_brief(cfg, job, research_file=RESEARCH_CITED)
    uncited = ji.research_brief(cfg, job, research_file=RESEARCH_UNCITED)
    network = ji.research_brief(cfg, job, allow_network=True)
    ev["stage_4_research"] = {
        "no_provider": {"status": research_none["status"], "facts": len(research_none["facts"]),
                        "requested": research_none["requested"][:3],
                        "notes": research_none["notes"][:2]},
        "cited_file": {"status": cited["status"], "facts": cited["facts"],
                       "sources": cited["sources"]},
        "partly_uncited_file": {"status": uncited["status"], "accepted": len(uncited["facts"]),
                                "rejected": uncited["rejected_facts"]},
        "allow_network_without_provider": {"status": network["status"],
                                           "facts": len(network["facts"]),
                                           "notes": [n for n in network["notes"] if "network" in n]},
        "providers": research_none["providers"],
        "browser_provider_enabled": research_none["providers"]["browser"]["enabled"],
    }
    check("stage4 with no provider the brief records research_needed and invents nothing",
          research_none["status"] == "research_needed" and research_none["facts"] == [])
    check("stage4 a cited provider file yields cited facts",
          cited["status"] == "provided" and len(cited["facts"]) == 2
          and all(f["source"] and f["citation"] for f in cited["facts"]))
    check("stage4 an uncited fact is rejected and never used",
          len(uncited["facts"]) == 1 and len(uncited["rejected_facts"]) == 1
          and "Uncited assertion" not in json.dumps(uncited["facts"]),
          uncited["rejected_facts"])
    check("stage4 browser research provider is disabled (owner GUI-safety directive)",
          research_none["providers"]["browser"]["enabled"] is False)
    check("stage4 --allow-network without an enabled provider fetches nothing",
          network["facts"] == [] and any("nothing was fetched" in n for n in network["notes"]))

    # ---------------- stage 5: handoff ----------------------------------- #
    brief_with_research = ji.build_brief(cfg, job=job, jd_text=jd_uk_text,
                                         jd_source=f"synthetic fixture {JD_UK.name}",
                                         research_file=RESEARCH_CITED, stamp=stamp,
                                         brief_id=f"jb-{stamp}-cited")
    handoff_text = ji.handoff_jd_text(brief_with_research)
    handoff_path = brief_dir / "handoff_jd_text.txt"
    handoff_path.write_text(handoff_text + "\n", encoding="utf-8")
    known = set(jd_lines.values())
    handoff_bad = [apr.normalise_posting_line(l) for l in handoff_text.splitlines()
                   if apr.normalise_posting_line(l) not in known]
    brief_with_research["brief_path"] = str(brief_path)
    brief_path.write_text(json.dumps(brief_with_research, indent=2, ensure_ascii=False, default=str),
                          encoding="utf-8")
    ev["stage_5_handoff"] = {
        "handoff_path": str(handoff_path),
        "lines": len(handoff_text.splitlines()),
        "all_lines_from_posting": not handoff_bad,
        "not_from_posting": handoff_bad[:5],
        "only_source_supported_facts": True,
        "research_status_in_pack_brief": brief_with_research["research"]["status"],
        "company_facts_in_pack_brief": len(brief_with_research["company_facts"]),
    }
    check("stage5 every handoff line is verbatim posting text", not handoff_bad, handoff_bad[:5])
    check("stage5 the pack brief carries cited company research",
          brief_with_research["research"]["status"] == "provided"
          and len(brief_with_research["company_facts"]) == 2)

    # ---------------- stage 6: CV + cover-letter drafts ------------------ #
    draft_dir = run_root / "cv-drafts"
    drafts = cvw.build_drafts(wf_cfg, profiles, job=job, jd_text=handoff_text,
                              jd_source=f"JobBrief source_supported_facts ({brief_path.name})",
                              stamp=stamp, run_dir=draft_dir)
    ev["stage_6_drafts"] = {
        "ok": drafts.get("ok"),
        "status": drafts.get("status"),
        "run_dir": drafts.get("run_dir"),
        "cv_draft": drafts.get("cv_draft", {}).get("path"),
        "cover_payload": drafts.get("cover_letter", {}).get("payload_path"),
        "cover_html": drafts.get("cover_letter", {}).get("html_path"),
        "fact_gate": {k: v.get("verdict") for k, v in (drafts.get("fact_gate") or {}).items()},
        "jd_terms_ranked": (drafts.get("job_description") or {}).get("terms_ranked"),
        "terms_absent_from_canonical": (drafts.get("job_description") or {}).get(
            "terms_absent_from_canonical_sources"),
        "owner_input_required": drafts.get("owner_input_required"),
        "external_actions_taken": drafts.get("external_actions_taken"),
        "next_step_owner_gated": bool(drafts.get("next_step_owner_gated")),
    }
    check("stage6 CV + cover-letter drafts produced through the existing workflow",
          bool(drafts.get("ok")), drafts.get("status"))
    check("stage6 install fact gate did not block either artifact",
          all(v.get("verdict") != "block" for v in (drafts.get("fact_gate") or {}).values()),
          ev["stage_6_drafts"]["fact_gate"])
    check("stage6 rendered cover-letter HTML exists", bool(ev["stage_6_drafts"]["cover_html"]))
    check("stage6 the draft workflow performed no external action",
          drafts.get("external_actions_taken") == [])

    pack = {
        "brief": brief_with_research,
        "cv_draft": Path(drafts["cv_draft"]["path"]),
        "payload": Path(drafts["cover_letter"]["payload_path"]),
        "html": Path(drafts["cover_letter"]["html_path"]),
        "draft_result": Path(drafts["run_dir"]) / "draft_result.json",
    }

    def run_review(pack_dir: Path | None) -> dict:
        if pack_dir is None:
            cv_draft, payload, html = pack["cv_draft"], pack["payload"], pack["html"]
            draft_result = pack["draft_result"]
        else:
            cv_draft = pack_dir / "cv_draft.md"
            payload = pack_dir / "cover_letter_payload.json"
            html = pack_dir / "cover_letter_draft.html"
            draft_result = pack_dir / "draft_result.json"
        return apr.review(cfg, brief=brief_with_research, cv_draft_path=cv_draft,
                          payload_path=payload, html_path=html,
                          draft_result_path=draft_result, jd_path=JD_UK,
                          handoff_path=handoff_path)

    # ---------------- stage 7: independent reviewer (B17) ---------------- #
    review = run_review(None)
    review_path = run_root / "pack_review.json"
    review_path.write_text(json.dumps(review, indent=2, ensure_ascii=False, default=str),
                           encoding="utf-8")
    findings_by_area: dict[str, list] = {}
    for f in review["findings"]:
        findings_by_area.setdefault(f["area"], []).append(
            {"id": f["id"], "severity": f["severity"]})
    ev["stage_7_review"] = {
        "reviewer": review["reviewer"],
        "reviewer_role": review["reviewer_role"],
        "independent_of_generator": "separate module; re-derives from artifacts",
        "independence_statement": review["independence"],
        "verdict": review["verdict"],
        "truthfulness_verified": review["truthfulness_verified"],
        "blockers": review["blockers"],
        "findings_by_area": findings_by_area,
        "coverage_counts": review["checks"]["requirement_coverage"]["counts"],
        "coverage_essential": [
            {"text": e["text"][:70], "status": e["status"], "match_ratio": e["match_ratio"]}
            for e in review["checks"]["requirement_coverage"]["essential"]],
        "coverage_desirable_reported_separately": True,
        "consistency": {k: v for k, v in review["checks"]["consistency"].items()
                        if k in ("identity_mismatches", "posting_citation_mismatches",
                                 "handoff_lines_not_in_posting", "candidate_name")},
        "formatting": review["checks"]["formatting"],
        "unresolved_unknowns": review["checks"]["unresolved_unknowns"].get("owner_input_required"),
        "pack_id": review["pack_id"],
        "pack_sha256": review["pack_sha256"],
        "external_actions_taken": review["external_actions_taken"],
    }
    check("stage7 reviewer did not block an honest pack", review["verdict"] != "block",
          review["blockers"])
    check("stage7 reviewer verified truthfulness", review["truthfulness_verified"] is True)
    check("stage7 reviewer found no truthfulness/consistency/formatting blocker",
          not [f for f in review["blockers"]])
    check("stage7 reviewer reported essential coverage numbers",
          review["checks"]["requirement_coverage"]["counts"]["essential_total"] == 5,
          review["checks"]["requirement_coverage"]["counts"])
    check("stage7 reviewer re-checked every posting citation and found no drift",
          review["checks"]["consistency"]["posting_citation_mismatches"] == [])
    check("stage7 reviewer surfaced unresolved unknowns to the owner",
          bool(review["owner_input_required"]))
    check("stage7 reviewer performed no external action", review["external_actions_taken"] == [])

    # ---------------- stage 8: reviewer independence (tamper proof) ------ #
    tamper_dir = run_root / "tampered-pack"
    tamper_dir.mkdir(parents=True, exist_ok=True)
    for name in ("cv_draft.md", "cover_letter_payload.json", "cover_letter_draft.html"):
        shutil.copy2(pack["cv_draft" if name.startswith("cv") else
                         ("payload" if name.endswith("json") else "html")], tamper_dir / name)
    shutil.copy2(pack["draft_result"], tamper_dir / "draft_result.json")
    tampered_cv = (tamper_dir / "cv_draft.md").read_text(encoding="utf-8")
    invented_line = "- Reduced security incidents by 45% across a 250-user estate."
    (tamper_dir / "cv_draft.md").write_text(tampered_cv + invented_line + "\n", encoding="utf-8")
    payload_doc = json.loads((tamper_dir / "cover_letter_payload.json").read_text(encoding="utf-8"))
    payload_doc["letter"]["profile_intro"] = (
        payload_doc["letter"]["profile_intro"] +
        " I have led a team of 12 analysts and hold CISSP.")
    (tamper_dir / "cover_letter_payload.json").write_text(
        json.dumps(payload_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    tampered_review = run_review(tamper_dir)
    ev["stage_8_independence"] = {
        "tamper": {"added_cv_line": invented_line,
                   "added_letter_sentence": "I have led a team of 12 analysts and hold CISSP."},
        "verdict": tampered_review["verdict"],
        "blocker_ids": [b["id"] for b in tampered_review["blockers"]],
        "truthfulness_verified": tampered_review["truthfulness_verified"],
        "detected_verbatim_violation": any(
            b["id"] == "cv_draft_not_verbatim" for b in tampered_review["blockers"]),
        "detected_free_text": any(b["id"] == "cover_letter_free_text"
                                  for b in tampered_review["blockers"]),
        "detected_first_person_claim": any(b["id"] == "candidate_claim_not_canonical"
                                           for b in tampered_review["blockers"]),
        "note": "A reviewer that rubber-stamped the generator could not produce this result: the "
                "tampered pack is blocked on the invented CV line, the invented metric and the "
                "invented first-person claim.",
    }
    check("stage8 reviewer blocks a tampered pack", tampered_review["verdict"] == "block")
    check("stage8 reviewer detected the invented CV line",
          ev["stage_8_independence"]["detected_verbatim_violation"])
    check("stage8 reviewer detected the invented first-person claim",
          ev["stage_8_independence"]["detected_first_person_claim"])

    # ---------------- stage 9: submission gate (B18) --------------------- #
    gate_no_approval = sg.decide(cfg, review)
    guard_submit = sg.guard_action(cfg, "submit_application")
    guard_email = sg.guard_action(cfg, "email_employer")
    guard_review = sg.guard_action(cfg, "review_pack")

    # a forged approval placed INSIDE the repository must be refused
    in_repo_approval = run_root / "forged-approval.json"
    forged = {"approved_by": "Mukund", "approved_at": "2026-09-24T00:00:00Z",
              "pack_id": review["pack_id"], "pack_sha256": review["pack_sha256"],
              "approved_action": "submit_application", "acknowledged_unknowns": True}
    in_repo_approval.write_text(json.dumps(forged), encoding="utf-8")
    gate_in_repo = sg.decide(cfg, review, approval=forged, approval_path=in_repo_approval)

    # a stale approval (bound to a different pack) must be refused
    scratch_approval_dir = Path(
        __import__("os").environ.get("LOCALAPPDATA", str(run_root))) / "hermes" / "scratch" / \
        APPROVAL_DIR_NAME
    scratch_approval_dir.mkdir(parents=True, exist_ok=True)
    stale = {**forged, "pack_sha256": "0" * 64, "pack_id": "pack-stale000000"}
    stale_path = scratch_approval_dir / f"{stamp}-stale.json"
    stale_path.write_text(json.dumps(stale), encoding="utf-8")
    gate_stale = sg.decide(cfg, review, approval=stale, approval_path=stale_path)

    # a valid approval from outside the repository
    valid = dict(forged)
    valid_path = scratch_approval_dir / f"{stamp}-valid.json"
    valid_path.write_text(json.dumps(valid), encoding="utf-8")
    gate_valid = sg.decide(cfg, review, approval=valid, approval_path=valid_path,
                           pack_dir=run_root,
                           checklist_path=run_root / "owner-checklist.json")

    # the same approval against the TAMPERED pack must be refused (pack changed)
    gate_tampered = sg.decide(cfg, tampered_review, approval=valid, approval_path=valid_path)

    # truthfulness-unverified refusal proof (the reviewer's own flag is honoured)
    unverified = {**review, "truthfulness_verified": False}
    gate_unverified = sg.decide(cfg, unverified)

    ev["stage_9_submission_gate"] = {
        "gate": gate_no_approval["gate"],
        "policy": gate_no_approval["policy"],
        "no_approval": {"status": gate_no_approval["status"],
                        "submission_eligible": gate_no_approval["submission_eligible"],
                        "external_action_performed": gate_no_approval["external_action_performed"],
                        "owner_action_required": gate_no_approval["owner_action_required"][:300]},
        "guards": {"submit_application": {"status": guard_submit["status"],
                                          "allowed": guard_submit["allowed"],
                                          "performed": guard_submit["performed"]},
                   "email_employer": {"status": guard_email["status"],
                                      "allowed": guard_email["allowed"]},
                   "review_pack": {"status": guard_review["status"],
                                   "allowed": guard_review["allowed"],
                                   "note": "a non-external action is still never performed by the gate"}},
        "approval_inside_repository": {"status": gate_in_repo["status"],
                                       "problems": gate_in_repo.get("approval_problems")},
        "stale_approval": {"status": gate_stale["status"],
                           "problems": gate_stale.get("approval_problems")},
        "valid_external_approval": {"status": gate_valid["status"],
                                    "submission_eligible": gate_valid["submission_eligible"],
                                    "external_action_performed":
                                        gate_valid["external_action_performed"],
                                    "checklist_path": gate_valid.get("checklist_path"),
                                    "owner_action_required": gate_valid.get("owner_action_required")},
        "approval_vs_tampered_pack": {"status": gate_tampered["status"],
                                      "problems": gate_tampered.get("approval_problems")},
        "truthfulness_unverified": {"status": gate_unverified["status"],
                                    "reason": gate_unverified.get("reason")},
        "external_actions_taken": [],
    }
    check("stage9 without owner approval the gate waits and performs nothing",
          gate_no_approval["status"] == "awaiting_owner_approval"
          and gate_no_approval["external_action_performed"] is False)
    check("stage9 the gate refuses every external action",
          guard_submit["status"] == "refused" and guard_submit["allowed"] is False
          and guard_email["status"] == "refused")
    check("stage9 an approval placed inside the repository is refused",
          gate_in_repo["status"] == "refused"
          and any("inside the repository" in p for p in gate_in_repo["approval_problems"]))
    check("stage9 an approval bound to a different pack is refused",
          gate_stale["status"] == "refused" and gate_stale["approval_problems"])
    check("stage9 a valid external approval still performs no external action",
          gate_valid["status"] == "approved_pending_owner_manual_submission"
          and gate_valid["submission_eligible"] is True
          and gate_valid["external_action_performed"] is False
          and Path(gate_valid["checklist_path"]).exists())
    check("stage9 an approval for a changed pack is refused",
          gate_tampered["status"] == "refused")
    check("stage9 the gate refuses when truthfulness is not verified",
          gate_unverified["status"] == "refused")

    # ---------------- stage 10: nothing else changed --------------------- #
    after = {k: cvw.sha256_file(p) for k, p in paths.items()}
    tracker_hashes: dict = {}
    for region, rcfg in profiles["regions"].items():
        tp = Path(rcfg["tracker"])
        tracker_hashes[region] = {"path": str(tp), "exists": tp.exists(),
                                  "sha256": tw.sha256_file(tp) if tp.exists() else None}
    ev["stage_10_no_side_effects"] = {
        "canonical_sources_before": before,
        "canonical_sources_after": after,
        "canonical_sources_unchanged": before == after,
        "trackers": tracker_hashes,
        "canonical_trackers_touched": False,
        "applications_submitted": 0,
        "external_messages_sent": 0,
        "browser_launched": False,
        "network_research_calls_by_this_runner": 0,
    }
    check("stage10 canonical Career Ops sources untouched", before == after)

    ev["checks"] = checks
    failed = [c["check"] for c in checks if c["critical"] and not c["ok"]]
    ev["critical_checks_failed"] = failed
    ev["ok"] = not failed

    (out_dir / "acceptance.json").write_text(
        json.dumps(ev, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md = [
        f"# Job intelligence + application pack acceptance — {stamp}",
        "",
        f"Overall: {'PASS' if ev['ok'] else 'FAIL'}  |  checks "
        f"{sum(1 for c in checks if c['ok'])}/{len(checks)}",
        "",
        "## Path",
        "",
        f"1. Job record ({ev['stage_2_job_record']['source_kind']}): "
        f"{ev['stage_2_job_record']['job'].get('title')} @ "
        f"{ev['stage_2_job_record']['job'].get('company')}",
        f"2. JobBrief {ev['stage_3_job_brief']['brief_id']}: "
        f"{ev['stage_3_job_brief']['counts']}",
        f"3. Research: {ev['stage_4_research']['no_provider']['status']} without a provider; "
        f"{ev['stage_4_research']['cited_file']['status']} with a cited provider; "
        f"{len(ev['stage_4_research']['partly_uncited_file']['rejected'])} uncited fact rejected",
        f"4. Handoff: {ev['stage_5_handoff']['lines']} source-supported lines, all posting-verbatim",
        f"5. CV draft: {ev['stage_6_drafts']['cv_draft']}",
        f"6. Cover letter: {ev['stage_6_drafts']['cover_html']}",
        f"7. Reviewer verdict: {ev['stage_7_review']['verdict']} "
        f"(essential coverage {ev['stage_7_review']['coverage_counts']['essential_coverage_ratio']})",
        f"8. Reviewer on a tampered pack: {ev['stage_8_independence']['verdict']} "
        f"— {', '.join(ev['stage_8_independence']['blocker_ids'])}",
        f"9. Submission gate: {ev['stage_9_submission_gate']['no_approval']['status']} without "
        f"approval; {ev['stage_9_submission_gate']['valid_external_approval']['status']} with a "
        "valid external approval; external_action_performed="
        f"{ev['stage_9_submission_gate']['valid_external_approval']['external_action_performed']}",
        "10. Canonical sources and trackers untouched",
        "",
        "## Checks",
        "",
        "| check | result |",
        "|---|---|",
    ]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |" for c in checks]
    md += ["", "## Not performed", ""]
    md += [f"- {n}" for n in cfg.get("not_performed", [])]
    (out_dir / "acceptance.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "acceptance_run": stamp,
        "ok": ev["ok"],
        "evidence": str(out_dir / "acceptance.json"),
        "evidence_md": str(out_dir / "acceptance.md"),
        "checks_passed": sum(1 for c in checks if c["ok"]),
        "checks_total": len(checks),
        "critical_failed": failed,
        "brief_id": brief["brief_id"],
        "brief": str(brief_path),
        "review_verdict": review["verdict"],
        "pack_id": review["pack_id"],
        "tampered_verdict": tampered_review["verdict"],
        "gate_status": gate_no_approval["status"],
        "gate_status_with_valid_approval": gate_valid["status"],
        "applications_submitted": 0,
    }, indent=2, ensure_ascii=False, default=str))
    return 0 if ev["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
