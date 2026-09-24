#!/usr/bin/env python3
"""Deployment inventory collector (read-only, no secrets, no network).

Emits a JSON inventory of the facts the deployment manifest needs:

* interpreter/runtime versions and the paths the runtime actually uses;
* E3 worker provider/interface/model identity plus the **names** of the
  credential stores each adapter resolves against (never a credential value);
* the network endpoints each worker adapter is configured to call;
* the local state/database paths with size + presence;
* the scheduled-task set that keeps the runtime alive;
* third-party Python imports used by the runtime code.

It reads only adapter *configuration* (introspection of `config`), and it never
dereferences a credential: `_resolve_auth()` is not called here.

Usage:
    python scripts/deployment_inventory.py [--out PATH]
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"
HERMES_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"

SECRET_SUBSTRINGS = ("key", "secret", "token", "password", "apikey", "auth_value",
                     "credential_blob")
# Config keys that *name* a store rather than hold a value.
NAME_ONLY_KEYS = {"credential_target", "env_var", "auth_env_var"}

TASK_NAMES = [
    "Hermes_Gateway", "HermesRemoteQueuePoller", "ChiefDiscordSync",
    "ChiefCareerBrief", "ChiefCareerScan-UK", "ChiefCareerScan-Dubai",
    "ChiefCareerScan-Japan", "ChiefCareerScan-Singapore",
]

STATE_PATHS = [
    RUNTIME_ROOT / "exec_brain.db",
    RUNTIME_ROOT / "governor.db",
    RUNTIME_ROOT / "orchestration.db",
    RUNTIME_ROOT / "chain-head.json",
    RUNTIME_ROOT / "gov-chain-head.json",
    RUNTIME_ROOT / "deepseek-config.json",
    HERMES_ROOT / "state.db",
    HERMES_ROOT / "kanban.db",
    HERMES_ROOT / "shared-state.db",
    HERMES_ROOT / "cron" / "executions.db",
]


def scrub(value):
    """Recursively redact anything that looks like a secret *value*."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            lowered = k.lower()
            if lowered in NAME_ONLY_KEYS:
                out[k] = v
            elif any(s in lowered for s in SECRET_SUBSTRINGS):
                out[k] = "<redacted:name-only>"
            else:
                out[k] = scrub(v)
        return out
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def worker_inventory():
    sys.path.insert(0, str(REPO_ROOT / "exec-brain"))
    sys.path.insert(0, str(RUNTIME_ROOT))
    import generic_openai_adapter as goa
    from worker_registry import WorkerRegistry

    registry = WorkerRegistry()
    all_workers = registry.get_all_workers()
    if isinstance(all_workers, dict):
        entries = [dict(v, worker_id=k) for k, v in all_workers.items()]
    else:
        entries = list(all_workers)
    workers = []
    for entry in entries:
        wid = entry.get("worker_id") or entry.get("id")
        record = {
            "worker_id": wid,
            "registry_provider": entry.get("provider"),
            "registry_model": entry.get("model"),
            "registry_interface": entry.get("interface"),
            "registry_routable": entry.get("routable"),
            "registry_qualification": entry.get("qualification")
            or entry.get("qualification_state"),
        }
        try:
            adapter = goa.get_adapter(wid)
            cfg = scrub(dict(adapter.config))
            record["adapter_config"] = cfg
            record["adapter_env_var_names"] = sorted(
                k for k in (adapter.config or {})
                if k.lower() in NAME_ONLY_KEYS)
        except Exception as exc:  # defensive: an adapter may not exist yet
            record["adapter_config"] = None
            record["adapter_error"] = type(exc).__name__
        workers.append(record)
    return workers


def scheduled_tasks():
    out = []
    for name in TASK_NAMES:
        rec: dict = {"task_name": name}
        try:
            proc = subprocess.run(
                ["schtasks", "/query", "/tn", name, "/xml"],
                capture_output=True, text=True, timeout=60)
            xml = proc.stdout or ""
            rec["query_ok"] = proc.returncode == 0
            for tag in ("Command", "Arguments", "StartBoundary", "LogonType",
                        "Interval", "Enabled", "UserId"):
                m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.S)
                if m:
                    rec[tag[0].lower() + tag[1:]] = m.group(1).strip()
            rec["triggers"] = {
                "time": "<TimeTrigger>" in xml,
                "calendar": "<CalendarTrigger>" in xml,
                "logon": "<LogonTrigger>" in xml,
                "boot": "<BootTrigger>" in xml,
            }
            rec["restart_on_failure"] = "<RestartOnFailure>" in xml
            rec["start_when_available"] = "<StartWhenAvailable>true<" in xml
        except Exception as exc:
            rec["query_ok"] = False
            rec["error"] = type(exc).__name__
        out.append(rec)
    return out


