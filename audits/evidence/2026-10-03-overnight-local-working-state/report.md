# Overnight working state investigation — 2026-10-03

No repair, checkout, reset, restore, merge, deletion, credential change, scheduler change, service restart, or provider call was performed for this investigation. HEAD remains 9101d2af5e1f64aee78b9719b6b0937895d3ba5b. Git fsck --lost-found added recovery files under .git/lost-found as requested; it did not restore the working tree. Evidence is uncommitted.

## Findings / six answers

1. YES: Hermes built and used local working implementations overnight. Most were committed locally on main, rather than remaining wholly uncommitted. They were absent from the remote main state recorded at 01:06 BST and from the separate repair branch. By 10:06 BST, the main push contained the overnight commits. The proposition that the work never reached GitHub is therefore false for these source changes today.
2. Changes included explicit Codex CLI model gpt-6-sol, stdin prompt delivery through the Windows shim, live web-search event validation/error reporting, a Codex bulk semantic classifier and automatic fallback after unfunded DeepSeek, handling zero classifications as failure, LinkedIn access-token readiness/API version/image byte upload/workflow argument forwarding, new content generation/news fact-checking, and daily job-link delivery code. An outside-repo runtime codex_adapter.py also gained native-executable preference and stdin handling. Local LinkedIn edits were captured by the 02:44 poller stash.
3. YES: the main working tree was replaced by the separate fix/e3-whole-repo-architecture branch. Current HEAD is not a descendant containing these overnight main commits. Current Career Ops classifier/web-search/adapter files lack the overnight functionality, and several launchers/generation scripts are absent. The morning targeted repair independently reinstated LinkedIn readiness/image support and replaced incident flushing with ACK-safe code; those fixes should be preserved.
4. The definitive later replacement was git checkout fix/e3-whole-repo-architecture at 11:24:05 BST, from main 860cb105 to repair branch 7d5bf62c. This was the checkout executed in this Codex conversation for the preceding requested acceptance. No hard reset was used by that command. An earlier automatic poller stash at 02:44:02 BST preserved uncommitted LinkedIn changes; image argparse failed again at 02:56:52 before Hermes reapplied and committed them at 02:59:19. This supports a separate overnight auto-stash interference episode, but does not prove every stash caused permanent loss. Repeated reflog 'reset: moving to HEAD' entries align with automated stash/pull activity; reflog alone does not identify reset flags or prove a hard reset.
5. YES: the last proven working image publisher is e8e33659 (03:00:22 BST), immediately followed by a successful image post at 03:00:29. The proven successful UK discovery/classification configuration uses main through 4edcf322, observed completed at 02:16:12. The later complete overnight source snapshot af28d6db (03:26:06) is recoverable, but its additional news gates/content features were not all proven end-to-end. Copies of those versions, earlier GitHub-observed state 795968d3, current HEAD, stashed LinkedIn code, runtime adapter and wrappers are preserved here, with SHA-256 manifests and diffs.
6. For a subsequent repair: selectively integrate the confirmed Codex transport/model fixes through the approved E3 seam; restore the absent launchers/digest and LinkedIn generation/factcheck modules with tests; reconcile the outside-runtime adapter and wrappers into versioned deployment artifacts; verify scheduled command targets exist; preserve current LinkedIn readiness/image fixes and incident ACK reconciliation. Prevent deployment/checkouts and the poller's automatic stash/pull from racing active edits. Do not blindly restore an entire main snapshot or bypass the branch's approved architecture.

## Timeline (Europe/London, BST)

