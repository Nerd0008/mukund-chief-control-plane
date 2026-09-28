#!/usr/bin/env python3
"""Install/rollback the reversible Hermes E3 model-provider plugin.

This is the supported activation seam. It changes only the user model-provider
plugin directory; Hermes continues to own gateway auth, sessions, tools, skills,
approvals and the agent loop.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hermes-plugins" / "e3-model-provider"
TARGET = Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "plugins" / "model-providers" / "e3"


def install(*, target: Path = TARGET, dry_run: bool = False) -> dict:
    if not (SOURCE / "__init__.py").is_file() or not (SOURCE / "plugin.yaml").is_file():
        raise RuntimeError("source-controlled E3 model-provider plugin is incomplete")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target.parent / "backups" / f"chief-e3-provider-{stamp}"
    if not dry_run:
        if target.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup / "e3")
        target.mkdir(parents=True, exist_ok=True)
        for name in ("__init__.py", "plugin.yaml"):
            shutil.copy2(SOURCE / name, target / name)
    return {"action": "would-install" if dry_run else "installed",
            "source": str(SOURCE), "target": str(target), "backup": str(backup)}


def restore(backup: Path, *, target: Path = TARGET) -> dict:
    source = backup / "e3"
    if not source.is_dir():
        raise RuntimeError(f"backup is missing e3 plugin: {source}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return {"action": "restored", "target": str(target), "backup": str(backup)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target", type=Path, default=TARGET)
    ap.add_argument("--restore", type=Path)
    args = ap.parse_args()
    print(restore(args.restore, target=args.target) if args.restore else install(target=args.target, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
