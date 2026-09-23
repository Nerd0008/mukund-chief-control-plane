#!/usr/bin/env python3
"""Reproducible per-suite evidence runner for the chief control plane.

Every suite is executed as a real subprocess with an explicit import root, and
the runner records only what the process actually reported: UTC time, code SHA,
exact command, runtime/import roots, collected/passed/failed/error/skipped
counts, and the process exit code.

Design rules:
* nothing is inferred — an unparsable or unavailable suite is recorded as
  ``unavailable`` with the observed error, never silently counted as passing;
* suites are never run against the live remote queue: the queue suite is the
  isolated one in ``remote_queue/tests/test_queue.py``;
* the output is plain JSON + markdown so a historical run can be preserved
  separately and never overwritten by a later claim.

Usage:
    python scripts/evidence_runner.py [--label NAME] [--out-dir DIR] [--only SUBSTR]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
FAILED_RE = re.compile(r"^FAILED \((?P<body>.*)\)", re.MULTILINE)
OK_RE = re.compile(r"^OK(?: \((?P<body>.*)\))?", re.MULTILINE)

# Each suite declares the exact module path, the import root(s) it needs, and a
# guard path that must exist for the suite to be runnable at all.
SUITES = [
    {
        "name": "E1 executive brain runtime matrix",
        "script": "exec-brain/tests/test_eb.py",
        "pythonpath": [],
        "guard": RUNTIME_ROOT / "eb.py",
        "guard_note": "E1 runtime eb.py (LOCALAPPDATA/hermes/exec-brain/eb.py)",
    },
    {
        "name": "E2 governor / provider adapters",
        "script": "exec-brain/tests/test_governor.py",
        "pythonpath": [RUNTIME_ROOT],
        "guard": RUNTIME_ROOT / "governor.py",
        "guard_note": "E2 runtime governor.py (LOCALAPPDATA/hermes/exec-brain/governor.py)",
    },
    {
        "name": "E3 baseline",
        "script": "exec-brain/tests/test_e3.py",
        "pythonpath": [REPO_ROOT / "exec-brain"],
        "guard": None,
    },
    {
        "name": "E3 extended",
        "script": "exec-brain/tests/test_e3_extended.py",
        "pythonpath": [REPO_ROOT / "exec-brain"],
        "guard": None,
    },
    {
        "name": "E3 shadow orchestrator",
        "script": "exec-brain/tests/test_e3_shadow_orchestrator.py",
        "pythonpath": [REPO_ROOT / "exec-brain"],
        "guard": None,
    },
    {
        "name": "E3 production rehearsal (real path, isolation, E1/E2 boundary)",
        "script": "exec-brain/tests/test_e3_production_rehearsal.py",
        "pythonpath": [REPO_ROOT / "exec-brain"],
        "guard": None,
    },
    {
        "name": "E3 production execution leg (dispatch, verification gating, DAG/evidence persistence)",
        "script": "exec-brain/tests/test_e3_execution.py",
        "pythonpath": [REPO_ROOT / "exec-brain"],
        "guard": None,
    },
    {
        "name": "E3 production execution rehearsal driver (stubbed providers, isolated db)",
        "script": "exec-brain/tests/test_e3_execution_rehearsal.py",
        "pythonpath": [REPO_ROOT / "exec-brain"],
        "guard": None,
    },
    {
        "name": "E4 resource continuity + E5 safe mode (combined suite)",
        "script": "exec-brain/tests/test_e4e5.py",
        "pythonpath": [REPO_ROOT / "exec-brain"],
        "guard": None,
    },
    {
        "name": "Remote queue (isolated: disposable roots, mocked/live-free boundaries)",
        "script": "remote_queue/tests/test_queue.py",
        "pythonpath": [],
        "guard": None,
    },
    {
        "name": "Remote bridge watchdog/timeout hardening (isolated: fake Hermes child, no live queue)",
        "script": "remote_queue/tests/test_bridge_watchdog.py",
        "pythonpath": [],
        "guard": None,
    },
]


def _code_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def _parse_counts(output: str) -> dict:
    ran = RAN_RE.search(output)
    if not ran:
        return {"collected": None, "passed": None, "failed": None,
                "error": None, "skipped": None}
    collected = int(ran.group(1))

    failed = error = skipped = 0
    failed_match = FAILED_RE.search(output)
    if failed_match:
        body = failed_match.group("body")
        for key, pattern in (
            ("failed", r"failures=(\d+)"),
            ("error", r"errors=(\d+)"),
            ("skipped", r"skipped=(\d+)"),
        ):
            found = re.search(pattern, body)
            if found:
                if key == "failed":
                    failed = int(found.group(1))
                elif key == "error":
                    error = int(found.group(1))
                else:
                    skipped = int(found.group(1))
    else:
        ok_match = OK_RE.search(output)
        if ok_match and ok_match.group("body"):
            found = re.search(r"skipped=(\d+)", ok_match.group("body"))
            if found:
                skipped = int(found.group(1))

    return {
        "collected": collected,
        "passed": collected - failed - error - skipped,
        "failed": failed,
        "error": error,
        "skipped": skipped,
    }


def run_suite(suite: dict) -> dict:
    script = REPO_ROOT / suite["script"]
    record = {
        "suite": suite["name"],
        "script": suite["script"],
        "import_root": str(REPO_ROOT),
        "pythonpath": [str(p) for p in suite["pythonpath"]],
        "command": None,
        "status": "unavailable",
        "counts": {"collected": None, "passed": None, "failed": None,
                   "error": None, "skipped": None},
        "exit_code": None,
        "notes": None,
    }

    guard = suite.get("guard")
    if guard and not Path(guard).exists():
        record["notes"] = f"runnable guard missing: {suite.get('guard_note', guard)}"
        return record

    env = os.environ.copy()
    if suite["pythonpath"]:
        env["PYTHONPATH"] = os.pathsep.join([str(p) for p in suite["pythonpath"]])
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    command = [sys.executable, str(script)]
    record["command"] = " ".join(command) + (
        f"  (PYTHONPATH={env['PYTHONPATH']})" if suite["pythonpath"] else ""
    )

    try:
        result = subprocess.run(
            command, cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=1800, env=env,
        )
    except subprocess.TimeoutExpired:
        record["status"] = "unavailable"
        record["notes"] = "suite exceeded the 1800s evidence-runner timeout"
        return record

    output = (result.stdout or "") + (result.stderr or "")
    record["exit_code"] = result.returncode
    record["counts"] = _parse_counts(output)

    if record["counts"]["collected"] is None:
        record["status"] = "unavailable"
        record["notes"] = "no unittest summary line; suite did not run to completion"
        tail = output.strip().splitlines()[-3:]
        record["diagnostic_tail"] = [line[:300] for line in tail]
        return record

    if result.returncode == 0:
        record["status"] = "pass"
    else:
        record["status"] = "fail"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="isolated-queue-recovery")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--only", default=None,
                        help="run only suites whose name/script contains this substring")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    sha = _code_sha()

    selected = [s for s in SUITES
                if args.only is None or args.only.lower() in (s["name"] + " " + s["script"]).lower()]
    results = [run_suite(s) for s in selected]

    report = {
        "label": args.label,
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_sha": sha,
        "working_directory": str(REPO_ROOT),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "unittest_summary": {
            "suites_run": len(results),
            "suites_passed": sum(1 for r in results if r["status"] == "pass"),
            "suites_failed": sum(1 for r in results if r["status"] == "fail"),
            "suites_unavailable": sum(1 for r in results if r["status"] == "unavailable"),
            "tests_collected": sum(r["counts"]["collected"] or 0 for r in results),
            "tests_passed": sum(r["counts"]["passed"] or 0 for r in results),
        },
        "suites": results,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence" / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-{args.label}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"# Test evidence — {args.label}",
        "",
        f"- Run started (UTC): {report['run_started_utc']}",
        f"- Run finished (UTC): {report['run_finished_utc']}",
        f"- Code SHA: `{sha}`",
        f"- Python: {report['python_version']} ({report['python_executable']})",
        f"- Working directory / import root: `{REPO_ROOT}`",
        "",
        "| Suite | Status | Ran | Passed | Failed | Errors | Skipped | Exit | Import root |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        c = r["counts"]
        roots = ", ".join(r["pythonpath"]) or str(REPO_ROOT)
        lines.append(
            f"| {r['suite']} | {r['status']} | {c['collected']} | {c['passed']} | "
            f"{c['failed']} | {c['error']} | {c['skipped']} | {r['exit_code']} | `{roots}` |"
        )
    lines += [
        "",
        "Suite totals are recorded per suite only. No cross-suite aggregate is asserted here.",
        "",
        "## Exact commands",
        "",
    ]
    for r in results:
        lines.append(f"- {r['suite']}: `{r['command']}`")
        if r["notes"]:
            lines.append(f"  - note: {r['notes']}")
    (out_dir / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(report["unittest_summary"], indent=2))
    print(f"evidence written to {out_dir}")
    return 0 if report["unittest_summary"]["suites_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
