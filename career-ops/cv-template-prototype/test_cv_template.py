import json, pathlib, time
import pytest
import pymupdf as fitz
import cv_template as cv
from cv_compile_prototype import compile_prototype, protect

def original(request): return {}
def slow(request): time.sleep(5); return {}
def bounded(request):
    s=next(s for s in cv.load_layout()['slots'] if s['bullet'] and s['variable'])
    return {s['id']:{'text':s['text'][2:],'sources':[s['id']]}}
def shorten(request):
    l=cv.load_layout(); ss=[s for s in l['slots'] if s['bullet'] and s['variable']]
    s=ss[0]
    if request['mode']=='shorten': return {s['id']:{'text':s['text'][2:],'sources':[s['id']]}}
    return {s['id']:{'text':' '.join(x['text'][2:] for x in ss),'sources':[x['id'] for x in ss]}}

def test_original_content(tmp_path):
    result=cv.reproduce(tmp_path/'repro.pdf'); assert result['status']=='PASS',result
def test_reproducible(tmp_path):
    l=cv.load_layout(); cv.render(l,{},tmp_path/'a.pdf');cv.render(l,{},tmp_path/'b.pdf')
    assert cv.digest(tmp_path/'a.pdf')==cv.digest(tmp_path/'b.pdf')
def test_genuine_content_fit_failure():
    l=cv.load_layout(); failures=cv.fit(l,shorten({'mode':'generate'}))
    assert failures and all(f['reason']=='content capacity exceeded' for f in failures)
def test_capacity_by_rendered_lines():
    l=cv.load_layout(); assert cv.fit(l,bounded({}))==[]
def test_invented_fact():
    s=next(s for s in cv.load_layout()['slots'] if s['variable'])
    assert any(f['reason']=='unverified/invented content' for f in cv.fit(cv.load_layout(),{s['id']:{'text':'I led a team of 500 experts.','sources':[s['id']]}}))
@pytest.mark.parametrize('text',['<b>arbitrary bold</b>','broken\ufffd','a\n\nb'])
def test_markup_blank_corruption(text):
    s=next(s for s in cv.load_layout()['slots'] if s['variable'])
    assert cv.content_check(cv.load_layout(),{s['id']:{'text':text,'sources':[s['id']]}})
def test_no_section_reordering():
    assert cv.fit(cv.load_layout(),{'section_order':{'text':'Education first','sources':[]}})
def test_actual_pixel_corruption(tmp_path):
    p=tmp_path/'bad.pdf';cv.render(cv.load_layout(),{},p)
    d=fitz.open(p);d[0].draw_rect(fitz.Rect(570,50,590,70),fill=(0,0,0));d.save(tmp_path/'changed.pdf')
    assert any('pixels' in f['reason'] for f in cv.validate(cv.load_layout(),{},tmp_path/'changed.pdf')['failures'])
def test_actual_neighbour_corruption(tmp_path):
    p=tmp_path/'bad.pdf';cv.render(cv.load_layout(),{},p)
    d=fitz.open(p); d[0].add_redact_annot(fitz.Rect(20,790,450,845));d[0].apply_redactions();d.save(tmp_path/'changed.pdf')
    assert any('ATS text' in f['reason'] for f in cv.validate(cv.load_layout(),{},tmp_path/'changed.pdf')['failures'])
def test_extra_page(tmp_path):
    p=tmp_path/'bad.pdf';cv.render(cv.load_layout(),{},p);d=fitz.open(p);d.new_page();d.save(tmp_path/'changed.pdf')
    assert cv.validate(cv.load_layout(),{},tmp_path/'changed.pdf')['status']=='FAIL'
def test_native_original_pipeline(tmp_path):
    r=compile_prototype('SOC analyst read-only offline fixture','test',tmp_path/'job',original)
    assert r['delivery_allowed'] and r['content_calls']==1 and r['renders']==1,r
def test_one_targeted_shortening(tmp_path):
    r=compile_prototype('Long content fixture','test',tmp_path/'job',shorten)
    assert r['delivery_allowed'] and r['content_calls']==2 and r['renders']==1,r
def test_real_wall_clock_cancellation(tmp_path):
    r=compile_prototype('timeout fixture','test',tmp_path/'job',slow,hard_seconds=.5)
    assert not r['delivery_allowed'] and r['reason']=='hard wall-clock timeout' and 'pdf_path' not in r
    assert r['elapsed_seconds']<3
