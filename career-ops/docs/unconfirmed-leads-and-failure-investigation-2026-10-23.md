# Unconfirmed leads and failure investigation - 23 October 2026

Only the requested UNCONFIRMED tracker/digest policy was changed. The 26 failures were investigated, NOT fixed. No main merge, application, outreach, LinkedIn action, Gmail/Calendar access, CV/provider change or destructive Git operation.

## Tracker policy and live evidence

The scheduled launcher runs discovery then `promote_manifest.py --apply`, which delegates through `career_ops_cli.py write` to the shared guarded `tracker_writer.write_records`. Direct search uses the same writer. Eligible UNKNOWN vacancies are retained and appended with **UNCONFIRMED** visible before the URL in Apply Link, plus an explanatory Career Ops comment. Missing availability data also gets the tag. URL values/hyperlink targets and default application status are preserved; no seventh column. New OPEN rows do not inherit the uncertainty format. Repeat input deduplicates.

Confirmed closure/past deadlines, listing pages, unsuitable region/level/experience, prohibited clearance and insufficient employer identity remain independent blockers. UNKNOWN does not mean OPEN. Existing ambiguous records are not automatically merged/reclassified. Discovery cannot promise new suitable vacancies on every run.

The actual ChiefCareerScan-UK run on 22 October 23:45 BST completed at 23:59:23 BST with Task Result 0. The separate promotion receipt confirms **31 inputs, 20 actual appends, 11 duplicates, 0 refreshes, 0 deletions, verification OK**, growing UK from125 to145 rows. The discovery document's dry_run:true describes discovery, while its subsequent promotion explicitly records applied:true. Both UK tasks remain Enabled/Ready. No schedule was changed; other regions remain disabled.

Exactly21 existing Career Ops UNVERIFIED tags were migrated through the guarded writer to UNCONFIRMED. Hash-verified backup, exclusive lock, staged verification, immediate pre-replace drift check and post-write verification all passed. Replay made no further write. All145 rows, every cell value/formula, URL/hyperlink target and owner status/note stayed unchanged. Cell font/fill/border/alignment/protection compare equal to backup; only21 authorized formats and Career Ops comment prefixes changed. Six columns remain.

Before SHA-256: `ad38b32493619d4d3e76d15b1951aa1f05a66de0abc3cdfb851487dd5d1b4cc1`

After SHA-256: `b8027d178aa629c00285192394e8a5d970048593aad03c6794f80cc52d49e895`

Private recovery, verified backup, per-cell audit, JUnit, probes and style comparison: `C:/Users/mukun/Documents/Codex/career-failure-investigation-20261023`. Workbooks/runtime databases/raw private evidence are excluded from Git.

## 1. Mailbox layout and bounded apply: 4 failures

Two assertions are stale:

- `test_accepted_snapshot_recovers_dedupe_without_restoring_workbook` expects snapshot recovery count1. Its fixture now writes to the private sidecar, which survives rebuilding the workbook. WorkbookTracker.read merges the sidecar first: message IDs are recovered, so the later snapshot counter is correctly0.
- `test_ambiguous_snapshot_identity_is_never_fuzzily_merged` correctly receives an ambiguity refusal from the earlier sidecar merge. Its regex expects 'reconciliation', while the actual message is 'ambiguous mailbox sidecar identity'. Neither failure demonstrates fuzzy merging or lost dedupe.

Two tests expose an insertion contract gap, alongside stale layout expectations:

- `test_url_less_owner_row_occupies_append_position` still expects metadata in G/H, incompatible with the six-column canonical UK profile.
- `test_new_compact_application_preserves_existing_cells` tries to stage a new explicitly approved application.

The six-column/sidecar contract was intentionally introduced (`e360bff62`, `296a0f3b1`). WorkbookTracker._upsert_sidecar now updates metadata only for exactly one existing row and refuses new/ambiguous identities. However career_mail_bounded_apply.stage_workbooks and normal career_mail_monitor.apply_report still call tracker.upsert directly, with no canonical-writer delegation for an approved new row.

