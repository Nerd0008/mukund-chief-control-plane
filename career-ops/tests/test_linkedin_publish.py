#!/usr/bin/env python3
"""Offline tests for the owner-approved LinkedIn publishing path.

No test in this file touches the network, the Windows Credential Manager, the
real publish ledger, or any LinkedIn account. The HTTP transport, the credential
store and the ledger path are all injected:

* ``auth.presence``/``auth.resolve`` are patched so a fake "configured" account
  can be simulated without storing anything;
* ``linkedin_publish.publish_post``/``resolve_person_urn`` take a stub transport;
* the ledger is a temp file.

The last class asserts the *negative* guarantees — that the guards still refuse,
that a 4xx is never retried, and that no secret ever reaches the output or the
ledger — because those are the properties that make the integration safe to
hand to an owner-approved action.

Run:  python -m pytest career-ops/tests/test_linkedin_publish.py -v
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import pytest

CAREER_OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAREER_OPS))

import linkedin_auth as auth  # noqa: E402
import linkedin_publish as lp  # noqa: E402

FAKE_TOKEN = "FAKE-ACCESS-TOKEN-DO-NOT-LOG"
FAKE_SECRET = "FAKE-CLIENT-SECRET-DO-NOT-LOG"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def drafts_file(tmp_path: Path, body: str = "Notes from a recent project: example.",
                *, blocked: bool = False, verdict: str | None = "pass",
                news_verdict: str | None = "pass") -> Path:
    """A draft artefact in the same shape `linkedin_workflow.py draft` writes.

    ``news_verdict`` defaults to a provenance-bearing ``pass`` so the flow tests
    exercise the publish path. Pass ``None`` to omit the news-claims record, or
    another verdict to exercise the refusal.
    """
    post = {"kind": "post", "topic": "Project note", "status": "draft_unsent",
            "publish_requires": "explicit owner authorization", "body": body,
            "blocked": blocked,
            "sources": [{"source": "cv.md", "line": 10, "section": "Profile",
                         "text": "canonical line"}]}
    if verdict is not None:
        post["fact_gate"] = {"verdict": verdict, "invented": [], "unsupportedFacts": [],
                             "forbidden": [], "available": True, "exit_code": 0}
    if news_verdict is not None:
        post["news_fact_gate"] = {
            "gate_name": "linkedin-news-claims", "gate_version": 1,
            "ran_at": "2026-09-24T22:00:00+00:00",
            "body_sha256": lp.sha256_text(body.strip()),
            "verdict": news_verdict, "unsupported_claims": [],
        }
    p = tmp_path / "drafts.json"
    p.write_text(json.dumps({
        "ok": True,
        "generated_at": "2026-09-24T22:00:00+00:00",
        "drafts": [
            {"kind": "profile", "status": "draft_unsent", "headline": "example"},
            post,
            {"kind": "outreach", "subtype": "recruiter", "status": "draft_unsent",
             "recipient": None, "body": "Hello,\n\nI am looking for a first role."},
        ],
    }), encoding="utf-8")
    return p


def run(fn, argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = fn(argv)
    return code, json.loads(buf.getvalue())


def configured():
    """Patch the credential store as if the owner had completed OAuth setup."""
    presence = {k: {"target": auth.CRED_TARGETS[k], "env_var": auth.ENV_VARS[k],
                    "present": True, "source": "credential_manager"}
                for k in auth.CRED_TARGETS}
    values = {"client_id": "fake-client-id", "client_secret": FAKE_SECRET,
              "refresh_token": "fake-refresh-token", "access_token": FAKE_TOKEN}
    return (
        mock.patch.object(auth, "presence", return_value=presence),
        mock.patch.object(auth, "resolve", side_effect=lambda p: (values[p], "credential_manager")),
        mock.patch.object(auth, "access_token_expiry", return_value="2099-12-02T00:26:11Z"),
    )


class StubTransport:
    """A recordable transport. Never touches a socket."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def __call__(self, method, url, *, headers=None, data=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "data": data})
        if not self.script:
            raise AssertionError(f"unexpected extra call: {method} {url}")
        return self.script.pop(0)


