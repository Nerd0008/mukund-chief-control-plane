# Router workflow hardening — 26 October 2026

Branch: `fix/e3-whole-repo-architecture`. No main merge.

## Owner policy

Codex is the default worker for job search only (scheduled launcher and discovery defaults). All other compatible workflows offer their existing authorized transports to the router brain. The reasoner remains Codex CLI `gpt-6.1-sol`, high reasoning, with provider-blind evidence selection. Using Codex to reason about worker selection does not make Codex the universal worker.

The native Hermes controller retains Nous/LongCat and its tool protocol. A plain-text CLI is not substituted into tool, grounded-search or image protocols. Explicit current-request worker preferences constrain eligible offers, still requiring router authorization. Nested turns inherit that preference; it resets afterward. Model-generated tool arguments cannot establish owner preferences.

## Repairs

- Gate physical auxiliary relay dispatch, including primary, fallback, rebuilt clients, sync, async and streams. Require `physical-relay-v1` at startup; a stale loaded adapter needs restart.
- Share a monotonic operation deadline across selection and execution. Subtract selection time, bound stream lifetime and async cancellation, and terminate only owned CLI child processes. Disable hidden Google SDK retry multiplication.
- Coalesce identical concurrent selections while keeping per-caller deadlines. Record allowlisted workflow/operation/stage/provider/model/timing/error receipts without prompts, private facts, tokens or raw provider bodies.
- Treat typed router denial as terminal, not as a reason to rotate credentials or enter the native recovery ladder. Preserve actionable auth/usage/configuration/timeout categories.
- Stop discovery research/classification on routing failure and mark production health accordingly; do not report a healthy empty result. Remove conflicting local 30-second research ceilings.
- Route compatible LinkedIn text and explicit CV/cover worker requests through the same authorization seam. Preserve existing CV facts, template, layout, master hashes and delivery verification.
- Register the existing Gemini Nano Banana image provider through the configured `e3` interface. Audio integration explicitly excluded by owner; no transcription backend or STT configuration was added.

## Cover fact-gate correction

Live testing found a false positive: an explicit first-person statement that the candidate lacks experience with a tool list was treated as a positive experience claim. The correction only removes tool flags when every mention is inside an explicit negative-experience clause. Positive/ambiguous uses, contrasting positive clauses, invented facts, forbidden phrases and unavailable gates remain blocked. Thirteen regression cases cover these boundaries. The original gate result is preserved.

## Acceptance evidence

Offline full-suite results and runtime deployment are recorded in the completion section after final verification. Private recovery, patches, full test XML and QA artifacts are outside Git under `Documents/Codex/router-hardening-2026-10-25`.

Bounded live tests before activation:

| Path | Result | Elapsed |
| --- | --- | --- |
| Native controller | ROUTED/PASS | 14.844 seconds |
| LinkedIn explicit Codex text | PASS, no publishing | 9.484 seconds |
| Existing image provider | PASS | 13.938 seconds |
| CV explicit Codex | PASS, one content call, one render | 22.297 seconds |
| Cover content generation | Successful Codex content call | 22.828 seconds |
| Same cover content after scoped fact-gate fix | PASS, no additional model call | 2.594 seconds |

CV protected dependency hashes were identical before/after. Both QA PDFs were rendered and visually checked: one page, no clipping/overlap, existing typography/sections intact and cover closing follows its text. No Gmail mutations, tracker/Calendar writes, messages, applications or LinkedIn publishing were performed. Private PDF content, profile facts and credentials are not included in this evidence.
