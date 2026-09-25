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

## Live owner-action summary — current priority

The historical detail below is preserved, but the active order is now:

1. **NOW / Stage-2 critical:** resolve Tencent first, then Qwen, GLM, LongCat, MiniMax, StepFun and Mistral provider-account blockers one at a time.
2. **AFTER providers:** decide the Google image `IMAGE_RECITATION` Stage-2 criterion and whether v1 requires a real live-provider E4/E5 failover drill.
3. **BEFORE production trust:** perform the owner-attended laptop security audit, verify persistence after an owner-initiated reboot, and choose an off-machine backup destination/retention.
4. **AFTER local proof:** choose final laptop/VPS/hybrid topology; provide VPS details locally only if that path is selected.
5. **CAREER OPS, non-Stage-2:** Gmail read-only OAuth, company watchlist names, tracker vocabulary, monthly-rollover policy, and Dubai/Japan discovery-source choice.
6. **OPTIONAL integrations:** LinkedIn live OAuth/publishing, company/role research provider, recruiter feed, and Career Daily Brief delivery channel.
7. **NOT an active proactive TODO:** visa/sponsorship/right-to-work wording. Only handle it when an application/employer explicitly asks, using accurate owner-grounded facts.

Canonical concise view: `deployments/03-owner-action-todo.md`.

## Current owner actions

### 1. Configure all remaining provider credentials
**Status:** ✅ COMPLETE — all ten roster credentials present (verified 2026-09-24T20:54:33Z)  
**Verification:** the presence-only probe now reports `still_missing_count = 0` (10/10 roster workers have a stored credential). No credential value was read, printed, logged or committed.  
**Blocks:** nothing on the credential-absence side any more — but see the new item 1b: every newly-credentialed provider still refuses live dispatch.  
**Action (historical):** credentials were provisioned locally for Mistral, GLM, Qwen, LongCat, MiniMax, Step, and Tencent Hunyuan using approved local secret storage.  
**Continue without owner:** qualification harness, orchestration, multi-worker execution evidence, E4/E5 integration, tests, evidence, bridge hardening, deployment preparation.

### 1b. Fund / enable the seven provider accounts so the stored keys can serve traffic
**Status:** PENDING — OWNER ACTION REQUIRED (recorded 2026-09-24 after the post-key verification)  
**Blocks:** live execution of the seven generic API workers, provider-diverse E3 routing, and the live-provider E4/E5 failover drill.  
**What was verified:** endpoint + API model ID live-verified for 6/7 (Tencent documentation-derived because its key is rejected); every one of the seven bounded smoke completions was refused by the provider itself.  
**Action:** the six working keys need account-level billing/quota/entitlement; Tencent needs a re-issued TokenHub key:
- mistral — HTTP 429 `Rate limit exceeded` (a single diagnostic call on 2026-09-24 captured the response headers; the provider exposed no Retry-After / x-ratelimit headers, so the cause cannot be narrowed further from provider evidence)
- GLM / Z.ai — HTTP 429 `Insufficient balance or no resource package`
- Qwen (intl dashscope) — HTTP 403 `AccessDenied.Unpurchased` on the owner's intended `qwen3.7-plus` (purchase/enable **`qwen3.7-plus`**; the earlier `qwen3.8-27b` selection was a Hermes-side mapping error, corrected 2026-09-24 — the intended id IS present in the live catalogue)
- LongCat — HTTP 402 `Insufficient token quota`
- MiniMax — HTTP 402 `insufficient balance (1008)`
- StepFun (global) — HTTP 402 `exceeded your current quota`
- Tencent Hunyuan/Hy3 — HTTP 401 `code 401002` invalid API key (re-confirmed by a single GET /v1/models re-probe on 2026-09-24); re-issue at https://console.tencentcloud.com/tokenhub/apikey
**Safest next action for Mukund:** fund/enable the six provider accounts and re-issue the Tencent TokenHub key, then re-run `python scripts/e3_provider_bounded_smoke.py` followed by the readiness gate.

### 2. Complete E3 Stage 2 after all provider keys are configured
**Status:** ATTEMPTED — NOT ENABLED (post-key verification executed 2026-09-24; see item 2b)  
**Blocks:** final local Stage 2 enablement only; independent engineering and evidence work continues.  
**Owner directive (historical):** complete local Stage 2 after configuring all remaining provider keys; do not enable overnight before the keys exist; once configured, re-run the full readiness checks and then complete local Stage 2 if all objective gates pass.  
**Outcome of that sequence:** the post-key sequence ran in full (presence probe → live identity reconciliation → bounded smoke → adapter/registry corrections → deploy → full regression → bounded real-provider rehearsal → E4/E5 drills → readiness gate). Stage 2 was **not** enabled because a recorded readiness criterion is unmet and every newly-credentialed provider refused live dispatch — the gate was not weakened to force a pass.  
**Scope:** local Stage 2 only. This does not authorize VPS cutover or a final deployment-architecture choice.

