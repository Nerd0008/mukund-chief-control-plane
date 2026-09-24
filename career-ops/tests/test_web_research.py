#!/usr/bin/env python3
"""Tests for the bounded, read-only open-web job research lane (roster B26).

These prove the successor contract: the open-web research surface normalises
LinkedIn / Indeed / ATS / employer-career search results into the ONE unified
candidate schema, preserves full per-result provenance, collapses cross-source
duplicates, and fails closed — a destination that was not validated live can
never reach a tracker manifest, and a "result" the research worker did not
actually search for is never accepted.

Offline and non-destructive: no test launches a browser, logs into anything,
calls a live provider, writes a canonical workbook, or contacts an employer,
recruiter or agency. The one network-capable function (URL validation) is
exercised against a faked HTTP layer, never the real network.

Run:  python -m pytest career-ops/tests/test_web_research.py -v
"""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import sys
import urllib.parse
from contextlib import redirect_stdout
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
CONTROL_PLANE = CAREER_OPS.parent
sys.path.insert(0, str(CAREER_OPS))
sys.path.insert(0, str(CAREER_OPS / "discovery"))

import pipeline  # noqa: E402
import tracker_writer as tw  # noqa: E402
import web_research as wr  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "discovery"
WEB_FIXTURES = FIXTURES / "web-research"
CAPTURE = WEB_FIXTURES / "captured-codex-search.json"
UNVERIFIED_EXPORT = WEB_FIXTURES / "web-research-export-unverified.json"
REGIONAL = FIXTURES / "regional-overlap.json"
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


def run_cli(argv: list) -> tuple:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = pipeline.main(argv)
    return rc, json.loads(buf.getvalue())


def run_lane_cli(argv: list) -> tuple:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = wr.main(argv)
    return rc, json.loads(buf.getvalue())


def fixture_queries() -> list:
    """The four capture queries as matrix entries (matching the capture by query)."""
    doc = json.loads(CAPTURE.read_text(encoding="utf-8"))
    return [{k: q.get(k) for k in ("query_id", "query", "region", "role_family",
                                   "surface_scope", "query_provenance")}
            for q in doc["queries"]]


def export_from_capture(tmp_path, *, validate_fn=None) -> Path:
    """Run the lane over the synthetic capture and write a real research export."""
    doc = wr.run_research(fixture_queries(), wr.CapturedResultsProvider(CAPTURE),
                          region="uk", validate=validate_fn is not None,
                          validate_fn=validate_fn)
    path = Path(tmp_path) / "web-research-export.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def matrix_shaped_capture(tmp_path, n: int = 4) -> Path:
    """A capture of the first ``n`` generated matrix queries (matrix <-> capture round-trip)."""
    matrix = wr.build_query_matrix("uk")[:n]
    queries = []
    for i, q in enumerate(matrix):
        queries.append(dict(q, executed=True, web_search_observed=True,
                            executed_queries=[q["query"]],
                            results=[{"title": f"Graduate SOC Analyst @ Fixture {i} Ltd "
                                               f"(NOT A REAL VACANCY)",
                                      "url": f"https://fixture-{i}.invalid/jobs/graduate-soc-{i}",
                                      "snippet": "London, United Kingdom (NOT A REAL VACANCY)"}]))
    doc = {"kind": wr.EXPORT_KIND, "not_a_real_vacancy": True,
           "captured_from": "codex-web-search", "captured_at": "2026-09-24T06:00:00Z",
           "queries": queries}
    path = Path(tmp_path) / "matrix-capture.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def fake_validate_live(url, **kw):
    return {"url": url, "status": wr.FETCH_VALIDATED_LIVE, "http_status": 200,
            "canonical_url": wr.canonical_url(url), "final_url": url,
            "page_title": None, "meta_description": None, "robots": "test", "error": None}


def fake_validate_failed(url, **kw):
    return {"url": url, "status": wr.FETCH_VALIDATION_FAILED, "http_status": 404,
            "canonical_url": wr.canonical_url(url), "final_url": url,
            "page_title": None, "meta_description": None, "robots": "test",
            "error": "HTTP 404"}


