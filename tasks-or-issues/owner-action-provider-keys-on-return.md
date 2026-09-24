# Owner Action — Provision Remaining Provider API Keys

Status: COMPLETE (keys provisioned 2026-09-24) — verification executed; residual action moved to
`tasks-or-issues/overnight-owner-actions-2026-09-24.md` items 1b and 2b
Created: 2026-09-23
Owner: Mukund
Priority: HIGH
Deadline context: full operational build + VPS cutover by 2026-09-24 evening

## Outcome (recorded 2026-09-24)

All ten roster credentials are now present (`still_missing_count = 0`, presence-only probe at
2026-09-24T20:54:33Z). The ten post-provision steps below were then executed for every one of the
seven newly-credentialed providers:

1. credential presence verification — PASS (presence only; no value read or stored)
2. authenticated provider discovery — PASS for 6/7 (the provider's own `/models` catalogue)
3. exact live model ID confirmation — 6/7 confirmed by the provider response; Tencent/Hy3 derived
   from Tencent's TokenHub documentation because the key is rejected
4. adapter compatibility validation — adapter corrected (`/models` + chat-completions both OK)
5. harmless smoke test — **0/7 passed**: every provider refused the bounded call
   (mistral 429, GLM/Z.ai 429 balance, Qwen 403 Unpurchased, LongCat 402 quota, MiniMax 402
   balance, StepFun 402 quota, Tencent 401 invalid key)
6. provider-returned usage capture — no usage figures exposed by any refusing provider
7. E2 record-request linkage — exercised for all seven; each row read back with status `error`
8. truthful registry update — `routable=false`, `qualification=UNPROVEN` for all seven; credential
   presence alone was never promoted to routable or qualified
9. regressions/audits — full E1–E5 regression plus the bounded real-provider rehearsal and E4/E5 drills
10. commit/push — this task's commit

**Resulting state:** `routable=false` for all seven (step 5 failed at the provider, not the adapter).
`qualification` stays evidence-driven / UNPROVEN.

**Residual owner action:** fund/enable the six provider accounts and re-issue the Tencent TokenHub key.
See `overnight-owner-actions-2026-09-24.md` item 1b.

## Original owner action (preserved)

When Mukund returns, provision API credentials for the seven remaining provider workers.

Providers:
1. Mistral
2. GLM
3. Qwen
4. LongCat
5. MiniMax
6. Step
7. Tencent Hunyuan

## Rules

- Store credentials locally only using the approved secret-storage pattern.
- Do not paste keys into ChatGPT, Discord, GitHub, source files, logs, or queue jobs.
- Use separate canonical credential names per provider.
- Presence checks should report only yes/no.
- Hermes must verify the actual live provider auth path, exact API model ID, and model availability before marking a worker execution-ready.
- Adapter existence alone does not imply routability.
- Smoke test does not imply qualification.

## After each key is provisioned

Hermes should immediately perform:
1. credential presence verification
2. authenticated provider discovery
3. exact live model ID confirmation
4. adapter compatibility validation
5. harmless smoke test
6. provider-returned usage capture where exposed
7. E2 record-request linkage
8. truthful registry update
9. regressions/audits
10. commit/push

Resulting state may become:
- routable=true only if execution-readiness checks pass
- qualification remains evidence-driven / UNPROVEN until cold-start evaluation

## While Mukund is away

Credential absence must NOT block:
- E3 qualification harness
- E3 orchestration implementation
- E4
- E5
- VPS preparation/deployment scripting
- tests/audits
- remote queue bridge setup

Hermes should continue all non-credential-dependent work.
