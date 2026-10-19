"""Requisition-scoped posting identity.

The failure this pins: one vacancy reachable by several URLs (employer ATS, Workday
requisition, aggregator listing) appeared as several tracker rows, so a role the owner
had already applied to was offered again. URL normalisation cannot see that these are
one vacancy; the ATS requisition ID can.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest

import codex_entry_level_search as search
from career_search_recall import posting_key
from posting_identity import (company_key, identity_keys, is_aggregator,
                              requisition_id, same_posting)

AMEX_EMPLOYER = 'https://careers.americanexpress.com/en/sites/CX_1/job/26013761/'
AMEX_ORACLE = ('https://egug.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/'
               'en/sites/CX_1/job/26013761')
AMEX_AGGREGATOR = ('https://www.jointheintake.com/internships/american-express-campus-'
                   'internship-programme-undergraduate-information-security-engineer-'
                   '2027-uk-burgess-hill-b4atml')


@pytest.mark.parametrize('url,expected', [
    (AMEX_EMPLOYER, '26013761'),
    (AMEX_ORACLE, '26013761'),
    ('https://barclays.wd3.myworkdayjobs.com/External_Career_Site_Barclays/job/'
     'Knutsford-Radbroke-Hall/XMLNAME-2027-Technology-Cyber-and-Security-Summer-'
     'Internship-Programme-Knutsford_JR-0000129173', 'JR-0000129173'),
    ('https://job-boards.greenhouse.io/gocardless/jobs/8066856?gh_src=885sh6b71us', '8066856'),
    ('https://jobs.smartrecruiters.com/TTP1/744000153148930', '744000153148930'),
    ('https://actica.pinpointhq.com/en/postings/973dc768-c64a-47d1-ae2c-9fc66aa2248d',
     '973DC768-C64A-47D1-AE2C-9FC66AA2248D'),
    ('https://symphony.com/company/apply/?gh_jid=8113704', '8113704'),
    # Listings that name no requisition of their own must yield nothing, not a guess.
    (AMEX_AGGREGATOR, ''),
    ('https://www.brightnetwork.co.uk/graduate-jobs/american-express/information-security-'
     'engineer-internship-burgess-hill-2026-amug', ''),
    ('', ''),
    ('not a url', ''),
])
def test_requisition_id_extracts_only_real_identifiers(url, expected):
    assert requisition_id(url) == expected


def test_same_requisition_on_different_hosts_is_one_posting():
    employer = {'company': 'American Express', 'url': AMEX_EMPLOYER}
    oracle = {'company': 'American Express', 'url': AMEX_ORACLE}
    assert same_posting(employer, oracle)


def test_different_employers_sharing_a_number_are_never_merged():
    """A bare numeric ID is not unique across employers; merging would drop a real job."""
    left = {'company': 'American Express', 'url': AMEX_EMPLOYER}
    right = {'company': 'Some Other Bank', 'url': 'https://other.example.com/job/26013761'}
    assert not same_posting(left, right)
    assert not (identity_keys(left['company'], left['url'])
                & identity_keys(right['company'], right['url']))


def test_employer_scoped_key_shape():
    keys = identity_keys('American Express', AMEX_EMPLOYER)
    assert keys == {'req:americanexpress:26013761'}


def test_records_without_an_employer_do_not_match_records_that_have_one():
    assert not (identity_keys(None, AMEX_ORACLE) & identity_keys('American Express', AMEX_EMPLOYER))
    # ...but two employer-less records naming one requisition still collapse.
    assert identity_keys(None, AMEX_ORACLE) == identity_keys(None, AMEX_EMPLOYER)


def test_resolved_employer_destination_collapses_a_relisted_vacancy():
    """An aggregator URL names no requisition; its resolved destination does."""
    assert not (identity_keys('American Express', AMEX_AGGREGATOR)
                & identity_keys('American Express', AMEX_EMPLOYER))
    assert (identity_keys('American Express', AMEX_AGGREGATOR, AMEX_ORACLE)
            & identity_keys('American Express', AMEX_EMPLOYER))


def test_company_key_normalises_punctuation_and_case():
    assert company_key('American Express') == company_key('american  express')
    assert company_key('L&G') == company_key('l g')
    assert company_key(None) == ''


@pytest.mark.parametrize('url,expected', [
    (AMEX_AGGREGATOR, True),
    ('https://www.brightnetwork.co.uk/graduate-jobs/x', True),
    ('https://uk.linkedin.com/jobs/view/x', True),
    ('https://careers.waterstons.com/jobs/8494621-graduate-security-consultant', False),
    (AMEX_EMPLOYER, False),
])
def test_is_aggregator(url, expected):
    assert is_aggregator(url) is expected


def test_search_treats_same_requisition_as_already_tracked(tmp_path, monkeypatch, capsys):
    """The exact regression: the Oracle URL must not become a second row for a role
    already tracked through the employer careers URL."""
    tracker = tmp_path / 'tracker.xlsx'
    tracker.touch()
    monkeypatch.setitem(search.TRACKERS, 'uk', tracker)
    monkeypatch.setattr(search.osp, 'load_profile', lambda: {})
    monkeypatch.setattr(search, '_profile_terms', lambda: (search.ENTRY_MARKERS, (), None))

    class Book:
        def close(self): pass
        def save(self, *a): pytest.fail('dry run wrote workbook')

    monkeypatch.setattr(search, 'read_tracker_urls', lambda p: (
        {posting_key(AMEX_EMPLOYER)},
        identity_keys('American Express', AMEX_EMPLOYER),
        None, Book(), {}, 2, None))
    monkeypatch.setattr(search, 'run_codex', lambda *a, **k: json.dumps([
        {'company': 'American Express', 'job_title': 'Cyber Security Intern',
         'url': AMEX_ORACLE}]))
    monkeypatch.setattr(search, 'fetch_jd',
                        lambda *a: pytest.fail('same-requisition job fetched'))
    monkeypatch.setattr(sys, 'argv', ['search', '--batches', '1', '--dry-run'])
    assert search.main() == 0
    report = json.loads(next(l.split(' ', 1)[1] for l in capsys.readouterr().out.splitlines()
                             if l.startswith('SEARCH_RECONCILIATION ')))
    assert report['counts']['already_tracked'] == 1
    assert report['counts']['new_candidates'] == 0
    assert 'same requisition' in report['decisions'][0]['reason']
    assert tracker.read_bytes() == b''
