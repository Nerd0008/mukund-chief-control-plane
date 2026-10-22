"""Regression controls for the 22 October search audit. Canonical workbooks are read only."""
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
import types
import pytest

import codex_entry_level_search as direct
import tracker_writer as tw
import promote_manifest as promotion
import pipeline
import regional_job_search as rjs
import web_research as web
import scheduled_orchestrator as scheduled
from career_search_recall import select_batches,query_batches
from experience_screening import experience_hits


@pytest.mark.parametrize('offset',[0,5,10,12])
def test_actual_first_batch_equals_logged_offset(offset):
    assert select_batches(13,1,offset)==[offset]
    assert select_batches(13,3,offset)==[(offset+i)%13 for i in range(3)]


def test_multiple_result_arrays_are_combined():
    assert len(direct.parse_jobs('[{"title":"A","url":"a"},{"title":"B","url":"b"}]\n[{"title":"C","url":"c"}]'))==3


@pytest.mark.parametrize('observed,error',[(False,None),(True,'provider unavailable')])
def test_unobserved_or_failed_provider_never_becomes_empty_success(monkeypatch,observed,error):
    class Provider:
        def __init__(self,**kwargs):pass
        def resolve(self):return 'fixture'
        def _run_one(self,*args,**kwargs):return {'web_search_observed':observed,'error':error,'results':[]}
    monkeypatch.setattr(web,'CodexWebSearchProvider',Provider)
    with pytest.raises(RuntimeError):direct.run_codex('fixture')


@pytest.mark.parametrize('text',[
    'Prior experience is desirable but not essential.',
    'Professional experience would be advantageous, but is not required.',
    'One year of professional experience required.',
    'No prior experience required.'])
def test_optional_or_one_year_experience_not_rejected(text):
    assert experience_hits(text)==[]


def test_mandatory_experience_still_blocks():
    assert experience_hits('At least three years of professional experience required.')


@pytest.mark.parametrize('title',['SOC Analyst L1','IT Support Technician'])
def test_neutral_supported_titles_reach_jd_screening(title):
    assert direct.is_entry_level(title)


def test_cursor_progress_is_persisted_and_corrupt_state_is_safe(tmp_path):
    path=tmp_path/'cursor.json'
    assert direct.read_cursor(path,5)==5
    direct.save_cursor(path,6)
    assert direct.read_cursor(path,5)==6
    path.write_text('invalid')
    assert direct.read_cursor(path,5)==5


def test_query_coverage_has_ats_and_all_profile_terms(monkeypatch):
    import owner_search_profile as profile
    monkeypatch.setattr(profile,'discipline_terms',lambda p:['field'+str(i) for i in range(10)])
    all_queries=[q for batch in query_batches({'profile':True},'UK',[],2026) for q in batch]
    assert any('site:jobs.ashbyhq.com' in q for q in all_queries)
    assert all(any('field'+str(i)+' ' in q for q in all_queries) for i in range(10))


def test_small_scheduled_query_budget_rotates_across_surfaces():
    matrix=web.build_query_matrix('uk')
    first=scheduled.select_queries(matrix,4,0)
    second=scheduled.select_queries(matrix,4,4)
    assert {q['query_id'] for q in first}.isdisjoint(q['query_id'] for q in second)
    assert any('after:' in q['query'] for q in matrix)


@pytest.fixture
def book_copy(tmp_path):
    profiles=tw.load_profiles();source=Path(tw.region_config(profiles,'uk')['tracker'])
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    target=tmp_path/'tracker.xlsx';shutil.copy2(source,target)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    yield profiles,target
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


def test_distinct_requisitions_with_same_title_survive_and_repeat_dedupes(book_copy,tmp_path):
    profiles,path=book_copy
    def record(identifier):return {'company':'Audit Fixture NOT REAL','title':'Cyber Security Intern',
        'date_found':'2026-10-22','url':f'https://jobs.audit.invalid/jobs/{identifier}'}
    rows=[record(90000111),record(90000112)]
    result=tw.write_records(profiles,'uk',rows,apply=True,tracker_override=str(path),backup_dir=str(tmp_path),cleanup_existing=False)
    assert result['applied'] and result['counts']['appended']==2
    repeat=record(90000112);repeat['url']='https://alternate.audit.invalid/jobs/90000112'
    result=tw.write_records(profiles,'uk',[repeat],apply=False,tracker_override=str(path),cleanup_existing=False)
    assert result['counts']['appended']==0 and result['counts']['duplicates']==1


