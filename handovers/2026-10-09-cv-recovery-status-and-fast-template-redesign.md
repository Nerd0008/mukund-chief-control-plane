# Handover: CV recovery status and pending fast template redesign

Date: 2026-10-09 (Europe/London)
Repository: C:/Users/mukun/Documents/mukund-chief-control-plane
Branch: fix/e3-whole-repo-architecture
Starting code/evidence HEAD for this handover: 855b9bf7c
Do not merge main. This handover records state; it does not implement the next redesign.

## Most important status

The owner has NOT accepted the generated CVs or the current PDF-span architecture as reliable production tailoring. Previous technical PASS reports and passing regression suites do not establish owner formatting acceptance or varied-JD reliability. Do not tell the owner this is seamless or guaranteed to work.

The current deployed implementation remains the immutable PDF-span pipeline with exact character-count rules. The owner has NOW relaxed identical character counts. That new decision has not yet been implemented. An editable/template document-flow replacement has only been discussed, not built or deployed.

The owner explicitly asked to stop further redesign work and create this handover first. Resume implementation only on the next instruction to continue.

## Latest owner requirements (supersede earlier exact-count instructions)

- Use the supplied master CV as the visual design reference and verified professional-information source.
- Tailor content meaningfully for each JD; identical character counts may change.
- Preserve the master’s clean one-page visual style: fonts, headings, margins, spacing, alignment and sensible skill-label/value relationships.
- Do not spend hours, get stuck, repeatedly patch the renderer or run open-ended visual repair loops.
- Results should normally arrive in a few minutes. Do not promise success every time without evidence.
- Never alter the owner master or implementation during a normal application job.
- Never deliver a failed/broken PDF, or silently substitute the untailored master for a requested tailored CV.
- Keep truthful facts; do not invent qualifications, skills or achievements.

Discussed (NOT implemented): three-minute target / five-minute hard elapsed timeout; one JD-content pass and at most one content-shortening pass; local deterministic formatting/validation; stop with stage/reason and preserve resumable draft on timeout. These are proposed operating limits, not measured achievements or a guaranteed SLA. The owner asked what happens on timeout, then requested this handover. No elapsed deadline/resume system currently exists in the CV implementation.

## Authoritative master

Owner-supplied path: C:/Users/mukun/Downloads/Mukund Didwania CV.pdf
Canonical path: C:/Users/mukun/Documents/mukund-chief-control-plane/career-ops/master/CV_FORMAT_MASTER.pdf
SHA-256 (both): 01643b073e63cce3d8d71b3cd0ebbc2d521bd3b74cb438de2da06e6e8a23039b
One page; page rect 595.5 x 842.25 pt; producer Canva.

The supplied PDF is byte-identical to the canonical file and original owner upload. No master mutation was found. No editable CV DOCX/ODT source was found in career-ops or the top-level Downloads scan; this was not an exhaustive disk search. Do not regenerate or overwrite the PDF. A future editable template would be a separate versioned artifact derived/calibrated against it.

Master manifest: career-ops/master/cv_master_manifest.json
Layout reference: career-ops/master/format_spec.json
The current manifest derives every span’s text, bbox, font, size, baseline/origin, width boundary, native glyph origin, neighbours, section and editability. It includes fixed-count policy and skill-label width constraints; those current production rules are superseded in intent by the owner’s latest relaxation, but remain deployed until replaced deliberately.

## What failed originally

A native Hermes application request ran about 44 minutes, with iteration 5/150 visible. It patched career-ops/cv_tailor.py while generating the CV, admitted manual reinsertion corruption and returned poorly formatted PDFs.

The 150 limit is the general native agent budget from %LOCALAPPDATA%/hermes/config.yaml -> agent.max_turns: 150, consumed by hermes-agent/gateway/run.py::_current_max_iterations and gateway/run_turn.py when creating the AIAgent. It was not a CV-specific retry budget.

The prior application skill explicitly instructed Hermes to extend cv_tailor.py if an edit could not be expressed. Redaction/reinsertion damaged neighbouring text; manual font/CMap/x-position/blank fixes and --force continued afterward. No enforced verification-to-attachment boundary prevented failed output delivery.

