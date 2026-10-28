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


@pytest.fixture(autouse=True)
def private_direct_search_retry_state(tmp_path, monkeypatch):
    # Direct-search integration tests must never consume/delete the owner's
    # pending candidate or query-progress files, regardless of test ordering.
    import codex_entry_level_search
    monkeypatch.setattr(codex_entry_level_search, 'SEARCH_STATE_DIR', tmp_path/'direct-search')


@pytest.fixture(autouse=True)
def private_controller_health(tmp_path,monkeypatch):
    source=pathlib.Path(__file__).resolve().parents[2]/'exec-brain'
    monkeypatch.syspath_prepend(str(source))
    import workflow_health
    monkeypatch.setattr(workflow_health,'DB_PATH',tmp_path/'native-health.sqlite3')


@pytest.fixture(autouse=True)
def private_codex_admission(tmp_path,monkeypatch):
    import codex_admission
    monkeypatch.setattr(codex_admission,'ROOT',tmp_path/'codex-admission')
