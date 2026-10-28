#!/usr/bin/env python3
"""Every-2-hours UK job scan that reports only roles it has NEVER reported before.

Owner request: "run a job scan every 2 hours" / "I want unique new jobs found
related to me including graduate and internships roles".

Why a delta and not a digest
----------------------------
The 07:45 daily job prints every accepted role, every day, so the same roles come
round again and again. Running that every two hours would post the same list
twelve times a day. This script keeps a ledger of every apply URL it has already
reported and prints only the roles that are new to it, so a scan is either a
short list of genuinely new vacancies or nothing at all.

Where the roles come from
-------------------------
The search is the pipeline's own `codex_entry_level_search.py`, which asks the
Codex CLI for live graduate/internship/junior vacancies, drops anything already
in the tracker or failing the eligibility, liveness, clearance and prior-
experience gates, and appends the survivors to the canonical UK tracker through
the shared guarded writer. This script adds no scoring and no second opinion: the
tracker delta is the report.

Silence is deliberate
---------------------
A clean scan that finds nothing prints nothing, so the scheduler delivers
nothing. A scan that FAILS says so, because a job that quietly stops working is
worse than one that is noisy.

Usage
-----
    python job_scan_delta.py              # one batch, rotating query set
    python job_scan_delta.py --dry-run    # search + report, ledger unchanged
    python job_scan_delta.py --skip-search
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent
sys.path.insert(0, str(HERE))

from posting_identity import identity_keys
from career_search_recall import posting_key  # noqa: E402
from run_lock import acquire_run_lock, write_atomic  # noqa: E402

RUNTIME = CONTROL_PLANE / "runtime" / "career-ops"
LEDGER = RUNTIME / "scan-seen.json"
SEARCH = HERE / "codex_entry_level_search.py"
PY = sys.executable
REGION = "uk"
SHEET = "Jobs"
STATUS_COL = 6
URL_COL = 4

#: Two hours. Used to turn "now" into a query-batch slot so consecutive runs
#: advance through the query set instead of re-running the same batch all day
#: (the search's own default rotates by DAY, which would repeat every run).
SLOT_SECONDS = 7200

#: Raw stdout/stderr of the most recent search, kept so a cycle can always be
#: diagnosed after the fact. The scan stays silent on Discord when there is
#: nothing new, which previously left no evidence at all of what the search did.
SEARCH_LOG = RUNTIME / "job-scan-last-search.log"
CURSOR = RUNTIME / "job-scan-cursor.json"
RUNS = RUNTIME / "job-scan-runs"


def read_tracker(path: pathlib.Path) -> list[dict]:
    """Every data row with its real hyperlink target, not just the cell text."""
    import openpyxl

    wb = openpyxl.load_workbook(path, keep_links=True)
    ws = wb[SHEET]
    out = []
    for r in range(3, ws.max_row + 1):
        company = ws.cell(row=r, column=2).value
        if not company:
            continue
        cell = ws.cell(row=r, column=URL_COL)
        link = cell.hyperlink
        url = str((link.target if link is not None else cell.value) or "").strip()
        out.append({
            "row": r,
            "company": str(company).strip(),
            "title": str(ws.cell(row=r, column=3).value or "").strip(),
            "url": url,
            "deadline": str(ws.cell(row=r, column=5).value or "").strip(),
            "status": str(ws.cell(row=r, column=STATUS_COL).value or "").strip(),
        })
    wb.close()
    return out


def load_ledger(path: pathlib.Path) -> dict:
    """The `seen` mapping only - never the wrapper, or every role looks new."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    seen = data.get("seen")
    return seen if isinstance(seen, dict) else {}


def save_ledger(path: pathlib.Path, seen: dict) -> None:
    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(seen),
        "seen": seen,
    }
    write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def ct_key(company: str, title: str) -> str:
    """A company+title identity, matching the guarded writer's duplicate rule.

    URL identity alone is not enough. A role already tracked from an aggregator
    comes back from the employer's own ATS with a different URL, so a URL-only
    ledger calls it new and re-reports a role the owner already has. The writer
    already treats company+title as the same posting ("posting URL may have
    moved"), so the report uses the same rule and the two agree.
    """
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

    c, t = norm(company), norm(title)
    return f"ct:{c}|{t}" if c and t else ""