- 00:49:29–00:49:32: Hermes config backup/current config modified. Both have provider=nous, model=meituan/longcat-2.5-preview:free, same Nous base URL. No provider switch established.
- 01:01:54: Hermes .env mtime. Variable names and hash recorded only; historical values cannot be reconstructed from mtime.
- 01:05:28: gateway launched under MISTY\mukun; same Python processes still observed during audit.
- 01:06:05: last remote main push recorded before overnight implementation work, commit 795968d3.
- 01:27:13: Hermes message 18584 reports Codex live web_search_observed=true.
- 01:31:59: 0fe5db68, fix live Codex web-search provider.
- 01:46:09: outside-repository Hermes exec-brain/codex_adapter.py mtime (UTC 00:46:09).
- 01:47:13: f4863fd9, Codex semantic fallback/model default.
- 01:49:00: 97491915, repository Codex adapter stdin fix.
- 02:09:26 and 02:27:23: LinkedIn text posts HTTP 201.
- 02:11:14: 4edcf322, zero-classification failure handling.
- 02:16:12: unified-uk-20261003T011120Z completed successfully using codex / gpt-6-sol. 523 raw, 18 open-web findings, 30 classified, 10 semantically accepted, 1 deterministic eligible/tracker candidate. Historical counter name deepseek_accept holds semantic accepts even though provider=codex. This proves UK discovery/classification, not all-region operation or application submission.
- 02:44:02: poller-autostash captures tracked LinkedIn auth/publisher edits, stash 7a537b040f8907572756939dccbed43533c45cc1.
- 02:56:52: publisher argparse refuses --image.
- 02:58–02:59: Hermes reapplies _apply_linkedin_patches.py; message 19272 says commit immediately to protect against auto-stash. The temporary patch/generator scripts were deliberately removed by Hermes before committing (historical command in session evidence).
- 02:59:19: 7eaebfe4, image publishing/API version/OAuth readiness.
- 03:00:22: e8e33659, image upload Content-Type fix.
- 03:00:29: image post HTTP 201, image URN present, share 7511968380464181248.
- 03:03–03:07: daily_jobs_links implementation and Hermes wrapper created.
- 03:11–03:26: news fact-check gates, content generation, incident scripts committed.
- 10:06:05: main pushed as 860cb105, containing the overnight commits.
- 11:24:05: checkout switches live source from main to the divergent repair branch.
- 11:29:41: targeted readiness/ACK acceptance evidence committed as 9101d2af.

## Current drift confirmed

- discovery/web_research.py: overnight direct validated CLI path used explicit gpt-6-sol and stdin; current branch uses E3 service execution instead. Transport/model fixes must be reconciled at that seam, not restored as an architecture bypass without review.
- discovery/classifiers.py / pipeline.py: overnight Codex semantic fallback is missing from current branch.
- exec-brain/codex_adapter.py: current source again puts objective in argv and omits the overnight explicit default model. Outside Hermes runtime has a different implementation, including native-executable preference.
- Missing current files recovered from af28d6db: career_catchup.py, nightly_career_run.py, run_nightly_career.cmd, daily_jobs_links.py, linkedin_content_gen.py, linkedin_factcheck.py.
- ChiefCareerNightly still points at missing run_nightly_career.cmd. Hermes career_daily_jobs_links.py still points at missing daily_jobs_links.py. These are structural runtime failures independent of provider billing.
- Current LinkedIn auth/publisher/workflow have morning repair changes; compare diffs rather than replacing them wholesale.

## Evidence coverage / limitations

- reflog --all, local branches, stashes, branch-only commits, untracked/ignored inventory, and Git object recovery inspected.
- fsck returned 12,935 dangling commits and 39 blobs in the parsed commit/blob inventory. 240 dangling commits dated in the overnight window were all poller stash/index/untracked snapshots; no separate named overnight development commit was found among them. No relevant standalone dangling script blob matched the targeted signatures. Reachable main commits and stashes already recover the important code.
- Source manifest: exact Git snapshot/file path, commit or filesystem timestamp, classification and SHA-256. additional-manifest.json covers the key 02:44 stash and outside-runtime adapter. file-comparison.json compares overnight/current/9101d2af hashes.
- Hermes state.db read-only selected tool/session evidence; Codex session event extracts; runtime reports and LinkedIn publication receipts; 636 relevant Task Scheduler events inspected. No relevant task registration/update events recorded in that window; actions/targets are recorded separately. This does not establish that cron jobs or all external launchers were unchanged.
- PowerShell history last modified before the overnight window and has no per-command timestamps. Hermes noninteractive commands provide stronger evidence.
- Config/auth/.env hashes and safe projections only. No tokens, credential blobs, auth.json values or .env values copied. Credential acquisition/usage occurred overnight; available evidence shows the same MISTY\mukun context, not an account-context loss. Historical secret/env values are intentionally not recoverable from these evidence copies.
- The active poller continued independently during this audit (including an 11:40 auto-stash). No poller/scheduler was stopped or modified. Evidence is additionally mirrored outside its checkout to protect the recovery copies.

## Next action

Review these recovered snapshots and diffs, then authorize a scoped integration of the missing main changes with current branch repairs. No repair was implemented by this investigation.
