import json
import types
import datetime as dt
import pytest
import application_links as links
from posting_resolution import PostingResolver


def source():
    return {'company':'Acme','title':'Cyber Security Intern 2027',
            'location':'London, United Kingdom','url':'https://www.linkedin.com/comm/jobs/view/123'}


def active(**identity):
    return {'vacancy_status':{'state':'OPEN','page_title':'Cyber Security Intern 2027'},
            'posting_identity':{'company':'Acme','title':'Cyber Security Intern 2027',
                                'location':'London, United Kingdom',**identity},
            'text':'Verified full job description', 'resolved_url':'https://jobs.acme.test/jobs/123'}


class Provider:
    def __init__(self, observed=True, urls=None):
        self.calls=0;self.observed=observed
        self.urls=urls or ['https://jobs.acme.test/jobs/123']
    def research(self, queries, **kwargs):
        self.calls+=1
        return {'queries':[{'web_search_observed':self.observed,
                            'results':[{'url':u} for u in self.urls]}]}


def test_email_link_uses_public_exact_job_id():
    for url in ['https://www.linkedin.com/comm/jobs/view/123?tracking=x',
                'https://uk.linkedin.com/jobs/view/cyber-intern-123']:
        assert links.canonical_posting_url(url)=='https://www.linkedin.com/jobs/view/123'
    assert links.canonical_posting_url('https://evil.test/comm/jobs/view/123').startswith('https://evil.test/')


def test_top_card_identity_does_not_claim_availability():
    html='''<h1>Cyber Security Intern 2027</h1><a class="topcard__org-name-link">Acme</a>
    <span class="topcard__flavor topcard__flavor--bullet">London, United Kingdom</span>'''
    identity=links.page_identity(html,'https://www.linkedin.com/jobs/view/123')
    assert identity=={k:v for k,v in source().items() if k!='url'}
    from job_liveness import assess
    assert assess(html,'A real JD',{},'https://www.linkedin.com/jobs/view/123')['state']=='UNKNOWN'
    assert links.page_identity('<h1>Sign in</h1>',source()['url']) is None


def test_get_application_route_is_discovered_but_post_is_not_executed():
    page=links.extract('<h1>Cyber Intern</h1><form method="GET" action="/jobs/123/apply"></form>'
                       '<form method="POST" action="/jobs/123/submit"></form>','https://acme.test/jobs/123')
    assert page['links']==[{'url':'https://acme.test/jobs/123/apply','label':'Apply'}]


def test_known_search_title_wrapper_does_not_reject_exact_employer_title():
    assert links.title_matches('United Kingdom National Nuclear Laboratory Jobs - Graduate Scheme 2027 - Information Security',
                               'Graduate Scheme 2027 - Information Security')
    assert not links.title_matches('Acme Jobs - Cyber Intern 2026','Cyber Intern 2027')


def test_search_is_not_evidence_without_observed_search():
    resolver=PostingResolver(Provider(observed=False),fetcher=lambda *a,**k:pytest.fail('must not fetch unobserved results'))
    assert resolver(source(),{}) is None


def test_verified_employer_route_and_same_input_cached():
    provider=Provider();calls=[]
    def fetch(url,**kwargs):calls.append(url);return active()
    resolver=PostingResolver(provider,fetcher=fetch)
    result=resolver(source(),{})
    assert result['resolved_url']=='https://jobs.acme.test/jobs/123'
    assert result['application_resolution']['employer_match']
    assert resolver(source(),{})==result
    assert provider.calls==1 and len(calls)==1


@pytest.mark.parametrize('change',[{'company':'Other'},{'title':'Cyber Security Intern 2026'},
                                  {'location':'Paris, France'}])
def test_wrong_employer_intake_or_location_never_resolves(change):
    assert PostingResolver(Provider(),fetcher=lambda *a,**k:active(**change))(source(),{}) is None


def test_multiple_requisitions_are_ambiguous_not_arbitrarily_selected():
    def fetch(url,**kwargs):return {**active(),'resolved_url':url}
    resolver=PostingResolver(Provider(urls=['https://acme.test/jobs/123','https://acme.test/jobs/456']),fetcher=fetch)
    assert resolver(source(),{}) is None
    assert resolver.evidence[0]['distinct_matches']==2


def test_closed_destination_cannot_be_promoted_to_open():
    resolver=PostingResolver(Provider(),fetcher=lambda *a,**k:{**active(),'vacancy_status':{'state':'CLOSED'}})
    assert resolver(source(),{}) is None


