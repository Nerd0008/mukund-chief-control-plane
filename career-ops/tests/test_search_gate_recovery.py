import json
from pathlib import Path
import sys
import pytest

CAREER=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(CAREER),str(CAREER/'discovery')]
import classifiers as c
import pipeline as p
import scheduled_orchestrator as scheduler
from semantic_contract import build_classification,candidate_id

def records(n=12):
    return [{'company':'Example','title':'Cyber Security Intern','location':'London','url':f'https://example.com/jobs/{i}'} for i in range(n)]

class NoBalance:
    def __init__(self):self.calls=0
    def check_health(self):return {'status':'healthy'}
    def get_identity(self):return {'observed_models':[{'id':'deepseek-flash'}]}
    def dispatch(self,request):
        self.calls+=1
        return {'status':'FAILED','error':'Insufficient Balance (request_id: synthetic)'}

def test_deepseek_balance_stops_after_one_request_not_split_or_all_batches():
    adapter=NoBalance()
    doc=c.deepseek_bulk_classify(records(219),adapter=adapter,batch_size=8)
    assert adapter.calls==1 and doc['requests']==1 and doc['split_retries']==0
    assert doc['classified']==0 and doc['terminal_failure']=='insufficient_balance'
    assert len(doc['classifications'])==219
    assert not any(x['accepted'] for x in doc['classifications'].values())

def test_auto_rescues_balance_failure_even_when_escalation_is_disabled(monkeypatch):
    rec=records(1)[0];adapter=NoBalance();calls=[]
    classification=build_classification(rec,primary_label='strong_entry_level_match',confidence=.9,reasons=['Cyber Security Intern title'],uncertainty=[],provider='codex',model='stub',classifier='codex_bulk')
    monkeypatch.setattr(p,'deepseek_probe',lambda model:{'available':True})
    def codex(*args,**kwargs):
        calls.append(1)
        return {'provider':'codex','classified':1,'classifications':{candidate_id(rec):classification}}
    monkeypatch.setattr(p,'_codex_semantic_pass',codex)
    doc=p._semantic_stage([rec],semantic='auto',deepseek_model='deepseek-flash',batch_size=8,timeout=1,mode='high_recall',deepseek_adapter=adapter)
    assert calls==[1] and doc['provider']=='codex'
    assert doc['deepseek_attempt']['requests']==1
    assert doc['deepseek_attempt']['terminal_failure']=='insufficient_balance'

def test_pinned_deepseek_does_not_silently_switch_provider(monkeypatch):
    monkeypatch.setattr(p,'deepseek_probe',lambda model:{'available':True})
    monkeypatch.setattr(p,'_codex_semantic_pass',lambda *a,**k:pytest.fail('explicit provider must remain explicit'))
    doc=p._semantic_stage(records(1),semantic='deepseek',deepseek_model='deepseek-flash',batch_size=8,timeout=1,mode='high_recall',deepseek_adapter=NoBalance())
    assert doc['provider']=='none' and doc['deepseek_attempt']['requests']==1

def test_failed_codex_rescue_remains_failure_not_model_success(monkeypatch):
    monkeypatch.setattr(p,'deepseek_probe',lambda model:{'available':True})
    monkeypatch.setattr(p,'_codex_semantic_pass',lambda *a,**k:{'provider':'none','classified':0,'classifications':{},'limitation':'unavailable'})
    doc=p._semantic_stage(records(1),semantic='auto',deepseek_model='deepseek-flash',batch_size=8,timeout=1,mode='high_recall',deepseek_adapter=NoBalance())
    assert doc['provider']=='none' and doc['codex_attempt']['limitation']=='unavailable'
    assert 'NOT a model pass' in doc['limitation']

def test_normal_scheduled_defaults_enable_bounded_escalation():
    assert scheduler.DEFAULT_CODEX_ESCALATION=='on'
    assert c.DEFAULT_CODEX_BUDGET==8

@pytest.mark.parametrize('message',['Read timeout','empty content','payload was not a list'])
def test_content_or_transient_errors_are_not_mislabelled_balance_failure(message):
    assert c.terminal_provider_error({'error':message}) is None


def test_smartrecruiters_tracking_variants_collapse_without_losing_requisition():
    import tracker_writer as tw
    from career_search_recall import posting_key
    base='https://jobs.smartrecruiters.com/Example/744000123-Cyber-Intern'
    assert tw.normalize_url(base+'?oga=true')==tw.normalize_url(base+'?trid=tracking')==posting_key(base)
    assert tw.normalize_url(base+'?jobId=123')!=tw.normalize_url(base+'?jobId=124')
    assert tw.normalize_url('https://other.example/jobs?trid=123')!=tw.normalize_url('https://other.example/jobs?trid=124')


def test_authoritative_ats_identity_reaches_writer_without_ats_becoming_employer():
    import regional_job_search as rjs
    candidate={'company':'SmartRecruiters','title':'Example Cyber Intern','location':None,
        'url':'https://jobs.smartrecruiters.com/Example/744000123-Cyber-Intern',
        'verified_posting':{'company':'Example','title':'Cyber Intern','location':'London, United Kingdom'}}
    record=rjs.build_record('uk',candidate,rjs.load_policy(),'test',{})
    assert record['company']=='Example' and record['title']=='Cyber Intern'
    assert record['location']=='London, United Kingdom'
    assert candidate['company']=='SmartRecruiters'
