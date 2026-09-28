#!/usr/bin/env python3
"""Tests for the high-recall multi-stage discovery pipeline.

Offline and non-destructive: no test scans a live source, calls DeepSeek or
Codex for real, writes a canonical workbook, submits an application, contacts
anyone, or opens a browser. Provider behaviour is exercised through stub
adapters that implement the real adapter interfaces.

Run:  python -m pytest career-ops/tests/test_discovery_pipeline.py -v
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
CONTROL_PLANE = CAREER_OPS.parent
sys.path.insert(0, str(CAREER_OPS))
sys.path.insert(0, str(CAREER_OPS / "discovery"))

import pipeline  # noqa: E402
import tracker_writer as tw  # noqa: E402
from funnel import Funnel  # noqa: E402
from semantic_contract import (  # noqa: E402
    ACCEPT_LABELS,
    LABELS,
    build_classification,
    candidate_id,
    guard,
)
from title_policy import (  # noqa: E402
    MODE_HIGH_RECALL,
    MODE_INTERN_ONLY,
    policy_document,
    tier_b_hits,
    title_decision,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "discovery"
TITLE_FIXTURES = FIXTURES / "title-fixtures.json"
CANDIDATES = FIXTURES / "candidates-synthetic.json"
PROFILES = tw.load_profiles()


def h(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_cli(argv, fn_name="main"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = getattr(pipeline, fn_name)(argv)
    return rc, json.loads(buf.getvalue())


def candidates():
    return pipeline.collect_from_records(CANDIDATES)["candidates"]


# --------------------------------------------------------------------------- #
# title policy
# --------------------------------------------------------------------------- #

def test_every_title_fixture_matches_its_expected_decision():
    doc = pipeline.selftest(TITLE_FIXTURES)
    assert doc["ok"], doc["failures"]
    assert doc["counts"]["failed"] == 0
    assert doc["counts"]["total"] >= 30


def test_old_policy_wrongly_rejected_titles_now_pass_high_recall():
    """The eight titles the owner's intern-only rule rejected, verified."""
    for title in ("Graduate Cyber Security Analyst", "Junior Security Analyst",
                  "SOC Analyst L1", "Information Security Analyst",
                  "Junior GRC Analyst", "Cyber Risk Analyst", "IAM Analyst",
                  "Technology Risk Graduate"):
        assert title_decision(title, MODE_INTERN_ONLY)["decision"] == "reject", title
        assert title_decision(title, MODE_HIGH_RECALL)["decision"] == "pass", title


def test_negative_fixtures_are_still_rejected_and_tier_b_is_named():
    for title in ("Senior Security Manager", "Principal Security Architect",
                  "Physical Security Guard", "Security Sales Director"):
        decision = title_decision(title, MODE_HIGH_RECALL)
        assert decision["decision"] == "reject", title
        assert decision["tier"] in ("A", "B")


def test_generic_word_security_alone_is_not_enough():
    assert title_decision("Security Assistant", MODE_HIGH_RECALL)["decision"] == "reject"
    assert title_decision("Security Officer", MODE_HIGH_RECALL)["decision"] == "reject"
    # ...but a qualified information-security officer is a real discipline signal
    assert title_decision("Information Security Officer", MODE_HIGH_RECALL)["decision"] == "pass"


def test_intern_only_mode_keeps_the_owner_semantics_verbatim():
    policy = policy_document()
    assert policy["owner_positive"] == ["Intern", "Internship"]
    assert "Senior" in policy["owner_negative"] and "Director" in policy["owner_negative"]
    assert title_decision("Cyber Security Intern", MODE_INTERN_ONLY)["decision"] == "pass"
    assert title_decision("Graduate Cyber Security Analyst", MODE_INTERN_ONLY)["decision"] == "reject"
    assert title_decision("Senior Cyber Security Intern", MODE_INTERN_ONLY)["decision"] == "reject"


def test_high_recall_is_the_default_mode_and_is_hashed():
    policy = policy_document()
    assert policy["default_mode"] == MODE_HIGH_RECALL
    assert policy["policy_sha256"] and len(policy["policy_sha256"]) == 64
    assert "prefilter only" in policy["boundary"]


