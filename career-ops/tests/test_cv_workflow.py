#!/usr/bin/env python3
"""Tests for the Chief <-> Career Ops CV / cover-letter draft workflow.

Offline and non-destructive: the canonical CV assets in the Career Ops install
(``cv.md``, ``config/profile.yml``, ``config/cv-facts.json``) are only ever read,
and every generated artifact goes to ``tmp_path``.

Run:  python -m pytest career-ops/tests/test_cv_workflow.py -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import cv_workflow as cvw  # noqa: E402
import tracker_writer as tw  # noqa: E402

CFG = cvw.load_config()
PATHS = cvw.source_paths(CFG)
INSTALL = cvw.install_root(CFG)
NODE = shutil.which(CFG["renderer"]["node"])
JD_FIXTURE = CAREER_OPS / "tests" / "fixtures" / "jd-information-security-analyst.txt"

needs_install = pytest.mark.skipif(
    not all(p.exists() for p in PATHS.values()),
    reason="Career Ops install sources are not present on this machine",
)
needs_node = pytest.mark.skipif(NODE is None or not (INSTALL / "verify-cv-facts.mjs").exists(),
                                reason="node or the install fact gate is unavailable")

SYNTHETIC_CV = """\
# Test Candidate

London, UK | test@example.invalid

## Profile

Information Security MSc graduate with phishing analysis project experience.

## Certifications

CompTIA Security+ | ISC2 Certified in Cybersecurity (CC)

## Projects

### Alpha Project | Endpoint tooling

- Used Windows Event Logs to review endpoint configuration risk.
- Wrote a Python script that summarises authentication failures.

### Beta Project | Web tooling

