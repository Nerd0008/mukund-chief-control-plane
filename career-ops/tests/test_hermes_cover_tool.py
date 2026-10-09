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


def test_corrected_cover_can_retry_once_without_bypassing_gate(tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(cover,'ROOT',tmp_path)
    calls=[]
    def rejected(*args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(cover.subprocess,'run',rejected)
    token=guard.JOB.set({'deadline':time.monotonic()+180,'cv_active':True})
    args={'company':'Example','role':'Graduate','paragraphs':['Original']*5}
    try:
        assert json.loads(cover.cover_tool(args))['status']=='FAIL'
        assert 'unchanged' in json.loads(cover.cover_tool(args))['reason']
        corrected=dict(args,paragraphs=['Corrected']*5)
        assert 'verification failed' in json.loads(cover.cover_tool(corrected))['reason']
        assert 'budget exhausted' in json.loads(cover.cover_tool(dict(args,paragraphs=['Third']*5)))['reason']
        assert len(calls)==2
    finally:guard.JOB.reset(token)


def test_expired_cover_never_launches_renderer(tmp_path,monkeypatch):
    monkeypatch.setattr(cover,'ROOT',tmp_path)
    monkeypatch.setattr(cover.subprocess,'run',lambda *a,**k:pytest.fail('expired renderer launched'))
    token=guard.JOB.set({'deadline':time.monotonic()-1,'cv_active':True})
    try:
        assert 'deadline' in json.loads(cover.cover_tool({'company':'Example','role':'Graduate','paragraphs':['Text']*5}))['reason']
        assert not list(tmp_path.iterdir())
    finally:guard.JOB.reset(token)


def test_verified_export_is_deliverable_and_tamper_checked(tmp_path,monkeypatch):
    import cv_workflow
    monkeypatch.setattr(cv_workflow,'fact_gate',lambda *a,**k:{'available':True,'exit_code':0})
    runtime=tmp_path/'runtime';runtime.mkdir()
    monkeypatch.setattr(cover,'ROOT',runtime)
    monkeypatch.setattr(cover,'EXPORT_ROOT',tmp_path/'exports')
    content=spec(runtime);path=runtime/'content.json';path.write_text(json.dumps(content))
    cover.build(path)
    exported=cover.export_verified(content['out'],'Example Ltd','Security Consultant')
    assert exported.name=='Mukund_Example_Security_Consultant_Cover_Letter.pdf'
    assert cover.verified(exported)
    exported.write_bytes(b'corrupt')
    assert not cover.verified(exported)


def test_unverified_cover_never_exported(tmp_path,monkeypatch):
    monkeypatch.setattr(cover,'ROOT',tmp_path/'runtime')
    monkeypatch.setattr(cover,'EXPORT_ROOT',tmp_path/'exports')
    with pytest.raises(ValueError,match='unverified'):cover.export_verified(tmp_path/'missing.pdf','Example','Role')
    assert not cover.EXPORT_ROOT.exists()