def test_tier_b_negatives_cover_the_owner_list_plus_explicit_additions():
    assert set(tier_b_hits("Chief Information Security Officer")) >= {"chief"}
    assert "senior" in tier_b_hits("Senior Security Manager")
    assert tier_b_hits("SOC Analyst L1") == []


# --------------------------------------------------------------------------- #
# semantic contract
# --------------------------------------------------------------------------- #

def _record(**kw):
    base = {"company": "Testco", "title": "SOC Analyst L1", "location": "London, United Kingdom",
            "url": "https://testco.invalid/jobs/1"}
    base.update(kw)
    return base


def test_contract_labels_are_closed_and_accept_set_is_declared():
    assert set(ACCEPT_LABELS) <= set(LABELS)
    assert "ambiguous_review" in LABELS and "hard_eligibility_block" in LABELS


def test_classification_without_jd_is_marked_as_not_jd_analysis():
    doc = build_classification(_record(), primary_label="plausible_entry_level", confidence=0.5,
                               reasons=["title names a SOC analyst role"],
                               uncertainty=[], provider="deepseek", model="stub")
    assert doc["jd_available"] is False
    assert doc["classification_basis"] == "title_company_location_only"
    assert any("NOT semantic JD analysis" in u for u in doc["uncertainty"])
    assert doc["missing_fields"]
    assert doc["valid"] is True


def test_guard_rejects_an_invented_fact_the_source_does_not_contain():
    bad = build_classification(_record(), primary_label="strong_entry_level_match",
                               confidence=0.9,
                               reasons=["requires 5 years of experience and DV clearance"],
                               uncertainty=[], provider="deepseek", model="stub")
    assert bad["valid"] is False
    assert any("years" in v or "clearance" in v or "'5'" in v for v in bad["guard"]["violations"])


def test_guard_rejects_a_field_the_record_does_not_have():
    doc = {"primary_label": "plausible_entry_level", "confidence": 0.5,
           "reasons": ["name a SOC role"], "uncertainty": [],
           "source_fields": {"company": "Testco", "salary": "90000"},
           "provider": "deepseek", "model": "stub"}
    result = guard(doc, _record())
    assert result["ok"] is False
    assert any("salary" in v for v in result["violations"])


def test_guard_rejects_an_unknown_label_and_out_of_range_confidence():
    doc = dict(build_classification(_record(), primary_label="plausible_entry_level",
                                    confidence=0.5, reasons=["x"], uncertainty=[],
                                    provider="deepseek", model="stub"))
    doc["primary_label"] = "looks_fine_to_me"
    doc["confidence"] = 4.2
    result = guard(doc, _record())
    assert result["ok"] is False
    assert any("unknown primary_label" in v for v in result["violations"])
    assert any("confidence" in v for v in result["violations"])


def test_source_fields_must_be_a_subset_with_equal_values():
    rec = _record()
    doc = build_classification(rec, primary_label="plausible_entry_level", confidence=0.5,
                               reasons=["SOC analyst"], uncertainty=[],
                               provider="deepseek", model="stub")
    assert doc["source_fields"] == {k: v for k, v in rec.items() if v}
    doc["source_fields"]["title"] = "Chief Executive Officer"
    assert guard(doc, rec)["ok"] is False


def test_every_classification_carries_provenance_and_uncertainty_fields():
    doc = build_classification(_record(), primary_label="ambiguous_review", confidence=None,
                               reasons=[], uncertainty=["nothing to go on"],
                               provider="deepseek", model="deepseek-chat",
                               model_identity_observed=True)
    for key in ("provider", "model", "model_identity_observed", "classifier",
                "prompt_version", "reasons", "uncertainty", "source_fields",
                "missing_fields", "jd_available", "classification_basis"):
        assert key in doc, key
    assert doc["model_identity_observed"] is True


# --------------------------------------------------------------------------- #
# classifiers (stub adapters only)
# --------------------------------------------------------------------------- #