def role_keys(company: str, title: str, url: str) -> list[str]:
    """Use posting URLs and employer-scoped requisitions, never title equality."""
    keys = sorted(identity_keys(company, url))
    key = posting_key(url)
    return ([key] if key else []) + keys


def already_seen(company: str, title: str, url: str, seen: dict) -> bool:
    # Old ct: ledger entries cannot prove that another requisition is the same
    # vacancy. Current-run writer receipts prevent replaying old tracker rows.
    return any(k in seen for k in role_keys(company, title, url))


#: The search prints one of these per batch. They are the ONLY way to tell a
#: healthy empty cycle ("the web had nothing new") from a broken one ("Codex
#: returned nothing at all"), because both leave the tracker unchanged and both
#: print no new roles.
BATCH_RESULTS_RE = re.compile(r"batch\s+\d+:\s+(\d+)\s+results returned")
BATCH_TIMEOUT_RE = re.compile(r"batch\s+\d+:\s+TIMEOUT")


def batch_result_counts(stdout: str) -> list[int]:
    return [int(m.group(1)) for m in BATCH_RESULTS_RE.finditer(stdout)]


def search_failed(stdout: str) -> str:
    """A reason when the search ran but produced no usable results, else ''.

    Silence is the correct output for a healthy cycle with nothing new, but it is
    the WRONG output for a search that never ran: that would report an outage as
    "no new jobs" and the owner would never learn the scan had stopped working.
    """
    coverage = parse_tagged(stdout, "SEARCH_COVERAGE")
    if coverage and coverage.get("coverage_complete") is True:
        return ""  # an observed, completed query can legitimately have no results
    counts = batch_result_counts(stdout)
    timeouts = len(BATCH_TIMEOUT_RE.findall(stdout))
    if counts and all(c == 0 for c in counts):
        return f"every one of {len(counts)} batch(es) returned 0 results"
    if not counts and timeouts:
        return f"{timeouts} batch(es) timed out and none returned results"
    return ""


def run_search(offset: int, timeout: int, *, dry_run: bool = False) -> tuple[int, str, str]:
    cmd = [PY, str(SEARCH), "--region", REGION, "--batches", "1",
           "--batch-offset", str(offset), "--timeout", str(timeout)]
    if dry_run:
        cmd.append("--dry-run")
    try:
        proc = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout + 300, cwd=str(CONTROL_PLANE))
    except subprocess.TimeoutExpired:
        return 124, "", f"search timed out after {timeout + 300}s"
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def parse_tagged(stdout: str, tag: str) -> dict | None:
    """Read a `TAG {json}` line the search prints for machine consumption."""
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(tag + " "):
            try:
                return json.loads(line[len(tag) + 1:])
            except ValueError:
                return None
    return None


def search_found(stdout: str) -> list[dict]:
    """Proposed rows, used only for truthful unsaved-write diagnostics."""
    return current_run_roles(stdout, dry_run=True)


def tagged_records(stdout: str, tag: str) -> list[dict]:
    return [doc for line in stdout.splitlines()
            if (doc := parse_tagged(line, tag)) is not None]


def current_run_roles(stdout: str, *, dry_run: bool = False) -> list[dict]:
    """Attribute only verified append outcomes from this invocation's batches."""
    delivery = {posting_key(row.get("url")): row
                for doc in tagged_records(stdout, "SEARCH_DELIVERY") + tagged_records(stdout, "SEARCH_PROPOSALS")
                for row in doc.get("records", [])}
    roles = []
    tag = "SEARCH_RECONCILIATION" if dry_run else "TRACKER_WRITE_RESULT"
    for result in tagged_records(stdout, tag):
        if not dry_run and (result.get("applied") is not True or result.get("error") or result.get("problems")):
            continue
        outcomes = result.get("canonical_outcomes", []) if dry_run else result.get("outcomes", [])
        for row in outcomes:
            if row.get("decision") == "appended" and row.get("url"):
                detail = delivery.get(posting_key(row["url"]), {})
                roles.append(dict(row, status="Not Applied",
                    availability=detail.get("availability", {"state": "UNKNOWN"}),
                    deadline=detail.get("deadline", "")))
    return roles


