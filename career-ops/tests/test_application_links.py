import datetime as dt
import json
from pathlib import Path
import sys
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import application_links as links
import jd_fetcher as jd
import job_liveness as live

SOURCE='https://www.jointheintake.com/graduate-schemes/example-cyber-intern-2027-123'
TARGET='https://careers.example.com/jobs/cyber-intern-2027'
TITLE='Cyber Security Intern 2027'


def source(target=TARGET):
    return f'<h1>{TITLE}</h1><a href="{target}"><span>Apply on Example’s site</span></a>'


def destination(title=TITLE, extra=''):
    return f'<h1>{title}</h1><p>Example opportunities</p>{extra}<a href="/jobs/cyber-intern-2027/apply">Apply Now</a>'


def transport(monkeypatch, pages):
    calls=[]
    class Response:
        status=200
        class Headers:
            def get_content_charset(self):return 'utf-8'
        headers=Headers()
        def __init__(self,url,body):self.url=url;self.body=body
        def geturl(self):return self.url
        def read(self,*a):return self.body.encode() if isinstance(self.body,str) else json.dumps(self.body).encode()
        def __enter__(self):return self
        def __exit__(self,*a):pass
    def fetch(req,timeout=None):
        assert req.get_method()=='GET'
        assert timeout>0
        url=req.full_url;calls.append(url)
        if url not in pages:pytest.fail('Unexpected network request: '+url)
        body=pages[url]
        if isinstance(body,Exception):raise body
        if isinstance(body,tuple):return Response(*body)
        return Response(url,body)
    monkeypatch.setattr(jd.urllib.request,'urlopen',fetch)
    return calls


@pytest.mark.parametrize('label',['Apply for job','Apply now','Apply online now','Apply for this role','Apply on Example’s site'])
def test_apply_labels_and_nested_multiline_markup(label):
    p=links.extract(f'<h1>{TITLE}</h1><a href="{TARGET}">\n<span>{label}</span>\n</a>',SOURCE)
    assert p['links']==[{'url':TARGET,'label':label}]


def test_aggregator_link_is_discovery_not_open_evidence():
    assert live.assess(source(),TITLE,{},SOURCE)['state']=='UNKNOWN'


def test_original_employer_resolved_with_provenance(monkeypatch):
    calls=transport(monkeypatch,{SOURCE:source(),TARGET:destination()})
    result=jd.fetch_jd(SOURCE,timeout=5)
    assert result['vacancy_status']['state']=='OPEN'
    assert result['resolved_url']==TARGET
    assert result['application_url']==TARGET+'/apply'
    assert result['url']==SOURCE
    assert result['application_resolution']['employer']=='Example'
    assert calls==[SOURCE,TARGET]


@pytest.mark.parametrize('html',[destination('Cyber Security Intern 2026'),destination('Senior Security Architect'),destination(extra='<p>This job has expired.</p>')])
def test_wrong_year_wrong_role_and_expired_target_cannot_authorize(monkeypatch,html):
    transport(monkeypatch,{SOURCE:source(),TARGET:html})
    result=jd.fetch_jd(SOURCE,timeout=5)
    assert result['vacancy_status']['state']!='OPEN'
    assert not result.get('resolved_url')


def test_wrong_employer_even_with_identical_title_withheld(monkeypatch):
    wrong='https://careers.other.com/jobs/123'
    transport(monkeypatch,{SOURCE:source(wrong),wrong:destination().replace('Example','Other')})
    result=jd.fetch_jd(SOURCE,timeout=5)
    assert result['vacancy_status']['state']=='UNKNOWN'
    assert result['application_resolution']['employer_match'] is False


def test_source_company_misassociation_cannot_authorize_tracker():
    result={'vacancy_status':{'state':'OPEN','page_title':TITLE},'resolved_url':TARGET,
            'application_resolution':{'employer':'Example','title_match':True,'employer_match':True,'state':'OPEN'}}
    assert live.record_verification({'company':'Wrong Company','title':TITLE,'url':SOURCE},result)['state']=='UNKNOWN'


def test_category_page_never_resolves_recommendation(monkeypatch):
    url='https://www.brightnetwork.co.uk/internships/cyber-security/'
    calls=transport(monkeypatch,{url:source()})
    result=jd.fetch_jd(url,timeout=5)
    assert result['vacancy_status']['state']=='UNKNOWN'
    assert 'category' in result['vacancy_status']['evidence']
    assert calls==[url]


def test_multiple_destinations_not_arbitrarily_selected(monkeypatch):
    html=source()+f'<a href="https://other.com/jobs/2">Apply Now</a>'
    calls=transport(monkeypatch,{SOURCE:html})
    assert jd.fetch_jd(SOURCE,timeout=5)['vacancy_status']['state']=='UNKNOWN'
    assert calls==[SOURCE]


