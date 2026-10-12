import pathlib,sys,pytest,types
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import hermes_owner_context as owner
import hermes_gmail_tools as gmail

@pytest.fixture
def refs(tmp_path):
    for name in owner.FILES:(tmp_path/name).write_text('PRIVATE MOTIVATION' if name=='personal_context.md' else 'Evidence '+name)
    return tmp_path

@pytest.mark.parametrize('question',['What do you know about my career aspirations?','What are my goals?','Who am I?','Tell me about myself','My full profile'])
def test_profile_retrieves_all_five(question,refs):
    text,evidence=owner.retrieve(question,refs)
    assert len(evidence)==5 and 'PRIVATE MOTIVATION' in text
    assert all(len(r['sha256'])==64 for r in evidence)

@pytest.mark.parametrize('question',['Write my LinkedIn post about my career aspirations','Build my CV','Write a cover letter','Draft my public profile'])
def test_public_work_never_receives_private_context(question,refs):
    text,evidence=owner.retrieve(question,refs)
    assert 'PRIVATE MOTIVATION' not in text
    assert 'personal_context.md' not in [e['file'] for e in evidence]
    assert 'superseded_history.md' in [e['file'] for e in evidence]

def test_missing_required_reference_fails_closed(refs):
    (refs/'personal_context.md').unlink()
    with pytest.raises(RuntimeError,match='unavailable'):owner.retrieve('What are my goals?',refs)

def test_unrelated_turn_does_not_read_private_files(tmp_path):
    assert owner.retrieve('What time is it?',tmp_path)==('',[])

def test_native_turn_uses_ephemeral_seam_despite_frozen_cache(refs,monkeypatch):
    monkeypatch.setattr(owner,'ROOT',refs)
    class Agent:
        ephemeral_system_prompt='existing overlay'
        _cached_system_prompt='old frozen summary'
        def run_conversation(self,msg,system=None,*a,**k):return self._cached_system_prompt+self.ephemeral_system_prompt
    gmail.install_language_policy(Agent)
    agent=Agent()
    assert 'PRIVATE MOTIVATION' in agent.run_conversation('What are my goals?','old frozen summary')
    assert len(agent._owner_context_retrieval)==5
    assert agent.ephemeral_system_prompt=='existing overlay'
    assert agent._cached_system_prompt=='old frozen summary'
    assert 'PRIVATE MOTIVATION' not in agent.run_conversation('Write my CV')

def test_changes_reloaded_each_turn(refs):
    first=owner.retrieve('Who am I?',refs)
    (refs/'personal_context.md').write_text('OWNER CORRECTION')
    second=owner.retrieve('Who am I?',refs)
    assert first[1][0]['sha256']!=second[1][0]['sha256']
    assert 'OWNER CORRECTION' in second[0]

def test_retrieval_failure_prevents_model_invocation(refs,monkeypatch):
    monkeypatch.setattr(owner,'ROOT',refs)
    (refs/'career_context.md').unlink()
    class Agent:
        def run_conversation(self,*a,**k):pytest.fail('model reached without required facts')
    gmail.install_language_policy(Agent)
    with pytest.raises(RuntimeError):Agent().run_conversation('What are my goals?')


def test_real_hermes_wire_builder_receives_profile_without_history_mutation(refs,monkeypatch):
    import datetime as dt
    sys.path.insert(0,'C:/Users/mukun/AppData/Local/hermes/hermes-agent')
    from agent.turn_context import build_api_messages
    monkeypatch.setattr(owner,'ROOT',refs)
    class Agent:
        ephemeral_system_prompt=None
        _cached_system_prompt='frozen original prompt'
        _current_turn_timestamp=dt.datetime.now(dt.timezone.utc)
        def run_conversation(self,msg,system=None,*a,**k):
            return build_api_messages(self,[],current_turn_user_idx=None,ext_prefetch_cache=None,
                plugin_user_context=None,moa_config=None,active_system_prompt=self._cached_system_prompt)
    gmail.install_language_policy(Agent)
    agent=Agent();wire,effective=agent.run_conversation('What do you know about my career aspirations?')
    assert wire[0]['role']=='system' and 'PRIVATE MOTIVATION' in wire[0]['content']
    assert effective.startswith('frozen original prompt')
    assert agent._cached_system_prompt=='frozen original prompt'
    assert agent.ephemeral_system_prompt is None
