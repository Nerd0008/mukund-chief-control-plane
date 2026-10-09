import json,pathlib,sys,types
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'discovery')]
import gmail_discovery as gd
from career_job_mail import save

def page(company='Acme',location='London',title='Graduate Security Analyst'):
    return '<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','title':title,'hiringOrganization':{'name':company},'jobLocation':{'address':{'addressLocality':location,'addressCountry':'GB'}},'description':'Graduate cyber security SOC analyst; no experience required.'})+'</script>'

def test_structured_posting_evidence_required():
    assert gd.posting('<title>Graduate Security Analyst</title>') is None
    assert gd.posting(page())['company']=='Acme'
    assert gd.posting(page().replace('"London"','null').replace('"GB"','null')) is None

def test_expired_posting_refused():
    p=page().replace('"@type": "JobPosting"','"@type": "JobPosting", "validThrough": "2020-01-01T00:00:00Z"')
    assert gd.posting(p) is None

def test_bounded_cached_collection_and_no_live_does_not_fetch(tmp_path):
    save(tmp_path/'jobs.json',[{'job_id':'a','url':'https://example.test/jobs/1','title':'Security Analyst'},{'job_id':'b','url':'https://example.test/jobs/2','title':'Engineer'}])
    args=types.SimpleNamespace(no_live=False,no_validate=False,max_urls=1,budget_seconds=10)
    calls=[]
    def fetch(url,timeout):calls.append(url);return page()
    lane=gd.collect('uk',args,root=tmp_path,fetcher=fetch)
    assert len(calls)==1 and lane['block']['coverage']['verified_postings']==1
    assert lane['block']['candidates'][1]['fetch_state']=='discovered_unverified'
    args.no_live=True
    gd.collect('uk',args,root=tmp_path,fetcher=lambda *a,**kw:pytest.fail('offline must not fetch'))

def test_unknown_or_blocked_never_claimed_verified(tmp_path):
    save(tmp_path/'jobs.json',[{'job_id':'a','url':'https://example.test/jobs/1','title':'Security Analyst'}])
    args=types.SimpleNamespace(no_live=False,no_validate=False,max_urls=1,budget_seconds=10)
    result=gd.collect('uk',args,root=tmp_path,fetcher=lambda *a,**kw:'<html>Blocked</html>')
    assert result['block']['candidates'][0]['fetch_state']=='discovered_unverified'

@pytest.mark.parametrize('url',['file:///etc/passwd','http://127.0.0.1/jobs/1','http://localhost/jobs/1','https://example.test:1234/jobs/1'])
def test_mail_link_cannot_fetch_private_services(url):
    with pytest.raises((ValueError,OSError)):gd.public_url(url)

def test_daily_orchestrator_includes_newsletter_lane():
    import scheduled_orchestrator as so
    import inspect
    assert '("gmail_job_alerts", ingest_gmail_alerts)' in inspect.getsource(so.run_region)