def ok_post(headers=None):
    return {"status": 201, "headers": headers or {"x-restli-id": "urn:li:share:7000000001"},
            "body": ""}


# --------------------------------------------------------------------------- #
# guards: nothing is sent until the owner approves the exact bytes
# --------------------------------------------------------------------------- #

class TestPublishGuards:
    def test_plan_refuses_without_the_owner_approval_flag(self, tmp_path):
        d = drafts_file(tmp_path)
        code, out = run(lp.main, ["plan", "--drafts", str(d), "--ledger",
                                  str(tmp_path / "ledger.jsonl")])
        self_checks = {c["check"]: c for c in out["checks"]}
        assert self_checks["owner_approval_flag"]["passed"] is False
        assert self_checks["owner_approval_matches_bytes"]["passed"] is False
        assert code == 1 and out["ok"] is False
        assert out["network_calls_spent"] == 0
        assert not (tmp_path / "ledger.jsonl").exists()

    def test_plan_refuses_when_confirm_token_does_not_match_the_body(self, tmp_path):
        d = drafts_file(tmp_path)
        with configured()[1]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", "0" * 64, "--ledger",
                                      str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["owner_approval_flag"]["passed"] is True
        assert checks["owner_approval_matches_bytes"]["passed"] is False
        assert code == 1

    def test_plan_refuses_anything_that_is_not_a_post(self, tmp_path):
        d = drafts_file(tmp_path)
        code, out = run(lp.main, ["plan", "--drafts", str(d), "--kind", "outreach",
                                  "--approve-publish", "--confirm-token", "0" * 64])
        assert code == 1
        assert out["blockers"][0]["check"] == "kind_supported"
        assert "message" in lp.STILL_BLOCKED_ACTIONS
        assert out["network_calls_spent"] == 0

    def test_plan_passes_and_spends_nothing_when_approved_and_configured(self, tmp_path):
        d = drafts_file(tmp_path)
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--ledger",
                                      str(tmp_path / "ledger.jsonl")])
        assert out["ok"] is True, out
        assert code == 0
        assert out["body_sha256"] == body_sha
        assert out["network_calls_spent"] == 0
        assert out["external_actions_taken"] == []
        assert out["dry_run_possible"] is True
        assert not (tmp_path / "ledger.jsonl").exists()

    def test_plan_reports_missing_credentials_without_inventing_them(self, tmp_path):
        d = drafts_file(tmp_path)
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        # Isolate missing-credential coverage from the owner's real credential store.
        with mock.patch.object(auth, 'read_secret', return_value=None), mock.patch.dict(os.environ, {}, clear=True):
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--ledger",
                                      str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["oauth_credentials_present"]["passed"] is False
        assert "no usable access token" in checks["oauth_credentials_present"]["detail"]
        assert code == 1

    def test_a_draft_blocked_by_the_fact_gate_is_never_publishable(self, tmp_path):
        d = drafts_file(tmp_path, blocked=True, verdict="fail")
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--ledger",
                                      str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_review"]["passed"] is False
        assert out["fact_gate_verdict"] == "fail"
        assert out["draft_blocked_flag"] is True
        assert code == 1

    def test_a_draft_with_no_recorded_review_is_refused_not_assumed_pass(self, tmp_path):
        """Silence is not evidence the text was checked.

        A draft carrying no gate record at all used to be treated as reviewed.
        It is now refused, and the report says plainly that nothing verified it.
        """
        d = drafts_file(tmp_path, verdict=None)
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--ledger",
                                      str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_review"]["passed"] is False
        assert "nothing verified the author's own claims" in checks["draft_passed_review"]["detail"]
        assert out["fact_gate_verdict"] is None
        assert code == 1


# --------------------------------------------------------------------------- #
# the news-claims gate is enforced, not decorative
# --------------------------------------------------------------------------- #

def news_gate(body: str, verdict: str, *, gate_name: str = "linkedin-news-claims",
              sha: str | None = None, reason: str = "") -> dict:
    """A news-claims gate record, with real provenance over ``body`` by default."""
    import hashlib
    return {
        "gate_name": gate_name,
        "gate_version": 1,
        "ran_at": "2026-10-03T00:00:00+00:00",
        "body_sha256": sha if sha is not None else hashlib.sha256(
            body.strip().encode("utf-8")).hexdigest(),
        "verdict": verdict,
        "reason": reason,
        "unsupported_claims": [] if verdict == "pass" else [{"claim": "x"}],
    }


