# Bridge validation — hardened Hermes remote bridge

- Task: `agent-bridge-watchdog-validation-2026-09-23`
- Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
- Run (UTC): 2026-09-23T21:18Z
- Base SHA: `07dd4a1` (inspected commits `617fd47c`, `b83c9ad`)
- Structured checks: `bridge_checks.json` (same directory)
- Suite evidence for the full baseline: `evidence.json` / `evidence.md` (same directory)

## Result

PASS. Every claim in the task contract that was in scope was verified against the code and
against executed tests. **No bridge defect was found, so no production code was changed.**

## What was verified

1. **No-stream-event watchdog (default 300s, `HERMES_REMOTE_IDLE_TIMEOUT`).**
   `remote_queue/visible_worker.py:38-43` reads the bound; `:248-266` fires only while the child is
   alive, the bound is positive, and no stream event has arrived for that many seconds. Exercised
   with a 2s test-only bound against a silent fake child; the production 300s bound was never waited
   on. A bound of `0` disables the watchdog rather than inverting it (separate test).
2. **Targeted child-tree termination only.** `visible_worker.py:123-147` uses
   `taskkill /PID <child pid> /T /F` with a `terminate()`/`kill()` fallback. A static check asserts the
   PID-scoped form and asserts `"/IM"` never appears; the executed test asserts the fake child is
   actually dead afterwards. No unrelated process was touched.
3. **Hard task bound (default 1200s, `HERMES_REMOTE_TASK_TIMEOUT`).** `hermes_dispatch.py:169-173`
   resolves the bound, `:226` applies it to the helper wait, `:229-234` kills the helper tree on
   expiry. Observed `timeout=1200` with no override and `timeout=137` with the env override; an
   expired bound returns `blocked` / `execution_error`.
4. **Watchdog exit code 124 is truthful.** `visible_worker.py:295-302` forces `rc = 124` and writes
   `124` to the exit file when the watchdog fires; `hermes_dispatch.py:252-267` turns that into
   `status: blocked`, `blocker_category: execution_error`, summary `… hit the <N>s no-progress
   watchdog`. A 124 is never parsed as a completed task, and no final response text is fabricated for
   a watchdog kill (the output file stays empty).
5. **Frozen running contract + standing approvals in the generated prompt.**
   `hermes_dispatch.py:79-80` emits both rules, with the task id interpolated into
   `remote-queue/running/<task_id>.json`. The contract this run actually received carried both
   sentences verbatim, and this run did not rewrite its own running record.
6. **Isolation.** The new suite runs only in per-test temp directories, launches no real Hermes
   process (the "Hermes" child is a throwaway local python script or a fake process object), and the
   existing `TestIsolationGuards` + module tear-down snapshot guard still pass.

## Tests actually run

| Scope | Command | Result |
|---|---|---|
| Compile | `python -m py_compile remote_queue/visible_worker.py remote_queue/hermes_dispatch.py remote_queue/poller.py remote_queue/tests/test_queue.py` | `COMPILE_OK` |
| New bridge suite | `python -m unittest remote_queue.tests.test_bridge_watchdog -v` | 12 / 12 passed, exit 0 |
| Isolated queue suite | `python -m unittest discover -s remote_queue/tests -v` | 30 / 30 passed, exit 0 |
| Full baseline | `python scripts/evidence_runner.py --label bridge-watchdog-validation` | 11 suites, 335 / 335 passed, 0 failed, exit 0 |

Baseline moved from 323 to 335 tests; the delta is exactly the 12 new bridge tests. The bridge suite
was added to `scripts/evidence_runner.py` so the recorded regression baseline stays truthful.

## Findings recorded but deliberately not changed

- `remote_queue/poller.py:197-212` still routes task ids containing `operational` / `bridge-validation` /
  `e2e` to hardcoded stub handlers that return fabricated `completed` payloads with no execution
  evidence. This is already recorded as a deliberately unfixed defect in
  `state/current_company_state.md:170-172`. The validated task id matches none of those patterns and
  was correctly dispatched to `dispatch_task`, so this is out of the validated path; changing live
  routing was out of scope for a bounded bridge check.
- `_terminate_child_tree` returns after `taskkill` without checking its return code, so the documented
  `terminate()`/`kill()` fallback is only reachable if `taskkill` raises. In practice the watchdog
  retries once per second while the child is alive and the 1200s hard bound is the outer backstop, so
  this was left alone rather than changed without a reproduced failure.

## Handoff before exit

- No E3 rehearsal retry was pending or running with a healthy worker at exit time (the previous
  rehearsal is `blocked/` on `execution_error` and the umbrella record has no worker).
- Staged one bounded successor: `remote-queue/pending/agent-e3-local-production-rehearsal-retry-2026-09-23.json`
  — a formal production-rehearsal re-run on the now-built execution leg, explicitly scoped not to race
  or duplicate `agent-e3-image-diagnosis-and-multiworker-execution-2026-09-23` (already pending and
  left unchanged).
- Stage 2 remains disabled; this task did not enable it, weaken a criterion, or treat approval text as
  evidence. A new owner directive landed on the authority during this run (`a58549c` / `2d5f332` /
  `d7e718c`, "Owner directive update — 2026-09-23 late evening"): do not enable local Stage 2
  overnight; complete it only after Mukund configures all remaining provider credentials on
  2026-09-24 and the readiness gates are re-run. The staged retry contract was aligned to that
  directive.
