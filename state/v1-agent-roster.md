# Chief OS v1 — Master Agent / Worker Roster

**Owner:** Mukund  
**Morning target:** major progress / ideally engineering-complete; NOT a stop condition  
**Owner manual configuration:** remaining provider keys only  
**Deployment:** as soon as complete, keys verified, acceptance passed, and deployment-ready  

This roster is the completeness checklist for v1. "Agent" means a managed worker/service under Chief; deterministic tooling is preferred where it is safer and more reliable than an LLM.

## A. Executive / control plane

| ID | Worker / service | Mode | Overnight target |
|---|---|---|---|
| A01 | Hermes Chief of Staff / owner interface | AI coordinator | validate active |
| A02 | E1 Intake, classification and immutable quality-floor controller | deterministic + AI assist | already active; regression |
| A03 | E2 Resource Governor / provider telemetry | deterministic | already active; regression |
| A04 | Daily Resource Brief generator | deterministic | validate delivery/output |
| A05 | E3 Planner / decomposer | AI + deterministic DAG | finish evidence |
| A06 | E3 Router / meta-selector / Qualification Gate | AI proposal + deterministic gate | finish evidence |
| A07 | E3 Context Compiler | deterministic | regression |
| A08 | E3 Permission Compiler | deterministic | regression |
| A09 | E3 Dynamic Team Assembler | deterministic policy + evidence | multi-worker evidence |
| A10 | E3 Worker Execution Manager | deterministic orchestration | real-path evidence |
| A11 | E3 Integrator | AI role under verification | evidence |
| A12 | E3 Independent Critic / Verifier | independent AI/deterministic verifier | evidence |
| A13 | E3 Conflict / targeted-rework / replanning / escalation manager | hybrid | evidence |
| A14 | E3 Capability Learning / benchmark / qualification manager | deterministic evidence + tests | evidence toward qualification |
| A15 | E4 Resource Continuity / checkpoint / failover manager | deterministic | real-path drill |
| A16 | E5 Safe Mode / failure-drill / convergence manager | deterministic + owner escalation | real-path drill |
| A17 | Audit / decision-journal / evidence-state reconciler | deterministic | reconcile final local state |
| A18 | Remote Queue Scheduler / watchdog / recovery supervisor | deterministic | validated; regression |
| A19 | Discord Chief Gateway + archive/sync worker | deterministic bridge | validate live + restart-safe |
| A20 | Company Registry / system inventory worker | deterministic inventory | reconcile local registry with this roster |
| A21 | Local health / backup / restore / boot-persistence worker | deterministic | prepare/validate for deployment |
| A22 | Morning Chief Brief aggregator | deterministic aggregation with Chief summary | build/validate |

## B. Career department

| ID | Worker / service | Mode | Overnight target |
|---|---|---|---|
| B01 | Career Ops Manager / Chief integration | workflow manager | integrate existing Career Ops |
| B02 | UK Job Search Agent | deterministic scanner + policy filter | automate/schedule |
| B03 | Dubai Job Search Agent | deterministic scanner + policy filter | automate/schedule |
| B04 | Japan Job Search Agent | deterministic scanner + policy filter | automate/schedule |
| B05 | Singapore Job Search Agent | deterministic scanner + policy filter | automate/schedule |
| B06 | Job Eligibility / role-policy filter | deterministic rules + optional AI classifier | integrate |
| B07 | Job/Company/Application dedupe-state manager | deterministic | canonical shared state |
| B08 | Excel Tracker Writer | deterministic Python/openpyxl preferred | replace artifact-tool dependency |
| B09 | Monthly Tracker Rollover / archive worker | deterministic | implement/validate |
| B10 | Company Watch Agent | structured ATS/career watcher | build/integrate |
| B11 | Recruiter / intermediary Watch Agent | read-only discovery | integrate with Company Watch |
| B12 | Application Inbox / Status Monitor | read-only email/status ingestion | build; owner OAuth if required |
| B13 | Job Description Analyzer / requirement extractor | AI + deterministic schema | build |
| B14 | Company / Role Research Brief Agent | research worker with provenance | build |
| B15 | CV Tailor Agent | AI drafting under source-truth constraints | integrate existing CV workflow |
| B16 | Cover Letter Agent | AI drafting under source-truth constraints | build/integrate |
| B17 | Application Pack Reviewer / truth & completeness gate | independent verifier | build |
| B18 | Submission Gate / owner-approval handoff | deterministic gate | build; no autonomous submit |
| B19 | LinkedIn Job Discovery Agent | read-only discovery | build/integrate |
| B20 | LinkedIn Profile / Post Draft Agent | AI drafting only | build; no posting |
| B21 | Networking / Recruiter Outreach Draft Agent | AI drafting only | build; no sending |
| B22 | Interview Prep Agent | AI using job/company/application context | build |
| B23 | Career Daily Brief / Pipeline Prioritizer | deterministic ranking + Chief summary | build |
| B24 | Regional Scheduler / run-health monitor | deterministic scheduled-task manager | build/validate |
| B25 | High-recall semantic discovery funnel | AI + deterministic multi-stage pipeline | build |
| B26 | Open-Web Research Agent | bounded read-only web research worker | build |

