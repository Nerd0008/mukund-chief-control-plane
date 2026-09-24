# Full-Build Tracker

Status: ACTIVE. Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`.

Evidence source for every test figure below (supersedes the 22:40:55Z run):
`audits/evidence/2026-09-23T22-52-48Z-e3-stage2-readiness-gate-rerun/evidence.json`
(run 2026-09-23T22:52:48Z, code SHA `342ee66`, 12 suites, 364 collected, 364 passed,
0 failed, 0 errors, 0 skipped, every suite exit 0). Prior source:
`audits/evidence/2026-09-23T22-40-55Z-e3-stage2-readiness-gate-rerun/evidence.json`.

Regression evidence source for the E4/E5 drill work is **newer** and supersedes the figures
above where they differ:
`audits/evidence/2026-09-23T23-55-09Z-e4e5-real-path-drills/evidence.json`
(run 2026-09-23T23:55:09Z, code SHA `bd0a7aa`, **15 suites, 438 collected / 438 passed, 0 failed,
0 errors, 0 skipped, every suite exit 0**) — the 22:52Z run predates two suites
(`test_e4e5_drills.py` 38 tests, `remote_queue/tests/test_console_quickedit.py` 12 tests) and the
`test_worker_retry.py` suite (24 tests) that are present now. An intermediate regression run
(23:51:09Z) failed the E1 suite on a directory-hygiene assertion because that revision of the drill
harness opened the live WAL store; it is preserved (with its reason) under
`audits/evidence/superseded/2026-09-23T23-51-09Z-e4e5-real-path-drills-superseded-by-final-drill-run/`.

E3 Stage 2 readiness gate verdict (2026-09-23T22:53:53Z, credential-triggered retry, 0
provider calls): `audits/evidence/2026-09-23T22-53-53Z-e3-stage2-readiness-gate-verdict/` — Stage 2
**NOT ENABLED** (credentials still 0/7 configured; Google image worker intermittency unresolved;
owner authorization conditional on the credentials). Previous verdicts: 2026-09-23T22:41:57Z and
2026-09-23T22:37:29Z.
Superseded gate intermediates preserved under `audits/evidence/superseded/`.

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
| E3 | Stage 2 local production enablement | **NOT ENABLED (gate re-run 2026-09-23T22:53Z, credential-triggered retry)** | deterministic readiness gate `scripts/e3_stage2_readiness_gate.py` (0 provider calls): regressions 12 suites/364 pass, real-path rehearsal consumed (0 failed checks), isolation+boundary+rollback MET, qualification evidence-driven — but (a) **0/7 provider credentials configured (presence-only probe, re-confirmed 22:52Z with two independent probes; `newly_configured_workers=[]`)**, (b) Google image worker intermittency unresolved, (c) owner authorization conditional on (a). Exact remaining conditions recorded in `audits/evidence/2026-09-23T22-53-53Z-e3-stage2-readiness-gate-verdict/` |
| E3 | Truth defects found and fixed | 8 FIXED | gemini output-token mapping; `e3_commands` hardcoded schema version; rehearsal CLI-binding detector; `build_dag` positional dependency wiring; executor DAG-state sync; `e3-status`/`e3-verify-db` reading the oldest schema row; an unrequested optional rehearsal scenario reported as passing; (2026-09-23T21:53Z) the always-PASS synthetic cold-start benchmark, now structurally unable to produce a qualification |
| E4 | Resource continuity implementation | PRESENT, unit-tested | 37/37 combined suite + 38/38 drill suite |
| E4 | Checkpoint/failover drill evidence (stubbed provider failures, isolated db) | **EVIDENCED 33/33 checks** | `exec-brain/e4e5_drill_harness.py` D1/D2 — checkpoint created + restored byte-identical, equivalent-worker failover (deepseek-v41-flash → codex-cli, both QUALIFIED in the *live* registry read via a snapshot copy), handover objective carrying the restored checkpoint delivered to the replacement adapter, replacement COMPLETE only after a verification PASS, **no** equivalent → owner escalation with the quality floor NOT lowered; 0 real provider calls, live stores byte-identical; `audits/evidence/2026-09-23T23-55-06Z-e4e5-real-path-drill-harness/` |
| E4 | Checkpoint/failover drill on the **live provider** path | OWNER-GATED (afternoon checklist) | needs Stage 2 + provider credentials; exact steps recorded in `tasks-or-issues/overnight-owner-actions-2026-09-24.md` §8 |
| E5 | Safe mode / resilience implementation | PRESENT, unit-tested | 37/37 combined suite + 38/38 drill suite |
| E5 | Failure-drill evidence (stubbed provider failures, isolated db) | **EVIDENCED 33/33 checks** | D3/D4/D5/D6 — provider outage reported *and* raised → node FAILED with the error verbatim, no failover claimed; malformed output rejected by the deterministic verifier, repair path converges to a verified COMPLETE; convergence cap bounded (exactly 3 dispatches, no 4th, quarantine + escalated convergence event); safe-mode entry persisted; owner-override audit (owner-only trigger not auto-resolved), recovery refused without an override and when the probe is unhealthy, recovery succeeds after override → NORMAL with 0 active events; same evidence dir |
| E5 | Owner override UX + recovery path | **BUILT + EVIDENCED** | `safe_mode.SafeModeRecovery` + `safe_mode.record_owner_override` (writes `safe_mode_event` **and** `decision_rationale_event` with `decision_actor='owner'`); recovery requires a healthy probe AND a recorded override for owner-only triggers |
| Providers | DeepSeek (deepseek-flash) | ROUTABLE, REAL EXECUTION OK, QUALIFIED (builder) | real dispatch COMPLETE across scenarios A/B/F-node-1 (8 recorded execution rows); provider usage captured; E2 linkage verified; capability_registry builder 8 recorded / 8 verified passes / 3 first-pass |
| Providers | Codex CLI | ROUTABLE, REAL EXECUTION OK, QUALIFIED (builder + integrator) | real non-interactive dispatch COMPLETE; served model identity UNKNOWN; usage not exposed; capability_registry builder 3/3/3 and integrator 2/2/2 |
| Providers | Google image worker | ROUTABLE, REAL EXECUTION INTERMITTENT, EVALUATING (vision) | one identical request returned no image part, the next returned a decodable 1024×1024 JPEG; trigger unknown; 2 recorded executions, 1 verified pass — not qualified |
| Providers | 7 generic API workers | NOT READY (correctly refused) | routable=false; the execution leg refused a dispatch with 0 provider calls |
| Deployment | E3 module deployment to local runtime root | DONE | `scripts/deploy_e3_runtime.py`; per-file backup + SHA-256 manifest + `--restore` |
| Deployment | Architecture decision | DEFERRED BY OWNER | owner direction: prove local operation first; laptop-primary + GitHub control plane + VPS watchdog/failover is a recorded *preference*, not a final decision |
| Deployment | VPS access/details | NOT PROVIDED | owner dependency |
| Deployment | Non-architecture-dependent deployment preparation | PARTIAL | the deploy script + manifest give a reproducible local runtime procedure; no VPS work performed |

## E4/E5 real-path drill harness + readiness (2026-09-24T23:55Z)

Task `agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23`. Evidence:
`audits/evidence/2026-09-23T23-55-06Z-e4e5-real-path-drill-harness/` (`evidence.json` +
`evidence.md`) and the regression bundle
`audits/evidence/2026-09-23T23-55-09Z-e4e5-real-path-drills/`.

The harness (`exec-brain/e4e5_drill_harness.py`) drives the **real** execution abstractions —
`E3ProductionExecutor`, `ExecutionAdapterRegistry`, `OrchestrationStore` (schema v2),
`CapabilityRegistry`, `EquivalentFailover`, `CheckpointManager`, `SafeModeManager`,
`ConvergenceEnforcer`, `MalformedOutputHandler`, `SafeModeRecovery` — against a disposable,
isolated schema-v2 DB, with provider transport replaced by a recorded in-process stub.

| Drill | What is evidenced | Result |
|---|---|---|
| D1 checkpoint → equivalent failover → state handover | checkpoint created and restored byte-identical; primary worker (`deepseek-v41-flash`) FAILED with the injected outage recorded verbatim; equivalence selected from a **snapshot copy of the live registry** (`codex-cli`, both QUALIFIED for `code`/`builder`); replacement dispatched with the restored checkpoint in its objective and reached `COMPLETE` only after a deterministic verification PASS; persisted state log shows the failed cycle then the replacement cycle on the same node | PASS |
| D2 no equivalent worker → owner escalation | registry queried truthfully returns `None` for role `verifier`; owner escalation recorded (`no_qualified_worker`, `OWNER_APPROVAL_REQUIRED`) in `decision_rationale_event`; **quality floor not lowered** | PASS |
| D3 provider outage | reported provider error (`HTTP 503`) and raised transport error both leave the node `FAILED` with the error verbatim, evidence row written; no node reaches `COMPLETE`; **no failover claimed** | PASS |
| D4 malformed output | the shallow structural pre-check flags None/empty/missing-field output and is explicitly recorded as *not* the authority (it passes a non-empty garbage string); the independent deterministic verifier rejects the malformed output; with a repair budget the node converges to a verified `COMPLETE` via `REWORK` | PASS |
| D5 repeated-failure convergence cap | the loop terminates exactly at the cap (3 dispatches, no 4th) with one stop marker; convergence events escalate to `quarantine_worker`; the system enters `DEGRADED` then `SAFE_MODE` | PASS |
| D6 safe-mode entry, owner override, recovery | safe-mode event persisted; recovery **refused** while an owner-only trigger is active without an override and **refused** when the health probe is unhealthy; `record_owner_override` writes both the safe-mode event and a `decision_actor='owner'` rationale row; recovery then succeeds → `NORMAL`, 0 active events; owner-only triggers are resolved with `auto_resolved=0` | PASS |

Truth boundaries recorded in the artifact, not glossed over:

- `evidence_kind = "stubbed_provider_failure"`, `real_provider_calls = 0`. These drills evidence
  **our** handling of injected failures on the real code path; they are **not** real external
  provider evidence and no failover success on a real provider is claimed.
- The failover equivalence rows are a **labelled fixture** written only into the disposable drill DB
  (`capability_fixture.kind = "drill_fixture_not_qualification_evidence"`). No live capability or
  qualification store is written; the live registry is read only through a snapshot copy.
- The recovery health probe is a labelled local stub (drill-DB `integrity_check`), recorded as
  `provider_health_verified = false`. Real provider-health re-verification before leaving safe mode
  on the live system stays owner-gated.
- Isolation is machine-checked: SHA-256 of `orchestration.db`, `governor.db`, `exec_brain.db` and
  their `-wal`/`-shm` sidecars before vs after → **unchanged**; 0 live E2 rows written (the stub E2
  ids are labelled `e2-stub-*`).
- Stage 2 is **not** enabled and nothing was deployed.

Owner-gated remainder (exact checklist in `tasks-or-issues/overnight-owner-actions-2026-09-24.md`
§8): re-run the same harness on the **live** provider path with real workers once Stage 2 and the
provider credentials exist, and confirm a real provider outage → real equivalent-worker failover.

## Owner gates (must not be bypassed)

1. E3 Stage 2 **local** production enablement — **NOT ENABLED** (deterministic gate re-run
   2026-09-23T22:53Z, credential-triggered retry; previous verdicts 22:41Z and 22:37Z). The gate fails
   all three conditions: (a) 0/7 provider credentials configured (presence-only probe re-confirmed at
   22:52Z by two independent probes; no new credential appeared), (b) Google image worker intermittency
   unresolved, (c) owner authorization conditional on (a). Owner's late-evening directive
   (`a58549c`/`2d5f332`/`d7e718c`): complete local Stage 2 only after the remaining provider
   credentials are configured on 2026-09-24 and the full readiness gates are re-run. The older standing
   conditional approval is not exercised.
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
- **Found and fixed 2026-09-24T23:5xZ (E4/E5 drill work):** (1) `OrchestrationStore.connect()`
  discarded the connection `init_db()` returned, leaking one SQLite file handle per store connect
  and keeping the store DB open/locked on Windows after `close()` — now closed explicitly
  (`exec-brain/e3_execution.py`). (2) The first revision of the drill harness opened the **live**
  runtime `orchestration.db` read-only for its registry grounding read, which created stray
  `orchestration.db-shm` / `-wal` sidecars in the deployed runtime directory and broke the E1
  `test_t13_no_gateway_modification` directory-hygiene assertion. The harness now reads a scratch
  **snapshot copy** and never opens the live file; the stray sidecars were removed (the live store's
  own mtime was unchanged, so no data was written or lost) and the failing suite passes again. Both
  facts and the superseded intermediate regression bundle are preserved under
  `audits/evidence/superseded/2026-09-23T23-51-09Z-e4e5-real-path-drills-superseded-by-final-drill-run/`.
- **Recorded limitation (E5 malformed-output handling):** `MalformedOutputHandler.validate_output`
  is a shallow structural pre-check. It flags `None`, an empty string and a dict missing a required
  field, but it **passes** a non-empty garbage string. The authority for contract conformance is the
  independent deterministic verifier. The drill records both facts and asserts the verifier
  rejection, so the pre-check is never read as the decision.

## Non-E3 runtime services + Company Registry audit (2026-09-23T22:35Z)

New worker: `scripts/company_inventory.py` (roster A20 — Company Registry / system inventory,
deterministic, read-only). Evidence:
`audits/evidence/2026-09-23T22-30-00Z-company-registry-gap-audit/`.

| Lane | Item | Status | Evidence |
|---|---|---|---|
| Registry | Roster reconciliation | **DONE — 0 gaps** | 50/50 roster items mapped; 7/7 owned scheduled tasks mapped; `inventory.json` |
| Registry | Company Registry access | VERIFIED | skill `personal/mukund-company-registry` + 6 references readable |
| Registry | Legacy donor systems | RECORDED, NOT TOUCHED | July Chief / Mukund OS / new custom Chief / Career Ops install all exist; superseded task `Mukund Chief of Staff` recorded as donor |
| Ops | Hermes Chief / gateway | LIVE | `gateway_state.json`: running, discord connected, 22:23:02Z |
| Ops | Discord archive sync | GREEN | `sync.log` last 8 runs `ok`; last publish 21:06:04Z (8 published, 0 rejected) |
| Ops | Remote queue poller | WORKING | 2-min cadence, queue-log pickups, claimed this task 22:22:06Z; last result `0x800710E0` recorded, meaning unresolved |
| Ops | E1 / E2 / E3 integrity gates | PASS | `audit --verify`, `gov-verify`, `e3-verify-db` (schema v2) |
| Ops | A04 Daily Resource Brief | WORKS | `eb brief` deterministic; unknown dimensions stay UNKNOWN |
| Ops | Boot persistence | PARTIAL / UNVERIFIED | gateway at logon + restart-on-failure; poller + sync sync have no logon/boot trigger and no `StartWhenAvailable` — post-reboot resumption unverified (reboot prohibited) |
| Career | Scheduled regional scan defect | **FOUND + FIXED + LIVE-CONFIRMED** | `ChiefCareerScan-UK` exited 1 after a successful scan (`UnicodeEncodeError` on cp1252 stdout); `emit()` hardened + `run_scheduled_scan.cmd` sets UTF-8; `career-ops/tests/test_emit_encoding.py` 5 tests; suite 33/33; real Task Scheduler re-run 2026-09-23T22:28:39Z → Last Result 0, valid JSON stdout, 89.0 s dry-run, 0 tracker writes |
| Career | B07/B08 tracker interface | **PRESERVED + COMMITTED + TESTED** | `career-ops/career_ops_cli.py` + `tracker_writer.py` (33 tests) were untracked; committed at `70dd715` and still green |
| Career | B09 Monthly rollover worker | **BUILT + EVIDENCED 2026-09-24** | `career-ops/tracker_rollover.py`; 32 new tests; acceptance on copies at `audits/evidence/2026-09-24T02-04-31Z-career-ops-monthly-rollover/` |

## Next bounded task

Staged in `remote-queue/pending/` by
`agent-e3-content-stop-operator-surface-and-rehearsal-integration-2026-09-24` (this task):
`agent-e4-provider-content-stop-pressure-visibility-2026-09-24` — surface the *recorded* provider
content-side stop pressure (per worker/provider/model: attempts, stops, rate with its sample size,
last finishReason, and a bounded "content withheld at a measurable rate" flag) through the E4 /
operator-facing resource-continuity status, using rows already on disk only. It is an observation,
not an action: no automatic failover or re-dispatch, no gate weakened, no provider call spent, and it
does not pre-empt the pending whole-company acceptance.

Closed / consumed since the previous staging (deliberately NOT re-staged):

- the credential-triggered Stage-2 gate re-check chain (`…-after-provider-keys-retry*`) is
  **parked**: the 2026-09-23T22:52Z presence probe found **0/7** provider credentials configured, so
  Stage 2 remains **NOT ENABLED**, and `agent-blocked-work-final-reconciliation-2026-09-24`
  classified the retry records as deterministic owner/external blockers with the duplicate retry
  chain closed. A further credential-triggered re-check is intentionally not staged; the owner
  configures a key and the deterministic readiness gate is re-run on demand.

Already pending and NOT duplicated or replaced:

- `agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23` — a strictly bounded
  repeat series to measure how often the no-image response recurs, a controlled comparison of the
  image request shape, the truth about whether a requested image size can be honoured, and then a
  re-run of the evidence-backed qualification for the vision role.
- `agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23` — **CONSUMED 2026-09-24T23:55Z**
  (this task). The E4/E5 drill harnesses are built and evidenced (33/33 checks, 0 real provider
  calls, live stores byte-identical) and the harness is registered in the regression runner. The
  only part that remains is the owner-gated **live** drill against real providers, which requires
  Stage 2 plus the provider credentials — recorded as an exact afternoon checklist item in
  `tasks-or-issues/overnight-owner-actions-2026-09-24.md` §8. No successor task was staged: staging
  another `agent-e4e5-*` task now would duplicate work rather than advance it.
- `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23` — final acceptance sweep and
  handover narrative.

Three gate contracts are now **executed** — `agent-e3-stage2-readiness-gate-rerun-2026-09-24` (verdict
2026-09-23T22:37Z), `agent-e3-stage2-readiness-gate-after-provider-keys-2026-09-24` (verdict
2026-09-23T22:41:57Z) and `agent-e3-stage2-readiness-gate-after-provider-keys-retry-2026-09-24`
(verdict 2026-09-23T22:53:53Z) — all three returned Stage 2 NOT ENABLED (0/7 credentials; the retry's
presence probe at 22:52Z also found 0/7). No pending task was found equivalent to the credential-
triggered successor, so exactly one new task was staged.

## CV / cover-letter + minimal LinkedIn workflow (2026-09-24T23:40Z)

Task `agent-cv-cover-letter-linkedin-workflows-2026-09-23`. Both remaining v1 company-workflow lanes
are now implemented, wired to Career Ops job state, and acceptance-evidenced locally. Existing Career
Ops tooling was reused, not rebuilt: the install's own `verify-cv-facts.mjs` is the fact gate, its
own `generate-cover-letter.mjs` `buildHtml` is the cover-letter renderer, and
`company_watch.build_shared_dedupe` / `dedupe_decision` are the dedupe engine.

| Lane | Item | Status | Evidence |
|---|---|---|---|
| CV/cover-letter | Connect existing CV workflow to Career Ops job state | **DONE** | `career-ops/cv_workflow.py`; `job-context` resolves a job from the canonical workbook, `data/pipeline.md` or a handed-over signal record |
| CV/cover-letter | Job-description input → tailored drafts, with provenance | **DONE** | `career-ops/cv_workflow.py` `draft`; `cv_draft.md` + `cv_draft_provenance.json` + `cover_letter_payload.json` |
| CV/cover-letter | No invented experience/metrics/certifications/visa | **ENFORCED** | Deterministic **reordering only** (no rewrite); the install's own fact gate must not return `block`; a blocked draft produces no HTML. Tests prove the gate catches a fabricated metric (`94772 users` → block) and a disavowed employer (`Apollo Clinic` → block) |
| CV/cover-letter | Cover-letter rendering through the existing engine | **DONE (HTML only)** | `career-ops/cv_render_cover.mjs` → install `buildHtml` + `verifyFacts`; **PDF rendering not performed** (headless Chromium; owner-gated) |
| CV/cover-letter | LLM tailoring path | **WIRED, NOT EXECUTED** | `openai-tailor.mjs` request record emitted with `executed: false` (sends cv.md + JD off-machine; owner-gated) |
| LinkedIn | Read-only job/discovery signal intake | **DONE** | `career-ops/linkedin_workflow.py` `intake`; `.json/.jsonl/.csv/.md/.txt`; URL-less lines reported `unclassified`, never guessed |
| LinkedIn | Profile/post/outreach drafting assistance | **DONE (unsent)** | `draft` → `draft_unsent` drafts, each fact-gated, each with `cv.md` line refs |
| LinkedIn | Handoff into Career Ops/company tracking | **DONE** | `handoff` → shared writer, dry-run by default, provenance into a non-owner column |
| LinkedIn | Dedupe vs Career Ops **and** Company Watch | **DONE** | canonical workbook + cross-month ledger + Company Watch registry names + Company Watch handoff manifests + same-batch merge |
| LinkedIn | Draft/read-only — no post/message/connect/apply | **ENFORCED** | `guard` refuses and logs every external action; module imports no network/browser library (asserted by test); read-only contract `network_used=false`, `urls_fetched=0`, `browser_launched=false`, `account_mutations=0` |
| Acceptance | Representative end-to-end local path | **PASS 23/23** | `python career-ops/run_cv_linkedin_acceptance.py` → `audits/evidence/20260923T234310Z-cv-linkedin-workflows/` (run on the final committed code; the earlier `20260923T234013Z` bundle is preserved as the historical run) |
| Tests | New suites | **PASS** | `career-ops/tests/test_cv_workflow.py` 21 passed; `career-ops/tests/test_linkedin_workflow.py` 34 passed; whole `career-ops/tests/` 88 passed; `company-watch/tests/` 31 passed |
| Regression | Whole-repo evidence runner | **PASS** | `python scripts/evidence_runner.py --label cv-linkedin-workflows` → `audits/evidence/2026-09-23T23-40-25Z-cv-linkedin-workflows/` — **14/14 suites pass, 400 collected / 400 passed, 0 failed, 0 errors, 0 skipped**, every suite exit 0, code SHA `b2ed978` |

Acceptance path proven (all local, fixture + owner-owned data): Career Ops job record (Crown Agents
Bank — Information Security Analyst, from the real `data/pipeline.md`) → tailored CV draft + cover
letter, fact gate **pass** for both, HTML rendered by the install's renderer with no browser → LinkedIn
intake 10 signals (6 job / 4 company / 3 unclassified) → dedupe (3 new, 1 same-posting merge, 2 blocked
by the owner's own filters) → LinkedIn drafts 6 (1 profile, 4 post, 1 outreach; gate **pass**, all
`draft_unsent`) → handoff applied to a **dated copy** with a hash-verified backup, provenance written to
non-owner column `Q`, append verified, **canonical workbook hash unchanged** → replay deduped → rollback
hash-verified → Chief summary produced.

Recorded limitations (truthful): the job description used by the acceptance run is an explicitly
labelled **synthetic fixture**, not a live vacancy, and no vacancy is claimed live; PDF cover letters are
not produced; LinkedIn intake consumes owner-exported local files only (no LinkedIn account/API access
exists, so the live LinkedIn surface is **owner-gated** and untested against the real account).

Successor task: **no new task staged** — the allowed scope requires exactly one successor
`agent-*` whole-company acceptance task "unless an equivalent task already exists", and
`agent-whole-company-local-acceptance-and-morning-handover-2026-09-23` (pending) already covers the
whole-company local acceptance test and morning handover. Its scope already lists "LinkedIn
draft/read-only path" and "CV/cover-letter path", so staging another would duplicate it.

## Regional job-search workers + scheduled execution (2026-09-24T00:14Z)

Task `agent-regional-job-search-agents-and-schedulers-2026-09-23` (attempt 2; attempt 1 landed this
work but was cut off by a 1200 s dispatch timeout before it could update state/commit). One
implementation, four regions — no per-region codebase forks.
Acceptance evidence: `career-ops/evidence/acceptance-20260924T001500Z.json`.

| Lane | Item | Status | Evidence |
|---|---|---|---|
| Regional | Four regions on one shared scanner/dedupe implementation | **DONE** | `career-ops/regional_job_search.py` (sha256 `962d38a9…`); dedupe, workbook index, cross-month index and write path all reused from `tracker_writer.py` |
| Regional | Dubai / Japan / Singapore lane configs | **DONE** | `career-ops/lanes/{dubai,japan,singapore}/{portals.yml,pipeline.md,scan-history.tsv}` — held in the control plane so the owner's Career Ops install is **never modified**; `resolve_lane` reports all four regions `ready: true` |
| Regional | Explicit eligibility/work-authorisation/location filter | **DONE** | `career-ops/regional_policy.json` (sha256 `ed045010…`) + `evaluate_record`: owner title policy, region location scope mirroring the scanner's tier order, clearance/citizenship policy from `config/profile.yml`, multi-year-experience rejection, mandatory-URL rule, **fail-closed** when no region scope resolves |
| Regional | Owner facts never invented | **ENFORCED** | UK authorisation `authorised` (Graduate visa → 2027-12-23, from `config/profile.yml`); Dubai/UAE, Japan, Singapore are **UNKNOWN** and every accepted record carries the region tracker's own `visa_pathway` text (`Visa unknown` / `JAPAN WORK VISA UNKNOWN` / `WORK PASS UNKNOWN`) plus an UNKNOWN flag. No right to work is inferred for those regions |
| Regional | Deterministic scheduled execution | **REGISTERED** | `ChiefCareerScan-UK` 23:45, `-Dubai` 23:50, `-Japan` 23:55, `-Singapore` 00:00 — all four `Ready` via `install_schedules.py --status`; staggered, bounded **dry-run only**, never writes a tracker, never submits |
| Regional | Run-health + idempotency metadata | **DONE** | `runtime/career-ops/scan-runs/regional-run-state.json` keys each run by a SHA-256 of its accepted candidate set; a replay marks candidates `duplicate-prior-run` and emits an empty manifest; the shared writer independently refuses anything already in the workbook / rotated workbook / cross-month ledger |
| Regional | No fabricated jobs | **ENFORCED** | Dry-run "New offers:" lines carry no URL, so they are reported `scan_offers_without_url` and can never become tracker rows on their own — only URL-bearing candidates can be accepted |
| Regional | Bounded dry-run evidence, all four regions | **PASS** | Two run-all passes 2026-09-24T00:06–00:19Z; UK 93 candidates, Dubai/Japan/Singapore 0 candidates; every region `last_status: ok`, `last_would_append: 0` |
| Regional | Safe workbook-write acceptance | **PASS** | Acceptance written to a **test copy** with a hash-verified pre-write backup, 2 labelled probe rows (`NOT A REAL VACANCY`, reserved `.invalid` domain), append verified, verification clean, then rolled back to the pre-write hash (`equals_pre_write_hash: true`) |
| Regional | Canonical trackers untouched | **VERIFIED** | All four canonical workbook hashes re-read at 2026-09-24T00:20Z and **identical** to the acceptance record: UK `84c53dcb…`, Dubai `495edb45…`, Japan `a8c4ef90…`, Singapore `25c7b95b…`. `applications_submitted: 0`, `external_messages_sent: 0` |
| Regional | Tests | **PASS** | `career-ops/tests/test_regional_job_search.py` **32 passed**; whole `career-ops/tests/` **120 passed** |
| Regional | Provider coverage stated honestly | **RECORDED** | Singapore is the only region with first-party providers in the install (MyCareersFuture, Glints SG, Jobstreet/SEEK `SG-Main`). **No UAE or Japan provider exists**, so those lanes run the global/remote boards under their region scope plus the region's `search_queries` agent-driven source list; a thin Dubai/Japan scan means "no provider for that region", never "no vacancies there" |

Owner action required (recorded, does not block the other lanes): `tasks-or-issues/overnight-owner-actions-2026-09-24.md`
item 6 — state the Dubai/UAE, Japan and Singapore work-authorisation position, because every record
produced for those regions is labelled UNKNOWN until the owner says otherwise; item 7 — decide whether
to add a UAE/Japan-specific provider or accept the agent-driven `search_queries` path.

## Job intelligence + application pack: JobBrief, research brief, reviewer, submission gate (2026-09-24T00:50Z)

Task `agent-job-intelligence-and-application-pack-2026-09-23` (roster B13, B14, B17, B18).
Acceptance evidence: `audits/evidence/2026-09-24T00-50-49Z-job-intelligence-and-application-pack/`
(`acceptance.json` + `acceptance.md`). Two earlier runs of the same runner are preserved under
`audits/evidence/superseded/`: the 00-44-06Z run predates the reviewer single-line-comment fix,
and the 00-46-02Z run predates the `job_intelligence` CLI input/output flag fix below.

| Lane | Item | Status | Evidence |
|---|---|---|---|
| B13 | Structured JobBrief schema | **DONE** | `career-ops/job_brief_schema.json` (JSON Schema, required keys + per-bucket `source_line`); `validate_brief()` enforces it and `brief` exits non-zero if it fails |
| B13 | Extractive JD analysis, no invention | **ENFORCED** | every requirement/responsibility/eligibility line is a verbatim posting line with its 1-based `source_line`; acceptance re-checks each cited line against the posting file (0 mismatches) |
| B13 | Preferences are never facts | **ENFORCED** | desirable/preferred lines (section or inline marker) carry `kind: "desirable"` and are mirrored into `preferences` with an explicit note; the acceptance asserts the desirable set and the essential set are disjoint and that `Location:`/`Right to work:` lines never enter the requirements bucket; a 5/4 essential/desirable split is asserted |
| B13 | No candidate claim can enter the brief | **ENFORCED** | `candidate_claims: []`, `external_actions_taken: []`, and a first-person-claim scanner over every string in the brief; schema validation includes both |
| B13 | Eligibility is never assumed | **ENFORCED** | `satisfied_by_owner_source` requires a canonical owner source and cites file + line; the UAE fixture posting is `unknown` and raises a blocker risk; the owner profile lists only the United Kingdom |
| B14 | Research brief interface | **BUILT; sources owner-gated** | cited provider file -> facts carried; an uncited fact is rejected and listed; no provider -> `research.status = "research_needed"` + the exact requested list; `http` provider disabled (no owner-approved endpoint), `browser` provider disabled by the owner GUI-safety directive, and `--allow-network` with no enabled provider fetches nothing |
| Handoff | Only source-supported facts reach CV/cover-letter | **ENFORCED** | `handoff_jd_text()` joins `source_supported_facts` verbatim in source order; the acceptance asserts every handoff line exists in the posting |
| B17 | Independent Application Pack Reviewer | **BUILT + EVIDENCED** | `career-ops/application_pack_review.py` — separate module, re-reads artifacts + posting + canonical sources; truthfulness / requirement_coverage (essential vs desirable separate) / consistency / formatting / unresolved_unknowns; `pass`, `pass_with_owner_input_required`, `block` |
| B17 | Independence is real, not declared | **PROVEN** | a deliberately tampered pack (invented CV line, invented metric, invented first-person CISSP claim) is blocked on `cv_draft_not_verbatim` + `cover_letter_free_text` + `candidate_claim_not_canonical`; the honest pack is not blocked |
| B18 | Submission gate always requires owner approval | **BUILT + EVIDENCED** | `career-ops/submission_gate.py`; refuses a blocked review, unverified truthfulness, no approval, an approval not bound to `pack_id`+`pack_sha256`, a pack changed after approval, unacknowledged unknowns, and an approval located inside the repository |
| B18 | No autonomous submission | **ENFORCED** | 14 external actions all refused and logged; a valid external approval yields `approved_pending_owner_manual_submission` + an owner checklist, with `external_action_performed: false` on every decision |
| Safety | Canonical sources + trackers untouched | **VERIFIED** | `cv.md` / `config/profile.yml` / `config/cv-facts.json` SHA-256 identical before and after the acceptance run; `applications_submitted: 0`, `external_messages_sent: 0`, `browser_launched: false`, `network_research_calls: 0` |
| Tests | New suite + no regressions | **PASS** | `career-ops/tests/test_job_intelligence.py` **41 passed**; whole `career-ops/tests/` **248 passed** (was 207); acceptance runner **42/42 checks, 0 critical failures** |
| Defect found + fixed | CLI wrote over a file it was reading | **FIXED + REGRESSION-TESTED** | `job_intelligence.py brief` originally reused one `--record` flag for both the input job record and the output path (the Career Ops workflow's `--record` means *output*), so a CLI smoke run wrote the brief over the job-record fixture. Inputs and outputs are now separate flags (`--job-record`/`--jd-file`/`--research-file` vs `--out`/`--out-record`) and `_refuse_to_overwrite_inputs()` refuses any command whose output path resolves to one of its own inputs (exit 1, nothing written). Caught by re-running the suite against the committed revision rather than trusting the earlier green run |

Not claimed (deliberately): any live company research (no approved provider exists, so
every brief carries `research_needed`), any live vacancy (the fixture posting is
synthetic), any submission, and any "independent AI opinion" — B17 is independent
deterministic re-derivation and its own output records that limitation.

## LinkedIn people/network layer: outreach drafts + Interview Prep Agent (2026-09-24T01:30Z)

Task `agent-linkedin-networking-interview-support-2026-09-23` (roster B19, B20, B21, B22).
Acceptance evidence (authoritative): `audits/evidence/20260924T020000Z-linkedin-outreach-interview-prep/`
(`acceptance.json` + `acceptance.md`) — **27/27 checks passed, 0 critical failures**, run against
code SHA `bc6391c` (recorded in the artifact itself). Earlier runs of the same runner are preserved:
`…T015000Z-…`, `…T014000Z-…` (27/27 each) and `…T013000Z-…` (27/27, on the pre-test-only revision),
plus `audits/evidence/20260924T014100Z-cv-linkedin-workflows/` (**23/23, 0 critical failures** — the
pre-existing LinkedIn/CV acceptance re-run against the modified workflow; no regression).
`runtime/career-ops/interview-prep/acceptance/20260924T013000Z/` holds the generated JobBrief and pack
(runtime state is git-ignored).

The B19 read-only intake and the B20 profile/post drafts already existed and were
evidenced by `agent-cv-cover-letter-linkedin-workflows-2026-09-23`; this task added the
people/network layer on top of them.

| Lane | Item | Status | Evidence |
|---|---|---|---|
| B21 | Networking / recruiter / hiring-manager outreach drafts | **BUILT + EVIDENCED — unsent** | `linkedin_workflow.build_outreach_drafts()`; three variants, each `draft_unsent` |
| B21 | Explicit unsent state | **ENFORCED** | every outreach draft carries `unsent_state`: `sent=false`, `sent_at=null`, `recipient_selected=false`, `recipient=null`, `connection_request_created=false`, `message_queued=false`, `scheduled=false`, `attachments_sent=0`, `owner_approval_required=true`; the run reports `sends_performed=0`, `messages_queued=0`, `connection_requests_created=0` |
| B21 | Provenance per draft | **ENFORCED** | `provenance` block per draft: generator, timestamp, canonical `cv.md`/`profile.yml`/`cv-facts.json` SHA-256s, and the exact `cv.md:<line>` refs |
| B21 | No invented role/employer | **ENFORCED** | the hiring-manager draft names the role/employer only from the resolved Career Ops record, recorded in `references_job` (id/title/company/location/source kind/source path); with no job context the variant is **omitted**, never guessed |
| B21 | Generated phrasing is bounded and declared | **ENFORCED** | `linkedin_workflow.STRUCTURAL_PHRASES` is the exhaustive exported list of non-canonical lines; the test suite asserts draft bodies against that same list rather than a copy |
| B22 | Interview Prep Agent | **BUILT + EVIDENCED** | `career-ops/interview_prep.py` + `career-ops/interview_prep_schema.json`; `pack` consumes a JobBrief (+ optional cited research file), `from-job` resolves the job from Career Ops state and briefs it first |
| B22 | Role-specific technical + behavioural prep | **DONE** | 13 technical prompts + 7 behavioural themes on the fixture posting, each tied to the verbatim posting line and its `source_line`, with the derivation stated |
| B22 | Likely questions are never employer questions | **ENFORCED** | every question item carries `employer_supplied: false`, its posting basis, and a note saying a deterministic template generated it; `validate_pack` fails a pack that claims employer origin |
| B22 | Evidence-backed talking points | **DONE + PROVEN** | talking points quote canonical CV lines verbatim with `cv.md:<line>`; the acceptance run **independently re-reads `cv.md`** and confirms every quote; a deliberately altered quote is detected |
| B22 | No invented claims | **ENFORCED** | `candidate_claims: []`, `external_actions_taken: []`, `interview_scheduled/attended: false`; a first-person-claim scanner runs over every generated (non-quoted) field and an injected claim is detected |
| B22 | Honest gaps | **ENFORCED** | a requirement with no canonical evidence becomes `owner_input_required` with an explicit owner action; the UAE fixture posting's eligibility stays `unknown` and no right-to-work position is invented |
| B22 | Commercial-credibility defect found and fixed | **FIXED** | the first revision scored evidence by any term overlap, so a mainframe-RACF requirement was reported `evidence_backed` off the word "security" alone. `evidence_matching.general_terms` now strips domain words before scoring (a match must include a term outside that list), and a qualification requirement is answered from the canonical qualification headings (`qualification_section_patterns`) instead of the general-term filter. Ordinary-postings terms are unaffected. Caught by an explicit test, not by inspection |
| Safety | Owner action gate | **ENFORCED** | `guard` refuses and logs `post`, `message`, `connection_request`, `apply`, `profile_update`, `inmail`; no code path performs any of them |
| Safety | Canonical sources + trackers untouched | **VERIFIED** | source SHA-256s re-read after the run: identical; the run's own writes are the pack, its markdown and the brief under git-ignored `runtime/` |
| Tests | New/extended suites | **PASS** | `career-ops/tests/test_interview_prep.py` **26 passed** (new); `career-ops/tests/test_linkedin_workflow.py` **38 passed** (was 34); whole `career-ops/tests/` **278 passed** (was 248); `career-ops/tests/` + `company-watch/tests/` together **308 passed**. One of the new tests validates a real pack against the committed `interview_prep_schema.json` with `jsonschema`, and asserts the schema rejects a pack whose question claims employer origin — so the schema is a contract, not decoration |

Truth boundaries recorded in the artifact, not glossed over:

- The questions in a pack are **generated preparation prompts derived from the
  posting's own text**. They are not the employer's interview questions, and the pack
  never claims an interview, a panel, an interviewer or a process detail.
- The job description and job record used by the acceptance run are explicitly
  labelled **synthetic fixtures**; no live vacancy is claimed and nothing is
  submitted. The cited research file is a labelled transport/shape fixture, not live
  company research.
- `questions_to_ask_employer` suggestions are prompts for the candidate to ask; they
  are not claims that the employer said anything.
- The live LinkedIn account surface is **owner-gated and untested** — no account,
  session, API key or browser path exists in this runtime (owner decision recorded as
  item 13 in `tasks-or-issues/overnight-owner-actions-2026-09-24.md`).

Successor task: **no new `agent-*` task staged** — the whole-company local acceptance
task (`agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`, pending)
already lists the LinkedIn draft/read-only path, and its scope does not mention the
interview-prep path, so that gap is recorded here for that task rather than duplicated.

## Career Daily Brief / Pipeline Prioritizer (2026-09-24T03:40Z)

Task `agent-career-daily-brief-and-pipeline-prioritizer-2026-09-23` (roster B23).
Acceptance evidence (authoritative): `audits/evidence/20260924T034000Z-career-daily-brief/`
(`acceptance.json` + `acceptance.md`) — **32/32 checks passed, 0 critical failures**. The earlier run
of the same runner is preserved (`…T033000Z-…`, 30/30), superseded because stage 3's partial-input
check was tightened from an `or`-chained assertion to three precise ones.

The brief is an aggregator, so this task added **no new career state**: it reads the artifacts the
other Career-department workers already own and restates them.

| Lane | Item | Status | Evidence |
|---|---|---|---|
| B23 | Daily Brief / Pipeline Prioritizer | **BUILT + EVIDENCED** | `career-ops/daily_brief.py` + `career-ops/daily_brief_config.json`; subcommands `inputs`, `policy`, `build`, `summary`, `status`; `build` writes a machine-readable brief + a concise Chief summary and nothing else |
| B23 | Read-only aggregation from canonical state | **ENFORCED** | canonical workbooks read through `tracker_writer.py` only; SHA-256s re-read after the run are identical; `canonical_workbook_writes: 0`; the `safety` block reports `canonical_state_unchanged: true`; the module has no network/browser/subprocess-CLI surface (asserted by test) |
| B23 | Deterministic priority policy | **DECLARED + ENFORCED** | five explicit inputs with declared weights (deadline 40, application stage 20, eligibility certainty 15, freshness 15, owner flag 10) and declared class bands P1–P4; score is taken over the **full** policy weight, so an UNKNOWN input lowers the score rather than being imputed; each item publishes `components` (value, weight, contribution, observed), `coverage_pct`, its UNKNOWN inputs and any override that fired |
| B23 | No fabricated priority facts | **ENFORCED** | `score_semantics.kind = "deterministic_policy_output"` with an explicit note that it is not a vacancy assessment, a fit score or an employer ranking; a status outside the declared stage vocabulary is UNKNOWN, never zero; a candidate with no known policy input is reported at P4 **and labelled `unscoreable`**; the acceptance runner asserts every score equals the sum of its declared components and that no input is reported as both known and unknown |
| B23 | Three declared overrides | **ENFORCED** | `urgent_deadline` (deadline within 3 days → at least P2), `owner_action_min_class` (owner-only action → at least P2), `unscoreable` (→ P4, labelled); overrides are recorded on the item with the rule that fired, so a P1 is always explainable from its components |
| B23 | Unknowns are named, not filled | **ENFORCED** | the UK tracker has no deadline column, so deadline is UNKNOWN for **every** UK row rather than assumed; Dubai/Japan/Singapore have no recorded work-authorisation position, so eligibility certainty stays UNKNOWN there; an unrecognised status, a missing posting date and a missing owner-action file are all named unknowns with a reason |
| B23 | Regional scan health | **DONE** | per-region health from the workers' own run-state file: last status, last run time, age in hours against the **injected** logical clock, ok/failed run counters and the scanner's own parsed accepted/rejected/duplicate counters |
| B23 | Newly added jobs | **DONE + HONEST** | tracker rows with a date-stamp inside the brief window, plus scan offers — which carry **no URL** and are labelled as not yet tracker rows, because the shared writer's dedupe is URL-based and an unresolved offer cannot become one |
| B23 | Duplicates suppressed | **DONE** | reported from three real sources: the scanner's own duplicate counter, the prior-brief idempotency result, and the shared writer's dedupe policy (stated as policy, not as a measured count) |
| B23 | Application-status changes | **DONE** | Application Inbox monitor proposals (`build_summary()`), including monitor-raised owner actions; no status is applied — the brief reports proposals the owning worker would make |
| B23 | Interview / follow-up items | **DONE** | Interview Prep packs, filtered to declared stage values at or above the configured follow-up threshold; a section that is unavailable says so with the reason (`available: false` + `error`) instead of rendering as empty |
| B23 | Company Watch findings | **DONE + PRIVATE-SAFE** | findings counts and freshness; the company registry is restated at aggregate level only, because it is owner-private |
| B23 | Owner actions | **DONE** | open items read from `overnight-owner-actions-2026-09-24.md`, each becoming a priority candidate with `owner_action_min_class`; an absent file yields zero items and a named missing input, never an invented action |
| B23 | Machine-readable + Chief-facing outputs | **DONE** | `brief-<digest>.json` (with its own schema block, priority items, unknowns, safety block and run metadata) plus `chief-summary-<digest>.md`, bounded to a declared maximum of lines, `latest.json`/`latest.md` for stable paths |
| B23 | Idempotency | **PROVEN (quantized)** | the content digest excludes `generated_at`, `brief_id`, `content_digest` and the `delivery` block; where the stored file's recomputed digest matches, the run writes **no new bytes** and reports `idempotent: true`; a repeat run is asserted byte-neutral apart from the append-only `run-log.jsonl`. The as-of clock is floored to `window.quantize_minutes` (60; `0` disables), so a run inside the same quantum over unchanged artifacts is the same brief and crossing the quantum is a new one |
| B23 | Empty / partial input behaviour | **PROVEN** | an empty-input run (no workbooks, no run-state, no findings, no owner-action file, no packs) still builds, labels every absent input as absent, never reports an absent source as healthy or as zero, and keeps `ok: true`; a partial-input run names the missing sources and invents no owner action |
| B23 | Delivery honesty | **ENFORCED** | local file only, verified by sha256 read-back (`stored_content_matches`); `external_channels: []` and `external_channel_health: "not_verified"` — nothing is sent, posted or scheduled to a messaging surface, and no channel is assumed healthy |
| B23 | Morning schedulability | **DONE** | `ChiefCareerBrief` registered daily at **07:00** (`career-ops/run_scheduled_brief.cmd`); `install_schedules.py` gained `--install-brief` / `--remove-brief`, and `--status` now includes the brief task alongside the regional lanes |
| Safety | No submission, no outreach | **ENFORCED** | the module contains no submission, messaging, browser or provider call; acceptance asserts zero submissions, zero external messages, zero external actions |
| Safety | Canonical state not overwritten | **VERIFIED** | workbook SHA-256s identical before/after; the brief's only writes are its own digest-named artifact, the `latest` pointers and its run log, all under git-ignored `runtime/career-ops/daily-brief/` |
| Tests | New suite | **PASS** | `career-ops/tests/test_daily_brief.py` **22 passed** (new; 21 at attempt 1 + the quantized-identity contract); whole `career-ops/tests/` **300 passed** (was 278) |

Defect found and fixed inside this task (recorded because it was a real correctness bug, not polish):
the content digest was computed **before** `chief_summary`, `input_fingerprint`, `delivery` and
`brief_id` were attached, so the stored file's recomputed digest could never match the in-memory one
— every run would have rewritten its own "identical" artifact and idempotency would have been
claimed but false. The digest is now finalised after the brief is complete (with the volatile keys
excluded), and idempotency is **asserted** by the acceptance runner rather than asserted in prose.
A second leak of the same class was fixed with it: run ages were computed against the wall clock
instead of the injected logical clock, which made two otherwise identical runs differ.

Truth boundaries recorded in the artifact, not glossed over:

- The brief **owns nothing**. It is a view over canonical artifacts; deleting it loses no career
  state, and a wrong brief cannot corrupt a tracker.
- The priority score is a **policy output over declared inputs**. A low score with low coverage means
  "little policy evidence", not "poor opportunity", and the brief says so in its own semantics block.
- Scan offers are **not** tracker rows and the brief does not pretend otherwise.
- The schedule makes the brief *available* in the morning. **No external delivery channel is
  configured, verified or claimed** (`not_verified`); choosing one is a pending owner decision
  (`tasks-or-issues/overnight-owner-actions-2026-09-24.md` item 14).

Successor task: **no new `agent-*` task staged** — the aggregation is complete and scheduled inside
this task's scope; the only open item is the owner delivery-channel decision, which is a decision,
not engineering.

### Attempt 2 amendment (2026-09-24, task retry)

Attempt 1 of this task ended in a recoverable execution failure **after** it had committed and pushed
the worker (code SHA `911fd9c`), and left one uncommitted change plus its test not yet updated. The
retry finished that unit only — nothing above was recreated, reverted or re-run as new work.

- **What was outstanding:** the as-of clock was the instant the process ran, so two runs of the same
  unchanged artifacts minutes apart were two different briefs and the second rewrote everything. The
  fix floors the as-of/window clock to a declared quantum — `window.quantize_minutes` (default 60;
  `0` is the documented opt-out) — so the brief's identity is "the state as of the end of a quantum".
  `generated_at` keeps the true run instant and stays excluded from the content digest.
- **Second defect found while completing it:** `brief_id` was still stamped with the raw run clock
  while the as-of was floored, so two runs over an identical digest published different ids
  (`cdb-…T013130Z-62b8de90` vs `cdb-…T013136Z-62b8de90`). The id is now stamped with the brief's own
  `as_of`, so an id no longer drifts per run. Verified on the real scheduled path
  (`run_scheduled_brief.cmd` run twice: second run `wrote: []`, `idempotent: true`, identical
  `brief_id` in both run-log entries).
- **Contract pinned both ways:** `tests/test_daily_brief.py` now asserts a sub-quantum rerun is the
  same id and digest with no writes, a crossed quantum is a new brief, and `quantize_minutes: 0`
  restores per-run identity (22 passed, was 21; whole `career-ops/tests/` **300 passed**, was 299).
  The acceptance runner gained the same stage-4 checks against the live config.
- **Harness defect found and fixed inside this retry:** the first version of the new stage-4 check
  compared *all* files after the sub-quantum run, including the append-only `run-log.jsonl`, which
  must grow — so it reported a false failure. The check now excludes the run log; the false-negative
  run is preserved under `audits/evidence/superseded/20260924T012854Z-career-daily-brief-interim-check-bug/`
  rather than deleted.
- **Authoritative evidence:** `audits/evidence/20260924T013238Z-career-daily-brief/` — **34/34 critical
  checks, 0 failures** (attempt 1: 32/32), code SHA `9b414f1` recorded in the artifact, canonical
  workbook SHA-256s identical before/after, zero submissions / messages / canonical writes, no
  external channel claimed. Attempt 1's evidence (`…T033000Z-…`, `…T034000Z-…`) is left untouched as
  the record of the pre-amendment code; the interim 34/34 run
  (`…T012926Z-…`, before the `brief_id` fix) is kept under `audits/evidence/superseded/`.
- **Unchanged:** scope, stop conditions, priority policy, delivery honesty (`not_verified`), the
  07:00 `ChiefCareerBrief` schedule (queried as `Ready`, next run 24-09-2026 07:00), and the fact that
  this worker still owns no career state.

## Google image worker — bounded repeat series + image request-protocol conformance (2026-09-24T01:44Z)

Task `agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23`. Everything below is
from recorded provider responses and recorded store rows. **Stage 2 and production dispatch were
NOT enabled** by this work.

| Item | State | Evidence |
|---|---|---|
| Stated call budget honoured | **DONE** | 9 real Google image generations declared in the evidence artifact before the first call; 9 attempted, 9 recorded, no abort. Table: 6 identical `IMAGE-only` repeats, 2 `['TEXT','IMAGE']`, 1 `['TEXT','IMAGE']+imageConfig`. No metadata call was made either, so generations == stated total |
| Ran on the real deployed path | **DONE** | every call went `ExecutionAdapterRegistry` → `GeminiImageExecutionAdapter` → `generateContent`; per-call sanitized diagnostics recorded; schema-v2 `dag_node`/`dag_state_event`/`performance_evidence` rows persisted (google evidence rows 2 → 11) |
| E2 integration public-interface only | **VERIFIED** | telemetry written only through `governor.record_request()`; all 9 request ids read back from `governor.db` (`all_found: true`); the two failures record `status=error` with `output_tokens=null`, never approximated; no SQL write to `exec_brain.db` or `governor.db` from E3 |
| Recurrence measured, not characterised | **DONE** | **2 of 9** (rate 0.2222); 2/6 on `IMAGE-only`, 0/2 `TEXT+IMAGE`, 0/1 `TEXT+IMAGE+imageConfig`. Reported as counts over executed calls; no stable/unreliable/broken claim is made |
| Root signal of the recurrence | **NEW FINDING** | both recurrences carried provider-supplied `finishReason=IMAGE_RECITATION`, empty response part list, no candidate, 17 prompt / **0** output tokens — a provider content-side stop, not an adapter/transport failure and not a modality rejection |
| Request shape completeness | **SETTLED (measured)** | the production shape (`responseModalities=['IMAGE']`, no `imageConfig`) is accepted and returned a decodable 1024×1024 JPEG on 4 of its 6 calls; `['TEXT','IMAGE']` is also accepted. The adapter now takes an optional contract-declared `response_modalities` / `image_config` (production default unchanged) and echoes the shape used into the result + sanitized metadata + persisted attempt record |
| Prompt-stated image size | **IGNORED — protocol fact, not a pass** | objective asked 64×64; every `IMAGE-only` call returned 1024×1024 |
| Explicit size control | **SUPPORTED PARAMETER PROVEN** | `generationConfig.imageConfig={imageSize:'512'}` was accepted and returned **512×512**; exact 64×64 is **not** achievable through it (size class, not arbitrary pixels) → recorded as a **known limitation** |
| Readiness criteria weakened | **NONE** | the image node's deterministic verification contract is unchanged ("image part present and decodes"); size findings are recorded as protocol facts |
| Evidence-backed qualification for vision | **MOVED OFF EVALUATING** | `scripts/e3_qualification_from_evidence.py` (bar unchanged: ≥2 verified passes over ≥2 recorded executions, ≥1 first-pass) → `google-nano-banana-2`/vision **QUALIFIED**: 11 recorded executions, 8 verified passes, 8 first-pass, all six checks pass, `qualified_rows_without_evidence = 0`. **Not** to be read as "always returns an image" — the same series measured a 2/9 no-image rate; the bar qualifies recorded dispatch repeatability under the declared contract |
| New offline test suite | **PASS** | `exec-brain/tests/test_e3_google_image_protocol.py` — **18 passed** (stubbed HTTP layer, isolated db, no provider call) covering the declared shape reaching the payload, shape + diagnostics surviving into the persisted attempt, the no-image-is-not-a-pass rule, and the repeat-series accounting |
| Full regression | **PASS** | `python scripts/evidence_runner.py --label e3-google-image-protocol-conformance` → **16 suites / 456 tests / 16 passed / 0 failed / 0 unavailable, exit_code 0**, code SHA `5a12463`; artifact `audits/evidence/2026-09-24T01-47-46Z-e3-google-image-protocol-conformance/` |
| Deployment | **DONE** | `python scripts/deploy_e3_runtime.py` copied `e3_qualification_benchmark.py`, `e3_execution.py`, `gemini_adapter.py` to the runtime root with rollback backup `exec-brain/backups/e3-deploy-20260924T014415Z` (manifest recorded there) |

Still open (recorded, not chased): **what makes the provider's recitation filter fire on some calls
and not others for the identical prompt.** The earlier 21:07Z failure `gem-d8c43b8cb447` captured no
`finish_reason`, so its identity with these recurrences is an inference from identical usage (17
prompt / 0 output tokens) and the identical request — stated as an inference, never as a fact. No
unbounded or exploratory generation was performed to chase it.

Evidence: `audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/` (evidence.json,
evidence.md, observations.json — the per-call record written incrementally) and
`audits/evidence/2026-09-24T01-46-56Z-e3-qualification-from-evidence/`. One driver defect was fixed
inside this task: the first revision of the runner wrote `evidence.json` and then crashed in the
markdown renderer (`calls_completed` read from the wrong nesting level). The provider cost was
already spent at that point, so the artifacts were re-derived from the captured responses with the
new `--from-evidence` path — **0 additional provider calls** — rather than re-running the series.

## Career Ops tracker interface committed + Monthly Tracker Rollover worker (B09) (2026-09-24T02:04Z)

Task `agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23`. This closed the one real
coverage gap found by the company-registry gap audit: the deterministic Chief ⇄ Career Ops tracker
interface (B07/B08) was preserved and committed, and the missing Monthly Tracker Rollover / archive
worker (B09) was built, tested and evidenced. The regional lanes and Company Watch were **not**
touched — other pending tasks own them.

| Item | State | Evidence |
|---|---|---|
| B07/B08 interface confirmed | **PASS — no change needed** | `career-ops/career_ops_cli.py` + `tracker_writer.py` were already committed at `70dd715`; they import cleanly and the whole suite is green (no revert of the audit's `emit()` UnicodeEncodeError fix) |
| B09 Monthly Tracker Rollover / archive worker | **BUILT** | `career-ops/tracker_rollover.py` (+ `career_ops_cli.py rollover` / `archives`): rotates one closed month per region into `uk-cyber-job-tracker.<YYYY-MM>.xlsx` / `<Region>_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx`, dry-run by default |
| Archive preserves the canonical schema | **PROVEN** | the archive is built from a copy of the canonical workbook, so sheets, table, header row, data validations, number formats and column layout are inherited; row-number-dependent formulas are re-templated; every cell of every rotated row is copied verbatim, owner columns included (asserted cell by cell) |
| Canonical workbook stays authoritative | **ENFORCED** | the archive is written and verified *before* the canonical is touched; a canonical write takes a hash-verified backup, writes to `*.rollover-tmp.xlsx`, re-opens and verifies it (row count + owner columns unchanged at their new positions), passes a concurrent-modification hash guard, and is only then atomically replaced |
| Owner state is never silently deleted | **ENFORCED — and it fired on real data** | rotation refuses the whole run when a row due to rotate carries a value in an owner-only column that is not the profile's own automation default; conflicts are reported by row/column only and the value never enters the result. Running `rollover --month 2026-09` against the real canonical workbooks today: **uk 26 conflicting rows (J×5, K×21), dubai 8 (R), singapore 4 (R), japan 0** — those rows carry owner application state, so rotation was correctly refused rather than deleting them |
| Rotated rows feed the cross-month dedupe index | **PROVEN** | every rotated row is present in `tracker_writer.build_cross_month_index` via the region's archive glob, and re-adding the same posting is refused as `duplicate-cross-month` with **0 appends** in all four regions |
| Determinism / idempotency | **PROVEN** | a byte-identical re-run reports `unchanged` and rewrites nothing; a re-run after rotation reports `no_rows`; an existing archive with different content is refused unless `--force`, which backs it up hash-verified first |
| Reversibility | **PROVEN** | the dated copy restores byte-identically from the rollover backup, and deleting the archive removes exactly its keys from the dedupe index |
| New regression suite | **PASS** | `career-ops/tests/test_tracker_rollover.py` — **32 passed** (was 0); whole `career-ops/tests/` suite **332 passed** (was 300) |
| Reversible acceptance run (safe copies only) | **PASS** | `career-ops/run_rollover_acceptance.py`, exit 0, `ok: true` for all four regions; artifact `audits/evidence/2026-09-24T02-04-31Z-career-ops-monthly-rollover/acceptance-20260924T020431Z.json` (aggregate only) |
| Canonical workbooks untouched by the whole exercise | **VERIFIED** | SHA-256 of all four canonical workbooks identical before and after the tests and the acceptance run; the suite asserts it as a final test |
| Department run-health (B08 + B09) | **BUILT + RECORDED** | `career-ops/dept_run_health.py` → `runtime/career-ops/run-health/tracker-writer.json` and `monthly-rollover.json` (last run, result, row counts, mode, per region), read back with `career_ops_cli.py run-health`. Aggregate only — a test asserts no URL or workbook text is ever stored there. Both workers state `excel_is_source_of_truth: true` and `chief_state_role: "orchestration-only"` |
| Registry / operating map updated | **DONE** | registry skill references updated: `ownership_map.md` (dedupe / UK tracker writing / monthly rollover / run-health rows), `integration_rules.md` §8 (the interface + its 8 non-weakenable rules), `company_registry.yaml` (new `career_records_interface` resource), `resource_map.md` (canonical ↔ archive naming), `schedule_map.md` (rollover is deliberately unscheduled) |

Documented limits (recorded, not hidden): a row whose `date_found` is not a real date or ISO date
string (e.g. the free text `"Posted 30+ days ago"`) is reported as `undated` and never rotated; the
regional profiles map the manifest `notes` field to column `Z` while also declaring `Z` an owner
column, so `Z` is automation-writable and is reported under `owner_columns_automation_writable`
rather than being claimed as protected; overview sheets (UK `Summary`) are not rewritten — their
formulas use whole-column ranges and recompute over the remaining rows when opened.

Owner decision still open: whether to rotate the current month out of the live workbooks at all, and
what to do with the rows that carry owner application state. The worker refuses those rotations by
design; nothing was forced, and no canonical workbook was modified.

## Company Watch / job-search integration — recovery pass (2026-09-24T02:27Z)

Task `agent-company-watch-recovery-final-pass-2026-09-24`, recovering the record
`agent-company-watch-job-search-integration-2026-09-23` that was claimed at 2026-09-23T22:58:06Z and
hard-blocked at 2026-09-23T23:18:06Z with `execution_error` ("Hermes dispatch exceeded 1200
seconds"). **Nothing was rebuilt**: the inspection the task asked for first showed the module had
already reached `main` in commit `42a2bec` (the CV/cover-letter + LinkedIn task, which imports
Company Watch for its dedupe). The recovery pass therefore verified that landed work, closed the one
real evidence gap it found, and produced fresh bounded evidence.

| Item | State | Evidence |
|---|---|---|
| Inventory / reconciliation before editing | **DONE** | `company-watch/` is tracked on `main` at `42a2bec`: `company_registry.py`, `ats_endpoints.py`, `company_watch.py` (CLI `registry`/`resolve`/`scan`/`handoff`/`workbook`/`run`), `company_watch_config.json`, aggregate `registry/company_watch_registry_summary.json`, `tests/test_company_watch.py`. No unpushed partial work was found in the worktree, and none was assumed |
| Original blocked run's evidence | **PRESERVED + COMMITTED (private-safe)** | `audits/evidence/2026-09-23T23-10-46Z-company-watch-integration/` — `evidence.md`, `evidence.json`, `acceptance.json` committed; `findings.json`, `resolution.json`, `manifest-*.json` and the raw tracker backup stay git-ignored because they name companies/postings |
| Structured ATS/career endpoint watcher | **VERIFIED WORKING** | bounded live `resolve` still resolves vendor boards (`greenhouse`/`ashby`/`lever`/`workable`/`smartrecruiters`); attribution stays `high` only when the vendor payload names the company — 1 board resolved, 11 `manual_attribution_required` in this run |
| Canonical dedupe handoff | **VERIFIED, canonical untouched** | shared dedupe read from `career-ops/tracker_writer.py` (34 canonical data rows + 154 cross-month keys); dry-run handoff of the marked sample appended 3/3 against the canonical workbook with the canonical SHA-256 re-checked identical afterwards |
| Regional tracker handoff (dubai/japan/singapore) | **GAP FOUND AND CLOSED** | the previous suite only asserted the regional *provenance mapping*, never an end-to-end write. Added `test_regional_handoff_writes_provenance_to_a_tracker_copy` (parametrized per region) and `test_regional_handoff_requires_an_explicit_region`: provenance lands in `Source` (X), existing owner columns (R,S,T,U,V,Z) are unchanged, re-applying appends 0 with 1 duplicate, canonical regional workbook hash unchanged |
| Bounded acceptance evidence | **PASS (fresh, this pass)** | `audits/evidence/2026-09-24T02-27-00Z-company-watch-recovery/` — 12 companies, 58 HTTP requests, **23.2 s**, `budget_exhausted: false`; 19 findings (all `new`), 0 tracker-eligible under the owner's intern-only UK filter; acceptance write on a **copy** 3 appended → repeat 3 duplicates, canonical untouched |
| Evidence attribution | **FIXED** | the evidence header had the original task id hardcoded, so a later acceptance/recovery run could not label its own evidence. `run --task-id <id>` now sets it (default unchanged), documented in `company-watch/README.md` |
| Tests | **PASS** | `company-watch/tests/test_company_watch.py` **35 passed** (was 31; +4 regional end-to-end/refusal tests), offline |
| No external action | **ENFORCED** | read-only public ATS GETs only; no applications, messages, recruiter/company contact, account or LinkedIn mutation; no secrets or raw email content added |

Truth boundaries recorded, not glossed over:

- The historical counts (**203** confirmed/strongly evidenced employers, **18** recruiters, **221**
  organisations with application/CV evidence) are **re-parsed from the owner's recorded history file**
  (`uk_application_company_history_18_months.md`, SHA-256 `2fb46ce8…`) on every refresh with no
  declared-vs-parsed mismatch — that is *re-derivation from the recording*, not a re-verification
  against the mailbox. They stay historical.
- An empty tracker-eligible set is the owner's own filter doing its job (UK lane is
  `Intern`/`Internship` only), not a claim that no watched company is hiring.
- `run-health/tracker-writer.json` is written by *any* writer invocation, including the
  copy-targeted acceptance writes, so a test run can move the department health counters. It was
  restored to its committed state after this pass; hardening it would belong to the tracker-writer
  owner, not to this task.
- Not this task's to finish: the regional scan/schedule lanes
  (`agent-regional-job-search-agents-and-schedulers-2026-09-23`) and the reconciliation of the
  historical blocked record itself, which the pending `agent-blocked-work-final-reconciliation-
  2026-09-24` owns (it lists this recovery as its prerequisite, so the blocked JSON was deliberately
  left in place).

## Historical blocked-work final reconciliation — `agent-blocked-work-final-reconciliation-2026-09-24`

Audited 2026-09-24T02:45Z at code SHA `9bc20a7`. Authority:
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`.

