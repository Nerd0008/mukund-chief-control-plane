#!/usr/bin/env python3
"""Add an owner-supplied job link to the canonical UK tracker.

Owner instruction (2026-11-07, verbatim):
  "No from now whatever job link I send read it and add it to the tracker"

So the trigger is a bare URL in chat. This tool is the whole of that intake:
fetch the posting, screen it for a security-clearance/citizenship bar, read the
employer/role/deadline off the page, then append one row through the guarded
writer the pipeline already uses.

Design constraints, all load-bearing:

* **One write path.** The append goes through ``tracker_writer.write_records``
  via ``career_ops_cli.py write``. That is the only path that dedupes, takes a
  hash-verified backup, holds a lock, binds hyperlinks, asserts integrity,
  writes to a temp file and verifies before an atomic replace. A hand-rolled
  ``wb.save`` here would recreate every defect class the tracker skill lists.
* **The clearance gate runs before the write.** Owner standing instruction
  (2026-10-03): a posting that requires security clearance or UK citizenship
  stops the intake. No row, no documents. Only a *requirement* is a hit; a
  desirable mention is not, and an unreadable page is UNSCREENED, never CLEAR.
* **Never invent an employer or a role.** ``page_identity`` reads the posting's
  own structured metadata. When it cannot, the row is refused rather than
  guessed -- a plausible-looking company is indistinguishable from a real one
  once it is in the tracker.
* **The Status column is the owner's.** The writer deliberately cannot set it,
  so an intake row lands as ``Not Applied``. Marking it Applied needs employer
  evidence and its own writer (``application_state.py``).
* **A duplicate is reported, not re-added.** The writer's own dedupe decides:
  same URL, same employer-scoped requisition, or same company+title.

Usage:
    python career-ops/tracker_add_link.py --url <url>            # dry run
    python career-ops/tracker_add_link.py --url <url> --apply   # write
    python career-ops/tracker_add_link.py --url <url> --region uk
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent
sys.path.insert(0, str(HERE))

import tracker_writer as tw  # noqa: E402
from application_deadlines import deadline_label  # noqa: E402
from clearance_screening import (  # noqa: E402
    clearance_evidence,
    clearance_hits,
    is_readable,
)
from jd_fetcher import fetch_jd  # noqa: E402

CLI = HERE / "career_ops_cli.py"
DEFAULT_REGION = "uk"

#: Hosts that only re-list another employer's vacancy. The employer's own ATS
#: page is preferred when the page publishes one.
AGGREGATOR_HINT = re.compile(
    r"apply\s+on\s+(.+?)[’']s\s+(?:site|website)", re.I
)


def _clean(text) -> str:
    """Collapse a fetched string to single-spaced prose."""
    return " ".join(str(text or "").split())


def _employer_from_page(page: dict, url: str) -> str:
    """Employer name from the posting's own metadata, else its apply label."""
    identity = page.get("discovered_posting") or {}
    name = _clean(identity.get("company"))
    if name:
        return name
    match = AGGREGATOR_HINT.search(_clean(page.get("text")))
    if match:
        return _clean(match.group(1))
    return ""


def _role_from_page(page: dict) -> str:
    identity = page.get("discovered_posting") or {}
    return _clean(identity.get("title"))


def _deadline_from_page(page: dict):
    """Return ``(value, label)`` for the Application Deadline cell.

    Only an explicit date or explicit rolling wording is written. UNKNOWN stays
    empty: the column is the owner's, and a blank reads as "not stated" rather
    than as a date we made up.
    """
    info = page.get("deadline_info") or {}
    kind = info.get("type")
    if kind == "EXACT" and info.get("date"):
        return info["date"], "explicit application closing date"
    if kind == "ROLLING":
        return "Rolling", "explicit rolling or early-close wording"
    return None, (info.get("reason") or "no reliable application deadline in available JD text")


def read_posting(url: str, timeout: int) -> dict:
    """Fetch and reduce a posting to the fields the tracker row needs."""
    page = fetch_jd(url, timeout=timeout)
    if not isinstance(page, dict):
        page = {}
    text = page.get("text") or ""
    readable = bool(text.strip()) and is_readable(text)
    return {
        "url": url,
        "final_url": page.get("final_url") or url,
        "status": page.get("status"),
        "fetch_state": page.get("fetch_state"),
        "error": page.get("error"),
        "text": text,
        "readable": readable,
        "vacancy": page.get("vacancy_status") or {},
        "deadline_info": page.get("deadline_info") or {},
        "company": _employer_from_page(page, url),
        "title": _role_from_page(page),
        "hits": clearance_hits(text) if readable else [],
        "evidence": clearance_evidence(text) if readable else [],
    }


