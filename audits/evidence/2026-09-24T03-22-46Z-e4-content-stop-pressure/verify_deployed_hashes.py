#!/usr/bin/env python3
"""Verify the deployed runtime modules hash-match the repository source.

Read-only. Reports repo vs deployed SHA-256 per module (E3 + the E4 module
deployed for the pressure view) and the unchanged E3 modules for comparison.

Usage: python verify_deployed_hashes.py [--out PATH]
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "exec-brain"

MODULES = [
    "e3_commands.py",
    "e3_cli.py",
    "resource_monitor.py",
    "e3_execution.py",
    "e3_shadow_orchestrator.py",
    "e3_execution_rehearsal.py",
]


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    lines = [f"runtime root: {RUNTIME_ROOT}",
             f"repo root:    {REPO_ROOT}", ""]
    all_ok = True
    for name in MODULES:
        repo_sha = sha256(REPO_ROOT / "exec-brain" / name)
        deployed_sha = sha256(RUNTIME_ROOT / name)
        match = repo_sha is not None and repo_sha == deployed_sha
        all_ok = all_ok and match
        lines.append(f"{name}: repo={repo_sha} deployed={deployed_sha} "
                     f"match={match}")
    lines.append("")
    lines.append("ALL_MATCH" if all_ok else "MISMATCH")

    text = "\n".join(lines) + "\n"
    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "deployed_hash_verification.txt")
    out_path.write_text(text, encoding="utf-8")
    print(text)
    print(f"written to {out_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
