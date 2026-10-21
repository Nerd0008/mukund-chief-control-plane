#!/usr/bin/env python3
"""Clearance screening — visible text only, strong phrases, context-bound tokens.

Three failures, all observed against the live tracker while running the
eligibility sweep (not inferred from reading code):

1. **Markup matched.** The Acturis Graduate Technical Business Analyst posting
   contains ``<div class="sc-129pb7e-1 bh">``; the bare ``\\bSC\\b`` token matched
   the styled-components class and flagged a role that requires no vetting.
2. **Bare tokens matched out of context.** ``SC`` is also a Microsoft
   certification code (``SC-200``) and a US state (``Myrtle Beach, SC``); ``DV``
   is also a company name (``DV Trading``, ``the DV Group``). Each produced a
   false "clearance required" verdict on a genuinely eligible role.
3. **Garbled pages treated as clean.** Two rows fetched as undecodable byte soup
   produced hits on random characters.

And the drift hazard: the token regex lived in two hand-maintained copies (the
search lane and the regional worker). Both now import this one module.
"""

import importlib
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import clearance_screening as cs  # noqa: E402

REAL_MBDA = (
    "Salary: £31,900 plus a £3000 joining bonus. "
    "Security Clearance: British Citizen or a Dual UK national with British citizenship. "
    "As a minimum and after offer stage, all successful candidates will need to undergo "
    "HMG Basic Personnel Security Standard checks (BPSS)."
)

REAL_NNL = (
    "You will have the right to work in the UK, have lived in the UK for at least 5 years "
    "and be able to achieve SC level security clearance."
)

REAL_THAMES = (
    "be able to successfully complete and maintain UK Government security checks, "
    "including Baseline Personnel Security Standard (BPSS) screening and Security "
    "Clearance (SC), which is a government background check, before starting employment. "
    "To be eligible for SC clearance, you will typically need to have lived in the UK "
    "continuously for the last five years."
)

# --- 1. markup ------------------------------------------------------------- #

ACTURIS_FRAGMENT = (
    "<div class=\"sc-129pb7e-1 bh\">University of Southampton</div>"
    " We have a variety of join dates available for this role."
)


def test_markup_class_names_are_not_clearance_requirements():
    assert cs.clearance_hits(ACTURIS_FRAGMENT) == []


def test_script_and_style_bodies_are_ignored():
    assert cs.clearance_hits(
        "<style>body{color:red}</style><script>var SC = 1;</script>Nothing here."
    ) == []


def test_html_comments_are_ignored():
    assert cs.clearance_hits("Hello<!-- Security Clearance required -->world") == []


def test_visible_text_strips_tags_and_unescapes_entities():
    t = cs.visible_text("<p>Security&nbsp;Clearance &amp; BPSS</p>")
    assert "Security Clearance" in t
    assert "BPSS" in t
    assert "<p>" not in t


# --- 2. bare tokens need context ------------------------------------------- #

@pytest.mark.parametrize("text,why", [
    ("the following certifications are a plus: CompTIA Security+ – A foundational "
     "certification in cybersecurity. Microsoft SC-200 – Security Operations Analyst "
     "(focused on Microsoft Defender and Sentinel).", "Microsoft exam code"),
    ("About Us: Founded 20 years ago and headquartered in Chicago, the DV Group of "
     "financial services firms has grown to more than 600 people.", "company name"),
    ("Arcade Supervisor Ocean Lakes Service Corp. Myrtle Beach, SC Be an early applicant",
     "US state abbreviation"),
    ("Client Platforms Engineer Intern - Summer 2027 DV Trading LLC London, England",
     "another employer named in a listing"),
])
def test_bare_tokens_without_vetting_context_are_not_hits(text, why):
    assert cs.clearance_hits(text) == [], why


def test_bare_token_with_vetting_context_is_a_hit():
    """``SC`` alone is nothing; ``SC level security clearance`` is a requirement."""
    assert "sc" in cs.clearance_hits(REAL_NNL)


def test_bpss_with_personnel_security_context_is_a_hit():
    assert "bpss" in cs.clearance_hits(
        "all successful candidates will need to undergo HMG Basic Personnel Security "
        "Standard checks (BPSS), which are managed by the Personnel Security Team."
    )


