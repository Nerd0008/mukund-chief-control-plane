# Search availability gate recovery — 22 October 2026

## Owner policy

The owner explicitly approved flagged unverified tracker rows. Preserve Hermes' concurrent policy changes; its original handoff is HANDOFF-codex-unverified-leads.md. Confirmed closed vacancies, unusable destinations, listing pages, clearance/experience restrictions and unsuitable regions remain blocked. UNKNOWN availability is never labelled verified OPEN.

## Reproduced defects

The saved UK run unified-uk-20261021T224502Z semantically reviewed 219 candidates using Codex, accepted 72, and rejected 71 on availability. Its discovery-input JD coverage (33/1,587) was measured before post-semantic fetch, and was not a count of all later fetch attempts. Another aggregate run used DeepSeek, exhausted balance and wasted 68 requests; a healthy probe followed by zero classifications bypassed the normal Codex auto fallback. These are separate runs, not evidence that the UK run used DeepSeek.

PA Consulting's official advert returned HTTP 200, linked through an “I'm interested” control to a specific SmartRecruiters requisition, then redirected into its form. The resolver missed that label and lacked SmartRecruiters public posting support. Exact company/requisition-matched public API content now supplies full JD/qualifications and employer/title/location, without logging in or bypassing bot controls. Tracking-only oga/trid variants deduplicate on that ATS; requisition parameters elsewhere remain meaningful.

## Production path

run_scheduled_scan.cmd -> discovery/scheduled_orchestrator.py -> discovery/pipeline.py -> regional_job_search.build_record -> candidate manifest -> promote_manifest.py -> career_ops_cli.py write --apply -> tracker_writer.write_records.

Availability evidence now survives that entire manifest path. New unverified rows display UNVERIFIED on the Apply Link cell and store the reason as a cell note. Raw URL/hyperlink, application status and the six-column UK schema stay intact. Digests distinguish verified OPEN from flagged UNKNOWN and withhold known closure/past deadlines. The direct codex_entry_level_search path uses the same flag and writer.

Terminal balance/auth errors stop further DeepSeek requests; auto mode attempts the existing Codex classifier when a healthy probe yields zero usable classifications. Explicitly selected DeepSeek remains explicit. Scheduled bounded escalation defaults on (budget eight). No provider credentials/configuration changed. --no-live now also suppresses post-semantic network fetches; test newsletter/liveness caches are private, and the discovery import path is available to independently run test files.

## Acceptance

- Focused search/resolver/availability/digest/writer/orchestrator suites: 320 passed, zero failed.
- New writer test saves/reopens only a workbook copy: visible flag/note, intact URL/hyperlink/status, six columns, following verified row does not inherit marker, repeat input produces zero appends and identical file hash.
- Fresh public GET replay of the same saved 72 acceptances: 5 OPEN, 65 UNKNOWN, 2 CLOSED. After all eligibility gates: 65 accepted, including 60 flagged UNKNOWN. Canonical dedupe proposes 49 distinct rows (3 OPEN, 46 flagged UNKNOWN); 16 duplicates avoided; zero rejected by writer.
- This is a replay with fresh verification, not a new discovery/model run. Zero provider calls; zero canonical tracker writes. Before/after workbook SHA-256: 9340232290bc43b03cadfc0f2169fd33959d44bcc85dcdbb76bc0ee698ec4f36.
- Application deadline/Gmail discovery/liveness/regional/rollover/recovery extended run: 136 passed, 11 failed. All 11 also fail using committed HEAD writer. Full rollover/recovery/LinkedIn comparison: 58 passed, 20 failed both before and after, identical failure IDs, zero new failures. UK rollover fixtures assume no pre-existing August owner rows; Singapore fixture assumes fixed duplicate row 33; LinkedIn handoff assumes a provenance column absent from the current UK six-column layout. These unrelated paths were not redesigned or weakened.

## Preservation and boundaries

Private recovery/evidence: C:/Users/mukun/Documents/Codex/career-search-gates-20261022-180820, including before copies, final-source-snapshot with hashes/mtimes, test XML and public-fetch replay details. Only sanitized aggregate evidence is committed. No reset, clean, stash, restore, rebase or bulk staging. No application submission, outreach, Gmail/Calendar mutation, LinkedIn action, CV or E3 redesign. No main merge. Canonical workbook was not bulk repaired or retroactively relabelled.
