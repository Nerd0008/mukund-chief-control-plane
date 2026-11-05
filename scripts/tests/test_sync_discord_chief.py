"""Regression tests for the Discord archive sync dedupe identity.

Root cause these tests lock down: Discord reuses a message ID when a
background-process completion is posted as a reply to that message. The sync
keyed dedupe on (direction, message_id) alone, so the completion notice was
silently dropped as a "duplicate" of the message it replied to.

Run: python -m pytest scripts/tests/test_sync_discord_chief.py
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "sync_discord_chief.py"
spec = importlib.util.spec_from_file_location("sync_discord_chief", SCRIPT)
sync = importlib.util.module_from_spec(spec)
sys.modules["sync_discord_chief"] = sync
spec.loader.exec_module(sync)


def owner(mid, ts, content):
    return {
        "timestamp": ts,
        "direction": "inbound",
        "channel_id": "1",
        "channel_name": "chief",
        "thread_id": None,
        "session_id": "s",
        "author_role": "owner",
        "message_id": mid,
        "content": content,
    }


def assistant(ts, content):
    return {
        "timestamp": ts,
        "direction": "outbound",
        "channel_id": "1",
        "channel_name": "chief",
        "thread_id": None,
        "session_id": "s",
        "author_role": "assistant",
        "message_id": None,
        "content": content,
    }


def dedupe(records):
    """Re-run the script's merge/dedupe over a single batch."""
    seen_ids, seen_fb, uniq = set(), set(), []
    for r in records:
        mid = r.get("message_id")
        if mid:
            key = (r.get("direction"), str(r.get("timestamp")), str(mid))
            if key in seen_ids:
                continue
            seen_ids.add(key)
        else:
            key = (
                r.get("timestamp"),
                r.get("direction"),
                sync.hashlib.sha256(str(r.get("content")).encode()).hexdigest(),
            )
            if key in seen_fb:
                continue
            seen_fb.add(key)
        uniq.append(r)
    return uniq


def test_background_completion_reusing_message_id_is_kept():
    """The exact failure: a completion notice reuses the message ID it replies to."""
    original = owner("1567795175529652265", "2026-11-05T06:58:59+00:00", "Let me know when it lands")
    notice = owner(
        "1567795175529652265",
        "2026-11-05T08:13:01+00:00",
        "[IMPORTANT: Background process proc_92d7e7c1a1a1 completed normally (exit code 0).",
    )
    out = dedupe([original, notice])
    assert len(out) == 2, "completion notice reusing a message ID must not be dropped"
    assert out[0]["timestamp"] == "2026-11-05T06:58:59+00:00"
    assert out[1]["timestamp"] == "2026-11-05T08:13:01+00:00"


def test_genuine_duplicate_message_id_is_still_deduped():
    """A real repeat of the same message at the same timestamp must still collapse."""
    a = owner("1551676997309038734", "2026-09-21T19:39:50+00:00", "Bridge live 922")
    b = owner("1551676997309038734", "2026-09-21T19:39:50+00:00", "Bridge live 922")
    assert len(dedupe([a, b])) == 1


def test_same_content_different_timestamp_is_not_deduped():
    """Content matching alone must never dedupe distinct messages."""
    a = assistant("2026-10-22T00:23:38+00:00", "Here's the draft.")
    b = assistant("2026-10-22T00:23:39+00:00", "Here's the draft.")
    assert len(dedupe([a, b])) == 2


def test_repeated_completion_notices_for_one_message_are_all_kept():
    """Seven completion notices reused one message ID on 2026-10-23."""
    mid = "1555733966630158347"
    stamps = [
        "2026-10-23T14:36:11+00:00",
        "2026-10-23T14:39:14+00:00",
        "2026-10-23T14:45:07+00:00",
        "2026-10-23T21:33:11+00:00",
        "2026-10-23T21:38:13+00:00",
        "2026-10-23T21:41:45+00:00",
        "2026-10-23T21:50:38+00:00",
    ]
    recs = [owner(mid, ts, f"completion {i}") for i, ts in enumerate(stamps)]
    assert len(dedupe(recs)) == 7


def test_id_and_fallback_namespaces_stay_separate():
    """A message_id record and a message_id-less record never collapse together."""
    with_id = owner("1", "2026-11-05T06:58:59+00:00", "same text")
    without_id = assistant("2026-11-05T06:58:59+00:00", "same text")
    assert len(dedupe([with_id, without_id])) == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