def test_duplicate_buttons_same_route_are_not_ambiguous():
    assert len(links.extract(source()+source(),SOURCE)['links'])==1


def test_navigation_and_related_jobs_do_not_supply_application_route():
    html=f'<h1>{TITLE}</h1><nav><a href="/apply">Apply Now</a></nav><section class="related-jobs"><a href="/another-job/apply">Apply Now</a></section>'
    assert links.extract(html,TARGET)['links']==[]


@pytest.mark.parametrize('url',['javascript:alert(1)','mailto:jobs@example.com','http://127.0.0.1/a','http://localhost/a','https://u:p@example.com/a','#Apply'])
def test_nonpublic_and_nonhttp_routes_are_not_followed(url):
    assert links.public_url(url,TARGET) is None


def test_closed_source_not_resurrected_by_outbound(monkeypatch):
    calls=transport(monkeypatch,{SOURCE:source()+'<p>Applications closed</p>'})
    assert jd.fetch_jd(SOURCE,timeout=5)['vacancy_status']['state']=='CLOSED'
    assert calls==[SOURCE]


def test_http_redirect_final_url_is_used(monkeypatch):
    final='https://careers.example.com/jobs/new-slug'
    transport(monkeypatch,{SOURCE:source(),TARGET:(final,destination())})
    assert jd.fetch_jd(SOURCE,timeout=5)['resolved_url']==final


def test_cycle_is_bounded_and_not_open(monkeypatch):
    calls=transport(monkeypatch,{SOURCE:source(),TARGET:destination().replace('/jobs/cyber-intern-2027/apply',SOURCE)})
    assert jd.fetch_jd(SOURCE,timeout=5)['vacancy_status']['state']=='UNKNOWN'
    assert calls==[SOURCE,TARGET]


def test_http_bot_wall_stays_unknown_with_found_link(monkeypatch):
    calls=transport(monkeypatch,{SOURCE:source(),TARGET:urllib.error.HTTPError(TARGET,403,'Forbidden',None,None)})
    result=jd.fetch_jd(SOURCE,timeout=5)
    assert result['vacancy_status']['state']=='UNKNOWN'
    assert result['application_resolution']['outbound_url']==TARGET
    assert calls==[SOURCE,TARGET]


def test_workday_exact_requisition_get_not_application_post(monkeypatch):
    url='https://example.wd3.myworkdayjobs.com/External/job/London/Cyber-Intern_JR-123'
    endpoint='https://example.wd3.myworkdayjobs.com/wday/cxs/example/External/job/London/Cyber-Intern_JR-123'
    api={'jobPostingInfo':{'jobReqId':'JR-123','title':TITLE,'posted':True,'canApply':True,'jobDescription':'Cyber internship','endDate':'2099-11-01'}}
    calls=transport(monkeypatch,{url:'<title>Workday</title>',endpoint:api})
    result=jd.fetch_jd(url,timeout=5)
    assert result['vacancy_status']['state']=='OPEN'
    assert result['deadline']=='2099-11-01'
    assert calls==[url,endpoint]
    api['jobPostingInfo']['jobReqId']='JR-999'
    assert jd.fetch_jd(url,timeout=5)['vacancy_status']['state']=='UNKNOWN'
    api['jobPostingInfo']['jobReqId']='JR-123';api['jobPostingInfo']['canApply']=False
    assert jd.fetch_jd(url,timeout=5)['vacancy_status']['state']=='UNKNOWN'


def test_exact_employer_fragment_form_is_read_never_posted(monkeypatch):
    frame='https://careers.example.com/pages/123/blocks/456?job_uid=job123'
    posting={'@type':'JobPosting','title':TITLE,'identifier':{'value':'job123'}}
    html=f'<h1>{TITLE}</h1><div data-call-to-action--form-kind-value="apply_url"><turbo-frame src="{frame}"></turbo-frame></div><script type="application/ld+json">{json.dumps(posting)}</script>'
    fragment='<form method="post" action="/call_to_actions/123/form_submissions?job_id=job123"></form>'
    calls=transport(monkeypatch,{TARGET:html,frame:fragment})
    result=jd.fetch_jd(TARGET,timeout=5)
    assert result['vacancy_status']['state']=='OPEN'
    assert result['resolved_url']==TARGET
    assert calls==[TARGET,frame]
    assert not links.fragment_route(links.extract(html,TARGET),fragment.replace('job123','wrong'),TARGET,frame)