Read-only SQLite evidence: %LOCALAPPDATA%/hermes/state.db, session 20261003_010551_5b27acbc. Renderer patches include messages 24803/24805/24807/24809/24811/24813; manual corruption admission 24877 at 2026-10-08T23:52:09Z; further x-offset patches 24883/24885. Do not dump full sessions or credentials into evidence.

## What was built and deployed

- career-ops/cv_golden.py: original PDF glyph-stream edits, original embedded fonts, bounded output workspace, per-span fit, one render, structural/ATS/native-stream/pixel checks, Windows read-only handles plus before/after dependency hashes.
- career-ops/cv_tailor.py: canonical CLI wrapper; no --force, geometry exemptions or parallel builder.
- career-ops/audit_cv_format.py: strict independent audit.
- career-ops/hermes_cv_guard.py: CV-only eight-turn cap, restricted writes/commands, direct tools, independent Discord attachment gate.
- career-ops/hermes-plugins/career-cv-golden-guard/: native plugin loader/manifest.
- career-ops/hermes-skills/job-application-intake/SKILL.md: revised production instructions, copied to Hermes runtime.
- career-ops/tests/test_cv_golden.py: offline safety/renderer/tool regressions.
- career-ops/CV_GOLDEN_MASTER.md and audits/evidence/2026-10-09-cv-golden-master-recovery/: implementation/audit records.

Direct native tools: career_cv_master and career_cv_build, registered in career_cv toolset. Discord toolsets now include hermes-discord and career_cv. Tool-search/describe/call bridge is allowed while underlying calls remain guarded. Native offline initialization and actual Discord tool selection verified both tools without model calls.

Current limits: eight native CV turns (NOT an elapsed timeout), up to three content-fit attempts per span persisted across command re-entry, one render per job. Exact count and label-width rules still active. The manifest/master/renderer/verifier/guard/layout are protected. Non-CV agent budget remains 150.

Output root: %LOCALAPPDATA%/hermes/runtime/career-ops/cv-output/<job>/
Files: cv_edits.json, PDF on PASS only, adjacent .verification.json, content_fit_verification.json ledger and optional previews.

Delivery guard checks sidecar PASS, output/dependency/master/manifest hashes and independently reruns structural/visual checks. Renamed CV PDFs are also detected. It binds through a native platform connect/reload callback to the REAL lazy-loaded Discord adapter (hermes_plugins.platforms__discord.adapter), not just a duplicate static import.

Last observed gateway PID at handover inspection: 29900. PID can change; recheck gateway.pid/logs. Plugin enabled; Discord connected after restart. No provider calls or Discord test messages were initiated by these recovery checks. Hermes did make owner-triggered live calls independently; do not report the entire gateway had zero calls.

## Follow-up failures and corrections

1. The initial guard blocked diagnostic shell commands mentioning the protected renderer, returning a misleading unlock message. It was corrected to allow a narrow read-only Git diagnostic form and expose direct native CV tools, so application generation does not require shell/code access.
2. Real build attempts (messages 24989/24991; results 24990/24992) failed on content fit, then whitespace extraction. Master spaces are stored in separate PDF objects; after edits extraction can regroup them. Verification now handles grouping while checking non-edited native streams byte-for-byte, rather than blindly accepting arbitrary whitespace changes. Native glyph origin fixes the corresponding six falsely reported outside-mask pixels.
3. Skill labels were initially immutable; they became bounded editable labels. A sample technically passed but shorter labels left LARGE GAPS before unchanged value anchors. The owner rejected its formatting. Outside-region pixel matching did not catch this because the labels were authorised edit regions.
4. Exact original character count and label advance-width within 0.5 pt were added to prevent those gaps. The owner later rejected the underlying brittle fixed-span approach and agreed to relax counts for a replacement architecture.

These corrections did not prove the PDF-span design handles varied JDs reliably. Do not reuse the old exact-count constraint in the redesign simply to satisfy old tests; preserve equivalent safety/layout checks under the newly approved requirement.

## Test evidence and its limits

Last full Career Ops regression: 808 passed, zero failed (91.76 seconds).
Focused golden-master regressions: 29 passed, including native whitespace, same-count label changes, exact-count failures, shortened-label rejection, font/baseline/neighbour corruption, unexpected pixels, protected files, fit budgets, reproducibility and delivery blocking.
Pillow getdata deprecation warnings remain; not failures.

These prove the implemented contracts, not broad content quality, latency or owner visual acceptance. No varied-JD template prototype or live acceptance exists for the NEW proposed architecture.

