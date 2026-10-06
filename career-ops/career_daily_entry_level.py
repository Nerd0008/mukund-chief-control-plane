#!/usr/bin/env python3
"""Run the Codex entry-level search for every region, then emit the digest.

One command for the daily cron: searches each region's tracker via Codex live
web search, appends genuinely new entry-level roles, then prints the
job-links digest.

Read-only with respect to everything except the four tracker workbooks.

Usage
-----
    python career_daily_entry_level.py                # all regions, 3 batches UK
    python career_daily_entry_level.py --batches 1    # quick pass
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent
PY = sys.executable

SEARCH = CONTROL_PLANE / "career-ops" / "codex_entry_level_search.py"
DIGEST = CONTROL_PLANE / "career-ops" / "daily_jobs_links.py"

#: region -> batches. UK carries the owner's primary market so it gets more.
#: Owner request: "pause the rest of the job search agents for now only keep
#: running uk job search agent" — only UK runs until further notice.
REGION_BATCHES = {"uk": 3}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batches", type=int, default=0,
                    help="override batches per region (0 = per-region defaults)")
    ap.add_argument("--timeout", type=int, default=600, help="per-batch Codex timeout")
    ap.add_argument("--skip-search", action="store_true",
                    help="skip the search; just emit the digest")
    args = ap.parse_args()

    failures = []
    if not args.skip_search:
        for region, default_batches in REGION_BATCHES.items():
            n = args.batches or default_batches
            print(f"\n{'=' * 60}\nREGION: {region} ({n} batch(es))\n{'=' * 60}", flush=True)
            try:
                proc = subprocess.run(  # noqa: S603
                    [PY, str(SEARCH), "--region", region,
                     "--batches", str(n), "--timeout", str(args.timeout)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=args.timeout * (n + 2),
                )
                sys.stdout.write(proc.stdout or "")
                if proc.returncode != 0:
                    failures.append(f"{region}: exit {proc.returncode}")
                    if proc.stderr:
                        sys.stdout.write("\n[stderr]\n" + proc.stderr[-800:])
            except subprocess.TimeoutExpired:
                failures.append(f"{region}: timeout")
                print(f"  {region}: TIMEOUT")

    print(f"\n{'=' * 60}\nDIGEST\n{'=' * 60}", flush=True)
    if DIGEST.exists():
        proc = subprocess.run(  # noqa: S603
            [PY, str(DIGEST)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300)
        sys.stdout.write(proc.stdout or "")
        if proc.returncode not in (0, 3):
            print(f"\n[digest exit {proc.returncode}]", file=sys.stderr)
    else:
        print(f"ERROR: digest script missing at {DIGEST}", file=sys.stderr)
        failures.append("digest missing")

    if failures:
        print("\nREGION FAILURES: " + "; ".join(failures), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