## C. Release / acceptance

| ID | Worker / service | Mode | Overnight target |
|---|---|---|---|
| C01 | Whole-company Local Acceptance Runner | deterministic scenario runner | build and run after prerequisites |
| C02 | Owner-Action Consolidator | deterministic checklist | keep afternoon TODO exact |
| C03 | Deployment Prep / Manifest / Restore Agent | deterministic deployment tooling | prepare; no cutover overnight |
| C04 | Final Morning Handover Generator | deterministic evidence synthesis | produce by morning |

## Explicit external-action gates

These can be engineered tonight but cannot perform external mutations without owner authorization:
- job application submission,
- LinkedIn post/message/connection/application,
- recruiter/company outreach,
- account/OAuth/credential configuration,
- Stage 2 enablement before the owner-configured provider keys + fresh readiness check,
- final deployment architecture/cutover.

## Completeness rule

Before the morning handover, the local Company Registry and existing machine workflows must be compared against this roster. Any owner-relevant agent/workflow found locally but absent here must either:
1. be added and queued,
2. be explicitly retired/superseded with evidence, or
3. be recorded as an owner-only/external blocker.

No silent omissions.

## Reconciliation record — 2026-09-23 (Company Registry / system-inventory audit)

Executed by task `agent-company-registry-gap-audit-and-runtime-services-2026-09-23` against
`state/v1-agent-roster.md` (method and raw facts:
`audits/evidence/2026-09-23T22-30-00Z-company-registry-gap-audit/`). Deterministic worker:
`scripts/company_inventory.py` (read-only; `--json` output).

Result: **all 50 roster items (A01–A22, B01–B24, C01–C04) were accounted for; no roster entry had
to be added and no locally discovered owner-relevant workflow was left unmapped.**

- Owned Windows scheduled tasks discovered: 7 (`Hermes_Gateway`, `ChiefDiscordSync`,
  `HermesRemoteQueuePoller`, `ChiefCareerScan-UK|-Dubai|-Japan|-Singapore`) — all map to
  A18/A19/B02–B05.
- `Mukund Chief of Staff` (legacy new-custom-Chief logon task) is **superseded by Hermes** and is
  recorded here as a donor, with evidence, rather than deleted. It is not an active v1 service.
- Legacy donors (Career Ops install, July Chief, Mukund OS, new custom Chief) all still exist and
  were inspected as status sources only; none was revived or restructured.
- Real coverage gap found and closed by staging exactly one successor task:
  `agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23` (B09 Monthly Tracker Rollover was
  owned by no task, and the B07/B08 interface produced by the `execution_error` task existed only in
  the unpushed working tree). It explicitly excludes the scope already owned by
  `agent-regional-job-search-agents-and-schedulers-2026-09-23` and
  `agent-company-watch-job-search-integration-2026-09-23`.
- Owner-only dependencies discovered by the audit are recorded in
  `tasks-or-issues/overnight-owner-actions-2026-09-24.md`.

## Status update — 2026-09-24 (job intelligence + application pack task)

Task `agent-job-intelligence-and-application-pack-2026-09-23`. Evidence:
`audits/evidence/2026-09-24T00-50-49Z-job-intelligence-and-application-pack/`.

