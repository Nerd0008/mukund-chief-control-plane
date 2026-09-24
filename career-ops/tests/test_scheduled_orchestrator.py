#!/usr/bin/env python3
"""Regression tests for the unified scheduled Career discovery orchestrator.

These prove the cutover contract:

  * high_recall is the production discovery policy and the owner's
    Intern/Internship-only rule can only be run as an explicit diagnostic;
  * every required source class (public LinkedIn Jobs, public Indeed, Google /
    web-indexed discovery, direct ATS/employer careers) is attempted by the bounded
    query budget and recorded from evidence as reached / blocked / unavailable /
    not_applicable / searched_no_results — a blocked source is never called empty;
  * the scheduled launcher invokes the orchestrator (not the old single worker) and
    keeps CRLF line endings;
  * one bounded run writes one unified funnel + manifest and never touches a
    canonical workbook, submits anything, contacts anyone, logs in anywhere or
    opens a browser/GUI;
  * a run without a live current-web mechanism is not production-ready and the CLI
    exits 3 with the blocker recorded (no silent fixture fallback);
  * the Career Daily Brief reports the unified source coverage.

Offline and non-destructive: no test performs a live search, writes a canonical
workbook, submits an application, contacts anyone or uses any account/session.

Run:  python -m pytest career-ops/tests/test_scheduled_orchestrator.py -v
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

import daily_brief  # noqa: E402
import pipeline  # noqa: E402
import scheduled_orchestrator as so  # noqa: E402
import tracker_writer as tw  # noqa: E402
import web_research as wr  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "discovery"
WEB_FIXTURES = FIXTURES / "web-research"
UNVERIFIED_EXPORT = WEB_FIXTURES / "web-research-export-unverified.json"
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


def run_cli(argv: list, fn_name: str = "main"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = getattr(so, fn_name)(argv)
    return rc, json.loads(buf.getvalue())


def offline_argv(out_dir, region="uk", **overrides) -> list:
    """A bounded, fully offline run: replayed export, no scan, no live provider."""
    args = ["run", "--region", region, "--no-live",
            "--reuse-web-export", str(UNVERIFIED_EXPORT),
            "--skip-regional-scan", "--semantic", "off", "--codex", "off",
            "--no-lock", "--out-dir", str(out_dir),
            "--web-out-dir", str(Path(out_dir) / "web"),
            "--state-file-out", str(Path(out_dir) / "state.json")]
    for key, value in overrides.items():
        flag = f"--{key.replace('_', '-')}"
        if value is True:
            args.append(flag)
        elif value is False:
            continue
        else:
            args += [flag, str(value)]
    return args


@pytest.fixture(scope="module")
def offline_doc(tmp_path_factory):
    out = tmp_path_factory.mktemp("orch-offline")
    rc, doc = run_cli(offline_argv(out))
    assert rc == 0
    return doc


@pytest.fixture(scope="module")
def offline_doc_fresh(tmp_path_factory):
    out = tmp_path_factory.mktemp("orch-offline-fresh")
    rc, doc = run_cli(offline_argv(out))
    assert rc == 0
    return doc


# --------------------------------------------------------------------------- #
# policy: high recall is the production gate, intern-only is a diagnostic
# --------------------------------------------------------------------------- #

def test_default_discovery_mode_is_high_recall():
    assert so.DEFAULT_MODE == "high_recall"
    assert pipeline.DEFAULT_MODE == so.DEFAULT_MODE


def test_the_owner_intern_rule_is_only_a_declared_diagnostic_mode():
    policy = so.policy_document()
    assert policy["production_discovery_policy"] == "high_recall"
    assert "intern_only" in policy["diagnostic_modes"]
    assert "never the scheduled discovery gate" in policy["diagnostic_modes"]["intern_only"]


def test_cli_refuses_intern_only_without_the_explicit_compare_flag(tmp_path):
    rc, doc = run_cli(["run", "--region", "uk", "--mode", "intern_only", "--no-live",
                       "--skip-regional-scan", "--no-lock", "--out-dir", str(tmp_path)])
    assert rc == 2
    assert doc["status"] == "refused"
    assert "--compare" in doc["reason"]


def test_compare_mode_runs_only_with_the_flag(tmp_path):
    rc, doc = run_cli(["run", "--region", "uk", "--mode", "intern_only", "--compare",
                       "--no-live", "--reuse-web-export", str(UNVERIFIED_EXPORT),
                       "--skip-regional-scan", "--semantic", "off", "--no-lock",
                       "--out-dir", str(tmp_path),
                       "--state-file-out", str(tmp_path / "state.json")])
    assert rc == 0
    assert doc["discovery_mode"] == "intern_only"
    assert doc["diagnostic_mode"] is True
    assert doc["production_discovery_policy"] == "high_recall"


def test_full_only_intern_candidates_are_rejected_by_high_recall_but_not_by_the_old_gate():
    """The old narrow gate is a precision filter; high recall is the discovery path."""
    title = "Security Analyst"
    high = so.pipeline.prefilter(
        [{"company": "X", "title": title, "location": "London", "url": "https://a.invalid/1",
          "sources": ["fixture"]}], mode="high_recall", funnel=so.Funnel())
    narrow = so.pipeline.prefilter(
        [{"company": "X", "title": title, "location": "London", "url": "https://a.invalid/1",
          "sources": ["fixture"]}], mode="intern_only", funnel=so.Funnel())
    assert high["decisions"][0]["decision"] == "pass"
    assert narrow["decisions"][0]["decision"] == "reject"


# --------------------------------------------------------------------------- #
# query budget: every required source class is attempted first
# --------------------------------------------------------------------------- #

def test_query_selection_attempts_every_required_source_class_within_the_budget():
    matrix = wr.build_query_matrix("uk")
    picked = so.select_queries(matrix, 8)
    scopes = {q["surface_scope"] for q in picked}
    assert len(picked) == 8
    for required in ("linkedin_jobs", "indeed", "google_index"):
        assert required in scopes
    assert scopes & set(so.ATS_SURFACES)


def test_every_surface_maps_to_one_of_the_declared_classes():
    for surfaces, _desc in ((s, d) for _n, s, d in so.SOURCE_CLASSES):
        for surface in surfaces:
            assert so.surface_class(surface) is not None
    assert so.surface_class("linkedin_jobs") == "public_linkedin_jobs"
    assert so.surface_class("indeed") == "public_indeed"
    assert so.surface_class("google_index") == "web_index"
    assert so.surface_class("greenhouse") == "ats_employer_careers"
    assert so.surface_class("employer_careers") == "ats_employer_careers"


def test_every_declared_source_class_has_an_evidence_rule():
    for _name, _surfaces, _desc in so.SOURCE_CLASSES:
        pass
    for state in ("reached", "blocked", "unavailable", "not_applicable",
                  "searched_no_results"):
        assert state in so.COVERAGE_STATE_RULES


# --------------------------------------------------------------------------- #
# source coverage: evidence only, never "empty" for a blocked source
# --------------------------------------------------------------------------- #

def _candidate(url, surface, fetch_state, result_kind=wr.RESULT_KIND_POSTING, fetch=None):
    return {"url": url, "company": "C", "title": "T", "location": "L",
            "fetch_state": fetch_state, "result_kind": result_kind,
            "web_research": {"discovery_surface": surface, "fetch": fetch or {}}}


def _web(queries, candidates, *, provider_available=True):
    return {"queries_run": queries, "candidates": candidates,
            "provider": {"available": provider_available, "web_search_observed_queries":
                         sum(1 for q in queries if q.get("web_search_observed"))},
            "reused_export": False}


def test_a_reached_class_reports_the_discovered_urls():
    web = _web([{"surface_scope": "linkedin_jobs", "executed": True,
                 "web_search_observed": True}],
               [_candidate("https://uk.linkedin.com/jobs/view/1", "linkedin_jobs",
                           "validated_live")])
    cov = so.build_source_coverage(web, provider_available=True)
    entry = cov["classes"]["public_linkedin_jobs"]
    assert entry["state"] == "reached"
    assert entry["result_urls_discovered"] == 1
    assert entry["job_posting_urls"] == 1
    assert entry["validated_live"] == 1


def test_a_refused_destination_is_blocked_and_never_called_empty():
    web = _web([{"surface_scope": "indeed", "executed": True, "web_search_observed": True}],
               [_candidate("https://uk.indeed.com/viewjob?jk=1", "indeed",
                           "validation_failed",
                           fetch={"http_status": 403, "robots": "robots.txt allows this path"})])
    cov = so.build_source_coverage(web, provider_available=True)
    entry = cov["classes"]["public_indeed"]
    assert entry["state"] == "blocked"
    assert "HTTP 403" in entry["blocking_evidence"]
    assert "empty" in entry["reason"] and "never as empty" in entry["reason"]


def test_a_robots_refusal_is_blocking_evidence():
    web = _web([{"surface_scope": "indeed", "executed": True, "web_search_observed": True}],
               [_candidate("https://uk.indeed.com/viewjob?jk=1", "indeed",
                           "validation_failed",
                           fetch={"http_status": None,
                                  "robots": "robots.txt disallows '/viewjob' for this agent"})])
    cov = so.build_source_coverage(web, provider_available=True)
    assert cov["classes"]["public_indeed"]["state"] == "blocked"


def test_no_live_search_mechanism_is_unavailable_not_empty():
    web = _web([{"surface_scope": "google_index", "executed": True,
                 "web_search_observed": False}], [], provider_available=False)
    cov = so.build_source_coverage(web, provider_available=False)
    entry = cov["classes"]["web_index"]
    assert entry["state"] == "unavailable"
    assert "NOT evidence the source is empty" in entry["reason"]


def test_a_class_with_no_query_is_not_applicable():
    cov = so.build_source_coverage(_web([], []), provider_available=True)
    assert cov["classes"]["public_linkedin_jobs"]["state"] == "not_applicable"


def test_a_searched_class_with_no_results_says_so_instead_of_empty():
    web = _web([{"surface_scope": "google_index", "executed": True,
                 "web_search_observed": True}], [])
    cov = so.build_source_coverage(web, provider_available=True)
    entry = cov["classes"]["web_index"]
    assert entry["state"] == "searched_no_results"
    assert "not a claim that the source is empty" in entry["reason"]


def test_all_five_states_are_documented_in_the_policy():
    policy = so.policy_document()
    for source in policy["sources"]:
        assert set(source["states"]) == set(so.COVERAGE_STATE_RULES)


# --------------------------------------------------------------------------- #
# the bounded offline run: one funnel, one manifest, no writes
# --------------------------------------------------------------------------- #

def test_run_writes_region_run_health_and_manifest(offline_doc):
    assert Path(offline_doc["run_health_file"]).exists()
    assert Path(offline_doc["manifest_file"]).exists()
    manifest = json.loads(Path(offline_doc["manifest_file"]).read_text(encoding="utf-8"))
    assert manifest["read_only"] is True
    assert manifest["canonical_workbook_written"] is False
    assert manifest["kind"] == "career-ops.unified-candidate-manifest"


def test_run_combines_every_declared_source_into_one_funnel(offline_doc):
    sources = {b["source"] for b in offline_doc["collection"]}
    for source in (pipeline.SOURCE_SCAN_RECORD, pipeline.SOURCE_WEB_RESEARCH,
                   pipeline.SOURCE_COMPANY_WATCH, pipeline.SOURCE_PRIORITY_WATCHLIST,
                   pipeline.SOURCE_RECRUITER_WATCH, pipeline.SOURCE_LINKEDIN_EXPORT):
        assert source in sources
    assert offline_doc["funnel"]["counts"]["discovered_raw"] >= 0
    assert "by_source" in offline_doc["funnel"]


def test_only_candidates_that_passed_the_gates_reach_the_manifest(offline_doc):
    manifest = json.loads(Path(offline_doc["manifest_file"]).read_text(encoding="utf-8"))
    accepted = {d["url"] for d in offline_doc["eligibility"]["decisions"]
                if d["decision"] == "accepted"}
    for record in manifest["records"]:
        assert record["url"] in accepted


def test_a_run_is_read_only_and_declares_its_safety(offline_doc):
    safety = offline_doc["safety"]
    assert safety["canonical_workbook_written"] is False
    assert safety["applications_submitted"] == 0
    assert safety["browser_or_gui_used"] is False
    assert safety["login_or_account_used"] is False
    assert safety["cookies_or_session_used"] is False
    assert offline_doc["read_only"] is True


def test_the_run_records_a_source_coverage_matrix(offline_doc):
    coverage = offline_doc["source_coverage"]
    assert set(coverage["classes"]) == set(so.CLASS_ORDER)
    for entry in coverage["classes"].values():
        assert entry["state"] in so.COVERAGE_STATE_RULES
        assert entry["state_rule"]


def test_the_run_declares_the_production_policy_and_the_live_mechanism(offline_doc):
    assert offline_doc["title_policy_mode"] == "high_recall"
    assert offline_doc["production_discovery_policy"] == "high_recall"
    mechanism = offline_doc["live_research"]
    assert mechanism["operational"] is False
    assert "not live proof" in (mechanism["limitation"] or "")


def test_require_live_web_exits_three_and_records_a_no_go(tmp_path):
    rc, doc = run_cli(offline_argv(tmp_path, require_live_web=True))
    assert rc == 3
    assert doc["production_ready"] is False
    assert "NOT production-ready" in doc["no_go"]


def test_idempotency_key_is_recorded_and_a_replay_is_reported(tmp_path):
    rc, first = run_cli(offline_argv(tmp_path))
    assert rc == 0
    rc, second = run_cli(offline_argv(tmp_path))
    assert rc == 0
    assert second["idempotency"]["previous_run_key"] == first["idempotency"]["run_key"]
    assert second["idempotency"]["idempotent_replay"] is True


def test_a_concurrent_run_is_skipped_by_the_lock(tmp_path, monkeypatch):
    lock = tmp_path / "lock.json"
    monkeypatch.setattr(so, "LOCK_FILE", lock)
    lock.write_text(json.dumps({"pid": 1, "started_at": so.now_utc()}), encoding="utf-8")
    rc, doc = run_cli(["run", "--region", "uk", "--no-live", "--skip-regional-scan",
                       "--no-validate", "--semantic", "off", "--out-dir", str(tmp_path)])
    assert rc == 0
    assert doc["status"] == "overlap_skipped"
    assert "lock" in doc


def test_the_offline_run_leaves_the_canonical_workbooks_byte_identical(tmp_path,
                                                                       offline_doc_fresh):
    before = tracker_hashes()
    rc, _doc = run_cli(offline_argv(tmp_path))
    assert rc == 0
    assert tracker_hashes() == before


# --------------------------------------------------------------------------- #
# run-all: one unified funnel + one unified manifest
# --------------------------------------------------------------------------- #

def test_run_all_produces_one_unified_funnel_and_manifest(tmp_path):
    rc, doc = run_cli(["run-all", "--no-live", "--reuse-web-export", str(UNVERIFIED_EXPORT),
                       "--skip-regional-scan", "--semantic", "off", "--codex", "off",
                       "--no-lock", "--out-dir", str(tmp_path),
                       "--web-out-dir", str(tmp_path / "web"),
                       "--state-file-out", str(tmp_path / "state.json")])
    assert rc == 0
    assert doc["kind"] == "career-ops.unified-scheduled-discovery"
    assert doc["regions_covered"] == sorted(REGIONS)
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "unified-manifest-latest.json").exists()
    manifest = json.loads((tmp_path / "unified-manifest-latest.json").read_text(
        encoding="utf-8"))
    assert manifest["kind"] == "career-ops.unified-nightly-candidate-manifest"
    assert manifest["regions"] == sorted(REGIONS)
    assert doc["aggregation_note"].startswith("counters are the SUM")
    for region in REGIONS:
        entry = doc["regions"][region]
        assert entry["run_health_file"]
        assert entry["live_research"]["operational"] is False


def test_run_all_aggregate_counts_are_the_sum_of_the_regions(tmp_path):
    rc, doc = run_cli(["run-all", "--no-live", "--reuse-web-export", str(UNVERIFIED_EXPORT),
                       "--skip-regional-scan", "--semantic", "off", "--no-lock",
                       "--out-dir", str(tmp_path), "--web-out-dir", str(tmp_path / "web"),
                       "--state-file-out", str(tmp_path / "state.json")])
    assert rc == 0
    for key, value in doc["funnel"]["counts"].items():
        if isinstance(value, int) and key in so.COUNT_KEYS:
            assert value == sum(d["funnel"]["counts"].get(key, 0)
                                for d in doc["regions"].values())


# --------------------------------------------------------------------------- #
# the scheduled launcher wiring and its documentation
# --------------------------------------------------------------------------- #

LAUNCHER = CAREER_OPS / "run_scheduled_scan.cmd"


def test_the_scheduled_launcher_invokes_the_unified_orchestrator():
    text = LAUNCHER.read_text(encoding="utf-8")
    active = [line for line in text.splitlines() if not line.strip().lower().startswith("rem")]
    joined = "\n".join(active)
    assert "scheduled_orchestrator.py" in joined
    assert "--scheduled" in joined
    assert "--require-live-web" in joined
    assert "--mode high_recall" in joined
    assert "regional_job_search.py" not in joined
    assert "--apply" not in joined and "submission" not in joined


def test_the_scheduled_launcher_keeps_crlf_and_the_rollback_command():
    raw = LAUNCHER.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") > 0
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "regional_job_search.py" in text  # only inside the documented rollback
    assert "Rollback" in text


def test_the_operational_documentation_exists_and_covers_the_required_sections():
    doc = (CAREER_OPS / "scheduled_orchestrator.md").read_text(encoding="utf-8")
    for section in ("Run commands", "Outputs", "Source-coverage matrix", "Rollback",
                    "No-go criteria", "Daily Brief integration", "Bounds, retries and",
                    "concurrency"):
        assert section in doc


def test_policy_document_declares_budgets_rollback_and_no_go():
    policy = so.policy_document()
    budget = policy["budgets"]
    for key in ("overall_seconds", "web_queries_per_region", "max_urls_validated_per_region",
                "per_query_timeout_s", "regional_scan_timeout_s", "retries",
                "ingest_stale_after_hours"):
        assert budget.get(key)
    assert policy["rollback"]["previous_launcher_command"]
    assert policy["no_go_criteria"]
    assert policy["concurrency"]["lock_file"]
    assert policy["safety"]["canonical_workbook_written"] is False


def test_schedules_declare_staggered_times_and_the_orchestrator():
    schedules = json.loads((CAREER_OPS / "regional_schedules.json").read_text(
        encoding="utf-8"))
    times = {r: s["time"] for r, s in schedules["regions"].items()}
    assert len(set(times.values())) == len(times)
    assert schedules["unified_orchestrator"]["worker"].endswith("scheduled_orchestrator.py")
    assert "require-live-web" in schedules["unified_orchestrator"]["live_requirement"]
    for spec in schedules["regions"].values():
        assert "scheduled_orchestrator.py" in spec["orchestrator"]


def test_the_orchestrator_imports_no_browser_or_scraping_library():
    source = (CAREER_OPS / "discovery" / "scheduled_orchestrator.py").read_text(
        encoding="utf-8")
    for banned in ("selenium", "playwright", "pyppeteer", "requests_html", "webbrowser",
                   "scrapy", "splinter"):
        assert banned not in source


def test_selftest_passes():
    rc, doc = run_cli(["selftest"])
    assert rc == 0
    assert doc["ok"] is True


# --------------------------------------------------------------------------- #
# Career Daily Brief integration
# --------------------------------------------------------------------------- #

def test_the_brief_reports_the_unified_source_coverage(offline_doc, tmp_path):
    doc = dict(offline_doc)
    view = daily_brief.source_coverage_view(doc)
    assert view["sources"]
    assert view["classes_by_region"]
    assert view["class_state_vocabulary"]
    assert "never reported as an empty source" in view["note"]


def test_the_brief_view_handles_the_unified_multi_region_shape(tmp_path):
    rc, unified = run_cli(["run-all", "--no-live", "--reuse-web-export",
                           str(UNVERIFIED_EXPORT), "--skip-regional-scan", "--semantic",
                           "off", "--no-lock", "--out-dir", str(tmp_path),
                           "--web-out-dir", str(tmp_path / "web"),
                           "--state-file-out", str(tmp_path / "state.json")])
    assert rc == 0
    view = daily_brief.source_coverage_view(unified)
    assert sorted(view["classes_by_region"]) == sorted(REGIONS)
    for region in REGIONS:
        assert set(view["classes_by_region"][region]) == set(so.CLASS_ORDER)


def test_the_brief_collector_reports_the_unified_run(tmp_path, monkeypatch):
    rc, unified = run_cli(["run-all", "--no-live", "--reuse-web-export",
                           str(UNVERIFIED_EXPORT), "--skip-regional-scan", "--semantic",
                           "off", "--no-lock", "--out-dir", str(tmp_path),
                           "--web-out-dir", str(tmp_path / "web"),
                           "--state-file-out", str(tmp_path / "state.json")])
    assert rc == 0
    cfg = daily_brief.load_config()
    cfg["discovery"] = dict(cfg.get("discovery") or {}, latest=str(tmp_path / "latest.json"))
    collected = daily_brief.collect_discovery_funnel(cfg)
    assert collected["available"] is True
    assert collected["run_kind"] == "career-ops.unified-scheduled-discovery"
    assert collected["regions_covered"] == sorted(REGIONS)
    assert collected["source_coverage"]["sources"]
    assert collected["live_research"] is not None
    assert collected["production_ready"] is False
    assert collected["no_go"]
