import base64,pathlib,sys,json
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from career_job_mail import extract,merge,safe_url,compile_list
from career_google_clients import GmailReader

def message(html,subject='New jobs newsletter',mid='m1'):
    return {'id':mid,'threadId':'t1','internalDate':'1791500000000','payload':{'mimeType':'text/html','headers':[{'name':'Subject','value':subject}], 'body':{'data':base64.urlsafe_b64encode(html.encode()).decode()}}}

def test_extract_multiple_job_links_not_unsubscribe():
    jobs=extract(message('<a href="https://company.test/jobs/123?utm_source=email">Graduate Security Analyst</a><a href="https://company.test/jobs/456">IT Support Engineer</a><a href="https://company.test/unsubscribe?token=secret">Unsubscribe</a>'))
    assert len(jobs)==2 and jobs[0]['title']=='Graduate Security Analyst'
    assert all(j['needs_review'] and j['validation']=='discovered_unverified' for j in jobs)
    assert 'secret' not in json.dumps(jobs) and 'utm_source' not in json.dumps(jobs)

def test_duplicate_alert_and_repeat_scan_idempotent(tmp_path):
    messages=[message('<a href="https://company.test/jobs/123">Security Analyst</a>'),message('<a href="https://company.test/jobs/123?utm=x">Security Analyst</a>',mid='m2')]
    counts=compile_list(messages,tmp_path)
    assert counts['job_list_total']==1 and counts['duplicates_collapsed']==1
    assert compile_list(messages,tmp_path)['job_list_total']==1
    assert len(json.loads((tmp_path/'jobs.json').read_text())[0]['source_message_ids'])==2

def test_unknown_title_not_fabricated():
    jobs=extract(message('<a href="https://company.test/jobs/123">Apply now</a>'))
    assert jobs[0]['title'] is None and jobs[0]['company'] is None

def test_generic_newsletter_no_jobs():
    assert extract(message('<a href="https://company.test/about">About us</a>'))==[]

@pytest.mark.parametrize('url',['javascript:alert(1)','https://user:password@company.test/jobs/1','https://company.test/privacy'])
def test_unsafe_links_rejected(url):assert safe_url(url) is None

def test_signed_params_removed_public_job_id_preserved():
    assert safe_url('https://company.test/jobs?jobId=123&token=secret&utm_source=mail')=='https://company.test/jobs?jobId=123'

def test_tracking_redirect_not_followed():
    assert extract(message('<a href="https://mail.test/click?url=https://company.test/jobs/1">Security Engineer</a>'))==[]

def test_reader_scoped_query_get_only():
    calls=[]
    def transport(method,url,**kw):
        calls.append((method,url));return {'historyId':'123'} if '/profile' in url else {}
    result=GmailReader('fake',transport,request_interval=0).read_window(query='subject:newsletter',max_messages=10)
    assert all(m=='GET' for m,u in calls) and 'subject%3Anewsletter' in calls[1][1]
    assert result['gmail_mutations']==0

def test_manifest_does_not_write_tracker_or_calendar(tmp_path):
    compile_list([message('<a href="https://company.test/jobs/1">Graduate Engineer</a>')],tmp_path)
    assert {p.name for p in tmp_path.iterdir()}=={'jobs.json','job-list.md','summary.json'}
