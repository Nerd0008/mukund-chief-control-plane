# Codex reasoning for the E3 router

Owner decision, 25 October 2026: GPT-6.1 Sol via the existing Codex CLI powers
router reasoning. Worker selection is provider-neutral and evidence-based.

`E3ApplicationService.execute` and `execute_chat` invoke `RouterBrain` after
qualification/routability/Stage-2 filtering and before worker execution. Shadow
and dry-run preparation remain offline. Injected orchestration factories are
explicit test seams; production uses the configured reasoner. Direct low-level
engineering orchestration is not a substitute for the application service.

The existing `CodexExecutionAdapter` has an additional `router` profile. Its
normal worker profiles retain their contracts. Router invocations request
`gpt-6.1-sol`, high reasoning, read-only sandbox, no inherited user configuration
or repository rules, no persisted Codex session, disabled shell/unified-exec,
disabled multi-agent and disabled web search. No worker is run by this role.
The native-executable preference found in the installed adapter is preserved
in source, avoiding an older command shim that rejects this model.

The reasoner receives random opaque candidate handles, task-fit/capability and
qualification evidence; provider/model/worker identities are omitted. It must
return every eligible handle exactly once, an owner-review flag and enumerated
reason codes. Missing, invented, duplicate or malformed entries, tool use,
timeout and owner-review decisions block execution. There is no hidden ranking
or reasoning-model fallback. LongCat's hardcoded primary boost and Codex's
hardcoded fallback preference have been removed. Worker fallbacks must come from
the same already-filtered ranking. Existing image and permission restrictions
remain. Provider blinding reduces brand preference; it is not proof of universal
fairness or ranking quality.

Policy is non-secret and local:
`%LOCALAPPDATA%/hermes/exec-brain/router-brain-policy.json`.
Use `router-brain-policy.example.json`; `executable: null` uses the existing
validated executable resolver. An explicit override must validate. Never
silently substitute another model if access disappears. The model ID and effort
are requested values; the CLI does not independently attest served model identity.

Decision receipts live privately at
`%LOCALAPPDATA%/hermes/runtime/router-brain/decisions/`. They include request hash,
selected worker order, model/effort requested, CLI provenance, status and elapsed
time, but no task text, hidden reasoning, credentials or raw provider output.
Each routing call has a hard 45-second maximum and no retry loop.

## Validation and rollout limits

Synthetic live acceptance used the actual new adapter/profile, not a fake model:
stronger evidence selected a non-OpenAI worker in one case and an OpenAI worker
in the other (4.172s / 4.500s). No real downstream worker executed. Offline tests
cover permission filtering before reasoning, provider blinding, invalid decisions,
timeouts, tool-use rejection, receipts and service integration.

This change installs/configures the E3 router core. It does **not** establish
universal Hermes coverage. The normal gateway still uses native Nous. CV,
discovery, LinkedIn, cron and auxiliary helper paths identified in the private
25 October coverage audit still require migration into the shared decision and
execution boundary. Do not claim the model change fixes those bypasses, revive
the old incompatible provider shim, or broaden Stage-2 worker permissions.
The existing architecture audit continues to report discovery's two business
adapter imports. Keep that failure visible until the actual call paths migrate.
No gateway restart or CV/template/Gmail/Calendar/LinkedIn configuration change is
part of the router-core installation.
