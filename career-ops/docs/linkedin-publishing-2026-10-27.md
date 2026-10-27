# LinkedIn workflow and publishing acceptance, 27 October 2026

Publishing is enabled by owner instruction. Capability permission is separate from
authenticated approval of an exact post body. No new approval system was introduced.

The already-approved Tuesday post was published once using the existing publisher,
image upload and append-only ledger. Returned identity:
`urn:li:share:7520854748456075266`.

## Production path

Sunday `linkedin_weekly.py` runs with Hermes Python through the existing cron script
runner. It retrieves complete authoritative professional references, researches an
AI/cyber and an AI/noncyber event, drafts those plus one personal reflection, checks
topic reuse and length, and runs the actual news and personal-fact gates. Research
uses observed browser-search evidence and actual readable article text. No private
profile facts enter web queries. A live LinkedIn full-profile read is unavailable;
the report explicitly identifies the local verified professional-reference fallback.

Preparation checkpoints into the existing private LinkedIn runtime. Completed
verified slots resume without rerunning workers. Existing exact approvals remain
approved even when review is blocked. New bodies remain unapproved. Images are
deferred until text approval. The weekly script cannot approve, schedule or publish.

All worker stages consult the existing router with their actual task family. Writing
receives the real cached source, rather than only a research summary. A complete
factual rejection permits one content correction; transport/source failures do not
trigger content loops. Any changed body gets both independent reviews again.

`linkedin_state.py publishing enable|disable|status` manages capability permission.
With permission enabled, the existing exact-body `plan` operation arms only the
earliest approved, verified future dated slot per weekday through `cron.jobs.update_job`.
Stale, missing, tampered, already-published and blocked slots cannot arm. Dry-runs do
not alter scheduling. After successful scheduled publication, empty weekdays pause;
later valid approved slots can arm automatically. Publisher approval/hash/duplicate
guards remain mandatory at dispatch and in the publisher itself.

## Live findings

- Research returned three sourced events with real search receipts.
- An inaccessible source returned HTTP 403. It is blocked before drafting rather
  than converted into invented evidence.
- A readable primary-source draft passed the news gate with all 6,418 source
  characters supplied. The conservative personal verifier rejected ambiguous
  wording as unsupported tool claims. One wording correction passed both real
  gates on its new exact body. The candidate verifier was not changed.
- The image helper previously called a stale Lite model and swallowed errors.
  It now reuses the existing routed Nano Banana 2 backend, model
  `gemini-3.1-flash-image`, at 4:5. HTTP 402 is exposed as
  `media_provider_billing`, without retries or provider substitution.
- Live Google image generation is blocked: the existing project reports depleted
  prepayment credits. Listing models/authentication health alone does not prove
  image-generation readiness. No purchase or billing change was made.

## Verification

259 relevant LinkedIn, publication, source coverage, stage handoff, routing and media
regressions passed. Coverage includes unapproved/changed bodies, missing/stale slots,
private scheduler isolation, weekly resumption, complete profile requirements,
quota stops, preserved blocked approvals and both gates on corrected wording.

The existing tracked topic registry now also enforces the already-retired SafePaste
narrative; no publication date was invented. The full current-week live preparation
completed with the published Tuesday preserved and two newly verified unapproved drafts.
Canonical `week` status exposes these prepared drafts as awaiting owner approval,
so it cannot contradict preparation by reporting that no draft exists.

Private runtime artifacts, profile evidence, generated drafts, credential material and the
publication ledger are deliberately excluded from this source commit. Unrelated
dirty Career Ops search files are preserved. No merge of main, tracker change,
application submission, Gmail mutation or job-search resumption is part of this work.