def test_source_transport_failure_cannot_veto_verified_official_posting():
    policy=rjs.load_policy();scope=rjs.lane_scope('uk',rjs.load_schedules()['regions']['uk'])
    rec={'company':'Acme','title':'Cyber Security Intern','location':'London, United Kingdom',
         'url':'https://audit.invalid/jobs/1','fetch_state':'validation_failed',
         'resolved_url':'https://jobs.smartrecruiters.com/Acme/744000123456789-intern',
         'vacancy_status':{'state':'OPEN','verification_source':'https://api.smartrecruiters.com/v1/companies/Acme/postings/744000123456789'}}
    assert pipeline.deterministic_gates('uk',rec,policy,scope)['decision']=='accepted'
    rec['vacancy_status']={'state':'CLOSED'}
    assert pipeline.deterministic_gates('uk',rec,policy,scope)['decision']=='rejected'


def test_recommendation_expiry_does_not_close_target(monkeypatch):
    class Response:
        status=200;headers={'Content-Type':'text/html'}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def geturl(self):return 'https://audit.invalid/jobs/1'
        def read(self,n):return b'<html><title>Cyber Intern</title><a href="/apply">Apply now</a><aside class="related-jobs">This job has expired</aside></html>'
    monkeypatch.setattr(web,'_robots_allows',lambda *a:(True,'fixture'))
    monkeypatch.setattr(web.urllib.request,'urlopen',lambda *a,**k:Response())
    assert web.fetch_validate('https://audit.invalid/jobs/1')['status']==web.FETCH_VALIDATED_LIVE


@pytest.fixture
def fresh_manifest(monkeypatch,tmp_path):
    doc={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'run_id':'fixture-run',
         'records':[{'company':'Audit Fixture NOT REAL','title':'Cyber Intern','url':'https://audit.invalid/jobs/1'}]}
    monkeypatch.setattr(promotion,'read_manifest',lambda region:doc)
    monkeypatch.setattr(promotion,'read_manifest_run',lambda region:{'run_id':'fixture-run'})
    monkeypatch.setattr(promotion,'normalized_manifest',lambda *args:tmp_path/'never-written.json')
    return doc


def test_valid_json_writer_error_is_not_reported_applied(monkeypatch,fresh_manifest):
    monkeypatch.setattr(promotion.subprocess,'run',lambda *a,**k:types.SimpleNamespace(returncode=2,
        stdout=json.dumps({'applied':False,'error':'synthetic workbook lock','counts':{'appended':0}}),stderr=''))
    assert promotion.promote('uk',apply=True)['state']=='writer-failed'


@pytest.mark.parametrize('change',['stale','run-id'])
def test_stale_or_wrong_run_manifest_never_launches_writer(monkeypatch,fresh_manifest,change):
    if change=='stale':fresh_manifest['generated_at']='2020-01-01T00:00:00Z'
    else:fresh_manifest['run_id']='different-run'
    monkeypatch.setattr(promotion.subprocess,'run',lambda *a,**k:pytest.fail('must not launch writer'))
    assert promotion.promote('uk',apply=True)['state']=='manifest-refused'


def test_launcher_propagates_promotion_failure_and_stops_failed_scan():
    text=(Path(direct.HERE)/'run_scheduled_scan.cmd').read_text()
    assert 'if %RC% neq 0 exit /b %RC%' in text
    assert text.rstrip().endswith('exit /b %PRC%')


def test_direct_and_scheduled_paths_use_same_posting_resolver():
    import inspect
    assert 'PostingResolver' in inspect.getsource(direct.main)
    assert 'PostingResolver' in inspect.getsource(scheduled.run_region)


def test_same_requisition_collapses_across_hostnames_without_merging_distinct():
    left={'company':'Acme','title':'Cyber Intern','url':'https://one.audit.invalid/jobs/90000001'}
    same={**left,'url':'https://two.audit.invalid/jobs/90000001'}
    other={**left,'url':'https://two.audit.invalid/jobs/90000002'}
    assert pipeline.canonical_key(left)==pipeline.canonical_key(same)
    assert pipeline.canonical_key(left)!=pipeline.canonical_key(other)