### 2b. Resolve or re-scope the two Stage-2 readiness conditions
**Status:** PENDING — OWNER DECISION REQUIRED  
**Blocks:** local E3 Stage 2 enablement (production dispatch through the Executive Brain).  
**Conditions still unmet:**
1. *Google image worker real-dispatch resolved (not intermittent).* The bounded repeat series observed 2/9 recurrences, each carrying the provider's own `finishReason = IMAGE_RECITATION`; the trigger is provider-side and unknown. The vision role is therefore not qualified and no stability claim is made. Owner decision: accept the attributed provider-side intermittency (re-scoping the criterion) or fund a stability investigation.
2. *Provider execution.* See item 1b — all seven newly-credentialed workers are `routable=false`.
3. *(preserved, not blocking Stage 2)* the live-provider E4/E5 failover/recovery drill has no real mode in the harness; only stubbed-failure evidence exists. That gap is recorded explicitly and is never claimed as live evidence.
**Safest next action for Mukund:** complete item 1b, then decide on condition 1; then re-run `python scripts/e3_stage2_readiness_gate.py`.

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

### 6. State your work-authorisation position for Dubai/UAE, Japan and Singapore
**Status:** PENDING — OWNER FACT REQUIRED (recorded 2026-09-24 by the regional job-search task)
**Blocks:** nothing mechanically; every Dubai/Japan/Singapore record produced by the regional workers is
labelled `Visa unknown` / `JAPAN WORK VISA UNKNOWN` / `WORK PASS UNKNOWN` and carries the flag
"work authorisation UNKNOWN — no owner-stated right to work". No application can be prepared for those
regions until you say which of these is true.
**Why owner-only:** `config/profile.yml#location.authorized_in` lists only the United Kingdom. Whether you
have any right to work in the UAE, Japan or Singapore (or want sponsorship pursued there) is a personal
legal fact that must never be inferred or invented by the build.
**Action:** reply with one line per region — e.g. "UAE: would need sponsorship", "Japan: no route,
drop", "Singapore: open to sponsorship". If a region is a no-go, say so and its lane can be parked
rather than reporting UNKNOWN rows indefinitely.

### 7. Decide on provider coverage for the Dubai and Japan lanes
**Status:** PENDING — OWNER DECISION (recorded 2026-09-24)
**Blocks:** only the yield of the Dubai/Japan regional workers. Their lanes are built, scheduled and
running dry-run scans, but the Career Ops install has no UAE- or Japan-specific provider (checked
`providers/` exhaustively), so those lanes can only see postings that the global/remote boards happen to
label with a UAE/Japan location. Expect near-zero.
**Why owner-only:** closing the gap means either (a) adding/authorising a new regional provider or data
source (cost, terms, account), or (b) accepting that Dubai/Japan discovery stays a manual/agent-driven
path. Both are owner decisions, not engineering defaults.
**Action:** choose one — "add a provider for region X", "keep search_queries (agent-driven path) only",
or "park the region's scanning".

### 9. Authorise the Gmail read-only monitor once (owner OAuth)
**Status:** PENDING — OWNER ACTION (recorded 2026-09-24 by the application-inbox task)
**Blocks:** the *live* mailbox feed for the Application Inbox / Status Monitor
(`career-ops/application_inbox.py`). Everything else about that monitor is built,
tested and evidenced; only the live read needs an owner-authorised account.
**Why owner-only:** it is an OAuth consent and client-secret step against your own
Google account. Automation must not create, hold or approve that grant.
**Exact steps (about 10 minutes):**
1. Google Cloud Console -> create/select a project -> enable **Gmail API**.
2. OAuth consent screen: type `External`, publishing status `Testing`, add your own
   address as a test user.
3. Create an OAuth client of type **Desktop app** and download the client JSON.
4. Save it — outside the repository — to
   `C:\Users\mukun\AppData\Local\hermes\secrets\gmail-readonly\credentials.json`
   (the path in `career-ops/application_inbox_config.json#adapters.gmail_readonly.credential_path`;
   it can also be overridden with the `CHIEF_GMAIL_CREDENTIALS` environment variable).
5. Authorise the single scope `https://www.googleapis.com/auth/gmail.readonly` once
   and save the resulting refresh token to `…\gmail-readonly\token.json`
   (`CHIEF_GMAIL_TOKEN`).
6. Set `adapters.gmail_readonly.enabled` to `true`, then run
   `python career-ops/application_inbox.py adapters` — it must report
   `available: true`.
**Safety:** the scope is read-only. The monitor cannot send, reply, forward,
archive, delete, move, label or mark anything read, and every such action is
refused and logged. Nothing is ever written to a workbook or submitted anywhere.
**Continue without owner:** everything else on this feature is complete and
evidenced. Until step 5, the monitor runs on an owner-provided local export
directory (`career-ops/application_inbox.py run --inbox DIR`) with no loss of
capability other than automatic retrieval.

