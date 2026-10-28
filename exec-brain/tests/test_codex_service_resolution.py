from pathlib import Path
from types import SimpleNamespace
import pytest
import codex_adapter as adapter
from router_brain import cli_failure_code
import native_router_plugin as plugin


def environment(monkeypatch,tmp_path):
    for name in adapter.CODEX_EXECUTABLE_ENV:monkeypatch.delenv(name,raising=False)
    shim=tmp_path/'node/codex.cmd';shim.parent.mkdir();shim.touch()
    older=tmp_path/'desktop/old/codex.exe';older.parent.mkdir(parents=True);older.touch()
    newer=tmp_path/'desktop/new/codex.exe';newer.parent.mkdir(parents=True);newer.touch()
    versions={shim:'codex-cli 0.156.1',older:'codex-cli 0.164.0-alpha.11.1',newer:'codex-cli 0.165.0-alpha.1.2'}
    monkeypatch.setattr(adapter,'_codex_version_of',lambda p:versions.get(p))
    monkeypatch.setattr(adapter,'_installed_codex_candidates',lambda:[older,newer])
    monkeypatch.setattr(adapter.shutil,'which',lambda name:str(shim) if name=='codex' else None)
    return shim,older,newer,versions


def test_service_path_cannot_shadow_validated_desktop_install(monkeypatch,tmp_path):
    shim,older,newer,versions=environment(monkeypatch,tmp_path)
    assert adapter._resolve_codex_executable()==newer


def test_interactive_and_service_paths_select_the_same_desktop_build(monkeypatch,tmp_path):
    shim,older,newer,versions=environment(monkeypatch,tmp_path)
    from_service=adapter._resolve_codex_executable()
    monkeypatch.setattr(adapter.shutil,'which',lambda name:str(older))
    assert adapter._resolve_codex_executable()==from_service==newer


def test_explicit_owner_executable_override_is_preserved(monkeypatch,tmp_path):
    shim,older,newer,versions=environment(monkeypatch,tmp_path)
    monkeypatch.setenv('CODEX_EXECUTABLE',str(older))
    assert adapter._resolve_codex_executable()==older


def test_invalid_desktop_builds_do_not_hide_the_only_working_launcher(monkeypatch,tmp_path):
    shim,older,newer,versions=environment(monkeypatch,tmp_path)
    versions.pop(older);versions.pop(newer)
    assert adapter._resolve_codex_executable()==shim


def test_model_incompatibility_is_not_collapsed_into_generic_configuration():
    result={'status':'FAILED','stderr':"The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account. model_not_found"}
    assert cli_failure_code(result)=='router_cli_model_unsupported'


def test_router_failure_heading_does_not_blame_the_uncontacted_provider():
    emitted=[]
    agent=SimpleNamespace(_emit_diagnostic_status=emitted.append)
    classified=SimpleNamespace(error_context={'component':'router_brain','router_failure':'router_cli_model_unsupported'})
    def terminal(agent,classified):
        agent._emit_diagnostic_status("Nous Portal rejected the request and retrying won't help")
        return 'kept-terminal-contract'
    module=SimpleNamespace(nonretryable_copy=lambda *a,**k:'original',nonretryable_client_error_result=terminal)
    plugin.install_failure_copy(module)
    assert module.nonretryable_client_error_result(agent,classified)=='kept-terminal-contract'
    assert 'Nous' not in emitted[0]
    assert 'Codex' in emitted[0] or 'Routing' in emitted[0]
