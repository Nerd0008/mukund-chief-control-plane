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
 replacement='MSc Information Security graduate with software development skills and cybersecurity knowledge plus practical IT support.'
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


def test_actual_discord_wrapper_never_attaches_failed_pdf(setup,monkeypatch):
 fake=types.ModuleType('gateway.platforms.base');fake.SendResult=lambda **kw:types.SimpleNamespace(**kw)
 monkeypatch.setitem(sys.modules,'gateway.platforms.base',fake)
 runtime=types.SimpleNamespace(_current_max_iterations=lambda:150)
 class Turn:
  async def _run_agent(self,*a,**kw):return None
 class Media:
  def __init__(self):self.attachments=0;self.responses=[]
  async def send(self,**kw):self.responses.append(kw['content'])
  async def send_document(self,*a,**kw):self.attachments+=1;return 'sent'
 guard.install_runtime(runtime,Turn,Media);media=Media()
 result=asyncio.run(media.send_document('chief',setup[3]/'broken_CV.pdf'))
 assert result.success is False and media.attachments==0 and 'CV generation failed' in media.responses[0]


def test_cv_hook_shares_one_workspace_across_copied_context(setup):
 import contextvars
 token=guard.CV_ACTIVE.set(True);workspace=guard.CV_WORKSPACE.set({'path':None})
 try:
  contextvars.copy_context().run(guard.pre_tool,'write_file',{'path':str(setup[3]/'a/cv_edits.json')})
  assert guard.pre_tool('write_file',{'path':str(setup[3]/'b/cv_edits.json')})['action']=='block'
 finally:guard.CV_WORKSPACE.reset(workspace);guard.CV_ACTIVE.reset(token)


def test_unknown_mutating_tools_fail_closed(setup):
 token=guard.CV_ACTIVE.set(True)
 try:
  for name in ['memory','skill_manage','custom_pdf_builder','send_message']:
   assert guard.pre_tool(name,{'action':'write'})['action']=='block'
 finally:guard.CV_ACTIVE.reset(token)


def test_renaming_a_cv_does_not_bypass_attachment_guard(setup):
 import shutil
 pdf=setup[3]/'innocent.pdf';shutil.copyfile(g.MASTER,pdf)
 assert guard.needs_gate(pdf)


def test_lazy_platform_module_alias_also_gets_delivery_guard(setup,monkeypatch):
 fake=types.ModuleType('gateway.platforms.base');fake.SendResult=lambda **kw:types.SimpleNamespace(**kw);monkeypatch.setitem(sys.modules,'gateway.platforms.base',fake)
 runtime=types.SimpleNamespace(_current_max_iterations=lambda:150)
 class Turn:
  async def _run_agent(self,*a,**kw):pass
 class StaticMedia:
  async def send_document(self,*a,**kw):return 'static'
 class ActualLazyMedia:
  async def send(self,**kw):pass
  async def send_document(self,*a,**kw):raise AssertionError('unverified file attached')
 guard.install_runtime(runtime,Turn,StaticMedia)
 guard.install_runtime(runtime,Turn,ActualLazyMedia)
 assert asyncio.run(ActualLazyMedia().send_document('chief',setup[3]/'bad_CV.pdf')).success is False


def test_read_only_diagnostic_allowed_without_unlock():
 command='git -C "'+str(guard.REPO)+'" log --oneline -3 -- career-ops/cv_tailor.py'
 assert guard.pre_tool('terminal',{'command':command}) is None
 assert not guard.safe_readonly(command+' && git reset --hard')


def test_native_cv_build_tool_no_shell_or_renderer_patch(setup):
 token=guard.CV_WORKSPACE.set({'path':None});active=guard.CV_ACTIVE.set(True)
 try:
  result=json.loads(guard.build_tool(setup[2]));assert result['status']=='PASS' and g.delivery_allowed(result['verified_pdf'])
  assert json.loads(guard.build_tool(setup[2]))['status']=='FAIL'
 finally:guard.CV_WORKSPACE.reset(token);guard.CV_ACTIVE.reset(active)


def test_separate_native_skill_whitespace_is_preserved(setup):
 manifest=setup[0];original={x['id']:x['text'].strip() for x in manifest['spans']};spec={'edits':[{'span_id':'p0-s27','replace':original['p0-s27'].replace('Hardware','Endpoint')},{'span_id':'p0-s29','replace':original['p0-s29'].replace('Azure','Cloud')},{'span_id':'p0-s30','replace':original['p0-s30'].replace('Detection','Analytics') }]}
 p=setup[3]/'skills_CV.pdf';r=g.generate(g.MASTER,g.MANIFEST,spec,p)
 assert r['status']=='PASS' and r['outside_region_changed_pixels']==0 and g.delivery_allowed(p)


def test_skill_labels_can_be_tailored_without_font_or_origin_changes(setup):
 spec={'edits':[{'span_id':'p0-s28','replace':'Cloud Security & Cyber Platforms:'},{'span_id':'p0-s34','replace':'Software Development & Data Analysis:'}]}
 p=setup[3]/'labels_CV.pdf';r=g.generate(g.MASTER,g.MANIFEST,spec,p)
 assert r['status']=='PASS' and r['outside_region_changed_pixels']==0 and g.delivery_allowed(p)


@pytest.mark.parametrize('replacement',['Information Security MSc graduate.','i'*175])
def test_exact_character_count_rejects_shorter_and_longer_content(setup,replacement):
 spec=setup[2];spec['edits'][0]['replace']=replacement
 r=g.generate(g.MASTER,g.MANIFEST,spec,setup[3]/'flexible_CV.pdf')
 assert r['status']=='FAIL' and 'exact character count' in r['problems'][0]


def test_skill_label_shortening_cannot_create_large_value_gap(setup):
 spec={'edits':[{'span_id':'p0-s28','replace':'Cloud & Security Platforms:'}]}
 r=g.generate(g.MASTER,g.MANIFEST,spec,setup[3]/'gaps_CV.pdf')
 assert r['status']=='FAIL' and not (setup[3]/'gaps_CV.pdf').exists()
