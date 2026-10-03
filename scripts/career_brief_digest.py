#!/usr/bin/env python3
"""Career daily briefing -> Discord digest (delivery adapter, roster B23 delivery).

WHY THIS EXISTS
---------------
The Career Daily Brief (career-ops/daily_brief.py, roster B23) already builds the
briefing, but it is a LOCAL FILE ONLY artifact: its own config records
`delivery.external_channels: []` and `external_channel_health: "not_verified"`.
Nothing in this organisation delivered it anywhere. This script is the thin,
delivery-only adapter that turns the brief the worker already produced into a
message-sized digest for a messaging surface.

It owns NO career state. It never scores, ranks, re-words or summarises with a
model. Every fact it prints is a line the brief worker itself wrote; this script
only (a) optionally refreshes the brief, (b) removes the fixed footers, and
(c) truncates the priority list to fit a message budget, saying how many items
were left out.

Safety contract
---------------
* No network call, no browser, no GUI, no credential read.
* Read-only against every tracker, ledger and other workflow's store. The only
  write it can perform is to invoke the brief worker's own `build`, which writes
  inside that worker's own runtime directory (runtime/career-ops/daily-brief/).
* Never presents a stale or missing brief as if it were fresh: an artifact older
  than --stale-hours is labelled STALE/UNKNOWN and the exit code is non-zero so a
  watchdog can tell the difference.
* No application, outreach, submission or LinkedIn action. Ever.

Exit codes
----------
0  a fresh brief digest was printed
3  the brief artifact is missing or stale (digest printed with an explicit label)
4  the optional refresh (--build) failed and no usable artifact was available
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONTROL_PLANE = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "daily-brief"
REPO_PYTHON = Path(
    r"C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
)
BRIEF_WORKER = CONTROL_PLANE / "career-ops" / "daily_brief.py"

# Lines the worker emits that are metadata about the artifact rather than career
# state. Dropped from the digest so the message budget goes to real content.
DROP_PREFIXES = ("Delivery:", "Safety:")

DEFAULT_BUDGET = 1850


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _refresh_brief(out_dir: Path, timeout: int) -> tuple[bool, str]:
    """Invoke the brief worker's own build. Returns (ok, note)."""
    if not BRIEF_WORKER.exists():
        return False, f"brief worker not found at {BRIEF_WORKER}"
    interpreter = REPO_PYTHON if REPO_PYTHON.exists() else Path(sys.executable)
    cmd = [
        str(interpreter),
        str(BRIEF_WORKER),
        "build",
        "--out-dir",
        str(out_dir),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(CONTROL_PLANE),
        )
    except subprocess.TimeoutExpired:
        return False, f"brief build timed out after {timeout}s"
    except OSError as exc:  # pragma: no cover - environment specific
        return False, f"brief build could not start: {exc}"
    if proc.returncode != 0:
        return False, f"brief build exited {proc.returncode}"
    return True, "refreshed"


def _read_latest(out_dir: Path) -> tuple[dict | None, str | None]:
    meta_path = out_dir / "latest.json"
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"no brief metadata at {meta_path}"
    except (OSError, ValueError) as exc:
        return None, f"brief metadata unreadable: {exc}"


def build_digest(out_dir: Path, budget: int, stale_hours: float) -> tuple[str, int]:
    meta, meta_error = _read_latest(out_dir)
    md_path = out_dir / "latest.md"

    if meta is None and not md_path.exists():
        msg = (
            "Career daily briefing — UNAVAILABLE\n"
            f"No brief artifact was found ({meta_error}).\n"
            "This is UNKNOWN, never 'no jobs': the brief worker has not produced "
            "an artifact yet. Nothing is invented to fill the gap."
        )
        return msg, 3

    header: list[str] = ["Career daily briefing"]
    stale_note = ""
    as_of = _parse_iso((meta or {}).get("generated_at"))
    if as_of is None:
        stale_note = (
            "Freshness: UNKNOWN — the artifact carries no readable generation "
            "timestamp."
        )
    else:
        age = datetime.now(timezone.utc) - as_of
        age_h = age.total_seconds() / 3600.0
        if age_h > stale_hours:
            stale_note = (
                f"Freshness: STALE — this brief was built {age_h:.1f}h ago "
                f"(threshold {stale_hours}h). It is NOT today's state."
            )

    md_lines: list[str] = []
    if md_path.exists():
        md_lines = md_path.read_text(encoding="utf-8").splitlines()

    # The worker's own first line carries the brief's as-of and its window:
    #   "Career Daily Brief — 2026-09-25T06:00:00+00:00 (window 24h)".
    # Reuse it rather than deriving a window of our own.
    window = None
    if md_lines:
        match = re.search(r"\(window\s+([^)]+)\)", md_lines[0])
        if match:
            window = match.group(1).strip()
    header.append(
        f"As of: {(meta or {}).get('generated_at', 'UNKNOWN')}"
        f" | window {window if window else 'not stated by the brief'}"
    )
    if stale_note:
        header.append(stale_note)

    body: list[str] = []
    if md_lines:
        for line in md_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(DROP_PREFIXES):
                continue
            if stripped.startswith("Career Daily Brief —"):
                continue
            body.append(line.rstrip())
    else:
        body.append("Brief text artifact missing (latest.md not found).")

    # Fixed tail is the pointer to the full artifact, never invented content.
    tail = [
        "",
        f"Full brief: {md_path} (+ brief-<digest>.json for the machine-readable form).",
        "Read-only aggregation: no submission, no outreach, no tracker write.",
    ]

    def render(b: list[str], t: list[str]) -> str:
        return "\n".join(header + [""] + b + t)

    dropped = 0
    while len(render(body, tail)) > budget and len(body) > 6:
        body.pop()
        dropped += 1

    if dropped:
        tail = [
            f"... {dropped} line(s) omitted to fit the message limit.",
        ] + tail

    text = render(body, tail)
    code = 3 if stale_note else 0
    return text, code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                        help="max characters to print (message limit safety)")
    parser.add_argument("--stale-hours", type=float, default=26.0,
                        help="age beyond which the brief is labelled STALE")
    parser.add_argument("--no-build", dest="build", action="store_false",
                        help="read the existing artifact without refreshing it")
    parser.add_argument("--build", dest="build", action="store_true",
                        help="refresh the brief via the brief worker before reading "
                             "(default for the scheduled daily delivery)")
    parser.add_argument("--build-timeout", type=int, default=240)
    parser.set_defaults(build=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    refresh_failed = ""
    if args.build:
        ok, note = _refresh_brief(out_dir, args.build_timeout)
        if not ok:
            refresh_failed = note

    text, code = build_digest(out_dir, args.budget, args.stale_hours)
    if refresh_failed and code == 0:
        text = text.replace(
            "Career daily briefing",
            f"Career daily briefing (using the previous artifact; refresh failed: "
            f"{refresh_failed})",
            1,
        )
    if refresh_failed and code == 3:
        code = 4
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
