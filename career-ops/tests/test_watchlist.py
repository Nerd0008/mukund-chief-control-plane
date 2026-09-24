#!/usr/bin/env python3
"""Tests for the owner-company priority watchlist lane (roster B27).

These prove the watchlist contract:

* an owner-editable list of company names — including an EMPTY list and a list
  that is not there at all — is a valid input, so the infrastructure can be
  finished before the owner supplies names;
* duplicate spellings of one company collapse deterministically while distinct
  companies never merge;
* every company gets BOTH query families (official-careers/ATS discovery and
  company-name + role-family research), never one ATS URL on its own;
* each company's official careers page / ATS host is *discovered and verified*
  where possible — from an owner-supplied URL, from the public structured
  endpoints Company Watch already implements, or from the research lane's own
  discovery — and an unreachable or unattributable company is labelled
  unavailable/unknown, never "no jobs";
* findings carry the ``priority_watchlist`` provenance flag and go through the
  SAME unified funnel as every other source, including its semantic and
  deterministic eligibility gates, which the flag never bypasses;
* per-company health records last checked, careers source found/not found,
  queries executed, live vacancies observed, funnel outcome, blocking reason and
  next retry;
* the acceptance fixtures the task names all pass, and nothing here writes a
  canonical tracker.

Offline and non-destructive: no test launches a browser, logs into a session,
calls a live provider, contacts an employer, recruiter or agency, or writes a
canonical workbook. The lane's only network-capable functions (URL validation
and the structured ATS probe) are exercised against faked HTTP layers.

Run:  python -m pytest career-ops/tests/test_watchlist.py -v
"""

from __future__ import annotations

import hashlib
import inspect
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
sys.path.insert(0, str(CAREER_OPS / "tests"))

import pipeline  # noqa: E402
import tracker_writer as tw  # noqa: E402
import watchlist as wl  # noqa: E402
import watchlist_fixtures as fx  # noqa: E402
import web_research as wr  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "discovery"
WL_FIXTURES = FIXTURES / "watchlist"
INPUT_FIXTURE = WL_FIXTURES / "watchlist-input.json"
COMPANY_WATCH_OVERLAP = WL_FIXTURES / "company-watch-overlap.json"

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
        rc = wl.main(argv)
    return rc, json.loads(buf.getvalue())


def company_by_name(lane: dict, name: str) -> dict:
    for row in lane["companies"]:
        if row["company"] == name:
            return row
    raise AssertionError(f"{name} not in lane health: "
                         f"{[r['company'] for r in lane['companies']]}")


def make_capture(tmp_path, companies, region: str = "uk") -> Path:
    path = Path(tmp_path) / "watchlist-capture.json"
    path.write_text(json.dumps(fx.build_capture(companies, region), indent=2), encoding="utf-8")
    return path


def write_lane(tmp_path, *, region: str = "uk", companies=None) -> tuple:
    """Run the whole lane offline against the fixtures. Returns (lane, companies)."""
    out = fx.write_lane_fixture(tmp_path, region=region, companies=companies)
    return out["lane"], out["companies"]


