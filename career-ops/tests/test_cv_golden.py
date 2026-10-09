"""Golden master regressions: temporary outputs; no provider or Discord calls."""
import json,sys,hashlib,asyncio,types
from pathlib import Path
import pytest,pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv_golden as g
import hermes_cv_guard as guard
@pytest.fixture
def setup(tmp_path,monkeypatch):
 monkeypatch.setattr(g,'OUTPUT_ROOT',tmp_path)
 manifest=json.loads(g.MANIFEST.read_text());s=next(s for s in manifest['spans'] if s['editable'] and s['section']=='Professional Summary')
 replacement='MSc Information Security graduate combining software development and cybersecurity knowledge with practical IT systems support,'
 spec={'edits':[{'span_id':s['id'],'replace':replacement}]}
 return manifest,s,spec,tmp_path

def candidate(setup):
 m,s,spec,tmp=setup;p=tmp/'candidate.pdf'
 with pymupdf.open(g.MASTER) as doc:
  plan=g.prepare(doc,m,spec);g.render_once(doc,plan,str(p))
 return p,plan

def mutate(p,fn):
 d=pymupdf.open(p);fn(d);other=p.with_suffix('.changed.pdf');d.save(other,no_new_id=True);d.close();other.replace(p)

def test_valid_bounded_replacement_passes(setup):
 p,plan=candidate(setup);r=g.verify(g.MASTER,p,setup[0],plan)
 assert r['status']=='PASS' and r['outside_region_changed_pixels']==0

def test_master_and_renderer_are_os_read_only_during_run(tmp_path):
 for name in ['master.pdf','cv_tailor.py','manifest.json','font-layout.json']:
  p=tmp_path/name;p.write_bytes(b'protected');before=g.sha(p)
  with g.immutable_files([p]):
   if sys.platform=='win32':
    with pytest.raises(OSError):p.write_bytes(b'changed')
  assert g.sha(p)==before

@pytest.mark.parametrize('defect',['neighbour','font','baseline','pixels'])
def test_structural_and_pixel_corruption_fails(setup,defect):
 p,plan=candidate(setup)
 def break_it(d):
  page=d[0]
  if defect=='pixels':page.draw_rect(pymupdf.Rect(5,5,8,8),fill=(0,0,0))
  elif defect=='neighbour':
   # Reproduce the failed renderer's overlapping redaction; no reinsertion loop.
   s=next(s for s in setup[0]['spans'] if s['text'].startswith('faster identification'));page.add_redact_annot(pymupdf.Rect(s['bbox']));page.apply_redactions()
  elif defect=='font':
   x=plan[0]['span']['stream_xref'];data=d.xref_stream(x);d.update_stream(x,data.replace(b'/F4 ',b'/F5 ',1))
  else:
   x=plan[0]['span']['stream_xref'];data=d.xref_stream(x);d.update_stream(x,data.replace(b' 13 Tm',b' 15 Tm',1))
 mutate(p,break_it);r=g.verify(g.MASTER,p,setup[0],plan)
 assert r['status']=='FAIL'
 if defect=='pixels':assert r['outside_region_changed_pixels']>0

@pytest.mark.parametrize('extra',[{'x':1},{'bold_prefix':'MSc'},{'char_budget_exempt':True}])
def test_geometry_and_force_exemptions_forbidden(setup,extra):
 spec=setup[2];spec['edits'][0].update(extra)
 with pymupdf.open(g.MASTER) as d:
  with pytest.raises(ValueError,match='forbidden'):g.prepare(d,setup[0],spec)

def test_overflow_asks_content_rewrite_without_modifying_renderer(setup):
 m,s,spec,tmp=setup;spec['edits'][0]['replace']='W'*1000;calls=[];before=g.sha(g.HERE/'cv_tailor.py')
 def rewrite(span,text,reason,attempt):calls.append((span['id'],reason));return s['text']
 with pymupdf.open(g.MASTER) as d:plan=g.prepare(d,m,spec,rewrite)
 assert len(calls)==1 and plan[0]['attempts']==2 and before==g.sha(g.HERE/'cv_tailor.py')

