#!/usr/bin/env python3
"""Verification command for the canonical project status.

Fails (exit 1) when any of the following is true:

1. the canonical status source is missing a required section;
2. a referenced evidence artifact does not exist;
3. a figure in the canonical source disagrees with the evidence artifact it
   names (regression counts, roster counts, credential readiness, deployment
   preflight, E4/E5 drill results, persistence);
4. a required production blocker is missing, or an optional/feature-gated item
   has been wrongly promoted to a production blocker;
5. the generated executive tracker, or a generated status-summary block in
   README.md / state/current_company_state.md / state/full_build_tracker.md,
   is stale relative to the canonical status source;
6. the generated output contains possible secret material;
7. the status claims readiness while production blockers remain open.

Warnings (non-fatal unless `--strict`) cover evidence directories newer than the
status `as_of`. This makes static drift visible instead of silently accepted.

Usage:
    python scripts/status_verify.py [--strict] [--quiet]

Reads repository artifacts only: no network call, no provider call, no credential
value, no private runtime database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import status_render
import status_sources as src

DOC_TARGETS = [
    ("readme-block", src.REPO_ROOT / "README.md", "README.md"),
    ("company-state-block", src.REPO_ROOT / "state" / "current_company_state.md",
     "state/current_company_state.md"),
    ("tracker-block", src.REPO_ROOT / "state" / "full_build_tracker.md",
     "state/full_build_tracker.md"),
]


def check_generated_outputs(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    outputs = status_render.build_outputs(canonical)

    tracker = src.EXECUTIVE_TRACKER_PATH
    if not tracker.exists():
        problems.append(("FAIL", "generated executive tracker is missing: status/executive-tracker.md"))
    else:
        on_disk = src.normalise(src.read_source(tracker))
        fresh = src.normalise(outputs["executive-tracker"])
        if on_disk != fresh:
            problems.append(("FAIL", "status/executive-tracker.md is stale relative to the canonical status "
                                     "source — regenerate with `python scripts/status_render.py`"))

    for key, path, label in DOC_TARGETS:
        if not path.exists():
            problems.append(("FAIL", f"derived-summary target is missing: {label}"))
            continue
        text = src.read_source(path)
        block = src.extract_block(text)
        if block is None:
            problems.append(("FAIL", f"{label} has no generated status block (expected the "
                                     f"executive-status markers) — run `python scripts/status_render.py`"))
            continue
        if src.normalise(block) != src.normalise(outputs[key]):
            problems.append(("FAIL", f"{label} generated status block is stale relative to the canonical "
                                     f"status source — regenerate with `python scripts/status_render.py`"))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings (unincorporated newer evidence) as failures")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    canonical = src.load_canonical()
    problems = src.run_all_checks(canonical, include_block_checks=True)
    problems += check_generated_outputs(canonical)

    fails = [m for level, m in problems if level == "FAIL"]
    warns = [m for level, m in problems if level == "WARN"]

    if not args.quiet:
        for message in fails:
            print(f"FAIL: {message}")
        for message in warns:
            print(f"WARN: {message}")
        if fails:
            print(f"\ncanonical status verification FAILED ({len(fails)} failure(s), {len(warns)} warning(s))")
        elif warns and args.strict:
            print(f"\ncanonical status verification FAILED in strict mode ({len(warns)} warning(s))")
        else:
            print(f"canonical status verification PASSED "
                  f"(as_of {canonical['as_of']}; {len(canonical['production_blockers'])} production blocker(s) recorded;"
                  f" {len(warns)} warning(s))")

    if fails or (warns and args.strict):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
