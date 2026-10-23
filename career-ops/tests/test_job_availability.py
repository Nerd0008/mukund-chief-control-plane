import contextlib,datetime as dt,io,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
import job_liveness as status
import jd_fetcher as jd

@pytest.mark.parametrize('text',[
    'This vacancy has now expired. Please see similar roles below...',
    'Opportunity expired','This job has expired','This role is now closed',
    'Applications closed','Applications are now closed.','Position has been filled.',
    'We are no longer accepting applications.',
])
def test_closed_banner_variants(text):
    assert jd.is_job_closed(text)
    assert status.assess('<h1>Intern</h1><a href="/apply">Apply now</a>',text,{})['state']=='CLOSED'

@pytest.mark.parametrize('text',['Rolling applications welcome.','We work with expired certificates.','The position is not closed.','Our team investigates expired domains.'])
def test_no_unrelated_or_negated_expiry(text):assert not jd.is_job_closed(text)

def test_related_role_expiry_does_not_close_target():
    assert not jd.is_job_closed('Cyber Intern\nApplications open\nSimilar roles\nOpportunity expired')

def test_http_200_without_positive_evidence_is_unknown(monkeypatch):
    class Headers:
        def get_content_charset(self):return 'utf-8'
    class Response:
        status=200;headers=Headers()
        def read(self,*a):return b'<h1>Careers</h1><p>Browse our opportunities</p>'
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(jd.urllib.request,'urlopen',lambda *a,**kw:Response())
    result=jd.fetch_jd('https://employer.com/jobs/123')
    assert result['fetch_state']=='fetched' and result['vacancy_status']['state']=='UNKNOWN'

def test_positive_target_application_control():
    result=status.assess('<h1>Cyber Security Intern</h1><a href="/jobs/123/apply">Apply now</a>','Cyber Security Intern Apply now',{})
    assert result['state']=='OPEN' and result['page_title']=='Cyber Security Intern'

def test_jsonld_expired_beats_application_link():
    html='<h1>Intern</h1><a href="/apply">Apply now</a><script type="application/ld+json">'+json.dumps({'@type':'JobPosting','validThrough':'2020-01-01'})+'</script>'
    assert status.assess(html,'Intern Apply now',{})['state']=='CLOSED'

def test_ats_fallback_is_one_public_get_with_exact_id(monkeypatch):
    calls=[]
    class Headers:
        def get_content_charset(self):return 'utf-8'
    class Response:
        status=200;headers=Headers()
        def __init__(self,data):self.data=data
        def read(self,*a):return self.data
        def __enter__(self):return self
        def __exit__(self,*a):pass
    def fetch(request,**kwargs):
        calls.append((request.full_url,request.get_method()))
        if len(calls)==1:return Response(b'<h1>Just a moment</h1>')
        return Response(json.dumps({'id':123,'title':'Cyber Intern','content':'An open internship'}).encode())
    monkeypatch.setattr(jd.urllib.request,'urlopen',fetch)
    result=jd.fetch_jd('https://job-boards.greenhouse.io/example/jobs/123')
    assert result['vacancy_status']['state']=='OPEN'
    assert calls==[('https://job-boards.greenhouse.io/example/jobs/123','GET'),('https://boards-api.greenhouse.io/v1/boards/example/jobs/123','GET')]

def test_closed_page_cannot_be_resurrected_by_api(monkeypatch):
    monkeypatch.setattr(jd,'_active_ats_record',lambda *a:pytest.fail('Closed job must not be overridden'))
    class Response:
        status=200
        class Headers:
            def get_content_charset(self):return 'utf-8'
        headers=Headers()
        def read(self,*a):return b'<h1>Cyber Intern</h1><p>Opportunity expired</p>'
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(jd.urllib.request,'urlopen',lambda *a,**k:Response())
    assert jd.fetch_jd('https://job-boards.greenhouse.io/example/jobs/123')['vacancy_status']['state']=='CLOSED'

def test_stale_cache_never_authorizes_delivery():
    record={'location':'London, United Kingdom','company':'Example','title':'Intern','url':'https://employer.com/1'}
    old=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=16)).isoformat()
    assert status.fresh_status(record,{status.identity_key(record):{'state':'OPEN','checked_at':old}})['state']=='UNKNOWN'