def state_paths():
    out = []
    for path in STATE_PATHS:
        rec: dict = {"path": str(path), "exists": path.exists()}
        if path.exists():
            stat = path.stat()
            rec["size_bytes"] = stat.st_size
            rec["modified_utc"] = datetime.fromtimestamp(
                stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
            if path.suffix == ".db":
                try:
                    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                    tables = [r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "ORDER BY name")]
                    rec["tables"] = tables
                    rec["integrity_check"] = con.execute(
                        "PRAGMA integrity_check").fetchone()[0]
                    con.close()
                except Exception as exc:
                    rec["db_error"] = f"{type(exc).__name__}: {exc}"
        out.append(rec)
    return out


STDLIB_HINTS = {"argparse", "json", "os", "sys", "re", "sqlite3", "pathlib",
                "subprocess", "datetime", "hashlib", "shutil", "ctypes",
                "typing", "unittest", "tempfile", "time", "collections",
                "itertools", "math", "random", "uuid", "csv", "textwrap",
                "dataclasses", "enum", "functools", "logging", "threading",
                "glob", "io", "statistics", "difflib", "string", "base64",
                "traceback", "contextlib", "warnings", "zipfile", "shlex",
                "codecs", "secrets", "email", "http", "urllib", "socket",
                "signal", "platform", "struct", "copy", "abc", "inspect",
                "operator", "ast", "configparser", "decimal", "fractions",
                "gc", "pickle", "pprint", "queue", "sched", "ssl", "unittest",
                "fnmatch", "importlib", "shlex", "unicodedata", "binascii",
                "getpass", "winreg", "ctypes", "difflib", "filecmp", "zipfile",
                "tarfile", "gzip", "stat", "locale", "textwrap", "numbers"}


def third_party_imports():
    """Classify imports into local-project modules and true third-party packages."""
    local_names = set()
    roots = [REPO_ROOT / "exec-brain", REPO_ROOT / "career-ops",
             REPO_ROOT / "company-watch", REPO_ROOT / "remote_queue",
             REPO_ROOT / "remote-queue", REPO_ROOT / "scripts",
             RUNTIME_ROOT]
    for root in roots:
        if root.exists():
            for py in root.glob("*.py"):
                local_names.add(py.stem)
    seen = {}
    pattern = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)")
    for base in roots:
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if "__pycache__" in py.parts or "tests" in py.parts:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                m = pattern.match(line)
                if not m:
                    continue
                mod = m.group(1)
                if mod in STDLIB_HINTS or mod in local_names:
                    continue
                if mod.startswith("_") or mod.startswith("e3_"):
                    continue
                seen.setdefault(mod, set()).add(
                    str(py.relative_to(REPO_ROOT)).replace("\\", "/")
                    if REPO_ROOT in py.parents else str(py))
    return {mod: sorted(files) for mod, files in sorted(seen.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    inventory = {
        "artifact": "deployment inventory (read-only collector)",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": {
            "platform": platform.platform(),
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "note": "python_executable is the interpreter that ran this collector",
        },
        "paths": {
            "repo_root": str(REPO_ROOT),
            "runtime_root": str(RUNTIME_ROOT),
            "hermes_root": str(HERMES_ROOT),
        },
        "workers": worker_inventory(),
        "scheduled_tasks": scheduled_tasks(),
        "state_paths": state_paths(),
        "third_party_imports": third_party_imports(),
        "collector_guarantees": [
            "read-only; made no network call",
            "no credential value read, dereferenced, printed or stored",
            "credential stores referenced by name only",
        ],
    }
    text = json.dumps(inventory, indent=2, default=str)
    digest = {
        "generated_utc": inventory["generated_utc"],
        "python_version": inventory["host"]["python_version"],
        "paths": inventory["paths"],
        "worker_ids": [w["worker_id"] for w in inventory["workers"]],
        "workers_without_adapter": [w["worker_id"] for w in inventory["workers"]
                                    if not w.get("adapter_config")],
        "scheduled_tasks": {t["task_name"]: {
            "triggers": t.get("triggers"), "logon_type": t.get("logonType"),
            "restart_on_failure": t.get("restart_on_failure")}
            for t in inventory["scheduled_tasks"]},
        "state_paths_missing": [s["path"] for s in inventory["state_paths"]
                                if not s["exists"]],
        "integrity_not_ok": [s["path"] for s in inventory["state_paths"]
                             if s.get("integrity_check") not in (None, "ok")],
        "third_party_imports": sorted(inventory["third_party_imports"]),
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        digest["out"] = str(out)
        print(json.dumps(digest, indent=2))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