# --------------------------------------------------------------------------- #
# fixtures are synthetic and privacy-safe
# --------------------------------------------------------------------------- #

def test_capture_fixture_is_synthetic_and_uses_reserved_hosts():
    doc = json.loads(CAPTURE.read_text(encoding="utf-8"))
    text = CAPTURE.read_text(encoding="utf-8")
    assert doc["not_a_real_vacancy"] is True
    assert "NOT A REAL" in text
    # every discovered RESULT URL is a reserved .invalid host (the surface token may
    # appear earlier in the hostname, but the registrable TLD is always .invalid)
    for q in doc["queries"]:
        for r in q["results"]:
            host = urllib.parse.urlsplit(r["url"]).hostname or ""
            assert host.endswith(".invalid"), f"capture result uses a real host: {r['url']}"


def test_unverified_export_fixture_is_synthetic():
    doc = json.loads(UNVERIFIED_EXPORT.read_text(encoding="utf-8"))
    assert doc["not_a_real_vacancy"] is True
    states = {c["fetch_state"] for c in doc["candidates"]}
    assert states == {"validated_live", "discovered_unverified", "validation_failed"}


# --------------------------------------------------------------------------- #
# surface classification (LinkedIn / Indeed / ATS / employer)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("url,surface", [
    # real public hostnames, as literals — no product data is stored here
    ("https://www.linkedin.com/jobs/view/4012345678", "linkedin_jobs"),
    ("https://uk.indeed.com/viewjob?jk=abc", "indeed"),
    ("https://job-boards.greenhouse.io/acme/jobs/123", "greenhouse"),
    ("https://jobs.lever.co/acme/123", "lever"),
    ("https://acme.wd1.myworkdayjobs.com/en-US/careers/job/123", "workday"),
    ("https://jobs.ashbyhq.com/acme/123", "ashby"),
    ("https://jobs.smartrecruiters.com/acme/123", "smartrecruiters"),
    ("https://acme.teamtailor.com/jobs/123", "teamtailor"),
    ("https://apply.workable.com/acme/j/123", "workable"),
    ("https://acme.bamboohr.com/careers/123", "bamboohr"),
    ("https://acme.recruitee.com/o/123", "recruitee"),
    ("https://acme.jobcan.com/123", "jobcan_hrmos"),
    ("https://www.google.com/search?q=cyber+security+graduate", "google_index"),
    ("https://careers.acme.example.org/roles/graduate-analyst", "employer_careers"),
])
def test_classify_surface_maps_real_hosts(url, surface):
    assert wr.classify_surface(url) == surface


def test_classify_surface_handles_the_synthetic_fixture_hosts_and_blanks():
    assert wr.classify_surface("https://uk.linkedin.invalid/jobs/view/1") == "linkedin_jobs"
    assert wr.classify_surface("https://uk.indeed.invalid/viewjob?jk=1") == "indeed"
    assert wr.classify_surface("https://job-boards.greenhouse.io.invalid/acme/jobs/1") == "greenhouse"
    assert wr.classify_surface(None) == "employer_careers"
    assert wr.classify_surface("not a url") == "employer_careers"


def test_parse_result_title_uses_the_documented_owner_pattern():
    assert wr.parse_result_title("SOC Analyst L1 @ Acme") == ("SOC Analyst L1", "Acme")
    assert wr.parse_result_title("SOC Analyst L1 | Acme") == ("SOC Analyst L1", "Acme")
    assert wr.parse_result_title("Information Security Analyst at Acme") == \
        ("Information Security Analyst", "Acme")
    # no separator -> the company stays missing, never guessed
    assert wr.parse_result_title("SOC Analyst L1") == ("SOC Analyst L1", None)
    assert wr.parse_result_title("") == (None, None)


