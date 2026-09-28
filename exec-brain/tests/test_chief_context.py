import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chief_context import ChiefContextCompiler, ContextSource


def _compiler(**kwargs):
    return ChiefContextCompiler(sources=(
        ContextSource("owner-context", "state/current_company_state.md",
                      "Mukund owns the Hermes project and is building Chief OS."),
        ContextSource("company-registry", "state/v1-agent-roster.md",
                      "Career Ops owns UK, Dubai, Japan and Singapore job-search workers."),
        ContextSource("secret-fixture", "private.txt", "api_key=DO_NOT_INCLUDE"),
    ), **kwargs)


def test_owner_query_uses_persistent_context_and_provenance():
    package = _compiler().compile("Based on all our previous conversations, what do you know about me?")
    ids = {row["source_id"] for row in package["source_manifest"]}
    assert {"owner-context", "company-registry"} <= ids
    assert package["inferences"] == []
    assert package["chars_included"] <= package["char_budget"]


def test_job_search_query_keeps_career_ops_reachable():
    package = _compiler().compile("What do you know about my existing job-search agent?")
    assert any(row["source_id"] == "company-registry" for row in package["source_manifest"])
    assert "Career Ops" in repr(package)


def test_budget_and_secrets_are_enforced():
    package = _compiler(max_chars=40, source_limit=40).compile("company project")
    assert package["chars_included"] <= 40
    assert "DO_NOT_INCLUDE" not in repr(package)
    assert _compiler().validate(package) == []


def test_context_package_is_provider_independent():
    one = _compiler().compile("company project")
    two = _compiler().compile("company project")
    assert one == two
