# Handover: fix the UK job scan (Codex)

**Date:** 2026-11-18
**From:** Chief of Staff (Hermes)
**Owner:** Mukund Didwania
**Repo:** `Nerd0008/mukund-chief-control-plane`, branch `fix/e3-whole-repo-architecture`
**Entry point:** `career-ops/job_scan_delta.py` (cron `5a66e1129e58`, `0 9 * * *`, daily 09:00 UK)
**Status:** the scan has failed 6 of its last 8 runs. It is not finding new roles.

---

## 1. What the owner sees

Every scheduled run prints:

```
Job scan FAILED: the search did not complete.
exit 2; 5/6 queries completed; search_worker_timeout=1, verification_budget_exhausted=1.
Successful queries are retained for bounded retry; incomplete batches cannot write tracker rows.
```

The owner has twice asked "run a job search again" and got this. The tracker has not grown from scanning since 17 Nov.

## 2. Verified evidence

Run artifacts: `runtime/career-ops/job-scan-runs/*.json`

| Run | exit | coverage_complete | elapsed |
|---|---|---|---|
| 20261118T155101Z-c6459714 | 2 | false | 784.36s |
| 20261118T091314Z-c7e37386 | 2 | false | 782.95s |
| 20261117T090814Z-e5e16fef | **0** | **true** | 446.83s |
| 20261117T062128Z-31833bb8 | 2 | false | 718.53s |
| 20261116T144734Z-ce2e2c16 | 2 | false | 783.86s |
| 20261112T104801Z-765e01f9 | 2 | false | 125.28s |
| 20261111T112837Z-c3319f57 | **0** | **true** | 710.83s |
| 20261111T103832Z-7d70d771 | 2 | false | 802.48s |

The 18 Nov 15:51 run artifact is the cleanest example. Batch offset 2, 6 queries:

```
security operations placement the UK 2027   complete  raw_events 20
grc placement the UK                       complete  raw_events 18
iam placement the UK 2026                  complete  raw_events  6
cyber risk placement the UK 2027           complete  raw_events 20
it support placement the UK                complete  raw_events 12
technology placement the UK 2026           INCOMPLETE
  error: TimeoutExpired: Command '[...codex.cmd exec --json --skip-git-repo-check
  --sandbox read-only --cd C:\Users\mukun\Documents\mukund-chief-control-plane
  --model gpt-6-sol -]' timed out after 98.0 seconds
```

Five of six queries returned real web-search events. The sixth was killed at 98.0s.

## 3. Root cause (verified, not inferred)

The per-query budget is too small for the slowest query, and one slow query
voids the whole batch.

`career-ops/codex_entry_level_search.py:342-356`:

```python
started = time.monotonic()
...
batch = provider.authorize_batch(executable, queries, timeout) ...
with batch:
    pending = sum(q not in saved for q in queries)
    available = timeout - (time.monotonic() - started)
    per_query = max(1, int(available / max(1, pending)))
```

- `--timeout` default is **600** (`job_scan_delta.py:402`).
- `authorize_batch` runs a router `select()` that consumes ~12s before the loop.
- `available` is therefore ~588-593s, and `per_query = int(588/6) = 98`.
- The observed timeout is exactly **98.0s**, matching this arithmetic.

So the budget is 98s per query. Query 6 of batch 2 needs more than 98s. It is
killed, `coverage_complete` becomes false, and
`codex_entry_level_search.py:817` returns 2:

```python
if not coverage['coverage_complete']:
    retain_candidates(args.region, collected, 'partial search or verification; retry with fresh verification')
    return 2
```

Nothing is written. The whole batch's 5 good queries are discarded for delivery.

Note the design intent in the docstring at line 328: *"Keep partial discoveries
and their coverage receipt, but never call a partial batch complete or write its
candidates automatically."* That intent is correct for eligibility safety. The
defect is that a single slow query costs the entire batch's delivery, every time.

## 4. The retry queue is never drained (second defect)

`retain_candidates()` writes to
`%LOCALAPPDATA%\hermes\runtime\career-ops\direct-search\uk-blocked-candidates.json`.
That file currently holds **148 records**, created 2026-11-18T15:51:01Z, reason
"partial search or verification; retry with fresh verification".

The file is read back at `codex_entry_level_search.py:582-586` and appended to
`work_batches` as batch `-1` (line 590). But `job_scan_delta.py:451` always
passes a **non-negative** offset:

```python
slot = args.batch_offset if args.batch_offset is not None else direct.read_cursor(CURSOR, 0)
```

