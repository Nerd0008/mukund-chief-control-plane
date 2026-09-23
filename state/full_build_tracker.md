# Full-Build Tracker

Status: ACTIVE. Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`.

Evidence source for every test figure below (supersedes the earlier 20:55:13Z run):
`audits/evidence/2026-09-23T21-11-03Z-e3-production-execution-leg-regression/evidence.json`
(run 2026-09-23T21:11:03Z, code SHA `6c19a01`, 10 suites, 323 collected, 323 passed,
0 failed, 0 errors, 0 skipped, all suites exit 0).

Real-execution evidence (NEW):
`audits/evidence/2026-09-23T21-10-00Z-e3-production-execution-rehearsal/evidence.json`
(+ `evidence.md`, `deployment_check.json`) — real worker execution on the local E3 path,
5 bounded provider calls.

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
| E3 | Production rehearsal (Stage-1 orchestration path) | EVIDENCED | 24/24 pass, exit 0; 5 executable scenarios incl. verifier rejection → targeted repair → re-verification PASS |
| E3 | Simulation-evidence isolation | PROVEN | production stores SHA-256 unchanged before/after; rehearsal evidence sink fail-closed |
| E3 | E1/E2 public-interface boundary | **VERIFIED** | static scan: 0 direct SQL to E1/E2 stores from any `exec-brain/*.py`; E2 `governor.record_request()` exercised against an isolated store and, on the real path, against the live store (5 rows) |
| E3 | **Production execution leg (orchestrator → worker adapter dispatch)** | **BUILT + EVIDENCED** | real dispatch to deepseek-v41-flash (×2), codex-cli (×1) all COMPLETE with persisted DAG/evidence rows and E2 linkage; credential-missing worker refused with 0 provider calls; 18/18 + 10/10 new tests |
| E3 | Deterministic verification gates COMPLETE | **ENFORCED** | a node reaches COMPLETE only after a verification PASS; no-test-case nodes are BLOCKED without a dispatch (asserted in `tests/test_e3_execution.py`) |
| E3 | E3 orchestration modules deployed to runtime root | **DONE** | 29/29 required modules present, `missing_modules: []` (`deployment_check.json`) |
| E3 | `e3-*` CLI bindings in runtime `eb.py` | **DONE** | all 10 bindings present; `eb.py e3-status` / `e3-plan` / `e3-verify-db` / `e3-execute` (dry run) verified in-run |
| E3 | Google image worker real dispatch | **FAILED / UNRESOLVED** | provider returned no image part; 17 prompt tokens, no output tokens; root cause undetermined. Only 1 call spent |
| E3 | Real dispatch on a decomposed multi-worker plan | OPEN | only single-node plans dispatched this run |
| E3 | Worker qualification evidence | OPEN | every worker remains UNPROVEN; smoke readiness ≠ qualification |
| E3 | Stage 2 local production enablement | **NOT ENABLED (owner instruction)** | live contract `1ba7f43`: do not enable Stage 2 or production dispatch in this task regardless of outcome; preconditions re-evaluated, none weakened |
| E3 | Truth defects found and fixed | 3 FIXED | gemini output-token mapping; `e3_commands` hardcoded schema version; rehearsal CLI-binding detector |
| E4 | Resource continuity implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E4 | Checkpoint/failover drill evidence on real execution paths | OPEN | gated: the contract asks for this only if Stage 2 is enabled, which it is not |
| E5 | Safe mode / resilience implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E5 | Failure-drill evidence on real execution paths | OPEN | gated: same as E4 |
| Providers | DeepSeek (deepseek-flash) | ROUTABLE, REAL EXECUTION OK, QUALIFICATION UNPROVEN | real dispatch COMPLETE ×2; provider usage captured; E2 linkage verified |
| Providers | Codex CLI | ROUTABLE, REAL EXECUTION OK, QUALIFICATION UNPROVEN | real non-interactive dispatch COMPLETE; served model identity UNKNOWN; usage not exposed |
| Providers | Google image worker | ROUTABLE, REAL EXECUTION FAILED, QUALIFICATION UNPROVEN | real dispatch returned no image part |
| Providers | 7 generic API workers | NOT READY (correctly refused) | routable=false; the execution leg refused a dispatch with 0 provider calls |
| Deployment | E3 module deployment to local runtime root | DONE | `scripts/deploy_e3_runtime.py`; per-file backup + SHA-256 manifest + `--restore` |
| Deployment | Architecture decision | DEFERRED BY OWNER | owner direction: prove local operation first; laptop-primary + GitHub control plane + VPS watchdog/failover is a recorded *preference*, not a final decision |
| Deployment | VPS access/details | NOT PROVIDED | owner dependency |
| Deployment | Non-architecture-dependent deployment preparation | PARTIAL | the deploy script + manifest give a reproducible local runtime procedure; no VPS work performed |

## Owner gates (must not be bypassed)

1. E3 Stage 2 **local** production enablement — **currently prohibited by direct owner instruction**
   (live contract `1ba7f43`): do not enable in this task regardless of outcome; record the remaining
   conditions for a separate owner decision. The older standing conditional approval is not
   exercised. **Not enabled.**
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

## Next bounded task

Staged in `remote-queue/pending/`: diagnose the Google image real-dispatch failure with a bounded
diagnostic call, then exercise the real dispatch path on a decomposed multi-worker plan with
per-node deterministic verification, and record evidence toward worker qualification. Stage 2 /
production dispatch remains disabled pending a separate explicit owner decision.