# --------------------------------------------------------------------------- #
# the query matrix (role families × regions × surfaces)
# --------------------------------------------------------------------------- #

def test_query_matrix_covers_every_role_family_and_the_owner_site_patterns():
    matrix = wr.build_query_matrix("uk")
    families = {q["role_family"] for q in matrix}
    assert set(wr.ROLE_FAMILIES) <= families
    surfaces = {q["surface_scope"] for q in matrix}
    for scope, _site in wr.OWNER_ATS_SITE_QUERIES:
        assert scope in surfaces, f"owner ATS surface {scope} missing from the matrix"
    for scope, _site in wr.BROAD_SURFACES:
        assert scope in surfaces, f"broad surface {scope} missing from the matrix"
    # the owner's own query shapes are preserved, not guessed
    text = json.dumps(matrix)
    assert "site:job-boards.greenhouse.io" in text
    assert "site:jobs.lever.co" in text
    assert "site:linkedin.com/jobs" in text
    assert "London" in text


def test_query_matrix_is_per_region_and_rejects_an_unknown_region():
    for region in REGIONS:
        matrix = wr.build_query_matrix(region)
        assert matrix and all(q["region"] == region for q in matrix)
        assert wr.REGION_LOCATIONS[region][0] in json.dumps(matrix)
    with pytest.raises(SystemExit):
        wr.build_query_matrix("atlantis")


def test_query_ids_are_stable_and_provenance_carried():
    a = wr.build_query_matrix("uk")
    b = wr.build_query_matrix("uk")
    assert [q["query_id"] for q in a] == [q["query_id"] for q in b]
    assert all(q["query_provenance"] for q in a)


def test_watchlist_hook_adds_company_queries_and_is_optional(tmp_path):
    generic = wr.build_query_matrix("uk")
    hook = wr.build_query_matrix("uk", include_watchlist=["Fixture Corp (NOT A REAL COMPANY)"])
    assert len(hook) > len(generic)
    watch = [q for q in hook if q["role_family"] == "watchlist"]
    assert watch and all("Fixture Corp (NOT A REAL COMPANY)" in q["query"] for q in watch)
    assert any("site:" in q["query"] for q in watch)
    # the generic search works with no watchlist at all
    assert not [q for q in generic if q["role_family"] == "watchlist"]
    # an absent watchlist file is not an error
    assert wr.load_watchlist(tmp_path / "missing.json") == []


def test_watchlist_file_parses_both_shapes(tmp_path):
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({"companies": ["Alpha (NOT REAL)", {"company": "Beta (NOT REAL)"}]}),
                 encoding="utf-8")
    assert wr.load_watchlist(p) == ["Alpha (NOT REAL)", "Beta (NOT REAL)"]
    p.write_text(json.dumps(["Gamma (NOT REAL)"]), encoding="utf-8")
    assert wr.load_watchlist(p) == ["Gamma (NOT REAL)"]


# --------------------------------------------------------------------------- #
# canonical URL
# --------------------------------------------------------------------------- #

def test_canonical_url_drops_tracking_parameters_and_www():
    assert wr.canonical_url("https://www.overlap-test.invalid/jobs/x?utm_source=a&utm_medium=b") \
        == "https://overlap-test.invalid/jobs/x"
    assert wr.canonical_url(None) is None


# --------------------------------------------------------------------------- #
# provider interface
# --------------------------------------------------------------------------- #

def test_captured_provider_probe_and_research():
    provider = wr.CapturedResultsProvider(CAPTURE)
    probe = provider.probe()
    assert probe["available"] is True
    assert probe["captured_from"] == "codex-web-search"
    doc = provider.research(fixture_queries())
    assert doc["available"] is True
    assert len(doc["queries"]) == 4
    assert all(q["web_search_observed"] for q in doc["queries"])
    assert sum(len(q["results"]) for q in doc["queries"]) == 6