### 10. Two tracker-vocabulary gaps worth a decision (not blocking)
**Status:** PENDING — OWNER DECISION (recorded 2026-09-24 by the application-inbox task)
**Blocks:** nothing mechanically; it limits what the monitor can propose.
**Exact facts, from the monitor's own drift tests:**
* an **assessment / online test** invitation has no accurate status in *any* of the
  four regional vocabularies, so no status is proposed for one and it appears as an
  owner decision every time (`status_map.*.assessment_invite == null`);
* a **rejection** has no accurate status in the **Japan** vocabulary
  (`Pending, Selected, CV Tailored, Applied, Closed, Discarded`), so a Japan
  rejection also becomes an owner decision rather than a proposed status;
* a **Dubai offer** likewise has no equivalent status in that vocabulary.
**Why owner-only:** changing a tracker's status vocabulary is a change to your own
operational records, and adding a status is an owner decision about how you want
the tracker to read.
**Action (optional):** say whether you want an `Assessment` (and/or `Offer` for
Dubai, `Rejected` for Japan) status added to the relevant tracker's validation
list, or whether you prefer these to keep arriving as owner decisions.

### 11. Optional — authorise a company/role research provider

**Status:** PENDING — OWNER DECISION (recorded 2026-09-24 by the job-intelligence task)
**Blocks:** nothing. Every JobBrief produced today carries `research.status = "research_needed"`
and zero company facts, because no research provider is approved.
**Why owner-only:** enabling a research source is a decision about *which* source and on
what terms (an ATS/company endpoint, a paid API, a terms-of-service question). The build
will not pick one on your behalf, and it will not guess a company fact.
**Two providers are deliberately disabled and recorded as such:** `http`
(`research.providers.http.enabled = false`, "no owner-approved research endpoint is
configured") and `browser` (disabled by your own 2026-09-23 GUI-safety directive — the
system never launches an interactive browser).
**Safe interim:** supply a cited research file and the same interface accepts it —
`python career-ops/job_intelligence.py brief … --research-file RESEARCH.json` where each
fact carries `claim`, `value`, `source`, `citation`. Facts without a citation are rejected.
**Action (optional):** name one research source you are happy with, or say "keep the
cited-file path only".

### 12. How to approve an application pack (the B18 gate's exact interface)

**Status:** DOCUMENTED PROCEDURE — no action needed now (recorded 2026-09-24)
**Blocks:** nothing. It exists so that when a pack IS ready, you know the exact step, and
so the approval is a real owner action rather than a file the build could write itself.

The submission gate refuses to call a pack submission-eligible until an approval record
exists **outside the repository** and binds this exact pack:

