# Full Build / Remote Bridge / Deployment Handover — 2026-09-23

## Purpose

Continue Mukund's Chief-of-Staff / Chief Control Plane build without reopening completed decisions or losing the current deadline context.

This handover covers:
- current E1/E2/E3 worker/provider state,
- Google/DeepSeek readiness,
- the seven-provider credential blocker,
- the Hermes GitHub remote-task bridge,
- the recent Git recovery incident,
- the full Sep 24 deadline,
- the latest laptop-vs-VPS architecture discussion,
- exact next actions for the next chat.

---

# Owner deadline / scope

Mukund's deadline remains:

**Everything operational by 2026-09-24 evening.**

Owner explicitly rejected an MVP/reduced-scope launch.

Current full-scope authority:
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`

Commit:
`2e99cbfefc4008873d855dab3a30b9c38ab6cd77`

Important:
- no intentional worker deferrals,
- no weakening E1/E2/E3 gates for speed,
- accelerate with parallel work, reuse and automation,
- external provider/account/credential blockers must be recorded truthfully rather than fabricated around.

The earlier reduced sprint was explicitly superseded.

---

# Executive Brain baseline

Architecture remains frozen unless a verified implementation blocker requires amendment.

## E1
ACTIVE / verified.
Last known baseline:
- 32/32 tests PASS
- audit --verify PASS

## E2
ACTIVE / verified.
Last known baseline:
- 45/45 tests PASS
- gov-verify PASS

## E3 Stage 1
Implemented / SHADOW ONLY until Stage 2 owner approval.

Implemented baseline includes:
- task fingerprinting,
- decomposition planning,
- execution DAG,
- capability registry,
- worker contracts,
- qualification gate,
- decision-rationale events,
- rationale/trace/why CLI views,
- separate orchestration.db,
- event-sourced governance-critical state.

Stage 2 is still **NOT APPROVED**.

Smoke-test readiness does NOT equal qualification.

---

# Worker pool — verified shared state

## 1. DeepSeek

Execution-ready.

Observed:
- live API model: `deepseek-flash`
- E3 execution adapter implemented
- smoke PASS
- E2 record-request VERIFIED
- routable=true
- qualification=UNPROVEN

DeepSeek setup record:
`tasks-or-issues/e3-deepseek-provider-access-setup.md`

Important incident truth:
- the active DeepSeek key was pasted into ChatGPT during setup,
- it was NOT rotated afterward,
- the same active key was later stored in Windows Credential Manager,
- do not repeat or expose the key.

## 2. Google image worker

Execution-ready.

Worker display/roster identity:
- Google Nano Banana 2

Confirmed live backing model:
- `gemini-3.1-flash-image`

Implementation commit:
`69f1f74ea71c60f170e4eee14ef26ab35a8c2765`

Observed smoke:
- PASS 8/8
- returned modelVersion: gemini-3.1-flash-image
- image/jpeg
- 53,299 bytes
- 1024 x 1024
- runtime 8.52s
- provider usage captured
- E2 observation: `obs-20260923-d44f030a`

Registry:
- routable=true
- qualification=UNPROVEN

Gemini task:
`tasks-or-issues/e3-google-nano-banana-2-provider-access-setup.md`

A merge conflict caused literal conflict markers to be committed into the task Markdown. This was repaired in:
`c8b86e2539dcf47c155b4e3807344709d337f3ad`

Do NOT rerun Gemini unless a real regression requires it.

## 3. Codex CLI

Adapter exists and was hardened.

Current blocker:
- ChatGPT/Codex usage limit reset

Current truthful state:
- routable=false
- smoke=BLOCKED_USAGE_LIMIT
- model identity=UNKNOWN until observed
- E2 usage linkage=NOT_VERIFIED
- qualification=UNPROVEN

TODO:
`tasks-or-issues/e3-codex-smoke-test-after-limit-reset.md`

Codex must not block independent work.

## 4–10. Remaining API workers

- Mistral Small 4
- GLM-5.3 Flash
- Qwen3.8-27B
- LongCat 2.0
- MiniMax M3
- Step 3.7 Flash
- Tencent Hunyuan Hy3

Hermes reported locally implementing a shared/config-driven OpenAI-compatible adapter path for these seven and reported:
- local commit `aa38126`
- E3 tests 50/50
- combined tests 127/127
- all seven still NOT_RUN / routable=false because credentials are absent

CRITICAL:
At the time this handover was created, `aa38126` was **not visible in the GitHub commit history**.
Treat this as local reported state, not shared source-of-truth, until Hermes pushes/syncs it and it is verified remotely.

Task:
`tasks-or-issues/e3-remaining-provider-credentials-and-parallel-continuation.md`

---

# Owner TODO — provider credentials

Mukund will provision the seven remaining provider keys when he returns.

Authority:
`tasks-or-issues/owner-action-provider-keys-on-return.md`

Commit:
`240b14b3b8a05af6826f641a8fe1addd3e112314`

Providers:
1. Mistral
2. GLM
3. Qwen
4. LongCat
5. MiniMax
6. Step
7. Tencent Hunyuan

Rules:
- keys stay local,
- do not paste into ChatGPT/Discord/GitHub/logs,
- verify exact provider auth/base URL/live model ID,
- adapter existence alone does not imply routability,
- smoke test does not imply qualification.

Credential absence must NOT block unrelated E3/E4/E5/deployment work.

---

# Hermes GitHub remote-task bridge

Goal:
Allow trusted collaborators/ChatGPT to enqueue structured Hermes work while Mukund is away.

Bridge specification:
`tasks-or-issues/hermes-github-remote-queue.md`

Commit:
`f6a00a037193e41ac0a81170dab330b8308b8fce`

Expected queue layout:
- `remote-queue/pending/`
- `remote-queue/running/`
- `remote-queue/completed/`
- `remote-queue/blocked/`

Security model:
- NOT arbitrary shell execution,
- structured task objects only,
- tasks must reference approved authority,
- normal E1/E2/E3/E4/E5 gates remain active,
- owner approval gates cannot be bypassed,
- secrets/raw CoT never enter queue,
- task IDs deduplicated,
- local kill switch required,
- Windows Task Scheduler persistence required,
- poll target: every ~2 minutes.

Jobs already created:
- `remote-queue/pending/full-operational-build-2026-09-24.json`
  - commit `6324ad6975e0ee72efe926138c9070396fb4cad4`
- `remote-queue/pending/bridge-validation-and-autonomous-continuation.json`
  - commit `b7fc298abff4ca893cdb404b2d749fdb2e42c111`

Latest user report:
- Hermes is currently setting up the bridge.

At handover creation time, the GitHub bridge specification still says:
**READY_TO_IMPLEMENT**

No verified GitHub commit proving the poller implementation was found yet.

Next chat must verify whether Hermes subsequently pushed the bridge implementation before assuming it is live.

---

# Automated build watch

A recurring hourly build watch/coordinator was created from ChatGPT.

Intent:
- inspect GitHub progress,
- if the remote Hermes poller is live, keep non-destructive structured work moving,
- notify Mukund only when owner action is actually required,
- also flag a ~2-hour critical-path stall with no blocker.

Owner-action notification categories:
- credentials/account access,
- explicit Stage 2 approval,
- VPS/host access/details,
- irreversible/destructive action,
- architecture/safety decision.

Do not assume this automation can directly control Hermes unless the GitHub poller is actually installed and consuming queue tasks.

---

# Recent local Git recovery incident

During Gemini work, Hermes/Python appeared hung.

Observed:
- multiple Python processes,
- stale/hung subprocess recovery attempted,
- terminal recovered,
- repo was actually in a Git merge conflict,
- local Gemini task and remote Gemini task had diverged.

Recovery:
1. preserved Hermes' newer local completed Gemini task,
2. resolved merge,
3. fetched/merged current origin/main,
4. pushed,
5. discovered literal conflict markers remained in Markdown,
6. repaired the Markdown remotely,
7. local repo fast-forwarded to repaired state.

Important lesson:
Before killing Python processes, inspect PID + command line.
Do not broadly kill unrelated control-plane Python jobs.

Also:
GitHub edits by ChatGPT and local edits by Hermes can collide on the same file.
Avoid concurrent writes to the same task file where possible.

---

# Current state file is stale

`state/current_company_state.md` still reflects 2026-09-22 state and incorrectly says things such as:
- no execution adapters implemented yet,
- old routability assumptions.

Do NOT use that stale snapshot over newer verified commits/tasks.

It must be refreshed once current bridge/provider work stabilises.

---

# E3/E4/E5 work while owner is away

Hermes should continue all non-credential-dependent work.

E3:
- qualification harness,
- contextual worker × task family/fingerprint × role qualification,
- planner,
- router/meta-selector,
- decomposition review,
- production DAG dispatch,
- context compiler,
- permission compiler,
- temporary team assembly,
- integrator,
- independent critic/verifier,
- conflict handling,
- targeted rework,
- logical replanning,
- failure attribution,
- outcome learning,
- exploration/shadow rules,
- rationale/trace/why auditing.

E4:
- predictive provider/resource exhaustion,
- runway,
- protected reserves,
- checkpointing,
- state handover,
- equivalent-worker continuity/failover,
- owner escalation if no safe equivalent worker exists.

E5:
- safe/degraded mode,
- outage handling,
- malformed output handling,
- failure drills,
- convergence enforcement,
- owner override UX/audit,
- recovery path.

Hard gates remain:
- no fabricated model IDs/usage/cost/quota,
- UNKNOWN stays UNKNOWN,
- no smoke=>qualification shortcut,
- no routable=true without verified readiness,
- no raw CoT logging,
- no direct E3 SQL writes into E1/E2 databases,
- no silent quality-floor degradation,
- no infinite retry loops,
- Stage 2 production requires explicit owner approval.

---

# Laptop vs VPS — latest architecture discussion

This is the newest design discussion and is **NOT yet a formally approved replacement** for the current full-scope VPS plan.

Mukund observed:
- his laptop has strong hardware,
- it is normally always on,
- Hermes is already accessible through Discord,
- GitHub provides shared control-plane storage/backup of curated repo state,
- his uncle could collaborate through GitHub/structured queues.

Conclusion discussed:
A VPS is **not technically required** for:
- uncle collaboration,
- remote task submission,
- Discord control,
- GitHub-mediated agent-to-agent handoff.

However, laptop-only has real flaws:

1. Same-machine control failure:
   Discord/Hermes remote control depends on the same laptop/Hermes stack being healthy.
   If the host or Hermes fails, the remote control path fails with it.

2. GitHub is not a complete runtime backup:
   GitHub intentionally does not contain API keys, live databases, all runtime state, caches/temp artifacts, etc.

3. Remote command != host recovery:
   Discord is excellent for healthy-system operation, but cannot repair a dead host, dead connector, Windows issue, network outage, etc.

4. Workload contention:
   The laptop is both Mukund's workstation and proposed production node; user reboots/drivers/heavy local workloads can interfere with always-on service behaviour.

5. No independent failure domain:
   If power/internet/hardware fails, all execution stops unless a secondary node exists.

Preferred architecture discussed:

**Laptop = Primary Execution Node**
- Hermes
- E1/E2/E3/E4/E5
- heavy execution
- local tools/files
- API workers/local AI
- Discord

**GitHub = control/collaboration/curated-state plane**
- tasks,
- handovers,
- decisions,
- queue,
- code/config,
- collaboration provenance.

**Optional small VPS later = Control / Watchdog / Failover Node**
- heartbeat monitoring,
- queue/status persistence,
- alerts,
- public webhook/collaboration gateway if needed,
- lightweight failover coordination,
- possibly backup/status relay.

The VPS would NOT need to replace the stronger laptop or run the heavy AI workload.

This can be a better long-term architecture than migrating the entire Chief of Staff to weaker rented hardware.

IMPORTANT:
The current authoritative deadline file still says full VPS cutover is required.
Do not silently remove that requirement.
Next chat should ask Mukund whether he wants to formally change the deployment architecture to:
`Laptop Primary Production Node + optional/lightweight VPS control/failover later`
or keep the existing full VPS cutover requirement.

---

# Uncle collaboration

No VPS is inherently required.

Initial collaboration can be:

Uncle's agent
-> structured GitHub collaboration/queue interface
-> Mukund's Hermes
-> execute under Mukund's policies
-> return result + provenance

Keep:
- separate owner authority,
- separate credentials,
- separate worker pools,
- explicit task delegation,
- provenance,
- permission-scoped access,
- no silent mutation across systems.

Do NOT put uncle inside Mukund's unrestricted Hermes trust domain.

---

# Immediate next-chat checklist

1. Fetch latest GitHub commits FIRST.
2. Verify whether Hermes pushed:
   - local reported `aa38126` generic adapter work,
   - the GitHub remote-task poller implementation.
3. Verify bridge:
   - polling actually running,
   - scheduled persistence,
   - claim/deduplication works,
   - kill switch works,
   - test job transitions pending -> running -> completed,
   - blocked-owner-action path works.
4. Check remote queue states.
5. Confirm Hermes continues E3/E4/E5/deployment prep while Mukund is away.
6. When Mukund returns, provision the seven provider API keys.
7. After each key:
   auth -> live model discovery -> adapter compatibility -> smoke -> usage -> E2 linkage -> registry -> regressions.
8. Retry Codex after usage reset.
9. Update stale `state/current_company_state.md`.
10. Ask Mukund for a formal deployment decision:
    - keep full VPS cutover, OR
    - laptop as Primary Production Node + harden backups/recovery + optional small VPS control/failover later.
11. Do not approve E3 Stage 2 production without Mukund's explicit approval.

---

# Source-of-truth / recent commits

Relevant recent shared commits at handover creation:
- `240b14b3b8a05af6826f641a8fe1addd3e112314` — owner TODO for remaining provider keys
- `b7fc298abff4ca893cdb404b2d749fdb2e42c111` — bridge validation/autonomous continuation queue job
- `ffa33e7655bc6b37f5981baccc49e6b84074ac63` — remaining provider credentials + parallel continuation
- `6324ad6975e0ee72efe926138c9070396fb4cad4` — full operational build queue job
- `f6a00a037193e41ac0a81170dab330b8308b8fce` — secure Hermes GitHub remote queue specification
- `c8b86e2539dcf47c155b4e3807344709d337f3ad` — repair Gemini task conflict markers
- `69f1f74ea71c60f170e4eee14ef26ab35a8c2765` — Gemini E3 provider setup complete
- `22206dbbf17884e5c0b19a1b356110a425c37cc3` — DeepSeek setup merged complete
- `8671de487586fa9ab7fcf9b1fdac9029aa8d1730` — Codex hardening
- `2e99cbfefc4008873d855dab3a30b9c38ab6cd77` — full operational build + VPS cutover plan

Always re-fetch recent commits because Hermes may have pushed more after this handover was created.