| ID | Worker / service | Status now | Evidence |
|---|---|---|---|
| B13 | Job Description Analyzer / requirement extractor | **BUILT + EVIDENCED** | `career-ops/job_intelligence.py` + `career-ops/job_brief_schema.json`; extractive only, every line verbatim with `source_line`; desirable items recorded as preferences and never promoted to essential; `candidate_claims: []` with a first-person scanner |
| B14 | Company / Role Research Brief Agent | **BUILT + EVIDENCED (sources owner-gated)** | `job_intelligence.research_brief()`; cited facts accepted, uncited facts rejected, no provider -> `research_needed`; `http` provider disabled (no owner-approved endpoint), `browser` provider disabled by the owner GUI-safety directive |
| B17 | Application Pack Reviewer / truth & completeness gate | **BUILT + EVIDENCED** | `career-ops/application_pack_review.py`; separate module, own re-derivation; truthfulness / coverage / consistency / formatting / unknowns; blocks a deliberately tampered pack |
| B18 | Submission Gate / owner-approval handoff | **BUILT + EVIDENCED — no autonomous submit** | `career-ops/submission_gate.py`; every external action refused; approval must be owner-supplied from outside the repository and bound to `pack_id` + `pack_sha256`; `external_action_performed: false` on every decision |

Not claimed: any live company research (no approved provider), any live vacancy, any
submission, and any "independent AI opinion" — B17 is independent deterministic
re-derivation, not a second model.

## Status update — 2026-09-24 (Career Daily Brief / Pipeline Prioritizer: B23)

Task `agent-career-daily-brief-and-pipeline-prioritizer-2026-09-23`. Acceptance evidence:
`audits/evidence/20260924T013238Z-career-daily-brief/` (**34/34 critical checks**,
0 failures, code SHA `9b414f1` recorded in the artifact; attempt 1's 32/32 runs at
`…T033000Z-…`/`…T034000Z-…` are preserved as the pre-amendment record).

| ID | Worker / service | Status now | Evidence |
|---|---|---|---|
| B23 | Career Daily Brief / Pipeline Prioritizer | **BUILT + EVIDENCED — read-only aggregator** | `career-ops/daily_brief.py` + `career-ops/daily_brief_config.json`; `build` emits a machine-readable brief + concise Chief summary; `inputs`/`policy`/`summary`/`status` subcommands; writes only `runtime/career-ops/daily-brief/` (git-ignored) |
| B23 | Deterministic priority policy | **DECLARED + ENFORCED** | five explicit inputs (deadline 40, stage 20, eligibility certainty 15, freshness 15, owner flag 10); score over the full policy weight so an UNKNOWN lowers the score instead of being imputed; every item reports components, weights, contributions, `coverage_pct`, UNKNOWN inputs and any override; three declared overrides (`urgent_deadline`, `owner_action_min_class`, `unscoreable`) |
| B23 | No fabricated priority facts | **ENFORCED** | `score_semantics.kind = "deterministic_policy_output"`; a status outside the declared stage vocabulary is UNKNOWN (not zero); the UK tracker has no deadline column so deadline is UNKNOWN for every UK row; Dubai/Japan/Singapore work authorisation stays UNKNOWN; a zero-coverage item is labelled, never scored silently |
| B23 | Required content | **DONE** | regional scan health per region, newly added jobs (window-dated tracker rows + scan offers that carry no URL), duplicates suppressed (scanner counters + prior-run idempotency + shared writer dedupe), Company Watch findings, application-status change proposals, interview/follow-up items, owner actions |
| B23 | Idempotency | **PROVEN (quantized)** | a repeat run over unchanged inputs produces the same content digest and input fingerprint, writes **no new bytes**, and appends only to `run-log.jsonl`; the as-of clock is floored to `window.quantize_minutes` (60; `0` disables) so a run inside the same quantum is the same brief, and crossing the quantum is a genuinely new one |
| B23 | Delivery honesty | **ENFORCED** | local file, verified by sha256 read-back; `external_channels: []`, `external_channel_health: "not_verified"` — no messaging/Discord delivery is configured, attempted or assumed healthy |
| B24-related | Morning schedule | **REGISTERED** | `ChiefCareerBrief` daily 07:00 via `career-ops/run_scheduled_brief.cmd`; `install_schedules.py --install-brief/--remove-brief/--status` (brief task included in `--status`) |
| Tests | New suite | **PASS** | `career-ops/tests/test_daily_brief.py` **22 passed**; whole `career-ops/tests/` **300 passed** (was 278 before B23) |
| Safety | Read-only | **VERIFIED** | canonical workbook SHA-256s identical before/after; `applications_submitted: 0`, `external_messages_sent: 0`, `canonical_workbook_writes: 0`; no network/browser/CLI-execution surface in the module (asserted by test) |

