# UK scan ten-run failure: diagnosis and tested repair

30 October 2026, Europe/London. Branch fix/e3-whole-repo-architecture. No main merge.

## Exact cause

All ten saved runs from 01:13 through 19:47 on 30 October completed query work and
failed at the same canonical workbook replacement. Their stderr names:

`TRACKER_WRITE_BLOCKED [WinError 5] Access is denied: uk-cyber-job-tracker.write-tmp.xlsx -> uk-cyber-job-tracker.xlsx`

The last successful run was 29 October23:08:46, which saved two rows. The canonical
workbook was not subsequently replaced by those ten failed transactions.

Windows Restart Manager identifies Microsoft Excel PID14388 as the actual file holder.
Non-mutating CreateFile probes establish read allowed, write denied with sharing
violation32, DELETE access denied with sharing violation32. ACL grants the owner full
control and the file has Archive attributes, not ReadOnly. This is a live Excel sharing
lock, not guessed bot-wall/provider failure, missing filesystem permission, or bad JD.
No process was killed and no owner workbook was closed or overwritten.

## Software defects that amplified the lock

1. Direct search returned exit2 after a successful search when the writer could not
   commit. The parent returned3 and printed search did not complete, with only the
   generic search_or_tracker_failure category. The alert hid the precise failing stage.
2. Search cursor advancement was coupled to successful Excel delivery. Cursor stayed9
   for ten cycles, repeatedly returning to the same query batch. Saved query progress
   helped reuse successful queries, but it did not advance coverage.
3. A durable blocked-candidate queue already existed. The repair reuses it; it does
   not introduce a second ledger/writer, bypass locks, or report queued jobs as saved.

## Changes

- New tracker_delivery.py distinguishes confirmed Windows sharing conflicts from
  arbitrary access, disk, validation and integrity errors.
- It tests DELETE sharing without deleting or writing. A positive probe defers the
  write. It also rechecks after a commit exception to cover Excel opening mid-transaction.
- A candidate queue must be successfully saved BEFORE search progress advances.
  Queue failure stays a failure; unclassified permission/storage errors stay failures.
- Direct search emits TRACKER_WRITE_DEFERRED with applied=false, zero tracker writes,
  retained candidate count, pending proposal count and requires_fresh_verification=true.
- Completed search progress can advance while delivery waits. The parent stops the
  current bounded cycle on deferral and reports a completed search with pending delivery,
  exit0. It does not reset schedules or silently disable scans.
- Existing retry records are still subject to the existing fresh fetch, eligibility,
  identity, deadline and canonical dedupe logic before the writer can deliver them.
- Actual non-busy commit failures now emit TRACKER_WRITE_FAILED with stage and safe
  exception metadata; parent failure summaries name tracker_write_failed.
- No workbook layout, statuses, hyperlinks, row deletion, eligibility policy, providers,
  approval settings or scheduler configuration was changed by this repair.

## Tests and reproductions

Focused final run:97passed (new delivery tests, existing delta tests and writer tests).
An additional exact-staged-source test is recorded in the execution results.

The new Windows test holds a private canonical file open with Excel-style sharing,
reproduces os.replace failure, verifies original bytes preserved, observes deferred
retention and cursor order, releases its own test handle, then successfully replaces
the private file. No live lock is bypassed.

Other regressions cover retention failure, generic ACL/disk failures remaining hard
errors, successful writer return, complete-search cursor advancement, stopping further
queries after deferral, zero claimed deliveries, stage-specific error reporting, and
an incomplete-coverage marker never being hidden by a deferred receipt.

Wider search suite:133passed and11failed. The exact same11failures were independently
reproduced using pre-repair source loaded in another process; production files were
never reverted. They concern earlier eligibility/policy expectations (experience,
student status, title overlay, closure, unresolved employer identity), intake-variant
dedupe and recall accounting. Their names and traces are in scan-baseline-tests.log
and the broad/baseline JUnit reports. These are not presented as green or silently
changed to fit this repair. Existing owner-policy edits remain untouched.

## Live acceptance

Real production command:
`career-ops/job_scan_delta.py --max-batches 1 --timeout 600 --budget-seconds 1200`

Exit0, completed search,14proposed rows retained pending Excel delivery. No claim of
saved rows. Cursor advanced9->10 at21:11:37. This is a delivery-deferred result, not
proof that every retained posting is suitable or currently open.

Canonical SHA-256 before and after:
`45c2b523c14c1d87ed420b0b6684fa362ed37ee7b25d3e261cffad96f7b3170b`

Excel still held the canonical workbook at read-back. Live append recovery therefore
remains unverified until the owner saves/closes it. Private Windows unlock/retry
recovery passed. The existing scheduled scan will use the patched entrypoint on its
next invocation; no gateway restart is needed for these standalone script changes.
Historical failed-run counts remain historical until the scheduler records a new run.

## Preservation and evidence

Pre-edit source copies, dirty diff, staged diff and status are in this recovery folder.
Only this repair's hunks are staged; unrelated working-tree changes are not included.
Live output: sibling scan-repair-live-20261030.log.
Focused JUnit: sibling scan-repair-final-tests.xml.
Broad and baseline evidence: sibling scan-repair-broad-tests.xml, scan-baseline-tests.xml,
scan-baseline-tests.log. Lock reproduction: sibling scan_lock_probe_20261030.py.

Required owner action: save and close the UK tracker. Do not terminate Excel, discard
unsaved edits, delete lock files, weaken ACLs or overwrite the workbook in place.
