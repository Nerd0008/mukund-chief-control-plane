import json,time
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as NS
import pytest

def test_search_only_default_is_codex():
    from discovery import pipeline,scheduled_orchestrator
    assert pipeline.DEFAULT_SEMANTIC==scheduled_orchestrator.DEFAULT_SEMANTIC=='codex'
    root=Path(__file__).resolve().parents[1]
    assert '--semantic codex' in (root/'run_scheduled_scan.cmd').read_text(encoding='utf-8')

def test_cv_model_argument_cannot_force_codex(tmp_path,monkeypatch):
    import hermes_cv_compiler_guard as guard
    from workflow_control import CONTENT_WORKER
    seen=[];monkeypatch.setattr(guard,'OUTPUT_ROOT',tmp_path)
    def compile(*a,**kw):seen.append(a[3]);return {'status':'FAIL','delivery_allowed':False}
    monkeypatch.setattr(guard,'compile_prototype',compile)
    token=guard.JOB.set({'deadline':time.monotonic()+180,'attempted':False,'cv_active':True})
    preference=CONTENT_WORKER.set(None)
    try:
        guard.compile_tool({'jd':'synthetic','job_id':'fixture','company':'Example','short_role':'Engineer','content_worker':'codex'})
        assert seen==[guard.generate]
    finally:CONTENT_WORKER.reset(preference);guard.JOB.reset(token)

def test_default_text_worker_offers_native_and_codex():
    import workflow_routing as wr
    from workflow_control import CONTENT_WORKER
    sdk=NS(chat=NS(completions=NS(create=lambda **kw:'response')))
    token=CONTENT_WORKER.set(None);seen=[]
    def choose(workflow,offers,**kw):seen.extend(o['id'] for o in offers);return 'native',{}
    try:
        with patch.object(wr,'select',side_effect=choose):
            wr.RoutedClient(sdk,'native-provider','model').chat.completions.create(messages=[])
    finally:CONTENT_WORKER.reset(token)
    assert seen==['native','codex']