## Generated artifacts — NOT owner-accepted

Various PDFs exist under the CV output root, including allstate-golden-release-2026-10-09 and allstate-jd-final-2026-10-09. The later Allstate sample showed the skill-label gaps and was rejected. Do not claim a new accepted CV is ready. Historical technical PASS reports are not owner acceptance; protected-source/manifest changes also invalidate prior delivery reports. Preserve evidence rather than reusing or silently delivering an older PDF/master.

Private pre-repair dirty renderer/auditor copies:
%LOCALAPPDATA%/hermes/runtime/career-ops/cv-recovery-backups/2026-10-09/
Original captured copies also exist in the Codex workspace cv-recovery/ directory. Runtime config/skill backups are private; do not commit their credential-related content.

## Independent checkout interference

HermesRemoteQueuePoller runs every two minutes from remote_queue/run_poller_hidden.vbs. remote_queue/poller.py::git_pull_safely does stash push -> pull --rebase -> stash pop in the same checkout. Stash temporarily restores tracked files to HEAD, disrupting concurrent uncommitted repair. Reflog and queue.log show this at 01:08/01:10/01:12 BST. Recovery did not run reset, clean or checkout.

Owner said the poller problem would be fixed later. Its schedule/code was NOT changed. Avoid concurrent active-checkout edits; checkpoint promptly or isolate engineering work safely. Do not reset/clean/stash away owner changes or rewrite queue history. Existing unrelated runtime/queue dirty files are not this handover’s changes.

## Implementation checkpoints

- d7d1084cb: immutable glyph pipeline and manifest.
- 31f36ac7b: original font default glyph-width handling.
- b9ca01880 / f99ac013f: CV budget/delivery guard and persisted budgets.
- ee5a8a4ab / 42ed6a19a / 5369c5f: deployable guard/skill, unknown-tool/renamed-CV protection, actual lazy Discord binding.
- 00d246e7b: initial recovery audit, 801 passing regressions (not owner acceptance).
- e6c922f5f / 528e5c65c: direct native CV tools and native tool-discovery bridge.
- 040108539 / c964b0686: native whitespace and bounded skill-label support, real-case regressions and compact tool response.
- 9a601a167: temporary relaxed count policy; subsequently superseded.
- 9e795b55b / b33db4830: exact-count/label-spacing guard and explicit targets.
- 855b9bf7c: owner-supplied master confirmation and 808-test audit.
All pushed to fix/e3-whole-repo-architecture. No main merge.

## Next work — not yet implemented

1. Prototype a separate editable/layout template reproducing the master’s design using its ORIGINAL content first. Do not overwrite the master.
2. Prefer logical paragraphs/bullets/inline bold skill labels with real text flow, not absolute PDF glyph surgery or permanently fixed label-to-value anchors. Content counts may vary under the latest owner decision.
3. Preserve fonts/margins/heading hierarchy/rules/spacing/one-page style. Document which content-dependent line endings can legitimately change; do not promise pixel identity for different text.
4. Use truthful JD-focused content from the master/facts. Keep generation and rendering separate; never let application jobs patch code.
5. Validate varied short/long JDs and skill labels offline. Check geometry, font sizes/families, line spacing, collisions/overflow, one-page output, ATS extraction, fact provenance and reproducibility. Show the prototype before calling it ready or replacing the live path.
6. Implement a real wall-clock deadline/cancellation budget across content generation, renderer and verification. Do not confuse max agent turns with elapsed time. Proposed target three minutes/hard stop five minutes still needs implementation/testing and provider-latency measurements.
7. One content-generation pass plus at most one bounded shortening pass was proposed. Preserve a usable content draft on timeout; a local formatter can finish only if it has enough valid content. If the provider never returns usable content, report that honestly. No blind automatic retry, master substitution or unsafe attachment.
8. Preserve native Hermes tools/session/skill integration, provider binding and unrelated Career Ops/Gmail/Calendar/LinkedIn/schedules/E3 configuration. Do not change providers/billing/secrets or initiate unrelated live actions.
9. Commit and push prototype/fixes/evidence to the repair branch, no main merge. Deploy the replacement only after offline prototype evidence and owner-facing visual comparison establish it is acceptable.

The actual latest user request is this handover. No further architecture or runtime changes were made for it.