Controlled reproduction: isolated current-layout workbook + private LOCALAPPDATA. Existing metadata update succeeds, message dedupe survives, workbook hash unchanged. Passing an explicitly owner-confirmed new record to normal apply_report raises 'new or ambiguous mailbox application requires canonical writer reconciliation; no row restored', with workbook unchanged. The normal allowed-record filter can admit owner_confirmed_application, so this is reachable when such a new record is present. Ordinary uncertain new records are already review-only. This does not mean all existing Gmail updates are broken. An exception prevents successful checkpoint commit. No live Gmail scan/apply or OAuth health check was performed.

Next repair: approved unique new identities must go through canonical writer reconciliation before metadata upsert; keep uncertain records review-only, preserve owner data/six columns, and isolate/update sidecar fixtures. Do not restore G/H or the snapshot dependency.

## 2. LinkedIn publication gates: 2 failures, plus a real coverage flaw

The fixtures each provide the other passing gate. drafts_file(verdict=None) still creates a hash-bound passing news gate. approved_file(news=None) still supplies a passing personal gate. The test called 'no recorded review' is therefore not a truly unreviewed draft. Commit342847451 intentionally changed mandatory-both to applicable-gate behavior; b93f7459c accepted personal pass/warn verdicts. A correctly scoped news-only or personal-only post can legitimately need one gate.

But applicability is NOT established from the actual claims. linkedin_publish.preflight substitutes gate presence for coverage: absent personal+present news becomes personal coverage, and absent news+passing personal becomes proof there are no world claims. Personal verdicts are not bound to current body hash here. _gate_available only checks for a dict not explicitly unavailable.

Controlled reproduction: fake credentials, synthetic owner approval in private SQLite, PLAN only, publish stubbed to fail if invoked. No-gates control refused; intended single-gate controls passed. Mixed synthetic personal+external-claim bodies passed with only either gate. A personal PASS with wrong body hash also passed. Every case spent0 network calls. This proves planning coverage/hash gaps, NOT a historical publication or bypass of exact owner approval. Existing owner approval and news hash checks remain separate guards.

Read-only inspection also found runtime/linkedin/create_approved_drafts.py hardcodes a personal PASS without invoking the personal verifier, whereas the normal linkedin_workflow draft builder calls the personal fact gate. The runtime builder was not executed; which historical artifacts used it remains unproven.

Next repair: explicit claim scopes; every applicable gate over exact final body; no fabricated receipts; retain legitimate single-gate posts and exact owner approval. Add mixed-claim/stale-personal-hash negative tests. No LinkedIn code/config was changed here.

## 3. Legacy LinkedIn tracker handoff: 9 failures

All nine cascade from one early schema guard. linkedin_workflow.build_handoff_manifest calls company-watch/company_watch.py::provenance_targets, requiring a non-owner discovery/source field. Current UK six-column layout has neither. It refuses with 'no non-owner provenance column' and0 records. Tests then index absent keys or expect a write that never happened. Replay still being 'new' is not evidence that writer dedupe failed: the first handoff wrote nothing.

Controlled reproduction: current actual profile refuses; an in-memory legacy profile adding only a non-owner discovery field lets the same synthetic candidate build a one-record manifest. No real schema mutation/write. The explicit no-provenance refusal test passes.

Reachability: the legacy linkedin_workflow handoff CLI remains callable and returns1 on this refusal (it does not crash in that branch). Normal scheduled discovery reuses only its read-only intake/parser/classifier, then the shared pipeline/promotion writer, bypassing this legacy handoff. These nine failures do not block the proven scheduled20-row promotion; the legacy UK handoff is unsupported.

Next repair: preserve provenance outside owner columns via existing sidecar/manifest conventions, or formally retire the route and update tests. Do not grow the workbook or overwrite deadline/status.

## 4. UK rollover: 10 failures from fixture contamination

