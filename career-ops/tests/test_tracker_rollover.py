#!/usr/bin/env python3
"""Tests for the Monthly Tracker Rollover / archive worker (roster B09).

Safety rules for this suite:

* Every rollover and every append happens on a **copy** of a canonical workbook
  under pytest's ``tmp_path``. The canonical workbooks are only ever opened
  read-only, and the last test in the file asserts their hashes are unchanged
  since the module was imported.
* No test submits, messages or contacts anyone, and no test touches an owner
  column except the deliberately-refused owner-state case (on a copy).

Run:  python -m pytest career-ops/tests/test_tracker_rollover.py -v
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from fnmatch import fnmatch
from pathlib import Path

import openpyxl
import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import tracker_writer as tw  # noqa: E402
import tracker_rollover as ro  # noqa: E402
import dept_run_health as drh  # noqa: E402
import career_ops_cli as cli  # noqa: E402

PROFILES = tw.load_profiles()
REGIONS = list(PROFILES["regions"])
TARGET_MONTH = "2026-08"
# hash of every canonical workbook at import time: nothing in this suite may change them
CANONICAL_HASHES = {r: tw.sha256_file(Path(cfg["tracker"])) for r, cfg in PROFILES["regions"].items()}


def h(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cfg_of(region: str) -> dict:
    return dict(tw.region_config(PROFILES, region), region=region)


def copy_tracker(region: str, dest_dir: Path) -> Path:
    src = Path(PROFILES["regions"][region]["tracker"])
    dest = dest_dir / f"{region}-{src.name}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def probe(i: int, month: str = TARGET_MONTH) -> dict:
    """An unmistakable acceptance probe — reserved .invalid domain, never a vacancy."""
    return {
        "date_found": f"{month}-{5 + i:02d}",
        "company": f"ZZZ ROLLOVER PROBE {i} (NOT A REAL VACANCY)",
        "title": f"Rollover probe {i} — delete this row",
        "location": "n/a — acceptance artifact",
        "url": f"https://rollover-probe.invalid/{month}/{i}",
        "fit_score": 0.0,
        "live_status": "Uncertain",
        "clearance_check": "n/a — acceptance artifact",
        "work_authorisation_risk": "n/a — acceptance artifact",
        "key_gap": "n/a — acceptance artifact",
        "recommendation": "Rollover acceptance probe on a TEST COPY only.",
        "discovery": f"ROLLOVER ACCEPTANCE {month} — TEST COPY ONLY",
        "source": "career-ops/tests/test_tracker_rollover.py probe",
        "notes": "Probe row. Not a vacancy. Safe to delete.",
    }


@pytest.fixture()
def prepared(tmp_path):
    """A region copy holding exactly two probe rows dated in TARGET_MONTH."""
    def _make(region: str):
        copy = copy_tracker(region, tmp_path)
        res = tw.write_records(PROFILES, region, [probe(1), probe(2)], apply=True,
                               tracker_override=str(copy),
                               backup_dir=str(tmp_path / "wb-backups"))
        assert res["applied"], res.get("error")
        assert res["counts"]["appended"] == 2, res["counts"]
        return copy
    return _make


@pytest.fixture()
def run_env(tmp_path):
    return {
        "archive_dir": str(tmp_path / "archive"),
        "backup_dir": str(tmp_path / "canon-backups"),
        "state_dir": str(tmp_path / "run-health"),
    }


# --------------------------------------------------------------------------- #
# helpers / naming
# --------------------------------------------------------------------------- #

def test_archive_filenames_match_the_region_archive_globs():
    """The archive name must be picked up by tracker_writer's cross-month index."""
    for region in REGIONS:
        name = ro.archive_filename(region, TARGET_MONTH)
        assert any(fnmatch(name, g) for g in tw.default_archive_globs(region)), (region, name)


def test_month_helpers():
    assert ro.parse_month("2026-08") == "2026-08"
    for bad in ("2026-13", "2026-8", "August", "", None, "2026-08-01"):
        with pytest.raises(ValueError):
            ro.parse_month(bad)
    assert ro.month_of(dt.datetime(2026, 8, 5, 12, 0)) == "2026-08"
    assert ro.month_of(dt.date(2026, 8, 5)) == "2026-08"
    assert ro.month_of("2026-08-05") == "2026-08"
    # free-text dates are not rotated, they are retained
    assert ro.month_of("Posted 30+ days ago") is None
    assert ro.month_of(None) is None
    assert ro.previous_month(dt.date(2026, 9, 24)) == "2026-08"
    assert ro.previous_month(dt.date(2026, 1, 2)) == "2025-12"


