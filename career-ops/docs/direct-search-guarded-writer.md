# Direct search guarded writer and UK integrity recovery — 2026-10-17

Root cause: codex_entry_level_search.py appended/saved with its own openpyxl logic instead of the canonical writer. That bypassed shared write locking, verified backups, current-workbook dedupe, concurrency fingerprints and staged/post-write integrity verification. Restoring hyperlinks alone did not remove this parallel write path.

Direct search now delegates non-dry-run delivery to tracker_writer.write_records. It passes cleanup_existing=False so new-search delivery cannot delete unrelated existing passed/listing rows. Writer failures return a nonzero exit code without claiming success. Counts reflect the writer result, not the pre-write candidate list. No remaining direct wb.save path exists in the search command.

Canonical repair:
- Before hash: 41eb05be26c0e60c9985302aa3e6efd6697bc5634f895842039d8beee1863dd4
- After hash: 9f087ec2b9402bd1227f8c2723ff1db94aefdafbb593e51bae50c95d1f45d72a
- Eleven missing hyperlink entries D225:D235 rebound from their own displayed URLs.
- Original row 233 archived privately and removed as an exact unapplied duplicate of original row 230: Galaxy, Off-Cycle Fall 2026 Cybersecurity Internship, Greenhouse requisition 6163325004. All five non-URL fields match, including discovery date and Not Applied status. URL differs only by gh_src tracking. Other Galaxy rows from other sources were preserved.
- All other values/styles/comments preserved and verified after save/reopen. Six-column UK layout and status validation preserved. No other rows deleted or statuses changed.
- Shared exclusive lock, staged verification, immediate pre-commit source hash check and hash-verified backup used. Rollback only restores over bytes still owned by this repair.
- Private backup and complete archived row/audit: Documents/Codex/tracker-writer-recovery/uk-repair/. No workbook is committed.

Verification: canonical verify_workbook now returns ok=true, problems=[]. The read-only no-op write_records plan succeeds with zero appends/refreshes/deletions and applied=false. Affected regression suite: 217 tests (writer, repair, direct search, deadlines, regional search, liveness, digest and discovery). Repair tests cover source-preserving dry run, exact duplicate archival, rejection of applied records, concurrent-edit abort, shared locking and cleanup opt-out. Direct-search tests pin shared writer delegation and correct failure exit. Before/after previews were reviewed privately; no restyling was performed.

Remaining data review: Amey, QinetiQ and LHV Bank retain disputed visible URLs. They were neither guessed nor cleared; technical hyperlink correctness does not establish that those destinations match the named roles. The five existing listing/category URL rows were also preserved. Schedule enablement and live application actions are unchanged. No provider/search calls, applications, outreach, Gmail mutations or main merge occurred.
