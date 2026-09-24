# Morning handover — Chief OS v1 engineering cutoff, 2026-09-24

**Owner:** Mukund
**Task:** `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`
**Authority:** `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
**Acceptance evidence:** `audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/`
(`acceptance.md`, `results.json`, `roster_account.md`, `roster_account.json` + 12 sub-artifacts)
**Acceptance code SHA:** `31eecdbbae4945fcde7ad2831a6f5d8ca4da0507`

---

## 1. Bottom line

The whole-company **local** acceptance pass is **PASS**: **34 steps — 33 PASS, 0 FAIL, 1 owner-gated,
0 unavailable**. `canonical_workbooks_unchanged: true`. **0 external mutations, 0 provider calls.**
Full regression at the acceptance SHA: **21 suites / 579 collected / 579 passed / 0 failed /
0 errors / 0 unavailable / every suite exit 0**. E4/E5 drill harness: **36/36 checks,
`real_provider_calls = 0`**. Deployment preflight: **verdict GO** (11 checks, 0 FAIL, 1 WARN =
the 7 absent provider credentials). Backup/restore/rollback drill: **PASS, 10 artifacts**.
All **50/50 roster items** are accounted for with no UNKNOWN omission.

Every remaining gap is **owner-only** (provider credentials, one owner OAuth grant, owner decisions,
VPS access/architecture, an owner-attended machine trust audit) or **deliberately out of scope**
(local Stage 2 enablement, live-provider E4/E5 drill, deployment cutover). Nothing non-owner remains
recoverable.

E3 Stage 2 remains **NOT ENABLED**. No production dispatch. No VPS cutover. No tracker, mailbox,
LinkedIn, employer, or provider surface was mutated.

---

## 2. What the acceptance run proved (each line is a real subprocess, exit recorded)

| Area | Step | Result |
|---|---|---|
| Chief intake → E1 | `chief_intake_e1_classify` + `e1_quality_floor_audit` | PASS (intake record `eb-20260924-edf746ec`; integrity + quality-floor chain verify PASS) |
| E2 | `e2_resource_brief`, `e2_gov_verify`, `e2_telemetry` | PASS (governor verify PASS; unknown provider dimensions stay UNKNOWN) |
| E3 | `e3_status`, `e3_verify_db` | PASS (schema v2, all tables present) |
| E3 delegation/verification + E4 + E5 | `e4e5_drill_harness` | PASS 36/36 checks, 0 real provider calls, stubbed-failure drills D1–D7 |
| Whole repo | `regression_runner` (`scripts/evidence_runner.py`) | PASS 21 suites / 579 tests / exit 0 |
| Remote queue + watchdog | `remote_queue_scheduler_state` (read-only) | PASS — 9 tasks inspected; persistence limits recorded |
| Discord sync | `discord_sync_dry_run` | PASS (archive sync dry-run; **nothing published**) |
| Career Ops | `career_ops_scan_dedupe_write`, `career_ops_cli_inventory` | PASS (scan → eligibility → dedupe → write, dated copy only) |
| Regional jobs | `regional_jobs_lanes` + 4 offline eligibility replays | PASS (UK/Dubai/Japan/Singapore lanes ready; offline replay of recorded scans) |
| Company Watch | `company_watch_registry`, `company_watch_handoff_dry_run` | PASS (handoff dry-run against the canonical workbook; **hash unchanged**) |
| Application status | `application_status_monitor` | PASS (fixture + runtime-synthesised mailbox; store byte-identical on repeat) |
| JobBrief/CV/cover letter/reviewer/gate | `jobbrief_cv_cover_reviewer` | PASS (incl. a deliberately tampered pack being blocked) |
| CV + LinkedIn read-only | `cv_cover_linkedin_handoff`, `linkedin_outreach_interview_prep` | PASS (0 network calls, 0 LinkedIn mutations, unsent drafts only) |
| Career brief | `career_daily_brief`, `career_brief_status` | PASS (scheduled 07:00 local; delivery channel `not_verified`) |
| Morning brief / health | `morning_chief_brief`, `operational_health_snapshot` | PASS — verdict `ATTENTION`, `fail_count 0`, 2 attention items, 18 owner actions |
| Owner escalation | `owner_escalation_and_gates` + drill D2 | PASS (external action refused; no-qualified-worker escalation recorded) |
| Backup/restore | `operational_backup_dry_run`, `backup_restore_drill` | PASS — status PASS, 10 artifacts, rollback availability verified |
| Deployment prep | `deployment_preflight` | PASS — verdict GO (WARN: credentials absent, owner-gated) |
| Credentials | `credential_presence_probe` | **OWNER_GATED** — 7/7 API worker credentials absent (presence only, no value read) |

---

## 3. Completed engineering (as of this run)

- **E1/E2**: intake/classification, immutable quality-floor chain, governor chain, telemetry, resource
  brief — all verified live this run.
- **E3**: planner, decomposition review, router/meta-selector + qualification gate, context/permission
  compilers, team assembly, execution manager, integrator, independent verifier, conflict/targeted
  rework/replanning/escalation, capability learning + evidence-backed qualification, operator surfaces
  (`e3-status`/`e3-trace`/`e3-why`, DAG state + node failure attribution), orchestrator boundary.
- **E4**: resource continuity, runway/checkpointing, checkpoint→equivalent-failover state handover,
  content-side stop pressure view (rate + sample size + finishReason, bounded flag), surfaced in
  `e3-status`, the health snapshot and the Morning Chief Brief.
- **E5**: safe/degraded mode, failure drills, malformed-output handling, convergence enforcement,
  owner-override audit, recovery path.
- **Remote queue / watchdog / bridge**: hardened dispatcher, immutable running-task input, no-stream
  watchdog, PID-scoped termination, audit hardening, isolated regression suites.
- **Discord**: Chief gateway + 30-minute archive sync (`ChiefDiscordSync`), verified read-only here.
- **Career department**: Career Ops integration (`career_ops_cli.py` single Chief interface), tracker
  writer (openpyxl, artifact-tool dependency replaced), monthly rollover, four regional lanes +
  schedules, eligibility/dedupe state, Company Watch (+ recruiter/intermediary watch), application
  inbox/status monitor, JobBrief/requirement extractor, research-brief (cited-only), CV tailor,
  cover-letter, application-pack reviewer, submission gate, LinkedIn read-only intake/drafts,
  interview prep, career daily brief, run-health.
- **Operational**: health snapshot, Morning Chief Brief, backup with 7-snapshot retention, log-rotation
  plan, read-only persistence validation.
- **Deployment preparation**: `deployments/` package (manifest, secret checklist, owner-action order,
  dependency inventory, backup/restore plan, service definitions with re-importable task XML, cutover
  runbook, rollback/no-go list, acceptance commands) + `deployment_inventory.py`,
  `deployment_preflight.py`, `deployment_backup_restore_drill.py`, `set_provider_key.py`.
- **Acceptance harness (this task)**: `scripts/whole_company_acceptance.py` (roster C01) — deterministic,
  incremental, fail-closed, emits the roster account; no external mutation, no provider call.

---

## 4. Tests and evidence (exact counts)

| Artifact | Result |
|---|---|
| `…whole-company-acceptance-final/regression/evidence.json` | **21 suites / 579 collected / 579 passed / 0 failed / 0 errors / 0 unavailable**, every suite exit 0, code SHA `31eecdb`, python 3.11.16 (win32) |
| `…whole-company-acceptance-final/e4e5-drills/` | **36/36 checks**, `real_provider_calls = 0`, `stub_dispatches = 10`, `evidence_kind = stubbed_provider_failure` |
| `…whole-company-acceptance-final/backup-restore/` | status **PASS**, 10 artifacts, rollback `--dry-run` clean |
| `…whole-company-acceptance-final/deployment-preflight/` | verdict **GO**, 11 checks, 0 FAIL, 1 WARN (credentials absent) |
| `…whole-company-acceptance-final/persistence/` | 9 tasks inspected read-only; 8 Chief tasks + legacy donor; **2** survive a reboot |
| `…whole-company-acceptance-final/roster_account.md` | **50/50 roster items accounted for**; supplementary owner-gated items listed |
| `…whole-company-acceptance-final/results.json` | 34 steps, full command lines, exit codes, stdout/stderr tails |
| Attempt-1 record | `audits/evidence/2026-09-24T03-51-07Z-whole-company-acceptance-attempt1-partial/NOTE.md` — the runner's own evaluator defect (persistence `tasks` object vs list) after 9 PASS steps; preserved, fixed, no work hidden |

Baseline progression this sprint: 15 suites / 438 tests → **21 suites / 579 tests**; drills 33 → **36**
checks. Nothing regressed; no suite was removed.

---

## 5. Manual afternoon steps — exact order

Ordered by critical-path impact. Steps 1–2 are the only ones the build cannot do.

1. **Configure the seven provider credentials** (≈10 min).
   `python scripts/set_provider_key.py --worker mistral-small-4` (repeat for `glm-53-flash`,
   `qwen38-27b`, `longcat-2.0`, `minimax-m3`, `step-37-flash`, `tencent-hunyuan-hy3`).
   It prompts without echo — no key ever reaches shell history, a log, chat, or GitHub.
   Verify: `python scripts/set_provider_key.py --status` → expect **10/10 present**.
2. **Run the post-key verification sequence** — engineering-run, your only manual part is step 1
   (exact commands in §6).
3. **State your work-authorisation position** for UAE / Japan / Singapore (one line per region).
   Until then every non-UK record stays labelled `UNKNOWN` and no application can be prepared there.
4. **Deployment architecture decision** (one written line) — laptop-primary + GitHub + VPS
   watchdog/failover is the recorded *preference*, not a decision or an authorisation.
5. **VPS host/account details** — only if a VPS path is chosen; supply locally, never via GitHub.
6. **Owner-attended laptop security audit** (the two unexplained UI events) — evidence is preserved,
   nothing was cleaned; required before the laptop can be a trusted production host.
7. **Reboot-persistence confirmation** — after your next reboot, confirm the 7 non-`Hermes_Gateway`
   tasks return to Ready/Running with advancing Next Run Time (the exact fix is pre-written in the
   validator's `owner_checklist` if one does not).
8. **Decide the legacy `Mukund Chief of Staff` task** disposition (it still starts the superseded
   stack at sign-in; it is a known persistence/survives-boot row in the audit above).
9. **Authorise the Gmail read-only OAuth** for the live Application Inbox feed (6 steps, ≈10 min,
   scope `gmail.readonly`, path recorded in `career-ops/application_inbox_config.json`).
10. **Optional, non-blocking**: research provider for JobBrief company facts; LinkedIn live-surface
    decision; Career Daily Brief delivery channel; tracker-vocabulary gaps (assessment invite, Japan
    rejection, Dubai offer); operational-service scheduling cadence; whether the current month
    should be rotated out of the live workbooks (owner-column rows block it today: uk 26 / dubai 8 /
    singapore 4); whether a UAE/Japan provider is added for those lanes.

Full detail and rationale for every item: `tasks-or-issues/overnight-owner-actions-2026-09-24.md`.

---

## 6. Stage 2 readiness steps — to run **after** step 1 (engineering-run)

From the repository root, in this order:

1. `python scripts/e3_credential_presence_probe.py` — must show the seven workers configured.
2. `python scripts/e3_stage2_readiness_gate.py` — must report the readiness conditions MET and the
   Stage 2 verdict; record its output directory.
3. `python scripts/evidence_runner.py --label post-keys-regression` — must be
   **21 suites / 579 collected / 579 passed / 0 failed / 0 errors / 0 unavailable, every suite exit 0**
   (the figure to beat, set by this acceptance run at `31eecdb`). Any suite failure blocks Stage 2.
4. `python exec-brain/e3_execution_rehearsal.py` — the bounded **real-provider** execution rehearsal
   (the only driver that spends real provider calls; default ≈7 calls).
5. `python exec-brain/e4e5_drill_harness.py` — confirm **36/36 checks**, `real_provider_calls = 0`,
   `live_stores_changed = []`.
6. Only then complete local Stage 2 (item 2 in the owner-action file) — local only; this does **not**
   authorise VPS cutover or fix the deployment architecture.

Also re-check Google image intermittency (recorded rate 2/9, `finishReason=IMAGE_RECITATION`) before
declaring that worker's path stable in Stage 2 reporting.

---

## 7. Deployment prerequisites (before any cutover)

- Preflight **GO** re-run on the destination node; backup/restore drill **PASS** on the source node.
- 10/10 roster workers credential-present **or** each missing worker consciously accepted non-routable
  in writing.
- Deployment **architecture decided** and **cutover explicitly authorised**; VPS host/account details
  supplied outside GitHub.
- Owner-attended laptop trust audit cleared if the laptop is to be a production node.
- Off-site backup exists (none today); log rotation/retention implemented; battery gating fixed; reboot
  persistence confirmed; secrets provisioned through VPS-local storage only.
- Rollback path rehearsed (see §8).

Full package: `deployments/01`–`10`, cutover runbook `deployments/07`, no-go list `deployments/08`.

---

## 8. Rollback and no-go criteria

**Hard no-go (any one blocks/aborts the cutover):** preflight not GO; backup/restore drill not PASS;
no verified source-node pre-cutover backup; any DB `integrity_check` failure or restored row-count
mismatch; the regression runner reporting any failure/error/skip; the drill harness not 36/36 or
reporting `real_provider_calls > 0`; a needed credential unresolved; any secret travelling through
GitHub/chat/queue/repo; topology undecided or cutover unauthorised; rollback path unavailable; laptop
trust audit uncleared; destination becoming the only copy; a raw private runtime artifact published.

**Roll back immediately if:** integrity verification fails on the destination; a worker is marked
routable without evidence; any credential exposure; an unbounded retry/repair loop; an E3 write into an
E1/E2 store outside the public interface; an acceptance checkpoint unmet; destination instability; loss
of the rollback path.

**Mechanisms:** R1 `python scripts/deploy_e3_runtime.py --restore <runtime-root>/backups/e3-deploy-<stamp>`
(seconds, SHA-256-provable), R2 git revert to last known-good, R3 restore state from the pre-cutover
snapshot with chain-head, R4 topology rollback, R5 disable all Chief tasks and escalate. Nothing is
deleted. Default posture when uncertain: **stop and escalate**.

Soft no-go items currently open (owner may accept in writing): battery gating, log rotation, reboot
persistence unverified, no off-site backup, no live-provider failover drill, legacy task undecided.

---

## 9. Exact remaining blockers

**Owner-only**

1. Seven provider credentials absent (0/7) — blocks live onboarding of Mistral, GLM, Qwen, LongCat,
   MiniMax, Step, Tencent Hunyuan, and (by owner instruction) local Stage 2.
2. Gmail read-only OAuth not granted — blocks only the *live* mailbox feed (local-export path works).
3. Company/research provider not approved — every JobBrief reports `research_needed`; cited-file path works.
4. Work-authorisation facts for UAE/Japan/Singapore unstated — those records stay UNKNOWN.
5. Deployment architecture + VPS details + explicit cutover authorisation outstanding.
6. Owner-attended laptop trust audit outstanding.
7. Reboot persistence unverified (a reboot is prohibited by this task's stop conditions).
8. Legacy `Mukund Chief of Staff` task disposition undecided.
9. Optional decisions: brief delivery channel, operational scheduling cadence, tracker vocabulary,
   month rotation policy, LinkedIn live surface.

**Externally/architecturally gated (not defects)**

10. Local Stage 2 enablement — gated on 1 + the explicit owner step; the anti-loop directive forbids
    re-staging the readiness gate while the credential state is unchanged.
11. Live-provider E4 failover / E5 recovery drill — the harness has no live-provider mode by design.
12. Google image worker — recorded intermittent `IMAGE_RECITATION` stop (2/9); trigger unknown and
    deliberately not chased with unbounded generation.
13. VPS cutover — not authorised; preparation is complete and preflight is GO.

---

## 10. Truth boundaries (what is NOT claimed)

- No live external integration is claimed where only fixtures exist: the CV/cover/JobBrief/LinkedIn
  acceptance fixtures are labelled synthetic; no live vacancy, no employer contact, no submission.
- No live mailbox evidence (no credentials), no live LinkedIn account access, no live company research.
- E4/E5 drill evidence is `stubbed_provider_failure` on the real code path — **not** real provider
  evidence.
- Qualification is evidence-driven and partial: codex-cli (builder/integrator), deepseek-v41-flash
  (builder) and google-nano-banana-2 (vision) are QUALIFIED from recorded executions; the seven
  credential-missing workers have **no** execution evidence and are correctly `routable=false`.
- Discord sync was validated in **dry-run** here; nothing was published by this task.
- Dubai/Japan thin scan results mean "no regional provider", never "no vacancies there".
- The acceptance ran on the working tree at committed SHA `31eecdb`; the runner itself was committed
  in `31eecdb` before this authoritative run.

---

## 11. Roster account

`audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/roster_account.md`
(also `.json`) lists all **50/50** roster items (A01–A22, B01–B24, C01–C04) with status and evidence:
**47 PASS**, **3 READY_NEEDS_OWNER_CONFIG** (B12 live mailbox OAuth; B14 research provider;
C03 deployment preparation — cutover itself owner-gated), **0 BLOCKED_EXTERNAL**, **0 unmapped**,
plus **10 supplementary owner-gated/external items** (provider credentials, Stage 2, live-provider
drill, deployment architecture, reboot persistence, laptop audit, rollover policy, regional
work-authorisation, LinkedIn live surface, operational scheduling). No UNKNOWN omission.

Superseded with evidence (outside the roster): the legacy `Mukund Chief of Staff` logon task
(`state/v1-agent-roster.md`, 2026-09-23 Company Registry audit) — retained as a donor, not revived,
not deleted; it is also a known `survives boot = yes` row in the persistence audit above.