class StubE3:
    """E3 boundary fake: no test may inject a provider adapter into Career Ops."""
    def __init__(self, labels=None, health="healthy"):
        self.labels = labels or {}
        self._health = health
        self.calls = []

    def execute(self, *, objective, dry_run=False, **_kwargs):
        if dry_run:
            return ({"status": "DRY_RUN", "routable_workers": ["stub-e3"]}
                    if self._health == "healthy" else {"status": "FAILED"})
        self.calls.append({"objective": objective})
        payload = json.loads(objective.split("Candidates:\n", 1)[1])
        out = []
        for item in payload:
            label, conf = self.labels.get(item["title"], ("plausible_entry_level", 0.5))
            out.append({"candidate_id": item["candidate_id"], "primary_label": label,
                        "confidence": conf,
                        "reasons": [f"title '{item['title']}' matched the discipline rule"],
                        "uncertainty": ["no job description supplied"]})
        return {"status": "COMPLETED", "content": json.dumps(out), "provider": "stub-e3",
                "model": "stub-e3"}


def test_deepseek_bulk_pass_produces_contract_shaped_classifications():
    import classifiers
    recs = candidates()[:4]
    service = StubE3()
    doc = classifiers.deepseek_bulk_classify(recs, e3_service=service, batch_size=2)
    assert doc["limitation"] is None
    assert doc["batches"] == 2 and doc["requests"] == 2
    assert len(doc["classifications"]) == 4
    for cls in doc["classifications"].values():
        assert cls["primary_label"] in LABELS
        assert cls["provider"] == "stub-e3"
        assert cls["valid"] is True
    assert "owned by E3" in doc["model_resolution"]


def test_unhealthy_provider_is_recorded_as_a_limitation_not_as_zero_jobs():
    import classifiers
    doc = classifiers.deepseek_bulk_classify(candidates()[:2],
                                             e3_service=StubE3(health="unhealthy"))
    assert doc["classifications"] == {}
    assert "no eligible semantic worker" in doc["limitation"]


def test_escalation_conditions_are_deterministic_and_codex_is_budgeted():
    import classifiers
    recs = candidates()[:6]
    classes = {}
    for i, rec in enumerate(recs):
        label = "ambiguous_review" if i % 2 == 0 else "plausible_entry_level"
        cls = build_classification(rec, primary_label=label, confidence=0.4,
                                   reasons=["rule"], uncertainty=[],
                                   provider="deepseek", model="deepseek-chat",
                                   classifier="e3_bulk")
        cls["escalation_eligible"] = True
        classes[candidate_id(rec)] = cls
    plan = classifiers.select_escalations(recs, classes, budget=2)
    assert len(plan["selected"]) == 2
    assert plan["dropped_due_to_budget"]
    assert all(e["dropped"] == "codex_budget_exhausted"
               for e in plan["dropped_due_to_budget"])
    # ambiguous_review outranks a low-confidence plausible match
    assert plan["selected"][0]["reason"] == "semantic_label_ambiguous_review"


def test_deterministic_fallback_never_claims_to_be_a_model_pass():
    import classifiers
    doc = classifiers.deterministic_classify(candidates()[0])
    assert doc["provider"] == "none"
    assert doc["classifier"] == "deterministic"
    assert doc["confidence"] is None
    assert doc["escalation_eligible"] is False
    assert any("not a model judgement" in u for u in doc["uncertainty"])


class StubE3SecondPass:
    def execute(self, *, objective, dry_run=False, **_kwargs):
        if dry_run:
            return {"status": "DRY_RUN", "routable_workers": ["stub-e3"]}
        payload = json.loads(objective.split("Candidates:\n", 1)[1])
        out = [{"candidate_id": item["candidate"]["candidate_id"],
                "primary_label": "strong_entry_level_match", "confidence": 0.85,
                "reasons": ["second-pass review of a similarly-described entry role"],
                "uncertainty": ["no job description supplied"]} for item in payload]
        return {"status": "COMPLETED", "content": json.dumps(out), "provider": "stub-e3",
                "model": "stub-e3"}


def test_codex_second_pass_is_bounded_and_only_reviews_escalations():
    import classifiers
    recs = candidates()[:5]
    classes = {}
    for rec in recs:
        cls = build_classification(rec, primary_label="ambiguous_review", confidence=0.3,
                                   reasons=["rule"], uncertainty=[], provider="deepseek",
                                   model="deepseek-chat", classifier="e3_bulk")
        cls["escalation_eligible"] = True
        classes[candidate_id(rec)] = cls
    doc = classifiers.codex_escalate(recs, classes, budget=3, e3_service=StubE3SecondPass())
    assert doc["requests"] <= 3
    assert len(doc["escalated"]) == 3
    assert len(doc["dropped_due_to_budget"]) == 2
    assert all(c["classifier"] == "e3_second_pass"
               for c in doc["classifications"].values())
    assert all(c["escalation_reason"] for c in doc["classifications"].values())