def test_query_budget_and_wall_clock_prevent_more_search():
    provider=Provider();resolver=PostingResolver(provider,max_queries=0)
    assert resolver(source(),{}) is None and provider.calls==0
    resolver=PostingResolver(provider,deadline=0)
    assert resolver(source(),{}) is None and provider.calls==0


def test_newsletter_unchecked_links_are_not_starved_by_yesterday_cache(tmp_path):
    import gmail_discovery as gd
    from career_job_mail import save
    jobs=[{'job_id':str(i),'url':f'https://acme.test/jobs/{i}','title':'Cyber Intern'} for i in (1,2)]
    save(tmp_path/'jobs.json',jobs)
    yesterday=(dt.date.today()-dt.timedelta(days=1)).isoformat()
    save(tmp_path/'validated-postings.json',{'1':{'checked_day':yesterday,'posting':None}})
    calls=[]
    gd.collect('uk',types.SimpleNamespace(max_urls=1,budget_seconds=10,no_live=False,no_validate=False),root=tmp_path,
               fetcher=lambda url,**kwargs:calls.append(url) or '<h1>Unknown</h1>')
    assert calls==['https://acme.test/jobs/2']


def test_fetcher_never_requests_notification_login_route(monkeypatch):
    import jd_fetcher as fetcher
    class Response:
        status=200
        headers=types.SimpleNamespace(get_content_charset=lambda:'utf-8')
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def geturl(self):return 'https://www.linkedin.com/jobs/view/123'
        def read(self,n):return b'<h1>Cyber Intern</h1>'
    calls=[]
    monkeypatch.setattr(fetcher.urllib.request,'urlopen',lambda req,**kwargs:calls.append(req.full_url) or Response())
    result=fetcher.fetch_jd(source()['url'])
    assert calls==['https://www.linkedin.com/jobs/view/123']
    assert result['retrieval_url']==calls[0]


def test_copied_company_metadata_on_a_job_board_is_not_official_evidence():
    provider=Provider(urls=['https://www.drjobpro.com/jobs/123'])
    resolver=PostingResolver(provider,fetcher=lambda *a,**k:pytest.fail('third party must not be probed as official'))
    assert resolver(source(),{}) is None


def test_recovery_progress_survives_next_run_without_repeating_failed_head(tmp_path):
    path=tmp_path/'recovery.json'
    provider=Provider(observed=False)
    first=PostingResolver(provider,state_path=path)
    assert first(source(),{}) is None and provider.calls==1
    second=PostingResolver(provider,state_path=path)
    assert second(source(),{}) is None and provider.calls==1
    assert second.priority({**source(),'url':'https://acme.test/never-attempted'}) < second.priority(source())


def test_provider_failure_stays_bounded_and_does_not_crash_scan():
    class Broken:
        def research(self,*args,**kwargs):raise TimeoutError('synthetic transport failure')
    resolver=PostingResolver(Broken())
    assert resolver(source(),{}) is None
    assert resolver.evidence[0]['failure_type']=='TimeoutError'


def test_explicit_title_location_suffix_is_used_without_guessing():
    result=PostingResolver(Provider(),fetcher=lambda *a,**k:active())(
        {**source(),'title':'Cyber Security Intern 2027 in London, United Kingdom','location':None},{})
    assert result is not None


@pytest.mark.parametrize('title',['Senior Cyber Security Intern 2027','Cyber Security Graduate 2027'])
def test_same_company_title_overlap_cannot_change_seniority_or_programme(title):
    resolver=PostingResolver(Provider(),fetcher=lambda *a,**k:active(title=title))
    assert resolver(source(),{}) is None


def test_newest_unchecked_newsletter_lead_gets_budget_first(tmp_path):
    import gmail_discovery as gd
    from career_job_mail import save
    save(tmp_path/'jobs.json',[{'job_id':str(i),'title':'Cyber Intern','url':f'https://acme.test/jobs/{i}',
        'received_at':date} for i,date in ((1,'2026-10-01T09:00:00+00:00'),(2,'2026-10-22T09:00:00+00:00'))])
    calls=[]
    gd.collect('uk',types.SimpleNamespace(max_urls=1,budget_seconds=10,no_live=False,no_validate=False),root=tmp_path,
               fetcher=lambda url,**kwargs:calls.append(url) or '<h1>Unknown</h1>')
    assert calls==['https://acme.test/jobs/2']
