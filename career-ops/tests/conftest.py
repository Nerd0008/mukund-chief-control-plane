"""Keep public vacancy-status evidence out of the owner's runtime during tests."""
import pathlib,sys
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
@pytest.fixture(autouse=True)
def private_liveness_test_cache(tmp_path,monkeypatch):
    import job_liveness
    monkeypatch.setattr(job_liveness,'CACHE_PATH',tmp_path/'vacancy-status.json')