def test_jsonld_description_retained_for_clearance_gate(monkeypatch):
    posting={'@type':'JobPosting','title':TITLE,'description':'<p>SC clearance required</p>'}
    html=destination()+f'<script type="application/ld+json">{json.dumps(posting)}</script>'
    transport(monkeypatch,{TARGET:html})
    result=jd.fetch_jd(TARGET,timeout=5)
    assert 'SC clearance required' in result['text']


def test_digest_uses_fresh_verified_original_destination(monkeypatch):
    import daily_jobs_links as digest
    rec={'company':'Example','title':TITLE,'url':SOURCE,'date':dt.date.today(),'id':'','status':'Not Applied'}
    live.record_verification(rec,{'vacancy_status':{'state':'OPEN','page_title':TITLE},'resolved_url':TARGET})
    monkeypatch.setattr(digest,'tracker_rows',lambda region:([dict(rec)],None))
    monkeypatch.setattr(digest,'latest_run_doc',lambda region:(None,None))
    text,_=digest.build_digest(26,12000,10)
    assert TARGET in text and SOURCE not in text


@pytest.mark.parametrize('already_tracked',[True,False])
def test_direct_search_dedupes_and_carries_resolved_destination(monkeypatch,tmp_path,capsys,already_tracked):
    import codex_entry_level_search as search
    from career_search_recall import posting_key
    p=tmp_path/'tracker';p.touch();monkeypatch.setitem(search.TRACKERS,'uk',p)
    class Book:
        def close(self):pass
    monkeypatch.setattr(search,'read_tracker_urls',lambda p:({posting_key(TARGET)} if already_tracked else set(),None,Book(),{},2,None))
    monkeypatch.setattr(search,'_profile_terms',lambda:(search.ENTRY_MARKERS,(),None))
    monkeypatch.setattr(search,'run_codex',lambda *a,**k:json.dumps([{'company':'Example','title':TITLE,'url':SOURCE}]))
    monkeypatch.setattr(search,'fetch_jd',lambda url:{'vacancy_status':{'state':'OPEN','page_title':TITLE},'resolved_url':TARGET})
    monkeypatch.setattr(sys,'argv',['search','--batches','1','--dry-run'])
    assert search.main()==0
    report=json.loads(next(x.split(' ',1)[1] for x in capsys.readouterr().out.splitlines() if x.startswith('SEARCH_RECONCILIATION ')))
    assert report['counts']['already_tracked']==int(already_tracked)
    assert report['counts']['new_candidates']==int(not already_tracked)
    assert any(x.get('url')==TARGET for x in report['decisions'])


def test_regional_writer_uses_resolved_url_without_rewriting_source_identity():
    import regional_job_search as rjs
    candidate={'company':'Example','title':TITLE,'location':'London','url':SOURCE,'resolved_url':TARGET}
    record=rjs.build_record('uk',candidate,rjs.load_policy(),'test',{})
    assert record['url']==TARGET and candidate['url']==SOURCE


def test_external_route_cannot_be_open_at_hop_limit(monkeypatch):
    transport(monkeypatch,{TARGET:destination().replace('/jobs/cyber-intern-2027/apply','https://external.example.com/jobs/123')})
    result=jd.fetch_jd(TARGET,timeout=5,_depth=2)
    assert result['vacancy_status']['state']=='UNKNOWN'
    assert not result.get('resolved_url')


def test_no_new_request_after_elapsed_budget_is_spent(monkeypatch):
    calls=transport(monkeypatch,{SOURCE:source()})
    ticks=iter([0,10,11,12])
    monkeypatch.setattr(jd.time,'monotonic',lambda:next(ticks))
    assert jd.fetch_jd(SOURCE,timeout=1)['vacancy_status']['state']=='UNKNOWN'
    assert calls==[SOURCE]


def test_discovery_stale_transport_requires_positive_resolved_identity():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'discovery'))
    import pipeline
    import regional_job_search as rjs
    rec={'company':'Example','title':'Cyber Security Intern','location':'London, United Kingdom',
         'url':SOURCE,'fetch_state':'discovered_unverified','jd_text':'Cyber internship in London',
         'vacancy_status':{'state':'OPEN'}}
    policy=rjs.load_policy();scope=rjs.lane_scope('uk',rjs.load_schedules()['regions']['uk'])
    verdict=lambda:pipeline.deterministic_gates('uk',rec,policy,scope)
    assert verdict()['decision']=='rejected'
    rec['resolved_url']=TARGET
    rec['vacancy_status']['application_resolution']={'title_match':True,'employer_match':True,'state':'OPEN'}
    assert verdict()['decision']=='accepted'
    rec['vacancy_status']['application_resolution']['employer_match']=False
    assert verdict()['decision']=='rejected'
