# Career Ops regression repairs - 23 October 2026

## Scope

Repair the five investigated failure groups from `unconfirmed-leads-and-failure-investigation-2026-10-23.md`, investigate related defects before changing them, and retain the six-column UK workbook, owner data, Gmail read-only boundaries and UNCONFIRMED lead policy. Branch: `fix/e3-whole-repo-architecture`. No main merge.

## Confirmed causes and repairs

| Group | Original failures | Repair |
|---|---:|---|
| Mailbox adapter / bounded apply | 4 | Connect explicitly owner-confirmed new applications to the shared guarded writer; keep metadata in the existing sidecar; correct two obsolete snapshot/error assertions. |
| Publication review | 2 | Require independent news and personal coverage of the exact final post, validate body/scope hashes and process results, and refuse blocked artifacts without a valid exact owner override. |
| LinkedIn tracker handoff | 9 | Store UK provenance in the durable handoff manifest, preserve six columns and owner rows, propagate writer failures, and retain repeat dedupe. |
| UK rollover | 10 | Isolate the fixture's target month in temporary workbook copies. Preserve the production owner-state refusal and archive/dedupe behavior. |
| Singapore integrity | 1 | Validate every duplicate-discovery acknowledgement against a unique parent ID and matching URL/company/role, even after it leaves a duplicate group. Preserve distinct owner records sharing a URL without a false acknowledgement. |

The 26 failures were not 26 separate production bugs. Some were stale layout/counter/message assertions; the implementation defects were reproduced separately before repair. No production safety gate was weakened to satisfy an outdated test.

## Mailbox safety details

- Existing application metadata continues through the sidecar. Only explicitly owner-confirmed, non-review, new identities can use the trusted mailbox insertion option; ordinary discovery/CLI input cannot set Applied or omit its URL requirement.
- The shared writer is called while the existing mailbox/discovery lock is held. Owner rows are preserved; no existing-row cleanup runs. No URL is fabricated when an approved application lacks one.
- Conflicting posting evidence, ambiguous exact identities, stale row references and known owner-deleted applications fail closed. Incoming public posting identity uses one canonical projection.
- New confirmed rows receive Applied based on explicit owner confirmation; owner status in existing rows is never changed by this insertion path.
- Workbook-before/after and metadata drift checks, verified backups, staged verification and replay protection remain. If metadata fails after the new workbook row is committed, the caller must not advance its checkpoint; retry reconciles that row rather than appending again. This is resumable ordered commit, not a claim of a distributed atomic transaction.
- Bounded staging now copies the sidecar into its private staging directory. It does not write live metadata while preparing workbook bytes. Commit validates original workbook and metadata hashes under the same shared locks, then persists audited changes. Concurrent metadata changes abort rather than being overwritten.

## Related defects investigated and closed

1. **Premature staging metadata writes:** stage_workbooks previously changed only the workbook path, leaving the sidecar bound to the live runtime. New tests prove staging leaves both original workbook and sidecar untouched and that drift/overlapping writers block commit.
2. **False-success handoff:** a mocked writer returning exit0 plus a JSON error was reported OK. The handoff now validates the result/error/verification receipt as well as the exit code.
3. **Owner-row cleanup in handoff:** automated Company Watch/LinkedIn handoffs now explicitly request preserve-existing-rows. The older Company Watch test helper omitted that flag and deleted existing Passed rows in its private copy; it now exercises the actual production contract.
4. **Combined-draft personal verdict:** one review over combined drafts was copied to every post without individual text binding. Normal generation now calls the verifier for each actual review scope and binds each receipt to that post's exact body.
5. **Fabricated legacy personal PASS:** the ignored runtime-only `runtime/linkedin/create_approved_drafts.py` contained a hardcoded personal PASS and a source-free news PASS. It now invokes the actual canonical review helpers. Its private embedded post content is not committed; the code-only, zero-context patch is versioned as `legacy-linkedin-builder-review.patch.json`. The runtime script was syntax-inspected, not executed or scheduled.
6. **Spreadsheet formula injection:** an explicitly confirmed company value beginning with '=' was stored as a formula in a private reproduction. Incoming mapped string values are now literal text on append/refresh. Template-owned formulas remain formulas; the regression distinguishes these paths.
7. **Sidecar test isolation:** once a legacy test could successfully insert a row, its temporary workbook still used the owner's LOCALAPPDATA sidecar. One synthetic record was briefly written there. The exact hash-verified pre-test backup was recovered, all other records compared equal, and that sidecar was restored under the shared lock. No owner workbook row changed. Both affected mail test modules now isolate LOCALAPPDATA automatically. Final owner-state hashes must equal the restored baseline.
8. **Normal metadata lost-update window:** an external private-sidecar edit injected during serialization was overwritten in the original reproduction. Normal upsert now fingerprints the sidecar, verifies its backup and checks it again immediately before replacement. The test now refuses the write and preserves the injected external revision.
9. **Contradictory review state:** a blocked flag with passing verdicts, or a PASS paired with failed verifier exit status, could pass preflight. Both are refused. Exact owner fact-check override remains distinct from ordinary publish approval.
10. **Subject-blind CV facts verifier:** a real local probe blocked both 'A vendor reports 500 million active users' and 'I supported 500 million active users' as fabricated candidate achievements. Applying it blindly to news would reproduce false blocks. `linkedin_personal_review.py` conservatively projects out only clearly attributed reporting clauses from an entirely non-personal post. First-person, implicit-career, mixed and ambiguous content is reviewed in full. Every scoped receipt records the full body hash, reviewed-text hash and scope version; publication recomputes that scope. The independent news gate is still mandatory over the whole post, so excluded news is not unchecked content.

