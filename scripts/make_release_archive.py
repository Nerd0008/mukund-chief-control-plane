#!/usr/bin/env python3
"""Build a verifiable release archive (ZIP) from a committed revision.

A ZIP cannot carry ``.git`` history, so this tool does not pretend it does.
Instead it:

1. exports the committed tree with ``git archive`` (no ``.git``, no untracked
   or ignored files — private runtime data cannot leak in),
2. computes a release manifest over *the exported tree itself*, so every hash
   provably describes what is inside the archive,
3. injects ``release-manifest.json`` and ``ARCHIVE-README.txt`` into the ZIP,
4. re-opens the finished ZIP and verifies the manifest against it before
   reporting success.

The archive therefore proves its own commit identity, dependency set and file
hashes without containing any Git history.

Usage:
    python scripts/make_release_archive.py --out release/chief-<sha>.zip
    python scripts/make_release_archive.py --allow-dirty ...
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_manifest as rm  # noqa: E402

ARCHIVE_README = """\
Mukund Chief Control Plane — release archive
============================================

This archive was exported from a committed Git revision with `git archive`.
It deliberately contains NO .git directory and NO Git history; a ZIP cannot
truthfully carry either.

Provenance for this archive lives in `release-manifest.json` at the root:

  * repository commit SHA / branch / commit subject
  * dirty state of the authoring worktree
  * supported Python version (see `requirements.txt` / `requirements.lock`)
  * SHA-256 of the dependency lock, plus every pinned package
  * SHA-256 of the important deployable artifacts
  * an aggregate source-tree hash over every shipped file
  * the acceptance-evidence identifiers recorded at packaging time

Verify it before use:

    python scripts/verify_release_archive.py <this-archive>.zip

To go from an archive to a working clone of the same revision:

    git clone <repository> && git checkout <commit_sha from the manifest>

Machine-local state (provider credentials, Windows Credential Manager entries,
Hermes state databases, the Codex login under %USERPROFILE%/.codex, owner
application data, Windows scheduled tasks) is intentionally NOT in this
archive. See docs/SETUP.md for what must be provisioned on a host and the
deterministic probes that check it.
"""


def _git(root: Path, *args) -> str:
    result = subprocess.run(["git", *args], cwd=str(root),
                            capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def export_committed_tree(root: Path, revision: str, dest: Path) -> None:
    """Write the committed tree (no .git) into `dest`."""
    archive = dest.parent / "git-archive.zip"
    subprocess.run(
        ["git", "archive", "--format=zip", f"--output={archive}", revision],
        cwd=str(root), check=True, capture_output=True,
    )
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)
    archive.unlink()


def files_in_tree(root: Path) -> list:
    out = []
    for path in root.rglob("*"):
        if path.is_file():
            out.append(path.relative_to(root).as_posix())
    return sorted(out)


def build(root: Path, revision: str, out_path: Path, allow_dirty: bool) -> dict:
    identity = rm.git_identity(root)
    dirty = rm.worktree_state(root)

    if not dirty["clean"] and not allow_dirty:
        raise SystemExit(
            "refusing to build a release archive from a dirty worktree "
            f"({dirty['modified_tracked_count']} modified tracked paths). "
            "Commit first, or pass --allow-dirty to record the dirty state "
            "explicitly in the manifest."
        )

    tmp = Path(tempfile.mkdtemp(prefix="chief-release-"))
    try:
        tree = tmp / "tree"
        export_committed_tree(root, revision, tree)

        exported = files_in_tree(tree)
        hard = [p for p in exported if rm.is_excluded(p)]
        if hard:
            raise SystemExit(
                "refusing to build a release archive: the committed tree "
                "contains hard-excluded secret-like path(s): " + ", ".join(hard)
            )

        manifest = rm.build_manifest(tree, exported, identity, dirty)
        (tree / "release-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (tree / "ARCHIVE-README.txt").write_text(ARCHIVE_README,
                                                 encoding="utf-8")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in files_in_tree(tree):
                zf.write(tree / rel, rel)

        # Verify the finished archive against its own manifest.
        check_dir = tmp / "check"
        with zipfile.ZipFile(out_path) as zf:
            zf.extractall(check_dir)
        with open(check_dir / "release-manifest.json", encoding="utf-8") as fh:
            manifest_out = json.load(fh)
        problems = rm.verify_manifest(manifest_out, check_dir,
                                      files_in_tree(check_dir))
        if problems:
            for problem in problems:
                print(f"PROBLEM: {problem}", file=sys.stderr)
            raise SystemExit(f"archive verification failed: {len(problems)} problem(s)")
        return manifest_out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(rm.REPO_ROOT))
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--out", required=True,
                        help="output ZIP path")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path

    manifest = build(root, args.revision, out_path, args.allow_dirty)
    repo = manifest["repository"]
    size = out_path.stat().st_size
    print(f"wrote {out_path} ({size} bytes)")
    print(f"  commit       {repo['commit_sha']} ({repo['branch']})")
    print(f"  dirty        {repo['head_is_dirty']}")
    print(f"  lock sha256  {manifest['dependencies']['lock_sha256']}")
    print(f"  source tree  {manifest['source_tree']['file_count']} files "
          f"sha256={manifest['source_tree']['sha256']}")
    print("  verified     manifest re-checked against the finished archive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
