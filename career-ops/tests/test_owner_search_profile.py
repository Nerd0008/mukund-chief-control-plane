#!/usr/bin/env python3
"""Tests for the profile-driven search vocabulary (``owner_search_profile``).

Offline and read-only: no test performs a network call, writes a workbook, or
touches the owner's live profile. The live-profile tests only READ it; every
write test uses a tmp_path fixture.

Run:  python -m pytest career-ops/tests/test_owner_search_profile.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import owner_search_profile as osp  # noqa: E402

LIVE_PROFILE = osp.profile_path()


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def profile_file(tmp_path):
    """A minimal but real-shaped owner profile."""
    p = tmp_path / "profile.yml"
    p.write_text(
        "candidate:\n"
        "  full_name: \"Test Owner\"\n"
        "target_roles:\n"
        "  primary:\n"
        "    - \"Cybersecurity Intern\"\n"
        "    - \"GRC Intern\"\n"
        "    - \"IT Support Intern\"\n"
        "  archetypes:\n"
        "    - name: \"Cybersecurity and Information Security Internship\"\n"
        "      level: \"Internship; graduates eligible\"\n"
        "      fit: \"primary\"\n"
        "location:\n"
        "  country: \"United Kingdom\"\n"
        "  authorized_in: [\"United Kingdom\"]\n"
        "  needs_sponsorship: false\n"
        "  visa_status: \"Graduate visa through 23 December 2027\"\n"
        "  clearance_filter: \"Reject SC, DV, CTC, NPPV, UKSV; also reject "
        "British-citizenship and indefinite-right-to-work requirements\"\n",
        encoding="utf-8",
    )
    return p


# --------------------------------------------------------------------------- #
# fail-closed behaviour
# --------------------------------------------------------------------------- #

def test_missing_profile_fails_closed(tmp_path):
    with pytest.raises(osp.ProfileUnavailable, match="not found"):
        osp.load_profile(tmp_path / "absent.yml")


def test_empty_profile_fails_closed(tmp_path):
    p = tmp_path / "profile.yml"
    p.write_text("   \n\n", encoding="utf-8")
    with pytest.raises(osp.ProfileUnavailable, match="empty"):
        osp.load_profile(p)


def test_unparseable_profile_fails_closed(tmp_path):
    p = tmp_path / "profile.yml"
    p.write_text("candidate: [unclosed\n", encoding="utf-8")
    with pytest.raises(osp.ProfileUnavailable):
        osp.load_profile(p)


def test_non_mapping_profile_fails_closed(tmp_path):
    p = tmp_path / "profile.yml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(osp.ProfileUnavailable, match="not a mapping"):
        osp.load_profile(p)


# --------------------------------------------------------------------------- #
# target roles
# --------------------------------------------------------------------------- #

def test_target_keywords_mirror_the_install_shape(profile_file):
    """``primary`` + ``archetypes[].name``, strings only, deduped."""
    kw = osp.target_role_keywords(osp.load_profile(profile_file))
    assert kw == [
        "Cybersecurity Intern", "GRC Intern", "IT Support Intern",
        "Cybersecurity and Information Security Internship",
    ]


def test_target_keywords_tolerate_bad_shapes():
    assert osp.target_role_keywords({}) == []
    assert osp.target_role_keywords({"target_roles": None}) == []
    assert osp.target_role_keywords({"target_roles": {"primary": "scalar"}}) == []
    assert osp.target_role_keywords(
        {"target_roles": {"primary": ["A", 1, None, "A", " "]}}) == ["A"]
    assert osp.target_role_keywords(
        {"target_roles": {"archetypes": [{"level": "no name"}, "junk", None]}}) == []


def test_disciplines_strip_only_the_level_word(profile_file):
    disc = osp.discipline_terms(osp.load_profile(profile_file))
    assert "cybersecurity" in disc
    assert "grc" in disc
    assert "it support" in disc
    # the level word is gone, the discipline words are untouched
    assert not any(d.endswith(" intern") for d in disc)


def test_entry_level_terms_come_from_the_profile(profile_file):
    terms = osp.entry_level_terms(osp.load_profile(profile_file))
    assert "intern" in terms
    assert "graduate" in terms


# --------------------------------------------------------------------------- #
# eligibility facts
# --------------------------------------------------------------------------- #

def test_clearance_terms_read_the_owner_sentence(profile_file):
    terms = osp.clearance_terms(osp.load_profile(profile_file))
    assert "SC" in terms and "DV" in terms and "NPPV" in terms and "UKSV" in terms
    assert "british citizenship" in terms
    assert "indefinite right to work" in terms


def test_clearance_terms_do_not_invent_a_uk_token(tmp_path):
    """'long-UK-residency' must not yield a bare 'UK' clearance token."""
    p = tmp_path / "profile.yml"
    p.write_text(
        "location:\n"
        "  clearance_filter: \"reject long-UK-residency requirements\"\n",
        encoding="utf-8")
    terms = osp.clearance_terms(osp.load_profile(p))
    assert "UK" not in terms
    assert "long uk residency" in terms


@pytest.mark.parametrize("text", [
    "This role requires British-citizenship.",
    "This role requires British citizenship.",
    "Must hold indefinite-right-to-work status.",
    "Requires national-security clearance.",
])
def test_hyphenated_clearance_phrases_are_caught(text):
    """The owner's own spelling is hyphenated; adverts may not be, and vice versa.

    Both matchers are checked because the search script carries its own copy of
    the pattern and the two must not drift.
    """
    import codex_entry_level_search as ces
    import regional_job_search as rjs

    assert rjs.clearance_hits(text), f"shared matcher missed {text!r}"
    assert ces.clearance_hits(text), f"search matcher missed {text!r}"


def test_work_authorisation_is_never_upgraded(tmp_path):
    p = tmp_path / "profile.yml"
    p.write_text("location:\n  country: \"United Kingdom\"\n", encoding="utf-8")
    wa = osp.work_authorisation(osp.load_profile(p))
    assert wa["status"] == "UNKNOWN"
    assert wa["authorized_in"] == []


def test_work_authorisation_reads_authorized_in(profile_file):
    wa = osp.work_authorisation(osp.load_profile(profile_file))
    assert wa["status"] == "authorised"
    assert wa["authorized_in"] == ["United Kingdom"]
    assert wa["needs_sponsorship_now"] is False


# --------------------------------------------------------------------------- #
# queries
# --------------------------------------------------------------------------- #

def test_queries_are_bounded_and_deduped(profile_file):
    qs = osp.search_queries(osp.load_profile(profile_file), "UK", year=2026)
    assert qs, "a profile with target roles must produce queries"
    assert len(qs) == len(set(qs))
    assert all("UK" in q for q in qs)
    assert all("2026" in q for q in qs)


def test_queries_respect_the_limit(profile_file):
    assert len(osp.search_queries(osp.load_profile(profile_file), "UK", limit=3)) == 3


def test_queries_quote_the_primary_roles(profile_file):
    qs = osp.search_queries(osp.load_profile(profile_file), "UK", year=2026)
    assert '"Cybersecurity Intern" UK 2026' in qs


def test_no_target_roles_yields_no_queries(tmp_path):
    p = tmp_path / "profile.yml"
    p.write_text("candidate:\n  full_name: \"Nobody\"\n", encoding="utf-8")
    assert osp.search_queries(osp.load_profile(p), "UK") == []


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #

def test_digest_is_stable_and_changes_with_content(profile_file):
    first = osp.profile_digest(profile_file)
    assert first == osp.profile_digest(profile_file)
    profile_file.write_text(
        profile_file.read_text(encoding="utf-8") + "\n# edit\n", encoding="utf-8")
    assert osp.profile_digest(profile_file) != first


def test_snapshot_reports_the_contract(profile_file):
    snap = osp.snapshot(profile_file)
    assert snap["candidate_name"] == "Test Owner"
    assert snap["profile_sha256"] == osp.profile_digest(profile_file)
    assert snap["target_roles"]
    assert snap["clearance_terms"]
    assert snap["work_authorisation"]["status"] == "authorised"


# --------------------------------------------------------------------------- #
# the live owner profile (read-only)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not LIVE_PROFILE.is_file(), reason="owner install not present")
def test_live_profile_is_readable_and_has_target_roles():
    profile = osp.load_profile()
    assert osp.target_role_keywords(profile), "live profile must state target roles"


@pytest.mark.skipif(not LIVE_PROFILE.is_file(), reason="owner install not present")
def test_live_profile_queries_are_uk_scoped():
    qs = osp.search_queries(osp.load_profile(), "UK")
    assert qs
    assert all("UK" in q for q in qs)


@pytest.mark.skipif(not LIVE_PROFILE.is_file(), reason="owner install not present")
def test_live_profile_clearance_matches_the_shared_matcher():
    """Every clearance term the profile names must fire the shared matcher.

    Compared on the hyphen-normalised form: the profile writes
    "British-citizenship" and the matcher may report "british citizenship" (or
    vice versa) for the same requirement.
    """
    import regional_job_search as rjs

    def norm(s: str) -> str:
        return s.lower().replace("-", " ")

    profile = osp.load_profile()
    hits = {norm(h) for h in rjs.clearance_hits(osp.clearance_text(profile))}
    for term in osp.clearance_terms(profile):
        assert norm(term) in hits, (
            f"profile names '{term}' but the shared matcher misses it")
