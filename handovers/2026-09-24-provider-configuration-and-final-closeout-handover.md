# Hermes Setup Handover — Provider Configuration + Final Closeout

**Date:** 2026-09-24  
**Owner:** Mukund  
**Repository:** `Nerd0008/mukund-chief-control-plane`  
**Purpose:** Continue immediately in a fresh chat without re-discovering state.

## Immediate next action

Continue configuring the remaining provider credentials. **MiniMax is next.**

Do not paste API keys into chat, GitHub, Discord, source files, queue tasks, or logs. Store keys only through:

```powershell
cd C:\Users\mukun\Documents\mukund-chief-control-plane
python scripts/set_provider_key.py --worker <worker-id>
```

The prompt uses no-echo input. Pasting normally shows no characters. Verify only presence with:

```powershell
python scripts/set_provider_key.py --check <worker-id>
```

## Provider configuration state

Already available before today's manual setup:
- Codex CLI — authenticated through its own login.
- DeepSeek — credential present.
- Google Nano Banana — credential present.

Configured manually today and confirmed stored in Windows Credential Manager:
- Mistral — worker `mistral-small-4` — **DONE**
- Qwen / Alibaba Model Studio — worker `qwen38-27b` — **DONE**
- GLM / Z.ai — worker `glm-53-flash` — **DONE**

Still to configure:
- MiniMax — worker `minimax-m3`
- Nous / LongCat — worker `longcat-2.0`
- StepFun — worker `step-37-flash`
- Tencent Hunyuan — worker `tencent-hunyuan-hy3`

After all remaining keys are stored, run the full post-key verification sequence from `tasks-or-issues/overnight-owner-actions-2026-09-24.md` item 8.

## Provider model / endpoint corrections intentionally deferred to the verification run

Do not assume that a stored credential means a provider is qualified.

### Mistral
Credential is stored against worker `mistral-small-4`.
Later verification must re-check the live Mistral model catalogue and correct the adapter model id if required before smoke/qualification. During setup, `mistral-small-latest` / the current Small 4 family was selected as the intended target.

TODO commit:
- `b4566e8f` — Mistral model-id verification added.

### Qwen
Credential is stored under worker `qwen38-27b` for compatibility with the current credential registry.
The model selected from the live Alibaba Model Studio page was **Qwen3.7-Plus**.
Later verification must confirm the live Singapore-region model id/endpoint and remap the adapter if required.

TODO commit:
- `df27879a` — Qwen 3.7 Plus + Singapore endpoint verification added.

### GLM
Credential is stored under worker `glm-53-flash`.
Later verification must confirm `glm-5.3-flash` and update/verify the adapter against the current Z.ai API endpoint rather than blindly retaining the legacy BigModel endpoint.

TODO commit:
- `180ca6ae` — current GLM/Z.ai endpoint verification added.

## Exact next credential commands

### MiniMax
```powershell
python scripts/set_provider_key.py --worker minimax-m3
python scripts/set_provider_key.py --check minimax-m3
```

### Nous / LongCat
```powershell
python scripts/set_provider_key.py --worker longcat-2.0
python scripts/set_provider_key.py --check longcat-2.0
```

### StepFun
```powershell
python scripts/set_provider_key.py --worker step-37-flash
python scripts/set_provider_key.py --check step-37-flash
```

### Tencent Hunyuan
```powershell
python scripts/set_provider_key.py --worker tencent-hunyuan-hy3
python scripts/set_provider_key.py --check tencent-hunyuan-hy3
```

If any provider's current model name, API endpoint, account product, pricing, or region is unclear, verify against the **current official provider docs before spending money**. Do not trust stale hard-coded adapter names blindly.

## Post-key sequence

Once every intended provider credential is present:

```powershell
python scripts/e3_credential_presence_probe.py
python scripts/e3_stage2_readiness_gate.py
python scripts/evidence_runner.py --label post-keys-regression
python exec-brain/e3_execution_rehearsal.py
python exec-brain/e4e5_drill_harness.py
```

Important:
- Report the **current measured** test count. Do not force the historical 579 count.
- Do not enable E3 Stage 2 until all objective gates pass.
- Real-provider qualification must remain evidence-driven.
- Do not claim live-provider failover has passed unless a real-provider failover/recovery path was actually exercised.

## Live engineering status at handover

### Release reproducibility / Codex portability — COMPLETE

Queue completion commit:
- `03fdab59`

Major evidence:
- pinned `requirements.txt` + `requirements.lock`
- clean-clone setup docs
- release manifest + archive build/verification tooling
- portable Codex identity contract with UNKNOWN preserved truthfully
- line-ending/archive hash reproducibility fix
- isolated CPython 3.11.16 acceptance run

Latest preserved result:
- **21 suites**
- **583 collected**
- **583 passed**
- **0 failed**
- **0 unavailable**
- E3 baseline **58/58**
- Stage 2 still **NOT ENABLED**
- real provider calls during that acceptance: **0**

Relevant implementation/evidence commits include:
- `61d8b67c` — reproducibility tooling + Codex portability contract
- `3469185b` — isolated acceptance evidence, 583/583
- `fa561d92` — deterministic cross-platform archive line endings
- `021f7abc` — archive commit acceptance reconfirmation
- `03fdab59` — task completed

### Canonical status / generated tracker / doc-drift cleanup — RUNNING

