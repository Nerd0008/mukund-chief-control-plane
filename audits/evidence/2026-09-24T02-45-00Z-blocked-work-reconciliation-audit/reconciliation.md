# Blocked-work final reconciliation — 2026-09-24

Task: `agent-blocked-work-final-reconciliation-2026-09-24`
Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
Audited at: 2026-09-24T02:45:00Z · Code SHA at audit: `9bc20a7`

## Purpose

Before whole-company acceptance, reconcile every historical blocked task that does
not require owner action: separate superseded/resolved historical execution
failures from genuinely unfinished recoverable work, close any remaining bounded
engineering gap, and make sure no non-owner recoverable blocker is silently left
behind.

## Verdict

- Historical blocked records audited: **12**
- Superseded/resolved by verified successor evidence: **10** (rerun not needed)
- Deterministic owner/external blockers, parked: **2** (the duplicate Stage-2
  credential-gate retry chain)
- Unresolved recoverable engineering work inside `blocked/`: **0**
- Additional non-owner gaps found outside `blocked/` and **closed by this task**: **2**
- Unresolved non-owner recoverable blockers remaining: **0**

## Classification (blocked/ records)

| Record | Recorded blocker | Classification | Superseded / parked by |
|---|---|---|---|
| agent-autonomous-nonblocked-continuation-2026-09-23 | execution_error (prose instead of JSON) | superseded | 617e69cb/aae7d036 + deepseek-utf8 recovery + later E3 tasks |
| agent-career-ops-integration-and-tracker-automation-2026-09-23 | execution_error (1200s timeout) | superseded | company-registry audit + career-ops tracker-writer/monthly-rollover |
| agent-company-watch-job-search-integration-2026-09-23 | execution_error (1200s timeout) | superseded | company-watch-recovery-final-pass-2026-09-24 |
| agent-e3-integration-and-truth-reconciliation-2026-09-23 | execution_error (orphaned running record) | superseded | deepseek-utf8 recovery (per-suite re-verification) |
| agent-e3-local-production-rehearsal-2026-09-23 | execution_error (0xC000013A) | superseded | e3-production-execution-leg + rehearsal retry + readiness gate rerun |
| agent-e3-local-production-rehearsal-retry-2026-09-23 | execution_error (>1200s) | superseded | its evidence consumed by the readiness gate rerun |
| agent-e3-stage2-readiness-gate-after-provider-keys-retry-2026-09-24 | execution_error + 0/7 credentials | deterministic blocker — parked | owner credentials (unchanged) |
| agent-e3-stage2-readiness-gate-after-provider-keys-retry-2-2026-09-24 | execution_error + 0/7 credentials | deterministic blocker — parked | owner credentials (unchanged) |
| agent-live-queue-recovery-2026-09-23 | external_provider (Nous OAuth 429) | superseded | deepseek-utf8 recovery after the DeepSeek switch |
| agent-live-queue-recovery-deepseek-2026-09-23 | execution_error (stream decode) | superseded | deepseek-utf8 recovery; bridge hardening e643fd16 |
| agent-queue-isolation-and-evidence-recovery-2026-09-23 | execution_error (orphaned record) | superseded | deepseek-utf8 recovery (isolated queue suite + evidence runner) |
| agent-queue-isolation-and-evidence-recovery-retry-2026-09-23 | execution_error (CLI exit 1) | superseded | deepseek-utf8 + QuickEdit/two-retry hardening 85f604aa |

Every record stayed in `blocked/` as preserved historical evidence, and each
gained an additive `final_reconciliation_2026_09_24` note. A programmatic check
confirmed all 12 edits are strictly additive: parsed JSON at `HEAD` equals parsed
JSON now, once the added key is removed.

## Contract-required specific verifications

1. **Queue-recovery / UTF-8 / QuickEdit failures** — CONFIRMED SUPERSEDED.
   `agent-live-queue-recovery-deepseek-utf8-2026-09-23` isolated the queue suite,
   fixed four reproduced lifecycle defects and produced per-suite evidence; bridge
   UTF-8 hardening `e643fd16`; `agent-visible-worker-console-quickedit-hardening-2026-09-23`
   cleared `ENABLE_QUICK_EDIT_MODE` per process, moved the watchdog to its own
   thread and installed the audited `MAX_RETRIES=2` policy. No rerun needed.
