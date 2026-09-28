#!/usr/bin/env python3
"""Read-only provenance check for source-controlled Chief/E3 runtime modules."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "exec-brain"
RUNTIME_MODULES = (
    "e3_service.py", "chief_routing.py", "discord_chief_bridge.py", "department_dispatch.py",
)


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def compare_runtime(runtime_root: Path) -> dict:
    rows = []
    for name in RUNTIME_MODULES:
        source, runtime = SOURCE_ROOT / name, runtime_root / name
        source_hash, runtime_hash = sha256(source), sha256(runtime)
        rows.append({
            "module": name,
            "source_sha256": source_hash,
            "runtime_sha256": runtime_hash,
            "status": "MATCH" if source_hash and source_hash == runtime_hash else "DRIFT",
        })
    return {
        "read_only": True,
        "provider_calls": 0,
        "runtime_root": str(runtime_root),
        "modules": rows,
        "drift_count": sum(row["status"] == "DRIFT" for row in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=str(Path(os.environ.get("LOCALAPPDATA", "")) /
                                                       "hermes" / "exec-brain"))
    args = parser.parse_args()
    report = compare_runtime(Path(args.runtime_root))
    print(json.dumps(report, indent=2))
    return 0 if report["drift_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
