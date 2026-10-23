import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "linkedin_factcheck.py"
spec = importlib.util.spec_from_file_location("linkedin_factcheck", MODULE_PATH)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)


def inputs(prompt):
    return json.loads(prompt.split("\nCLAIMS:\n", 1)[1].split("\nSOURCE:\n", 1)[0])


def response(prompt, verdict="supported", evidence="The Port of Rotterdam went offline on October 21.", runs=3):
    claims = [dict(item, verdict=verdict, evidence=evidence,
                   reason="The source establishes the sentence.") for item in inputs(prompt)]
    return {"reason": None, "runs": [[dict(a) for a in claims] for _ in range(runs)],
            "receipt": {"prompt_chars": len(prompt), "prompt_sha256": fc.sha256_text(prompt)}}


class TestClaimJudging(unittest.TestCase):
    def test_fixed_ids_prevent_paraphrase_duplicates(self):
        seen = []
        def judge(prompt, **kwargs):
            seen.extend(inputs(prompt))
            return response(prompt)
        with patch.object(fc, "run_judge", side_effect=judge):
            result = fc.llm_verify_claims("The port went offline.",
                    "The Port of Rotterdam went offline on October 21.", api_key="test")
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["claims"]), 1)
        self.assertEqual(result["claims"][0]["judge_runs"], 3)
        self.assertEqual(result["claims"][0]["claim_id"], seen[0]["claim_id"])

    def test_supported_claim_requires_actual_source_quote(self):
        with patch.object(fc, "run_judge", side_effect=lambda p, **k: response(p, evidence="An invented source quotation.")):
            result = fc.llm_verify_claims("The port went offline.", "Unrelated source.", api_key="test")
        self.assertFalse(result["complete"])
        self.assertEqual(result["claims"][0]["verdict"], "incomplete")

    def test_missing_run_is_incomplete(self):
        with patch.object(fc, "run_judge", side_effect=lambda p, **k: response(p, runs=2)):
            result = fc.llm_verify_claims("The port went offline.",
                    "The Port of Rotterdam went offline on October 21.", api_key="test")
        self.assertFalse(result["complete"])

    def test_duplicate_and_missing_ids_are_incomplete(self):
        def judge(prompt, **kwargs):
            data = response(prompt)
            for run in data["runs"]:
                run.append(dict(run[0]))
            return data
        with patch.object(fc, "run_judge", side_effect=judge):
            result = fc.llm_verify_claims("The port went offline.",
                    "The Port of Rotterdam went offline on October 21.", api_key="test")
        self.assertFalse(result["complete"])

    def test_timing_contradiction_still_blocks(self):
        quote = "The Port of Rotterdam went offline on October 21."
        def judge(prompt, **kwargs):
            self.assertIn("Evaluation date: 2026-10-23", prompt)
            data = response(prompt, verdict="contradicted", evidence=quote)
            for run in data["runs"]:
                run[0]["reason"] = "October 21 is this week, not last week, relative to October 23."
            return data
        with patch.object(fc, "now_utc", return_value="2026-10-23T15:00:00+00:00"), patch.object(fc, "run_judge", side_effect=judge):
            result = fc.llm_verify_claims("The port went offline last week.", quote, api_key="test")
        self.assertTrue(result["complete"])
        self.assertEqual(result["claims"][0]["verdict"], "contradicted")
        self.assertIn("this week", result["claims"][0]["reason"])

    def test_single_supported_vote_does_not_override_rejections(self):
        quote = "The Port of Rotterdam went offline on October 21."
        def judge(prompt, **kwargs):
            data = response(prompt, verdict="unsupported", evidence="")
            data["runs"][0][0].update(verdict="supported", evidence=quote)
            return data
        with patch.object(fc, "run_judge", side_effect=judge):
            result = fc.llm_verify_claims("The port went offline.", quote, api_key="test")
        self.assertTrue(result["complete"])
        self.assertEqual(result["claims"][0]["verdict"], "unsupported")

    def test_verbatim_sentence_is_required(self):
        def judge(prompt, **kwargs):
            data = response(prompt)
            for run in data["runs"]:
                run[0]["claim"] = "A different paraphrase"
            return data
        with patch.object(fc, "run_judge", side_effect=judge):
            result = fc.llm_verify_claims("The port went offline.",
                    "The Port of Rotterdam went offline on October 21.", api_key="test")
        self.assertFalse(result["complete"])



