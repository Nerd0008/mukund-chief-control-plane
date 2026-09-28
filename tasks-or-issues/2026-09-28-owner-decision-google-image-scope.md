# Owner decision — separate Chief text Stage 2 from Google image capability

Date: 2026-09-28
Owner: Mukund
Status: APPROVED

## Decision

Google Nano Banana is **not a prerequisite for bringing the Chief/E3 text stack operational**.

For the immediate production activation:

- General Chief / Discord / Career Ops text execution uses the text Stage-2 pool.
- Initial text Stage-2 allowlist: `longcat-2.0`.
- `google-nano-banana-2` is excluded from the initial general/text Stage-2 activation.
- The historical Google image intermittency must therefore **not block** readiness or activation of the text/Chief pool.

Google Nano Banana is retained as a **separate image-generation capability**, primarily for LinkedIn visual/content-generation workflows.

## Google image capability policy

The existing evidence remains truthful and unchanged:

- recorded repeat series observed 2/9 no-image responses;
- both recurrences carried provider finish reason `IMAGE_RECITATION`;
- no claim is made that the intermittency is resolved;
- no stability claim may be inferred from later individual successes.

When the Google image capability is invoked explicitly:

- it is eligible only for an image/vision task, never as the general Chief text worker;
- preserve its evidence-backed vision capability state exactly as supported by the current registry/evidence;
- preserve the existing bounded content-stop policy;
- maximum recovery remains the recorded bounded same-request retry policy;
- unrecovered image stops must fail visibly/escalate rather than silently succeed;
- no unbounded retry;
- no automatic fallback that bypasses E3 policy;
- no weakening of verification or qualification gates.

If the current Stage-2 implementation cannot express role/capability-scoped allowlisting, keep Google outside the active Stage-2 allowlist for this Chief activation and treat LinkedIn image activation as a separate scoped capability activation. Do not widen the general text pool merely to make image generation available.

## Readiness-gate re-scope

The global readiness rule:

`Google image worker real-dispatch failure resolved (not intermittent)`

must no longer be a release blocker for a Stage-2 activation whose requested production scope contains no Google image worker.

The readiness gate must evaluate the **requested activation scope**:

- LongCat/text readiness must stand on LongCat/text evidence and the shared E1/E2/E3 architecture gates.
- Google-image readiness remains separately reportable and must continue to show the known intermittency honestly.
- Excluding Google from the requested activation scope is not equivalent to declaring its image issue resolved.

## Authorization

Mukund authorizes the following bounded continuation:

1. Record this owner decision as the authoritative scope decision.
2. Update/re-scope the readiness gate so optional out-of-scope image workers cannot block the requested text-only Stage-2 activation.
3. Re-run the readiness gate with zero unnecessary provider calls.
4. If all in-scope gates pass, enable local Stage 2 for `longcat-2.0` only.
5. Keep OpenRouter disabled/not required.
6. Perform the previously defined bounded live Discord acceptance for:
   - persistent Chief context/memory;
   - deterministic Career Ops routing;
   - Hermes tool/skill loop through E3.
7. Do not spend a Google image call as part of Chief text activation.
8. Do not merge to main automatically.

LinkedIn image generation using Google Nano Banana remains a separate explicit image-capability workflow and must not gate normal Chief operation.
