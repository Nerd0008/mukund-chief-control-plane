# Current Company State

- Timestamp: 2026-09-23T20:22:00Z
- Latest evidence run: 2026-09-23T20:21:03Z at code SHA `40f8f68363d9e23a761c3398c91ed09b066991ed`
- Evidence file: `audits/evidence/2026-09-23T20-21-03Z-isolated-queue-recovery/evidence.json` (+ `.md`)
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

All numbers below come from one isolated run at 2026-09-23T20:21:03Z recorded by
`scripts/evidence_runner.py`. Each suite is one real subprocess with a declared import root;
counts are per suite and are not extrapolated.

- E1 executive brain runtime matrix: 32 collected / 32 passed / exit 0
- E2 governor + provider adapters: 45 collected / 45 passed / exit 0
- E3 baseline: 50 collected / 48 passed / 2 errors / exit 1 (both errors environmental — Codex CLI binary is not installed on this machine; no other failures)
- E3 extended: 60 collected / 60 passed / exit 0
- E3 shadow orchestrator: 13 collected / 13 passed / exit 0
- E4 resource continuity + E5 safe mode (combined suite): 37 collected / 37 passed / exit 0
- Remote queue (isolated suite): 30 collected / 30 passed / exit 0
- Single-run totals: 267 collected, 265 passed, 2 errors, 0 skipped across 7 suites

Corrections to earlier state claims:

- The previously recorded "207 tests pass" aggregate is not reproducible. The old arithmetic
  32+45+50+60+13+37+15 also never equalled 207. The table above replaces it.
- `test_governor.py` was previously recorded as un-runnable (missing `governor` module). It is
  runnable when the E2 runtime import root `%LOCALAPPDATA%\hermes\exec-brain` is on `PYTHONPATH`,
  and it passes 45/45. E1/E2 evidence is therefore measured now, not only historical.

### E3 status

- E3 Stage 1: ACTIVE / SHADOW ONLY
- E3 Stage 2 production enablement: STANDING CONDITIONAL OWNER APPROVAL granted 2026-09-23 for
  **local** enablement only (authority updated in `3838c61`, owner-actions file in `baf73d8`).
  It is not self-executing: local enablement requires the recorded preconditions — local
  E1/E2/E3/E4/E5 regressions pass, production rehearsal passes, no unresolved critical
  integrity/privacy/safety defect, evidence-based routing, an available rollback/recovery path,
  and truthfully updated state/evidence. It does not authorize VPS cutover or a final
  deployment-architecture choice.
  - Unmet precondition as of this run: production rehearsal evidence does not exist yet
    (E3 rehearsal is OPEN in the tracker below). Stage 2 therefore was NOT enabled by this
    recovery task, which is also required by this task's own stop conditions.
- E3 orchestration DB: schema v2
- Implemented component set (unchanged by this run): task fingerprinting, decomposition planner,
  execution DAG, capability registry + qualification gate, worker contracts, planner, router /
  meta-selector, decomposition review, context compiler, permission compiler, temporary team
  assembly, integrator, independent verifier / critic surface, conflict handling, logical
  replanning, evidence / outcome learning, escalation, exploration / shadow rules, cold-start
  qualification benchmark harness, decision rationale audit surface, shadow orchestrator.
- Recorded gap: the shadow orchestrator passing 13/13 composition tests is NOT production
  rehearsal evidence. Executable rejection/repair and simulation-evidence isolation remain open.

### E4 / E5

- E4: ResourceMonitor, CheckpointManager, EquivalentFailover, orchestration schema v2
  resource/checkpoint persistence
- E5: SafeModeManager, FailureDrills, ConvergenceEnforcer, MalformedOutputHandler, schema v2
  safe-mode/failure/convergence persistence
- Both are unit-verified only; drill/failover evidence on real execution paths remains open.

## Worker / provider state

Smoke readiness is not qualification; qualification is evidence-driven.

- DeepSeek (deepseek-flash): adapter implemented; live model observed; smoke PASS; E2 linkage
  VERIFIED; routable=true; qualification UNPROVEN
- Google image worker (gemini-3.1-flash-image): adapter implemented; smoke PASS; E2 linkage
  VERIFIED; routable=true; qualification UNPROVEN
- Codex CLI: adapter implemented; usage limit reported reset by owner (2026-09-23) — this is a
  claim to re-test, not execution evidence; routable=false; qualification UNPROVEN
  - Observed on this machine 2026-09-23T20:24Z: the two E3 baseline Codex tests
    (`TestCodexAdapter.test_codex_cli_version`, `TestCodexAdapter.test_codex_smoke_blocked`)
    error with `RuntimeError: Codex CLI not found: checked configured path and PATH`
    (`exec-brain/codex_adapter.py:28`). Recorded as evidence for the re-validation task; the
    CLI was not installed or located by this recovery, and no Codex allowance was spent.
- Remaining seven generic API workers (Mistral Small 4, GLM-5.3 Flash, Qwen3.8-27B, LongCat 2.0,
  MiniMax M3, Step 3.7 Flash, Tencent Hunyuan Hy3): adapters exist; owner-local credentials and
  live readiness evidence outstanding; routable=false