Truth boundaries: the brief **owns no career state** — every fact is read back out
of the canonical artifact that owns it, and nothing is re-derived into a new
authoritative record. Scan offers carry no URL and cannot become tracker rows until
one is resolved. The schedule makes the brief available in the morning; delivering
it to a messaging surface is a separate, unverified step (owner decision recorded
in `tasks-or-issues/overnight-owner-actions-2026-09-24.md` item 14). The brief is
not a fit score: a low score with low coverage means "little policy evidence", not
"poor opportunity".

## Status update — 2026-09-24 (LinkedIn people/network layer: B19, B20, B21, B22)

Task `agent-linkedin-networking-interview-support-2026-09-23`. Acceptance evidence:
`audits/evidence/20260924T013000Z-linkedin-outreach-interview-prep/` (27/27 checks,
0 critical failures).

| ID | Worker / service | Status now | Evidence |
|---|---|---|---|
| B19 | LinkedIn Job Discovery Agent | **BUILT + EVIDENCED — read-only** | `career-ops/linkedin_workflow.py` `intake`/`dedupe`/`handoff`; owner-exported local files only, no login/API/scrape/browser; deduped against Career Ops workbook + cross-month ledger + Company Watch registry + Company Watch handoff manifests |
| B20 | LinkedIn Profile / Post Draft Agent | **BUILT + EVIDENCED — no posting** | `draft`; profile/posts are canonical CV text verbatim plus declared structural phrasing, fact-gated by the install's own `verify-cv-facts.mjs`; every draft `draft_unsent` with a `provenance` block |
| B21 | Networking / Recruiter Outreach Draft Agent | **BUILT + EVIDENCED — no sending** | `draft` emits `networking`, `recruiter` and `hiring_manager` variants; explicit `unsent_state` (sent/sent_at/recipient_selected/connection_request_created/message_queued/scheduled/attachments all false or null); the hiring-manager variant names the role/employer only from the resolved Career Ops record (`references_job`) and is omitted when no job context resolves |
| B22 | Interview Prep Agent | **BUILT + EVIDENCED** | `career-ops/interview_prep.py` + `career-ops/interview_prep_schema.json`; consumes JobBrief + cited research + canonical `cv.md`/`profile.yml`/`cv-facts.json`; produces technical/behavioural prep, a likely-question list, `cv.md`-quoted talking points and an explicit unknown list; every question is a deterministic template marked `employer_supplied: false` |

Truth boundaries: the interview prep pack's questions are **generated preparation
prompts**, not employer-supplied questions, and every one says so; talking points
quote canonical lines verbatim (independently re-read from `cv.md` in the acceptance
run); a requirement with no canonical evidence becomes an owner action, never a
claim. A LinkedIn account/API read path does not exist in this runtime, so the live
LinkedIn surface remains **owner-gated and untested against the real account**
(recorded in `tasks-or-issues/overnight-owner-actions-2026-09-24.md` item 13).

## Final account — whole-company local acceptance (2026-09-24)

Task `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`. Machine-readable account:
`audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/roster_account.json` (+ `.md`),
generated by `scripts/whole_company_acceptance.py` (roster C01) and backed by that run's 34 steps.

**All 50/50 roster items (A01–A22, B01–B24, C01–C04) are accounted for: 47 PASS,
3 READY_NEEDS_OWNER_CONFIG, 0 BLOCKED_EXTERNAL, 0 unmapped. No UNKNOWN omission.**

| ID | Worker / service | Final status |
|---|---|---|
| B12 | Application Inbox / Status Monitor | **READY_NEEDS_OWNER_CONFIG** — built + acceptance-passing on fixtures/local export; only the live mailbox feed needs the owner's Gmail read-only OAuth (owner-action item 9) |
| B14 | Company / Role Research Brief Agent | **READY_NEEDS_OWNER_CONFIG** — built; every brief reports `research_needed` until an owner-approved research provider exists (item 11); the cited-file path works |
| C03 | Deployment Prep / Manifest / Restore Agent | **READY_NEEDS_OWNER_CONFIG** — manifest/preflight/backup-restore prepared and verified; the cutover itself is owner-gated (architecture + VPS details + explicit authorisation) |