Claim commit:
- `63cda9b9`

Task:
`agent-canonical-status-generated-tracker-and-doc-drift-2026-09-24`

Goal:
- one canonical machine-readable project status
- generated/verified executive tracker
- reconcile README E3/E4/E5 state
- reconcile `state/current_company_state.md`
- separate implemented / verified / Stage2 enabled / production deployed
- represent real production blockers and owner-gated items truthfully
- fail verification when generated status/tracker is stale

**Do not interrupt this worker unless the normal watchdog/recovery rules say it is actually stuck.**

### Career live-research scheduled cutover — BLOCKED / PARKED

Task:
`agent-career-live-research-schedule-cutover-and-acceptance-2026-09-24`

Final block commit:
- `f164eac8`

Attempts:
- attempt 1 hit the 300s no-progress watchdog
- attempt 2 exceeded the 1200s hard timeout
- attempt 3 exceeded 1200s
- retry budget exhausted

There were also repeated Git push/rebase problems:
- push rejected: fetch first
- recovery rebase failed because of unstaged changes

The underlying Career engineering is not lost:
- high-recall semantic discovery exists
- unified recruiter/LinkedIn export intake exists
- open-web job research lane exists
- priority company watchlist engine exists

What remains blocked is the **scheduled operational cutover + live acceptance** that makes the new research stack the actual nightly UK/Dubai/Japan/Singapore scheduled path.

Do not falsely mark this production-ready until that cutover is recovered and proved.

## Career engineering already completed

Important completed layers include:
- high-recall discovery replacing Intern/Internship-only gating
- structured regional/global providers
- recruiter/intermediary watch
- LinkedIn owner-export intake
- open-web/Codex-style research lane
- priority company watchlist engine
- one unified provenance/funnel architecture
- Career Brief integration
- public/open-web discovery only; no signed-in LinkedIn browser/session automation

The owner still needs to populate actual company names by copying:
`career-ops/watchlist/company-watchlist.example.json`
to the git-ignored runtime watchlist path and editing the names.

## Remaining owner closeout items

Keep these on the final checklist:

1. Finish the remaining provider credentials: MiniMax, Nous/LongCat, StepFun, Tencent Hunyuan.
2. Add actual company names to the runtime company watchlist.
3. Run the complete post-key credential/readiness/regression sequence.
4. Run bounded real-provider E3 rehearsal and obtain real-provider failover/recovery evidence.
5. Enable local E3 Stage 2 only after clean gates.
6. Recover the blocked Career scheduled live-research cutover task.
7. Finish canonical generated status/tracker cleanup (currently running).
8. Perform owner-attended laptop trust/security audit for the unexplained Edge `events near me` search and blank terminal event before treating the laptop as a trusted production host.
9. Empirically confirm reboot persistence.
10. Resolve scheduled-task battery gating for unattended laptop-primary operation if owner approves the service-definition change.
11. Create an off-machine backup before production.
12. Make final deployment/cutover topology decision; provide VPS access only if VPS is chosen.
13. State work-authorisation/sponsorship position for UAE, Japan and Singapore.
14. Re-evaluate whether Dubai/Japan need additional dedicated provider coverage after open-web schedule cutover is functioning.
15. Optional: Gmail read-only OAuth.
16. Optional: approved research provider if still needed after open-web work.
17. Optional: signed-in LinkedIn live account access remains owner-gated; public web + export path already exists.
18. Optional: Career Daily Brief delivery channel.
19. Optional: operational service cadence.
20. Optional tracker vocabulary decisions.
21. Resolve legacy `Mukund Chief of Staff` scheduled task disposition.

## Queue / worker operational rules

When asked for status in the next chat, **live-check GitHub first**:
- recent commits
- running/pending/completed/blocked task files
- queue log tail when useful

Do not infer status from this handover alone.

Watchdog semantics:
- heartbeat means liveness, not useful progress
- <300s silence is normally left alone
- >300s with no watchdog action warrants investigation
- hard attempt timeout = 1200s
- `execution_error` retries up to 3 total attempts

Do not broadly kill processes or Ctrl+C a useful worker.
Do not hard-reset the repo blindly.
`remote-queue/logs/queue.log` is tracked telemetry and often dirties the working tree; preserve worker changes.

Also avoid unnecessary GitHub edits while a worker is actively pushing because this has contributed to fetch-first collisions. Credential provisioning in Windows Credential Manager is safe to continue because it does not mutate GitHub.

## External-mutation boundaries

No autonomous:
- job applications
- LinkedIn posts/messages/connections/applications
- recruiter/company outreach
- account/OAuth/credential creation or mutation without owner action
- Stage2 enablement before keys + readiness
- final deployment cutover without owner decision

Engineering may draft, test, inspect, and run read-only discovery/acceptance where already authorized.

## Where the next chat should resume

Mukund has just finished storing the **GLM key** successfully.

The next chat should start with:

> Continue provider configuration. MiniMax is next. Verify the current official MiniMax API/model/account path before asking Mukund to spend money, then guide him through creating the correct API key. Once generated, store it with `python scripts/set_provider_key.py --worker minimax-m3` and verify presence. Then continue to Nous/LongCat, StepFun and Hunyuan.

Do not repeat completed Mistral/Qwen/GLM setup unless verification fails later.
