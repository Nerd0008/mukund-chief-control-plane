#!/usr/bin/env python3
"""Verify that every ARMED LinkedIn publish job would actually succeed.

Why this exists
---------------
The workflow relied on a script the skill referenced as
``scripts/verify_armed_jobs.py``. It did not exist, so nothing ever checked what
an armed 08:00 job would really publish. Consequences seen in practice:

  * an armed job pointed at a draft whose body was already in the published
    ledger, so it failed the duplicate check at 08:00 with nobody watching;
  * an armed job pointed at a reused topic, which the ledger cannot detect
    because the ledger had no topic field.

This script resolves each armed job the same way ``publish_scheduled.py`` does
(newest ``approved_<YYYYMMDD>_<day>/``) and then runs the same checks the
publish path would run, offline and without spending a network call:

  1. a draft exists for the job's weekday
  2. the draft JSON carries a non-empty body
  3. the frozen text matches the draft body
  4. the confirm token equals the sha256 of the exact body
  5. the body is not already in the published ledger (duplicate guard)
  6. the topic is not already used (topic-reuse guard)
  7. both fact gates are present and passing (or owner-overridden)
  8. an image is present (warning only)

Usage
-----
    python scripts/verify_armed_jobs.py

Exit codes
----------
    0  every armed job would succeed
    1  at least one armed job would fail
    2  could not read the cron job list
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

CONTROL_PLANE = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
DRAFTS_DIR = CONTROL_PLANE / "runtime" / "linkedin" / "drafts"
LEDGER = CONTROL_PLANE / "runtime" / "linkedin" / "published" / "posts.jsonl"
TOPIC_REGISTRY = CONTROL_PLANE / "runtime" / "linkedin" / "topic_registry.json"
SCRIPTS_DIR = CONTROL_PLANE / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import topic_reuse_check as trc  # noqa: E402
except Exception:                      # noqa: BLE001
    trc = None

JOBS_JSON = Path.home() / "AppData" / "Local" / "hermes" / "cron" / "jobs.json"

DAY_WORDS = {"monday": "tuesday", "tuesday": "tuesday", "wednesday": "wednesday",
             "thursday": "thursday", "friday": "friday", "saturday": "saturday",
             "sunday": "sunday"}
VALID_PUBLISH_DAYS = ("tuesday", "wednesday", "thursday")


def load_jobs() -> list[dict]:
    if not JOBS_JSON.exists():
        raise FileNotFoundError(f"cron job list not found: {JOBS_JSON}")
    data = json.loads(JOBS_JSON.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("jobs", []) or []
    return data if isinstance(data, list) else []


def job_day(job: dict) -> str | None:
    """The publish weekday an armed job refers to, or None if not a publish job."""
    name = (job.get("name") or "").lower()
    if "linkedin post" not in name:
        return None
    m = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", name)
    if not m:
        return None
    return m.group(1)


def find_draft_dir(day: str) -> Path | None:
    candidates = [d for d in DRAFTS_DIR.glob(f"approved_*_{day}")
                  if (d / "linkedin_drafts.json").exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def ledger_hashes() -> set[str]:
    out: set[str] = set()
    if not LEDGER.exists():
        return out
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("result") == "published" and row.get("body_sha256"):
            out.add(row["body_sha256"])
    return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def check_job(job: dict, ledger: set[str]) -> dict:
    report = {"job_id": job.get("job_id") or job.get("id"), "name": job.get("name"),
              "enabled": bool(job.get("enabled")), "checks": [], "blockers": [], "warnings": []}

    def check(name, ok, detail, blocking=True):
        report["checks"].append({"check": name, "passed": bool(ok), "detail": detail})
        if not ok:
            (report["blockers"] if blocking else report["warnings"]).append(
                {"check": name, "detail": detail})

    if not report["enabled"]:
        report["skipped"] = True
        report["note"] = "job is disabled; nothing will publish"
        return report

    day = job_day(job)
    report["day"] = day
    if day not in VALID_PUBLISH_DAYS:
        report["skipped"] = True
        report["note"] = f"weekday {day!r} is not a publish day"
        return report

    draft_dir = find_draft_dir(day)
    report["draft_dir"] = draft_dir.name if draft_dir else None
    if draft_dir is None:
        check("draft_exists", False,
              f"no approved_*_{day} directory with a draft JSON; the job would exit 1 at 08:00")
        return report
    check("draft_exists", True, draft_dir.name)

    try:
        draft = json.loads((draft_dir / "linkedin_drafts.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        check("draft_loads", False, f"{type(exc).__name__}: {exc}")
        return report
    check("draft_loads", True, "linkedin_drafts.json parsed")

    body = draft.get("post_text") or ""
    check("body_present", bool(body.strip()), f"{len(body)} chars")
    if not body.strip():
        return report
    body_sha = sha256_text(body)

    frozen = draft_dir / "frozen_text.txt"
    if frozen.exists():
        frozen_body = frozen.read_text(encoding="utf-8")
        check("frozen_text_matches", sha256_text(frozen_body) == body_sha,
              "frozen_text.txt matches the draft body" if sha256_text(frozen_body) == body_sha
              else "frozen_text.txt does NOT match the draft body")
    else:
        check("frozen_text_matches", False, "frozen_text.txt is missing")

    token = draft.get("confirm_token")
    check("confirm_token_matches", token == body_sha,
          f"confirm_token matches sha256(body) ({body_sha})" if token == body_sha
          else f"confirm_token {token!r} != sha256(body) {body_sha}")

    check("not_a_duplicate", body_sha not in ledger,
          "body hash is not in the published ledger" if body_sha not in ledger
          else f"body hash is already published (duplicate guard would refuse at 08:00)")

    if trc is not None:
        reuse = trc.check_text(body, topic=draft.get("topic", {}).get("title")
                               if isinstance(draft.get("topic"), dict) else None,
                               registry_path=TOPIC_REGISTRY)
        check("topic_not_reused", not reuse["blocked"],
              "no used topic matched" if not reuse["blocked"]
              else "topic already used: " + "; ".join(
                  f"{m['topic']} (used_on {m.get('used_on')})" for m in reuse["matches"]))
        report["topic_warnings"] = reuse["warnings"]

    gate = draft.get("fact_gate") or draft.get("personal_fact_gate")
    gv = gate.get("verdict") if isinstance(gate, dict) else None
    check("personal_gate_passes", gv in ("pass", "passed"),
          f"personal-claims gate verdict {gv!r}")

    news = draft.get("news_fact_gate")
    nv = news.get("verdict") if isinstance(news, dict) else None
    ok_news = nv in ("pass", "passed") or bool(draft.get("owner_override"))
    check("news_gate_passes", ok_news,
          f"news-claims gate verdict {nv!r}" + (" (owner override recorded)" if draft.get("owner_override") else ""))

    image = draft_dir / "image.jpg"
    check("image_present", image.exists(),
          f"{image.name} present ({image.stat().st_size} bytes)" if image.exists()
          else "no image; the post would publish text only", blocking=False)

    report["body_sha256"] = body_sha
    return report


def main() -> int:
    try:
        jobs = load_jobs()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read cron job list: {exc}", file=sys.stderr)
        return 2

    ledger = ledger_hashes()
    armed = [j for j in jobs if job_day(j) is not None]

    if not armed:
        print("No armed LinkedIn publish jobs found.")
        return 0

    print(f"Armed LinkedIn publish jobs: {len(armed)}   ledger published hashes: {len(ledger)}\n")
    any_block = False
    for job in armed:
        rep = check_job(job, ledger)
        status = ("SKIP  " if rep.get("skipped") else
                  "FAIL  " if rep["blockers"] else "OK    ")
        print(f"{status} {rep['name']}  ({rep.get('job_id')})")
        print(f"       day={rep.get('day')}  draft={rep.get('draft_dir')}")
        for c in rep["checks"]:
            mark = "  ok " if c["passed"] else "FAIL "
            print(f"       {mark} {c['check']}: {c['detail']}")
        for w in rep.get("warnings", []):
            print(f"       warn {w['check']}: {w['detail']}")
        for b in rep["blockers"]:
            any_block = True
        if rep.get("topic_warnings"):
            for w in rep["topic_warnings"]:
                print(f"       note {w['topic']}: {w['signals_hit']} ({w.get('note','')})")
        if rep.get("note"):
            print(f"       note {rep['note']}")
        print()

    if any_block:
        print("RESULT: at least one armed job would FAIL at 08:00. Fix before the job fires.")
        return 1
    print("RESULT: every armed job would publish cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
