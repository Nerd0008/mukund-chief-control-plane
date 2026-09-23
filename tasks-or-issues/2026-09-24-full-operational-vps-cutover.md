# Full Operational Build + VPS Cutover — 2026-09-24 Deadline

Status: ACTIVE — FULL SCOPE / NO INTENTIONAL DEFERRALS
Created: 2026-09-23
Owner: Mukund
Deadline: 2026-09-24 evening

## Owner directive

Complete the full planned system and configure it on the VPS by tomorrow evening.

No MVP reduction.
No intentional deferral of roster workers.
No weakening of E1/E2/E3 quality, qualification, privacy, audit, or owner-approval gates to save time.

Time is recovered through parallelisation, reuse, automation, and immediate blocker escalation — not through architectural shortcuts.

## Definition of done

By cutover, the system should have all of the following completed or have an explicitly documented external blocker that only the owner/provider can resolve:

### Worker pool
All 10 roster workers processed through real provider readiness:
1. Codex CLI
2. Mistral Small 4
3. Google image worker / gemini-3.1-flash-image
4. DeepSeek / deepseek-flash
5. GLM-5.3 Flash
6. Qwen3.8-27B
7. LongCat 2.0
8. MiniMax M3
9. Step 3.7 Flash
10. Tencent Hunyuan Hy3

For every worker:
- credential/interface configured where required
- live identity/model discovery
- separate E3 execution adapter or verified execution interface
- harmless smoke test
- provider-returned usage captured where exposed
- E2 record-request linkage
- truthful routable state
- qualification remains evidence-driven
- no secret leakage
- tests/regressions pass

Codex usage-limit reset is an external blocker if still active; keep testing for availability rather than removing Codex from scope.

### E3
- cold-start benchmark/qualification framework complete
- contextual worker × task-family/fingerprint × role qualification
- planner role operational
- router/meta-selector operational
- decomposition review operational
- execution DAG production path operational
- worker contracts operational
- context compiler operational
- permission compiler operational
- temporary team assembly operational
- integrator operational
- independent critic/verifier operational
- conflict handling operational
- targeted rework operational
- risk-sensitive convergence limits operational
- logical replanning operational
- failure attribution/outcome learning operational
- exploration/shadow rules implemented
- rationale/trace/why audit surfaces operational
- no raw chain-of-thought or secrets in rationale/performance logs
- E1/E2 integration only through public interfaces
- production rehearsal passes
- owner approval for Stage 2 production enablement: STANDING CONDITIONAL APPROVAL granted 2026-09-23 for local enablement once objective local readiness gates pass; no additional approval prompt is required while owner is asleep or at work

### E4
Implement the approved resource-continuity scope:
- predictive provider/resource exhaustion
- runway calculation
- protected reserves
- resource-driven checkpointing
- checkpoint/state handover
- equivalent-worker continuity/failover
- resource-aware continuation without silent quality degradation
- owner escalation when no equivalent safe worker exists
- tests + audit/telemetry coverage

### E5
Implement the approved resilience/safe-operation scope:
- safe mode / degraded mode
- explicit failure drills
- provider/model outage handling
- malformed output handling
- repeated-failure convergence enforcement
- mature owner override UX and audit
- recovery path from safe/degraded mode
- tests + audit coverage

### VPS deployment
The VPS is part of completion, not post-launch work.

Before deployment:
- discover actual VPS OS/runtime/network environment
- document required packages/runtime versions
- ensure repository/local runtime separation is understood
- create a reproducible deployment/config procedure
- identify data/state that must migrate vs remain local
- define credential provisioning without committing secrets
- define backup/restore before migration

Deploy/configure:
- current control-plane code
- Executive Brain E1/E2/E3/E4/E5 runtime
- required databases/state with integrity verification
- worker/provider configuration
- secrets provisioned through VPS-local secret storage/environment mechanism without GitHub exposure
- Hermes runtime/service
- required scheduled/background jobs
- logs with rotation/retention
- backups
- restart-on-failure / boot persistence
- firewall/network exposure restricted to required services only

VPS acceptance:
- service survives restart/reboot
- E1 audit PASS
- E2 gov-verify PASS
- E3 DB/integrity verification PASS
- E4/E5 checks PASS
- provider health checks PASS or truthful external-blocker state
- one text task executes end-to-end
- one multi-worker task executes end-to-end
- one image-generation task executes end-to-end
- verifier rejection + repair path tested
- provider failure/failover path tested
- owner escalation path tested
- GitHub/current_company_state updated to match deployed reality

## Execution strategy — parallel full scope

Do not serialize the whole project unnecessarily.

### Lane A — provider onboarding
Immediately after current Gemini setup:
- create/reuse a common provider-adapter contract/helper where safe
- onboard remaining API workers in parallel batches where credentials/access permit
- do not wait for one blocked provider before starting another
- if owner input is needed for a key/account/billing step, ask immediately and continue non-dependent work

### Lane B — E3 qualification/orchestration
While provider onboarding continues:
- finish qualification benchmark harness
- qualify workers as soon as each becomes execution-ready
- implement/finish real dispatch, integration, verification, targeted rework and replanning
- add new workers to the candidate pool as evidence arrives

### Lane C — E4/E5
Once E3 execution interfaces are stable enough:
- implement E4 resource continuity against the common execution/provider abstractions
- implement E5 safe mode and failure drills
- do not wait for every provider benchmark to finish before writing non-provider-specific E4/E5 mechanics

### Lane D — VPS
Start VPS work before local completion:
- inventory VPS now
- prepare runtime/deployment scripts/config now
- install dependencies now
- establish secret-storage and service-management pattern now
- perform dry-run deployment as soon as the runtime is coherent
- final sync/cutover happens after local verification

## Time discipline

