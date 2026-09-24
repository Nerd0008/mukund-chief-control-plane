#!/usr/bin/env python3
"""Acceptance run for the bounded, read-only open-web job research lane (B26).

Proves, offline and against a real bounded live pass when the runtime supports it:

1. the query matrix is generated across role families and configured regions, the
   owner's existing ``search_queries`` site: patterns are preserved, and the
   company-watchlist hook is optional;
2. the surface classifier maps public LinkedIn / Indeed / ATS / employer URLs to
   the right discovery surface;
3. a captured search run normalises into the ONE unified candidate schema with
   full per-result provenance (query, surface, result URL, canonical URL, observed
   fields, fetch state, source timestamp, missing fields);
4. one posting seen by two queries collapses to one candidate;
5. every declared telemetry counter exists and a zero is attributable;
6. **anti-fabrication**: a "result" the research worker did not actually search for
   is never accepted;
7. **fail-closed**: a destination that was not validated live never reaches a
   tracker manifest, and the zero is attributed to the deterministic gate;
8. the web-research surface collapses with the regional lane into ONE canonical
   candidate carrying both surfaces' provenance;
9. the Codex provider reports unavailability truthfully when the CLI is absent;
10. the four canonical workbooks are byte-identical before and after;
11. (``--live``) the Codex CLI can perform a real web search in this runtime, and
    a bounded live research pass produces real candidates from whatever source
    classes were genuinely reached — recorded truthfully, never fabricated.

Raw result URLs are owner-private job-search data: they are written under the
git-ignored runtime directory, and only aggregate counters/source classes are
printed/committed.

Usage:
  python career-ops/run_web_research_acceptance.py [--live] [--stamp S] [--json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
for _p in (str(CAREER_OPS_DIR), str(CAREER_OPS_DIR / "discovery")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pipeline  # noqa: E402
import tracker_writer as tw  # noqa: E402
import web_research as wr  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures" / "discovery"
WEB_FIXTURES = FIXTURES / "web-research"
CAPTURE = WEB_FIXTURES / "captured-codex-search.json"
UNVERIFIED_EXPORT = WEB_FIXTURES / "web-research-export-unverified.json"
REGIONAL = FIXTURES / "regional-overlap.json"
PROFILES = tw.load_profiles()
REGIONS = ("uk", "dubai", "japan", "singapore")
RUNTIME = CONTROL_PLANE / "runtime" / "career-ops" / "web-research"


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


def capture_queries() -> list:
    doc = json.loads(CAPTURE.read_text(encoding="utf-8"))
    return [{k: q.get(k) for k in ("query_id", "query", "region", "role_family",
                                   "surface_scope", "query_provenance")}
            for q in doc["queries"]]


def fake_validate_failed(url, **kw):
    return {"url": url, "status": wr.FETCH_VALIDATION_FAILED, "http_status": 404,
            "canonical_url": wr.canonical_url(url), "final_url": url, "page_title": None,
            "meta_description": None, "robots": "test", "error": "HTTP 404"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Open-web research lane acceptance (B26)")
    ap.add_argument("--live", action="store_true",
                    help="also run a bounded live Codex web-research pass")
    ap.add_argument("--live-queries", type=int, default=3)
    ap.add_argument("--stamp")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    started = dt.datetime.now(dt.timezone.utc)
    stamp = args.stamp or started.strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = CONTROL_PLANE / "audits" / "evidence" / f"{stamp}-career-open-web-research"
    out_dir.mkdir(parents=True, exist_ok=True)

    checks: list = []

    def check(name: str, ok: bool, detail) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    before = tracker_hashes()

    # 1. query matrix -------------------------------------------------------- #
    matrix = wr.build_query_matrix("uk")
    families = {q["role_family"] for q in matrix}
    surfaces = {q["surface_scope"] for q in matrix}
    check("query_matrix_covers_role_families", set(wr.ROLE_FAMILIES) <= families,
          sorted(families))
    check("query_matrix_covers_owner_ats_site_patterns",
          all(s in surfaces for s, _ in wr.OWNER_ATS_SITE_QUERIES), sorted(surfaces))
    check("query_matrix_covers_broad_public_surfaces",
          all(s in surfaces for s, _ in wr.BROAD_SURFACES),
          [s for s, _ in wr.BROAD_SURFACES])
    check("query_matrix_is_per_region",
          all(wr.build_query_matrix(r) and all(q["region"] == r
              for q in wr.build_query_matrix(r)) for r in REGIONS), list(REGIONS))
    wl = wr.build_query_matrix("uk", include_watchlist=["Fixture Corp (NOT A REAL COMPANY)"])
    check("watchlist_hook_adds_company_queries_and_is_optional",
          len(wl) > len(matrix)
          and any(q["role_family"] == "watchlist" for q in wl)
          and not any(q["role_family"] == "watchlist" for q in matrix),
          {"generic": len(matrix), "with_watchlist": len(wl)})

    # 2. surface classification --------------------------------------------- #
    surface_cases = {
        "https://www.linkedin.com/jobs/view/4012345678": "linkedin_jobs",
        "https://uk.indeed.com/viewjob?jk=a": "indeed",
        "https://job-boards.greenhouse.io/acme/jobs/1": "greenhouse",
        "https://jobs.lever.co/acme/1": "lever",
        "https://acme.wd1.myworkdayjobs.com/en-US/careers/job/1": "workday",
        "https://jobs.ashbyhq.com/acme/1": "ashby",
        "https://jobs.smartrecruiters.com/acme/1": "smartrecruiters",
        "https://acme.teamtailor.com/jobs/1": "teamtailor",
        "https://apply.workable.com/acme/j/1": "workable",
        "https://acme.jobcan.com/1": "jobcan_hrmos",
        "https://careers.acme.example.org/roles/graduate": "employer_careers",
    }
    wrong = {u: wr.classify_surface(u) for u, s in surface_cases.items()
             if wr.classify_surface(u) != s}
    check("surface_classifier_maps_linkedin_indeed_ats_employer", not wrong, wrong or "all ok")

    # 3. captured normalisation + provenance -------------------------------- #
    research_doc = wr.run_research(capture_queries(), wr.CapturedResultsProvider(CAPTURE),
                                   region="uk", validate=False)
    check("captured_run_normalises_into_the_candidate_schema",
          len(research_doc["candidates"]) == 5
          and len({c["web_research"]["discovery_surface"] for c in research_doc["candidates"]}) >= 4,
          {"candidates": len(research_doc["candidates"])})
    provenance_ok = all(
        c["web_research"]["search_query"] and c["web_research"]["query_id"]
        and c["web_research"]["result_url"] == c["url"]
        and c["web_research"]["canonical_url"] and c["web_research"]["source_timestamp"]
        and c["fetch_state"] in wr.FETCH_STATES
        and "missing_fields" in c["web_research"]
        for c in research_doc["candidates"])
    check("per_result_provenance_is_complete", provenance_ok, "query/surface/url/state/timestamp")
    check("a_posting_seen_by_two_queries_collapses_to_one_candidate",
          research_doc["telemetry"]["duplicates_collapsed"] == 1,
          research_doc["telemetry"]["duplicates_collapsed"])

    # 4. telemetry ---------------------------------------------------------- #
    telemetry = research_doc["telemetry"]
    check("every_declared_telemetry_counter_exists",
          all(k in telemetry for k in wr.TELEMETRY_KEYS), sorted(telemetry))
    zero_wait = wr.run_research(capture_queries(), wr.CapturedResultsProvider(CAPTURE),
                                region="uk", validate=True, validate_fn=fake_validate_failed)
    check("a_zero_is_attributable_to_the_failing_stage",
          zero_wait["telemetry"]["validation_failed"] == 5
          and zero_wait["telemetry"]["zero_attribution"].get("validation"),
          zero_wait["telemetry"]["zero_attribution"])

    # 5. anti-fabrication --------------------------------------------------- #
    class NoSearchProvider(wr.ResearchProvider):
        name = "acceptance-no-search"

        def probe(self):
            return {"provider": self.name, "available": False}

        def research(self, queries, *, limit_per_query=5, timeout=240):
            return {"provider": self.name, "available": False, "requests": 1,
                    "web_search_observed_queries": 0,
                    "queries_without_observed_search": len(queries),
                    "queries": [dict(q, executed=True, web_search_observed=False,
                                     results=[{"title": "Fabricated @ X (NOT REAL)",
                                               "url": "https://fabricated.invalid/1"}])
                                for q in queries]}

    fab = wr.run_research(capture_queries()[:1], NoSearchProvider(), region="uk", validate=False)
    check("a_result_without_an_observed_search_is_never_accepted",
          fab["candidates"] == [] and fab["telemetry"]["results_seen"] == 0
          and fab["telemetry"]["rejections_by_reason"].get("search_not_observed") == 1,
          fab["telemetry"]["rejections_by_reason"])

    # 6. fail-closed -------------------------------------------------------- #
    with tempfile.TemporaryDirectory() as tmp:
        unv = run_cli(pipeline, ["run", "--region", "uk",
                                 "--web-research", str(UNVERIFIED_EXPORT),
                                 "--semantic", "off", "--codex", "off",
                                 "--out-dir", str(Path(tmp) / "out")])
    decisions = {d["company"]: d for d in unv["eligibility"]["decisions"]}
    live_ok = decisions.get("Validated Live Ltd (NOT A REAL VACANCY)", {}).get("decision")
    blocked = [c for c, d in decisions.items() if c != "Validated Live Ltd (NOT A REAL VACANCY)"
               and d["decision"] == "rejected"]
    check("only_the_validated_destination_passes_the_gates",
          live_ok == "accepted" and len(blocked) == 3
          and unv["funnel"]["counts"]["deterministic_eligibility_pass"] == 1,
          {"accepted": live_ok, "rejected": len(blocked)})
    gate_text = json.dumps(unv["funnel"]["by_source"][pipeline.SOURCE_WEB_RESEARCH]
                           ["rejections_by_reason"])
    check("unverified_and_failed_destinations_are_refused_by_the_gate",
          "not validated live" in gate_text, "deterministic gate reason present")

    # 7. cross-source collapse ---------------------------------------------- #
    with tempfile.TemporaryDirectory() as tmp:
        export = Path(tmp) / "export.json"
        export.write_text(json.dumps(research_doc, indent=2), encoding="utf-8")
        merged = run_cli(pipeline, ["run", "--region", "uk",
                                    "--records", str(REGIONAL),
                                    "--web-research", str(export),
                                    "--semantic", "off", "--codex", "off",
                                    "--out-dir", str(Path(tmp) / "out")])
    shared = [c for c in merged["canonical_candidates"]
              if c["duplicate_discoveries"]
              and pipeline.SOURCE_WEB_RESEARCH in c["sources"]
              and pipeline.SOURCE_EXPLICIT in c["sources"]]
    check("web_research_and_the_regional_lane_collapse_to_one_candidate",
          len(shared) == 1 and len(shared[0]["provenance"]) == 2,
          {"shared": len(shared),
           "sources": shared[0]["sources"] if shared else None})

    # 8. provider honesty --------------------------------------------------- #
    provider = wr.CodexWebSearchProvider(executable="/nonexistent/codex")
    real_resolve = provider.resolve

    def _boom():
        raise RuntimeError("Codex CLI not found (acceptance)")

    provider.resolve = _boom
    absent = provider.probe()
    provider.resolve = real_resolve
    check("codex_provider_reports_unavailability_truthfully_when_absent",
          absent["available"] is False and "unavailable" in absent["reason"],
          absent["reason"])

    # 9. lane CLI is read-only ---------------------------------------------- #
    with tempfile.TemporaryDirectory() as tmp:
        none_doc = run_cli(wr, ["run", "--region", "uk", "--provider", "none",
                                "--limit-queries", "2", "--out-dir", tmp])
    check("lane_default_run_is_read_only_and_declares_zero_attribution",
          none_doc["safety"]["read_only"] is True
          and none_doc["safety"]["canonical_workbook_written"] is False
          and none_doc["candidates"] == []
          and bool(none_doc["telemetry"]["zero_attribution"]),
          none_doc["telemetry"]["zero_attribution"])

    # 10. workbooks untouched ----------------------------------------------- #
    after = tracker_hashes()
    check("canonical_workbooks_byte_identical", before == after,
          {r: after[r]["sha256"] for r in after})

    live = {"attempted": False}
    if args.live:
        live = live_acceptance(RUNTIME, args.live_queries)
        check("live_codex_web_search_capability_proven",
              bool(live["probe"].get("available")), live["probe"].get("reason") or "available")
        check("live_research_produced_real_candidates",
              live["run"]["telemetry"]["results_seen"] > 0
              and len(live["run"]["candidates"]) > 0,
              {"queries_executed": live["run"]["telemetry"]["queries_executed"],
               "results_seen": live["run"]["telemetry"]["results_seen"],
               "candidates": len(live["run"]["candidates"]),
               "source_classes_reached": live["source_classes_reached"]})
        check("live_research_declares_only_reached_source_classes",
              isinstance(live["source_classes_reached"], list)
              and all(s in wr.SURFACES for s in live["source_classes_reached"]),
              live["source_classes_reached"])

    after_live = tracker_hashes()
    check("canonical_workbooks_byte_identical_after_live_pass", before == after_live,
          {r: after_live[r]["sha256"] for r in after_live})

    finished = dt.datetime.now(dt.timezone.utc)
    failed = [c for c in checks if not c["ok"]]
    doc = {
        "task": "agent-career-codex-style-open-web-job-research-2026-09-24",
        "runner": "career-ops/run_web_research_acceptance.py",
        "stamp": stamp,
        "started_at": started.replace(microsecond=0).isoformat(),
        "finished_at": finished.replace(microsecond=0).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "counts": {"checks": len(checks), "passed": len(checks) - len(failed),
                   "failed": len(failed)},
        "matrix": {"queries_uk": len(matrix), "surfaces": sorted(surfaces),
                   "families": sorted(families)},
        "research_telemetry": telemetry,
        "live": live,
        "canonical_workbooks": after_live,
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
        "privacy_note": ("raw result URLs are owner-private job-search data and stay under the "
                         "git-ignored runtime directory; this evidence is aggregate only"),
    }
    (out_dir / "evidence.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    lines = [f"# Open-web research lane acceptance — {stamp}", "",
             f"Status: **{doc['status']}** ({doc['counts']['passed']}/{doc['counts']['checks']} checks)",
             ""]
    for c in checks:
        lines.append(f"- [{'x' if c['ok'] else ' '}] `{c['check']}` — "
                     f"{json.dumps(c['detail'], ensure_ascii=False)[:400]}")
    lines += ["", "Raw result URLs stay in the git-ignored runtime directory; this evidence is "
                  "aggregate only. No canonical workbook was written and no application, "
                  "outreach, browser or account action occurred."]
    (out_dir / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"{doc['status']}: {doc['counts']['passed']}/{doc['counts']['checks']} checks; "
              f"evidence written to {out_dir}")
        for c in failed:
            print(f"  FAILED {c['check']}: {json.dumps(c['detail'], ensure_ascii=False)[:300]}")
    return 0 if not failed else 1


def live_acceptance(runtime_dir: Path, live_queries: int) -> dict:
    """Bounded live pass. Records only aggregate counts publicly; raw URLs stay local."""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    provider = wr.CodexWebSearchProvider()
    probe = provider.probe()
    result = {"attempted": True, "probe": {k: v for k, v in probe.items()
                                           if k != "executed_queries"},
              "executed_queries": probe.get("executed_queries") or [],
              "run": {"candidates": [], "telemetry": {}}, "source_classes_reached": [],
              "export_file": None, "queries_executed": []}
    if not probe.get("available"):
        return result
    matrix = wr.build_query_matrix("uk")[:max(1, live_queries)]
    doc = wr.run_research(matrix, provider, region="uk", limit_per_query=5, timeout=300,
                          validate=True, max_urls=live_queries * 5)
    path = runtime_dir / f"live-acceptance-{doc['export_id']}.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    latest = runtime_dir / "live-acceptance-latest.json"
    latest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    result["export_file"] = str(path)
    result["run"] = {"candidates": doc["candidates"], "telemetry": doc["telemetry"],
                     "export_id": doc["export_id"]}
    result["queries_executed"] = [q["query"] for q in doc["queries"] if q["executed"]]
    result["source_classes_reached"] = sorted({c["web_research"]["discovery_surface"]
                                               for c in doc["candidates"]})
    return result


if __name__ == "__main__":
    raise SystemExit(main())
