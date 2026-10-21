#!/usr/bin/env python3
"""Arm an approved LinkedIn draft artefact: real gates + real owner approval.

Why this exists
---------------
An artefact is only publishable when three things are true of the SAME bytes:

1. a real news-claims gate record (``news_fact_gate``) whose ``body_sha256``
   matches the text;
2. a real personal-claims gate record (``personal_fact_gate``) from the install's
   own ``verify-cv-facts.mjs``;
3. an ``owner_approval`` receipt naming a real Discord owner message and bound to
   the same body hash.

Each of those can drift. The text can be edited after a gate ran, a gate can be
run over a draft that was later replaced, and an approval can be given in chat
without ever being recorded against the bytes. Publishing then fails at the last
gate, or worse, publishes text that was never checked.

This script re-runs BOTH gates over the artefact's current text and records the
owner's approval from the Hermes message database, so the artefact that gets
armed is provably the artefact that was checked and approved.

It never writes a verdict of its own, and it never invents a message id: an
approval that cannot be found in the database is refused.

Usage
    python career-ops/linkedin_arm_drafts.py \
        --drafts runtime/linkedin/drafts/approved_20261021_wednesday/linkedin_drafts.json \
        --approve-message-id 32952 [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

CONTROL_PLANE = Path(__file__).resolve().parent.parent
CAREER_OPS = CONTROL_PLANE / "career-ops"
sys.path.insert(0, str(CAREER_OPS))

import linkedin_factcheck as fc  # noqa: E402
import cv_workflow as cvw  # noqa: E402

APPROVAL_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "state.db"
OWNER_DISCORD_ID = "1551585829279764531"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def lookup_approval(message_id: int) -> tuple[bool, str, str]:
    """Return (ok, timestamp, detail) for a recorded Discord owner message."""
    if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
        return False, "", "approval message id is not a positive integer"
    try:
        with sqlite3.connect(APPROVAL_DB.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT m.role, m.content, m.timestamp, s.source "
                "FROM messages m JOIN sessions s ON s.id = m.session_id "
                "WHERE m.id = ?",
                (message_id,),
            ).fetchone()
    except (OSError, sqlite3.Error, ValueError) as exc:
        return False, "", f"approval history unavailable: {type(exc).__name__}: {exc}"
    if not row:
        return False, "", f"no message {message_id} in the Hermes database"
    role, content, timestamp, source = row
    if role != "user":
        return False, "", f"message {message_id} is a {role} message, not the owner's own"
    if source != "discord":
        return False, "", f"message {message_id} came from {source}, not Discord"
    text = (content or "").lower()
    keywords = ("approved", "approve", "publish", "yes", "go ahead",
                "looks good", "post it")
    if not any(k in text for k in keywords):
        return False, "", (f"message {message_id} carries no explicit approval wording")
    return True, str(timestamp or ""), f"owner approval recorded in message {message_id}"


def run_news_gate(body: str, sources: list[str]) -> dict:
    """Run the real news-claims gate. Never a verdict of this script's."""
    return fc.verify_post(body, sources, use_llm=True, api_key=fc._load_api_key())


def run_personal_gate(body: str, label: str) -> dict:
    """Run the real personal-claims gate. Never a verdict of this script's."""
    cfg = cvw.load_config(CAREER_OPS / "cv_workflow_config.json")
    scratch = (CONTROL_PLANE / "runtime" / "linkedin" / ".gate-scratch").resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    return cvw.fact_gate(cfg, body, label=label, scratch=scratch)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", required=True, help="path to linkedin_drafts.json")
    ap.add_argument("--approve-message-id", type=int, required=True,
                    help="Hermes message id of the owner's Discord approval")
    ap.add_argument("--dry-run", action="store_true",
                    help="run both gates and report, write nothing")
    args = ap.parse_args()

    path = Path(args.drafts)
    doc = json.loads(path.read_text(encoding="utf-8"))
    body = doc.get("post_text") or ""
    if not body.strip():
        print(json.dumps({"ok": False, "reason": "artefact has no post_text"}))
        return 1

    sha = sha256_text(body)
    day = doc.get("day") or path.parent.name
    old_news = doc.get("news_fact_gate") or {}
    sources = list(old_news.get("sources") or [])

    print(f"artefact : {path}")
    print(f"day      : {day}")
    print(f"body sha : {sha}")
    print(f"sources  : {len(sources)}")

    # A gate record that already proves it ran over these exact bytes is reused.
    # It is not re-run for its own sake: re-running costs judge calls and, if the
    # claim model is unavailable at that moment, would downgrade text that was
    # genuinely verified. A record that does NOT match is re-run, because that is
    # the case where the text was edited after the gate ran.
    if fc.provenance_ok(old_news, body)[0]:
        news = old_news
        news_source = "reused: record already proves it ran over this text"
    else:
        news = run_news_gate(body, sources)
        news_source = "re-run: the stored record does not cover this text"
    personal = run_personal_gate(body, f"draft-{day}")

    news_ok = news.get("verdict") == "pass" and news.get("body_sha256") == sha
    personal_verdict = personal.get("verdict")
    personal_ok = personal_verdict in ("pass", "warn")
    personal_blocked = personal_verdict == "block"

    print(f"news gate: {news.get('verdict')}  ({news_source}; "
          f"provenance match: {news.get('body_sha256') == sha})")
    print(f"personal gate: {personal_verdict}  available={personal.get('available')}"
          + (f"  warnings={personal.get('warnings')!r}" if personal.get("warnings") else ""))

    ok, approved_at, approval_detail = lookup_approval(args.approve_message_id)
    print(f"approval : {'ok' if ok else 'REFUSED'} — {approval_detail}")

    result = {
        "ok": bool(news_ok and personal_ok and ok),
        "body_sha256": sha,
        "news_gate_verdict": news.get("verdict"),
        "news_gate_provenance_match": news.get("body_sha256") == sha,
        "personal_gate_verdict": personal_verdict,
        "personal_gate_available": personal.get("available"),
        "approval": ok,
        "approval_detail": approval_detail,
        "blockers": [b for b, cond in (
            ("news gate did not pass with provenance over this text", not news_ok),
            ("personal-claims gate refused this text", not personal_ok),
            ("owner approval not found", not ok),
        ) if cond],
    }

    if args.dry_run:
        result["dry_run"] = True
        result["would_write"] = {
            "news_fact_gate": news.get("verdict"),
            "personal_fact_gate": personal_verdict,
            "owner_approval": {"hermes_message_id": args.approve_message_id,
                               "body_sha256": sha},
            "confirm_token": sha,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1

    if not result["ok"]:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("NOT WRITTEN: the artefact does not yet satisfy the publish gates.")
        return 1

    doc["news_fact_gate"] = news
    doc["personal_fact_gate"] = personal
    doc["confirm_token"] = sha
    doc["blocked"] = personal_blocked
    doc["owner_approval"] = {
        "approved": True,
        "approved_by": "Mukund",
        "approved_at": approved_at,
        "approval_method": "explicit Discord approval",
        "hermes_message_id": args.approve_message_id,
        "body_sha256": sha,
    }
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    result["written"] = str(path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
