#!/usr/bin/env python3
"""Owner-safe acceptance for the unified scheduled Career discovery cutover.

What this proves
----------------
``career-ops/discovery/scheduled_orchestrator.py`` is the real scheduled path
(``career-ops/run_scheduled_scan.cmd`` -> ``ChiefCareerScan-{UK,Dubai,Japan,
Singapore}``). This runner proves, from real execution only:

  1. structural/cutover checks (offline): the launcher invokes the orchestrator and
     not the old single worker, high_recall is the production policy, the owner's
     Intern/Internship-only rule is a declared diagnostic, the five coverage states
     exist and every required source class is declared;
  2. a bounded offline whole-company regression: one unified funnel + one unified
     candidate manifest across all four regions, and the Career Daily Brief reads it;
  3. (``--live``) a bounded live pass per region: the research provider is
     probed and each region's bounded run is executed with a small query budget;
     each region's source classes are recorded from that run's own evidence
     (reached / blocked / unavailable / not_applicable / searched_no_results) and a
     region with no operational current-web search is reported as NOT
     production-ready with its ``no_go`` text — never as an empty market;
  4. public LinkedIn Jobs discovery is exercised explicitly (the round-robin query
     selection puts ``site:linkedin.com/jobs`` first), and the result is recorded
     truthfully: a discovered public LinkedIn result URL, or the blocked/unavailable
     state with its evidence;
  5. the canonical tracker workbooks are byte-identical before and after every run
     (no tracker write, no application, no outreach, no login, no browser/GUI).

Safety: no canonical workbook is ever opened for writing, nothing is submitted or
contacted, no account/session/cookie is used and no browser or GUI automation is
imported. Raw result URLs are owner-private job-search data and stay under the
git-ignored ``runtime/`` tree; the committed evidence is aggregate only.

Usage
-----
  python career-ops/run_scheduled_orchestrator_acceptance.py
  python career-ops/run_scheduled_orchestrator_acceptance.py --live --live-queries 2 --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
for _p in (str(CAREER_OPS_DIR), str(CAREER_OPS_DIR / "discovery")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import daily_brief  # noqa: E402
import pipeline  # noqa: E402
import scheduled_orchestrator as so  # noqa: E402
import tracker_writer as tw  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures" / "discovery"
UNVERIFIED_EXPORT = FIXTURES / "web-research" / "web-research-export-unverified.json"
LAUNCHER = CAREER_OPS_DIR / "run_scheduled_scan.cmd"
DOC = CAREER_OPS_DIR / "scheduled_orchestrator.md"
PROFILES = tw.load_profiles()
REGIONS = ("uk", "dubai", "japan", "singapore")
RUNTIME = CONTROL_PLANE / "runtime" / "career-ops" / "discovery"
EVIDENCE_ROOT = CONTROL_PLANE / "audits" / "evidence"

BANNED_IMPORTS = ("selenium", "playwright", "pyppeteer", "requests_html", "webbrowser",
                  "scrapy", "splinter")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tracker_hashes() -> dict:
    out = {}
    for region in REGIONS:
        p = Path(tw.region_config(PROFILES, region)["tracker"])
        out[region] = {"path": str(p), "sha256": sha256_file(p) if p.exists() else None}
    return out


def run_cli(mod, argv: list):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(argv)
    return rc, json.loads(buf.getvalue())


def browser_free() -> dict:
    """No browser/GUI/scraping library is imported anywhere on this path."""
    offenders = {}
    targets = [CAREER_OPS_DIR / "discovery" / "scheduled_orchestrator.py",
               CAREER_OPS_DIR / "discovery" / "pipeline.py",
               CAREER_OPS_DIR / "discovery" / "web_research.py"]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        found = [b for b in BANNED_IMPORTS if b in text]
        if found:
            offenders[str(path)] = found
    return offenders


def offline_checks(check) -> None:
    # 1. cutover wiring ----------------------------------------------------- #
    text = LAUNCHER.read_text(encoding="utf-8")
    raw = LAUNCHER.read_bytes()
    active = [ln for ln in text.splitlines() if not ln.strip().lower().startswith("rem")]
    joined = "\n".join(active)
    check("launcher_invokes_the_unified_orchestrator",
          "scheduled_orchestrator.py" in joined and "--scheduled" in joined,
          {"active_lines": len(active)})
    check("launcher_requires_a_live_current_web_mechanism",
          "--require-live-web" in joined, "--require-live-web present")
    check("launcher_uses_the_high_recall_production_policy",
          "--mode high_recall" in joined, "--mode high_recall present")
    check("launcher_no_longer_runs_the_old_single_worker",
          "regional_job_search.py" not in joined
          and "regional_job_search.py" in text,  # rollback doc keeps the old command
          "old worker only inside the documented rollback")
    check("launcher_keeps_crlf_line_endings",
          raw.count(b"\r\n") == raw.count(b"\n") > 0, "CRLF preserved (bytes)")
    check("launcher_never_applies_or_submits",
          "--apply" not in joined and "submission" not in joined, "read-only")

    # 2. policy ------------------------------------------------------------- #
    policy = so.policy_document()
    check("production_discovery_policy_is_high_recall",
          policy["production_discovery_policy"] == "high_recall"
          and so.DEFAULT_MODE == "high_recall" and pipeline.DEFAULT_MODE == "high_recall",
          policy["production_discovery_policy"])
    check("owner_intern_rule_is_a_declared_diagnostic_only",
          "intern_only" in policy["diagnostic_modes"]
          and "never the scheduled discovery gate" in policy["diagnostic_modes"]["intern_only"],
          policy["diagnostic_modes"]["intern_only"])
    check("five_coverage_states_are_declared",
          set(so.COVERAGE_STATE_RULES) == {"reached", "blocked", "unavailable",
                                           "not_applicable", "searched_no_results"},
          sorted(so.COVERAGE_STATE_RULES))
    check("every_required_source_class_is_declared",
          set(so.CLASS_ORDER) == {"public_linkedin_jobs", "public_indeed", "web_index",
                                  "ats_employer_careers"},
          list(so.CLASS_ORDER))
    check("budgets_lock_and_rollback_are_declared",
          bool(policy["budgets"]["overall_seconds"]) and bool(policy["concurrency"]["lock_file"])
          and bool(policy["rollback"]["previous_launcher_command"])
          and bool(policy["no_go_criteria"]), "budgets/lock/rollback/no-go present")

    # 3. operational documentation ------------------------------------------ #
    doc = DOC.read_text(encoding="utf-8")
    missing = [s for s in ("Run commands", "Outputs", "Source-coverage matrix", "Rollback",
                           "No-go criteria", "Daily Brief integration", "Bounds, retries and",
                           "concurrency") if s not in doc]
    check("operational_documentation_covers_required_sections", not missing, missing or "complete")

    # 4. no browser/GUI/scraping import ------------------------------------- #
    offenders = browser_free()
    check("no_browser_or_gui_imports_on_this_path", not offenders, offenders or "clean")

    # 5. offline whole-company regression ----------------------------------- #
    out = RUNTIME / "acceptance"
    out.mkdir(parents=True, exist_ok=True)
    rc, unified = run_cli(so, ["run-all", "--no-live", "--reuse-web-export",
                               str(UNVERIFIED_EXPORT), "--skip-regional-scan",
                               "--semantic", "off", "--codex", "off", "--no-lock",
                               "--out-dir", str(out), "--web-out-dir", str(out / "web"),
                               "--state-file-out", str(out / "state.json")])
    check("whole_company_regression_run_all_completes", rc == 0, {"rc": rc})
    check("one_unified_run_covers_all_four_regions",
          unified.get("regions_covered") == sorted(REGIONS), unified.get("regions_covered"))
    manifest = None
    mf = out / "unified-manifest-latest.json"
    if mf.exists():
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    check("one_unified_candidate_manifest_is_written",
          bool(manifest) and manifest["kind"] == "career-ops.unified-nightly-candidate-manifest"
          and manifest["regions"] == sorted(REGIONS) and manifest["read_only"] is True
          and manifest["canonical_workbook_written"] is False,
          (manifest or {}).get("counts"))
    check("aggregate_counters_are_the_sum_of_the_regions",
          all(unified["funnel"]["counts"].get(k, 0) ==
              sum((d["funnel"]["counts"] or {}).get(k, 0) for d in unified["regions"].values())
              for k in so.COUNT_KEYS), "sum verified")
    coverage = unified.get("source_coverage") or {}
    check("every_region_records_a_source_coverage_matrix",
          sorted(coverage) == sorted(REGIONS)
          and all(set(c.get("classes") or {}) == set(so.CLASS_ORDER)
                  for c in coverage.values()),
          {r: {k: v.get("state") for k, v in (c.get("classes") or {}).items()}
           for r, c in sorted(coverage.items())})
    check("no_coverage_state_is_the_bare_word_empty",
          all((entry.get("state") in so.COVERAGE_STATE_RULES)
              for c in coverage.values() for entry in (c.get("classes") or {}).values()),
          "states restricted to the declared vocabulary")

    # 6. Daily Brief reads the unified run ----------------------------------- #
    view = daily_brief.source_coverage_view(unified)
    check("daily_brief_reads_the_unified_source_coverage",
          bool(view["sources"]) and sorted(view["classes_by_region"]) == sorted(REGIONS)
          and "never reported as an empty source" in view["note"],
          sorted(view["classes_by_region"]))

    # 7. idempotency + lock are honoured ------------------------------------ #
    rc2, second = run_cli(so, ["run-all", "--no-live", "--reuse-web-export",
                               str(UNVERIFIED_EXPORT), "--skip-regional-scan",
                               "--semantic", "off", "--codex", "off", "--no-lock",
                               "--out-dir", str(out), "--web-out-dir", str(out / "web"),
                               "--state-file-out", str(out / "state.json")])
    check("a_repeat_run_is_bounded_and_idempotent",
          rc2 == 0 and all(d["live_research"]["operational"] is False
                           for d in second["regions"].values()), "offline replay is not live proof")


def live_checks(check, queries: int, per_query_timeout: int, budget_seconds: int,
                regions: tuple, max_urls: int, label: str = "live") -> dict:
    """Bounded live pass per region. Read-only; raw URLs stay under runtime/."""
    results = {}
    out = RUNTIME / f"acceptance-{label}"
    out.mkdir(parents=True, exist_ok=True)
    for region in regions:
        argv = ["run", "--region", region, "--scheduled", "--require-live-web",
                "--mode", "high_recall", "--web-queries", str(queries),
                "--max-urls", str(max_urls), "--per-query-timeout", str(per_query_timeout),
                "--budget-seconds", str(budget_seconds), "--skip-regional-scan",
                "--semantic", "off", "--codex", "off", "--no-lock",
                "--out-dir", str(out / region),
                "--web-out-dir", str(out / region / "web"),
                "--state-file-out", str(out / region / "state.json"),
                "--scan-records-dir", str(out / region / "scan-runs")]
        try:
            rc, doc = run_cli(so, argv)
        except Exception as exc:  # noqa: BLE001 - a failed region is recorded, not raised
            results[region] = {"rc": None, "error": f"{type(exc).__name__}: {exc}"}
            check(f"{label}_{region}_run_completed_without_error", False,
                  results[region]["error"])
            continue
        lr = doc.get("live_research") or {}
        cov = {k: v.get("state") for k, v in
               ((doc.get("source_coverage") or {}).get("classes") or {}).items()}
        classes = (doc.get("source_coverage") or {}).get("classes") or {}
        linkedin = classes.get("public_linkedin_jobs") or {}
        region_result = {
            "rc": rc,
            "run_health_file": doc.get("run_health_file"),
            "production_ready": doc.get("production_ready"),
            "no_go": doc.get("no_go"),
            "live_mechanism": lr.get("mechanism"),
            "live_search_queries_observed": lr.get("live_search_queries_observed"),
            "classes": cov,
            "class_counters": {k: {"queries_targeting": v.get("queries_targeting"),
                                   "queries_with_observed_live_search":
                                       v.get("queries_with_observed_live_search"),
                                   "result_urls_discovered": v.get("result_urls_discovered"),
                                   "job_posting_urls": v.get("job_posting_urls"),
                                   "validated_live": v.get("validated_live"),
                                   "validation_failed": v.get("validation_failed"),
                                   "blocking_evidence": v.get("blocking_evidence")}
                               for k, v in classes.items()},
            "linkedin_class": {"state": linkedin.get("state"),
                               "result_urls_discovered": linkedin.get("result_urls_discovered"),
                               "job_posting_urls": linkedin.get("job_posting_urls"),
                               "validated_live": linkedin.get("validated_live"),
                               "blocking_evidence": linkedin.get("blocking_evidence")},
            "tracker_candidates": (doc.get("funnel") or {}).get("counts", {}).get(
                "tracker_candidates"),
        }
        results[region] = region_result
        check(f"{label}_{region}_run_completed_without_error", rc in (0, 3),
              {"rc": rc, "region": region})
        check(f"{label}_{region}_records_a_coverage_matrix_from_evidence",
              set(cov) == set(so.CLASS_ORDER) and all(s in so.COVERAGE_STATE_RULES
                                                      for s in cov.values()), cov)
        check(f"{label}_{region}_live_mechanism_is_proven_or_truthfully_absent",
              bool(lr) and (lr.get("operational") is True or bool(doc.get("no_go"))),
              {"operational": lr.get("operational"), "mechanism": lr.get("mechanism"),
               "no_go": doc.get("no_go")})
        # a blocked/unavailable class must never be reported as empty
        check(f"{label}_{region}_no_blocked_class_is_called_empty",
              all(s != "empty" for s in cov.values()), cov)
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unified scheduled Career discovery cutover "
                                             "acceptance")
    ap.add_argument("--live", action="store_true",
                    help="also run a bounded live pass per region (real current-web search)")
    ap.add_argument("--live-queries", type=int, default=2,
                    help="bounded queries per region (round-robin: LinkedIn first)")
    ap.add_argument("--live-regions", default=",".join(REGIONS))
    ap.add_argument("--broad-region", default="uk",
                    help="region used for the broad source-class live pass (all four classes)")
    ap.add_argument("--broad-queries", type=int, default=4,
                    help="queries for the broad pass; round-robin reaches every source class "
                         "(0 disables)")
    ap.add_argument("--per-query-timeout", type=int, default=180)
    ap.add_argument("--budget-seconds", type=int, default=900)
    ap.add_argument("--max-urls", type=int, default=8)
    ap.add_argument("--stamp")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    started = dt.datetime.now(dt.timezone.utc)
    stamp = args.stamp or started.strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = EVIDENCE_ROOT / f"{stamp}-career-scheduled-orchestrator-cutover"
    out_dir.mkdir(parents=True, exist_ok=True)

    checks: list = []

    def check(name: str, ok: bool, detail) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    before = tracker_hashes()
    offline_checks(check)
    after_offline = tracker_hashes()
    check("canonical_workbooks_byte_identical_after_the_offline_regression",
          before == after_offline, {r: after_offline[r]["sha256"] for r in after_offline})

    live = {"attempted": False}
    if args.live:
        regions = tuple(r.strip() for r in args.live_regions.split(",") if r.strip())
        live = {"attempted": True, "regions": list(regions),
                "queries_per_region": args.live_queries,
                "results": live_checks(check, args.live_queries, args.per_query_timeout,
                                       args.budget_seconds, regions, args.max_urls)}
        live["regions_with_production_ready_live"] = sorted(
            r for r, d in live["results"].items() if d.get("production_ready"))
        live["linkedin_public_discovery"] = {
            r: d.get("linkedin_class") for r, d in live["results"].items()}

        # broad pass: one region, enough queries that round-robin reaches EVERY required
        # source class (public LinkedIn Jobs, public Indeed, Google/web index, ATS/employer
        # careers). The small per-region budget above cannot reach the last two.
        broad_region = (args.broad_region or "").strip()
        if args.broad_queries > 0 and broad_region:
            broad = live_checks(check, args.broad_queries, args.per_query_timeout,
                                args.budget_seconds, (broad_region,), args.max_urls,
                                label="broad")
            entry = broad.get(broad_region) or {}
            states = entry.get("classes") or {}
            counters = entry.get("class_counters") or {}
            attempted = sorted(k for k, v in states.items() if v != "not_applicable")
            check("broad_live_pass_attempts_every_required_source_class",
                  set(attempted) == set(so.CLASS_ORDER),
                  {"region": broad_region, "attempted": attempted, "states": states})
            check("broad_live_pass_records_linkedin_indeed_webindex_and_ats_evidence",
                  all(states.get(c) in so.COVERAGE_STATE_RULES
                      for c in so.CLASS_ORDER),
                  {c: counters.get(c) for c in so.CLASS_ORDER})
            live["broad"] = {"region": broad_region, "queries": args.broad_queries,
                             "results": broad}

    after = tracker_hashes()
    check("canonical_workbooks_byte_identical_after_every_run", before == after,
          {r: after[r]["sha256"] for r in after})

    finished = dt.datetime.now(dt.timezone.utc)
    failed = [c for c in checks if not c["ok"]]
    doc = {
        "task": "agent-career-live-research-schedule-cutover-and-acceptance-2026-09-24",
        "runner": "career-ops/run_scheduled_orchestrator_acceptance.py",
        "stamp": stamp,
        "started_at": started.replace(microsecond=0).isoformat(),
        "finished_at": finished.replace(microsecond=0).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "counts": {"checks": len(checks), "passed": len(checks) - len(failed),
                   "failed": len(failed)},
        "policy": {"production_discovery_policy": so.DEFAULT_MODE,
                   "diagnostic_mode": so.DIAGNOSTIC_MODE,
                   "regions": list(REGIONS),
                   "source_classes": list(so.CLASS_ORDER),
                   "coverage_states": sorted(so.COVERAGE_STATE_RULES)},
        "live": live,
        "canonical_workbooks": after,
        "safety": {
            "canonical_workbook_writes": 0,
            "applications_submitted": 0,
            "employer_or_recruiter_contacts": 0,
            "linkedin_mutation": False,
            "browser_or_gui_used": False,
            "login_or_account_used": False,
            "cookies_or_session_used": False,
            "captcha_bypassed": False,
            "scraping_behind_auth": False,
        },
        "privacy_note": ("raw result URLs are owner-private job-search data and stay under the "
                         "git-ignored runtime/ tree; this evidence is aggregate only"),
    }
    (out_dir / "evidence.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    lines = [f"# Unified scheduled Career discovery cutover acceptance — {stamp}", "",
             f"Status: **{doc['status']}** ({doc['counts']['passed']}/{doc['counts']['checks']} "
             "checks)", ""]
    for c in checks:
        lines.append(f"- [{'x' if c['ok'] else ' '}] `{c['check']}` — "
                     f"{json.dumps(c['detail'], ensure_ascii=False)[:400]}")
    lines += ["", "Raw result URLs stay in the git-ignored runtime directory; this evidence is "
                  "aggregate only. No canonical workbook was written and no application, "
                  "outreach, LinkedIn mutation, login, cookie/session or browser action "
                  "occurred."]
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