Tests copy the live canonical workbook, fix TARGET_MONTH to August2026, append2 probes and assume exactly2 target rows. Current workbook already has2 August rows (121/123 in this snapshot), both with protected owner Status. Four rows therefore match, and rollover correctly refuses owner-state loss. Archive/replay/health expectations cascade from the refused rollover.

Controlled proof: private pytest plugin changes ONLY pre-existing target-month date membership in temporary test copies before probes are appended, retaining every row/URL/status. With production code unchanged, all32 rollover tests pass, including owner-state refusal. The unmodified suite reproduces ten UK failures. No live rollover/archive/deletion occurred.

Next repair: synthetic isolated workbook fixtures or an empty fixture month, retaining separate read-only real-layout checks. Do not weaken owner-state protection to satisfy counts.

## 5. Singapore provenance integrity: 1 genuine guard blind spot

tracker_writer.verify_workbook groups duplicate keys by normalized URL+company+title, intentionally permitting distinct owner records to share a URL. It validates 'Career Ops duplicate discovery of <ID>' only inside those groups. Changing B33 company splits the group; the now-false acknowledgement in Z33 is no longer checked, so verification incorrectly stays OK.

Controlled proof on private copies: canonical baseline passes; changed company with false marker retained also passes (defect); changed company with marker removed passes (legitimate distinct-row control). Original duplicate identity with Applied owner status or arbitrary marker correctly fails. No Singapore canonical edit. This does not justify deleting/merging distinct owner applications.

Reachability: this verifier is used by writer post-write/recovery validation. Current canonical baseline is valid; no present corruption is asserted.

Next repair: validate every acknowledgement independently against a unique canonical ID/compatible identity, rejecting dangling/conflicting markers while preserving legitimate shared URLs.

## Validation and boundaries

- Focused writer/availability/tagging: **85 passed**.
- Six affected legacy suites, unchanged: **125 passed,26 failed**.
- Whole Career Ops: **1,444 passed,26 failed**,145.79s. Exact same failing IDs as previous1442/26; two new tests pass.
- Fixture-isolated rollover diagnostic: **32 passed**. This is not counted as repairing the original regression suite.
- Offline controls distinguish real gaps from stale expectations. No publication, credential access or live-mail operation was necessary.
- Only the requested tagging/digest changes were implemented. The unrelated failures await the next repair stage; no all-green or perfect-operation claim.

## Earlier17 proposals and exact failing test IDs

The appendix below identifies the17 proposals referenced in the earlier response. They are the22 October diagnostic snapshot, NOT a newly verified-open list. The later31-input scheduled promotion and20 actual appends are a separate run. Do not replay the earlier17 blindly. Distinct source URLs can still represent one employer requisition where no shared requisition evidence is available.

1. Apple - Information Security Internship - https://www.linkedin.com/jobs/view/4480402491
2. Tesco - IMS Technology – Cyber Security Graduate Scheme - https://www.linkedin.com/jobs/view/4468794494
3. KnowBe4 - Graduate Cybersecurity Threat Researcher (Position located in Cheltenham, United Kingdom) - https://www.linkedin.com/jobs/view/4479371170
4. Experian - Junior Information Security Officer - https://www.linkedin.com/jobs/view/4479091420
5. NCC Group - Associate Security Engineer - https://www.linkedin.com/jobs/view/4479522193
6. Bank of America - Global Technology, Cyber Security, Summer 2027 Analyst - Chester - https://www.linkedin.com/jobs/view/4460271848
7. Revolut - Internship Programme 2027: Information Security Engineer (Appsec) - https://www.linkedin.com/jobs/view/4433230351
8. Waterstons - Graduate Security Consultant (September 2027) - https://www.linkedin.com/jobs/view/4476010824
9. Revolut - Graduate Programme 2027: Information Security Engineer (Appsec) - https://www.linkedin.com/jobs/view/4433221716
10. Waterstons - Graduate Security Consultant - https://www.linkedin.com/jobs/view/4475250668
11. InfoSum - Junior Security Analyst (Basingstoke) - https://www.linkedin.com/jobs/view/4477808681
12. CoreTech Security - Vulnerability Researcher Internship - Summer 2027 - https://www.linkedin.com/jobs/view/4469156068
13. Laing O'Rourke - 2027 Group IT - Cyber Security Graduate - https://www.linkedin.com/jobs/view/4476201343
14. EY - Technology Risk Graduate Programme - September 2027 intake - https://www.linkedin.com/jobs/view/4477806240
15. Experian - Junior Information Security Officer - https://www.linkedin.com/jobs/view/4477464361
16. PA Consulting - 2027 Graduate - Digital Trust & Cyber Security Analyst - London - https://www.linkedin.com/jobs/view/4479976690
17. PA Consulting - 2027 Industrial Placement - Digital (Digital Trust & Cyber Security) - London - https://www.linkedin.com/jobs/view/4479983483