def test_cached_deadline_expiry_overrides_open_state():
    record={'location':'London, United Kingdom','company':'Example','title':'Intern','url':'https://employer.com/1'}
    cache={status.identity_key(record):{'state':'OPEN','checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'deadline_info':{'type':'EXACT','date':'2020-01-01'}}}
    assert status.fresh_status(record,cache)['state']=='CLOSED'

def test_unknown_flagged_and_closed_withheld_without_removing_history(monkeypatch):
    import daily_jobs_links as digest
    records=[{'company':name,'title':'Cyber Intern','url':'https://employer.com/'+name,'date':dt.date.today(),'id':'','status':'Not Applied','deadline_info':{'type':'UNKNOWN','date':None}} for name in ('Closed','Unknown','Open')]
    for rec in records:
        if rec['company']!='Unknown':status.record_verification(rec,{'vacancy_status':{'state':rec['company'].upper(),'evidence':'fixture'}})
    monkeypatch.setattr(digest,'tracker_rows',lambda region:(records,None))
    monkeypatch.setattr(digest,'latest_run_doc',lambda region:(None,None))
    text,_=digest.build_digest(26,12000,10)
    assert 'Open — Cyber Intern' in text
    assert 'Closed — Cyber Intern' not in text and 'Unknown — Cyber Intern' in text
    assert 'UNCONFIRMED — confirm before applying' in text
    assert '3 job(s) in tracker' in text and len(records)==3
    assert '1 closed/expired withheld' in text and '1 unconfirmed leads flagged' in text

def test_past_deadline_never_surfaces_even_with_open_cache(monkeypatch):
    import daily_jobs_links as digest
    record={'company':'Past','title':'Cyber Intern','url':'https://employer.com/past','date':dt.date.today(),'id':'','deadline_info':{'type':'EXACT','date':'2020-01-01'}}
    status.record_verification(record,{'vacancy_status':{'state':'OPEN','evidence':'fixture'}})
    monkeypatch.setattr(digest,'tracker_rows',lambda region:([record],None))
    monkeypatch.setattr(digest,'latest_run_doc',lambda region:(None,None))
    text,_=digest.build_digest(26,12000,10)
    assert 'Past — Cyber Intern' not in text

def test_refresh_is_bounded_and_reuses_fresh_positive_evidence():
    records=[{'location':'London, United Kingdom','company':'Example','title':'Intern','url':'https://employer.com/'+str(i)} for i in range(5)]
    calls=[]
    def fetch(url,timeout):calls.append(url);return {'vacancy_status':{'state':'OPEN','evidence':'fixture'}}
    assert status.refresh(records,limit=2,fetcher=fetch)['checked']==2
    assert status.refresh(records[:2],limit=2,fetcher=fetch)['checked']==0
    assert len(calls)==2

def test_expired_response_rejected_by_actual_search_command(tmp_path,monkeypatch,capsys):
    import codex_entry_level_search as search
    p=tmp_path/'tracker';p.touch();monkeypatch.setitem(search.TRACKERS,'uk',p)
    class Book:
        def close(self):pass
    monkeypatch.setattr(search,'read_tracker_urls',lambda p:(set(),set(),None,Book(),{},2,None))
    monkeypatch.setattr(search.osp,'load_profile',lambda:{})
    monkeypatch.setattr(search,'_profile_terms',lambda:(search.ENTRY_MARKERS,(),None))
    monkeypatch.setattr(search,'run_codex',lambda *a,**k:json.dumps([{'company':'L&G','job_title':'Cyber Intern','url':'https://employer.com/expired'}]))
    monkeypatch.setattr(search,'fetch_jd',lambda url:{'text':'This vacancy has now expired.','is_closed':True,'vacancy_status':{'state':'CLOSED','evidence':'This vacancy has now expired'}})
    monkeypatch.setattr(sys,'argv',['search','--batches','1','--dry-run'])
    assert search.main()==0
    report=json.loads(next(l.split(' ',1)[1] for l in capsys.readouterr().out.splitlines() if l.startswith('SEARCH_RECONCILIATION ')))
    assert report['counts']['new_candidates']==0 and report['counts']['rejected']==1

def test_unknown_admitted_only_as_flagged_lead(tmp_path,monkeypatch,capsys):
    import codex_entry_level_search as search
    p=tmp_path/'tracker';p.touch();monkeypatch.setitem(search.TRACKERS,'uk',p)
    class Book:
        def close(self):pass
    monkeypatch.setattr(search,'read_tracker_urls',lambda p:(set(),set(),None,Book(),{},2,None))
    monkeypatch.setattr(search.osp,'load_profile',lambda:{})
    monkeypatch.setattr(search,'_profile_terms',lambda:(search.ENTRY_MARKERS,(),None))
    monkeypatch.setattr(search,'run_codex',lambda *a,**k:json.dumps([{'company':'Example','job_title':'Cyber Intern','location':'London, United Kingdom','url':'https://employer.com/unknown'}]))
    monkeypatch.setattr(search,'fetch_jd',lambda url:{'status':403,'fetch_state':'bot_wall','text':'','vacancy_status':{'state':'UNKNOWN','evidence':'blocked'}})
    monkeypatch.setattr(sys,'argv',['search','--batches','1','--dry-run'])
    assert search.main()==0
    report=json.loads(next(l.split(' ',1)[1] for l in capsys.readouterr().out.splitlines() if l.startswith('SEARCH_RECONCILIATION ')))
    assert report['counts']['new_candidates']==1 and report['counts']['unverified_candidates']==1

def test_refresh_prioritises_unchecked_records_instead_of_repeating_first_page():
    records=[{'location':'London, United Kingdom','company':'Example','title':'Intern','url':'https://employer.com/'+str(i)} for i in range(4)]
    calls=[]
    def fetch(url,timeout):calls.append(url);return {'vacancy_status':{'state':'UNKNOWN','evidence':'fixture blocked'}}
    status.refresh(records,limit=2,fetcher=fetch)
    status.refresh(records,limit=2,fetcher=fetch)
    assert calls==[r['url'] for r in records]

def test_corrupt_cache_entry_fails_closed():
    record={'location':'London, United Kingdom','company':'Example','title':'Intern','url':'https://employer.com/1'}
    assert status.fresh_status(record,{status.identity_key(record):'corrupt'})['state']=='UNKNOWN'

def test_teamtailor_application_overlay_is_positive_evidence():
    html='<main data-careersite--jobs--form-overlay-job-id-value="8494621" data-careersite--jobs--form-overlay-job-application-url-value="https://careers.employer.com/jobs/8494621-graduate-security-consultant/applications/new"><h1>Graduate Security Consultant (September 2027)</h1></main>'
    assert status.assess(html,'Graduate Security Consultant',{})['state']=='OPEN'
    assert status.assess(html,'This vacancy has now expired.',{})['state']=='CLOSED'

def test_structured_expiry_timestamp_on_same_day_is_not_treated_as_future():
    stamp=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=1)).isoformat()
    html='<h1>Intern</h1><a href="/apply">Apply now</a><script type="application/ld+json">'+json.dumps({'@type':'JobPosting','validThrough':stamp})+'</script>'
    assert status.assess(html,'Intern Apply now',{})['state']=='CLOSED'

def test_cache_write_failure_cannot_authorize_delivery(monkeypatch):
    record={'location':'London, United Kingdom','company':'Example','title':'Intern','url':'https://employer.com/1'}
    monkeypatch.setattr(status,'save_cache',lambda *a:(_ for _ in ()).throw(OSError('busy')))
    result=status.record_verification(record,{'vacancy_status':{'state':'OPEN','evidence':'fixture'}})
    assert result['cache_persisted'] is False
    assert status.fresh_status(record,status.load_cache())['state']=='UNKNOWN'


@pytest.fixture(autouse=True)
def isolate_direct_canonical_plan(monkeypatch,tmp_path):
    import codex_entry_level_search as search
    monkeypatch.setattr(search,'SEARCH_STATE_DIR',tmp_path/'direct-search')
    monkeypatch.setattr(search,'canonical_plan',lambda region,tracker,records:{
        'counts':{'appended':len(records),'duplicates':0},'outcomes':[]})