def approved_file(tmp_path: Path, body: str, news: dict | None,
                  *, personal: str = "pass", name: str = "approved.json") -> Path:
    """A single-post approved artefact, the shape create_approved_drafts.py writes."""
    doc = {
        "post_text": body,
        "news_fact_gate": news,
        "personal_fact_gate": {"verdict": personal, "gate_name": "verify-cv-facts",
                               "version": 1},
        "topic": {"title": "t", "sources": []},
        "confirm_token": lp.sha256_text(body),
        "approved": True,
    }
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


class TestNewsClaimsGate:
    def test_flat_approved_artefact_is_readable(self, tmp_path):
        """The Oct 6-8 artefact shape must be selectable, not a LookupError."""
        body = "A checked post body."
        d = approved_file(tmp_path, body, news_gate(body, "pass"))
        doc = lp.load_drafts(d)
        draft = lp.select_draft(doc, "post", 0)
        assert lp.draft_body(draft) == body

    def test_a_provenance_bearing_pass_is_accepted(self, tmp_path):
        body = "A checked post body."
        d = approved_file(tmp_path, body, news_gate(body, "pass"))
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", lp.sha256_text(body),
                                      "--ledger", str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_news_claims"]["passed"] is True
        assert out["news_fact_gate_verdict"] == "pass"
        assert code == 0

    def test_a_blocked_news_gate_is_refused(self, tmp_path):
        """The defect that let a blocked post stay publishable."""
        body = "Data centres consume millions of gallons of water every day."
        d = approved_file(tmp_path, body, news_gate(body, "block"))
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", lp.sha256_text(body),
                                      "--ledger", str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_news_claims"]["passed"] is False
        assert out["news_fact_gate_verdict"] == "block"
        assert code == 1

    def test_an_ungated_news_record_is_refused(self, tmp_path):
        body = "A post whose claims were never verified."
        d = approved_file(tmp_path, body,
                          news_gate(body, "ungated", reason="no source text could be read"))
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", lp.sha256_text(body),
                                      "--ledger", str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_news_claims"]["passed"] is False
        assert "ungated" in checks["draft_passed_news_claims"]["detail"]
        assert code == 1

    def test_a_missing_news_record_is_refused(self, tmp_path):
        body = "A post with no news gate record at all."
        d = approved_file(tmp_path, body, None)
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", lp.sha256_text(body),
                                      "--ledger", str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_news_claims"]["passed"] is False
        assert "not checked" in checks["draft_passed_news_claims"]["detail"]
        assert code == 1

    def test_a_forged_gate_name_is_refused(self, tmp_path):
        """A hand-written verdict cannot name the gate, so it is not a verdict."""
        body = "A post with a hand-written pass."
        forged = {"verdict": "pass", "gate_name": "some-other-gate"}
        d = approved_file(tmp_path, body, forged)
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", lp.sha256_text(body),
                                      "--ledger", str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_news_claims"]["passed"] is False
        assert code == 1

    def test_a_pass_for_different_text_is_refused(self, tmp_path):
        """The approved action must name the approved bytes."""
        body = "The text that will actually be published."
        stale = news_gate(body, "pass", sha=lp.sha256_text("some earlier draft"))
        d = approved_file(tmp_path, body, stale)
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", lp.sha256_text(body),
                                      "--ledger", str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_news_claims"]["passed"] is False
        assert code == 1


# --------------------------------------------------------------------------- #
# dry-run and the real path, over an injected transport
# --------------------------------------------------------------------------- #