def test_no_reentry_retry(tmp_path):
    w=tmp_path/'job';w.mkdir();(w/'draft.json').write_text('{}')
    with pytest.raises(ValueError,match='fresh bounded'):compile_prototype('fixture','test',w,original)
def test_master_renderer_lock(tmp_path):
    p=tmp_path/'protected.py';p.write_text('original')
    with protect([p]):
        with pytest.raises(PermissionError): p.write_text('changed')
    assert p.read_text()=='original'
def test_hard_budget_not_increasable(tmp_path):
    with pytest.raises(ValueError): compile_prototype('fixture','test',tmp_path/'job',original,181)

@pytest.mark.parametrize('mutation',['font','baseline','overflow','bold','missing'])
def test_rendered_geometry_regressions(tmp_path,mutation):
    layout=cv.load_layout(); s=next(s for s in layout['slots'] if s['bullet'] and s['variable'])
    if mutation=='font': layout['fonts']['normal']='arial.ttf'
    if mutation=='baseline': s['baseline']+=2
    if mutation=='overflow': s['width']=100
    if mutation=='bold': s['runs'][0]['style']='bold'
    if mutation=='missing': s['runs'][0]['text']='Truncated.'
    p=tmp_path/'bad.pdf';cv.render(layout,{},p)
    assert cv.validate(cv.load_layout(),{},p)['status']=='FAIL'

def test_shortening_failure_stops(tmp_path):
    r=compile_prototype('long fixture','test',tmp_path/'job',always_long)
    assert not r['delivery_allowed'] and r['content_calls']==2 and r['renders']==0 and 'pdf_path' not in r

def always_long(request): return shorten({'mode':'generate'})

def test_engineering_content_all_slots_fit(tmp_path):
    from cv_content_adapter import resolve_plan
    bank=json.loads((cv.HERE/'fact_bank.json').read_text(encoding='utf-8'))
    content=resolve_plan({'selections':{key:'engineering' for key in bank['slots']}})
    assert not cv.fit(cv.load_layout(),content)
    p=tmp_path/'engineering.pdf';cv.render(cv.load_layout(),content,p)
    assert cv.validate(cv.load_layout(),content,p)['status']=='PASS'

def test_variant_cannot_introduce_fake_fact():
    from cv_content_adapter import resolve_plan
    bank=json.loads((cv.HERE/'fact_bank.json').read_text(encoding='utf-8'))
    content=resolve_plan({'selections':{key:'engineering' for key in bank['slots']}})
    content['s04']['text']='Senior engineer with 20 years experience.'
    assert cv.content_check(cv.load_layout(),content)

@pytest.mark.parametrize('plan',[{'selections':{}},{'selections':{'s04':'invented'}}])
def test_incomplete_model_plan_rejected(plan):
    from cv_content_adapter import resolve_plan
    with pytest.raises(ValueError):resolve_plan(plan)

def test_native_reasoning_retained_for_bounded_planning():
    from cv_content_adapter import request_options
    assert request_options('nous','meituan/longcat-2.5-preview:free')=={'reasoning':{'enabled':True,'effort':'low'},'thinking':{'type':'enabled'}}
    assert request_options('other','other-model')=={}

def test_underfilled_bullet_blocks_delivery():
    layout=cv.load_layout();s=next(s for s in layout['slots'] if s['bullet'] and s['variable'])
    text=s['text'][2:].split(',')[0]+'.'
    # Existing substring evidence deliberately excludes an invented abbreviation.
    c={s['id']:{'text':s['text'][2:].split(',')[0],'sources':[s['id']]}}
    assert any('underfills' in f['reason'] for f in cv.fit(layout,c))

def test_skill_label_cannot_disappear():
    l=cv.load_layout()
    assert any(f['reason']=='missing skill label/value' for f in cv.content_check(l,{'s06':{'text':'Phishing analysis','sources':['s06']}}))

def test_profile_fragment_rejected():
    l=cv.load_layout()
    assert any(f['reason']=='incomplete sentence' for f in cv.content_check(l,{'s04':{'text':'MSc Information Security graduate','sources':['s04']}}))