def test_captured_provider_marks_a_query_absent_from_the_capture():
    provider = wr.CapturedResultsProvider(CAPTURE)
    doc = provider.research([{"query_id": "q-nope", "query": "a query nobody ran",
                              "region": "uk", "role_family": "x", "surface_scope": "y"}])
    assert doc["available"] is False
    assert doc["queries"][0]["executed"] is False
    assert doc["queries"][0]["web_search_observed"] is False
    assert doc["limitation"]


def test_null_provider_yields_a_declared_zero():
    doc = wr.NullProvider().research([{"query_id": "q1", "query": "q", "region": "uk",
                                       "role_family": "x", "surface_scope": "y"}])
    assert doc["available"] is False
    assert doc["queries"][0]["results"] == []
    assert "zero queries" in (doc["limitation"] or "")


def test_codex_provider_reports_unavailable_truthfully_when_cli_is_absent(monkeypatch):
    provider = wr.CodexWebSearchProvider(executable="/nonexistent/codex")

    def _boom():
        raise RuntimeError("Codex CLI not found (test)")

    monkeypatch.setattr(provider, "resolve", _boom)
    probe = provider.probe()
    assert probe["available"] is False
    assert "unavailable" in probe["reason"]
    doc = provider.research([{"query_id": "q1", "query": "q", "region": "uk",
                              "role_family": "x", "surface_scope": "y"}])
    assert doc["available"] is False
    assert doc["queries"][0]["results"] == []
    assert doc["queries"][0]["web_search_observed"] is False


def test_a_result_without_an_observed_search_is_never_accepted():
    """Anti-fabrication: a memory recall is not a search result."""
    class NoSearchProvider(wr.ResearchProvider):
        name = "no-search-stub"

        def probe(self):
            return {"provider": self.name, "available": False}

        def research(self, queries, *, limit_per_query=5, timeout=240):
            return {"provider": self.name, "available": False, "limitation": "no live search",
                    "requests": 1, "web_search_observed_queries": 0,
                    "queries_without_observed_search": len(queries),
                    "queries": [dict(q, executed=True, web_search_observed=False,
                                     results=[{"title": "Fabricated Role @ X (NOT REAL)",
                                               "url": "https://fabricated.invalid/1"}])
                                for q in queries]}

    doc = wr.run_research(fixture_queries()[:1], NoSearchProvider(), region="uk",
                          validate=False)
    assert doc["telemetry"]["results_seen"] == 0
    assert doc["candidates"] == []
    assert doc["telemetry"]["rejections_by_reason"].get("search_not_observed") == 1
    assert doc["telemetry"]["zero_attribution"]


# --------------------------------------------------------------------------- #
# normalisation + provenance
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def research_doc():
    captured = wr.CapturedResultsProvider(CAPTURE)
    return wr.run_research(fixture_queries(), captured, region="uk", validate=False)


def test_run_research_normalises_every_surface_into_the_candidate_schema(research_doc):
    assert research_doc["kind"] == wr.EXPORT_KIND
    assert len(research_doc["candidates"]) == 5   # 6 results, 1 duplicate collapsed
    surfaces = {c["web_research"]["discovery_surface"] for c in research_doc["candidates"]}
    assert {"linkedin_jobs", "indeed", "greenhouse", "employer_careers"} <= surfaces
    for c in research_doc["candidates"]:
        assert c["url"].startswith("https://")
        assert c["fetch_state"] in wr.FETCH_STATES
        assert c["title"]


def test_run_research_preserves_full_provenance_per_result(research_doc):
    for c in research_doc["candidates"]:
        prov = c["web_research"]
        assert prov["search_query"]
        assert prov["query_id"]
        assert prov["query_provenance"]
        assert prov["region"] == "uk"
        assert prov["role_family"]
        assert prov["result_url"] == c["url"]
        assert prov["canonical_url"]
        assert prov["source_timestamp"]
        assert prov["title_source"] in ("fetched_page_title", "search_result_title")
        assert "observed" in prov and "missing_fields" in prov
        assert prov["discovery_surface"] in wr.SURFACES


