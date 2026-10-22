"""The nightly pipeline must honour the owner's regional pause.

Owner request (2026-10-17): "pause the rest of the job search agents for now
only keep running uk job search agent". Paused regions must be skipped by the
nightly scan AND by its tracker writes; resuming one must be an explicit choice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nightly_career_run as ncr


def test_active_regions_is_uk_only():
    assert ncr.ACTIVE_REGIONS == ("uk",)


def test_all_regions_still_declared_so_resume_is_possible():
    assert tuple(ncr.REGION_ORDER) == ("uk", "dubai", "japan", "singapore")


def test_scan_command_targets_active_regions_only():
    cmd = ncr.scan_command(["uk"], "high_recall", 2700, 900, 4, 24, 180, 1, True)
    assert "--regions" in cmd
    after = cmd[cmd.index("--regions") + 1:]
    assert after[:1] == ["uk"]
    for absent in ("dubai", "japan", "singapore"):
        assert absent not in cmd


def test_scan_command_resumes_explicit_regions():
    cmd = ncr.scan_command(["uk", "dubai"], "high_recall", 2700, 900, 4, 24, 180, 1, True)
    after = cmd[cmd.index("--regions") + 1:]
    assert after[:2] == ["uk", "dubai"]


def test_scan_command_adds_live_web_flag_only_when_requested():
    yes = ncr.scan_command(["uk"], "high_recall", 2700, 900, 4, 24, 180, 1, True)
    no = ncr.scan_command(["uk"], "high_recall", 2700, 900, 4, 24, 180, 1, False)
    assert "--require-live-web" in yes
    assert "--require-live-web" not in no


def test_scan_command_is_read_only_run_all():
    cmd = ncr.scan_command(["uk"], "high_recall", 2700, 900, 4, 24, 180, 1, True)
    assert "run-all" in cmd
    assert "--scheduled" in cmd
    assert not any(str(part).startswith("--apply") for part in cmd)


def test_main_defaults_to_active_regions(monkeypatch, tmp_path):
    """The nightly, invoked with no --regions, must process UK only."""
    monkeypatch.setattr(ncr, "NIGHTLY_DIR", tmp_path)
    calls = {}

    def fake_scan(args, regions):
        calls["scan"] = list(regions)
        return {"exit_code": 0, "production_ready": True, "live": True, "region_runs":{r:"fixture-run" for r in regions}}

    def fake_track(args, regions, stamp):
        calls["track"] = list(regions)
        return {}

    monkeypatch.setattr(ncr, "scan", fake_scan)
    monkeypatch.setattr(ncr, "tracker_sync", fake_track)
    monkeypatch.setattr(ncr, "applied_view", lambda args: {"ok": True})
    monkeypatch.setattr(ncr, "acquire_lock", lambda budget: {"acquired": True})

    rc = ncr.main(["--dry-run-trackers"])

    assert rc == 0
    assert calls["scan"] == ["uk"]
    assert calls["track"] == ["uk"]


def test_main_honours_explicit_region_resume(monkeypatch, tmp_path):
    monkeypatch.setattr(ncr, "NIGHTLY_DIR", tmp_path)
    calls = {}

    def fake_scan(args, regions):
        calls["scan"] = list(regions)
        return {"exit_code": 0, "production_ready": True, "live": True, "region_runs":{r:"fixture-run" for r in regions}}

    def fake_track(args, regions, stamp):
        calls["track"] = list(regions)
        return {}

    monkeypatch.setattr(ncr, "scan", fake_scan)
    monkeypatch.setattr(ncr, "tracker_sync", fake_track)
    monkeypatch.setattr(ncr, "applied_view", lambda args: {"ok": True})
    monkeypatch.setattr(ncr, "acquire_lock", lambda budget: {"acquired": True})

    rc = ncr.main(["--dry-run-trackers", "--regions", "uk,dubai"])

    assert rc == 0
    assert calls["scan"] == ["uk", "dubai"]
    assert calls["track"] == ["uk", "dubai"]
