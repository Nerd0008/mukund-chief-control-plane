# Current Company State

- Timestamp: 2026-09-23T21:11:52Z
- Latest evidence run: 2026-09-23T21:11:03Z at code SHA `6c19a01` (this run's commit)
- Evidence files:
  - `audits/evidence/2026-09-23T21-10-00Z-e3-production-execution-rehearsal/evidence.json` (+ `.md`,
    `deployment_check.json`) — **real worker execution** on the local E3 path
  - `audits/evidence/2026-09-23T21-11-03Z-e3-production-execution-leg-regression/evidence.json` (+ `.md`)
  - `audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-run/` — Stage-1 shadow rehearsal
    (simulated specialist outputs, isolation proof)
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

All numbers below come from one isolated run at 2026-09-23T21:11:03Z recorded by
`scripts/evidence_runner.py` at code SHA `6c19a01`. Each suite is one real subprocess with a
declared import root; counts are per suite and are not extrapolated.

- E1 executive brain runtime matrix: 32 collected / 32 passed / exit 0
- E2 governor + provider adapters: 45 collected / 45 passed / exit 0
- E3 baseline: 54 collected / 54 passed / exit 0
- E3 extended: 60 collected / 60 passed / exit 0
- E3 shadow orchestrator: 13 collected / 13 passed / exit 0
- E3 production rehearsal (Stage-1 path, isolation, E1/E2 boundary): 24 collected / 24 passed / exit 0
- E3 production execution leg (dispatch, verification gating, DAG/evidence persistence): 18 collected / 18 passed / exit 0
- E3 production execution rehearsal driver (stubbed providers, isolated DB): 10 collected / 10 passed / exit 0
- E4 resource continuity + E5 safe mode (combined suite): 37 collected / 37 passed / exit 0
- Remote queue (isolated suite): 30 collected / 30 passed / exit 0
- Single-run totals: 323 collected, 323 passed, 0 failed, 0 errors, 0 skipped across 10 suites

**Superseding baseline (2026-09-23T21:18:27Z, `scripts/evidence_runner.py --label
bridge-watchdog-validation`):** 11 suites, 335 collected / 335 passed / 0 failed / exit 0. The delta
is exactly the new isolated bridge suite `remote_queue/tests/test_bridge_watchdog.py` (12 collected /
12 passed / exit 0), added by the bridge-watchdog validation run below. Every other suite count is
unchanged. Evidence: `audits/evidence/2026-09-23T21-18-27Z-bridge-watchdog-validation/`.

Supersedes the 8-suite / 295-test figure at SHA `4ac1a22`. The delta is the two new E3 execution
suites (18 + 10 = 28) plus nothing else. Two intermediate runs of the same runner were executed
against uncommitted code while this run's changes were still being edited; they are preserved but
marked superseded under `audits/evidence/superseded/` (`…T21-08-55Z-…`,
`…T21-09-51Z-e3-production-execution-leg-regression`). The 21:11:03Z run at SHA `6c19a01` is the
authoritative figure.

### E3 status

- E3 Stage 1: ACTIVE
- E3 Stage 2 production enablement: **NOT ENABLED** — and, per the live task contract, *not to be
  enabled by this task regardless of outcome*.
  - The authority (`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`) records a standing
    conditional owner approval for **local-only** enablement. The live running task contract for
    `agent-e3-production-execution-leg-2026-09-23` was amended by the owner/coordinator at
    2026-09-23T21:04Z (`1ba7f43`) to read: *"Regardless of outcome, do not enable LOCAL Stage 2 or
    production dispatch; leave it disabled and record the exact remaining conditions for a separate
    owner-directed decision."* That newest instruction governs; the conditional approval was **not**
    exercised this run, so no readiness criterion was weakened and none was treated as satisfied by
    approval text.
  - Preconditions were nevertheless re-evaluated with evidence — see below.
- E3 orchestration DB: schema **v2** (live `orchestration.db` upgraded from v1 by the execution leg)
- Worker-capability states in the live store: none QUALIFIED (no qualification evidence exists)

### E3 production execution leg — BUILT AND EVIDENCED (this run)

The recorded unmet Stage 2 condition from the 2026-09-23 rehearsal was: *the orchestrator composes
planning/routing/assembly/integration/verification but has no dispatch step to a worker
`ExecutionAdapter`*. That leg now exists and has been exercised with **real workers**.

New/changed modules:

- `exec-brain/e3_execution.py` — `ExecutionAdapterRegistry` (dispatch is refused with
  `WorkerNotRoutable` unless the registry reports `routable=true`; a credential-missing worker is
  never called), `OrchestrationStore` (schema-v2 `dag_node` / `dag_state_event` /
  `performance_evidence` persistence) and `E3ProductionExecutor`
  (`READY → RUNNING → VERIFYING → COMPLETE`; a genuine verifier rejection moves the node to
  `REWORK` and re-dispatches; the node reaches `FAILED` when the repair budget is spent). **A node
  can only reach `COMPLETE` after a deterministic verification PASS**; a node with no configured
  deterministic test cases is `BLOCKED` without spending a provider call.
- `exec-brain/e3_shadow_orchestrator.py` — `orchestrate_and_execute()`: the full real-path pipeline
  (plan → decomposition review → route → context/permission compile → team assembly → **dispatch** →
  integrate real outputs → per-node verification → persist → escalate/replan).
- `exec-brain/e3_execution_rehearsal.py` — real-path rehearsal driver (bounded calls only).
- `exec-brain/e3_cli.py` — the `e3-*` CLI bindings (including `e3-execute`, which requires
  `--confirm` before it will spend provider quota).
- `scripts/deploy_e3_runtime.py` — deploys the E3 module set to the runtime root with a per-file
  backup, a SHA-256 manifest and a documented `--restore` path. No secret-bearing file is ever
  copied, and E1/E2-owned files are not touched (runtime `eb.py` receives only the one e3-*
  registration hook, with the pre-patch copy backed up).

Deployment verified directly (artifact `…e3-production-execution-rehearsal/deployment_check.json`):
all 29 required E3 modules present in `%LOCALAPPDATA%\hermes\exec-brain`, `missing_modules: []`,
and all ten `e3-*` bindings present (`e3-init`, `e3-register-workers`, `e3-status`, `e3-plan`,
`e3-route`, `e3-rationale`, `e3-trace`, `e3-why`, `e3-verify-db`, `e3-execute`). The local CLI drives
E3 (`eb.py e3-status`, `e3-plan`, `e3-verify-db`, `e3-execute` dry-run all verified in-run).

### Real-path rehearsal evidence (NEW — real worker execution)

Driver: `exec-brain/e3_execution_rehearsal.py`. Evidence:
`audits/evidence/2026-09-23T21-10-00Z-e3-production-execution-rehearsal/`.
Run as a real process from the deployed runtime root, writing to the live `orchestration.db` and
reporting E2 telemetry through the public `governor.record_request()` interface only.

Bounded real provider usage: **5 calls** (deepseek 3, openai/codex-cli 1, google 1). Provider-returned
usage was captured on 4 of them; the Codex CLI exposes none, recorded as null (never estimated).

| Scenario | Worker | Result | Detail |
|---|---|---|---|
| A — rejection → targeted repair → re-verification | deepseek-v41-flash | **COMPLETE** | Call 1 returned prose; the deterministic verifier **rejected** it (`expected READY-7391, got "I am the AI assistant executing this rehearsal leg…"`); the targeted repair re-dispatched with the plan's declared exact content; attempt 2 **PASSED**. Persisted transitions `READY→RUNNING→VERIFYING→REWORK→RUNNING→VERIFYING→COMPLETE`. E2 rows `obs-20260923-ce0dc42c`, `obs-20260923-83675c19` |
| B — first-pass deterministic PASS | deepseek-v41-flash | **COMPLETE** | One call; `READY→RUNNING→VERIFYING→COMPLETE`. E2 row `obs-20260923-0347c684` |
| C — Codex CLI dispatch | codex-cli | **COMPLETE** | One non-interactive `codex exec --json` call in a scratch working directory; provider `openai`; **served model identity UNKNOWN** (not exposed); usage not exposed. E2 row `obs-20260923-cb6aece9` |
| D — Google image dispatch | google-nano-banana-2 | **FAILED** | Real call, provider error `no_image_part_in_response`; provider usage shows 17 prompt tokens and **no** output tokens. Unresolved — see below. E2 row `obs-20260923-f0913024` |
| E — credential-missing worker refusal | mistral-small-4 | **BLOCKED (expected)** | Assignment refused with `worker_not_routable:mistral-small-4`; **zero** provider calls; adapter stub recorded 0 dispatches |

Persistence verified by reading the live store back after the run: 5 `dag_node` rows (4 `COMPLETE`/
`FAILED` + 1 `BLOCKED`), 20 `dag_state_event` rows, 4 `performance_evidence` rows
(`A: first_pass_success=0, final_success=1, retries=1, corrections=1`; `B`, `C: 1/1, 0 retries`;
`D: 0/0, failure_attribution=verification_fail`), and 5 new `observed_request` rows in `governor.db`
written through the public E2 interface. E1/E2 boundary static scan: **0** direct SQL writes to E1/E2
stores from any `exec-brain/*.py`.

### Unresolved: Google image worker real dispatch (D)

The Google image worker's real dispatch returned a candidate **without an inline image part**; the
provider reported 17 prompt tokens and no output tokens, so no image was produced or billed. The
adapter reported this honestly (`no_image_part_in_response`) and the deterministic verifier recorded
`FAIL`; no qualification or success was invented. Root cause is **not yet determined** (prompt
wording, `responseModalities` handling, or a provider-side block are all consistent with the
observed response). One earlier, separate smoke test of this adapter did produce a decodable
1024×1024 image, so the adapter itself is not known-broken. A single extra diagnostic call was
**not** spent, to respect the bounded-usage instruction; the executor now records `finish_reason`,
image mime/dims/size and `prompt_feedback` on every attempt so the next run is diagnosable from
evidence alone.

### Defects found and fixed this run

1. `gemini_adapter.report_usage_to_e2` reported `totalTokenCount` as *output* tokens whenever
   `candidatesTokenCount` was absent — i.e. it reported prompt+output as output. Observed on the
   failed image response above (17 prompt tokens recorded as 17 output tokens,
   `obs-20260923-f0913024`). Now reports the provider's candidate count only, or null. The historical
   row was left as written; it is a record of the defect, not corrected in place.
2. `e3_commands.init` printed a hardcoded `Schema version: 1`; it now reads the store's real version.
3. The rehearsal's runtime CLI-binding detector looked for the `e3-*` command names inside `eb.py`
   (they live in the deployed `e3_cli.py`, reached through one registration hook in `eb.py`) and so
   wrongly reported no bindings. Fixed, and re-checked without spending a provider call
   (`deployment_check.json`).

## Worker / provider state

Smoke readiness is not qualification; qualification is evidence-driven.

- Codex CLI: routable=true; executed on the real path this run (scenario C, COMPLETE); served model
  identity **UNKNOWN**; usage not exposed by the CLI; E2 linkage VERIFIED; qualification UNPROVEN
- DeepSeek (`deepseek-flash`): routable=true; executed on the real path this run (scenarios A and B,
  both COMPLETE); provider-returned usage captured; E2 linkage VERIFIED; qualification UNPROVEN
- Google image worker (`gemini-3.1-flash-image`): routable=true; **real dispatch failed this run**
  (scenario D, provider error, no image produced); E2 linkage row written (status `error`);
  qualification UNPROVEN
- Remaining seven generic API workers (Mistral Small 4, GLM-5.3 Flash, Qwen3.8-27B, LongCat 2.0,
  MiniMax M3, Step 3.7 Flash, Tencent Hunyuan Hy3): adapters exist; owner-local credentials and live
  readiness evidence outstanding; routable=false — and correctly refused by the execution leg
  (scenario E)

## Remote Task Queue

- Canonical GitHub task-data location: `remote-queue/`; implementation package: `remote_queue/`
- Bridge: implemented and remotely E2E-verified
- `agent-*` tasks are dispatched into the Hermes CLI through `remote_queue/hermes_dispatch.py`
- Queue tests are isolated (`remote_queue/tests/test_queue.py`: 30/30, exit 0)
- Scheduler: `HermesRemoteQueuePoller` registered and Ready (2-minute cadence)
- Recorded, deliberately unfixed defect: `poller.handle_task` routes any task id containing
  "operational" to `handle_operational_build()`, which returns a hardcoded status with no
  execution evidence. It must not be read as evidence of executed work.
- `full-operational-build-2026-09-24` remains the umbrella record in `running/` (no worker).
- This run: `agent-e3-production-execution-leg-2026-09-23` claimed and worked; one successor task
  staged in `remote-queue/pending/`.
- Bridge validation run `agent-bridge-watchdog-validation-2026-09-23` (2026-09-23T21:18Z, base SHA
  `07dd4a1`) verified the hardened bridge commits `617fd47c` and `b83c9ad` and found **no defect in
  the validated path**, so no production code was changed: no-stream watchdog (default 300s,
  `HERMES_REMOTE_IDLE_TIMEOUT`), PID-scoped child-tree termination, dispatch hard bound (default
  1200s, `HERMES_REMOTE_TASK_TIMEOUT`), watchdog exit code 124 surfaced as `execution_error` and never
  as completion, and `running/<task_id>.json` frozen as immutable input with standing conditional
  approvals respected. 12 new isolated bridge tests; 11 suites / 335 passed / exit 0. Evidence:
  `audits/evidence/2026-09-23T21-18-27Z-bridge-watchdog-validation/`.
- That run staged exactly one successor: `agent-e3-local-production-rehearsal-retry-2026-09-23`
  (pending) — the formal production-rehearsal re-run on the now-built execution leg, scoped not to
  race or duplicate the already-pending `agent-e3-image-diagnosis-and-multiworker-execution-2026-09-23`.
- Owner directive `a58549c` / `2d5f332` / `d7e718c` ("Owner directive update — 2026-09-23 late
  evening") arrived during this run: continue all independent local work overnight, do **not** enable
  local E3 Stage 2 overnight, and complete it only after Mukund configures all remaining provider
  credentials on 2026-09-24 and the readiness gates are re-run. Both staged/pending E3 contracts now
  carry that directive; Stage 2 remains disabled.

## Stage 2 readiness evaluation (precondition by precondition)

Recorded preconditions (authority owner-directive update + `full_build_tracker.md`). Evaluated for
evidence; **no precondition was skipped or weakened**, and Stage 2 remains disabled by direct owner
instruction irrespective of the results below.

| # | Precondition | Result | Evidence |
|---|---|---|---|
| 1 | E1/E2/E3/E4/E5 relevant regressions pass | MET | 10 suites, 323/323, exit 0, SHA `6c19a01` |
| 2 | Production rehearsal passes | **PARTIALLY MET** | the execution leg now runs real workers end-to-end (A, B, C COMPLETE with persisted DAG state, evidence rows and E2 linkage; refusal path proven); the Google image real dispatch **failed** (see unresolved) and the leg exercises single-node plans, not a multi-worker real plan |
| 3 | No unresolved critical integrity/privacy/safety defect | MET (in the E3 path) | nodes cannot complete without a verification PASS (18 tests assert this); refusal path spends no provider call; raw objectives are stored only as hashes; no raw provider content in the DAG/state log; E1/E2 boundary scan clean; 3 defects found and fixed |
| 4 | Worker routing/qualification state evidence-driven | MET | `routable` still derives from smoke PASS + E2 linkage; qualification remains UNPROVEN everywhere; the rehearsal used no QUALIFIED claim |
| 5 | Rollback/recovery available | MET | `scripts/deploy_e3_runtime.py` backs up every overwritten file with a SHA-256 manifest and a documented `--restore`; the pre-patch `eb.py` is backed up; the E3 store is separate from E1/E2 |
| 6 | State/evidence truthfully updated | MET | this file + `full_build_tracker.md` + the two evidence artifacts above |

**Exact remaining conditions (recorded, not resolved):**

1. **Direct owner instruction (governing):** the live task contract states Stage 2 / production
   dispatch must not be enabled by this task regardless of outcome. Enabling now requires a
   separate, explicit owner decision.
2. **Google image worker real dispatch fails** — provider returned no image part; root cause
   undetermined (unresolved, above).
3. **The real dispatch path has not been exercised on a decomposed multi-worker plan**; only
   single-node plans were dispatched, and the worker capability registry holds no QUALIFIED worker,
   so a multi-node real plan would currently assemble only if `EVALUATING` rows exist. No
   multi-worker real execution has been evidenced.
4. **Qualification evidence is still absent for every worker** (smoke readiness ≠ qualification), so
   routing still relies on `EVALUATING` state for low-risk work.

## Current blockers / owner dependencies

- E3 Stage 2 local enablement: **blocked by explicit current owner instruction** (not an engineering
  gap any more — the execution leg now exists and is evidenced).
- Google image worker real dispatch: unresolved provider-side failure (engineering, not owner action).
- Seven provider credentials / account readiness steps remain owner/provider dependent
- Deployment architecture: intentionally deferred by owner until local operation is proven. The
  authority records laptop-primary + GitHub control plane + VPS watchdog/failover as the current
  owner *preference*, explicitly not a final decision and not authorization for VPS cutover.
- VPS access/details required before any real deployment/cutover; cutover is not authorized

## Next non-blocked priority

1. Diagnose the Google image real-dispatch failure with one bounded call now that the executor
   records `finish_reason` / `prompt_feedback` / image metadata.
2. Exercise the real dispatch path on a **decomposed multi-worker plan** with deterministic
   verification per node.
3. Provide evidence toward capability qualification for the routable workers (cold-start benchmark
   harness) so routing stops depending on `EVALUATING`.
4. E4 checkpoint/failover and E5 convergence/safe-mode drill evidence on real execution paths
   (currently gated: the contract only asks for these if Stage 2 is enabled, which it is not).
5. Provider onboarding resumes immediately when owner-local credentials are supplied.
6. Local-first completion work (owner direction: prove local operation before any deployment
   architecture choice).

Do not fabricate qualification/provider evidence, and do not enable Stage 2 or choose a
deployment architecture without the readiness evidence and the owner decisions recorded in the
authority file.
