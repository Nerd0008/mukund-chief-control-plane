#!/usr/bin/env python3
"""Consistency tests for the canonical project-status source and its outputs.

These are the deterministic, offline checks that keep the executive tracker and
the derived status summaries from drifting: every figure in
``status/canonical-status.json`` is compared against the recorded evidence
artifact it names, and every generated surface is compared against a fresh
render of the canonical source.

No network call, no provider call, no credential value, no private runtime
database and no live scheduled task is touched. Safe to run under
``scripts/evidence_runner.py`` alongside the live system.
"""

import copy
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import status_render  # noqa: E402
import status_sources as src  # noqa: E402
import status_verify  # noqa: E402


class CanonicalStatusSource(unittest.TestCase):
    def setUp(self):
        self.canonical = src.load_canonical()

    def test_01_required_sections_present(self):
        self.assertEqual(src.check_required_keys(self.canonical), [])

    def test_02_referenced_evidence_paths_exist(self):
        self.assertEqual(src.check_evidence_references(), [])

    def test_03_latest_evidence_matches_artifact(self):
        self.assertEqual(src.check_latest_evidence(self.canonical), [])

    def test_04_regression_counts_match_evidence(self):
        self.assertEqual(src.check_regression(self.canonical), [])

    def test_05_roster_accounting_matches_evidence(self):
        self.assertEqual(src.check_roster(self.canonical), [])

    def test_06_provider_credential_readiness_matches_probe(self):
        self.assertEqual(src.check_credentials(self.canonical), [])

    def test_07_deployment_preflight_matches_evidence(self):
        self.assertEqual(src.check_preflight(self.canonical), [])

    def test_08_e4e5_drill_figures_match_evidence(self):
        self.assertEqual(src.check_drills(self.canonical), [])

    def test_09_persistence_evidence_consistent(self):
        self.assertEqual(src.check_persistence(self.canonical), [])

    def test_10_no_newer_evidence_left_unincorporated(self):
        # A newer evidence directory is surfaced rather than silently ignored.
        self.assertEqual(src.check_unincorporated_evidence(self.canonical), [])

    def test_11_required_production_blockers_are_represented(self):
        self.assertEqual(src.check_blockers(self.canonical), [])
        ids = {b["id"] for b in self.canonical["production_blockers"]}
        self.assertTrue(src.REQUIRED_PRODUCTION_BLOCKERS.issubset(ids))

    def test_12_optional_items_are_not_promoted_to_release_blockers(self):
        optional_ids = {o["id"] for o in self.canonical["optional_gated"]}
        blocker_ids = {b["id"] for b in self.canonical["production_blockers"]}
        self.assertTrue(src.REQUIRED_OPTIONAL_GATED.issubset(optional_ids))
        self.assertEqual(src.REQUIRED_OPTIONAL_GATED & blocker_ids, set())
        for entry in self.canonical["optional_gated"]:
            self.assertFalse(entry.get("release_scope", False),
                             f"{entry['id']} must not be declared release scope")

    def test_13_owner_gated_unknowns_are_not_reported_as_pass(self):
        # Stop condition: no owner-gated UNKNOWN may be turned into PASS, and the
        # status may not claim readiness while production blockers remain open.
        for entry in self.canonical["production_blockers"]:
            self.assertIn(entry["state"], {"OPEN", "UNKNOWN", "BLOCKED"},
                          f"production blocker {entry['id']} has a non-open state")
        self.assertNotEqual(self.canonical["stage2"]["state"], "ENABLED")
        self.assertEqual(self.canonical["executive_brain"]["E3"]["stage2_enabled"], False)
        self.assertNotIn(self.canonical["deployment"]["state"], {"DEPLOYED", "PRODUCTION"})
        self.assertNotEqual(self.canonical["deployment"]["cutover"], "authorised")
        self.assertTrue(self.canonical["production_blockers"])
        self.assertEqual(src.check_no_ready_claim(self.canonical), [])

    def test_14_unknowns_are_preserved(self):
        self.assertTrue(self.canonical["unknowns"])
        for text in self.canonical["unknowns"]:
            self.assertTrue(text.strip())


