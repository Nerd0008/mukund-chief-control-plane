import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from career_mail_parser import parse_message,extract_deadline
from career_mail_monitor import reconcile,analyze_signal
from career_mail_rules import role_key,company_key,visible

def mail(body,subject='Your application',mid='m',thread='t'):
    return dict(message_id=mid,thread_id=thread,received_at='2026-10-01T10:00:00+00:00',body=body,subject=subject)
def record(company='Acme Ltd',role='Graduate Cybersecurity Analyst',region='uk',**extras):
    return dict(company=company,role=role,region=region,application_id=region+company+role,seen_message_ids=[],thread_ids=[],**extras)
@pytest.mark.parametrize('suffix',['Ltd','PLC','UK','Group','Careers'])
def test_suffix_normalization_requires_full_role(suffix):
    raw=mail('Company: Acme '+suffix+'\nRole: Grad Cyber Security Analyst\nYour application has been received.')
    assert reconcile([raw],[record()])['counts']['matched_existing']==1

def test_two_distinct_company_roles_not_merged():
    raw=mail('Company: Acme\nRole: Intern Cybersecurity Analyst\nYour application has been received.')
    assert not reconcile([raw],[record()])['proposed_records']

def test_placement_not_internship():
    assert role_key('Cybersecurity Placement')!=role_key('Cybersecurity Internship')

def test_seniority_and_year_retained():
    assert role_key('Senior Engineer 2026')!=role_key('Engineer 2027')

def test_location_suffix_and_synonym():
    raw=mail('Company: Acme\nRole: Cybersecurity Grad Analyst - London\nYour application has been received.')
    assert reconcile([raw],[record()])['counts']['matched_existing']==1

def test_suffix_collision_is_review_not_first_match():
    r=reconcile([mail('Company: Acme Careers\nRole: Grad Cybersecurity Analyst\nYour application has been received.')],[record(),record(company='Acme PLC')])
    assert not r['proposed_records']
    assert 'multiple' in r['needs_review'][0]['review_reason']

def test_reference_beats_thread():
    rows=[record(application_identity='REF1',thread_ids_override=None),record(company='Other',application_identity='REF2')]
    rows[0]['thread_ids']=['wrong-thread']
    raw=mail('Company: Other\nRole: Graduate Cybersecurity Analyst\nApplication ID: REF2\nYour application has been received.',thread='wrong-thread')
    r=reconcile([raw],rows)
    assert r['proposed_records'][0]['company']=='Other'
    assert r['proposed_records'][0]['match_method']=='application/reference ID'

def test_company_only_cannot_select_one_job():
    r=reconcile([mail('Acme: Please complete your online assessment.')],[record()])
    assert not r['proposed_records']

@pytest.mark.parametrize('text,expected',[
 ('Complete by 11:59pm on 10 October 2026 BST.','2026-10-10T23:59:00+01:00'),
 ('Complete before 23:59 on 10 October 2026 UTC.','2026-10-10T23:59:00+00:00'),
 ('Complete no later than October 10, 2026 at 11:59pm BST.','2026-10-10T23:59:00+01:00'),
 ('Deadline: 2026-10-10 at 23:59 UTC.','2026-10-10T23:59:00+00:00'),
 ('Your assessment expires on 10 October 2026 at 23:59 BST.','2026-10-10T23:59:00+01:00'),
 ('Your interview is scheduled on 10 October 2026 at 14:00 BST.','2026-10-10T14:00:00+01:00'),
])
def test_reliable_timing_patterns(text,expected):
    d=extract_deadline(text,'2026-10-01T10:00:00+00:00','m','t')
    assert d['kind']=='EXACT' and d['value']==expected

@pytest.mark.parametrize('text',['Complete by 11:59pm on 10 October BST.','Complete before 23:59 on 10 October 2026.'])
def test_no_guessed_year_or_timezone(text):
    d=extract_deadline(text,'2026-10-01T10:00:00+00:00','m','t')
    assert d['needs_review'] and not d['value']

def test_within_hours_from_email():
    d=extract_deadline('Please complete your assessment within 48 hours of receiving this email.','2026-10-01T10:00:00+00:00','m','t')
    assert d['value']=='2026-10-03T10:00:00+00:00' and d['kind']=='DERIVED'

def test_separate_invite_not_reminder_receipt():
    d=extract_deadline('Reminder: You need to complete the assessment within 7 days of receiving the invite.','2026-10-01T10:00:00+00:00','m','t')
    assert d['needs_review'] and not d['value']

def test_employer_response_not_deadline_or_rejection():
    raw=mail('Thank you for your application. We aim to contact you within 14 days. If you have not heard from us within 28 days, please assume your application has been unsuccessful.','We have received your application')
    p=parse_message(raw)
    assert p['latest_status']=='application_received'
    assert not p['deadline']['value'] and not p['deadline']['needs_review']

def test_future_interview_not_current_interview():
    p=parse_message(mail('Thank you for applying. If you are selected for a video interview, we will contact you.','Confirmation of Application'))
    assert p['latest_status']=='application_confirmation' and not p['assessment_type']

def test_future_centre_not_current_centre():
    p=parse_message(mail('Please complete your online assessment. The later stages include an assessment centre.','National Highways - Next Steps'))
    assert p['latest_status']=='online_assessment'

@pytest.mark.parametrize('subject',['Roles are now open','Tell us about your Application Experience','Candidate survey'])
def test_generic_content_ignored(subject):
    assert parse_message(mail('Thank you for applying. SHL assessments and interviews.',subject)) is None