| Item | State | Evidence |
|---|---|---|
| `remote-queue/blocked/` records audited | **DONE — 12/12** | each file read against current `main`, the completed successor records, `audits/evidence/`, and the pending/running contracts |
| Records classified superseded/resolved (rerun NOT needed) | **10** | successor + concrete evidence recorded per record in an additive `final_reconciliation_2026_09_24` note (all 12 edits programmatically proven strictly additive) |
| Records classified deterministic owner/external blocker (parked) | **2** | both `agent-e3-stage2-readiness-gate-after-provider-keys-retry*`; 0/7 credentials unchanged, Stage 2 NOT ENABLED, duplicate retry chain closed |
| Records left unreconciled | **0** | — |
| Contract verification 1: queue-recovery / UTF-8 / QuickEdit failure class | **SUPERSEDED — CONFIRMED** | deepseek-utf8 recovery completed (isolated queue suite, 4 lifecycle defects fixed) + bridge UTF-8 hardening `e643fd16` + QuickEdit/two-retry hardening `85f604aa` |
| Contract verification 2: E3 integration/rehearsal failures | **SUPERSEDED — CONFIRMED, no provider calls repeated** | production execution leg built/deployed/executed; bounded Google image diagnosis + 9-call series (2/9 `IMAGE_RECITATION`); readiness gate rerun 12 suites / 364 tests / exit 0 at `56d923b`, rehearsal evidence consumed (sha256 `88212b70…`) |
| Contract verification 3: Career Ops historical timeout | **CLOSED — CONFIRMED** | committed Career Ops⇄Chief interface (33 tests, encoding fix live-confirmed via Task Scheduler) + B09 monthly rollover (career-ops suite 332 passing, canonical workbooks SHA-256 unchanged) |
| GAP-1 (high): genuine agent task silently swallowed by poller routing | **FIXED** | `remote_queue/poller.py` — `agent-` dispatch now precedes all legacy substring placeholder routers; `agent-operational-brief-health-backup-persistence-2026-09-23` (claimed 2026-09-24T01:38:05Z, never executed) restored to `pending/` with the same task_id; new `remote_queue/tests/test_poller_routing.py` (9 tests) |
| GAP-2 (medium): E1 static gate failing on SQLite sidecars | **FIXED** | `exec-brain/tests/test_eb.py` T13 accepts only `-wal`/`-shm` sidecars of already-allowed databases; negative proof recorded (unexpected file still fails, probe deleted); E1 **32/32 exit 0** |
| Regression evidence | **PASS** | `scripts/evidence_runner.py --label blocked-work-final-reconciliation-final` → **17 suites, 465 collected / 465 passed, 0 failed, 0 errors, 0 unavailable, every suite exit 0** (`audits/evidence/2026-09-24T02-37-18Z-blocked-work-final-reconciliation-final/`); the new routing suite was added to the runner; isolated queue discovery 87/87 |
| Owner action | **NONE NEW** | unchanged dependencies only: seven provider credentials, Career Ops rollover policy, pre-existing laptop/scheduled-task admin items |
| Ready for whole-company acceptance | **YES** | 0 unresolved non-owner recoverable blockers |

