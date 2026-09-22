# Handover — E3 Provider Access + CLI Setup / Stage 1 Continuation

Date: 2026-09-22
Owner: Mukund
Purpose: Resume the Executive Brain E3 build after work / tomorrow without losing the exact implementation and provider-access context.

## IMPORTANT — first action in the next ChatGPT thread

Do NOT rely only on this handover.

At startup:

1. Read this file.
2. Read `state/current_company_state.md`.
3. Read `decisions/exec-brain-e2-rollout.md`.
4. Read `architecture-proposals/executive-brain-e3-architecture-amendment.md`.
5. Read `architecture-proposals/executive-brain-e3-implementation-plan.md`.
6. Read `handovers/2026-09-22-e3-model-roster-handover.md`.
7. Read `handovers/2026-09-22-ai-model-selection-handover.md` if model-selection background is needed.
8. Check the latest commits on `main`.
9. Treat the live control-plane repo as source of truth if anything in this handover is stale.

Repository:
`Nerd0008/mukund-chief-control-plane`

Local repo:
`C:\Users\mukun\Documents\mukund-chief-control-plane`

---

# 1. Current phase status

## E1 — COMPLETE / ACTIVE

E1 is the Executive Brain quality-control foundation.

Key properties:
- classify → decompose(optional) → freeze → route discipline
- immutable quality floors
- append-only/audited records
- route-before-freeze blocked
- owner overrides
- hash-chain integrity
- backup/restore

Verified rollout:
- 32/32 tests PASS
- `eb audit --verify` PASS

Do not reopen E1 unless a verified defect appears.

## E2 — COMPLETE / ACTIVE

E2 Resource Governor is live.

Current verified state:
- 45/45 E2 tests PASS
- 32/32 E1 regression PASS
- `eb gov-verify` PASS
- separate `governor.db`
- Nous/LongCat telemetry present
- DeepSeek telemetry present
- Codex observed-only
- Antigravity observed-only
- UNKNOWN semantics preserved
- resource telemetry separated from routability

Rollout commit:
`aed691078095450440bddebc68e42093a1983424`

Latest merged repo state before E3 planning:
`2d55abcb44990e151e9a051e00677789bdf28d6a`

## E3 — PLANNED / NOT IMPLEMENTED

E3 implementation has NOT started.

The architecture was expanded from narrow worker qualification into:

**Intelligent Multi-Model Orchestration + Dynamic Team Assembly + Worker Qualification**

The current E3 planning documents include owner decisions D-AI-1 through D-AI-7, architecture corrections A1-A7, and A8 Decision Rationale / Reasoning Audit Log.

Latest E3 planning commit at handover creation:
`c91acdc833387e7e6aa9814f86364ba3de32500f`

E3 is still PLAN-ONLY at this point.

---

# 2. E3 architecture decisions already settled

Do NOT reopen these unless an implementation blocker appears.

## D-AI-1
Use separate `orchestration.db`.

E1 `exec_brain.db`, E2 `governor.db`, and E3 `orchestration.db` remain separated.

## D-AI-2
Router is a capability role, NOT a permanent hardcoded model.

Use:
deterministic meta-selector → eligible Router AI → deterministic Qualification Gate.

Current Hermes inference may act as a configurable bootstrap router during Stage 1 only.

## D-AI-3
Planner and router are separate logical capabilities.

Same worker may perform both only if independently qualified for both.

## D-AI-4
Shadow evaluation belongs to E3.

Support in v1, disabled by default, R0/R1 only, independently/deterministically verifiable.

## D-AI-5
Exploration is conservative and policy-based.

No arbitrary exploration percentage.

## D-AI-6
Convergence is risk-sensitive.

R0/R1: initial + up to 2 targeted recoveries.
R2: initial + max 1 autonomous repair.
R3: no repeated autonomous repair loop after material verified failure.

## D-AI-7
Integrator is a separate dynamically selected capability role.

Integrator cannot self-certify.

---

# 3. Architecture corrections already incorporated

## A1 — Hybrid decomposition gate

Deterministic structural validation + AI semantic decomposition critic.

## A2 — E2 telemetry adapters are NOT E3 execution adapters

Every worker needs an independent E3 execution path/adapter before it becomes dispatchable.

## A3 — E1/E2 public interfaces

E3 does not directly SQL-write to E1/E2 DBs.

New/replanned E3 subtasks call E1 public classify/decompose/freeze interfaces.

Actual provider executions report usage through the E2 public record-request interface.

## A4 — Event-sourced governance state

Qualification changes and DAG state transitions must have append-only authoritative event history.

## A5 — UNKNOWN capacity remains UNKNOWN

Unknown E2 capacity is policy-based, never automatically treated as zero/unlimited/healthy.

## A6 — Long-term evidence survives retention