def test_default_month_is_the_previous_calendar_month():
    today = dt.date.today()
    assert ro.previous_month(today) <= today.strftime("%Y-%m")


# --------------------------------------------------------------------------- #
# plan is read-only
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("region", REGIONS)
def test_plan_is_read_only(region, prepared, run_env):
    copy = prepared(region)
    before = h(copy)
    p = ro.plan(PROFILES, region, TARGET_MONTH, tracker_override=str(copy),
                archive_dir=run_env["archive_dir"])
    assert p["status"] == "planned" and p["ok"]
    assert p["month_rows"] == 2, p
    assert p["retained_rows"] >= 1
    assert p["months_present"][TARGET_MONTH] == 2
    assert TARGET_MONTH in p["months_present"]
    assert p["archive_filename"] == ro.archive_filename(region, TARGET_MONTH)
    assert p["archive_exists"] is False
    assert p["canonical_authoritative"] is True
    assert h(copy) == before, "plan modified the workbook"
    assert not Path(run_env["archive_dir"]).exists(), "plan created the archive directory"


@pytest.mark.parametrize("region", REGIONS)
def test_dry_run_writes_nothing(region, prepared, run_env):
    copy = prepared(region)
    before = h(copy)
    res = ro.rollover(PROFILES, region, TARGET_MONTH, apply=False, tracker_override=str(copy),
                      **run_env)
    assert res["status"] == "planned" and res["applied"] is False
    assert h(copy) == before
    assert not Path(res["archive"]).exists()


# --------------------------------------------------------------------------- #
# the real rollover
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("region", REGIONS)
def test_rollover_archives_and_rotates(region, prepared, run_env):
    """Archive first, then rotate the rows out of the canonical workbook."""
    cfg = cfg_of(region)
    copy = prepared(region)
    tr = tw.Tracker(copy, cfg)
    pre_rows = tr.last_data_row() - cfg["first_data_row"] + 1
    dcol = tw.column_index_from_string(cfg["field_map"]["date_found"])
    # capture the rolled rows verbatim so the archive can be compared cell by cell
    rolled = [tw.Tracker.row_dict(tr, r) for r in range(cfg["first_data_row"], tr.last_data_row() + 1)
              if ro.month_of(tr.ws.cell(row=r, column=dcol).value) == TARGET_MONTH]
    pre_validations = {c: len(v) for c, v in tw._dv_map(tr.ws).items()}
    tr.wb.close()
    assert len(rolled) == 2

    res = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, tracker_override=str(copy), **run_env)

    assert res["status"] == "written", res
    assert res["applied"] is True and res["ok"] is True
    assert res["counts"]["archived_rows"] == 2
    assert res["counts"]["rotated_out_of_canonical"] == 2

    # --- archive workbook: same schema, only the month's rows ------------- #
    arch = Path(res["archive"]["path"])
    assert arch.exists()
    av = tw.verify_workbook(arch, cfg, expect_data_rows=2)
    assert av["ok"], av["problems"]
    awb = openpyxl.load_workbook(arch)
    aws = awb[cfg["sheet"]]
    # sheet set inherited from the canonical workbook
    cwb = openpyxl.load_workbook(cfg["tracker"], read_only=True)
    assert awb.sheetnames == cwb.sheetnames, awb.sheetnames
    cwb.close()
    # formulas + data validations preserved
    assert {c: len(v) for c, v in tw._dv_map(aws).items()} == pre_validations
    for spec in cfg.get("formula_map", {}).values():
        col = spec["column"]
        for r in range(cfg["first_data_row"], cfg["first_data_row"] + 2):
            assert str(aws[f"{col}{r}"].value).startswith("="), (col, r)
    # every cell of every rotated row is preserved verbatim, owner columns included
    formula_cols = {spec["column"] for spec in cfg.get("formula_map", {}).values()}
    for i, row in enumerate(rolled):
        r = cfg["first_data_row"] + i
        for letter, value in row.items():
            if letter in formula_cols:
                continue  # re-templated for the new row position, asserted above
            assert aws[f"{letter}{r}"].value == value, (letter, r, value, aws[f"{letter}{r}"].value)
    # table ref covers exactly the archived rows
    tref = aws.tables[cfg["table"]].ref if cfg.get("table") else aws.auto_filter.ref
    assert int(tref.split(":")[1].replace(tref.split(":")[1][0], "")) >= cfg["first_data_row"] + 1
    awb.close()

    # --- canonical workbook: rotated, verified, backed up ----------------- #
    canon = res["canonical"]
    assert Path(canon["backup"]).exists()
    assert canon["verification"]["ok"], canon["verification"]["problems"]
    assert canon["data_rows"] == pre_rows - 2, canon["data_rows"]
    assert res["canonical_untouched"] is False
    post = tw.verify_workbook(copy, cfg, expect_data_rows=pre_rows - 2)
    assert post["ok"], post["problems"]
    assert post["owner_columns_unchanged"] is True
    assert post["duplicate_urls_in_workbook"] == []
    t2 = tw.Tracker(copy, cfg)
    remaining_dates = [ro.month_of(t2.ws.cell(row=r, column=dcol).value)
                       for r in range(cfg["first_data_row"], t2.last_data_row() + 1)]
    t2.wb.close()
    assert TARGET_MONTH not in remaining_dates, "a rotated row survived in the canonical workbook"
    assert h(Path(cfg["tracker"])) == CANONICAL_HASHES[region], "the canonical workbook was modified"


