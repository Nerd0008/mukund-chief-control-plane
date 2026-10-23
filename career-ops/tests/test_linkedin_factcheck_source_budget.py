import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "linkedin_factcheck.py"
spec = importlib.util.spec_from_file_location("linkedin_factcheck", MODULE_PATH)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)

LATE = "A single researcher completed in a week what a team would take months."


def judge(prompt, **kwargs):
    items = json.loads(prompt.split("\nCLAIMS:\n", 1)[1].split("\nSOURCE:\n", 1)[0])
    source = prompt.split("\nSOURCE:\n", 1)[1]
    present = LATE in source
    answer = [dict(i, verdict="supported" if present else "unsupported",
                   evidence=LATE if present else "",
                   reason="Explicit research comparison." if present else "Comparison absent from this section.") for i in items]
    return {"runs": [[dict(a) for a in answer] for _ in range(3)], "reason": None,
            "receipt": {"prompt_chars": len(prompt), "prompt_sha256": fc.sha256_text(prompt)}}


class TestSourceCoverage(unittest.TestCase):
    def verify(self, sources, side_effect=judge):
        # Test audit writes in a disposable runtime, never the owner's runtime.
        with tempfile.TemporaryDirectory() as temp:
            fake_module = Path(temp) / "career-ops/linkedin_factcheck.py"
            with patch.object(fc, "__file__", str(fake_module)), patch.object(fc, "run_judge", side_effect=side_effect):
                record = fc.verify_post(LATE, list(sources), source_texts=sources, api_key="test")
            audit = json.loads(Path(record["audit_path"]).read_text(encoding="utf-8"))
            return record, audit

    def test_late_evidence_reaches_judge_in_multiple_long_articles(self):
        sources = {"https://example.com/one": "A" * 24000,
                   "https://example.com/two": "B" * 16000 + LATE + "B" * 3000}
        record, audit = self.verify(sources)
        self.assertEqual(record["verdict"], "pass")
        self.assertTrue(record["verification_complete"])
        self.assertEqual(record["source_chars_fed"], record["source_chars_total"])
        self.assertIn(LATE, audit["judge"]["audit"][0]["prompt"])
        for value in record["source_coverage"].values():
            self.assertEqual(value["original_chars"], value["supplied_chars"])

    def test_over_budget_sources_are_sectioned_without_loss(self):
        sources = {"https://example.com/one": "A" * 15000 + LATE + "A" * 1000}
        with patch.object(fc, "JUDGE_SOURCE_CHARS", 6000):
            record, audit = self.verify(sources)
        self.assertEqual(record["verdict"], "pass")
        sections = audit["judge"]["section_coverage"]
        self.assertGreater(len(sections), 1)
        self.assertEqual(sections[0]["start"], 0)
        self.assertEqual(sections[-1]["end"], record["source_chars_total"])
        self.assertTrue(all(a["end"] >= b["start"] for a, b in zip(sections, sections[1:])))

    def test_failed_section_never_passes(self):
        def fail_later(prompt, **kwargs):
            return judge(prompt) if LATE in prompt.split("\nSOURCE:\n", 1)[1] else {"runs": [], "reason": "timeout"}
        with patch.object(fc, "JUDGE_SOURCE_CHARS", 6000):
            record, audit = self.verify({"https://example.com/one": "A" * 15000 + LATE}, fail_later)
        self.assertEqual(record["verdict"], "ungated")
        self.assertFalse(record["verification_complete"])
        self.assertGreater(record["source_chars_fed"], 0)
        self.assertLess(record["source_chars_fed"], record["source_chars_total"])
        self.assertGreater(record["source_coverage"]["https://example.com/one"]["omitted_chars"], 0)
        self.assertIn("incomplete", record["reason"].lower())

    def test_partial_answers_never_pass_or_become_factual_rejections(self):
        def partial(prompt, **kwargs):
            data = judge(prompt)
            data["runs"] = data["runs"][:2]
            return data
        record, audit = self.verify({"https://example.com/one": LATE}, partial)
        self.assertEqual(record["verdict"], "ungated")
        self.assertFalse(record["verification_complete"])
        self.assertIn("judge", audit)


    def test_missing_explanation_cannot_pass(self):
        def missing_reason(prompt, **kwargs):
            data = judge(prompt)
            for run in data["runs"]:
                run[0].pop("reason")
            return data
        record, audit = self.verify({"https://example.com/one": LATE}, missing_reason)
        self.assertEqual(record["verdict"], "ungated")

    def test_audit_write_failure_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(fc, "__file__", str(Path(temp) / "career-ops/linkedin_factcheck.py")), patch.object(fc, "run_judge", side_effect=judge), patch.object(Path, "write_text", side_effect=OSError("disk full")):
                record = fc.verify_post(LATE, ["https://example.com/one"], source_texts={"https://example.com/one": LATE}, api_key="test")
        self.assertEqual(record["verdict"], "ungated")
        self.assertIn("audit", record["reason"].lower())


if __name__ == "__main__":
    unittest.main()
