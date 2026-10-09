import json
import cv_template as cv
from cv_writing_policy import policy, check
from cv_compile_prototype import dependency_paths

def test_reference_is_explicit():
    assert policy()['source'].endswith('Wikipedia:Signs_of_AI_writing')
    assert policy()['mode']=='reviewed_local_reference'

def test_factual_technical_language_allowed():
    assert not check('MSc Information Security, CompTIA Security+ and ISC2 CC. Investigated incidents using Python and SIEM tools.')

def test_boilerplate_and_filler_rejected():
    for text in ['As an AI language model, here is your CV.', 'Expert in the ever-evolving landscape.', '[Insert company name]', 'Not just security but also excellence.']:
        assert check(text)

def test_bank_wording_passes():
    bank=json.loads((cv.HERE/'fact_bank.json').read_text(encoding='utf-8'))
    for variants in bank['slots'].values():
        for item in variants.values():
            assert not check(item['text'])

def test_validation_enforces_policy():
    layout=cv.load_layout()
    slot=next(s for s in layout['slots'] if s['variable'])
    errors=cv.content_check(layout,{slot['id']:{'text':'Game-changing unparalleled expertise.', 'sources':[slot['id']]}})
    assert any('writing policy' in e['reason'] for e in errors)

def test_policy_is_immutable_dependency():
    assert cv.HERE/'cv_writing_policy.py' in dependency_paths()

def test_prompt_always_includes_policy():
    source=(cv.HERE/'cv_content_adapter.py').read_text(encoding='utf-8')
    assert "'writing_policy':policy()" in source
    assert "policy()['guidance']" in source
