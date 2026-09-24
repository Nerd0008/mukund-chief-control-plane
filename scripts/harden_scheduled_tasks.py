#!/usr/bin/env python3
"""Harden the owned Hermes/Chief scheduled tasks and register the operational
service schedules — reversible, verifiable, plan-first.

Owner-approved scope (recorded in
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md` and the running
queue record `agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24`):

* remove `DisallowStartIfOnBatteries` / `StopIfGoingOnBatteries` from the seven
  affected Hermes/Chief tasks;
* stop the interactive-idle stop condition (`StopOnIdleEnd` -> false) so a task
  is not killed when the laptop simply goes idle;
* set `StartWhenAvailable` so a missed schedule run still happens after the
  machine returns (this is what makes a task survive a reboot without needing a
  logon trigger on a heavy daily job);
* add a *logon* trigger only to the two light periodic tasks (queue poller,
  Discord sync) so they resume immediately after a restart;
* register the four owner-approved operational service schedules (backup, log
  rotation, health snapshot, morning brief) from the checked-in definitions.

Hard constraints this script respects:

* it NEVER switches a task to SYSTEM or another account — the owner's
  user-scoped Windows Credential Manager secrets must stay readable, so every
  task keeps `<LogonType>InteractiveToken</LogonType>` for the owner's own SID;
* it NEVER touches the legacy `Mukund Chief of Staff` task (its disposition is
  an owner decision and it is kept as a rollback donor);
* it writes a byte-exact backup of every live definition it is about to replace,
  so `--restore` is a real rollback rather than a rebuild;
* it never reboots, signs out or power-cycles the machine.

Usage
    python scripts/harden_scheduled_tasks.py --plan
    python scripts/harden_scheduled_tasks.py --apply
    python scripts/harden_scheduled_tasks.py --verify
    python scripts/harden_scheduled_tasks.py --restore --backup-dir DIR
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFINITIONS_DIR = REPO_ROOT / "deployments" / "service-definitions"
BACKUP_ROOT = DEFINITIONS_DIR / "backups"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

# The seven tasks that carried DisallowStartIfOnBatteries=true. The owner
# approved removing that gate for all of them.
HARDENED_TASKS = [
    "HermesRemoteQueuePoller",
    "ChiefDiscordSync",
    "ChiefCareerBrief",
    "ChiefCareerScan-UK",
    "ChiefCareerScan-Dubai",
    "ChiefCareerScan-Japan",
    "ChiefCareerScan-Singapore",
]

# Light periodic tasks: also get a logon trigger so they resume after a restart.
LOGON_TRIGGER_TASKS = {"HermesRemoteQueuePoller": "PT2M", "ChiefDiscordSync": "PT5M"}

# `Hermes_Gateway` is already hardened (battery false + StartWhenAvailable +
# logon trigger); it is exported for the record but never modified.
REFERENCE_TASKS = ["Hermes_Gateway"]

# Recorded, never imported, never modified: rollback donor kept for the owner.
LEGACY_TASKS = ["Mukund Chief of Staff"]

# Owner-approved operational service schedules. Cadence is deliberately bounded
# and staggered away from the existing scan/brief windows (23:45-00:00 scans,
# 07:00 career brief).
PYTHON = r"C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"

OPERATIONAL_TASKS = [
    {
        "name": "ChiefOperationalBackup",
        "service": "backup",
        "time": "02:30",
        "what": ("operational backup of the declared state set (7 SQLite databases + "
                 "E1/E2 chain heads) with 7-snapshot retention; snapshot root stays "
                 "outside the repository at %LOCALAPPDATA%\\hermes\\backups\\operational"),
    },
    {
        "name": "ChiefLogRotation",
        "service": "logs",
        "time": "03:00",
        "what": ("bounded log rotation/retention over the declared live log paths "
                 "(archive above 5 MB, keep the newest 5 archives per log)"),
    },
    {
        "name": "ChiefMorningBrief",
        "service": "brief",
        "time": "06:30",
        "what": ("Morning Chief Brief aggregate written to runtime\\chief\\morning-brief; "
                 "LOCAL ARTIFACT ONLY - no external delivery destination is configured"),
    },
    {
        "name": "ChiefHealthSnapshot",
        "service": "health",
        "time": "08:00",
        "what": ("deterministic health snapshot (databases, queue, tasks, credentials "
                 "presence, log sizes) written to runtime\\chief\\health-snapshot"),
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_sha() -> str:
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                              capture_output=True, text=True, timeout=60)
        return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


# --------------------------------------------------------------------------- #
# Live definition access
# --------------------------------------------------------------------------- #

def export_task_xml(name: str) -> dict:
    """Byte-exact live definition. Read-only."""
    proc = run(["schtasks", "/Query", "/TN", name, "/XML"])
    if proc.returncode != 0:
        return {"task": name, "exists": False,
                "error": (proc.stdout or proc.stderr).strip()}
    return {"task": name, "exists": True, "raw": proc.stdout}


def normalize(xml: str) -> str:
    """Strip the doubled carriage returns bash/schtasks redirection introduces.

    The XML *declaration* is deliberately left as ``encoding="UTF-16"``: this is
    what the Task Scheduler XML loader requires. Feeding it ``encoding="UTF-8"``
    (with matching UTF-8 bytes) fails with
    ``(1,40)::ERROR: unable to switch the encoding``; the same document with the
    UTF-16 declaration and ASCII content imports successfully. Verified on this
    host 2026-09-24 (see the hardening evidence bundle).
    """
    return xml.replace("\r\n", "\n").replace("\r", "\n")


# --------------------------------------------------------------------------- #
# The hardening transform
# --------------------------------------------------------------------------- #

def harden(xml: str, *, logon_delay: str | None = None) -> tuple[str, list[str]]:
    """Return (hardened_xml, list_of_applied_changes)."""
    changes: list[str] = []
    text = xml

    before = text
    text = text.replace("<DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>",
                        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>")
    if text != before:
        changes.append("DisallowStartIfOnBatteries: true -> false")

    before = text
    text = text.replace("<StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>",
                        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>")
    if text != before:
        changes.append("StopIfGoingOnBatteries: true -> false")

    before = text
    text = text.replace("<StopOnIdleEnd>true</StopOnIdleEnd>",
                        "<StopOnIdleEnd>false</StopOnIdleEnd>")
    if text != before:
        changes.append("StopOnIdleEnd: true -> false (an idle laptop no longer stops it)")

    if "<StartWhenAvailable>" not in text:
        text = text.replace("  </Settings>",
                            "    <StartWhenAvailable>true</StartWhenAvailable>\n  </Settings>",
                            1)
        changes.append("StartWhenAvailable: added (true)")

    if logon_delay and "<LogonTrigger>" not in text:
        text = text.replace(
            "  <Triggers>\n",
            "  <Triggers>\n    <LogonTrigger>\n"
            f"      <Delay>{logon_delay}</Delay>\n"
            "    </LogonTrigger>\n",
            1)
        changes.append(f"LogonTrigger: added (delay {logon_delay})")

    return text, changes


# --------------------------------------------------------------------------- #
# Operational service definitions
# --------------------------------------------------------------------------- #

NEW_TASK_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>{date}</Date>
    <Author>{author}</Author>
    <URI>\\{name}</URI>
    <Description>{description}</Description>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>{sid}</UserId>
      <LogonType>InteractiveToken</LogonType>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start_boundary}</StartBoundary>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>"{launcher}"</Command>
      <Arguments>{service}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _principal_from(xml: str) -> dict:
    sid = re.search(r"<UserId>(.*?)</UserId>", xml, re.S)
    author = re.search(r"<Author>(.*?)</Author>", xml, re.S)
    return {"sid": sid.group(1).strip() if sid else None,
            "author": author.group(1).strip() if author else None}


def build_operational_definition(spec: dict, principal: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return NEW_TASK_TEMPLATE.format(
        date=today,
        author=principal["author"],
        name=spec["name"],
        description=(f"Chief operational service: {spec['what']}. Interactive user token "
                     "is preserved so the owner's user-scoped Windows Credential Manager "
                     "secrets stay readable. No external delivery destination."),
        sid=principal["sid"],
        start_boundary=f"{datetime.now().strftime('%Y-%m-%d')}T{spec['time']}:00",
        launcher=str(REPO_ROOT / "scripts" / "run_scheduled_ops.cmd"),
        service=spec["service"],
    )


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #

def write_definitions(*, apply: bool) -> dict:
    """Transform live definitions, write the checked-in set, import them."""
    tasks = HARDENED_TASKS + REFERENCE_TASKS + LEGACY_TASKS
    live = {t: export_task_xml(t) for t in tasks}

    missing = [t for t, rec in live.items() if not rec["exists"] and t not in LEGACY_TASKS]
    if missing:
        return {"ok": False, "error": f"live task(s) not found: {missing}"}

    principal = None
    for t in HARDENED_TASKS + REFERENCE_TASKS:
        if live[t]["exists"]:
            principal = _principal_from(live[t]["raw"])
            break
    if not principal or not principal.get("sid"):
        return {"ok": False, "error": "could not resolve the owner SID from a live task"}

    report: dict = {"artifact": "scheduled-task hardening + operational schedules",
                    "run_utc": utc_now(), "code_sha": git_sha(),
                    "mode": "apply" if apply else "plan",
                    "battery_gating_removed_from": HARDENED_TASKS,
                    "legacy_tasks_recorded_not_modified": LEGACY_TASKS,
                    "logon_type_preserved": "InteractiveToken (owner SID "
                                            f"{principal['sid']}) - never SYSTEM",
                    "definition_encoding_note": (
                        "checked-in definitions keep the Task Scheduler XML "
                        "'encoding=\"UTF-16\"' declaration: the loader REJECTS "
                        "encoding=\"UTF-8\" with '(1,40)::ERROR: unable to switch the "
                        "encoding' even when the bytes match. Verified on this host."),
                    "changes": {}, "definitions_written": [], "imported": [],
                    "live_state_modified": False}

    backup_dir = None
    if apply:
        backup_dir = BACKUP_ROOT / f"{_stamp()}-pre-hardening"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for t, rec in live.items():
            if rec["exists"]:
                safe = t.replace(" ", "_")
                (backup_dir / f"{safe}.xml").write_text(rec["raw"], encoding="utf-8")
        report["backup_dir"] = str(backup_dir)

    body = {}
    for t in HARDENED_TASKS:
        hardened, changes = harden(normalize(live[t]["raw"]),
                                   logon_delay=LOGON_TRIGGER_TASKS.get(t))
        report["changes"][t] = changes
        body[t] = hardened
    for t in REFERENCE_TASKS + LEGACY_TASKS:
        if live[t]["exists"]:
            report["changes"][t] = ["none (recorded; already hardened / legacy donor)"]

    for spec in OPERATIONAL_TASKS:
        body[spec["name"]] = build_operational_definition(spec, principal)
        report["changes"][spec["name"]] = [
            "new definition: daily " + spec["time"] + " -> run_scheduled_ops.cmd "
            + spec["service"]]

    if apply:
        for name, text in body.items():
            path = DEFINITIONS_DIR / f"{name}.xml"
            path.write_text(text, encoding="utf-8")
            report["definitions_written"].append(str(path))
            proc = run(["schtasks", "/Create", "/TN", name, "/XML", str(path), "/F"])
            report["imported"].append({
                "task": name, "exit_code": proc.returncode, "ok": proc.returncode == 0,
                "output": (proc.stdout or proc.stderr).strip().splitlines()[-1]
                if (proc.stdout or proc.stderr).strip() else ""})
        report["live_state_modified"] = any(r["ok"] for r in report["imported"])

    return report


def restore(backup_dir: Path) -> dict:
    """Re-import every task definition found in a backup directory."""
    files = sorted(Path(backup_dir).glob("*.xml"))
    if not files:
        return {"ok": False, "error": f"no task definitions under {backup_dir}"}
    results = []
    for f in files:
        name = f.stem.replace("_", " ")
        # Exact names win when known; otherwise the file stem is the task name.
        known = HARDENED_TASKS + REFERENCE_TASKS + [s["name"] for s in OPERATIONAL_TASKS]
        exact = next((k for k in known if k.replace(" ", "_") == f.stem), None)
        if exact:
            name = exact
        if name in LEGACY_TASKS:
            results.append({"task": name, "skipped": True,
                            "reason": "legacy donor is never imported by this tool"})
            continue
        proc = run(["schtasks", "/Create", "/TN", name, "/XML", str(f), "/F"])
        results.append({"task": name, "exit_code": proc.returncode,
                        "ok": proc.returncode == 0,
                        "output": (proc.stdout or proc.stderr).strip()})
    return {"artifact": "scheduled-task restore", "run_utc": utc_now(),
            "backup_dir": str(backup_dir), "results": results,
            "ok": all(r.get("ok", True) for r in results)}


def verify() -> dict:
    """Read-only verification of the live state after a change."""
    import operational_services as ops  # noqa: E402

    names = HARDENED_TASKS + REFERENCE_TASKS + [s["name"] for s in OPERATIONAL_TASKS] \
        + LEGACY_TASKS
    tasks = ops.collect_tasks(names)
    analysis = ops.analyse_persistence(tasks)
    return {
        "artifact": "scheduled-task hardening verification",
        "run_utc": utc_now(), "code_sha": git_sha(), "read_only": True,
        "owned_tasks": HARDENED_TASKS + [s["name"] for s in OPERATIONAL_TASKS],
        "tasks": {n: {k: v for k, v in (t.get("definition") or {}).items()
                      if k in ("logon_type", "triggers", "start_when_available",
                               "disallow_on_batteries", "stop_on_batteries",
                               "execution_time_limit")} | {"state": t.get("state"),
                                                           "exists": t.get("exists")}
                  for n, t in tasks.items()},
        "verdicts": analysis["verdicts"],
        "unverified_after_reboot": analysis["unverified_after_reboot"],
        "still_battery_gated": [n for n, t in tasks.items()
                                if (t.get("definition") or {}).get("disallow_on_batteries")],
        "owner_checklist": analysis["owner_checklist"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--verify", action="store_true")
    g.add_argument("--restore", action="store_true")
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.plan or args.apply:
        report = write_definitions(apply=args.apply)
    elif args.verify:
        report = verify()
    else:
        if not args.backup_dir:
            ap.error("--restore requires --backup-dir")
        report = restore(Path(args.backup_dir))

    print(json.dumps(report, indent=2, default=str))
    if report.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
