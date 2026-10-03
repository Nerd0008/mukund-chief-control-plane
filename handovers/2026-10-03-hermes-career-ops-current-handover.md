# Hermes / Career Ops handover — 2026-10-03

## Purpose

This handover captures the current state after restoring native Hermes/Nous operation, testing Career Ops, and investigating the latest LinkedIn + incident-delivery regressions.

Use this as the starting point for the next chat/contributor. Do not reopen already-proven architecture unless new evidence contradicts it.

Branch: `fix/e3-whole-repo-architecture`
Starting head at handover creation: `9faa353aa4e7f760f1c9e9661629211705da6d56`

---

## 1. Native Hermes / Discord / Nous state

### Proven working

The custom E3-as-Hermes-provider path was abandoned after repeated tool-call compatibility failures.

The system was restored to native Hermes transport:

```
Discord
-> Hermes native gateway / AIAgent
-> Nous
-> meituan/longcat-2.5-preview:free
-> Hermes native tools / skills / approvals
-> final Discord response
```

A stale vendor interception patch was found in the live Hermes gateway and removed by restoring the pre-patch `gateway/run_turn.py` backup.

The stale patch marker was:
`CHIEF_E3_DISCORD_BRIDGE`

After removal:
- native AIAgent creation resumed;
- native Nous provider resolution resumed;
- E3 provider shim remained inactive.

LongCat 2.0 free alias was rejected by Nous with HTTP 404.
The live Nous catalogue exposed:
`meituan/longcat-2.5-preview:free`

Native tool-loop proof was obtained:
- scheduled run at 08:15 used LongCat 2.5;
- five native tool calls were produced;
- Hermes executed them;
- results returned to the model;
- second model call produced final text;
- response delivered to Discord.

A subsequent live `#chief` request also returned real local system state through Hermes tools, proving Discord inbound -> native agent -> tools -> final response.

Therefore the native Hermes tool architecture itself is operational.

### Open model-selection drift issue

Later, Hermes unexpectedly attempted to use:
`z-ai/glm-5.3-flash`

instead of:
`meituan/longcat-2.5-preview:free`

This produced a Nous balance error.

No root-cause report for that model-selection drift was shared in this chat after the forensic prompt. Do not assume it is fixed.

If it recurs, inspect read-only:
- `config.yaml model.provider/default/base_url/persist_switch_by_default`
- main `#chief` session override
- channel/thread override
- cached AIAgent model
- recent `/model` switch events
- config modification time
- exact precedence tier that selected GLM

Do not fund Nous just to hide the wrong-model selection. The intended Chief model is LongCat 2.5 free unless the owner explicitly changes it.

### Discord offline event

On 2026-10-02 the Discord bot was observed offline. The owner asked Hermes to investigate, but the resulting root-cause report was not provided in this chat.

Treat gateway availability as something to verify, not assume.

---

## 2. Chief personal/context behavior that was validated

Chief successfully retrieved and summarized current owner/context facts and system state.

Important standing rules:
- newest explicit owner instruction beats older files;
- never fabricate;
- distinguish facts from assumptions/inference;
- no public/external action without explicit approval;
- every JD + generated CV is treated as an applied job and should be logged automatically;
- base CV dated 2026-09-25 is authoritative;
- Colourful Aura role and SafePaste metrics are owner-confirmed current facts;
- Apollo Clinic remains disavowed.

Do not reintroduce older contradictory CV assumptions without new owner instruction.

---

## 3. Career Ops live acceptance

Acceptance task:
`tasks-or-issues/2026-09-30-career-all-job-search-agents-live-acceptance.md`
Commit:
`5e3624ff36a2e8e5bde300bfe7465249b2422f57`

Search/discovery scope:
- B01 Career Ops Manager
- B02 UK
- B03 Dubai
- B04 Japan
- B05 Singapore
- B06 eligibility
- B07 dedupe
- B10 Company Watch
- B11 Recruiter Watch
- B19 LinkedIn job discovery intake
- B24 scheduler/run-health
- B25 high-recall semantic funnel
- B26 open-web research