Detailed execution data may expire, but compact verified capability history, suspensions, serious failures, model identity, and qualification transitions remain preserved.

## A7 — Data privacy

No raw chain-of-thought, unrestricted private prompts, credentials, or secrets in rationale/performance logs.

Use structured rationale codes, concise explanation, and evidence references.

---

# 4. A8 — Owner-reviewable Decision Rationale Audit Log

Mukund explicitly requires the ability to review WHY Chief/E3 made a management decision.

E3 therefore includes append-only decision rationale and outcome-review records.

Required for consequential decisions such as:
- task decomposition
- decomposition rejection/revision
- team/router selection
- worker selection
- candidate rejection
- Qualification Gate outcomes
- conflict resolution
- integration decisions
- targeted rework
- replanning
- verifier/critic conclusions
- escalation

Rationale should record:
- what was decided
- alternatives considered
- why alternatives were rejected
- decisive factors
- evidence references
- assumptions
- uncertainties
- confidence
- tradeoffs
- verification plan

After execution, a linked hindsight-safe Outcome Review records what actually happened and whether the original management decision was SUPPORTED / PARTIALLY_SUPPORTED / POOR / INCONCLUSIVE.

Owner-facing CLI views planned:
- `eb e3-rationale <decision_id>`
- `eb e3-trace <task_id>`
- `eb e3-why <node_id>`

The original rationale must never be overwritten by hindsight.

---

# 5. Current 10-worker E3 pool

Authority:
`handovers/2026-09-22-e3-model-roster-handover.md`

Current roster:

1. Codex CLI
2. Mistral Small 4
3. Google Nano Banana 2
4. DeepSeek V4.1 Flash
5. GLM-5.3 Flash
6. Qwen3.8-27B
7. LongCat 2.0
8. MiniMax M3
9. Step 3.7 Flash
10. Tencent Hunyuan Hy3

Important:

"LOCKED" in the roster means included in the pool.
It does NOT mean configured, callable, routable, or QUALIFIED.

Qualification is evidence-based and task/role-specific.

No static mappings such as:
`coding -> Codex`
or
`research -> DeepSeek`.

E3 dynamically reasons over each task and may assemble several different workers into one temporary team.

---

# 6. Critical provider-access status at handover

Mukund has NOT yet configured the E3 worker APIs/CLI execution paths.

Do not assume any worker is callable merely because it is in the roster.

Track these separately for every worker:

- included_in_pool
- provider metadata known
- credential reference present
- CLI/tool installed
- execution interface present
- execution adapter implemented
- adapter smoke-test passed
- routable
- qualification state

Example truthful initial state:

```
worker: Mistral Small 4
included_in_pool: yes
credential_configured: no/unknown
execution_interface_present: no/unknown
adapter_verified: no
routable: no
qualification: UNPROVEN
```

Missing access must NOT block Stage 1 shadow planning.

A worker with no verified execution path remains non-routable.

---

# 7. API key / credential setup policy

Mukund wants to begin configuring provider credentials and CLI paths when work resumes.

Do this ONE PROVIDER AT A TIME.

NEVER ask Mukund to paste API keys into:
- ChatGPT
- Discord
- GitHub
- source code
- logs
- prompts

Keys must be entered locally on Windows and stored by local secret reference.

Existing E2 policy:
Windows Credential Manager is canonical for DeepSeek.

For every new provider, prefer:
- Windows Credential Manager or another local OS-backed secret store
- environment-variable fallback only where needed
- code/config references SECRET NAMES, never secret values

Before storing anything:
- inspect whether a credential reference already exists
- report yes/no only
- never print the value

After configuration:
- run a minimal provider smoke test locally
- ensure secret values do not appear in stdout/logs
- mark the execution path verified only if the smoke test succeeds

---

# 8. CLI setup is part of the continuation

Mukund explicitly wants CLI-side setup included, not only API keys.

Codex CLI is especially important because it is one of the 10 E3 worker slots and is intentionally treated as an interface/worker rather than separate GPT model slots.

Current E2 state:
- Codex = observed-only / non-routable
- Antigravity = observed-only / non-routable

E3 must independently investigate/configure actual CLI/automation paths.

For each CLI worker/interface verify:

1. installed?
2. authenticated?
3. executable non-interactively?
4. accepts structured task/context input?
5. returns machine-capturable output?
6. exit codes/errors deterministic enough to map?
7. can model/reasoning/profile be controlled where supported?
8. can usage/model identity be observed?
9. cancellation/timeout behaviour?
10. safe secret handling?
11. can E2 usage be updated after execution?

Do not call a CLI E3-routable until automation is verified.

---

# 9. Suggested provider-access order

When resuming, prioritize setup that gives E3 a useful initial set of workers without trying to configure all 10 at once.

Suggested progression:

1. DeepSeek API
   - E2 integration already exists
   - configure/verify local secret reference
   - create/verify independent E3 execution path later

