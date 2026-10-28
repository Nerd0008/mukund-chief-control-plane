# Native router timeout investigation and mitigation — 28 October 2026

## Confirmed incident

LinkedIn owner message at 14:18:03 UTC stopped at 14:18:49. Router decision
192ab48ebf8a42d4a61af6e13f33a346 has cli_status TIMEOUT after 45.344 seconds,
with the native Codex executable 0.164.0-alpha.11.1, model gpt-6.1-sol and high
reasoning. The following job-report controller decision also timed out at 45s.
The underlying native transport label in Hermes remains Nous; that label does
not mean Nous caused this router-selector timeout.

The LinkedIn session recorded only the owner message and the failure response
during this attempt, with zero tool calls. The inspected draft, frozen text,
schedule and publication ledger did not change during this repair. Earlier
work in the same session did execute actions; this report does not erase that
history or infer that earlier attempts were harmless.

A fresh synthetic test on the same installed CLI/model/high effort routed in
8.562 seconds. Account usage was not exhausted at inspection. Those findings
disprove a persistent CLI startup failure, but do not establish why the three
earlier calls were slow. Existing receipts discarded partial CLI progress and
local Codex log databases did not contain the child-process failure detail.
No exact remote-service, network or reasoning-delay cause is claimed.

## Mitigation and diagnostic repair

- Native controller selection can use up to 90 seconds while reserving at
  least 25% of its existing request budget for the chosen worker. A shorter
  parent deadline remains authoritative. No request deadline is extended.
- Shared selection plumbing accepts that explicit native-controller budget;
  ordinary workflow callers retain their existing default 45-second budgets.
- gpt-6.1-sol/high reasoning, unbiased worker selection, compatibility and
  qualification checks are preserved. No provider or credential config changed.
- No automatic routing/action retry or publication replay was introduced.
- Cancel-aware child cleanup now preserves captured timeout output long enough
  for the adapter to derive safe protocol milestones and coarse error categories.
  Only allowlisted flags/categories enter router receipts. Prompt/response text,
  reasoning, raw stderr and credentials are excluded from those receipts.

## Verification and deployment

The new tests reproduced a 50-second otherwise-valid selection being blocked
by the previous 45-second cap, and timeout progress being discarded. After
repair, a 50-second decision proceeds within the same total deadline; a
95-second over-budget decision blocks without invoking the worker or retrying.
Actual child-timeout cleanup and privacy filtering are regression-tested.

254 relevant regressions passed: native selection, router decisions, routing,
controller health, stage contracts, admission, auxiliary gates, approval/draft
workflow and operational diagnostics. One initial fixture needed the required
receipt_evidence symbol; one initial E3-only invocation lacked career-ops in
PYTHONPATH. The corrected explicit-source run passed; those earlier failed
invocations are not counted as successful tests.

Five modules were deployed atomically after confirming zero active agents and
zero claimed/running scheduler executions. Gateway drained cleanly and restarted
as PID 40936 through the guarded entrypoint. Discord is connected. Runtime and
repository module hashes match. No scan was paused or interrupted.

A live synthetic test through the deployed middleware made a real router call,
received a valid decision in 9.125 seconds with a 90-second selection allowance,
and invoked its inert synthetic worker exactly once. All worker health/selection
evidence for that test was isolated privately. No real downstream worker model,
owner profile transmission, image generation, Discord message, or publication
was performed. This is not proof that every future provider call will succeed.

Private recovery and receipts:
C:/Users/mukun/Documents/Codex/native-router-timeout-20261028/

Official CLI reference consulted for structured execution diagnostics:
https://developers.openai.com/codex/cli/reference/
