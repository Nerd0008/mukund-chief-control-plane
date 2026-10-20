#!/usr/bin/env python3
"""Deterministic LinkedIn topic-reuse guard.

Why this exists
---------------
Dedupe was previously an *instruction* to the drafting model ("check the index,
don't reuse a topic"). That failed: on 2026-10-18 the Sunday draft job produced a
third AI + water post because

  * ``old_bot_posts_index.json`` only holds the old bot's July posts, not our own;
  * ``published/posts.jsonl`` is a hash ledger with no topic field, so it can only
    catch a byte-identical repost, never a new post on the same topic;
  * the job's scope was "the previous week", and the water posts were older.

An instruction the model may misread is not a control. This script is a control:
it reads ``runtime/linkedin/topic_registry.json`` and refuses any draft whose text
matches a topic that has already been used. It is wired into
``runtime/linkedin/build_approved_drafts.py`` so a reused topic cannot produce an
artefact at all, and into ``scripts/verify_armed_jobs.py`` so an armed job cannot
publish one either.

It never judges style, never writes an artefact and never publishes. It only
answers one question: is this topic already taken?

Usage
-----
    python scripts/topic_reuse_check.py --text "post body"
    python scripts/topic_reuse_check.py --file runtime/linkedin/drafts/approved_20261021_wednesday/post_text.txt
    python scripts/topic_reuse_check.py --text "..." --topic "AI + water" --json

Exit codes
----------
    0  no reused topic (ok)
    1  a used topic matched (blocked)
    2  registry missing or unreadable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTROL_PLANE = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
DEFAULT_REGISTRY = CONTROL_PLANE / "runtime" / "linkedin" / "topic_registry.json"


def normalise(text: str) -> str:
    """Lowercase and collapse whitespace so signals match reliably."""
    return " ".join((text or "").lower().split())


def load_registry(path: Path | str = DEFAULT_REGISTRY) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"topic registry not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def check_text(text: str, *, topic: str | None = None,
               registry_path: Path | str = DEFAULT_REGISTRY) -> dict:
    """Return a report. ``blocked`` is True when a used topic matched."""
    report = {"blocked": False, "matches": [], "warnings": [], "registry": str(registry_path)}
    try:
        registry = load_registry(registry_path)
    except (OSError, json.JSONDecodeError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["blocked"] = True          # fail closed: no registry, no pass
        report["fail_closed"] = True
        return report

    haystack = normalise(text)
    declared = normalise(topic) if topic else ""

    for entry in registry.get("topics", []):
        title = normalise(entry.get("topic", ""))
        signals = [normalise(s) for s in entry.get("signals", []) if s]
        hits = [s for s in signals if s and s in haystack]

        # An explicitly declared topic that names a used topic is a block
        # regardless of signal count.
        declared_hit = bool(declared) and bool(title) and (
            title in declared or declared in title
        )
        if declared_hit:
            match = {
                "topic": entry.get("topic"),
                "status": entry.get("status"),
                "used_on": entry.get("used_on"),
                "evidence": entry.get("evidence"),
                "matched_by": "declared_topic",
                "signals_hit": hits,
                "strict": bool(entry.get("strict")),
            }
            # Same pending rule as the signal path: a topic planned for THIS
            # week must not block its own approval.
            if (entry.get("status") or "used").lower() == "pending":
                report["warnings"].append({**match, "note": "planned topic, not yet published"})
            else:
                report["matches"].append(match)
            continue

        strict = bool(entry.get("strict"))
        status = (entry.get("status") or "used").lower()
        if (strict and hits) or (not strict and len(hits) >= 2):
            match = {
                "topic": entry.get("topic"),
                "status": entry.get("status"),
                "used_on": entry.get("used_on"),
                "evidence": entry.get("evidence"),
                "matched_by": "signals",
                "signals_hit": hits,
                "strict": strict,
            }
            # A topic that is merely planned for THIS week is not a reuse yet;
            # it must not block its own approval. It still warns, so the
            # drafter sees it, and once published it becomes "used" and blocks.
            if status == "pending":
                report["warnings"].append({**match, "note": "planned topic, not yet published"})
            else:
                report["matches"].append(match)
        elif hits:
            report["warnings"].append({
                "topic": entry.get("topic"),
                "signals_hit": hits,
                "note": "weak match; not blocking",
            })

    report["blocked"] = bool(report["matches"])
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Refuse a LinkedIn draft whose topic is already used.")
    ap.add_argument("--text", help="the post body to check")
    ap.add_argument("--file", help="read the post body from this file instead")
    ap.add_argument("--topic", help="the declared topic title, e.g. 'AI + water'")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--json", action="store_true", help="emit a JSON report only")
    args = ap.parse_args()

    if args.file:
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {args.file}: {exc}", file=sys.stderr)
            return 2
    elif args.text:
        text = args.text
    else:
        ap.error("supply --text or --file")

    report = check_text(text, topic=args.topic, registry_path=args.registry)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if report["blocked"] else 0

    if report.get("fail_closed"):
        print(f"FAIL CLOSED: {report['error']}")
        return 2

    for m in report["matches"]:
        print(f"BLOCKED  topic already used: {m['topic']}")
        print(f"         used_on: {m.get('used_on')}   status: {m.get('status')}")
        print(f"         evidence: {m.get('evidence')}")
        print(f"         matched_by: {m['matched_by']}  signals_hit: {m['signals_hit']}")
    for w in report["warnings"]:
        print(f"warning  weak match on '{w['topic']}': {w['signals_hit']} ({w['note']})")

    if report["blocked"]:
        print("\nRefuse this draft. Pick a different topic.")
        return 1
    print("OK  no reused topic detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