## Provider content-side stop attribution — `agent-e3-provider-content-stop-attribution-and-image-retry-policy-2026-09-24`

Audited 2026-09-24, authority `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`.
Evidence: `audits/evidence/2026-09-24T02-59-00Z-e3-provider-content-stop-attribution/`.

| Item | State | Evidence |
|---|---|---|
| Provider-call budget for this task | **0 (stated up front)** | recorded 2026-09-24T01:44:32Z responses used verbatim as offline fixtures; the series was NOT re-run |
| Content-side stop given its own attribution | **DONE** | `provider_content_stop` in `exec-brain/e3_execution.py`, decided only from provider-returned `finishReason` / `promptFeedback` |
| Transport/provider error separated | **DONE** | `provider_error` (HTTP status, absent credential, raised exception, or 200 with no image and no content-side stop reason) |
| Contract failure separated | **DONE** | `verification_fail` retained for a delivered, well-formed output that fails its declared contract |
| Provider finishReason recorded in the terminal state | **DONE** | DAG transition cause `provider_content_stop_unrecovered:<finishReason>`, `blocking_reason`, and the evidence row's structured deterministic-test results |
| Retry policy encoded from recorded evidence | **DONE** | bounded identical same-request retry, `DEFAULT_MAX_CONTENT_STOP_RETRIES = 2` (≤ 3 identical single-shot calls per node); same objective + same contract-declared shape, never a reworded repair |
| Non-silent terminal path | **DONE** | node `BLOCKED` + E3 escalation `trigger=provider_content_stop` naming the finish reason and the owner decision; never a pass, never a silent `verification_fail` |
| Unbounded retry prevented | **CONFIRMED** | hard bound `1 + max_repair_attempts + max_content_stop_retries` plus a defensive `attempt_budget_exhausted` BLOCKED guard; Stage-2 credential gate untouched |
| Verification criterion | **UNCHANGED** | only an independent deterministic verification PASS reaches `COMPLETE` |
| E4 resource continuity / E5 convergence | **CONFIRMED UNCHANGED** | no fabricated or silent failover; worker identity never changed silently; `ConvergenceEnforcer` warn → quarantine → stop cap tests still pass |
| New offline tests | **25 tests / exit 0 / 0 provider calls** | `exec-brain/tests/test_e3_provider_content_stop.py`, registered in `scripts/evidence_runner.py` |
| Regression | **PASS — baseline beaten** | `scripts/evidence_runner.py --label regression-post-content-stop` → **19 suites / 19 passed / 0 failed / 0 unavailable / 507 tests / exit 0** (`audits/evidence/2026-09-24T02-56-57Z-regression-post-content-stop/`); baseline 18 / 482 / exit 0 at `d9d1a7f` |
| E3 Stage 2 / production dispatch / VPS cutover | **NOT ENABLED / NOT PERFORMED** | no readiness, qualification or verification criterion changed |
| Owner action | **NONE NEW** | unchanged dependencies only |