def test_codex_is_not_called_when_nothing_escalates():
    import classifiers
    recs = candidates()[:3]
    classes = {}
    for rec in recs:
        cls = build_classification(rec, primary_label="strong_entry_level_match",
                                   confidence=0.95, reasons=["rule"], uncertainty=[],
                                   provider="deepseek", model="deepseek-chat",
                                   classifier="e3_bulk")
        cls["escalation_eligible"] = True
        classes[candidate_id(rec)] = cls
    doc = classifiers.codex_escalate(recs, classes, budget=5, e3_service=StubE3SecondPass())
    assert doc["requests"] == 0
    assert doc["escalated"] == []
    assert "no candidate met the deterministic escalation conditions" == doc["limitation"]


# --------------------------------------------------------------------------- #
# funnel
# --------------------------------------------------------------------------- #

def test_funnel_reports_where_a_zero_happened():
    f = Funnel()
    f.discover("source-a", 19)
    doc = f.document()
    assert doc["counts"]["discovered_raw"] == 19
    assert doc["zero_attribution"]["first_zero_stage"] == "after_hard_negative_prefilter"
    assert "Tier B" in doc["zero_attribution"]["reason"]
    assert doc["counts"]["discovered_raw_by_source"] == {"source-a": 19}


def test_funnel_lists_every_declared_counter():
    doc = Funnel().document()["counts"]
    for key in ("discovered_raw", "after_hard_negative_prefilter", "semantically_reviewed",
                "deepseek_accept", "codex_escalated", "codex_accept",
                "deterministic_eligibility_pass", "duplicates_removed", "tracker_candidates"):
        assert key in doc, key


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #

def test_scan_record_collection_marks_offers_as_url_less_and_reports_coverage(tmp_path):
    record = {"region": "uk", "run_id": "uk-test", "status": "ok",
              "scan": {"ok": True, "counters": {"jobs_found": 2861},
                       "stdout_tail": "New offers:\n  + Acme | SOC Analyst L1 | London, UK\n"}}
    p = tmp_path / "run.json"
    p.write_text(json.dumps(record), encoding="utf-8")
    block = pipeline.collect_from_scan_record(p)
    assert len(block["candidates"]) == 1
    assert block["candidates"][0]["needs_url_resolution"] is True
    assert block["coverage"]["counters"]["jobs_found"] == 2861
    assert "no posting URL" in block["coverage"]["note"]


def test_company_watch_findings_enter_the_funnel_with_attributable_exclusions(tmp_path):
    doc = {"region": "uk", "generated_at": "2026-09-24T00:00:00Z", "findings": [
        {"company": "A", "title": "SOC Analyst L1", "location": "London, UK",
         "url": "https://a.invalid/jobs/1", "decision": "new", "region_route": "uk",
         "owner_filter_eligible": False, "tracker_eligible": False},
        {"company": "B", "title": "SOC Analyst L1", "location": "London, UK",
         "url": "https://b.invalid/jobs/1", "decision": "duplicate", "region_route": "uk"},
        {"company": "C", "title": "SOC Analyst L1", "location": "Tokyo, Japan",
         "url": "https://c.invalid/jobs/1", "decision": "new", "region_route": "japan"},
    ]}
    p = tmp_path / "findings.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    block = pipeline.collect_from_company_watch(p, "uk")
    assert len(block["candidates"]) == 1
    cov = block["coverage"]
    assert cov["findings_total"] == 3
    assert cov["findings_entering_this_funnel"] == 1
    assert cov["findings_excluded_before_the_funnel"] == {
        "company_watch_decision:duplicate": 1, "routed_other_region:japan": 1}


# --------------------------------------------------------------------------- #
# full funnel run (offline, deterministic semantic, codex off)
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def run_doc(tmp_path_factory):
    out = tmp_path_factory.mktemp("discovery-run")
    rc, doc = run_cli(["run", "--region", "uk", "--records", str(CANDIDATES),
                       "--semantic", "deterministic", "--codex", "off",
                       "--out-dir", str(out)])
    assert rc == 0
    return doc


