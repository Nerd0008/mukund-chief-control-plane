# Overnight Owner-Action TODO — 2026-09-24

**Owner:** Mukund  
**Mode:** Maximum-effort continuous completion run — continue until deployment-ready  
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

### 1. Configure all remaining provider credentials
**Status:** PENDING — OWNER PLANS TO DO THIS ON 2026-09-24  
**Blocks:** live onboarding/verification of the remaining seven E3 provider workers and, by direct owner instruction, final local Stage 2 completion.  
**Action:** provision credentials locally for Mistral, GLM, Qwen, LongCat, MiniMax, Step, and Tencent Hunyuan using approved local secret storage. Never paste keys into ChatGPT, Discord, GitHub, source files, queue jobs, or logs.  
**Continue without owner:** qualification harness, orchestration, Google-image diagnosis, multi-worker execution evidence, E4/E5 integration, tests, evidence, bridge hardening, deployment preparation.

### 2. Complete E3 Stage 2 after all provider keys are configured
**Status:** DEFERRED BY OWNER UNTIL AFTER KEY CONFIGURATION ON 2026-09-24  
**Blocks:** final local Stage 2 enablement only; independent engineering and evidence work must continue.  
**Owner directive:** Mukund will complete local Stage 2 after he configures all remaining provider keys tomorrow. Do not enable Stage 2 overnight before those keys are configured. Once the keys are configured, re-run the full readiness checks and then complete local Stage 2 if all objective gates pass.  
**Readiness conditions before enabling:** all intended provider credentials configured and truthfully verified; local E1/E2/E3/E4/E5 regressions pass; production rehearsal passes; no unresolved critical integrity/privacy/safety defect; worker routing/qualification state remains evidence-driven; rollback/recovery exists; state/evidence is updated truthfully.  
**Scope:** local Stage 2 only. This does not authorize VPS cutover or a final deployment-architecture choice.

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


### 5. Owner-attended laptop security audit after the overnight build
**Status:** DEFERRED — DO WITH MUKUND PRESENT  
**Reason:** Two unexplained visible local UI events occurred while Hermes was running: (1) Microsoft Edge opened/searched `events near me` even though Mukund does not normally use Edge for browsing, and (2) a blank terminal window opened. These observations do not prove compromise, but they require attribution before treating the laptop as a trusted production host.
**Preserve now:** do not clear Edge history, shell history, Windows Event Logs, Task Scheduler history, Defender history, Hermes/queue logs, or browser/process artifacts.
**Audit scope when Mukund is present:** correlate timestamps across Hermes/remote-queue logs, Windows process-creation/event records where available, Task Scheduler, PowerShell/terminal history, startup/autorun entries, Defender detections/exclusions, Edge history/extensions/background startup, recent installs, listening/network connections, and Hermes child-process launch paths. Establish whether the UI events came from Hermes/a child process, Windows/Edge background behavior, another automation, or an unknown process.
**Blocks:** trust decision for using the laptop as the final production host; does not block safe non-GUI engineering overnight.
**Safety:** no destructive cleanup or evidence deletion before attribution.

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

## Owner manual-work target

Mukund's expected manual task is **provider-key configuration only**. Engineering does not stop in the morning; it continues until the system is complete and deployment-ready.

Do not assign ordinary engineering, scripting, testing, scheduling, integration, documentation, acceptance preparation, or deployment preparation to Mukund. If an unforeseen external service genuinely requires owner interaction that cannot be completed safely by the system, record the exact reason and minimum action here, then continue all independent work.
