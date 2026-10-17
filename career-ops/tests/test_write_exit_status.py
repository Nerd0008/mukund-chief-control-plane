"""`write` exits 0 for a successful no-op and 1 only for a real error.

Regression (2026-10-17): the nightly run exited 1 because a manifest whose
records were *all already in the tracker* returned exit 1. Nothing had failed
-- the tracker simply already held those rows. The exit code now matches
_write_run_status(), which already classified that case as a no-op.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import career_ops_cli as cli  # noqa: E402


def _args(**over):
    base = dict(profiles=None, region="uk", manifest="m.json", apply=True,
                backup_dir=None, update_existing=False, archive_dir=None,
                tracker=None, state_dir=None)
    base.update(over)
    return argparse.Namespace(**base)


def _run(monkeypatch, result, apply=True):
    seen = {}
    monkeypatch.setattr(cli, "load_profiles", lambda profiles: {})
    monkeypatch.setattr(cli, "_load_manifest", lambda manifest: [])
    monkeypatch.setattr(cli.tracker_writer, "write_records",
                        lambda *a, **k: result)
    monkeypatch.setattr(cli, "emit", lambda payload: seen.setdefault("emitted", payload))
    monkeypatch.setattr(cli.dept_run_health, "record_run",
                        lambda *a, **kw: seen.setdefault("recorded", kw))
    rc = cli.cmd_write(_args(apply=apply))
    return rc, seen


def test_all_duplicates_is_success_not_failure(monkeypatch):
    result = {"applied": False,
              "counts": {"input": 1, "appended": 0, "duplicates": 1},
              "tracker": "uk.xlsx"}
    rc, seen = _run(monkeypatch, result)
    assert rc == 0
    assert seen["recorded"]["status"] == "no-op"
    assert seen["emitted"]["counts"]["duplicates"] == 1


def test_real_error_exits_non_zero(monkeypatch):
    result = {"applied": False,
              "error": "post-write verification failed; canonical workbook untouched",
              "tracker": "uk.xlsx"}
    rc, seen = _run(monkeypatch, result)
    assert rc == 1
    assert seen["recorded"]["status"] == "failed"


def test_appended_rows_exit_zero(monkeypatch):
    result = {"applied": True,
              "counts": {"input": 2, "appended": 2},
              "tracker": "uk.xlsx"}
    rc, seen = _run(monkeypatch, result)
    assert rc == 0
    assert seen["recorded"]["status"] == "ok"


def test_dry_run_exits_zero(monkeypatch):
    result = {"applied": False,
              "counts": {"input": 1, "appended": 0},
              "tracker": "uk.xlsx"}
    rc, seen = _run(monkeypatch, result, apply=False)
    assert rc == 0
    assert seen["recorded"]["status"] == "dry-run"
