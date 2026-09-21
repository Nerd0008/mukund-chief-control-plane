# Handover — Chief OS Build Sprint
Date: 2026-09-21
Owner: Mukund
Purpose: Start a fresh ChatGPT thread tomorrow without losing context.

## Current goal
Finish the first complete operational version of Mukund's digital Chief-of-Staff / company system by **24 September 2026**.

Definition of v1: the company can operate end-to-end with Executive Brain, no-degradation enforcement, resource awareness, provider routing, career workflows, tracker automation, Company Watch, daily briefings, and whole-system acceptance testing. Long-term learning maturity, VPS migration, Phase 2B Discord, dashboards, and other polish are post-v1.

## Working model
Mukund = owner.
Hermes Chief of Staff = direct report / head manager / personal assistant.
Existing workflows and agents = employees under Chief.
Chief should coordinate and supervise existing systems rather than rebuild them unnecessarily.

Management loop:
Observe → Understand → Prioritize → Plan → Delegate → Monitor → Verify → Report → Learn → Improve.

Cost/complexity order:
existing resource → deterministic Python/PowerShell/SQL/Excel → Hermes tools → cheap/local model → premium model only when materially useful.

Quality rule:
Resource scarcity may alter provider, timing, decomposition, scheduling, or handover, but must NOT silently lower capability, reasoning depth, verification, factual accuracy, safety, or the frozen quality floor. If no equivalent route exists, pause rather than degrade.

## Shared control plane
Private GitHub repo:
`Nerd0008/mukund-chief-control-plane`

Local repo:
`C:\Users\mukun\Documents\mukund-chief-control-plane`

ChatGPT can read this repo directly through the GitHub connector. Prefer reading repo state instead of asking Mukund for screenshots where possible.

Discord #chief capture is active:
Discord → local archive → GitHub → ChatGPT.

