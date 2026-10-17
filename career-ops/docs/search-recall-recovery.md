# Direct Career Ops search recall recovery — 2026-10-17

Recorded evidence: an earlier run returned 9+18+14 records, rejected three and added six rows including two Galaxy URL variants. A later run returned 12+15+12 records but added zero. Both repeated the same 14 profile queries three times. Zero additions was not zero discoveries. No claim is made that these historical listings remain open today.

Changes:
- Profile entry-level terms widen the existing vocabulary; they no longer replace it. Senior-title exclusions and eligibility checks remain.
- Every invocation includes an internship batch. Remaining batches rotate distinctly without wrapping/repeating within one invocation. Requests remain bounded by the requested --batches count and the finite pool.
- Queries are unquoted, cover current/next-year and year-free variants, and rotate across disciplines. Varied legacy queries remain available with stale years refreshed. The production prompt no longer fixes intake to 2026.
- Known tracking parameters (gh_src/utm_* etc.) are removed for duplicate identity; job IDs and case-sensitive paths are preserved. No company/title-only merge is added.
- SEARCH_RECONCILIATION reports raw retrieved records, existing URLs, within-run duplicates, invalid records, rejections, new candidates, exact query batches and profile fingerprint. Zero additions is explicitly distinguished from zero retrieval.

Offline acceptance runs the real main() path with mocked Codex/JD responses and a write-forbidden temporary workbook. Tests assert exact accounting, distinct batches, placement acceptance, senior exclusion, tracking URL dedupe, distinct requisitions, and no duplicate JD fetches. No provider calls, live searches, tracker changes or schedule changes were made during this repair.

The existing dirty search source was backed up before edits under Documents/Codex/search-recall-recovery/20261017-222336. Existing owner_search_profile.py and jd_fetcher.py are direct runtime imports previously untracked; they must accompany the committed search source. Unrelated dirty launchers/discovery/digest/runtime files are excluded. The current canonical launcher imports the source on each invocation; gateway restart is unnecessary.

Limits: this improves recall but cannot guarantee exhaustive web indexing or eligibility for all student placements. This work does not loosen clearance or student-enrolment requirements. The existing direct workbook write behavior is unchanged; no workbook was opened for write in acceptance.