2. Codex CLI
   - install/authenticate/configure CLI
   - verify non-interactive automation
   - this is a distinct E3 execution path, not E2 telemetry

3. Google API / Nano Banana 2
   - configure local key/reference
   - image worker

4. Mistral API

5. GLM API

6. Qwen API

7. MiniMax API

8. Step API

9. Tencent Hunyuan API

10. Nous / LongCat access path
    - existing Hermes/Nous path exists, but E3 dispatch must still be independently verified

The order can change if provider setup/access realities make another path easier.

Do not create unnecessary provider complexity merely to finish all 10 immediately.

---

# 10. E3 Stage 1 intent

The owner has effectively approved the E3 architecture direction after D-AI-1..7 and A1..A8 review.

However, as of this handover, the planning docs remain the latest committed state and E3 code is not yet implemented.

The next build action should first re-check whether the approved architecture has been applied to `approved-architecture/executive-brain-v2.md` after this handover.

If NOT yet applied, the next Hermes instruction should:

1. record final E3 architecture approval
2. apply the amendment to the approved architecture
3. implement E3 CORE + STAGE 1 only
4. stop before Stage 2

Stage 1 is SHADOW ONLY.

It may:
- understand tasks
- propose decomposition
- build execution DAGs
- generate candidate workers/teams
- run Qualification Gate logic
- generate decision rationales
- show e3-rationale / e3-trace / e3-why
- accumulate reviewed planning/routing evidence

It must NOT dispatch production worker tasks.

Missing API keys/CLIs must not block Stage 1.

---

# 11. Stage 2 readiness gate

Do NOT enable Stage 2 automatically.

Before any worker can be dispatched, require:

- provider/interface actually configured
- credentials/access stored locally
- execution adapter implemented
- smoke test passed
- routable state true
- E2 usage linkage working where applicable
- worker allowed under cold-start qualification rules
- no privacy/egress violation

UNPROVEN roster workers enter low-risk work as EVALUATION_ONLY, not production-qualified.

Before Stage 2, produce a readiness report for all 10 workers:

READY
CONFIGURATION_REQUIRED
INTERFACE_MISSING
ADAPTER_MISSING
SMOKE_TEST_REQUIRED
UNAVAILABLE

---

# 12. Tests / rollout expectations

Current revised E3 planning target is approximately 108 tests after A8.

E3 implementation must preserve:

E1:
- 32/32 regression PASS
- `eb audit --verify` PASS
- exec_brain.db schema unchanged

E2:
- 45/45 regression PASS
- `eb gov-verify` PASS
- governor.db schema unchanged

E3:
- `eb e3-verify-db` PASS
- Stage 1 shadow demos
- rationale audit trail working
- no production dispatch before owner approval

---

# 13. Owner schedule / continuation context

At handover time Mukund is leaving for work in roughly 10 minutes.

He expects to return late tonight and may be too tired for substantial implementation.

If he has energy tonight:
- do only light, low-risk setup/review
- one provider credential/CLI at a time
- avoid starting a large implementation block if there is not enough time to verify it cleanly

Main continuation is expected tomorrow.

Mukund noted that relevant CLI/resource limits should reset tomorrow, so tomorrow is a better time for heavier CLI setup/testing.

Do not rush secret setup or worker activation because of the sprint.

---

# 14. Recommended first actions when Mukund resumes

1. Read this handover + live repo state.
2. Check whether any commits landed after `c91acdc833387e7e6aa9814f86364ba3de32500f`.
3. Confirm whether E3 architecture has been formally applied to `approved-architecture/executive-brain-v2.md`.
4. If not, complete the final architecture-approval/apply step before implementation.
5. Decide whether Mukund wants to:
   A. configure provider access/CLIs first, or
   B. implement E3 Stage 1 shadow infrastructure first.
6. Either sequence is valid because Stage 1 does not require the full worker pool to be callable.
7. If configuring access, start with ONE provider/interface and verify it fully before moving to the next.
8. Never expose credential values in chat or GitHub.

Suggested practical sequence tomorrow:

```
DeepSeek credential/access verification
        ↓
Codex CLI install/auth/automation verification
        ↓
E3 Stage 1 core implementation
        ↓
remaining provider credentials/adapters progressively
        ↓
Stage 1 acceptance review
        ↓
owner approval
        ↓
Stage 2 controlled EVALUATION_ONLY execution
```

This sequence is not mandatory if local setup realities suggest a better ordering.

---

# 15. Suggested first message for the continuation chat

"Use handovers/2026-09-22-e3-access-setup-handover.md from my GitHub control plane. Read everything it tells you to read and check the latest repo state. E1/E2 are complete, E3 is plan-only with A1-A8 incorporated. I have not configured the E3 API keys or CLIs yet. Continue from the exact current state, one thing at a time."