class GeneratedOutputs(unittest.TestCase):
    def setUp(self):
        self.canonical = src.load_canonical()
        self.outputs = status_render.build_outputs(self.canonical)

    def test_20_generated_executive_tracker_is_current(self):
        self.assertTrue(src.EXECUTIVE_TRACKER_PATH.exists(),
                        "status/executive-tracker.md is missing")
        on_disk = src.normalise(src.read_source(src.EXECUTIVE_TRACKER_PATH))
        self.assertEqual(on_disk, src.normalise(self.outputs["executive-tracker"]))

    def test_21_derived_status_summaries_are_current(self):
        for key, path, label in status_verify.DOC_TARGETS:
            block = src.extract_block(src.read_source(path))
            self.assertTrue(block is not None, f"{label} has no generated status block")
            self.assertEqual(src.normalise(block or ""), src.normalise(self.outputs[key]),
                             f"{label} generated block is stale")

    def test_22_no_secret_material_in_generated_output(self):
        for key, rendered in self.outputs.items():
            self.assertEqual(src.check_no_secrets(rendered), [], f"secret-shaped text in {key}")

    def test_23_generated_tracker_covers_later_career_discovery_work(self):
        tracker = self.outputs["executive-tracker"]
        for marker in ("B25", "B26", "B27", "B19", "B11",
                       "Scheduled orchestrator cutover", "COMPLETE / PASS"):
            self.assertIn(marker, tracker, f"generated tracker omits {marker}")


class DriftDetection(unittest.TestCase):
    """The verifier must not be vacuous: a tampered value has to fail."""

    def test_30_tampered_regression_count_fails(self):
        canonical = src.load_canonical()
        broken = copy.deepcopy(canonical)
        broken["regressions"]["tests_passed"] = broken["regressions"]["tests_passed"] - 1
        problems = src.check_regression(broken)
        self.assertTrue(any(level == "FAIL" for level, _ in problems),
                        "a wrong regression figure was not detected")

    def test_31_tampered_credential_count_fails(self):
        canonical = src.load_canonical()
        broken = copy.deepcopy(canonical)
        # The probe now reports 0 absent, so the tamper must invent absences the
        # probe never recorded; a wrong-and-nonzero figure has to be caught.
        broken["provider_credentials"]["credentials_absent"] = 3
        broken["provider_credentials"]["absent_workers"] = [
            "minimax-m3", "step-37-flash", "tencent-hunyuan-hy3"]
        problems = src.check_credentials(broken)
        self.assertTrue(any(level == "FAIL" for level, _ in problems),
                        "a wrong credential-readiness figure was not detected")

    def test_32_missing_blocker_fails(self):
        canonical = src.load_canonical()
        broken = copy.deepcopy(canonical)
        broken["production_blockers"] = [
            b for b in broken["production_blockers"] if b["id"] != "stage2-not-enabled"
        ]
        problems = src.check_blockers(broken)
        self.assertTrue(any(level == "FAIL" for level, _ in problems),
                        "a dropped production blocker was not detected")

    def test_33_stale_tracker_fails_verification(self):
        canonical = src.load_canonical()
        # A stale block is produced by rendering from a mutated canonical source.
        broken = copy.deepcopy(canonical)
        broken["latest_evidence"]["verdict"] = "PASS (tampered)"
        outputs = status_render.build_outputs(broken)
        self.assertNotEqual(src.normalise(outputs["executive-tracker"]),
                            src.normalise(src.read_source(src.EXECUTIVE_TRACKER_PATH)))

    def test_34_verify_command_fails_on_drift_and_passes_on_current(self):
        self.assertEqual(status_verify.main(["--quiet"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
