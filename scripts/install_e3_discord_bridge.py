#!/usr/bin/env python3
"""Install the E3 Discord bridge and prepare LongCat evaluation capabilities.

No provider call is made. No credential is read. Stage 2 state is not changed.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = REPO_ROOT / "hermes-plugins" / "e3-discord-router"
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

EVALUATION_ROWS = {
    "code": "builder",
    "review": "critic",
    "research": "researcher",
    "analysis": "data-analyst",
    "writing": "writer",
    "data-processing": "data-analyst",
    "ops": "builder",
    "decision-support": "builder",
    "extraction": "builder",
    "summarization": "writer",
    "verification": "verifier",
    "other": "builder",
}


def hermes_home() -> Path:
    explicit = os.environ.get("HERMES_HOME")
    return Path(explicit).expanduser() if explicit else Path.home() / ".hermes"


def install_plugin(*, dry_run: bool) -> Path:
    dest = hermes_home() / "plugins" / "e3-discord-router"
    if not PLUGIN_SOURCE.is_dir():
        raise RuntimeError(f"plugin source missing: {PLUGIN_SOURCE}")

    print(f"plugin source: {PLUGIN_SOURCE}")
    print(f"plugin target: {dest}")
    if dry_run:
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = dest.parent / f"e3-discord-router.backup-{stamp}"
        shutil.copytree(dest, backup)
        print(f"plugin backup: {backup}")
        shutil.rmtree(dest)

    shutil.copytree(PLUGIN_SOURCE, dest)
    print("plugin installed")
    return dest


def prepare_longcat(*, dry_run: bool) -> None:
    if not RUNTIME_ROOT.is_dir():
        raise RuntimeError(f"E3 runtime root missing: {RUNTIME_ROOT}")

    sys.path.insert(0, str(RUNTIME_ROOT))
    from capability_registry import CapabilityRegistry
    from worker_registry import WorkerRegistry

    worker = WorkerRegistry().get_worker("longcat-2.0")
    if not worker:
        raise RuntimeError("longcat-2.0 missing from deployed worker registry")
    if not worker.get("routable"):
        raise RuntimeError("deployed longcat-2.0 is not routable; deploy the recovery branch first")

    db = RUNTIME_ROOT / "orchestration.db"
    print(f"orchestration db: {db}")
    for family, role in EVALUATION_ROWS.items():
        print(f"  longcat-2.0  {family}/{role} -> EVALUATING")
    if dry_run:
        return

    con = sqlite3.connect(str(db))
    try:
        reg = CapabilityRegistry(con)
        for family, role in EVALUATION_ROWS.items():
            reg.register_worker(
                "longcat-2.0",
                worker.get("provider") or "longcat",
                worker.get("api_model_id") or worker.get("model") or "LongCat-2.0",
                roles=[role],
                state="EVALUATING",
                task_family=family,
            )
    finally:
        con.close()
    print("LongCat evaluation capabilities prepared")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--plugin-only", action="store_true")
    ap.add_argument("--capabilities-only", action="store_true")
    args = ap.parse_args()

    if args.plugin_only and args.capabilities_only:
        ap.error("--plugin-only and --capabilities-only are mutually exclusive")

    if not args.capabilities_only:
        install_plugin(dry_run=args.dry_run)
    if not args.plugin_only:
        prepare_longcat(dry_run=args.dry_run)

    print()
    print("Stage 2 state was NOT changed.")
    print("Restart Hermes_Gateway only after the new regression evidence is clean and Stage 2 is re-enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