1. Read the pack yourself (CV draft, rendered cover letter, the reviewer's findings).
2. Create, outside the repository, e.g.
   `C:\Users\mukun\AppData\Local\hermes\secrets\application-approvals\<pack>.json`:
   `{"approved_by": "Mukund", "approved_at": "<ISO8601>", "pack_id": "<pack-…>",
   "pack_sha256": "<full hash>", "approved_action": "submit_application",
   "acknowledged_unknowns": true}`
   (`acknowledged_unknowns` is only required when the reviewer left unresolved owner-input
   items; set it true only after reading them.)
3. `python career-ops/submission_gate.py status --review <pack_review.json> --approval <that file>`

A valid approval returns `approved_pending_owner_manual_submission` plus an owner
checklist — and still performs **no** external action. You submit manually. An approval
stored inside the repository, or one whose `pack_sha256` no longer matches (the pack
changed), is refused.

### 13. Decide whether the live LinkedIn surface should ever have account access

**Status:** PARTIALLY IMPLEMENTED 2026-09-24 — an owner-authenticated publishing path now
exists; still needs an owner credential set before it can go live.
**Blocks:** nothing. The LinkedIn layer (B19 job discovery, B20 profile/post
drafts, B21 networking/recruiter/hiring-manager outreach drafts) is built, tested
and acceptance-evidenced **entirely on owner-exported local files and canonical CV
text**. As of 2026-09-24 there is also a built-but-not-live OAuth publishing path
around the B20/B21 drafts (`career-ops/linkedin_auth.py`, `linkedin_publish.py`,
`linkedin_workflow.py`; official REST `api.linkedin.com/rest/posts`, owning only
`posts`), but **no LinkedIn app or OAuth credential set exists**, so nothing was
published and no live PASS is claimed.

**Why owner-only:** whether the build may touch the real account at all is a
decision about your own account's terms and risk. No read-only personal-job-data
API is available to this runtime, and your 2026-09-23 GUI-safety directive forbids
driving an interactive browser from this machine, so the honest options are:

1. **keep the current owner-export path** (recommended, no action needed): export
   saved jobs / alerts / followed companies to a local file — e.g.
   `runtime/linkedin/inbox/` — and the workflow parses it read-only. Formats:
   `.json`, `.jsonl`, `.csv`, `.md`, `.txt`;
2. **authorise a different read-only source** you are content with (name it
   explicitly); or
3. **say the live surface stays owner-only forever** and the drafts remain
   copy-paste material for you to send by hand.

**To take publishing live (optional, separate from generation):** create a LinkedIn
developer app through the official API path, store the client id/secret + a member
token in Windows Credential Manager under the `chief-linkedin-*` targets (never in
chat, GitHub, a queue job or a log), then authorise one specific post — publishing
requires both an owner approval flag and a confirm-token equal to the sha256 of the
exact draft body. Dry-run is the default and a duplicate body is refused.
See `career-ops/linkedin-live-publish.md` and the evidence bundle
`audits/evidence/2026-09-24T22-35-00Z-linkedin-live-publish-integration/`.

**Continue without owner:** everything in the layer is complete; nothing else is
blocked. Posting, messaging, connecting and applying are owner-gated by design and
no code path performs them without a distinct owner-approved action (`guard`
refuses and logs each one). No browser automation, session-cookie reuse, CAPTCHA
bypass or scraping behind authentication exists anywhere in the path.

## Resolved / no longer owner-blocking

- Hermes primary execution brain: restored via DeepSeek direct API.
- Nous Portal: currently rate-limited with HTTP 429; do not keep retrying overnight. This is not an owner-action blocker because Hermes has a working DeepSeek path.
- Codex allowance: owner reports reset; fresh Codex worker re-validation remains engineering work, not an owner blocker unless login/account action is actually requested by the CLI.
- Codex CLI worker re-validation: COMPLETED 2026-09-23 (`agent-codex-reset-revalidation-2026-09-23`).
  CLI resolved at `bin/80f78947ad880e6e/codex.exe` v0.155.0-alpha.16.3 (the hardcoded hash path was
  stale), auth mode `chatgpt`, one harmless smoke returned `READY`, E2 linkage
  `obs-20260923-d42e34a5`, routable=true, qualification UNPROVEN. The CLI requested no login,
  account, subscription, or billing action — no owner action outstanding for Codex.

### 5. Laptop availability during unattended overnight work
**Status:** OWNER-SIDE PRECONDITION (found by the 2026-09-23 Company Registry gap audit)
**Blocks:** every scheduled service (queue poller, Discord sync, regional scans) and any unattended
overnight execution.
**Why owner-only:** all four Chief tasks plus the queue poller run under the interactive user token
(`Logon Mode: Interactive only`), so they only run while Mukund is signed in; no engineering change
can make them run for a signed-out user without an owner-approved credential/service change.
**Action:** keep the laptop powered, signed in and configured not to sleep/ hibernate during the
build window (as recorded in `handovers/2026-09-21-chief-os-sprint-handover.md`).

### 6. Confirm task persistence after a reboot (owner-gated verification)
**Status:** CONFIGURED 2026-09-24 — the reboot itself is still unobserved (prohibited by task stop conditions)
**Blocks:** the v1 "service survives restart/reboot" acceptance criterion only.
**Exact facts (re-verified read-only 2026-09-24 by
`scripts/harden_scheduled_tasks.py --verify` and
`scripts/operational_services.py validate-persistence`, evidence in
`audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/`):**
every owned task now carries `StartWhenAvailable` and `StopOnIdleEnd` is cleared; the two
light periodic tasks (`HermesRemoteQueuePoller`, `ChiefDiscordSync`) additionally carry a
logon trigger. The read-only assessment is therefore `unverified_after_reboot = []`. This is
a **configuration** assessment: no reboot was performed (this task's stop conditions prohibit
it), so no survival claim is made either way.
**Action:** after the next owner-initiated reboot, run
`deployments/11-owner-reboot-acceptance-checklist.md` (seven short checks) and record the result.

### 7. Decide the disposition of the legacy `Mukund Chief of Staff` logon task
**Status:** DISABLED 2026-09-24 (verified live) — kept in place as a rollback donor, **not deleted**
**Blocks:** nothing immediately; it is an operational-hygiene and conflict risk.
**Exact facts:** the task previously started the superseded new-custom-Chief Telegram/API/tunnel
stack at sign-in (`…\ChatGPT\CV customizer\mukund-chief-of-staff\…\scr…`), last result
`-1073741510` (terminated). It now reports `Scheduled Task State: Disabled`,
`Next Run Time: N/A`. Hermes is the Chief layer now. The task was **not** deleted — it remains
available as a donor for rollback.
**Action:** confirm whether the legacy task should eventually be removed, or kept indefinitely as
a donor. Engineering will not delete it without that decision.


### 8. After the provider keys are configured — run the exact post-key verification sequence (owner + engineering)

**EXECUTED 2026-09-24 (task `agent-e3-provider-verification-stage2-closeout-2026-09-24`).** The
sequence below was run in full. Outcome: Stage 2 was **not** enabled, because a recorded readiness
criterion is unmet and every newly-credentialed provider refused live dispatch. The gate was not
weakened. See items 1b and 2b for the remaining owner actions.

**Provider adapter verification TODOs (all three RESOLVED 2026-09-24 by live-provider evidence):**
- **Mistral** — confirmed `mistral-small-latest` against the live catalogue; the stale
  `mistral-small-4` string was corrected in the adapter and worker registry. Smoke call then refused
  by the provider itself (HTTP 429 `Rate limit exceeded`).
- **Qwen** — the live Singapore/international catalogue contains BOTH `qwen3.7-plus` and
  `qwen3.7-plus-2026-05-26` (the owner's intended model), and the endpoint was corrected from the CN
  DashScope host to the international host. **Corrected 2026-09-24** (task
  `agent-provider-debug-qwen-tencent-entitlement-2026-09-24`): the earlier closeout wrongly claimed the
  intended id did not appear in the catalogue — it does. The adapter and registry model id were
  corrected from `qwen3.8-27b` to `qwen3.7-plus` (worker_id `qwen38-27b` kept as the stable
  credential-registry key). One bounded re-test of the corrected id was refused by the provider
  (HTTP 403 `AccessDenied.Unpurchased` — the intended model must be purchased/enabled for this account).
- **GLM** — endpoint corrected to the current Z.ai API host and the live `glm-5.3-flash` id confirmed
  from the provider catalogue. Smoke call refused by the provider (HTTP 429 `Insufficient balance or
  no resource package`).
- No worker was marked qualified: qualification stayed `UNPROVEN` for all seven because the smoke
  tests failed at the provider.

**Status:** SEQUENCE EXECUTED; Stage 2 still OWNER-GATED on the two conditions in item 2b. The
live-provider E4/E5 drill (the *only* remaining E4/E5 item) is still not runnable.
**Blocks:** the *only* remaining E4/E5 item — a drill on the **live provider** path (a real provider
failure actually failing a node, and real provider-health re-verification before leaving safe mode).
Everything that can be proven without a real provider is already done and evidenced.

**Why owner-only:** it needs (a) the provider credentials from item 1, which only Mukund can
provision, and (b) Stage 2 enablement, which the owner deferred until those keys exist.

**Exact sequence (run in this order, from the repository root):**

1. `python scripts/e3_credential_presence_probe.py` — must show the seven workers as configured.
2. `python scripts/e3_stage2_readiness_gate.py` — must report the readiness conditions MET and the
   Stage 2 verdict; record its output directory.
3. `python scripts/evidence_runner.py --label post-keys-regression` — must be **579 collected /
   579 passed / 0 failed / 0 errors / 0 unavailable, every suite exit 0** (21 suites; the figure to
   beat, set by the whole-company acceptance run of 2026-09-24T03:57:34Z at SHA `31eecdb`). Any suite
   failure blocks Stage 2.
4. `python exec-brain/e3_execution_rehearsal.py` — the bounded **real-provider** execution rehearsal.
   This is the only driver that spends real provider calls; keep it bounded (its default is ~7 calls).
5. `python exec-brain/e4e5_drill_harness.py` — re-run the E4/E5 drills on the enabled system and
   confirm **36/36 checks** with `real_provider_calls = 0` and `live_stores_changed = []`.
6. Only then complete local Stage 2 (item 2 above).

**Truthful gap to close before claiming live failover coverage (engineering, small, not owner work):**
`e4e5_drill_harness.py` has **no live-provider mode** — it always stubs provider transport, by design.
So a *real* provider outage → real equivalent-worker failover has **not** been exercised and must not
be claimed. Closing it needs two small changes that are deliberately **not** part of this task's
scope (they touch the live execution path and depend on the credentials/Stage 2 state):

- add a bounded `--live` drill mode that dispatches to real routable workers and injects the failure
  through a provider-level mechanism (e.g. an invalid model id / revoked test call), not by stubbing;
- wire a real provider-health probe into `SafeModeRecovery` recovery (today the drill's probe is a
  labelled local stub, and `provider_health_verified` is recorded as `false`).

**Decision needed from Mukund (acceptance question, not an engineering question):** is the
stubbed-failure drill (33/33 checks) plus the existing real-path execution rehearsal sufficient
E4/E5 evidence for v1 acceptance, or is a live-provider failover drill required before cutover? The
recorded state does not assume an answer either way.

### 14. Decide whether the Career Daily Brief should be *delivered* anywhere (not blocking)

**Status:** PENDING — OWNER DECISION (recorded 2026-09-24 by the Career Daily Brief task)
**Blocks:** nothing. The brief (roster B23) is **built, tested, acceptance-evidenced (32/32) and
scheduled**: `ChiefCareerBrief` runs daily at **07:00** and writes a machine-readable brief plus a
concise Chief summary, locally, under `runtime/career-ops/daily-brief/`.
**Why owner-only:** the task explicitly said not to assume an external delivery channel is healthy
until it is verified. Nothing in the system sends, posts or notifies, and this build did **not**
assume otherwise — every brief records
`delivery.external_channel_health = "not_verified"` and `external_channels = []`. Choosing a
channel (or confirming none is wanted) is a decision about where your daily brief should surface and
under whose account.
**Action (optional):** say one of —
1. "keep it local" (recommended, no action needed): open
   `runtime/career-ops/daily-brief/latest.md` (or `latest.json`) yourself, or ask Chief for the
   summary; or
2. name a channel you want it delivered to (e.g. Discord `#career`), and engineering will wire it
   behind that channel's own health check — the delivery path will stay separate from the brief so a
   broken channel can never make the brief look unhealthy.
**Note:** the schedule makes the brief *available* in the morning; it does not deliver it anywhere.

### 15. Approve scheduling the operational services (backup, log rotation, briefs)

**Status:** DONE 2026-09-24 — owner-approved and registered (verified live); this is no longer an open owner action.
**Cadence registered** (staggered away from the 23:45–00:00 career scans and the 07:00 career brief):
`ChiefOperationalBackup` 02:30, `ChiefLogRotation` 03:00, `ChiefMorningBrief` 06:30,
`ChiefHealthSnapshot` 08:00. All `InteractiveToken` + `StartWhenAvailable`, local artifacts only —
**no external delivery destination exists and none was invented**.
**Evidence:** `audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/`.
**Action (optional):** adjust the cadence or disable a schedule at any time; the uninstall path is
`schtasks /Delete /TN <TaskName> /F`.



## Consolidated owner-action order (added 2026-09-24 by the deployment-prep task)

The numbered items above remain the authoritative detail. This is the single
ordered execution list, produced while preparing the deployment package
(`deployments/`; long form in `deployments/03-owner-action-todo.md`):

1. **Configure the seven provider credentials** (item 1). Use
   `python scripts/set_provider_key.py --worker <id>` — it prompts with no
   echo, so no key ever reaches shell history, a log, chat or GitHub. Verify with
   `python scripts/set_provider_key.py --status` (expect 10/10 present).
2. **Post-key verification sequence** (item 8, steps 1–6) — engineering-run; your
   only manual part is step 1 above.
3. **Deployment architecture decision** (item 3) — one written line.
4. **VPS host/account details** (item 4) — only if a VPS path is chosen; supply
   locally, never via GitHub.
5. **Owner-attended laptop security audit** (item 5).
6. **Reboot-persistence confirmation** (item 6).
7. Optional, non-blocking: items 10, 11, 13, 14, 15, the regional work-authorisation
   answer (item 6) and Dubai/Japan provider choice (item 7), the E4/E5 acceptance
   question in item 8, and the legacy `Mukund Chief of Staff` task disposition.

New deployment-time facts surfaced by the deployment-prep task, recorded here so
they are not lost (all recorded, none changed):

- **Battery gating:** 7 of the 8 Chief tasks set
  `DisallowStartIfOnBatteries=true` / `StopIfGoingOnBatteries=true`, so on battery
  the queue poller, Discord sync, daily brief and all four regional scans will not
  run (only `Hermes_Gateway` is exempt). Needs an owner-aware fix before any
  unattended laptop-primary role. See `deployments/06-service-definitions.md` §2.
- **Log rotation/retention is not implemented** for `%LOCALAPPDATA%\hermes\logs`,
  `gateway-starts.log` or `remote-queue\logs\queue.log`.
- **No off-site backup exists.** Both deployment topologies need one before the
  node is treated as production.
- **No inbound network exposure is required** by any Chief/Hermes component
  (outbound 443 only), which simplifies the firewall and the topology choice.
- **Interactive-token constraint confirmed:** every Chief task runs only while
  Mukund is signed in; no unattended topology is possible without an
  owner-approved service-account change.
- **Deployment package prepared** under `deployments/` (manifest, secret checklist,
  owner-action order, dependency inventory, backup/restore plan, service
  definitions with re-importable task XML, cutover runbook, rollback/no-go list,
  acceptance commands) with three new executable verifiers:
  `scripts/deployment_inventory.py`, `scripts/deployment_preflight.py`,
  `scripts/deployment_backup_restore_drill.py`, plus
  `scripts/set_provider_key.py` for item 1.

## Reconciliation — gated Stage-2 activation successor (2026-09-24T21:21Z)

Task `agent-e3-stage2-enable-after-provider-verification-2026-09-24` (the gated successor created by
queue commit `df0514b`). Evidence:
`audits/evidence/2026-09-24T21-21-21Z-e3-stage2-readiness-gate-verdict/`.

- **Stage 2 remains NOT ENABLED — system left unchanged.** The successor's contract permits
  enablement only if the predecessor's fresh evidence proves every mandatory gate green. The
  predecessor `agent-e3-provider-verification-stage2-closeout-2026-09-24` ended **terminal/blocked
  (`external_provider`)**, so the successor's own stop condition required leaving Stage 2 OFF and
  recording the precise blocker instead of retrying.
- **Independent verification (0 provider calls).** The successor re-ran `scripts/e3_stage2_readiness_gate.py`
  at HEAD: condition (a) credentials **PASS** (10/10 present, presence-only, no value read),
  condition (b) **FAIL** on the sole Google image real-dispatch criterion, condition (c) **FAIL**
  (the gate's authorization-marker source is the predecessor contract, now terminal, so it fails
  closed). 0/7 newly-credentialed providers execution-ready; regression evidence all-pass (22 suites).
- **No gate was weakened and nothing was enabled.** No VPS cutover, no deployment, no topology
  decision, no secret exposed.
- **No new owner action was created by this task.** Items **1b** (fund/enable the seven provider
  accounts + re-issue the Tencent TokenHub key) and **2b** (resolve or re-scope the Google-image
  criterion; decide the live-provider E4/E5 failover acceptance question) are confirmed as the exact,
  still-current blockers. Re-run `python scripts/e3_stage2_readiness_gate.py` only after they change.

---

## Owner manual-work target

Mukund's expected manual task is **provider-key configuration only**. Engineering does not stop in the morning; it continues until the system is complete and deployment-ready.

Do not assign ordinary engineering, scripting, testing, scheduling, integration, documentation, acceptance preparation, or deployment preparation to Mukund. If an unforeseen external service genuinely requires owner interaction that cannot be completed safely by the system, record the exact reason and minimum action here, then continue all independent work.

---

## Reconciliation — whole-company local acceptance (2026-09-24T03:57Z)

Task `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`. Evidence:
`audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/`;
handover: `handovers/2026-09-24-morning-handover.md`.

- **Local acceptance: PASS** — 34 steps, **33 PASS, 0 FAIL, 1 owner-gated, 0 unavailable**;
  `canonical_workbooks_unchanged: true`; 0 external mutations; 0 provider calls; code SHA `31eecdb`.
- **No new owner action was created by this task.** The list above is confirmed as the complete and
  current owner-action set, and nothing in it was worked around or silently dropped.
- Two figures in item 8 were stale and are now corrected to the verified current numbers:
  regression baseline **21 suites / 579 tests** (was "15 suites / 438"), drill harness **36/36**
  (was "33/33").
- Items 1 (seven provider credentials) and 2 (post-key Stage 2) remain the critical path. The
  credential gate was deliberately **not** re-run or re-staged (anti-loop directive).
- Deployment preflight re-run inside acceptance: **GO** (11 checks, 0 FAIL, 1 WARN = the seven absent
  credentials), and the backup/restore/rollback drill **PASS** (10 artifacts) — both read-only; no
  cutover, no deployment, no scheduled task changed.
- Roster account: **50/50 items accounted for** — 47 PASS, 3 READY_NEEDS_OWNER_CONFIG (B12 Gmail
  read-only OAuth = item 9; B14 research provider = item 11; C03 cutover owner-gated = items 3/4),
  0 BLOCKED_EXTERNAL, 0 unmapped (`state/v1-agent-roster.md` § "Final account").

---

## Reconciliation — post-Stage-2 integrations and production hardening (2026-09-24T22:37Z)

Task `agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24`. Evidence:
`audits/evidence/2026-09-24T22-37-43Z-post-stage2-integration-gap-audit/audit.md` (read-only gap
audit), `audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/`
(task hardening + schedules), `audits/evidence/2026-09-24T22-35-00Z-linkedin-live-publish-integration/`
(LinkedIn publish path). This section is measured against live state; no historical evidence was
removed.

**Closed / changed by this task (no owner action needed):**

- **Battery gating**: removed from all seven affected tasks; every owned task also gained
  `StartWhenAvailable`, `StopOnIdleEnd` cleared, and the two light periodic tasks a logon trigger.
  Byte-exact reversible backups + a verified round-trip restore exist.
- **Operational service schedules**: registered and Enabled (item 15 above is now DONE).
- **Log rotation/retention**: implemented + scheduled (03:00) and evidenced dry-run then bounded apply.
- **Legacy `Mukund Chief of Staff` task**: verified `Disabled`, kept as a rollback donor (item 7).
- **Reboot persistence**: configured on every owned task; the reboot itself remains unobserved —
  see `deployments/11-owner-reboot-acceptance-checklist.md` (item 6).
- **LinkedIn**: owner-authenticated publish path built around the B20/B21 drafts; no credential set
  exists, so it is READY_NEEDS_OWNER_CONFIG and **no live PASS is claimed** (item 13).

**Still owner-gated (unchanged, exact next step recorded):** provider account funding (1b), the
Google-image / E4-E5 acceptance conditions (2b), deployment architecture + VPS detail (3, 4),
owner-attended laptop trust audit (5), regional work-authorisation facts (6), Dubai/Japan provider
coverage (7), Gmail read-only OAuth (9), tracker vocabulary (10), research provider (11), Career
Daily Brief delivery (14), plus the off-machine backup destination, the owner company watchlist
names and the LinkedIn app credentials. None of these was auto-activated or assumed complete.

**Discipline applied:** no fixture or dry-run result was recorded as a live PASS; no credential
value was read, printed, logged or committed; the laptop was not rebooted, signed out or
power-cycled; no VPS/off-site vendor was chosen; the legacy task was not deleted.

## Owner decision update — 2026-09-25

Mukund accepted the Google image worker's attributed provider-side `IMAGE_RECITATION` intermittency for the **local E3 readiness criterion**. Preserve the observed 2/9 recurrence, provider attribution, bounded retry/fallback evidence and the worker's unqualified/stability status; this decision does not fabricate a stability result or bypass provider-execution evidence. The remaining Stage 2 blocker is live execution readiness for the text-provider roster, and Stage 2 remains disabled until its objective gates pass.

Mukund also directed the project to remain **local-only for now**. VPS architecture, access, deployment and cutover are deferred to a future owner decision. Continue local engineering, qualification, verification, evidence and reversible deployment preparation only.

## Provider evidence update — 2026-09-25

**Tencent Hunyuan Hy3:** PASS. After the owner re-issued and stored the TokenHub key, one bounded smoke through the deployed adapter completed with HTTP 200. The configured and returned model were both `hy3`; model identity was confirmed and E2 linkage was recorded. Evidence: `audits/evidence/2026-09-25T16-20-00Z-tencent-hy3-smoke/`.

This closes Tencent credential/authentication as a provider-execution blocker. It does not establish broad provider readiness, alter the remaining provider-account blockers, qualify any worker beyond the recorded evidence, or enable E3 Stage 2.

**LongCat 2.0:** partial live evidence only. After the owner account change, one bounded smoke reached the configured model and returned HTTP 200 plus provider usage (31 total tokens); the response ended `finish_reason=length` at the 16-token cap, so the strict single-word completion condition did not pass. Catalogue observation confirmed `LongCat-2.0` exists. The result proves endpoint/auth/quota reachability for that call but does not qualify the worker or mark the smoke complete. Evidence: `audits/evidence/2026-09-25T16-30-00Z-longcat-smoke/`.

**LongCat 2.0 correction:** the earlier capped result was caused by LongCat's default
reasoning mode consuming the deliberately tiny smoke budget before visible content was
emitted. The bounded compatibility probe now sends LongCat's documented
`thinking: {"type": "disabled"}` request option for its fixed one-word check only;
ordinary worker contracts retain LongCat's provider default. One fresh, single-attempt
16-token smoke then completed with HTTP 200, returned `LongCat-2.0`, returned `READY`
with finish reason `stop`, and recorded provider-returned usage plus E2 linkage.
Evidence: `audits/evidence/2026-09-25T16-45-00Z-longcat-thinking-disabled-smoke/`.
This resolves the strict smoke failure but does not by itself enable E3 Stage 2.

**MiniMax M3:** one bounded deployed-adapter smoke reached the configured endpoint
and credential but received HTTP 402, provider error `insufficient balance (1008)`.
The failed attempt was recorded through E2; no retry was performed. The exact
remaining owner action is to add MiniMax API balance, then request a new bounded
smoke. Evidence: `audits/evidence/2026-09-25T16-55-00Z-minimax-m3-smoke/`.

**MiniMax M3 recheck:** the current stored credential was rejected with HTTP 401
(`authorized_error`, error code 1004), before a balance condition could be evaluated.
The prior balance observation remains historical; the current first blocker is to
replace the MiniMax API secret in the credential store with an active API key, then
request one fresh bounded smoke. E2 recorded this failed attempt; no retry was made.
Evidence: `audits/evidence/2026-09-25T17-05-00Z-minimax-m3-recheck/`.

**MiniMax M3 current result:** PASS. A fresh bounded smoke completed with HTTP 200;
the provider returned `MiniMax-M3`, supplied a `stop` completion with the required
`READY` content, and E2 linkage was recorded. This supersedes the earlier credential
rejection as the current execution result. Evidence:
`audits/evidence/2026-09-25T17-15-00Z-minimax-m3-recheck-2/`. It does not enable
E3 Stage 2 or qualify the rest of the provider roster.

**GLM-5.3 Flash:** one bounded deployed-adapter smoke reached the configured endpoint
and stored credential but received HTTP 429: `Insufficient balance or no resource
package. Please recharge.` E2 recorded the failed attempt; no retry was made. The
exact remaining owner action is to add GLM account credit or an eligible resource
package, then request a fresh bounded smoke. Evidence:
`audits/evidence/2026-09-25T17-25-00Z-glm-53-flash-smoke/`.

**Mistral Small:** one bounded deployed-adapter smoke reached the configured endpoint
and stored credential but received HTTP 429 `Rate limit exceeded`. E2 recorded the
failed attempt; no retry was made. The exact remaining owner action is to wait for or
increase the Mistral account's usable API rate/tier, then request one fresh bounded
smoke. Evidence: `audits/evidence/2026-09-25T17-35-00Z-mistral-small-smoke/`.

**Mistral Small current result:** PASS. A fresh bounded smoke completed with HTTP 200;
the provider returned `mistral-small-latest`, supplied the required `READY` completion
with finish reason `stop`, and E2 linkage was recorded. This supersedes the earlier
rate-limit result as the current execution evidence. Evidence:
`audits/evidence/2026-09-25T17-45-00Z-mistral-small-recheck/`. It does not enable
E3 Stage 2 or qualify the remaining provider roster.
