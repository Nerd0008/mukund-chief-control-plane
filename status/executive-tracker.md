# Executive Tracker — Chief Control Plane

> **GENERATED FILE — DO NOT EDIT BY HAND.** Every figure below is rendered
> from `status/canonical-status.json` by `python scripts/status_render.py`.
> Change the canonical status source, then regenerate. Verify with
> `python scripts/status_verify.py` (or the suite `scripts/tests/test_status_consistency.py`).

- Canonical source: `status/canonical-status.json` (schema v1.0)
- Generation command: `python scripts/status_render.py`
- Verification command: `python scripts/status_verify.py`
- Status as of (newest incorporated evidence): **2026-09-24T21:10:44Z**
- Newest evidence run: `2026-09-24T21-09-18Z-e3-provider-verification-regression` — **PASS (22 suites / 606 collected / 606 passed / 0 failed)**

## 1. Code and release identity

| Field | Value |
|---|---|
| Repository | https://github.com/Nerd0008/mukund-chief-control-plane.git |
| Branch | main |
| Authoring HEAD | `6cbb573aaaf90cd32bd69b819c96d38a1cae642e` |
| Verified evidence SHA | `6cbb573aaaf90cd32bd69b819c96d38a1cae642e` |
| Supported Python | 3.11.16 |
| Unsupported | 3.14.x |
| Dependency manifest / lock | `requirements.txt` / `requirements.lock` |
| Release identity doc | `docs/RELEASE.md` |

## 2. Executive Brain — implementation, verification, enablement, deployment

Implementation completion, Stage 2 enablement and production deployment are three
separate states and are never collapsed into one.

| Phase | Scope | Implementation | Verified | Stage 2 | Production deployed |
|---|---|---|---|---|---|
| **E1** | Intake, classification, immutable quality floors, owner overrides, audit integrity | verified | ACTIVE | n/a | no |
| **E2** | Resource Governor telemetry, provider capacity/state tracking, deterministic Daily Resource Brief | verified | ACTIVE | n/a | no |
| **E3** | Intelligent multi-model orchestration, team assembly, qualification, execution DAGs, verification, rationale audit | verified | IMPLEMENTED AND VERIFIED, STAGE 2 NOT ENABLED | NOT ENABLED | no |
| **E4** | Predictive exhaustion, protected reserves, resource-driven checkpointing, handover, equivalent-worker failover | verified | IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES) | n/a | no |
| **E5** | Safe/degraded mode, failure drills, outage and malformed-output handling, convergence enforcement, owner override UX and recovery | verified | IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES) | n/a | no |

- **E1** — 32 collected / 32 passed (suite "E1 executive brain runtime matrix").
  - E1 passes only because this host's machine-local Hermes runtime root is present; on a bare clone it is truthfully recorded `unavailable`.
- **E2** — 45 collected / 45 passed (suite "E2 governor / provider adapters").
  - Same machine-local runtime-root caveat as E1.
- **E3** — E3 baseline 58 / E3 extended 60 / shadow orchestrator 18 / production rehearsal 24 / execution leg 22 / qualification 13 — all pass in the 22-suite run.
  - E3 orchestration, dispatch, deterministic verification gating and evidence-backed qualification are built and real-path evidenced. Stage 2 (production enablement) remains gated: a recorded readiness criterion (Google image real-dispatch settled) is unmet and every newly-credentialed provider refused live dispatch at the billing/entitlement/auth layer, so provider-diverse routing cannot execute.
- **E4** — 36 checks passed / 36 total, real_provider_calls = 0, live stores byte-identical.
  - evidence_kind = stubbed_provider_failure. A real provider outage -> real equivalent-worker failover has NOT been exercised and is not claimed (see production blocker `live-provider-failover-gap`).
- **E5** — 36 checks passed / 36 total; safe-mode entry, owner override audit, recovery refusal/success and the bounded 3-dispatch convergence cap all asserted.
  - The recovery health probe in the drill is a labelled local stub; the real provider-health probe into SafeModeRecovery is not wired and stays owner-gated.

## 3. Roster accounting

**50 roster items — 47 PASS, 3 READY_NEEDS_OWNER_CONFIG, 0 BLOCKED_EXTERNAL, 0 unaccounted.**

| ID | Worker / service | Status | Reason |
|---|---|---|---|
| B12 | Application Inbox / Status Monitor | READY_NEEDS_OWNER_CONFIG | built + acceptance-passing on fixtures/local export; only the live mailbox feed needs the owner's Gmail read-only OAuth |
| B14 | Company / Role Research Brief Agent | READY_NEEDS_OWNER_CONFIG | built; every brief reports research_needed until an owner-approved research provider exists |
| C03 | Deployment Prep / Manifest / Restore Agent | READY_NEEDS_OWNER_CONFIG | manifest/preflight/backup-restore prepared and verified; the cutover itself is owner-gated |