2. **E3 integration / rehearsal failures** — CONFIRMED SUPERSEDED without
   repeating provider calls. The execution leg was built, deployed and really
   executed; the image failure was diagnosed with one bounded call, then measured
   by a bounded 9-call series (2/9 `IMAGE_RECITATION`); the readiness gate rerun
   recorded 12 suites / 364 tests / exit 0 and *consumed* the multi-worker
   rehearsal evidence instead of repeating it. This task repeated no live or
   expensive provider rehearsal.
3. **Career Ops historical timeout** — CONFIRMED CLOSED. The deterministic
   interface was committed by the company-registry audit (33 tests, encoding fix
   live-confirmed through the real Task Scheduler path) and B09 monthly rollover
   plus department run-health were delivered by
   `agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23`
   (career-ops suite 332 passing, canonical workbooks SHA-256 unchanged).

## Gaps found and closed

### GAP-1 — a genuine agent task was silently swallowed (high)

`poller.handle_task` matched the substring `operational` **before** the `agent-`
dispatch branch, so `agent-operational-brief-health-backup-persistence-2026-09-23`
was claimed at 2026-09-24T01:38:05Z and immediately returned
`handle_operational_build()`'s hardcoded `in_progress` status — no Hermes
dispatch, no work, no terminal transition. `queue.log` shows the claim and the
`in progress (attempt 1)` line 1 ms apart.

A systematic sweep of every queue id (pending/running/completed/blocked) confirmed
exactly one genuine agent task was affected. The intentional non-agent umbrella
`full-operational-build-2026-09-24` also uses the placeholder, and that behaviour
is preserved deliberately.

Fix: `remote_queue/poller.py` — the `agent-` dispatch branch now precedes all
legacy placeholder routers, so every `agent-*` task reaches Hermes. Unknown
non-agent queue objects still fail closed with `ValueError`.

Recovery: the swallowed task was restored to `remote-queue/pending/` with the
**same task_id** (no duplicate retry chain) plus resume evidence.

### GAP-2 — the E1 static gate failed on normal runtime debris (medium)

The first reconciliation evidence run (02:32:23Z, preserved under
`audits/evidence/superseded/2026-09-24T02-32-23Z-blocked-work-final-reconciliation-superseded-by-e1-sidecar-fix/`)
reported E1 31/32: the deployed
runtime root held `orchestration.db-shm` (plus a 0-byte `orchestration.db-wal`)
left by an earlier uncleanly-exited worker, and `test_t13_no_gateway_modification`
enumerated only database basenames. That false failure would block the authority's
"E1 audit PASS" acceptance item for no real reason.

Fix: T13 now accepts only the `-wal`/`-shm` sidecars of databases already on its
allow-list. Negative proof recorded: with a deliberately unexpected file in the
runtime root the check **fails**, and passes once it is removed (probe deleted).
E1 then ran 32/32 exit 0.

## Owner TODOs (unchanged dependencies only)

1. Configure the seven owner-local provider credentials (Mistral Small 4,
   GLM-5.3 Flash, Qwen3.8-27B, LongCat 2.0/Nous, MiniMax M3, Step 3.7 Flash,
   Tencent Hunyuan Hy3) via Windows Credential Manager targets (`mistral`, `glm`,
   `qwen`, `nous`, `minimax`, `stepfun`, `hunyuan`) or the matching env vars —
   never via GitHub/chat/logs. Only then may the post-key Stage-2 readiness gate be
   re-staged; it must not be requeued while the credential state is unchanged.
2. Decide the Career Ops monthly rollover policy before month-end. No canonical
   workbook has been rotated.
3. Carried forward from the company-registry audit: keep the laptop
   powered/signed-in (scheduled tasks run under the interactive user token);
   after the next reboot confirm `HermesRemoteQueuePoller` and `ChiefDiscordSync`
   resume; decide the disposition of the superseded legacy "Mukund Chief of Staff"
   logon task.

## Deliberately not done

- No Stage-2 credential-gate retry was requeued (0/7 credential state unchanged;
  forbidden by the authority's anti-loop directive).
- No historical broad task was rerun; no live or expensive provider rehearsal was
  repeated.
- No owner-gated external mutation, deployment cutover, account action or secret
  handling.
- The Google image provider-content-stop attribution/retry policy stays owned by
  the pending `agent-e3-provider-content-stop-attribution-and-image-retry-policy-2026-09-24`;
  it was not duplicated.
- The non-agent umbrella `full-operational-build-2026-09-24` stays in `running/`
  as a placeholder; its status must be re-derived from evidence by whoever
  retires it.

## Result

No unresolved non-owner recoverable blocker remains before whole-company
acceptance. The final whole-company acceptance task may proceed.
