"""Keep public vacancy-status evidence out of the owner's runtime during tests."""
import pathlib,sys
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1] / "discovery"))
@pytest.fixture(autouse=True)
def private_liveness_test_cache(tmp_path,monkeypatch):
    import job_liveness
    monkeypatch.setattr(job_liveness,'CACHE_PATH',tmp_path/'vacancy-status.json')

@pytest.fixture(scope="session", autouse=True)
def private_newsletter_fixture_root(tmp_path_factory):
    # Session scope also isolates module-scoped scheduled-run fixtures.
    import gmail_discovery
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(gmail_discovery.collect.__kwdefaults__, "root",
                      tmp_path_factory.mktemp("newsletter-fixtures"))
        yield


@pytest.fixture(autouse=True)
def private_verification_evidence(tmp_path, monkeypatch):
    import verification_evidence
    monkeypatch.setattr(verification_evidence, 'ROOT', tmp_path/'verification-evidence')

@pytest.fixture(autouse=True)
def offline_router_reasoning(monkeypatch,tmp_path):
    # External selection is stubbed explicitly in offline regressions.
    source=pathlib.Path(__file__).resolve().parents[2]/'exec-brain'
    monkeypatch.syspath_prepend(str(source))
    import router_brain
    import workflow_routing
    monkeypatch.setattr(workflow_routing,'RECEIPT_ROOT',tmp_path/'workflow-receipts')
    class OfflineBrain:
        def rank(self,candidates,**kwargs):
            return candidates, {'status':'OFFLINE_TEST_ROUTED','provider_call_made':False,'worker_order':[c.worker_id for c in candidates]}
    monkeypatch.setattr(router_brain.RouterBrain,'configured',classmethod(lambda cls:OfflineBrain()))
