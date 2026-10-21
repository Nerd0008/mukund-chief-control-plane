"""Prior-experience screening of job descriptions.

The failure this pins: a vacancy advertised as "IT Support Analyst" was accepted
because the gate read the title only, even though its own job description asked
for "2+ years of experience in a similar IT support role". The title of a role
says nothing about the experience it wants; the JD does.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experience_screening as es  # noqa: E402

# Verbatim from the IT support posting the owner flagged.
IT_SUPPORT_JD = """
Key Skills and Qualifications
* 2+ years of experience in a similar IT support role
* Strong troubleshooting skills and the ability to think logically and critically
* Good communication skills for interacting with end-users, team members,
  internal customers and vendors
* Good problem-solving capabilities
* Ability to work independently and as part of a team

Technology Requirements
* Strong knowledge of Microsoft Windows operating systems
* Proficiency in Microsoft Office 365 suite
* Active Directory and Azure Infrastructure support
* Familiarity with common business software and cloud-based services such as
  Slack, Box, Zoom and Jira
Keep up-to-date with industry best practices and emerging technologies.
"""

GRADUATE_JD = """
Cyber Security Graduate Programme 2027
You will join our security operations team and rotate across GRC, IAM and
incident response. No prior experience is necessary; we provide full training.
You should be in your penultimate year of study, or have graduated within the
last two years. Strong analytical skills and a genuine interest in security.
"""


def test_the_it_support_posting_is_caught():
    hits = es.experience_hits(IT_SUPPORT_JD)
    assert hits, 'a 2+ years requirement must be found'
    assert any('2+' in h or 'years of experience' in h for h in hits)


def test_a_genuine_graduate_programme_is_not_caught():
    assert es.experience_hits(GRADUATE_JD) == []


def test_markup_alone_is_not_a_requirement():
    html = '<div class="2-years-3-columns"><span>Apply now</span></div>'
    assert es.experience_hits(html) == []


def test_zero_to_one_years_is_entry_level():
    assert es.experience_hits('0-1 years of experience in a SOC') == []
    assert es.experience_hits('1 year of experience required') == []


def test_two_years_is_the_threshold():
    assert es.experience_hits('2 years of experience required')
    assert es.experience_hits('3 years of experience required')
    assert es.experience_hits('minimum of 5 years experience')


def test_word_numbers_count():
    assert es.experience_hits('at least two years of experience in IT')


def test_a_range_counts_from_its_floor():
    """'2-5 years' is a two-year minimum, not a five-year one."""
    assert es.experience_hits('2-5 years of relevant experience')
    assert es.experience_hits('0-2 years of experience') == []


def test_company_age_is_not_a_candidate_requirement():
    """The failure mode the context window exists to prevent."""
    assert es.experience_hits('We have supported clients for over 25 years.') == []
    assert es.experience_hits('Founded 2 years ago, we are growing fast.') == []


def test_years_of_study_are_not_years_of_experience():
    assert es.experience_hits('A 3 year degree, penultimate year of study') == []
    assert es.experience_hits('You are in your final year of study') == []


def test_strong_phrases_are_caught_without_a_number():
    assert es.experience_hits('You will have proven track record in security')
    assert es.experience_hits('Prior experience in a helpdesk environment is essential')
    assert es.experience_hits('Commercial experience delivering SIEM projects')


def test_strong_phrases_skip_a_graduate_context():
    assert es.experience_hits(
        'No prior experience is needed; this is a graduate programme') == []


def test_unreadable_text_is_not_screened():
    """An undecodable page proves nothing, so it must not be reported as clean."""
    soup = ''.join(chr(0xFFFD) * 400)
    assert es.experience_hits(soup) == []
    assert not es.is_readable(soup)


def test_empty_and_missing_text_is_safe():
    assert es.experience_hits('') == []
    assert es.experience_hits(None) == []


def test_evidence_is_reported_for_a_human():
    ev = es.experience_evidence(IT_SUPPORT_JD)
    assert ev and all('phrase' in e for e in ev)