class TestJudgeTransportAndProvenance(unittest.TestCase):
    def test_actual_child_receives_full_prompt_and_retains_raw_responses(self):
        import sys
        prelude = """import types,sys
google = types.ModuleType('google')
google.genai = types.SimpleNamespace(Client=lambda **kw: types.SimpleNamespace(models=types.SimpleNamespace(generate_content=lambda **kw: types.SimpleNamespace(text='{"claims":[]}'))))
sys.modules['google'] = google
"""
        prompt = "A" * 16000 + "A late passage with Unicode: café." + "B" * 100000
        with patch.object(fc, "resolve_judge_interpreter", return_value=sys.executable), patch.object(fc, "_JUDGE_CHILD", prelude + fc._JUDGE_CHILD):
            result = fc.run_judge(prompt, model="fake", api_key="fake", runs=3)
        self.assertIsNone(result["reason"])
        self.assertEqual(result["receipt"]["prompt_sha256"], fc.sha256_text(prompt))
        self.assertEqual(result["receipt"]["prompt_chars"], len(prompt))
        self.assertEqual(len(result["responses"]), 3)
        self.assertEqual(result["responses"][0]["raw"], '{"claims":[]}')

    def test_receipt_mismatch_is_incomplete(self):
        from types import SimpleNamespace
        proc = SimpleNamespace(stdout=json.dumps({"runs": [[]] * 3, "receipt": {"prompt_chars": 1, "prompt_sha256": "wrong"}}), returncode=0)
        with patch.object(fc, "resolve_judge_interpreter", return_value="fake"), patch.object(fc.subprocess, "run", return_value=proc):
            result = fc.run_judge("A full prompt", model="fake", api_key="fake", runs=3)
        self.assertIn("receipt", result["reason"])
        self.assertEqual(result["runs"], [])

    def test_old_or_incomplete_pass_cannot_be_reused(self):
        body = "A post."
        gate = {"gate_name": fc.GATE_NAME, "gate_version": 1, "verification_complete": True,
                "body_sha256": fc.sha256_text(body), "verdict": "pass"}
        self.assertFalse(fc.provenance_ok(gate, body)[0])
        gate.update(gate_version=fc.GATE_VERSION, verification_complete=False)
        self.assertFalse(fc.provenance_ok(gate, body)[0])
        gate["verification_complete"] = True
        self.assertTrue(fc.provenance_ok(gate, body)[0])

    def test_source_less_claims_still_work(self):
        with patch.object(fc, "run_judge", return_value={"reason": None, "runs": [[{"claim": "The moon is cheese"}]] * 3}):
            result = fc.llm_check_no_world_claims("The moon is cheese", api_key="fake")
        self.assertTrue(result["used"])
        self.assertEqual(len(result["claims"]), 1)

    def test_source_less_partial_run_cannot_pass(self):
        with patch.object(fc, "run_judge", return_value={"reason": None, "runs": [[]]}):
            result = fc.llm_check_no_world_claims("My own reflection", api_key="fake")
        self.assertFalse(result["used"])



class TestSourceQuotationFormatting(unittest.TestCase):
    def test_markdown_link_text_and_html_entities_are_valid_quotes(self):
        source = "Developers [released urgent new fixes](https://example.com/fix) in PHP&#46; Older versions have reached end of life ."
        self.assertTrue(fc._evidence_present("Developers released urgent new fixes in PHP.", source))
        self.assertTrue(fc._evidence_present("Older versions have reached end of life.", source))

    def test_bracketed_omission_preserves_exact_fragments(self):
        source = "Two flaws are grouped under two CVEs, with severity reaching CVSS 9.2. Some other text. These vulnerabilities allow unauthenticated remote code execution in PHP itself."
        evidence = "grouped under two CVEs, with severity reaching CVSS 9.2. [...] These vulnerabilities allow unauthenticated remote code execution in PHP itself."
        self.assertTrue(fc._evidence_present(evidence, source))

    def test_formatting_normalisation_never_changes_facts(self):
        source = "A [single researcher](https://example.com) completed the work in a week&#46;"
        self.assertFalse(fc._evidence_present("A single researcher completed the work in a day.", source))
        self.assertFalse(fc._evidence_present("A single researcher completed the work in a week. [...] This invented detail was not reported.", source))


if __name__ == "__main__":
    unittest.main()
