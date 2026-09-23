# Full-Build Tracker

Status: ACTIVE. Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`.

Evidence source for every test figure below (supersedes the 21:33:19Z run):
`audits/evidence/2026-09-23T21-53-37Z-e3-image-diagnosis-and-qualification/evidence.json`
(run 2026-09-23T21:53:37Z, code SHA `4da92eb`, 12 suites, 364 collected, 364 passed,
0 failed, 0 errors, 0 skipped, every suite exit 0). Delta vs the 21:33:19Z run (11 suites / 351):
exactly +1 suite / +13 tests — the new `exec-brain/tests/test_e3_qualification_evidence.py`.

Diagnosis + qualification evidence from the same task:
`audits/evidence/2026-09-23T21-49-21Z-e3-google-image-diagnosis/` (bounded Google image diagnosis,
exactly 1 real call, failure did NOT reproduce) and
`audits/evidence/2026-09-23T21-53-01Z-e3-qualification-from-evidence/` (evidence-backed worker
qualification, 0 provider calls; dry-run artifact at `…T21-52-00Z-…`).

Real-execution evidence (authoritative, supersedes 21:10:00Z):
`audits/evidence/2026-09-23T21-32-41Z-e3-production-execution-rehearsal/evidence.json`
(+ `evidence.md`) — **formal production-rehearsal re-run**: decomposed multi-worker real plan
(2 nodes / 2 distinct workers, per-node deterministic verification, rejection → repair →
re-verification, dependency-gated dispatch), isolation + contamination re-proof, E2 read-back;
7 bounded real provider calls. First attempt preserved (superseded) under
`audits/evidence/superseded/2026-09-23T21-31-09Z-e3-production-execution-rehearsal/`.

Earlier real-execution evidence (still valid, superseded as the authoritative run):
`audits/evidence/2026-09-23T21-10-00Z-e3-production-execution-rehearsal/evidence.json`
(+ `evidence.md`, `deployment_check.json`) — real worker execution on the local E3 path,
single-node plans only, 5 bounded provider calls.

Stage-1 shadow-rehearsal evidence (unchanged, still valid):
`audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-run/evidence.json`.

## Lane status

| Lane | Item | Status | Evidence |
|---|---|---|---|
| Queue bridge | Remote queue + `agent-*` dispatch to Hermes CLI | OPERATIONAL | queue.log pickups; `remote_queue/hermes_dispatch.py` |
| Queue bridge | Visible worker streaming | HARDENED | commit `e643fd162cf2b627d734b5735e205de3d00387a4` |
| Queue bridge | Queue test isolation | DONE | `remote_queue/tests/test_queue.py` — 30/30 pass |
| Queue bridge | Queue lifecycle defects | 4 FIXED, 1 RECORDED | see state/current_company_state.md §Remote Task Queue |
| E1 | Runtime + test matrix | VERIFIED | 32/32 pass, exit 0 |
| E2 | Governor + provider adapters | VERIFIED | 45/45 pass, exit 0 |
| E3 | Baseline suite | VERIFIED | 54/54 pass, exit 0 |
| E3 | Extended suite | VERIFIED | 60/60 pass, exit 0 |
| E3 | Shadow orchestrator composition | VERIFIED | 13/13 pass, exit 0 |
| E3 | Evidence-backed qualification harness | **NEW + VERIFIED** | 13/13 pass, exit 0 (`tests/test_e3_qualification_evidence.py`); derives qualification only from recorded `performance_evidence`; fixture harness can never return PASS |
| E3 | Production rehearsal (Stage-1 orchestration path) | EVIDENCED | 24/24 pass, exit 0; 5 executable scenarios incl. verifier rejection → targeted repair → re-verification PASS |
| E3 | **Production rehearsal on the real path (decomposed multi-worker plan)** | **EVIDENCED** | scenario F: planner-decomposed 2-node plan (builder/deepseek → integrator/codex-cli), per-node deterministic test case, rejection → REWORK → targeted repair → re-verify inside the plan, dependency-gated dispatch proven from the persisted state log; 7 bounded real calls total; `audits/evidence/2026-09-23T21-32-41Z-e3-production-execution-rehearsal/` |
| E3 | Simulation-evidence isolation | PROVEN (re-proven in-run) | fail-closed refusal on all three live stores; SHA-256 before/after identical incl. `-wal`/`-shm` sidecars; isolated sink outside the production root; live-store contamination check: 0 simulated/shadow rows |
| E3 | E1/E2 public-interface boundary | **VERIFIED** | static scan `clean: true` (0 direct SQL / 0 direct connections to E1/E2 stores from any `exec-brain/*.py`) + two clean `grep` runs; the re-run's 7 E2 rows read back **from the live `governor.db`** via `governor.record_request()` |
| E3 | **Production execution leg (orchestrator → worker adapter dispatch)** | **BUILT + EVIDENCED** | real dispatch to deepseek-v41-flash and codex-cli, all COMPLETE with persisted DAG/evidence rows and E2 linkage, single-node **and** decomposed multi-node plans; credential-missing worker refused with 0 provider calls; 22/22 + 22/22 tests |
| E3 | Deterministic verification gates COMPLETE | **ENFORCED** | a node reaches COMPLETE only after a verification PASS; no-test-case nodes are BLOCKED without a dispatch (asserted in `tests/test_e3_execution.py`) |
| E3 | E3 orchestration modules deployed to runtime root | **DONE** | 29/29 required modules present, `missing_modules: []` (`deployment_check.json`) |
| E3 | `e3-*` CLI bindings in runtime `eb.py` | **DONE** | all 10 bindings present; `eb.py e3-status` / `e3-plan` / `e3-verify-db` / `e3-execute` (dry run) verified in-run |
| E3 | Google image worker real dispatch | **INTERMITTENT (diagnosed, not settled)** | earlier call returned no image part (17 prompt / 0 output tokens); the bounded 21:49Z re-dispatch of the **identical** request returned a decodable 1024×1024 JPEG (finishReason STOP, inlineData:image/jpeg, 434365 bytes, candidate tokens 1383) with the deterministic verifier PASS. Trigger unknown; a bounded repeat series is required. Prompt-stated size (64×64) was not honoured |
| E3 | Real dispatch on a decomposed multi-worker plan | **EVIDENCED** | scenario F (21:32:41Z re-run): 2 nodes → 2 distinct routable workers, per-node deterministic verification, dependency gate ordered from the persisted log |
| E3 | Worker qualification evidence | **PARTIAL (evidence-backed)** | `EvidenceBackedBenchmark` + `scripts/e3_qualification_from_evidence.py`, 0 provider calls: codex-cli builder QUALIFIED (3/3/3), codex-cli integrator QUALIFIED (2/2/2), deepseek-v41-flash builder QUALIFIED (8/8/3), google-nano-banana-2 vision EVALUATING (2 recorded, 1 pass). `qualified_rows_without_evidence = 0`; the registry refuses a QUALIFIED row with zero evidence; the fixture harness can never produce a qualification |
| E3 | Stage 2 local production enablement | **NOT ENABLED (owner instruction)** | live contract `1ba7f43` + owner late-evening directive (`a58549c`/`2d5f332`/`d7e718c`): complete local Stage 2 only after the remaining provider credentials are configured on 2026-09-24 and the readiness gates are re-run; preconditions re-evaluated, none weakened |
| E3 | Truth defects found and fixed | 8 FIXED | gemini output-token mapping; `e3_commands` hardcoded schema version; rehearsal CLI-binding detector; `build_dag` positional dependency wiring; executor DAG-state sync; `e3-status`/`e3-verify-db` reading the oldest schema row; an unrequested optional rehearsal scenario reported as passing; (2026-09-23T21:53Z) the always-PASS synthetic cold-start benchmark, now structurally unable to produce a qualification |
| E4 | Resource continuity implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E4 | Checkpoint/failover drill evidence on real execution paths | OPEN | gated: the contract asks for this only if Stage 2 is enabled, which it is not |
| E5 | Safe mode / resilience implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E5 | Failure-drill evidence on real execution paths | OPEN | gated: same as E4 |
| Providers | DeepSeek (deepseek-flash) | ROUTABLE, REAL EXECUTION OK, QUALIFIED (builder) | real dispatch COMPLETE across scenarios A/B/F-node-1 (8 recorded execution rows); provider usage captured; E2 linkage verified; capability_registry builder 8 recorded / 8 verified passes / 3 first-pass |
| Providers | Codex CLI | ROUTABLE, REAL EXECUTION OK, QUALIFIED (builder + integrator) | real non-interactive dispatch COMPLETE; served model identity UNKNOWN; usage not exposed; capability_registry builder 3/3/3 and integrator 2/2/2 |
| Providers | Google image worker | ROUTABLE, REAL EXECUTION INTERMITTENT, EVALUATING (vision) | one identical request returned no image part, the next returned a decodable 1024×1024 JPEG; trigger unknown; 2 recorded executions, 1 verified pass — not qualified |
| Providers | 7 generic API workers | NOT READY (correctly refused) | routable=false; the execution leg refused a dispatch with 0 provider calls |
| Deployment | E3 module deployment to local runtime root | DONE | `scripts/deploy_e3_runtime.py`; per-file backup + SHA-256 manifest + `--restore` |
| Deployment | Architecture decision | DEFERRED BY OWNER | owner direction: prove local operation first; laptop-primary + GitHub control plane + VPS watchdog/failover is a recorded *preference*, not a final decision |
| Deployment | VPS access/details | NOT PROVIDED | owner dependency |
| Deployment | Non-architecture-dependent deployment preparation | PARTIAL | the deploy script + manifest give a reproducible local runtime procedure; no VPS work performed |

## Owner gates (must not be bypassed)

1. E3 Stage 2 **local** production enablement — **currently prohibited by direct owner instruction**
   (live contract `1ba7f43` plus the owner's late-evening directive `a58549c`/`2d5f332`/`d7e718c`):
   do not enable in this task regardless of outcome; complete local Stage 2 only after the remaining
   provider credentials are configured on 2026-09-24 and the full readiness gates are re-run. The
   older standing conditional approval is not exercised. **Not enabled.**
2. Deployment architecture choice and VPS cutover — deferred by owner until the local system is
   proven; the recorded laptop-primary preference is not a decision and cutover is not authorized.
3. Seven provider credentials provisioned locally (never via GitHub/queue/logs).
4. Anything irreversible or destructive.

## Known truth defects (recorded, not silently resolved)

- `poller.handle_task` routes any task id containing "operational" to
  `handle_operational_build()`, which returns a hardcoded status with no execution evidence.
  `full-operational-build-2026-09-24` therefore must not be read as evidence that its listed
  steps ran.
- The umbrella record remains in `running/` with no associated worker process.
- `.bridge-stash/` in the repository contains two py files tracked from an earlier bridge
  autostash; one (`safe_mode.py`) differs from the live `exec-brain/` version. Flagged for
  owner/coordinator decision on whether it should be removed.
- The E3 conflict handler reports the alphabetically-first differing common key for a node pair;
  detection is deterministic but the heuristic's precision is a known limitation.
- Historical row `obs-20260923-f0913024` in `governor.db` records 17 output tokens for a response
  that produced 0 output tokens (the `gemini_adapter` output-token mapping defect fixed this run).
  The row is left as written: it is the record of the defect, not a corrected measurement.
- The real-path rehearsal writes to the **live** `orchestration.db` and, through the public E2
  interface, to the live `governor.db`. That is intentional (it is the production path), unlike the
  Stage-1 shadow rehearsal, which is strictly isolated. It must not be read as a Stage-2 enablement.
- Four further truth defects were found and fixed in the 2026-09-23T21:32:41Z re-run (positional
  dependency wiring in `build_dag`; the executor not syncing DAG node state with the store;
  `e3-status`/`e3-verify-db` printing the oldest schema row; an unrequested optional rehearsal
  scenario reported as passing). They are recorded in `state/current_company_state.md`; the
  superseded artifact that exhibited the last one is preserved with its reason.
- **Latent truth hazard found and closed 2026-09-23T21:53Z:** the cold-start benchmark harness
  (`ColdStartBenchmark`) shipped four evaluation functions that returned placeholder strings and were
  therefore *always* recorded as `PASS`. Nothing used them to mark a real qualification, but a
  synthetic PASS is exactly the shape of an unearned qualification claim. The bundled fixture suite
  now marks every result `evidence_backed=False`, can never return `PASS`, and can never map to
  `QUALIFIED`; real qualification goes through `EvidenceBackedBenchmark`, which reads only recorded
  `performance_evidence` rows cross-checked against `dag_node`. Covered by 13 tests.
- **Recorded, deliberately unresolved:** the Google image no-image response is intermittent. The
  bounded re-dispatch of the identical request succeeded, so the failure could not be reproduced and
  its trigger is unknown. No stability claim is made and the vision role is **not** qualified. Its
  node row in `dag_node` reads `COMPLETE` because rehearsal node ids are reused and `dag_node` is
  upserted; the historical failure is still on record in `performance_evidence`
  (`evidence-53374aa1dde4`).
- **Recorded limitation:** the qualification evidence counts are `performance_evidence` rows, not
  distinct DAG nodes. Rehearsal plans reuse node ids, so several rows can share a `dag_node_id`
  (e.g. codex-cli builder: 3 rows, 1 distinct DAG node). Both figures are reported in the artifact so
  the strength of the evidence is visible.

## Next bounded task

Staged in `remote-queue/pending/` by
`agent-e3-image-diagnosis-and-multiworker-execution-2026-09-23`:
`agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23` — a strictly bounded repeat
series to measure how often the no-image response recurs, a controlled comparison of the image
request shape, the truth about whether a requested image size can be honoured, and then a re-run of
the evidence-backed qualification for the vision role. Budget must be stated up front; no stability
claim may be made that the series does not support.

Already pending and NOT duplicated or replaced:

- `agent-e3-stage2-readiness-gate-rerun-2026-09-24` — after the owner configures the remaining
  provider credentials on 2026-09-24, verify what is configured, re-run the full local Stage 2
  readiness gate with executable evidence, and enable **LOCAL** Stage 2 only if the credentials are
  confirmed configured AND every readiness criterion is objectively satisfied by that run's evidence
  AND the authority records explicit owner authorization for the enablement step; otherwise leave it
  disabled and record the exact remaining condition. It consumes this run's diagnosis and
  qualification results (an additive `state_update_2026_09_23T2153Z` note was recorded in its staged
  contract) and must not repeat the multi-worker rehearsal. Stage 2 remains **NOT ENABLED**.
- `agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23` — E4/E5 drill harnesses.

No pending task was found to be equivalent to the intermittency/protocol successor, so exactly one
new task was staged.
