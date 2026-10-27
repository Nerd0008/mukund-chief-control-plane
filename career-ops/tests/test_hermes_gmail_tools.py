import asyncio,json,pathlib,sys,types
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import hermes_gmail_tools as g

def test_old_session_receives_local_gmail_route_every_turn():
    class Turn:
        async def _run_agent(self,message,context,history,*a,**kw):return context
    g.install_turn_guidance(Turn)
    context=asyncio.run(Turn()._run_agent('Gmail is still unavailable','old frozen prompt',[]))
    assert 'career_gmail_status first' in context and 'NOT evidence' in context
    g.install_turn_guidance(Turn)
    assert asyncio.run(Turn()._run_agent('Hi','',[])).count(g.GUIDANCE)==1

def test_scan_native_tool_is_dry_run_no_apply(monkeypatch):
    seen=[]
    def run(argv,**kw):
        seen.append(argv);return types.SimpleNamespace(stdout=json.dumps({'mode':'dry-run','gmail_mutations':0}),returncode=0)
    monkeypatch.setattr(g.subprocess,'run',run)
    assert json.loads(g.scan_tool({}))['mode']=='dry-run'
    assert seen[0][-1]=='scan' and '--apply' not in seen[0]

def test_no_invalid_stdout_or_stderr_exposure(monkeypatch):
    monkeypatch.setattr(g.subprocess,'run',lambda *a,**kw:types.SimpleNamespace(stdout='SECRET',stderr='SECRET',returncode=1))
    assert 'SECRET' not in g.status_tool({})

def test_native_gmail_registration(monkeypatch):
    mod=types.ModuleType('gateway.run_turn');mod.GatewayTurnMixin=object
    monkeypatch.setitem(sys.modules,'gateway.run_turn',mod)
    monkeypatch.setattr(g,'install_turn_guidance',lambda *a:None)
    monkeypatch.setattr(g,'install_language_policy',lambda *a:None)
    class Context:
        def __init__(self):self.tools={};self.prompt=None
        def register_system_prompt_section(self,*a,**kw):self.prompt=a[1]
        def register_tool(self,**kw):self.tools[kw['name']]=kw
    ctx=Context();g.register(ctx)
    assert set(ctx.tools)=={'career_gmail_status','career_gmail_scan','career_gmail_jobs','career_gmail_assessments','career_workflow_status'}
    assert ctx.tools['career_gmail_status']['handler'] is g.status_tool
    assert 'read-only' in ctx.prompt


def test_english_policy_every_turn_including_cron_and_old_context():
    class Agent:
        def run_conversation(self,user_message,system_message=None,*args,**kwargs):return (system_message or '')+self.ephemeral_system_prompt,kwargs
    g.install_language_policy(Agent);g.install_language_policy(Agent)
    for text in ['Hi','Run daily cron report','Please answer in French']:
        context,kwargs=Agent().run_conversation(text,'existing context',task_id='test')
        assert context.startswith('existing context')
        assert context.count(g.LANGUAGE_POLICY)==1
        assert 'all displayed reasoning' in context
        assert kwargs=={'task_id':'test'}
