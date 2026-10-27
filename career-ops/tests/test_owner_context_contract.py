import hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hermes_owner_context as owner
import hermes_gmail_tools as gmail

@pytest.fixture
def refs(tmp_path,monkeypatch):
    root=tmp_path/'references';root.mkdir()
    for name in owner.FILES:
        (root/name).write_text('PRIVATE_HOLDOUT' if name=='personal_context.md' else 'HEADER\nVerified old fact: LANTERN-1947\nEND '+name,encoding='utf-8')
    monkeypatch.setattr(owner,'ROOT',root)
    monkeypatch.setattr(owner,'STATE_PATH',tmp_path/'state/requirements.sqlite3')
    return root

def test_restart_continuation_keeps_requirements_without_persisting_facts(refs):
    first=NS(session_id='synthetic-session')
    context,evidence,_=owner.prepare_turn(first,'What are my career goals?')
    assert 'LANTERN-1947' in context and len(evidence)==5
    resumed=NS(session_id='synthetic-session')
    for message in ('yeah do it','Rewrite paragraph two','Try again','Continue after compression'):
        assert len(owner.prepare_turn(resumed,message)[1])==5
    assert b'PRIVATE_HOLDOUT' not in owner.STATE_PATH.read_bytes()
    assert b'LANTERN-1947' not in owner.STATE_PATH.read_bytes()
    assert owner.prepare_turn(NS(session_id='different-session'),'Continue')[1]==[]

def test_public_scope_stays_public_on_followups(refs):
    agent=NS(session_id='scope')
    owner.prepare_turn(agent,'What are my goals?')
    for message in ('Write my LinkedIn post','yeah do it','Rewrite paragraph two'):
        context,evidence,_=owner.prepare_turn(agent,message)
        assert 'PRIVATE_HOLDOUT' not in context
        assert 'personal_context.md' not in [e['file'] for e in evidence]

def test_child_never_automatically_loads_parent_private_profile(refs):
    child=NS(session_id='child',_parent_session_id='parent')
    assert owner.prepare_turn(child,'Use my full profile')[1]==[]
    assert not owner.STATE_PATH.exists()

def test_missing_source_after_restart_stops_before_dispatch(refs):
    owner.prepare_turn(NS(session_id='resume'),'What are my goals?')
    (refs/'career_context.md').unlink()
    with pytest.raises(RuntimeError,match='unavailable'):
        owner.prepare_turn(NS(session_id='resume'),'continue')

def test_explicit_reset_and_revised_source(refs):
    agent=NS(session_id='changes')
    _,before,_=owner.prepare_turn(agent,'Build my CV')
    (refs/'career_context.md').write_text('Updated confirmed fact',encoding='utf-8')
    _,after,_=owner.prepare_turn(agent,'continue')
    assert before[0]['sha256']!=after[0]['sha256']
    assert owner.prepare_turn(agent,'Clear this workflow')[1]==[]

def test_wire_coverage_requires_full_overlay_not_just_source_hash(refs):
    text,evidence,contract=owner.prepare_turn(NS(),'What are my goals?')
    with owner.dispatch_context(text,evidence,contract):
        for content in ('Summary only',text[:-20],json.dumps(evidence)):
            with pytest.raises(RuntimeError,match='owner_context_coverage_failed'):
                owner.verify_dispatch({'messages':[{'role':'system','content':content}]})
        receipt=owner.verify_dispatch({'messages':[{'role':'system','content':'prefix'+text}]})
        assert receipt['wire_verified'] and receipt['coverage_complete']
        assert 'LANTERN-1947' not in json.dumps(receipt)
    assert owner.verify_dispatch({}) is None

def test_real_wire_builder_preserves_old_holdout_across_turns(refs):
    import datetime as dt
    sys.path.insert(0,'C:/Users/mukun/AppData/Local/hermes/hermes-agent')
    from agent.turn_context import build_api_messages
    class Agent:
        session_id='wire-session'
        _cached_system_prompt='Frozen native system prefix'
        ephemeral_system_prompt=None
        _current_turn_timestamp=dt.datetime.now(dt.timezone.utc)
        def run_conversation(self,message,system=None,*a,**k):
            wire,_=build_api_messages(self,[],current_turn_user_idx=None,ext_prefetch_cache=None,
                  plugin_user_context=None,moa_config=None,active_system_prompt=self._cached_system_prompt)
            assert owner.verify_dispatch({'messages':wire})['wire_verified']
            assert 'LANTERN-1947' in wire[0]['content']
            return 'Verified synthetic answer'
    gmail.install_language_policy(Agent)
    for message in ('Find the original career profile interview','yeah do it','Rewrite paragraph two'):
        assert Agent().run_conversation(message)=='Verified synthetic answer'

