# Tracker integrity recovery — 2026-10-13

Verified failure mechanism: openpyxl row deletion/movement changes cell coordinates but leaves existing hyperlink.ref values stale. Serialization can attach those links to other rows. Direct Hermes execute_code calls used openpyxl/delete_rows without rebinding hyperlinks. Canonical writer verification checked values/rows but not hyperlink targets/ref. The append function copies styles, not hyperlink objects; an append-only off-by-one is not established by this audit.

The locally modified UK profile removed column_ceiling=6 and reintroduced mail_identity in G. Mailbox upsert then appended its 20 metadata headers. The previous conditional ceiling guard could be bypassed by mail_identity. The six-column contract is restored, and the conflicting configuration is rejected.

Changes: validate required headers, column ceiling, hyperlink target and cell-coordinate identity. Rebind links from each row's own explicit URL before staging. Validate saved files before replacement. All discovery, mailbox and rollover writers share one fail-fast lock, hash checks and verified backups. The append writer restores its verified backup after an unexpected post-commit failure only if the canonical bytes still equal its own staged write; never overwrite a concurrent owner edit.

UK mailbox metadata uses a private sidecar keyed by application identity and exact company/role/posting evidence; metadata does not add columns. Deleted applications are not recreated. New or ambiguous mailbox applications require canonical writer reconciliation. Sidecar data and workbook copies remain private. Direct native-agent workbook/schema mutation is blocked by a separately installed career-tracker-integrity hook; normal audited CLI writes and unrelated tools remain available.

Owner decision: leave the 16 restored rows for review. This repair deletes/restores no job rows. UK core A–F values were preserved; existing email metadata migrated to the private store. Schedule applies temporarily disabled; owner-paused Hermes was not restarted. Guard hot-loaded through supported plugin activation.

Remaining source-data issues: duplicate displayed URL groups predate this repair (including unrelated employer/role pairs) and one URL-only phantom row. They require source reconciliation rather than guessing replacements or deleting jobs. Staged writer verification correctly blocks commits from that inconsistent baseline. Live-data writer/rollover tests consequently fail; isolated writer/lock/rollback/mail tests pass. Do not advertise unattended release-ready until source-data review is complete.

Private verified backup and audit: Documents/Codex/tracker-integrity-recovery-20261013. No canonical workbooks or mailbox metadata committed to Git.
