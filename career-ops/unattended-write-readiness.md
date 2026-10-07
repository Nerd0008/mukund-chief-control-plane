# Career Ops unattended-write readiness recovery — 2026-10-07

This supersedes the blockers in `current-layout-scheduled-gmail.md`. Automatic writes remain disabled; this report does not authorize their activation.

## UK canonical metadata

Recovered 17 previously accepted application metadata records (20 Gmail signals), skipped 0. The source staged workbook was checked against the successful bounded-apply receipt, and every destination had one exact company/role/region match with identical posting host/path and reference evidence. Occupied/conflicting metadata would abort. Only the Career Ops identity/email metadata headers and cells were added; all pre-existing cells, including statuses, notes, formulas and styles, were compared unchanged. Other ZIP members were preserved byte-for-byte.

Before: `f1e35aeb27cfad1d700e4899a7ad780c191932af5d643603b45882ab4f3fc084`
After: `cd82b749f382545c7c88168d1fb03d86123662c21bf90f81dbc8f373ff9676a5`

Verified backups and private per-cell audit are under `%LOCALAPPDATA%\hermes\runtime\career-ops\gmail-monitor\unattended-recovery-2026-10-07`. Recovery uses an exclusive scan lock, verified backup, and source fingerprint checks before backup and immediately before atomic replacement. No old workbook was restored. `accepted_mail_state` was removed from the active regional profile: the normal adapter now reads all 17 records directly from the current canonical workbook.

## Regional integrity

Japan rows 43–62 are populated canonical job records dated 4–6 October, with company/title/posting URL. They were preserved. Only `JapanJobsTable` and its table filter were extended from `A1:Z42` to `A1:Z62`; worksheet content, formatting, formulas and other package members did not change.

Singapore row 17 is the original Ensign Technical Graduate Programme 2026 record (`SG-GRAD-260911-01`). Row 33 has the identical company/title/requisition URL and a later discovery date, but no ID, application status or owner detail. Neither row nor URL was removed. Row 33 now explicitly records that it is duplicate discovery provenance for the original ID. Verification accepts this relationship only if the original ID is unique, company/title/URL agree, the exact provenance marker exists, and the discovery row has no conflicting owner fields. Unresolved duplicates still fail; physical duplicates remain separately reported. Tests prove company, status or marker conflicts fail closed.

## Discovery contract

The six failures were stale test contracts. Commit `019e7a8576d7524be9f1cb1a973b984c19e67714` intentionally restored the native Codex/DeepSeek discovery adapters on 4 October from the earlier working implementation. Current classifier/pipeline signatures take adapter injection, not `e3_service`; native classifier names and escalation attribution are `deepseek_bulk` and `codex_second_pass`. Tests now use offline native-adapter doubles and still verify unhealthy-provider limitations, observed model resolution, classification safety, deterministic escalation, strict budgets, no unnecessary second pass, and rejection attribution. Production model transport was not changed.

## Production rehearsal

The normal Hermes Python command `career-ops/career_mail_monitor.py scan` ran in incremental dry-run mode from the verified baseline cursor. OAuth was ready with Gmail read-only and Calendar events-owned scopes. It inspected 30 messages: 9 recruitment signals, 1 existing match, 0 new rows, 21 ignored messages, and 8 new review signals. Tracker/Calendar/Gmail writes and model calls were zero. The original 45 review-only signals remain protected separately from that new window.

Report ID: `8530fe3adab65692b9467cdbeea6cf167d325c1895f2868dea71a7b5c8a40136`.

Accepted-state replay: 20 duplicate signals, zero repeat tracker writes. Three existing REVIEW calendar events verified via GET only with 24-hour/3-hour reminders; no event creation/update. Offline expired-history fallback: 20 duplicates, zero tracker/event proposals, no checkpoint. No persistent checkpoint or write approval was created.

## Validation

Native discovery plus recovery safety: 43 passed. Writer, rollover and recovery safety: 68 passed. Final entire Career Ops regression: **773 passed, 0 failed**.

All three requested blocker groups are resolved if the final regression is green. Enabling recurring writes remains a separate owner decision, with review-only identities still excluded. No main merge, Gmail mutation, application submission, outreach, or LinkedIn publishing.
