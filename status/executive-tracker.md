# Executive Tracker — Chief Control Plane

> **GENERATED FILE — DO NOT EDIT BY HAND.** Every figure below is rendered
> from `status/canonical-status.json` by `python scripts/status_render.py`.
> Change the canonical status source, then regenerate. Verify with
> `python scripts/status_verify.py` (or the suite `scripts/tests/test_status_consistency.py`).

- Canonical source: `status/canonical-status.json` (schema v1.0)
- Generation command: `python scripts/status_render.py`
- Verification command: `python scripts/status_verify.py`
- Status as of (newest incorporated evidence): **2026-09-25T18:14:49Z**
- Newest evidence run: `2026-09-25T18-13-26Z-stage2-enable-regression` — **PASS (23 suites / 614 collected / 614 passed / 0 failed)**

## 1. Code and release identity

| Field | Value |
|---|---|
| Repository | https://github.com/Nerd0008/mukund-chief-control-plane.git |
| Branch | main |
| Authoring HEAD | `ec581e6643cd29a3da394cea08892a2b7c837aba` |
| Verified evidence SHA | `8e2847b3d4d8b544a670434c066c23f3fbe6b1f1` |
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
| **E3** | Intelligent multi-model orchestration, team assembly, qualification, execution DAGs, verification, rationale audit | verified | LOCAL STAGE 2 ENABLED; VERIFIED WORKER POOL ONLY | ENABLED | yes |
| **E4** | Predictive exhaustion, protected reserves, resource-driven checkpointing, handover, equivalent-worker failover | verified | IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES) | n/a | no |
| **E5** | Safe/degraded mode, failure drills, outage and malformed-output handling, convergence enforcement, owner override UX and recovery | verified | IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES) | n/a | no |

- **E1** — 32 collected / 32 passed (suite "E1 executive brain runtime matrix").
  - E1 passes only because this host's machine-local Hermes runtime root is present; on a bare clone it is truthfully recorded `unavailable`.
- **E2** — 45 collected / 45 passed (suite "E2 governor / provider adapters").
  - Same machine-local runtime-root caveat as E1.
- **E3** — E3 baseline 58 / E3 extended 60 / shadow orchestrator 18 / production rehearsal 24 / execution leg 22 / qualification 13 / Stage 2 control 2 — all pass in the 23-suite, 614-test regression.
  - Local Stage 2 was explicitly authorized and enabled only for codex-cli, deepseek-v41-flash and google-nano-banana-2. One bounded local production-dispatch acceptance completed through codex-cli and passed deterministic verification. The seven provider-deferred workers remain non-routable; this does not claim provider-diverse routing, VPS deployment, or a live-provider E4/E5 failover.
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

- Suites: **23 run / 23 passed / 0 failed / 0 unavailable**
- Tests: **614 collected / 614 passed / 0 failed**
- Code SHA: `8e2847b3d4d8b544a670434c066c23f3fbe6b1f1`
- Interpreter: 3.14.6
- Source: `audits/evidence/2026-09-25T18-13-26Z-stage2-enable-regression/evidence.json`
- Regression that includes the Stage 2 control tests. A final full regression will supersede this after canonical-status reconciliation.

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
- **Scheduled orchestrator cutover** — **COMPLETE / PASS** (None, 1/1 attempts): Recorded from this lane's final acceptance run. Supersedes the recovery worker's offline-only record (live.attempted=false) and the earlier parked/blocked record; both stay committed and are referenced here. The predecessor's live codex-web-search pass at 2026-09-24T14-39-12Z ran on pre-CRLF-fix bytes and is historical proof only, never proof for this revision. Two bounded offline records are preserved under audits/evidence/superseded/: the pre-live pre-flight of revision 9042ab5 (2026-09-24T21-26-53Z-career-scheduled-orchestrator-cutover-offline-preflight-superseded-by-live-acceptance/) and a pre-commit structural re-verification bound to HEAD 5d7edae (2026-09-24T21-51-05Z-career-scheduled-orchestrator-cutover-offline-reverification-at-head/, PASS 23/23 including launcher_keeps_crlf_line_endings); both are subsumed into the single live acceptance record above. No owner scheduled task was registered, enabled, disabled, replaced or triggered: a read-only query confirmed ChiefCareerScan-UK/Dubai/Japan/Singapore and ChiefCareerBrief all Ready with advancing next-run times, so no schedule change was needed.
  - Evidence: `audits/evidence/2026-09-24T21-28-53Z-career-scheduled-orchestrator-cutover/evidence.json`

