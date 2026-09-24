#!/usr/bin/env python3
"""Verify a release archive without trusting anything it says about itself.

Checks performed on the ZIP:

1. ``release-manifest.json`` exists and parses;
2. every listed artifact hash and the dependency-manifest/lock hashes recompute
   to the recorded values from the bytes inside the archive;
3. the aggregate source-tree hash recomputes (this also proves no file was
   added or removed);
4. the archive is self-consistent (no missing listed artifact);
5. optional ``--expect-commit`` / ``--expect-lock-sha256`` bind the archive to a
   known revision and dependency set;
6. optional ``--repo`` additionally proves the recorded commit exists in a real
   repository (``git cat-file -e``), i.e. the identity is not invented;
7. hygiene: the archive contains no ``.git`` entry, no auth store, database or
   other secret-like path.

Exit code 0 == verified, 1 == verification failed.

Usage:
    python scripts/verify_release_archive.py release/chief-<sha>.zip
    python scripts/verify_release_archive.py release/chief-<sha>.zip \
        --expect-commit <sha> --expect-lock-sha256 <sha256>
"""

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_manifest as rm  # noqa: E402


def _files_in(root: Path) -> list:
    return sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*") if p.is_file())


def hygiene_problems(names) -> list:
    """Hard secret / history leakage checks over the archive's member names."""
    problems = []
    for name in names:
        parts = name.split("/")
        if ".git" in parts:
            problems.append(f"archive contains git history entry: {name}")
        if name in rm.ARCHIVE_EXCLUDE_NAMES:
            continue
        if rm.is_excluded(name):
            problems.append(f"archive contains hard-excluded secret-like path: {name}")
    parents = set()
    for name in names:
        parts = name.split("/")
        for i in range(1, len(parts)):
            parents.add("/".join(parts[:i]))
    if ".git" in parents or any(p.endswith("/.git") for p in parents):
        problems.append("archive contains a .git directory")
    return problems


def reviewed_name_paths(names) -> list:
    """Tier-2 heuristic matches — reported for review, not a failure."""
    return sorted(n for n in names
                  if n not in rm.ARCHIVE_EXCLUDE_NAMES and rm.is_review_named(n))


def verify(archive: Path, expect_commit=None, expect_lock=None,
           repo_root=None) -> list:
    problems = []
    if not archive.is_file():
        return [f"archive not found: {archive}"]

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        problems += hygiene_problems(names)
        if "release-manifest.json" not in names:
            return problems + ["archive has no release-manifest.json — "
                               "cannot establish release identity"]
        with zf.open("release-manifest.json") as fh:
            manifest = json.load(fh)

    with tempfile.TemporaryDirectory(prefix="chief-verify-") as tmp:
        check_dir = Path(tmp) / "extract"
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(check_dir)
        problems += rm.verify_manifest(manifest, check_dir, _files_in(check_dir))

    repo = manifest.get("repository", {})
    if expect_commit and repo.get("commit_sha") != expect_commit:
        problems.append(f"commit mismatch: archive={repo.get('commit_sha')} "
                        f"expected={expect_commit}")
    lock_sha = manifest.get("dependencies", {}).get("lock_sha256")
    if expect_lock and lock_sha != expect_lock:
        problems.append(f"lock hash mismatch: archive={lock_sha} "
                        f"expected={expect_lock}")
    if repo.get("head_is_dirty"):
        problems.append("archive was built from a dirty worktree: "
                        + ", ".join(repo.get("modified_tracked_paths", [])[:10]))

    if repo_root:
        sha = repo.get("commit_sha")
        result = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                                cwd=str(repo_root), capture_output=True,
                                text=True, timeout=120)
        if result.returncode != 0:
            problems.append(f"recorded commit {sha} does not exist in {repo_root}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--expect-commit")
    parser.add_argument("--expect-lock-sha256")
    parser.add_argument("--repo", default=None,
                        help="repository to prove the recorded commit exists in")
    args = parser.parse_args(argv)

    archive = Path(args.archive)
    if not archive.is_absolute():
        archive = Path(rm.REPO_ROOT) / archive

    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("release-manifest.json").decode("utf-8")) \
            if "release-manifest.json" in zf.namelist() else {}
        names = zf.namelist()

    problems = verify(archive, args.expect_commit, args.expect_lock_sha256,
                      args.repo)

    repo = manifest.get("repository", {})
    print(f"archive      {archive}")
    print(f"commit       {repo.get('commit_sha')} ({repo.get('branch')})")
    print(f"subject      {repo.get('commit_subject')}")
    print(f"dirty        {repo.get('head_is_dirty')}")
    print(f"lock sha256  {manifest.get('dependencies', {}).get('lock_sha256')}")
    print(f"packages     {manifest.get('dependencies', {}).get('package_count')}")
    print(f"source tree  {manifest.get('source_tree', {}).get('file_count')} files "
          f"sha256={manifest.get('source_tree', {}).get('sha256')}")
    reviewed = reviewed_name_paths(names)
    if reviewed:
        print(f"review-named {len(reviewed)} path(s) matched a name heuristic "
              "(no secret content; recorded in the manifest):")
        for name in reviewed:
            print(f"             {name}")
    if problems:
        print()
        for problem in problems:
            print(f"PROBLEM: {problem}")
        print(f"\nFAIL: {len(problems)} problem(s)")
        return 1
    print("\nOK: archive verified (identity + dependency + file hashes + hygiene)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
