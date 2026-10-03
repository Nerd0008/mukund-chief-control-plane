#!/usr/bin/env python3
"""Hermes cron launcher: daily job links (name + apply link) -> Discord.

Owner request (2026-10-03): "All the jobs you find daily I want the name and its
link to apply in this chat also daily."

The digest logic lives WITH the career-ops pipeline it reports on
(mukund-chief-control-plane/career-ops/daily_jobs_links.py) so the delivery
adapter is versioned next to the workflow it serves. Hermes cron only accepts
launchers inside its own scripts directory, so this file is a thin pass-through:
it runs the control-plane script and re-emits its stdout verbatim (which is the
message body the scheduler delivers) and its exit code.

No logic here: no scoring, no re-wording, no fallbacks that could turn an
unavailable run into an invented job list.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CONTROL_PLANE_SCRIPT = Path(
    r"C:\Users\mukun\Documents\mukund-chief-control-plane\career-ops\daily_jobs_links.py"
)
REPO_PYTHON = Path(
    r"C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
)


def main() -> int:
    if not CONTROL_PLANE_SCRIPT.exists():
        print(
            "Jobs found — launcher error\n"
            f"The digest script is missing at {CONTROL_PLANE_SCRIPT}.\n"
            "No job list is available; nothing is invented."
        )
        return 3
    interpreter = REPO_PYTHON if REPO_PYTHON.exists() else Path(sys.executable)
    proc = subprocess.run(
        [str(interpreter), str(CONTROL_PLANE_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=420,
        cwd=str(CONTROL_PLANE_SCRIPT.parent.parent),
    )
    stdout = (proc.stdout or "").strip()
    if stdout:
        print(stdout)
    else:
        print(
            "Jobs found — produced no output.\n"
            f"digest exit {proc.returncode}; "
            f"stderr: {(proc.stderr or '').strip()[:400]}"
        )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
