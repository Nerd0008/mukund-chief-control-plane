# Current Company State

- Timestamp: 2026-09-23T20:55:13Z
- Latest evidence run: 2026-09-23T20:55:13Z at code SHA `4ac1a22` (this run's commit)
- Evidence files:
  - `audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-run/evidence.json` (+ `.md`)
  - `audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-regression/evidence.json` (+ `.md`)
- Shared Control Plane status: Phase 2A
- Hermes: running on DeepSeek direct API (`deepseek-flash`); the GitHub remote bridge dispatches `agent-*` tasks through it
- Discord: connected
- Company Registry: installed
- Company audit: completed
- Discord capture: active for Chief channel (#chief + its threads)
- Local archive: active
- Automatic periodic Chief sync: scheduled task "ChiefDiscordSync" (every 30 min), observed Ready and scheduled; functionality itself not re-exercised in this run
- Manual fallback: python C:\Users\mukun\Documents\mukund-chief-control-plane\scripts\sync_discord_chief.py

## Executive Brain — measured test state

All numbers below come from one isolated run at 2026-09-23T20:55:13Z recorded by
`scripts/evidence_runner.py`. Each suite is one real subprocess with a declared import root;
counts are per suite and are not extrapolated.

- E1 executive brain runtime matrix: 32 collected / 32 passed / exit 0
- E2 governor + provider adapters: 45 collected / 45 passed / exit 0
- E3 baseline: 54 collected / 54 passed / exit 0
- E3 extended: 60 collected / 60 passed / exit 0
- E3 shadow orchestrator: 13 collected / 13 passed / exit 0
- E3 production rehearsal (real path, isolation, E1/E2 boundary): 24 collected / 24 passed / exit 0
- E4 resource continuity + E5 safe mode (combined suite): 37 collected / 37 passed / exit 0
- Remote queue (isolated suite): 30 collected / 30 passed / exit 0
- Single-run totals: 295 collected, 295 passed, 0 failed, 0 errors, 0 skipped across 8 suites

Note: prior state files recorded 271/271 across 7 suites at SHA `a999f6f`. That is superseded
by the 8-suite / 295-test figure above; the delta is the new rehearsal suite (24) and nothing else.

### E3 status

- E3 Stage 1: ACTIVE / SHADOW ONLY
- E3 Stage 2 production enablement: **NOT ENABLED**.
  - Standing conditional owner approval (authority `3838c61`, owner-actions `baf73d8`) authorizes
    **local-only** enablement once the recorded readiness preconditions pass. It is not
    self-executing and does not authorize VPS cutover or a deployment-architecture choice.
  - This run evaluated every recorded precondition and did **not** enable Stage 2, because an
    objective readiness condition is unmet (recorded below). No criterion was weakened.
- E3 orchestration DB: schema v2
- Implemented component set (unchanged): task fingerprinting, decomposition planner, execution DAG,
  capability registry + qualification gate, worker contracts, planner, router / meta-selector,
  decomposition review, context compiler, permission compiler, temporary team assembly, integrator,
  independent verifier / critic surface, conflict handling, logical replanning, evidence / outcome
  learning, escalation, exploration / shadow rules, cold-start qualification benchmark harness,
  decision rationale audit surface, shadow orchestrator.

### E3 production rehearsal evidence (NEW — produced by this run)

Real module: `exec-brain/e3_production_rehearsal.py`, run as a real process against a real
isolated orchestration DB. Evidence: `audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-run/`.

Five executable scenarios, all recorded from real component output (no hand-written results):

1. `Rehearsal: deterministic validation task` — outcome REHEARSAL_PASSED. Real router produced 2
   candidates for the single builder node; real team assembly assigned `codex-cli`; the
   independent verifier **rejected** the integrated output on attempt 1
   (`expected validated, got simulated`), a targeted repair was applied, and **re-verification
   PASSED** on attempt 2 (`first_attempt_passed=false`, `repaired=true`).
2. `Rehearsal: unrepaired rejection task` — verifier rejected and no repair was configured; the
   **replanner was consulted** (`replan-*` recorded) and the driver **escalated** to the owner.
3. `Rehearsal: task family with no seeded worker` — the router found **0 candidates**, team
   assembly was incomplete, and the pipeline **escalated** (`no_qualified_worker`). No assignment
   was fabricated.
4. `Rehearsal: decomposed multi-node task` — 3-node decomposition with a real integrator node;
   cross-role routing assigned `codex-cli` (builder) and `google-nano-banana-2` (vision); the
   integrator ran and verification PASSED. Team remained incomplete because no worker exists for
   the `integrator` role (reported honestly, not hidden).
5. `Rehearsal: contradictory multi-node task` — a deliberate cross-node contradiction was
   **detected** by the conflict handler (`factual_disagreement`, `value-A vs value-B`).

Isolation and boundary proof recorded in the same evidence file:

- Rehearsal-seeded capability rows are derived only from truthful `routable=true` workers
  (`codex-cli`, `google-nano-banana-2`, `deepseek-v41-flash`) and use state **EVALUATING**;
  no worker was marked QUALIFIED.
- Simulation isolation: production stores (`orchestration.db`, `governor.db`, `exec_brain.db`)
  were SHA-256 hashed before and after; **unchanged** (no diffs). A rehearsal-tagged evidence
  sink refuses (fail-closed) to persist into any production store.
- E1/E2 boundary: static scan of every `exec-brain/*.py` found **0** direct sqlite connections to
  `governor.db` / `exec_brain.db` and 0 direct SQL writes to E2 tables; the E2 public entry point
  (adapters calling `governor.record_request`) is present in 4 adapter modules. The public
  `governor.record_request()` interface was exercised against an **isolated** governor store only.

### E3 defects found by the rehearsal and fixed (commit `4ac1a22`)

1. Plan nodes carried no `node_id`, so router candidate keys (`node-0…`) never matched the node
   keys used by team assembly (`node-1…`): a team could never be assembled on the real path. The
   planner now emits stable `node_id`s and `build_dag` reuses them.
2. `TaskFingerprint.verification_type` (`'deterministic'`) was written straight into the node-level
   `verification_method` vocabulary, so every deterministic-verification task was rejected by
   decomposition review. An explicit mapping (`deterministic → test`) is now applied.
3. `ConflictHandler.detect_conflict` (and the integrator's contradiction scan) iterated an unordered
   set, so the reported disputed key changed between processes — non-reproducible audit evidence.
   Iteration is now sorted.

## Worker / provider state

Smoke readiness is not qualification; qualification is evidence-driven.

- DeepSeek (deepseek-flash): adapter implemented; live model observed; smoke PASS; E2 linkage
  VERIFIED; routable=true; qualification UNPROVEN
- Google image worker (gemini-3.1-flash-image): adapter implemented; smoke PASS; E2 linkage
  VERIFIED; routable=true; qualification UNPROVEN
- Codex CLI: re-validated 2026-09-23T20:35:47Z. Executable resolved at
  `%LOCALAPPDATA%\OpenAI\Codex\bin\80f78947ad880e6e\codex.exe` (CLI `0.155.0-alpha.16.3`);
  resolver is override -> PATH -> validated installed bin candidates. Auth confirmed locally
  (`codex doctor --json`, auth mode `chatgpt`); no token read or committed. One harmless smoke
  returned READY (exit 0). Provider `openai` reported; **served model identity remains UNKNOWN**.
  E2 linkage VERIFIED (`obs-20260923-d42e34a5`, token columns null). routable=true;
  qualification UNPROVEN.
- Remaining seven generic API workers (Mistral Small 4, GLM-5.3 Flash, Qwen3.8-27B, LongCat 2.0,
  MiniMax M3, Step 3.7 Flash, Tencent Hunyuan Hy3): adapters exist; owner-local credentials and
  live readiness evidence outstanding; routable=false

## Remote Task Queue

- Canonical GitHub task-data location: `remote-queue/`; implementation package: `remote_queue/`
- Bridge: implemented and remotely E2E-verified
- `agent-*` tasks are dispatched into the Hermes CLI through `remote_queue/hermes_dispatch.py`
- Visible remote-worker console support: implemented
- Queue tests are isolated (`remote_queue/tests/test_queue.py`: 30/30, exit 0)
- Scheduler: `HermesRemoteQueuePoller` registered and Ready (2-minute cadence)
- Recorded, deliberately unfixed defect: `poller.handle_task` routes any task id containing
  "operational" to `handle_operational_build()`, which returns a hardcoded status with no
  execution evidence. It must not be read as evidence of executed work.
- `full-operational-build-2026-09-24` remains the umbrella record in `running/` (no worker).
- This run: `agent-e3-local-production-rehearsal-2026-09-23` claimed and worked to a terminal
  state; one successor task staged in `remote-queue/pending/`.

## Stage 2 readiness evaluation (precondition by precondition)

Recorded preconditions (authority owner-directive update + `full_build_tracker.md`):

| # | Precondition | Result | Evidence |
|---|---|---|---|
| 1 | E1/E2/E3/E4/E5 relevant regressions pass | MET | 8 suites, 295/295, exit 0 (`…-e3-production-rehearsal-regression`) |
| 2 | Production rehearsal passes | PARTIALLY MET | orchestration-path rehearsal passes (`…-e3-production-rehearsal-run`); it does **not** exercise real worker execution — see unmet condition |
| 3 | No unresolved critical integrity/privacy/safety defect | MET (in the E3 path) | isolation fail-closed + production stores unchanged; E1/E2 boundary scan clean; 3 functional defects found and fixed |
| 4 | Worker routing/qualification state evidence-driven | MET | `routable` derives from smoke PASS + E2 linkage; qualification UNPROVEN; rehearsal used EVALUATING only |
| 5 | Rollback/recovery available | MET | rollback procedure documented (implementation plan §15); runtime `backups/` present; E3 store isolated from E1/E2; enablement reversible by reverting one record |
| 6 | State/evidence truthfully updated | MET | this file + `full_build_tracker.md` + evidence artifacts |

**Unmet condition (exact, factual):** the E3 orchestration path has **no production execution
leg**. `E3ShadowOrchestrator.rehearse()` composes planning/routing/assembly/integration/verification
but never dispatches an assigned node to a worker `ExecutionAdapter`; there is no
orchestrator→adapter dispatch step anywhere (`ExecutionAdapter(` is instantiated only inside
`codex_adapter.py`'s own smoke test). Consequently:

- no real low-risk R0/R1 task can be executed through E3, so the Stage 2 acceptance
  ("10 low-risk R0/R1 tasks executed with deterministic verification") cannot be met; and
- the production rehearsal exercises the orchestration path with simulated specialist outputs,
  not real worker execution.

Two supporting deployment facts, verified directly:

- none of the E3 orchestration modules (`e3_planner.py`, `e3_router.py`, `e3_team_assembly.py`,
  `e3_integrator.py`, `e3_verifier.py`, `e3_shadow_orchestrator.py`, `e3_conflict.py`,
  `e3_replan.py`, `e3_escalate.py`, `e3_evidence.py`, `e3_context.py`, `e3_permissions.py`,
  `e3_decomposition_review.py`, `e3_exploration.py`, `e3_qualification_benchmark.py`) are present
  in the live runtime root `%LOCALAPPDATA%\hermes\exec-brain`; only `e3_commands.py` is there.
- `eb.py` in the runtime has no `e3-*` CLI bindings, so the local CLI cannot drive E3.

Stage 2 therefore remains disabled. No readiness criterion was weakened.

## Current blockers / owner dependencies

- E3 Stage 2 local enablement: blocked on the unbuilt production execution leg above (engineering,
  not owner action).
- Seven provider credentials / account readiness steps remain owner/provider dependent
- Deployment architecture: intentionally deferred by owner until local operation is proven. The
  authority records laptop-primary + GitHub control plane + VPS watchdog/failover as the current
  owner *preference*, explicitly not a final decision and not authorization for VPS cutover.
- VPS access/details required before any real deployment/cutover; cutover is not authorized

## Next non-blocked priority

1. Build the E3 production execution leg: orchestrator node dispatch to the assigned worker's real
   `ExecutionAdapter`, schema v2 DAG/state + evidence persistence, deterministic verification
   wiring, and deploy the E3 orchestration modules + `e3-*` CLI bindings to the runtime root.
2. Re-run the production rehearsal **with real worker execution**, then re-evaluate Stage 2.
3. E4 checkpoint/failover and E5 convergence/safe-mode drill evidence on real execution paths.
4. Provider onboarding resumes immediately when owner-local credentials are supplied.
5. Local-first completion work (owner direction: prove local operation before any deployment
   architecture choice).

Do not fabricate qualification/provider evidence, and do not enable Stage 2 or choose a
deployment architecture without the readiness evidence and owner decisions recorded in the
authority file.