def lane_export(tmp_path, lane: dict) -> Path:
    path = Path(tmp_path) / "watchlist-lane.json"
    path.write_text(json.dumps(lane, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 1. the owner's input: empty is valid, names become companies
# --------------------------------------------------------------------------- #

def test_an_empty_watchlist_is_valid_and_needs_no_companies(tmp_path):
    """Phase 1 must be able to finish before the owner supplies any names."""
    empty = tmp_path / "company-watchlist.json"
    empty.write_text(json.dumps({"schema_version": 1, "kind": "career-ops.company-watchlist",
                                 "companies": []}), encoding="utf-8")
    loaded = wl.load_watchlist_input(empty)
    assert loaded["present"] is True
    assert loaded["empty"] is True
    assert loaded["companies"] == []
    assert loaded["limitation"] and "empty" in loaded["limitation"].lower()
    identity = wl.build_identity(loaded["companies"])
    assert identity["companies"] == []
    assert identity["duplicate_spellings_collapsed"] == 0

    lane, _ = write_lane(tmp_path, companies=identity["companies"])
    assert lane["watchlist"]["empty"] is True
    assert lane["watchlist"]["companies_in_watchlist"] == 0
    assert lane["companies"] == []
    assert lane["candidates"] == []
    assert lane["telemetry"]["companies_in_watchlist"] == 0
    # An empty list is a valid input, not a failure: nothing is blocked, nothing is
    # fabricated, and the lane itself is still well formed.
    assert lane["kind"] == wl.LANE_KIND
    assert lane["safety"]["read_only"] is True
    assert lane["safety"]["canonical_workbook_written"] is False
    assert lane["telemetry"]["zero_attribution"]["first_zero_stage"] == "no_company_in_watchlist"


def test_a_missing_watchlist_file_is_valid_and_says_so(tmp_path):
    loaded = wl.load_watchlist_input(tmp_path / "nope" / "company-watchlist.json")
    assert loaded["present"] is False
    assert loaded["empty"] is True
    assert loaded["companies"] == []
    assert loaded["limitation"]
    assert "valid" in loaded["limitation"].lower()


def test_owner_input_accepts_names_objects_and_notes(tmp_path):
    path = tmp_path / "company-watchlist.json"
    path.write_text(json.dumps({"companies": [
        "Bare Name Ltd",
        {"company": "Object Name Ltd", "careers_url": "https://object-name.invalid/careers",
         "notes": "owner note", "aliases": ["Object Name Limited"], "regions": ["uk"]},
        {"name": "Alias Key Name Ltd"},
        {"company": "", "notes": "no name at all"},
        "   ",
    ]}), encoding="utf-8")
    loaded = wl.load_watchlist_input(path)
    names = [c["company"] for c in loaded["companies"]]
    assert names == ["Bare Name Ltd", "Object Name Ltd", "Alias Key Name Ltd"]
    assert loaded["companies"][1]["careers_url"] == "https://object-name.invalid/careers"
    assert loaded["companies"][1]["notes"] == "owner note"
    # Rows with no company name are reported, never silently invented.
    assert len(loaded["malformed_rows"]) == 2


def test_the_shipped_template_is_a_valid_empty_watchlist():
    template = json.loads((CAREER_OPS / "watchlist" / "company-watchlist.example.json")
                          .read_text(encoding="utf-8"))
    assert template["kind"] == "career-ops.company-watchlist"
    assert template["schema_version"] == 1
    assert template["companies"] == []
    assert "runtime/career-ops/watchlist/company-watchlist.json" in json.dumps(template)


# --------------------------------------------------------------------------- #
# 2. deterministic identity: collapse duplicates, never merge distinct companies
# --------------------------------------------------------------------------- #

def test_duplicate_spellings_collapse_and_distinct_companies_do_not():
    companies = fx.load_companies()
    names = [c["company"] for c in companies]
    # 7 rows, 3 of them one company → 5 distinct companies, 2 collapses.
    assert names == ["Fixture Security Ltd", "Fixture Security Group", "Overlap Test Ltd",
                     "No Surface Co", "Quiet Roles Ltd"]
    merged = next(c for c in companies if c["company"] == "Fixture Security Ltd")
    assert set(merged["merged_from"]) == {"Fixture Security",
                                          "fixture security LTD"}
    assert "Fixture Security Limited" in merged["aliases"]
    assert merged["careers_url"] == "https://fixture-security.invalid/careers"
    group = next(c for c in companies if c["company"] == "Fixture Security Group")
    assert group["merged_from"] == []
    assert group["identity_key"] != merged["identity_key"]


def test_identity_is_deterministic_and_order_independent():
    """The mapping is order-independent; only the reported order follows the owner's list."""
    rows = fx.load_input_fixture()["companies"]
    a = wl.build_identity([dict(r, _index=i) for i, r in enumerate(rows)])
    b = wl.build_identity([dict(r, _index=i) for i, r in enumerate(reversed(rows))])
    key = lambda doc: sorted((c["company"], c["identity_key"], sorted(c["merged_from"]))
                             for c in doc["companies"])
    assert key(a) == key(b)
    assert sorted({m["basis"] for m in a["merges"]}) == \
        sorted({m["basis"] for m in b["merges"]})
    assert {n for m in a["merges"] for n in m["companies"]} == \
        {n for m in b["merges"] for n in m["companies"]}
    assert a["duplicate_spellings_collapsed"] == 2
    assert a["merge_rules"]
    # Companies are reported in the order the owner declared them, so the owner's own
    # ordering survives identity normalisation.
    assert [c["company"] for c in a["companies"]][0] == "Fixture Security Ltd"


def test_identity_records_the_basis_of_every_merge():
    identity = wl.build_identity([dict(r, _index=i)
                                 for i, r in enumerate(fx.load_input_fixture()["companies"])])
    bases = {m["basis"] for m in identity["merges"]}
    assert bases  # every collapse is explained, never silent
    for m in identity["merges"]:
        assert m["detail"] and len(m["companies"]) >= 2
        assert all(c and isinstance(c, str) for c in m["companies"])


def test_identity_always_collects_explained_collapses():
    """A declared alias and a declared ATS slug both fold in, and both are recorded."""
    identity = wl.build_identity([
        {"company": "Declared Alias Ltd", "aliases": ["DA Ltd"], "_index": 0},
        {"company": "DA Ltd", "_index": 1},
        {"company": "Slug Form Ltd", "ats_slug_candidates": ["slugform"], "_index": 2},
        {"company": "Slug Form", "_index": 3},
    ])
    names = [c["company"] for c in identity["companies"]]
    assert names == ["Declared Alias Ltd", "Slug Form Ltd"]
    assert identity["duplicate_spellings_collapsed"] == 2
    assert [m["basis"] for m in identity["merges"]].count("declared_alias") == 1


# --------------------------------------------------------------------------- #
# 3. careers / ATS surface discovery and verification
# --------------------------------------------------------------------------- #

def test_ats_families_are_classified_on_whole_host_labels():
    cases = {
        "https://job-boards.greenhouse.io/acme/jobs/1": ("greenhouse", "structured"),
        "https://jobs.lever.co/acme/abc": ("lever", "structured"),
        "https://jobs.ashbyhq.com/acme/1": ("ashby", "structured"),
        "https://apply.workable.com/acme/j/1": ("workable", "structured"),
        "https://jobs.smartrecruiters.com/acme/1": ("smartrecruiters", "structured"),
        "https://acme.wd1.myworkdayjobs.com/en-US/careers": ("workday", "discovered_url_only"),
        "https://acme.teamtailor.com/jobs/1": ("teamtailor", "discovered_url_only"),
        "https://acme.hrmos.co/": ("jobcan_hrmos", "discovered_url_only"),
        "https://acme.icims.com/jobs/1": ("icims", "discovered_url_only"),
        # A declared ATS family is never inferred from a substring.
        "https://clever.com/careers": (None, None),
        "https://notgreenhouse.io/jobs": (None, None),
        # An employer's own domain is not an ATS family.
        "https://acme.example/careers": (None, None),
    }
    for url, (family, probe) in cases.items():
        got = wl.classify_ats_host(url)
        assert (got["family"], got["probe"]) == (family, probe), url


def test_a_discovered_workday_surface_keeps_its_tenant_and_is_never_guessed():
    got = wl.classify_ats_host("https://acme.wd1.myworkdayjobs.com/en-US/careers")
    assert got["family"] == "workday"
    assert got["tenant"] == "acme"
    assert got["probe"] == "discovered_url_only"
    # No tenant means no board: a Workday tenant is never invented from a name.
    blank = wl.classify_ats_host("https://myworkdayjobs.com/en-US/careers")
    assert blank["family"] == "workday"
    assert blank["tenant"] is None
    surface = wl.describe_careers_surface("https://acme.wd1.myworkdayjobs.com/en-US/careers")
    assert surface["kind"] == "ats_board" and "acme" in surface["description"]


def test_every_declared_family_is_stated_in_the_policy_document():
    policy = wl.policy_document()
    declared = policy["ats_families"]
    for required in ("greenhouse", "lever", "workday", "ashby", "smartrecruiters",
                     "teamtailor", "workable"):
        assert required in declared
    for name, spec in declared.items():
        assert spec["probe"] in ("structured", "discovered_url_only")
        assert spec["site_query"].startswith("site:")
        assert spec["host_labels"]
    assert set(declared) == set(wl.ATS_FAMILIES)


def test_an_owner_supplied_careers_url_is_verified_before_it_is_trusted():
    company = {"company": "Fixture Security Ltd", "identity_key": "fixturesecurityltd",
               "careers_url": "https://fixture-security.invalid/careers",
               "name_variants": ["fixturesecurityltd"]}
    ok = wl.resolve_careers_surface(company, fetcher=fx.FakeFetcher(),
                                    page_validator=fx.fake_fetch)
    assert ok["state"] == wl.STATE_FOUND
    assert ok["careers_source_found"] is True
    assert ok["careers_source"] == "owner_supplied_careers_url"
    assert ok["careers_page_name_confirmed"] is True
    assert ok["careers_page_http_status"] == 200
    assert ok["access_blocking_reason"] is None
    assert ok["evidence"]

    dead = dict(company, careers_url="https://gone-away.invalid/careers")
    bad = wl.resolve_careers_surface(dead, fetcher=fx.FakeFetcher(),
                                     page_validator=fx.fake_fetch)
    # An unreachable owner URL is UNKNOWN, never "found" and never "no jobs".
    assert bad["careers_source_found"] is False
    assert bad["state"] in (wl.STATE_UNAVAILABLE, wl.STATE_UNKNOWN)
    assert bad["access_blocking_reason"]
    assert "not 'no jobs'" in bad["access_blocking_reason"] or \
        "UNKNOWN" in bad["access_blocking_reason"]


def test_a_structured_board_is_used_only_when_the_payload_names_the_company():
    company = {"company": "Attributed Board Ltd", "identity_key": "attributedboardltd",
               "ats_slug_candidates": ["attributedboard"],
               "name_variants": ["attributedboardltd"]}
    good = wl.resolve_careers_surface(
        company, fetcher=fx.structured_board_fetcher("attributedboard",
                                                     company_name="Attributed Board Ltd"),
        page_validator=fx.fake_fetch)
    assert good["state"] == wl.STATE_FOUND
    assert good["careers_source"] == "structured_ats_board"
    assert good["ats_family"] == "greenhouse"
    assert good["attribution_confidence"] == "high"

    # The same board that never names the company must NOT be trusted.
    plain = wl.resolve_careers_surface(dict(company, ats_slug_candidates=["some-unrelated"]),
                                       fetcher=fx.unattributed_board_fetcher("some-unrelated"),
                                       page_validator=fx.fake_fetch)
    assert plain["careers_source_found"] is False
    assert plain["state"] in (wl.STATE_UNAVAILABLE, wl.STATE_UNKNOWN)
    assert "UNKNOWN" in plain["access_blocking_reason"] or \
        "not 'no jobs'" in plain["access_blocking_reason"]


def test_a_company_with_no_careers_page_is_unavailable_not_no_jobs(tmp_path):
    lane, _ = write_lane(tmp_path)
    row = company_by_name(lane, "No Surface Co")
    assert row["careers_source_found"] is False
    assert row["careers_state"] == wl.STATE_UNAVAILABLE
    assert row["careers_url"] is None
    assert row["manual_attribution_required"] is True
    reason = row["access_blocking_reason"]
    assert reason and "not 'no jobs'" in reason
    # The only thing the run saw for it was a keyword listing page, which is a board's
    # own listing, not a vacancy.
    assert "search_listing_refused" in json.dumps(lane["telemetry"])
    assert row["live_vacancies_observed"] == 0
    # One result was recorded — a keyword listing page, refused as a non-vacancy.
    assert row["findings"] == 1
    assert row["listings_refused"] == 1
    unavailable = pipeline.collect_from_priority_watchlist(
        lane_export(tmp_path, lane), "uk")["coverage"]["companies_unavailable_or_unknown_detail"]
    assert any(u["company"] == "No Surface Co" for u in unavailable)
    assert any("not 'no jobs'" in (u["reason"] or "") for u in unavailable
               if u["company"] == "No Surface Co")
    assert not any(c["watchlist_company"] == "No Surface Co"
                   and c["result_kind"] != wr.RESULT_KIND_SEARCH_LISTING
                   for c in lane["candidates"])


def test_a_company_whose_careers_surface_resolves_but_have_no_matching_roles(tmp_path):
    lane, _ = write_lane(tmp_path)
    row = company_by_name(lane, "Quiet Roles Ltd")
    assert row["careers_source_found"] is True
    assert row["careers_state"] == wl.STATE_FOUND
    assert row["queries_executed"] > 0
    assert row["live_vacancies_observed"] == 0
    assert row["findings"] == 0
    # A zero is scoped to THIS run and THIS company's queries, never to the market.
    assert "not a market fact" in (row["access_blocking_reason"] or "")
    assert row["next_retry_at"]


def test_a_careers_surface_discovered_by_the_research_lane_is_promoted(tmp_path):
    lane, _ = write_lane(tmp_path)
    row = company_by_name(lane, "Fixture Security Group")
    # No owner URL and no structured board offered it a board, yet the careers-family
    # research found the Workday surface and the page named the company.
    assert row["careers_source_found"] is True
    assert row["careers_source"] == "discovered_via_research_lane"
    assert row["ats_family"] == "workday"
    surfaces = row["discovered_careers_surfaces"]
    assert surfaces and surfaces[0]["name_confirmed"] is True
    assert surfaces[0]["ats_family"] == "workday"
    assert surfaces[0]["discovered_via_query"]


def test_an_unconfirmed_discovered_surface_stays_unknown(tmp_path):
    """A discovered URL that never names the company must not become 'the' careers page."""
    companies = [{"company": "Unconfirmed Names Ltd", "identity_key": "unconfirmednamesltd",
                  "aliases": [], "merged_from": [], "ats_slug_candidates": [],
                  "name_variants": ["unconfirmednamesltd"], "careers_url": None}]
    capture = json.loads(json.dumps(fx.build_capture(companies)))
    for q in capture["queries"]:
        if q["query_family"] == wl.FAMILY_CAREERS:
            q["results"] = [{"title": "Careers", "url": "https://fixture-security.invalid/jobs/9",
                             "snippet": "Careers"}]
    path = Path(tmp_path) / "capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    lane = wl.run_lane(companies, region="uk", provider=wr.CapturedResultsProvider(path),
                       fetcher=fx.FakeFetcher(), page_validator=fx.fake_fetch,
                       validate_fn=fx.fake_fetch, max_urls_per_company=50)
    row = lane["companies"][0]
    assert row["careers_source_found"] is False
    assert row["state" if "state" in row else "careers_state"] in (wl.STATE_UNAVAILABLE,
                                                                  wl.STATE_UNKNOWN)
    assert row["discovered_careers_surfaces"][0]["name_confirmed"] is False
    assert "manual attribution required" in row["access_blocking_reason"]


# --------------------------------------------------------------------------- #
# 4. two complementary query families, always
# --------------------------------------------------------------------------- #

def test_both_query_families_are_generated_for_every_company():
    companies = fx.load_companies()
    families = {}
    for company in companies:
        qs = wl.build_company_queries(company, "uk")
        got = {q["query_family"] for q in qs}
        families[company["company"]] = got
        assert got == {wl.FAMILY_CAREERS, wl.FAMILY_ROLE}, company["company"]
        # The ATS-discovery family must cover the declared families, not one board.
        scopes = {q["surface_scope"] for q in qs if q["query_family"] == wl.FAMILY_CAREERS}
        assert {"greenhouse", "lever", "workday", "ashby", "smartrecruiters", "teamtailor",
                "workable"} <= scopes
        for q in qs:
            assert q["priority_watchlist"] is True
            assert q["watchlist_company"] == company["company"]
            assert q["region"] == "uk"
            assert company["company"] in q["query"] or q["surface_scope"] in wl.ATS_FAMILIES


def test_role_family_queries_carry_the_region_and_the_entry_clause():
    qs = [q for q in wl.build_company_queries(fx.load_companies()[0], "uk")
          if q["query_family"] == wl.FAMILY_ROLE]
    assert len(qs) >= 2
    for q in qs:
        assert '"Fixture Security Ltd"' in q["query"]
        assert wr.DISCIPLINE_CLAUSE in q["query"]
        assert any(loc in q["query"] for loc in wr.REGION_LOCATIONS["uk"])
    assert {q["role_family"] for q in qs} >= {"watchlist_cross_family"}


def test_an_unknown_role_family_or_region_is_refused_not_guessed():
    with pytest.raises(SystemExit):
        wl.build_company_queries(fx.load_companies()[0], "atlantis")
    with pytest.raises(SystemExit):
        wl.build_company_queries(fx.load_companies()[0], "uk",
                                 role_families=["not_a_real_family"])


def test_a_query_limit_never_drops_a_whole_family():
    qs = wl.build_company_queries(fx.load_companies()[0], "uk")
    kept, truncated = wl.apply_query_limit(qs, 6)
    assert truncated is True
    assert len(kept) == 6
    assert {q["query_family"] for q in kept} == {wl.FAMILY_CAREERS, wl.FAMILY_ROLE}
    all_kept, truncated_all = wl.apply_query_limit(qs, 0)
    assert truncated_all is False and all_kept == qs


def test_a_limited_run_still_records_the_truncation(tmp_path):
    lane, companies = write_lane(tmp_path)
    row = company_by_name(lane, "Fixture Security Ltd")
    assert row["queries_truncated_by_limit"] is False
    assert row["queries_planned"] == row["queries_executed"]

    limited = wl.run_lane(companies[:1], region="uk",
                          provider=wr.CapturedResultsProvider(
                              make_capture(tmp_path, companies[:1])),
                          fetcher=fx.FakeFetcher(), page_validator=fx.fake_fetch,
                          validate_fn=fx.fake_fetch, limit_queries_per_company=6)
    row = limited["companies"][0]
    assert row["queries_truncated_by_limit"] is True
    assert row["queries_executed"] == 6
    assert row["queries_planned"] > 6


# --------------------------------------------------------------------------- #
# 5. per-company health
# --------------------------------------------------------------------------- #

HEALTH_FIELDS = ("company", "last_checked", "careers_source_found", "careers_state",
                 "queries_executed", "live_vacancies_observed", "findings",
                 "candidates_after_funnel", "tracker_candidates", "access_blocking_reason",
                 "next_retry_at")


def test_every_company_has_the_required_health_fields(tmp_path):
    lane, companies = write_lane(tmp_path)
    assert len(lane["companies"]) == len(companies)
    for row in lane["companies"]:
        for f in HEALTH_FIELDS:
            assert f in row, f
        assert row["last_checked"]
        assert row["queries_executed"] > 0
        assert row["next_retry_at"]
    # A retry is scheduled furthest out for a resolved company, soonest for one whose
    # infrastructure could not be reached at all.
    found = company_by_name(lane, "Fixture Security Ltd")
    gone = company_by_name(lane, "No Surface Co")
    # A resolved company is re-checked on the slower cadence; one whose infrastructure
    # could not be reached is retried sooner, because that is the state that may change.
    assert found["next_retry_at"] > gone["next_retry_at"]
    assert found["retry_hours"] > gone["retry_hours"]


def test_a_run_that_executed_no_query_blocks_and_says_why(tmp_path):
    """Anti-fabrication: a lane that searched nothing can never claim a finding."""
    companies = fx.load_companies()[:1]
    capture = json.loads(json.dumps(fx.build_capture(companies)))
    for q in capture["queries"]:
        q["web_search_observed"] = False
        q["executed_queries"] = []
        q["results"] = []
    capture["provider"].update({"web_search_observed_queries": 0,
                                "queries_without_observed_search": len(capture["queries"])})
    path = Path(tmp_path) / "no-search-capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    lane = wl.run_lane(companies, region="uk",
                       provider=wr.CapturedResultsProvider(path),
                       fetcher=fx.FakeFetcher(), page_validator=fx.fake_fetch,
                       validate_fn=fx.fake_fetch)
    row = lane["companies"][0]
    assert row["searches_observed"] == 0
    assert row["live_vacancies_observed"] == 0
    assert row["findings"] == 0
    assert lane["candidates"] == []
    assert row["access_blocking_reason"]
    zero = lane["telemetry"]["zero_attribution"]
    assert zero["first_zero_stage"]
    assert zero["provider_gap"]["queries_without_observed_search"] > 0
    assert zero["per_company_blocking_reason"]


