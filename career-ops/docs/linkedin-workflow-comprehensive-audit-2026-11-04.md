# LinkedIn workflow audit and repair — 4 November 2026

## Conclusion

The repeated failures were a chain of consent parsing, post-versus-image presentation detection, lost publication preferences, uncontrolled repair scripts, incomplete status evidence and provider failures. They were not a single fact-check problem. The claimed content_ready/slot_matches circular dependency does not exist. The original 845-character post had valid owner approval, personal review and factual override, but image_required was true and no image existed.

This audit covers the native conversation tool, prepared and dated artifacts, authenticated history, post edits, review generation and caching, image generation, immediate publishing, exact-date scheduling, weekly planning, scheduler control, ledger verification, provider cooldown behavior, operational status and deployed instructions. It does not prove unlimited future provider availability.

## Recorded incident evidence

The current post is the 845-character fridge post, body 4de5d8317eafef817cc7aeacd62c24e479fe72d6a5b3d69381a9f8bea3754c6c. Owner message 42884 requested removal of a line. Assistant 42887 presented the resulting body; owner 42888 approved publication and requested the image. Assistant 42907 then displayed an image-generation prompt and billing warning. Owner 42912 said “wtf publish man skip the image”. The old presentation heuristic treated that quoted image prompt as a different LinkedIn draft and refused the owner's message. Later exact-hash override message 42972 verified the text/override but did not carry an image preference; image_required remained true.

At investigation start canonical state was owner_approved=true, personal_review_passed=true, explicit_owner_override=true, reviews_ready=true, text_integrity_passed=true, image_available=false, content_ready=false. The missing schedule was a separate observation. The session then repeatedly attempted shell/writer workarounds and described a nonexistent planning circularity. Tool record 43065 preserved approval but omitted the missing-image condition from its reduced current_state, contributing to the false diagnosis.

## Findings and implemented corrections

| Area | Verified failure | Correction |
| --- | --- | --- |
| Ordinary publication | Bare publish was not consistently parsed as consent or routed through capture | Bare publish/post and supported conversational requests bind to the exact presented post; publish mode now captures authenticated approval/preferences before invoking the existing publisher |
| Informed overrides | Natural “Override fact check” was not accepted; some code treated publish-now itself as an override | Accept explicit natural override/skip-fact-check only with the exact post and warning context; plain publication does not waive factual review |
| Changed versions | The removed line changed the body, so old approval could not cover it | Retain exact-body checks; owner 42888 did approve the edited body. Never hand-rebind a receipt or carry consent onto arbitrary revised text |
| Presentation classification | Quoted image-generation instructions looked like a new public post | Recognise explicit image/billing/prompt framing separately; regression uses the actual incident shape |
| Image preference | Real skip-image instruction was lost | Preserve text-only choice through later approvals. Recover actual owner message 42912 against the unchanged body and save its receipt separately |
| Readiness diagnostics | Coarse “only verified content can be planned” hid the actual condition | Emit content_blockers, including required_image_unavailable, approval, factual/personal review, frozen-text and date failures. Expose them through tools and canonical responses |
| Misdiagnosis | Agent asserted content_ready depends on slot_matches | Test the independence explicitly. Immediate publication needs no schedule manifest; planning checks content readiness before creating its slot |
| Duplicate approval/scheduling paths | Publish mode assumed an already captured and fully ready artifact | Publish mode uses the same authenticated capture and preference path as approval, then invokes the guarded publisher. Its success still requires URN plus ledger |
| Fact-check reruns | Same text/evidence repeatedly sampled, including manual scripts | Reuse complete pass AND block decisions keyed by post prose, full source text, gate version, model, judge count, UTC date and forbidden phrases. Changed text/evidence/policy invalidates reuse |
| Draft factual additions | Historical and universal assertions exceeded supplied sources | Strengthen initial source-grounding instruction before review. Retain the existing bounded correction path and all claim evidence checks |
| Scratch-loop escape | Guard used filenames/keywords; generic temporary script names bypassed it | During bounded LinkedIn actions block interpreter/write-script workarounds regardless of helper filename. Read-only file tools remain available |
| Runaway turn length | Gateway configured 150 iterations; repeated failures filled context | Approval/publication turns receive at most eight model iterations, restored afterward even on failure. This does not impose a global limit on other work |
| Custom slot tool exposure | Python backend supported all weekdays, but native tool schema and generic-cron protection still assumed three | Expose all weekdays; use registry-backed protected scheduler identities and include custom slots in operational evidence |
| Conflicting skill copies | Old override-construction examples encouraged artifact patching | Remove raw override-writing examples; update active skill and both maintained source copies with one recovery contract |
| Provider failure | LongCat disconnected and cooldown retry handling previously failed quickly | Prior deployed repair waits once through a short cooldown within the original deadline, without replaying tools. Provider billing, network and rate limits remain distinct operational failures |

