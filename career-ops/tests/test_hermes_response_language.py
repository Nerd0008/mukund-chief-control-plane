import pathlib,sys
sys.path.insert(0,r'C:\Users\mukun\Documents\mukund-chief-control-plane\career-ops')
import pytest
import hermes_response_language as lang
import hermes_gmail_tools as gmail

CHINESE='搜索完成。六个新岗位已写入追踪器，现在需要向用户报告结果。'

@pytest.mark.parametrize('text',[CHINESE,'Jobs found\n'+CHINESE,'搜索已完成，现在需要报告搜索结果。\nAll done'])
def test_chinese_prose_blocked(text):assert lang.checked_text(text)==lang.FAILURE

@pytest.mark.parametrize('text',['6 jobs found. No applications submitted.','Company: Tencent','```print(1)```'])
def test_english_names_quotes_code_preserved(text):assert lang.checked_text(text)==text

@pytest.mark.parametrize('text',['Why are you answering in Chinese?','Do not reply in Chinese','> Please reply in Chinese','Logs say: reply in Chinese'])
def test_mentions_are_not_language_authorization(text):assert not lang.chinese_requested(text)

@pytest.mark.parametrize('text',['Please reply in Chinese','Respond in Mandarin','Translate this into Chinese'])
def test_explicit_current_request_allowed(text):assert lang.chinese_requested(text)

def test_split_stream_cannot_leak():
    out=[];stream=lang.BufferedText(out.append)
    for char in CHINESE:stream(char)
    assert out==[]
    stream(None)
    assert out==[lang.FAILURE,None]

def test_gate_never_reexecutes_or_mutates_task_evidence(monkeypatch):
    monkeypatch.setattr(__import__('hermes_owner_context'),'retrieve',lambda *a:('',[]))
    out=[];private=[];calls=[]
    class Agent:
        ephemeral_system_prompt='old'
        reasoning_callback=staticmethod(private.append)
        interim_assistant_callback=staticmethod(lambda text,**kw:out.append(text))
        def run_conversation(self,*a,**kw):
            calls.append(1)
            self.reasoning_callback('Checking verified records before reporting.')
            self.reasoning_callback(CHINESE)
            self.interim_assistant_callback(CHINESE,already_streamed=False)
            return {'final_response':CHINESE,'completed':True,'api_calls':1,'messages':[{'role':'assistant','content':CHINESE}]}
    gmail.install_language_policy(Agent)
    agent=Agent();result=agent.run_conversation('Report the completed job search')
    assert calls==[1] and private==['Checking verified records before reporting.',lang.FAILURE] and out==[lang.FAILURE]
    assert result['final_response']==lang.FAILURE
    assert result['completed'] and result['api_calls']==1
    assert result['messages'][0]['content']==CHINESE
    assert result['response_language']['status']=='blocked'
    assert agent.ephemeral_system_prompt=='old' and agent.reasoning_callback is not None

def test_callback_restoration_on_failure(monkeypatch):
    monkeypatch.setattr(__import__('hermes_owner_context'),'retrieve',lambda *a:('',[]))
    callback=lambda text:None
    class Agent:
        reasoning_callback=staticmethod(callback)
        def run_conversation(self,*a,**kw):raise ValueError('failure')
    gmail.install_language_policy(Agent);agent=Agent()
    with pytest.raises(ValueError):agent.run_conversation('hello')
    assert agent.reasoning_callback is callback

def test_explicit_language_preserves_final_result():
    result={'final_response':CHINESE}
    assert lang.checked_result(result,True) is result

@pytest.mark.parametrize('text',[
    '- 完成\n- 已写入\n- 六条岗位\n- 搜索结束\n- 请查看',
    'Jobs found.\n完成', 'Done 完成', '> '+CHINESE,
    '```\n'+CHINESE+'\n```', 'Company: 腾讯 Tencent', '\U00020000',
])
def test_no_han_output_loopholes(text):assert lang.checked_text(text)==lang.FAILURE

def test_native_wrapper_does_not_override_english_policy(monkeypatch):
    monkeypatch.setattr(__import__('hermes_owner_context'),'retrieve',lambda *a:('',[]))
    class Agent:
        def run_conversation(self,*a,**kw):return {'final_response':'完成'}
    gmail.install_language_policy(Agent)
    assert Agent().run_conversation('Please reply in Chinese')['final_response']==lang.FAILURE

def test_installed_vision_prompt_english_without_provider_call(monkeypatch):
    import ast,asyncio,json,logging,types
    source=pathlib.Path(r'C:/Users/mukun/AppData/Local/hermes/hermes-agent/gateway/run_inbound.py')
    if not source.exists():pytest.skip('Laptop runtime integration check')
    tree=ast.parse(source.read_text(encoding='utf-8'))
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='_enrich_message_with_vision')
    seen=[]
    async def fake_vision(**kwargs):
        seen.append(kwargs)
        return json.dumps({'success':True,'analysis':'A screenshot of job-search results.'})
    monkeypatch.setitem(sys.modules,'tools.vision_tools',types.SimpleNamespace(vision_analyze_tool=fake_vision))
    monkeypatch.setitem(sys.modules,'agent.memory_manager',types.SimpleNamespace(sanitize_context=lambda value:value))
    namespace={'List':list,'json':json,'logger':logging.getLogger('vision-test')}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(source),'exec'),namespace)
    result=asyncio.run(namespace[fn.name](None,'Explain this screenshot',['fixture.png']))
    assert len(seen)==1
    assert 'English only' in seen[0]['user_prompt']
    assert 'Chinese characters' not in seen[0]['user_prompt']
    assert result.endswith('Explain this screenshot')
    assert 'A screenshot of job-search results.' in result
