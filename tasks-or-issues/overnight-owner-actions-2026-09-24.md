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
**Status:** STANDING CONDITIONAL APPROVAL GRANTED 2026-09-23  
**Blocks:** nothing, provided the local readiness gates are objectively satisfied.  
**Owner directive:** Mukund explicitly authorizes Stage 2 local production enablement while he is asleep or at work if the system is judged ready from evidence. Do not pause solely for another approval prompt.  
**Readiness conditions before enabling:** local E1/E2/E3/E4/E5 regressions pass; production rehearsal passes; no unresolved critical integrity/privacy/safety defect; worker routing is evidence-based; rollback/recovery path exists; current state/evidence is updated truthfully.  
**Scope:** this standing approval covers local Stage 2 enablement only. It does not authorize VPS cutover or a final deployment-architecture choice.

### 3. Deployment architecture decision
**Status:** DEFERRED UNTIL LOCAL SYSTEM IS PROVEN  
**Blocks:** final real deployment/cutover topology only.  
**Owner direction:** first make the system run perfectly locally. Do not pause local completion to choose deployment architecture.  
**Current preference (not final approval):** laptop as primary production node, GitHub as control/collaboration plane, VPS as watchdog/failover.  
**Continue without owner:** local Stage 2, local production rehearsal, qualification, regressions, evidence, deployment scripts/manifests, service definitions, backup/restore plan, secret provisioning design, reboot acceptance plan, and dry-run preparation.

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
- Codex CLI worker re-validation: COMPLETED 2026-09-23 (`agent-codex-reset-revalidation-2026-09-23`).
  CLI resolved at `bin/80f78947ad880e6e/codex.exe` v0.155.0-alpha.16.3 (the hardcoded hash path was
  stale), auth mode `chatgpt`, one harmless smoke returned `READY`, E2 linkage
  `obs-20260923-d42e34a5`, routable=true, qualification UNPROVEN. The CLI requested no login,
  account, subscription, or billing action — no owner action outstanding for Codex.

## Morning target

By Mukund's return, the system should be as close as safely possible to the authoritative definition of done, with any remaining owner-only blockers concentrated in this file rather than scattered across stalled tasks.