def test_worker_uses_utf8_for_structured_unicode_events(monkeypatch):
    import subprocess
    captured={}
    events=[{'type':'item.completed','item':{'type':'web_search','query':'fixture'}},
        {'type':'item.completed','item':{'type':'agent_message','text':json.dumps([{'title':'IT Support Intern — London','url':'https://audit.invalid/jobs/1'}])}}]
    def run(*args,**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(returncode=0,stdout='\n'.join(json.dumps(e) for e in events),stderr='')
    monkeypatch.setattr(subprocess,'run',run)
    result=web.CodexWebSearchProvider()._run_one('fixture','fixture',limit=1,timeout=2)
    assert captured['encoding']=='utf-8' and captured['errors']=='replace'
    assert result['web_search_observed'] and len(result['results'])==1


def test_recommendation_mask_preserves_legitimate_deadline_sidebar():
    from application_links import mask_recommendations
    html='<main>Cyber Intern</main><aside>Application deadline: 10 December 2026</aside><aside>Similar jobs: this job has expired</aside>'
    result=mask_recommendations(html)
    assert '10 December 2026' in result and 'expired' not in result


def test_canonical_plan_reports_actual_duplicate_not_another_new_role(book_copy):
    profiles,path=book_copy;cfg=tw.region_config(profiles,'uk');tracker=tw.Tracker(path,cfg)
    row=next(r for r in tracker.data_rows() if 'intern' in str(r[2]).lower())
    tracker.wb.close()
    result=direct.canonical_plan('uk',path,[{'company':row[1],'title':row[2],'location':'London, United Kingdom',
        'url':'https://audit.invalid/alternative-application-form','deadline_info':{'type':'UNKNOWN'},'availability':{'state':'UNKNOWN'}}])
    assert result['counts']['appended']==0 and result['counts']['duplicates']==1


@pytest.mark.parametrize('vendor',['Ashby','Workable'])
@pytest.mark.parametrize('change',['valid','wrong-id','missing-description','not-published','ambiguous'])
def test_public_ats_feed_requires_exact_published_record(monkeypatch,vendor,change):
    import io
    import jd_fetcher
    if vendor=='Ashby':
        url='https://jobs.ashbyhq.com/audit/11111111-1111-1111-1111-111111111111'
        job={'jobUrl':url,'applyUrl':url+'/application','isListed':True,'title':'Cyber Intern',
             'descriptionPlain':'Cyber security internship in London.','location':'London, United Kingdom'}
        if change=='wrong-id':job['jobUrl']=url.replace('11111111','22222222')
        if change=='not-published':job['isListed']=False
        if change=='missing-description':job.pop('descriptionPlain')
    else:
        url='https://apply.workable.com/audit/j/ABC123/'
        job={'shortcode':'ABC123','state':'published','title':'Cyber Intern',
             'description':'Cyber security internship in London.','location':{'city':'London','country':'United Kingdom'}}
        if change=='wrong-id':job['shortcode']='DIFFERENT'
        if change=='not-published':job['state']='closed'
        if change=='missing-description':job.pop('description')
    jobs=[job,job] if change=='ambiguous' else [job]
    monkeypatch.setattr(jd_fetcher.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(json.dumps({'jobs':jobs}).encode()))
    result=jd_fetcher._active_ats_record(url,1)
    if change=='valid':
        assert result['vacancy_status']['state']=='OPEN'
        assert result['posting_identity']['location']=='London, United Kingdom'
    else:assert result is None


def test_it_administrator_is_supported_it_discipline():
    from title_policy import tier_a_signals
    assert tier_a_signals('IT Administrator Intern')['discipline_families']


def test_known_tracker_payload_never_enters_search_prompt():
    import inspect
    source=inspect.getsource(direct.main)
    assert 'known_tracker' not in source and 'existing_urls}' not in source


def test_semantic_attribution_is_provider_neutral():
    from funnel import Funnel
    f=Funnel()
    for key in ('discovered_raw','canonical_candidates','after_hard_negative_prefilter','semantically_reviewed','semantic_accept','deterministic_eligibility_pass','tracker_candidates'):f.set(key,1)
    f.set('deepseek_accept',0)
    doc=f.document()
    assert doc['zero_attribution']['first_zero_stage']!='deepseek_accept'


@pytest.mark.parametrize('provider',['codex','deepseek'])
def test_elapsed_budget_stops_new_model_dispatches(provider):
    import time
    import classifiers
    class Adapter:
        def check_health(self):return {'status':'healthy'}
        def get_identity(self):return {'observed_models':[]}
        def dispatch(self,*a,**k):pytest.fail('elapsed budget dispatched model request')
    records=[{'company':'Audit','title':'Cyber Intern','url':'https://audit.invalid/jobs/1'}]
    fn=classifiers.codex_bulk_classify if provider=='codex' else classifiers.deepseek_bulk_classify
    result=fn(records,adapter=Adapter(),deadline=time.time()-1)
    assert result['requests']==0 and not any(c['accepted'] for c in result['classifications'].values())
    assert 'budget exhausted' in result['limitation']


def test_blocked_candidate_retention_is_atomic_additive_and_private(monkeypatch,tmp_path):
    monkeypatch.setattr(direct,'SEARCH_STATE_DIR',tmp_path)
    def job(i):return {'company':'Fixture','title':'Cyber Intern','location':'London, United Kingdom',
        'url':f'https://audit.invalid/jobs/{i}','deadline_info':{'type':'UNKNOWN'},'availability':{'state':'UNKNOWN'}}
    path=direct.retain_candidates('uk',[job(1)],'fixture locked workbook')
    direct.retain_candidates('uk',[job(2)],'fixture locked workbook')
    direct.retain_candidates('uk',[job(1)],'fixture locked workbook')
    doc=json.loads(path.read_text())
    assert len(doc['records'])==2 and doc['requires_fresh_verification'] is True
    assert not list(tmp_path.glob('*.tmp'))


def test_same_requisition_changed_title_in_manifest_still_dedupes(book_copy):
    profiles,path=book_copy
    first={'company':'Audit Fixture','title':'Cyber Intern','url':'https://one.audit.invalid/jobs/90000999'}
    second={**first,'title':'Cybersecurity Internship','url':'https://two.audit.invalid/jobs/90000999'}
    result=tw.write_records(profiles,'uk',[first,second],apply=False,tracker_override=str(path),cleanup_existing=False)
    assert result['counts']['appended']==1
    assert result['outcomes'][1]['decision']=='duplicate-in-manifest'



def test_worker_parser_preserves_all_result_arrays():
    rows,error=web._parse_json_array('[{"title":"One","url":"https://a.invalid/1"}]\n[{"title":"Two","url":"https://b.invalid/2"}]')
    assert error is None and len(rows)==2


def test_zero_duplicates_is_not_a_failed_funnel():
    from funnel import Funnel
    f=Funnel()
    for key in ('discovered_raw','after_hard_negative_prefilter','semantically_reviewed','semantic_accept','deterministic_eligibility_pass','tracker_candidates'):f.set(key,1)
    assert f.document()['zero_attribution']['first_zero_stage'] is None


def test_verified_deadline_and_destination_survive_manifest_boundary(monkeypatch,book_copy):
    profiles,path=book_copy;profiles['regions']['uk']['tracker']=str(path)
    monkeypatch.setattr(tw,'load_profiles',lambda *a,**k:profiles)
    deadline={'type':'EXACT','date':'2099-12-31','source':'JD','evidence':'Applications close on 31 December 2099'}
    target='https://official.audit.invalid/jobs/90000888'
    monkeypatch.setattr(pipeline,'fetch_jd',lambda *a,**k:{'text':'Cyber security internship in London.','vacancy_status':{'state':'OPEN','evidence':'exact published ATS posting'},'deadline_info':deadline,'resolved_url':target})
    rec={'company':'Audit Fixture','title':'Cyber Security Intern','location':'London, United Kingdom','url':'https://lead.audit.invalid/jobs/90000888'}
    doc=pipeline.run_funnel([rec],region='uk',mode='high_recall',semantic='off',deepseek_model='unused',batch_size=8,codex_budget=0,codex_enabled=False,timeout=1,run_id='fixture-metadata')
    canonical=doc['canonical_candidates'][0]
    rebuilt=rjs.build_record('uk',canonical,rjs.load_policy(),'fixture-metadata',{})
    assert rebuilt['deadline_info']==deadline and rebuilt['availability']['state']=='OPEN'
    assert rebuilt['url']==target


def test_old_newsletter_sources_are_not_counted_as_fresh(tmp_path):
    import gmail_discovery
    from career_job_mail import save
    save(tmp_path/'jobs.json',[{'job_id':'old','url':'https://audit.invalid/jobs/1','received_at':'2020-01-01T00:00:00Z','title':'Cyber Intern'}])
    args=types.SimpleNamespace(no_live=True,no_validate=True)
    rec=gmail_discovery.collect('uk',args,root=tmp_path)['block']['candidates'][0]
    assert rec['historical_seed'] and rec['source_generated_at']=='2020-01-01T00:00:00Z'


@pytest.mark.parametrize('url',[
    'https://job-boards.greenhouse.io/knowbe4','https://jobs.ashbyhq.com/example',
    'https://audit.wd1.myworkdayjobs.com/en-US/Careers',
    'https://apply.workable.com/example/','https://uk.whatjobs.com/company/pa-consulting/jobs',
    'https://www.brightnetwork.co.uk/internships/cyber-security/'])
def test_live_observed_board_homepages_never_become_application_rows(url):
    assert tw.listing_page_reason(url)


@pytest.mark.parametrize('company',['','Unknown','targetjobs UK'])
def test_live_observed_unresolved_employers_remain_review_only(company,book_copy):
    profiles,path=book_copy;scope=rjs.lane_scope('uk',rjs.load_schedules()['regions']['uk'])
    rec={'company':company,'title':'Cyber Intern','location':'London, United Kingdom','url':'https://audit.invalid/jobs/90000777'}
    assert pipeline.deterministic_gates('uk',rec,rjs.load_policy(),scope)['decision']=='rejected'
    result=tw.write_records(profiles,'uk',[rec],apply=False,tracker_override=str(path),cleanup_existing=False)
    assert result['counts']['appended']==0 and result['outcomes'][0]['decision']=='rejected'


def test_observed_search_without_final_response_is_a_failure(monkeypatch):
    import subprocess
    events=[{'type':'item.completed','item':{'type':'web_search','query':'fixture'}}]
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:types.SimpleNamespace(returncode=0,stdout='\n'.join(json.dumps(e) for e in events),stderr=''))
    result=web.CodexWebSearchProvider()._run_one('fixture','fixture',limit=1,timeout=1)
    assert result['web_search_observed'] and 'response missing' in result['error']


