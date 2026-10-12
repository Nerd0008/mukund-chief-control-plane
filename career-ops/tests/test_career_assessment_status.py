import datetime as dt,pathlib,sys
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import career_assessment_status as a
NOW=dt.datetime(2026,10,12,12,tzinfo=dt.timezone.utc)

@pytest.mark.parametrize('value,expected',[('2026-10-14T12:00:00Z','OPEN'),('2026-10-10T12:00:00Z','EXPIRED'),('2026-10-12T12:00:00Z','EXPIRED')])
def test_reliable_deadline(value,expected):
    assert a.lifecycle({'deadline':{'value':value}}, {},NOW)[0]==expected

@pytest.mark.parametrize('deadline',[{}, {'value':'2026-10-14T12:00:00Z','needs_review':True},{'value':'2026-10-14T12:00:00'}])
def test_no_evidence_never_open(deadline):
    assert a.lifecycle({'deadline':deadline},{'body':'Please complete your assessment. Link attached.'},NOW)[0]=='UNKNOWN'

@pytest.mark.parametrize('date,expected',[('2026-10-10','EXPIRED'),('2026-10-12','UNKNOWN'),('2026-10-14','OPEN')])
def test_date_only(date,expected):
    assert a.lifecycle({'deadline':{'value':date,'date_only':True}}, {},NOW)[0]==expected

@pytest.mark.parametrize('body,expected',[('Thank you for completing your assessment.','COMPLETED'),('Your assessment has expired.','EXPIRED')])
def test_explicit_status_overrides_old_deadline(body,expected):
    assert a.lifecycle({'deadline':{'value':'2026-10-14T12:00:00Z'}},{'body':body},NOW)[0]==expected

def test_newsletter_is_not_personal_assessment():
    assert a.newsletter({'subject':'Jobs for you','body':'Online assessment guide','from':'Totaljobs'})
    assert not a.newsletter({'subject':'Assessment invitation','body':'Please complete your assessment.','from':'Talogy'})

def test_completed_update_supersedes_invitation_without_company_only_merge(monkeypatch):
    monkeypatch.setattr(a,'prepare_messages',lambda m,r:m)
    def resolve(raw,records):
        return {'gmail_message_id':raw['message_id'],'gmail_thread_id':raw['thread_id'],'application_identity':None,
                'assessment_type':raw['kind'],'latest_status':raw['kind'],'company':'Example','role':'Graduate',
                'assessment_received_date':raw['received_at'],'deadline':{}},[],None
    monkeypatch.setattr(a,'resolve',resolve)
    messages=[{'message_id':'1','thread_id':'A','kind':'online_assessment','received_at':'2026-10-10T10:00:00Z'},
              {'message_id':'2','thread_id':'A','kind':'assessment_completed','received_at':'2026-10-11T10:00:00Z'},
              {'message_id':'3','thread_id':'B','kind':'online_assessment','received_at':'2026-10-11T11:00:00Z'}]
    report=a.analyze(messages,[],NOW)
    assert report['counts']['COMPLETED']==1 and report['counts']['UNKNOWN']==1
    assert report['gmail_mutations']==report['tracker_writes']==report['calendar_writes']==0
    assert not report['checkpoint_advanced']

def test_native_route_does_not_use_incremental_checkpoint(monkeypatch):
    import hermes_gmail_tools as g
    calls=[]
    monkeypatch.setattr(g,'command',lambda script,verb:calls.append((script,verb)))
    g.assessments_tool({})
    assert calls==[('career_assessment_status.py','scan')]
    assert 'No deadline is UNKNOWN' in g.GUIDANCE


def test_timeout_is_bounded_and_does_not_expose_private_output(monkeypatch):
    import hermes_gmail_tools as g
    def timeout(*a,**k):raise g.subprocess.TimeoutExpired('private-command',240,output='SECRET')
    monkeypatch.setattr(g,'command',timeout)
    result=g.assessments_tool({})
    assert 'timed out' in result and 'SECRET' not in result


def test_prose_is_not_returned_as_job_title(monkeypatch):
    monkeypatch.setattr(a,'prepare_messages',lambda m,r:m)
    monkeypatch.setattr(a,'resolve',lambda raw,records:({'gmail_message_id':'m','gmail_thread_id':'t','assessment_type':'online_assessment',
        'company':'Example','role':'join Example:','deadline':{}},[],None))
    row=a.analyze([{'subject':'Assessment invitation','body':'Please complete your assessment.'}],[],NOW)['assessments'][0]
    assert row['role'] is None and row['identity_needs_review']