Safety result:
- canonical workbook writes: 0
- applications submitted: 0
- external actions: 0

### Live regional result

UK:
- last run reported: 2026-09-29T22:47Z
- raw discovered: 505
- after prefilter: 15
- semantic accepts: 0
- tracker candidates: 0
- zero stage: `deepseek_accept`

Important nuance:
the 505 findings were stale Company Watch data from 2026-09-23 and included many non-cyber roles.
The 15 candidates could not complete semantic classification because DeepSeek returned insufficient balance.

DeepSeek:
- 3 model calls
- all failed with insufficient balance

Owner stated they can recharge DeepSeek.
No confirmation that recharge or post-recharge test has happened yet.

Correct next step after recharge:
1. one minimal DeepSeek health check;
2. resume the existing 15 UK prefilter candidates from semantic classification only;
3. report semantic accepts/rejects, eligibility, dedupe, candidate manifest;
4. only if that passes, one fresh bounded UK discovery cycle.

Do not rerun every fixture suite just because DeepSeek was recharged.

Dubai:
- discovered_raw: 0
- live mechanism reported not working

Japan:
- discovered_raw: 0
- live mechanism reported not working

Singapore:
- discovered_raw: 0
- live mechanism reported not working

These three fail before the semantic stage, so DeepSeek funding will not fix them.

B26 Open-Web Research:
- live invocation attempted
- Codex CLI present
- no `web_search` tool event observed
- model calls: 0
- blocker is separate from DeepSeek

B11 Recruiter Watch:
- no current recruiter-watch live input/export

B19 LinkedIn discovery:
- no current owner-exported LinkedIn jobs input

### Fixture acceptance

All reported fixture runners passed, including:
- run_acceptance.py
- application inbox
- CV/LinkedIn
- daily brief
- discovery
- interview prep
- job intelligence
- rollover
- scheduled orchestrator
- watchlist
- web research

Owner reported 349 total fixture checks passing.

Do not equate fixture PASS with live operational status.

---

## 4. LinkedIn publish regression — root cause now proven

The owner reported that LinkedIn OAuth/image publishing had worked recently and then appeared to stop.

Codex forensic result:

### Credential state
- client_id: present
- client_secret: present
- access_token: present
- refresh_token: absent
- stored access-token expiry:
  `2026-12-02T00:26:11Z`
- credential reads succeed under Hermes interpreter as:
  `MISTY\mukun`
- no user/account-context change is established

### Root cause 1 — false-negative OAuth readiness

Current status/preflight logic requires:
`client_id + client_secret + refresh_token`

But the real publish path can use a valid access token directly.

Therefore status can say not ready even while publishing is actually possible.

Correct readiness semantics should be:

```
usable_access_token =
    access_token present
    AND expiry valid
    AND expiry still in future with safety skew

refresh_path_available =
    client_id present
    AND client_secret present
    AND refresh_token present

oauth_ready = usable_access_token OR refresh_path_available
```

Missing/invalid expiry should fail closed or report UNKNOWN, not silently assume validity.

### Root cause 2 — latest image failure was CLI misuse

The most recent failed image-publish attempt failed before OAuth/upload:

`linkedin_publish.py: error: unrecognized arguments: --image ...`

A subsequent image post succeeded with HTTP 201.

Therefore:
- OAuth was not the cause of that specific failure;
- the caller used the wrong image argument/interface;
- do NOT blindly add `--image` to the existing text-only publisher.

Trace the successful HTTP 201 image-post path and make the caller use the supported image-aware interface/argument contract.

Yesterday's claimed success was not independently verified, so preserve that uncertainty.

### Current fix task

`tasks-or-issues/2026-10-03-linkedin-readiness-and-incident-ack-fix.md`
Commit/head:
`9faa353aa4e7f760f1c9e9661629211705da6d56`

The task specifies:
- one canonical LinkedIn OAuth readiness helper;
- tests for valid-access-token-only and refresh-path cases;
- correct the image caller contract;
- no live LinkedIn post required for the code fix.