## Remote Task Queue

- Canonical GitHub task-data location: `remote-queue/`; implementation package: `remote_queue/`
- Bridge: implemented and remotely E2E-verified
- `agent-*` tasks are dispatched into the Hermes CLI through `remote_queue/hermes_dispatch.py`
- Visible remote-worker console support: implemented
- Streaming hardening: `e643fd162cf2b627d734b5735e205de3d00387a4` forces UTF-8 with replacement
  fallback in the visible worker and fails closed on reader errors
- Queue tests are now isolated: `remote_queue/tests/test_queue.py` runs against disposable queue
  and repository roots, with git publication mocked or aimed at a throwaway bare origin, a
  distinct poller mutex, and env-redirected kill switch / lock paths. Isolation is asserted by
  guard tests, including a whole-suite live-state check.
- Scheduler: `HermesRemoteQueuePoller` is registered and Ready (2-minute cadence)
- Queue lifecycle defects fixed and regression-tested on 2026-09-23:
  1. `claim_task` could destroy a task when publication raised (pending unlinked first, then the
     running copy deleted) — now the running copy is written first and the task is never in
     neither state.
  2. `find_pending_tasks` / `get_running_tasks` read task JSON with the platform default codec,
     so non-ASCII task content raised `UnicodeDecodeError` and silently demoted or dropped
     records on Windows — now explicit UTF-8.
  3. A push rejected because origin advanced (observed live at 2026-09-23T20:13:59Z) left queue
     state unpublished with no retry — now rebased and retried exactly once, failing closed with
     the local commit preserved when a rebase genuinely conflicts.
  4. An invalid pending task could never reach a terminal state: `block_task()` raised for a
     pending file, which skipped the `blocked/` copy, so the task failed validation on every
     later cycle — now it is copied to `blocked/` and removed from `pending/`.
- Recorded, deliberately unfixed defect: `poller.handle_task` routes any task id containing
  "operational" to `handle_operational_build()`, which returns a hardcoded status with no
  execution evidence. Left as-is because the umbrella id is not an `agent-` id, so re-routing it
  would immediately block the umbrella; it must not be read as evidence of executed work.
- Queue record reconciliation 2026-09-23T20:22:00Z:
  - `agent-live-queue-recovery-deepseek-2026-09-23`: terminal, `execution_error`, verdict
    interrupted by the bridge stream decoding failure; successor linkage recorded.
  - `agent-e3-integration-and-truth-reconciliation-2026-09-23`: orphaned running record with no
    worker and no terminal transition; moved to `blocked/` with evidence, implementation commits
    `617e69cb` and `aae7d036` preserved, completion deliberately not inferred from code existing.
  - `full-operational-build-2026-09-24`: still in `running/` as the umbrella task, annotated with
    the handler-truth finding above.
- Pending: `agent-codex-reset-revalidation-2026-09-23`, staged by commit `f80eefc8`
  (observed on origin/main at 2026-09-23T20:2xZ). `pending/` was empty when this
  recovery began; this recovery added no queue task of its own.

## Current blockers / owner dependencies

- E3 Stage 2 production enablement: standing conditional owner approval granted 2026-09-23 for
  local enablement only — it becomes actionable when the recorded readiness preconditions pass
  (production rehearsal is the currently unmet one). This recovery task did not enable Stage 2.
- Seven provider credentials / account readiness steps remain owner/provider dependent
- Codex CLI re-validation is now engineering work (allowance reset); no owner blocker unless the
  CLI itself requests login/account action
- Deployment architecture: intentionally deferred by owner until local operation is proven. The
  authority records laptop-primary + GitHub control plane + VPS watchdog/failover as the current
  owner *preference*, explicitly not a final architecture decision and not authorization for VPS
  cutover. This run did not choose or act on any architecture.
- VPS access/details are required before any real deployment/cutover, and cutover is not yet
  authorized

## Next non-blocked priority

1. `agent-codex-reset-revalidation-2026-09-23` — re-test the existing Codex CLI worker now that
   the allowance has reset: discover the real CLI path, prove non-interactive harmless execution
   and a harmless smoke, capture provider-returned usage if exposed, verify E2 linkage, and set
   routability truthfully without marking Codex QUALIFIED from smoke alone.
2. E3 shadow orchestration rejection/repair and executable rehearsal evidence — this is now the
   critical path: the standing conditional Stage 2 approval needs production rehearsal evidence
   before local enablement can be considered.
3. E4 checkpoint/failover and E5 convergence/safe-mode drill evidence on real execution paths.
4. Provider onboarding resumes immediately when owner-local credentials are supplied.
5. Local-first completion work (owner direction: make the system run perfectly locally before any
   deployment architecture choice); deployment preparation that needs no architecture decision or
   VPS access may proceed in parallel.

Do not fabricate qualification/provider evidence, and do not enable Stage 2 or choose a
deployment architecture without the readiness evidence and owner decisions recorded in the
authority file.
