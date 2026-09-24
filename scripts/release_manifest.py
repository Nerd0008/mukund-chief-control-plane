#!/usr/bin/env python3
"""Release manifest generator for the chief control plane.

Records *identity*, not content: the commit this release represents, whether the
worktree was dirty, the supported Python line, the dependency-lock hash, the
hashes of the important deployable artifacts, a full source-tree hash, and the
acceptance-evidence identifiers present at generation time.

Hard rules (enforced in code, not by convention):

* never read, hash or record a secret, credential file, auth store, cookie jar or
  private runtime database — excluded paths are reported by pattern, not content;
* never claim to be a Git repository: a ZIP cannot carry ``.git``, so an archive
  records commit identity + hashes instead of fabricating history;
* hashes are always computed from bytes on disk. Nothing is estimated.

Usage:
    python scripts/release_manifest.py                       # write + print summary
    python scripts/release_manifest.py --out release/release-manifest.json
    python scripts/release_manifest.py --stdout              # JSON only
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = "1.0"

# Supported interpreter for this release. The repository is exercised on the
# 3.11 line; a host may have newer interpreters, which are simply not supported.
SUPPORTED_PYTHON = "3.11.16"
SUPPORTED_PYTHON_LINE = "3.11.x"
KNOWN_UNSUPPORTED_INTERPRETERS = ["3.14.x"]

# ─── Secret / private-data exclusion ────────────────────────────────────────
# Two tiers, so a filename heuristic cannot silently drop a legitimate tracked
# file from a release while a real secret still cannot slip through.
#
# TIER 1 — hard exclusion. These paths are never opened, never hashed, and their
# presence inside an archive is a hard verification failure.
HARD_EXCLUDE_PATTERNS = [
    ".env",
    ".env.",
    "*.pem",
    "*.key",
    "*.ppk",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "authorized_keys",
    "known_hosts",
    "auth.json",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.session",
    "cookie*",
    "cookies*",
]
# The one documented exception: a filename that matches a credential-name
# heuristic but contains no secret — presence-check tooling referenced by the
# deployment runbook.
SECRET_EXCLUDE_EXCEPTIONS = ["scripts/e3_credential_presence_probe.py"]

# TIER 2 — name heuristics. Reviewed but not a blocker: a committed file whose
# *name* merely mentions credentials/tokens/secrets is recorded explicitly in
# `exclusions.review_named_paths` instead of being silently dropped. Dropping it
# would leave it unhashed while still present in the archive, i.e. an unaudited
# hole in the source-tree hash.
REVIEW_NAME_PATTERNS = [
    "*credential*",
    "*secret*",
    "*token*",
    "*password*",
]

# Never shipped in a release archive even if present on disk.
ARCHIVE_EXCLUDE_NAMES = {"release-manifest.json", "ARCHIVE-README.txt"}

# Important deployable artifacts, hashed individually so a consumer can check a
# single file without unpacking the whole tree.
ARTIFACT_SPECS = [
    ("exec-brain/codex_adapter.py", "runtime-core"),
    ("exec-brain/generic_openai_adapter.py", "runtime-core"),
    ("exec-brain/gemini_adapter.py", "runtime-core"),
    ("exec-brain/deepseek_adapter.py", "runtime-core"),
    ("exec-brain/worker_registry.py", "runtime-core"),
    ("exec-brain/capability_registry.py", "runtime-core"),
    ("exec-brain/e3_cli.py", "entrypoint"),
    ("exec-brain/e3_commands.py", "entrypoint"),
    ("exec-brain/e3_execution.py", "runtime-core"),
    ("scripts/evidence_runner.py", "acceptance"),
    ("scripts/whole_company_acceptance.py", "acceptance"),
    ("scripts/deploy_e3_runtime.py", "deployment"),
    ("scripts/deployment_backup_restore_drill.py", "deployment"),
    ("scripts/release_manifest.py", "release"),
    ("scripts/verify_release_archive.py", "release"),
    ("scripts/make_release_archive.py", "release"),
    ("remote_queue/poller.py", "runtime-core"),
    ("remote_queue/queue_schema.py", "runtime-core"),
    ("requirements.txt", "dependencies"),
    ("requirements.lock", "dependencies"),
]


def rm(p):
    return Path(p).as_posix()


def _matches(path: str, pattern: str) -> bool:
    path = path.lower()
    pattern = pattern.lower()
    if pattern.startswith("*") and pattern.endswith("*"):
        return pattern.strip("*") in path
    if pattern.startswith("*"):
        return path.endswith(pattern[1:]) or f"/{pattern[1:]}" in path
    if pattern.endswith("*"):
        return path.startswith(pattern[:-1])
    return path == pattern or path.endswith("/" + pattern) or f"/{pattern}" in path


def is_excluded(rel_path: str) -> bool:
    """True when a path must never be hashed into a release artifact."""
    rel_path = rm(rel_path)
    if rel_path in SECRET_EXCLUDE_EXCEPTIONS:
        return False
    return any(_matches(rel_path, p) for p in HARD_EXCLUDE_PATTERNS)


def is_review_named(rel_path: str) -> bool:
    """True when a path only matches a credential-name heuristic (tier 2)."""
    rel_path = rm(rel_path)
    if rel_path in SECRET_EXCLUDE_EXCEPTIONS or is_excluded(rel_path):
        return False
    return any(_matches(rel_path, p) for p in REVIEW_NAME_PATTERNS)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_hash(root: Path, rel_paths) -> dict:
    """Aggregate hash over (relative path, content hash) for every shipped file.

    Defined exactly as: sha256 over the UTF-8 lines ``"<relpath>\\n<sha256>\\n"``
    for the lexicographically sorted relative paths, excluding the release
    manifest and archive readme themselves. A missing, added or edited file
    changes the aggregate, so the archive verifier can prove set equality too.
    """
    lines = []
    files = 0
    for rel in sorted(set(rel_paths)):
        if Path(rel).name in ARCHIVE_EXCLUDE_NAMES:
            continue
        if is_excluded(rel):
            continue
        target = root / rel
        if not target.is_file():
            continue
        lines.append(f"{rel}\n{sha256_file(target)}\n")
        files += 1
    aggregate = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    return {"file_count": files, "sha256": aggregate}


def _git(root: Path, *args) -> str:
    result = subprocess.run(["git", *args], cwd=str(root),
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def git_identity(root: Path) -> dict:
    return {
        "remote": _git(root, "config", "--get", "remote.origin.url").strip(),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "commit_sha": _git(root, "rev-parse", "HEAD").strip(),
        "commit_subject": _git(root, "log", "-1", "--pretty=%s").strip(),
        "commit_date": _git(root, "log", "-1", "--pretty=%cI").strip(),
    }


def worktree_state(root: Path) -> dict:
    porcelain = _git(root, "status", "--porcelain", "--untracked-files=no")
    modified = [line[3:].strip() for line in porcelain.splitlines() if line.strip()]
    return {
        "clean": not modified,
        "modified_tracked_paths": modified,
        "modified_tracked_count": len(modified),
    }


def dependency_state(root: Path) -> dict:
    manifest_path = root / "requirements.txt"
    lock_path = root / "requirements.lock"
    pinned = {}
    if lock_path.is_file():
        for line in lock_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "==" in line:
                name, _, version = line.partition("==")
                pinned[name.strip()] = version.split("\\")[0].strip()
    return {
        "manifest_file": "requirements.txt",
        "manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
        "lock_file": "requirements.lock",
        "lock_sha256": sha256_file(lock_path) if lock_path.is_file() else None,
        "pinned_packages": dict(sorted(pinned.items())),
        "package_count": len(pinned),
    }


def acceptance_evidence(root: Path) -> dict:
    evidence_root = root / "audits" / "evidence"
    ids = []
    if evidence_root.is_dir():
        ids = sorted(p.name for p in evidence_root.iterdir() if p.is_dir())
    return {"root": "audits/evidence", "count": len(ids), "identifiers": ids}


def curated_artifacts(root: Path) -> list:
    out = []
    for rel, category in ARTIFACT_SPECS:
        target = root / rel
        if not target.is_file():
            out.append({"path": rel, "category": category, "present": False,
                        "sha256": None, "size_bytes": None})
            continue
        if is_excluded(rel):
            raise RuntimeError(f"artifact spec refused as secret-like: {rel}")
        out.append({
            "path": rel,
            "category": category,
            "present": True,
            "sha256": sha256_file(target),
            "size_bytes": target.stat().st_size,
        })
    return out


def build_manifest(root: Path, rel_paths, identity: dict, dirty: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/release_manifest.py",
        "repository": {
            **identity,
            "head_is_dirty": not dirty["clean"],
            "modified_tracked_paths": dirty["modified_tracked_paths"],
            "modified_tracked_count": dirty["modified_tracked_count"],
            "note": ("A source archive cannot carry .git history. The commit "
                     "identity above plus the hashes below are the archive's "
                     "proof of what it contains."),
        },
        "python": {
            "supported_version": SUPPORTED_PYTHON,
            "supported_line": SUPPORTED_PYTHON_LINE,
            "known_unsupported_interpreters": KNOWN_UNSUPPORTED_INTERPRETERS,
        },
        "dependencies": dependency_state(root),
        "artifacts": curated_artifacts(root),
        "source_tree": source_tree_hash(root, rel_paths),
        "acceptance_evidence": acceptance_evidence(root),
        "exclusions": {
            "hard_excluded_patterns": HARD_EXCLUDE_PATTERNS,
            "review_name_patterns": REVIEW_NAME_PATTERNS,
            "documented_exceptions": SECRET_EXCLUDE_EXCEPTIONS,
            "hard_excluded_paths_present": sorted(
                p for p in rel_paths if is_excluded(p)),
            "review_named_paths": sorted(
                p for p in rel_paths if is_review_named(p)),
            "archive_excluded_names": sorted(ARCHIVE_EXCLUDE_NAMES),
            "note": ("Hard-excluded paths are never opened and their presence "
                     "in a release archive fails verification. Release "
                     "artifacts carry no secrets, credentials, cookies, auth "
                     "stores or private runtime databases."),
        },
    }


def verify_manifest(manifest: dict, root: Path, rel_paths) -> list:
    """Return a list of human-readable problems (empty list == verified)."""
    problems = []
    expected = {a["path"]: a for a in manifest.get("artifacts", [])}
    for rel, _ in ARTIFACT_SPECS:
        entry = expected.get(rel)
        if entry is None:
            problems.append(f"manifest does not list artifact {rel}")
            continue
        target = root / rel
        if not target.is_file():
            if entry.get("present"):
                problems.append(f"artifact missing on disk: {rel}")
            continue
        actual = sha256_file(target)
        if actual != entry.get("sha256"):
            problems.append(
                f"artifact hash mismatch: {rel}\n  manifest={entry.get('sha256')}\n  actual  ={actual}")
    for key in ("manifest_sha256", "lock_sha256"):
        entry = manifest.get("dependencies", {})
        filename = entry.get("manifest_file" if key == "manifest_sha256" else "lock_file")
        target = root / filename
        if not target.is_file():
            problems.append(f"dependency artifact missing: {filename}")
            continue
        actual = sha256_file(target)
        if actual != entry.get(key):
            problems.append(
                f"dependency hash mismatch: {filename}\n  manifest={entry.get(key)}\n  actual  ={actual}")
    actual_tree = source_tree_hash(root, rel_paths)
    if actual_tree != manifest.get("source_tree"):
        problems.append(
            "source-tree hash mismatch: "
            f"manifest={manifest.get('source_tree')} actual={actual_tree}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="release/release-manifest.json",
                        help="where to write the manifest")
    parser.add_argument("--stdout", action="store_true",
                        help="print the manifest JSON and do not write a file")
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--verify", action="store_true",
                        help="regenerate and verify against an existing manifest")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    tracked = _git(root, "ls-files").splitlines()

    if args.verify:
        existing_path = Path(args.out)
        if not existing_path.is_absolute():
            existing_path = root / existing_path
        manifest = json.loads(existing_path.read_text(encoding="utf-8"))
        problems = verify_manifest(manifest, root, tracked)
        for problem in problems:
            print(f"PROBLEM: {problem}")
        if problems:
            print(f"\nFAIL: {len(problems)} verification problem(s)")
            return 1
        print(f"OK: {existing_path.name} verified against {root}")
        return 0

    manifest = build_manifest(root, tracked, git_identity(root),
                              worktree_state(root))

    if args.stdout:
        print(json.dumps(manifest, indent=2))
        return 0

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n",
                        encoding="utf-8")

    repo = manifest["repository"]
    print(f"wrote {out_path}")
    print(f"  commit         {repo['commit_sha']} ({repo['branch']})")
    print(f"  dirty          {repo['head_is_dirty']} "
          f"({repo['modified_tracked_count']} modified tracked paths)")
    print(f"  python         {manifest['python']['supported_version']}")
    print(f"  lock sha256    {manifest['dependencies']['lock_sha256']}")
    print(f"  packages       {manifest['dependencies']['package_count']}")
    print(f"  source tree    {manifest['source_tree']['file_count']} files "
          f"sha256={manifest['source_tree']['sha256']}")
    print(f"  evidence ids   {manifest['acceptance_evidence']['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
