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

