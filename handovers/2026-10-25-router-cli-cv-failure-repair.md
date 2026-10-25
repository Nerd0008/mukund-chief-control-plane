# Codex router failure during CV / cover requests — 25 October 2026

## Verified cause

`router_cli_failed` originated in RouterBrain before the downstream native model call. It was not evidence of a Nous outage. Router execution failures were collapsed to one category; Hermes treated the resulting exception as retryable and produced the global provider's generic three-attempt failure copy.

Of the most recent 45 receipts inspected, 21 were blocked. Several calls ended at 30.08–30.11 seconds, matching the workflow's imposed 30-second timeout. Other failures ended in 2–4 seconds; their historical underlying cause cannot be recovered from the old receipts. Do not label those failures quota or authentication errors without evidence.

The CLI was available during this investigation: a synthetic no-tools check passed in 4.48 seconds. No authentication reset or fallback-provider change was needed.

## Bounded repair

- Use RouterBrain's existing maximum 45-second allowance instead of imposing 30 seconds in the workflow wrapper. A caller's shorter deadline still wins. Text routing and execution share the original elapsed-time budget; CV hard stop remains 180 seconds.
- Retain only allowlisted failure categories and executable/version/exit/timeout metadata. Never persist raw stderr, provider bodies, prompts, tokens or reasoning in failure receipts.
- Classify typed routing denials through the host's supported error-classification hook as nonretryable, with no credential rotation, compression or fallback. Unrelated provider exceptions retain their normal handling.
- Install a narrow failure-copy adapter so router failures identify Codex routing rather than falsely accusing Nous. No automatic three-attempt replay.
- Carry an explicit current-owner Codex preference into `career_cv_compile` and its spawned content planner. The brain still authorizes the eligible offer. No unused Nous credentials/client are initialized for pinned Codex planning.

## Transport boundary

The native Hermes controller retains its existing tool/stream-compatible provider. Codex CLI is a bounded text worker, not an emulated native tool-call transport. `career_cover_compile` renders and validates five paragraphs supplied by that controller; it does not invoke a separate cover-writing model. This repair fixes routing failures that precede either document tool; it does not claim cover composition has been moved to Codex.

## Validation

Focused router, CV integration, cover, template and writing-policy regressions run with external provider execution disabled. Tests cover typed nonretryable errors, sanitized receipts, deadline limits, exact eligible offers, owner preference scope/pickling and unchanged delivery gates.

A bounded live acceptance used the already-approved Allstate sample and verified professional variants. Router: ROUTED in 5.468 seconds. CV: PASS in 34.609 seconds, one content call, one render, OpenAI/gpt-6.1-sol; zero Nous calls. No attachment was sent, no application submitted, no tracker modified. Private CV/evidence remain outside Git.

Master, layout, fonts, renderer, fact bank and delivery verification were not changed. Existing unrelated dirty runtime files were preserved. No main merge.

Final combined focused regression: 164 passed, 0 failed (51.66 seconds).
