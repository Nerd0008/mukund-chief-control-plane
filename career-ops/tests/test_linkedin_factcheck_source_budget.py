import importlib.util
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "linkedin_factcheck.py"
spec = importlib.util.spec_from_file_location("linkedin_factcheck", MODULE_PATH)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)


def test_second_source_reaches_claim_judge():
    sources = {
        "https://example.com/first": "A" * 14000,
        "https://example.com/second": "B" * 7000 + "Grounding fact: blue otters sing." + "B" * 6000,
    }
    combined = fc.combine_sources(sources)
    assert len(combined) > 20000
    assert combined.index("Grounding fact") > 20000
    prompts = []

    def judge(prompt, **kwargs):
        prompts.append(prompt)
        return {"reason": None, "runs": [[{
            "claim": "Blue otters sing", "verdict": "supported",
            "evidence": "Grounding fact: blue otters sing.",
        }]]}

    with patch.object(fc, "run_judge", side_effect=judge):
        record = fc.verify_post("Blue otters sing.", list(sources),
                                source_texts=sources, api_key="test-key")

    assert "Grounding fact: blue otters sing." in prompts[0]
    assert record["source_chars_total"] == len(combined)
    assert record["source_chars_fed"] == len(combined)


def test_late_passage_is_not_cut_from_an_individual_source():
    late = "A single researcher completed in a week what a team would take months."
    source = "A" * 15000 + late
    combined = fc.combine_sources({"https://example.com/wiz": source})
    assert late in combined
    assert len(combined) > 15000
