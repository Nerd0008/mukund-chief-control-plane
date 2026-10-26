"""Inventory regressions use disposable paths, never the live runtime."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_contract as contract
import deploy_e3_runtime as deploy


def test_every_deployed_module_is_declared():
    assert set(deploy.E3_MODULES) <= set(contract.source_files())
    assert all(p.is_file() for p in contract.source_files().values())


def test_future_deployment_declaration_needs_no_second_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, 'SRC_DIR', tmp_path)
    monkeypatch.setattr(deploy, 'E3_MODULES', ['future_module.py'])
    assert contract.source_files()['future_module.py'] == tmp_path / 'future_module.py'


def test_unknown_files_reported_together(tmp_path):
    for name in ['rogue.py', 'rogue.db', 'old.bak', '.pytest_cache']:
        (tmp_path / name).touch()
    report = contract.audit_runtime(tmp_path)
    assert not report['ok']
    assert report['unexpected'] == ['.pytest_cache', 'old.bak', 'rogue.db', 'rogue.py']


def test_only_declared_database_sidecars_allowed(tmp_path):
    for name in contract.DATABASES:
        for suffix in ['', '-wal', '-shm']:
            (tmp_path / (name + suffix)).touch()
    assert contract.audit_runtime(tmp_path)['ok']


def test_configuration_contents_are_not_read(tmp_path):
    for name in contract.STATE_FILES:
        (tmp_path / name).write_text('PRIVATE_SENTINEL', encoding='utf-8')
    report = contract.audit_runtime(tmp_path)
    assert report['ok'] and 'PRIVATE_SENTINEL' not in str(report)


def test_allowed_filename_cannot_be_directory(tmp_path):
    (tmp_path / 'router_brain.py').mkdir()
    assert contract.audit_runtime(tmp_path)['wrong_type'] == ['router_brain.py']


def test_runtime_missing_fails_closed(tmp_path):
    report = contract.audit_runtime(tmp_path / 'absent')
    assert not report['ok'] and report['runtime_missing']


def test_unbacked_source_declaration_fails(tmp_path):
    report = contract.audit_runtime(tmp_path, source_root=tmp_path / 'missing-source')
    assert not report['ok'] and 'governor.py' in report['missing_source']