## Provider content-side stop — operator surface + orchestrator boundary + rehearsal integration — `agent-e3-content-stop-operator-surface-and-rehearsal-integration-2026-09-24`

Ran 2026-09-24T03:08Z–03:12Z at code SHA `82ddf0081b1de0503d487f901d8bf294a3eaa223`.
Evidence: `audits/evidence/2026-09-24T03-08-34Z-e3-content-stop-operator-surface/`.
Provider-call budget: **0 (stated up front)** — deterministic stub adapters on the real code path
plus the response recorded by the predecessor task, reused verbatim as a fixture.

| Item | State | Evidence |
|---|---|---|
| Operator surface (a) | **DONE** | `exec-brain/e3_commands.py`: new `finish_reason_from_cause()` + `node_failure_view()`; `e3-status` gained a DAG state breakdown and a **Node Failure Attribution** section (`TERMINAL_FAILURE_STATES = ("BLOCKED","FAILED")`, capped at `MAX_STATUS_ATTRIBUTION_NODES = 20` with the full count still printed); `e3-trace` prints the same block; `e3-why <node>` prints the persisted attribution and still reports an unknown node as unknown. Read-only over already-persisted rows — **no new schema, no E1/E2 write** |
| Operator surface, end to end | **CAPTURED** | `operator_surface_output.txt` / `operator_surface_demo.py` (real execution leg, stub adapter, isolated db): `e3-status` → `Failure attribution: provider_content_stop` / `Provider finish reason: IMAGE_RECITATION` / `Terminal transition cause: provider_content_stop_unrecovered:IMAGE_RECITATION`; identical on `e3-trace` (plan) and `e3-why` (node) |
| CLI JSON | **EXTENDED ADDITIVELY** | `exec-brain/e3_cli.py` forwards `outcome`/`plan_id`/`team_complete`/`team_assignments`/`execution`/`escalation`; the operator surface itself lives in `e3_commands.py` |
| Orchestrator boundary (b) | **DONE** | `e3_shadow_orchestrator.orchestrate_and_execute` returns `execution_escalations` (the leg's records, verbatim) and `content_stop_escalation` — `trigger=provider_content_stop` with `finish_reasons`, `node_ids`, `worker_ids`, `content_stop_retries`, `execution_escalation_ids`; `null` on a clean run |
| Existing escalation behaviour | **UNCHANGED** | `out["escalation"]` still `trigger=repeated_failure`, owner gate and escalation-on-incomplete behaviour untouched — the change is additive |
| Rehearsal driver (c) | **DONE** | `exec-brain/e3_execution_rehearsal.py` scenario **`G_content_stop_terminal`** (`stub_only`, can never spend a provider call) runs the recorded stop (finishReason `IMAGE_RECITATION`, empty part list, no image, 0 candidate tokens) on the real code path and records `content_stop_finish_reason`, `content_stop_retry_budget`, `content_stop_retry_count`, `content_stop_retries_are_identical_requests`, `content_stop_escalation`, `content_stop_terminal_path_recorded`; new checks `content_stop_terminal_path_recorded`, `content_stop_retries_stayed_bounded`; `EXPECTED_BLOCK_SCENARIOS` now covers G |
| Driver artifact | **PRODUCED, 0 provider calls** | `execution_rehearsal_stub_report.json` via `run_stub_execution_rehearsal.py` (real `run()` path, every adapter factory replaced by a deterministic stub, isolated db): **23/23 checks true**, 3 stub dispatches, `content_stop_retry_count = 2` against `content_stop_retry_budget = 2`, no 4th dispatch, node persisted `BLOCKED` with cause `provider_content_stop_unrecovered:IMAGE_RECITATION`, escalation `trigger=provider_content_stop` / `finish_reason=IMAGE_RECITATION` / `content_stop_retries=2`. The artifact states in-band that `provider_calls_actually_spent = 0` |
| New offline tests | **PASS, 0 provider calls** | `exec-brain/tests/test_e3_operator_surface.py` **13 passed** (new, registered in `scripts/evidence_runner.py`); `test_e3_shadow_orchestrator.py` **13 → 18** (`TestOrchestrateAndExecuteContentStopEscalation`); `test_e3_execution_rehearsal.py` **22 → 26** (scenario G + `test_bounded_usage_counts_real_dispatches_only` rewritten to filter `adapter_call_log` by `STUB_ONLY_SCENARIOS` so stub-only scenarios can never be miscounted as real dispatches) |
| Regression | **PASS — baseline beaten** | pre-deploy `--label regression-post-content-stop-operator-surface` → **20 suites / 20 passed / 0 failed / 0 unavailable / 529 tests / exit 0** (`audits/evidence/2026-09-24T03-08-19Z-regression-post-content-stop-operator-surface/`); post-deploy `--label regression-post-content-stop-operator-surface-postdeploy` → **identical, 20 / 529 / exit 0** (`audits/evidence/2026-09-24T03-10-22Z-regression-post-content-stop-operator-surface-postdeploy/`); final frozen re-run after the last test edit `--label regression-post-content-stop-operator-surface-final` → **identical, 20 / 529 / exit 0** (`audits/evidence/2026-09-24T03-13-53Z-regression-post-content-stop-operator-surface-final/`); baseline was 19 suites / 507 tests at `8930572` |
| Deployment | **DONE, hashes verified** | `scripts/deploy_e3_runtime.py` 2026-09-24T03:10:14Z copied `e3_commands.py`, `e3_cli.py`, `e3_shadow_orchestrator.py`, `e3_execution_rehearsal.py` (backup `…\exec-brain\backups\e3-deploy-20260924T031014Z`, `eb_py` already-patched); deployed vs repo SHA-256 match for all four plus the unchanged `e3_execution.py` (`6f625a0a…`) |
| E3 Stage 2 / production dispatch / VPS cutover | **NOT ENABLED / NOT PERFORMED** | no readiness, qualification or verification criterion changed; the 0/7 credential gate was not re-run, re-parameterised or re-opened; no unbounded retry path created |
| Still open, deliberately not chased | **RECORDED** | what makes the recitation filter fire on some identical calls and not others; the provider exposes the stop reason but not the filter input, and no unbounded generation may be used to chase it |
| Successor staged | **ONE** | `remote-queue/pending/agent-e4-provider-content-stop-pressure-visibility-2026-09-24.json` — surface recorded content-side stop pressure through the E4/operator resource-continuity status (observation only, 0 provider calls); the pending whole-company acceptance is neither duplicated nor pre-empted |
| Owner action | **NONE NEW** | unchanged dependencies only |

## E4 resource continuity — recorded provider content-side stop pressure — `agent-e4-provider-content-stop-pressure-visibility-2026-09-24`

Ran 2026-09-24T03:22:46Z–03:30:56Z at code SHA `03ebc74`.
Evidence: `audits/evidence/2026-09-24T03-22-46Z-e4-content-stop-pressure/` (`evidence.md`, `evidence.json`).
Provider-call budget: **0 (stated up front)** — stub adapters on the real execution path + isolated
dbs, the recorded `performance_evidence` rows, and the recorded series artifact read verbatim.
No provider series was re-run.

| Item | State | Evidence |
|---|---|---|
| Gap | **CLOSED** | the E4 continuity view measured only tokens/counts/cost-derived exhaustion, so a provider that repeatedly withholds content while still consuming prompt tokens (`promptTokenCount: 17` on every recorded `IMAGE_RECITATION` call) was reported as *healthy capacity* |
| Pressure view | **DONE** | `exec-brain/resource_monitor.py`: `content_stop_pressure()`, `evidence_row_ledgers()`, `recorded_series_ledger()`, `render_content_stop_pressure()`, `build_content_stop_pressure_view()`, `ResourceMonitor.get_content_stop_pressure()`. Per worker/provider/model: attempts observed (classified/unclassified), content-side stops observed, stop rate **with its sample size**, last observed finishReason, last recorded stop time, bounded `content_withheld_at_measurable_rate`; status `unknown`/`clean`/`stops_recorded_below_bound`/`pressured`. Sources never merged; read-only; no new schema; no E1/E2 write |
| Bounded flag | **DONE, documented** | `MEASURABLE_CONTENT_STOP_RATE = 0.2` (just below the only recorded rate for this roster, 2/9 = 0.222) and `MEASURABLE_CONTENT_STOP_MIN_SAMPLE = 5` (the bounded per-node path records at most 3 dispatch attempts). Bounds only bound the flag — rate, sample size, finishReason and stop time are always reported; zero classified attempts reports `unknown`, never a rate and never "clear" |
| Operator surface | **DONE** | `e3-status` prints an `E4 Resource Continuity: provider content-side stop pressure` section; `e3-status --pressure-series <observations.json>` (repeatable, additive) adds a recorded provider series as its own source; a missing E4 module degrades to an explicit "unavailable … deploy it" line instead of breaking E3 status. Captured in `operator_pressure_output.txt` / `operator_pressure_demo.py` |
| Existing recorded state, reported honestly | **CAPTURED** | live-store copy read-only: `performance_evidence` 29 attempts observed / **0 classified** (codex-cli 5, deepseek-v41-flash 13, google-nano-banana-2 11) → `unknown` for all three (rows predate the classification), **never reported healthy**; the recorded series source shows the google pair at 9 attempts / 2 stops → `0.222 (sample size 9)`, finishReason `IMAGE_RECITATION`, `content_withheld_at_measurable_rate = yes` |
| Action | **NONE — observation only** | no automatic worker swap, re-dispatch, failover, retry or safe-mode entry; `test_the_view_writes_nothing_and_acts_on_nothing` proves all table counts are unchanged after the view is built |
| New offline tests | **PASS, 0 provider calls** | `exec-brain/tests/test_e4_content_stop_pressure.py` — **31 tests**, registered in `scripts/evidence_runner.py`: clean provider, recorded stops (truthful rate + finishReason), repeated stops across nodes flagged, zero attempts → unknown, pre-classification rows unclassified, recorded artifact read without modification, operator surface, sources never merged |
| Regression | **PASS — baseline beaten** | pre-deploy `--label regression-pre-content-stop-pressure` → **21 suites / 21 passed / 0 failed / 0 unavailable / 560 tests**, every suite exit 0 (`audits/evidence/2026-09-24T03-23-28Z-regression-pre-content-stop-pressure/`); first post-deploy run failed exactly one test — E1 `test_t13_no_gateway_modification` rejected the newly deployed `resource_monitor.py` in the runtime root (`audits/evidence/2026-09-24T03-25-04Z-regression-post-content-stop-pressure-postdeploy/`) — the allow-list was extended by exactly the deployed module (additive, negative proof: an unexpected probe file still fails and was deleted); final post-deploy `--label regression-post-content-stop-pressure-final-exitcheck` → **21 / 21 / 560 / 0 failed / 0 unavailable, runner exit code 0 (captured)** (`audits/evidence/2026-09-24T03-29-37Z-regression-post-content-stop-pressure-final/`); baseline was 20 suites / 529 tests at `82ddf0` |
| Deployment | **DONE, hashes verified** | `scripts/deploy_e3_runtime.py` 2026-09-24T03:24:48Z copied `e3_commands.py`, `e3_cli.py`, `resource_monitor.py` (E4 module added to the deployed set because the deployed `e3-status` imports it; backup `…\exec-brain\backups\e3-deploy-20260924T032448Z`, `eb_py` already-patched); repo vs deployed SHA-256 `ALL_MATCH` (`e3_commands` `bcd12768…`, `e3_cli` `8c50a33c…`, `resource_monitor` `c138c0ec…`; unchanged `e3_execution` `6f625a0a…`, `e3_shadow_orchestrator` `808b092a…`, `e3_execution_rehearsal` `b482775f…`); the deployed module, imported from the runtime root only, printed the section including the recorded series (`deployed_surface_output.txt`) |
| E3 Stage 2 / production dispatch / VPS cutover | **NOT ENABLED / NOT PERFORMED** | no readiness, qualification or verification criterion weakened; the 0/7 credential gate was not run, re-parameterised or re-opened; no automatic failover/re-dispatch path created |
| Still open, deliberately not chased | **RECORDED** | what makes the recitation filter fire on some identical calls and not others; the provider exposes the stop reason but not the filter input, and no unbounded generation may be used to chase it |
| Owner action | **NONE NEW** | unchanged dependencies only |

## E4 provider content-side stop pressure on the operator surfaces — `agent-e4-content-stop-pressure-operator-brief-integration-2026-09-24`

Ran 2026-09-24T03:36Z–03:44Z at code SHA `ed390db`.
Evidence: `audits/evidence/2026-09-24T03-40-43Z-e4-content-stop-pressure-operator-brief-final/`
(`integration_evidence.md`, `operator_surface_output.txt`, `health_snapshot.json/.md`,
`latest.json/.md`, `evidence.json/.md`, `regression/evidence.json`,
`source_and_deployed_hashes.txt`, `deploy_dry_run.json`).
Provider-call budget: **0 (stated up front)** — recorded rows/artifacts, stubs/fixtures only; no
provider series re-run.

| Item | State | Evidence |
|---|---|---|
| Gap | **CLOSED** | the pressure view was visible only by running `e3-status` by hand; the surfaces the owner reads (operational-services health snapshot, Morning Chief Brief escalation list, E4/E5 drill artifact) did not carry it |
| Health snapshot / Morning Chief Brief | **DONE** | `scripts/operational_services.py`: `content_stop_pressure_status()` (reuses `resource_monitor.build_content_stop_pressure_view`; orchestration store `mode=ro`; declared recorded series consumed verbatim, repeatable `--pressure-series`), `pressure_escalations()`, `render_pressure_lines()`; new check `resource.content_stop_pressure` + **warning**-grade escalation `provider_content_stop_pressure` carrying rate, sample size, last finishReason, bounded flag; Morning Chief Brief carries it in `resource_status` beside the E2 resource status and renders it |
| Honesty rules kept | **DONE** | clean provider → `PASS` and **no** escalation; unclassified/pre-classification sample → `UNKNOWN`, never clear; zero attempts → `unknown`, never a rate; missing/unreadable store or series → `UNKNOWN`/source error, never fabricated; the pressure check adds no `FAIL` and changes no gate |
| First real operator output | **CAPTURED (live, read-only)** | health snapshot check `ATTENTION`, one warning: `google/gemini-3.1-flash-image [worker google-nano-banana-2] stop rate 0.222 at sample size 9 classified recorded dispatch attempts (bounds: rate >= 0.2 AND sample >= 5); last finishReason IMAGE_RECITATION`; store rows still `unknown` (codex-cli 5 / deepseek-v41-flash 13 / google-nano-banana-2 11, 0 classified → 29 observed / 0 classified); verdict `ATTENTION`, `fail_count 0` |
| Drill harness | **DONE** | `exec-brain/e4e5_drill_harness.py`: `D7_content_stop_pressure_observation` records the same read-only view over the harness's isolated drill store (like continuity/outage/convergence): `store_rows_written_by_observation 0` (via `Connection.total_changes`), `provider_calls_spent 0`, unchanged `performance_evidence` rows, operator lines; **36/36 checks** (was 33), `real_provider_calls 0`; the drill store classifies clean → no warning |
| New offline tests | **PASS, 0 provider calls** | `scripts/tests/test_operational_services.py` 17 → **27** (+10) and `exec-brain/tests/test_e4e5_drills.py` 38 → **47** (+9), registered in `scripts/evidence_runner.py`: clean → no warning; pre-classification → unknown not clear; zero attempts → no rate; crossing rate → warning with rate/sample/finishReason/bounded flag; snapshot list + markdown; brief carry + render; store never written (hash + sidecar); absent/undeclared store → unknown; declared series consumed by default; unreadable series recorded as a source error |
| Regression | **PASS — baseline beaten** | post-commit `python scripts/evidence_runner.py --label e4-operator-pressure-integration-final` → **21 suites / 21 passed / 0 failed / 0 unavailable / 579 tests collected / 579 passed, runner exit code 0** (`…/2026-09-24T03-40-43Z-e4-content-stop-pressure-operator-brief-final/regression/`); pre-commit same-change run at `13634b3` → 21 / 579 / exit 0 (`audits/evidence/2026-09-24T03-38-51Z-regression-operator-brief-pressure-integration/`); no suite lost tests (only the two touched suites grew); baseline 21 / 560 at `03ebc74` (20 / 529 at `82ddf0`); final frozen re-run after the evidence/state commit `7580a30` (`--label e4-operator-pressure-integration-final-exitcheck`) → **21 / 21 / 579 / 579, runner exit code 0** (`…/regression-final-exitcheck/`) |
| Deployment | **NONE REQUIRED, NONE PERFORMED** | only `scripts/` + the repo-only drill harness changed; `exec-brain/resource_monitor.py` byte-identical to the deployed copy (`c138c0ec…`); `python scripts/deploy_e3_runtime.py --dry-run` → `copied: []`, exit 0; no runtime module, no E1/E2 file, no store schema, no E1 runtime-root allow-list change |
| Action | **NONE — observation only** | no automatic worker swap, re-dispatch, failover, retry or safe-mode entry; any failover stays an explicit E4/owner decision (stated in every rendered line and escalation item) |
| E3 Stage 2 / production dispatch / VPS cutover | **NOT ENABLED / NOT PERFORMED** | no readiness, qualification or verification criterion weakened; the 0/7 credential gate was not run, re-parameterised or re-opened |
| Still open, deliberately not chased | **RECORDED** | what makes the recitation filter fire on some identical calls and not others; the provider exposes the stop reason but not the filter input, and no unbounded generation may be used to chase it |
| Owner action | **NONE NEW** | the pressure warning is informational; unchanged dependencies only (7 provider credentials still absent, pending whole-company acceptance not pre-empted) |

## Whole-company local acceptance + morning handover — `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`

Ran 2026-09-24T03:57:34Z–04:00Z at code SHA `31eecdb`.
Evidence: `audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/`
(`acceptance.md`, `results.json`, `roster_account.json/.md`, 13 sub-artifact directories).
Provider-call budget: **0 (stated up front)**; external mutations: **0**.

| Item | State | Evidence |
|---|---|---|
| Acceptance verdict | **PASS** | 34 steps — **33 PASS, 0 FAIL, 1 owner-gated (credential presence probe), 0 unavailable**; `canonical_workbooks_unchanged: true` |
| Driver | **NEW (roster C01)** | `scripts/whole_company_acceptance.py` — orchestrates the existing verified surfaces as real subprocesses, incremental `results.json`, fail-closed (an unavailable/unparsable step is never a pass; a broken evaluator is `unavailable`) |
| Regression | **PASS** | `scripts/evidence_runner.py` inside the run: **21 suites / 579 collected / 579 passed / 0 failed / 0 errors / 0 unavailable**, every suite exit 0 (`…/regression/evidence.json`). Baseline at sprint start: 15 suites / 438 tests |
| E3 delegation/verification + E4/E5 | **PASS** | drill harness **36/36 checks**, `real_provider_calls = 0`, `stub_dispatches = 10`, `evidence_kind = stubbed_provider_failure` |
| Chief intake / E1 / E2 | **PASS** | E1 classify + quality-floor/integrity audit PASS; E2 governor verify PASS; E2 resource brief + telemetry exit 0 |
| E3 store | **PASS** | `e3-verify-db`: schema v2, all required tables present |
| Remote queue + watchdog | **PASS (read-only)** | 9 tasks inspected, 2 configured to survive a reboot; 8 Chief tasks + the legacy donor; no task created/modified/deleted |
| Discord sync | **PASS (dry-run)** | `scripts/sync_discord_chief.py --dry-run` — nothing published by this task |
| Career Ops records | **PASS** | `run_acceptance.py` (scan → eligibility → dedupe → tracker write on a dated copy → Chief summary) + `career_ops_cli inventory`; rollover acceptance PASS |
| Regional jobs | **PASS** | lanes ready; UK/Dubai/Japan/Singapore offline eligibility + dedupe replays of recorded scans |
| Company Watch | **PASS** | registry parse + handoff interface dry-run against the canonical workbook (recorded findings + 3 labelled ineligible test rows; hash unchanged) |
| Application status | **PASS** | `run_application_inbox_acceptance.py` (fixture + runtime-synthesised mailbox; store byte-identical on repeat) |
| JobBrief / CV / cover letter / reviewer / gate | **PASS** | `run_job_intelligence_acceptance.py` (incl. a tampered pack being blocked) |
| LinkedIn read-only / drafts / interview prep | **PASS** | `run_cv_linkedin_acceptance.py` + `run_interview_prep_acceptance.py`; 0 network calls, 0 account mutations, unsent drafts |
| Career brief | **PASS** | `run_daily_brief_acceptance.py` + `daily_brief.py status` (scheduled 07:00; delivery channel `not_verified`) |
| Morning Chief Brief / health | **PASS** | verdict `ATTENTION`, `fail_count 0`, attention 2; brief active 2 / blocked 12 / owner actions 18 / escalations 3 |
| Owner escalation / external-action refusal | **PASS** | `submission_gate.py guard --action submit_application` refuses; drill D2 escalation recorded |
| Backup / restore | **PASS** | operational backup + log-rotation **dry-run** exit 0; backup/restore/rollback drill `status: PASS`, 10 artifacts |
| Deployment preflight | **PASS** | verdict **GO**, 11 checks, 0 FAIL, 1 WARN (credentials absent, owner-gated) |
| Credentials | **OWNER_GATED** | presence-only probe: 7/7 API worker credentials absent — owner action, not a defect |
| Roster account | **50/50, no omission** | 47 PASS, 3 READY_NEEDS_OWNER_CONFIG (B12, B14, C03), 0 BLOCKED_EXTERNAL, 0 unmapped + 10 supplementary owner-gated items (`roster_account.md`) |
| Morning handover | **PRODUCED** | `handovers/2026-09-24-morning-handover.md` |
| Attempt-1 defect | **RECORDED, FIXED** | the runner's persistence evaluator assumed `tasks` was a list (it is a keyed object) and died after 9 PASS steps; partial record preserved under `audits/evidence/2026-09-24T03-51-07Z-whole-company-acceptance-attempt1-partial/` with a NOTE; evaluator fixed + fail-closed guard added |
| E3 Stage 2 / production dispatch / VPS cutover | **NOT ENABLED / NOT PERFORMED** | no readiness, qualification or verification criterion weakened; the 0/7 credential gate was not re-run or re-staged |
| Owner action | **NONE NEW** | pre-existing dependencies only (7 provider credentials, Gmail read-only OAuth, research provider, work authorisation, deployment architecture/VPS, laptop audit, reboot confirmation, legacy task disposition, optional decisions) |