# --------------------------------------------------------------------------- #
# 6. through the SAME funnel: provenance, gates, dedupe
# --------------------------------------------------------------------------- #

def test_the_collector_publishes_the_lane_as_one_more_source(tmp_path):
    lane, companies = write_lane(tmp_path)
    collection = pipeline.collect_from_priority_watchlist(lane_export(tmp_path, lane), "uk")
    assert collection["available"] is True
    assert collection["candidates"]
    coverage = collection["coverage"]
    assert coverage["kind"] == "owner priority watchlist lane export"
    assert coverage["watchlist_present"] is True
    assert coverage["companies_in_watchlist"] == len(companies)
    assert coverage["watchlist_empty"] is False
    assert coverage["findings_entering_this_funnel"] == len(collection["candidates"])
    assert coverage["companies_unavailable_or_unknown"] >= 1
    for rec in collection["candidates"]:
        assert rec["priority_watchlist"] is True
        assert rec["watchlist_company"]
        assert rec["source"] == pipeline.SOURCE_PRIORITY_WATCHLIST


def test_an_empty_watchlist_lane_yields_no_candidates_and_no_error(tmp_path):
    lane, _ = write_lane(tmp_path, companies=[])
    collection = pipeline.collect_from_priority_watchlist(lane_export(tmp_path, lane), "uk")
    assert collection["candidates"] == []
    assert collection["coverage"]["watchlist_empty"] is True


