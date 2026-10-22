"""The availability gate: an unverified role is a lead, not a rejection.

Owner instruction 2026-10-22: "still add if not verified open".

Why this rule exists: the vacancy verifier is a browserless HTTP fetch, so it cannot prove
OPEN on JavaScript-rendered ATS pages (Workday, SmartRecruiters, LinkedIn). Requiring proof
of availability therefore rejected 71 of 72 accepted roles in a real run and the tracker
received nothing, even though the roles found were exactly the ones the owner wanted.

The rule is one-way: only POSITIVE evidence of closure blocks a role. Absence of
verification is reported as an unverified lead. These tests pin both halves, so a future
change cannot quietly restore the fail-closed behaviour or, worse, drop the closure checks.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'discovery'))

import pipeline  # noqa: E402
import regional_job_search as rjs  # noqa: E402


def _verdict(rec):
    policy = rjs.load_policy()
    scope = rjs.lane_scope('uk', rjs.load_schedules()['regions']['uk'])
    return pipeline.deterministic_gates('uk', rec, policy, scope)


def _role(**over):
    rec = {'company': 'Example Ltd', 'title': 'Cyber Security Intern',
           'location': 'London, United Kingdom', 'url': 'https://example.com/jobs/1',
           'jd_text': 'A cyber security internship in London.'}
    rec.update(over)
    return rec


def _unverified_flags(v):
    return [f for f in v['flags'] if 'UNVERIFIED' in f]


def test_unknown_availability_is_added_as_an_unverified_lead():
    v = _verdict(_role(vacancy_status={'state': 'UNKNOWN', 'evidence': 'job not fetched'}))
    assert v['decision'] == 'accepted'
    assert _unverified_flags(v)


def test_never_checked_availability_is_added_not_dropped():
    """No vacancy_status at all is the common case for a freshly discovered role."""
    v = _verdict(_role())
    assert v['decision'] == 'accepted'
    assert _unverified_flags(v)


def test_discovered_unverified_transport_is_added_as_an_unverified_lead():
    v = _verdict(_role(fetch_state='discovered_unverified'))
    assert v['decision'] == 'accepted'
    assert _unverified_flags(v)


def test_bot_wall_is_added_as_an_unverified_lead():
    """403/429 is not evidence the vacancy is closed."""
    v = _verdict(_role(fetch_state='bot_wall'))
    assert v['decision'] == 'accepted'
    assert _unverified_flags(v)


def test_validation_failure_is_still_refused():
    """A failed validation is a NEGATIVE result (dead link, expired marker, non-2xx,
    robots refusal), not an absence of evidence — a dead link must never reach the
    tracker."""
    v = _verdict(_role(fetch_state='validation_failed',source_failure_kind='closed'))
    assert v['decision'] == 'rejected'
    assert any('failed validation' in r for r in v['reasons'])


def test_proven_closed_availability_is_still_rejected():
    """The one-way rule must not become 'add everything'."""
    v = _verdict(_role(vacancy_status={'state': 'CLOSED', 'evidence': 'HTTP 404'}))
    assert v['decision'] == 'rejected'
    assert any('CLOSED' in r for r in v['reasons'])


def test_jd_stating_the_application_is_closed_is_still_rejected():
    v = _verdict(_role(jd_is_closed=True))
    assert v['decision'] == 'rejected'


def test_a_verified_open_role_is_not_flagged_unverified():
    v = _verdict(_role(vacancy_status={'state': 'OPEN'},
                       fetch_state='validated_live'))
    assert v['decision'] == 'accepted'
    assert not _unverified_flags(v)


def test_clearance_requirement_still_rejects_an_unverified_role():
    """Relaxing availability must not relax the owner's clearance rule."""
    v = _verdict(_role(jd_text='This role requires SC security clearance before starting.'))
    assert v['decision'] == 'rejected'
    assert any('clearance' in r.lower() for r in v['reasons'])


def test_explicit_null_availability_is_flagged_without_crashing():
    verdict = _verdict(_role(vacancy_status=None))
    assert verdict["decision"] == "accepted"
    assert _unverified_flags(verdict)
