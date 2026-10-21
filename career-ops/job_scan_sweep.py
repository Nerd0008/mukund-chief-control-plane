#!/usr/bin/env python3
"""Drain the job-search query set on demand.

Owner request: "fire job search ... I want new roles everytime dont stop until u
dont find new roles".

`job_scan_delta.py` searches ONE query batch per run (the batch the 2-hour slot
selects), so a single firing only ever sees part of the query set. This walks
EVERY batch in turn and repeats the whole sweep while it is still turning up
roles, then stops the moment a full sweep finds nothing new.

Why a full sweep is the stopping rule, not a single empty run: one empty run only
proves that ONE batch is exhausted. Stopping there would leave the other batches
unsearched and the owner would be told the search was drained when it was not.

Each batch run is the ordinary `job_scan_delta.py`, so everything it guarantees
still holds: new roles go into the tracker through the guarded writer, and only
roles never reported before are printed. This driver adds no logic of its own -
it never scores, re-words, or invents a role, and it reports exactly what the
scans printed.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SCAN = HERE / "job_scan_delta.py"
PY = sys.executable
MAX_SWEEPS = 2
FALLBACK_BATCHES = 6

NEW_RE = re.compile(r"^(\d+)\s+new role\(s\) found", re.MULTILINE)


def batch_count() -> int:
    """The search's own batch count, so a sweep covers the whole query set.

    The search applies its own modulo to the offset, so guessing too high is
    harmless (it wraps) while guessing too low would leave batches unsearched.
    """
    try:
        sys.path.insert(0, str(HERE))
        import datetime as dt

        import codex_entry_level_search as ces
        import owner_search_profile as osp
        from career_search_recall import query_batches

        profile = osp.load_profile()
        batches = query_batches(
            profile,
            ces.REGION_LABEL["uk"],
            ces.QUERY_BATCHES["uk"],
            dt.datetime.now(dt.timezone.utc).year,
        )
        return max(1, len(batches))
    except Exception as exc:  # noqa: BLE001 - fall back, never fail the drain
        print(f"[sweep] batch count unavailable ({exc.__class__.__name__}); "
              f"using {FALLBACK_BATCHES}")
        return FALLBACK_BATCHES


def run_batch(offset: int, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, str(SCAN), "--batch-offset", str(offset), "--timeout", str(timeout)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout + 300,
        cwd=str(HERE),
    )
    return proc.returncode, (proc.stdout or "")


def new_count(out: str) -> int:
    m = NEW_RE.search(out)
    return int(m.group(1)) if m else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=600, help="per-batch Codex timeout")
    args = ap.parse_args()

    n = batch_count()
    print(f"Job scan drain: {n} query batch(es) per sweep, "
          f"up to {MAX_SWEEPS} sweep(s).")
    total = 0
    sweeps_done = 0
    for sweep in range(1, MAX_SWEEPS + 1):
        sweeps_done = sweep
        sweep_new = 0
        print(f"\n=== sweep {sweep}/{MAX_SWEEPS} ===")
        for offset in range(n):
            rc, out = run_batch(offset, args.timeout)
            out = out.strip()
            if out:
                print(out)
            elif rc not in (0,):
                print(f"[sweep] batch {offset}: scan exited {rc} with no output")
            sweep_new += new_count(out)
        total += sweep_new
        print(f"--- sweep {sweep} complete: {sweep_new} new role(s) ---")
        if sweep_new == 0:
            print(f"\nDrained: a full sweep of all {n} batch(es) found nothing new.")
            break
    else:
        print(f"\nStopped at the {MAX_SWEEPS}-sweep cap; roles were still "
              f"appearing, so the query set is not exhausted.")

    print(f"\n=== DONE: {total} new role(s) across {sweeps_done} sweep(s) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
