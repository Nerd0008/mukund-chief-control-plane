# Company Registry gap audit + non-E3 runtime service validation

- Task: `agent-company-registry-gap-audit-and-runtime-services-2026-09-23` (remote queue, running→completed)
- Date: 2026-09-23 (local, UTC+01:00)
- Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
- Execution window: claimed by `HermesRemoteQueuePoller` at 2026-09-23T22:22:06Z; inspection, fixes,
  tests and the evidence commit completed by ~22:32Z. The `2026-09-23T22-30-00Z-…` directory name is
  a nominal artifact label, not a claim about the exact second of execution.
- Method: read `state/v1-agent-roster.md` and the Sep 21/Sep 23 handovers first, then inspect the actual
  machine (Windows scheduled tasks, Hermes skills/hooks/cron, remote-queue state, Career Ops dirs,
  Discord sync/archive, legacy donor systems, canonical trackers) and run the new deterministic
  inventory worker `scripts/company_inventory.py`. Read-only against every external system.

## 1. Machine inventory (raw facts)

`inventory.json` in this directory is the machine-readable output of `scripts/company_inventory.py`.

- Roster items parsed from the master roster: **50** (A01–A22, B01–B24, C01–C04).
- **Unmapped roster ids: 0.** Every roster id has a declared state/coverage entry in the worker's
  `ROSTER_COVERAGE` map (active, built+evidenced, or a named pending/running task). No roster item
  is silently omitted.
- Owned Windows scheduled tasks found: **7**; **unmapped owned tasks: 0**.
- Remote queue at audit time: **13 pending / 2 running / 9 blocked / 12 completed**.

### Scheduled tasks owned by the organisation

| Task | Roster | State | Last run | Last result |
|---|---|---|---|---|
| `Hermes_Gateway` | A19 | active — at logon, restart-on-failure, `StartWhenAvailable` | 21-09-2026 17:59:42 | 0 |
| `ChiefDiscordSync` | A19 | active — 30-min repetition | 23-09-2026 23:06:01 | 0 |
| `HermesRemoteQueuePoller` | A18 | active — 2-min repetition, currently `Running` | 23-09-2026 23:26:01 | 0x800710E0 (recorded, meaning unresolved) |
| `ChiefCareerScan-UK` | B02 | registered, **defect found and fixed** (see §3) | 23-09-2026 23:18:11 | 1 (pre-fix) |
| `ChiefCareerScan-Dubai` | B03 | registered, fails safe (`ready:false`, no lane config) | never (267011) | 267011 |
| `ChiefCareerScan-Japan` | B04 | registered, fails safe | never (267011) | 267011 |
| `ChiefCareerScan-Singapore` | B05 | registered, fails safe | never (267011) | 267011 |

`Mukund Chief of Staff` (legacy new-custom-Chief startup task, at logon, last result -1073741510)
is **not** an owned service of the current organisation: Hermes supersedes it as the Chief layer.
It is recorded as a superseded donor and was **left untouched** (no destructive cleanup).

### Hermes capability surface

- 62 installed skills (including `personal/mukund-company-registry`, `personal/mukund-owner-context`,
  `operations/executive-brain-e1`, `operations/executive-brain-planning`,
  `operations/hermes-gateway-capture`, `ai-worker-onboarding`).
- 1 hook: `discord-chief-archive` → maps to A19.
- 0 Hermes cron jobs (all scheduling is on Windows Task Scheduler; no parallel scheduler to reconcile).

### Legacy donor systems / canonical resources

All four donor systems still exist and were inspected only as status sources; none was revived,
rebuilt, restructured or deleted:

| Donor | Path | Status |
|---|---|---|
| Career Ops install (v1.29.0) | `…\ChatGPT\CV customizer\career-ops-career-ops-v1.29.0` | EXISTS — reused in place, its git repo untouched |
| July Chief-of-Staff | `…\Codex\2026-07-27\…\outputs\mukund-chief-of-staff` | EXISTS, disconnected (donor) |
| Mukund OS | `…\Documents\Chief of staff` | EXISTS, disconnected (donor) |
| New custom Chief | `…\ChatGPT\CV customizer\mukund-chief-of-staff` | EXISTS, superseded by Hermes |