Truth boundaries that hold:
- Title matching is a prefilter, never an eligibility decision; the authoritative gates run after semantic classification and cannot be overridden by a model.
- A model label is evidence about a posting, never a fact about the owner's eligibility.
- No application, message, employer/recruiter contact, browser/GUI action or account mutation is performed by any discovery path.
- Canonical workbooks stay byte-identical through engineering acceptance (hash-verified before and after).

## 6. Queue and service state

- **Remote queue** — OPERATIONAL. Hermes remote queue + agent-* dispatch; poller task HermesRemoteQueuePoller at a 2-minute cadence.
- **Owned scheduled tasks** — 12 tasks; logon type InteractiveToken (all twelve run only while Mukund is signed in; preserved deliberately so the user-scoped Windows Credential Manager secrets stay readable).
  - `Hermes_Gateway`, `HermesRemoteQueuePoller`, `ChiefDiscordSync`, `ChiefCareerBrief`, `ChiefCareerScan-UK`, `ChiefCareerScan-Dubai`, `ChiefCareerScan-Japan`, `ChiefCareerScan-Singapore`, `ChiefOperationalBackup`, `ChiefLogRotation`, `ChiefMorningBrief`, `ChiefHealthSnapshot`
- **Operational services** — BUILT + TESTED 17/17, SCHEDULED (4 owner-approved daily tasks, verified live). `scripts/operational_services.py`, see `deployments/10-operational-services.md`.

Known open items:
- The umbrella record `full-operational-build-2026-09-24` remains in running/ with no associated worker process, and poller.handle_task routes any task id containing "operational" to a handler that returns a hardcoded status with no execution evidence — it must not be read as evidence that its steps ran.
- agent-career-scheduled-cutover-recovery-after-watchdog-2026-09-24 completed the scheduled cutover (23/23 checks); the earlier parked record is superseded.
- The running contract for agent-e3-provider-verification-stage2-closeout-2026-09-24 carries a live coordinator override (2026-09-24T20:56Z) forbidding local E3 Stage 2 enablement for that run; the readiness gate reads it and evaluates condition (c) as unsatisfied while it stands.
- Local E3 Stage 2 enablement is deferred to the queued successor task agent-e3-stage2-enable-after-provider-verification-2026-09-24, which is gated on the owner's live authorization plus the provider accounts serving traffic.

## 7. Provider credential readiness