def test_run_reports_every_funnel_counter(run_doc):
    counts = run_doc["funnel"]["counts"]
    assert counts["discovered_raw"] == 10
    assert counts["after_hard_negative_prefilter"] == 8   # senior + physical guard removed
    assert counts["semantically_reviewed"] == 8
    assert counts["deepseek_accept"] == 0                  # deterministic fallback, not deepseek
    assert counts["codex_escalated"] == 0
    assert counts["deterministic_eligibility_pass"] == 5   # clearance, India posting and missing URL gate out
    assert counts["tracker_candidates"] >= 0
    assert run_doc["funnel"]["rejections_by_reason"]
    # the fallback run made no DeepSeek call, and says so rather than reporting a funnel zero
    assert "deepseek_accept" in run_doc["funnel"]["not_applicable_stages"]


def test_run_attaches_a_reason_to_every_rejection(run_doc):
    reasons = run_doc["funnel"]["rejections_by_reason"]
    assert any("tier B" in r or "non-cyber" in r or "no early-career" in r for r in reasons)
    assert any("no usable application URL" in r for r in reasons)
    assert any("clearance" in r for r in reasons)
    assert any("outside the region scope" in r or "does not name the region" in r
               or "blocked location" in r for r in reasons)


def test_run_never_writes_a_canonical_workbook_and_reports_safety(run_doc):
    assert run_doc["safety"]["canonical_workbook_written"] is False
    assert run_doc["safety"]["applications_submitted"] == 0
    assert run_doc["safety"]["employer_contacts"] == 0
    assert run_doc["dedupe"]["applied"] is False
    assert run_doc["dedupe"]["engine"].startswith("career-ops/tracker_writer.py")


def test_run_records_the_missing_jd_limitation_explicitly(run_doc):
    gap = run_doc["jd_gap"]
    assert gap["candidates"] == 10
    assert gap["with_job_description_text"] == 0
    assert gap["limitation"] and "NOT semantic JD analysis" in gap["limitation"]


def test_run_health_file_is_written_and_does_not_touch_trackers(tmp_path):
    tracker = Path((tw.region_config(PROFILES, "uk"))["tracker"])
    before = h(tracker)
    out = tmp_path / "discovery"
    rc, doc = run_cli(["run", "--region", "uk", "--records", str(CANDIDATES),
                       "--semantic", "deterministic", "--codex", "off",
                       "--out-dir", str(out)])
    assert rc == 0
    assert Path(doc["run_health_file"]).exists()
    assert h(tracker) == before