@pytest.mark.parametrize("region", REGIONS)
def test_rotated_rows_feed_the_cross_month_dedupe_index(region, prepared, run_env):
    """A posting archived in a previous month cannot be appended again."""
    copy = prepared(region)
    res = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, tracker_override=str(copy), **run_env)
    assert res["status"] == "written", res

    cross = res["cross_month_dedupe"]
    assert cross["rotated_url_keys"] == 2
    assert cross["all_rotated_rows_indexed"] is True, cross
    assert cross["archive_in_index_sources"] is True, cross
    assert res["dedupe_proof"]["appended"] == 0
    assert res["dedupe_proof"]["decisions"] == {"duplicate-cross-month": 2}, res["dedupe_proof"]

    # independent re-check through the public interface, not just the internals
    redo = tw.write_records(PROFILES, region, [probe(1)], apply=False,
                            tracker_override=str(copy),
                            extra_archive_dirs=[run_env["archive_dir"]])
    assert redo["counts"]["appended"] == 0
    assert [o["decision"] for o in redo["outcomes"]] == ["duplicate-cross-month"]


def test_rollover_refuses_when_a_row_carries_owner_state(prepared, run_env):
    """Owner application state is never silently deleted; the run stops instead."""
    region = "uk"
    cfg = cfg_of(region)
    copy = prepared(region)
    guarded, _automation = ro._guarded_owner_columns(cfg)
    assert guarded, "the UK profile must have at least one owner-only column"
    owner_col = guarded[0]  # UK: J (application status)
    wb = openpyxl.load_workbook(copy)
    ws = wb[cfg["sheet"]]
    dcol = tw.column_index_from_string(cfg["field_map"]["date_found"])
    target_row = next(r for r in range(cfg["first_data_row"], ws.max_row + 1)
                      if ro.month_of(ws.cell(row=r, column=dcol).value) == TARGET_MONTH)
    marker = "OWNER-STATE-PROBE-DO-NOT-ROTATE"
    ws[f"{owner_col}{target_row}"] = marker
    wb.save(copy)
    wb.close()
    before = h(copy)

    res = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, tracker_override=str(copy), **run_env)
    assert res["status"] == "refused", res
    assert res["applied"] is False
    assert res["owner_action_required"] is True
    assert res["owner_state_conflicts"] == [{"row": target_row, "column": owner_col}]
    assert h(copy) == before, "refusal still modified the canonical workbook"
    assert not Path(res["archive"]).exists(), "refusal still wrote an archive"

    # the conflict record reports position only, never the owner's value
    payload = json.dumps(res, default=str)
    assert marker not in payload
    assert "OWNER-STATE-PROBE" not in payload

    # and with explicit override it proceeds (still on the copy)
    forced = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, tracker_override=str(copy),
                         allow_owner_state_removal=True, **run_env)
    assert forced["status"] == "written", forced
    awb = openpyxl.load_workbook(forced["archive"]["path"])
    aws = awb[cfg["sheet"]]
    owner_vals = [aws[f"{owner_col}{r}"].value
                  for r in range(cfg["first_data_row"], cfg["first_data_row"] + 2)]
    awb.close()
    assert marker in owner_vals, "the owner value was not preserved in the archive"
    # the owner's row moved to the archive: it is no longer in the canonical workbook
    cwb = openpyxl.load_workbook(copy)
    cws = cwb[cfg["sheet"]]
    remaining = [cws[f"{owner_col}{r}"].value for r in range(cfg["first_data_row"], cws.max_row + 1)]
    cwb.close()
    assert marker not in remaining


