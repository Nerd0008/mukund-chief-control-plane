# Owner-scoped Gmail reconciliation

career_mail_bounded_apply.py binds a one-time subset to report c974caa787d82e6f31176e57dbab4d725bf4ed595e673ceeaceda4c906cb339f. It does not create write-approval.json, advance the Gmail checkpoint, change schedules or enable automatic writes.

Only the four explicit owner confirmations, freshly unique existing matches and three identity-review deadlines are eligible. The Calendar IDs are deterministic by employer/deadline; unknown-employer signals cannot generate reminders. Events use sendUpdates=none, no attendees, explicit review warning, source IDs and derivation metadata.

The command defaults to dry-run. --apply is only for this exact approved bounded operation. It reloads canonical workbooks, verifies fingerprints, preserves owner-confirmed metadata, stages changes privately, checks every original non-email cell, verifies backups and acquires Windows share=0 exclusive file handles before comparing expected hashes. Handles remain exclusive through commit and Calendar acknowledgement. Workbook data is flushed and read back; backups are retained for crash recovery. Calendar/workbook operations are not a distributed transaction; per-step receipts expose any partial failure.

The UK workbook was compacted externally. Only the exact six-header compact layout is recognized by this scoped adapter. Unknown layouts are rejected. Existing canonical statuses are preserved; only new owner-confirmed rows receive Applied. Shared Gmail threads cannot combine distinct full application roles.

Acceptance: four rows added, thirteen updated, three review events created/read back; zero remaining authorized tracker writes in the post-apply dry reconciliation. Final focused suites: 138 passed, zero failed. Two earlier legacy application_inbox real-workbook tests fail against the stale global UK layout binding; broader consumer integration must be reviewed before unrestricted automation. No global profile was changed by this task.

Public evidence is aggregate only. Backups, mailbox metadata, exact application/event IDs and owner reconciliation report remain under the private Hermes gmail-monitor runtime.
