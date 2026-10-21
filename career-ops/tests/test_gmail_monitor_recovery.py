import json
import subprocess
import sys
from pathlib import Path

import pytest
import career_mail_monitor as monitor
from career_google_auth import GoogleError


def test_overlap_refused_and_exception_releases_lock(tmp_path):
    with pytest.raises(RuntimeError):
        with monitor.scan_lock(tmp_path):
            with pytest.raises(ValueError, match='another Gmail scan'):
                with monitor.scan_lock(tmp_path):
                    pytest.fail('overlapping scan admitted')
            raise RuntimeError('interrupted scan')
    with monitor.scan_lock(tmp_path):
        pass


def test_crash_releases_operating_system_lock(tmp_path):
    code = '''import os,sys
sys.path.insert(0,sys.argv[1])
from career_mail_monitor import scan_lock
with scan_lock(sys.argv[2]):
    os._exit(7)
'''
    result = subprocess.run([sys.executable, '-c', code, str(Path(monitor.__file__).parent), str(tmp_path)], timeout=20)
    assert result.returncode == 7
    with monitor.scan_lock(tmp_path):
        pass


def test_failed_scheduled_scan_saves_safe_health_without_checkpoint(tmp_path, monkeypatch, capsys):
    cfg = tmp_path/'config.json'
    cfg.write_text('{}')
    monitor.atomic_json(tmp_path/'health.json', {'last_success_at': 'last-good'})
    def fail(*a, **k):
        raise GoogleError('reauthorization required', 400, 'invalid_grant')
    monkeypatch.setattr(monitor, 'run_scan', fail)
    assert monitor.main(['scan', '--apply', '--config', str(cfg), '--runtime', str(tmp_path)]) == 1
    health = json.loads((tmp_path/'health.json').read_text())
    assert not health['ok'] and health['owner_action_required']
    assert health['failure_reason'] == 'invalid_grant'
    assert health['last_success_at'] == 'last-good'
    assert not (tmp_path/'checkpoint.json').exists()


def test_status_reports_live_auth_failure_with_nonzero_exit(tmp_path, monkeypatch, capsys):
    cfg = tmp_path/'config.json'
    cfg.write_text('{"scan_interval_minutes":60}')
    calls = []
    def status(**kwargs):
        calls.append(kwargs)
        return {'oauth_ready':False, 'failure_reason':'invalid_grant'}
    monkeypatch.setattr(monitor, 'status', status)
    assert monitor.main(['status', '--config', str(cfg), '--runtime', str(tmp_path)]) == 1
    assert calls == [{'verify':True}]
