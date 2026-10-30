import json,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"cv-template-prototype"))
from types import SimpleNamespace as NS
import pytest
import cv_template as cv
import cv_validation_mode as mode
import cv_tailoring_grounding as grounding
import cv_role_writer as writer
import hermes_cv_compiler_guard as guard
import application_package_state as package
from test_role_tailoring import fixture,JD

@pytest.fixture(autouse=True)
def private_authority(tmp_path,monkeypatch):
    monkeypatch.setattr(grounding,'ROOT',tmp_path/'reviews')
    monkeypatch.setenv('CV_TAILORING_REVIEW_ROOT',str(tmp_path/'reviews'))

def test_production_is_default_even_for_bad_or_partial_config():
    path=mode.config_path();path.parent.mkdir(parents=True,exist_ok=True)
    for text in ['{','null','[]','{"canonical_fact_gate_enabled":false}',
                 '{"mode":"production","canonical_fact_gate_enabled":false}',
                 '{"mode":"development","canonical_fact_gate_enabled":"false"}']:
        path.write_text(text,encoding='utf-8')
        assert mode.canonical_gate_enabled()
    mode.configure(True);assert not mode.canonical_gate_enabled()
    mode.configure(False);assert mode.canonical_gate_enabled()

def test_development_receipt_cannot_be_issued_in_production():
    layout,content,requirements,review=fixture()
    with pytest.raises(ValueError,match='not enabled'):
        grounding.issue(content,requirements,layout,JD,review,{}, {'status':mode.DISABLED})

def test_development_receipt_is_rejected_after_production_is_restored():
    layout,content,requirements,review=fixture()
    mode.configure(True)
    content=grounding.issue(content,requirements,layout,JD,review,{}, {'status':mode.DISABLED})
    assert not cv.content_check(layout,content)
    mode.configure(False)
    assert any(f['reason']=='unverified/invented content' for f in cv.content_check(layout,content))

def test_development_skips_both_factual_checks_and_records_it_honestly(tmp_path,monkeypatch):
    import workflow_routing,cv_workflow
    layout,content,requirements,review=fixture()
    replies=iter([{'content':content,'requirements':requirements}]);calls=[]
    def complete(*a,**k):
        calls.append(k['workflow'])
        return NS(model='fixture',choices=[NS(finish_reason='stop',message=NS(content=json.dumps(next(replies))))]),{'selected_provider':'fixture'}
    monkeypatch.setattr(workflow_routing,'complete_text',complete)
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**k:pytest.fail('disabled canonical gate was called'))
    mode.configure(True)
    content=writer.generate({'jd':JD,'mode':'generate','workspace':str(tmp_path)})
    assert not cv.content_check(layout,content)
    assert writer.generate.last_metadata['validation_mode']=='DEVELOPMENT'
    assert json.loads((tmp_path/'canonical-fact-gate.json').read_text())=={'status':mode.DISABLED,'available':False,'verdict':'not_run','exit_code':None}
    assert calls==['career.cv.tailor']
    assert writer.generate.last_metadata['independent_fact_review']==mode.DISABLED
    assert json.loads((tmp_path/'independent-review.json').read_text())['facts_verified'] is False
    receipt=json.loads((grounding.ROOT/(content['s04']['review_receipt']+'.json')).read_text())
    assert receipt['payload']['canonical_fact_gate']==mode.DISABLED
    assert receipt['payload']['independent_fact_review']==mode.DISABLED

class ReviewedFixture:
    requires_tailoring=True
    def __init__(self,content):self.content=content
    def __call__(self,request):return self.content
    @property
    def last_metadata(self):return {'model_calls':0,'validation_mode':'DEVELOPMENT','canonical_fact_gate':mode.DISABLED}