class TestPublishFlow:
    def test_dry_run_sends_nothing_and_records_a_dry_run(self, tmp_path):
        d = drafts_file(tmp_path)
        ledger = tmp_path / "ledger.jsonl"
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        transport = StubTransport([])
        with configured()[0], configured()[1], configured()[2], \
                mock.patch.object(auth, "urllib_transport", transport), \
                mock.patch.object(lp.auth, "urllib_transport", transport):
            code, out = run(lp.main, ["publish", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--dry-run",
                                      "--ledger", str(ledger)])
        assert code == 0 and out["dry_run"] is True and out["performed"] is False
        assert transport.calls == []
        assert out["external_actions_taken"] == []
        rows = lp.read_ledger(ledger)
        assert len(rows) == 1 and rows[0]["result"] == "dry_run"

    def test_real_publish_logs_urn_timestamp_and_result(self, tmp_path):
        d = drafts_file(tmp_path)
        ledger = tmp_path / "ledger.jsonl"
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        transport = StubTransport([
            {"status": 200, "headers": {}, "body": json.dumps({"sub": "abc123"})},
            ok_post()])
        with configured()[0], configured()[1], configured()[2], \
                mock.patch.object(auth, "urllib_transport", transport):
            code, out = run(lp.main, ["publish", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--no-backoff",
                                      "--ledger", str(ledger)])
        assert code == 0, out
        assert out["performed"] is True
        assert out["post_urn"] == "urn:li:share:7000000001"
        assert out["post_url"].startswith("https://www.linkedin.com/feed/update/")
        assert out["external_actions_taken"] == ["linkedin.post"]
        assert out["timestamp"]
        rows = lp.read_ledger(ledger)
        published = [r for r in rows if r["result"] == "published"]
        assert len(published) == 1
        assert published[0]["body_sha256"] == body_sha
        assert published[0]["http_status"] == 201
        assert transport.calls[0]["method"] == "GET"
        assert transport.calls[1]["method"] == "POST"
        payload = json.loads(transport.calls[1]["data"])
        assert payload["author"] == "urn:li:person:abc123"
        assert payload["lifecycleState"] == "PUBLISHED"
        assert payload["distribution"]["feedDistribution"] == "MAIN_FEED"

    def test_duplicate_prevention_refuses_a_repeat_unless_allowed(self, tmp_path):
        d = drafts_file(tmp_path)
        ledger = tmp_path / "ledger.jsonl"
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        ledger.write_text(json.dumps({"at": "2026-09-24T22:10:00+00:00",
                                      "result": "published", "body_sha256": body_sha,
                                      "post_urn": "urn:li:share:1"}) + "\n", encoding="utf-8")
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["publish", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--ledger", str(ledger)])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["not_a_duplicate"]["passed"] is False
        assert code == 1
        assert out["performed"] is False
        assert out["external_actions_taken"] == []

    def test_allow_duplicate_bypasses_the_guard_deliberately(self, tmp_path):
        d = drafts_file(tmp_path)
        ledger = tmp_path / "ledger.jsonl"
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        ledger.write_text(json.dumps({"at": "2026-09-24T22:10:00+00:00",
                                      "result": "published", "body_sha256": body_sha}) + "\n",
                          encoding="utf-8")
        with configured()[0], configured()[1], configured()[2]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--allow-duplicate",
                                      "--ledger", str(ledger)])
        assert code == 0 and out["blockers"] == []


# --------------------------------------------------------------------------- #
# bounded retries, and what is deliberately never retried
# --------------------------------------------------------------------------- #

class TestRetryPolicy:
    def test_transient_429_is_retried_then_succeeds(self):
        transport = StubTransport([{"status": 429, "headers": {}, "body": ""},
                                   {"status": 429, "headers": {}, "body": ""},
                                   ok_post()])
        res = lp.publish_post(FAKE_TOKEN, "urn:li:person:x", "hello",
                              transport=transport, max_retries=2, sleep=lambda s: None)
        assert res["ok"] is True
        assert [a["status"] for a in res["attempts"]] == [429, 429, 201]
        assert len(transport.calls) == 3

    def test_retries_are_bounded_and_then_reported(self):
        transport = StubTransport([{"status": 503, "headers": {}, "body": "unavailable"}] * 3)
        res = lp.publish_post(FAKE_TOKEN, "urn:li:person:x", "hello",
                              transport=transport, max_retries=2, sleep=lambda s: None)
        assert res["ok"] is False
        assert res["retries_exhausted"] is True
        assert len(res["attempts"]) == 3
        assert len(transport.calls) == 3

    def test_401_is_never_retried(self):
        transport = StubTransport([{"status": 401, "headers": {}, "body": "unauthorized"}])
        res = lp.publish_post(FAKE_TOKEN, "urn:li:person:x", "hello",
                              transport=transport, max_retries=2, sleep=lambda s: None)
        assert res["ok"] is False
        assert res["retryable"] is False
        assert len(transport.calls) == 1

    def test_403_permission_refusal_is_never_retried(self):
        transport = StubTransport([{"status": 403, "headers": {},
                                    "body": "insufficient permissions"}])
        res = lp.publish_post(FAKE_TOKEN, "urn:li:person:x", "hello",
                              transport=transport, max_retries=5, sleep=lambda s: None)
        assert res["ok"] is False and len(transport.calls) == 1


