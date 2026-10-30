import sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'cv-template-prototype'))
import copy,json
from types import SimpleNamespace as NS
import pytest
import cv_template as cv
import cv_tailoring_grounding as grounding
import cv_role_writer as writer
from cv_content_adapter import resolve_plan

@pytest.fixture(autouse=True)
def private_tailoring_review_authority(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parents[1]/'cv-template-prototype'))
    import cv_tailoring_grounding
    monkeypatch.setenv('CV_TAILORING_REVIEW_ROOT', str(tmp_path/'tailoring-reviews'))
    monkeypatch.setattr(cv_tailoring_grounding, 'ROOT', tmp_path/'tailoring-reviews')

JD='Build Python software tools. Support Windows systems. Communicate technical findings.'

def fixture():
    layout=cv.load_layout()
    bank=json.loads((cv.HERE/'fact_bank.json').read_text(encoding='utf-8'))
    content=resolve_plan({'selections':{key:'engineering' for key in bank['slots']}})
    content={k:{'text':v['text'],'sources':v['sources'],'why':'Prioritises supported engineering evidence for this role.'} for k,v in content.items()}
    requirements=[{'id':'r'+str(i),'quote':quote,'covered_by':['s04']} for i,quote in enumerate(JD.split('. ')[:3])]
    facts=grounding.facts(layout)
    review={'verdict':'pass','slots':{k:{'supported':True,'reason':'The quoted owner evidence supports the factual wording.',
             'evidence':[{'source':v['sources'][0],'quote':facts[v['sources'][0]][:40]}]} for k,v in content.items()},
            'tailoring':{'substantial':True,'reason':'Summary, skills and engineering project emphasis address the stated requirements.',
                         'requirement_ids':[r['id'] for r in requirements]}}
    return layout,content,requirements,review

def test_reviewed_wording_passes_exact_original_geometry(tmp_path):
    layout,content,requirements,review=fixture()
    signed=grounding.issue(content,requirements,layout,JD,review,{}, {'available':True,'exit_code':0})
    assert cv.content_check(layout,signed)==[]
    assert cv.fit(layout,signed)==[]
    path=tmp_path/'tailored.pdf';cv.render(layout,signed,path)
    assert cv.validate(layout,signed,path)['status']=='PASS'

@pytest.mark.parametrize('mutation',['text','sources','why','signature','facts'])
def test_receipt_cannot_authorize_tampered_content(mutation):
    layout,content,requirements,review=fixture()
    signed=grounding.issue(content,requirements,layout,JD,review,{}, {'available':True,'exit_code':0})
    if mutation=='text':signed['s04']['text']='Senior auditor with 20 years of experience.'
    if mutation=='sources':signed['s04']['sources']=['s21']
    if mutation=='why':signed['s04']['why']='different rationale'
    if mutation=='signature':signed['s04']['review_receipt']='0'*64
    if mutation=='facts':layout['slots'][13]['text']+=' altered'
    assert not grounding.valid_item('s04',signed['s04'],layout)

def test_unreviewed_faithful_paraphrase_still_needs_review():
    layout,content,_,_=fixture()
    assert any(f['reason']=='unverified/invented content' for f in cv.content_check(layout,content))

@pytest.mark.parametrize('problem',['blocked','unsupported','empty_evidence','invented_quote','generic','missing_requirements'])
def test_independent_review_fails_closed(problem):
    layout,content,requirements,review=fixture()
    if problem=='blocked':review['verdict']='block'
    if problem=='unsupported':review['slots']['s04']['supported']=False
    if problem=='empty_evidence':review['slots']['s04']['evidence']=[]
    if problem=='invented_quote':review['slots']['s04']['evidence'][0]['quote']='An entirely invented source quote.'
    if problem=='generic':review['tailoring']['substantial']=False
    if problem=='missing_requirements':review['tailoring']['requirement_ids']=[]
    with pytest.raises(ValueError):grounding.issue(content,requirements,layout,JD,review,{}, {'available':True,'exit_code':0})