@pytest.mark.parametrize('preserve',[True,False])
def test_cli_forwards_explicit_existing_row_preservation(monkeypatch,tmp_path,preserve):
    import career_ops_cli as cli
    monkeypatch.setattr(cli,'load_profiles',lambda *a:{})
    monkeypatch.setattr(cli,'_load_manifest',lambda *a:[])
    monkeypatch.setattr(cli.dept_run_health,'record_run',lambda *a,**k:None)
    seen={}
    def writer(*a,**k):
        seen.update(k)
        return {'tracker':str(tmp_path/'fixture.xlsx'),'applied':False,'counts':{}}
    monkeypatch.setattr(tw,'write_records',writer)
    args=types.SimpleNamespace(profiles=None,manifest='fixture',region='uk',apply=False,backup_dir=None,
        update_existing=False,archive_dir=None,tracker=None,preserve_existing_rows=preserve)
    assert cli.cmd_write(args)==0
    assert seen['cleanup_existing'] is (not preserve)


def test_direct_worker_retains_observed_query_evidence(monkeypatch):
    class Provider:
        def __init__(self,**kwargs):pass
        def resolve(self):return 'fixture'
        def _run_one(self,*a,**k):return {'web_search_observed':True,'executed_queries':['actual public query'],
            'results':[],'raw_events':2,'elapsed_s':1}
    monkeypatch.setattr(web,'CodexWebSearchProvider',Provider)
    result=direct.run_codex('fixture')
    assert str(result)=='[]' and result.evidence['executed_queries']==['actual public query']