---

## 5. Incident delivery regression — root cause now proven

Local/runtime components reported by Hermes/Codex:
- `incident_flush.py` wrapper under Hermes local scripts
- incidents stored in `runtime/incidents/incidents.jsonl`
- cron id `ebd5d0bcd189`
- cron cadence: every 30 min
- destination: Discord channel `1551586416260161699`

Initial symptom:
cron reported `silent (empty output)` and it looked like stdout/no_agent forwarding was broken.

Codex disproved that diagnosis.

### Proven behavior

- wrapper reproduction: empty stdout, empty stderr, exit 0
- inner script reproduction: empty stdout, empty stderr, exit 0
- output disappeared inside the inner flush script's 60-minute grace-period filter
- UTC/local comparison is correct
- Discord delivery itself works
- 09:40 run produced Discord message id:
  `1555862125103030283`

Therefore `no_agent` / stdout forwarding is not the main defect.

### Actual defect

Successful Discord delivery does not update incident records.

Incidents remain:
`delivered=false`

and repeat later.

The flush timestamp is recorded before delivery confirmation.

Required invariant:
- pending remains pending until Discord ACK;
- successful ACK marks exactly those incident ids delivered;
- failed/no ACK keeps them pending;
- crash between emission and ACK must not lose incidents;
- retries must be idempotent.

Preferred design:
`pending -> in_flight/emitted -> delivered`
or equivalent ACK ledger keyed by stable incident id.

Do not remove the 60-minute grace period unless separately required.
Do not replace deterministic cron delivery with an LLM-agent workaround.

The current fix task at head `9faa353...` contains the required tests and acceptance criteria.

---

## 6. What to do next

Priority order:

1. Implement and offline-test the LinkedIn readiness predicate fix.
2. Trace the successful HTTP 201 image path and fix only the wrong caller/CLI contract.
3. Implement ACK-safe incident delivery state and regression tests.
4. Re-verify Discord gateway is online before any live acceptance.
5. If DeepSeek has been recharged:
   - one minimal health check;
   - resume existing 15 UK candidates from semantic stage;
   - then one fresh bounded UK scan if successful.
6. Debug B26 Codex web-search evidence separately.
7. Debug Dubai/Japan/Singapore raw discovery separately.
8. Investigate Hermes model-selection drift if GLM appears again.

Do not mix these into one giant repair.

---

## 7. Non-negotiable constraints

- local-only topology
- no main merge unless explicitly authorized
- do not expose secrets
- no autonomous job applications
- no recruiter/company outreach
- no LinkedIn posting unless the owner explicitly approves the exact action
- no Gmail mutation
- no OpenRouter automatic fallback
- Google/Nano Banana is for image workflows, not general Chief text routing
- E3 remains orchestration/worker infrastructure, not Hermes' active LLM transport
- native Hermes/Nous path is the known-good Chief transport
- use evidence, not assumptions
- report BLOCKED honestly rather than looping retries

---

## 8. Key files/tasks

- `tasks-or-issues/2026-10-03-linkedin-readiness-and-incident-ack-fix.md`
- `tasks-or-issues/2026-09-30-career-all-job-search-agents-live-acceptance.md`
- `career-ops/linkedin_auth.py`
- `career-ops/linkedin_publish.py`
- `career-ops/linkedin_workflow.py`
- `career-ops/discovery/`
- `career-ops/discovery/web_research.py`
- `career-ops/discovery/scheduled_orchestrator.py`
- `state/v1-agent-roster.md`

Local-only incident scripts may not be committed in the repo; inspect the Hermes runtime on the laptop before assuming repo search should find them.

---

## Suggested opening instruction for the next chat

Read this handover first. Continue from branch `fix/e3-whole-repo-architecture` at `9faa353aa4e7f760f1c9e9661629211705da6d56` or later.

First verify current branch/runtime state, then focus only on the currently proven LinkedIn readiness + image caller bug and the incident ACK bug. Do not redesign Hermes, E3, Career Ops or Discord. Do not make public/external actions without explicit owner approval.
