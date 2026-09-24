#!/usr/bin/env python3
"""Regression tests for the unified discovery funnel across every read-only source.

These prove the successor contract: Recruiter/Intermediary Watch (B11) and the
LinkedIn read-only job-discovery intake (B19) run through the SAME funnel as the
regional lanes and Company Watch — one candidate schema, one semantic contract,
one set of deterministic gates, one dedupe engine — and that the same vacancy
discovered from several surfaces collapses to one canonical candidate with its
provenance preserved.

Offline and non-destructive: no test scans a live source, calls a provider for
real, writes a canonical workbook, submits an application, contacts an agency or
an employer, opens a browser or uses any account/session.

Run:  python -m pytest career-ops/tests/test_unified_discovery_sources.py -v
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

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "discovery"
OVERLAP = FIXTURES / "multi-source-overlap.json"
REGIONAL = FIXTURES / "regional-overlap.json"
RECRUITER = FIXTURES / "recruiter-watch-overlap.json"
LINKEDIN = FIXTURES / "linkedin-overlap.json"
PROFILES = tw.load_profiles()
REGIONS = ("uk", "dubai", "japan", "singapore")


def h(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tracker_hashes() -> dict:
    out = {}
    for region in REGIONS:
        p = Path(tw.region_config(PROFILES, region)["tracker"])
        out[region] = h(p) if p.exists() else None
    return out


def run_cli(argv: list, fn_name="main"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = getattr(pipeline, fn_name)(argv)
    return rc, json.loads(buf.getvalue())


def multi_source_argv(out_dir) -> list:
    return ["run", "--region", "uk",
            "--records", str(REGIONAL),
            "--recruiter-watch", str(RECRUITER),
            "--linkedin", str(LINKEDIN),
            "--semantic", "off", "--codex", "off",
            "--out-dir", str(out_dir)]


@pytest.fixture(scope="module")
def run_doc(tmp_path_factory):
    out = tmp_path_factory.mktemp("unified-run")
    rc, doc = run_cli(multi_source_argv(out))
    assert rc == 0
    return doc


# --------------------------------------------------------------------------- #
# the fixtures themselves
# --------------------------------------------------------------------------- #

def test_the_overlap_fixture_declares_the_expected_canonical_vacancy():
    doc = json.loads(OVERLAP.read_text(encoding="utf-8"))
    assert doc["not_a_real_vacancy"] is True
    assert set(doc["canonical_vacancy"]["discovered_by"]) == {
        pipeline.SOURCE_EXPLICIT, pipeline.SOURCE_RECRUITER_WATCH,
        pipeline.SOURCE_LINKEDIN_EXPORT}


@pytest.mark.parametrize("path", [REGIONAL, RECRUITER, LINKEDIN])
def test_every_source_fixture_is_synthetic_and_uses_reserved_hosts(path):
    text = path.read_text(encoding="utf-8")
    assert "NOT A REAL" in text
    assert ".invalid" in text
    assert "https://" in text
    # no real job board or social host is referenced by any fixture URL
    for host in ("linkedin.com", "indeed.", "greenhouse.io", "lever.co", "workday"):
        assert host not in text, f"{path.name} references a real host: {host}"


# --------------------------------------------------------------------------- #
# new collectors normalise into the one candidate schema
# --------------------------------------------------------------------------- #

def test_recruiter_watch_findings_enter_the_funnel_with_attributable_exclusions():
    block = pipeline.collect_from_recruiter_watch(RECRUITER, "uk")
    assert block["available"] is True
    assert len(block["candidates"]) == 2
    cov = block["coverage"]
    assert cov["findings_total"] == 4
    assert cov["findings_entering_this_funnel"] == 2
    assert cov["findings_excluded_before_the_funnel"] == {
        "recruiter_watch_decision:duplicate": 1, "routed_other_region:dubai": 1}
    for rec in block["candidates"]:
        assert rec["_collection_source"] == pipeline.SOURCE_RECRUITER_WATCH
        assert rec["intermediary"]
        assert "NOT A REAL AGENCY" in rec["intermediary"]


def test_linkedin_export_job_signals_are_candidates_and_company_signals_are_not():
    block = pipeline.collect_from_linkedin(LINKEDIN, "uk")
    assert block["available"] is True
    assert len(block["candidates"]) == 2
    cov = block["coverage"]
    assert cov["job_signals_entering_this_funnel"] == 2
    assert cov["company_signals_not_job_candidates"] == 1
    assert cov["file_sha256"]
    for rec in block["candidates"]:
        assert rec["_collection_source"] == pipeline.SOURCE_LINKEDIN_EXPORT
        assert rec["url"].startswith("https://")
        # a company-only signal must never be turned into a vacancy candidate
        assert rec["title"]


def test_collectors_declare_read_only_safety_and_no_account_use():
    for block in (pipeline.collect_from_recruiter_watch(RECRUITER, "uk"),
                  pipeline.collect_from_linkedin(LINKEDIN, "uk")):
        note = block["coverage"]["note"].casefold()
        assert "read-only" in note or "read only" in note
        assert "no login" in note or "no account" in note or "not contacted" in note


def test_cli_requires_a_source_and_names_the_new_ones():
    rc, doc = run_cli(["run", "--region", "uk"])
    assert rc == 2
    assert "no candidate source supplied" in doc["reason"]
    assert "--recruiter-watch" in doc["reason"] and "--linkedin" in doc["reason"]


# --------------------------------------------------------------------------- #
# cross-source canonical collapse: one vacancy -> one candidate
# --------------------------------------------------------------------------- #

def test_collapse_merges_the_same_url_seen_through_several_surfaces():
    raw = (pipeline.collect_from_records(REGIONAL)["candidates"]
           + pipeline.collect_from_recruiter_watch(RECRUITER, "uk")["candidates"]
           + pipeline.collect_from_linkedin(LINKEDIN, "uk")["candidates"])
    result = pipeline.collapse_candidates(raw)
    assert result["counts"]["raw_discoveries"] == 6
    assert result["counts"]["canonical_candidates"] == 4
    assert result["counts"]["cross_source_duplicates_removed"] == 2
    assert result["counts"]["multi_source_canonical_candidates"] == 1
    assert len(result["collapsed"]) == 1
    entry = result["collapsed"][0]
    assert entry["discoveries"] == 3
    assert set(entry["sources"]) == {pipeline.SOURCE_EXPLICIT, pipeline.SOURCE_RECRUITER_WATCH,
                                     pipeline.SOURCE_LINKEDIN_EXPORT}


def test_collapse_preserves_every_discovery_in_the_canonical_provenance():
    raw = (pipeline.collect_from_records(REGIONAL)["candidates"]
           + pipeline.collect_from_recruiter_watch(RECRUITER, "uk")["candidates"]
           + pipeline.collect_from_linkedin(LINKEDIN, "uk")["candidates"])
    result = pipeline.collapse_candidates(raw)
    canonical = {c["candidate_id"]: c for c in result["candidates"]}
    overlaps = [c for c in canonical.values() if c.get("duplicate_discoveries")]
    assert len(overlaps) == 1
    candidate = overlaps[0]
    collection_sources = {p["collection_source"] for p in candidate["provenance"]}
    assert collection_sources == set(candidate["sources"])
    assert set(candidate["sources"]) == {pipeline.SOURCE_EXPLICIT,
                                         pipeline.SOURCE_RECRUITER_WATCH,
                                         pipeline.SOURCE_LINKEDIN_EXPORT}
    # the intermediary discovery keeps the agency that advertised the vacancy
    assert candidate["intermediary"]
    assert "NOT A REAL AGENCY" in candidate["intermediary"]
    # the declared per-source label survives alongside the collection surface, and a
    # discovery that declared no source is recorded as such rather than given one
    declared = {p["declared_source"] for p in candidate["provenance"] if p["declared_source"]}
    assert "linkedin-saved-job-feed" in declared
    assert "uk regional scan" in declared
    recruiter_entries = [p for p in candidate["provenance"]
                         if p["collection_source"] == pipeline.SOURCE_RECRUITER_WATCH]
    assert len(recruiter_entries) == 1
    assert recruiter_entries[0]["declared_source"] is None


def test_collapse_does_not_merge_two_url_less_records_or_invent_fields():
    a = pipeline.normalise_candidate({"company": "One Ltd", "title": "SOC Analyst L1",
                                      "location": "London"}, "src-a")
    b = pipeline.normalise_candidate({"company": "Two Ltd", "title": "SOC Analyst L1",
                                      "location": "London"}, "src-b")
    result = pipeline.collapse_candidates([a, b])
    assert result["counts"]["canonical_candidates"] == 2
    assert result["counts"]["cross_source_duplicates_removed"] == 0
    for cand in result["candidates"]:
        assert cand["duplicate_discoveries"] == 0
        assert cand["sources"] == [cand["source"]]


def test_collapse_of_a_url_less_pair_keeps_one_candidate_with_both_sources():
    a = pipeline.normalise_candidate({"company": "One Ltd", "title": "SOC Analyst L1"},
                                     "src-a")
    b = pipeline.normalise_candidate({"company": "One Ltd", "title": "SOC Analyst L1",
                                      "location": "London, United Kingdom"}, "src-b")
    result = pipeline.collapse_candidates([a, b])
    assert result["counts"]["canonical_candidates"] == 1
    cand = result["candidates"][0]
    assert set(cand["sources"]) == {"src-a", "src-b"}
    # the missing field was filled from the richer copy, never invented
    assert cand["location"] == "London, United Kingdom"
    assert cand["canonical_key"][0] == "pair"


# --------------------------------------------------------------------------- #
# the full multi-source run
# --------------------------------------------------------------------------- #

def test_run_counts_every_source_and_collapses_the_overlap(run_doc):
    counts = run_doc["funnel"]["counts"]
    assert counts["discovered_raw"] == 6
    assert counts["canonical_candidates"] == 4
    assert counts["cross_source_duplicates_removed"] == 2
    assert counts["discovered_raw_by_source"] == {
        pipeline.SOURCE_EXPLICIT: 2,
        pipeline.SOURCE_RECRUITER_WATCH: 2,
        pipeline.SOURCE_LINKEDIN_EXPORT: 2}
    assert run_doc["cross_source_dedupe"]["counts"]["multi_source_canonical_candidates"] == 1


def test_run_reports_the_canonical_candidate_with_all_three_sources(run_doc):
    shared = [c for c in run_doc["canonical_candidates"] if c["duplicate_discoveries"]]
    assert len(shared) == 1
    cand = shared[0]
    assert set(cand["sources"]) == {pipeline.SOURCE_EXPLICIT,
                                    pipeline.SOURCE_RECRUITER_WATCH,
                                    pipeline.SOURCE_LINKEDIN_EXPORT}
    assert [p["collection_source"] for p in cand["provenance"]]
    assert len(cand["provenance"]) == 3


def test_run_exposes_the_source_registry_and_contract(run_doc):
    assert run_doc["source_registry"] == pipeline.SOURCE_REGISTRY
    contract = pipeline.source_contract_document()
    assert set(contract["sources"]) >= {pipeline.SOURCE_RECRUITER_WATCH,
                                        pipeline.SOURCE_LINKEDIN_EXPORT}
    assert "canonical_identity" in contract and "provenance" in contract


def test_every_source_gets_its_own_funnel_counters(run_doc):
    by_source = run_doc["funnel"]["by_source"]
    for source in (pipeline.SOURCE_EXPLICIT, pipeline.SOURCE_RECRUITER_WATCH,
                   pipeline.SOURCE_LINKEDIN_EXPORT):
        entry = by_source[source]
        assert entry["counts"]["discovered"] == 2
        assert entry["counts"]["canonical"] == 2
        assert entry["counts"]["after_hard_negative_prefilter"] == 2
        assert "rejections_by_reason" in entry
        assert "zero_attribution" in entry


def test_a_source_zero_is_attributable_by_source_and_stage(tmp_path):
    """A source whose candidates all lack a URL must blame its own gates."""
    records = tmp_path / "nourl.json"
    records.write_text(json.dumps({"records": [
        {"company": "Test A (NOT A REAL VACANCY)", "title": "SOC Analyst L1",
         "location": "London, United Kingdom", "source": "uk regional scan"},
    ]}), encoding="utf-8")
    recruiter = tmp_path / "rw.json"
    recruiter.write_text(json.dumps({"region": "uk", "findings": [
        {"intermediary": "Agency X (NOT A REAL AGENCY)",
         "employer": "Test B (NOT A REAL VACANCY)", "title": "SOC Analyst L1",
         "location": "London, United Kingdom", "decision": "new", "region_route": "uk"},
    ]}), encoding="utf-8")
    rc, doc = run_cli(["run", "--region", "uk", "--records", str(records),
                       "--recruiter-watch", str(recruiter),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    by_source = doc["funnel"]["by_source"]
    for source in (pipeline.SOURCE_EXPLICIT, pipeline.SOURCE_RECRUITER_WATCH):
        attribution = by_source[source]["zero_attribution"]
        assert attribution["first_zero_stage"] == "deterministic_eligibility_pass"
        assert "deterministic gate" in attribution["reason"]
        assert "not an inference" in attribution["attribution_source"]
        assert "no usable application URL" in json.dumps(
            by_source[source]["rejections_by_reason"])
    # the global funnel still names its own first zero
    assert doc["funnel"]["zero_attribution"]["first_zero_stage"] == \
        "deterministic_eligibility_pass"


def test_a_disabled_semantic_stage_is_not_reported_as_a_source_zero(run_doc):
    for entry in run_doc["funnel"]["by_source"].values():
        assert "semantic_accept" in entry["not_applicable_stages"]
        assert entry["zero_attribution"]["first_zero_stage"] != "semantic_accept"


def test_recruiter_watch_pre_funnel_exclusions_are_reported_in_coverage(run_doc):
    blocks = {b.get("source"): b for b in run_doc["collection"]}
    cov = blocks[pipeline.SOURCE_RECRUITER_WATCH]["coverage"]
    assert cov["findings_excluded_before_the_funnel"] == {
        "recruiter_watch_decision:duplicate": 1, "routed_other_region:dubai": 1}
    linkedin_cov = blocks[pipeline.SOURCE_LINKEDIN_EXPORT]["coverage"]
    assert linkedin_cov["company_signals_not_job_candidates"] == 1


def test_multi_source_run_writes_a_manifest_only_and_touches_no_workbook(tmp_path):
    before = tracker_hashes()
    out = tmp_path / "run"
    rc, doc = run_cli(multi_source_argv(out) + ["--manifest-out", str(tmp_path / "m.json")])
    assert rc == 0
    assert doc["safety"]["canonical_workbook_written"] is False
    assert doc["safety"]["applications_submitted"] == 0
    assert doc["safety"]["employer_contacts"] == 0
    assert doc["dedupe"]["applied"] is False
    assert tracker_hashes() == before


def test_the_shortest_source_set_still_collapses_without_a_region_scan():
    """Company Watch + recruiter watch + LinkedIn alone are enough to dedupe."""
    block = pipeline.collect_from_recruiter_watch(RECRUITER, "uk")
    raw = block["candidates"] + pipeline.collect_from_linkedin(LINKEDIN, "uk")["candidates"]
    result = pipeline.collapse_candidates(raw)
    assert result["counts"]["cross_source_duplicates_removed"] == 1
    assert len(result["collapsed"]) == 1
    assert result["collapsed"][0]["discoveries"] == 2


def test_candidate_ids_are_source_independent_for_the_same_vacancy():
    """The canonical id is the same whatever surface discovered it."""
    raw = (pipeline.collect_from_records(REGIONAL)["candidates"]
           + pipeline.collect_from_recruiter_watch(RECRUITER, "uk")["candidates"]
           + pipeline.collect_from_linkedin(LINKEDIN, "uk")["candidates"])
    result = pipeline.collapse_candidates(raw)
    shared = [c for c in result["candidates"] if c["duplicate_discoveries"]][0]
    for provenance in shared["provenance"]:
        assert provenance["candidate_id"] != "" and provenance["candidate_id"]


def test_policy_command_exposes_the_source_registry_and_no_provider_key():
    rc, doc = run_cli(["policy"])
    assert rc == 0
    assert doc["source_registry"] == pipeline.SOURCE_REGISTRY
    assert doc["source_contract"]["contract_version"] == 1
    text = json.dumps(doc)
    for secret in ("api_key", "sk-", "Bearer "):
        assert secret not in text


def test_canonical_key_matches_across_url_variants_and_collapses_to_one():
    """The same posting reached through a tracked link has the same canonical key."""
    a = pipeline.normalise_candidate({"company": "Overlap Test Ltd (NOT A REAL VACANCY)",
                                      "title": "SOC Analyst L1", "location": "London",
                                      "url": "https://overlap-test.invalid/jobs/soc-analyst-l1"},
                                     "src-a")
    b = pipeline.normalise_candidate({"company": "Overlap Test Ltd (NOT A REAL VACANCY)",
                                      "title": "SOC Analyst L1", "location": "London",
                                      "url": "https://overlap-test.invalid/jobs/soc-analyst-l1?utm_source=z"},
                                     "src-b")
    assert pipeline.canonical_key(a) == pipeline.canonical_key(b)
    result = pipeline.collapse_candidates([a, b])
    assert result["counts"]["canonical_candidates"] == 1
    assert result["counts"]["cross_source_duplicates_removed"] == 1
    # each raw discovery keeps its own id, and the canonical record has one id
    assert result["candidates"][0]["candidate_id"]
    assert len({p["candidate_id"] for p in result["candidates"][0]["provenance"]}) == 2
