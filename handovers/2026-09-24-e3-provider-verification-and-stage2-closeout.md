# Handover — Post-key E3 provider verification and local Stage 2 closeout (2026-09-24)

Task: `agent-e3-provider-verification-stage2-closeout-2026-09-24`
Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`

## Verdict

**Local E3 Stage 2 remains NOT ENABLED.** The post-key verification sequence was executed in full
and the readiness gate was re-run with a clean regression. Condition (a) *all intended provider
credentials configured* is SATISFIED (10/10) and provider identity is verified for every intended
provider. Condition (b) is unmet on exactly one criterion — the Google image real-dispatch condition
(`resolved, not intermittent`). Condition (c) is **False for this run**: the live coordinator
instruction appended to the running contract at 2026-09-24T20:56Z forbids local E3 Stage 2 enablement
in this execution and supersedes the earlier embedded authorization. Independently, every
newly-credentialed provider refused live dispatch, so provider-diverse routing cannot execute even
though the credentials exist.

Enablement belongs to the gated successor task
`agent-e3-stage2-enable-after-provider-verification-2026-09-24` (queue commit `df0514b`).

No qualification, verification, safety, privacy, cost, retry or readiness gate was weakened. The gate
now reads the coordinator override from the contract and fails closed while it stands.

## What was run (in order)

| Step | Command | Result |
|---|---|---|
| 1 | `scripts/e3_credential_presence_probe.py` | `still_missing_count = 0` — 10/10 roster credentials present. 0 network calls, 0 provider calls, no credential value read, printed, logged or stored. |
| 2 | `scripts/e3_provider_live_identity_probe.py` | 6/7 provider endpoints + API model IDs confirmed from the provider's own live `/models` catalogue; 1/7 (Tencent/Hy3) authoritative-documentation derived because the key is rejected. 0 completion calls. |
| 3 | adapter + registry corrections, `scripts/deploy_e3_runtime.py` | Corrected modules deployed to `%LOCALAPPDATA%/hermes/exec-brain` with the deployment backup/manifest retained. |
| 4 | `scripts/e3_provider_bounded_smoke.py` | **0/7 passed.** One bounded completion per worker (`max_tokens=16`, single attempt, no retries); every provider refused. |
| 5 | `scripts/evidence_runner.py --label e3-provider-verification-regression` | **PASS** — 22 suites / 606 collected / 606 passed / 0 failed / 0 unavailable. |
| 6 | `exec-brain/e3_execution_rehearsal.py` | **PASS** — bounded real-provider production rehearsal, no failed check, 7 real calls (deepseek 5 / openai 2). |
| 7 | `exec-brain/e4e5_drill_harness.py` | **PASS 36/36**, `real_provider_calls = 0`, `evidence_kind = stubbed_provider_failure`. |
| 8 | `scripts/e3_stage2_readiness_gate.py --regression-evidence <step 5>` | `NOT ENABLED` — a=PASS, b=FAIL (Google image criterion), c=FAIL (live coordinator override forbids enablement for this run). Evidence: `audits/evidence/2026-09-24T21-12-42Z-e3-stage2-readiness-gate-verdict/`. |

## Corrections made from live-provider evidence

| Provider | Was | Now (evidence) |
|---|---|---|
| Mistral | `mistral-small-4` | `mistral-small-latest` (live catalogue) |
| MiniMax | `minimax-m3` (lower case) | `MiniMax-M3` (live catalogue) |
| Qwen | CN DashScope host, intended `qwen3.7-plus` | international DashScope host, `qwen3.8-27b` (the intended id is not in this account's catalogue) — **SUPERSEDED 2026-09-24** (task `agent-provider-debug-qwen-tencent-entitlement-2026-09-24`): this claim was wrong. The committed live catalogue evidence lists BOTH `qwen3.7-plus` and `qwen3.7-plus-2026-05-26`; the adapter/registry model id was corrected to `qwen3.7-plus` and one bounded re-test of the corrected id returned HTTP 403 `AccessDenied.Unpurchased` (account entitlement, not a mapping/config fault). See `handovers/2026-09-24-provider-debug-qwen-tencent-reconciliation.md`. |
| GLM | legacy BigModel CN endpoint | Z.ai international endpoint, `glm-5.3-flash` confirmed |
| StepFun | `api.stepfun.com` | `api.stepfun.ai` (global API), `step-3.7-flash` confirmed |
| LongCat | direct API | **unchanged — already correct**, preserved deliberately |
| Tencent Hunyuan/Hy3 | regional/legacy hosts | TokenHub international `hy3` (documentation-derived; key rejected) |

## Provider refusals (exact, as returned by the provider)

- mistral — HTTP 429 `Rate limit exceeded`
- glm-53-flash — HTTP 429 `Insufficient balance or no resource package. Please recharge.`
- qwen38-27b — HTTP 403 `Access to model denied. Please make sure you are eligible for using the model.`
- longcat-2.0 — HTTP 402 `Call failed: Insufficient token quota.`
- minimax-m3 — HTTP 402 `insufficient balance (1008)`
- step-37-flash — HTTP 402 `You exceeded your current quota, please check your plan and billing details`
- tencent-hunyuan-hy3 — HTTP 401 `The API Key does not exist or signature verification failed.`

Auth-error bodies are never persisted verbatim. Every one of the seven is
`routable = false`, `qualification = UNPROVEN`; credential presence was never promoted to routable or
qualified. E2 linkage was exercised for all seven through the public `governor.record_request()`
interface and each row was read back with status `error`.

## Preserved gaps (never claimed)

- **Live-provider E4/E5 failover/recovery is NOT evidenced.** `e4e5_drill_harness.py` always stubs
  provider transport; it has no live mode. Only stubbed-failure evidence exists, and the production
  blocker `live-provider-failover-gap` stays open.
- **Google image stability is NOT claimed.** The bounded repeat series observed 2/9 recurrences, each
  carrying the provider's own `finishReason = IMAGE_RECITATION`. The trigger is provider-side and
  unknown; the vision role is unqualified.
- **Tencent/Hy3 provider identity is documentation-derived only**, because the credential is rejected.

## Owner actions

1. **Fund/enable the six provider accounts and re-issue the Tencent TokenHub key** (see
   `tasks-or-issues/overnight-owner-actions-2026-09-24.md` item 1b for the exact per-provider action).
2. **Decide on the Google-image criterion** (item 2b): accept the attributed provider-side
   intermittency as re-scoping the criterion, or fund a stability investigation.
3. **Answer the recorded E4/E5 acceptance question**: are the stubbed-failure drills (36/36) plus the
   real-path execution rehearsal sufficient for v1, or is a live-provider failover drill required?

After 1 and 2: re-run `python scripts/e3_provider_bounded_smoke.py`, then
`python scripts/e3_stage2_readiness_gate.py --regression-evidence <latest clean regression>`.

## Credential-safety notes

- The presence probe reports presence and store names only; it never reads a value.
- One early identity-probe bundle had captured a partial credential echoed back by a provider's 401
  body. That bundle was deleted outright rather than trusting a redaction, and the probe was patched
  so auth-failure bodies are never persisted (classified to `error_class` only).
- No secret, credential value, token, cookie or private runtime database is committed or rendered in
  the canonical status.

## Retry attempt 2 of 3 — re-verification (2026-09-24T21:14–21:16Z)

Attempt 1 landed and pushed all of the work above, then the dispatch was killed at the 1200-second
limit before it returned its final response (queue record: `execution_error`, recoverable). Attempt 2
therefore resumed by *re-verifying* rather than repeating:

| Step | Command | Result |
|---|---|---|
| 1 | `python scripts/e3_credential_presence_probe.py` | `still_missing_count = 0` — 10/10 present; no value read. Local-only artifact (git-ignored). |
| 2 | `python scripts/e3_provider_bounded_smoke.py` | **0/7 dispatched.** One minimal completion per worker (`max_tokens=16`, single attempt, no retries); the provider state is **unchanged** — same refusal classes as attempt 1 (mistral 429, GLM/Z.ai 429 balance, Qwen 403 Unpurchased, LongCat 402 quota, MiniMax 402 balance, StepFun 402 quota, Tencent 401 code 401002). Evidence: `audits/evidence/2026-09-24T21-14-53Z-e3-provider-bounded-smoke/`. |
| 3 | `python scripts/e3_stage2_readiness_gate.py --regression-evidence audits/evidence/2026-09-24T21-09-18Z-e3-provider-verification-regression/evidence.json` | `NOT ENABLED` — identical verdict (a=PASS 10/10, b=FAIL Google image criterion, c=FAIL live coordinator override), `0` execution-ready providers. 0 provider calls. Evidence: `audits/evidence/2026-09-24T21-16-01Z-e3-stage2-readiness-gate-verdict/`. |
| 4 | `python scripts/status_render.py` + `python scripts/status_verify.py` | regenerated; **PASSED, 0 warnings** |
| 5 | `python scripts/tests/test_status_consistency.py` | **23/23 OK** |

**Disposition.** The unchanged provider refusal is a *deterministic external blocker*, not a retryable
execution failure, so this task is parked rather than looped, per the owner's 2026-09-24 retry policy
(do not retry an unchanged external-provider blocker; the 0/7-key style gate is not retryable). No
provider call was repeated beyond one minimal completion per worker, no gate was weakened, no live
failover is claimed, and Stage 2 remains **NOT ENABLED**. The full 22-suite regression is not re-run
here because no code changed after the committed clean run at SHA `6cbb573`; the canonical status
records that run as `latest_evidence`.