- Roster workers: **10**
- Credentials configured: **10 / 10** (0 absent)
- Absent workers: 
- Present interfaces: codex-cli (auth mode chatgpt), deepseek-v41-flash (direct API, live-verified), google image worker / gemini (routable; content-side intermittency attributed), mistral-small-4 (present; endpoint+model live-verified; provider refuses dispatch HTTP 429), glm-53-flash (present; Z.ai endpoint+model live-verified; provider refuses dispatch HTTP 429 balance), qwen38-27b (present; dashscope-intl endpoint verified; API model corrected to the owner's intended `qwen3.7-plus`, which the live catalogue contains; the corrected id was re-tested and the provider refuses dispatch HTTP 403 AccessDenied.Unpurchased = account entitlement, not a Hermes fault), longcat-2.0 (present; direct endpoint+model live-verified; provider refuses dispatch HTTP 402 quota), minimax-m3 (present; endpoint+model live-verified; provider refuses dispatch HTTP 402 balance), step-37-flash (present; StepFun global endpoint+model live-verified; provider refuses dispatch HTTP 402 quota), tencent-hunyuan-hy3 (present; TokenHub international endpoint+model documentation-derived; provider REJECTS the credential HTTP 401 code 401002)
- Routable: `codex-cli`, `deepseek-v41-flash`, `google-nano-banana-2`
- Routable = execution access + implemented adapter + passing smoke test. The three pre-existing workers are routable. All seven newly-credentialed generic API workers are routable=false with smoke_test='FAILED' and qualification='UNPROVEN': credential presence was never treated as routable or qualified, and each refusal is recorded with its exact provider-returned error. E2 linkage was exercised for all seven through the public governor.record_request() interface and every row was read back (status 'error').
- Owner record: `handovers/2026-09-24-provider-configuration-and-final-closeout-handover.md` — Owner handover recording the manual credential configuration. It is superseded on the credential count by the 2026-09-24T20:54:33Z presence probe (10/10 present) and is preserved as the historical record of the setup plus the explicitly deferred adapter corrections.
- Source: `audits/evidence/2026-09-25T18-08-01Z-e3-credential-presence-status-sanitized/evidence.json` — Sanitized presence-only evidence: all seven generic API credential entries are present; no provider/network calls, credential values, environment values, or Credential Manager target enumeration are included.

## 8. Stage 2 state

**ENABLED** (gate `exec-brain/stage2_control.py (machine-local fail-closed control)`, verdict 2026-09-25T18:16:34Z)

Failing conditions at the last verdict:
- Seven provider-deferred workers remain non-routable pending independent provider recovery or qualification.
- Google image IMAGE_RECITATION intermittency remains accepted as provider-side and is not used by the enabled local Stage 2 pool.

Do not re-run provider smokes until the owner elects to pursue each external billing, entitlement or authentication dependency. Local Stage 2 uses only the three recorded verified workers.

## 9. Deployment state

- **State: LOCAL DEPLOYED** — cutover local-authorised.
- **Architecture:** LOCAL-ONLY BY OWNER — current laptop deployment; VPS topology and cutover remain deferred.
- **VPS details:** DEFERRED BY OWNER — no VPS access or cutover requested.
- **Preflight:** GO (10 PASS, 0 WARN, 0 FAIL); sole warning: none
  - Local deployment preflight rerun after installing the declared dependencies: all checks passed. Local E3 Stage 2 enablement and acceptance are recorded separately; this does not authorize a VPS cutover.
- **Backup/restore drill:** PASS (10 artifacts)
- Runbook `deployments/07-cutover-runbook.md`, rollback `deployments/08-rollback-and-no-go-checklist.md`, services `deployments/06-service-definitions.md`
- Inbound network: none required by any Chief/Hermes component (outbound 443 only)

## 10. Production blockers (separate from implementation completion)

7 open item(s). Implementation completion is NOT release readiness.

| ID | Blocker | Category | State | Owner action |
|---|---|---|---|---|
| `provider-execution-blocked` | All ten roster credentials are present but the seven newly-credentialed providers refuse live dispatch (billing / entitlement / quota / invalid key) | external_provider | OPEN | required |
| `live-provider-failover-gap` | No live-provider E4 failover / E5 provider-health recovery has been exercised | architecture | OPEN | required |
| `deployment-cutover-decision` | Deployment architecture and VPS cutover are undecided and unauthorised | owner_approval | OPEN | required |
| `offsite-backup-absent` | No off-site backup exists | architecture | OPEN | required |
| `reboot-persistence-unverified` | Reboot survival is configured on every owned task; the reboot itself is still unobserved | owner_approval | UNKNOWN | required |
| `laptop-trust-audit` | Owner-attended laptop UI-event attribution audit not performed | safety | OPEN | required |
| `unattended-interactive-token` | Every Chief task runs only under the interactive user token | architecture | OPEN | required |

### `provider-execution-blocked` — All ten roster credentials are present but the seven newly-credentialed providers refuse live dispatch (billing / entitlement / quota / invalid key)

- Blocks: live execution of the seven generic API workers and therefore provider-diverse E3 routing; Tencent/Hy3 provider identity stays documentation-derived only
- Evidence: `audits/evidence/2026-09-24T21-00-28Z-e3-provider-bounded-smoke/evidence.json`
- Owner action: Fund / enable the provider accounts so the stored keys can serve traffic: mistral 429 'Rate limit exceeded' (a single diagnostic call captured the response headers and the provider exposed no Retry-After / x-ratelimit headers, so the cause cannot be separated further from provider evidence); GLM/Z.ai 429 'Insufficient balance or no resource package'; Qwen intl 403 AccessDenied.Unpurchased on the owner's intended `qwen3.7-plus` (purchase/enable qwen3.7-plus for this account — the earlier `qwen3.8-27b` selection was a Hermes-side mapping error, now corrected, and the intended id IS present in the live catalogue); LongCat 402 'Insufficient token quota'; MiniMax 402 'insufficient balance (1008)'; StepFun 402 'exceeded your current quota'; Tencent re-issue a TokenHub API key at https://console.tencentcloud.com/tokenhub/apikey (401 code 401002 repeats on a single GET /v1/models re-probe — TokenHub credential/product/account mismatch). Each worker stays routable=false meanwhile.

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

### `reboot-persistence-unverified` — Reboot survival is configured on every owned task; the reboot itself is still unobserved

- Blocks: the v1 "service survives restart/reboot" acceptance criterion
- Evidence: `audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/persistence/persistence.json`
- Owner action: StartWhenAvailable is now set and StopOnIdleEnd cleared on all eleven owned tasks, and the two light periodic tasks (queue poller, Discord sync) additionally carry a logon trigger, so all eleven are configured to survive a reboot (read-only assessment, `unverified_after_reboot = []`). Engineering must not reboot the laptop, so the reboot itself is unobserved. After your next reboot, run the checklist in `deployments/11-owner-reboot-acceptance-checklist.md` and record the result.

### `laptop-trust-audit` — Owner-attended laptop UI-event attribution audit not performed

- Blocks: the trust decision for using the laptop as the final production host
- Evidence: `tasks-or-issues/overnight-owner-actions-2026-09-24.md (item 5)`
- Owner action: Perform the recorded audit with Mukund present. Do not clear Edge/shell/Windows Event/Task Scheduler/Defender/Hermes logs or browser artifacts before attribution.

### `unattended-interactive-token` — Every Chief task runs only under the interactive user token

- Blocks: any unattended topology where the laptop is not powered and signed in
- Evidence: `audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/verify_after_apply.json`
- Owner action: Decide whether to keep the laptop powered and signed in, or approve a service-account/credential change for the scheduled tasks. The 2026-09-24 hardening deliberately did NOT switch any task to SYSTEM or another account, because the seven provider keys live in the owner's user-scoped Windows Credential Manager and a different account could not read them.

### Resolved blockers (3 — recorded, not deleted)

| ID | Item | State |
|---|---|---|
| `battery-gating` | Battery gating removed from the seven affected Chief tasks | RESOLVED 2026-09-24 (applied + verified live) |
| `log-rotation-retention` | Bounded log rotation/retention over every declared live log path | RESOLVED 2026-09-24 (dry-run then bounded apply evidenced) |
| `stage2-not-enabled` | E3 Stage 2 local enablement gate | RESOLVED 2026-09-25 (local-only, restricted worker pool) |

- **`battery-gating`** — DisallowStartIfOnBatteries and StopIfGoingOnBatteries are false on every owned task, so an unattended run is no longer blocked on battery. Applied by scripts/harden_scheduled_tasks.py with byte-exact reversible pre-change backups under deployments/service-definitions/backups/20260924T221712Z-pre-hardening. Evidence: `audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/verify_after_apply.json`
- **`log-rotation-retention`** — python scripts/operational_services.py rotate-logs [--apply]: archive a log above 5 MB, keep the newest 5 archives per log, over the live Hermes/Chief log paths only. Hermes-managed JSON record stores are recorded out of scope and never pruned. Scheduled daily at 03:00 (ChiefLogRotation). Evidence: `audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/log-rotation/log_rotation.json`
- **`stage2-not-enabled`** — Owner explicitly authorized local Stage 2. The machine-local fail-closed control was enabled only for codex-cli, deepseek-v41-flash and google-nano-banana-2, then one bounded production-dispatch acceptance passed through codex-cli. Provider-deferred workers remain non-routable. Evidence: `audits/evidence/2026-09-25T18-16-34Z-local-stage2-enable-and-acceptance/stage2_enablement.json`

## 11. Optional / feature-gated owner decisions (NOT release blockers)

These are recorded so nothing is silent; none of them is claimed to block release
unless the documented product scope requires it.

| ID | Item | Classification | State |
|---|---|---|---|
| `gmail-readonly-oauth` | Gmail read-only OAuth for the Application Inbox / Status Monitor (B12) | feature_gated_optional | READY_NEEDS_OWNER_CONFIG |
| `research-provider` | Company/role research provider (B14) | feature_gated_optional | READY_NEEDS_OWNER_CONFIG |
| `linkedin-live-account` | Live LinkedIn account access + owner-gated publishing | feature_gated_optional | READY_NEEDS_OWNER_CONFIG (OAuth/publish path built 2026-09-24; no credential set exists) |
| `recruiter-live-feed` | Live recruiter/intermediary watch feed (B11) | feature_gated_optional | FIXTURES ONLY |
| `regional-work-authorisation` | Work-authorisation facts for UAE / Japan / Singapore | owner_fact_required | UNKNOWN (never inferred) |
| `dubai-japan-provider-coverage` | Regional provider coverage for the Dubai and Japan lanes | feature_gated_optional | OWNER DECISION PENDING |
| `career-brief-delivery` | External delivery channel for the Career Daily Brief (B23) | feature_gated_optional | LOCAL ONLY, external_channel_health = not_verified |
| `ops-scheduling-cadence` | Scheduling cadence for operational backup / log rotation / briefs | feature_gated_optional | SCHEDULED 2026-09-24 (owner-approved; verified live) |
| `tracker-vocabulary` | Tracker status-vocabulary gaps (assessment invite / Japan rejection / Dubai offer) | feature_gated_optional | OWNER DECISION PENDING |
| `monthly-rollover-policy` | Rotating 2026-09 out of the live workbooks (owner-column rows blocked) | owner_approval | REFUSED, NOT DELETED |
| `legacy-chief-task` | Disposition of the legacy `Mukund Chief of Staff` logon task | owner_approval | DISABLED (verified live 2026-09-24; kept as a rollback donor, not deleted) |
| `e4e5-acceptance-question` | Is the stubbed-failure drill sufficient E4/E5 evidence for v1 acceptance? | owner_approval | OPEN QUESTION |

- **`gmail-readonly-oauth`** — The monitor is built, tested and acceptance-evidenced on an owner-provided local export; only the automatic live mailbox retrieval needs the grant. No documented v1 release criterion requires a live mailbox feed.
  - Owner action (optional): Optionally authorise the read-only OAuth grant (about 10 minutes) following the recorded steps.
- **`research-provider`** — Every JobBrief still works and truthfully reports research_needed; the cited-file path is fully functional. Enabling a source is a terms-of-service decision, not a release gate.
  - Owner action (optional): Optionally name an approved research source, or keep the cited-file path only.
- **`linkedin-live-account`** — The whole LinkedIn layer (B19/B20/B21) is built and evidenced on owner-exported local files and canonical CV text. An owner-authenticated OAuth publishing path now exists around the B20/B21 drafts (official REST posts endpoint, dry-run by default, duplicate ledger, bounded retries, post-id/timestamp logging) but no LinkedIn app/OAuth credential set exists, so nothing was published and no live PASS is claimed. Posting, messaging, connecting and applying remain owner-gated by design and no code path performs them without a distinct owner-approved action.
  - Owner action (optional): Optionally create a LinkedIn developer app and store the client id/secret + member token in Windows Credential Manager under the chief-linkedin-* targets (never in chat, GitHub or logs). Until then B20/B21 stay generation/review only. See career-ops/linkedin-live-publish.md and the evidence bundle audits/evidence/2026-09-24T22-35-00Z-linkedin-live-publish-integration/.
- **`recruiter-live-feed`** — The intake collector is built and evidenced against a declared read-only findings export; no live producer exists and none is required by the recorded v1 scope.
  - Owner action (optional): Optionally provide a read-only export or name a source.
- **`regional-work-authorisation`** — The UK lane is unaffected and every non-UK record is explicitly labelled UNKNOWN; nothing mechanically blocks release.
  - Owner action (optional): Optionally state one line per region (for example "UAE: would need sponsorship").
- **`dubai-japan-provider-coverage`** — The lanes are built, scheduled and running bounded read-only dry-run scans; they simply see few region-labelled postings.
  - Owner action (optional): Optionally choose to add a regional provider, keep the agent-driven search path only, or park a region.
- **`career-brief-delivery`** — The brief is built, tested, acceptance-evidenced and scheduled at 07:00 local; delivery somewhere is a separate, unverified step by design.
  - Owner action (optional): Optionally name a delivery channel, or keep it local.
- **`ops-scheduling-cadence`** — The owner approved a bounded cadence, so the four operational service schedules are now registered and Enabled: ChiefOperationalBackup 02:30, ChiefLogRotation 03:00, ChiefMorningBrief 06:30, ChiefHealthSnapshot 08:00, staggered away from the 23:45-00:00 career scans and the 07:00 career brief. All four write local artifacts only - no external delivery destination was invented.
  - Owner action (optional): Optionally adjust the cadence or disable a schedule. Evidence: audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/.
- **`tracker-vocabulary`** — Affects only what the monitor may propose; such items arrive as owner decisions instead of proposals.
  - Owner action (optional): Optionally extend the relevant tracker validation lists.
- **`monthly-rollover-policy`** — The rollover worker is built and evidenced on copies; the live workbooks contain owner-state rows (uk 26 / dubai 8 / singapore 4) and are deliberately left untouched.
  - Owner action (optional): Optionally decide the rollover disposition for those owner-state rows.
- **`legacy-chief-task`** — Operational-hygiene and conflict risk only. The task is now confirmed Disabled in Task Scheduler and is retained in place as a donor; it was not deleted and not revived. The superseded stack stays suspended as the owner directed.
  - Owner action (optional): Optionally confirm whether the legacy task should eventually be removed or kept indefinitely as a donor. Evidence: audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/verify_after_apply.json.
- **`e4e5-acceptance-question`** — The recorded state does not assume an answer; it is the acceptance framing of `live-provider-failover-gap`.
  - Owner action (optional): Optionally answer the recorded acceptance question.

## 12. Unresolved unknowns

- The Google image no-image response recurred 2/9 with the provider's own finishReason IMAGE_RECITATION; what makes the provider's recitation filter fire on some identical prompts is unknown. No stability claim is made and the vision role is not qualified.
- Reboot survival of the owned Chief tasks is configured-not-observed: StartWhenAvailable is set and StopOnIdleEnd cleared on all twelve, and the two light periodic tasks carry a logon trigger (read-only assessment unverified_after_reboot=[]), but no reboot was performed (prohibited), so survival is still unverified until the owner runs deployments/11-owner-reboot-acceptance-checklist.md.
- The Codex CLI served-model identity is UNKNOWN (provider reported as unknown; configured provider/model are recorded separately) and it exposes no usage figures.
- The live-provider failover behaviour is unknown — never exercised.
- Whether the six provider accounts can be funded/entitled so the stored keys serve traffic, and whether the Tencent key belongs to the correct TokenHub product, are owner/provider questions.

## 13. Evidence chronology (newest first)

| At (UTC) | Evidence | Result | What |
|---|---|---|---|
| 2026-09-24T22:37:43Z | `2026-09-24T22-37-43Z-post-stage2-integration-gap-audit` | 13 built-but-not-live integration items accounted for; 0 live PASS; operational hardening confirmed | Successor task agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24 (attempt 2) produced a deterministic, read-only built-but-not-live gap audit (`scripts/integration_gap_audit.py`) measuring live state for all thirteen items the authority requires: Gmail read-only OAuth (READY_NEEDS_OWNER_CONFIG, gmail_readonly adapters enabled=false/available=false/credentials_present=false), JobBrief research provider (READY_NEEDS_OWNER_CONFIG), live recruiter/intermediary feed (FIXTURES ONLY), Career Daily Brief external delivery (LOCAL ONLY, not_verified), tracker vocabulary gaps (OWNER DECISION PENDING), current-month rollover (REFUSED, NOT DELETED — owner-state rows), owner company watchlist (AWAITING_OWNER_INPUT), UAE/Japan provider coverage (OWNER DECISION PENDING), LinkedIn live account (READY_NEEDS_OWNER_CONFIG — OAuth/publish path built, no credential set), off-machine backup destination (OPEN, owner decision), laptop trust audit (OPEN, owner-attended), final deployment topology/VPS (OPEN, owner decision), live-provider E4/E5 evidence (OPEN, stubbed drills only). No fixture or dry-run pass was recorded as a live PASS, no credential value was read, and every open item carries its exact next owner step. Owner reboot acceptance checklist added at deployments/11-owner-reboot-acceptance-checklist.md. |
| 2026-09-24T22:35:00Z | `2026-09-24T22-35-00Z-linkedin-live-publish-integration` | BUILT — no live PASS claimed (no LinkedIn app/OAuth credential set exists) | Owner-authenticated LinkedIn publishing path added around the existing B20/B21 draft generators (career-ops/linkedin_auth.py, linkedin_publish.py, linkedin_workflow.py): OAuth credential/token layer keeping client id/secret/refresh/access tokens in Windows Credential Manager (presence-only status) or CHIEF_LINKEDIN_* env on non-Windows — never the repository, argv or a log; an official REST `api.linkedin.com/rest/posts` publish path with guards (credentials present, owner approval flag AND a confirm-token equal to the sha256 of the exact draft body, the B20 review verdict/blocked flag, a local body-hash ledger for duplicate prevention), dry-run by default, and bounded retries on 429/5xx/transport only (a 4xx is never retried). Publication records post URN/URL/timestamp/status/attempts and never a token. No browser automation, session-cookie reuse, CAPTCHA bypass or scraping behind authentication anywhere in the path. 22 new offline tests; a live drill over a real B20 draft recorded. State READY_NEEDS_OWNER_CONFIG: nothing was published and no live PASS is claimed (a dry-run pass is not a live PASS). |
| 2026-09-24T22:22:00Z | `2026-09-24T22-21-49Z-task-hardening-and-operational-schedules` | APPLIED + VERIFIED — battery gating removed, operational services scheduled, log rotation live, legacy task disabled | scripts/harden_scheduled_tasks.py applied the owner-approved service-definition change with byte-exact reversible backups under deployments/service-definitions/backups/20260924T221712Z-pre-hardening and a verified round-trip restore: DisallowStartIfOnBatteries/StopIfGoingOnBatteries set false on the seven affected tasks, StopOnIdleEnd cleared, StartWhenAvailable set, and a logon trigger added to the two light periodic tasks (queue poller, Discord sync). The owner's InteractiveToken principal was preserved on every task — nothing was switched to SYSTEM or another account, so the user-scoped Windows Credential Manager secrets stay readable. Four owner-approved operational schedules were registered and are Enabled (ChiefOperationalBackup 02:30, ChiefLogRotation 03:00, ChiefMorningBrief 06:30, ChiefHealthSnapshot 08:00; local artifacts only, no external delivery destination). Log rotation/retention runs dry-run then bounded apply over every declared live log path (archive above 5 MB, keep newest 5 archives; Hermes-managed JSON record stores recorded out of scope, never pruned). Read-only post-verification recorded still_battery_gated=[] and unverified_after_reboot=[] for all eleven owned tasks. The legacy `Mukund Chief of Staff` task is Disabled and was NOT deleted (kept as a rollback donor). No reboot was performed. |
| 2026-09-24T22:09:28Z | `2026-09-24T22-08-43Z-e3-provider-bounded-smoke` | QWEN MAPPING CORRECTED (qwen3.8-27b -> qwen3.7-plus); re-test HTTP 403 AccessDenied.Unpurchased (account entitlement) | Task agent-provider-debug-qwen-tencent-entitlement-2026-09-24: a live debug of the post-key provider failures. (1) Qwen model-selection reconciliation fixed — the owner's intended model is `qwen3.7-plus` and the committed live catalogue evidence lists both `qwen3.7-plus` and `qwen3.7-plus-2026-05-26`, so the earlier claim that the intended id was absent was wrong; generic_openai_adapter.py and worker_registry.py were corrected from `qwen3.8-27b` to `qwen3.7-plus` (worker_id `qwen38-27b` preserved as the stable credential-registry key; the credential resolves via credential_target `qwen`). The corrected E3 runtime was deployed and exactly ONE bounded real call was made to `qwen3.7-plus` (max_tokens=16, one attempt, no retry): HTTP 403 code=AccessDenied.Unpurchased, no returned model field, no usage — a genuine account entitlement blocker for the intended model. (2) Tencent/Hy3: one bounded GET /v1/models re-probe reproduced HTTP 401 code 401002 (no chat call) — TokenHub credential/product/account mismatch. (3) Mistral: one bounded diagnostic call captured the 429 response headers; the provider exposed no Retry-After / x-ratelimit headers, so the cause cannot be separated further from provider evidence. GLM/LongCat/MiniMax/StepFun were classified from existing catalogue/deterministic-billing evidence without new calls; the Google image IMAGE_RECITATION finding was audited as a provider content-side stop with the Stage-2 criterion left unchanged. No credential value was read, printed, logged or stored; Stage 2 remains NOT ENABLED. |
| 2026-09-24T21:34:00Z | `2026-09-24T21-28-53Z-career-scheduled-orchestrator-cutover` | PASS 39/39 (23 offline structural/whole-company + 16 live) | Final scheduled-cutover acceptance bound to committed revision 9042ab5 (code_sha recorded in the artifact): the offline structural and whole-company checks pass, including launcher_keeps_crlf_line_endings, and a bounded live pass (--live --live-queries 2, broad pass not run) ran over all four regions. The non-GUI Codex CLI web_search mechanism was probed operational before the run and its live search events were observed per region; all four regions recorded production_ready; canonical workbooks byte-identical before and after; 0 workbook writes, 0 applications, 0 employer/recruiter contacts, no LinkedIn mutation, no browser/GUI, no login/cookie/session. Live acceptance on this committed revision is PASS; the predecessor's codex-web-search evidence at 2026-09-24T14-39-12Z stays historical proof on pre-CRLF-fix bytes and the recovery record at 2026-09-24T20-33-25Z was offline-only (live.attempted=false). |
| 2026-09-24T21:21:21Z | `2026-09-24T21-21-21Z-e3-stage2-readiness-gate-verdict` | NOT ENABLED (a=PASS 10/10 credentials, b=FAIL Google image criterion, c=FAIL) | Gated successor task agent-e3-stage2-enable-after-provider-verification-2026-09-24 independently re-ran the readiness gate at HEAD with 0 provider calls and evaluated the enablement rule. Stage 2 was NOT enabled: the predecessor task agent-e3-provider-verification-stage2-closeout-2026-09-24 had reached a terminal blocked state (external_provider), and its fresh evidence proves the mandatory readiness criterion (Google image real-dispatch settled) is still unmet plus all seven newly-credentialed providers still refuse live dispatch. The action left the system unchanged and recorded the exact blocker rather than retrying the external blocker in a loop. |
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