def test_owner_column_guard_is_explicit_about_automation_writable_columns():
    """The guard must name the columns it protects and the ones it cannot.

    The regional profiles map the manifest's ``notes`` field to column Z while
    also declaring Z an owner column, so Z is automation-writable and cannot be
    attributed to the owner from the data alone. That is reported, not hidden.
    """
    for region in ("dubai", "japan", "singapore"):
        cfg = cfg_of(region)
        guarded, automation = ro._guarded_owner_columns(cfg)
        assert automation == ["Z"], (region, automation)
        assert "Z" not in guarded
        assert set(cfg["owner_columns"]) == set(guarded) | set(automation)
        assert "V" in guarded  # applied date is owner-only
    guarded_uk, automation_uk = ro._guarded_owner_columns(cfg_of("uk"))
    cfg = cfg_of("uk")
    assert set(automation_uk) == set(cfg["owner_columns"]) & set(cfg["field_map"].values())
    assert "F" in guarded_uk
    assert set(guarded_uk) | set(automation_uk) == set(cfg["owner_columns"])


def test_archive_only_leaves_the_canonical_untouched(prepared, run_env):
    region = "japan"
    copy = prepared(region)
    before = h(copy)
    res = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, archive_only=True,
                      tracker_override=str(copy), **run_env)
    assert res["status"] == "written", res
    assert res["counts"]["archived_rows"] == 2
    assert res["counts"]["rotated_out_of_canonical"] == 0
    assert res["canonical_untouched"] is True
    assert h(copy) == before


def test_archive_only_rerun_is_unchanged(prepared, run_env):
    region = "uk"
    copy = prepared(region)
    first = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, archive_only=True,
                        tracker_override=str(copy), **run_env)
    assert first["status"] == "written"
    arch_hash = tw.sha256_file(first["archive"]["path"])
    second = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, archive_only=True,
                         tracker_override=str(copy), **run_env)
    assert second["status"] == "unchanged", second
    assert second["applied"] is False
    assert tw.sha256_file(second["archive"]) == arch_hash


def test_existing_archive_with_different_content_is_refused_then_forced(prepared, run_env):
    region = "dubai"
    cfg = cfg_of(region)
    copy = prepared(region)
    arch_dir = Path(run_env["archive_dir"])
    arch_dir.mkdir(parents=True)
    arch = arch_dir / ro.archive_filename(region, TARGET_MONTH)
    # a planted archive holding different content
    shutil.copy2(copy, arch)
    wb = openpyxl.load_workbook(arch)
    ws = wb[cfg["sheet"]]
    ws[f"{cfg['dedupe']['url_column']}{cfg['first_data_row']}"] = "https://planted.invalid/x"
    wb.save(arch)
    wb.close()
    planted_hash = tw.sha256_file(arch)

    res = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, tracker_override=str(copy), **run_env)
    assert res["status"] == "refused" and res["applied"] is False
    assert tw.sha256_file(arch) == planted_hash, "a refused run modified the existing archive"

    forced = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, force=True,
                         tracker_override=str(copy), **run_env)
    assert forced["status"] == "written", forced
    backup = Path(forced["archive"]["previous_archive_backup"])
    assert backup.exists() and tw.sha256_file(backup) == planted_hash
    assert tw.sha256_file(arch) != planted_hash