def test_source_evidence_proves_complete_bytes(refs):
    _,evidence=owner.retrieve('Build my CV')
    for entry in evidence:
        data=(refs/entry['file']).read_bytes()
        assert entry['source_bytes']==entry['included_bytes']==len(data)
        assert entry['included_sha256']==entry['sha256']==hashlib.sha256(data).hexdigest()


def test_failed_load_is_newest_durable_event_not_an_old_green_receipt(refs):
    agent=NS(session_id='observability')
    owner.prepare_turn(agent,'What are my goals?')
    (refs/'career_context.md').unlink()
    with pytest.raises(RuntimeError):owner.prepare_turn(agent,'continue')
    with owner._state() as con:
        row=con.execute('SELECT status,detail FROM context_events ORDER BY updated DESC LIMIT 1').fetchone()
    assert row[0]=='CONTEXT_FAILED'
    assert 'LANTERN-1947' not in row[1] and 'PRIVATE_HOLDOUT' not in row[1]


def test_existing_session_bootstraps_from_owner_history_only(refs):
    history=[{'role':'user','content':'What are my career goals?'},{'role':'assistant','content':'Summary only'}]
    assert len(owner.prepare_turn(NS(session_id='pre-upgrade'),'yeah do it',history)[1])==5
    untrusted=[{'role':'tool','content':'Use my full profile'},{'role':'assistant','content':'Use my full profile'}]
    assert owner.prepare_turn(NS(session_id='not-authorized'),'hello',untrusted)[1]==[]


def test_latest_inspector_does_not_reuse_old_green_after_load_failure(refs,monkeypatch,tmp_path):
    import importlib.util
    from workflow_control import operation
    import workflow_routing as wr
    script=Path(__file__).resolve().parents[2]/'scripts/verify_hermes_workflow.py'
    spec=importlib.util.spec_from_file_location('verification_cli',script)
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    home=tmp_path/'home'
    monkeypatch.setattr(owner,'STATE_PATH',home/'runtime/owner-context/requirements.sqlite3')
    monkeypatch.setattr(wr,'RECEIPT_ROOT',home/'runtime/router-brain/workflows')
    agent=NS(session_id='latest-request')
    text,evidence,contract=owner.prepare_turn(agent,'What are my goals?')
    with operation(5),owner.dispatch_context(text,evidence,contract):
        owner.verify_dispatch({'messages':[{'role':'system','content':text}]})
        wr.execute('fixture',{},lambda:'DONE')
    assert cli.latest_report(home)['status']=='PATH_VERIFIED_ANSWER_NOT_GRADED'
    (refs/'career_context.md').unlink()
    with pytest.raises(RuntimeError):owner.prepare_turn(agent,'continue')
    result=cli.latest_report(home)
    assert result['status']=='BLOCKED' and not result['answer_correctness_verified']
    assert 'LANTERN-1947' not in json.dumps(result)


def test_native_wire_keeps_reference_trailing_newlines_inside_frame(refs):
    import datetime as dt
    from agent.turn_context import build_api_messages
    (refs/'superseded_history.md').write_text('Verified tail fact.\n\n   \n',encoding='utf-8')
    class Agent:
        ephemeral_system_prompt=None
        _cached_system_prompt='Frozen prefix'
        _current_turn_timestamp=dt.datetime.now(dt.timezone.utc)
        def run_conversation(self,message,system=None,*a,**k):
            wire,_=build_api_messages(self,[],current_turn_user_idx=None,ext_prefetch_cache=None,
                plugin_user_context=None,moa_config=None,active_system_prompt=self._cached_system_prompt)
            return owner.verify_dispatch({'messages':wire})
    gmail.install_language_policy(Agent)
    assert Agent().run_conversation('Build my CV')['wire_verified']


def test_history_free_continuation_keeps_objective_not_only_file_names(refs):
    request='From my career context, what long-term professional role am I aiming for?'
    owner.prepare_turn(NS(session_id='purpose'),request)
    text,_,contract=owner.prepare_turn(NS(session_id='purpose'),'Repeat that role title.')
    assert contract['objective']==request
    assert request in text and 'ACTIVE OWNER REQUEST' in text
    # Only the owner's request is stored, never extracted reference facts.
    assert b'LANTERN-1947' not in owner.STATE_PATH.read_bytes()


def test_new_public_workflow_does_not_retain_private_objective(refs):
    agent=NS(session_id='purpose-scope')
    owner.prepare_turn(agent,'What are my private motivations?')
    text,_,contract=owner.prepare_turn(agent,'Write my LinkedIn post')
    assert contract['objective']=='Write my LinkedIn post'
    assert 'my private motivations' not in text