## Exact failing tests

- `career-ops.tests.test_career_current_layout::test_url_less_owner_row_occupies_append_position`
- `career-ops.tests.test_career_current_layout::test_accepted_snapshot_recovers_dedupe_without_restoring_workbook`
- `career-ops.tests.test_career_current_layout::test_ambiguous_snapshot_identity_is_never_fuzzily_merged`
- `career-ops.tests.test_career_mail_bounded_apply::test_new_compact_application_preserves_existing_cells`
- `career-ops.tests.test_linkedin_publish.TestPublishGuards::test_a_draft_with_no_recorded_review_is_refused_not_assumed_pass`
- `career-ops.tests.test_linkedin_publish.TestNewsClaimsGate::test_a_missing_news_record_is_refused`
- `career-ops.tests.test_linkedin_workflow::test_manifest_never_carries_application_state`
- `career-ops.tests.test_linkedin_workflow::test_manifest_provenance_names_the_linkedin_signal_source`
- `career-ops.tests.test_linkedin_workflow::test_handoff_dry_run_is_default_and_leaves_the_canonical_tracker_untouched`
- `career-ops.tests.test_linkedin_workflow::test_handoff_manifest_is_written_inside_the_linkedin_runtime_only`
- `career-ops.tests.test_linkedin_workflow::test_handoff_apply_to_a_copy_appends_verifies_and_leaves_canonical_untouched`
- `career-ops.tests.test_linkedin_workflow::test_replaying_a_written_linkedin_job_is_deduped`
- `career-ops.tests.test_linkedin_workflow::test_handoff_manifest_records_posted_date_when_known`
- `career-ops.tests.test_linkedin_workflow::test_ineligible_signal_is_excluded_from_the_manifest_by_default`
- `career-ops.tests.test_linkedin_workflow::test_ineligible_signal_can_only_be_included_as_a_labelled_test_row`
- `career-ops.tests.test_tracker_rollover::test_plan_is_read_only[uk]`
- `career-ops.tests.test_tracker_rollover::test_dry_run_writes_nothing[uk]`
- `career-ops.tests.test_tracker_rollover::test_rollover_archives_and_rotates[uk]`
- `career-ops.tests.test_tracker_rollover::test_rotated_rows_feed_the_cross_month_dedupe_index[uk]`
- `career-ops.tests.test_tracker_rollover::test_rollover_refuses_when_a_row_carries_owner_state`
- `career-ops.tests.test_tracker_rollover::test_archive_only_rerun_is_unchanged`
- `career-ops.tests.test_tracker_rollover::test_rotated_rows_can_be_restored_from_the_backup`
- `career-ops.tests.test_tracker_rollover::test_cli_rollover_emits_one_json_object[uk]`
- `career-ops.tests.test_tracker_rollover::test_run_health_records_both_workers`
- `career-ops.tests.test_tracker_rollover::test_cli_run_health_emits_one_json_object`
- `career-ops.tests.test_workbook_recovery::test_duplicate_discovery_ack_fails_closed_on_conflict[company]`