def test_run_research_collapses_a_url_seen_by_two_queries(research_doc):
    assert research_doc["telemetry"]["duplicates_collapsed"] == 1
    urls = [c["url"] for c in research_doc["candidates"]]
    assert len(urls) == len(set(urls))


def test_run_research_telemetry_has_the_declared_counters(research_doc):
    telemetry = research_doc["telemetry"]
    for key in wr.TELEMETRY_KEYS:
        assert key in telemetry, f"telemetry is missing {key}"
    assert telemetry["queries_executed"] == 4
    assert telemetry["results_seen"] == 6
    assert telemetry["candidate_urls"] == 5
    assert telemetry["duplicates_collapsed"] == 1
    # the funnel stages are not attempted here, so they stay zero and are labelled
    assert telemetry["semantically_reviewed"] == 0
    assert telemetry["deterministic_eligibility_pass"] == 0
    assert telemetry["tracker_candidates"] == 0


def test_normalisation_never_invents_a_company_from_a_missing_title():
    result = {"title": "Graduate SOC Analyst", "url": "https://x.invalid/jobs/1", "snippet": "s"}
    entry = {"query_id": "q1", "query": "q", "region": "uk", "role_family": "f",
             "surface_scope": "employer_careers"}
    cand = wr.normalise_result(result=result, query_entry=entry, fetch=None,
                               source_timestamp="2026-09-24T00:00:00Z")
    assert cand["company"] is None
    assert cand["fetch_state"] == wr.FETCH_DISCOVERED_UNVERIFIED
    assert "company" in cand["web_research"]["missing_fields"]


def test_normalisation_prefers_the_fetched_page_title():
    result = {"title": "Old Cached Title @ Wrong Co (NOT REAL)",
              "url": "https://x.invalid/jobs/1", "snippet": "s"}
    entry = {"query_id": "q1", "query": "q", "region": "uk", "role_family": "f",
             "surface_scope": "employer_careers"}
    fetch = {"status": wr.FETCH_VALIDATED_LIVE, "canonical_url": "https://x.invalid/jobs/1",
             "page_title": "SOC Analyst L1 @ Correct Co (NOT REAL)"}
    cand = wr.normalise_result(result=result, query_entry=entry, fetch=fetch,
                               source_timestamp="2026-09-24T00:00:00Z")
    assert cand["company"] == "Correct Co (NOT REAL)"
    assert cand["web_research"]["title_source"] == "fetched_page_title"


# --------------------------------------------------------------------------- #
# validation (faked HTTP layer — no real network)
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, body: bytes, status=200, url="https://x.invalid/", ctype="text/html"):
        self._body = body
        self.status = status
        self._url = url
        self.headers = {"Content-Type": ctype}

    def read(self, n=None):
        return self._body[:n] if n else self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, robots_body=b"User-agent: *\nAllow: /\n", page=None,
                   page_status=200):
    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/robots.txt"):
            return _FakeResponse(robots_body, url=url, ctype="text/plain")
        if page_status >= 400:
            raise wr.urllib.error.HTTPError(url, page_status, "err", {}, None)
        return _FakeResponse(page or b"<html><head><title>SOC Analyst L1 @ Acme</title></head></html>",
                             status=page_status, url=url)
    monkeypatch.setattr(wr.urllib.request, "urlopen", fake_urlopen)


def test_fetch_validate_refuses_a_non_http_scheme_without_network():
    rec = wr.fetch_validate("ftp://example.invalid/job/1")
    assert rec["status"] == wr.FETCH_VALIDATION_FAILED
    assert "non-http" in rec["error"]


def test_fetch_validate_marks_a_live_page_and_extracts_only_page_fields(monkeypatch):
    _patch_urlopen(monkeypatch)
    rec = wr.fetch_validate("https://acme.invalid/jobs/graduate-analyst")
    assert rec["status"] == wr.FETCH_VALIDATED_LIVE
    assert rec["http_status"] == 200
    assert rec["page_title"] == "SOC Analyst L1 @ Acme"


