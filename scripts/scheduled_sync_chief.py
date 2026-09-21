#!/usr/bin/env python3
"""Wrapper for scheduled Chief Discord -> GitHub sync.

Runs the existing sync_discord_chief.py with a cross-process lock so overlapping
scheduled runs cannot occur, captures a one-line summary (no message contents,
no secrets) to a local log outside the repo, and exits 0. Failures exit 1 so the
Windows Task Scheduler can show last-run-status, but the local archive is never
touched by failure: sync_discord_chief.py only advances its checkpoint after a
successful push.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SYNC_SCRIPT = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane\scripts\sync_discord_chief.py")
LOG = Path(r"C:\Users\mukun\DiscordArchive\chief\sync.log")
LOCK = Path(r"C:\Users\mukun\DiscordArchive\chief\.sync.lock")
LOCK_TIMEOUT = 600  # seconds; give up if another sync genuinely hangs


def log(entry):
    line = json.dumps(entry, ensure_ascii=False)
    try:
        with open(LOCK.with_suffix(".log.lock"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    # Cross-process lock: atomic create; stale lock (>timeout) is reclaimed.
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    try:
        lock_fd = open(LOCK, "x")
    except FileExistsError:
        try:
            age = time.time() - LOCK.stat().st_mtime
            if age > LOCK_TIMEOUT:
                LOCK.unlink(missing_ok=True)
                lock_fd = open(LOCK, "x")
            else:
                log({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "result": "skipped", "reason": "another sync running",
                     "push": None, "attempted": 0, "published": 0, "rejected": 0,
                     "error": ""})
                return 0
        except FileNotFoundError:
            lock_fd = open(LOCK, "x")
    try:
        r = subprocess.run([sys.executable, str(SYNC_SCRIPT)],
                           capture_output=True, text=True, encoding="utf-8", timeout=570)
        out = (r.stdout or "") + (r.stderr or "")
        published = 0
        rejected = 0
        nothing = "Nothing new to sync" in out
        push_ok = r.returncode == 0
        for token in out.splitlines():
            t = token.strip()
            if t.startswith("Published "):
                try:
                    published = int(t.split()[1])
                except Exception:
                    pass
            if t.startswith("rejected:"):
                try:
                    rejected = int(t.split(":")[1].split(".")[0])
                except Exception:
                    pass
        err = ""
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "unknown error").strip().splitlines()[-1][:200]
        log({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "result": "ok" if push_ok else "failed",
             "nothing_to_sync": nothing,
             "push": push_ok, "attempted": published + rejected,
             "published": published, "rejected": rejected,
             "error": err})
        return r.returncode
    finally:
        try:
            lock_fd.close()
        except Exception:
            pass
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