All other 47 items PASS with evidence recorded in `roster_account.md`; every PASS is a step of the
2026-09-24T03-57-34Z acceptance run, a suite of the 21-suite / 579-test regression at SHA `31eecdb`,
or a named prior evidence artifact. Supplementary owner-gated/external items (provider credentials,
Stage 2, live-provider drill, deployment architecture, reboot persistence, laptop audit, rollover
policy, regional work-authorisation, LinkedIn live surface, operational scheduling) are listed in the
same artifact — none is a roster omission.

Superseded with evidence: the legacy `Mukund Chief of Staff` logon task (recorded in this file's
2026-09-23 reconciliation record) remains a donor; it is not an active v1 service and was not
revived, restructured or deleted.

## Status update — 2026-09-24 (unified discovery surfaces: B11 + B19 funnel integration)

Task `agent-career-unified-discovery-surfaces-followup-2026-09-24`. Evidence:
`audits/evidence/20260924T053909Z-career-high-recall-discovery-acceptance/` (**22/22 checks PASS**,
fixtures only) and the registered whole-company step re-run at HEAD →
`audits/evidence/2026-09-24T05-29-54Z-unified-discovery-followup-step-verification/`
(PASS, `canonical_workbooks_unchanged: true`).

The high-recall semantic discovery contract is now the single funnel for **every** read-only
discovery surface, so no source keeps a private classifier, eligibility rule set or dedupe engine.

| ID | Worker / service | Status now | Evidence |
|---|---|---|---|
| B11 | Recruiter / intermediary Watch Agent | **BUILT + EVIDENCED — read-only discovery intake in the shared funnel** | `career-ops/discovery/pipeline.py` `collect_from_recruiter_watch()`; a declared read-only findings export normalises into the one candidate schema; pre-funnel exclusions keep their own reasons (`recruiter_watch_decision:<d>`, `routed_other_region:<r>`); no agency/employer contact and no live watch producer yet |
| B19 | LinkedIn Job Discovery Agent | **BUILT + EVIDENCED — read-only owner export in the same funnel** | `career-ops/discovery/pipeline.py` `collect_from_linkedin()` reuses `career-ops/linkedin_workflow.py` `parse_inbox_file`/`classify` (one LinkedIn parser); only `job_signal`s become candidates; company-only signals and URL-less lines are counted, never guessed |
| B25-related | Cross-source canonical identity + per-source metrics | **BUILT + EVIDENCED** | `collapse_candidates()` (normalised URL else company+title, provenance per discovery) and `funnel.by_source[source]` (own stage counts, own `rejections_by_reason`, own `zero_attribution`); fixture proof `discovered_raw=6 → canonical 4 → cross-source duplicates removed 2` with one canonical candidate carrying three surfaces' provenance |
| B26 | Open-Web Research Agent | **BUILT + EVIDENCED — read-only active research surface in the same funnel** | `career-ops/discovery/web_research.py` (`SOURCE_WEB_RESEARCH` = `collect_from_web_research()`): generated query matrix (role families × regions × surfaces, owner `site:` shapes preserved, optional company watchlist) → research worker (`codex-web-search` proves a live `web_search` in the execution stream, `captured` replay, or declared `none`) → per-result normalisation into the one candidate schema with provenance → robots-respecting HTTP validation. Search/listing pages are labelled `search_listing` and refused tracker handoff (`classify_result_kind`). Acceptance: `career-ops/run_web_research_acceptance.py` **21/21 PASS** (fixtures) and **24/24 PASS** with a bounded live Codex pass that reached public LinkedIn Jobs, Indeed and employer-careers result classes; bounded live research evidence `audits/evidence/<stamp>-career-open-web-research/`. Owner action: none (read-only, dry-run; no canonical workbook write, no application, outreach or account action) |

Not claimed: no live recruiter/intermediary watch feed and no live LinkedIn account surface was
scanned or contacted. The collectors' evidence is fixture-only, and every discovery path remains
read-only (no login, account/session, scraping, browser, posting, messaging or application).
The open-web lane is the one surface with a real bounded live pass; it logged in nowhere, used no
cookie/session/browser, and the raw result URLs stay owner-private under the git-ignored runtime
directory.