def test_fetch_validate_marks_a_dead_link_as_validation_failed(monkeypatch):
    _patch_urlopen(monkeypatch, page_status=404)
    rec = wr.fetch_validate("https://acme.invalid/jobs/gone")
    assert rec["status"] == wr.FETCH_VALIDATION_FAILED
    assert rec["http_status"] == 404


def test_fetch_validate_detects_a_closed_posting_marker(monkeypatch):
    _patch_urlopen(monkeypatch, page=b"<html><head><title>Job</title></head>"
                                     b"<body>This job has expired</body></html>")
    rec = wr.fetch_validate("https://acme.invalid/jobs/expired")
    assert rec["status"] == wr.FETCH_VALIDATION_FAILED
    assert rec["expired_marker"]


def test_fetch_validate_obeys_robots_disallow(monkeypatch):
    _patch_urlopen(monkeypatch, robots_body=b"User-agent: *\nDisallow: /jobs\n")
    rec = wr.fetch_validate("https://acme.invalid/jobs/secret")
    assert rec["status"] == wr.FETCH_VALIDATION_FAILED
    assert "robots.txt disallows" in rec["error"]


def test_run_research_counts_validated_and_failed_destinations():
    doc = wr.run_research(fixture_queries(), wr.CapturedResultsProvider(CAPTURE),
                          region="uk", validate=True, validate_fn=fake_validate_failed)
    assert doc["telemetry"]["validated_live"] == 0
    assert doc["telemetry"]["validation_failed"] == 5
    assert doc["telemetry"]["zero_attribution"].get("validation")


# --------------------------------------------------------------------------- #
# pipeline collector + unified funnel
# --------------------------------------------------------------------------- #

def test_collector_normalises_the_export_into_candidates_with_provenance():
    block = pipeline.collect_from_web_research(UNVERIFIED_EXPORT, "uk")
    assert block["available"] is True
    assert len(block["candidates"]) == 4
    for rec in block["candidates"]:
        assert rec["_collection_source"] == pipeline.SOURCE_WEB_RESEARCH
        assert rec["fetch_state"] in wr.FETCH_STATES
        assert rec["web_research"]["search_query"]
        assert rec["web_research"]["discovery_surface"]
    cov = block["coverage"]
    assert cov["queries_executed"] == 1
    assert cov["candidates_excluded_before_the_funnel"] == {
        "destination_not_validated_live": 1, "destination_not_verified": 1}
    assert cov["provider"] == "codex-web-search"


def test_collector_is_registered_as_a_source_and_declares_read_only_safety():
    assert pipeline.SOURCE_WEB_RESEARCH in pipeline.SOURCE_REGISTRY
    assert pipeline.SOURCE_REGISTRY[pipeline.SOURCE_WEB_RESEARCH] == "collect_from_web_research"
    note = pipeline.collect_from_web_research(UNVERIFIED_EXPORT, "uk")["coverage"]["note"].casefold()
    assert "no login" in note and "no browser" in note
    contract = pipeline.source_contract_document()
    assert pipeline.SOURCE_WEB_RESEARCH in contract["sources"]


def test_collector_reports_an_unreadable_export_as_a_limitation(tmp_path):
    block = pipeline.collect_from_web_research(tmp_path / "missing.json", "uk")
    assert block["available"] is False
    assert block["candidates"] == []
    assert "could not be read" in block["coverage"]["limitation"]


