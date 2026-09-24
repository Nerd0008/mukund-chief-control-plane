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
                *, blocked: bool = False, verdict: str | None = "pass") -> Path:
    """A draft artefact in the same shape `linkedin_workflow.py draft` writes."""
    post = {"kind": "post", "topic": "Project note", "status": "draft_unsent",
            "publish_requires": "explicit owner authorization", "body": body,
            "blocked": blocked,
            "sources": [{"source": "cv.md", "line": 10, "section": "Profile",
                         "text": "canonical line"}]}
    if verdict is not None:
        post["fact_gate"] = {"verdict": verdict, "invented": [], "unsupportedFacts": [],
                             "forbidden": [], "available": True, "exit_code": 0}
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
        with configured()[0], configured()[1]:
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
        # No 'configured()' patch: the real store is empty on this host.
        code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                  "--confirm-token", body_sha, "--ledger",
                                  str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["oauth_credentials_present"]["passed"] is False
        assert "owner setup required" in checks["oauth_credentials_present"]["detail"]
        assert code == 1

    def test_a_draft_blocked_by_the_fact_gate_is_never_publishable(self, tmp_path):
        d = drafts_file(tmp_path, blocked=True, verdict="fail")
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        with configured()[0], configured()[1]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--ledger",
                                      str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_review"]["passed"] is False
        assert out["fact_gate_verdict"] == "fail"
        assert out["draft_blocked_flag"] is True
        assert code == 1

    def test_a_draft_with_no_recorded_review_says_so_instead_of_assuming_pass(self, tmp_path):
        d = drafts_file(tmp_path, verdict=None)
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        with configured()[0], configured()[1]:
            code, out = run(lp.main, ["plan", "--drafts", str(d), "--approve-publish",
                                      "--confirm-token", body_sha, "--ledger",
                                      str(tmp_path / "ledger.jsonl")])
        checks = {c["check"]: c for c in out["checks"]}
        assert checks["draft_passed_review"]["passed"] is True
        assert "no review verdict recorded" in checks["draft_passed_review"]["detail"]
        assert out["fact_gate_verdict"] is None
        assert code == 0


# --------------------------------------------------------------------------- #
# dry-run and the real path, over an injected transport
# --------------------------------------------------------------------------- #

class TestPublishFlow:
    def test_dry_run_sends_nothing_and_records_a_dry_run(self, tmp_path):
        d = drafts_file(tmp_path)
        ledger = tmp_path / "ledger.jsonl"
        body_sha = lp.sha256_text("Notes from a recent project: example.")
        transport = StubTransport([])
        with configured()[0], configured()[1], \
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
        with configured()[0], configured()[1], \
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
        with configured()[0], configured()[1]:
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
        with configured()[0], configured()[1]:
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
        with configured()[0], configured()[1], \
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
    def test_linkedin_version_header_is_yyyy_mm(self):
        import datetime as dt
        assert lp.linkedin_version_header(dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc)) \
            == "202609"

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
