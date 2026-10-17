import pathlib,sys
sys.path.insert(0,r'C:\Users\mukun\Documents\mukund-chief-control-plane\career-ops')
import pytest
import hermes_response_language as lang
import hermes_gmail_tools as gmail

CHINESE='搜索完成。六个新岗位已写入追踪器，现在需要向用户报告结果。'

@pytest.mark.parametrize('text',[CHINESE,'Jobs found\n'+CHINESE,'搜索已完成，现在需要报告搜索结果。\nAll done'])
def test_chinese_prose_blocked(text):assert lang.checked_text(text)==lang.FAILURE

@pytest.mark.parametrize('text',['6 jobs found. No applications submitted.','Company: 腾讯 Tencent','> '+CHINESE,'```\n'+CHINESE+'\n```'])
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
