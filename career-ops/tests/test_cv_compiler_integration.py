import asyncio,json,pathlib,sys,time,types
import pytest
ROOT=pathlib.Path(__file__).parent
if ROOT.name=='tests':ROOT=ROOT.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'cv-template-prototype'))
import hermes_cv_compiler_guard as g
import cv_template as cv
from cv_compile_prototype import compile_prototype,delivery_allowed
from role_family_acceptance import offline_selection

def test_native_compiler_and_attachment_verification(tmp_path,monkeypatch):
    monkeypatch.setattr(g,'OUTPUT_ROOT',tmp_path)
    monkeypatch.setattr(g,'EXPORT_ROOT',tmp_path/'exports')
    monkeypatch.setattr(g,'generate',offline_selection)
    token=g.JOB.set({'deadline':time.monotonic()+180,'attempted':False})
    try:
        r=json.loads(g.compile_tool({'jd':'Python and Windows graduate software support','job_id':'test'}))
        assert r['status']=='PASS',r
        assert g.verified_attachment(r['verified_pdf'])
        assert pathlib.Path(r['verified_pdf']).name=='Mukund_test_Tailored_CV.pdf'
        assert json.loads(g.compile_tool({'jd':'same','job_id':'test'}))['status']=='FAIL'
        pathlib.Path(r['verified_pdf']).write_bytes(b'broken')
        assert not delivery_allowed(r['verified_pdf'],tmp_path)
    finally:g.JOB.reset(token)

def test_old_span_tool_retired():
    assert json.loads(g.retired_build({'edits':[]}))['status']=='RETIRED'
    assert 'required_characters' not in g.master_tool({})

@pytest.mark.parametrize('name',['terminal','execute_code','write_file','patch','apply_patch','delegate_task','custom_pdf_builder'])
def test_application_cannot_engineer_renderer(name):
    token=g.JOB.set({'deadline':time.monotonic()+180})
    try:assert g.pre_tool(name,{'command':'anything','path':'cv_template.py'})['action']=='block'
    finally:g.JOB.reset(token)

def test_non_cv_tools_unchanged():
    assert g.pre_tool('terminal',{'command':'anything'}) is None

def test_native_budget_only_cv():
    runtime=types.SimpleNamespace(_current_max_iterations=lambda:150)
    class Turn:
        async def _run_agent(self,message,context,history,*a,**kw):
            return {'limit':runtime._current_max_iterations(),'context':context}
    class Media:
        async def send_document(self,*a,**kw):return True
    g.install_runtime(runtime,Turn,Media)
    r=asyncio.run(Turn()._run_agent('Tailor my CV','',[]))
    assert r['limit']==4 and 'career_cv_compile' in r['context']
    assert 'vision_analyze is allowed' in r['context']
    assert 'CURRENT inbound message' in r['context']
    assert 'Do not label a provider failure' in r['context']
    assert 'already installed' in r['context']
    assert asyncio.run(Turn()._run_agent('Unrelated request','',[]))['limit']==150

def test_failed_pdf_blocked_on_actual_lazy_adapter(tmp_path,monkeypatch):
    fake=types.ModuleType('gateway.platforms.base');fake.SendResult=lambda **kw:types.SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules,'gateway.platforms.base',fake)
    class Media:
        async def send(self,**kw):pass
        async def send_document(self,*a,**kw):raise AssertionError('bad attachment sent')
    g.install_delivery(Media)
    result=asyncio.run(Media().send_document('channel',tmp_path/'Broken_CV.pdf'))
    assert not result.success

def test_expired_job_no_tools():
    token=g.JOB.set({'deadline':time.monotonic()-1})
    try:assert g.pre_tool('career_cv_compile',{})['action']=='block'
    finally:g.JOB.reset(token)

@pytest.mark.parametrize('message',['Here is the JD','Tailor to this job description'])
def test_jd_only_intake_gets_cv_guards(message):
    assert g.cv_request(message)

def test_forged_verification_cannot_skip_dependencies(tmp_path):
    folder=tmp_path/'a';folder.mkdir();pdf=folder/'candidate.pdf';pdf.write_bytes(b'fake')
    (folder/'verification.json').write_text(json.dumps({'status':'PASS','delivery_allowed':True,'hashes_before':{},'hashes_after':{}}))
    assert not delivery_allowed(pdf,tmp_path)

def test_registered_tools_are_flow_compiler(monkeypatch):
    # Structural registration without initializing providers or Discord.
    monkeypatch.setattr(g,'install_runtime',lambda *a:None)
    modules={'gateway.run':types.ModuleType('gateway.run'),'gateway.run_turn':types.ModuleType('gateway.run_turn'),
        'plugins.platforms.discord.adapter_media':types.ModuleType('plugins.platforms.discord.adapter_media')}
    modules['gateway.run_turn'].GatewayTurnMixin=object
    modules['plugins.platforms.discord.adapter_media'].DiscordMediaMixin=object
    for name,m in modules.items():monkeypatch.setitem(sys.modules,name,m)
    import gateway
    monkeypatch.setattr(gateway,'run',modules['gateway.run'],raising=False)
    class Context:
        def __init__(self):self.tools={}
        def register_hook(self,*a):pass
        def register_platform_handler(self,*a):pass
        def register_tool(self,**kw):self.tools[kw['name']]=kw
    ctx=Context();g.register(ctx)
    assert ctx.tools['career_cv_compile']['handler'] is g.compile_tool
    assert ctx.tools['career_cv_build']['handler'] is g.retired_build
    assert ctx.tools['career_cv_compile']['schema']['parameters']['required']==['jd','job_id']

