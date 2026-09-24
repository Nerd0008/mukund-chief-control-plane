#!/usr/bin/env python3
"""Tests for the Interview Prep Agent (roster B22).

Offline and non-destructive: nothing here opens a network connection, starts a
browser or contacts an employer, recruiter or candidate. The canonical sources
are read-only; the only writes go to pytest's tmp_path.

Run:  python -m pytest career-ops/tests/test_interview_prep.py -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import interview_prep as ip  # noqa: E402
import cv_workflow as cvw  # noqa: E402
import job_intelligence as ji  # noqa: E402

CFG = ip.load_config()
FIXTURES = CAREER_OPS / "tests" / "fixtures"
JOB_RECORD = FIXTURES / "job-intelligence" / "job-record-uk.json"
JD = FIXTURES / "jd-information-security-analyst.txt"
JD_UNKNOWN_ELIGIBILITY = FIXTURES / "job-intelligence" / "jd-unknown-eligibility.txt"
RESEARCH_CITED = FIXTURES / "job-intelligence" / "research-cited.json"

needs_install = pytest.mark.skipif(
    not all(p.exists() for p in cvw.source_paths(ip.cv_config(CFG)).values()),
    reason="Career Ops install sources are not present on this machine")


def minimal_brief(**overrides) -> dict:
    """A minimally valid JobBrief for unit-level tests (no install access needed)."""
    brief = {
        "brief_id": "jb-test-0001",
        "generated_at": "2026-09-24T00:00:00Z",
        "generator": "career-ops/job_intelligence.py",
        "job": {"id": "T-1", "company": "Fixture Co", "title": "Security Analyst",
                "location": "London, United Kingdom", "region": "uk",
                "source_kind": "unit-test-fixture", "source_path": None},
        "provenance": {"job_description": {"available": True, "source": "fixture",
                                           "sha256": "x", "chars": 10, "lines": 1}},
        "requirements": [
            {"text": "Familiarity with regular expressions and log analysis.",
             "kind": "essential", "source_line": 19, "source_section": "requirements"},
            {"text": "Experience with Splunk or another SIEM platform.",
             "kind": "desirable", "source_line": 23, "source_section": "desirable"},
        ],
        "responsibilities": [
            {"text": "Monitor security alerts and support incident response triage.",
             "source_line": 9, "source_section": "responsibilities"},
        ],
        "eligibility": [
            {"text": "Right to work: applicants must already hold the right to work in the "
                     "United Kingdom.", "source_line": 26, "status": "satisfied_by_owner_source",
             "owner_source": "config/profile.yml", "owner_source_line": 6},
        ],
        "preferences": [],
        "keywords": [],
        "risks_unknowns": [],
        "company_facts": [],
        "research": {"status": "research_needed", "requested": [], "providers": {}},
        "source_supported_facts": [],
        "candidate_claims": [],
        "not_performed": [],
        "external_actions_taken": [],
    }
    brief.update(overrides)
    return brief


@pytest.fixture(scope="module")
def real_brief() -> dict:
    """A JobBrief built from the labelled synthetic fixture posting + job record."""
    if not all(p.exists() for p in cvw.source_paths(ip.cv_config(CFG)).values()):
        pytest.skip("Career Ops install sources are not present on this machine")
    job = json.loads(JOB_RECORD.read_text(encoding="utf-8"))
    job["_region"] = "uk"
    job["_source_kind"] = "synthetic-fixture-job-record"
    job["_source_path"] = str(JOB_RECORD)
    return ji.build_brief(ip.ji_config(CFG), job=job, jd_text=JD.read_text(encoding="utf-8"),
                          jd_source=f"synthetic fixture {JD.name}",
                          stamp="20260924T000000Z")


# --------------------------------------------------------------------------- #
# brief intake
# --------------------------------------------------------------------------- #

def test_load_brief_refuses_a_document_that_is_not_a_job_brief(tmp_path):
    p = tmp_path / "not-a-brief.json"
    p.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    with pytest.raises(ip.BriefError) as exc:
        ip.load_brief(p)
    assert "not a JobBrief" in str(exc.value)


def test_load_brief_refuses_a_brief_carrying_candidate_claims(tmp_path):
    doc = minimal_brief(candidate_claims=[{"claim": "I have 10 years of experience"}])
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ip.BriefError):
        ip.load_brief(p)


def test_load_brief_missing_file_is_reported_not_guessed(tmp_path):
    with pytest.raises(ip.BriefError):
        ip.load_brief(tmp_path / "absent.json")


# --------------------------------------------------------------------------- #
# questions are derived prompts, never employer-supplied questions
# --------------------------------------------------------------------------- #

def test_technical_questions_come_only_from_essential_requirements_and_responsibilities():
    brief = minimal_brief()
    qs = ip.technical_questions(brief, CFG)
    kinds = [q["basis"]["kind"] for q in qs]
    assert "posting_requirement" in kinds and "posting_responsibility" in kinds
    texts = [q["basis"]["text"] for q in qs]
    assert "Experience with Splunk or another SIEM platform." not in texts, \
        "a desirable line must not generate a technical requirement prompt"
    for q in qs:
        assert q["employer_supplied"] is False
        assert "NOT" in q["note"]
        assert q["basis"]["source_line"] is not None


def test_every_question_carries_the_posting_line_it_was_derived_from():
    brief = minimal_brief()
    jd_lines = JD.read_text(encoding="utf-8").splitlines()
    for q in ip.technical_questions(brief, CFG):
        line = q["basis"]["source_line"]
        assert q["basis"]["text"].strip()
        if 1 <= line <= len(jd_lines):
            # only asserted for the fixture posting's own lines
            assert q["basis"]["text"][:20] in jd_lines[line - 1] or \
                jd_lines[line - 1].strip() in q["basis"]["text"]


def test_behavioural_questions_link_to_a_responsibility_only_when_one_matches():
    brief = minimal_brief()
    qs = ip.behavioural_questions(brief, CFG)
    linked = [q for q in qs if q["basis"]["kind"] == "posting_responsibility"]
    unlinked = [q for q in qs if q["basis"]["kind"] == "standard_behavioural_theme"]
    assert linked, "a responsibility mentioning monitoring/alerts should link a theme"
    assert all(q["basis"]["text"] == brief["responsibilities"][0]["text"] for q in linked)
    assert unlinked, "themes with no matching posting line must be labelled as generic"
    assert all(q["basis"]["source_line"] is None for q in unlinked)


def test_questions_are_bounded_by_the_config_limits():
    brief = minimal_brief(
        requirements=[{"text": f"Essential requirement number {i}.", "kind": "essential",
                       "source_line": i, "source_section": "requirements"} for i in range(60)],
        responsibilities=[])
    qs = ip.technical_questions(brief, CFG)
    assert len(qs) == CFG["limits"]["max_technical_questions"]
    assert len(ip.likely_questions(brief, CFG)) <= CFG["limits"]["max_likely_questions"]


def test_motivation_and_eligibility_prompts_carry_their_basis():
    brief = minimal_brief()
    motiv = ip.motivation_questions(brief, CFG)
    assert motiv and all(q["basis"]["kind"] == "job_record" for q in motiv)
    elig = ip.eligibility_questions(brief)
    assert elig[0]["basis"]["text"] == brief["eligibility"][0]["text"]
    assert elig[0]["basis"]["resolved_status"] == "satisfied_by_owner_source"


# --------------------------------------------------------------------------- #
# talking points quote canonical evidence verbatim
# --------------------------------------------------------------------------- #

@needs_install
def test_talking_point_quotes_are_verbatim_canonical_lines():
    brief = minimal_brief()
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    assert pack["quote_violations"] == []
    talking = pack["sections"]["evidence_backed_talking_points"]
    assert talking
    backed = [t for t in talking if t["status"] == "evidence_backed"]
    assert backed, "the fixture requirement on log analysis should find canonical evidence"
    for tp in backed:
        assert tp["quotes"], tp["id"]
        for q in tp["quotes"]:
            assert q["source"] == "cv.md"
            assert q["source_line"] > 0


@needs_install
def test_a_qualification_requirement_is_answered_from_the_canonical_education_section():
    brief = minimal_brief(
        requirements=[{"text": "A degree in information security, cyber security or a related "
                               "discipline.", "kind": "essential", "source_line": 16,
                       "source_section": "requirements"}],
        responsibilities=[])
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    tp = pack["sections"]["evidence_backed_talking_points"][-1]
    assert tp["status"] == "evidence_backed"
    assert "qualification_education" in tp["match_basis"]
    assert any("msc" in (q["section"] or "").casefold()
               or "bachelor" in (q["section"] or "").casefold() for q in tp["quotes"])
    assert pack["quote_violations"] == []


@needs_install
def test_a_requirement_with_no_canonical_evidence_becomes_an_owner_action():
    brief = minimal_brief(
        requirements=[{"text": "Experience administering mainframe RACF security.",
                       "kind": "essential", "source_line": 30,
                       "source_section": "requirements"}],
        responsibilities=[])
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    tp = [t for t in pack["sections"]["evidence_backed_talking_points"]
          if t.get("requirement") and "RACF" in t["requirement"]["text"]]
    assert tp, "the unmatched requirement must still appear as a talking point"
    assert tp[0]["status"] == "owner_input_required"
    assert tp[0]["quotes"] == []
    assert "will not invent" in tp[0]["owner_action"]
    assert any(u["kind"] == "requirement_without_canonical_evidence"
               for u in pack["sections"]["unknowns"])


@needs_install
def test_opening_talking_point_uses_only_the_canonical_profile_line():
    brief = minimal_brief()
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    opening = pack["sections"]["evidence_backed_talking_points"][0]
    assert opening["id"] == "tp-opening"
    assert len(opening["quotes"]) == 1
    cv_lines = cvw.read_text(cvw.source_paths(ip.cv_config(CFG))["cv_md"]).splitlines()
    line = cv_lines[opening["quotes"][0]["source_line"] - 1].strip()
    assert opening["quotes"][0]["quote"] == line


# --------------------------------------------------------------------------- #
# truth enforcement
# --------------------------------------------------------------------------- #

@needs_install
def test_a_clean_pack_reports_no_candidate_claim_or_quote_violations():
    brief = minimal_brief()
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    assert pack["candidate_claim_violations"] == []
    assert pack["quote_violations"] == []
    assert pack["candidate_claims"] == []
    assert pack["external_actions_taken"] == []
    assert pack["interview_scheduled"] is False
    assert pack["interview_attended"] is False
    assert pack["ok"] is True


@needs_install
def test_a_first_person_claim_in_generated_text_is_caught():
    brief = minimal_brief()
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    pack["sections"]["technical_prep"][0]["prompt"] = "I have five years of SOC experience."
    violations = ip.candidate_claim_violations(pack)
    assert violations and violations[0]["pattern"] == r"\bI have\b"


@needs_install
def test_a_tampered_quote_fails_the_quote_check():
    brief = minimal_brief()
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    tp = [t for t in pack["sections"]["evidence_backed_talking_points"]
          if t["quotes"]][0]
    tp["quotes"][0]["quote"] = "Led a 24/7 security operations centre."
    violations = ip.quote_violations(pack, CFG)
    assert violations and violations[0]["reason"] == "quote is not verbatim at that line"


def test_validate_pack_rejects_an_employer_supplied_question_and_a_claim():
    pack = ip.build_prep_pack(CFG, minimal_brief(), stamp="20260924T000000Z") \
        if all(p.exists() for p in cvw.source_paths(ip.cv_config(CFG)).values()) else None
    if pack is None:
        pytest.skip("Career Ops install sources are not present on this machine")
    pack["sections"]["likely_questions"][0]["employer_supplied"] = True
    result = ip.validate_pack(pack, CFG)
    assert result["ok"] is False
    assert any("employer-supplied" in e for e in result["errors"])


@needs_install
def test_a_general_domain_word_alone_is_not_treated_as_evidence():
    """'security' matching a CV line must not make a RACF requirement look sourced."""
    evidence = ip.canonical_evidence(CFG)
    req = "Experience administering mainframe RACF security."
    assert ip.match_evidence(req, evidence, CFG) == [], \
        "a match on general domain words alone must not count as evidence"
    # the same sentence with a specific term does match something real
    specific = "Developed a JavaScript / Manifest V3 prototype using regular expressions."
    assert ip.match_evidence(specific, evidence, CFG), \
        "a specific-term requirement must still find canonical evidence"


@needs_install
def test_the_committed_schema_validates_a_real_pack():
    """The JSON schema is a contract, not decoration: it must accept a real pack."""
    jsonschema = pytest.importorskip("jsonschema")
    pack = ip.build_prep_pack(CFG, minimal_brief(), stamp="20260924T000000Z")
    schema = json.loads(ip.pack_schema_path(CFG).read_text(encoding="utf-8"))
    jsonschema.validate(instance=pack, schema=schema)
    # and it must reject a pack whose question claims employer origin
    broken = json.loads(json.dumps(pack))
    broken["sections"]["likely_questions"][0]["employer_supplied"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=broken, schema=schema)


def test_module_imports_no_network_or_browser_library():
    src = (CAREER_OPS / "interview_prep.py").read_text(encoding="utf-8")
    imports = "\n".join(line for line in src.splitlines()
                        if re.match(r"^\s*(import|from)\s", line))
    for banned in ("urllib", "requests", "socket", "http.client", "httpx", "aiohttp",
                   "webbrowser", "playwright", "selenium", "pyppeteer"):
        assert not re.search(rf"\b{re.escape(banned)}\b", imports), \
            f"{banned} must not be imported by the interview prep agent"


# --------------------------------------------------------------------------- #
# integration with the real brief / fixture posting
# --------------------------------------------------------------------------- #

@needs_install
def test_real_fixture_brief_produces_a_role_specific_pack(real_brief):
    pack = ip.build_prep_pack(CFG, real_brief, stamp="20260924T000000Z")
    assert pack["ok"] is True
    assert pack["job"]["company"] == "Crown Agents Bank"
    assert pack["counts"]["technical_prep"] >= 5
    assert pack["counts"]["behavioural_prep"] >= 5
    assert pack["counts"]["talking_points_evidence_backed"] >= 1
    prompts = " ".join(q["prompt"] for q in pack["sections"]["technical_prep"])
    assert "phishing" in prompts.casefold(), \
        "the posting's phishing requirement should produce a phishing-specific prompt"
    for q in pack["sections"]["likely_questions"]:
        assert q["employer_supplied"] is False


@needs_install
def test_unknown_eligibility_stays_unknown_and_produces_employer_questions():
    job = json.loads(JOB_RECORD.read_text(encoding="utf-8"))
    job.update({"_region": "uk", "_source_kind": "synthetic-fixture-job-record",
                "_source_path": str(JOB_RECORD)})
    brief = ji.build_brief(ip.ji_config(CFG), job=job,
                           jd_text=JD_UNKNOWN_ELIGIBILITY.read_text(encoding="utf-8"),
                           jd_source=f"synthetic fixture {JD_UNKNOWN_ELIGIBILITY.name}",
                           stamp="20260924T000000Z")
    pack = ip.build_prep_pack(CFG, brief, stamp="20260924T000000Z")
    unknown_elig = [e for e in brief["eligibility"]
                    if e["status"] != "satisfied_by_owner_source"]
    assert unknown_elig, "the UAE fixture posting must resolve eligibility as unknown"
    assert any(u["kind"] == "eligibility_unknown" for u in pack["sections"]["unknowns"])
    assert pack["counts"]["questions_to_ask_employer"] >= 1
    # the pack must not decide the owner's right-to-work position for him
    joined = json.dumps(pack).casefold()
    for claim in ("i hold", "i have the right to work", "sponsorship required",
                  "no sponsorship needed"):
        assert claim not in joined


@needs_install
def test_cited_research_file_is_carried_and_uncited_is_not(real_brief):
    pack = ip.build_prep_pack(CFG, real_brief, research_file=RESEARCH_CITED,
                             stamp="20260924T000000Z")
    assert pack["research"]["facts_available"] == 2
    assert pack["research"]["status"] == "provided"
    assert all(f.get("citation") for f in pack["research"]["facts"])
    assert "research-cited.json" in pack["provenance"]["research_source"]


@needs_install
def test_pack_without_research_records_research_needed(real_brief):
    pack = ip.build_prep_pack(CFG, real_brief, stamp="20260924T000000Z")
    assert pack["research"]["facts_available"] == 0
    assert any(u["kind"] == "research_needed" for u in pack["sections"]["unknowns"])


# --------------------------------------------------------------------------- #
# CLI safety
# --------------------------------------------------------------------------- #

@needs_install
def test_cli_refuses_to_write_over_one_of_its_own_inputs(tmp_path):
    """The job_intelligence defect (output over input) must not be repeated here."""
    out = tmp_path / "job_brief.json"
    out.write_text("{}", encoding="utf-8")
    args = type("A", (), {"brief": str(out), "jd_file": None, "job_record": None,
                          "research_file": None})()
    problems = ip._refuse_to_overwrite_inputs(args, [out])
    assert problems and problems[0]["reason"] == "output path would overwrite an input file"


@needs_install
def test_cli_pack_writes_both_artifacts_and_reports_no_external_action(tmp_path, capsys):
    pack_dir = tmp_path / "pack"
    rc = ip.main(["pack", "--brief", str(_write_brief(tmp_path)), "--out", str(pack_dir),
                  "--stamp", "20260924T000000Z"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["ok"] is True
    assert Path(payload["pack_path"]).exists()
    assert Path(payload["pack_markdown"]).exists()
    assert payload["external_actions_taken"] == []
    assert payload["candidate_claim_violations"] == []


def _write_brief(tmp_path: Path) -> Path:
    p = tmp_path / "brief-input.json"
    p.write_text(json.dumps(minimal_brief()), encoding="utf-8")
    return p


@needs_install
def test_cli_pack_refuses_a_non_brief_document(tmp_path, capsys):
    p = tmp_path / "junk.json"
    p.write_text('{"not": "a brief"}', encoding="utf-8")
    rc = ip.main(["pack", "--brief", str(p), "--out", str(tmp_path / "o")])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1 and payload["ok"] is False
    assert "not a JobBrief" in payload["reason"]
