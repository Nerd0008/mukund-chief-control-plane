import sys
import json
import tempfile
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


def test_live_owner_and_history_adapters_are_bounded_and_provenanced():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills/personal/mukund-owner-context").mkdir(parents=True)
        (root / "skills/personal/mukund-company-registry/references").mkdir(parents=True)
        (root / "skills/personal/mukund-owner-context/SKILL.md").write_text(
            "Owner context fixture: personal preferences live locally.", encoding="utf-8")
        (root / "skills/personal/mukund-company-registry/SKILL.md").write_text(
            "Company registry fixture: Career Ops is a department.", encoding="utf-8")
        history = root / "archive"
        history.mkdir()
        (history / "chief.jsonl").write_text(
            json.dumps({"role": "owner", "content": "Previous Chief conversation fixture."}) + "\n",
            encoding="utf-8")
        compiler = ChiefContextCompiler(root=Path(__file__).resolve().parents[2], local_context_root=root,
                                        history_root=history)
        package = compiler.compile("Based on all our previous conversations, what do you know about me?")
        ids = {row["source_id"] for row in package["source_manifest"]}
        assert {"owner-context-local", "company-registry-local", "discord-chief-history"} <= ids
        assert package["chars_included"] <= package["char_budget"]
        assert compiler.validate(package) == []


def test_required_tail_fact_cannot_pass_as_complete():
    source=ContextSource('required-profile','synthetic.md','A'*4000+' IMPORTANT TAIL FACT','owner')
    compiler=ChiefContextCompiler(sources=[source])
    package=compiler.compile('profile',required_source_ids=['required-profile'])
    assert not package['coverage_complete']
    assert package['source_manifest'][0]['complete'] is False
    assert compiler.validate(package)==['required source incomplete: required-profile']


def test_exhausted_and_missing_required_sources_are_reported():
    compiler=ChiefContextCompiler(max_chars=3,sources=[ContextSource('a','a','AAAA','owner'),ContextSource('b','b','BBBB','owner')])
    package=compiler.compile('profile',required_source_ids=['b','missing'])
    assert package['omitted_source_ids']==['b']
    assert len(compiler.validate(package))==2
