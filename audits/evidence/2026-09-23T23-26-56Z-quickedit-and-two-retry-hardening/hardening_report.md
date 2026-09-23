# QuickEdit/Select console hardening + bounded two-retry recovery

- Task: `agent-visible-worker-console-quickedit-hardening-2026-09-23`
- Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
  (owner directives: "Worker failure retry policy — owner directive 2026-09-24",
  "Stage-2 credential gate anti-loop directive")
- Run (UTC): 2026-09-23T23:28Z
- Base SHA at test time: `2fbe2f4` (`agent-visible-worker-console-quickedit-hardening-2026-09-23` claim)
- Structured checks: `hardening_checks.json` (same directory)
- Isolated suite evidence for the whole baseline: `evidence.json` / `evidence.md` (same directory),
  label `quickedit-and-two-retry-hardening` — 14 suites, 400/400 tests passed, 0 failed
- Test-run SHA note: `evidence.json` records `code_sha = 2fbe2f4`, i.e. the HEAD at run time;
  the changes below were still uncommitted at that moment. The commit that lands them is recorded
  in `hardening_checks.json` and in the task's completion record.

## Result

COMPLETED. Both halves of the objective are implemented, bounded and covered by isolated
regression tests, with real-console evidence for the Windows part.

## 1. QuickEdit / Select mode can no longer suspend the worker

Root cause (evidence-based, not inferred): the observed window title
`Select Administrator: Hermes Remote Worker ...` is the classic console mark/QuickEdit title
prefix. In a classic Windows console, once a click/drag puts the console into select (mark) mode,
the next write to that console suspends the process until a key is pressed. `visible_worker.py`
printed its progress *and its watchdog from the same thread*, so the incident could suspend both
the worker and its 300s no-progress watchdog — while the dispatched task had already landed its
commit but the wrapper stayed open.

Fix 1 — per-console mode change (`remote_queue/visible_worker.py`):

- `disable_quick_edit_for_this_console()` opens **this process's own** console input buffer
  (`CreateFileW("CONIN$")`), reads the input mode, clears `ENABLE_QUICK_EDIT_MODE` (0x0040) and
  ensures `ENABLE_EXTENDED_FLAGS` (0x0080) is set, then verifies the result.
- Scope is this worker console only: the window stays visible, no global/registry console
  preference is read or written, and no other process's console is attached to, allocated, freed,
  or enumerated (asserted by source-inspection test).
- It runs before the first progress line, so the console is hardened before the child is launched.
- If it cannot be applied, the exact limitation is printed
  (`Console QuickEdit hardening: UNAVAILABLE (<reason>); global console settings left unchanged
  and the worker window stays visible.`) and the worker continues unchanged — matching the task's
  "record the exact limitation and leave global settings unchanged" stop condition.

Fix 2 — a jammed console can no longer stall the control path:

- Console output is serialised through a bounded writer thread (`_ConsoleWriter`); the progress
  loop, the stream reader, the watchdog and the exit-file bookkeeping never block on a console
  write. If the queue fills, lines are dropped and counted and reported, never allowed to stall.
- The no-progress watchdog now also runs in its own thread, terminates the Hermes child tree
  **before** it prints anything, and both firing paths are idempotent. The in-loop watchdog check
  is retained unchanged as a second fail-closed backstop (existing 300s default,
  `HERMES_REMOTE_IDLE_TIMEOUT`, exit code 124 and `taskkill /PID <child> /T /F` semantics are
  untouched, and the existing bridge regressions still pass).
- Stream activity is now recorded by the stream reader, so the watchdog measures stream silence
  rather than how quickly a possibly-stalled consumer drains its queue.

Real-console evidence (not simulated), `scripts/quickedit_console_probe.py`:

```json
{
  "applied": true, "changed": true, "reason": "ok",
  "mode_before": 503, "mode_after": 439,
  "quick_edit_before": true, "quick_edit_after": false,
  "scope": "this-process-console-only"
}
```

503 -> 439 is exactly the QuickEdit bit (0x40) being cleared on a live console with all other
input-mode bits preserved. The probe changed only the probing process's own console instance
(the Hermes terminal session console). No registry/HKCU value, no shortcut property and no
owner-level console preference was written, and the worker's launcher
(`run_poller_hidden.vbs` -> `poller.py` -> `CREATE_NEW_CONSOLE`) is unchanged, so the visible
worker window requirement is preserved.

## 2. Recoverable failures retry the same task twice, then park

New policy module `remote_queue/retry_policy.py` (single source of truth):

- `MAX_RETRIES = 2`, `MAX_ATTEMPTS = 3` — initial attempt plus at most two automatic retries.
- Retryable: `execution_error` only — the class that covers transient CLI/tool errors, wrapper
  launch failures, hard-timeout (1200s) expiry, the no-progress watchdog kill (exit 124), and a
  handler crash.
- Never retried (park immediately, continue other work): `credentials`, `owner_approval`,
  `architecture`, `safety`, `irreversible_action`, `external_provider`. The Stage-2 0/7
  provider-key gate is therefore still covered by the anti-loop directive and cannot self-requeue.
  An unknown/missing `blocker_category` on a blocked result also parks (fail closed: transient
  cannot be proven).
