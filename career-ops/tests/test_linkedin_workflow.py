#!/usr/bin/env python3
"""Tests for the minimal LinkedIn workflow (read-only intake + drafts).

Offline and non-destructive: nothing here opens a network connection, starts a
browser, signs in to LinkedIn or mutates an account. The canonical regional
workbooks are copied before any write, and their hashes are asserted unchanged.

Run:  python -m pytest career-ops/tests/test_linkedin_workflow.py -v
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import linkedin_workflow as liw  # noqa: E402
import cv_workflow as cvw  # noqa: E402
import tracker_writer as tw  # noqa: E402

CFG = liw.load_config()
FIXTURE_INBOX = CAREER_OPS / "tests" / "fixtures" / "linkedin"
PROFILES = tw.load_profiles(str(cvw.profiles_path(liw.cv_config(CFG))))
CANONICAL = Path(PROFILES["regions"]["uk"]["tracker"])
NODE = shutil.which(CFG["fact_gate"]["node"])

needs_install = pytest.mark.skipif(
    not all(p.exists() for p in cvw.source_paths(liw.cv_config(CFG)).values()),
    reason="Career Ops install sources are not present on this machine")
needs_workbook = pytest.mark.skipif(not CANONICAL.exists(),
                                    reason="canonical UK workbook not present on this machine")
needs_node = pytest.mark.skipif(NODE is None, reason="node is unavailable")


def signals() -> list[dict]:
    return liw.collect_signals(CFG, FIXTURE_INBOX)["signals"]


def one_job(**kw) -> list[dict]:
    base = {"company": "Example Analytics Ltd", "title": "Cyber Security Intern",
            "location": "London, United Kingdom", "posted_at": "2026-09-20",
            "url": "https://job-boards.greenhouse.io/exampleanalytics/jobs/999000111",
            "source": "linkedin-fixture", "signal_kind": "job_signal",
            "provenance": {"file": "fixture", "file_sha256": "x", "index": 0}}
    base.update(kw)
    return [base]


# --------------------------------------------------------------------------- #
# intake
# --------------------------------------------------------------------------- #

def test_intake_parses_the_fixture_inbox():
    doc = liw.collect_signals(CFG, FIXTURE_INBOX)
    assert doc["ok"] is True
    assert doc["counts"]["job_signals"] >= 3
    assert doc["counts"]["company_signals"] >= 1


def test_intake_read_only_contract_holds():
    roc = liw.collect_signals(CFG, FIXTURE_INBOX)["read_only_contract"]
    assert roc["network_used"] is False
    assert roc["urls_fetched"] == 0
    assert roc["browser_launched"] is False
    assert roc["linkedin_authenticated"] is False
    assert roc["account_mutations"] == 0


def test_text_line_without_a_url_is_not_guessed():
    found, unclassified = liw.parse_text_signals(
        "- [Cyber Security Intern](https://example.com/jobs/1)\n"
        "A line with no link at all\n")
    assert len(found) == 1 and found[0]["url"] == "https://example.com/jobs/1"
    assert len(unclassified) == 1
    assert "no URL" in unclassified[0]["reason"]


def test_markdown_link_title_and_company_are_split():
    found, _ = liw.parse_text_signals(
        "- [Cyber Security Intern — Example Analytics Ltd](https://example.com/jobs/1)")
    assert found[0]["title"] == "Cyber Security Intern"
    assert found[0]["company"] == "Example Analytics Ltd"


def test_classify_distinguishes_jobs_companies_and_unknowns():
    assert liw.classify({"company": "A", "title": "B",
                         "url": "https://x.example/a"})["signal_kind"] == "job_signal"
    assert liw.classify({"company": "A"})["signal_kind"] == "company_signal"
    assert liw.classify({"title": "orphan"})["signal_kind"] == "unclassified"


def test_signal_carries_file_provenance():
    for signal in signals():
        prov = signal["provenance"]
        assert Path(prov["file"]).exists()
        assert len(prov["file_sha256"]) == 64


def test_intake_missing_inbox_is_reported_not_silently_empty(tmp_path):
    doc = liw.collect_signals(CFG, tmp_path / "nope")
    assert doc["ok"] is False
    assert "not found" in doc["reason"]


def test_unsupported_extension_is_skipped_explicitly(tmp_path):
    (tmp_path / "notes.exe").write_text("binary-ish", encoding="utf-8")
    doc = liw.collect_signals(CFG, tmp_path)
    assert doc["files"][0]["skipped"]
    assert doc["counts"]["signals"] == 0


# --------------------------------------------------------------------------- #
# the workflow has no network / browser capability at all
# --------------------------------------------------------------------------- #

def test_module_imports_no_network_or_browser_library():
    src = (CAREER_OPS / "linkedin_workflow.py").read_text(encoding="utf-8")
    imports = "\n".join(line for line in src.splitlines()
                        if re.match(r"^\s*(import|from)\s", line))
    for banned in ("urllib", "requests", "socket", "http.client", "httpx", "aiohttp",
                   "webbrowser", "playwright", "selenium", "pyppeteer", "linkedin_api"):
        assert not re.search(rf"\b{re.escape(banned)}\b", imports), \
            f"{banned} must not be imported by the read-only LinkedIn workflow"


def test_not_performed_declares_the_absent_capabilities():
    joined = " ".join(CFG["not_performed"]).casefold()
    for phrase in ("login", "browser", "posting", "application"):
        assert phrase in joined


# --------------------------------------------------------------------------- #
# owner action gate
# --------------------------------------------------------------------------- #

def test_guard_refuses_every_external_action(tmp_path, monkeypatch):
    monkeypatch.setattr(liw, "runtime_dir", lambda cfg: tmp_path)
    for action in ("post", "message", "connection_request", "apply", "profile_update",
                   "reaction", "follow"):
        result = liw.guard_action(CFG, action)
        assert result["allowed"] is False, action
        assert result["owner_gated"] is True
        assert result["performed"] is False


def test_guard_does_not_block_read_and_draft_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(liw, "runtime_dir", lambda cfg: tmp_path)
    for action in ("intake", "dedupe", "draft"):
        assert liw.guard_action(CFG, action)["allowed"] is True


def test_guard_logs_the_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(liw, "runtime_dir", lambda cfg: tmp_path)
    liw.guard_action(CFG, "post")
    logged = (tmp_path / "action-gate-log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(logged) == 1
    assert json.loads(logged[0])["owner_gated"] is True


# --------------------------------------------------------------------------- #
# dedupe
# --------------------------------------------------------------------------- #

@needs_workbook
def test_dedupe_flags_a_posting_already_in_canonical_state(tmp_path):
    copy = tmp_path / CANONICAL.name
    shutil.copy2(CANONICAL, copy)
    region_cfg = dict(tw.region_config(PROFILES, "uk"))
    region_cfg["region"] = "uk"
    tr = tw.Tracker(copy, region_cfg)
    try:
        url_idx = tw.column_index_from_string(region_cfg["dedupe"]["url_column"]) - 1
        existing_url = None
        for row in tr.data_rows():
            if row[url_idx]:
                existing_url = row[url_idx]
                break
    finally:
        tr.wb.close()
    assert existing_url, "canonical workbook has no URL to test against"

    result = liw.dedupe_signals(CFG, "uk",
                                one_job(url=existing_url, company="Existing Co",
                                        title="Existing Role"),
                                tracker_override=str(copy))
    decision = result["job_decisions"][0]
    assert decision["decision"].startswith("duplicate"), decision
    assert result["counts"]["duplicates"] == 1


def test_dedupe_merges_the_same_posting_within_one_batch():
    batch = one_job(location=None, posted_at=None) + one_job()
    result = liw.dedupe_signals(CFG, "uk", batch)
    assert len(result["job_decisions"]) == 1
    merged = result["job_decisions"][0]
    assert merged["location"] == "London, United Kingdom"
    assert merged["posted_at"] == "2026-09-20"
    assert merged["merged_signals"] == 1
    assert merged["owner_filter_eligible"] is True
    assert merged["merged_provenance"], "merged provenance must be retained"


@needs_workbook
def test_dedupe_does_not_touch_the_canonical_tracker():
    before = tw.sha256_file(CANONICAL)
    liw.dedupe_signals(CFG, "uk", one_job())
    assert tw.sha256_file(CANONICAL) == before


def test_unknown_company_is_not_claimed_as_known_to_company_watch():
    result = liw.dedupe_signals(CFG, "uk", one_job(company="Zzz Unlikely Fixture Company Ltd"))
    assert result["job_decisions"][0]["company_known_to_company_watch"] is False


def test_dedupe_reports_the_shared_engine():
    result = liw.dedupe_signals(CFG, "uk", one_job())
    assert result["dedupe_engine"].startswith("company_watch.build_shared_dedupe")
    assert "company_watch" in result


def test_company_signal_decision_is_review_only():
    result = liw.dedupe_signals(CFG, "uk", [
        {"company": "Zzz Unlikely Fixture Company Ltd", "signal_kind": "company_signal",
         "provenance": {"file": "fixture"}}])
    decision = result["company_decisions"][0]
    assert decision["decision"] in ("new-company-signal", "duplicate")
    assert "review signal only" in decision["reason"] or \
        "not present in Career Ops" in decision["reason"]


# --------------------------------------------------------------------------- #
# handoff
# --------------------------------------------------------------------------- #

def test_manifest_never_carries_application_state():
    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    assert manifest["ok"] is True
    for record in manifest["records"]:
        assert "application_status" not in record
        assert "status" not in record
    assert manifest["application_state_written"] is False


def test_manifest_provenance_names_the_linkedin_signal_source():
    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    prov_col = manifest["provenance_column"]
    value = manifest["records"][0][prov_col]
    assert value.startswith(liw.LINKEDIN_PROVENANCE_PREFIX)
    assert "read-only LinkedIn signal intake" in value
    assert "NOT human-verified" in value


def test_manifest_refuses_a_region_without_a_non_owner_provenance_column(monkeypatch):
    monkeypatch.setattr(liw.cw, "provenance_targets",
                        lambda region_cfg: {"provenance": None, "prior_signal": None,
                                            "live_status": None, "posted_date": None,
                                            "last_checked": None,
                                            "owner_column_keys_excluded": []})
    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    assert manifest["ok"] is False
    assert "no non-owner provenance column" in manifest["reason"]


@needs_workbook
def test_handoff_dry_run_is_default_and_leaves_the_canonical_tracker_untouched():
    before = tw.sha256_file(CANONICAL)
    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    result = liw.handoff(CFG, "uk", manifest, apply=False)
    assert result["mode"] == "dry-run"
    assert (result["result"] or {}).get("applied") is False
    assert tw.sha256_file(CANONICAL) == before


@needs_workbook
def test_handoff_manifest_is_written_inside_the_linkedin_runtime_only(tmp_path):
    """Company Watch reads its own handoff manifests; LinkedIn must not litter them."""
    cw_runtime = liw.CONTROL_PLANE / liw.cw_config(CFG)["runtime_dir"]
    before = sorted(p.name for p in cw_runtime.glob("handoff-*.json")) if cw_runtime.exists() else []
    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    result = liw.handoff(CFG, "uk", manifest, apply=False)
    manifest_path = Path(result["manifest"])
    assert "linkedin" in str(manifest_path).casefold()
    after = sorted(p.name for p in cw_runtime.glob("handoff-*.json")) if cw_runtime.exists() else []
    assert after == before, "a LinkedIn run must not write into Company Watch's runtime"


@needs_workbook
def test_handoff_apply_to_a_copy_appends_verifies_and_leaves_canonical_untouched(tmp_path):
    copy = tmp_path / CANONICAL.name
    shutil.copy2(CANONICAL, copy)
    copy_before = tw.sha256_file(copy)
    canonical_before = tw.sha256_file(CANONICAL)

    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    assert manifest["counts"]["selected"] == 1
    result = liw.handoff(CFG, "uk", manifest, tracker=str(copy), apply=True,
                         backup_dir=str(tmp_path / "backups"))
    payload = result["result"]
    assert payload["applied"] is True, payload.get("error")
    assert payload["counts"]["appended"] == 1
    assert payload["verification"]["ok"] is True
    assert Path(payload["backup"]).exists()
    assert tw.sha256_file(copy) != copy_before
    assert tw.sha256_file(CANONICAL) == canonical_before

    region_cfg = dict(tw.region_config(PROFILES, "uk"))
    region_cfg["region"] = "uk"
    tr = tw.Tracker(copy, region_cfg)
    try:
        col = region_cfg["field_map"][manifest["provenance_column"]]
        values = [tr.ws[f"{col}{r}"].value for r in
                  range(region_cfg["first_data_row"], tr.last_data_row() + 1)]
    finally:
        tr.wb.close()
    assert any(isinstance(v, str) and v.startswith(liw.LINKEDIN_PROVENANCE_PREFIX)
               for v in values), "LinkedIn provenance was not written"


@needs_workbook
def test_replaying_a_written_linkedin_job_is_deduped(tmp_path):
    copy = tmp_path / CANONICAL.name
    shutil.copy2(CANONICAL, copy)
    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    liw.handoff(CFG, "uk", manifest, tracker=str(copy), apply=True,
                backup_dir=str(tmp_path / "backups"))
    replay = liw.dedupe_signals(CFG, "uk", one_job(), tracker_override=str(copy))
    assert replay["job_decisions"][0]["decision"].startswith("duplicate")


@needs_workbook
def test_handoff_manifest_records_posted_date_when_known():
    dedupe = liw.dedupe_signals(CFG, "uk", one_job())
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    record = manifest["records"][0]
    posted = manifest["provenance_targets"]["posted_date"]
    assert posted and record[posted] == "2026-09-20"


def test_ineligible_signal_is_excluded_from_the_manifest_by_default():
    dedupe = liw.dedupe_signals(CFG, "uk", one_job(location="Austin, United States"))
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe)
    assert manifest["counts"]["selected"] == 0


def test_ineligible_signal_can_only_be_included_as_a_labelled_test_row():
    dedupe = liw.dedupe_signals(CFG, "uk", one_job(location="Austin, United States"))
    manifest = liw.build_handoff_manifest(CFG, "uk", dedupe, include_ineligible_as_test=True)
    assert manifest["counts"]["selected"] == 0, \
        "a non-UK posting must not be routed into the UK tracker even as a test row"


# --------------------------------------------------------------------------- #
# drafts
# --------------------------------------------------------------------------- #

@needs_install
@needs_node
def test_drafts_are_unsent_and_fact_gated(tmp_path):
    result = liw.build_linkedin_drafts(CFG, out_dir=tmp_path, scratch=tmp_path / "fg")
    assert result["ok"] is True
    assert result["fact_gate"]["verdict"] in ("pass", "warn")
    assert result["posts_performed"] == 0
    assert result["sends_performed"] == 0
    for draft in result["drafts"]:
        assert draft["status"] == "draft_unsent"
        assert draft["publish_requires"] == "explicit owner authorization"
        assert draft["sources"], f"{draft['kind']} draft has no source"

    outreach = [d for d in result["drafts"] if d["kind"] == "outreach"][0]
    assert outreach["sent"] is False


@needs_install
@needs_node
def test_draft_bodies_are_canonical_text_only(tmp_path):
    """Every draft line is either canonical CV text or a declared structural phrase.

    The structural list is imported from the module rather than copied, so a new
    generated phrasing can never pass this test without being declared.
    """
    result = liw.build_linkedin_drafts(CFG, out_dir=tmp_path, scratch=tmp_path / "fg")
    canonical = set()
    for line in cvw.read_text(cvw.source_paths(liw.cv_config(CFG))["cv_md"]).splitlines():
        s = line.strip()
        if s:
            canonical.add(s)
            canonical.add(s.lstrip("#").strip())
            canonical.add(s[1:].strip() if s.startswith("-") else s)
    allowed_framing = set(liw.STRUCTURAL_PHRASES)
    assert allowed_framing, "the structural-phrase contract must not be empty"
    for draft in result["drafts"]:
        body = draft.get("body") or draft.get("about") or ""
        for line in body.splitlines():
            s = line.strip()
            if not s or s in allowed_framing:
                continue
            if draft["kind"] == "outreach" and s == draft["body"].splitlines()[-1]:
                continue  # the owner's own canonical full name
            assert s in canonical, f"non-canonical line in {draft['kind']} draft: {s!r}"


# --------------------------------------------------------------------------- #
# networking / recruiter / hiring-manager outreach drafts (B21)
# --------------------------------------------------------------------------- #

JOB_FIXTURE = CAREER_OPS / "tests" / "fixtures" / "job-intelligence" / "job-record-uk.json"


def _job() -> dict:
    return json.loads(JOB_FIXTURE.read_text(encoding="utf-8"))


@needs_install
@needs_node
def test_outreach_variants_are_drafts_with_explicit_unsent_state(tmp_path):
    result = liw.build_linkedin_drafts(CFG, out_dir=tmp_path, scratch=tmp_path / "fg")
    outreach = [d for d in result["drafts"] if d["kind"] == "outreach"]
    assert result["counts"]["outreach_networking"] == 1
    assert result["counts"]["outreach_recruiter"] == 1
    assert result["counts"]["outreach_hiring_manager"] == 0, \
        "no job context was supplied, so no hiring-manager draft may be produced"
    for draft in outreach:
        st = draft["unsent_state"]
        assert draft["status"] == "draft_unsent"
        assert draft["sent"] is False and draft["recipient"] is None
        assert st["sent"] is False and st["sent_at"] is None
        assert st["recipient_selected"] is False and st["recipient"] is None
        assert st["connection_request_created"] is False
        assert st["message_queued"] is False and st["scheduled"] is False
        assert st["attachments_sent"] == 0
        assert st["owner_approval_required"] is True
        assert draft["publish_requires"] == "explicit owner authorization"
    assert result["messages_queued"] == 0
    assert result["connection_requests_created"] == 0
    assert result["sends_performed"] == 0


@needs_install
@needs_node
def test_every_draft_carries_provenance(tmp_path):
    result = liw.build_linkedin_drafts(CFG, out_dir=tmp_path, scratch=tmp_path / "fg")
    paths = cvw.source_paths(liw.cv_config(CFG))
    for draft in result["drafts"]:
        prov = draft["provenance"]
        assert prov["generator"] == "career-ops/linkedin_workflow.py"
        assert prov["canonical_sources"][str(paths["cv_md"])] == cvw.sha256_file(paths["cv_md"])
        assert prov["source_lines"] == [f"cv.md:{s['line']}" for s in draft["sources"]]
        assert all(line.startswith("cv.md:") for line in prov["source_lines"])


@needs_install
@needs_node
def test_hiring_manager_outreach_is_produced_only_from_a_job_context(tmp_path):
    job = _job()
    drafts = liw.build_outreach_drafts(CFG, liw.canonical_blocks(CFG), job=job)
    hm = [d for d in drafts if d.get("subtype") == "hiring_manager"]
    assert len(hm) == 1
    ref = hm[0]["references_job"]
    assert ref["title"] == job["title"] and ref["company"] == job["company"]
    assert ref["provenance"].startswith("job context read from the Career Ops record")
    assert hm[0]["sent"] is False and hm[0]["recipient"] is None
    assert "No recipient is chosen" in hm[0]["notes"][0]


@needs_install
@needs_node
def test_outreach_drafts_never_name_a_recipient_or_a_channel_that_sends(tmp_path):
    drafts = liw.build_outreach_drafts(CFG, liw.canonical_blocks(CFG), job=None)
    assert {d["subtype"] for d in drafts} == {"networking", "recruiter"}
    for draft in drafts:
        assert draft["recipient"] is None
        assert "owner-sent only" in draft["channel"]
        assert draft["status"] == "draft_unsent"


@needs_install
@needs_node
def test_profile_headline_is_verbatim_from_profile_yml(tmp_path):
    result = liw.build_linkedin_drafts(CFG, out_dir=tmp_path, scratch=tmp_path / "fg")
    profile = [d for d in result["drafts"] if d["kind"] == "profile"][0]
    root = cvw.install_root(liw.cv_config(CFG))
    text = (root / "config" / "profile.yml").read_text(encoding="utf-8")
    assert f'headline: "{profile["headline"]}"' in text or \
        f"headline: {profile['headline']}" in text


@needs_install
@needs_node
def test_draft_artifacts_are_written_and_listed(tmp_path):
    result = liw.build_linkedin_drafts(CFG, out_dir=tmp_path, scratch=tmp_path / "fg")
    doc = json.loads(Path(result["drafts_path"]).read_text(encoding="utf-8"))
    assert len(doc["drafts"]) == result["counts"]["total"]
    assert "unsent" in Path(result["drafts_markdown"]).read_text(encoding="utf-8").casefold()


@needs_install
@needs_node
def test_no_canonical_asset_is_modified_by_a_draft_run(tmp_path):
    paths = cvw.source_paths(liw.cv_config(CFG))
    before = {k: cvw.sha256_file(p) for k, p in paths.items()}
    liw.build_linkedin_drafts(CFG, out_dir=tmp_path, scratch=tmp_path / "fg")
    assert {k: cvw.sha256_file(p) for k, p in paths.items()} == before
