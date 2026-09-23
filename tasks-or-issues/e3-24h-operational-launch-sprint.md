# E3 24-Hour Operational Launch Sprint

Status: ACTIVE
Created: 2026-09-23
Owner: Mukund
Target: operational E3 production capability by 2026-09-24 evening

## Objective

Get the Chief-of-Staff system operational by tomorrow evening without weakening the frozen E1/E2/E3 safety architecture.

"Operational" for this sprint means:
- at least one production-capable text/reasoning worker,
- one independent text/verification worker,
- one image-generation worker,
- E3 planner/router/team assembly can dispatch real work,
- qualification gate has enough cold-start evidence for launch roles,
- integration + independent verification work end-to-end,
- failure/escalation path works,
- E1/E2/E3 regressions and audits pass,
- owner explicitly approves Stage 2 production dispatch.

It does NOT require every roster worker to be configured or qualified before launch.

## Current starting state

- DeepSeek: execution-ready, routable=true, qualification=UNPROVEN
- Gemini image worker: authentication + model discovery complete; adapter/smoke/E2 linkage in progress
- Codex CLI: adapter implemented; parked until usage limit resets
- Remaining roster providers: not yet execution-ready
- E3 Stage 1: implemented, shadow-only
- Stage 2: NOT APPROVED

## Sprint strategy

Do not serially configure all ten workers before attempting Stage 2.

Launch-critical worker set:
1. DeepSeek — primary text/reasoning candidate
2. Gemini image — image-generation candidate
3. One independent text provider — Mistral preferred unless blocked; use another available low-cost provider if Mistral access becomes a blocker
4. Codex only if usage limit resets in time; otherwise it is non-blocking for launch

Additional roster workers are post-launch expansion unless they are immediately available with no setup friction.

## Critical path

### Phase A — Finish Gemini
- implement Google image adapter
- run smoke test
- capture actual usage/metadata
- E2 record-request
- regressions/audits
- routable=true only if all readiness checks pass
- qualification remains UNPROVEN

### Phase B — Add one independent text worker
Use the fastest provider with working credentials/API access.
Target: Mistral Small 4.
Follow the proven DeepSeek onboarding pattern:
credential -> live model discovery -> adapter -> deterministic smoke -> actual usage -> E2 linkage -> regressions -> routable.

Do not stop launch because other roster providers are not ready.

### Phase C — Cold-start qualification
Build/execute a compact deterministic launch benchmark suite for only the roles required for Stage 2:
- planner
- router
- text worker/builder
- critic/verifier
- integrator
- image generator

Qualification must remain contextual.
Do not create one universal worker score.

Require at least:
- one qualified candidate for planner/router/integrator path,
- one independently qualified verifier/critic path where possible,
- one qualified image-generation path.

### Phase D — End-to-end E3 production rehearsal
Run representative real flows:
1. simple single-worker text task
2. decomposed two-worker task
3. worker + independent verifier task
4. image-generation task
5. forced worker failure/unavailability -> fallback or owner escalation
6. verifier rejection -> one targeted repair
7. no-qualified-worker case -> owner escalation

Verify:
- E1 classify/freeze is invoked where required
- E2 record-request receives actual execution telemetry
- rationale/trace/why views work
- DAG/event state updates correctly
- no raw secrets or chain-of-thought are logged
- failure loops obey R0/R1/R2/R3 convergence rules

### Phase E — Owner launch gate
Only after the rehearsal passes:
- update current_company_state.md truthfully
- produce Stage 2 readiness record
- run full E1/E2/E3 regressions + audit/gov/e3 verification
- owner explicitly approves Stage 2
- enable production dispatch in controlled mode

## Cut / defer until after launch

Do not let these block the deadline:
- configuring all remaining 10 roster workers
- benchmarking every worker across every capability
- E4 predictive exhaustion/resource continuity
- E5 resilience drills/safe-mode maturity
- Phase 2B Discord expansion
- uncle/federation work
- cosmetic documentation cleanup not required for truth/audit

## Deadline discipline

If a provider setup takes more than ~30 minutes because of access, billing, SDK, or credential issues:
- park it,
- record the blocker,
- move to the next viable provider.

If a launch-critical implementation defect cannot be resolved safely:
- escalate to Mukund,
- do not silently weaken a deterministic gate.

## Definition of Done for tomorrow evening

E3 is operational when:
- Stage 2 production dispatch is owner-approved and enabled,
- at least two independent text-capable execution paths are usable OR one text path plus Codex if Codex is restored,
- Gemini image generation is usable,
- launch-critical roles have cold-start qualification evidence,
- end-to-end multi-worker orchestration succeeds,
- independent verification works,
- controlled repair/replan works,
- owner escalation works,
- E1/E2/E3 regressions and audits pass,
- source-of-truth state is current.

Everything beyond this is expansion, not a launch blocker.
