# 09 — Health checks and acceptance commands

Every command here was executed against the live system on 2026-09-24 and its
real result is recorded. Anything not executed is marked `NOT RUN`.

Run everything from the repository root with the runtime interpreter:

```bash
cd C:/Users/mukun/Documents/mukund-chief-control-plane
```

---

## 1. Deployment preflight / go-no-go

```bash
python scripts/deployment_preflight.py
```

Checks: host/Python version, repo + runtime E3 module set, `eb.py` `e3-*` patch,
7 databases (existence + `PRAGMA integrity_check`), all 8 scheduled tasks
(existence, enabled state, logon type, trigger kind), third-party dependencies
importable, credential presence for all 10 workers, acceptance-command targets
present, no secret-looking file tracked/staged in git, topology decision still
pending.

- Exit code `0` = GO, `1` = NO-GO.
- **Verified 2026-09-24: `verdict: GO`, 0 failures, 1 warning** (the 7 missing
  provider credentials — an owner-gated dependency, not a fault).
- Evidence: `audits/evidence/2026-09-24T02-14-49Z-deployment-preflight/`.

## 2. Backup / restore verification

```bash
python scripts/deployment_backup_restore_drill.py
```

- **Verified 2026-09-24: `status: PASS`** — 10/10 artifacts
  (7 databases + 3 JSON state files), every snapshot `integrity_check = ok`,
  every restore byte/row-identical to its snapshot, and
  `deploy_e3_runtime.py --dry-run` clean (wrote nothing).
- Evidence: `audits/evidence/2026-09-24T02-15-42Z-deployment-backup-restore-drill/`.

## 3. Credential and provider health

```bash
python scripts/set_provider_key.py --status     # all 10 roster workers
python scripts/e3_credential_presence_probe.py         # the 7 API workers, 3 presence paths
python scripts/e3_stage2_readiness_gate.py             # E3 Stage 2 readiness verdict
```

- **Verified 2026-09-24:** DeepSeek (`deepseek`), Gemini (`gemini-api`) and
  Codex CLI present; **7 workers absent** — Mistral, GLM, Qwen, LongCat, MiniMax,
  Step, Tencent Hunyuan. Truthful state: those workers are `routable=false`,
  `smoke_test=NOT_RUN`, `qualification=UNPROVEN`. Never report them as healthy.
- Presence checks make no network call and read no credential value.

## 4. E1 / E2 / E3 database and audit verification

```bash
python "%LOCALAPPDATA%/hermes/exec-brain/eb.py" e3-verify-db      # E3 orchestration DB
python "%LOCALAPPDATA%/hermes/exec-brain/eb.py" --help            # E1/E2 commands (init, classify, audit, backup)
```

- **Verified 2026-09-24:** `e3-verify-db` → `Schema version: 2 / Verification
  PASSED / All required tables present / Schema version valid` (exit 0).
- E1 audit and E2 gov-verify commands are run through this same CLI; run them as
  part of the destination-node acceptance (`07` Phase 4).

## 5. E4 / E5 resilience drills

```bash
python exec-brain/e4e5_drill_harness.py
```

- **Verified 2026-09-24 (run `deployment-prep-regression`): 33/33 checks,
  `failed_checks: []`, `real_provider_calls: 0`, `stub_dispatches: 10`,
  `evidence_kind: stubbed_provider_failure`, code SHA `b6329b7`.**
  Evidence: `audits/evidence/2026-09-24T02-18-21Z-e4e5-real-path-drills/`.
- Honest limitation: the harness has **no live-provider mode** — a *real*
  provider outage → real failover has not been exercised and must not be claimed.
  Recorded as an acceptance question for the owner.

## 6. E3 production / execution rehearsal (spends real provider calls)

```bash
python exec-brain/e3_production_rehearsal.py          # replay/rehearsal
python exec-brain/e3_execution_rehearsal.py           # bounded real-provider leg (~7 calls)
```

- `e3_execution_rehearsal.py` is the only driver that spends real provider calls.
  Keep it bounded; never loop it.
- `NOT RUN` in this task: these consume provider quota and the credential set is
  incomplete (7/7 keys absent). They are part of the post-key sequence.

## 7. Full regression suite

```bash
python scripts/evidence_runner.py --label <name> [--only SUBSTR]
```

- 15+ suites across `exec-brain/tests/`, `remote_queue/tests/` and career-ops.
- **Verified 2026-09-24 (run `deployment-prep-regression`, code SHA `b6329b7`):
  16 suites run, 16 passed, 0 failed, 0 unavailable, 456 tests collected,
  456 passed, 0 errors, 0 skipped, every suite exit 0.**
  Evidence: `audits/evidence/2026-09-24T02-18-54Z-deployment-prep-regression/`.
- Historical baseline to beat: 438 tests / 15 suites (as of 2026-09-24T23:55Z);
  the suite count has since grown, so compare *pass/fail*, not the raw total.
- `--only` runs a subset; use it for a fast smoke before a full run.

## 8. Career Ops / Company Watch health

```bash
python career-ops/dept_run_health.py summary
python career-ops/run_acceptance.py
python career-ops/daily_brief.py --help          # morning brief generation
```

- **Verified 2026-09-24:** `dept_run_health.py summary` returns structured
  run-health metadata per job (e.g. regional scan last status
  `refused` with `dry-run` mode and recorded counts) — exit 0.
- Scans are bounded dry-runs; they never write a tracker or submit anything.

## 9. Service / scheduler checks

```bash
schtasks /query /tn Hermes_Gateway /fo LIST /v
schtasks /query /tn HermesRemoteQueuePoller /fo LIST /v
schtasks /query /tn ChiefDiscordSync /fo LIST /v
python career-ops/install_schedules.py --status
```

Expected: all `Enabled`, logon mode `Interactive only`, next-run times advancing.

## 10. Acceptance sequence at cutover (destination node)

| Acceptance | Command | Pass condition |
|---|---|---|
| Service survives restart | restart gateway via `06` §4, then `scripts/deployment_preflight.py` | GO |
| E1 audit | `eb.py` E1 audit command | PASS |
| E2 gov-verify | E2 verification command | PASS |
| E3 DB/integrity | `eb.py e3-verify-db` | PASSED |
| E4/E5 | `e4e5_drill_harness.py` | 33/33, real provider calls 0 |
| Provider health | `e3_credential_presence_probe.py` | 7/7 configured, or truthful blocker |
| Text task end-to-end | `eb e3-execute --objective … --confirm` (bounded) | node completes, evidence recorded |
| Multi-worker task end-to-end | rehearsal driver | DAG completes, integrator + verifier ran |
| Image task end-to-end | Google image worker path | image artifact produced, E2 linkage recorded |
| Verifier rejection + repair | rehearsal with a deliberately failing node | rejection recorded, targeted rework ran |
| Provider failure/failover | E4/E5 drill (+ live mode once built) | failover to equivalent worker or honest escalation |
| Owner escalation | escalation path in `e3_escalate.py` | escalation surfaces to the owner with a rationale record |
| State truth | `state/current_company_state.md` updated | matches deployed reality |

## 11. Safety properties of every command above

- No command here starts, stops, creates or deletes a scheduled task.
- No command here makes a public/external/posted change.
- Secret values are never printed; presence and store names only.
- The only commands that spend provider quota are in §6/§10 and are explicitly
  marked.
