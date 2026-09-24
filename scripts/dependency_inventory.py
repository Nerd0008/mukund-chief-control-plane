#!/usr/bin/env python3
"""Deterministic dependency inventory for the chief control plane.

Walks the repository, parses every Python file with ``ast`` and classifies each
top-level imported module as one of:

* ``stdlib``            — Python 3.11 standard library
* ``repository-local``  — a module/package shipped in this repository
* ``third-party``       — an external distribution (mapped to its PyPI name)
* ``unresolved``        — neither of the above and not in the known-external map
                          (reported explicitly, never silently ignored)

It then cross-checks the third-party set against ``requirements.txt`` so an
undeclared import is a hard failure rather than a surprise at deploy time.

Truth rules: the inventory reports what the source actually imports. It never
adds a package to the manifest on its own, and it never guesses a version.

Usage:
    python scripts/dependency_inventory.py                # human summary
    python scripts/dependency_inventory.py --json         # machine-readable
    python scripts/dependency_inventory.py --check        # exit 1 if undeclared
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules",
    ".bridge-stash",
}

# Import name -> PyPI distribution name. Only aliases that differ are listed;
# every other third-party import maps to itself.
DISTRIBUTION_ALIASES = {
    "yaml": "PyYAML",
}

# Modules that are deliberately provided by the machine-local Hermes runtime
# (`%LOCALAPPDATA%/hermes/exec-brain/`) rather than by this repository or PyPI.
# The E1/E2 suites import these through an explicit PYTHONPATH entry.
MACHINE_LOCAL_RUNTIME_MODULES = {
    "eb": "E1 runtime eb.py (%LOCALAPPDATA%/hermes/exec-brain/eb.py)",
    "governor": "E2 runtime governor.py (%LOCALAPPDATA%/hermes/exec-brain/governor.py)",
    "adapters": "E2 provider adapters (%LOCALAPPDATA%/hermes/exec-brain/adapters.py)",
}


def _repository_local_modules() -> set:
    """Top-level module and package names shipped in this repository."""
    names = set()
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = Path(root).relative_to(REPO_ROOT)
        if len(rel.parts) > 2:
            dirs[:] = []
        for name in dirs:
            if (Path(root) / name / "__init__.py").is_file():
                names.add(name)
        for name in files:
            if name.endswith(".py"):
                names.add(name[:-3])
    return names


def _iter_python_files():
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                yield Path(root) / name


def _top_level_imports(path: Path):
    """Yield (module_name, lineno) for every top-level import in `path`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        yield "__parse_error__", f"{type(exc).__name__}: {exc}"
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — repository-local by definition
                continue
            if node.module:
                yield node.module.split(".")[0], node.lineno


def collect() -> dict:
    stdlib = set(sys.stdlib_module_names)
    local = _repository_local_modules()
    declared = _declared_distributions()

    third_party = {}
    machine_local = {}
    unresolved = []
    errors = []

    for path in sorted(_iter_python_files()):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for module, lineno in _top_level_imports(path):
            if module == "__parse_error__":
                errors.append({"file": rel, "error": lineno})
                continue
            if module in stdlib or module in local:
                continue
            if module in declared:
                info = third_party.setdefault(
                    module, {"files": [], "lines": []})
                info["files"].append(rel)
                info["lines"].append(f"{rel}:{lineno}")
            elif module in MACHINE_LOCAL_RUNTIME_MODULES:
                info = machine_local.setdefault(module, {
                    "module": module,
                    "kind": "machine-local-runtime",
                    "note": MACHINE_LOCAL_RUNTIME_MODULES[module],
                    "files": [],
                })
                info["files"].append(f"{rel}:{lineno}")
            else:
                unresolved.append(f"{rel}:{lineno} -> {module}")

    for module, info in third_party.items():
        info["files"] = sorted(set(info["files"]))
        info["import_sites"] = len(info.pop("lines"))
        info["distribution"] = declared[module]

    # Anything imported but not declared in requirements.txt.
    undeclared = sorted(
        m for m in third_party if not _requirements_declare(declared[m])
    )

    return {
        "repository_root": str(REPO_ROOT),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "third_party": {k: third_party[k] for k in sorted(third_party)},
        "machine_local_runtime": machine_local,
        "unresolved_imports": sorted(unresolved),
        "undeclared_in_requirements": undeclared,
        "parse_errors": errors,
    }


def _requirements_path() -> Path:
    return REPO_ROOT / "requirements.txt"


def _declared_distributions() -> dict:
    """Import name -> distribution name for everything requirements.txt pins."""
    dists = {}
    path = _requirements_path()
    if not path.is_file():
        return dists
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        name = line.split("==", 1)[0].strip()
        package = name.split("[", 1)[0]
        for import_name, dist in DISTRIBUTION_ALIASES.items():
            if dist.lower() == package.lower():
                dists[import_name] = package
        dists.setdefault(package.lower().replace("-", "_"), package)
        dists.setdefault(package, package)
    return dists


def _requirements_declare(distribution: str) -> bool:
    path = _requirements_path()
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8").lower()
    return f"{distribution.lower()}==" in text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when an import is undeclared")
    args = parser.parse_args(argv)

    report = collect()

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"repository: {report['repository_root']}")
        print(f"python:     {report['python_version']}")
        print()
        print("third-party imports declared in requirements.txt:")
        for module, info in report["third_party"].items():
            print(f"  {module:12s} -> {info['distribution']:10s} "
                  f"({info['import_sites']} import sites)")
        if report["machine_local_runtime"]:
            print()
            print("machine-local runtime modules (not a repository dependency):")
            for module, info in report["machine_local_runtime"].items():
                print(f"  {module:12s} {info['note']}")
        if report["unresolved_imports"]:
            print()
            print("UNRESOLVED imports (neither stdlib, repository-local nor declared):")
            for site in report["unresolved_imports"]:
                print(f"  {site}")
        if report["undeclared_in_requirements"]:
            print()
            print("UNDECLARED third-party imports:")
            for module in report["undeclared_in_requirements"]:
                print(f"  {module}")
        if report["parse_errors"]:
            print()
            print("parse errors:")
            for err in report["parse_errors"]:
                print(f"  {err['file']}: {err['error']}")

    if args.check:
        problems = list(report["undeclared_in_requirements"])
        problems += [e["file"] for e in report["parse_errors"]]
        if problems:
            print(f"\nFAIL: {len(problems)} undeclared import(s) / parse error(s)",
                  file=sys.stderr)
            return 1
        print("\nOK: every third-party import is declared in requirements.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
