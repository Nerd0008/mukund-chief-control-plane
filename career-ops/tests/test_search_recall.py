import json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
import codex_entry_level_search as search
from career_search_recall import posting_key,query_batches

def test_profile_can_only_widen_entry_levels(monkeypatch):
    monkeypatch.setattr(search.osp,'load_profile',lambda:{})
    monkeypatch.setattr(search.osp,'entry_level_terms',lambda p:['intern','graduate','custom-level'])
    monkeypatch.setattr(search.osp,'profile_digest',lambda:'test')
    terms,_,_=search._profile_terms()
    assert set(search.ENTRY_MARKERS)<=set(terms)
    for title in ['Security Operations Placement Year','Junior SOC Analyst','Trainee Security Analyst','Cyber Apprentice','Off-cycle Security Role','Custom-Level Cyber Role']:
        assert search.is_entry_level(title,terms)
    assert not search.is_entry_level('Senior Cyber Security Intern',terms)

def test_queries_have_diverse_levels_and_years():
    batches=query_batches({},'UK',[],2026)
    queries=[q for b in batches for q in b]
    assert len(queries)==len(set(queries))
    assert len(batches)>3 and all(0<len(b)<=6 for b in batches)
    assert any('2026' in q for q in queries)
    assert any('2027' in q for q in queries)
    assert any(not any(str(y) in q for y in (2026,2027)) for q in queries)
    for word in ['internship','graduate','placement','junior','trainee','apprentice','off-cycle']:
        assert any(word in q for q in queries)
    assert all('"' not in q for q in queries)

def test_url_tracking_variants_collapse_but_distinct_ids_survive():
    root='https://job-boards.greenhouse.io/company/jobs/123'
    assert posting_key(root)==posting_key(root+'?gh_src=Simplify&utm_source=board#apply')
    assert posting_key('https://example.com/jobs?job_id=123')!=posting_key('https://example.com/jobs?job_id=124')
    assert posting_key('https://example.com/jobs/AbC')!=posting_key('https://example.com/jobs/abc')

@pytest.mark.parametrize('url',['','not a URL','javascript:alert(1)'])
def test_invalid_urls_rejected(url):assert posting_key(url)==''

@pytest.mark.parametrize('offset',[0,5])
def test_offline_production_dry_run_has_distinct_batches_and_exact_accounting(tmp_path,monkeypatch,capsys,offset):
    tracker=tmp_path/'tracker.xlsx';tracker.touch()
    monkeypatch.setitem(search.TRACKERS,'uk',tracker)
    monkeypatch.setattr(search.osp,'load_profile',lambda:{})
    monkeypatch.setattr(search,'_profile_terms',lambda:(search.ENTRY_MARKERS,(),None))
    class Book:
        def close(self):pass
        def save(self,*a):pytest.fail('dry run wrote workbook')
    monkeypatch.setattr(search,'read_tracker_urls',lambda p:({'https://jobs.example/known'},None,Book(),{},20,None))
    rows=[{'job_title':'Cyber Security Intern','url':'https://jobs.example/known'},
          {'job_title':'Cyber Security Internship','company':'Galaxy','url':'https://jobs.example/123?gh_src=one'},
          {'job_title':'Cyber Security Internship','company':'Galaxy','url':'https://jobs.example/123'},
          {'job_title':'Security Operations Placement Year','company':'Test','url':'https://jobs.example/placement'},
          {'job_title':'Senior SOC Analyst','url':'https://jobs.example/senior'},
          {'job_title':'Intern','url':''}]
    prompts=[];fetches=[]
    def fake_run(prompt,timeout):prompts.append(prompt);return json.dumps(rows)
    monkeypatch.setattr(search,'run_codex',fake_run)
    def fake_fetch(url):fetches.append(url);return {'text':'Open role.','is_closed':False}
    monkeypatch.setattr(search,'fetch_jd',fake_fetch)
    monkeypatch.setattr(sys,'argv',['search','--batches','3','--batch-offset',str(offset),'--dry-run'])
    assert search.main()==0
    assert len(prompts)==len(set(prompts))==3
    assert 'cyber security internship' in prompts[0]
    assert all('current and upcoming intakes' in prompt for prompt in prompts)
    assert len(fetches)==2
    text=capsys.readouterr().out
    report=json.loads(next(l.split(' ',1)[1] for l in text.splitlines() if l.startswith('SEARCH_RECONCILIATION ')))
    c=report['counts']
    assert c['retrieved_records']==18 and c['new_candidates']==2 and c['rejected']==1
    assert c['already_tracked']==3 and c['invalid_records']==3 and c['repeated_in_run']==9
    assert sum(c[k] for k in ('already_tracked','repeated_in_run','invalid_records','rejected','new_candidates'))==18
    assert tracker.read_bytes()==b''

def test_no_new_is_not_reported_as_no_discovery(tmp_path,monkeypatch,capsys):
    tracker=tmp_path/'tracker.xlsx';tracker.touch()
    monkeypatch.setitem(search.TRACKERS,'uk',tracker)
    monkeypatch.setattr(search.osp,'load_profile',lambda:{})
    monkeypatch.setattr(search,'_profile_terms',lambda:(search.ENTRY_MARKERS,(),None))
    class Book:
        def close(self):pass
    monkeypatch.setattr(search,'read_tracker_urls',lambda p:({'https://jobs.example/known'},None,Book(),{},20,None))
    monkeypatch.setattr(search,'run_codex',lambda *a,**k:json.dumps([{'job_title':'Intern','url':'https://jobs.example/known'}]))
    monkeypatch.setattr(search,'fetch_jd',lambda *a:pytest.fail('already-tracked job fetched'))
    monkeypatch.setattr(sys,'argv',['search','--batches','1','--dry-run'])
    assert search.main()==0
    text=capsys.readouterr().out
    assert 'does not mean no jobs were retrieved' in text
    assert '"retrieved_records": 1' in text and '"already_tracked": 1' in text

def test_profile_disciplines_beyond_six_are_not_permanently_lost(monkeypatch):
    import owner_search_profile as osp
    monkeypatch.setattr(osp,'discipline_terms',lambda p:['field'+str(i) for i in range(8)])
    queries=[q for b in query_batches({'present':True},'UK',[],2026) for q in b]
    assert all(any('field'+str(i)+' ' in q for q in queries) for i in range(8))
