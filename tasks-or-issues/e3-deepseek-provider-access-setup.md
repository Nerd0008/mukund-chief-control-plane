# E3 DeepSeek Provider Access Setup — COMPLETE

Task authority: tasks-or-issues/e3-deepseek-provider-access-setup.md
Date: 2026-09-23
Executor: Chief (E3 provider setup workstream)

## STEP 1 — Credential discovery (presence only)

- Windows Credential Manager entry (`deepseek` target): PRESENT
  (stored by owner locally via `cmdkey /generic:deepseek /user:api /pass:***`)
- DEEPSEEK_API_KEY environment variable: ABSENT
- E2 secret reference: Credential Manager (canonical, D2 policy)

Security incident during setup: owner pasted an API key into chat once.
Chief refused to use it and instructed rotation. Owner revoked the exposed
key, generated a new one, and stored it locally via cmdkey. The new key
never passed through chat, logs, or source. Old key treated as compromised
and revoked by owner.

Key access helper: `deepseek_keyaccess.py` reads via CredReadW
(in-process only). No key value is ever printed, logged, or committed.

## STEP 2 — Authentication / provider discovery

- GET https://api.deepseek.com/models with Bearer auth: HTTP 200
- Observed live model IDs:
  - `deepseek-flash` (owned_by: deepseek) — CONFIRMED
  - `deepseek-v4-pro` (owned_by: deepseek)
- Expected model ID `deepseek-flash` CONFIRMED by provider.
- Old registry string `deepseek-v4.1-flash` is NOT a valid API model ID —
  corrected in worker registry. display_name=DeepSeek V4.1 Flash,
  api_model_id=deepseek-flash (observed).

## STEP 3 — E3 ExecutionAdapter

- File: `deepseek_adapter.py` (distinct from E2 telemetry probe_deepseek)
- Reuses: credential helper (deepseek_keyaccess.py), budget config
- dispatch(): chat/completions, synchronous, timeout client-enforced
- retrieve(): inline (synchronous API)
- cancel(): process-kill only; no server-side job — reported truthfully
- Structured errors: 400/401/402/403/422/429 parsed from provider JSON
- Model identity: response `model` field captured per dispatch
- Usage capture: provider-returned usage fields ONLY (never estimated)
- Sanitized dispatch metadata: dispatch_id, contract_id, objective_hash,
  objective_summary (50 chars), api_endpoint, auth_source, timeout,
  elapsed, http_status, exit_status. No raw objective, no secrets.

## STEP 4 — Token / model telemetry

Observed from smoke-test response (provider-returned, not estimated):
- prompt_tokens: 51
- completion_tokens: 23
- total_tokens: 74
- prompt_cache_hit_tokens: 0
- prompt_cache_miss_tokens: 51
- reasoning_tokens: null (not exposed by deepseek-flash for this call)
- returned model ID: deepseek-flash
- finish_reason: stop
- prompt_cache_hit/miss fields captured

E2 linkage: reported through governor.record_request() public interface.
E3 performed NO direct SQL writes to governor.db.
E2 record-request ID: obs-20260923-44da95cd
monetary_cost recorded as "unknown" (provider does not return cost;
never estimated per E2 rules).

## STEP 5 — Smoke test

- Objective: 'Return exactly the JSON object {"result":4} and nothing else. This is 2+2.'
- Model: deepseek-flash, max_tokens=32, temperature=0.0
- Result: COMPLETED, content = '{"result":4}' (exact match)
- Deterministic validation: PASS
- dispatch_id: ds-926ce9ed0999, runtime 1.05s
- Smoke test proves EXECUTION READINESS only, not capability qualification.

## STEP 6 — Tests and audits

- E3 regression: 40/40 PASS
- E1 regression: 32/32 PASS
- E2 regression: 45/45 PASS
- eb audit --verify: PASS
- eb gov-verify: PASS
- e3 verify-db: PASSED (11 tables, schema v1)

Test updates (environment-driven, not weakened):
- tests/test_governor.py T6: now simulates credential absence for BOTH
  env var and Credential Manager (key is now present in the real store,
  so the old env-only simulation no longer isolates the no-credential path)
- tests/test_e3.py: DeepSeek routability test updated to assert the new
  verified state (adapter + PASS smoke test + VERIFIED E2 linkage +
  UNPROVEN qualification)
- tests/test_eb.py T13: allowed-files list extended for
  deepseek_adapter.py, deepseek_keyaccess.py
- e3_commands.py: import fallback for direct script execution (no
  behaviour change when imported as package)

No E1/E2 schema modifications.

## STEP 7 — Worker registry truth

deepseek-v41-flash:
- auth_configured: true (credential_manager)
- adapter_implemented: true
- smoke_test: PASS
- execution_interface_present: true
- e2_usage_linkage: VERIFIED
- routable: true (execution readiness only)
- qualification: UNPROVEN

## Current pool state after this task

- codex-cli: routable=false (smoke test BLOCKED_USAGE_LIMIT, parked)
- deepseek-v41-flash: routable=true, UNPROVEN
- all other 8 workers: routable=false (no adapter, no smoke test)

## Files changed

- exec-brain/deepseek_keyaccess.py — NEW (credential helper, D2)
- exec-brain/deepseek_adapter.py — NEW (E3 ExecutionAdapter)
- exec-brain/worker_registry.py — deepseek entry updated (observed identity)
- exec-brain/e3_commands.py — import fallback for direct execution
- exec-brain/tests/test_e3.py — routability test updated
- exec-brain/tests/test_governor.py — T6 dual-source absence simulation
- exec-brain/tests/test_eb.py — T13 allowed files extended

## Boundaries respected

- Codex untouched (parked until usage limit resets)
- No other provider configured
- Stage 2 remains NOT APPROVED
- No E1/E2 schema changes
- No qualification granted (smoke test != qualification)
