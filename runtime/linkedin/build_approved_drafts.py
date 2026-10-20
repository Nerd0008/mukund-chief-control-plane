#!/usr/bin/env python3
"""Create pre-approved LinkedIn drafts from real, gate-checked text.

Why this replaces the old create_approved_drafts.py
--------------------------------------------------
The previous version hand-wrote gate verdicts:

    {'verdict': 'pass', 'gate_name': 'linkedin-news-claims', ...}

and, for the news gate, supplied a hand-typed three-sentence *summary* of the
article as the source text. Both are now refused:

* a verdict that cannot prove it came from a real run is not a verdict
  (``linkedin_factcheck.provenance_ok``);
* a source shorter than ``MIN_GROUNDING_CHARS`` is not a readable article, so
  the gate reports ``ungated`` instead of judging the post against a stub.

This script therefore does the honest thing:

1. fetch and cache the REAL article text for each source URL;
2. run the real news-claims gate over the post;
3. write the artefact ONLY if the gate returns ``pass``;
4. carry the real gate record through to the publisher.

It never writes a verdict of its own, and it never publishes.

Usage
    python runtime/linkedin/build_approved_drafts.py [--dry-run]

Draft text lives in ``drafts_input.json`` next to this script, so the copy is
reviewable and editable without touching code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

CONTROL_PLANE = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
CAREER_OPS = CONTROL_PLANE / "career-ops"
SCRIPTS_DIR = CONTROL_PLANE / "scripts"
sys.path.insert(0, str(CAREER_OPS))
sys.path.insert(0, str(SCRIPTS_DIR))

import linkedin_factcheck as fc  # noqa: E402
import topic_reuse_check as trc  # noqa: E402

DRAFTS_DIR = CONTROL_PLANE / "runtime" / "linkedin" / "drafts"
INPUT = Path(__file__).resolve().parent / "drafts_input.json"
TOPIC_REGISTRY = CONTROL_PLANE / "runtime" / "linkedin" / "topic_registry.json"


def source_urls(spec: dict) -> list[str]:
    """All source URLs a post cites, single or list."""
    if spec.get("sources"):
        return [u for u in spec["sources"] if u]
    return [spec["source_url"]] if spec.get("source_url") else []


def fetch_and_cache(url: str) -> tuple[str | None, str]:
    """Return (text, how) for a source URL, caching a real fetch."""
    cached = fc.cached_source_text(url)
    if cached:
        return cached, "cache"
    text = fc.fetch_source_text(url)
    if not text:
        return None, "unavailable"
    fc.cache_source_text(url, text, source="fetch")
    return text, "fetch"


def build_one(spec: dict) -> dict:
    """Run the real gate over one post. Returns a result record, never a verdict."""
    urls = source_urls(spec)
    result: dict = {"day": spec["day"], "title": spec.get("title", ""),
                    "sources": []}
    for url in urls:
        text, how = fetch_and_cache(url)
        result["sources"].append({"url": url, "how": how,
                                  "chars": len(text) if text else 0})
        if not text:
            result["ok"] = False
            result["reason"] = (
                f"source could not be read ({url}); no claims can be grounded, "
                f"so no draft is written")
            return result
    gate = fc.verify_post(spec["post_text"], urls,
                          use_llm=True, api_key=fc._load_api_key())
    result["verdict"] = gate.get("verdict")
    result["llm_used"] = gate.get("llm_used")
    result["unsupported"] = [c.get("claim") for c in gate.get("unsupported_claims", [])]
    result["world_claims"] = [c.get("claim") for c in gate.get("world_claims", [])]
    result["gate"] = gate
    result["ok"] = gate.get("verdict") == "pass"
    if not result["ok"]:
        result["reason"] = (gate.get("reason")
                            or f"{len(result['unsupported'])} claim(s) not supported")
    return result


def write_draft(spec: dict, gate: dict) -> Path:
    """Write the approved artefact, carrying the real gate record through."""
    day = spec["day"]
    out_dir = DRAFTS_DIR / spec["dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    body = spec["post_text"]
    token = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
    doc = {
        "post_text": body,
        "news_fact_gate": gate,
        "personal_fact_gate": spec.get("personal_fact_gate"),
        "topic": {"title": spec.get("title", ""),
                  "sources": [spec["source_url"]] if spec.get("source_url") else []},
        "confirm_token": token,
        "image_path": str(out_dir / "image.jpg") if (out_dir / "image.jpg").exists() else None,
        "approved": True,
        "day": day,
    }
    (out_dir / "post_text.txt").write_text(body, encoding="utf-8")
    (out_dir / "linkedin_drafts.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="run the gates and report, but write no artefact")
    args = ap.parse_args()

    specs = json.loads(INPUT.read_text(encoding="utf-8"))
    schedule = {}
    exit_code = 0
    for spec in specs:
        print("=" * 72)
        print(f"{spec['day']}  ({spec.get('title','')})")

        # Hard topic-reuse guard. Runs BEFORE the fact gate so a reused topic
        # costs nothing and cannot produce an artefact at all. This is the
        # control that replaced the "please don't reuse a topic" instruction,
        # which failed on 2026-10-18 when a third AI + water post was drafted.
        reuse = trc.check_text(spec["post_text"], topic=spec.get("title"),
                               registry_path=TOPIC_REGISTRY)
        if reuse["blocked"]:
            exit_code = 1
            print("  REFUSED  topic already used:")
            for m in reuse["matches"]:
                print(f"    - {m['topic']}  (used_on {m.get('used_on')}; "
                      f"matched_by {m['matched_by']}; signals {m['signals_hit']})")
                print(f"      evidence: {m.get('evidence')}")
            print("    No artefact written. Pick a different topic.")
            continue
        for w in reuse["warnings"]:
            print(f"  warning  {w['topic']}: {w['signals_hit']} ({w['note']})")

        res = build_one(spec)
        if res.get("sources"):
            for s in res["sources"]:
                print(f"  source: {s['how']}  {s['chars']} chars  {s['url']}")
        print(f"  gate: {res.get('verdict')}  (llm_used={res.get('llm_used')})")
        if res["ok"]:
            if args.dry_run:
                print("  PASS  (dry-run: no artefact written)")
            else:
                d = write_draft(spec, res["gate"])
                token = hashlib.sha256(spec["post_text"].strip().encode()).hexdigest()
                schedule[spec["day"]] = {
                    "draft_path": str(d / "linkedin_drafts.json"),
                    "image_path": str(d / "image.jpg") if (d / "image.jpg").exists() else None,
                    "confirm_token": token,
                    "title": spec.get("title", ""),
                }
                print(f"  PASS  artefact written: {d}")
        else:
            exit_code = 1
            print(f"  REFUSED  {res.get('reason')}")
            for c in res.get("unsupported", [])[:5]:
                print(f"    - {str(c)[:150]}")

    if schedule and not args.dry_run:
        p = DRAFTS_DIR / "schedule.json"
        p.write_text(json.dumps(schedule, indent=2), encoding="utf-8")
        print(f"\nschedule written: {p}")
        print(json.dumps(schedule, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
