import ssl,urllib.error
from pathlib import Path
import pytest
import jd_fetcher as jd
import clearance_screening as cs
import regional_job_search as regional
from pipeline import deterministic_gates

URL='https://employer.example/job/123'


def test_certificate_retry_keeps_hostname_and_ca_verification(monkeypatch):
    calls=[];sentinel=object()
    def open(request,**kw):
        calls.append(kw)
        if len(calls)==1:raise urllib.error.URLError(ssl.SSLCertVerificationError(1,'issuer missing'))
        assert kw['context'].verify_mode==ssl.CERT_REQUIRED
        assert kw['context'].check_hostname is True
        assert 0<kw['timeout']<=3
        return sentinel
    monkeypatch.setattr(jd.urllib.request,'urlopen',open)
    assert jd._verified_open(URL,3) is sentinel
    assert len(calls)==2

@pytest.mark.parametrize('error',[urllib.error.URLError('offline'),urllib.error.HTTPError(URL,403,'Forbidden',{},None),
 urllib.error.HTTPError(URL,429,'Limit',{},None)])
def test_non_certificate_errors_are_not_retried(monkeypatch,error):
    calls=[]
    def fail(*a,**k):calls.append(1);raise error
    monkeypatch.setattr(jd.urllib.request,'urlopen',fail)
    with pytest.raises(urllib.error.URLError) as caught:jd._verified_open(URL,3)
    assert caught.value is error and calls==[1]


def test_untrusted_certificate_still_fails_after_bounded_retry(monkeypatch):
    calls=[]
    def fail(*a,**k):calls.append(1);raise urllib.error.URLError(ssl.SSLCertVerificationError(1,'untrusted'))
    monkeypatch.setattr(jd.urllib.request,'urlopen',fail)
    with pytest.raises(urllib.error.URLError):jd._verified_open(URL,3)
    assert len(calls)==2

@pytest.mark.parametrize('text',['','   ','\ufffd'*100])
def test_missing_or_garbled_jd_cannot_pass_unknown_availability(text):
    rec={'company':'Example','title':'Cyber Security Intern','location':'London, United Kingdom','url':URL,
         'jd_text':text,'jd_screening_required':True,'vacancy_status':{'state':'UNKNOWN'}}
    scope=regional.lane_scope('uk',regional.load_schedules()['regions']['uk'])
    result=deterministic_gates('uk',rec,regional.load_policy(),scope)
    assert result['decision']=='rejected'
    assert any('eligibility UNSCREENED' in reason for reason in result['reasons'])


def test_readable_jd_with_clearance_rejected_and_clean_unknown_still_allowed():
    rec={'company':'Example','title':'Cyber Security Intern','location':'London, United Kingdom','url':URL,
         'jd_screening_required':True,'vacancy_status':{'state':'UNKNOWN'}}
    scope=regional.lane_scope('uk',regional.load_schedules()['regions']['uk'])
    for text,decision in [('Graduate cyber security internship in London. Security clearance at SC level required.','rejected'),
                          ('Graduate cyber security internship in London. No prior experience required.','accepted')]:
        result=deterministic_gates('uk',dict(rec,jd_text=text),regional.load_policy(),scope)
        assert result['decision']==decision


@pytest.mark.parametrize('field,value',[('company','Different Employer'),('url','https://employer.example/different')])
def test_sweep_rechecks_identity_under_shared_writer_lock(tmp_path,field,value):
    import openpyxl,eligibility_sweep as sweep,tracker_writer as writer
    path=tmp_path/'tracker.xlsx';wb=openpyxl.Workbook();ws=wb.active;ws.title='Jobs'
    ws.append(['UK Jobs']);ws.append(['Date Found','Company','Role Title','Apply Link','Application Deadline','Status'])
    ws.append(['2026-10-26','Example','Cyber Intern',URL,'UNKNOWN','Not Applied']);wb.save(path);wb.close()
    before=writer.sha256_file(path)
    record={'row':3,'outcome':'FLAGGED','company':'Example','title':'Cyber Intern','url':URL};record[field]=value
    result=sweep.apply_flags(path,[record],profiles=writer.load_profiles(),backup_dir=tmp_path/'backups')
    assert result['applied'] is False and 'identity changed' in result['error']
    assert writer.sha256_file(path)==before
    assert not path.with_suffix('.xlsx.career-mail.lock').exists()
