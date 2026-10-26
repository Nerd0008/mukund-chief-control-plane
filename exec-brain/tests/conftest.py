"""Run E3 tests against repository source with isolated controller health."""
import sys,os,importlib.util
from pathlib import Path
import pytest
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
sys.path.append(str(Path(os.environ.get('LOCALAPPDATA',''))/'hermes/hermes-agent'))

@pytest.fixture(autouse=True)
def private_controller_health(tmp_path,monkeypatch):
    if importlib.util.find_spec('workflow_health') is not None:
        import workflow_health
        monkeypatch.setattr(workflow_health,'DB_PATH',tmp_path/'native-health.sqlite3')