def test_zero_attribution_names_the_first_empty_stage(tmp_path):
    """A run whose candidates all lack an application URL must say so."""
    records = tmp_path / "nourl.json"
    records.write_text(json.dumps({"records": [
        {"company": "Test A (NOT A REAL VACANCY)", "title": "SOC Analyst L1",
         "location": "London, United Kingdom"},
        {"company": "Test B (NOT A REAL VACANCY)", "title": "Graduate Cyber Security Analyst",
         "location": "Leeds, England"},
    ]}), encoding="utf-8")
    rc, doc = run_cli(["run", "--region", "uk", "--records", str(records),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    counts = doc["funnel"]["counts"]
    assert counts["discovered_raw"] == 2
    assert counts["after_hard_negative_prefilter"] == 2
    assert counts["deterministic_eligibility_pass"] == 0
    z = doc["funnel"]["zero_attribution"]
    assert z["first_zero_stage"] == "deterministic_eligibility_pass"
    assert "deterministic gate" in z["reason"]
    assert "not an inference" in z["attribution_source"]
    # a stage disabled by configuration is reported separately, never as a funnel zero
    assert "semantically_reviewed" in doc["funnel"]["not_applicable_stages"]
    assert any("no usable application URL" in r
               for r in doc["funnel"]["rejections_by_reason"])


def test_semantic_rejections_are_counted_and_attributed(tmp_path):
    """A run whose semantics accept nothing must blame the semantic stage, not a gate."""
    import pipeline as pl
    records = tmp_path / "sem.json"
    records.write_text(json.dumps({"records": [
        {"company": "Test A (NOT A REAL VACANCY)", "title": "SOC Analyst L1",
         "location": "London, United Kingdom", "url": "https://a.invalid/jobs/1"},
        {"company": "Test B (NOT A REAL VACANCY)", "title": "IAM Analyst",
         "location": "Leeds, England", "url": "https://b.invalid/jobs/2"},
    ]}), encoding="utf-8")
    collected = pl.collect_from_records(records)
    doc = pl.run_funnel(collected["candidates"], region="uk", mode=MODE_HIGH_RECALL,
                        semantic="deepseek", deepseek_model="deepseek-flash", batch_size=5,
                        codex_budget=0, codex_enabled=False, timeout=10,
                        run_id="test-semantic-reject", collection=[
                            {"source": SOURCE, "candidates": collected["candidates"],
                             "coverage": {}}],
                        e3_service=StubE3(
                            labels={"SOC Analyst L1": ("wrong_discipline", 0.9),
                                    "IAM Analyst": ("too_senior", 0.9)}))
    counts = doc["funnel"]["counts"]
    assert counts["semantically_reviewed"] == 2
    assert counts["deepseek_accept"] == 0
    assert counts["deterministic_eligibility_pass"] == 0
    reasons = doc["funnel"]["rejections_by_reason"]
    assert reasons.get("semantic_label: wrong_discipline (e3_bulk)") == 1
    assert reasons.get("semantic_label: too_senior (e3_bulk)") == 1
    z = doc["funnel"]["zero_attribution"]
    assert z["first_zero_stage"] in {"deepseek_accept", "deterministic_eligibility_pass"}
    assert z["reason"]


SOURCE = pipeline.SOURCE_EXPLICIT


# --------------------------------------------------------------------------- #
# compare modes
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def compare_doc():
    rc, doc = run_cli(["compare-modes", "--region", "uk", "--records", str(CANDIDATES)])
    assert rc == 0
    return doc


def test_compare_modes_reports_a_recall_delta_without_writing_anything(compare_doc):
    assert compare_doc["safety"]["canonical_workbook_written"] is False
    assert compare_doc["safety"]["manifest_written"] is False
    assert compare_doc["safety"]["tracker_probe_run"] is False
    old = compare_doc["modes"][MODE_INTERN_ONLY]
    new = compare_doc["modes"][MODE_HIGH_RECALL]
    assert old["title_pass"] == 0
    assert new["title_pass"] == 8
    delta = compare_doc["recall_delta"]
    assert delta["title_pass_delta"] == 8
    regained = {r["title"] for r in delta["recall_regained_titles"]}
    assert "SOC Analyst L1" in regained and "Graduate Cyber Security Analyst" in regained
    assert delta["recall_lost_titles"] == []


def test_compare_modes_separates_title_recall_from_tracker_delta(compare_doc):
    delta = compare_doc["recall_delta"]
    assert "tracker_candidate_delta" in delta
    # the India-located and URL-less titles are regained titles that still fail the gates
    blocked = [r for r in delta["recall_regained_titles"]
               if r["deterministic_decision"] != "accepted"]
    assert blocked, "a regained title failing deterministic gates must be visible as such"
    assert any(r["gate_reasons"] for r in blocked)


def test_compare_modes_over_the_same_candidate_set_uses_identical_gates(compare_doc):
    for mode in (MODE_INTERN_ONLY, MODE_HIGH_RECALL):
        rows = compare_doc["modes"][mode]
        assert rows["title_pass"] + rows["title_reject"] == 10


# --------------------------------------------------------------------------- #
# CLI surface
# --------------------------------------------------------------------------- #

def test_policy_command_exposes_both_modes_and_the_contract():
    assert Path(CAREER_OPS / "discovery" / "pipeline.py").exists()
    policy = policy_document()
    assert set(policy["modes"]) == {MODE_HIGH_RECALL, MODE_INTERN_ONLY}
    assert "soc_security_operations" in policy["discipline_families"]
    assert "iam_identity" in policy["discipline_families"]
    assert "technology_risk" in policy["discipline_families"]


def test_run_requires_a_candidate_source():
    rc, doc = run_cli(["run", "--region", "uk"])
    assert rc == 2
    assert doc["ok"] is False
    assert "no candidate source supplied" in doc["reason"]