def test_old_generic_default_and_cosmetic_project_swaps_rejected():
    layout,content,requirements,review=fixture()
    originals={s['id']:s for s in layout['slots']}
    for key,item in content.items():item['text']=originals[key]['text'].removeprefix('\u2022 ')
    with pytest.raises(ValueError,match='generic default'):grounding.review_result(review,content,requirements,layout)
    content['s36']['text']='Built a phishing prototype using Python and the Gmail API.'
    with pytest.raises(ValueError,match='cosmetic'):grounding.review_result(review,content,requirements,layout)

def test_fabricated_number_and_jd_quote_rejected_before_review():
    layout,content,requirements,_=fixture()
    plan={'content':content,'requirements':requirements}
    plan['content']['s21']['text']='I managed 500 experts.'
    with pytest.raises(ValueError,match='numeric'):grounding.parse_plan(plan,layout,JD)
    plan['requirements'][0]['quote']='An invented job requirement nowhere in the JD.'
    with pytest.raises(ValueError,match='quote'):grounding.parse_plan(plan,layout,JD)

def test_canonical_gate_block_cannot_be_signed():
    layout,content,requirements,review=fixture()
    with pytest.raises(ValueError,match='canonical'):grounding.issue(content,requirements,layout,JD,review,{}, {'available':True,'exit_code':1})

def test_writer_calls_independent_review_and_canonical_gate(monkeypatch):
    import workflow_routing,cv_workflow
    layout,content,requirements,review=fixture()
    plan={'content':content,'requirements':requirements}
    replies=iter([plan,review]);calls=[]
    def complete(messages,**kwargs):
        calls.append((messages,kwargs))
        return NS(model='fixture',choices=[NS(finish_reason='stop',message=NS(content=json.dumps(next(replies))))]),{'selected_provider':'fixture'}
    monkeypatch.setattr(workflow_routing,'complete_text',complete)
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**k:{'available':True,'exit_code':0})
    result=writer.generate({'jd':JD,'mode':'generate','worker':'codex'})
    assert cv.content_check(layout,result)==[]
    assert [k['workflow'] for _,k in calls]==['career.cv.tailor','career.cv.review']
    assert writer.generate.last_metadata['model_calls']==2
    assert 'not candidate evidence' in calls[0][0][0]['content']

def test_approved_renderer_and_layout_files_not_changed():
    # Geometry stays an immutable input; no generated content contains layout controls.
    layout,content,_,_=fixture()
    assert all(set(v)=={'text','sources','why'} for v in content.values())
    assert all(s['font_size']==11 for s in layout['slots'] if s['heading'])


def test_review_receipts_are_bound_to_exact_jd():
    layout,content,requirements,review=fixture()
    signed=grounding.issue(content,requirements,layout,JD,review,{}, {'available':True,'exit_code':0})
    assert grounding.matches_jd(signed,JD)
    assert not grounding.matches_jd(signed,JD+' Different role.')


def test_writer_deadline_prevents_starting_when_no_review_time_remains(monkeypatch):
    import time,workflow_routing
    monkeypatch.setattr(workflow_routing,'complete_text',lambda *a,**k:pytest.fail('provider must not start'))
    with pytest.raises(ValueError,match='insufficient time'):
        writer.generate({'jd':JD,'mode':'generate','deadline_monotonic':time.monotonic()+1})


