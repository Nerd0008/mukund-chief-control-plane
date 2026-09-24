#!/usr/bin/env python3
"""Tests for the read-only Application Inbox / Status Monitor.

Offline and non-destructive:
* no network call, no browser, no mailbox login, no mail is sent;
* every store write goes to ``tmp_path``;
* the canonical workbooks are only ever opened read-only, and the suite asserts
  their hashes are unchanged.

Run:  python -m pytest career-ops/tests/test_application_inbox.py -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import application_inbox as ai  # noqa: E402
import gmail_readonly as gr  # noqa: E402
import tracker_writer as tw  # noqa: E402
import run_application_inbox_acceptance as acc  # noqa: E402

CFG = ai.load_config()
FIXTURE_INBOX = CAREER_OPS / "tests" / "fixtures" / "application-inbox"
PROFILES = ai.load_profiles(CFG)
REGIONS = list(PROFILES["regions"])


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def synthetic_index() -> dict:
    """A canonical index in the production shape, built from synthetic rows.

    Uses the production ``normalize_row`` / ``index_rows`` so the fixture cannot
    drift from the real index-building code.
    """
    rows_by_region = {
        "uk": [
            ai.normalize_row("uk", 10, id="J10", company="Northwind Analytics Ltd",
                             title="Security Analyst",
                             url="https://jobs.example.test/northwind/security-analyst",
                             application_status="To Review"),
            ai.normalize_row("uk", 11, id="J11", company="Contoso Security",
                             title="SOC Analyst Level 1",
                             url="https://jobs.example.test/contoso/soc-analyst",
                             application_status="Applied"),
            ai.normalize_row("uk", 12, id="J2", company="Tiny Co", title="IT Support",
                             url="https://jobs.example.test/tiny/it-support",
                             application_status="To Review"),
        ],
        "singapore": [
            ai.normalize_row("singapore", 2, id="SG-GRAD-260909-01", company="PwC Singapore",
                             title="Cyber Audit Associate",
                             url="https://jobs.example.test/pwc/audit",
                             application_status="Pending"),
            ai.normalize_row("singapore", 3, id="SG-GRAD-260909-02", company="PwC Singapore",
                             title="Cyber Associate",
                             url="https://jobs.example.test/pwc/associate",
                             application_status="Pending"),
        ],
    }
    index: dict = {"regions": {}, "by_url": {}, "by_company": {}, "by_id": {}}
    for region, rows in rows_by_region.items():
        index["regions"][region] = {"region": region, "tracker": f"C:/tmp/{region}.xlsx",
                                    "available": True, "sha256": "synthetic", "rows": rows}
        ai.index_rows(rows, index)
    return index


def msg(subject: str, body: str, **kw) -> dict:
    base = {"message_id": "<t@example.test>", "thread_id": None,
            "received_at": "2026-09-23T00:00:00+00:00", "sender": "x@example.test",
            "recipients": "mukund@example.com", "subject": subject, "body": body,
            "source": "local_mailbox",
            "provenance": {"adapter": "local_mailbox", "file": "fixture",
                           "file_sha256": "x", "index": 0}}
    base.update(kw)
    return base


def ingest_messages(messages: list[dict], tmp_path: Path, cfg=None, index=None) -> dict:
    cfg = cfg or CFG
    collected = {"ok": True, "adapter": "local_mailbox", "evidence_mode": "fixture",
                 "inbox": "synthetic", "files": [], "counts": {"files": 0, "messages": len(messages)},
                 "messages": messages,
                 "read_only_contract": {"network_used": False, "mailbox_mutations": 0}}
    root = ai.runtime_dir(cfg, tmp_path)
    index_ = index if index is not None else synthetic_index()
    real_build = ai.build_canonical_index
    ai.build_canonical_index = lambda *a, **k: index_          # noqa: ARG005
    try:
        result = ai.ingest(cfg, collected, root)
        summary = ai.build_summary(cfg, root)
    finally:
        ai.build_canonical_index = real_build
    return {"ingest": result, "summary": summary, "store": root}


def signals_of(root: Path) -> list[dict]:
    return ai._read_jsonl(ai.store_paths(root)["signals"])


def events_of(root: Path) -> list[dict]:
    return ai._read_jsonl(ai.store_paths(root)["status_events"])


# --------------------------------------------------------------------------- #
# configuration contract
# --------------------------------------------------------------------------- #

def test_config_kinds_are_complete_and_ordered():
    spec = CFG["classification"]
    kinds = set(spec["kinds"])
    assert kinds == set(spec["priority"]), "every kind must appear exactly once in priority"
    for kind, kdef in spec["kinds"].items():
        assert kdef["patterns"], kind
        assert {t for t, _ in kdef["patterns"]} <= {"strong", "weak"}, kind
        assert any(t == "strong" for t, _ in kdef["patterns"]), \
            f"{kind} must have at least one strong pattern or it can never decide a status"
        assert isinstance(kdef["implies_application"], bool)


def test_status_map_covers_every_region_and_kind():
    for region in REGIONS:
        assert region in CFG["status_map"], region
        assert set(CFG["status_map"][region]) == set(CFG["classification"]["kinds"]), region
        assert region in CFG["pre_application_states"], region


def test_status_map_values_are_in_each_regions_own_vocabulary():
    """Drift guard: a proposal can never name a status the tracker does not offer."""
    for region in REGIONS:
        allowed = acc.allowed_statuses(PROFILES, region)
        assert allowed, f"{region} has no application-status validation configured"
        for kind, target in CFG["status_map"][region].items():
            if target is None:
                continue
            assert target in allowed, f"{region}/{kind}: '{target}' not in {allowed}"


def test_pre_application_states_are_real_statuses():
    for region in REGIONS:
        allowed = set(acc.allowed_statuses(PROFILES, region))
        for state in CFG["pre_application_states"][region]:
            assert state in allowed, f"{region}: '{state}' is not a configured status"


def test_owner_action_kinds_cover_every_kind_plus_unknown():
    for kind in list(CFG["classification"]["kinds"]) + ["unknown"]:
        assert kind in CFG["owner_action_kinds"], kind


def test_blocked_actions_cover_every_mailbox_mutation():
    blocked = {a.casefold() for a in CFG["blocked_actions"]}
    for action in ("send", "reply", "forward", "archive", "delete", "trash", "move",
                   "mark_read", "label_apply", "mark_spam", "unsubscribe"):
        assert action in blocked, action


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("subject,body,expected", [
    ("Application received", "Thank you for applying to Example Ltd.", "application_acknowledgement"),
    ("Your application", "We have received your application.", "application_acknowledgement"),
    ("Outcome", "Unfortunately, we will not be proceeding with your application.", "rejection"),
    ("Invitation", "We would like to invite you for an interview.", "interview_invite"),
    ("Assessment", "We would like to invite you to complete an assessment.", "assessment_invite"),
    ("Documents", "Please provide your notice period.", "follow_up_request"),
    ("Hello", "I came across your profile and am reaching out about a role.", "recruiter_outreach"),
    ("Hello", "We are pleased to offer you the position.", "offer"),
])
def test_classification_of_clear_signals(subject, body, expected):
    assert ai.classify_message(subject, body, CFG)["kind"] == expected


def test_rejection_outranks_acknowledgement_in_the_same_message():
    cls = ai.classify_message("Outcome of your application",
                              "Thank you for applying. Unfortunately, we will not be "
                              "proceeding with your application.", CFG)
    assert cls["kind"] == "rejection"
    assert cls["ambiguous"] is False


def test_contradictory_strong_signals_are_ambiguous_and_not_guessed():
    cls = ai.classify_message("Your application",
                              "We are pleased to offer you the position. Unfortunately, we "
                              "will not be proceeding with your application.", CFG)
    assert cls["kind"] == "unknown"
    assert cls["ambiguous"] is True
    assert cls["requires_human_review"] is True
    assert cls["contradictions"], "the contradiction must be recorded as evidence"
    assert "contradictory" in cls["basis"]


def test_weak_only_matches_never_decide_a_status():
    cls = ai.classify_message("Weekly newsletter",
                              "We are hiring across many teams. Our talent acquisition team "
                              "shares job offer highlights.", CFG)
    assert cls["kind"] == "unknown"
    assert cls["ambiguous"] is True
    assert "weak" in cls["basis"]


def test_unmatched_text_stays_unknown_and_is_not_flagged_ambiguous():
    cls = ai.classify_message("Checking in", "Let me know your thoughts.", CFG)
    assert cls["kind"] == "unknown"
    assert cls["ambiguous"] is False
    assert cls["requires_human_review"] is True


def test_quoted_reply_history_is_removed_before_classification():
    text = (FIXTURE_INBOX / "quoted-reply.eml").read_text(encoding="utf-8")
    doc = ai.parse_file(FIXTURE_INBOX / "quoted-reply.eml", CFG)
    body = doc["messages"][0]["body"]
    cls = ai.classify_message(doc["messages"][0]["subject"], body, CFG)
    # the visible reply carries no status phrase; the quoted acknowledgement must not be used
    assert cls["kind"] == "unknown"
    assert cls["quoted_content_removed"] is True
    assert "thank you for applying" not in ai.normalize_text(ai.strip_quoted(body)).casefold()
    assert text  # fixture read


def test_classification_is_case_and_whitespace_insensitive():
    a = ai.classify_message("THANK YOU FOR APPLYING", "We have RECEIVED your    application.", CFG)
    b = ai.classify_message("thank you for applying", "we have received your application.", CFG)
    assert a["kind"] == b["kind"] == "application_acknowledgement"


def test_recruiter_outreach_does_not_imply_an_application():
    assert CFG["classification"]["kinds"]["recruiter_outreach"]["implies_application"] is False
    assert CFG["classification"]["kinds"]["rejection"]["implies_application"] is True


def test_classification_records_which_phrases_matched():
    cls = ai.classify_message("", "Thank you for applying.", CFG)
    hits = cls["matched"]["application_acknowledgement"]
    assert {"tier": "strong", "phrase": "thank you for applying"} in hits


# --------------------------------------------------------------------------- #
# parsing local mailbox formats
# --------------------------------------------------------------------------- #

def test_jsonl_parser_reads_every_fixture_message_with_line_provenance():
    doc = ai.parse_file(FIXTURE_INBOX / "messages.jsonl", CFG)
    assert len(doc["messages"]) == 11
    assert doc["messages"][0]["provenance"]["line"] == 1
    assert doc["messages"][0]["message_id"] == "<fixture-ack-001@example.com>"


def test_gmail_api_json_export_is_parsed_including_base64_body_and_headers():
    doc = ai.parse_file(FIXTURE_INBOX / "gmail-export.json", CFG)
    assert len(doc["messages"]) == 2
    first = doc["messages"][0]
    assert first["provenance"]["gmail_message_id"] == "fixturegmail0001"
    assert first["provenance"]["gmail_thread_id"] == "fixturethread0001"
    assert first["sender"] == "no-reply@example-ats.test"
    assert "thank you for applying" in first["body"].casefold()
    assert first["received_at"].startswith("2026-09-")
    assert ai.classify_message(first["subject"], first["body"], CFG)["kind"] == \
        "application_acknowledgement"


def test_gmail_payload_falls_back_to_html_when_no_plain_part_exists():
    payload = {"mimeType": "text/html",
               "body": {"data": "PHA+VGhhbmsgeW91IGZvciBhcHBseWluZy48L3A+"}}
    out = ai.parse_gmail_api_message({"id": "x", "payload": payload})
    assert "Thank you for applying" in out["body"]


def test_csv_parser_reads_messages():
    doc = ai.parse_file(FIXTURE_INBOX / "messages.csv", CFG)
    assert len(doc["messages"]) == 2
    assert ai.classify_message(doc["messages"][0]["subject"], doc["messages"][0]["body"],
                               CFG)["kind"] == "rejection"


def test_eml_parser_reads_message_envelope():
    doc = ai.parse_file(FIXTURE_INBOX / "quoted-reply.eml", CFG)
    assert doc["messages"][0]["sender"] == "recruitment@northwind.test"
    assert doc["messages"][0]["message_id"] == "<fixture-eml-0001@example.com>"


def test_free_text_files_are_skipped_not_guessed(tmp_path):
    doc = ai.parse_file(FIXTURE_INBOX / "notes.md", CFG)
    assert doc["messages"] == []
    assert "no message envelope" in doc["skipped"]


def test_unsupported_extension_is_skipped(tmp_path):
    p = tmp_path / "thing.xyz"
    p.write_text("hello", encoding="utf-8")
    doc = ai.parse_file(p, CFG)
    assert doc["messages"] == []
    assert "unsupported extension" in doc["skipped"]


def test_collect_local_mailbox_reports_read_only_contract_and_skips():
    doc = ai.collect_local_mailbox(CFG, FIXTURE_INBOX)
    assert doc["ok"] is True
    assert doc["counts"]["messages"] == 16
    assert doc["counts"]["skipped_files"] == 1
    roc = doc["read_only_contract"]
    assert roc["network_used"] is False
    assert roc["mailbox_mutations"] == 0
    assert roc["messages_sent"] == 0


def test_collect_local_mailbox_reports_a_missing_inbox_truthfully():
    doc = ai.collect_local_mailbox(CFG, Path("C:/definitely/not/here"))
    assert doc["ok"] is False
    assert "inbox not found" in doc["reason"]


# --------------------------------------------------------------------------- #
# matching against canonical state
# --------------------------------------------------------------------------- #

def test_posting_url_match_is_high_confidence():
    m = ai.match_signal("See https://jobs.example.test/contoso/soc-analyst for details.",
                        synthetic_index(), CFG)
    assert m["status"] == "matched"
    assert m["confidence"] == "high"
    assert m["basis"] == "posting_url_in_message"
    assert m["row"]["id"] == "J11"


def test_tracking_parameters_do_not_break_a_url_match():
    m = ai.match_signal("https://jobs.example.test/contoso/soc-analyst?utm_source=x&ref=y",
                        synthetic_index(), CFG)
    assert m["status"] == "matched" and m["row"]["id"] == "J11"


def test_explicit_canonical_reference_matches_and_trailing_punctuation_is_ignored():
    m = ai.match_signal("Your application reference is SG-GRAD-260909-01.",
                        synthetic_index(), CFG)
    assert m["status"] == "matched" and m["confidence"] == "high"
    assert m["basis"] == "explicit_canonical_reference_in_message"
    assert m["row"]["id"] == "SG-GRAD-260909-01"


def test_two_character_id_is_never_matched_by_reference():
    m = ai.match_signal("Your reference is J2.", synthetic_index(), CFG)
    assert m["status"] != "matched" or m["row"]["id"] != "J2"


def test_a_bare_number_in_prose_is_never_a_reference():
    m = ai.match_signal("We received 26090901 applications this year.", synthetic_index(), CFG)
    assert m["status"] == "unmatched"


def test_company_and_title_agreement_is_medium_confidence():
    m = ai.match_signal("Re: Security Analyst role at Northwind Analytics Ltd", synthetic_index(), CFG)
    assert m["status"] == "matched" and m["confidence"] == "medium"
    assert m["basis"] == "company_and_title_agreement"
    assert m["row"]["id"] == "J10"


def test_company_only_match_is_ambiguous_and_never_picks_a_row():
    m = ai.match_signal("Thank you for applying to PwC Singapore.", synthetic_index(), CFG)
    assert m["status"] == "ambiguous"
    assert m["row"] is None
    assert m["requires_human_review"] is True
    assert len(m["candidates"]) == 2


def test_company_mention_without_title_agreement_is_ambiguous():
    m = ai.match_signal("Northwind Analytics Ltd sent a newsletter about payroll.", synthetic_index(), CFG)
    assert m["status"] == "ambiguous"
    assert m["row"] is None


def test_unmatched_message_reports_why_and_invents_nothing():
    m = ai.match_signal("Thank you for applying to Unrelated Employer Limited.", synthetic_index(), CFG)
    assert m["status"] == "unmatched"
    assert m["candidates"] == []
    assert m["row"] is None
    assert "no canonical reference" in m["basis"]


def test_unmatched_url_is_reported_as_such():
    m = ai.match_signal("https://jobs.example.test/nowhere/role thanks for applying",
                        synthetic_index(), CFG)
    assert m["status"] == "unmatched"
    assert "match no canonical row" in m["basis"]


def test_very_short_company_keys_are_not_used_for_matching():
    index = synthetic_index()
    index["regions"]["uk"]["rows"].append(
        ai.normalize_row("uk", 13, id="J13", company="7X", title="Security Associate",
                         url="https://jobs.example.test/7x/associate",
                         application_status="To Review"))
    ai.index_rows([index["regions"]["uk"]["rows"][-1]], index)
    m = ai.match_signal("A note about 7x and other things", index, CFG)
    assert m["status"] == "unmatched"


def test_extract_urls_deduplicates_and_respects_the_limit():
    text = " ".join(f"https://x.test/{i}" for i in range(10)) + " https://x.test/0"
    urls = ai.extract_urls(text, limit=5)
    assert len(urls) == 5
    assert len(set(urls)) == 5


# --------------------------------------------------------------------------- #
# proposals
# --------------------------------------------------------------------------- #

def test_proposal_maps_to_the_regions_own_status():
    p = ai.proposal_for("rejection", "uk", "Applied", CFG)
    assert p["proposed_status"] == "Rejected"
    assert p["requires_owner_confirmation"] is False
    assert p["implied_application_not_yet_recorded"] is False


def test_proposal_is_none_where_the_region_has_no_equivalent_status():
    p = ai.proposal_for("rejection", "japan", "Pending", CFG)
    assert p["proposed_status"] is None
    assert p["proposal_state"] == "owner_decision_required"
    assert "no status that matches" in p["reason"]


def test_proposal_is_none_when_the_tracker_already_reflects_it():
    p = ai.proposal_for("rejection", "uk", "Rejected", CFG)
    assert p["proposed_status"] is None
    assert p["proposal_state"] == "already_reflected"


def test_pre_application_row_requires_owner_confirmation():
    p = ai.proposal_for("application_acknowledgement", "uk", "To Review", CFG)
    assert p["proposed_status"] == "Applied"
    assert p["requires_owner_confirmation"] is True
    assert p["implied_application_not_yet_recorded"] is True
    assert "owner must confirm" in p["reason"]


def test_non_application_signal_never_requires_confirmation():
    p = ai.proposal_for("recruiter_outreach", "uk", "Applied", CFG)
    assert p["proposed_status"] is None
    assert p["requires_owner_confirmation"] is False


# --------------------------------------------------------------------------- #
# ingest + idempotent store
# --------------------------------------------------------------------------- #

def test_ingest_stores_signals_events_and_state(tmp_path):
    m = msg("Outcome", "Unfortunately, we will not be proceeding with your application. "
                       "Reference J11.")
    out = ingest_messages([m], tmp_path)
    assert out["ingest"]["counts"]["new_signals"] == 1
    assert out["ingest"]["counts"]["status_events"] == 1
    events = events_of(out["store"])
    assert len(events) == 1
    assert events[0]["proposed_status"] == "Rejected"
    assert events[0]["state_written"] is False
    assert events[0]["authoritative_system"] == "excel"
    assert events[0]["row_id"] == "J11"


def test_replaying_the_same_mailbox_changes_nothing(tmp_path):
    m = msg("Outcome", "We will not be proceeding with your application. Reference J11.")
    first = ingest_messages([m], tmp_path)
    before = {p.name: ai.sha256_file(p) for p in first["store"].iterdir()
              if p.is_file() and p.name != "run-log.jsonl"}
    second = ingest_messages([m], tmp_path)
    after = {p.name: ai.sha256_file(p) for p in second["store"].iterdir()
             if p.is_file() and p.name != "run-log.jsonl"}
    assert before == after
    assert second["ingest"]["counts"]["new_signals"] == 0
    assert second["ingest"]["counts"]["already_ingested"] == 1
    assert second["ingest"]["counts"]["status_events"] == 0


def test_current_state_holds_no_run_timestamp_so_replay_is_stable(tmp_path):
    m = msg("Outcome", "We will not be proceeding with your application. Reference J11.")
    ingest_messages([m], tmp_path)
    state = json.loads((tmp_path / "current-state.json").read_text(encoding="utf-8"))
    blob = json.dumps(state)
    assert "generated_at" not in blob
    assert state["regions"]["uk"]["J11"]["proposed_status"] == "Rejected"


def test_unmatched_signal_goes_to_review_and_creates_nothing(tmp_path):
    m = msg("Thank you for applying", "Thank you for applying to Unrelated Employer Limited.")
    out = ingest_messages([m], tmp_path)
    assert out["ingest"]["counts"]["unmatched"] == 1
    assert out["ingest"]["counts"]["status_events"] == 0
    assert events_of(out["store"]) == []
    review = out["ingest"]["state"]["review_queue"]
    assert len(review) == 1
    assert review[0]["state_written"] is False
    assert "nothing invented" in review[0]["reason"]
    assert out["ingest"]["state"]["regions"] == {}


def test_every_stored_event_points_at_a_real_canonical_row(tmp_path):
    index = synthetic_index()
    known = {(r["region"], str(r["id"])) for reg in index["regions"].values() for r in reg["rows"]}
    messages = [
        msg("Acknowledgement", "Thank you for applying to Northwind Analytics Ltd. "
            "https://jobs.example.test/northwind/security-analyst"),
        msg("Rejection", "We will not be proceeding. Reference J11."),
        msg("Unknown", "Nothing relevant here at all."),
    ]
    out = ingest_messages(messages, tmp_path, index=index)
    for e in events_of(out["store"]):
        assert (e["region"], str(e["row_id"])) in known
    assert out["ingest"]["counts"]["status_events"] == 2


def test_matched_row_without_a_status_target_is_still_recorded_as_a_decision(tmp_path):
    # a matched row whose region has no equivalent status must not vanish silently
    index = synthetic_index()
    index["regions"]["singapore"]["rows"][0]["application_status"] = "Pending"
    m = msg("Interview invitation", "We would like to invite you for an interview. "
            "Reference SG-GRAD-260909-01.")
    cfg = json.loads(json.dumps(CFG))
    cfg["status_map"]["singapore"]["interview_invite"] = None
    out = ingest_messages([m], tmp_path, cfg=cfg, index=index)
    events = events_of(out["store"])
    assert len(events) == 1
    assert events[0]["proposed_status"] is None
    assert events[0]["event_kind"] == "owner_decision_required"
    assert out["ingest"]["counts"]["status_events"] == 0
    assert out["ingest"]["counts"]["no_status_events"] == 1


def test_owner_actions_are_derived_for_matched_and_unmatched_signals(tmp_path):
    index = synthetic_index()
    messages = [
        msg("Interview invitation", "We would like to invite you for an interview. "
            "Reference SG-GRAD-260909-01."),
        msg("Hello", "Nothing relevant here."),
    ]
    out = ingest_messages(messages, tmp_path, index=index)
    actions = out["summary"]["owner_actions"]
    assert len(actions) == 2
    kinds = {a["kind"] for a in actions}
    assert kinds == {"interview_invite", "unknown"}
    for a in actions:
        assert a["reply_sent"] is False
        assert a["never_performed_by_this_monitor"] is True
    matched = [a for a in actions if a["match_status"] == "matched"][0]
    assert matched["row_id"] == "SG-GRAD-260909-01"
    assert matched["owner_action_required"] is True


def test_rejection_needs_no_reply_but_is_still_recorded(tmp_path):
    m = msg("Outcome", "We will not be proceeding with your application. Reference J11.")
    out = ingest_messages([m], tmp_path)
    summary = out["summary"]
    assert summary["counts"]["owner_actions_required"] == 0
    assert summary["counts"]["signals_recorded_with_no_action_needed"] == 1
    recorded = summary["no_action_required"][0]
    assert recorded["kind"] == "rejection"
    assert recorded["owner_action_required"] is False
    assert recorded["reply_sent"] is False


def test_signal_id_is_stable_and_content_sensitive():
    a = msg("Thank you for applying", "Thank you for applying to Example Ltd.")
    b = dict(a)
    c = dict(a, body="A different body entirely.")
    assert ai.signal_id(a, {}) == ai.signal_id(b, {})
    assert ai.signal_id(a, {}) != ai.signal_id(c, {})


def test_summary_reports_zero_mail_and_proposals_only(tmp_path):
    m = msg("Acknowledgement", "Thank you for applying to Northwind Analytics Ltd. "
                               "Reference J10.")
    out = ingest_messages([m], tmp_path)
    safety = out["summary"]["safety"]
    assert safety["emails_sent"] == 0
    assert safety["replies_sent"] == 0
    assert safety["mailbox_mutations"] == 0
    assert safety["workbooks_written"] == 0
    assert safety["applications_created"] == 0
    assert safety["state_written_to_canonical_workbook"] is False
    assert safety["excel_authoritative"] is True
    assert out["summary"]["counts"]["status_changes_ready_for_owner"] == 1


# --------------------------------------------------------------------------- #
# action guard
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("action", ["send", "reply", "forward", "archive", "delete", "move",
                                    "mark_read", "label_apply", "mark_spam", "unsubscribe",
                                    "apply", "attachment_download"])
def test_guard_refuses_every_mailbox_mutation(action, tmp_path):
    res = ai.guard_action(CFG, action, tmp_path)
    assert res["allowed"] is False
    assert res["owner_gated"] is True
    assert res["performed"] is False


@pytest.mark.parametrize("action", ["ingest", "summary", "status", "adapters"])
def test_guard_allows_read_and_propose_paths(action, tmp_path):
    assert ai.guard_action(CFG, action, tmp_path)["allowed"] is True


def test_guard_logs_every_refusal(tmp_path):
    ai.guard_action(CFG, "send", tmp_path)
    log = tmp_path / "action-gate-log.jsonl"
    assert log.exists()
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert entries and entries[0]["action"] == "send" and entries[0]["owner_gated"] is True


# --------------------------------------------------------------------------- #
# gmail read-only adapter (interface + refusal only: no credentials exist)
# --------------------------------------------------------------------------- #

def test_gmail_adapter_reports_unavailable_without_credentials(tmp_path):
    cfg = dict(CFG["adapters"]["gmail_readonly"])
    cfg["credential_path"] = str(tmp_path / "missing-credentials.json")
    cfg["token_path"] = str(tmp_path / "missing-token.json")
    status = gr.adapter_status(cfg)
    assert status["available"] is False
    assert status["credentials_present"] is False
    assert status["owner_action_required"] is True
    assert status["verification"] == "UNVERIFIED"
    assert status["required_scope"] == "https://www.googleapis.com/auth/gmail.readonly"


def test_gmail_fetch_refuses_without_credentials_and_uses_no_network(tmp_path):
    cfg = dict(CFG["adapters"]["gmail_readonly"])
    cfg["credential_path"] = str(tmp_path / "missing-credentials.json")
    cfg["token_path"] = str(tmp_path / "missing-token.json")
    res = gr.fetch(cfg, limit=5)
    assert res["ok"] is False
    assert res["available"] is False
    assert res["network_used"] is False
    assert res["messages"] == []
    assert res["owner_action_required"] is True


def test_gmail_adapter_status_never_reports_credential_contents(tmp_path):
    cred = tmp_path / "credentials.json"
    cred.write_text(json.dumps({"installed": {"client_secret": "TOP-SECRET-VALUE"}}),
                    encoding="utf-8")
    cfg = dict(CFG["adapters"]["gmail_readonly"])
    cfg["credential_path"] = str(cred)
    cfg["token_path"] = str(tmp_path / "missing-token.json")
    blob = json.dumps(gr.adapter_status(cfg))
    assert "TOP-SECRET-VALUE" not in blob
    assert "client_secret" not in blob


def test_gmail_credential_path_can_come_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_GMAIL_CREDENTIALS", str(tmp_path / "env-credentials.json"))
    assert gr.credential_path(CFG["adapters"]["gmail_readonly"]) == \
        tmp_path / "env-credentials.json"


def test_collect_gmail_reports_the_refusal_without_network(tmp_path):
    cfg = json.loads(json.dumps(CFG))
    cfg["adapters"]["gmail_readonly"]["credential_path"] = str(tmp_path / "nope.json")
    cfg["adapters"]["gmail_readonly"]["token_path"] = str(tmp_path / "nope2.json")
    out = ai.collect_gmail(cfg, limit=1)
    assert out["ok"] is False
    assert out["read_only_contract"]["network_used"] is False
    assert out["read_only_contract"]["mailbox_mutations"] == 0


# --------------------------------------------------------------------------- #
# capability boundary
# --------------------------------------------------------------------------- #

def test_ingest_module_imports_no_network_or_mail_library():
    src = (CAREER_OPS / "application_inbox.py").read_text(encoding="utf-8")
    imports = "\n".join(line for line in src.splitlines()
                        if re.match(r"^\s*(import|from)\s", line))
    for banned in ("urllib", "requests", "socket", "http.client", "httpx", "aiohttp",
                   "webbrowser", "playwright", "selenium", "imaplib", "smtplib", "poplib"):
        assert not re.search(rf"\b{re.escape(banned)}\b", imports), \
            f"{banned} must not be imported on the read-only ingest path"


def test_config_declares_the_absent_capabilities():
    joined = " ".join(CFG["not_performed"]).casefold()
    for phrase in ("send", "archive", "delete", "login", "workbook", "application record"):
        assert phrase in joined, phrase


def test_config_never_declares_a_send_capability():
    blob = json.dumps(CFG).casefold()
    assert "send_message" not in blob
    assert "smtp" not in blob


# --------------------------------------------------------------------------- #
# against the real canonical workbooks (read-only)
# --------------------------------------------------------------------------- #

needs_workbooks = pytest.mark.skipif(
    not all(Path(PROFILES["regions"][r]["tracker"]).exists() for r in REGIONS),
    reason="canonical regional workbooks are not present on this machine")


@needs_workbooks
def test_canonical_index_reads_real_rows_without_writing():
    before = {r: acc.ai.sha256_file(Path(PROFILES["regions"][r]["tracker"])) for r in REGIONS}
    index = ai.build_canonical_index(CFG, PROFILES)
    after = {r: acc.ai.sha256_file(Path(PROFILES["regions"][r]["tracker"])) for r in REGIONS}
    assert before == after
    for region in REGIONS:
        rows = index["regions"][region]["rows"]
        assert rows, region
        assert all(r["company_key"] for r in rows), region
    assert index["by_url"] and index["by_id"] and index["by_company"]


@needs_workbooks
def test_no_canonical_row_status_is_outside_its_region_vocabulary():
    index = ai.build_canonical_index(CFG, PROFILES)
    for region in REGIONS:
        allowed = set(acc.allowed_statuses(PROFILES, region))
        for row in index["regions"][region]["rows"]:
            status = row.get("application_status")
            if status in (None, ""):
                continue
            assert str(status) in allowed, f"{region} {row['id']}: '{status}'"


@needs_workbooks
def test_running_the_monitor_does_not_touch_the_workbooks_or_default_store(tmp_path):
    before = {r: acc.ai.sha256_file(Path(PROFILES["regions"][r]["tracker"])) for r in REGIONS}
    default_store = Path(ai.CONTROL_PLANE / CFG["runtime_dir"])
    existed = default_store.exists()
    collected = ai.collect_local_mailbox(CFG, FIXTURE_INBOX)
    ai.ingest(CFG, collected, ai.runtime_dir(CFG, tmp_path))
    after = {r: acc.ai.sha256_file(Path(PROFILES["regions"][r]["tracker"])) for r in REGIONS}
    assert before == after
    assert default_store.exists() == existed


@needs_workbooks
def test_acceptance_runner_passes_on_this_machine(tmp_path):
    out_dir = tmp_path / "evidence"
    rc = acc.main(["--out-dir", str(out_dir)])
    ev = json.loads((out_dir / "acceptance.json").read_text(encoding="utf-8"))
    assert rc == 0, [c for c in ev["checks"] if not c["ok"]]
    assert ev["verdict"] == "PASS"
    assert ev["safety"]["canonical_workbooks_unchanged"] is True
    assert ev["idempotency"]["store_byte_identical"] is True
    assert ev["proposals"]["state_written_to_workbook"] == 0