def test_html_css_not_role():
    text=visible('<html><head><style>.a {position:absolute;}</style></head><body><p>Role: Graduate Analyst</p></body></html>')
    assert 'absolute' not in text and 'Graduate Analyst' in text

def test_likely_new_full_identity_still_review_only_without_region():
    a=analyze_signal(mail('Company: New Employer\nRole: Graduate Engineer\nThank you for applying.'),[])
    assert a['category']=='likely new application' and a['needs_review']
    assert not reconcile([mail('Company: New Employer\nRole: Graduate Engineer\nThank you for applying.')],[])['proposed_records']


def test_program_manager_not_manager():
    assert role_key("Program Manager")!=role_key("Manager")

def test_different_explicit_cities_not_merged():
    raw=mail("Company: Acme\nRole: Grad Cybersecurity Analyst - Chester\nYour application has been received.")
    r=reconcile([raw],[record(role="Graduate Cybersecurity Analyst - London")])
    assert not r["proposed_records"]


def test_wrapped_portal_role_does_not_truncate():
    raw=mail("Thank you for your interest in Johnson Controls. Your application for the position of Technical\nSupport Advisor has been received.","Johnson Controls - Application received")
    a=analyze_signal(raw,[record(company="Johnson Controls / ADT",role="Technical Support Advisor")])
    assert a["category"]=="confident existing application match"

def test_pimco_portal_receipt_role_without_for():
    p=parse_message(mail("Thank you for applying to our 2027 Summer Intern – Product Analyst, EMEA opportunity! Your application has been received.","Thank you for applying to PIMCO!"))
    assert p["role"]=="2027 Summer Intern – Product Analyst, EMEA"

def test_role_of_does_not_include_employer():
    p=parse_message(mail("Thank you for applying for the role of Graduate Analyst at Acme.","Application received"))
    assert p["role"]=="Graduate Analyst"

def test_logo_alt_can_identify_explicit_employer():
    assert "Acme" in visible('<div><img alt="Acme"><p>Welcome</p></div>')

def test_inline_html_word_boundaries():
    assert "Analyst role" in visible('<span>Analyst</span><span>role</span>')


def test_current_role_can_disambiguate_reused_thread():
    rows=[record(role="Graduate Engineer"),record(role="Internship Analyst")]
    rows[0]["thread_ids"]=["t"]
    raw=mail("Company: Acme\nRole: Intern Analyst\nYour application has been received.")
    r=reconcile([raw],rows)
    assert r["proposed_records"][0]["role"]=="Internship Analyst"

def test_thread_evidence_recovers_missing_role():
    confirmation=mail("Company: Acme\nRole: Graduate Engineer\nThank you for applying.",mid="a")
    assessment=mail("Please complete your online assessment.",subject="Assessment invitation",mid="b")
    r=reconcile([confirmation,assessment],[record(role="Graduate Engineer")])
    assert r["counts"]["matched_existing"]==2
    assert all(x["category"]=="confident existing application match" for x in r["signal_analysis"])

def test_conflicting_thread_context_not_inherited():
    first=mail("Company: Acme\nRole: Graduate Engineer\nThank you for applying.",mid="a")
    second=mail("Company: Acme\nRole: Internship Analyst\nThank you for applying.",mid="b")
    third=mail("Please complete your online assessment.",subject="Assessment invitation",mid="c")
    r=reconcile([first,second,third],[record(role="Graduate Engineer"),record(role="Internship Analyst")])
    a=next(x for x in r["signal_analysis"] if x["gmail_message_id"]=="c")
    assert a["needs_review"] and not a.get("role")

def test_repeated_invite_does_not_shift_relative_deadline():
    first=mail("Company: Acme\nRole: Graduate Engineer\nPlease complete your assessment within 5 days.",subject="Assessment invitation",mid="a")
    later=dict(first,message_id="b",received_at="2026-10-02T10:00:00+00:00")
    r=reconcile([first,later],[record(role="Graduate Engineer")])
    assert {x["deadline"]["value"] for x in r["signal_analysis"]}=={"2026-10-06T10:00:00+00:00"}

def test_wrapped_word_number_relative_period():
    d=extract_deadline("Please complete the assessment within the next\nthree days.","2026-10-01T10:00:00+00:00","m","t")
    assert d["value"]=="2026-10-04T10:00:00+00:00"


def test_privacy_footer_company_cannot_override_explicit_employer():
    raw=mail("Thank you for applying for the Graduate Auditor role with Menzies. This takes time.","Application received")
    a=analyze_signal(raw,[record(company="Takes",role="Graduate Auditor")])
    assert a["company"]=="Menzies" and a["category"]!="confident existing application match"

def test_candidate_id_is_not_application_reference():
    raw=mail("Candidate ID: PERSON1\nCompany: Acme\nRole: Internship Analyst\nYour application has been received.")
    a=analyze_signal(raw,[record(role="Graduate Engineer",application_identity="PERSON1")])
    assert a["category"]!="confident existing application match"


def test_canonical_employer_host_requires_full_role():
    raw=mail('Your application for Graduate Engineer has been received. https://careers.acme.example/jobs/help',subject='Application received')
    a=analyze_signal(raw,[record(role='Graduate Engineer',canonical_job_host='careers.acme.example')])
    assert a['category']=='confident existing application match'

def test_generic_platform_domain_cannot_identify_employer():
    raw=mail('Your application for Graduate Engineer has been received. https://myworkday.com/help',subject='Application received')
    a=analyze_signal(raw,[record(role='Graduate Engineer',canonical_job_host='myworkday.com')])
    assert a['category']!='confident existing application match'