Canonical trackers present: `uk-cyber-job-tracker.xlsx`, `Dubai_Cybersecurity_Job_Tracker.xlsx`,
`Japan_Cybersecurity_Job_Tracker.xlsx`, `Singapore_Cybersecurity_Job_Tracker.xlsx` (all under
`C:\Users\mukun\Downloads\codex`). No workbook was modified by this task.

## 2. Non-E3 operational service validation (no destructive changes)

| Service | Check | Result |
|---|---|---|
| Hermes Chief / gateway | `gateway_state.json` | **live** — `gateway_state: running`, `platforms.discord.state: connected`, updated 2026-09-23T22:23:02Z, code_version 0.21.4 |
| E1 intake/quality floor | `eb.py audit --verify` | **PASS** (`integrity_check: ok`, chain ok, `verify: PASS`) |
| E2 governor/telemetry | `eb.py gov-verify` | **PASS** |
| E3 store | `eb.py e3-status` / `e3-verify-db` | schema **v2**, `Verification PASSED`; capability registry: builder QUALIFIED ×2, integrator QUALIFIED ×1, vision EVALUATING ×1 |
| A04 Daily Resource Brief | `eb.py brief` | **works**, deterministic, no LLM; UNKNOWN dimensions still reported as UNKNOWN |
| Discord archive sync | `ChiefDiscordSync` + `DiscordArchive\chief\sync.log` | **green** — last 8 runs `result: ok`, last publish 21:06:04Z (`published: 8`, `rejected: 0`); checkpoint advancing |
| Remote queue poller | task state + `remote-queue/logs/queue.log` | **working** — 2-min cadence, `git pull: success`, and it claimed *this* task at 22:22:06Z |
| Company Registry access | skill `personal/mukund-company-registry` + its 6 reference files | **installed and readable** |
| Career Ops deterministic interface | `career-ops/career_ops_cli.py` + `career-ops/tests/` | **works** — 33/33 tests pass |

### Restart / boot expectations (recorded, not changed)

- `Hermes_Gateway` = at logon, restart-on-failure, `StartWhenAvailable: true` → survives logon.
- `HermesRemoteQueuePoller` and `ChiefDiscordSync` have a one-time time trigger with unlimited
  repetition and **no logon/boot trigger and no `StartWhenAvailable`**. Whether they resume after a
  reboot is therefore **not verified** — verifying it requires a reboot, which is prohibited by this
  contract's stop conditions. Recorded as an owner/admin verification item.
- All four Chief tasks are `Interactive only` (interactive token): they run only while Mukund is
  signed in. Unattended overnight operation therefore depends on the laptop staying signed in and
  awake — an owner-side condition, recorded in the owner-actions file.

### Recorded observations without interpretation

- `HermesRemoteQueuePoller` reports last result `0x800710E0` while its status is `Running`. Its
  observable behaviour (2-minute cadence, queue-log pickups, and the claim of this very task) is
  healthy; the meaning of that code was **not** resolved and is not claimed.
- This audit therefore makes no reboot-persistence or task-result-code claim beyond what is quoted.

## 3. Defect found and fixed: scheduled regional scan aborted after success

- Symptom: `ChiefCareerScan-UK` last result **1**; `runtime/career-ops/scan-runs/uk-last-stdout.json`
  contains a `UnicodeEncodeError` traceback instead of a JSON result.
- Root cause: the scheduled wrapper redirects stdout to a file whose encoding defaults to the local
  ANSI code page (cp1252). `career_ops_cli.emit()` used `print(json.dumps(..., ensure_ascii=False))`,
  so a scan that had **already succeeded** (record: `ok: true`, exit_code 0, 2861 jobs found,
  86.6 s) aborted while printing non-Latin job titles, and the task reported failure.
