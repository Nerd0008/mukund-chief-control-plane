# E3 Remaining Provider Credentials + Parallel Continuation

Status: ACTIVE
Created: 2026-09-23
Owner: Mukund
Authority: tasks-or-issues/2026-09-24-full-operational-vps-cutover.md

## Current observed local Hermes state

Hermes reported local commit:
- `aa38126` — Generic OpenAI adapter + registry updates

Reported implementation:
- `exec-brain/generic_openai_adapter.py`
- one config-driven adapter intended for the seven remaining API workers:
  - Mistral
  - GLM
  - Qwen
  - LongCat
  - MiniMax
  - Step
  - Tencent Hunyuan
- E3 tests reported 50/50 PASS
- combined reported 127/127 PASS
- all seven remaining workers NOT_RUN / not routable because credentials are absent

IMPORTANT:
This commit was not yet observed on GitHub at the time this task was created.
Hermes must push/sync it before treating the state as shared/authoritative.

## Credential blocker

Remaining provider workers need real provider access before smoke tests can run.

For each provider:
- discover exact supported auth mechanism
- discover exact base URL
- discover exact live model ID
- store credential only in approved local secret storage
- never hardcode or commit keys
- never assume OpenAI compatibility merely because a generic adapter exists
- if provider behaviour differs, add a provider-specific adapter/branch only where verified necessary

## Required credential targets

Hermes should define canonical secret names before owner provisioning, e.g.:
- mistral-api
- glm-api
- qwen-api
- longcat-api
- minimax-api
- step-api
- hunyuan-api

Exact names may differ if an existing approved naming convention already exists.

## Immediate Hermes action

Do NOT remain idle while credentials are missing.

1. Push/sync local commit aa38126 (or its current descendant) to GitHub.
2. Verify shared GitHub state.
3. Continue all non-credential-dependent work in parallel:
   - E3 qualification harness
   - planner/router/integrator/verifier production path
   - failure/rework/replan logic
   - E4 resource continuity implementation
   - E5 safe-mode/resilience implementation
   - VPS inventory/deployment prep
   - deployment scripts/config
   - tests/audits
4. For provider onboarding:
   - prepare per-provider config stubs
   - verify official API compatibility assumptions
   - prepare smoke-test harnesses
   - STOP short of authenticated calls until credentials exist
5. If the generic OpenAI adapter is not actually compatible with a provider's verified API, correct it rather than forcing the abstraction.

## Owner action required

Mukund must provision provider credentials for the seven remaining API workers.

Until then:
- these workers stay routable=false
- smoke_test=NOT_RUN
- qualification=UNPROVEN

Credential absence must not block unrelated E3/E4/E5/VPS progress.

## No-shortcut rule

Do not:
- fabricate live model IDs
- infer auth success without an authenticated call
- mark workers routable from adapter existence alone
- mark qualification from smoke tests
- weaken the full Sep 24 completion scope
