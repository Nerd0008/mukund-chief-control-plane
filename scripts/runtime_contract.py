"""Read-only runtime inventory, derived from the deployment declaration.

Configuration/state filenames are declared, never read. Undeclared source,
backups at the root, arbitrary databases and disguised directories fail closed.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

BASE_MODULES = ("eb.py", "governor.py", "adapters.py")
STATE_FILES = {
    "chain-head.json", "gov-chain-head.json", "telemetry.log", "telemetry.lock",
    "prune.log", "deepseek-config.json", "e3-stage2-state.json",
    "native-binding.json", "router-brain-policy.json",
}
DATABASES = {"exec_brain.db", "governor.db", "orchestration.db"}
DIRECTORIES = {"backups", "tests", "__pycache__"}
LEGACY_TESTS = {"test_governor.py": "tests/test_governor.py", "test_e3.py": "tests/test_e3.py"}


def source_files(source_root=None):
    from deploy_e3_runtime import E3_MODULES, SRC_DIR
    root = Path(source_root) if source_root is not None else SRC_DIR
    names = (*BASE_MODULES, *E3_MODULES)
    return {**{name: root / name for name in names},
            **{name: root / target for name, target in LEGACY_TESTS.items()}}


def audit_runtime(runtime_root, *, source_root=None):
    root = Path(runtime_root)
    sources = source_files(source_root)
    missing = sorted(name for name, path in sources.items() if not path.is_file())
    files = set(sources) | STATE_FILES | DATABASES
    files |= {name + suffix for name in DATABASES for suffix in ("-wal", "-shm")}
    unexpected, wrong_type = [], []
    if not root.is_dir():
        return {"ok": False, "unexpected": [], "wrong_type": [],
                "missing_source": missing, "runtime_missing": True}
    for path in root.iterdir():
        if path.name not in files | DIRECTORIES:
            unexpected.append(path.name)
        elif path.is_symlink() or (path.name in DIRECTORIES) != path.is_dir():
            wrong_type.append(path.name)
    return {"ok": not (unexpected or wrong_type or missing),
            "unexpected": sorted(unexpected), "wrong_type": sorted(wrong_type),
            "missing_source": missing, "runtime_missing": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", "")) / "hermes/exec-brain")
    report = audit_runtime(parser.parse_args().runtime_root)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
