#!/usr/bin/env python3
"""Deploy the E3 orchestration modules + `e3-*` CLI bindings to the runtime root.

The repository checkout (`exec-brain/`) is the source of truth; the live runtime
root (`%LOCALAPPDATA%\\hermes\\exec-brain`) is what the local `eb` CLI and the
E1/E2 suites actually execute against. This script keeps them in step for the
E3 module set only, with full rollback:

* every file it overwrites is first copied into
  ``<runtime-root>/backups/e3-deploy-<UTC-stamp>/`` preserving the path;
* a manifest records, for every deployed file, its source path, destination
  path and SHA-256 before/after, plus the source git commit;
* secret-bearing files are refused outright (never copied, never committed);
* ``--restore <backup-dir>`` rolls a deployment back byte-for-byte.

It does not touch E1 (`eb.py` is patched in place only to register the `e3-*`
subcommands, and the pre-patch copy is backed up), E2 (`governor.py`,
`governor.db`), or any database.

Usage:
    python scripts/deploy_e3_runtime.py [--dry-run]
    python scripts/deploy_e3_runtime.py --restore <backup-dir>
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "exec-brain"
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# The E3 module set (orchestration + adapters + shared E3 deps). Deliberately
# excludes E1/E2-owned files (eb.py is patched separately, governor.py is E2's).
E3_MODULES = [
    "orchestration_db.py",
    "stage2_control.py",
    "execution_dag.py",
    "worker_contract.py",
    "worker_registry.py",
    "capability_registry.py",
    "qualification_gate.py",
    "task_fingerprint.py",
    "decision_rationale.py",
    "e3_commands.py",
    "e3_cli.py",
    "e3_planner.py",
    "e3_router.py",
    "e3_team_assembly.py",
    "e3_integrator.py",
    "e3_verifier.py",
    "e3_conflict.py",
    "e3_context.py",
    "e3_permissions.py",
    "e3_decomposition_review.py",
    "e3_evidence.py",
    "e3_escalate.py",
    "e3_exploration.py",
    "e3_replan.py",
    "e3_qualification_benchmark.py",
    "e3_shadow_orchestrator.py",
    "e3_production_rehearsal.py",
    "e3_execution.py",
    "e3_service.py",
    "chief_routing.py",
    "discord_chief_bridge.py",
    "department_dispatch.py",
    "chief_context.py",
    "e3_execution_rehearsal.py",
    "generic_openai_adapter.py",
    "deepseek_adapter.py",
    "codex_adapter.py",
    "gemini_adapter.py",
    "deepseek_keyaccess.py",
    "gemini_keyaccess.py",
    # E4 resource continuity is imported by the deployed e3-status surface (the
    # provider content-side stop pressure view over recorded evidence), so it is
    # part of the deployed module set. It is pure stdlib and touches no store.
    "resource_monitor.py",
]

# Never copy anything that looks like a secret, whatever it is named.
SECRET_PATTERNS = (".env", ".key", ".pem", ".ppk", "secret", "credential",
                   "password", "token", "cookie")


def _sha256(path: Path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _is_secret(name: str) -> bool:
    lowered = name.lower()
    return any(p in lowered for p in SECRET_PATTERNS)


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=60)
        return out.stdout.strip() if out.returncode == 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


E3_CLI_REGISTRATION = '''
    # E3: orchestration subcommands (registered by scripts/deploy_e3_runtime.py)
    try:
        from e3_cli import register as _register_e3_subcommands
        _register_e3_subcommands(sub)
    except Exception as _e3_cli_error:  # pragma: no cover - degrade, never crash E1
        print(f"warning: E3 CLI bindings unavailable: {_e3_cli_error}",
              file=sys.stderr)
'''


def patch_eb(runtime_root: Path, backup_dir: Path, dry_run: bool) -> dict:
    """Register the e3-* subcommands in the runtime eb.py (idempotent)."""
    eb = runtime_root / "eb.py"
    record = {"file": str(eb), "action": "skipped", "reason": None}
    if not eb.exists():
        record["reason"] = "eb.py not present in runtime root"
        return record

    text = eb.read_text(encoding="utf-8")
    if "_register_e3_subcommands" in text:
        record["action"] = "already-patched"
        return record
    if "    args = ap.parse_args()" not in text:
        record["reason"] = "argparse idiom not found; not patching"
        return record

    patched = text.replace("    args = ap.parse_args()",
                           E3_CLI_REGISTRATION.lstrip("\n") + "\n    args = ap.parse_args()",
                           1)
    record["action"] = "patched"
    record["before_sha256"] = _sha256(eb)
    record["after_sha256"] = hashlib.sha256(patched.encode("utf-8")).hexdigest()
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(eb, backup_dir / "eb.py")
        eb.write_text(patched, encoding="utf-8")
    return record


def deploy(runtime_root: Path, dry_run: bool) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = runtime_root / "backups" / f"e3-deploy-{stamp}"
    files = []

    for name in E3_MODULES:
        src = SRC_DIR / name
        dst = runtime_root / name
        entry = {"name": name, "source": str(src), "destination": str(dst)}
        if _is_secret(name):
            entry.update(action="refused", reason="secret-pattern")
            files.append(entry)
            continue
        if not src.exists():
            entry.update(action="missing-source")
            files.append(entry)
            continue
        entry["source_sha256"] = _sha256(src)
        entry["destination_sha256_before"] = _sha256(dst)
        if entry["source_sha256"] == entry["destination_sha256_before"]:
            entry["action"] = "up-to-date"
            files.append(entry)
            continue
        entry["action"] = "would-copy" if dry_run else "copied"
        if not dry_run:
            backup_dir.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.copy2(dst, backup_dir / name)
            shutil.copy2(src, dst)
            entry["destination_sha256_after"] = _sha256(dst)
        files.append(entry)

    eb_record = patch_eb(runtime_root, backup_dir, dry_run)

    manifest = {
        "deployed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_dir": str(SRC_DIR),
        "source_git_sha": _git_sha(),
        "runtime_root": str(runtime_root),
        "backup_dir": None if dry_run else str(backup_dir),
        "dry_run": dry_run,
        "files": files,
        "copied": [f["name"] for f in files if f["action"] == "copied"],
        "eb_py": eb_record,
        "note": ("E1/E2-owned files (eb.py except the e3-* registration patch, "
                 "governor.py, governor.db, exec_brain.db) are not modified."),
    }
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                                  encoding="utf-8")
    return manifest


def restore(backup_dir: Path, runtime_root: Path) -> dict:
    manifest_path = backup_dir / "manifest.json"
    restored = []
    for src in backup_dir.iterdir():
        if src.name == "manifest.json" or not src.is_file():
            continue
        dst = runtime_root / src.name
        shutil.copy2(src, dst)
        restored.append({"name": src.name, "destination": str(dst),
                         "sha256": _sha256(dst)})
    return {"backup_dir": str(backup_dir),
            "restored": restored,
            "manifest_present": manifest_path.exists()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--restore", default=None,
                        help="restore a previous backup directory")
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root) if args.runtime_root else RUNTIME_ROOT
    if args.restore:
        report = restore(Path(args.restore), runtime_root)
        print(json.dumps(report, indent=2))
        return 0

    report = deploy(runtime_root, args.dry_run)
    print(json.dumps({k: report[k] for k in
                      ("deployed_at_utc", "source_git_sha", "runtime_root",
                       "backup_dir", "dry_run", "copied", "eb_py")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