## Why the fact checker blocked the post

The stored review object reports two issues: the sentence about OWASP inclusion since 2004, and the universal “None of these require a novel exploit” assertion. Its supplied 2025 OWASP passage does not establish the historical continuity claim. The screenshot described only one issue, but the saved state had two. Repeated attempts did not add the missing historical evidence.

Independent inspection of OWASP's own archived 2004 update confirms A10 Insecure Configuration Management: https://github.com/OWASP-Foundation/OWASP-wiki-md/blob/master/2004_Updates_OWASP_Top_Ten_Project.md . That establishes the 2004 entry; it does not by itself establish every intervening edition or every generalisation in the post. This is an evidence-selection problem, not proof that every refusal is a false positive. The repair does not silently downgrade factual or personal checks. The owner may resolve a warning with new evidence/wording or explicitly override the factual warning conversationally.

The live gate record also contains noncanonical judge-count metadata (requested 1, used 2) following scratch-script edits. It has been preserved as incident evidence rather than relabelled as a clean pass. The existing independently verified owner override remains explicit. The repaired path does not handwrite verdicts, receipt IDs or evidence.

## Recovery of the current post

Re-verification of owner message 42912 now succeeds for the same 845-character body and establishes skip_image=true. Saved that real preference receipt with image_required=false and null image fields through the audited state writer. No text, approval, factual review, override or published ledger entry was fabricated. The result has content_blockers=[], content_ready=true and image_available=true. It is unscheduled and unpublished; automatic jobs remain paused.

The real publisher's dry-run completed with exit 0, ok=true, performed=false, dry_run=true and no blockers. This validated the current artifact through the actual publisher without sending it to LinkedIn. No public test posts were made. A live HTTP publication and actual paid image generation are distinct from these checks and were not performed in this repair.

## Validation matrix

The targeted regression suite covers natural publish without hash, negative/conditional/multiple-post refusal, exact changed text, quoted image prompts, informed natural overrides, text-only publication to a simulated endpoint, URN/ledger success, duplicate refusal, missing-image diagnosis, lack of scheduling circularity, guard bypass attempts, completed fact-review cache reuse and invalidation on new evidence, model-iteration limits and restoration, and truthful canonical status. Broader suites cover all weekdays, custom times, earliest-slot arming, Sunday preparation/checkpoint/resume, source coverage and real quotation validation, quota stops, publisher checks and cron guards.

Actual network limitations: source sites can block retrieval, model services can disconnect, usage limits can stop review, image account billing can prevent generation, and LinkedIn OAuth can expire. Those must produce specific operational states, not approval loops or fabricated success. Automated tests cannot guarantee future service availability. The repair preserves approval and partial state across those failures.

## Expected owner experience

Show final text. Owner says publish. Resolve the exact post and authenticated message internally, preserve any text-only preference, reuse the existing exact-evidence reviews, then call the guarded publisher once. Return the LinkedIn result only after URN and ledger verification. If there is a genuine factual warning, explain the exact claim once; normal “override fact check” or “publish it anyway” works in that context. If the owner edits the post, show the new final version and accept ordinary conversational approval. No hash command, repeated unchanged approval, silent rewrite, shell patch or automatic uncertain publication replay.

Additional guard correction: status/why previously changed the action to STATUS and reopened generic interpreter execution, allowing pending repair scripts to resume. Mutation guards now remain active on LinkedIn status and investigation turns too. Canonical workflow/status tools and read-only file inspection remain available.

Final verification: 295 tests passed in 100.77 seconds across the workflow, scheduling, publication, source-evidence and resource-stop suites. After the final cross-stage guard change, 58 focused workflow/seamless tests passed in 14.94 seconds. The live 845-character artifact passed the real publisher dry-run with exit 0, no blockers and performed=false. External LinkedIn publication and paid image generation were not exercised.

Deployment: repair pushed through commit 271e6089d and gateway gracefully reloaded to PID 39800, running with Discord connected. A subsequent real-publication command was rejected before execution by automatic approval review because historical database records were not accepted as a trusted current exact-post authorisation in this chat. No workaround or retry was attempted. A direct owner instruction in this chat is required before this agent can perform that live publication. This external approval-review block is separate from the repaired Hermes factual/image/approval workflow.