def run_searches(offset: int, timeout: int, *, dry_run: bool = False,
                 max_batches: int = 3, budget_seconds: int = 1200,
                 pool_size: int = 1) -> tuple[int, str, str, dict]:
    """Move beyond duplicate-only batches, with bounded time and saved progress."""
    started = time.monotonic()
    outputs, errors, receipts = [], [], []
    code = 0
    next_offset = offset % max(1, pool_size)
    requested_batches = min(max(1, max_batches), max(1, pool_size))
    stop_reason = 'max_batches_reached'
    batch_timeout = max(1, timeout)
    for _ in range(requested_batches):
        remaining = budget_seconds - (time.monotonic() - started)
        # Admission includes the child's 300s hard-timeout grace and a margin.
        # Never squeeze an optional later batch: six workers sharing a remnant
        # budget caused five 18-30s timeouts in the 28 October production run.
        if remaining < batch_timeout + 305:
            stop_reason = 'insufficient_budget_for_full_batch'
            break
        current = next_offset
        code, out, err = run_search(current, batch_timeout, dry_run=dry_run)
        outputs.append(out)
        errors.append(err)
        coverage = parse_tagged(out, "SEARCH_COVERAGE") or {}
        complete = code == 0 and coverage.get("coverage_complete") is True
        receipts.append({"batch_offset": current, "exit_code": code, "complete": complete,
                         "coverage": coverage,
                         "reconciliation": parse_tagged(out, "SEARCH_RECONCILIATION"),
                         "new_rows": len(current_run_roles(out, dry_run=dry_run))})
        if not complete:
            code = code or 3
            stop_reason = 'batch_incomplete'
            break
        next_offset = (current + 1) % max(1, pool_size)
        if not dry_run:
            write_atomic(CURSOR, json.dumps({"next_offset": next_offset, "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}))
        roles = current_run_roles(out, dry_run=dry_run)
        if any((row.get("availability") or {}).get("state") == "OPEN" for row in roles):
            stop_reason = 'confirmed_open_found'
            break
        # Unverified leads remain labelled; use the remaining bounded budget
        # to look for independently confirmed-open vacancies.
    summary = {"batches_attempted": len(receipts), "query_pool_batches": pool_size,
               "completed_batches": sum(r["complete"] for r in receipts),
               "next_offset": next_offset, "elapsed_seconds": round(time.monotonic() - started, 2),
               "coverage_complete": bool(receipts) and all(r["complete"] for r in receipts),
               "market_exhausted": False, "batches": receipts,
               "stop_reason": stop_reason,
               "deferred_batches": requested_batches - len(receipts)
                   if stop_reason == 'insufficient_budget_for_full_batch' else 0}
    if not receipts:
        code = 3
    return code, "\n".join(outputs), "\n".join(errors), summary


def failure_summary(coverage: dict) -> str:
    """Expose only actionable categories/counts, never a raw JSON/provider tail."""
    from collections import Counter
    failures = Counter()
    completed = total = 0
    allowed = {'router_cli_timeout','router_cli_failed','router_cli_usage_limit',
               'router_cli_auth','router_cli_configuration','workflow_deadline_exceeded',
               'not_attempted_after_routing_block','batch elapsed budget exhausted','codex_rate_limited','codex_busy','router_cli_rate_limited','router_cli_busy'}
    for batch in coverage.get('batches', []):
        for result in (batch.get('coverage') or {}).get('query_receipts', []):
            for query in result.get('query_receipts', []):
                total += 1
                completed += bool(query.get('complete'))
                if not query.get('complete'):
                    reason = query.get('error')
                    # Keep raw command/provider details private; surface a stable
                    # cause for the subprocess timeouts captured in older receipts.
                    if isinstance(reason, str) and reason.startswith('TimeoutExpired:'):
                        failures['search_worker_timeout'] += 1
                    else:
                        failures[reason if reason in allowed else 'search_worker_failed'] += 1
        counts = (batch.get('reconciliation') or {}).get('counts') or {}
        if counts.get('verification_budget_exhausted'):
            failures['verification_budget_exhausted'] += counts['verification_budget_exhausted']
        if batch.get('exit_code') and not failures:
            failures['search_or_tracker_failure'] += 1
    detail = ', '.join(f'{key}={value}' for key, value in sorted(failures.items()))
    return f'{completed}/{total} queries completed; {detail or "search incomplete"}. Successful queries are retained for bounded retry; incomplete batches cannot write tracker rows.'


def write_ok(stdout: str, stderr: str, code: int) -> tuple[bool, str]:
    """Did the guarded writer actually persist this run's rows?

    `applied: false` on its own is NOT a failure. The writer also returns it for a
    clean no-op, which is exactly what a duplicate candidate or an empty candidate
    list produces. Treating that as a failure cried wolf: it told the owner to
    close Excel and re-run the scan when nothing had been blocked at all, and it
    reported a healthy cycle as broken. Only a real refusal counts here.
    """
    blob = f"{stdout}\n{stderr}"
    if "TRACKER_WRITE_BLOCKED" in blob or "PermissionError" in blob:
        return False, "the tracker was locked by Excel or refused the write"
    result = parse_tagged(stdout, "TRACKER_WRITE_RESULT")
    if result is None:
        # No candidates at all is a clean no-op, not a failure.
        if code == 0:
            return True, ""
        return False, f"search exited {code}"
    if result.get("error"):
        return False, f"the writer reported: {result['error']}"
    if result.get("problems"):
        return False, f"the writer reported {result['problems']} workbook problem(s)"
    if result.get("applied") is True:
        return True, ""
    counts = result.get("counts") or {}
    if counts.get("appended", 0):
        return False, "the guarded writer did not confirm the append"
    return True, ""  # nothing needed appending: duplicates or no candidates


def build_digest(items: list[dict], when: dt.datetime) -> str:
    lines = [f"New jobs - 2-hour scan - {when.strftime('%d %b %Y %H:%M')}",
             f"{len(items)} new role(s) found", ""]
    names = []
    for i, it in enumerate(items, 1):
        head = it["company"] if it["company"] != "Unknown" else it["title"]
        lines.append(f"{i}. {it['company']} - {it['title']}" if it["company"] != "Unknown"
                     else f"{i}. {it['title']}")
        lines.append(f"   {it['url']}")
        availability = it.get("availability") or {}
        if availability.get("state") != "OPEN":
            lines.append("   Availability: UNVERIFIED — lead, not a confirmed-open vacancy")
        if it.get("deadline"):
            lines.append(f"   Deadline: {it['deadline']}")
        lines.append("")
        names.append(head)
    lines.append(f"Summary: {len(items)} new role(s) - " + "; ".join(names))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tracker", default=None)
    ap.add_argument("--timeout", type=int, default=600, help="per-batch Codex timeout")
    ap.add_argument("--skip-search", action="store_true")
    ap.add_argument("--max-batches", type=int, default=3)
    ap.add_argument("--budget-seconds", type=int, default=1200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--batch-offset",
        type=int,
        default=None,
        help="override the search's query-batch rotation. Default: the 2-hour "
             "slot, so scheduled runs spread across the whole query set. Set it "
             "explicitly to walk the batches on demand (0..N-1); the search "
             "applies its own modulo, so any non-negative value is safe.",
    )
    args = ap.parse_args()

    lock = acquire_run_lock(RUNTIME / ".job-scan-delta.lock")
    if lock is None:
        print("a job scan is already running; skipping this cycle")
        return 0

    tracker = pathlib.Path(args.tracker) if args.tracker else _uk_tracker()
    if not tracker.exists():
        print(f"Job scan FAILED: tracker not found at {tracker}")
        return 2

    now = dt.datetime.now()
    seen = load_ledger(LEDGER)

    # First run: the roles already in the tracker are the baseline, so the owner
    # is not sent his whole existing list as "new" the moment this is switched on.
    baseline = not seen
    baseline_rows = read_tracker(tracker) if baseline else []
    if baseline:
        seen = {}
        for r in baseline_rows:
            for k in role_keys(r["company"], r["title"], r["url"]):
                seen[k] = now.isoformat()
        if not args.dry_run:
            save_ledger(LEDGER, seen)

    found: list[dict] = []
    ok, why = True, ""
    if not args.skip_search:
        import codex_entry_level_search as direct
        import owner_search_profile as owner_profile
        from career_search_recall import query_batches
        pool_size = len(query_batches(owner_profile.load_profile(), direct.REGION_LABEL[REGION],
                                      direct.QUERY_BATCHES[REGION], dt.datetime.now().year))
        slot = args.batch_offset if args.batch_offset is not None else direct.read_cursor(CURSOR, 0)
        code, out, err, coverage_summary = run_searches(slot, args.timeout, dry_run=args.dry_run,
            max_batches=args.max_batches, budget_seconds=args.budget_seconds, pool_size=pool_size)
        if not args.dry_run:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
            write_atomic(RUNS / f"{stamp}.json", json.dumps({"coverage": coverage_summary,
                "stdout": out, "stderr": err, "exit_code": code, "tracker": str(tracker)}, indent=2))
        if not args.dry_run:
            write_atomic(SEARCH_LOG,
                         f"# batch-offset {slot}  exit {code}\n{out}\n"
                         f"--- stderr ---\n{err}\n")
        found = search_found(out)
        ok, why = write_ok(out, err, code)
        if code not in (0,):
            print("Job scan FAILED: the search did not complete.\n"
                  f"exit {code}; {failure_summary(coverage_summary)}")
            # Earlier complete batches may already have committed verified rows.
            # A later failure must neither hide those rows nor report proposals
            # from the failed batch as saved. Keep the nonzero failure status.
            saved_rows = [r for r in current_run_roles(out, dry_run=args.dry_run)
                          if not already_seen(r["company"], r["title"], r["url"], seen)]
            if saved_rows:
                print("\nCompleted batches saved these rows before the later failure:"
                      if not args.dry_run else "\nCompleted batches proposed these rows:")
                print(build_digest(saved_rows, now))
                if not args.dry_run:
                    for r in saved_rows:
                        for key in role_keys(r["company"], r["title"], r["url"]):
                            seen[key] = now.isoformat()
                    save_ledger(LEDGER, seen)
            return 3
        broken = search_failed(out)
        if broken:
            print(f"Job scan WARNING: the search ran but produced nothing - {broken}. "
                  "This cycle proves nothing about new roles.\n"
                  f"Check Codex, then read {SEARCH_LOG}.")
            return 3

    rows = current_run_roles(out, dry_run=args.dry_run) if not args.skip_search else []
    new = [r for r in rows
           if r["status"] == "Not Applied"
           and not already_seen(r["company"], r["title"], r["url"], seen)]

    # If the tracker write was blocked, the roles still exist and the owner
    # should see them; they simply are not persisted yet.
    if not ok and not new:
        new = [f for f in found
               if not already_seen(f.get("company", ""), f.get("title", ""),
                                   f.get("url", ""), seen)]

    if baseline:
        print(f"Job scan baseline established: {len(baseline_rows)} existing role(s) recorded as "
              f"already seen. Only roles found from now on will be reported.")

    if not new:
        if not ok:
            print(f"Job scan WARNING: {why}. No new role was reported this cycle.")
            return 3
        return 0  # clean scan, nothing new: stay silent

    print(build_digest(new, now))

    if not ok:
        print(f"\nWARNING: {why}. The roles above were found but are NOT saved in the "
              f"tracker yet - close Excel and re-run the scan to persist them.")

    if not args.dry_run:
        for r in new:
            for k in role_keys(r.get("company", ""), r.get("title", ""),
                               r.get("url", "")):
                seen[k] = now.isoformat()
        save_ledger(LEDGER, seen)
    return 0


def _uk_tracker() -> pathlib.Path:
    """The canonical UK workbook, from the profile when it is readable."""
    try:
        import tracker_writer as tw
        cfg = tw.region_config(tw.load_profiles(), REGION)
        return pathlib.Path(cfg["tracker"])
    except Exception:  # noqa: BLE001 - fall back to the known location
        return pathlib.Path(r"C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx")


if __name__ == "__main__":
    raise SystemExit(main())