def screen(posting: dict) -> dict:
    """Apply the owner's clearance/citizenship gate to a fetched posting."""
    if not posting["readable"]:
        return {
            "verdict": "UNSCREENED",
            "reason": "page could not be fetched or read; an unreadable page proves nothing",
            "hits": [],
            "evidence": [],
        }
    if posting["hits"]:
        return {
            "verdict": "STOPPED",
            "reason": "security clearance or citizenship requirement stated in the posting",
            "hits": posting["hits"],
            "evidence": posting["evidence"],
        }
    return {"verdict": "CLEAR", "reason": "no clearance or citizenship requirement found",
            "hits": [], "evidence": []}


def build_record(posting: dict, region: str) -> dict:
    """The manifest record for one owner-supplied link."""
    deadline, deadline_reason = _deadline_from_page(posting)
    return {
        "date_found": dt.date.today().isoformat(),
        "company": posting["company"],
        "title": posting["title"],
        "url": posting["final_url"],
        "deadline": deadline,
        # Provenance for the report only; the writer ignores unknown keys.
        "intake_source": "owner-supplied link",
        "intake_url": posting["url"],
        "deadline_reason": deadline_reason,
        "availability": {
            "state": posting["vacancy"].get("state") or "UNKNOWN",
            "evidence": posting["vacancy"].get("evidence") or "",
        },
    }


def write_record(region: str, record: dict, apply: bool) -> dict:
    """Append through the guarded writer. Returns the writer's own result."""
    # Hermes points TMPDIR at its own scratch dir; never a bare /tmp here.
    scratch = pathlib.Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or ".")
    scratch.mkdir(parents=True, exist_ok=True)
    manifest = scratch / f"owner-link-{uuid.uuid4().hex}.json"
    manifest.write_text(json.dumps({"records": [record]}, indent=2), encoding="utf-8")
    cmd = [sys.executable, str(CLI), "write", "--region", region,
           "--manifest", str(manifest), "--preserve-existing-rows"]
    if apply:
        cmd.append("--apply")
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, cwd=str(CONTROL_PLANE))
    finally:
        # mkstemp-style handles are not held here, but Windows still refuses to
        # unlink a file another process has open -- the writer reads it first.
        try:
            manifest.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        result = json.loads(run.stdout)
    except Exception:  # noqa: BLE001 - the writer's stdout is the contract
        return {"state": "writer-failed", "exit_code": run.returncode,
                "stdout_tail": (run.stdout or "")[-800:],
                "stderr_tail": (run.stderr or "")[-800:]}
    result["exit_code"] = run.returncode
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    url = args.url.strip()
    if not url.startswith(("http://", "https://")):
        print(json.dumps({"state": "refused", "reason": "not an http(s) URL"}, indent=2))
        return 2

    posting = read_posting(url, args.timeout)
    gate = screen(posting)
    record = build_record(posting, args.region)

    report = {
        "url": url,
        "final_url": posting["final_url"],
        "fetch_state": posting["fetch_state"],
        "http_status": posting["status"],
        "readable": posting["readable"],
        "company": record["company"],
        "title": record["title"],
        "deadline": record["deadline"],
        "deadline_reason": record["deadline_reason"],
        "availability": record["availability"],
        "clearance": gate,
    }

    if gate["verdict"] == "STOPPED":
        report["state"] = "stopped-clearance"
        report["evidence"] = [
            {"token": e.get("token"), "context": e.get("context")}
            for e in gate["evidence"]
        ]
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 3

    if not record["company"] or not record["title"]:
        report["state"] = "refused-identity"
        report["reason"] = ("employer or role could not be read off the page; "
                            "refusing rather than guessing")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 4

    result = write_record(args.region, record, args.apply)
    report["writer"] = result
    counts = result.get("counts") or {}
    outcomes = result.get("outcomes") or []
    decision = outcomes[0].get("decision") if outcomes else None
    report["decision"] = decision
    report["counts"] = counts
    if result.get("error"):
        report["state"] = "writer-error"
    elif decision == "appended":
        report["state"] = "applied" if args.apply else "dry-run-appended"
    elif decision and decision.startswith("duplicate"):
        report["state"] = "duplicate"
        report["existing_row"] = outcomes[0].get("existing_row")
    elif decision == "rejected":
        report["state"] = "rejected"
        report["reason"] = outcomes[0].get("reason")
    else:
        report["state"] = "no-change"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["state"] in ("applied", "dry-run-appended", "duplicate", "no-change") else 1


if __name__ == "__main__":
    raise SystemExit(main())
