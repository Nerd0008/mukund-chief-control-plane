#!/usr/bin/env python3
"""Register/remove the Chief Career regional scan schedules (Windows Task Scheduler).

Safety properties:
  * Registered tasks run BOUNDED DRY-RUN SCANS only. They never write a tracker,
    never submit an application and never contact an employer.
  * Registration is idempotent (`schtasks /Create /F`) and fully reversible
    (`--remove`).
  * A region whose Career Ops lane config is missing is registered in a
    *refused* state: the runner exits non-zero with a truthful dependency note
    instead of scanning the UK lane under another region's label.

Usage:
  python career-ops/install_schedules.py --status
  python career-ops/install_schedules.py --install          # register all regions
  python career-ops/install_schedules.py --install --region uk
  python career-ops/install_schedules.py --remove --region uk
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load_schedules() -> dict:
    return json.loads((HERE / "regional_schedules.json").read_text(encoding="utf-8"))


def task_command(spec: dict, region: str, schedules: dict) -> str:
    """Build the /TR value.

    schtasks rejects a /TR longer than 261 characters, so the interpreter path,
    the CLI path, the log directory and the redirect all live in the checked-in
    launcher `career-ops/run_scheduled_scan.cmd`; only the region is passed here.
    """
    cp = Path(schedules["control_plane"])
    launcher = cp / "career-ops" / "run_scheduled_scan.cmd"
    return f'"{launcher}" {region}'


def brief_spec(schedules: dict) -> dict:
    return schedules.get("brief") or {}


def brief_command(schedules: dict) -> str:
    """The Career Daily Brief has no region argument; its launcher takes none."""
    cp = Path(schedules["control_plane"])
    spec = brief_spec(schedules)
    launcher = cp / spec.get("runner", "career-ops/run_scheduled_brief.cmd")
    return f'"{launcher}"'


def install_named(name: str, when: str, cmd: str, extra: dict | None = None) -> dict:
    args = ["schtasks", "/Create", "/TN", name, "/TR", cmd, "/SC", "DAILY", "/ST", when, "/F"]
    proc = subprocess.run(args, capture_output=True, text=True, shell=False)
    return {"task_name": name, "time": when, "command": cmd,
            "exit_code": proc.returncode, "ok": proc.returncode == 0,
            "output": (proc.stdout or proc.stderr).strip(), **(extra or {})}


def remove_named(name: str, extra: dict | None = None) -> dict:
    proc = subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"],
                          capture_output=True, text=True, shell=False)
    return {"task_name": name, "exit_code": proc.returncode, "ok": proc.returncode == 0,
            "output": (proc.stdout or proc.stderr).strip(), **(extra or {})}


def install_brief(schedules: dict, time_override: str | None) -> dict:
    spec = brief_spec(schedules)
    if not spec:
        return {"task_name": None, "ok": False, "error": "no 'brief' schedule declared"}
    return install_named(spec["task_name"], time_override or spec["time"],
                         brief_command(schedules),
                         {"kind": "career-daily-brief", "mode": spec.get("mode"),
                          "delivery": spec.get("delivery")})


def query(task_name: str) -> dict:
    proc = subprocess.run(["schtasks", "/Query", "/TN", task_name, "/FO", "LIST"],
                          capture_output=True, text=True, shell=False)
    return {"registered": proc.returncode == 0, "output": (proc.stdout or proc.stderr).strip()}


def install(region: str, spec: dict, schedules: dict, time_override: str | None) -> dict:
    name = spec["task_name"]
    when = time_override or spec["time"]
    cmd = task_command(spec, region, schedules)
    args = ["schtasks", "/Create", "/TN", name, "/TR", cmd,
            "/SC", "DAILY", "/ST", when, "/F"]
    proc = subprocess.run(args, capture_output=True, text=True, shell=False)
    return {
        "region": region,
        "task_name": name,
        "time": when,
        "lane_ready": bool(spec.get("ready")),
        "command": cmd,
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
        "output": (proc.stdout or proc.stderr).strip(),
    }


def remove(region: str, spec: dict) -> dict:
    name = spec["task_name"]
    proc = subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"],
                          capture_output=True, text=True, shell=False)
    return {"region": region, "task_name": name, "exit_code": proc.returncode,
            "ok": proc.returncode == 0, "output": (proc.stdout or proc.stderr).strip()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true")
    g.add_argument("--remove", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--install-brief", action="store_true",
                   help="register the morning Career Daily Brief task")
    g.add_argument("--remove-brief", action="store_true")
    ap.add_argument("--region", action="append")
    ap.add_argument("--time", dest="time_override")
    args = ap.parse_args(argv)

    schedules = load_schedules()
    results = []

    if args.install_brief or args.remove_brief:
        spec = brief_spec(schedules)
        if args.status or not spec:
            results.append({"task_name": None, "ok": False,
                            "error": "no 'brief' schedule declared in regional_schedules.json"})
        elif args.install_brief:
            results.append(install_brief(schedules, args.time_override))
        else:
            results.append(remove_named(spec["task_name"], {"kind": "career-daily-brief"}))
        print(json.dumps({
            "action": "install-brief" if args.install_brief else "remove-brief",
            "schtasks_available": shutil.which("schtasks") is not None,
            "results": results,
            "note": "The Daily Brief task performs read-only aggregation and writes only its own "
                    "runtime artifact; it never writes a tracker, submits, or delivers externally.",
        }, indent=2))
        return 0 if all(r.get("ok") for r in results) else 1

    regions = args.region or list(schedules["regions"])
    for region in regions:
        if region not in schedules["regions"]:
            results.append({"region": region, "ok": False, "error": "unknown region"})
            continue
        spec = schedules["regions"][region]
        if args.status:
            q = query(spec["task_name"])
            q.update({"region": region, "time": spec["time"], "lane_ready": spec.get("ready"),
                      "mode": "bounded dry-run scan; never writes a tracker"})
            results.append(q)
        elif args.install:
            results.append(install(region, spec, schedules, args.time_override))
        else:
            results.append(remove(region, spec))

    if args.status and brief_spec(schedules):
        spec = brief_spec(schedules)
        q = query(spec["task_name"])
        q.update({"region": None, "kind": "career-daily-brief", "time": spec["time"],
                  "mode": spec.get("mode"), "delivery": spec.get("delivery")})
        results.append(q)

    print(json.dumps({
        "action": "status" if args.status else ("install" if args.install else "remove"),
        "schtasks_available": shutil.which("schtasks") is not None,
        "results": results,
        "note": "Scheduled tasks perform dry-run scans only; tracker writes stay an explicit backed-up step.",
    }, indent=2))
    return 0 if all(r.get("ok", True) for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