def test_bpss_without_context_is_not_a_hit():
    assert cs.clearance_hits("Our internal codename for the project is BPSS.") == []


def test_security_check_as_a_duty_is_not_a_requirement():
    """Lloyds: the role *performs* security checks, it is not subject to vetting."""
    assert cs.clearance_hits(
        "Create solutions that protect customers, colleagues and data from cyber "
        "threats. Automate repetitive tasks and security checks to make processes "
        "go faster."
    ) == []


def test_security_check_with_government_context_is_a_requirement():
    """Proact: "HMG Security Check - SC - clearance" is a vetting requirement."""
    hits = cs.clearance_hits(
        "Eligibility to obtain HMG Security Check - SC - clearance. A solid "
        "foundation in networking and security."
    )
    assert "security check" in hits
    assert "sc" in hits


def test_board_chrome_requirement_is_kept_and_visible():
    """Not filtered: the evidence shows the contamination so a reviewer can judge.

    A window tight enough to drop it also taints a genuine requirement quoted a
    few sentences later, and silently dropping a real requirement is worse.
    """
    hits = cs.clearance_hits(
        "Remote Junior GRC Analyst. Blue Cross and Blue Shield of Nebraska "
        "Omaha, NE 1 week ago Cyber Security Analyst - 306211 with Security "
        "Clearance."
    )
    assert hits == ["security clearance"]
    ev = cs.clearance_evidence(
        "Remote Junior GRC Analyst. Blue Cross and Blue Shield of Nebraska "
        "Omaha, NE 1 week ago Cyber Security Analyst - 306211 with Security "
        "Clearance."
    )
    assert "Blue Cross" in ev[0]["context"]


# --- strong phrases -------------------------------------------------------- #

@pytest.mark.parametrize("text,token", [
    (REAL_MBDA, "security clearance"),
    (REAL_MBDA, "british citizenship"),
    (REAL_MBDA, "bpss"),
    (REAL_THAMES, "sc"),
    (REAL_THAMES, "security clearance"),
    ("Must hold indefinite right to work in the UK.", "indefinite right to work"),
    ("Applicants require British-citizenship.", "british-citizenship"),
])
def test_real_requirements_are_still_found(text, token):
    assert token in cs.clearance_hits(text), (text[:60], token)


def test_clean_text_has_no_hits():
    assert cs.clearance_hits(
        "We are an equal opportunities employer. Hybrid working, London."
    ) == []


def test_results_are_sorted_and_unique():
    hits = cs.clearance_hits(f"{REAL_MBDA} {REAL_THAMES}")
    assert hits == sorted(set(hits))


def test_evidence_carries_the_surrounding_sentence():
    ev = cs.clearance_evidence(REAL_MBDA, context=40)
    assert "security clearance" in {e["token"] for e in ev}
    for e in ev:
        assert e["context"].strip()


# --- 3. garbled pages ------------------------------------------------------ #

def test_garbled_page_is_not_readable():
    assert not cs.is_readable("���Fo���8�Z�7Y� z�zWf�TK� \x17�����G��O` 6��~7�")


def test_multiline_prose_with_line_breaks_is_readable():
    """Counting ``\\n`` as garbling rejected every normal job description."""
    assert cs.is_readable("Line one of the job description.\nLine two.\n\nLine three.")


def test_garbled_page_yields_no_hits():
    soup = "���Fo���8�Z�7Y� z�zWf�TK� \x17�����G��O` SC DV BPSS"
    assert cs.clearance_hits(soup) == []


def test_garbled_page_yields_no_evidence():
    assert cs.clearance_evidence("���Fo���8�Z�7Y� \x17���� SC") == []


def test_plain_english_is_readable():
    assert cs.is_readable(REAL_MBDA)


def test_empty_and_non_string_input():
    assert cs.visible_text(None) == ""
    assert cs.visible_text(1234) == ""
    assert cs.clearance_hits(None) == []
    assert not cs.is_readable("")


# --- one implementation ---------------------------------------------------- #

def test_both_lanes_import_the_same_implementation():
    rjs = importlib.import_module("regional_job_search")
    ces = importlib.import_module("codex_entry_level_search")
    assert rjs.clearance_hits.__module__ == "clearance_screening"
    assert ces.clearance_hits.__module__ == "clearance_screening"
