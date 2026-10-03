#!/usr/bin/env python3
"""Deterministic, isolated tests for scripts/deploy_e3_runtime.py.

Every test runs against a disposable runtime root built from the repository's
own module set: no live runtime file, no `eb` CLI, no database and no network
call is touched. `SRC_DIR`/`RUNTIME_ROOT` are module constants read at import
time, so the module's `deploy()` is driven directly with an explicit root.

The regressions covered here are the two ways this script could quietly do the
wrong thing:

* it compared raw SHA-256, so a runtime copy with CRLF line endings reported as
  changed and was needlessly rewritten on every deploy;
* it overwrote whatever was in the runtime root, so a runtime copy holding
  NEWER code than the repository (live work written by the `eb` CLI or a smoke
  run, never committed back) was destroyed silently.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


class DeployRuntimeTest(unittest.TestCase):
    """Base: a disposable runtime root seeded from the repository module set."""

    def setUp(self):
        import deploy_e3_runtime as d
        self.d = d
        self._tmp = tempfile.TemporaryDirectory(prefix="deploy-e3-test-")
        self.root = Path(self._tmp.name)
        self.seeded = []
        for name in d.E3_MODULES:
            src = d.SRC_DIR / name
            if src.exists():
                shutil.copy2(src, self.root / name)
                self.seeded.append(name)
        self.assertTrue(self.seeded, "expected the repository module set to exist")

    def tearDown(self):
        self._tmp.cleanup()

    def action_for(self, report, name):
        return next(f["action"] for f in report["files"] if f["name"] == name)

    def make_runtime_newer(self, name, extra="\n# runtime-only newer work\n"):
        """Give `name` different content and a modification time in the future."""
        path = self.root / name
        path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")
        future = time.time() + 3600
        os.utime(path, (future, future))
        return path


class TestLineEndingComparison(DeployRuntimeTest):
    def test_crlf_only_difference_is_up_to_date(self):
        """A CRLF runtime copy of identical code must not be rewritten."""
        name = "orchestration_db.py"
        if name not in self.seeded:
            self.skipTest(f"{name} not present in the repository module set")

        # Same content, CRLF line endings, and newer mtime — the exact shape
        # that used to make every deploy rewrite ~18 untouched files.
        text = (self.d.SRC_DIR / name).read_bytes().replace(b"\r\n", b"\n")
        path = self.root / name
        path.write_bytes(text.replace(b"\n", b"\r\n"))
        future = time.time() + 3600
        os.utime(path, (future, future))

        report = self.d.deploy(self.root, dry_run=True)
        self.assertEqual(self.action_for(report, name), "up-to-date")
        self.assertEqual(report["copied"], [])
        self.assertEqual(report["skipped_runtime_newer"], [])

    def test_an_untouched_seed_deploys_nothing(self):
        """Deploying into a copy of the repo must be a no-op."""
        report = self.d.deploy(self.root, dry_run=True)
        self.assertEqual(report["copied"], [])
        self.assertEqual(report["skipped_runtime_newer"], [])


class TestNewerRuntimeIsProtected(DeployRuntimeTest):
    def test_newer_runtime_copy_is_skipped_not_overwritten(self):
        name = "worker_registry.py"
        if name not in self.seeded:
            self.skipTest(f"{name} not present in the repository module set")
        self.make_runtime_newer(name)

        report = self.d.deploy(self.root, dry_run=True)
        self.assertEqual(self.action_for(report, name), "skipped-runtime-newer")
        self.assertIn(name, report["skipped_runtime_newer"])
        self.assertNotIn(name, report["copied"])

    def test_newer_runtime_copy_survives_a_real_deploy(self):
        """The guard must hold on a real (non-dry-run) deploy too."""
        name = "worker_registry.py"
        if name not in self.seeded:
            self.skipTest(f"{name} not present in the repository module set")
        path = self.make_runtime_newer(name)
        before = path.read_text(encoding="utf-8")

        report = self.d.deploy(self.root, dry_run=False)
        self.assertIn(name, report["skipped_runtime_newer"])
        self.assertEqual(path.read_text(encoding="utf-8"), before,
                         "the runtime copy was overwritten despite being newer")

    def test_allow_runtime_newer_overwrites_and_backs_up(self):
        """The explicit opt-in overwrites, and the previous copy is preserved."""
        name = "worker_registry.py"
        if name not in self.seeded:
            self.skipTest(f"{name} not present in the repository module set")
        path = self.make_runtime_newer(name)
        newer_text = path.read_text(encoding="utf-8")

        report = self.d.deploy(self.root, dry_run=False, allow_runtime_newer=True)
        self.assertIn(name, report["copied"])

        backup = Path(report["backup_dir"]) / name
        self.assertTrue(backup.is_file(), "the overwritten copy was not backed up")
        self.assertEqual(backup.read_text(encoding="utf-8"), newer_text)
        self.assertEqual(path.read_text(encoding="utf-8"),
                         (self.d.SRC_DIR / name).read_text(encoding="utf-8"))


class TestSecretRefusal(DeployRuntimeTest):
    def test_secret_shaped_names_are_refused(self):
        """A module name matching a secret pattern is never copied."""
        self.assertTrue(self.d._is_secret("deepseek_credentials.py"))
        self.assertTrue(self.d._is_secret("api_token.py"))
        self.assertFalse(self.d._is_secret("codex_adapter.py"))


if __name__ == "__main__":
    unittest.main()
