# Full-Build Tracker

Status: ACTIVE. Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`.

Provenance: no in-repo tracker file existed at 2026-09-23T20:22:00Z. This file records verified
facts only, each with its evidence source.

Evidence source for every test figure below (supersedes the earlier 20:21:03Z run):
`audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-regression/evidence.json`
(run 2026-09-23T20:55:13Z, code SHA `4ac1a22`, 8 suites, 295 collected, 295 passed,
0 failed, 0 errors, 0 skipped, all suites exit 0).

Production-rehearsal evidence:
`audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-run/evidence.json`
(run 2026-09-23T20:55:13Z, code SHA `4ac1a22`).

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
| E3 | **Production rehearsal (real orchestration path)** | **EVIDENCED** | 24/24 pass, exit 0; 5 executable scenarios incl. verifier rejection → targeted repair → re-verification PASS, unrepaired rejection → replan + escalation, no-qualified-route → escalation, multi-node integrator flow, conflict detection. Evidence dir `…-e3-production-rehearsal-run` |
| E3 | Simulation-evidence isolation | **PROVEN** | production stores SHA-256 unchanged before/after; rehearsal evidence sink fail-closed against production stores |
| E3 | E1/E2 public-interface boundary | **VERIFIED** | static scan: 0 direct SQL to E1/E2 stores; E2 public `governor.record_request()` exercised against an isolated store |
| E3 | Stage 1 shadow implementation set | PRESENT | component list in state file; commits `617e69cb`, `aae7d036` preserved |
| E3 | **Production execution leg (orchestrator → worker adapter dispatch)** | **MISSING** | no orchestrator→adapter dispatch exists anywhere; `ExecutionAdapter(` instantiated only in `codex_adapter.py` smoke test |
| E3 | E3 orchestration modules deployed to runtime root | **MISSING** | none of the `e3_*.py` orchestration modules exist in `%LOCALAPPDATA%\hermes\exec-brain`; only `e3_commands.py` |
| E3 | `e3-*` CLI bindings in runtime `eb.py` | **MISSING** | no `e3-*` command names in `eb.py` |
| E3 | Stage 2 local production enablement | **CONDITIONALLY APPROVED, NOT ENABLED** | standing conditional owner approval 2026-09-23; unmet precondition recorded (production execution leg missing) |
| E3 | Real E3 path defects (found this run) | 3 FIXED | node_id mismatch, verification_type/method mismatch, conflict-handler nondeterminism (commit `4ac1a22`) |
| E4 | Resource continuity implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E4 | Checkpoint/failover drill evidence on real execution paths | OPEN | not evidenced |
| E5 | Safe mode / resilience implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E5 | Failure-drill evidence on real execution paths | OPEN | not evidenced |
| Providers | DeepSeek (deepseek-flash) | ROUTABLE, QUALIFICATION UNPROVEN | live model observed; smoke PASS; E2 linkage verified |
| Providers | Google image worker | ROUTABLE, QUALIFICATION UNPROVEN | smoke PASS; E2 linkage verified |
| Providers | Codex CLI | ROUTABLE, QUALIFICATION UNPROVEN | re-validated 2026-09-23: stable resolver, smoke PASS, E2 linkage verified, model identity UNKNOWN |
| Providers | 7 generic API workers | NOT READY | owner-local credentials / live readiness missing |
| Deployment | Architecture decision | DEFERRED BY OWNER | owner direction: prove local operation first; laptop-primary + GitHub control plane + VPS watchdog/failover is a recorded *preference*, not a final decision |
| Deployment | VPS access/details | NOT PROVIDED | owner dependency |
| Deployment | Non-architecture-dependent deployment preparation | NOT STARTED THIS RUN | out of scope of the 2026-09-23 rehearsal task |

## Owner gates (must not be bypassed)

1. E3 Stage 2 **local** production enablement — standing conditional approval granted
   2026-09-23; must not be enabled until every recorded precondition is objectively satisfied.
   The production execution leg is currently the unmet precondition. **Not enabled.**
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
  node outputs that legitimately differ only in per-node metadata (e.g. artifact name) are
  therefore reported as `factual_disagreement`. Detection is now deterministic; the heuristic's
  precision is a known limitation, not a correctness defect.

## Next bounded task

Staged in `remote-queue/pending/`: the successor builds the E3 production execution leg
(orchestrator → real worker `ExecutionAdapter` dispatch, DAG/state + evidence persistence,
deterministic verification wiring, runtime deployment of the E3 modules and `e3-*` CLI), re-runs
the production rehearsal with real worker execution, re-evaluates Stage 2, and only then proceeds
to E4/E5 real-path drills.