## Review boundaries

Personal/news-only content remains possible: each relevant specialist verifier runs, with the personal verifier receiving no candidate claims for clearly attributed non-personal reporting. A missing review record is never inferred to mean 'no claims'. Mixed or ambiguous content keeps conservative full-text personal review and may need wording correction; this is not a semantic guarantee that every legitimate post will pass automatically. Old artifacts missing exact-body reviews require fresh verification. Owner approval, current-body hash, cancellation, duplicate publishing and source/news checks remain separate guards. No LinkedIn publish action was performed.

The attribution projection is deliberately conservative and tested for first-person, implicit CV bullets, own-project context, mixed text, stale/unknown scope receipts and actual local fact-checker results. It does not modify the CV compiler or the underlying CV facts verifier, and does not waive news verification.

## Verification

- Entire Career Ops, final frozen source: **1,510 passed, 0 failed**, 163.94 seconds (16 warnings).
- All26 original failing test IDs are present and pass. Forty regression cases were added.
- Related Company Watch suite: **35 passed, 0 failed** (part of the separate48-test Company Watch/mail integration run).
- Focused personal-scope, generation and publication checks: **101 passed**.
- Before/after negative probes demonstrate the metadata race, inconsistent review-state checks, formula-as-code defect and subject-blind personal-verifier failure; their repaired paths pass.
- Final owner-state verification: UK, Dubai, Japan, Singapore and restored Gmail sidecar hashes all equal their recorded baseline.

Tests use private workbook copies, fake account transports/credentials and isolated metadata. No live recruitment-mail scan, OAuth repair, Calendar write, application submission, employer contact or LinkedIn publication was performed. Current Gmail OAuth/provider health is outside this repair's acceptance claim.

All four canonical workbook hashes and the restored owner sidecar hash compare equal before/after final testing. The UK workbook remains145 rows/six columns with the existing UNCONFIRMED tags. No production workbook data was changed during this repair.

## Files and evidence

Source: career_mail_tracker.py, career_mail_bounded_apply.py, tracker_writer.py, linkedin_publish.py, linkedin_workflow.py, new linkedin_personal_review.py, and company-watch/company_watch.py. Tests cover the affected mail/layout, handoff, publishing, rollover, recovery and shared Company Watch contracts; new test_mail_current_integration.py and test_linkedin_personal_review.py hold the added integration/scope cases.

Private source backups, before/after reproductions, JUnit, owner-state hashes and the synthetic-sidecar recovery receipt are under:

`C:/Users/mukun/Documents/Codex/career-regression-repair-20261023`

Only legitimate source/tests and sanitized documentation/evidence are committed. Runtime logs, private workbooks, OAuth material, sidecar contents, databases, scratch files and unrelated dirty state remain excluded. No reset/clean/stash/rebase/discard operation was used.