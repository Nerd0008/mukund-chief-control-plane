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

HERE = pathlib.Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent
sys.path.insert(0, str(HERE))

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
    keys = []
    u = posting_key(url)
    if u:
        keys.append(u)
    k = ct_key(company, title)
    if k:
        keys.append(k)
    return keys


def already_seen(company: str, title: str, url: str, seen: dict) -> bool:
    return any(k in seen for k in role_keys(company, title, url))


def run_search(offset: int, timeout: int) -> tuple[int, str, str]:
    cmd = [PY, str(SEARCH), "--region", REGION, "--batches", "1",
           "--batch-offset", str(offset), "--timeout", str(timeout)]
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
    """The candidates the search accepted this run, with their apply URLs."""
    doc = parse_tagged(stdout, "SEARCH_RECONCILIATION") or {}
    out = []
    for d in doc.get("decisions") or []:
        if d.get("reason") != "new candidate" or not d.get("url"):
            continue
        out.append({
            "company": "Unknown",
            "title": str(d.get("title") or "").strip(),
            "url": str(d.get("url") or "").strip(),
            "deadline": "",
            "location": "",
        })
    return out


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
    if baseline:
        seen = {}
        for r in read_tracker(tracker):
            for k in role_keys(r["company"], r["title"], r["url"]):
                seen[k] = now.isoformat()
        if not args.dry_run:
            save_ledger(LEDGER, seen)

    found: list[dict] = []
    ok, why = True, ""
    if not args.skip_search:
        slot = (args.batch_offset if args.batch_offset is not None
                else int(dt.datetime.now(dt.timezone.utc).timestamp() // SLOT_SECONDS))
        code, out, err = run_search(slot, args.timeout)
        found = search_found(out)
        ok, why = write_ok(out, err, code)
        if code not in (0,) and not found:
            print("Job scan FAILED: the search did not complete.\n"
                  f"exit {code}; {(err or out).strip()[-400:]}")
            return 3

    rows = read_tracker(tracker)
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
        print(f"Job scan baseline established: {len(seen)} existing role(s) recorded as "
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