Automatic sync:
Windows task `ChiefDiscordSync`, every 30 min, deterministic, no LLM.
Local archive:
`C:\Users\mukun\DiscordArchive\chief\`

## Hermes
Native Windows install.
Config:
`C:\Users\mukun\AppData\Local\hermes\config.yaml`

Current inference model:
`meituan/longcat-2.0:free` via Nous.

Important installed skills:
- `mukund-owner-context`
- `mukund-company-registry`
- `executive-brain-e1`

Hermes/Discord gateway is working.

## Executive Brain architecture
Approved baseline:
`approved-architecture/executive-brain-v2.md`
Baseline commit: `545b59a7031502c6ed234b43969e77559d724ba4`

Core pipeline:
Understand → Classify → Decompose(optional) → Freeze quality floors → Candidate Generation → Provider Router Proposal → Central Qualification Gate → Resource Governor → Final Route Selection → Execute/Monitor/Checkpoint → Verify → Learn.

Hierarchical routing:
- Executive Brain chooses execution/provider class.
- Provider-specific router chooses model/reasoning/profile.
- Central qualification gate owns final compliance decision.
- Providers cannot self-certify.

## E1 — COMPLETE AND ACTIVE
Implementation completed 2026-09-21.

Local implementation:
`%LOCALAPPDATA%\hermes\exec-brain\eb.py`

Local DB:
`%LOCALAPPDATA%\hermes\exec-brain\exec_brain.db`

Skill:
`%LOCALAPPDATA%\hermes\skills\operations\executive-brain-e1\SKILL.md`

Rollout record:
`decisions/exec-brain-e1-rollout.md`

Company state:
`state/current_company_state.md`

E1 status:
- 32/32 tests PASS
- SQLite schema v1
- classify/decompose/freeze/route/override/audit/backup/restore/summary implemented
- append-only records protected by DB triggers
- immutable quality floors
- SHA-256 hash chains + chain-head anchor
- route-before-freeze blocked
- low-confidence classification blocks normal routing
- route overrides bound to exact route fingerprint
- source event idempotency
- structural route-floor compliance enforced
- audit verification PASS
- backup/restore PASS
- Discord gateway regression PASS
- ChiefDiscordSync regression PASS
- no Career Ops/tracker/provider configuration modified
- no raw sensitive task text or secrets pushed to GitHub

Known E1 limitation:
Worker/model quality is NOT yet proven by E1. E1 checks structural floor compliance only. Worker qualification is E3.

## Next active work
Do NOT reopen E1 unless a verified bug appears.

Next sequence:
1. E2 — Resource Governor telemetry + Daily Resource Brief
2. E3 — task-specific worker qualification / performance evidence / central Qualification Gate
3. E4 — predictive exhaustion + protected reserves + proactive checkpoints / handovers
4. E5 — safe mode + failure drills + owner override UX
5. Career Ops integration and tracker automation
6. Company Watch v1
7. CV/cover-letter workflow connection
8. minimal LinkedIn workflow integration
9. whole-company acceptance test and v1 release

Do one active build task at a time.

## Resource Governor requirements
Must be passive with respect to quality floors; it cannot lower quality.

Track provider dimensions separately, never collapse incompatible units into one percentage:
- request/token windows
- daily/weekly/monthly allowances
- monetary budget/balance
- rate limits
- concurrency/provider credits
- reset/renewal
- telemetry source + confidence

Providers planned:
- Codex
- Antigravity
- DeepSeek API
- Nous/LongCat
- local models later

DeepSeek API key exists with owner; key must remain local in env/secret store, never chat/GitHub/logs/prompts/source.

Unknown telemetry must be UNKNOWN, not zero/unlimited/healthy.

Daily Resource Brief should show:
remaining capacity, protected reserve, effective usable capacity, resets, confidence, yesterday usage, burn trend, expected demand, exhaustion risk, likely handovers/conserve state.

## Career Ops / job systems
Career Ops:
`C:\Users\mukun\Documents\ChatGPT\CV customizer\career-ops-career-ops-v1.29.0`

Verified scan dry run:
~2,861 jobs processed in ~88 sec, zero failures/cost; one eligible offer found.

Current blocker:
`save-main-tracker.mjs` depends on `@oai/artifact-tool`, available in Codex runtime but not normal node_modules. Standalone scan writes `pipeline.md`; canonical Excel writing needs a deterministic replacement.

Canonical UK tracker:
`C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx`

Dubai/Japan/Singapore trackers also exist under Downloads\codex.

Regional automated schedules are not currently active; company was effectively manual before this rebuild.

Excel remains authoritative for departmental operational records. Chief DB/state is orchestration, not replacement.

Monthly rollover should eventually use pure Python/openpyxl, preserving structure/formulas/validation/status metadata and cross-month dedupe.

## Company Watch
Historical Gmail review found:
- 203 confirmed/strongly evidenced employers
- 18 recruiters/intermediaries
- 221 organizations with application/CV evidence

Company Watch should live under Career, scan prior employers using structured career/ATS endpoints where possible, use shared dedupe, and feed findings into regional trackers. It gets its own monthly operational workbook but must not create conflicting application state.

Not yet built.

## Owner's sprint schedule
Target release: **24 September 2026**.

Known availability:
- 21 Sep: tonight was build time; owner is now going to sleep.
- 22 Sep: work roughly 13:00–22:00; leave around 12:30. Morning build time available; after work only light review.
- 23 Sep: FREE — main build day, can work until 23:00.
- 24 Sep: rota will change; owner expects to leave work around 12:30 and then has afternoon/evening through ~23:00 for integration/release.
- Owner can stay awake/work until ~23:00 daily.

Sprint principle:
New ideas go to backlog until after 24 Sep. Do not expand scope during release sprint.

## Remote-work setup
Chrome Remote Desktop is now working on the owner's iPhone 17 Pro.

Remote control stack:
- Discord: primary interaction with Chief
- ChatGPT: review/design and direct GitHub control-plane reading
- GitHub: shared curated state
- Chrome Remote Desktop: full Windows fallback for PowerShell, Excel, file dialogs, permission prompts

Laptop should remain plugged in, connected, and configured not to sleep while plugged in during remote build periods.

For dangerous-command prompts from Hermes:
approve expected commands individually (Allow once); do not permanently allow generic Python/PowerShell/script execution.

## Interaction preferences
- Anything intended to be sent to Hermes should be in a compact Markdown block.
- Architecture/system implementation prompts go to Hermes PowerShell interactive session unless explicitly operational/Discord-oriented.
- User prefers one thing at a time.
- Review actual repo state directly when possible.
- Do not ask for screenshots when GitHub contains the needed state.
- If Hermes hits output truncation, keep reasoning quality and use file-first/incremental output rather than lowering reasoning.
- Preserve old July/Mukund OS systems as donors unless explicitly deciding to retire them.
- Do not initialize or restructure Career Ops git without owner approval.

## First thing to do in the new chat
1. Read this handover.
2. Check `state/current_company_state.md` and `decisions/exec-brain-e1-rollout.md` from GitHub for latest state.
3. Confirm E1 remains active.
4. Continue with **E2 planning only first**, unless repo state shows E2 has already begun.
5. Keep the 24 Sep whole-system release deadline in view.

## Suggested first user message
"Use the handover in `handovers/2026-09-21-chief-os-sprint-handover.md`. Check the latest control-plane state and continue from there. E1 is complete; next is E2 unless something changed overnight."
