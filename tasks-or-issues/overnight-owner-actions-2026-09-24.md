# Overnight Owner-Action TODO — 2026-09-24

**Owner:** Mukund  
**Mode:** Maximum-effort overnight completion sprint  
**Rule:** Owner-only blockers go here. They must not stop unrelated work.

## Operating protocol

When Hermes/Luna reaches a blocker that genuinely requires Mukund:

1. Record the exact action required in this file.
2. Record why it is owner-only.
3. Record what workstream is blocked.
4. Record the safest next command/action for Mukund.
5. Continue immediately to the next independent non-blocked task.
6. Do not weaken safety, qualification, privacy, evidence, deployment, or Stage 2 gates to avoid an owner dependency.
7. When Mukund returns, work this list top-to-bottom by critical-path impact.

## Current owner actions

### 1. Remaining provider credentials
**Status:** PENDING  
**Blocks:** live onboarding/verification of the remaining seven E3 provider workers.  
**Action:** provision credentials locally for Mistral, GLM, Qwen, LongCat, MiniMax, Step, and Tencent Hunyuan using approved local secret storage. Never paste keys into ChatGPT, Discord, GitHub, source files, queue jobs, or logs.  
**Continue without owner:** qualification harness, orchestration, E4/E5 integration, tests, evidence, bridge hardening, deployment preparation.

### 2. E3 Stage 2 production approval
**Status:** NOT READY / OWNER GATE  
**Blocks:** enabling production dispatch only.  
**Action:** when Stage 1 rehearsal and acceptance evidence is complete, review the readiness package and explicitly approve or reject Stage 2.  
**Continue without owner:** all Stage 1 shadow/rehearsal/qualification/evidence work.

### 3. Deployment architecture decision
**Status:** PENDING OWNER DECISION  
**Blocks:** final real deployment/cutover topology.  
**Decision required:** choose between the existing full-VPS cutover authority and the discussed laptop-primary + GitHub control plane + optional VPS watchdog/failover alternative.  
**Continue without owner:** reproducible deployment scripts/manifests, service definitions, backup/restore plan, secret provisioning design, reboot acceptance plan, dry-run preparation.

### 4. VPS access/details
**Status:** PENDING IF VPS PATH IS CHOSEN  
**Blocks:** real VPS deployment/cutover.  
**Action:** provide/access VPS host/account details locally when architecture is chosen. Do not place credentials in GitHub/chat/logs.  
**Continue without owner:** all non-destructive deployment preparation and local validation.

## Resolved / no longer owner-blocking

- Hermes primary execution brain: restored via DeepSeek direct API.
- Hermes model smoke: `deepseek-flash` returned `AUTH_OK` with exit code 0.
- Nous Portal: currently rate-limited with HTTP 429; do not keep retrying overnight. This is not an owner-action blocker because Hermes has a working DeepSeek path.
- Codex allowance: owner reports reset; fresh Codex worker re-validation remains engineering work, not an owner blocker unless login/account action is actually requested by the CLI.

## Morning target

By Mukund's return, the system should be as close as safely possible to the authoritative definition of done, with any remaining owner-only blockers concentrated in this file rather than scattered across stalled tasks.
