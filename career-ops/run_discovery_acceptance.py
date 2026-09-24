#!/usr/bin/env python3
"""Acceptance run for the high-recall multi-stage discovery pipeline (B25).

What this proves (offline; no live source, no provider call, no tracker write)
----------------------------------------------------------------------------
1. title-policy regression fixtures: every title the owner's intern-only rule
   wrongly rejected is accepted by the high-recall default, and every negative
   fixture (senior / non-cyber / wrong discipline) is still rejected;
2. the intern-only narrow mode still reproduces the owner's original rule
   exactly, so the strict policy remains available as an option;
3. the semantic contract rejects an invented fact (a year count or clearance
   token that is not in the source record) and marks missing-JD uncertainty;
4. the escalation budget is a hard cap: a larger ambiguous pool cannot spend
   more Codex calls than the budget;
5. a full funnel run over the synthetic fixture set produces every declared
   counter, attributes every rejection to a reason, and names the first zero;
6. ``compare-modes`` reports the recall delta between the old strict policy and
   the new pipeline over the SAME candidate set, without writing a canonical
   workbook, a manifest or a tracker probe;
7. the four canonical workbooks are byte-identical before and after this run;
8. (unified surfaces, 2026-09-24 successor) the recruiter/intermediary watch
   (B11) and the LinkedIn read-only job-discovery intake (B19) normalise into the
   same candidate schema and run the same funnel, the same vacancy discovered by
   several surfaces collapses to ONE canonical candidate with its provenance
   preserved, and every source carries its own counters and rejection reasons.

Everything runs against ``career-ops/tests/fixtures/discovery/`` (invented
titles, reserved ``.invalid`` URLs). No application, message, employer or agency
contact, browser, account/session or scrape action happens anywhere in this
runner.

Usage:
  python career-ops/run_discovery_acceptance.py [--out-dir DIR] [--json]
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

import classifiers  # noqa: E402
import pipeline  # noqa: E402
import tracker_writer as tw  # noqa: E402
from semantic_contract import build_classification, candidate_id  # noqa: E402
from title_policy import MODE_HIGH_RECALL, MODE_INTERN_ONLY, title_decision  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures" / "discovery"
TITLE_FIXTURES = FIXTURES / "title-fixtures.json"
CANDIDATES = FIXTURES / "candidates-synthetic.json"
REGIONAL_OVERLAP = FIXTURES / "regional-overlap.json"
RECRUITER_OVERLAP = FIXTURES / "recruiter-watch-overlap.json"
LINKEDIN_OVERLAP = FIXTURES / "linkedin-overlap.json"
PROFILES = tw.load_profiles()
REGIONS = ("uk", "dubai", "japan", "singapore")

#: titles the owner's intern-only policy rejected and the new default must accept
RECALL_TITLES = ("Graduate Cyber Security Analyst", "Junior Security Analyst", "SOC Analyst L1",
                 "Information Security Analyst", "Junior GRC Analyst", "Cyber Risk Analyst",
                 "IAM Analyst", "Technology Risk Graduate")
#: titles that must never pass
NEGATIVE_TITLES = ("Senior Security Manager", "Principal Security Architect",
                   "Physical Security Guard", "Security Sales Director")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tracker_hashes() -> dict:
    out = {}
    for region in REGIONS:
        p = Path(tw.region_config(PROFILES, region)["tracker"])
        out[region] = {"path": str(p), "sha256": sha256_file(p) if p.exists() else None}
    return out


def run_funnel_cli(argv: list) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        pipeline.main(argv)
    return json.loads(buf.getvalue())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="High-recall discovery pipeline acceptance (B25)")
    ap.add_argument("--out-dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    started = dt.datetime.now(dt.timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else (
        CONTROL_PLANE / "audits" / "evidence" / f"{run_id}-career-high-recall-discovery-acceptance")
    out_dir.mkdir(parents=True, exist_ok=True)

    checks: list = []

    def check(name: str, ok: bool, detail) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    before = tracker_hashes()

    # 1. title-policy fixtures -------------------------------------------------- #
    selftest = pipeline.selftest(TITLE_FIXTURES)
    check("title_policy_fixtures", selftest["ok"],
          f"{selftest['counts']['passed']}/{selftest['counts']['total']} fixtures matched")
    check("recall_titles_accepted_by_default",
          all(title_decision(t, MODE_HIGH_RECALL)["decision"] == "pass" for t in RECALL_TITLES),
          list(RECALL_TITLES))
    check("negative_titles_still_rejected",
          all(title_decision(t, MODE_HIGH_RECALL)["decision"] == "reject" for t in NEGATIVE_TITLES),
          list(NEGATIVE_TITLES))

    # 2. narrow mode preserved -------------------------------------------------- #
    narrow = {t: title_decision(t, MODE_INTERN_ONLY)["decision"] for t in RECALL_TITLES}
    check("intern_only_mode_preserved",
          all(v == "reject" for v in narrow.values())
          and title_decision("Cyber Security Intern", MODE_INTERN_ONLY)["decision"] == "pass",
          narrow)

    # 3. semantic contract guard ------------------------------------------------ #
    rec = {"company": "Testco (NOT A REAL VACANCY)", "title": "SOC Analyst L1",
           "location": "London, United Kingdom", "url": "https://testco.invalid/1"}
    invented = build_classification(rec, primary_label="strong_entry_level_match", confidence=0.9,
                                    reasons=["requires 5 years and DV clearance"], uncertainty=[],
                                    provider="stub", model="stub")
    honest = build_classification(rec, primary_label="plausible_entry_level", confidence=0.5,
                                  reasons=["the title names a SOC analyst role"], uncertainty=[],
                                  provider="stub", model="stub")
    check("contract_guard_rejects_invented_fact", invented["valid"] is False,
          invented["guard"]["violations"])
    check("contract_marks_missing_jd", honest["valid"] is True and honest["jd_available"] is False
          and any("NOT semantic JD analysis" in u for u in honest["uncertainty"]),
          honest["classification_basis"])

    # 4. bounded escalation ----------------------------------------------------- #
    recs = [dict(rec, title=f"SOC Analyst L1 (probe {i})",
                 url=f"https://testco.invalid/{i}") for i in range(6)]
    classes = {}
    for r in recs:
        cls = build_classification(r, primary_label="ambiguous_review", confidence=0.2,
                                   reasons=["rule"], uncertainty=[], provider="deepseek",
                                   model="stub", classifier="deepseek_bulk")
        cls["escalation_eligible"] = True
        classes[candidate_id(r)] = cls
    plan = classifiers.select_escalations(recs, classes, budget=2)
    check("codex_escalation_is_budgeted",
          len(plan["selected"]) == 2 and len(plan["dropped_due_to_budget"]) == 4,
          {"selected": len(plan["selected"]),
           "dropped": len(plan["dropped_due_to_budget"])})

    # 5. full funnel run over the fixtures -------------------------------------- #
    with tempfile.TemporaryDirectory() as tmp:
        run_doc = run_funnel_cli(["run", "--region", "uk", "--records", str(CANDIDATES),
                                  "--semantic", "off", "--codex", "off",
                                  "--out-dir", tmp])
        compare_doc = run_funnel_cli(["compare-modes", "--region", "uk",
                                      "--records", str(CANDIDATES)])
    counts = run_doc["funnel"]["counts"]
    declared = ("discovered_raw", "after_hard_negative_prefilter", "semantically_reviewed",
                "deepseek_accept", "codex_escalated", "codex_accept",
                "deterministic_eligibility_pass", "duplicates_removed", "tracker_candidates")
    check("funnel_exposes_every_declared_counter", all(k in counts for k in declared),
          {k: counts[k] for k in declared})
    check("every_rejection_has_a_reason",
          all("usable application URL" in r or "region" in r or "clearance" in r
              or "tier" in r.lower() or "cyber" in r or "early-career" in r or "location" in r
              for r in run_doc["funnel"]["rejections_by_reason"]),
          list(run_doc["funnel"]["rejections_by_reason"])[:4])
    check("zero_attribution_present",
          bool(run_doc["funnel"]["zero_attribution"]["reason"])
          or run_doc["funnel"]["zero_attribution"]["first_zero_stage"] is None,
          run_doc["funnel"]["zero_attribution"])
    check("funnel_run_wrote_no_canonical_workbook",
          run_doc["safety"]["canonical_workbook_written"] is False,
          run_doc["safety"])

    # 6. compare modes ---------------------------------------------------------- #
    delta = compare_doc["recall_delta"]
    check("compare_modes_reports_recall_delta",
          delta["title_pass_delta"] > 0 and compare_doc["modes"][MODE_INTERN_ONLY]["title_pass"] == 0,
          {"intern_only": compare_doc["modes"][MODE_INTERN_ONLY],
           "high_recall": compare_doc["modes"][MODE_HIGH_RECALL],
           "delta": {k: v for k, v in delta.items() if not k.endswith("titles")},
           "regained": len(delta["recall_regained_titles"]),
           "lost": len(delta["recall_lost_titles"])})
    check("compare_modes_wrote_nothing",
          not any(v for v in compare_doc["safety"].values()),
          compare_doc["safety"])

    # 7. canonical workbooks untouched ------------------------------------------ #
    after = tracker_hashes()
    check("canonical_workbooks_byte_identical", before == after,
          {r: after[r]["sha256"] for r in after})

    # 8. unified read-only discovery surfaces (B11 + B19 + provenance) ---------- #
    recruiter_block = pipeline.collect_from_recruiter_watch(RECRUITER_OVERLAP, "uk")
    linkedin_block = pipeline.collect_from_linkedin(LINKEDIN_OVERLAP, "uk")
    check("recruiter_watch_normalises_into_the_candidate_schema",
          len(recruiter_block["candidates"]) == 2
          and all(c["_collection_source"] == pipeline.SOURCE_RECRUITER_WATCH
                  for c in recruiter_block["candidates"]),
          {k: v for k, v in recruiter_block["coverage"].items()
           if k in ("findings_total", "findings_entering_this_funnel",
                    "findings_excluded_before_the_funnel")})
    check("recruiter_watch_exclusions_are_attributable",
          recruiter_block["coverage"]["findings_excluded_before_the_funnel"] == {
              "recruiter_watch_decision:duplicate": 1, "routed_other_region:dubai": 1},
          recruiter_block["coverage"]["findings_excluded_before_the_funnel"])
    check("linkedin_export_normalises_job_signals_only",
          len(linkedin_block["candidates"]) == 2
          and linkedin_block["coverage"]["company_signals_not_job_candidates"] == 1
          and all(c["_collection_source"] == pipeline.SOURCE_LINKEDIN_EXPORT
                  for c in linkedin_block["candidates"]),
          {k: v for k, v in linkedin_block["coverage"].items()
           if k in ("job_signals_entering_this_funnel",
                    "company_signals_not_job_candidates", "file_sha256")})

    with tempfile.TemporaryDirectory() as tmp:
        unified_doc = run_funnel_cli(["run", "--region", "uk",
                                      "--records", str(REGIONAL_OVERLAP),
                                      "--recruiter-watch", str(RECRUITER_OVERLAP),
                                      "--linkedin", str(LINKEDIN_OVERLAP),
                                      "--semantic", "off", "--codex", "off",
                                      "--out-dir", tmp])
    ucounts = unified_doc["funnel"]["counts"]
    check("multi_source_run_counts_every_surface",
          ucounts["discovered_raw"] == 6 and ucounts["canonical_candidates"] == 4
          and ucounts["cross_source_duplicates_removed"] == 2,
          {k: ucounts[k] for k in ("discovered_raw", "canonical_candidates",
                                   "cross_source_duplicates_removed")})
    shared = [c for c in unified_doc["canonical_candidates"] if c["duplicate_discoveries"]]
    expected_sources = {pipeline.SOURCE_EXPLICIT, pipeline.SOURCE_RECRUITER_WATCH,
                        pipeline.SOURCE_LINKEDIN_EXPORT}
    check("same_vacancy_dedupes_to_one_canonical_candidate_with_provenance",
          len(shared) == 1 and set(shared[0]["sources"]) == expected_sources
          and {p["collection_source"] for p in shared[0]["provenance"]} == expected_sources,
          {"shared_candidates": len(shared),
           "sources": shared[0]["sources"] if shared else None,
           "provenance_entries": len(shared[0]["provenance"]) if shared else 0})
    check("every_source_has_its_own_funnel_counters_and_zero_attribution",
          all(unified_doc["funnel"]["by_source"].get(s, {}).get("counts", {}).get("discovered")
              == 2 for s in expected_sources)
          and all("zero_attribution" in unified_doc["funnel"]["by_source"][s]
                  and "rejections_by_reason" in unified_doc["funnel"]["by_source"][s]
                  for s in expected_sources),
          {s: unified_doc["funnel"]["by_source"][s]["counts"] for s in expected_sources})
    check("unified_run_wrote_no_canonical_workbook",
          unified_doc["safety"]["canonical_workbook_written"] is False
          and unified_doc["dedupe"]["applied"] is False,
          unified_doc["safety"])

    after_unified = tracker_hashes()
    check("canonical_workbooks_still_byte_identical_after_unified_run",
          before == after_unified, {r: after_unified[r]["sha256"] for r in after_unified})

    finished = dt.datetime.now(dt.timezone.utc)
    failed = [c for c in checks if not c["ok"]]
    doc = {
        "task": "agent-career-high-recall-semantic-discovery-2026-09-24",
        "task_successor": "agent-career-unified-discovery-surfaces-followup-2026-09-24",
        "runner": "career-ops/run_discovery_acceptance.py",
        "run_id": run_id,
        "started_at": started.replace(microsecond=0).isoformat(),
        "finished_at": finished.replace(microsecond=0).isoformat(),
        "duration_s": round((finished - started).total_seconds(), 1),
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "counts": {"checks": len(checks), "passed": len(checks) - len(failed),
                   "failed": len(failed)},
        "funnel_counts": counts,
        "unified_discovery_surfaces": {
            "source_registry": dict(pipeline.SOURCE_REGISTRY),
            "recruiter_watch_findings": recruiter_block["coverage"]["findings_total"],
            "recruiter_watch_candidates": len(recruiter_block["candidates"]),
            "linkedin_job_signals": linkedin_block["coverage"][
                "job_signals_entering_this_funnel"],
            "unified_run_counts": {k: ucounts[k] for k in
                                   ("discovered_raw", "canonical_candidates",
                                    "cross_source_duplicates_removed",
                                    "after_hard_negative_prefilter",
                                    "deterministic_eligibility_pass",
                                    "tracker_candidates")},
            "canonical_candidate_sources": shared[0]["sources"] if shared else [],
            "per_source": {s: unified_doc["funnel"]["by_source"][s]["counts"]
                           for s in expected_sources},
        },
        "compare_modes": {
            "intern_only": compare_doc["modes"][MODE_INTERN_ONLY],
            "high_recall": compare_doc["modes"][MODE_HIGH_RECALL],
            "title_pass_delta": delta["title_pass_delta"],
            "tracker_candidate_delta": delta["tracker_candidate_delta"],
        },
        "canonical_workbooks": after,
        "safety": {
            "canonical_workbook_writes": 0,
            "applications_submitted": 0,
            "employer_or_recruiter_contacts": 0,
            "agency_or_intermediary_contacts": 0,
            "browser_or_gui_used": False,
            "account_or_session_used": False,
            "scraping_performed": False,
            "live_source_scanned": False,
            "live_provider_called": False,
            "fixtures_only": True,
        },
        "privacy_note": ("all candidates in this run come from the synthetic fixture set "
                         "(invented titles, reserved .invalid URLs); no real posting, company "
                         "or application URL appears in this evidence"),
    }
    (out_dir / "evidence.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    lines = [f"# High-recall discovery pipeline acceptance — {run_id}", "",
             f"Status: **{doc['status']}** ({doc['counts']['passed']}/{doc['counts']['checks']} checks)",
             ""]
    for c in checks:
        lines.append(f"- [{'x' if c['ok'] else ' '}] `{c['check']}` — "
                     f"{json.dumps(c['detail'], ensure_ascii=False)[:400]}")
    lines += ["", "No live source was scanned, no provider was called, no canonical workbook was "
                  "written, and no application/outreach/browser action occurred."]
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
