import pathlib,json,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]/'cv-template-prototype'
sys.path.insert(0,str(ROOT))
import cv_template as cv

def test_shared_data_and_rendered_reference_have_correct_punctuation():
    import pymupdf
    bad=('Python ,Gmail','London,UK','Applications , Maharashtra','ISO27001')
    data=(ROOT/'layout.json').read_text()+(ROOT/'fact_bank.json').read_text()
    assert not any(text in data for text in bad)
    with pymupdf.open(ROOT/'output/original-content-reproduction.pdf') as pdf:
        text=pdf[0].get_text()
        assert not any(value in text for value in bad)
        assert all(value in text for value in ('Python, Gmail','London, UK','Applications, Maharashtra','ISO 27001'))
    assert cv.validate(cv.load_layout(),{},ROOT/'output/original-content-reproduction.pdf')['status']=='PASS'
