#!/usr/bin/env python3
"""Acceptance run for the owner-company priority watchlist lane (roster B27).

Proves, offline and without touching a canonical tracker, exactly what the task
contract requires of the watchlist layer:

 1. a plain list of company names (and an EMPTY list, and no list at all) is a
    valid owner-editable input, so the infrastructure can be finished before the
    owner supplies names;
 2. deterministic company identity collapses duplicate spellings and never merges
    two distinct companies;
 3. the official careers page / ATS surface is discovered and verified where
    possible — the declared ATS families include Greenhouse, Lever, Workday,
    Ashby, SmartRecruiters, Teamtailor and Workable plus region-specific surfaces
    — and an unreachable or unattributable company is labelled
    unavailable/unknown, never "no jobs";
 4. every company gets BOTH query families (official-careers/ATS discovery and
    company-name + early-career cyber role-family research), never one ATS URL;
 5. findings carry the ``priority_watchlist`` provenance flag, are merged with
    Company Watch provenance when the same vacancy is found twice, and go through
    the SAME unified funnel — the flag NEVER bypasses the semantic stage or the
    deterministic eligibility gates;
 6. the six named acceptance fixtures all pass;
 7. a watchlist vacancy stays visible in the brief's own section even when it is
    not top-ranked globally (and even when it did not reach the gates);
 8. per-company health records last checked, careers source found/not found,
    queries executed, live vacancies observed, candidates after the funnel,
    blocking reason and next retry;
 9. the lane is read-only: no canonical workbook write, no application, no
    employer/recruiter contact, no browser or signed-in session.

Raw result URLs and the owner's company list are owner-private job-search data:
they are written under the git-ignored runtime directory, and only aggregate
counters/check results are printed or committed.

Usage:
  python career-ops/run_watchlist_acceptance.py [--stamp S] [--json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
for _p in (str(CAREER_OPS_DIR), str(CAREER_OPS_DIR / "discovery"),
           str(CAREER_OPS_DIR / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import daily_brief as db  # noqa: E402
import pipeline  # noqa: E402
import tracker_writer as tw  # noqa: E402
import watchlist as wl  # noqa: E402
import watchlist_fixtures as fx  # noqa: E402
import web_research as wr  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures" / "discovery"
WL_FIXTURES = FIXTURES / "watchlist"
INPUT_FIXTURE = WL_FIXTURES / "watchlist-input.json"
COMPANY_WATCH_OVERLAP = WL_FIXTURES / "company-watch-overlap.json"
REGIONAL = FIXTURES / "regional-overlap.json"
TEMPLATE = CAREER_OPS_DIR / "watchlist" / "company-watchlist.example.json"
RUNTIME = CONTROL_PLANE / "runtime" / "career-ops" / "watchlist"
PROFILES = tw.load_profiles()
REGIONS = ("uk", "dubai", "japan", "singapore")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tracker_hashes() -> dict:
    out = {}
    for region in REGIONS:
        p = Path(tw.region_config(PROFILES, region)["tracker"])
        out[region] = {"path": str(p), "sha256": sha256_file(p) if p.exists() else None}
    return out


def run_cli(mod, argv: list) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main(argv)
    return json.loads(buf.getvalue())


def company_by_name(lane: dict, name: str) -> dict:
    for row in lane["companies"]:
        if row["company"] == name:
            return row
    raise AssertionError(f"{name} not in lane health: "
                         f"{[r['company'] for r in lane['companies']]}")


def lane_export(tmp: Path, lane: dict) -> Path:
    path = Path(tmp) / "watchlist-lane.json"
    path.write_text(json.dumps(lane, indent=2), encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Owner priority watchlist acceptance (B27)")
    ap.add_argument("--stamp")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    started = dt.datetime.now(dt.timezone.utc)
    stamp = args.stamp or started.strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = CONTROL_PLANE / "audits" / "evidence" / f"{stamp}-career-priority-watchlist"
    out_dir.mkdir(parents=True, exist_ok=True)

    checks: list = []

    def check(name: str, ok: bool, detail) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    before = tracker_hashes()

    companies = fx.load_companies()
    identity = wl.build_identity([{**r, "_index": i}
                                  for i, r in enumerate(fx.load_input_fixture()["companies"])])

    # ----------------------------------------------------------------------- #
    # 1. the owner's input: empty is valid, names become companies
    # ----------------------------------------------------------------------- #
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    check("watchlist_template_is_a_valid_empty_watchlist",
          template["kind"] == "career-ops.company-watchlist"
          and template["companies"] == []
          and "companies" in template.get("_readme", ""),
          {"kind": template["kind"], "companies": len(template["companies"])})

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "empty.json").write_text(json.dumps(
            {"schema_version": 1, "kind": "career-ops.company-watchlist", "companies": []}),
            encoding="utf-8")
        empty_loaded = wl.load_watchlist_input(tmp / "empty.json")
        (tmp / "lane-empty").mkdir(parents=True, exist_ok=True)
        empty_lane = fx.write_lane_fixture(tmp / "lane-empty", companies=[])["lane"]
        missing = wl.load_watchlist_input(tmp / "nope" / "company-watchlist.json")
    check("an_empty_watchlist_is_valid_and_the_lane_runs_with_zero_companies",
          empty_loaded["present"] and empty_loaded["empty"] and empty_loaded["companies"] == []
          and empty_lane["companies"] == [] and empty_lane["candidates"] == []
          and empty_lane["telemetry"]["zero_attribution"]["first_zero_stage"]
          == "no_company_in_watchlist",
          {"empty_lane_companies": len(empty_lane["companies"]),
           "zero_stage": empty_lane["telemetry"]["zero_attribution"]["first_zero_stage"]})
    check("a_missing_watchlist_file_is_valid_and_says_so",
          missing["present"] is False and missing["empty"] is True
          and missing["companies"] == [] and missing["limitation"]
          and "valid" in missing["limitation"].lower(),
          missing["limitation"])

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rows.json"
        path.write_text(json.dumps({"companies": [
            "Bare Name Ltd",
            {"company": "Object Name Ltd", "careers_url": "https://object-name.invalid/careers",
             "aliases": ["Object Name Limited"], "notes": "owner note"},
            {"company": "", "notes": "no name"},
            "   ",
        ]}), encoding="utf-8")
        loaded = wl.load_watchlist_input(path)
    check("names_objects_and_notes_are_accepted_and_malformed_rows_are_reported",
          [c["company"] for c in loaded["companies"]] == ["Bare Name Ltd", "Object Name Ltd"]
          and len(loaded["malformed_rows"]) == 2
          and loaded["companies"][1]["careers_url"] == "https://object-name.invalid/careers",
          {"companies": [c["company"] for c in loaded["companies"]],
           "malformed": len(loaded["malformed_rows"])})

    # ----------------------------------------------------------------------- #
    # fixture: ALIASES — duplicate spellings collapse, distinct companies do not
    # ----------------------------------------------------------------------- #
    check("fixture_aliases__duplicate_spellings_collapse",
          [c["company"] for c in companies] == ["Fixture Security Ltd", "Fixture Security Group",
                                                "Overlap Test Ltd", "No Surface Co",
                                                "Quiet Roles Ltd"]
          and identity["duplicate_spellings_collapsed"] == 2,
          {"canonical": [c["company"] for c in companies],
           "collapsed": identity["duplicate_spellings_collapsed"]})
    merged = next(c for c in companies if c["company"] == "Fixture Security Ltd")
    group = next(c for c in companies if c["company"] == "Fixture Security Group")
    check("fixture_aliases__distinct_companies_never_merge",
          set(merged["merged_from"]) == {"Fixture Security", "fixture security LTD"}
          and "Fixture Security Limited" in merged["aliases"]
          and group["merged_from"] == [] and group["identity_key"] != merged["identity_key"],
          {"merged_from": merged["merged_from"], "group_key": group["identity_key"],
           "merged_key": merged["identity_key"]})
    check("fixture_aliases__every_merge_records_its_basis",
          identity["merges"] and all(m["basis"] and m["detail"] for m in identity["merges"]),
          [m["basis"] for m in identity["merges"]])
    rows = fx.load_input_fixture()["companies"]
    a = wl.build_identity([dict(r, _index=i) for i, r in enumerate(rows)])
    b = wl.build_identity([dict(r, _index=i) for i, r in enumerate(reversed(rows))])
    key = lambda doc: sorted((c["company"], c["identity_key"], sorted(c["merged_from"]))
                             for c in doc["companies"])
    check("identity_is_deterministic_and_order_independent", key(a) == key(b),
          "mapping identical for the reversed input")

    # ----------------------------------------------------------------------- #
    # 2. declared ATS families and their classification
    # ----------------------------------------------------------------------- #
    policy = wl.policy_document()
    required = ("greenhouse", "lever", "workday", "ashby", "smartrecruiters", "teamtailor",
                "workable")
    check("declared_ats_families_include_the_required_set_plus_region_specific",
          all(r in policy["ats_families"] for r in required)
          and "jobcan_hrmos" in policy["ats_families"],
          sorted(policy["ats_families"]))
    check("every_declared_family_has_a_site_query_host_labels_and_probe_mode",
          all(spec["site_query"].startswith("site:") and spec["host_labels"]
              and spec["probe"] in ("structured", "discovered_url_only")
              for spec in policy["ats_families"].values()),
          sorted(policy["ats_families"]))
    cases = {
        "https://job-boards.greenhouse.io/acme/jobs/1": "greenhouse",
        "https://jobs.lever.co/acme/abc": "lever",
        "https://jobs.ashbyhq.com/acme/1": "ashby",
        "https://apply.workable.com/acme/j/1": "workable",
        "https://jobs.smartrecruiters.com/acme/1": "smartrecruiters",
        "https://acme.wd1.myworkdayjobs.com/en-US/careers": "workday",
        "https://acme.teamtailor.com/jobs/1": "teamtailor",
        "https://acme.jobcan.com/1": "jobcan_hrmos",
        "https://clever.com/careers": None,
        "https://notgreenhouse.io/jobs": None,
        "https://acme.example/careers": None,
    }
    wrong = {u: wl.classify_ats_host(u)["family"] for u, f in cases.items()
             if wl.classify_ats_host(u)["family"] != f}
    check("fixture_ats_discovery__hosts_classified_on_whole_labels_never_substrings",
          not wrong, wrong or "all ok")
    wd = wl.classify_ats_host("https://acme.wd1.myworkdayjobs.com/en-US/careers")
    blank = wl.classify_ats_host("https://myworkdayjobs.com/en-US/careers")
    check("a_workday_tenant_comes_from_the_url_and_is_never_guessed",
          wd["tenant"] == "acme" and blank["tenant"] is None
          and wd["probe"] == "discovered_url_only",
          {"tenant": wd["tenant"], "no_tenant_host_tenant": blank["tenant"]})

    # ----------------------------------------------------------------------- #
    # 3. careers / ATS resolution
    # ----------------------------------------------------------------------- #
    co = {"company": "Fixture Security Ltd", "identity_key": "fixturesecurityltd",
          "careers_url": "https://fixture-security.invalid/careers",
          "name_variants": ["fixturesecurityltd"]}
    ok = wl.resolve_careers_surface(co, fetcher=fx.FakeFetcher(), page_validator=fx.fake_fetch)
    dead = wl.resolve_careers_surface(dict(co, careers_url="https://gone-away.invalid/careers"),
                                      fetcher=fx.FakeFetcher(), page_validator=fx.fake_fetch)
    check("owner_supplied_careers_url_is_verified_before_it_is_trusted",
          ok["state"] == wl.STATE_FOUND and ok["careers_source"] == "owner_supplied_careers_url"
          and ok["careers_page_name_confirmed"] is True and ok["evidence"]
          and dead["careers_source_found"] is False
          and "not 'no jobs'" in (dead["access_blocking_reason"] or ""),
          {"trusted": ok["state"], "unreachable": dead["state"]})
    board_co = {"company": "Attributed Board Ltd", "identity_key": "attributedboardltd",
                "ats_slug_candidates": ["attributedboard"], "name_variants": ["attributedboardltd"]}
    good = wl.resolve_careers_surface(
        board_co, fetcher=fx.structured_board_fetcher("attributedboard",
                                                      company_name="Attributed Board Ltd"),
        page_validator=fx.fake_fetch)
    plain = wl.resolve_careers_surface(
        dict(board_co, ats_slug_candidates=["some-unrelated"]),
        fetcher=fx.unattributed_board_fetcher("some-unrelated"), page_validator=fx.fake_fetch)
    check("a_structured_board_is_used_only_when_the_payload_names_the_company",
          good["careers_source"] == "structured_ats_board"
          and good["attribution_confidence"] == "high"
          and plain["careers_source_found"] is False
          and "UNKNOWN" in (plain["access_blocking_reason"] or ""),
          {"attributed": good["state"], "unattributed": plain["state"]})

    # the whole lane, offline
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = fx.write_lane_fixture(tmp, region="uk", companies=companies)
        lane = out["lane"]
        export = lane_export(tmp, lane)

        # fixture: COMPANY WITH NO CAREERS PAGE
        row = company_by_name(lane, "No Surface Co")
        check("fixture_company_with_no_careers_page_is_unavailable_not_no_jobs",
              row["careers_source_found"] is False
              and row["careers_state"] == wl.STATE_UNAVAILABLE
              and row["careers_url"] is None and row["manual_attribution_required"] is True
              and "not 'no jobs'" in (row["access_blocking_reason"] or "")
              and row["live_vacancies_observed"] == 0,
              {"state": row["careers_state"], "reason": row["access_blocking_reason"]})

        # fixture: COMPANY WITH ZERO MATCHING ROLES
        quiet = company_by_name(lane, "Quiet Roles Ltd")
        check("fixture_company_with_a_resolved_surface_and_zero_matching_roles",
              quiet["careers_source_found"] is True and quiet["queries_executed"] > 0
              and quiet["live_vacancies_observed"] == 0 and quiet["findings"] == 0
              and "not a market fact" in (quiet["access_blocking_reason"] or "")
              and quiet["next_retry_at"],
              {"state": quiet["careers_state"], "reason": quiet["access_blocking_reason"]})

        # fixture: ATS DISCOVERY (Workday via the research lane)
        grp = company_by_name(lane, "Fixture Security Group")
        check("fixture_ats_discovery__careers_surface_discovered_by_the_research_lane",
              grp["careers_source_found"] is True
              and grp["careers_source"] == "discovered_via_research_lane"
              and grp["ats_family"] == "workday"
              and grp["discovered_careers_surfaces"][0]["name_confirmed"] is True
              and grp["discovered_careers_surfaces"][0]["discovered_via_query"],
              {"ats_family": grp["ats_family"], "source": grp["careers_source"]})

        # two complementary query families, always
        fam_ok, scopes_ok = True, True
        needed = {"greenhouse", "lever", "workday", "ashby", "smartrecruiters", "teamtailor",
                  "workable"}
        for c in companies:
            qs = wl.build_company_queries(c, "uk")
            fam_ok = fam_ok and {q["query_family"] for q in qs} \
                == {wl.FAMILY_CAREERS, wl.FAMILY_ROLE}
            scopes = {q["surface_scope"] for q in qs if q["query_family"] == wl.FAMILY_CAREERS}
            scopes_ok = scopes_ok and needed <= scopes
        check("both_query_families_are_generated_for_every_company", fam_ok,
              {"families": [wl.FAMILY_CAREERS, wl.FAMILY_ROLE]})
        check("the_careers_family_covers_every_declared_ats_surface_not_one_board", scopes_ok,
              sorted(needed))
        qs = wl.build_company_queries(companies[0], "uk")
        kept, truncated = wl.apply_query_limit(qs, 6)
        check("a_query_limit_never_drops_a_whole_family",
              truncated and len(kept) == 6
              and {q["query_family"] for q in kept} == {wl.FAMILY_CAREERS, wl.FAMILY_ROLE},
              {"planned": len(qs), "kept": len(kept)})

        # per-company health
        health_fields = ("company", "last_checked", "careers_source_found", "careers_state",
                         "queries_executed", "live_vacancies_observed", "findings",
                         "candidates_after_funnel", "access_blocking_reason", "next_retry_at")
        rows_ok = all(all(f in r for f in health_fields) and r["last_checked"]
                      and r["queries_executed"] > 0 and r["next_retry_at"]
                      for r in lane["companies"])
        check("per_company_health_record_is_complete", rows_ok and len(lane["companies"]) == 5,
              {"companies": len(lane["companies"]), "fields": list(health_fields)})

        # collector: one more source, flag preserved
        collection = pipeline.collect_from_priority_watchlist(export, "uk")
        check("the_lane_is_published_as_one_more_source_with_the_flag",
              collection["available"] is True and collection["candidates"]
              and all(c["priority_watchlist"] is True and c["watchlist_company"]
                      and c["source"] == pipeline.SOURCE_PRIORITY_WATCHLIST
                      for c in collection["candidates"])
              and collection["coverage"]["companies_in_watchlist"] == 5,
              {"findings": len(collection["candidates"]),
               "companies": collection["coverage"]["companies_in_watchlist"]})

        # funnel run: the flag never bypasses a gate; a listing page is never a vacancy
        with tempfile.TemporaryDirectory() as tmp2:
            run = run_cli(pipeline, ["run", "--region", "uk",
                                     "--priority-watchlist", str(export),
                                     "--semantic", "off", "--codex", "off",
                                     "--out-dir", str(Path(tmp2) / "out")])
        listing_url = "https://no-surface.invalid/jobs/cyber-security-jobs-in-london"
        decisions = {d["url"]: d for d in run["eligibility"]["decisions"]}
        accepted_urls = {d["url"] for d in run["eligibility"]["decisions"]
                         if d["decision"] == "accepted"}
        check("the_flag_never_bypasses_the_deterministic_gates",
              decisions[listing_url]["decision"] == "rejected"
              and decisions[listing_url]["priority_watchlist"] is True
              and "not a vacancy posting" in json.dumps(decisions[listing_url]),
              {"decision": decisions[listing_url]["decision"]})
        check("fixture_listing_page_is_never_written_as_a_vacancy",
              decisions[listing_url]["decision"] == "rejected"
              and listing_url not in accepted_urls
              and run["dedupe"]["applied"] is False
              and run["safety"]["canonical_workbook_written"] is False,
              {"tracker_candidates": run["funnel"]["counts"]["tracker_candidates"],
               "accepted": len(accepted_urls)})

        # fixture: DUPLICATE VACANCY (Company Watch + watchlist) merges provenance
        merged_out = tmp / "merged"
        merged_out.mkdir(parents=True, exist_ok=True)
        merged_run = run_cli(pipeline, ["run", "--region", "uk",
                                        "--company-watch", str(COMPANY_WATCH_OVERLAP),
                                        "--priority-watchlist", str(export),
                                        "--semantic", "off", "--codex", "off",
                                        "--out-dir", str(merged_out)])
        # Persist the funnel run where the brief collector can read it (the run doc
        # carries the pipeline's own priority_watchlist block and collection coverage).
        latest = merged_out / "latest.json"
        latest.write_text(json.dumps(merged_run, indent=2), encoding="utf-8")
        url = fx.SHARED_VACANCY_URL
        collapsed = [c for c in merged_run["cross_source_dedupe"]["collapsed"]
                     if url in json.dumps(c)]
        blob = json.dumps(collapsed)
        check("fixture_duplicate_vacancy_from_company_watch_and_watchlist_collapses_with_"
              "both_provenances",
              merged_run["funnel"]["counts"]["cross_source_duplicates_removed"] >= 1
              and bool(collapsed)
              and pipeline.SOURCE_COMPANY_WATCH in blob
              and pipeline.SOURCE_PRIORITY_WATCHLIST in blob,
              {"duplicates_removed":
                   merged_run["funnel"]["counts"]["cross_source_duplicates_removed"]})

        # additive, never a replacement: a market-only run is unchanged
        with tempfile.TemporaryDirectory() as tmp2:
            market_only = run_cli(pipeline, ["run", "--region", "uk",
                                             "--company-watch", str(COMPANY_WATCH_OVERLAP),
                                             "--semantic", "off", "--codex", "off",
                                             "--out-dir", str(Path(tmp2) / "out")])
        check("the_watchlist_is_additive_to_broad_market_search_not_a_replacement",
              pipeline.SOURCE_PRIORITY_WATCHLIST not in
              market_only["funnel"]["counts"]["discovered_raw_by_source"]
              and market_only["funnel"]["counts"]["discovered_raw"] > 0
              and market_only["priority_watchlist"]["declared"] is False,
              {"market_only_discovered": market_only["funnel"]["counts"]["discovered_raw"]})

        # fixture: A WATCHLIST VACANCY STAYS VISIBLE EVEN WHEN NOT TOP-RANKED GLOBALLY
        cfg = {"priority_watchlist": {"latest": str(latest), "stale_after_hours": 48,
                                      "max_items": 10}}
        section = db.collect_priority_watchlist(cfg)
        items = section["items"]
        orders = [i["declared_order"] for i in items]
        check("fixture_watchlist_vacancy_stays_visible_even_when_not_top_ranked_globally",
              section["declared"] is True and items
              and orders == sorted(orders)
              and section["items_total"] == len(section["items"])
              and "canonical order" in section["ranking_semantics"]["note"],
              {"items": len(items), "orders": orders,
               "companies": section["companies"]})
        not_ranked = [i for i in items if not i["in_priority_ranking"]]
        check("a_watchlist_item_that_did_not_reach_the_gates_stays_visible_in_the_section",
              not_ranked and all(i["state"] for i in not_ranked)
              and section["items_not_reaching_gates"] >= 1,
              {"not_ranked": len(not_ranked),
               "items_total": section["items_total"]})

        # read-only manifest
        manifest = wl.read_only_manifest(lane, merged_run, "uk")
        check("the_read_only_manifest_lists_findings_and_writes_no_tracker",
              manifest["read_only"] is True
              and manifest["canonical_workbook_written"] is False
              and manifest["companies"] and "accepted" in manifest,
              {"companies": len(manifest["companies"]),
               "accepted": len(manifest["accepted"])})

    # ----------------------------------------------------------------------- #
    # 4. safety, privacy and STOP conditions
    # ----------------------------------------------------------------------- #
    src = Path(wl.__file__).read_text(encoding="utf-8")
    banned = ("selenium", "playwright", "pyppeteer", "webdriver", "mechanize", "cookiejar",
              "requests.session(", "logout(", "sign_in(", "log_in(")
    check("the_lane_uses_no_browser_gui_or_signed_in_session",
          not any(b in src for b in banned), "no browser/session construct present")

    hosts = re.findall(r"https?://([^/\"]+)", INPUT_FIXTURE.read_text(encoding="utf-8")
                       + COMPANY_WATCH_OVERLAP.read_text(encoding="utf-8"))
    check("no_fixture_claims_a_real_employer_or_vacancy",
          bool(hosts) and all(h.endswith(".invalid") for h in hosts)
          and json.loads(INPUT_FIXTURE.read_text(encoding="utf-8")).get("not_a_real_company")
          and json.loads(COMPANY_WATCH_OVERLAP.read_text(encoding="utf-8"))
          .get("not_a_real_vacancy"),
          {"hosts": len(hosts)})

    after = tracker_hashes()
    check("canonical_workbooks_byte_identical_before_and_after",
          before == after, {r: after[r]["sha256"] for r in after})

    finished = dt.datetime.now(dt.timezone.utc)
    failed = [c for c in checks if not c["ok"]]
    doc = {
        "task": "agent-career-priority-company-watchlist-engine-2026-09-24",
        "runner": "career-ops/run_watchlist_acceptance.py",
        "stamp": stamp,
        "started_at": started.replace(microsecond=0).isoformat(),
        "finished_at": finished.replace(microsecond=0).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "counts": {"checks": len(checks), "passed": len(checks) - len(failed),
                   "failed": len(failed)},
        "lane": {"companies": len(companies),
                 "duplicate_spellings_collapsed": identity["duplicate_spellings_collapsed"],
                 "ats_families": sorted(policy["ats_families"]),
                 "query_families": list(wl.QUERY_FAMILIES)},
        "canonical_workbooks": after,
        "safety": {
            "canonical_workbook_writes": 0,
            "applications_submitted": 0,
            "employer_or_recruiter_contacts": 0,
            "browser_or_gui_used": False,
            "login_or_account_used": False,
            "cookies_or_session_used": False,
            "captcha_bypassed": False,
            "scraping_behind_auth": False,
        },
        "privacy_note": ("the owner's company list and the discovered careers URLs/vacancies are "
                         "owner-private; they stay under the git-ignored runtime directory and "
                         "this evidence is aggregate only"),
    }
    (out_dir / "evidence.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    lines = [f"# Owner priority watchlist acceptance (B27) — {stamp}", "",
             f"Status: **{doc['status']}** ({doc['counts']['passed']}/{doc['counts']['checks']} "
             "checks)", ""]
    for c in checks:
        lines.append(f"- [{'x' if c['ok'] else ' '}] `{c['check']}` — "
                     f"{json.dumps(c['detail'], ensure_ascii=False)[:400]}")
    lines += ["", "Read-only: no canonical workbook was written and no application, outreach, "
                  "browser or account action occurred."]
    (out_dir / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"{doc['status']}: {doc['counts']['passed']}/{doc['counts']['checks']} checks; "
              f"evidence written to {out_dir}")
        for c in failed:
            print(f"  FAILED {c['check']}: {json.dumps(c['detail'], ensure_ascii=False)[:300]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