def test_retry_reuses_draft_but_never_skips_independent_review(monkeypatch):
    import workflow_routing,cv_workflow
    layout,content,requirements,review=fixture()
    calls=[]
    def complete(messages,**kwargs):
        calls.append(kwargs['workflow'])
        if kwargs['workflow']=='career.cv.tailor':value={'content':content,'requirements':requirements}
        else:value=review
        return NS(model='fixture',choices=[NS(finish_reason='stop',message=NS(content=json.dumps(value)))]),{'selected_provider':'fixture'}
    monkeypatch.setattr(workflow_routing,'complete_text',complete)
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**k:{'available':True,'exit_code':0})
    first=writer.generate({'jd':JD,'mode':'generate','worker':'codex'})
    second=writer.generate({'jd':JD,'mode':'generate','worker':'codex'})
    assert calls==['career.cv.tailor','career.cv.review','career.cv.review']
    assert grounding.matches_jd(first,JD) and grounding.matches_jd(second,JD)
    assert writer.generate.last_metadata['model_calls']==1
    review['verdict']='block'
    with pytest.raises(ValueError,match='did not pass'):
        writer.generate({'jd':JD,'mode':'generate','worker':'codex'})
    assert calls[-1]=='career.cv.review'
    assert not list((grounding.ROOT/'drafts').glob('*.json'))
    review['verdict']='pass'
    writer.generate({'jd':JD,'mode':'generate','worker':'codex'})
    assert calls[-2:]==['career.cv.tailor','career.cv.review']


def test_structured_schemas_require_all_slots_and_forbid_extra_keys():
    layout=cv.load_layout()
    for review in (False,True):
        schema=writer.response_schema(layout,review)
        def check(value):
            if isinstance(value,dict):
                if value.get('type')=='object':
                    assert value['additionalProperties'] is False
                    assert set(value['required'])==set(value['properties'])
                for child in value.values():check(child)
            elif isinstance(value,list):
                for child in value:check(child)
        check(schema)
        slots=schema['properties']['slots' if review else 'content']
        assert set(slots['required'])=={s['id'] for s in layout['slots'] if s['variable']}


def test_model_bullet_markers_are_normalized_before_fit_and_review():
    layout,content,requirements,_=fixture()
    slots={s['id']:s for s in layout['slots']}
    for k,v in content.items():
        if slots[k]['bullet']:v['text']='\u2022 '+v['text']
    result,_=grounding.parse_plan({'content':content,'requirements':requirements},layout,JD)
    assert all(not v['text'].startswith('\u2022') for v in result.values())
    for k,v in result.items():
        para=cv.paragraph(slots[k],v['text']);para.wrap(slots[k]['width'],1000)
        assert len(para.blPara.lines)==slots[k]['max_lines']


def test_duplicate_template_bullet_is_rejected_at_final_gate():
    layout,content,requirements,review=fixture()
    content['s21']['text']='\u2022 '+content['s21']['text']
    signed=grounding.issue(content,requirements,layout,JD,review,{}, {'available':True,'exit_code':0})
    assert any(f['reason']=='duplicate template bullet marker' for f in cv.content_check(layout,signed))


def test_canonical_fact_gate_rejection_does_not_poison_retry_cache(monkeypatch):
    import workflow_routing,cv_workflow
    layout,content,requirements,review=fixture()
    def complete(messages,**kwargs):
        value={'content':content,'requirements':requirements} if kwargs['workflow']=='career.cv.tailor' else review
        return NS(model='fixture',choices=[NS(finish_reason='stop',message=NS(content=json.dumps(value)))]),{'selected_provider':'fixture'}
    monkeypatch.setattr(workflow_routing,'complete_text',complete)
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**k:{'available':True,'exit_code':1,'verdict':'block'})
    with pytest.raises(ValueError,match='canonical'):
        writer.generate({'jd':JD,'mode':'generate','worker':'codex'})
    assert not list((grounding.ROOT/'drafts').glob('*.json'))
    assert writer.generate.last_metadata['model_calls']==2


def test_unmet_job_requirements_do_not_override_approved_substantial_tailoring():
    layout,content,requirements,review=fixture()
    requirements[0]['covered_by']=[]
    requirements[1]['covered_by']=[]
    review['tailoring']['requirement_ids']=[requirements[2]['id']]
    grounding.review_result(review,content,requirements,layout)


def test_no_supported_job_requirement_still_fails_tailoring():
    layout,content,requirements,review=fixture()
    for requirement in requirements:requirement['covered_by']=[]
    review['tailoring']['requirement_ids']=[]
    with pytest.raises(ValueError,match='insufficiently tailored'):
        grounding.review_result(review,content,requirements,layout)