def test_run_cli_accepts_web_research_and_collapses_it_with_other_surfaces(tmp_path):
    """Web research + the regional lane discover the SAME vacancy -> one candidate."""
    export = export_from_capture(tmp_path)
    rc, doc = run_cli(["run", "--region", "uk",
                       "--records", str(REGIONAL),
                       "--web-research", str(export),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    assert pipeline.SOURCE_WEB_RESEARCH in doc["source_registry"]
    by_source = doc["funnel"]["counts"]["discovered_raw_by_source"]
    assert by_source[pipeline.SOURCE_WEB_RESEARCH] >= 1
    assert by_source[pipeline.SOURCE_EXPLICIT] == 2
    shared = [c for c in doc["canonical_candidates"] if c["duplicate_discoveries"]]
    overlap = [c for c in shared
               if pipeline.SOURCE_WEB_RESEARCH in c["sources"]
               and pipeline.SOURCE_EXPLICIT in c["sources"]]
    assert overlap, "the overlap-test vacancy found by web research was not collapsed"
    cand = overlap[0]
    collection_sources = {p["collection_source"] for p in cand["provenance"]}
    assert pipeline.SOURCE_WEB_RESEARCH in collection_sources
    assert pipeline.SOURCE_EXPLICIT in collection_sources


def test_pipeline_source_declares_its_own_funnel_counters(tmp_path):
    export = export_from_capture(tmp_path)
    rc, doc = run_cli(["run", "--region", "uk",
                       "--web-research", str(export),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    entry = doc["funnel"]["by_source"][pipeline.SOURCE_WEB_RESEARCH]
    assert entry["counts"]["discovered"] >= 1
    assert "rejections_by_reason" in entry
    assert "zero_attribution" in entry


# --------------------------------------------------------------------------- #
# fail-closed behaviour
# --------------------------------------------------------------------------- #

def test_unverified_and_failed_destinations_never_reach_the_tracker(tmp_path):
    rc, doc = run_cli(["run", "--region", "uk",
                       "--web-research", str(UNVERIFIED_EXPORT),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    decisions = {d["company"]: d for d in doc["eligibility"]["decisions"]}
    assert decisions["Validated Live Ltd (NOT A REAL VACANCY)"]["decision"] == "accepted"
    for company in ("Unverified Ltd (NOT A REAL VACANCY)",
                    "Deadlink Ltd (NOT A REAL VACANCY)"):
        d = decisions[company]
        assert d["decision"] == "rejected"
        assert any("not validated live" in r for r in d["reasons"])
        assert any("fetch_state=" in r for r in d["reasons"])
    # the URL-less record is refused for the missing application URL
    nourl = decisions["No Url Ltd (NOT A REAL VACANCY)"]
    assert nourl["decision"] == "rejected"
    assert any("no usable application URL" in r for r in nourl["reasons"])
    # exactly the validated, URL-bearing record survives
    assert doc["funnel"]["counts"]["deterministic_eligibility_pass"] == 1


def test_a_run_over_only_unverified_results_collapses_to_an_attributable_zero(tmp_path):
    doc = json.loads(UNVERIFIED_EXPORT.read_text(encoding="utf-8"))
    doc["candidates"] = [c for c in doc["candidates"] if c["fetch_state"] != "validated_live"]
    doc["candidates"] = [c for c in doc["candidates"] if c.get("url")]
    p = tmp_path / "unverified-only.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    rc, run = run_cli(["run", "--region", "uk", "--web-research", str(p),
                       "--semantic", "off", "--codex", "off", "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    assert run["funnel"]["counts"]["deterministic_eligibility_pass"] == 0
    assert run["funnel"]["counts"]["tracker_candidates"] == 0
    entry = run["funnel"]["by_source"][pipeline.SOURCE_WEB_RESEARCH]
    assert entry["zero_attribution"]["first_zero_stage"] == "deterministic_eligibility_pass"
    assert "deterministic gate" in entry["zero_attribution"]["reason"]
    assert "not validated live" in json.dumps(entry["rejections_by_reason"])


def test_a_web_research_run_writes_no_canonical_workbook(tmp_path):
    before = tracker_hashes()
    export = export_from_capture(tmp_path)
    out = tmp_path / "run"
    rc, doc = run_cli(["run", "--region", "uk", "--web-research", str(export),
                       "--semantic", "off", "--codex", "off",
                       "--manifest-out", str(tmp_path / "m.json"),
                       "--out-dir", str(out)])
    assert rc == 0
    assert doc["safety"]["canonical_workbook_written"] is False
    assert doc["safety"]["applications_submitted"] == 0
    assert doc["safety"]["browser_used"] is False
    assert doc["dedupe"]["applied"] is False
    assert tracker_hashes() == before


# --------------------------------------------------------------------------- #
# lane CLI
# --------------------------------------------------------------------------- #

def test_lane_cli_matrix_probe_and_summary(tmp_path):
    rc, doc = run_lane_cli(["matrix", "--region", "uk"])
    assert rc == 0 and doc["counts"]["queries"] > 0
    rc, probe = run_lane_cli(["probe", "--provider", "captured", "--captured", str(CAPTURE)])
    assert rc == 0 and probe["available"] is True
    rc, policy = run_lane_cli(["policy"])
    assert rc == 0 and policy["rules"]


def test_lane_cli_run_writes_an_export_and_a_summary(tmp_path):
    capture = matrix_shaped_capture(tmp_path, 4)
    rc, doc = run_lane_cli(["run", "--region", "uk", "--provider", "captured",
                            "--captured", str(capture), "--no-validate",
                            "--limit-queries", "4", "--out-dir", str(tmp_path)])
    assert rc == 0
    export = Path(doc["export_file"])
    assert export.exists()
    rc, summary = run_lane_cli(["summary", "--export", str(export)])
    assert rc == 0
    assert summary["counts"]["queries_executed"] == 4
    assert summary["safety"]["login_or_account_used"] is False


def test_lane_cli_run_with_funnel_reports_the_full_telemetry(tmp_path):
    capture = matrix_shaped_capture(tmp_path, 4)
    rc, doc = run_lane_cli(["run", "--region", "uk", "--provider", "captured",
                            "--captured", str(capture), "--no-validate",
                            "--limit-queries", "4", "--with-funnel",
                            "--semantic", "off", "--codex", "off",
                            "--out-dir", str(tmp_path)])
    assert rc == 0
    telemetry = doc["telemetry"]
    assert telemetry["queries_executed"] == 4
    assert telemetry["semantically_reviewed"] == 0
    assert "deterministic_eligibility_pass" in telemetry
    assert "tracker_candidates" in telemetry
    assert doc["funnel"]["safety"]["canonical_workbook_written"] is False
    assert doc["funnel"]["zero_attribution"]["first_zero_stage"]


def test_lane_cli_default_run_is_read_only(tmp_path):
    rc, doc = run_lane_cli(["run", "--region", "uk", "--provider", "none",
                            "--limit-queries", "2", "--out-dir", str(tmp_path)])
    assert rc == 0
    assert doc["safety"]["read_only"] is True
    assert doc["safety"]["canonical_workbook_written"] is False
    assert doc["candidates"] == []
    assert doc["telemetry"]["zero_attribution"]


# --------------------------------------------------------------------------- #
# safety contract
# --------------------------------------------------------------------------- #

def test_the_lane_does_not_import_a_browser_or_scraping_library():
    """The lane's only network capability is the robots-aware validation fetch."""
    source = inspect.getsource(wr)
    imported = set()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            imported.add(stripped[len("import "):].split()[0].split(".")[0].strip(",;"))
        elif stripped.startswith("from ") and " import " in stripped:
            imported.add(stripped[len("from "):].split(" import ")[0].split(".")[0].strip())
    banned = {"playwright", "selenium", "pyppeteer", "puppeteer", "requests", "httpx",
              "webbrowser", "pyautogui", "seleniumbase", "splash", "scrapy"}
    assert not (imported & banned), f"the lane imports a browser/scraping library: {imported & banned}"
    # declared read-only + robots-aware
    assert "urllib" in imported
    assert "robots" in source


def test_policy_document_declares_the_safety_boundary():
    policy = wr.policy_document()
    text = json.dumps(policy).casefold()
    assert "no login" in text
    assert "no browser" in text or "browser" in text
    assert "watchlist" in text
    assert "active research" in text
