import importlib.util
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "linkedin_factcheck.py"
spec = importlib.util.spec_from_file_location("linkedin_factcheck", MODULE_PATH)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)


def test_focused_recheck_recovers_supported_claim_but_keeps_unsupported_claim():
    source = "Reuters reports that the Port of Rotterdam and several hospital websites went offline."
    seen = []

    def judge(prompt, **kwargs):
        seen.append(prompt)
        if len(seen) == 1:
            return {"reason": None, "runs": [[
                {"claim": "Port and hospital websites went offline", "verdict": "unsupported", "evidence": ""},
                {"claim": "The moon is made of cheese", "verdict": "unsupported", "evidence": ""},
            ]] * 3}
        claim = "Port and hospital websites went offline" if "CLAIM:\nPort" in prompt else "The moon is made of cheese"
        answer = {"claim": claim, "verdict": "supported" if claim.startswith("Port") else "unsupported",
                  "evidence": "the Port of Rotterdam and several hospital websites went offline" if claim.startswith("Port") else ""}
        return {"reason": None, "runs": [[answer]] * 3}

    with patch.object(fc, "run_judge", side_effect=judge):
        result = fc.llm_verify_claims("Port and hospital websites went offline. The moon is made of cheese.",
                                      source, api_key="test")

    assert [c["verdict"] for c in result["claims"]] == ["supported", "unsupported"]
    assert result["claims"][0]["evidence"]
    assert len(seen) == 3
    assert source in seen[1] and source in seen[2]


def test_focused_recheck_does_not_accept_missing_evidence_or_runs():
    calls = 0

    def judge(prompt, **kwargs):
        nonlocal calls
        calls += 1
        answer = {"claim": "Unsupported claim", "verdict": "supported" if calls > 1 else "unsupported",
                  "evidence": ""}
        return {"reason": None, "runs": [[answer]] * (3 if calls == 1 else 2)}

    with patch.object(fc, "run_judge", side_effect=judge):
        result = fc.llm_verify_claims("Unsupported claim", "Source", api_key="test")
    assert result["claims"][0]["verdict"] == "unsupported"


def test_focused_excerpt_keeps_relevant_later_source():
    source = ("[SOURCE: first]\n" + "Unrelated opening.\n\n" +
              "[SOURCE: second]\n" + "A single researcher with an AI model completed in a week "
              "what would have taken a team months of work.")
    excerpt = fc.focused_source_excerpt(source, "One researcher with an AI model did in a week what a team would take months")
    assert "[SOURCE: second]" in excerpt
    assert "completed in a week" in excerpt
