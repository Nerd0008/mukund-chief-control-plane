#!/usr/bin/env python3
"""Tests for job intelligence (B13/B14), the pack reviewer (B17) and the
submission gate (B18).

Offline and non-destructive: the canonical Career Ops sources (cv.md,
config/profile.yml) are only ever read, every artifact goes to tmp_path, no
network call is made, no browser is launched and nothing is submitted.

Run:  python -m pytest career-ops/tests/test_job_intelligence.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
CONTROL_PLANE = CAREER_OPS.parent
sys.path.insert(0, str(CAREER_OPS))

import application_pack_review as apr  # noqa: E402
import cv_workflow as cvw  # noqa: E402
import job_intelligence as ji  # noqa: E402
import submission_gate as sg  # noqa: E402

FIXTURES = CAREER_OPS / "tests" / "fixtures"
JI_FIXTURES = FIXTURES / "job-intelligence"
JD_UK = FIXTURES / "jd-information-security-analyst.txt"
JD_UAE = JI_FIXTURES / "jd-unknown-eligibility.txt"
RECORD_UK = JI_FIXTURES / "job-record-uk.json"
RESEARCH_CITED = JI_FIXTURES / "research-cited.json"
RESEARCH_UNCITED = JI_FIXTURES / "research-uncited.json"

CFG = ji.load_config()
WF_CFG = ji.load_workflow_config(CFG)


def uae_job() -> dict:
    record = json.loads(RECORD_UK.read_text(encoding="utf-8"))
    return {**record, "id": "FIXTURE-UAE-0001", "region": "uae",
            "location": "Dubai, United Arab Emirates", "_region": "uae",
            "_source_kind": "synthetic-fixture-job-record"}


def uk_brief(**kwargs) -> dict:
    """Build a JobBrief for the synthetic UK fixture posting."""
    job = json.loads(RECORD_UK.read_text(encoding="utf-8"))
    job = {k: v for k, v in job.items() if not k.startswith("_")}
    job["_region"] = job.get("region")
    job["_source_kind"] = job.get("source_kind")
    return ji.build_brief(CFG, job=job, jd_text=JD_UK.read_text(encoding="utf-8"),
                          jd_source=f"fixture {JD_UK.name}", **kwargs)


# --------------------------------------------------------------------------- #
# B13 — JD analysis
# --------------------------------------------------------------------------- #

def test_brief_extracts_only_verbatim_posting_lines():
    brief = uk_brief()
    lines = {no: apr.normalise_posting_line(raw)
             for no, raw in enumerate(JD_UK.read_text(encoding="utf-8").splitlines(), start=1)}
    for bucket in ("requirements", "responsibilities", "eligibility"):
        for entry in brief[bucket]:
            assert apr.normalise_posting_line(entry["text"]) == lines[entry["source_line"]], entry
    assert brief["requirements"] and brief["responsibilities"]


def test_brief_marks_desirable_items_as_preferences_not_requirements():
    brief = uk_brief()
    essential = {r["text"] for r in brief["requirements"] if r["kind"] == "essential"}
    desirable = {r["text"] for r in brief["requirements"] if r["kind"] == "desirable"}
    pref = {p["text"] for p in brief["preferences"]}
    assert desirable and not (essential & desirable)
    assert pref == desirable
    assert all("never a fact about the candidate" in p["note"] for p in brief["preferences"])


def test_brief_never_invents_a_requirement():
    # every requirement is traceable to the posting; nothing else may appear.
    brief = uk_brief()
    posting = JD_UK.read_text(encoding="utf-8")
    for entry in brief["requirements"] + brief["responsibilities"]:
        assert entry["text"] in posting


def test_location_and_right_to_work_lines_are_not_applicant_requirements():
    brief = uk_brief()
    texts = [r["text"] for r in brief["requirements"]]
    assert not any(t.casefold().startswith("right to work") for t in texts)
    assert not any(t.casefold().startswith("location") for t in texts)
    assert any(e["category"] == "right_to_work" for e in brief["eligibility"])


def test_brief_carries_no_candidate_claim_and_validates():
    brief = uk_brief()
    assert brief["candidate_claims"] == []
    assert brief["candidate_claim_violations"] == []
    assert brief["validation"]["ok"], brief["validation"]["errors"]
    assert brief["external_actions_taken"] == []


def test_candidate_claim_scanner_rejects_first_person_claims():
    polluted = {"requirements": [{"text": "I have 5 years of SOC experience."}]}
    violations = ji.candidate_claim_violations(polluted)
    assert violations and violations[0]["pattern"]


def test_eligibility_uk_satisfied_only_by_owner_source():
    brief = uk_brief()
    rtw = [e for e in brief["eligibility"] if e["category"] == "right_to_work"]
    assert rtw and rtw[0]["status"] == "satisfied_by_owner_source"
    assert "authorized_in" in (rtw[0]["owner_source"] or "")
    assert rtw[0]["owner_source_line"]


def test_eligibility_unstated_region_is_unknown_and_blocked():
    brief = ji.build_brief(CFG, job=uae_job(),
                           jd_text=JD_UAE.read_text(encoding="utf-8"),
                           jd_source="fixture")
    rtw = [e for e in brief["eligibility"] if e["category"] == "right_to_work"]
    assert rtw and rtw[0]["status"] == "unknown"
    assert any(r["severity"] == "blocker" for r in brief["risks_unknowns"])
    assert not any(e["status"] == "satisfied_by_owner_source" for e in brief["eligibility"])


def test_missing_posting_is_a_blocker_risk_not_a_guess():
    brief = ji.build_brief(CFG, job=json.loads(RECORD_UK.read_text(encoding="utf-8")),
                           jd_text="", jd_source=None)
    kinds = [r["kind"] for r in brief["risks_unknowns"]]
    assert "job_description_missing" in kinds
    assert brief["requirements"] == []
    assert brief["provenance"]["job_description"]["available"] is False


def test_schema_validation_catches_corruption():
    brief = uk_brief()
    bad = json.loads(json.dumps(brief))
    bad.pop("candidate_claims")
    bad["requirements"][0]["kind"] = "wishlist"
    result = ji.validate_brief(bad, CFG)
    assert not result["ok"]
    assert any("candidate_claims" in e for e in result["errors"])
    assert any("essential/desirable" in e for e in result["errors"])


# --------------------------------------------------------------------------- #
# B14 — research brief
# --------------------------------------------------------------------------- #

def test_research_without_provider_records_research_needed():
    brief = uk_brief()
    assert brief["research"]["status"] == "research_needed"
    assert brief["company_facts"] == []
    assert brief["research"]["requested"]
    assert brief["research"]["providers"]["browser"]["enabled"] is False


def test_research_accepts_only_cited_facts():
    brief = uk_brief(research_file=RESEARCH_CITED)
    assert brief["research"]["status"] == "provided"
    assert len(brief["company_facts"]) == 2
    for fact in brief["company_facts"]:
        assert fact["source"] and fact["citation"]


def test_research_rejects_uncited_facts():
    brief = uk_brief(research_file=RESEARCH_UNCITED)
    assert len(brief["company_facts"]) == 1
    assert len(brief["research"]["rejected_facts"]) == 1
    # the uncited assertion may only appear inside the labelled rejection record,
    # never as a company fact the brief carries forward
    carried = json.dumps(brief["company_facts"])
    assert "Uncited assertion" not in carried
    assert all(f["source"] and f["citation"] for f in brief["company_facts"])


def test_research_allow_network_without_provider_fetches_nothing():
    research = ji.research_brief(CFG, {"company": "X"}, allow_network=True)
    assert research["facts"] == []
    assert research["status"] == "research_needed"
    assert any("nothing was fetched" in n for n in research["notes"])


def test_research_missing_file_is_recorded_not_guessed(tmp_path):
    research = ji.research_brief(CFG, {"company": "X"}, research_file=tmp_path / "nope.json")
    assert research["status"] == "research_needed"
    assert any("not found" in n for n in research["notes"])


# --------------------------------------------------------------------------- #
# handoff
# --------------------------------------------------------------------------- #

def test_handoff_text_is_only_source_supported_posting_lines():
    brief = uk_brief()
    text = ji.handoff_jd_text(brief)
    posting_lines = {apr.normalise_posting_line(l)
                     for l in JD_UK.read_text(encoding="utf-8").splitlines() if l.strip()}
    assert text.splitlines()
    for line in text.splitlines():
        assert apr.normalise_posting_line(line) in posting_lines


def test_handoff_excludes_keywords_and_company_facts():
    brief = uk_brief(research_file=RESEARCH_CITED)
    text = ji.handoff_jd_text(brief)
    assert "fixture value" not in text
    # the handoff is exactly the source-supported facts, nothing appended
    assert len(text.splitlines()) == len(brief["source_supported_facts"])
    assert text == "\n".join(f["text"] for f in sorted(
        brief["source_supported_facts"],
        key=lambda f: (f.get("source_line") or 0, f.get("role") or "")))


# --------------------------------------------------------------------------- #
# B17 — reviewer
# --------------------------------------------------------------------------- #

def honest_pack(tmp_path: Path) -> dict:
    """A pack built only from canonical text + structural letter text."""
    cv_path_src = cvw.source_paths(WF_CFG)["cv_md"]
    cv_text = cv_path_src.read_text(encoding="utf-8")
    facts = cvw.profile_facts(WF_CFG)
    name = facts.get("full_name") or ""
    cv_path = tmp_path / "cv_draft.md"
    cv_path.write_text("<!-- draft -->\n" + cv_text, encoding="utf-8")
    payload = {
        "candidate": {"name": name, "email": facts.get("email") or "x@example.invalid"},
        "letter": {
            "company": "Crown Agents Bank", "role_title": "Information Security Analyst",
            "opening": "I am writing to apply for the Information Security Analyst position at "
                       "Crown Agents Bank.",
            "profile_intro": cvw.canonical_profile_paragraph(cv_text),
            "problems_section": "DRAFT ONLY \u2014 owner review required. No application has been "
                                "submitted and nothing has been sent to the employer.",
            "closing": "Thank you for considering this application.",
            "signature": {"valediction": "Sincerely,", "name": name},
            "footnotes": [],
        },
        "provenance": {"posting": {"company": "Crown Agents Bank",
                                   "title": "Information Security Analyst"}},
    }
    payload_path = tmp_path / "cover_letter_payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    html_path = tmp_path / "cover.html"
    html_path.write_text("<!DOCTYPE html><html><body>cover</body></html>", encoding="utf-8")
    return {"cv": cv_path, "payload": payload_path, "html": html_path, "dir": tmp_path}


def run_review(pack: dict, brief: dict, **kwargs) -> dict:
    return apr.review(CFG, brief=brief, cv_draft_path=pack["cv"], payload_path=pack["payload"],
                      html_path=pack["html"], jd_path=JD_UK, **kwargs)


def test_reviewer_does_not_block_an_honest_pack(tmp_path):
    result = run_review(honest_pack(tmp_path), uk_brief())
    assert result["verdict"] != "block", result["blockers"]
    assert result["truthfulness_verified"] is True
    assert result["pack_id"].startswith("pack-")
    assert result["external_actions_taken"] == []


def test_reviewer_blocks_an_invented_cv_line(tmp_path):
    pack = honest_pack(tmp_path)
    pack["cv"].write_text(pack["cv"].read_text(encoding="utf-8") +
                          "- Cut incident volume by 40% across 500 endpoints.\n", encoding="utf-8")
    result = run_review(pack, uk_brief())
    assert result["verdict"] == "block"
    assert any(b["id"] == "cv_draft_not_verbatim" for b in result["blockers"])


def test_reviewer_blocks_an_invented_first_person_claim(tmp_path):
    pack = honest_pack(tmp_path)
    payload = json.loads(pack["payload"].read_text(encoding="utf-8"))
    payload["letter"]["profile_intro"] = "I have led a team of 12 analysts and hold CISSP."
    pack["payload"].write_text(json.dumps(payload), encoding="utf-8")
    result = run_review(pack, uk_brief())
    assert result["verdict"] == "block"
    ids = [b["id"] for b in result["blockers"]]
    assert "cover_letter_free_text" in ids or "candidate_claim_not_canonical" in ids


def test_reviewer_detects_posting_citation_drift(tmp_path):
    brief = uk_brief()
    brief = json.loads(json.dumps(brief))
    brief["requirements"][0]["text"] = "Ten years of cloud security architecture experience."
    result = run_review(honest_pack(tmp_path), brief)
    assert result["verdict"] == "block"
    assert any(b["id"] == "posting_citation_mismatch" for b in result["blockers"])


def test_reviewer_detects_identity_mismatch(tmp_path):
    pack = honest_pack(tmp_path)
    payload = json.loads(pack["payload"].read_text(encoding="utf-8"))
    payload["letter"]["role_title"] = "Chief Technology Officer"
    pack["payload"].write_text(json.dumps(payload), encoding="utf-8")
    result = run_review(pack, uk_brief())
    assert result["verdict"] == "block"
    assert any(b["id"] == "job_identity_mismatch" for b in result["blockers"])


def test_reviewer_separates_essential_and_desirable_coverage(tmp_path):
    result = run_review(honest_pack(tmp_path), uk_brief())
    coverage = result["checks"]["requirement_coverage"]
    assert coverage["counts"]["essential_total"] == 5
    assert coverage["counts"]["desirable_total"] == 4
    assert coverage["essential"] and coverage["desirable"]
    assert coverage["counts"]["note"]


def test_reviewer_surfaces_unknowns_for_the_owner(tmp_path):
    result = run_review(honest_pack(tmp_path), uk_brief())
    assert result["verdict"] == "pass_with_owner_input_required"
    assert result["owner_input_required"]
    assert result["checks"]["unresolved_unknowns"]["research_status"] == "research_needed"


def test_reviewer_is_deterministic(tmp_path):
    pack = honest_pack(tmp_path)
    brief = uk_brief()
    first = run_review(pack, brief)
    second = run_review(pack, brief)
    assert first["pack_sha256"] == second["pack_sha256"]
    assert first["verdict"] == second["verdict"]
    assert [f["id"] for f in first["findings"]] == [f["id"] for f in second["findings"]]


# --------------------------------------------------------------------------- #
# B18 — submission gate
# --------------------------------------------------------------------------- #

def gate_review(tmp_path: Path) -> dict:
    return run_review(honest_pack(tmp_path), uk_brief())


def test_gate_requires_owner_approval_and_performs_nothing(tmp_path):
    review = gate_review(tmp_path)
    result = sg.decide(CFG, review)
    assert result["status"] == "awaiting_owner_approval"
    assert result["submission_eligible"] is False
    assert result["external_action_performed"] is False
    assert result["owner_action_required"]
    assert result["external_actions_taken"] == []


def test_gate_refuses_every_external_action():
    for action in ("submit_application", "apply", "email_employer", "linkedin_apply", "upload_cv"):
        result = sg.guard_action(CFG, action)
        assert result["status"] == "refused"
        assert result["allowed"] is False and result["performed"] is False
        assert result["owner_gated"] is True


def test_gate_refuses_an_approval_inside_the_repository(tmp_path):
    review = gate_review(tmp_path)
    approval = {"approved_by": "Mukund", "approved_at": "2026-09-24T00:00:00Z",
                "pack_id": review["pack_id"], "pack_sha256": review["pack_sha256"],
                "approved_action": "submit_application", "acknowledged_unknowns": True}
    in_repo = CONTROL_PLANE / "runtime" / "career-ops" / "job-intelligence" / "tmp-approval.json"
    in_repo.parent.mkdir(parents=True, exist_ok=True)
    in_repo.write_text(json.dumps(approval), encoding="utf-8")
    try:
        result = sg.decide(CFG, review, approval=approval, approval_path=in_repo)
    finally:
        in_repo.unlink(missing_ok=True)
    assert result["status"] == "refused"
    assert any("inside the repository" in p for p in result["approval_problems"])


def test_gate_refuses_a_stale_approval_and_a_changed_pack(tmp_path):
    review = gate_review(tmp_path)
    outside = tmp_path / "approval.json"
    stale = {"approved_by": "Mukund", "approved_at": "2026-09-24T00:00:00Z",
             "pack_id": "pack-other", "pack_sha256": "0" * 64,
             "approved_action": "submit_application", "acknowledged_unknowns": True}
    outside.write_text(json.dumps(stale), encoding="utf-8")
    result = sg.decide(CFG, review, approval=stale, approval_path=outside)
    assert result["status"] == "refused"
    assert len(result["approval_problems"]) >= 2

    changed = json.loads(json.dumps(review))
    changed["pack_sha256"] = "1" * 64
    result2 = sg.decide(CFG, changed, approval=stale, approval_path=outside)
    assert result2["status"] == "refused"


def test_gate_refuses_when_truthfulness_is_not_verified(tmp_path):
    review = gate_review(tmp_path)
    unverified = {**review, "truthfulness_verified": False}
    result = sg.decide(CFG, unverified)
    assert result["status"] == "refused"
    assert "truthfulness" in result["reason"]


def test_gate_refuses_a_blocked_review(tmp_path):
    pack = honest_pack(tmp_path)
    pack["cv"].write_text(pack["cv"].read_text(encoding="utf-8") +
                          "- Delivered 200% improvement in detection coverage.\n", encoding="utf-8")
    blocked = run_review(pack, uk_brief())
    assert blocked["verdict"] == "block"
    result = sg.decide(CFG, blocked)
    assert result["status"] == "refused"
    assert result["external_action_performed"] is False


def test_gate_with_a_valid_external_approval_still_submits_nothing(tmp_path):
    review = gate_review(tmp_path)
    approval = {"approved_by": "Mukund", "approved_at": "2026-09-24T00:00:00Z",
                "pack_id": review["pack_id"], "pack_sha256": review["pack_sha256"],
                "approved_action": "submit_application", "acknowledged_unknowns": True}
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    checklist = tmp_path / "checklist.json"
    result = sg.decide(CFG, review, approval=approval, approval_path=approval_path,
                       checklist_path=checklist)
    assert result["status"] == "approved_pending_owner_manual_submission"
    assert result["external_action_performed"] is False
    assert result["external_actions_taken"] == []
    assert checklist.exists()
    doc = json.loads(checklist.read_text(encoding="utf-8"))
    assert doc["manual_steps"] and doc["pack_sha256"] == review["pack_sha256"]


def test_gate_requires_acknowledgement_of_unresolved_unknowns(tmp_path):
    review = gate_review(tmp_path)
    approval = {"approved_by": "Mukund", "approved_at": "2026-09-24T00:00:00Z",
                "pack_id": review["pack_id"], "pack_sha256": review["pack_sha256"],
                "approved_action": "submit_application"}  # acknowledged_unknowns absent
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    result = sg.decide(CFG, review, approval=approval, approval_path=approval_path,
                       checklist_path=tmp_path / "c.json")
    assert result["status"] == "refused"
    assert any("acknowledged_unknowns" in p for p in result["approval_problems"])


def test_gate_rejects_an_unknown_approved_action(tmp_path):
    review = gate_review(tmp_path)
    approval = {"approved_by": "Mukund", "approved_at": "2026-09-24T00:00:00Z",
                "pack_id": review["pack_id"], "pack_sha256": review["pack_sha256"],
                "approved_action": "publish_linkedin_post", "acknowledged_unknowns": True}
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    result = sg.decide(CFG, review, approval=approval, approval_path=approval_path)
    assert result["status"] == "refused"
    assert any("not a recognised external application action" in p
               for p in result["approval_problems"])


def test_canonical_sources_are_never_modified_by_the_test_run():
    paths = cvw.source_paths(WF_CFG)
    before = {k: cvw.sha256_file(p) for k, p in paths.items()}
    uk_brief()
    after = {k: cvw.sha256_file(p) for k, p in paths.items()}
    assert before == after


@pytest.mark.parametrize("field", ["requirements", "responsibilities", "eligibility"])
def test_brief_buckets_are_lists(field):
    assert isinstance(uk_brief()[field], list)
