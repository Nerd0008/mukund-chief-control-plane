# Current UK layout and scheduled Gmail verification — 2026-10-07

The accepted apply was ee1e861c18fb705c24027578ba0db5cecad8de87. Before this repair, d065a1650 migrated regional_profiles.json to the six-column UK workbook, but consumers and fixtures still assumed header row 1, a mandatory job ID, an Excel table, and the older status vocabulary. The bounded apply had its own hard-coded compact-layout translation; the normal Gmail monitor did not share it.

## One layout authority

`regional_profiles.json` now exclusively defines UK header row 2, data from row 3, A–F core columns, no mandatory canonical ID or Excel table, optional email identity in G, and optional discovery provenance outside the email metadata columns. `career_tracker_layout.py` validates configured headers. Both bounded apply and scheduled `WorkbookTracker` use this validation; the generic writer and legacy inbox also consume the same profile. Historical owner statuses are normalized on read, never rewritten in the workbook.

The audit fixed URL-only row extent (which could overwrite approved applications with no URL), mandatory-ID assumptions in inbox/CLI/brief/CV/rollover, plain-range archive handling, and stale hyperlinks that resurrected deleted URLs after reload. The UK digest no longer defines another layout. Offline scheduled rehearsals no longer probe or escalate to a live provider automatically. An actual incremental Gmail message exposed an HTML `<img alt>` parser TypeError; it is fixed and tested.

## Production binding

The deployed `career-gmail-monitor` Hermes skill points directly at this repository's `career_mail_monitor.py` and the Hermes venv interpreter. No copied live Gmail adapter was found. The old schema file under Hermes cache/scratch/schema/pristine is historical, not the scheduled binding. Existing Career Scan tasks invoke `run_scheduled_scan.cmd` → `discovery/scheduled_orchestrator.py` → shared tracker writer/profile. They were not changed. No Gmail hourly task was installed or enabled. `schedule-plan` remains disabled and now proposes a dry `scan`, not `scan --apply`.

The exact normal command was run with the owner interpreter:

```
C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe career-ops/career_mail_monitor.py scan
```

It used the original hash-verified report cursor 1019003, read only subsequent history, and inspected 30 messages: 9 recruitment signals, 1 existing match, 0 proposed new rows, and 8 new review signals. OAuth was ready with Gmail read-only and Calendar events-owned scopes. Tracker, Calendar and Gmail writes were all zero. No checkpoint or write approval exists. The current workbook fingerprints equal those captured by the normal scan.

Dry-run ID: `4254052c711b4eca234bf17a799fb56bf53f775d764c16889890d176fd548a8c`.

## Accepted-state preservation

During verification the UK workbook was found reduced to six columns; its email metadata was missing, although the four approved application rows remained. Last write observed: 2026-10-07T20:03:51Z. The actor responsible was not proved; do not attribute it from timestamp alone. Naive replay proposed 17 repeat updates.

The existing private accepted staged workbook still matches the successful apply receipt. The adapter now reads that snapshot without restoring any canonical file. Recovery requires a successful apply/audit, matching snapshot hash, unique exact company/role/region, identical posting host/path and reference IDs, and no conflicting current application identity. Current row/owner status stay authoritative. Missing, modified, ambiguous or conflicting evidence fails closed. This restores 17 accepted application metadata records in memory, avoids all 20 authorised signal duplicates and proposes zero further authorised writes. The original 45 review signals remain review-only.

Three existing REVIEW Calendar events were read back using GET only; all remain present with 24-hour/3-hour reminders. No event was created or updated. An offline 404-history simulation used actual accepted message IDs with explicitly synthetic envelopes: bounded backfill, 20 duplicates, zero tracker/calendar proposals and no saved checkpoint. This is fixture fallback proof, not a second live 30-day scan.

Private evidence stays under `%LOCALAPPDATA%\hermes\runtime\career-ops\gmail-monitor\scheduled-rehearsal-2026-10-07`. Only aggregate evidence is committed. The verified staged snapshot must be retained; it is now an explicit read dependency, not an approval for unrestricted writes.

## Validation and blockers

Final focused Gmail/second-pass/bounded-apply/current-layout/application-inbox/scheduled/LinkedIn handoff suites: **314 passed, 0 failed**. Whole Career Ops: **751 passed, 15 failed**.

Remaining failures were not hidden or weakened:

- Japan canonical table ends at row 42, while data reaches row 62: 2 failures, including verification of the byte-identical restored test copy.
- Singapore has a duplicate Ensign posting URL: 7 writer/rollover failures. No owner row was deleted or merged.
- Existing discovery classifier/pipeline tests expect `e3_service` injection and `e3_bulk` escalation, while implementation exposes the native-adapter contract: 6 failures. These files were left unchanged under the prohibition on unrelated Hermes/E3 changes.

Read-only unattended scans now work through the normal adapter. Unattended automatic writes are **not release-ready**: all-regression-green is not satisfied, workbook integrity repair needs review, and the missing UK metadata columns still require an owner-approved canonical reconciliation or continued verified-snapshot dependency. Do not install/enable scheduled writes. No main merge, application submission, outreach, Gmail mutation, or live LinkedIn action occurred.
