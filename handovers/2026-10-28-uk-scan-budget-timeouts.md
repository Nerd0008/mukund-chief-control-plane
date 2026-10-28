# UK scheduled scan timeout repair — 28 October 2026

## Reproduced cause

Cron 5a66e1129e58 failed after its 13:23 invocation. Its receipt
20261028T133835Z-c64a3375 records two complete six-query batches (offsets 4
and 5), followed by offset 6 with only one complete query. The five errors
are subprocess TimeoutExpired, with 30, 30, 28, 25 and 18 second limits.
They are not evidence of a Nous outage, authentication loss or quota failure.

The outer loop reserved 305 seconds for child grace but squeezed each later
batch into whatever remained of the 1200-second total. The inner loop divided
that already reduced search allowance across six queries and recalculated it
after each attempt. Thus starting an optional extra batch manufactured very
short worker deadlines. An offline clock replay reproduced 600 -> 475 -> 195
second batch allowances; the test failed before the change.

## Repair

- Admit a batch only if its entire configured search timeout plus 300-second
  child grace and five-second margin fits. Never shrink a later batch.
- Keep the cursor at the next unattempted batch; record stop_reason and
  deferred_batches. Completed launched batches remain successful; a run with
  no admitted batches remains unsuccessful. Never claim market exhaustion.
- Allocate worker time once, after router authorization, across unsaved
  queries. If a full slice no longer fits, defer that query without launching
  a progressively shorter worker. Saved successful queries remain reusable
  with their original observation timestamps and existing expiry checks.
- Classify legacy TimeoutExpired receipts as search_worker_timeout in the
  alert without exposing private command/provider details.

A second reproduced defect hid an earlier successful writer append when a
later batch failed. The incident actually appended one EY Belfast graduate
programme row with UNKNOWN availability before the later timeout. The failure
branch now reports only confirmed earlier appends and records their delivery
identities, while retaining the nonzero failure exit. Unconfirmed proposals
and failed-batch candidates cannot become reported saved jobs. Partial batches
still cannot write. No JD, eligibility, clearance or availability guard changed.

## Validation

- Five new budget/alert cases failed before repair; the additional confirmed
  earlier-append reporting case also failed before its repair.
- Final focused suite: 101 passed.
- Broader relevant search suite: 352 passed, including query recovery, direct
  search, tracker attribution, web research, JD transport, application links,
  availability, country retry and eligibility protection.
- A real one-batch production-entrypoint retry was launched from offset 6
  using the existing Hermes Python and guarded tracker writer. Its final
  receipt and workbook reconciliation are retained in private recovery evidence.
  Completed 14:14:47 UTC with exit 0, 6/6 queries complete (one reused from the
  failed run, five freshly completed), cursor 6 -> 7. No new tracker rows; the
  workbook remained byte-for-byte unchanged, with 173 data rows and zero
  integrity problems. Total bounded retry elapsed approximately 363 seconds.

Normal Hermes two-hour scanning and the daily digests stay enabled. The
separate Codex overnight campaign remains paused. The existing cron launcher
starts the repository entrypoint afresh, so no gateway restart is needed.

Recovery evidence: C:/Users/mukun/Documents/Codex/uk-scan-failure-20261028-133835.
It contains the original receipt/log/cursor, source snapshots and diffs,
test XML, live retry evidence and a private pre-run workbook backup. Private
evidence, runtime artifacts, credentials and owner profile data are not staged.
The pre-existing jd_screening_required source hunk is preserved and excluded
from this repair commit, along with the other unrelated dirty files.