# --------------------------------------------------------------------------- #
# secrets never leak; the token layer is presence-only
# --------------------------------------------------------------------------- #

class TestNoSecretLeakage:
    def test_status_never_reads_a_secret_value(self):
        fake_presence = {k: {"target": auth.CRED_TARGETS[k], "env_var": auth.ENV_VARS[k],
                             "present": False, "source": "none"} for k in auth.CRED_TARGETS}
        with mock.patch.object(auth, "presence", return_value=fake_presence):
            code, out = run(lp.main, ["status"])
        assert code == 0
        assert out["network_calls_spent"] == 0
        assert out["browser_automation_used"] is False
        assert out["session_or_cookie_reuse"] is False
        assert out["scraping_behind_authentication"] is False
        assert "message" in out["still_refused_actions"]

    def test_token_and_secret_never_reach_output_or_ledger(self, tmp_path):
        d = drafts_file(tmp_path)
        ledger = tmp_path / "ledger.jsonl"
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        transport = StubTransport([{"status": 200, "headers": {},
                                    "body": json.dumps({"sub": "abc123"})}, ok_post()])
        with configured()[0], configured()[1], configured()[2], \
                mock.patch.object(auth, "urllib_transport", transport):
            code, out = run(lp.main, ["publish", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--no-backoff",
                                      "--ledger", str(ledger)])
        assert code == 0
        blob = json.dumps(out) + ledger.read_text(encoding="utf-8")
        assert FAKE_TOKEN not in blob
        assert FAKE_SECRET not in blob
        assert "Bearer" not in blob

    def test_auth_status_reports_presence_only(self):
        code, out = run(auth.main, ["status"])
        assert code == 0
        assert out["secret_values_read"] is False
        for purpose, rec in out["credentials"].items():
            assert "value" not in rec
            assert set(rec) == {"target", "env_var", "present", "source"}


# --------------------------------------------------------------------------- #
# request construction details
# --------------------------------------------------------------------------- #

class TestRequestConstruction:
    def test_linkedin_version_header_is_pinned_to_a_known_active_version(self):
        """The header must name an API version LinkedIn has actually activated.

        October 2026 is not live yet, so the current month cannot be used; the
        pin is July 2026 and must stay a yyyy-mm string.
        """
        import datetime as dt
        header = lp.linkedin_version_header(dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc))
        assert header == "202607"
        assert len(header) == 6 and header.isdigit()

    def test_person_urn_resolution_reports_a_provider_error_truthfully(self):
        transport = StubTransport([{"status": 401, "headers": {}, "body": "bad token"}])
        res = lp.resolve_person_urn(FAKE_TOKEN, transport=transport)
        assert res["ok"] is False and res["status"] == 401

    def test_draft_selection_never_rewrites_the_body(self, tmp_path):
        d = drafts_file(tmp_path)
        doc = lp.load_drafts(d)
        draft = lp.select_draft(doc, "post", 0)
        assert lp.draft_body(draft) == "Notes from a recent project: example."
        assert draft["status"] == "draft_unsent"

    def test_selecting_an_out_of_range_index_is_an_error(self, tmp_path):
        doc = lp.load_drafts(drafts_file(tmp_path))
        with pytest.raises(IndexError):
            lp.select_draft(doc, "post", 5)