- Reuse the DeepSeek integration as the reference API-worker pattern.
- Reuse Google only for modality-specific differences.
- Generalise repeated adapter/auth/usage/error plumbing where this can be done without weakening provider-specific truthfulness.
- Automate smoke/regression runs.
- Batch independent provider work.
- Keep commits small enough to recover quickly.
- Do not spend deadline time on cosmetic docs.
- Documentation that affects truth, security, deployment, recovery, or audit is mandatory.

If blocked:
1. record the exact blocker,
2. ask Mukund immediately if owner action is required,
3. continue every non-dependent lane,
4. revisit the blocker as soon as input becomes available.

## Hard gates that may not be bypassed

Deadline pressure does NOT permit:
- fabricated model IDs/usage/cost/quota
- treating UNKNOWN as healthy/zero/unlimited
- marking a smoke-tested worker QUALIFIED without qualification evidence
- setting routable=true without execution readiness
- direct E3 SQL writes into E1/E2 DBs
- committing credentials
- raw chain-of-thought logging
- silent quality-floor degradation
- infinite repair/retry loops
- enabling E3 production before the standing conditional owner approval criteria are satisfied
- VPS cutover without backup/restore and acceptance verification

## Final evidence package

Before declaring completion, produce:
- exact worker matrix: access / auth / model / adapter / smoke / E2 linkage / qualification / routable
- E1/E2/E3/E4/E5 test results
- production rehearsal results
- unresolved UNKNOWNs
- unresolved external blockers
- VPS deployment manifest
- backup/restore evidence
- service/reboot acceptance evidence
- final current_company_state.md
- final handover
- commit SHA(s)

Do not declare success from implementation alone. Success requires verified VPS operation.


## Owner directive update — 2026-09-23

Mukund explicitly authorized local Stage 2 enablement without waiting for another synchronous approval if the system passes objective readiness evidence. This authorization applies while he is asleep or at work.

Before local Stage 2 enablement:
- E1/E2/E3/E4/E5 relevant regressions must pass
- production rehearsal must pass
- no unresolved critical integrity/privacy/safety defect may remain
- worker routing/qualification state must remain evidence-driven
- rollback/recovery must be available
- state/evidence must be updated truthfully

Deployment architecture is intentionally deferred until local operation is proven. Current owner preference is laptop-primary + GitHub control/collaboration plane + VPS watchdog/failover, but this is not yet a final architecture decision or authorization for VPS cutover.


## Owner directive update — 2026-09-23 late evening

Mukund has superseded the earlier automatic local Stage 2 timing instruction.

- Continue all independent local engineering, diagnosis, qualification, multi-worker execution, E4/E5, regression, evidence, and deployment-preparation work overnight.
- **Do not enable local E3 Stage 2 overnight.**
- Mukund plans to configure all remaining provider credentials on **2026-09-24**.
- After those credentials are configured and truthfully verified, re-run the complete local Stage 2 readiness gates and complete local Stage 2 if they pass.
- This timing change does not weaken any readiness criterion and does not authorize VPS cutover or finalize deployment architecture.


## V1 company workflows — restored to active scope (owner reconfirmed 2026-09-23)

The Sep 21 Chief OS handover defines v1 as more than E1-E5. The following are active release-scope items and must be completed locally as far as safely possible before the final whole-company acceptance test:

### Career Ops + job-search automation
- inspect and preserve the existing Career Ops installation at `C:\Users\mukun\Documents\ChatGPT\CV customizer\career-ops-career-ops-v1.29.0`
- connect it to Chief as an employee/workflow rather than rebuilding it unnecessarily
- replace the standalone `@oai/artifact-tool` Excel-write dependency with a deterministic supported writer (prefer Python/openpyxl) while preserving the canonical workbook structure, formulas, validation/status metadata and dedupe rules
- preserve the canonical UK tracker at `C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx` and the existing Dubai/Japan/Singapore trackers
- restore/define regional automated job-search schedules without duplicating applications
- keep Excel authoritative for departmental operational records; Chief state is orchestration, not a replacement
- prove scan -> eligibility/filtering -> dedupe -> tracker write -> Chief summary on a bounded dry-run/evidence run

### Company Watch
- build Company Watch under Career using the historical employer/recruiter/application evidence already identified
- prefer structured career/ATS endpoints where available
- share dedupe/application state with Career Ops so it cannot create conflicting application records
- feed eligible findings into the appropriate regional tracker
- create its own monthly operational workbook only where it does not conflict with canonical application state
- evidence a bounded scan and handoff into Career Ops

### CV + cover-letter workflow
- connect the existing CV/customization workflow to Chief/Career Ops
- use job description + canonical CV/profile sources to produce a tailored draft and evidence record
- preserve source truth; do not fabricate experience, metrics, certifications or eligibility
- keep owner approval before any external application submission

### LinkedIn workflow
- implement the minimal LinkedIn workflow required for v1: job/discovery signal intake, profile/post drafting support, and handoff into Career Ops/company tracking
- drafts/read-only automation may run autonomously; external posting, messaging, connection requests, or application submission require explicit owner authorization unless a separately approved policy exists
- dedupe any LinkedIn-sourced job/company against Career Ops/Company Watch before adding it to trackers

### Whole-company acceptance
After the above lanes and E1-E5 local work are ready, run a local whole-company acceptance test covering:
- owner -> Chief intake
- E1 classification/floors
- E2 telemetry
- E3 delegation/verification
- E4/E5 continuity/safe-mode paths where applicable
- Career Ops job discovery + tracker write
- Company Watch handoff
- CV/cover-letter draft path
- LinkedIn draft/read-only path
- owner escalation for an action requiring approval
- truthful final state + handover

Do not initialize/restructure the existing Career Ops git repository without owner approval. Reuse existing systems and deterministic tooling first.