def test_watchlist_findings_carry_provenance_and_the_flag_through_the_funnel(tmp_path):
    lane, _ = write_lane(tmp_path)
    collection = pipeline.collect_from_priority_watchlist(lane_export(tmp_path, lane), "uk")
    rc, run = run_cli(["run", "--region", "uk", "--priority-watchlist",
                       str(lane_export(tmp_path, lane)),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    counts = run["funnel"]["counts"]
    assert counts["discovered_raw_by_source"][pipeline.SOURCE_PRIORITY_WATCHLIST] == \
        len(collection["candidates"])
    decisions = {d["url"]: d for d in run["eligibility"]["decisions"]}
    live = "https://fixture-security.invalid/jobs/soc-analyst-l1"
    assert decisions[live]["priority_watchlist"] is True
    assert decisions[live]["watchlist_company"] == "Fixture Security Ltd"
    # The flag is provenance: it does not exempt anything from the gates.
    listing = "https://no-surface.invalid/jobs/cyber-security-jobs-in-london"
    assert decisions[listing]["decision"] == "rejected"
    assert decisions[listing]["priority_watchlist"] is True
    assert "not a vacancy posting" in json.dumps(decisions[listing])
    block = run["priority_watchlist"]
    assert block["declared"] is True
    assert block["counts"]["canonical_candidates"] >= 1
    assert any(c["company"] == "Fixture Security Ltd" for c in block["candidates"])


def test_a_watchlist_vacancy_that_fails_the_gates_is_never_promoted(tmp_path):
    """A priority flag must not smuggle a non-entry-level or unverified role in."""
    lane = {
        "kind": wl.LANE_KIND, "read_only": True, "lane_id": "watchlist-fixture",
        "region": "uk", "generated_at": "2026-09-24T06:00:00+00:00",
        "watchlist": {"declared": True, "empty": False},
        "telemetry": {"companies_in_watchlist": 1, "companies_checked": 1,
                      "queries_executed": 12, "live_vacancies_observed": 1, "findings": 1},
        "companies": [{"company": "Senior Only Ltd", "careers_source_found": True,
                       "queries_executed": 12, "live_vacancies_observed": 1}],
        "candidates": [{
            "priority_watchlist": True, "watchlist_company": "Senior Only Ltd",
            "watchlist_query_family": wl.FAMILY_ROLE, "watchlist_role_family": "soc_security_operations",
            "company": "Senior Only Ltd", "title": "Senior Principal Head of Security",
            "location": "London", "url": "https://senior-only.invalid/jobs/1",
            "fetch_state": wr.FETCH_VALIDATED_LIVE, "result_kind": wr.RESULT_KIND_POSTING,
        }],
    }
    rc, run = run_cli(["run", "--region", "uk", "--priority-watchlist",
                       str(lane_export(tmp_path, lane)), "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    assert run["funnel"]["counts"]["tracker_candidates"] == 0
    block = run["priority_watchlist"]
    assert block["declared"] is True
    assert block["counts"]["deterministic_eligibility_pass"] == 0
    assert block["candidates"][0]["threshold_passed"] is False
    assert "did not reach the deterministic gates" in block["candidates"][0]["state"]
    appended = [o for o in (run["dedupe"]["outcomes"] or [])
                if o.get("decision") == "appended"]
    assert appended == []


def test_a_company_watch_vacancy_and_a_watchlist_vacancy_collapse_with_both_provenances(tmp_path):
    """The acceptance fixture: the same vacancy found by Company Watch and the watchlist."""
    lane, _ = write_lane(tmp_path)
    rc, run = run_cli(["run", "--region", "uk",
                       "--company-watch", str(COMPANY_WATCH_OVERLAP),
                       "--priority-watchlist", str(lane_export(tmp_path, lane)),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    url = fx.SHARED_VACANCY_URL
    canon = [c for c in run["canonical_candidates"]
             if (c.get("canonical_key") and url in json.dumps(c))]
    assert canon, "the shared vacancy should survive canonical collapse"
    assert run["funnel"]["counts"]["cross_source_duplicates_removed"] >= 1
    merged = [c for c in run["cross_source_dedupe"]["collapsed"] if url in json.dumps(c)]
    assert merged, "the Company Watch + watchlist duplicate should be reported as collapsed"
    surfaces = json.dumps(merged)
    assert pipeline.SOURCE_COMPANY_WATCH in surfaces
    assert pipeline.SOURCE_PRIORITY_WATCHLIST in surfaces
    watchlist_block = run["priority_watchlist"]
    entry = [c for c in watchlist_block["candidates"] if url in json.dumps(c)]
    assert entry and entry[0]["duplicate_discoveries"] >= 1
    assert watchlist_block["counts"]["also_found_by_another_surface"] >= 1


def test_priority_watchlist_manifests_stay_read_only(tmp_path):
    before = tracker_hashes()
    lane, _ = write_lane(tmp_path)
    rc, run = run_cli(["run", "--region", "uk", "--priority-watchlist",
                       str(lane_export(tmp_path, lane)), "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    assert tracker_hashes() == before
    assert run["safety"]["canonical_workbook_written"] is False
    assert run["safety"]["applications_submitted"] == 0
    assert run["dedupe"]["applied"] is False
    assert "manifest_written_to" not in run


def test_the_pipeline_never_needs_the_watchlist_to_be_present():
    missing = pipeline.collect_from_priority_watchlist(Path("C:/definitely/not/here.json"), "uk")
    assert missing["available"] is False
    assert missing["candidates"] == []
    assert missing["coverage"]["watchlist_present"] is False
    assert missing["coverage"]["limitation"]


def test_the_watchlist_is_additive_to_market_search_not_a_replacement(tmp_path):
    """A market-only run must be unchanged by this lane's existence."""
    rc, run = run_cli(["run", "--region", "uk",
                       "--company-watch", str(COMPANY_WATCH_OVERLAP),
                       "--semantic", "off", "--codex", "off",
                       "--out-dir", str(tmp_path / "out")])
    assert rc == 0
    assert pipeline.SOURCE_PRIORITY_WATCHLIST not in \
        run["funnel"]["counts"]["discovered_raw_by_source"]
    assert run["funnel"]["counts"]["discovered_raw"] > 0
    assert run["priority_watchlist"]["declared"] is False


# --------------------------------------------------------------------------- #
# 7. the lane is safe by construction
# --------------------------------------------------------------------------- #

def test_the_lane_declares_its_safety_and_io_contract():
    policy = wl.policy_document()
    assert policy["kind"] == wl.POLICY_KIND
    assert policy["writes"]["canonical_tracker"] is False
    assert policy["writes"]["owner_watchlist_input"] == "read-only"
    assert policy["input"]["empty_is_valid"] is True
    assert policy["prohibited"]
    assert policy["not_performed"]
    assert policy["ats_families"]
    assert policy["identity"]["merge_rules"]
    assert "no prefix/shared-word/similarity rule exists" in policy["identity"]["note"]
    for field in ("last_checked", "careers_source_found", "queries_executed",
                  "live_vacancies_observed", "candidates_after_funnel",
                  "access_blocking_reason", "next_retry_at"):
        assert field in policy["per_company_health_fields"]


def test_the_lane_never_uses_a_browser_or_a_signed_in_session():
    src = Path(wl.__file__).read_text(encoding="utf-8")
    for banned in ("selenium", "playwright", "pyppeteer", "webdriver", "mechanize",
                   "cookiejar", "requests.session(", "logout(", "sign_in(", "log_in("):
        assert banned not in src, banned


def test_no_fixture_claims_a_real_vacancy_or_employer():
    for path in (INPUT_FIXTURE, COMPANY_WATCH_OVERLAP):
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text)
        assert doc.get("not_a_real_company") or doc.get("not_a_real_vacancy")
        hosts = __import__("re").findall(r"https?://([^/\"]+)", text)
        assert hosts
        for host in hosts:
            assert host.endswith(".invalid"), host


def test_the_example_watchlist_states_the_field_contract():
    doc = json.loads((CAREER_OPS / "watchlist" / "company-watchlist.example.json")
                     .read_text(encoding="utf-8"))
    readme = doc.get("_readme")
    assert readme
    assert "companies" in readme
    assert "aliases" in json.dumps(doc)