def test_development_pdf_matches_production_design_and_normal_filename(tmp_path,monkeypatch):
    layout,content,requirements,review=fixture();mode.configure(True)
    content=grounding.issue(content,requirements,layout,JD,review,{}, {'status':mode.DISABLED})
    monkeypatch.setattr(guard,'generate',ReviewedFixture(content))
    monkeypatch.setattr(guard,'OUTPUT_ROOT',tmp_path/'compiled')
    monkeypatch.setattr(guard,'EXPORT_ROOT',tmp_path/'exports')
    state={'session_id':'development-fixture','cv_only':True,'cv_active':False}
    token=guard.JOB.set(state)
    try:result=json.loads(guard.compile_tool({'jd':JD,'job_id':'fixture','company':'HP Wolf','short_role':'Browser Software'}))
    finally:guard.JOB.reset(token)
    assert result['status']=='PASS',result
    assert result['validation_mode']=='DEVELOPMENT'
    assert Path(result['verified_pdf']).name=='Mukund_HP_Wolf_Browser_Software_CV.pdf'
    assert guard.verified_attachment(result['verified_pdf'])
    assert package.render(state).startswith('CV: ready.')
    assert package.outcome(state)=='DEVELOPMENT_READY'
    import pymupdf
    with pymupdf.open(result['verified_pdf']) as pdf:assert 'TEST ONLY' not in pdf[0].get_text()
    assert cv.validate(layout,content,result['verified_pdf'])['status']=='PASS'
    mode.configure(False)
    assert not guard.verified_attachment(result['verified_pdf'])


def test_live_context_recognizes_development_switch():
    import asyncio
    mode.configure(True)
    runtime=NS(_current_max_iterations=lambda:150)
    class Turn:
        async def _run_agent(self,message,context,history,*a,**k):return {'context':context}
    class Media:
        async def send_document(self,*a,**k):return True
    guard.install_runtime(runtime,Turn,Media)
    result=asyncio.run(Turn()._run_agent('Build my CV','',[],None,'development-context'))
    assert 'canonical CV fact gate is disabled by the owner' in result['context']
    assert 'no visible test label' in result['context']


def test_failed_build_still_reports_active_development_setting(monkeypatch):
    mode.configure(True)
    monkeypatch.setattr(guard,'compile_prototype',lambda *a,**k:{'status':'FAIL','reason':'fixture provider failure','delivery_allowed':False})
    token=guard.JOB.set({'cv_active':False})
    try:result=json.loads(guard.compile_tool({'jd':JD,'job_id':'fixture','company':'HP','short_role':'Browser Software'}))
    finally:guard.JOB.reset(token)
    assert result['status']=='FAIL' and result['validation_mode']=='DEVELOPMENT'
    assert 'disabled by owner' in result['validation_note']


def test_development_can_exercise_synthetic_metrics_but_production_rejects_them():
    layout,content,requirements,_=fixture()
    content['s21']['text']='Handled 77777 access requests in a synthetic test fixture.'
    plan={'content':content,'requirements':requirements}
    mode.configure(True)
    parsed,_=grounding.parse_plan(plan,layout,JD)
    assert '77777' in parsed['s21']['text']
    mode.configure(False)
    with pytest.raises(ValueError,match='numeric claim'):
        grounding.parse_plan(plan,layout,JD)


def test_compact_development_schema_has_one_version_and_only_affected_patch_slots():
    layout=cv.load_layout()
    schema=writer.response_schema(layout,compact=True,affected=['s21'])
    assert schema['properties']['content']['required']==['s21']
    assert schema['properties']['content']['properties']['s21']['properties']['alternatives']['maxItems']==0


def test_compact_fit_correction_preserves_all_unaffected_content(monkeypatch):
    import workflow_routing
    layout,content,requirements,_=fixture();mode.configure(True)
    patch={'content':{'s21':content['s21']},'requirements':requirements}
    def complete(*a,**k):
        assert k['response_schema']['properties']['content']['required']==['s21']
        return NS(model='fixture',choices=[NS(finish_reason='stop',message=NS(content=json.dumps(patch)))]),{'selected_provider':'fixture'}
    monkeypatch.setattr(workflow_routing,'complete_text',complete)
    result=writer.generate({'jd':JD,'mode':'shorten','content':content,'affected':['s21']})
    assert set(result)=={'s21'}
    assert grounding.valid_item('s21',result['s21'],layout)