and `read_cursor` rotates by day. Nothing ever passes `-1`. So the retained
queue is read, re-processed as a batch, and — when that batch also fails to reach
`coverage_complete` — written straight back. It has been growing since 18 Nov
and no retained candidate has ever been delivered.

`grep` for `blocked-candidates` shows only the writer, the reader, and one test.
There is no drain path.

## 5. Why this is worth fixing rather than working around

The Chief has been landing roles by hand from the failed runs' output (OCU,
Aviva, Xact, Corassure, KEYENCE). That is not sustainable and it is not the
owner's intent. The scan is the discovery engine; it is currently decorative.

Also worth knowing: even on the two successful runs, the yield was small. The
17 Nov run reconciled 144 records → 120 already tracked, 5 new. The 18 Nov run
reconciled 156 → 108 already tracked, 5 new. Most of what the scan surfaces is
already in the tracker. Fixing the timeout will not flood the tracker; it will
just make the scan reliable.

## 6. Suggested fix (recommended, in this order)

**A. Make a partial batch deliverable without weakening the safety gate.**
The current rule is all-or-nothing per batch. Change it so that queries which
returned `web_search_observed: true` with no error are eligible for the normal
eligibility and verification pipeline, and only the incomplete queries are
retained. Keep the "never write unverified eligibility" rule intact: a query
with no observed search still cannot produce a row. This is the real fix.

**B. Raise the per-query budget, or make it adaptive.**
98s is too tight. Options:
- raise `--timeout` from 600 to 900 (per-query becomes ~148s), or
- allocate the budget so a slow query does not starve the rest, e.g. reserve a
  floor per query and allow one query to borrow from the remainder, or
- run the six queries concurrently instead of sequentially.

Do not simply raise the timeout without (A): a longer budget means a longer
stall before the same all-or-nothing discard.

**C. Drain the retained queue.**
Either pass `-1` on the next run so batch `-1` is worked, or add a scheduled
drain. As written, 148 retained records are inert.

**D. Fix the cron's success reporting (already partly done).**
`job_scan_delta.py` exits 0 on some failure paths, which is why six consecutive
failures showed `last_status: ok`. The operational evidence now correctly reports
`phase: FAILED`, `last_status: error`, `writes: 0` for the 18 Nov runs. Verify
this holds for every failure path, and make sure `failure_streak` increments.

## 7. Constraints

- **Do not weaken the eligibility/clearance gates.** The owner's standing rule
  (17 Nov) is that only a security-clearance or citizenship requirement justifies
  stopping. Everything else is drafted. The scan's clearance gate must stay.
- **Do not write unverified availability as OPEN.** The availability gate was
  deliberately reversed on 22 Oct: only positive evidence of closure blocks a
  role; UNKNOWN is still added. Keep that.
- **The tracker is authoritative.** `C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx`,
  sheet `Jobs`, header row 2, data from row 3. All writes go through
  `career-ops/tracker_writer.py` (`write_records`). Never write the workbook
  directly — a direct write breaks hyperlink binding and post-write verification.
- **Warm-site rule.** Commit and push. The repo must stay deployable within
  hours. Branch `fix/e3-whole-repo-architecture`; no main merge.
- **Tests.** `career-ops/tests/test_scan_budget_admission.py` and
  `test_scan_query_recovery.py` cover the current budget behaviour and will need
  updating. Run from the repo root:
  `C:/Users/mukun/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -m pytest career-ops/tests/`
- **Do not stage unrelated files.** The working tree carries other agents'
  in-flight work (`runtime/linkedin/*`, `runtime/incidents/*`,
  `runtime/career-ops/run-health/*`). Stage only files you authored.

## 8. How to verify the fix

1. Run the scan by hand:
   `python career-ops/job_scan_delta.py` from the repo root.
2. Confirm `exit_code: 0` and `coverage_complete: true` in the newest
   `runtime/career-ops/job-scan-runs/*.json`.
3. Confirm the tracker row count grew and `career_ops_cli.py verify --region uk`
   returns `ok: true`.
4. Confirm `uk-blocked-candidates.json` stopped growing.
5. Confirm the cron's next 09:00 run reports `last_status: ok` with real writes,
   and that a deliberately broken run reports `error`, not `ok`.

## 9. Open questions for the owner (not blockers for Codex)

- The scan schedule is **daily at 09:00**, not every 2 hours as the job's name
  and prompt claim. The owner was told on 17 Nov and has not decided.
- Should the scan run more than once a day once fixed? The owner has not said.