def test_three_fit_attempts_fail_closed_without_pdf(setup):
 m,s,spec,tmp=setup;spec['edits'][0]['replace']='W'*1000;calls=[]
 def rewrite(*args):calls.append(args);return 'W'*1000
 report=g.generate(g.MASTER,g.MANIFEST,spec,tmp/'bad_CV.pdf',rewrite)
 assert report['status']=='FAIL' and 'three' in report['problems'][0] and len(calls)==2
 assert not (tmp/'bad_CV.pdf').exists() and not g.delivery_allowed(tmp/'bad_CV.pdf')

def test_reproducible_identical_input(setup):
 root=setup[3];a=root/'a'/'a_CV.pdf';b=root/'b'/'b_CV.pdf'
 assert g.generate(g.MASTER,g.MANIFEST,setup[2],a)['status']=='PASS'
 assert g.generate(g.MASTER,g.MANIFEST,setup[2],b)['status']=='PASS'
 assert g.sha(a)==g.sha(b)

def test_failed_or_forged_verification_blocks_delivery(setup):
 p=setup[3]/'guard_CV.pdf';assert g.generate(g.MASTER,g.MANIFEST,setup[2],p)['status']=='PASS';assert g.delivery_allowed(p)
 mutate(p,lambda d:d[0].draw_rect(pymupdf.Rect(5,5,8,8),fill=(0,0,0)))
 report=json.loads(p.with_suffix('.verification.json').read_text());report['output_sha256']=g.sha(p);p.with_suffix('.verification.json').write_text(json.dumps(report))
 assert not g.delivery_allowed(p)

def test_cv_application_tool_write_scope_and_renderer_protection(setup):
 token=guard.CV_ACTIVE.set(True)
 try:
  assert guard.pre_tool('patch',{'path':str(g.HERE/'cv_tailor.py')})['action']=='block'
  assert guard.pre_tool('terminal',{'command':'python -c "print(1)"'})['action']=='block'
  assert guard.pre_tool('write_file',{'path':str(setup[3]/'cv_edits.json')}) is None
  assert guard.pre_tool('write_file',{'path':'C:/Windows/bad.txt'})['action']=='block'
 finally:guard.CV_ACTIVE.reset(token)

def test_cv_agent_budget_is_local_not_global(setup):
 runtime=types.SimpleNamespace(_current_max_iterations=lambda:150)
 class Turn:
  async def _run_agent(self,*args,**kw):return runtime._current_max_iterations()
 class Media:
  async def send_document(self,*args,**kw):return 'sent'
 guard.install_runtime(runtime,Turn,Media)
 assert asyncio.run(Turn()._run_agent('Tailor my CV','',[],None))==8
 assert asyncio.run(Turn()._run_agent('Other task','',[],None))==150

def test_legacy_format_master_cannot_be_used(setup):
 import cv_tailor
 assert cv_tailor.main(['--master','C:/Users/mukun/Downloads/codex/CV_FORMAT_MASTER.pdf','--edits','x','--out','y'])==1


def test_three_attempt_budget_persists_across_process_reentry(setup):
 spec=setup[2];spec['edits'][0]['replace']='W'*1000;spec['edits'][0]['alternatives']=['W'*1000,'W'*1000]
 root=setup[3];first=g.generate(g.MASTER,g.MANIFEST,spec,root/'failed_CV.pdf');assert first['status']=='FAIL'
 spec['edits'][0]['replace']=setup[1]['text'];spec['edits'][0].pop('alternatives')
 second=g.generate(g.MASTER,g.MANIFEST,spec,root/'renamed_CV.pdf');assert second['status']=='FAIL' and 'three' in second['problems'][0]
 assert not (root/'renamed_CV.pdf').exists()