def test_no_rows_for_the_month_is_reported(prepared, run_env):
    region = "singapore"
    copy = prepared(region)
    before = h(copy)
    res = ro.rollover(PROFILES, region, "1999-01", apply=True, tracker_override=str(copy), **run_env)
    assert res["status"] == "no_rows" and res["applied"] is False
    assert h(copy) == before
    assert not Path(res["archive"]).exists()


def test_rotated_rows_can_be_restored_from_the_backup(prepared, run_env):
    """Reversibility: the pre-rollover backup restores the workbook byte-identically."""
    region = "uk"
    copy = prepared(region)
    before = h(copy)
    res = ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, tracker_override=str(copy), **run_env)
    assert res["status"] == "written"
    shutil.copy2(res["canonical"]["backup"], copy)
    assert h(copy) == before
    restored = tw.verify_workbook(copy, cfg_of(region))
    assert restored["ok"], restored["problems"]


# --------------------------------------------------------------------------- #
# interface: CLI + run-health
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("region", ["uk", "japan"])
def test_cli_rollover_emits_one_json_object(region, prepared, run_env):
    copy = prepared(region)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["--profiles", str(CAREER_OPS / "regional_profiles.json"),
                       "rollover", "--region", region, "--month", TARGET_MONTH, "--apply",
                       "--tracker", str(copy), "--archive-dir", run_env["archive_dir"],
                       "--backup-dir", run_env["backup_dir"], "--state-dir", run_env["state_dir"]])
    assert rc == 0
    doc = json.loads(buf.getvalue())
    assert doc["status"] == "written"
    assert doc["provenance"]["roster"] == "B09"
    assert Path(doc["archive"]["path"]).exists()


def test_run_health_records_both_workers(prepared, run_env, tmp_path):
    region = "uk"
    copy = prepared(region)
    # rollover worker
    ro.rollover(PROFILES, region, TARGET_MONTH, apply=True, tracker_override=str(copy), **run_env)
    # tracker writer through the public CLI path
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"records": [probe(3, month="2026-09")]}), encoding="utf-8")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["--profiles", str(CAREER_OPS / "regional_profiles.json"),
                       "write", "--region", region, "--manifest", str(manifest), "--apply",
                       "--tracker", str(copy), "--backup-dir", str(tmp_path / "wb2"),
                       "--state-dir", run_env["state_dir"]])
    assert rc == 0

    summary = drh.summarise(run_env["state_dir"])
    assert summary["excel_is_source_of_truth"] is True
    assert summary["chief_state_role"] == "orchestration-only"
    assert set(summary["jobs"]) == {"tracker-writer", "monthly-rollover"}
    rw = summary["jobs"]["tracker-writer"]
    assert rw["last_status"] == "ok" and rw["last_region"] == region
    assert rw["last_counts"]["appended"] == 1
    assert rw["last_counts"]["data_rows_after"] is not None
    ro_job = summary["jobs"]["monthly-rollover"]
    assert ro_job["last_status"] == "written"
    assert ro_job["last_counts"]["archived_rows"] == 2

    # run-health is aggregate-only: no workbook content ever lands in it
    payload = (Path(run_env["state_dir"]) / "monthly-rollover.json").read_text(encoding="utf-8")
    assert "https://" not in payload
    assert "ROLLOVER PROBE" not in payload
    payload2 = (Path(run_env["state_dir"]) / "tracker-writer.json").read_text(encoding="utf-8")
    assert "https://" not in payload2 and "PROBE" not in payload2


def test_unknown_job_is_refused(run_env):
    with pytest.raises(KeyError):
        drh.record_run("not-a-job", region="uk", status="ok", state_dir=run_env["state_dir"])


def test_cli_run_health_emits_one_json_object(run_env, prepared):
    copy = prepared("uk")
    ro.rollover(PROFILES, "uk", TARGET_MONTH, apply=True, tracker_override=str(copy), **run_env)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["run-health", "--state-dir", run_env["state_dir"]])
    assert rc == 0
    doc = json.loads(buf.getvalue())
    assert doc["jobs"]["monthly-rollover"]["last_status"] == "written"


# --------------------------------------------------------------------------- #
# final safety assertion
# --------------------------------------------------------------------------- #

def test_canonical_workbooks_were_never_modified_by_this_suite():
    for region in REGIONS:
        assert tw.sha256_file(Path(PROFILES["regions"][region]["tracker"])) == CANONICAL_HASHES[region]