- Built a JavaScript prototype for a browser extension.
"""

SYNTHETIC_JD = (
    "We need an analyst with Python automation skills, experience of Windows Event Logs "
    "and a strong grasp of authentication failures. Knowledge of GDPR is desirable."
)

TEST_JOB = {"company": "Example Analytics Ltd", "title": "Cyber Security Intern",
            "location": "London, United Kingdom", "_region": "uk", "_source_kind": "test"}


def _drafts(tmp_path: Path, stamp: str = "unit") -> dict:
    return cvw.build_drafts(CFG, tw.load_profiles(str(cvw.profiles_path(CFG))),
                            job=TEST_JOB, jd_text=cvw.read_text(JD_FIXTURE),
                            jd_source="synthetic fixture", stamp=stamp, run_dir=tmp_path)


# --------------------------------------------------------------------------- #
# canonical markdown parsing
# --------------------------------------------------------------------------- #

@needs_install
def test_parse_cv_markdown_preserves_every_line_verbatim():
    text = cvw.read_text(PATHS["cv_md"])
    sections = cvw.parse_cv_markdown(text)
    assert sections, "no sections parsed"

    source = text.splitlines()
    parsed = [(line["no"], line["kind"], line["text"])
              for section in sections for line in section["lines"] if line["kind"] != "blank"]
    assert parsed, "no non-blank lines parsed"
    for no, kind, value in parsed:
        assert 1 <= no <= len(source)
        expected = source[no - 1].strip()
        if kind == "bullet":
            assert expected.startswith(("-", "*")), expected
            assert value == expected[1:].strip()
        else:
            assert kind == "text"
            assert value == expected


@needs_install
def test_line_numbers_are_strictly_increasing_and_unique():
    sections = cvw.parse_cv_markdown(cvw.read_text(PATHS["cv_md"]))
    numbers = [l["no"] for s in sections for l in s["lines"] if l["kind"] != "blank"]
    assert numbers == sorted(numbers)
    assert len(numbers) == len(set(numbers))


# --------------------------------------------------------------------------- #
# drafting is selection/reordering only
# --------------------------------------------------------------------------- #

def test_cv_draft_contains_only_verbatim_source_lines():
    terms = cvw.jd_terms(CFG, SYNTHETIC_JD)
    draft = cvw.build_cv_draft(CFG, SYNTHETIC_CV, terms, job={"title": "Analyst"})
    source = {line.strip() for line in SYNTHETIC_CV.splitlines() if line.strip()}
    source |= {line.strip().lstrip("#").strip() for line in source}
    source |= {line.strip()[1:].strip() for line in source if line.strip().startswith("-")}

    body = []
    in_comment = False
    for raw in draft["text"].splitlines():
        line = raw.strip()
        if line.startswith("<!--"):
            in_comment = True
            continue
        if in_comment:
            in_comment = not line.endswith("-->")
            continue
        if line:
            body.append(line)
    assert body, "draft is empty"
    for line in body:
        assert line.lstrip("#").strip() in source or line in source, \
            f"line not reproduced from source: {line!r}"


def test_bullets_are_reordered_by_job_description_relevance():
    terms = cvw.jd_terms(CFG, SYNTHETIC_JD)
    draft = cvw.build_cv_draft(CFG, SYNTHETIC_CV, terms, job={})
    assert draft["text"].index("Used Windows Event Logs") < \
        draft["text"].index("Wrote a Python script")
    assert draft["text"].index("Wrote a Python script") < \
        draft["text"].index("Built a JavaScript prototype")


@needs_install
@needs_node
def test_provenance_entry_text_matches_its_source_line():
    draft = cvw.build_cv_draft(CFG, SYNTHETIC_CV, [], job={})
    source = SYNTHETIC_CV.splitlines()
    assert draft["provenance"], "no provenance recorded"
    for entry in draft["provenance"]:
        assert entry["source"] == "cv.md"
        assert 1 <= entry["source_line"] <= len(source)
        raw = source[entry["source_line"] - 1].strip()
        if entry["kind"] == "bullet":
            assert entry["text"] == raw[1:].strip()
        else:
            assert entry["text"] == raw


@needs_install
@needs_node
def test_draft_reports_jd_terms_with_no_canonical_evidence(tmp_path):
    """The reporting cap is configurable; nothing is ever written as a claim."""
    cfg = json.loads(json.dumps(CFG))
    cfg["tailoring"]["max_reported_unmatched_terms"] = 200
    result = cvw.build_drafts(cfg, tw.load_profiles(str(cvw.profiles_path(cfg))),
                              job=TEST_JOB, jd_text=cvw.read_text(JD_FIXTURE),
                              jd_source="fixture", stamp="unit4", run_dir=tmp_path)
    absent = result["job_description"]["terms_absent_from_canonical_sources"]
    assert "splunk" in absent, absent
    assert "python" not in absent, absent
    assert any("do not claim these" in item for item in result["owner_input_required"])


def test_matched_terms_are_recorded_per_bullet():
    terms = cvw.jd_terms(CFG, SYNTHETIC_JD)
    draft = cvw.build_cv_draft(CFG, SYNTHETIC_CV, terms, job={})
    hits = [p for p in draft["provenance"] if p["matched_terms"]]
    assert hits
    for entry in hits:
        for term in entry["matched_terms"]:
            assert term in SYNTHETIC_JD.casefold()


def test_no_matching_terms_leaves_canonical_order_intact():
    terms = cvw.jd_terms(CFG, "nothing in this text relates to the candidate")
    draft = cvw.build_cv_draft(CFG, SYNTHETIC_CV, terms, job={})
    assert draft["text"].index("Used Windows Event Logs") < \
        draft["text"].index("Built a JavaScript prototype")


# --------------------------------------------------------------------------- #
# job-description terms
# --------------------------------------------------------------------------- #

def test_jd_terms_strip_trailing_punctuation_and_drop_generic_words():
    terms = cvw.jd_terms(CFG, "Requirements: Python, Splunk. You will join our team!")
    assert "python" in terms and "splunk" in terms
    assert not [t for t in terms if t.endswith(".")]
    assert "team" not in terms and "join" not in terms and "you" not in terms


def test_posting_company_and_title_words_are_excluded():
    terms = cvw.jd_terms(CFG, "Crown Agents Bank seeks an Information Security Analyst",
                         exclude={"Crown", "Agents", "Bank", "Information", "Security",
                                  "Analyst"})
    assert all(t not in {"crown", "agents", "bank", "analyst"} for t in terms)


# --------------------------------------------------------------------------- #
# the install's fact gate is actually wired in (not bypassed)
# --------------------------------------------------------------------------- #

@needs_install
@needs_node
def test_fact_gate_blocks_a_fabricated_metric(tmp_path):
    gate = cvw.fact_gate(CFG, "Reached 94772 active users.", label="fabrication",
                         scratch=tmp_path)
    assert gate.get("available") is True
    assert gate["verdict"] == "block"
    assert gate["invented"], gate


@needs_install
@needs_node
def test_fact_gate_blocks_a_disavowed_employer(tmp_path):
    gate = cvw.fact_gate(CFG, "Assistant Systems Engineer at Apollo Clinic", label="disavowed",
                         scratch=tmp_path)
    assert gate["verdict"] == "block"
    assert gate["forbidden"], gate


@needs_install
@needs_node
def test_verbatim_canonical_text_passes_the_fact_gate(tmp_path):
    gate = cvw.fact_gate(CFG, cvw.read_text(PATHS["cv_md"]), label="canonical", scratch=tmp_path)
    assert gate.get("available") is True
    assert gate["verdict"] in ("pass", "warn"), gate
    assert not gate["invented"] and not gate["unsupportedFacts"] and not gate["forbidden"]


@needs_install
@needs_node
def test_fact_gate_reports_unavailable_rather_than_guessing(tmp_path):
    cfg = json.loads(json.dumps(CFG))
    cfg["renderer"]["node"] = "definitely-not-a-real-interpreter"
    gate = cvw.fact_gate(cfg, "anything", label="unavailable", scratch=tmp_path)
    assert gate["available"] is False
    assert "not found" in gate["reason"]


# --------------------------------------------------------------------------- #
# end-to-end draft build
# --------------------------------------------------------------------------- #

@needs_install
@needs_node
def test_draft_payload_renders_through_the_install_renderer(tmp_path):
    result = _drafts(tmp_path)
    assert result["status"] == "draft_ready_for_owner_review"
    assert result["fact_gate"]["cv_draft"]["verdict"] in ("pass", "warn")
    assert result["fact_gate"]["cover_letter"]["verdict"] in ("pass", "warn")
    render = result["cover_letter"]["render"]
    assert render["rendered"] is True
    assert render["renderer"] == "generate-cover-letter.mjs buildHtml"
    assert render["browser_launched"] is False
    assert render["pdf_rendered"] is False
    html = Path(result["cover_letter"]["html_path"]).read_text(encoding="utf-8")
    assert "{{" not in html, "unresolved template placeholder in the rendered letter"


@needs_install
@needs_node
def test_cover_letter_html_is_a_labelled_draft_with_provenance(tmp_path):
    result = _drafts(tmp_path, stamp="unit2")
    html = Path(result["cover_letter"]["html_path"]).read_text(encoding="utf-8")
    assert "DRAFT ONLY" in html
    assert "No application has been submitted" in html
    assert "cv.md:" in html
    payload = json.loads(Path(result["cover_letter"]["payload_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "draft_unreviewed"
    assert payload["provenance"]["rewrite_policy"].startswith("structural connective text only")
    assert payload["owner_input_required"]


@needs_install
@needs_node
def test_drafts_never_touch_the_canonical_cv_assets(tmp_path):
    before = {k: cvw.sha256_file(p) for k, p in PATHS.items()}
    _drafts(tmp_path, stamp="unit3")
    assert {k: cvw.sha256_file(p) for k, p in PATHS.items()} == before


@needs_install
def test_llm_tailor_request_is_recorded_but_not_executed(tmp_path):
    result = _drafts(tmp_path, stamp="unit5")
    request = result["llm_tailor_request"]
    assert request["executed"] is False
    assert "owner authorization" in request["reason"]
    assert result["external_actions_taken"] == []


# --------------------------------------------------------------------------- #
# job resolution
# --------------------------------------------------------------------------- #

@needs_install
def test_pipeline_jobs_read_from_career_ops_state():
    jobs = cvw.pipeline_jobs(CFG)
    assert jobs, "no pipeline entries found"
    first = jobs[0]
    assert first["company"] and first["title"] and first["url"]
    assert first["_source_kind"] == "career-ops-pipeline.md"


@needs_install
def test_resolve_job_reports_a_missing_match_rather_than_inventing_one():
    resolved = cvw.resolve_job(CFG, tw.load_profiles(str(cvw.profiles_path(CFG))),
                               region="uk", job_id="NOT-A-REAL-ID")
    assert resolved["ok"] is False
    assert "no matching row" in resolved["reason"]


def test_emit_is_ascii_safe_when_the_console_cannot_encode(tmp_path):
    """Regression: Task Scheduler redirects stdout to an OEM/ANSI code-page file."""
    script = tmp_path / "emit_probe.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(CAREER_OPS)!r})\n"
        "import cv_workflow as cvw\n"
        "cvw.emit({'title': 'Analyst \\u2014 Tokyo \\u30bb\\u30ad\\u30e5\\u30ea\\u30c6\\u30a3'})\n",
        encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                          encoding="cp1252", errors="replace", timeout=120)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert "Analyst" in payload["title"]
