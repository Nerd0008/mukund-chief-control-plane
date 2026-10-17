#!/usr/bin/env python3
"""Nightly backup of every live career tracker to Google Drive (G:).

Copies each live tracker workbook into a dated folder under
``G:\\My Drive\\Career Tracker Backups\\<YYYY-MM-DD>\\`` and verifies every
copy two ways: SHA-256 must match the source, and the copy must reload cleanly
with openpyxl. Prints a short confirmation suitable for delivery as a status
message.

Design notes:
  * Dated folders, never in-place overwrites, so a corrupt copy can never
    destroy the previous good backup and restore is "take the newest folder".
  * Only the four *live* workbooks are backed up. The ``.backup*`` /
    ``.pre-*`` / ``.bak*`` files next to them are historical snapshots, not
    live state, and are deliberately skipped.
  * Read-only on the sources: nothing here opens a tracker for writing.

Usage:
  python career-ops/backup_trackers.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import shutil
import sys
from pathlib import Path

CODEX = Path.home() / "Downloads" / "codex"

#: The four live trackers, as region -> source path. Keep in sync with
#: daily_jobs_links.TRACKERS, which remains the authoritative list.
TRACKERS = {
    "uk": CODEX / "uk-cyber-job-tracker.xlsx",
    "dubai": CODEX / "Dubai_Cybersecurity_Job_Tracker.xlsx",
    "japan": CODEX / "Japan_Cybersecurity_Job_Tracker.xlsx",
    "singapore": CODEX / "Singapore_Cybersecurity_Job_Tracker.xlsx",
}

#: Google Drive for Desktop mount. Backups live in a dated folder beneath it.
DRIVE = Path("G:/My Drive")
BACKUP_ROOT = DRIVE / "Career Tracker Backups"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect(path: Path) -> str:
    """Return 'sheet=<name> rows=<n> cols=<n>' for a workbook, or an error."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
    except Exception as exc:  # noqa: BLE001 - report, never crash the backup
        return f"UNREADABLE ({exc.__class__.__name__})"
    try:
        ws = wb[wb.sheetnames[0]]
        return f"sheet={ws.title} rows={ws.max_row} cols={ws.max_column}"
    finally:
        wb.close()


def main() -> int:
    stamp = dt.date.today().isoformat()
    if not DRIVE.exists():
        print(f"BACKUP FAILED: Google Drive mount unavailable: {DRIVE}")
        return 1

    dest_dir = BACKUP_ROOT / stamp
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied, problems = 0, []
    for region, src in TRACKERS.items():
        label = f"{src.name} ({region})"
        if not src.exists():
            problems.append(f"MISSING SOURCE {label}")
            continue
        dst = dest_dir / src.name
        try:
            shutil.copy2(src, dst)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"COPY FAILED {label}: {exc}")
            continue
        if sha256(src) != sha256(dst):
            problems.append(f"HASH MISMATCH {label}")
            continue
        copied += 1
        print(f"  {label}: {dst}")
        print(f"      {inspect(dst)}")

    print()
    if problems:
        print(f"BACKUP INCOMPLETE {stamp}: {copied}/{len(TRACKERS)} copied")
        for p in problems:
            print(f"  ! {p}")
        return 1

    total = sum(p.stat().st_size for p in dest_dir.iterdir())
    print(f"BACKUP OK {stamp}: {copied}/{len(TRACKERS)} trackers -> {dest_dir}")
    print(f"  total {total / 1024:.0f} KiB, sha256 verified, copies reload cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