Source: `audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/roster_account.json`. Roster definition: `state/v1-agent-roster.md`.

## 4. Regression evidence (newest verification run)

- Suites: **22 run / 22 passed / 0 failed / 0 unavailable**
- Tests: **606 collected / 606 passed / 0 failed**
- Code SHA: `6cbb573aaaf90cd32bd69b819c96d38a1cae642e`
- Interpreter: 3.11.16 (CPython; the isolated pinned-interpreter reproducibility run remains recorded below)
- Source: `audits/evidence/2026-09-24T21-09-18Z-e3-provider-verification-regression/evidence.json`
- Current run: 22 suites / 606 collected / 606 passed / 0 failed at SHA 6cbb573 (this task's post-adapter-correction, post-reconciliation run). Prior runs, reported as measured and never silently rewritten: 22 suites / 606 / 606 at SHA 63cda9b9 (audits/evidence/2026-09-24T15-35-35Z-canonical-status-verification/evidence.json), 21 suites / 583 collected / 583 passed at SHA e9d2195 in a clean isolated CPython 3.11.16 built from requirements.lock (audits/evidence/2026-09-24T15-45-00Z-isolated-release-reproducibility/evidence.json), and 21 suites / 579 collected / 579 passed at SHA 31eecdb (audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/regression/evidence.json). The count grew 579 -> 583 because the Codex identity contract replaced one incorrect exact-match test with five truthful-contract tests, and 583 -> 606 because the canonical-status consistency suite (23 tests) was added.

## 5. Career discovery state

- **B25 unified funnel** — BUILT + EVIDENCED: High-recall semantic discovery is the single funnel for every read-only discovery surface: light deterministic prefilter (title_policy.py) -> DeepSeek bulk semantic triage (classifiers.py) -> bounded Codex second pass -> deterministic eligibility (region/location, work authorisation, clearance/citizenship, mandatory experience, application URL) -> shared dedupe -> tracker manifest.
  - Code: `career-ops/discovery/pipeline.py, career-ops/discovery/classifiers.py, career-ops/discovery/title_policy.py, career-ops/discovery/funnel.py`

| ID | Surface | State | Note |
|---|---|---|---|
| B11 | Recruiter / intermediary Watch Agent | BUILT + EVIDENCED (fixtures only, read-only intake) | collect_from_recruiter_watch(); no live recruiter/intermediary watch feed exists yet |
| B19 | LinkedIn Job Discovery Agent | BUILT + EVIDENCED (owner-exported local files only) | collect_from_linkedin() reuses the single LinkedIn parser; no account, session, cookie, API or scraping path exists |
| B20 | LinkedIn Profile / Post Draft Agent | BUILT + EVIDENCED (drafts only, no posting) |  |
| B21 | Networking / Recruiter Outreach Draft Agent | BUILT + EVIDENCED (unsent drafts only, no sending) |  |
| B22 | Interview Prep Agent | BUILT + EVIDENCED |  |
| B26 | Open-Web Research Agent | BUILT + EVIDENCED (one bounded live read-only pass reached public LinkedIn Jobs, Indeed and employer-careers result classes) | robots-respecting HTTP validation; search/listing pages are labelled search_listing and refused tracker handoff; no login, cookie, session or browser used |
| B27 | Owner-Company Priority Watchlist Agent | BUILT + EVIDENCED (fixtures only; owner's real list not supplied) | additive discovery surface in the same funnel; flag gives prominence, never a bypass |

- **Regional workers (B02-B05)** — BUILT + EVIDENCED: UK/Dubai/Japan/Singapore; all four Windows scheduled tasks registered and Ready; canonical workbook hashes unchanged; applications_submitted 0
- **Scheduled orchestrator cutover** — **COMPLETE / PASS** (None, 1/1 attempts): Recorded from the recovery worker's committed evidence; supersedes the earlier parked/blocked record.
  - Evidence: `audits/evidence/2026-09-24T20-33-25Z-career-scheduled-orchestrator-cutover/evidence.json`

Truth boundaries that hold:
- Title matching is a prefilter, never an eligibility decision; the authoritative gates run after semantic classification and cannot be overridden by a model.
- A model label is evidence about a posting, never a fact about the owner's eligibility.
- No application, message, employer/recruiter contact, browser/GUI action or account mutation is performed by any discovery path.
- Canonical workbooks stay byte-identical through engineering acceptance (hash-verified before and after).

## 6. Queue and service state

- **Remote queue** — OPERATIONAL. Hermes remote queue + agent-* dispatch; poller task HermesRemoteQueuePoller at a 2-minute cadence.
- **Owned scheduled tasks** — 8 tasks; logon type InteractiveToken (all eight run only while Mukund is signed in).
  - `Hermes_Gateway`, `HermesRemoteQueuePoller`, `ChiefDiscordSync`, `ChiefCareerBrief`, `ChiefCareerScan-UK`, `ChiefCareerScan-Dubai`, `ChiefCareerScan-Japan`, `ChiefCareerScan-Singapore`
- **Operational services** — BUILT + TESTED 17/17, ON DEMAND ONLY. `scripts/operational_services.py`, see `deployments/10-operational-services.md`.

Known open items:
- The umbrella record `full-operational-build-2026-09-24` remains in running/ with no associated worker process, and poller.handle_task routes any task id containing "operational" to a handler that returns a hardcoded status with no execution evidence — it must not be read as evidence that its steps ran.
- agent-career-scheduled-cutover-recovery-after-watchdog-2026-09-24 completed the scheduled cutover (23/23 checks); the earlier parked record is superseded.
- The running contract for agent-e3-provider-verification-stage2-closeout-2026-09-24 carries a live coordinator override (2026-09-24T20:56Z) forbidding local E3 Stage 2 enablement for that run; the readiness gate reads it and evaluates condition (c) as unsatisfied while it stands.
- Local E3 Stage 2 enablement is deferred to the queued successor task agent-e3-stage2-enable-after-provider-verification-2026-09-24, which is gated on the owner's live authorization plus the provider accounts serving traffic.

## 7. Provider credential readiness

- Roster workers: **10**
- Credentials configured: **10 / 10** (0 absent)
- Absent workers: 
- Present interfaces: codex-cli (auth mode chatgpt), deepseek-v41-flash (direct API, live-verified), google image worker / gemini (routable; content-side intermittency attributed), mistral-small-4 (present; endpoint+model live-verified; provider refuses dispatch HTTP 429), glm-53-flash (present; Z.ai endpoint+model live-verified; provider refuses dispatch HTTP 429 balance), qwen38-27b (present; dashscope-intl endpoint+model live-verified; provider refuses dispatch HTTP 403 Unpurchased), longcat-2.0 (present; direct endpoint+model live-verified; provider refuses dispatch HTTP 402 quota), minimax-m3 (present; endpoint+model live-verified; provider refuses dispatch HTTP 402 balance), step-37-flash (present; StepFun global endpoint+model live-verified; provider refuses dispatch HTTP 402 quota), tencent-hunyuan-hy3 (present; TokenHub international endpoint+model documentation-derived; provider REJECTS the credential HTTP 401 code 401002)
- Routable: `codex-cli`, `deepseek-v41-flash`, `google-nano-banana-2`
- Routable = execution access + implemented adapter + passing smoke test. The three pre-existing workers are routable. All seven newly-credentialed generic API workers are routable=false with smoke_test='FAILED' and qualification='UNPROVEN': credential presence was never treated as routable or qualified, and each refusal is recorded with its exact provider-returned error. E2 linkage was exercised for all seven through the public governor.record_request() interface and every row was read back (status 'error').
- Owner record: `handovers/2026-09-24-provider-configuration-and-final-closeout-handover.md` — Owner handover recording the manual credential configuration. It is superseded on the credential count by the 2026-09-24T20:54:33Z presence probe (10/10 present) and is preserved as the historical record of the setup plus the explicitly deferred adapter corrections.
- Source: `audits/evidence/2026-09-24T20-54-33Z-e3-credential-presence-probe/evidence.json` — Presence-only probe: no network call, no credential value read, printed, logged or stored. Re-run at 2026-09-24T20:54:33Z: all seven remaining provider credentials are now present (still_missing_count = 0). This artifact is git-ignored by the repository credential policy, so it is corroboration on the authoring host and is never required to exist in a clean clone. The committed live-identity and bounded-smoke evidence below is the durable record.

## 8. Stage 2 state

**NOT ENABLED** (gate `scripts/e3_stage2_readiness_gate.py`, verdict 2026-09-24T21:16:01Z)

Failing conditions at the last verdict:
- condition (b) unmet readiness criterion: Google image worker real-dispatch failure resolved (not intermittent)
- condition (c) not satisfied for THIS run: the live coordinator instruction forbids local E3 Stage 2 enablement here and supersedes the earlier embedded authorization; enablement is deferred to the successor task

The post-key sequence ran in full on 2026-09-24 and the override-aware gate was re-run with the clean 22-suite regression. Condition (a) is SATISFIED (10/10 credentials present; provider identity verified for every intended provider - 6/7 live catalogue, 1/7 authoritative documentation). Condition (b) is unmet on exactly one criterion: the Google image real-dispatch condition ('resolved, not intermittent') - the bounded repeat series observed 2/9 recurrences carrying the provider's own finishReason IMAGE_RECITATION. Condition (c) is False for this run because the live coordinator instruction (appended to the running contract at 2026-09-24T20:56Z) forbids local E3 Stage 2 enablement and supersedes the earlier embedded authorization. Independently, all seven newly-credentialed workers were refused by their providers (billing/quota/entitlement/invalid key), so provider-diverse routing cannot execute. NEVER re-run this gate expecting enablement: enablement belongs to the dedicated successor task and needs the owner's live authorization plus the unmet criterion resolved or re-scoped.

## 9. Deployment state

- **State: NOT DEPLOYED** — cutover not authorised.
- **Architecture:** DEFERRED BY OWNER — no final architecture decision recorded. Recorded preference only: laptop-primary + GitHub control/collaboration plane + VPS watchdog/failover, explicitly not a decision.
- **VPS details:** NOT PROVIDED (owner dependency)
- **Preflight:** GO (10 PASS, 1 WARN, 0 FAIL); sole warning: credentials.presence (owner-gated): 7 API worker credential(s) absent
  - Preflight GO means the preparation is complete and no technical check fails; it is not a readiness-to-cut-over verdict, which remains owner-gated.
- **Backup/restore drill:** PASS (10 artifacts)
- Runbook `deployments/07-cutover-runbook.md`, rollback `deployments/08-rollback-and-no-go-checklist.md`, services `deployments/06-service-definitions.md`
- Inbound network: none required by any Chief/Hermes component (outbound 443 only)

## 10. Production blockers (separate from implementation completion)

10 open item(s). Implementation completion is NOT release readiness.

| ID | Blocker | Category | State | Owner action |
|---|---|---|---|---|
| `provider-execution-blocked` | All ten roster credentials are present but the seven newly-credentialed providers refuse live dispatch (billing / entitlement / quota / invalid key) | external_provider | OPEN | required |
| `stage2-not-enabled` | E3 Stage 2 (production enablement) is not enabled | owner_approval | OPEN | required |
| `live-provider-failover-gap` | No live-provider E4 failover / E5 provider-health recovery has been exercised | architecture | OPEN | required |
| `deployment-cutover-decision` | Deployment architecture and VPS cutover are undecided and unauthorised | owner_approval | OPEN | required |
| `offsite-backup-absent` | No off-site backup exists | architecture | OPEN | required |
| `battery-gating` | 7 of 8 Chief scheduled tasks will not run on battery | architecture | OPEN | required |
| `reboot-persistence-unverified` | Reboot survival of 7 of 8 Chief tasks is unverified | owner_approval | UNKNOWN | required |
| `laptop-trust-audit` | Owner-attended laptop UI-event attribution audit not performed | safety | OPEN | required |
| `unattended-interactive-token` | Every Chief task runs only under the interactive user token | architecture | OPEN | required |
| `log-rotation-retention` | Log rotation/retention is not implemented for all live log paths | architecture | OPEN | engineering |

### `provider-execution-blocked` — All ten roster credentials are present but the seven newly-credentialed providers refuse live dispatch (billing / entitlement / quota / invalid key)

- Blocks: live execution of the seven generic API workers and therefore provider-diverse E3 routing; Tencent/Hy3 provider identity stays documentation-derived only
- Evidence: `audits/evidence/2026-09-24T21-00-28Z-e3-provider-bounded-smoke/evidence.json`
- Owner action: Fund / enable the provider accounts so the stored keys can serve traffic: mistral 429 'Rate limit exceeded'; GLM/Z.ai 429 'Insufficient balance or no resource package'; Qwen intl 403 AccessDenied.Unpurchased (purchase qwen3.8-27b); LongCat 402 'Insufficient token quota'; MiniMax 402 'insufficient balance (1008)'; StepFun 402 'exceeded your current quota'; Tencent re-issue a TokenHub API key at https://console.tencentcloud.com/tokenhub/apikey (401 code 401002). Each worker stays routable=false meanwhile.

### `stage2-not-enabled` — E3 Stage 2 (production enablement) is not enabled

- Blocks: production dispatch through the Executive Brain; the live-provider E4/E5 drill
- Evidence: `audits/evidence/2026-09-23T22-53-53Z-e3-stage2-readiness-gate-verdict/`
- Owner action: The post-key verification sequence has now been executed (presence probe, live identity reconciliation, bounded smoke, full regression, bounded real-provider rehearsal, E4/E5 drills, readiness gate). Stage 2 stays disabled because a recorded readiness criterion is unmet (Google image real-dispatch not settled) and every newly-credentialed provider refused live dispatch. Owner decision required: resolve or re-scope the Google-image criterion and fund the provider accounts, then re-run the gate.

### `live-provider-failover-gap` — No live-provider E4 failover / E5 provider-health recovery has been exercised

- Blocks: the claim that real provider-outage failover and real provider-health recovery work; the v1 E4/E5 acceptance question
- Evidence: `audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/e4e5-drills/evidence.json`
- Owner action: Decide whether the stubbed-failure drills (36/36) plus the real-path execution rehearsal are sufficient E4/E5 evidence for v1, or whether a live-provider failover drill is required before cutover. The harness has no live-provider mode and the real provider-health probe is not wired; both are deliberately out of the recorded scope.

### `deployment-cutover-decision` — Deployment architecture and VPS cutover are undecided and unauthorised

- Blocks: any production deployment; every deployment acceptance criterion
- Evidence: `tasks-or-issues/overnight-owner-actions-2026-09-24.md (items 3 and 4)`
- Owner action: Record one written line choosing the deployment architecture, and supply VPS host/account details locally if a VPS path is chosen.

### `offsite-backup-absent` — No off-site backup exists

- Blocks: treating any node as production; both recorded deployment topologies need one before cutover
- Evidence: `tasks-or-issues/overnight-owner-actions-2026-09-24.md (deployment-time facts)`
- Owner action: Choose the off-site backup destination and retention, then authorise engineering to implement it (local backup/restore is already drilled and passing).

### `battery-gating` — 7 of 8 Chief scheduled tasks will not run on battery

- Blocks: unattended laptop-primary operation on battery
- Evidence: `deployments/06-service-definitions.md (section 2); audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/persistence/persistence.json`
- Owner action: Approve re-importing the task definitions with DisallowStartIfOnBatteries/StopIfGoingOnBatteries set to false (or confirm the laptop will always be on mains power).

### `reboot-persistence-unverified` — Reboot survival of 7 of 8 Chief tasks is unverified

- Blocks: the v1 "service survives restart/reboot" acceptance criterion
- Evidence: `audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/persistence/persistence.json`
- Owner action: After the next owner-initiated reboot, confirm all eight tasks return to Ready/Running with advancing Next Run Time; if any of the seven does not, ask engineering to add a logon trigger (small, reversible task re-import).

### `laptop-trust-audit` — Owner-attended laptop UI-event attribution audit not performed

- Blocks: the trust decision for using the laptop as the final production host
- Evidence: `tasks-or-issues/overnight-owner-actions-2026-09-24.md (item 5)`
- Owner action: Perform the recorded audit with Mukund present. Do not clear Edge/shell/Windows Event/Task Scheduler/Defender/Hermes logs or browser artifacts before attribution.

### `unattended-interactive-token` — Every Chief task runs only under the interactive user token

- Blocks: any unattended topology (the laptop must be powered and signed in)
- Evidence: `tasks-or-issues/overnight-owner-actions-2026-09-24.md (laptop availability precondition); persistence.json owner_checklist`
- Owner action: Decide whether to keep the laptop powered and signed in, or approve a service-account/credential change for the scheduled tasks.

### `log-rotation-retention` — Log rotation/retention is not implemented for all live log paths

- Blocks: production log hygiene on the eventual host
- Evidence: `tasks-or-issues/overnight-owner-actions-2026-09-24.md (deployment-time facts)`

## 11. Optional / feature-gated owner decisions (NOT release blockers)

These are recorded so nothing is silent; none of them is claimed to block release
unless the documented product scope requires it.

| ID | Item | Classification | State |
|---|---|---|---|
| `gmail-readonly-oauth` | Gmail read-only OAuth for the Application Inbox / Status Monitor (B12) | feature_gated_optional | READY_NEEDS_OWNER_CONFIG |
| `research-provider` | Company/role research provider (B14) | feature_gated_optional | READY_NEEDS_OWNER_CONFIG |
| `linkedin-live-account` | Live LinkedIn account access | feature_gated_optional | UNTESTED AGAINST THE REAL ACCOUNT (owner-gated by design) |
| `recruiter-live-feed` | Live recruiter/intermediary watch feed (B11) | feature_gated_optional | FIXTURES ONLY |
| `regional-work-authorisation` | Work-authorisation facts for UAE / Japan / Singapore | owner_fact_required | UNKNOWN (never inferred) |
| `dubai-japan-provider-coverage` | Regional provider coverage for the Dubai and Japan lanes | feature_gated_optional | OWNER DECISION PENDING |
| `career-brief-delivery` | External delivery channel for the Career Daily Brief (B23) | feature_gated_optional | LOCAL ONLY, external_channel_health = not_verified |
| `ops-scheduling-cadence` | Scheduling cadence for operational backup / log rotation / briefs | feature_gated_optional | ON DEMAND ONLY |
| `tracker-vocabulary` | Tracker status-vocabulary gaps (assessment invite / Japan rejection / Dubai offer) | feature_gated_optional | OWNER DECISION PENDING |
| `monthly-rollover-policy` | Rotating 2026-09 out of the live workbooks (owner-column rows blocked) | owner_approval | REFUSED, NOT DELETED |
| `legacy-chief-task` | Disposition of the legacy `Mukund Chief of Staff` logon task | owner_approval | RECORDED, NOT CHANGED |
| `e4e5-acceptance-question` | Is the stubbed-failure drill sufficient E4/E5 evidence for v1 acceptance? | owner_approval | OPEN QUESTION |

- **`gmail-readonly-oauth`** — The monitor is built, tested and acceptance-evidenced on an owner-provided local export; only the automatic live mailbox retrieval needs the grant. No documented v1 release criterion requires a live mailbox feed.
  - Owner action (optional): Optionally authorise the read-only OAuth grant (about 10 minutes) following the recorded steps.
- **`research-provider`** — Every JobBrief still works and truthfully reports research_needed; the cited-file path is fully functional. Enabling a source is a terms-of-service decision, not a release gate.
  - Owner action (optional): Optionally name an approved research source, or keep the cited-file path only.
- **`linkedin-live-account`** — The whole LinkedIn layer (B19/B20/B21) is built and evidenced on owner-exported local files and canonical CV text; posting, messaging, connecting and applying are owner-gated by design and no code path performs them.
  - Owner action (optional): Optionally decide whether the live surface should ever have account access, or keep the owner-export path.
- **`recruiter-live-feed`** — The intake collector is built and evidenced against a declared read-only findings export; no live producer exists and none is required by the recorded v1 scope.
  - Owner action (optional): Optionally provide a read-only export or name a source.
- **`regional-work-authorisation`** — The UK lane is unaffected and every non-UK record is explicitly labelled UNKNOWN; nothing mechanically blocks release.
  - Owner action (optional): Optionally state one line per region (for example "UAE: would need sponsorship").
- **`dubai-japan-provider-coverage`** — The lanes are built, scheduled and running bounded read-only dry-run scans; they simply see few region-labelled postings.
  - Owner action (optional): Optionally choose to add a regional provider, keep the agent-driven search path only, or park a region.
- **`career-brief-delivery`** — The brief is built, tested, acceptance-evidenced and scheduled at 07:00 local; delivery somewhere is a separate, unverified step by design.
  - Owner action (optional): Optionally name a delivery channel, or keep it local.
- **`ops-scheduling-cadence`** — Every operational service runs on demand and is tested; only regular cadence needs owner approval because it changes scheduled tasks.
  - Owner action (optional): Optionally approve a cadence.
- **`tracker-vocabulary`** — Affects only what the monitor may propose; such items arrive as owner decisions instead of proposals.
  - Owner action (optional): Optionally extend the relevant tracker validation lists.
- **`monthly-rollover-policy`** — The rollover worker is built and evidenced on copies; the live workbooks contain owner-state rows (uk 26 / dubai 8 / singapore 4) and are deliberately left untouched.
  - Owner action (optional): Optionally decide the rollover disposition for those owner-state rows.
- **`legacy-chief-task`** — Operational-hygiene and conflict risk only; it is recorded as a donor and was not deleted or revived.
  - Owner action (optional): Optionally confirm whether the legacy task should be disabled/removed or kept as a donor.
- **`e4e5-acceptance-question`** — The recorded state does not assume an answer; it is the acceptance framing of `live-provider-failover-gap`.
  - Owner action (optional): Optionally answer the recorded acceptance question.

## 12. Unresolved unknowns

- The Google image no-image response recurred 2/9 with the provider's own finishReason IMAGE_RECITATION; what makes the provider's recitation filter fire on some identical prompts is unknown. No stability claim is made and the vision role is not qualified.
- Reboot survival of the 7 non-Hermes_Gateway Chief tasks is UNKNOWN (a reboot was prohibited by the task stop conditions).
- The Codex CLI served-model identity is UNKNOWN (provider reported as unknown; configured provider/model are recorded separately) and it exposes no usage figures.
- The live-provider failover behaviour is unknown — never exercised.
- Whether the six provider accounts can be funded/entitled so the stored keys serve traffic, and whether the Tencent key belongs to the correct TokenHub product, are owner/provider questions.

## 13. Evidence chronology (newest first)

| At (UTC) | Evidence | Result | What |
|---|---|---|---|
| 2026-09-24T21:16:01Z | `2026-09-24T21-16-01Z-e3-stage2-readiness-gate-verdict` | NOT ENABLED (a=PASS 10/10 credentials, b=FAIL Google image criterion, c=FAIL live coordinator override) | Retry attempt 2 of 3 re-verified the post-key state at HEAD and re-ran the override-aware readiness gate with the newest bounded-smoke evidence and the same clean 22-suite regression. Credentials 10/10 present (presence-only probe, no value read); provider identity still verified for every intended provider; 0/7 newly-credentialed workers execution-ready because every provider refused the bounded call again with the same error class. Verdict unchanged and no gate weakened: Stage 2 stays NOT ENABLED. The unchanged external-provider refusal is a deterministic external blocker, so the task is parked pending owner provider funding rather than re-attempted in a loop. Evidence: bounded smoke audits/evidence/2026-09-24T21-14-53Z-e3-provider-bounded-smoke/evidence.json and gate verdict audits/evidence/2026-09-24T21-16-01Z-e3-stage2-readiness-gate-verdict/evidence.json. |
| 2026-09-24T21:12:42Z | `2026-09-24T21-12-42Z-e3-stage2-readiness-gate-verdict` | NOT ENABLED (a=PASS, b=FAIL, c=FAIL: live coordinator override) | Override-aware E3 Stage 2 readiness gate re-run with the clean 22-suite regression. Credential presence 10/10; provider identity verified for every intended provider; bounded real-provider rehearsal and E4/E5 drills consumed; regressions all pass; integrity isolation and rollback checks pass. Sole unmet readiness criterion is the Google image real-dispatch condition. Condition (c) additionally fails because the live coordinator instruction forbids enablement for this run. All seven provider refusals are recorded as external blockers with their exact provider errors. |
| 2026-09-24T21:11:06Z | `2026-09-24T21-11-06Z-e3-stage2-readiness-gate-verdict` | NOT ENABLED (condition a PASS, condition b FAIL, condition c PASS) | E3 Stage 2 readiness gate re-run with the clean 22-suite regression: credentials 10/10 present; provider identity verified for every intended provider (6/7 live catalogue, 1/7 authoritative documentation); bounded real-provider rehearsal and E4/E5 drills consumed; regressions all pass; integrity isolation and rollback checks pass. Sole unmet criterion is the Google image real-dispatch condition. All seven newly-credentialed provider refusals are recorded as external blockers with their exact provider errors. |
| 2026-09-24T21:10:44Z | `2026-09-24T21-09-18Z-e3-provider-verification-regression` | PASS 22 suites / 606 collected / 606 passed / 0 failed | Clean post-key regression at SHA 6cbb573: every E1/E2/E3/E4/E5 suite, the queue/bridge suites and the canonical-status consistency suite passed after the provider adapter and worker-registry corrections and the canonical-status reconciliation. |
| 2026-09-24T21:06:25Z | `2026-09-24T21-06-25Z-e3-provider-live-identity-probe` | 6/7 LIVE-VERIFIED, 1/7 DOCUMENTATION-DERIVED | Bounded GET /models reconciliation: corrected the stale mappings (mistral-small-4 -> mistral-small-latest, lower-case minimax-m3 -> MiniMax-M3, CN dashscope -> dashscope-intl, api.stepfun.com -> api.stepfun.ai, BigModel CN -> Z.ai international, hunyuan-hy3 -> TokenHub international 'hy3'); LongCat direct API preserved as already correct. Read-only, 0 completion calls. |
| 2026-09-24T21:04:19Z | `2026-09-24T21-04-19Z-e3-production-execution-rehearsal` | PASS - no failed check (7 bounded real provider calls) | Bounded real-provider E3 production rehearsal on the real execution leg at HEAD: planner-decomposed multi-worker plan, per-node deterministic verification, rejection -> repair -> re-verify, dependency-gated dispatch, content-stop stub scenario, production stores isolated. |
| 2026-09-24T21:04:31Z | `2026-09-24T21-04-31Z-e4e5-real-path-drills` | PASS 36/36 (stubbed provider failures, real_provider_calls = 0) | E4/E5 real-path drill harness re-run: checkpoint -> failover -> handover, provider outage, malformed output, convergence enforcement, safe-mode entry, owner override and recovery. The harness has no live-provider mode, so no live-provider failover/recovery is claimed. |
| 2026-09-24T21:02:05Z | `2026-09-24T21-02-05Z-post-keys-regression` | 22 suites / 21 passed (superseded by the clean post-update run) | First post-key regression run after the adapter corrections. The single failure was the status-consistency suite reporting that the new evidence bundles were not yet incorporated into the canonical status source - an authoring step, not a code regression. |
| 2026-09-24T21:00:28Z | `2026-09-24T21-00-28Z-e3-provider-bounded-smoke` | 0/7 EXECUTION-READY - every provider refused dispatch | One bounded real completion per generic API worker (max_tokens=16, single attempt, no retries). All seven FAILED at the provider: mistral 429 rate limit, GLM 429 balance, Qwen 403 Unpurchased, LongCat 402 quota, MiniMax 402 balance, StepFun 402 quota, Tencent 401 invalid key. E2 rows recorded for all seven via governor.record_request(). No credential value printed, logged or stored. |
| 2026-09-24T20:33:25Z | `2026-09-24T20-33-25Z-career-scheduled-orchestrator-cutover` | PASS 23/23 | Career recovery worker: scheduled launcher now invokes the unified high-recall orchestrator with a live-web requirement; the earlier parked cutover lane is superseded. |
| 2026-09-24T20:54:33Z | `2026-09-24T20-54-33Z-e3-credential-presence-probe` | 7 OF 7 CONFIGURED - 0 STILL MISSING | Presence-only credential probe: all seven remaining provider credentials present in Windows Credential Manager. 0 network calls, 0 provider calls, no credential value read or stored. |
| 2026-09-24T20:47:43Z | `2026-09-24T20-47-43Z-e3-credential-presence-probe` | 5 OF 7 CONFIGURED - 2 STILL MISSING | Presence-only credential probe during this task: mistral-small-4, glm-53-flash, qwen38-27b, longcat-2.0 and minimax-m3 present; step-37-flash and tencent-hunyuan-hy3 absent. 0 network calls, 0 provider calls, no credential value read or stored. |
| 2026-09-24T15:38:58Z | `2026-09-24T15-38-57Z-e3-credential-presence-probe` | 3 OF 7 CONFIGURED — 4 STILL MISSING | Presence-only credential probe after the owner's manual configuration: mistral-small-4, glm-53-flash and qwen38-27b present; longcat-2.0, minimax-m3, step-37-flash and tencent-hunyuan-hy3 absent. 0 network calls, 0 provider calls, no credential value read or stored. Local-only artifact (git-ignored by the repository credential policy); the durable record is the owner handover referenced by provider_credentials.owner_record. |
| 2026-09-24T15:36:57Z | `2026-09-24T15-35-35Z-canonical-status-verification` | PASS | Canonical status verification: 22 suites / 606 collected / 606 passed at SHA 63cda9b, including the new 23-test canonical-status consistency suite; the generated executive tracker and the derived status blocks verified against the canonical status source. |
| 2026-09-24T15:17:52Z | `2026-09-24T15-45-00Z-isolated-release-reproducibility` | PASS | Release reproducibility + Codex identity portability; 21 suites / 583 collected / 583 passed at SHA e9d2195. |
| 2026-09-24T14:45:37Z | `2026-09-24T14-39-12Z-career-scheduled-orchestrator-cutover` | FAIL (parked, execution_error) | Scheduled orchestrator cutover acceptance; one launcher line-ending check failed; no committed effect. |
| 2026-09-24T13:58:06Z | `2026-09-24T13-58-06Z-career-priority-watchlist` | PASS (fixtures only) | B27 owner-company priority watchlist agent: 32/32 checks. |
| 2026-09-24T13:22:22Z | `2026-09-24T13-22-22Z-career-open-web-research` | PASS (bounded live read-only pass) | B26 open-web research agent: 21/21 fixture checks and 24/24 with a bounded live Codex pass. |
| 2026-09-24T05:29:54Z | `2026-09-24T05-29-54Z-unified-discovery-followup-step-verification` | PASS | Unified discovery surfaces (B11 + B19) re-verified at HEAD; canonical_workbooks_unchanged true. |
| 2026-09-24T04:58:25Z | `2026-09-24T04-58-25Z-career-high-recall-discovery` | PASS | B25 high-recall semantic discovery pipeline. |
| 2026-09-24T03:59:44Z | `2026-09-24T03-57-34Z-whole-company-acceptance-final` | PASS (33 PASS, 0 FAIL, 1 owner-gated, 0 unavailable) | Whole-company local acceptance run at SHA 31eecdb: regression 21 suites / 579 passed, E4/E5 drills 36/36, deployment preflight GO (0 FAIL, 1 WARN), backup/restore PASS, roster 50/50. |
| 2026-09-23T22:53:53Z | `2026-09-23T22-53-53Z-e3-stage2-readiness-gate-verdict` | NOT ENABLED | E3 Stage 2 readiness gate (credential-triggered retry, 0 provider calls): 0/7 credentials, Google image intermittency unresolved. |
| 2026-09-23T21:32:41Z | `2026-09-23T21-32-41Z-e3-production-execution-rehearsal` | PASS | Formal production-rehearsal re-run on the real path: decomposed multi-worker plan, rejection to repair to re-verification, 7 bounded real provider calls. |

Historical narrative and per-lane detail remain in `state/full_build_tracker.md` and
`state/current_company_state.md`; those documents keep their own chronology and are
never overwritten by this renderer beyond their generated status header.