- The bound is structural: `plan_retry()` cannot return "retry" beyond the budget, and the poller
  additionally refuses to re-execute a task whose persisted budget is already exhausted, so no
  input can produce an unbounded loop.

Deterministic, auditable attempt state (`remote_queue/queue_schema.py`):

- `record_execution_attempt()` writes `execution_attempts[]` (attempt number, UTC time, status,
  blocker category, summary, retry decision, reason) and `retry_state`
  (`attempts_used`, `retries_used`, `max_attempts`, `max_retries`, `last_blocker_category`,
  `next_action`, `reason`) to `remote-queue/running/<task_id>.json` **before** the next attempt,
  and publishes it with the normal queue commit/push path.
- `read_retry_state()` + `next_attempt_number()` let the poller resume the same bounded count after
  a restart instead of restarting the retry loop.
- `poller._run_task_with_bounded_retry()` owns the loop; `poll run_poll_cycle()` delegates to it.
  After the second failed retry the task is marked blocked with the last blocker category and the
  poller advances.
- Landed work is preserved across attempts: retries are labelled with the attempt number, the
  visible console shows `Attempt: N`, and the generated prompt gains a `RETRY CONTEXT` block that
  instructs the agent to re-inspect repository/queue state first, keep commits and evidence already
  produced by earlier attempts, resume from the smallest unfinished unit, and report a genuine
  deterministic blocker truthfully instead of re-doing work. The running task contract file itself
  is never rewritten by this task.

## Tests actually run (this run)

| Scope | Command | Result |
|---|---|---|
| Compile | `python -m py_compile remote_queue/visible_worker.py remote_queue/hermes_dispatch.py remote_queue/poller.py remote_queue/queue_schema.py remote_queue/retry_policy.py` | `COMPILE_OK` |
| New console suite | `python -m unittest remote_queue.tests.test_console_quickedit -v` | 12 / 12 passed, exit 0 |
| New retry suite | `python -m unittest remote_queue.tests.test_worker_retry -v` | 24 / 24 passed, exit 0 |
| Existing bridge suite | `python -m unittest remote_queue.tests.test_bridge_watchdog -v` | 12 / 12 passed, exit 0 |
| Existing queue suite | `python -m unittest remote_queue.tests.test_queue -v` | 30 / 30 passed, exit 0 |
| Whole remote_queue package | `python -m unittest discover -s remote_queue/tests` (x3 runs) | 78 / 78 passed each run, exit 0 |
| Full baseline (14 suites) | `python scripts/evidence_runner.py --label quickedit-and-two-retry-hardening` | 14 suites / 400 tests, 400 passed, 0 failed, exit 0 |
| Real console probe | `python scripts/quickedit_console_probe.py` | applied=True, quick_edit_after=False (see above) |

The two new suites were registered in `scripts/evidence_runner.py`, so the recorded regression
baseline stays truthful. The full-baseline delta also includes unrelated suites that other
in-flight queue work already extended; the remote_queue package contributes exactly 78 tests
(30 existing queue + 12 existing bridge + 12 new console + 24 new retry).

Key regressions asserted (each fails against the pre-fix code):

1. `test_watchdog_still_fires_and_records_124_while_console_writes_block` — with the console sink
   deliberately blocked (mark-mode simulation), the worker still kills the Hermes child, writes
   `124` to its exit file, writes no fabricated response, and returns in under 15s instead of
   hanging on the console.
2. `test_console_writer_never_blocks_its_caller_and_counts_drops` — `say()` never blocks against a
   stalled console, drops are counted, and the bounded drain always returns.
3. `test_console_stall...` / `test_disables_quick_edit_on_this_console_only` — QuickEdit is cleared
   with the exact mode write to the process's own handle, unrelated input modes are preserved, and
   the handle is closed.
4. `test_worker_reports_the_exact_limitation_when_no_console_exists` — no console attached =>
   truthful `UNAVAILABLE (no-console-attached)` line, no write, worker still completes.
5. `test_recoverable_failure_is_retried_twice_then_blocked` — exactly attempts [1,2,3], then
   blocked with the retry metadata persisted and published; never a 4th execution.
6. `test_deterministic_blockers_park_on_the_first_attempt` (all five non-retryable categories) and
   `test_stage2_missing_key_gate_is_not_retried` — exactly one attempt, parked.
7. `test_resume_continues_from_persisted_attempt_count` / `test_exhausted_persisted_budget_is_not_re_executed`
   — a restart resumes the bounded count; an exhausted budget never re-runs.

## Limitations recorded truthfully

- The real-console probe proves the mode change on a live console of this host, but no *automated*
  test drives a real console window (the suites inject a fake console API / blocked sink). Verifying
  the visual window behaviour required a visible console and was deliberately not automated.
- `remote-queue/running/full-operational-build-2026-09-24.json` and the other state files
  (`state/current_company_state.md`, `state/full_build_tracker.md`) carried unrelated uncommitted
  work from the parent umbrella run, so this task did not touch them; the truthful record of this
  change lives in this evidence directory, `remote_queue/README.md` and the queue history.
- No scheduled task was installed, stopped, or modified; no worker console window was launched by
  the tests; no global console preference was changed.
