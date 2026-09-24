#!/usr/bin/env python3
"""Tests for the shared regional job-search worker (UK / Dubai / Japan / Singapore).

Offline and non-destructive: no test performs a network scan, none writes to a
canonical workbook, and nothing submits an application or contacts an employer.
Synthetic fixtures carry the reserved `.invalid` TLD and are labelled
"NOT A REAL VACANCY".

Run:  python -m pytest career-ops/tests/test_regional_job_search.py -v
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

CAREER_OPS = Path(__file__).resolve().parents[1]
CONTROL_PLANE = CAREER_OPS.parent
sys.path.insert(0, str(CAREER_OPS))

import career_ops_cli as cli  # noqa: E402
import regional_job_search as rjs  # noqa: E402
import tracker_writer as tw  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "regional"
PROFILES = tw.load_profiles()
POLICY = rjs.load_policy()
SCHEDULES = rjs.load_schedules()
REGIONS = ("uk", "dubai", "japan", "singapore")


def h(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_cli(argv, fn_name="main"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = getattr(rjs, fn_name)(argv)
    return rc, json.loads(buf.getvalue())


# --------------------------------------------------------------------------- #
# policy / provenance
# --------------------------------------------------------------------------- #

def test_non_uk_regions_mark_work_authorisation_unknown():
    for region in ("dubai", "japan", "singapore"):
        wa = rjs.region_policy(region, POLICY)["work_authorisation"]
        assert wa["status"] == "UNKNOWN", region
        assert wa["current_permission"] is None
        assert "authorized_in" in wa["basis"] or "no owner-stated" in wa["basis"]
        assert wa["tracker_visa_pathway"], "an UNKNOWN region must still state its tracker default"


def test_uk_work_authorisation_is_sourced_from_the_owner_profile():
    wa = rjs.region_policy("uk", POLICY)["work_authorisation"]
    assert wa["status"] == "authorised"
    assert "profile.yml" in wa["basis"]
    assert "23 Dec 2027" in wa["basis"]


def test_title_policy_matches_the_owner_install_file_verbatim():
    live = rjs.owner_title_filter(PROFILES)
    assert live, "the owner's portals.yml title_filter must be readable"
    assert live == {"positive": POLICY["title_policy"]["positive"],
                    "negative": POLICY["title_policy"]["negative"]}


def test_every_lane_title_filter_matches_the_owner_install_file():
    live = rjs.owner_title_filter(PROFILES)
    for region in REGIONS:
        env = SCHEDULES["regions"][region]["career_ops_env"]
        path = Path(env["CAREER_OPS_PORTALS"])
        if not path.is_absolute():
            path = Path(SCHEDULES["career_ops_root"]) / env["CAREER_OPS_PORTALS"]
        lane = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert lane["title_filter"] == live, f"{region} lane title_filter drifted from the owner's file"


def test_lane_location_scope_matches_the_declared_policy():
    for region in REGIONS:
        declared = rjs.location_scope_comparable(rjs.region_policy(region, POLICY)["location_scope"])
        configured = rjs.location_scope_comparable(rjs.lane_scope(region, SCHEDULES["regions"][region]))
        assert configured, f"{region}: no location scope configured in the lane"
        assert configured == declared, f"{region}: lane scope drifted from regional_policy.json"


def test_uk_location_scope_matches_the_owner_install_file():
    assert rjs.location_scope_comparable(rjs.owner_location_filter(PROFILES)) == \
        rjs.location_scope_comparable(rjs.region_policy("uk", POLICY)["location_scope"])


def test_policy_command_reports_no_drift():
    rc, out = run_cli(["policy"])
    assert rc == 0
    assert out["drift"]["title_policy_matches_owner_file"] is True
    assert out["drift"]["uk_location_scope_matches_owner_file"] is True
    assert set(out["regions"]) == set(REGIONS)


# --------------------------------------------------------------------------- #
# lanes / schedules
# --------------------------------------------------------------------------- #

def test_all_four_lanes_are_ready_and_scoped():
    rc, out = run_cli(["lanes"])
    assert rc == 0
    assert set(out["regions"]) == set(REGIONS)
    for region, info in out["regions"].items():
        assert info["ready"] is True, f"{region} lane not ready: {info['missing']}"
        assert info["missing"] == []
        assert info["location_scope_configured"] is True
        assert "dry-run" in info["mode"]


def test_schedule_registry_paths_exist_and_are_unique():
    times, tasks = set(), set()
    for region, spec in SCHEDULES["regions"].items():
        assert spec["ready"] is True
        assert spec["task_name"] not in tasks
        tasks.add(spec["task_name"])
        assert spec["time"] not in times, "scheduled runs must be staggered"
        times.add(spec["time"])
        for key, value in spec["career_ops_env"].items():
            path = Path(value)
            if not path.is_absolute():
                path = Path(SCHEDULES["career_ops_root"]) / value
            assert path.exists(), f"{region}.{key} -> {path} does not exist"
        lane_dir = Path(spec["lane_dir"])
        if spec["lane_kind"] == "control-plane-lane":
            assert lane_dir.exists() and str(lane_dir).startswith(str(CONTROL_PLANE))


def test_control_plane_lanes_do_not_live_inside_the_owner_install():
    install = Path(SCHEDULES["career_ops_root"]).resolve()
    for region in ("dubai", "japan", "singapore"):
        env = SCHEDULES["regions"][region]["career_ops_env"]
        for value in env.values():
            assert not Path(value).resolve().is_relative_to(install), value


def test_singapore_lane_has_real_provider_coverage():
    lane = yaml.safe_load((CONTROL_PLANE / "career-ops/lanes/singapore/portals.yml").read_text(encoding="utf-8"))
    providers = {b["provider"] for b in lane["job_boards"]}
    assert {"mycareersfuture", "glints", "jobstreet"} <= providers


# --------------------------------------------------------------------------- #
# scan parsing
# --------------------------------------------------------------------------- #

def test_parse_scan_offers_reads_the_dry_run_block():
    rec = json.loads((FIXTURES / "fixture-scan-dubai.json").read_text(encoding="utf-8"))
    offers = rjs.parse_scan_offers(rec["stdout_tail"])
    assert len(offers) == 1
    o = offers[0]
    assert o["title"].startswith("Cybersecurity Intern")
    assert o["location"] == "Dubai, UAE"
    assert o["trust_score"] == 90
    assert o["url"] is None, "scan.mjs dry-run output never carries a posting URL"
    c = rjs.parse_scan_counters(rec["stdout_tail"])
    assert c["jobs_found"] == 1234 and c["filtered_title"] == 1200 and c["new_offers_added"] == 1


def test_a_real_committed_uk_run_health_still_parses_when_present():
    runs = sorted((CONTROL_PLANE / "runtime/career-ops/scan-runs").glob("scan-uk-*.json"))
    if not runs:
        pytest.skip("no committed UK scan run-health file yet")
    data = json.loads(runs[-1].read_text(encoding="utf-8"))
    counters = rjs.parse_scan_counters(data.get("stdout_tail") or "")
    assert counters["jobs_found"] is not None
    offers = rjs.parse_scan_offers(data.get("stdout_tail") or "")
    assert all(o["url"] is None for o in offers)


def test_pipeline_entry_parser_reads_url_bearing_candidates(tmp_path):
    p = tmp_path / "pipeline.md"
    p.write_text("# Pipeline\n\n## Pending\n\n"
                 "- [ ] https://regional-fixture.invalid/ae/one | Fixture Co | Cyber Intern | Dubai, UAE\n\n"
                 "## Processed\n", encoding="utf-8")
    entries = rjs.parse_pipeline_entries(p)
    assert len(entries) == 1
    assert entries[0]["company"] == "Fixture Co"
    assert entries[0]["location"] == "Dubai, UAE"


# --------------------------------------------------------------------------- #
# eligibility (the shared filter)
# --------------------------------------------------------------------------- #

def _eval(region, rec):
    return rjs.evaluate_record(region, rec, POLICY, rjs.owner_title_filter(PROFILES),
                               rjs.lane_scope(region, SCHEDULES["regions"][region]))


def test_eligibility_accepts_a_region_matching_internship():
    v = _eval("dubai", {"company": "X", "title": "Cybersecurity Intern",
                        "location": "Dubai, UAE", "url": "https://regional-fixture.invalid/a"})
    assert v["decision"] == "accepted"
    assert v["work_authorisation"]["status"] == "UNKNOWN"
    assert any("UNKNOWN" in f for f in v["flags"])


@pytest.mark.parametrize("region,bad_location", [
    ("dubai", "London, United Kingdom"),
    ("uk", "Dubai, United Arab Emirates"),
    ("japan", "Singapore"),
    ("singapore", "Tokyo, Japan"),
])
def test_eligibility_rejects_the_wrong_region(region, bad_location):
    v = _eval(region, {"company": "X", "title": "Cybersecurity Intern",
                       "location": bad_location, "url": "https://regional-fixture.invalid/x"})
    assert v["decision"] == "rejected"
    assert any("location" in r for r in v["reasons"])


def test_eligibility_rejects_senior_titles_and_clearance_requirements():
    senior = _eval("uk", {"company": "X", "title": "Senior Security Manager",
                          "location": "London, UK", "url": "https://regional-fixture.invalid/s"})
    assert senior["decision"] == "rejected"
    cleared = _eval("uk", {"company": "X", "title": "Cybersecurity Intern", "location": "London, UK",
                           "url": "https://regional-fixture.invalid/c",
                           "summary": "Must hold DV clearance"})
    assert cleared["decision"] == "rejected"
    assert any("clearance" in r for r in cleared["reasons"])


def test_eligibility_rejects_a_bare_remote_posting_outside_its_region():
    """A 'Remote'-titled posting located in another country is not region-eligible.

    Measured 2026-09-24: the scanner's remote-title rescue let
    `Personalized Internet Assessor - Remote / USA` and `Anywhere in India`
    through the Dubai and Japan lanes, so the regional gate requires an explicit
    region match while the UK gate keeps the scanner's own behaviour.
    """
    remote_us = {"company": "X", "title": "Cybersecurity Intern - Remote",
                 "location": "USA", "url": "https://regional-fixture.invalid/us"}
    assert _eval("dubai", remote_us)["decision"] == "rejected"
    assert _eval("japan", {**remote_us, "location": "Anywhere in India"})["decision"] == "rejected"
    assert _eval("singapore", {**remote_us, "location": "Remote"})["decision"] == "rejected"
    # The UK keeps the scanner's own rescue, because the UK lane's own config is
    # the owner's and its location scope is the one used in production.
    assert _eval("uk", {**remote_us, "location": "Remote"})["decision"] == "accepted"


def test_eligibility_rejects_a_record_with_a_blank_location_outside_the_uk():
    noloc = {"company": "X", "title": "Cybersecurity Intern", "location": "",
             "url": "https://regional-fixture.invalid/noloc"}
    assert _eval("dubai", noloc)["decision"] == "rejected"
    assert any("region" in r for r in _eval("dubai", noloc)["reasons"])


def test_eligibility_rejects_a_record_without_a_url():
    v = _eval("japan", {"company": "X", "title": "Cybersecurity Intern", "location": "Tokyo, Japan", "url": ""})
    assert v["decision"] == "rejected"
    assert any("URL" in r for r in v["reasons"])


def test_eligibility_command_is_read_only_and_never_sets_application_state():
    rc, out = run_cli(["eligibility", "--region", "dubai",
                       "--manifest", str(FIXTURES / "fixture-candidates-dubai.json")])
    assert rc == 0
    assert out["writes_performed"] is False
    assert out["counts"]["input"] == 5
    decisions = {d["title"] + d["company"]: d for d in out["decisions"]}
    assert any(d["decision"] == "accepted" for d in out["decisions"])
    for d in out["decisions"]:
        assert "application_status" not in d


# --------------------------------------------------------------------------- #
# run: idempotency, dry-run safety, manifest handoff
# --------------------------------------------------------------------------- #

def _run(tmp_path, region="dubai", extra=()):
    argv = ["--state-file", str(tmp_path / "state.json"),
            "run", "--region", region,
            "--records", str(FIXTURES / "fixture-candidates-dubai.json"),
            "--fake-scan", str(FIXTURES / "fixture-scan-dubai.json"),
            "--record", str(tmp_path / "runs"),
            "--scheduled"]
    if extra:
        argv += list(extra)
    return run_cli(argv)


def test_run_is_dry_run_and_never_touches_the_canonical_workbook(tmp_path):
    before = {r: h(Path(PROFILES["regions"][r]["tracker"])) for r in REGIONS}
    rc, out = _run(tmp_path)
    assert out["status"] == "ok"
    assert out["dry_run"] is True
    assert out["canonical_workbook_written"] is False
    assert out["dedupe"]["applied"] is False
    assert out["writes"]["canonical_workbook"] is False
    assert before == {r: h(Path(PROFILES["regions"][r]["tracker"])) for r in REGIONS}


def test_run_rejects_wrong_region_senior_clearance_and_urlless_candidates(tmp_path):
    rc, out = _run(tmp_path)
    assert out["eligibility"]["input"] == 5
    assert out["eligibility"]["accepted"] == 1
    assert out["eligibility"]["rejected"] == 4
    assert out["candidates"]["scan_offers_without_url"] == 1
    assert out["would_append"] == 1
    assert Path(out["run_health_file"]).exists()


def test_a_repeated_run_cannot_duplicate_rows(tmp_path):
    rc1, first = _run(tmp_path)
    assert first["idempotency"]["replay_of_previous_run"] is False
    assert first["would_append"] == 1
    rc2, second = _run(tmp_path, extra=["--manifest-out", str(tmp_path / "replay-manifest.json")])
    assert second["idempotency"]["replay_of_previous_run"] is True
    assert second["idempotency"]["run_key"] == first["idempotency"]["run_key"]
    assert second["eligibility"]["accepted"] == 0
    assert second["would_append"] == 0
    assert second["dedupe"]["counts"]["appended"] == 0
    replay = json.loads((tmp_path / "replay-manifest.json").read_text(encoding="utf-8"))
    assert replay["counts"]["would_append"] == 0
    assert replay["records"] == []


def test_run_refuses_when_the_lane_is_missing(tmp_path, monkeypatch):
    sched = json.loads(json.dumps(SCHEDULES))
    sched["regions"]["dubai"]["career_ops_env"]["CAREER_OPS_PORTALS"] = str(tmp_path / "nope.yml")
    fake_dir = tmp_path / "career-ops"
    fake_dir.mkdir()
    (fake_dir / "regional_schedules.json").write_text(json.dumps(sched), encoding="utf-8")
    monkeypatch.setattr(rjs, "SCHEDULES_PATH", fake_dir / "regional_schedules.json")
    monkeypatch.setattr(cli, "CAREER_OPS_DIR", fake_dir)

    rc, out = run_cli(["--state-file", str(tmp_path / "state.json"), "run", "--region", "dubai",
                       "--records", str(FIXTURES / "fixture-candidates-dubai.json"),
                       "--record", str(tmp_path / "runs"), "--scheduled"])
    assert out["status"] == "refused"
    assert out["scan"]["refused"] is True
    assert out["lane_ready"] is False
    # Fail closed: without a resolvable region scope nothing can be accepted.
    assert out["eligibility"]["accepted"] == 0
    assert out["would_append"] == 0


def test_manifest_is_consumable_by_the_shared_tracker_writer_without_applying(tmp_path):
    manifest = tmp_path / "manifest-dubai.json"
    rc, out = _run(tmp_path, extra=["--manifest-out", str(manifest)])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["counts"]["would_append"] == 1
    assert len(data["records"]) == 1
    rec = data["records"][0]
    assert rec["url"].startswith("https://regional-fixture.invalid/")
    assert rec["visa_pathway"] == "Visa unknown", "an UNKNOWN region must record the tracker default"
    assert "application_status" not in rec, "a manifest must never carry application state"

    before = h(Path(PROFILES["regions"]["dubai"]["tracker"]))
    dry = tw.write_records(PROFILES, "dubai", data["records"], apply=False)
    assert dry["applied"] is False
    assert dry["counts"]["appended"] == 1
    assert dry["counts"]["duplicates"] == 0
    assert h(Path(PROFILES["regions"]["dubai"]["tracker"])) == before


def test_run_all_covers_every_region_offline(tmp_path):
    rc, out = run_cli(["--state-file", str(tmp_path / "state.json"), "run-all",
                       "--records", str(FIXTURES / "fixture-candidates-dubai.json"),
                       "--fake-scan", str(FIXTURES / "fixture-scan-dubai.json"),
                       "--record", str(tmp_path / "runs"), "--scheduled"])
    assert set(out["regions"]) == set(REGIONS)
    for region, info in out["regions"].items():
        assert info["status"] == "ok", region
        assert info["run_health_file"]


def test_status_reports_run_health_per_region(tmp_path):
    _run(tmp_path)
    rc, out = run_cli(["--state-file", str(tmp_path / "state.json"), "status"])
    assert rc == 0
    assert set(out["regions"]) == set(REGIONS)
    st = out["regions"]["dubai"]
    assert st["last_status"] == "ok"
    assert st["runs_recorded"] == 1
    assert st["work_authorisation"] == "UNKNOWN"
    assert out["regions"]["uk"]["work_authorisation"] == "authorised"


def test_records_carry_provenance_and_never_owner_application_state():
    rp = rjs.region_policy("singapore", POLICY)
    rec = rjs.build_record("singapore", {"company": "Fixture", "title": "Cybersecurity Intern",
                                         "location": "Singapore",
                                         "url": "https://regional-fixture.invalid/sg/1"},
                           POLICY, "singapore-test", {"jobs_found": 1})
    assert rec["visa_pathway"] == rp["work_authorisation"]["tracker_visa_pathway"]
    assert "singapore-test" in rec["source"]
    assert "UNKNOWN" in rec["main_gap"]
    for forbidden in ("application_status", "selected", "cv_status", "cover_letter_status",
                      "date_applied", "priority", "notes"):
        assert forbidden not in rec, f"{forbidden} is owner state and must never be set by a worker"
