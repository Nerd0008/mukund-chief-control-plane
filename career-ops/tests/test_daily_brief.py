#!/usr/bin/env python3
"""Tests for the Career Daily Brief / Pipeline Prioritizer (roster B23).

Offline and non-destructive. Nothing here writes to a canonical workbook, opens
a network connection, starts a browser, or contacts an employer/recruiter. Every
write in this file goes to pytest's `tmp_path`.

The tests pin the four contracts this worker is judged on:

1. **Empty / partial input behaviour** - a missing input is reported as missing
   and never silently treated as healthy; the brief still builds.
2. **No fabricated priority facts** - every score reports its components,
   weights and UNKNOWN inputs; an unknown input is not imputed.
3. **Idempotency** - re-running over unchanged inputs writes no new bytes and
   produces the same content digest; only the append-only run log grows.
4. **Read-only** - the canonical workbooks are byte-identical before/after and
   the brief records that.

Run:  python -m pytest career-ops/tests/test_daily_brief.py -v
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
CONTROL_PLANE = CAREER_OPS.parent
sys.path.insert(0, str(CAREER_OPS))

import daily_brief as db  # noqa: E402

CFG = db.load_config()
NOW = dt.datetime(2026, 9, 24, 7, 0, tzinfo=dt.timezone.utc)
POLICY = CFG["priority_policy"]


def empty_cfg(tmp_path: Path) -> dict:
    """The real config with every input redirected into an (empty) directory."""
    cfg = json.loads(json.dumps(CFG))
    cfg["inputs"] = {name: str(tmp_path / "absent" / name) for name in cfg["inputs"]}
    cfg["inputs"]["scan_runs_dir"] = str(tmp_path / "absent" / "scan-runs")
    cfg["inputs"]["linkedin_handoff_dir"] = str(tmp_path / "absent" / "handoffs")
    cfg["inputs"]["company_watch_runtime"] = str(tmp_path / "absent" / "company-watch")
    cfg["out_dir"] = str(tmp_path / "briefs")
    # The two config files this brief *loads* rather than hashes must exist for
    # the collectors to run at all; point them at the real ones.
    cfg["inputs"]["application_inbox_config"] = str(CAREER_OPS / "application_inbox_config.json")
    cfg["inputs"]["interview_prep_config"] = str(CAREER_OPS / "interview_prep_config.json")
    cfg["inputs"]["job_intelligence_config"] = str(CAREER_OPS / "job_intelligence_config.json")
    return cfg


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# 1. empty / partial input behaviour
# --------------------------------------------------------------------------- #

def test_empty_inputs_still_builds_and_labels_everything_unknown(tmp_path):
    out, _ = db.run_brief(empty_cfg(tmp_path), now=NOW)

    assert out["ok"] is True
    brief = json.loads(Path(out["brief_path"]).read_text(encoding="utf-8"))
    assert brief["schema_version"] == db.SCHEMA_VERSION
    # no workbooks -> nothing to claim as unchanged
    assert brief["safety"]["canonical_state_unchanged"] is True
    assert brief["safety"]["applications_submitted"] == 0
    assert brief["status"]["read_only"] is True
    assert brief["status"]["degraded"] is True
    # every declared input is reported absent rather than assumed
    absent = [n for n, f in brief["inputs"].items() if f.get("exists") is False]
    assert "regional_state" in absent and "owner_actions_file" in absent
    # nothing is invented: empty sections, zero counts, and unknowns recorded
    assert brief["priorities"] == []
    assert brief["newly_added_jobs"]["counts"]["tracker_rows_in_window"] == 0
    assert brief["deadlines_followups"]["counts"]["deadlines_known"] == 0
    assert brief["owner_actions"]["counts"]["open"] == 0
    assert any(u["area"] == "input" and u["input"] == "regional_state"
               for u in brief["unknowns"])
    assert "no candidates" in out["chief_summary"] or "Priorities" in out["chief_summary"]


def test_partial_inputs_report_the_missing_source_without_inventing_state(tmp_path):
    cfg = empty_cfg(tmp_path)
    # Only the regional state file exists: scan health is available, trackers are not.
    state = tmp_path / "scan-runs"
    state.mkdir(parents=True, exist_ok=True)
    (state / "regional-run-state.json").write_text(json.dumps({
        "schema_version": 1,
        "regions": {"uk": {"last_run_id": "uk-x", "last_run_at": "2026-09-24T06:00:00+00:00",
                           "last_status": "ok", "last_accepted": 0, "last_would_append": 0,
                           "runs": 1}},
    }), encoding="utf-8")
    cfg["inputs"]["regional_state"] = str(state / "regional-run-state.json")
    cfg["inputs"]["scan_runs_dir"] = str(state)

    out, _ = db.run_brief(cfg, now=NOW)
    brief = json.loads(Path(out["brief_path"]).read_text(encoding="utf-8"))

    # schedules + profiles are absent -> scan health is honestly unavailable...
    assert brief["regional_scan_health"]["available"] is False
    assert any(u["area"] == "regional_scan" for u in brief["unknowns"])
    # ...and the missing workbooks are named, one unknown per region
    assert brief["trackers"]["total_rows"] == 0
    assert [u for u in brief["unknowns"] if u["area"] == "input"
            and u["input"] == "canonical_workbooks"] or \
           [u for u in brief["unknowns"] if u["area"] == "input"]


def test_unreadable_json_is_reported_not_raised(tmp_path):
    cfg = empty_cfg(tmp_path)
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    cfg["inputs"]["regional_state"] = str(bad)
    out, _ = db.run_brief(cfg, now=NOW)
    assert out["ok"] is True
    brief = json.loads(Path(out["brief_path"]).read_text(encoding="utf-8"))
    assert brief["inputs"]["regional_state"]["exists"] is True  # it exists, it just will not parse
    assert brief["status"]["ok"] is True


# --------------------------------------------------------------------------- #
# 2. no fabricated priority facts
# --------------------------------------------------------------------------- #

def cand(**kw) -> dict:
    base = {"subject_type": "tracker_row", "region": "uk", "ref": "T1",
            "application_status": "To Review", "deadline_days": None,
            "freshness_days": 1, "owner_flag": False,
            "work_authorisation": {"status": "authorised"}}
    base.update(kw)
    return base


def test_policy_is_declared_and_reported_with_the_brief(tmp_path):
    cfg = empty_cfg(tmp_path)
    brief = db.build_brief(cfg, now=NOW)
    assert brief["policy"]["version"] == POLICY["version"]
    assert brief["policy"]["score_semantics"]["kind"] == "deterministic_policy_output"
    assert brief["policy"]["weights"] == POLICY["weights"]
    assert set(brief["policy"]["weights"]) == {
        "deadline", "stage", "eligibility_certainty", "freshness", "owner_flag"}
    assert "UNKNOWN" in brief["policy"]["score_semantics"]["note"]


def test_unknown_inputs_are_listed_and_never_imputed():
    r = db.score_candidate(cand(deadline_days=None, freshness_days=None,
                                work_authorisation={"status": "UNKNOWN"}), POLICY)
    listed = {u["input"] for u in r["unknown_inputs"]}
    assert {"deadline", "freshness", "eligibility_certainty"} <= listed
    known = {c["input"] for c in r["components"]}
    assert not ({"deadline", "freshness", "eligibility_certainty"} & known)
    # only stage (20) + owner_flag (10) of 100 weight are evidenced
    assert r["coverage_pct"] == 30.0
    # and the score is over the FULL weight, so unknowns lower it rather than vanish
    assert r["score"] == round(100 * (20 * 0.4 + 10 * 0.0) / 100, 1)
    assert r["score"] < db.score_candidate(cand(), POLICY)["score"]


def test_deadline_input_uses_declared_bands_and_overdue_is_flagged():
    soon = db.score_candidate(cand(deadline_days=2), POLICY)
    later = db.score_candidate(cand(deadline_days=20), POLICY)
    assert soon["score"] > later["score"]
    overdue = db.score_candidate(cand(deadline_days=-4), POLICY)
    comp = next(c for c in overdue["components"] if c["input"] == "deadline")
    assert comp["days"] == -4
    assert comp["value"] == POLICY["deadline_overdue_value"]
    assert any("passed" in w for w in overdue["why"])


def test_urgent_deadline_override_fires_only_when_the_class_would_be_lower():
    # near deadline but everything else unknown: the score alone would be P3,
    # so the declared override raises it to the urgent class and says so.
    r = db.score_candidate({"subject_type": "tracker_row", "region": "uk", "ref": "T2",
                            "application_status": None, "deadline_days": 2,
                            "freshness_days": None, "owner_flag": None,
                            "work_authorisation": {}}, POLICY)
    base = db.score_candidate(cand(deadline_days=2), POLICY)
    assert base["score"] > 70 and not base["overrides"]  # already P1 on its own merits
    assert any(o["rule"] == "urgent_deadline" for o in r["overrides"])
    assert r["priority_class"] == POLICY["urgent_min_class"]
    assert r["score"] == round(100 * POLICY["weights"]["deadline"] / 100, 1)


def test_unknown_status_is_not_scored_as_zero_stage():
    r = db.score_candidate(cand(application_status="Assessment Invite"), POLICY)
    assert any(u["input"] == "stage" for u in r["unknown_inputs"])
    assert not any(c["input"] == "stage" for c in r["components"])


def test_candidate_with_no_known_input_at_all_is_labelled_not_scored():
    r = db.score_candidate({"subject_type": "tracker_row", "region": "uk", "ref": "T9",
                            "application_status": None, "deadline_days": None,
                            "freshness_days": None, "owner_flag": None,
                            "work_authorisation": {}}, POLICY)
    assert r["coverage_pct"] == 0.0
    assert r["priority_class"] == POLICY["unscoreable_class"]
    assert any(o["rule"] == "unscoreable" for o in r["overrides"])
    assert len(r["unknown_inputs"]) == len(POLICY["weights"])


def test_owner_action_is_promoted_by_a_declared_rule_only():
    row = db.score_candidate(cand(), POLICY)
    action = db.score_candidate(cand(subject_type="owner_action", region=None,
                                     application_status="owner_action",
                                     work_authorisation={}), POLICY)
    assert action["score"] < row["score"]  # less evidence, lower score - unchanged
    assert any(o["rule"] == "owner_action_min_class" for o in action["overrides"])
    assert action["priority_class"] == POLICY["owner_action_min_class"]


def test_score_components_are_arithmetically_visible():
    r = db.score_candidate(cand(deadline_days=2), POLICY)
    total = sum(c["contribution"] for c in r["components"])
    assert abs(total - r["score"]) < 0.05
    for c in r["components"]:
        assert set(c) >= {"input", "value", "weight", "observed"}


def test_ranking_is_deterministic_and_ties_break_by_declared_order():
    def mk(ref, region="uk"):
        c = {"subject_type": "tracker_row", "region": region, "ref": ref,
             "application_status": "To Review", "deadline_days": None,
             "freshness_days": 1, "owner_flag": False,
             "work_authorisation": {"status": "authorised"}}
        c["priority"] = db.score_candidate(c, POLICY)
        return c

    # identical evidence -> identical score, so the declared tie-breakers decide:
    # subject type, deadline, then region, then reference.
    same_region = sorted([mk("B"), mk("A"), mk("C")],
                         key=lambda c: db.candidate_sort_key(c, POLICY))
    assert [c["ref"] for c in same_region] == ["A", "B", "C"]
    regions = sorted([mk("A", "japan"), mk("A", "uk")],
                     key=lambda c: db.candidate_sort_key(c, POLICY))
    assert [c["region"] for c in regions] == ["japan", "uk"]
    # and the sort is stable under input reordering
    shuffled = sorted([mk("C"), mk("A"), mk("B")],
                      key=lambda c: db.candidate_sort_key(c, POLICY))
    assert [c["ref"] for c in shuffled] == ["A", "B", "C"]


# --------------------------------------------------------------------------- #
# 3. idempotency
# --------------------------------------------------------------------------- #

def test_rerun_over_unchanged_inputs_writes_nothing(tmp_path):
    cfg = empty_cfg(tmp_path)
    first, _ = db.run_brief(cfg, now=NOW)
    before = {p.name: sha(p) for p in Path(cfg["out_dir"]).glob("*")}

    second, res2 = db.run_brief(cfg, now=NOW)

    assert first["content_digest"] == second["content_digest"]
    assert first["input_fingerprint"] == second["input_fingerprint"]
    assert second["idempotent"] is True
    assert res2["writes"] == []
    after = {p.name: sha(p) for p in Path(cfg["out_dir"]).glob("*")}
    # only the append-only run log may differ
    assert {k: v for k, v in before.items() if k != "run-log.jsonl"} == \
           {k: v for k, v in after.items() if k != "run-log.jsonl"}
    runs = [json.loads(l) for l in (Path(cfg["out_dir"]) / "run-log.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert len(runs) == 2 and runs[1]["idempotent"] is True and runs[1]["wrote"] == []


def test_content_digest_ignores_clock_and_delivery_but_not_content(tmp_path):
    cfg = empty_cfg(tmp_path)
    a = db.build_brief(cfg, now=NOW)
    b = db.build_brief(cfg, now=NOW)
    b["generated_at"] = "2099-01-01T00:00:00+00:00"
    b["brief_id"] = "different"
    b["delivery"] = {"channel": "local_file", "mode": "write"}
    assert db.content_digest(a) == db.content_digest(b)
    b["priorities"] = [{"injected": True}]
    assert db.content_digest(a) != db.content_digest(b)


def test_window_is_part_of_the_brief_identity_but_repeating_a_run_is_a_no_op(tmp_path):
    cfg = empty_cfg(tmp_path)
    db.run_brief(cfg, now=NOW)
    # a later logical clock changes the window, which is real content: new brief
    out2, _ = db.run_brief(cfg, now=NOW + dt.timedelta(minutes=30))
    files = sorted(p.name for p in Path(cfg["out_dir"]).glob("brief-*.json"))
    assert len(files) == 2
    # repeating the *same* run writes nothing at all
    out3, res3 = db.run_brief(cfg, now=NOW + dt.timedelta(minutes=30))
    assert out3["content_digest"] == out2["content_digest"]
    assert res3["writes"] == []
    assert sorted(p.name for p in Path(cfg["out_dir"]).glob("brief-*.json")) == files


# --------------------------------------------------------------------------- #
# 4. read-only
# --------------------------------------------------------------------------- #

def test_canonical_workbooks_are_never_modified(tmp_path):
    profiles = json.loads((CAREER_OPS / "regional_profiles.json").read_text(encoding="utf-8"))
    present = {r: Path(rc["tracker"]) for r, rc in profiles["regions"].items()
               if Path(rc["tracker"]).exists()}
    if not present:
        pytest.skip("no canonical workbook on this machine")
    before = {r: sha(p) for r, p in present.items()}

    out, _ = db.run_brief(CFG, now=NOW, out_dir_override=str(tmp_path / "briefs"))

    after = {r: sha(p) for r, p in present.items()}
    assert before == after
    brief = json.loads(Path(out["brief_path"]).read_text(encoding="utf-8"))
    assert brief["safety"]["canonical_state_unchanged"] is True
    assert brief["safety"]["canonical_hashes_before"] == brief["safety"]["canonical_hashes_after"]
    assert out["canonical_state_unchanged"] is True


def test_brief_has_no_submission_or_outreach_path():
    src = (CAREER_OPS / "daily_brief.py").read_text(encoding="utf-8")
    for banned in ("smtplib", "requests", "urllib.request", "http.client", "socket",
                   "subprocess", "webbrowser", "selenium", "playwright"):
        assert banned not in src, f"{banned} must not appear in the brief worker"
    # no workbook write API is reachable from this module
    assert "write_records" not in src
    assert "save(" not in src


def test_delivery_does_not_claim_an_external_channel(tmp_path):
    cfg = empty_cfg(tmp_path)
    out, _ = db.run_brief(cfg, now=NOW)
    assert out["delivery"]["channel"] == "local_file"
    assert out["delivery"]["external_channels"] == []
    assert out["delivery"]["external_channel_health"] == "not_verified"
    assert out["delivery"]["local_write_verified_by_hash"] is True


def test_dry_run_writes_nothing_but_still_reports_the_brief(tmp_path):
    cfg = empty_cfg(tmp_path)
    out, _ = db.run_brief(cfg, now=NOW, dry_run=True)
    assert out["dry_run"] is True
    assert not Path(cfg["out_dir"]).exists() or not list(Path(cfg["out_dir"]).glob("brief-*.json"))
    assert out["brief_id"] and out["chief_summary"]


# --------------------------------------------------------------------------- #
# 5. the real repository state (structure, not specific numbers)
# --------------------------------------------------------------------------- #

def test_live_brief_structure_when_inputs_exist(tmp_path):
    if not (CONTROL_PLANE / "runtime" / "career-ops" / "scan-runs").exists():
        pytest.skip("no runtime scan state on this machine")
    out, _ = db.run_brief(CFG, now=NOW, out_dir_override=str(tmp_path / "briefs"))
    brief = json.loads(Path(out["brief_path"]).read_text(encoding="utf-8"))
    for key in ("regional_scan_health", "trackers", "newly_added_jobs", "duplicates_suppressed",
                "company_watch", "application_status_changes", "interviews_and_followups",
                "deadlines_followups", "owner_actions", "workflow_outputs", "priorities",
                "unknowns", "safety"):
        assert key in brief, key
    assert brief["safety"]["canonical_state_unchanged"] is True
    # regional scan health must name a health value per region, never a bare number
    for region, entry in (brief["regional_scan_health"].get("regions") or {}).items():
        assert entry["health"] in ("ok", "stale", "unknown") or entry["health"].startswith("degraded")
    # every priority item carries its components and unknowns
    for item in brief["priorities"]:
        assert item["priority"]["score_kind"] == "deterministic_policy_output"
        assert "coverage_pct" in item["priority"]
        assert isinstance(item["priority"]["unknown_inputs"], list)
    # the Chief summary stays short and plain
    assert len(out["chief_summary"].splitlines()) <= CFG["brief"]["max_summary_lines"]


def test_owner_actions_are_parsed_without_inventing_state():
    cfg = dict(CFG)
    doc = db.collect_owner_actions(cfg)
    if not doc["available"]:
        pytest.skip("owner-action file not present")
    assert doc["items"], "the owner-action file has items"
    for it in doc["items"]:
        # open is tri-state: True / False / None(no readable status) - never guessed
        assert it["open"] in (True, False, None)
        if it["open"] is None:
            assert it["status"] is None