def test_wall_clock_watchdog_uses_native_interrupt_seam(monkeypatch):
    import threading
    done=threading.Event(); interrupted=threading.Event()
    module=types.ModuleType('gateway.run')
    module._abandon_timed_out_gateway_turn=lambda **kw:interrupted.set()
    monkeypatch.setitem(sys.modules,'gateway.run',module)
    runtime=types.SimpleNamespace(_current_max_iterations=lambda:150)
    worker=types.SimpleNamespace(worker_done=done,agent_timeout=1800)
    class Turn:
        async def _run_agent(self,*a,**kw):pass
        def _run_agent_start_turn_worker(self,*a):return worker
        def _reaper_kwargs(self,w):return {}
    class Media:
        async def send_document(self,*a,**kw):pass
    g.install_runtime(runtime,Turn,Media)
    state={'deadline':time.monotonic()+.03};token=g.JOB.set(state)
    try:
        Turn()._run_agent_start_turn_worker(types.SimpleNamespace(agent_holder=[None]),lambda:None)
        assert interrupted.wait(1)
        assert state['timed_out'] and worker.agent_timeout==180
    finally:g.JOB.reset(token);done.set()

@pytest.mark.parametrize('attempted',[False,True])
def test_cv_feedback_vision_is_allowed(attempted):
    token=g.JOB.set({'deadline':time.monotonic()+180,'attempted':attempted})
    try:
        assert g.pre_tool('vision_analyze',{'image_path':'feedback.png','question':'Inspect spacing'}) is None
        assert g.pre_tool('write_file',{'path':'cv_template.py'})['action']=='block'
    finally:g.JOB.reset(token)


def test_export_short_name_and_corruption(tmp_path,monkeypatch):
    monkeypatch.setattr(g,'OUTPUT_ROOT',tmp_path)
    monkeypatch.setattr(g,'EXPORT_ROOT',tmp_path/'exports')
    result=compile_prototype('Engineering fixture','allstate',tmp_path/'job',offline_selection)
    path=g.export_verified(result['pdf_path'],'Allstate Inc.','Product Engineer')
    assert pathlib.Path(path).name=='Mukund_Allstate_Product_Engineer_CV.pdf'
    assert g.verified_attachment(path)
    pathlib.Path(path).write_bytes(b'corrupt')
    assert not g.verified_attachment(path)


@pytest.mark.parametrize('message',[
    'Fix the Greenhouse regex', 'Update the tracker', 'Restart Hermes',
    'Fix the CV compiler guard blocking unrelated tasks',
    'Debug cv_template.py', 'Why did my CV fail?', 'Check this job eligibility',
])
def test_history_cannot_lock_unrelated_or_maintenance_request(message):
    history=[{'role':'user','content':'Tailor my CV to this JD'},
             {'role':'assistant','content':'Use career_cv_compile'}]
    assert not g.cv_request(message,history)


def test_bare_link_requires_latest_user_cv_intent():
    link='https://www.allstate.jobs/job/23947981/graduate'
    assert not g.cv_request(link)
    assert g.cv_request(link,[{'role':'user','content':'Tailor my CV'}])
    assert not g.cv_request(link,[{'role':'user','content':'Tailor my CV'},
                                 {'role':'user','content':'Check eligibility'}])


def test_unrelated_turn_keeps_normal_tools_after_cv_history():
    runtime=types.SimpleNamespace(_current_max_iterations=lambda:150)
    class Turn:
        async def _run_agent(self,message,context,history,*a,**kw):
            return {'limit':runtime._current_max_iterations(),
                    'patch':g.pre_tool('patch',{'path':'unrelated.py'}),
                    'context':context}
    class Media:
        async def send_document(self,*a,**kw):return True
    g.install_runtime(runtime,Turn,Media)
    result=asyncio.run(Turn()._run_agent('Fix the CV compiler guard','',
                         [{'role':'user','content':'Build my CV'}]))
    assert result['limit']==150 and result['patch'] is None
    assert 'career_cover_compile' in result['context']
    result=asyncio.run(Turn()._run_agent('Tailor my CV','',[]))
    assert result['limit']==4 and result['patch']['action']=='block'


def test_jd_attachment_can_activate_compiler_without_history_lock(monkeypatch):
    runtime=types.SimpleNamespace(_current_max_iterations=lambda:150)
    monkeypatch.setattr(g,'compile_prototype',lambda *a,**kw:{'status':'FAIL','stage':'fixture','reason':'bounded fixture','delivery_allowed':False})
    class Turn:
        async def _run_agent(self,message,context,history,*a,**kw):
            assert runtime._current_max_iterations()==150
            assert g.pre_tool('patch',{'path':'unrelated.py'}) is None
            assert g.pre_tool('tool_call',{'calls':[{'name':'career_cv_compile','arguments':{'jd':'Attached graduate role','job_id':'test'}}]}) is None
            result=json.loads(g.compile_tool({'jd':'Attached graduate role','job_id':'test'}))
            assert result.get('reason')!='native CV job context required'
            assert runtime._current_max_iterations()==4
            assert g.pre_tool('patch',{'path':'cv_template.py'})['action']=='block'
            assert json.loads(g.compile_tool({'jd':'retry','job_id':'test'}))['reason']=='compiler already invoked; no retries'
            return result
    class Media:
        async def send_document(self,*a,**kw):return True
    g.install_runtime(runtime,Turn,Media)
    result=asyncio.run(Turn()._run_agent('[Content of message.txt]: Graduate programme requirements','',[]))
    assert result['stage']=='fixture'
    assert g.JOB.get() is None
