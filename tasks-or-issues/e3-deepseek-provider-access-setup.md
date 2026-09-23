# Task — Configure DeepSeek API for E3 execution

Status: ACTIVE
Created: 2026-09-23
Owner: Mukund / Executive Brain E3
Worker: DeepSeek V4.1 Flash
Stage: Pre-Stage-2 provider readiness

## Important identity distinction

Human/roster label:
- DeepSeek V4.1 Flash

Current official DeepSeek API model ID:
- `deepseek-flash`

Do not invent or hardcode a different API model ID. Confirm the live model list during smoke testing.

## Readiness checklist

- [ ] Local credential presence checked without exposing secret value
- [ ] Credential stored in approved local secret store
- [ ] API authentication verified
- [ ] Live `/models` discovery succeeds
- [ ] Exact API model ID confirmed from provider
- [ ] E3 DeepSeek ExecutionAdapter implemented
- [ ] Minimal deterministic smoke test PASS
- [ ] Actual model identity returned by provider recorded
- [ ] Actual token usage captured from provider response
- [ ] E2 `record-request` linkage PASS
- [ ] No secret/raw credential appears in logs/GitHub
- [ ] Worker registry updated truthfully
- [ ] E1 regression PASS
- [ ] E2 regression PASS
- [ ] E3 regression PASS
- [ ] Stage-2 readiness documented

## Current policy

Until ALL execution readiness requirements are met:

- `routable = false`
- qualification = `UNPROVEN`
- roster inclusion does not imply qualification

A smoke test proves execution readiness only. It does NOT qualify DeepSeek for any production capability role.

## Credential policy

- Never paste the API key into ChatGPT, Discord, GitHub, source code, prompts, or logs.
- Windows Credential Manager is the existing approved canonical DeepSeek secret store.
- Environment-variable fallback may only be used according to existing E2 policy and must not be persisted into repository files.
- Report credential presence as yes/no only.

## Smoke-test expectations

Use a harmless deterministic request with a tiny response.

Capture only provider-supported metadata:
- response/request ID
- returned model ID
- system fingerprint where available
- input/output/total tokens
- reasoning tokens where available
- cache-token details where available
- finish/status
- runtime
- HTTP/provider errors

Then report observed usage through the E2 public `record-request` interface.

## Close condition

This task closes only when:
- authentication works,
- E3 execution adapter works,
- smoke test passes,
- E2 usage linkage passes,
- no secret leakage is detected,
- registry readiness state is truthful,
- regression tests pass,
- changes are committed and pushed.
