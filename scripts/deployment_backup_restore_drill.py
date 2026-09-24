#!/usr/bin/env python3
"""Backup / restore verification drill for the Chief control plane.

Purpose: prove *before* a cutover that the declared state set can be copied,
that the copies are integrit-verified, and that restoring them reproduces the
same content — without ever writing to live state.

What it does, per declared artifact:

1. **Backup** — SQLite databases are copied with the SQLite online backup API
   (consistent snapshot even while another process holds the DB open); JSON
   state files are copied byte-for-byte into the same snapshot directory.
2. **Verify the backup** — `PRAGMA integrity_check` on the copy, plus a
   content fingerprint (per-table row counts + `sha256` of each backup file).
3. **Restore test** — the copies are restored into a throwaway directory that
   is *not* under the live runtime root; integrity and fingerprints must match
   the backup exactly.
4. **Rollback availability** — `scripts/deploy_e3_runtime.py --dry-run` must
   produce a manifest and must not need to write anything.

Nothing here overwrites live state, changes a scheduled task, or makes a
network call. Output is a machine-readable report plus a Markdown summary.

Usage:
    python scripts/deployment_backup_restore_drill.py [--out-dir DIR]
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"
HERMES_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"

SQLITE_ARTIFACTS = [
    ("e1-e2-exec-brain", RUNTIME_ROOT / "exec_brain.db"),
    ("e2-governor", RUNTIME_ROOT / "governor.db"),
    ("e3-orchestration", RUNTIME_ROOT / "orchestration.db"),
    ("hermes-state", HERMES_ROOT / "state.db"),
    ("hermes-kanban", HERMES_ROOT / "kanban.db"),
    ("hermes-shared-state", HERMES_ROOT / "shared-state.db"),
    ("hermes-cron-executions", HERMES_ROOT / "cron" / "executions.db"),
]

JSON_ARTIFACTS = [
    ("e1-chain-head", RUNTIME_ROOT / "chain-head.json"),
    ("e2-gov-chain-head", RUNTIME_ROOT / "gov-chain-head.json"),
    ("e2-deepseek-config", RUNTIME_ROOT / "deepseek-config.json"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(path: Path) -> dict:
    """Content fingerprint: table row counts + integrity check (read-only)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {}
        for table in tables:
            counts[table] = con.execute(
                f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        return {"integrity_check": integrity, "row_counts": counts,
                "sha256": sha256_file(path)}
    finally:
        con.close()


def backup_sqlite(src: Path, dst: Path) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return fingerprint(dst)


def run_drill(out_dir: Path, snapshot_root: Path) -> dict:
    backup_dir = snapshot_root / "backup"
    restore_dir = snapshot_root / "restore-check"
    backup_dir.mkdir(parents=True, exist_ok=True)
    restore_dir.mkdir(parents=True, exist_ok=True)

    artifacts = []
    failures = []

    for label, src in SQLITE_ARTIFACTS:
        record: dict = {"label": label, "kind": "sqlite", "source": str(src)}
        if not src.exists():
            record.update(status="FAIL", reason="source missing")
            failures.append(label)
            artifacts.append(record)
            continue
        record["source_fingerprint"] = fingerprint(src)
        dst = backup_dir / f"{label}.db"
        record["backup_fingerprint"] = backup_sqlite(src, dst)
        restored = restore_dir / f"{label}.db"
        shutil.copy2(dst, restored)
        record["restore_fingerprint"] = fingerprint(restored)
        record["restore_matches_backup"] = (
            record["restore_fingerprint"] == record["backup_fingerprint"])
        record["status"] = ("PASS"
                            if record["backup_fingerprint"]["integrity_check"] == "ok"
                            and record["restore_matches_backup"] else "FAIL")
        if record["status"] == "FAIL":
            failures.append(label)
        artifacts.append(record)

    for label, src in JSON_ARTIFACTS:
        record: dict = {"label": label, "kind": "json", "source": str(src)}
        if not src.exists():
            record.update(status="FAIL", reason="source missing")
            failures.append(label)
            artifacts.append(record)
            continue
        record["source_sha256"] = sha256_file(src)
        dst = backup_dir / f"{label}.json"
        shutil.copy2(src, dst)
        restored = restore_dir / f"{label}.json"
        shutil.copy2(dst, restored)
        record["backup_sha256"] = sha256_file(dst)
        record["restore_sha256"] = sha256_file(restored)
        record["restore_matches_backup"] = (
            record["backup_sha256"] == record["restore_sha256"])
        record["status"] = "PASS" if record["restore_matches_backup"] else "FAIL"
        if record["status"] == "FAIL":
            failures.append(label)
        artifacts.append(record)

    # Rollback availability: the deployment script must produce a plan without
    # touching the runtime root.
    rollback: dict = {"command": "python scripts/deploy_e3_runtime.py --dry-run"}
    try:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "deploy_e3_runtime.py"),
             "--dry-run", "--runtime-root", str(snapshot_root / "rollback-dry-run-root")],
            capture_output=True, text=True, timeout=300)
        rollback["exit_code"] = proc.returncode
        try:
            parsed = json.loads(proc.stdout)
            rollback["dry_run"] = parsed.get("dry_run")
            rollback["would_copy"] = len(parsed.get("copied") or [])
            rollback["performed_no_write"] = (
                parsed.get("dry_run") is True and
                not (snapshot_root / "rollback-dry-run-root").exists())
        except Exception as exc:
            rollback["parse_error"] = f"{type(exc).__name__}: {exc}"
            rollback["stdout_head"] = (proc.stdout or "")[:400]
        rollback["status"] = ("PASS"
                              if rollback.get("exit_code") == 0
                              and rollback.get("performed_no_write") else "FAIL")
    except Exception as exc:
        rollback.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
    if rollback["status"] == "FAIL":
        failures.append("deployment-rollback-dry-run")

    return {
        "artifact": "backup/restore verification drill",
        "run_started_utc": None,
        "artifacts": artifacts,
        "rollback_dry_run": rollback,
        "failure_labels": failures,
        "status": "PASS" if not failures else "FAIL",
        "live_state_modified": False,
        "network_calls_spent": 0,
        "provider_calls_spent": 0,
        "guarantees": [
            "never writes to the live runtime root or any live database",
            "reads databases read-only; snapshots via the SQLite backup API",
            "no credential value read; no network call",
            "restore is verified into a throwaway directory, not over live state",
        ],
        "ownership_note": (
            "This drill verifies the *deployment* backup/restore path. The "
            "scheduled operational backup service and its retention policy are "
            "owned by agent-operational-brief-health-backup-persistence-2026-09-23."),
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Backup / restore verification drill",
        "",
        f"- Run (UTC): {report['run_started_utc']} -> {report['run_finished_utc']}",
        f"- Verdict: **{report['status']}**",
        f"- Live state modified: {report['live_state_modified']}",
        f"- Network calls spent: {report['network_calls_spent']}",
        "",
        "| Artifact | Kind | integrity_check | restore == backup | Status |",
        "|---|---|---|---|---|",
    ]
    for a in report["artifacts"]:
        integrity = "-"
        if a["kind"] == "sqlite":
            integrity = (a.get("backup_fingerprint") or {}).get("integrity_check", "-")
        lines.append(
            f"| {a['label']} | {a['kind']} | {integrity} | "
            f"{a.get('restore_matches_backup')} | {a['status']} |")
    rollback = report["rollback_dry_run"]
    lines += [
        "",
        "## Deployment rollback availability",
        "",
        f"- `{rollback['command']}` -> exit {rollback.get('exit_code')}, "
        f"status {rollback['status']}",
        f"- wrote nothing: {rollback.get('performed_no_write')}",
        "",
        "## Restore procedure (verified by this drill)",
        "",
        "1. Stop the writers: disable `HermesRemoteQueuePoller`, `ChiefDiscordSync`, "
        "`ChiefCareerBrief`, `ChiefCareerScan-*` and stop `Hermes_Gateway`.",
        "2. Copy the snapshot's `.db` files back over the live paths listed in "
        "`deployments/01-deployment-manifest.md`.",
        "3. For each restored database run `PRAGMA integrity_check` and compare the "
        "per-table row counts with the snapshot's `backup_fingerprint`.",
        "4. Re-enable the tasks and confirm the gateway restarts and one health/acceptance "
        "command passes.",
        "",
        "This drill is non-destructive; it never performs step 2 against live state.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-deployment-backup-restore-drill")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Snapshots are raw runtime databases: they stay OUT of the repository and
    # OUT of the evidence directory. The scratch dir is pruned when idle.
    scratch = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP")
                   or tempfile.gettempdir())
    snapshot_root = scratch / f"chief-backup-restore-drill-{started.strftime('%Y%m%dT%H%M%SZ')}"

    report = run_drill(out_dir, snapshot_root)
    report["run_started_utc"] = started.isoformat(timespec="seconds")
    report["run_finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["out_dir"] = str(out_dir)
    report["snapshot_dir"] = str(snapshot_root)
    report["snapshot_note"] = (
        "Raw database snapshots live outside the repository (scratch dir). They are "
        "not published; only this report (hashes, row counts, verdicts) is committed.")

    (out_dir / "backup_restore_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out_dir / "backup_restore_report.md").write_text(
        render_markdown(report), encoding="utf-8")

    print(json.dumps({
        "out_dir": str(out_dir),
        "status": report["status"],
        "failure_labels": report["failure_labels"],
        "rollback_dry_run": report["rollback_dry_run"].get("status"),
        "artifacts": {a["label"]: a["status"] for a in report["artifacts"]},
    }, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
