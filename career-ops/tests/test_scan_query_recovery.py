import json
import time
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import codex_entry_level_search as direct
import job_scan_delta as delta
import web_research as web
import query_progress as progress
from router_brain import RouterDecisionError

QUERIES = ['cyber placement UK', 'iam internship UK', 'grc graduate UK']
PROMPT = '\n'.join(f'{i}. "{q}"' for i, q in enumerate(QUERIES, 1))


def reply(query):
    return {'web_search_observed':True, 'executed_queries':[query],
            'results':[], 'raw_events':2, 'error':None}


def test_one_brain_decision_authorizes_all_exact_queries(monkeypatch):
    monkeypatch.setattr(web.CodexWebSearchProvider, 'resolve', lambda self:'fixture')
    def execute(*a, **kw):
        events=[{'type':'item.completed','item':{'type':'web_search','query':'observed'}},
                {'type':'item.completed','item':{'type':'agent_message','text':'[]'}}]
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, events)), stderr='')
    with patch('workflow_routing.select',return_value=('codex',{})) as brain, patch('subprocess.run',side_effect=execute) as worker:
        result=direct.run_codex(PROMPT)
    assert brain.call_count==1 and worker.call_count==3
    assert result.evidence['coverage_complete'] is True
    assert all(q in brain.call_args.kwargs['task'] for q in QUERIES)


@pytest.mark.parametrize('change', ['query','model','executable','expired','sandbox','workdir'])
def test_scope_cannot_authorize_other_work(change):
    provider=web.CodexWebSearchProvider(model='fixture')
    with patch('workflow_routing.select',return_value=('codex',{})), patch('subprocess.run') as worker:
        with provider.authorize_batch('fixture',QUERIES,60):
            query=QUERIES[0];exe='fixture'
            if change=='query':query='unauthorized query'
            if change=='model':provider.model='other'
            if change=='sandbox':provider.sandbox='other'
            if change=='workdir':provider.workdir='other'
            if change=='executable':exe='other'
            if change=='expired':provider._batch_scope['deadline']=time.monotonic()-1
            result=provider._run_one(exe,query,limit=1,timeout=20)
            assert result['routing_blocked'] and not result['results']
    worker.assert_not_called()
    assert provider._batch_scope is None


def test_router_denial_dispatches_no_workers(monkeypatch):
    monkeypatch.setattr(web.CodexWebSearchProvider,'resolve',lambda self:'fixture')
    with patch('workflow_routing.select',side_effect=RouterDecisionError('router_cli_timeout')) as brain, patch('subprocess.run') as worker:
        with pytest.raises(direct.SearchUnavailable) as failed:
            direct.run_codex(PROMPT)
        result=failed.value
    assert brain.call_count==1 and not result.evidence['coverage_complete']
    assert result.evidence['queries_completed']==0
    worker.assert_not_called()


def test_only_failed_queries_repeat_and_successes_keep_timestamp(monkeypatch,tmp_path):
    calls=[];failing=[True]
    class Provider:
        def __init__(self,**kw):pass
        def resolve(self):return 'fixture'
        def _run_one(self,exe,query,**kw):
            calls.append(query)
            if query==QUERIES[1] and failing[0]:
                return dict(reply(query),web_search_observed=False,error='search timeout')
            return reply(query)
    monkeypatch.setattr(web,'CodexWebSearchProvider',Provider)
    path=tmp_path/'resume.json'
    first=direct.run_codex(PROMPT,progress_path=path)
    original=json.loads(path.read_text())['records'][QUERIES[0]]['observed_at']
    assert not first.evidence['coverage_complete']
    calls.clear();failing[0]=False
    second=direct.run_codex(PROMPT,progress_path=path)
    assert calls==[QUERIES[1]] and second.evidence['coverage_complete']
    assert second.evidence['queries_completed']==3
    assert json.loads(path.read_text())['records'][QUERIES[0]]['observed_at']==original


def test_routing_block_stops_remaining_attempts(monkeypatch):
    calls=[]
    class Provider:
        def __init__(self,**kw):pass
        def resolve(self):return 'fixture'
        def _run_one(self,exe,query,**kw):
            calls.append(query)
            return dict(reply(query),web_search_observed=False,error='router_cli_timeout',routing_blocked=True)
    monkeypatch.setattr(web,'CodexWebSearchProvider',Provider)
    with pytest.raises(direct.SearchUnavailable) as failed:
        direct.run_codex(PROMPT)
    result=failed.value
    assert calls==QUERIES[:1] and not result.evidence['coverage_complete']
    assert result.evidence['query_receipts'][-1]['error']=='not_attempted_after_routing_block'


def test_dry_run_does_not_write_query_progress(monkeypatch,tmp_path):
    class Provider:
        def __init__(self,**kw):pass
        def resolve(self):return 'fixture'
        def _run_one(self,exe,query,**kw):return reply(query)
    monkeypatch.setattr(web,'CodexWebSearchProvider',Provider)
    path=tmp_path/'resume.json'
    assert direct.run_codex(PROMPT,progress_path=path,persist_progress=False).evidence['coverage_complete']
    assert not path.exists()


@pytest.mark.parametrize('mode',['expired','future','wrong_signature','corrupt','not_observed'])
def test_stale_or_untrusted_progress_is_not_success(tmp_path,mode):
    path=tmp_path/'resume.json';key=progress.signature(PROMPT,'fixture')
    record=dict(reply(QUERIES[0]),observed_at=time.time())
    progress.save(path,key,{QUERIES[0]:record})
    doc=json.loads(path.read_text())
    if mode=='expired':doc['created_at']-=progress.MAX_AGE+1
    if mode=='future':doc['created_at']+=3600
    if mode=='wrong_signature':doc['signature']='wrong'
    if mode=='not_observed':doc['records'][QUERIES[0]]['web_search_observed']=False
    path.write_text('{invalid' if mode=='corrupt' else json.dumps(doc))
    assert progress.load(path,key,QUERIES)=={}


def test_alert_reports_router_category_without_raw_tail():
    summary={'batches':[{'exit_code':2,'coverage':{'query_receipts':[{'query_receipts':[
        {'complete':True},{'complete':False,'error':'router_cli_timeout'},
        {'complete':False,'error':'PRIVATE-provider-content'}]}]}}]}
    text=delta.failure_summary(summary)
    assert '1/3 queries completed' in text and 'router_cli_timeout=1' in text
    assert 'PRIVATE' not in text and 'search_worker_failed=1' in text


def test_direct_search_tests_do_not_use_owner_retry_state(tmp_path):
    assert direct.SEARCH_STATE_DIR == tmp_path / 'direct-search'
    assert not direct.SEARCH_STATE_DIR.exists()


def test_credential_helpers_do_not_share_mutable_windows_function_types(monkeypatch):
    import ctypes
    import gemini_keyaccess as gemini
    import deepseek_keyaccess as deepseek
    shared = ctypes.windll.advapi32.CredReadW
    assert gemini._advapi32.CredReadW is not deepseek._advapi32.CredReadW
    assert gemini._advapi32.CredReadW is not shared
    assert deepseek._advapi32.CredReadW is not shared
    monkeypatch.setattr(shared, 'argtypes', [ctypes.c_void_p])
    for helper in (gemini, deepseek):
        assert helper._advapi32.CredReadW.argtypes[-1] == ctypes.POINTER(ctypes.POINTER(helper.CREDENTIAL))
