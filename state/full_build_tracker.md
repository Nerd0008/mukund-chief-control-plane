# Full-Build Tracker

Status: ACTIVE. Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`.

Provenance: no in-repo tracker file existed at 2026-09-23T20:22:00Z. The
"Master Project Tracker" produced in earlier sessions
(`Mukund_Chief_of_Staff_Master_Project_Tracker_2026-09-23.docx/.pdf`) is a local
conversation artifact, not a repository file, and has NOT been reconciled by this
run. This file is therefore the first in-repo tracker and records verified facts
only, each with its evidence source. It supersedes nothing.

Evidence source for every test figure below:
`audits/evidence/2026-09-23T20-21-03Z-isolated-queue-recovery/evidence.json`
(run 2026-09-23T20:21:03Z–20:21:49Z, code SHA `40f8f683`, 7 suites, 267 collected,
265 passed, 2 environmental errors, 0 skipped).

## Lane status

| Lane | Item | Status | Evidence |
|---|---|---|---|
| Queue bridge | Remote queue + `agent-*` dispatch to Hermes CLI | OPERATIONAL | queue.log pickups; `remote_queue/hermes_dispatch.py` |
| Queue bridge | Visible worker streaming | HARDENED | commit `e643fd162cf2b627d734b5735e205de3d00387a4` (UTF-8 + errors=replace + fail-closed reader) |
| Queue bridge | Queue test isolation | DONE | `remote_queue/tests/test_queue.py` — 30/30 pass, guard tests + whole-suite live-state check |
| Queue bridge | Queue lifecycle defects | 4 FIXED, 1 RECORDED | see state/current_company_state.md §Remote Task Queue |
| E1 | Runtime + test matrix | VERIFIED | 32/32 pass, exit 0 |
| E2 | Governor + provider adapters | VERIFIED | 45/45 pass, exit 0 (runtime import root `%LOCALAPPDATA%\hermes\exec-brain`) |
| E3 | Baseline suite | 48/50 PASS | 2 errors: Codex CLI binary not installed; exit 1 |
| E3 | Baseline Codex test identities | ENVIRONMENTAL | `TestCodexAdapter.test_codex_cli_version`, `TestCodexAdapter.test_codex_smoke_blocked` — `RuntimeError: Codex CLI not found: checked configured path and PATH` (`exec-brain/codex_adapter.py:28`) |
| E3 | Extended suite | VERIFIED | 60/60 pass, exit 0 |
| E3 | Shadow orchestrator composition | VERIFIED | 13/13 pass, exit 0 |
| E3 | Stage 1 shadow implementation set | PRESENT | component list in state file; commits `617e69cb`, `aae7d036` preserved |
| E3 | Production rehearsal / executable rejection + repair evidence | OPEN | not evidenced; composition tests are not rehearsal. This is the unmet precondition for the standing conditional Stage 2 approval |
| E3 | Stage 2 local production enablement | CONDITIONALLY APPROVED, NOT ENABLED | standing conditional owner approval 2026-09-23 (authority `3838c61`, owner-actions `baf73d8`); preconditions not all met |
| E4 | Resource continuity implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E4 | Checkpoint/failover drill evidence on real execution paths | OPEN | not evidenced |
| E5 | Safe mode / resilience implementation | PRESENT, unit-tested | included in the 37/37 combined suite |
| E5 | Failure-drill evidence on real execution paths | OPEN | not evidenced |
| Providers | DeepSeek (deepseek-flash) | ROUTABLE, QUALIFICATION UNPROVEN | live model observed; smoke PASS; E2 linkage verified |
| Providers | Google image worker | ROUTABLE, QUALIFICATION UNPROVEN | smoke PASS; E2 linkage verified |
| Providers | Codex CLI | BLOCKED ON RE-VALIDATION | allowance reported reset by owner; adapter present; no execution evidence |
| Providers | 7 generic API workers | NOT READY | owner-local credentials / live readiness missing |
| Deployment | Architecture decision | DEFERRED BY OWNER | owner direction: prove local operation first. Laptop-primary + GitHub control plane + VPS watchdog/failover is a recorded *preference*, not a final decision |
| Deployment | VPS access/details | NOT PROVIDED | owner dependency |
| Deployment | Non-architecture-dependent deployment preparation | NOT STARTED THIS RUN | out of scope of the 2026-09-23 recovery task |

## Owner gates (must not be bypassed)

1. E3 Stage 2 **local** production enablement — standing conditional approval granted
   2026-09-23; must not be enabled until every recorded precondition (including
   production rehearsal evidence) is objectively satisfied.
2. Deployment architecture choice and VPS cutover — deferred by owner until the local system is
   proven; the recorded laptop-primary preference is not a decision and cutover is not authorized.
3. Seven provider credentials provisioned locally (never via GitHub/queue/logs).
4. Anything irreversible or destructive.

## Known truth defects (recorded, not silently resolved)

- `poller.handle_task` routes any task id containing "operational" to
  `handle_operational_build()`, which returns a hardcoded status with no execution
  evidence. `full-operational-build-2026-09-24` therefore must not be read as
  evidence that its listed steps ran.
- The umbrella record remains in `running/` with no associated worker process.
- `.bridge-stash/` in the repository contains two py files tracked from an earlier
  bridge autostash; one (`safe_mode.py`) differs from the live `exec-brain/`
  version. Flagged for owner/coordinator decision on whether it should be removed.

## Next bounded task

`agent-codex-reset-revalidation-2026-09-23` — already staged in
`remote-queue/pending/` by commit `f80eefc8a8375f46af5b528e8d8fd93dab125f04`
("queue: stage Codex reset revalidation after recovery"), so this recovery did not
create a duplicate task definition. The singleton poller is expected to pick it up
only after this recovery task terminates; it must not run concurrently with it.