- Fix (bounded, no contract change): `emit()` now encodes the JSON to the actual stdout encoding and
  falls back to ASCII-escaped JSON when the code page cannot represent it — still exactly one JSON
  object on stdout. `career-ops/run_scheduled_scan.cmd` additionally sets `PYTHONIOENCODING=utf-8`
  and `PYTHONUTF8=1` (CRLF line endings preserved).
- Tests: new `career-ops/tests/test_emit_encoding.py` (5 tests) pins the behaviour for cp1252, ASCII
  and UTF-8 consoles. `career-ops` suite: **33/33 pass**. End-to-end probe under
  `PYTHONIOENCODING=cp1252` with redirected stdout: **exit 0**, valid JSON, no traceback.
- **Live confirmation (not just a unit test):** the scheduled task was re-run through the real
  Task Scheduler path at 2026-09-23T22:28:39Z (89.0 s, bounded dry-run, no tracker write). Result:
  `ChiefCareerScan-UK` **Last Result 0** (was 1), `uk-last-stdout.json` now contains **valid JSON**
  (`ok: true`, `exit_code: 0`) with **no traceback**, and a new run record
  `scan-uk-20260923T222839Z.json` was written. The scan found 1 new eligible offer (Celonis —
  Technology & Management Consulting Intern, London, trust 85/100, flagged
  `company_domain_mismatch`); it was **not** written to any tracker (dry-run only) and is reported
  here only as the scan's own output.
- The pre-fix traceback artifact was committed first (commit `70dd715`) and then overwritten by the
  live re-run, so the defect evidence survives in git history at
  `runtime/career-ops/scan-runs/uk-last-stdout.json`. The 23:45 daily fire is the routine confirmation.

## 4. Reconciliation outcome

- **No roster entry was missing**: all 50 roster items map to existing services or named
  pending/running tasks; no duplicate queue task was required for an already-covered item.
- **No locally discovered owner-relevant workflow is unaccounted for**: the 7 owned scheduled tasks
  and the Discord hook all map to the roster; the only discovered owner-relevant task absent from the
  roster is the superseded legacy `Mukund Chief of Staff` startup task, recorded above with evidence.
- **Two roster items have no task owning their remaining work**, and the work exists only in the
  unpushed working tree:
  - B08 Excel Tracker Writer — implemented (`career-ops/tracker_writer.py`, 28 tests) but
    **uncommitted** at audit time;
  - B09 Monthly Tracker Rollover / archive worker — **not implemented** and not owned by any
    pending/running task.
  This is a real coverage gap (the task that produced B07/B08 ended in `execution_error` before
  committing), so exactly **one** successor task was staged:
  `remote-queue/pending/agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23.json`. It is
  scoped to the canonical tracker writer/dedupe interface commitment + the monthly rollover worker +
  dept run-health, and explicitly excludes the regional lanes
  (`agent-regional-job-search-agents-and-schedulers-2026-09-23`) and Company Watch
  (`agent-company-watch-job-search-integration-2026-09-23`), which already own that scope.

## 5. Regressions run in this task

| Suite | Result |
|---|---|
| `career-ops/tests/` (tracker writer + new emit-encoding regression) | **33 passed** |
| `remote_queue/tests/` (isolated queue/bridge suite) | **42 passed** |
| `eb.py audit --verify` (E1) | **PASS** |
| `eb.py gov-verify` (E2) | **PASS** |
| `eb.py e3-verify-db` (E3) | **PASS** (schema v2) |
| `eb.py brief` (A04) | OK, deterministic |
| `scripts/company_inventory.py` (A20) | exit 0, 50 roster items, 0 unmapped |

E1/E2/E3 regressions from the sibling evidence runs (`audits/evidence/2026-09-23T21-53-37Z-…`) are
unchanged and were not re-executed in full here; the checks above are the E1/E2/E3 integrity gates.
