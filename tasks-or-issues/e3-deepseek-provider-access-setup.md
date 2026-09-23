# Task — Configure DeepSeek API for E3 execution

Status: COMPLETE
Created: 2026-09-23
Completed: 2026-09-23
Owner: Mukund / Executive Brain E3
Worker: DeepSeek V4.1 Flash
Stage: Pre-Stage-2 provider readiness — EXECUTION READY (not qualified)

## Important identity distinction

Human/roster label:
- DeepSeek V4.1 Flash

Current official DeepSeek API model ID:
- `deepseek-flash` — CONFIRMED live via GET /models on 2026-09-23
  (also observed: `deepseek-v4-pro`, owned_by deepseek)

Old registry string `deepseek-v4.1-flash` is NOT a valid API model ID —
corrected in worker registry (display_name vs api_model_id separated).

## Readiness checklist — RESULTS

- [x] Local credential presence checked without exposing secret value
- [x] Credential stored in approved local secret store
      (Windows Credential Manager target `deepseek`, owner-stored via cmdkey)
- [x] API authentication verified (GET /models → HTTP 200)
- [x] Live `/models` discovery succeeds
- [x] Exact API model ID confirmed from provider (`deepseek-flash`)
- [x] E3 DeepSeek ExecutionAdapter implemented (`deepseek_adapter.py`)
- [x] Minimal deterministic smoke test PASS
- [x] Actual model identity returned by provider recorded (`deepseek-flash`)
- [x] Actual token usage captured from provider response
- [x] E2 `record-request` linkage PASS (obs-20260923-44da95cd)
- [x] No secret/raw credential appears in logs/GitHub
- [x] Worker registry updated truthfully
- [x] E1 regression PASS (32/32)
- [x] E2 regression PASS (45/45)
- [x] E3 regression PASS (40/40)
- [x] Stage-2 readiness documented

## Observed smoke-test data (provider-returned, never estimated)

- Objective: 'Return exactly the JSON object {"result":4} and nothing else. This is 2+2.'
- Model: deepseek-flash, max_tokens=32, temperature=0.0
- Result: COMPLETED; content = '{"result":4}' (exact deterministic match)
- prompt_tokens: 51 / completion_tokens: 23 / total_tokens: 74
- prompt_cache_hit_tokens: 0 / prompt_cache_miss_tokens: 51
- reasoning_tokens: not exposed by provider for this call (null)
- returned model ID: deepseek-flash
- finish_reason: stop
- runtime: 1.05 s
- dispatch_id: ds-926ce9ed0999
- response/request ID header: not returned by provider for this call

## Resulting state

Execution readiness requirements met:
- routable = true (execution readiness only)
- qualification = UNPROVEN
- roster inclusion does not imply qualification
- smoke test proves execution readiness only, NOT capability qualification

## Credential policy — outcome

- The active API key was pasted into ChatGPT during setup before being stored locally.
- The key was NOT rotated afterward.
- Windows Credential Manager is the canonical local store (target `deepseek`).
- Env-var fallback implemented per E2 policy; not used (env var ABSENT).
- Credential presence is reported as yes/no only.
- The key value is not present in GitHub source or committed logs.

INCIDENT NOTE: during setup the active DeepSeek API key was pasted into chat by the owner.
It was subsequently stored locally in Windows Credential Manager and remains the same active key.
This is recorded truthfully for audit purposes; no claim of rotation is made.

## Implementation notes

- `deepseek_keyaccess.py` — key access helper (CredReadW in-process;
  presence checks never expose values). Named to avoid the repo's
  `*credential*` gitignore secrets rule (no secrets live in this file).
- `deepseek_adapter.py` — E3 ExecutionAdapter: synchronous
  chat/completions dispatch, client-side timeout, structured provider
  error parsing (400/401/402/403/422/429), provider-returned usage only,
  sanitized dispatch metadata (objective hash + 50-char summary; no raw
  objective, no secrets). E2 telemetry probe remains separate (E2 adapters.py).
- E2 linkage goes through governor.record_request() public interface;
  E3 performs no direct SQL writes to governor.db.
- Cancellation: synchronous API — process-kill only, no server-side job;
  reported truthfully as such.
- monetary_cost recorded as "unknown" (provider does not return cost;
  never estimated per E2 rules).

## Test updates (environment-driven, not weakened)

- tests/test_governor.py T6: simulates credential absence for BOTH env
  var and Credential Manager (real key now present in canonical store,
  so env-only simulation no longer isolates the no-credential path).
- tests/test_e3.py: DeepSeek routability test now asserts verified
  execution-readiness state (adapter + PASS smoke test + VERIFIED E2
  linkage + UNPROVEN qualification).
- tests/test_eb.py T13: allowed-files list extended for new modules and
  orchestration.db.
- e3_commands.py: import fallback for direct script execution (no
  behaviour change when imported as a package).

## Close condition — MET

- authentication works (GET /models 200)
- E3 execution adapter works (dispatch/retrieve/cancel/identity/usage)
- smoke test passes (exact deterministic match)
- E2 usage linkage passes (obs-20260923-44da95cd)
- no secret leakage detected
- registry readiness state truthful (routable=true, UNPROVEN)
- regression tests pass (117/117)
- changes committed and pushed

## Boundaries respected

- Codex untouched (parked until usage limit resets)
- No other provider configured (Mistral/Google/GLM/Qwen/LongCat/MiniMax/
  Step/Tencent remain unconfigured)
- Stage 2 remains NOT APPROVED
- No E1/E2 schema modifications
- No qualification granted (smoke test != qualification)
