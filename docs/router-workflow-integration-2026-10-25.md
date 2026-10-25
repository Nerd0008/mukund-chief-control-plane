# Shared workflow routing integration

Owner approval: 2026-10-25, including eligible JD and verified professional facts reaching Codex text workers. No new Gmail, Calendar, LinkedIn posting or application-submission permissions.

## Production seams

- Existing E3 execution uses RouterBrain with provider-masked candidate handles and evidence-based rankings.
- `workflow_routing.py` adds the same decision seam for CV content selection, discovery classification/research, and LinkedIn content/judging. CV master, template, renderer, facts and delivery verification are unchanged.
- `native_router_plugin.py` registers native `llm_execution` middleware and wraps auxiliary SDK clients. Native function calls, image requests, streaming and vendor-specific protocols keep compatible transports.
- `router_gateway_entry.py` requires router registration at startup and before every normal gateway LLM call. Missing routing blocks execution instead of falling through the host's ordinary fail-open plugin behavior. Auxiliary routing must also be installed before startup.
- Router/bounded-text CLI uses the existing authenticated native Codex executable, GPT-6.1 Sol, high reasoning, ephemeral read-only execution, user configuration/rules ignored, shell/exec/subagents/web search disabled. No new credentials are introduced.
- Native provider/model binding stores only IDs, resolves existing secure credentials at use, and preserves the current Nous/LongCat native transport. Cached decisions are scoped to workflow/task/offer set and expire in 120 seconds.
- Codex is eligible only for compatible bounded text. No simulated text CLI is offered for native tool/image/stream/vendor-structured calls. Unknown usage is reported as unknown rather than fabricated zero. A synchronous text operation shares one elapsed-time budget across routing and generation; the existing outer CV 180-second process limit remains authoritative.

## Verification

Full Career Ops plus initial router suites: **1667 passed**, zero failures, 182.97 seconds. Final router/core suite after adding the mandatory gateway registration guard: **52 passed**, 3.99 seconds. Offline tests explicitly block external network/model execution and isolate injected classifiers from real health probes.

One synthetic live text acceptance: PASS, 39.063 seconds, selected OpenAI/GPT-6.1 Sol; no owner content sent and no tools or external writes. Model identity is requested/receipt identity; the served model is not independently attested.

The initial archived copy produced layout-hash failures because Git archives use stored line endings while the owner-approved current workbook/layout files retain the live bytes. Current source approval hashes match, and the actual live-source CV integration tests pass. A simultaneous Hermes search-scope change temporarily invalidated a funnel counter fixture; Hermes updated its own fixture and the full current suite then passed. Its scope edits are preserved and excluded from this routing commit.

## Rollout and limits

Use the existing backed-up runtime deployer; install `router-brain-local`; enable that plugin; launch the normal service through the guarded gateway entrypoint; verify registration and controlled acceptance before calling activation successful. Keep the native global provider unchanged. Preserve existing hidden Windows launchers.

A single protocol-compatible transport still consults the brain but offers no interchangeable worker choice. This does not invent additional qualified providers. Pre-existing image/STT `e3` backend settings are not replaced by a text CLI: unavailable media backends remain a separate capability limitation. Deterministic, non-model tools do not require model-selection calls. Direct developer invocations bypassing the guarded service launcher are not represented as covered production gateway paths.

No reset, clean, stash, blanket staging, main merge or unrelated configuration changes are part of this integration.
