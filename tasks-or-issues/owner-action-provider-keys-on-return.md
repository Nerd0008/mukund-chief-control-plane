# Owner Action — Provision Remaining Provider API Keys

Status: PENDING_OWNER_RETURN
Created: 2026-09-23
Owner: Mukund
Priority: HIGH
Deadline context: full operational build + VPS cutover by 2026-09-24 evening

## Owner action

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
