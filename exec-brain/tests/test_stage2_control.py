import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage2_control

class Stage2ControlTests(unittest.TestCase):
    def test_default_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                stage2_control.require_enabled(Path(d) / "state.json")
    def test_enable_persists_only_non_secret_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d) / "state.json"
            saved=stage2_control.enable(approval_record="owner.md", regression_evidence="evidence.json", allowed_workers=["deepseek-v41-flash", "codex-cli"], path=path)
            self.assertTrue(saved["enabled"])
            self.assertEqual(stage2_control.require_enabled(path)["allowed_workers"], ["codex-cli", "deepseek-v41-flash"])

if __name__ == "__main__": unittest.main(verbosity=2)
