import json,pathlib,sys,time
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import hermes_cover_tool as cover
import hermes_cv_compiler_guard as guard

def spec(tmp_path):return {'heading':'Application for Graduate Security Consultant','salutation':'Dear Example Recruitment Team,','paragraphs':['I am applying for this graduate opportunity.','I would like to discuss how my studies relate to the role.','I can explain the work included in my application.','I welcome the opportunity to discuss the team responsibilities.','Thank you for considering my application.'],'out':str(tmp_path/'cover.pdf')}

def test_real_cover_render_and_text_validation(tmp_path,monkeypatch):
    import cv_workflow
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**kw:{'available':True,'exit_code':0,'ok':True})
    monkeypatch.setattr(cover,'ROOT',tmp_path)
    p=tmp_path/'spec.json';p.write_text(json.dumps(spec(tmp_path)))
    cover.build(p)
    assert cover.verified(tmp_path/'cover.pdf')
    (tmp_path/'cover.pdf').write_bytes(b'corrupted')
    assert not cover.verified(tmp_path/'cover.pdf')

def test_failed_fact_gate_never_verified(tmp_path,monkeypatch):
    import cv_workflow
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**kw:{'available':True,'exit_code':1})
    p=tmp_path/'spec.json';p.write_text(json.dumps(spec(tmp_path)))
    with pytest.raises(ValueError,match='fact gate'):cover.build(p)
    assert not (tmp_path/'cover.pdf').exists()

def test_cover_tool_allowed_after_cv_compile_without_shell():
    token=guard.JOB.set({'deadline':time.monotonic()+180,'attempted':True})
    try:
        assert guard.pre_tool('career_cover_compile',{}) is None
        assert guard.pre_tool('terminal',{})['action']=='block'
    finally:guard.JOB.reset(token)

def test_overflow_content_refused(tmp_path):
    s=spec(tmp_path);s['paragraphs'][0]='x'*3000
    p=tmp_path/'spec.json';p.write_text(json.dumps(s))
    with pytest.raises(ValueError,match='capacity'):cover.build(p)
