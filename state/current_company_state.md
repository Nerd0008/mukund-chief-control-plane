# Current Company State

<!-- BEGIN GENERATED: executive-status (scripts/status_render.py) -->
## Canonical status (generated)

_Generated from `status/canonical-status.json` at as-of **2026-09-24T21:10:44Z** by `python scripts/status_render.py`; verify with `python scripts/status_verify.py`. The evidence chronology below is preserved unchanged._

- **Code identity:** branch `main`, authoring HEAD `6cbb573aaaf90cd32bd69b819c96d38a1cae642e`, newest verified evidence SHA `6cbb573aaaf90cd32bd69b819c96d38a1cae642e`.
- **Newest evidence run:** `2026-09-24T21-09-18Z-e3-provider-verification-regression` — **PASS (22 suites / 606 collected / 606 passed / 0 failed)** (finished 2026-09-24T21:10:44Z); regression **22 suites / 606 collected / 606 passed / 0 failed / 0 unavailable**.
- **Executive Brain:** E1 ACTIVE; E2 ACTIVE; E3 IMPLEMENTED AND VERIFIED, STAGE 2 NOT ENABLED; E4 IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES); E5 IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES).
- **Roster:** 50 items — 47 PASS, 3 READY_NEEDS_OWNER_CONFIG, 0 BLOCKED_EXTERNAL.
- **Provider credentials:** 10 / 10 present (0 absent).
- **Stage 2:** NOT ENABLED. **Deployment:** NOT DEPLOYED (cutover not authorised; preflight GO with 1 owner-gated WARN).
- **Production blockers (10), separate from implementation completion:** `provider-execution-blocked`, `stage2-not-enabled`, `live-provider-failover-gap`, `deployment-cutover-decision`, `offsite-backup-absent`, `battery-gating`, `reboot-persistence-unverified`, `laptop-trust-audit`, `unattended-interactive-token`, `log-rotation-retention`.
- **Optional / feature-gated owner decisions (not release blockers):** 12 items — see `status/executive-tracker.md` section 11.

Full regenerated view: `status/executive-tracker.md`.
<!-- END GENERATED: executive-status (scripts/status_render.py) -->

- Timestamp: 2026-09-24T15:25:00Z (historical entry — the current canonical status is the
  generated block above; this chronology is preserved as written)
- Latest evidence run: 2026-09-24T15:16:16Z (run finished 15:17:52Z; evidence directory stamp
  `2026-09-24T15-45-00Z-isolated-release-reproducibility`) — **RELEASE REPRODUCIBILITY + CODEX IDENTITY
  PORTABILITY: PASS** (task `agent-release-reproducibility-and-codex-portability-2026-09-24`),
  `audits/evidence/2026-09-24T15-45-00Z-isolated-release-reproducibility/` (`evidence.json` + `evidence.md`)
  — the repository acceptance suite was executed by `scripts/evidence_runner.py` from a **clean isolated
  CPython 3.11.16 interpreter built from the pinned artifacts** (`uv venv --python 3.11.16`, installed from
  `requirements.lock`, no repository packages on `PYTHONPATH` beyond the declared suite import roots):
  **21 suites run / 21 passed / 0 failed / 0 errors / 0 unavailable, 583 collected / 583 passed**, every
  suite exit 0, at code SHA `e9d2195`. E3 baseline alone: **58 collected / 58 passed** in that interpreter,
  and the whole runner was re-executed independently at 2026-09-24T15:19Z in the same pinned interpreter
  (`scripts/evidence_runner.py --label verify-isolated-recheck`) reproducing **21 suites / 583 collected /
  583 passed / 0 failed / 0 unavailable** exactly. **The audit's 579-collected figure is superseded and is
  reported as measured, not forced to the old value** — the count grew because the Codex identity contract
  replaced one incorrect exact-match test with five truthful-contract tests (E3 baseline 54 → 58).
  The audit's fresh-smoke finding is closed: `codex doctor --json` may legitimately report `provider=unknown`,
  so `exec-brain/codex_adapter.py` now records `configured_provider`/`configured_model` (from `config.load`)
  **separately** from the observed identity and fills `provider` only from a live probe
  (`observed:network.websocket_reachability`); otherwise it stays `unknown`. UNKNOWN is never converted to
  `openai`, and routability (successful execution + verified E2 request record) and qualification
  (evidence-backed benchmark) requirements are unchanged. Offline compatibility fixtures cover
  `provider=openai`, `provider=unknown` and configured-provider-only payloads
  (`exec-brain/tests/fixtures/codex_doctor_*.json`); `scripts/codex_identity_contract_check.py` reproduces the
  audit failure as a correction and reports machine-local Codex facts by presence only.
  Reproducibility artifacts added: `requirements.txt` + hash-pinned `requirements.lock` (9 packages),
  `scripts/dependency_inventory.py --check` (fails on any undeclared third-party import),
  `scripts/release_manifest.py` (commit SHA, dirty state, Python, lock hash, artifact hashes, evidence IDs),
  `scripts/make_release_archive.py` + `scripts/verify_release_archive.py` (an exported ZIP proves its commit
  and dependency set by recorded hashes, **never fabricated Git history**), `docs/SETUP.md` (clean-clone
  setup plus a deterministic no-network/no-secret probe for each deliberately machine-local dependency) and
  `docs/RELEASE.md`. **No secrets, credentials, `auth.json`, cookies, private runtime databases or owner
  application data are included in any release artifact.** E1/E2 pass only because this host's machine-local
  Hermes runtime root is present; on a bare clone they are truthfully recorded `unavailable`. E3 Stage 2 still
  **NOT ENABLED**; **0 provider calls, 0 external mutations**; no VPS cutover in this task.
- Previous evidence run: 2026-09-24T03:57:34Z — **WHOLE-COMPANY LOCAL ACCEPTANCE: PASS** (task
  `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`),
  `audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/` (`acceptance.md`, `results.json`,
  `roster_account.md/.json`) — **34 steps: 33 PASS, 0 FAIL, 1 owner-gated, 0 unavailable**, code SHA
  `31eecdb`, `canonical_workbooks_unchanged: true`, **0 external mutations / 0 provider calls**.
  Driver `scripts/whole_company_acceptance.py` (roster C01). Full regression inside the run:
  **21 suites / 579 collected / 579 passed / 0 failed / 0 errors / 0 unavailable, every suite exit 0**;
  E4/E5 drills **36/36 checks, `real_provider_calls = 0`**; deployment preflight **GO** (0 FAIL, 1 WARN
  = the 7 absent credentials); backup/restore/rollback drill **PASS** (10 artifacts); roster **50/50**
  (47 PASS, 3 READY_NEEDS_OWNER_CONFIG). Morning handover:
  `handovers/2026-09-24-morning-handover.md`. E3 Stage 2 still **NOT ENABLED**; no production dispatch;
  no VPS cutover; the only remaining gaps are owner-only or deliberately out of scope.
- Previous evidence run: 2026-09-24T01:30:00Z — **LinkedIn people/network layer completed: networking /
  recruiter / hiring-manager outreach drafts + Interview Prep Agent (B22)** (task
  `agent-linkedin-networking-interview-support-2026-09-23`),
  `audits/evidence/20260924T020000Z-linkedin-outreach-interview-prep/acceptance.json` (+ `.md`) —
  **27/27 critical checks pass** (run against code SHA `bc6391c`): three unsent outreach variants each
  with an explicit unsent state and
  per-draft provenance (role/employer taken only from the resolved Career Ops record); interview prep
  pack built from a canonical JobBrief + cited research + the canonical `cv.md`/`profile.yml`
  (every talking point re-read verbatim from `cv.md`, every question marked
  `employer_supplied: false`); owner action gate refuses post/message/connect/apply. New suite
  `career-ops/tests/test_interview_prep.py` 26 passed; `test_linkedin_workflow.py` 38 passed; whole
  `career-ops/tests/` **278 passed**. 0 LinkedIn mutations, 0 messages, 0 applications, 0 provider
  calls, 0 browser launches; canonical source hashes unchanged.
- Previous evidence run: 2026-09-24T00:14:21Z — **four regional job-search workers + deterministic
  scheduled execution** (task `agent-regional-job-search-agents-and-schedulers-2026-09-23`),
  `career-ops/evidence/acceptance-20260924T001500Z.json` — one shared implementation for UK, Dubai,
  Japan and Singapore; all four Windows scheduled tasks registered and `Ready`; bounded dry-run
  evidence for every region; workbook write proven on a **test copy** and rolled back to the pre-write
  hash; **all four canonical workbook hashes unchanged**; `applications_submitted: 0`,
  `external_messages_sent: 0`. New suite `career-ops/tests/test_regional_job_search.py` 32 passed;
  whole `career-ops/tests/` 120 passed.
- Before that: 2026-09-23T23:43:10Z — **CV/cover-letter workflow connected + minimal LinkedIn
  workflow implemented** (task `agent-cv-cover-letter-linkedin-workflows-2026-09-23`),
  `audits/evidence/20260923T234310Z-cv-linkedin-workflows/acceptance.json` (+ `.md`) —
  **23/23 critical checks pass**: representative path Career Ops job → tailored CV/cover-letter draft
  (install fact gate **pass**) → LinkedIn read-only intake + unsent drafts → dedupe against Career Ops +
  Company Watch → tracker handoff on a dated copy with verified backup/rollback, **canonical workbooks
  hash-unchanged**. New suites: `career-ops/tests/test_cv_workflow.py` 21 passed,
  `career-ops/tests/test_linkedin_workflow.py` 34 passed. 0 provider calls, 0 LinkedIn mutations,
  0 applications.
- Earlier: 2026-09-23T22:53:53Z — E3 Stage 2 readiness gate re-run (credential-triggered
  retry, task `agent-e3-stage2-readiness-gate-after-provider-keys-retry-2026-09-24`)
  (`audits/evidence/2026-09-23T22-53-53Z-e3-stage2-readiness-gate-verdict/`, 0 provider calls) and
  its regression input (`audits/evidence/2026-09-23T22-52-48Z-e3-stage2-readiness-gate-rerun/`,
  code SHA `342ee66`). Before that: 2026-09-23T22:41:57Z at code SHA `88af27a`; then
  2026-09-23T22:37:29Z at code SHA `56d923b`.
- Evidence files (this run):
  - `audits/evidence/20260923T234310Z-cv-linkedin-workflows/acceptance.json` (+ `.md`) — CV/cover-letter
    workflow + minimal LinkedIn workflow acceptance: **23/23 critical checks pass** (see the section at
    the end of this file).
  - `audits/evidence/2026-09-23T23-40-25Z-cv-linkedin-workflows/evidence.json` (+ `.md`) — whole-repo
    regression via `python scripts/evidence_runner.py --label cv-linkedin-workflows`:
    **14/14 suites pass, 400 collected / 400 passed, 0 failed, 0 errors, 0 skipped**, every suite exit 0,
    code SHA `b2ed978`. 0 provider calls.
  - `audits/evidence/2026-09-23T21-53-37Z-e3-image-diagnosis-and-qualification/evidence.json` (+ `.md`)
    — **12 suites, 364 collected / 364 passed, 0 failed, 0 errors, 0 skipped, every suite exit 0**
  - `audits/evidence/2026-09-23T21-49-21Z-e3-google-image-diagnosis/evidence.json` (+ `.md`) —
    **bounded Google image real-dispatch diagnosis: exactly 1 real call spent**, on the identical
    request that had failed. The failure **did not reproduce**.
  - `audits/evidence/2026-09-23T21-52-00Z-e3-qualification-from-evidence/` — dry-run artifact
    (evaluated, wrote nothing); `…T21-52-08Z-…` and `…T21-53-01Z-…` — the qualification run
    (the 21:53:01Z artifact is the final one; the 21:52:08Z artifact predates the addition of the
    distinct-DAG-node reporting fields and is preserved rather than overwritten)
- Earlier evidence (still valid):
  - `audits/evidence/2026-09-23T21-10-00Z-e3-production-execution-rehearsal/` — first real-execution
    rehearsal on the built execution leg (single-node plans)
  - `audits/evidence/2026-09-23T21-11-03Z-e3-production-execution-leg-regression/` — 10 suites, 323/323
  - `audits/evidence/2026-09-23T20-55-13Z-e3-production-rehearsal-run/` — Stage-1 shadow rehearsal
    (simulated specialist outputs, isolation proof)
- Shared Control Plane status: Phase 2A
- Hermes: running on DeepSeek direct API (`deepseek-flash`); the GitHub remote bridge dispatches `agent-*` tasks through it
- Discord: connected
- Company Registry: installed
- Company audit: completed
- Discord capture: active for Chief channel (#chief + its threads)
- Local archive: active
- Automatic periodic Chief sync: scheduled task "ChiefDiscordSync" (every 30 min), observed Ready and scheduled; functionality itself not re-exercised in this run
- Manual fallback: python C:\Users\mukun\Documents\mukund-chief-control-plane\scripts\sync_discord_chief.py

## Executive Brain — measured test state

All numbers below come from one isolated run at 2026-09-23T21:11:03Z recorded by
`scripts/evidence_runner.py` at code SHA `6c19a01`. Each suite is one real subprocess with a
declared import root; counts are per suite and are not extrapolated.

- E1 executive brain runtime matrix: 32 collected / 32 passed / exit 0
- E2 governor + provider adapters: 45 collected / 45 passed / exit 0
- E3 baseline: 54 collected / 54 passed / exit 0
- E3 extended: 60 collected / 60 passed / exit 0
- E3 shadow orchestrator: 13 collected / 13 passed / exit 0
- E3 production rehearsal (Stage-1 path, isolation, E1/E2 boundary): 24 collected / 24 passed / exit 0
- E3 production execution leg (dispatch, verification gating, DAG/evidence persistence): 18 collected / 18 passed / exit 0
- E3 production execution rehearsal driver (stubbed providers, isolated DB): 10 collected / 10 passed / exit 0
- E3 evidence-backed qualification (recorded-evidence harness, isolated DB): 13 collected / 13 passed / exit 0 (new in the 21:53:37Z run)
- E4 resource continuity + E5 safe mode (combined suite): 37 collected / 37 passed / exit 0
- Remote queue (isolated suite): 30 collected / 30 passed / exit 0
- Single-run totals: 323 collected, 323 passed, 0 failed, 0 errors, 0 skipped across 10 suites

**Current baseline (2026-09-23T21:53:37Z, `scripts/evidence_runner.py --label
e3-image-diagnosis-and-qualification`):** 12 suites, 364 collected / 364 passed / 0 failed /
0 errors / 0 skipped, every suite exit 0, at code SHA `4da92eb`. The delta against the
21:33:19Z run (11 suites / 351) is exactly +1 suite / +13 tests:
`exec-brain/tests/test_e3_qualification_evidence.py` (13) — the evidence-backed qualification
harness suite. Every other suite count is unchanged. Evidence:
`audits/evidence/2026-09-23T21-53-37Z-e3-image-diagnosis-and-qualification/`.

**Superseding baseline (2026-09-23T21:33:19Z, `scripts/evidence_runner.py --label
e3-production-rehearsal-retry-regression`):** 11 suites, 351 collected / 351 passed / 0 failed /
0 errors / 0 skipped, every suite exit 0, at code SHA `bf48a2b`. The delta against the
21:18:27Z run (335) is exactly +16: `tests/test_e3_execution.py` 18 → 22 (+4: dependency-gated
multi-node execution ×2, DAG dependency wiring ×2) and `tests/test_e3_execution_rehearsal.py`
10 → 22 (+12: multi-worker plan, isolation proof, contamination, not-requested reporting). Every
other suite count is unchanged. Evidence:
`audits/evidence/2026-09-23T21-33-19Z-e3-production-rehearsal-retry-regression/`.

**Earlier baseline (2026-09-23T21:18:27Z, `scripts/evidence_runner.py --label
bridge-watchdog-validation`):** 11 suites, 335 collected / 335 passed / 0 failed / exit 0. The delta
against the 21:11:03Z run (323) was exactly the new isolated bridge suite
`remote_queue/tests/test_bridge_watchdog.py` (12/12). Evidence:
`audits/evidence/2026-09-23T21-18-27Z-bridge-watchdog-validation/`.

Supersedes the 8-suite / 295-test figure at SHA `4ac1a22`. The delta is the two new E3 execution
suites (18 + 10 = 28) plus nothing else. Two intermediate runs of the same runner were executed
against uncommitted code while this run's changes were still being edited; they are preserved but
marked superseded under `audits/evidence/superseded/` (`…T21-08-55Z-…`,
`…T21-09-51Z-e3-production-execution-leg-regression`). The 21:11:03Z run at SHA `6c19a01` is the
authoritative figure.

### E3 status

- E3 Stage 1: ACTIVE
- E3 Stage 2 production enablement: **NOT ENABLED** — and, per the live task contract, *not to be
  enabled by this task regardless of outcome*.
  - The authority (`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`) records a standing
    conditional owner approval for **local-only** enablement. The live running task contract for
    `agent-e3-production-execution-leg-2026-09-23` was amended by the owner/coordinator at
    2026-09-23T21:04Z (`1ba7f43`) to read: *"Regardless of outcome, do not enable LOCAL Stage 2 or
    production dispatch; leave it disabled and record the exact remaining conditions for a separate
    owner-directed decision."* That newest instruction governs; the conditional approval was **not**
    exercised this run, so no readiness criterion was weakened and none was treated as satisfied by
    approval text.
  - Preconditions were nevertheless re-evaluated with evidence — see below.
- E3 orchestration DB: schema **v2** (live `orchestration.db` upgraded from v1 by the execution leg)
- Worker-capability states in the live store: **4 rows** (2026-09-23T21:53Z) — `codex-cli` builder
  and `integrator` QUALIFIED, `deepseek-v41-flash` builder QUALIFIED, `google-nano-banana-2` vision
  EVALUATING. Every QUALIFIED row carries a non-zero evidence count and a
  `worker_capability_event` audit row; `qualified_rows_without_evidence = 0`

### E3 production execution leg — BUILT AND EVIDENCED (this run)

The recorded unmet Stage 2 condition from the 2026-09-23 rehearsal was: *the orchestrator composes
planning/routing/assembly/integration/verification but has no dispatch step to a worker
`ExecutionAdapter`*. That leg now exists and has been exercised with **real workers**.

New/changed modules:

- `exec-brain/e3_execution.py` — `ExecutionAdapterRegistry` (dispatch is refused with
  `WorkerNotRoutable` unless the registry reports `routable=true`; a credential-missing worker is
  never called), `OrchestrationStore` (schema-v2 `dag_node` / `dag_state_event` /
  `performance_evidence` persistence) and `E3ProductionExecutor`
  (`READY → RUNNING → VERIFYING → COMPLETE`; a genuine verifier rejection moves the node to
  `REWORK` and re-dispatches; the node reaches `FAILED` when the repair budget is spent). **A node
  can only reach `COMPLETE` after a deterministic verification PASS**; a node with no configured
  deterministic test cases is `BLOCKED` without spending a provider call.
- `exec-brain/e3_shadow_orchestrator.py` — `orchestrate_and_execute()`: the full real-path pipeline
  (plan → decomposition review → route → context/permission compile → team assembly → **dispatch** →
  integrate real outputs → per-node verification → persist → escalate/replan).
- `exec-brain/e3_execution_rehearsal.py` — real-path rehearsal driver (bounded calls only).
- `exec-brain/e3_cli.py` — the `e3-*` CLI bindings (including `e3-execute`, which requires
  `--confirm` before it will spend provider quota).
- `scripts/deploy_e3_runtime.py` — deploys the E3 module set to the runtime root with a per-file
  backup, a SHA-256 manifest and a documented `--restore` path. No secret-bearing file is ever
  copied, and E1/E2-owned files are not touched (runtime `eb.py` receives only the one e3-*
  registration hook, with the pre-patch copy backed up).

Deployment verified directly (artifact `…e3-production-execution-rehearsal/deployment_check.json`):
all 29 required E3 modules present in `%LOCALAPPDATA%\hermes\exec-brain`, `missing_modules: []`,
and all ten `e3-*` bindings present (`e3-init`, `e3-register-workers`, `e3-status`, `e3-plan`,
`e3-route`, `e3-rationale`, `e3-trace`, `e3-why`, `e3-verify-db`, `e3-execute`). The local CLI drives
E3 (`eb.py e3-status`, `e3-plan`, `e3-verify-db`, `e3-execute` dry-run all verified in-run).

### Real-path rehearsal evidence (NEW — real worker execution)

Driver: `exec-brain/e3_execution_rehearsal.py`. Evidence:
`audits/evidence/2026-09-23T21-10-00Z-e3-production-execution-rehearsal/`.
Run as a real process from the deployed runtime root, writing to the live `orchestration.db` and
reporting E2 telemetry through the public `governor.record_request()` interface only.

Bounded real provider usage: **5 calls** (deepseek 3, openai/codex-cli 1, google 1). Provider-returned
usage was captured on 4 of them; the Codex CLI exposes none, recorded as null (never estimated).

| Scenario | Worker | Result | Detail |
|---|---|---|---|
| A — rejection → targeted repair → re-verification | deepseek-v41-flash | **COMPLETE** | Call 1 returned prose; the deterministic verifier **rejected** it (`expected READY-7391, got "I am the AI assistant executing this rehearsal leg…"`); the targeted repair re-dispatched with the plan's declared exact content; attempt 2 **PASSED**. Persisted transitions `READY→RUNNING→VERIFYING→REWORK→RUNNING→VERIFYING→COMPLETE`. E2 rows `obs-20260923-ce0dc42c`, `obs-20260923-83675c19` |
| B — first-pass deterministic PASS | deepseek-v41-flash | **COMPLETE** | One call; `READY→RUNNING→VERIFYING→COMPLETE`. E2 row `obs-20260923-0347c684` |
| C — Codex CLI dispatch | codex-cli | **COMPLETE** | One non-interactive `codex exec --json` call in a scratch working directory; provider `openai`; **served model identity UNKNOWN** (not exposed); usage not exposed. E2 row `obs-20260923-cb6aece9` |
| D — Google image dispatch | google-nano-banana-2 | **FAILED** | Real call, provider error `no_image_part_in_response`; provider usage shows 17 prompt tokens and **no** output tokens. Unresolved — see below. E2 row `obs-20260923-f0913024` |
| E — credential-missing worker refusal | mistral-small-4 | **BLOCKED (expected)** | Assignment refused with `worker_not_routable:mistral-small-4`; **zero** provider calls; adapter stub recorded 0 dispatches |

Persistence verified by reading the live store back after the run: 5 `dag_node` rows (4 `COMPLETE`/
`FAILED` + 1 `BLOCKED`), 20 `dag_state_event` rows, 4 `performance_evidence` rows
(`A: first_pass_success=0, final_success=1, retries=1, corrections=1`; `B`, `C: 1/1, 0 retries`;
`D: 0/0, failure_attribution=verification_fail`), and 5 new `observed_request` rows in `governor.db`
written through the public E2 interface. E1/E2 boundary static scan: **0** direct SQL writes to E1/E2
stores from any `exec-brain/*.py`.

### Formal production-rehearsal re-run on the real path (2026-09-23T21:32:41Z) — NEW

This is the re-run of the blocked `agent-e3-local-production-rehearsal-2026-09-23`. Driver:
`exec-brain/e3_execution_rehearsal.py`, executed as a real process from the deployed runtime root
against the live `orchestration.db`. Evidence:
`audits/evidence/2026-09-23T21-32-41Z-e3-production-execution-rehearsal/`.

Bounded real provider usage: **7 calls, stated up front before the run** (deepseek 5, codex-cli 2 —
`max_tokens=256`, `temperature=0`, deterministic single-shot prompts; the plan and the reason for
each scenario's call count are recorded in `usage_plan`). Provider-returned usage was captured on 5
of them (the Codex CLI exposes none: recorded as null, never estimated). Note the Google image
scenario was **deliberately not spent here** — its real-dispatch diagnosis is owned by the pending
`agent-e3-image-diagnosis-and-multiworker-execution-2026-09-23`, and the report records it as
`google_image_complete: null` ("not evaluated", *not* a pass).

| Scenario | Nodes | Workers | Result | Detail |
|---|---|---|---|---|
| A — single-node rejection → repair → re-verify | 1 | deepseek-v41-flash | COMPLETE | attempt 1 rejected, REWORK, repaired, attempt 2 PASS |
| B — single-node first-pass | 1 | deepseek-v41-flash | COMPLETE | one call, PASS |
| C — Codex CLI dispatch | 1 | codex-cli | COMPLETE | one non-interactive `codex exec --json` call |
| **F — decomposed multi-worker plan** | **2** | **deepseek-v41-flash + codex-cli** | **COMPLETE** | node 1 `[Builder]` (deepseek): attempt 1 rejected → `REWORK` → targeted repair → PASS; node 2 `[Integrator]` (codex-cli): `READY` only **after** node 1 was persisted `COMPLETE`, then first-pass PASS |
| E — credential-missing refusal | 1 | mistral-small-4 | BLOCKED (expected) | refused pre-dispatch with `worker_not_routable:mistral-small-4`, **0** provider calls |

Scenario F is the decomposed multi-worker case that was recorded as OPEN in the previous run:

- the plan shape comes from the real planner (multi-role threshold), not from the test: 2 nodes,
  `node-plan-0001-1` (builder) → `node-plan-0001-2` (integrator, dependency declared);
- each node has its own deterministic exact-content test case (different literal per node) and is
  dispatched to its **own** real worker adapter — two distinct routable workers in one plan;
- the persisted, ordered `dag_state_event` log for the plan reads
  `n1 PLANNED→READY→RUNNING→VERIFYING→REWORK→RUNNING→VERIFYING→COMPLETE`,
  then `n2 PLANNED→READY→RUNNING→VERIFYING→COMPLETE` — the dependency gate is proven from the
  store, not asserted from memory;
- every node is `COMPLETE` with `final_verification=PASS` and one `performance_evidence` row.

Isolation / boundary re-proof (in-run, recorded in `isolation`):

- a rehearsal-tagged write aimed at each live production store (`orchestration.db`, `governor.db`,
  `exec_brain.db`) is **refused fail-closed** (`all_production_writes_refused: true`);
- the simulated-evidence sink is written **outside** the production root
  (`isolated_store_outside_production: true`), and every live store is byte-identical afterwards —
  SHA-256 before/after equal for the main database file **and** its `-wal`/`-shm` sidecars
  (`stores_unchanged_including_wal_sidecars: true`);
- live-store contamination check: `simulated_or_shadow_evidence_rows: 0`,
  `qualified_rows_without_evidence: 0`, and the `capability_registry` is still **empty** — no worker
  was marked QUALIFIED;
- E1/E2 boundary: static scan `clean: true`, 0 direct SQL writes / 0 direct connections to the E1/E2
  stores from any `exec-brain/*.py`; independently confirmed with two clean `grep` runs. The run's 7
  E2 rows were read back **out of the live `governor.db`** through the public
  `governor.record_request()` interface (5 with provider-returned token counts, 2 codex-cli rows with
  null tokens because the CLI exposes none).

Runtime deployment was refreshed for the changed modules (`scripts/deploy_e3_runtime.py`, backup
`backups/e3-deploy-20260923T213238Z`), and the deployed runtime CLI was re-checked:
`eb.py e3-status` and `eb.py e3-verify-db` both now report **Schema version: 2** (see defect 5 below).

### Unresolved: Google image worker real dispatch (D) — DIAGNOSED 2026-09-23T21:49Z, STILL NOT SETTLED

Original failure (2026-09-23T21:07Z, dispatch `gem-d8c43b8cb447`): the real dispatch returned a
candidate **without an inline image part**; the provider reported 17 prompt tokens and **no output
tokens**, so no image was produced. The adapter reported this honestly
(`no_image_part_in_response`) and the deterministic verifier recorded `FAIL`.

Bounded diagnosis (2026-09-23T21:49Z, evidence
`audits/evidence/2026-09-23T21-49-21Z-e3-google-image-diagnosis/`). **Exactly one** additional real
Google image call was spent, on the **identical** request (same objective, same adapter path), and
the failure **did not reproduce**:

- dispatch `gem-2a656cbf22c2`, `status=COMPLETED`, `error=None`;
- `finish_reason = STOP`, `prompt_feedback = None`, `candidate_count = 1`,
  `candidate_finish_reasons = ['STOP']`;
- `response_part_kinds = ['inlineData:image/jpeg']` — a real image part, no text part;
- `image_mime = image/jpeg`, `image_dims = (1024, 1024)`, `image_size_bytes = 434365`,
  `image_decode_ok = True`;
- provider usage: `promptTokenCount 17`, `candidatesTokenCount 1383`,
  `totalTokenCount 1400`, candidate IMAGE-modality tokens 1120;
- the deterministic verifier recorded `PASS` and the node persisted `COMPLETE`;
- E2 row `obs-20260923-40a19c78` written through the public `governor.record_request()`.

**Recorded conclusion (not an interpretation):** the earlier no-image response is **intermittent**;
it is *not* explained by the request shape, since the same shape now returns a decodable image with
normal provider-reported output tokens. **Remaining unknown:** the trigger of that single
intermittent response. One observation cannot distinguish provider-side variability from a transient
capacity or content-moderation condition, and this run does **not** claim the worker is stable. The
successor task
`agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23` (staged in
`remote-queue/pending/`) owns a bounded repeat series to measure the recurrence rate and a controlled
comparison of the request shape.

Two further facts recorded without interpretation: the objective asked for a **64×64** image and the
provider returned **1024×1024**, so the declared contract ("image decoded") passed while the
prompt-stated size was demonstrably **not** honoured — image size is not under prompt control here.
The earlier attempt's node row in `dag_node` now reads `COMPLETE` because the rehearsal reuses node
ids and `dag_node` is upserted; the historical **failure remains on record** in `performance_evidence`
(`evidence-53374aa1dde4`, `final_success=0`, `failure_attribution=verification_fail`).

### Evidence-backed worker qualification (NEW — 2026-09-23T21:53Z)

Harness: `exec-brain/e3_qualification_benchmark.py::EvidenceBackedBenchmark`, driven by
`scripts/e3_qualification_from_evidence.py`. Evidence:
`audits/evidence/2026-09-23T21-53-01Z-e3-qualification-from-evidence/`.

**No provider call is spent**: every check reads rows that already exist in the live
`orchestration.db` (`performance_evidence`, cross-checked against `dag_node`). The previously
synthetic `ColdStartBenchmark` is now explicitly a *fixture* harness — it marks every result
`evidence_backed=False`, can never return `PASS`, and can never map to `QUALIFIED`
(`registry_state_for()` returns `UNPROVEN` for any non-evidence-backed result).

Qualification bar (stated in the artifact, applied to recorded executions only): at least
`MIN_RECORDED_PASSES = 2` verified passes over at least `MIN_RECORDED_EXECUTIONS = 2` recorded
executions, with at least `MIN_FIRST_PASS_PASSES = 1` first-pass pass. Rationale recorded in the
artifact: a single observation cannot distinguish a capability from a lucky first attempt, and a
worker that has since recovered must not be permanently blocked by an earlier failed attempt.

| Worker | Role (task_family `code`) | Recorded executions | Verified passes | First-pass | Recorded failures | Result | Registry state |
|---|---|---|---|---|---|---|---|
| codex-cli | builder | 3 | 3 | 3 | 0 | pass | **QUALIFIED** |
| codex-cli | integrator | 2 | 2 | 2 | 0 | pass | **QUALIFIED** |
| deepseek-v41-flash | builder | 8 | 8 | 3 | 0 | pass | **QUALIFIED** |
| google-nano-banana-2 | vision | 2 | 1 | 1 | 1 | inconclusive | **EVALUATING** |

The Google vision row is deliberately **not** qualified: only 1 of its 2 recorded executions passed,
and the bar needs ≥ 2 verified passes. `qualified_rows_without_evidence = 0`, and
`CapabilityRegistry.record_qualification` raises rather than write a `QUALIFIED` row with zero
evidence (asserted by a test). Each decision wrote a `worker_capability_event` audit row
(`previous_state` → `new_state`, actor `e3-qualification-from-evidence`, model identity, evidence
references).

Honesty caveat recorded in the artifact: one `performance_evidence` row is one recorded execution
outcome, and rehearsal plans reuse node ids (`dag_node` is upserted), so several rows can share a
`dag_node_id`; the row count is not a count of distinct DAG nodes, and both figures are reported.
The static `worker_registry.py` fields stay `qualification: UNPROVEN` (they are the roster default
and are asserted by tests); each affected worker now carries an additive `qualification_source` field
pointing at the `capability_registry` as the evidence-backed state of record.

### Defects found and fixed this run

1. `gemini_adapter.report_usage_to_e2` reported `totalTokenCount` as *output* tokens whenever
   `candidatesTokenCount` was absent — i.e. it reported prompt+output as output. Observed on the
   failed image response above (17 prompt tokens recorded as 17 output tokens,
   `obs-20260923-f0913024`). Now reports the provider's candidate count only, or null. The historical
   row was left as written; it is a record of the defect, not corrected in place.
2. `e3_commands.init` printed a hardcoded `Schema version: 1`; it now reads the store's real version.
3. The rehearsal's runtime CLI-binding detector looked for the `e3-*` command names inside `eb.py`
   (they live in the deployed `e3_cli.py`, reached through one registration hook in `eb.py`) and so
   wrongly reported no bindings. Fixed, and re-checked without spending a provider call
   (`deployment_check.json`).

### Defects found and fixed in the 2026-09-23T21:32:41Z re-run

4. `E3Planner.build_dag` wired dependencies **positionally** (`dep_index -> node_id_map[dep_index]`),
   so on any plan with 3+ nodes every declared dependency mapped to the *first* node: a 3-node chain
   gave node 3 a dependency on node 1 instead of node 2, i.e. a node could be released before its
   real dependency. Dependencies declared as node ids are now resolved as ids, an unresolvable
   dependency is dropped rather than pointed at an arbitrary node, and two tests assert the wiring.
5. `E3ProductionExecutor` never updated the in-memory DAG node state, so the DAG still reported
   `PLANNED` for a node the store had persisted `COMPLETE` — a dependent node's dependency gate would
   then refuse to run (`dependency_incomplete`) even though its dependency had passed verification.
   Every persisted transition is now mirrored into the DAG, which is what made the decomposed
   multi-worker run possible; asserted by a dependency-gated multi-node execution test.
6. `e3-status` / `e3-verify-db` printed the **oldest** `schema_version` row, so a v2 store was
   reported as `Schema version: 1`. Both now read `MAX(version)`. (The previous run's claim that
   `e3-verify-db` reported "schema v2" is not reproducible against the pre-fix CLI; the store itself
   was v2 — the printed value was wrong.)
7. The rehearsal reported an optional scenario that was **not requested** as passing
   (`google_image_complete: true` with no Google call spent). An unrun scenario is now reported as
   `null` ("not evaluated") and a `scenarios_requested` map is written into the report; the first
   affected artifact is preserved under `audits/evidence/superseded/` with a `SUPERSEDED.md`.

## Owner throughput directive (arrived mid-run — 2026-09-23T22:50Z)

Owner commit `1310440` ("owner: prioritize completion over token conservation") was pushed to the
authority file while this task was executing. It states that for the completion sprint engineering
must **not** be optimised for token conservation or provider cost, and gives the priority order
correctness/truthfulness → completion/deployment readiness → execution speed and unattended
continuity → reliability/recoverability → token efficiency. It explicitly does **not** authorise
weakening gates or fabricating completion.

Effect on this task: none of its recorded results change. This task's live contract independently
capped the Google image diagnosis at **one** additional bounded call, so exactly one was spent; the
directive was received after that call and does not retroactively widen a contract that was already
authoritative. The next task should read the directive in full and may use DeepSeek aggressively
where it is the appropriate worker, while keeping every task bounded enough to avoid hangs.

## Worker / provider state

Smoke readiness is not qualification; qualification is evidence-driven. Qualification below is the
recorded `capability_registry` state (task_family `code`), derived from real executions only — see
the evidence-backed qualification section above.

- Codex CLI: routable=true; executed on the real path (scenario C and, in the 21:32:41Z re-run,
  scenario F node 2 under a dependency gate, COMPLETE); served model identity **UNKNOWN**; usage not
  exposed by the CLI; E2 linkage VERIFIED; **qualification: builder QUALIFIED (3/3/3), integrator
  QUALIFIED (2/2/2)**
- DeepSeek (`deepseek-flash`): routable=true; executed on the real path (scenarios A and B, plus
  scenario F node 1 — rejected then repaired — COMPLETE); provider-returned usage captured;
  E2 linkage VERIFIED; **qualification: builder QUALIFIED (8 recorded executions / 8 verified passes
  / 3 first-pass, 0 failures)**
- Google image worker (`gemini-3.1-flash-image`): routable=true; the 21:07Z real dispatch failed with
  no image part, and the bounded 21:49Z re-dispatch of the identical request **succeeded** (decodable
  1024×1024 JPEG). The failure is intermittent and its trigger is an open unknown.
  **qualification: vision EVALUATING (2 recorded executions, 1 verified pass)** — not qualified
- Remaining seven generic API workers (Mistral Small 4, GLM-5.3 Flash, Qwen3.8-27B, LongCat 2.0,
  MiniMax M3, Step 3.7 Flash, Tencent Hunyuan Hy3): adapters exist; owner-local credentials and live
  readiness evidence outstanding; routable=false — and correctly refused by the execution leg
  (scenario E)

## Remote Task Queue

- Canonical GitHub task-data location: `remote-queue/`; implementation package: `remote_queue/`
- Bridge: implemented and remotely E2E-verified
- `agent-*` tasks are dispatched into the Hermes CLI through `remote_queue/hermes_dispatch.py`
- Queue tests are isolated (`remote_queue/tests/test_queue.py`: 30/30, exit 0)
- Scheduler: `HermesRemoteQueuePoller` registered and Ready (2-minute cadence)
- Recorded defect, now **FIXED** (2026-09-24T02:45Z): `poller.handle_task` used to route any task id
  containing "operational" to `handle_operational_build()`, which returns a hardcoded status with no
  execution evidence. It silently swallowed the genuine agent task
  `agent-operational-brief-health-backup-persistence-2026-09-23` (claimed 2026-09-24T01:38:05Z, never
  dispatched). The `agent-` dispatch branch now precedes every legacy placeholder router, the
  swallowed task was restored to `pending/` with the same task_id, and
  `remote_queue/tests/test_poller_routing.py` (9 tests) guards the contract. The non-agent umbrella
  `full-operational-build-2026-09-24` deliberately keeps the placeholder. Evidence:
  `audits/evidence/2026-09-24T02-45-00Z-blocked-work-reconciliation-audit/`.
- Historical blocked-work reconciliation (2026-09-24T02:45Z): all 12 `remote-queue/blocked/` records
  classified — 10 superseded/resolved by verified successor evidence (no rerun needed), 2 parked as
  deterministic owner/external credential blockers. 0 unresolved non-owner recoverable blockers remain.
- `full-operational-build-2026-09-24` remains the umbrella record in `running/` (no worker).
- This run: `agent-e3-local-production-rehearsal-retry-2026-09-23` claimed and worked the formal
  production-rehearsal re-run (see the 21:32:41Z section above); the Google image diagnosis and the
  qualification benchmark were deliberately left to the pre-existing pending task
  `agent-e3-image-diagnosis-and-multiworker-execution-2026-09-23`, which was **not** raced and
  produced no evidence to consume yet (still pending). 7 bounded real provider calls were spent.
  One successor task was staged in `remote-queue/pending/` before exit.
- Bridge validation run `agent-bridge-watchdog-validation-2026-09-23` (2026-09-23T21:18Z, base SHA
  `07dd4a1`) verified the hardened bridge commits `617fd47c` and `b83c9ad` and found **no defect in
  the validated path**, so no production code was changed: no-stream watchdog (default 300s,
  `HERMES_REMOTE_IDLE_TIMEOUT`), PID-scoped child-tree termination, dispatch hard bound (default
  1200s, `HERMES_REMOTE_TASK_TIMEOUT`), watchdog exit code 124 surfaced as `execution_error` and never
  as completion, and `running/<task_id>.json` frozen as immutable input with standing conditional
  approvals respected. 12 new isolated bridge tests; 11 suites / 335 passed / exit 0. Evidence:
  `audits/evidence/2026-09-23T21-18-27Z-bridge-watchdog-validation/`.
- That run staged exactly one successor: `agent-e3-local-production-rehearsal-retry-2026-09-23`
  (pending) — the formal production-rehearsal re-run on the now-built execution leg, scoped not to
  race or duplicate the already-pending `agent-e3-image-diagnosis-and-multiworker-execution-2026-09-23`.
- Owner directive `a58549c` / `2d5f332` / `d7e718c` ("Owner directive update — 2026-09-23 late
  evening") arrived during this run: continue all independent local work overnight, do **not** enable
  local E3 Stage 2 overnight, and complete it only after Mukund configures all remaining provider
  credentials on 2026-09-24 and the readiness gates are re-run. Both staged/pending E3 contracts now
  carry that directive; Stage 2 remains disabled.

## Stage 2 readiness evaluation (precondition by precondition)

Recorded preconditions (authority owner-directive update + `full_build_tracker.md`). Evaluated for
evidence; **no precondition was skipped or weakened**, and Stage 2 remains disabled by direct owner
instruction irrespective of the results below.

| # | Precondition | Result | Evidence |
|---|---|---|---|
| 1 | E1/E2/E3/E4/E5 relevant regressions pass | MET | 12 suites, 364/364, 0 failed, 0 errors, 0 skipped, every suite exit 0, SHA `4da92eb` (`…T21-53-37Z-e3-image-diagnosis-and-qualification`) |
| 2 | Production rehearsal passes | **PARTIALLY MET (improved)** | the execution leg runs real workers end-to-end including a **decomposed multi-worker plan** (scenario F: 2 nodes, 2 distinct workers, per-node deterministic verification, rejection → REWORK → targeted repair → re-verify, dependency-gated dispatch) with persisted DAG state/evidence rows and E2 linkage, plus the refusal path; the Google image worker's earlier real dispatch **failure did not reproduce** on the identical request under a bounded single-call diagnosis (200, decodable 1024×1024 JPEG, deterministic verifier PASS), so the previously "failing" image path now has a recorded success — **but the failure was intermittent and its trigger is still an open unknown**, and the prompt-stated image size was not honoured. Not settled here |
| 3 | No unresolved critical integrity/privacy/safety defect | MET (in the E3 path) | nodes cannot complete without a verification PASS (tests assert the leg's truth rules, incl. dependency-gated multi-node execution); refusal path spends no provider call; raw objectives stored only as hashes; simulated evidence provably cannot reach the production stores (fail-closed + hashes incl. WAL); live stores hold no simulated row and **no QUALIFIED row without recorded evidence** (`qualified_rows_without_evidence = 0`; the registry now *refuses* to write one); E1/E2 boundary untouched — this run wrote only to the E3 store, and the qualification/regression steps spent **no** provider calls |
| 4 | Worker routing/qualification state evidence-driven | MET (strengthened) | `routable` still derives from smoke PASS + E2 linkage; qualification is now derived **only** from recorded `performance_evidence` via `EvidenceBackedBenchmark`, with the fixture harness structurally unable to produce a qualification; 3 scopes QUALIFIED with recorded evidence counts and audit events, 1 left EVALUATING because the evidence does not clear the bar; the static roster field is not used as the qualification source |
| 5 | Rollback/recovery available | MET | `scripts/deploy_e3_runtime.py` backs up every overwritten file with a SHA-256 manifest and a documented `--restore` (this run: `backups/e3-deploy-20260923T214919Z`, `…T215200Z`, `…T215301Z`, `…T215329Z`); the pre-patch `eb.py` is backed up; the E3 store is separate from E1/E2 |
| 6 | State/evidence truthfully updated | MET | this file + `full_build_tracker.md` + this run's evidence artifacts, including the dry-run artifact, the earlier qualification artifact superseded by a field addition (preserved, not overwritten), and the explicitly recorded remaining unknown |

**Exact remaining conditions (recorded, not resolved):**

1. **Direct owner instruction (governing):** the live task contract states Stage 2 / production
   dispatch must not be enabled by this task regardless of outcome, and the owner's late-evening
   directive (`a58549c` / `2d5f332` / `d7e718c`) defers local Stage 2 completion until **after
   Mukund configures all remaining provider credentials on 2026-09-24 and the readiness gates are
   re-run**. Enabling now requires that separate, explicit owner step.
2. **The Google image worker failure is intermittent, not resolved** — one identical request failed
   with no image part, the next returned a decodable 1024×1024 JPEG. The trigger is unknown and a
   bounded repeat series is required before the worker can be called stable or (re)qualified for the
   vision role. Prompt-stated image size is also not honoured (64×64 requested, 1024×1024 returned).
3. **Qualification is now partial, not complete** — 3 of 4 evidence-bearing (worker, role) scopes are
   QUALIFIED for task_family `code`; the vision role is EVALUATING, and the seven credential-missing
   workers have no execution evidence at all (a check that cannot be evaluated is never counted as a
   pass).
4. **E4 checkpoint/failover and E5 convergence/safe-mode drills on real execution paths remain
   unevidenced** — the contract gates them behind Stage 2 enablement, which is disabled.

Resolved from the previous list: *"Qualification evidence is still absent for every worker"* — now
partially resolved (3 scopes QUALIFIED from recorded evidence, with the bar, counts and audit events
recorded). The previously listed item *"Google image worker real dispatch fails — root cause
undetermined"* is now **partially** resolved: the diagnosis was made and the failure did not
reproduce, so the recorded state is "intermittent, trigger unknown" rather than "fails".

## Company Registry gap audit + non-E3 runtime validation (2026-09-23T22:35Z)

Task `agent-company-registry-gap-audit-and-runtime-services-2026-09-23`. Evidence:
`audits/evidence/2026-09-23T22-30-00Z-company-registry-gap-audit/` (`inventory.json` + `evidence.md`).
New deterministic worker: `scripts/company_inventory.py` (roster A20; read-only; `--json` output).

Verified facts (all machine-checked in this run, no provider calls):

- Roster reconciliation: **50/50 roster items accounted for, 0 unmapped**; 7 owned Windows
  scheduled tasks found and **all mapped** to A18/A19/B02–B05.
- Hermes Chief live: gateway `running`, Discord `connected`, updated 2026-09-23T22:23:02Z.
- `ChiefDiscordSync` green (last 8 runs `result: ok`; last publish 21:06:04Z, 8 published,
  0 rejected); archive checkpoint advancing.
- `HermesRemoteQueuePoller` working (2-min cadence, queue-log pickups, claimed this task at
  22:22:06Z). It reports last result `0x800710E0` while `Running` — **recorded, meaning unresolved**,
  not interpreted.
- E1 `audit --verify` **PASS**; E2 `gov-verify` **PASS**; E3 `e3-verify-db` **PASS** (schema v2);
  `eb brief` (A04) works deterministically and still reports unknown provider dimensions as UNKNOWN.
- Legacy donor systems (Career Ops install, July Chief, Mukund OS, new custom Chief) all still exist;
  none was revived, restructured or deleted.
- Boot persistence: `Hermes_Gateway` survives logon (logon trigger + restart-on-failure +
  `StartWhenAvailable`); `HermesRemoteQueuePoller` and `ChiefDiscordSync` have **no** logon/boot
  trigger and no `StartWhenAvailable`, so post-reboot resumption is **UNVERIFIED** (a reboot is
  prohibited by this contract). All Chief tasks are `Interactive only`, so unattended operation
  requires the laptop to stay signed in and awake — recorded as an owner-side precondition.

Defect found and fixed (non-E3 scheduled service):

- `ChiefCareerScan-UK` reported last result **1** while its scan had actually succeeded
  (`ok: true`, exit 0, 2861 jobs, 86.6 s). `career_ops_cli.emit()` raised `UnicodeEncodeError` because
  the scheduled run redirects stdout to a file in the local ANSI code page (cp1252) and the payload
  contained non-Latin job titles. `emit()` now encodes to the real stdout encoding and falls back to
  ASCII-escaped JSON (still exactly one JSON object); `run_scheduled_scan.cmd` also sets
  `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`. New regression suite
  `career-ops/tests/test_emit_encoding.py` (5 tests, cp1252/ascii/utf-8); career-ops suite 33/33.
  **Live confirmation:** the scheduled task was re-run through the real Task Scheduler path at
  2026-09-23T22:28:39Z (89.0 s bounded dry-run, no tracker write) → `Last Result 0` (was 1),
  `uk-last-stdout.json` now valid JSON (`ok: true`, `exit_code: 0`, no traceback), new run record
  `scan-uk-20260923T222839Z.json`; the scan found 1 new eligible offer (Celonis, London,
  trust 85/100, `company_domain_mismatch` flag) which was **not** written to any tracker.

Coverage gap closed:

- B09 Monthly Tracker Rollover / archive worker was owned by no task, and the B07/B08 Career Ops
  interface produced by the `execution_error` task existed only in the unpushed working tree
  (now committed). Exactly **one** successor task was staged:
  `remote-queue/pending/agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23.json`,
  explicitly excluding the scope already owned by the regional-lanes and Company Watch tasks.
  *(Update 2026-09-24T02:04Z: that successor has now executed — B09 is built, tested and evidenced;
  see the "Career Records: tracker writer + monthly rollover" section below.)*

No roster entry needed to be added: the audit found no missing owner-relevant workflow.

## E3 Stage 2 readiness gate re-run (2026-09-23T22:35Z–22:37Z)

Task `agent-e3-stage2-readiness-gate-rerun-2026-09-24`. This is the gate re-run the owner's
late-evening directive asks for **after** the remaining provider credentials are configured. It was
executed now against current state; the credentials are **not yet configured**, so the gate correctly
leaves Stage 2 disabled. The gate itself made **0 real provider calls** and read no credential value.

Evidence:
- `audits/evidence/2026-09-23T22-35-32Z-e3-stage2-readiness-gate-rerun/` — full regression via
  `scripts/evidence_runner.py --label e3-stage2-readiness-gate-rerun`.
- `audits/evidence/2026-09-23T22-37-29Z-e3-stage2-readiness-gate-verdict/` — the gate verdict
  (`scripts/e3_stage2_readiness_gate.py`, new; deterministic, 0 provider calls).
- Two earlier gate-run intermediates are preserved (not overwritten) under
  `audits/evidence/superseded/*-e3-stage2-readiness-gate-rerun-superseded-by-gate-verdict/`; they
  were produced by an early build of the gate script that mis-selected its regression input.

Verified facts (all machine-checked this run):

- **Credentials (presence only — no value read or logged): 0/7 of the credential-missing providers
  have locally configured credentials.** Still missing: `mistral-small-4`, `glm-53-flash`,
  `qwen38-27b`, `longcat-2.0`, `minimax-m3`, `step-37-flash`, `tencent-hunyuan-hy3`. The three
  already-configured workers verified present: `codex-cli` (chatgpt login),
  `google-nano-banana-2` (credential_manager), `deepseek-v41-flash` (credential_manager).
- Regressions: 12 suites, **364 collected / 364 passed, 0 failed, 0 errors, 0 skipped, every suite
  exit 0**, code SHA `56d923b`.
- Real-path production rehearsal: **consumed, not repeated** (the contract forbids repeating it).
  Re-derived from `audits/evidence/2026-09-23T21-32-41Z-e3-production-execution-rehearsal/evidence.json`
  (sha256 `88212b70…`): 0 failed checks, 7 bounded real calls, every multi-node / dependency-gate /
  isolation / E1-E2-boundary check `True`; `google_image_complete` = `None` (unrun — not counted as a
  pass).
- Google image worker: **still INTERMITTENT / not settled** — routable `true`, vision role
  `EVALUATING`, 2 recorded executions / 1 verified pass. Consumed from the recorded diagnosis.
- Qualification (evidence-derived, read-only, 0 calls): codex-cli builder QUALIFIED (3/3/3),
  codex-cli integrator QUALIFIED (2/2/2), deepseek-v41-flash builder QUALIFIED (8/8/3),
  google-nano-banana-2 vision EVALUATING. `qualified_rows_without_evidence = 0`.
- Isolation + boundary (fresh, in-run): all production writes refused fail-closed; all three stores
  byte-identical before/after **including `-wal`/`-shm` sidecars**; isolated sink written outside the
  production root; E1/E2 static scan `clean: true`, 0 direct SQL violations, E2 reached only via
  `governor.record_request()`.
- Rollback: deploy-script `--restore` path present, 14 backup dirs with manifests, 0 runtime E3
  modules missing, orchestration schema v2.

**Verdict: Stage 2 NOT ENABLED.** Enablement requires all three conditions; all three currently fail:

1. (a) credentials confirmed configured — **FAIL (0/7)**.
2. (b) every readiness criterion objectively satisfied by this run's evidence — **FAIL**: the Google
   image worker's real-dispatch intermittency is unresolved. Every other criterion is MET
   (regressions, real-path rehearsal, integrity/privacy/safety, evidence-driven qualification,
   rollback).
3. (c) explicit owner authorization for enablement at this point — **NOT SATISFIED**: the owner's
   authorization is conditional on the provider credentials being confirmed configured, which they
   are not (authority directive update 2026-09-23 late evening, commits `a58549c`/`2d5f332`/`d7e718c`).

E4 checkpoint/failover and E5 convergence/safe-mode drills on real execution paths remain **gated
behind Stage 2** and were not run.

## E3 Stage 2 readiness gate re-run — credential-triggered continuation (2026-09-23T22:41Z)

Task `agent-e3-stage2-readiness-gate-after-provider-keys-2026-09-24`. This is the credential-triggered
continuation of the 22:37Z gate re-run. Its first step is a **presence-only credential probe**; the
probe found the seven provider credentials **still absent**, so per the contract the gate remains
disabled and the exact owner action is recorded. The gate made **0 real provider calls** and read no
credential value.

Evidence:
- `audits/evidence/2026-09-23T22-40-55Z-e3-stage2-readiness-gate-rerun/` — full regression via
  `python scripts/evidence_runner.py --label e3-stage2-readiness-gate-rerun`.
- `audits/evidence/2026-09-23T22-41-57Z-e3-stage2-readiness-gate-verdict/` — the gate verdict
  (`python scripts/e3_stage2_readiness_gate.py`; deterministic, 0 provider calls).

Verified facts (all machine-checked this run, code SHA `88af27a`):

- **Credentials (presence only — no value read or logged): still 0/7.** All seven remain absent from
  both Windows Credential Manager and environment: `mistral-small-4`, `glm-53-flash`, `qwen38-27b`,
  `longcat-2.0`, `minimax-m3`, `step-37-flash`, `tencent-hunyuan-hy3`. `newly_configured_workers = []`,
  so no provider onboarding or smoke test was warranted or run.
- Regressions: 12 suites, **364 collected / 364 passed, 0 failed, 0 errors, 0 skipped, every suite
  exit 0**.
- Real-path production rehearsal: **consumed, not repeated** (0 failed checks; `google_image_complete`
  = `None`, i.e. unrun — never counted as a pass); isolation fail-closed, stores byte-identical
  including `-wal`/`-shm`, E1/E2 boundary clean; qualification evidence-driven
  (`qualified_rows_without_evidence = 0`); rollback available (deploy `--restore`, backups with
  manifests, schema v2).

**Verdict: Stage 2 NOT ENABLED** (unchanged from 22:37Z). All three enablement conditions still fail:

1. (a) credentials confirmed configured — **FAIL (0/7)**.
2. (b) every readiness criterion objectively satisfied by this run's evidence — **FAIL**: the Google
   image worker's real-dispatch intermittency is unresolved. Every other criterion is MET.
3. (c) explicit owner authorization for enablement at this point — **NOT SATISFIED**: the owner's
   standing conditional authorization applies only once the provider credentials are confirmed
   configured, which they are not.

E4 checkpoint/failover and E5 convergence/safe-mode drills remain **gated behind Stage 2** and were
not run.

**Exact owner action required:** on 2026-09-24, configure the seven provider credentials locally
(Windows Credential Manager targets `mistral`, `glm`, `qwen`, `nous`, `minimax`, `stepfun`,
`hunyuan`, or the env vars `MISTRAL_API_KEY`, `GLM_API_KEY`, `DASHSCOPE_API_KEY`, `NOUS_API_KEY`,
`MINIMAX_API_KEY`, `STEP_API_KEY`, `HUNYUAN_API_KEY`). Once present, the successor gate task re-runs
`scripts/e3_stage2_readiness_gate.py` and enables LOCAL Stage 2 only if all three conditions hold.

## E3 Stage 2 readiness gate re-run — credential-triggered retry (2026-09-23T22:52Z–22:54Z)

Task `agent-e3-stage2-readiness-gate-after-provider-keys-retry-2026-09-24`. This retry exists only to
re-check the credential condition after the owner's planned key configuration window. The
**presence-only** credential probe (no secret value read, logged or committed; no network call) was run
first and found **0/7** of the credential-missing providers configured:

- Windows Credential Manager targets present on this machine: `gemini:antigravity`, `deepseek`,
  `gemini-api`, plus git/GitHub/Microsoft/Outlook/DriveFS entries. **None** of `mistral`, `glm`,
  `qwen`, `nous`, `minimax`, `stepfun`, `hunyuan` is present.
- env vars `MISTRAL_API_KEY`, `GLM_API_KEY`, `DASHSCOPE_API_KEY`, `NOUS_API_KEY`, `MINIMAX_API_KEY`,
  `STEP_API_KEY`, `HUNYUAN_API_KEY`: all **absent**.
- Probe path: `generic_openai_adapter.get_adapter(<worker>)._resolve_auth()` (Credential Manager →
  env), reporting presence + auth-source name only. `newly_configured_workers = []`.

Because no provider was newly configured, the contract's identity/model discovery, smoke test,
`governor.record_request()` linkage and `routable=true` steps **do not apply to this run** and were not
performed: no worker was marked routable, no smoke test was claimed, and **no provider call was spent**
by this task (0 real provider calls).

Evidence produced this run (executable, no provider calls):

- `audits/evidence/2026-09-23T22-52-48Z-e3-stage2-readiness-gate-rerun/` — full regression via
  `python scripts/evidence_runner.py --label e3-stage2-readiness-gate-rerun`; script
  `scripts/evidence_runner.py`; **12/12 suites pass, 364 collected / 364 passed, 0 failed, 0 errors,
  0 skipped, every applicable suite exit 0**, code SHA `342ee66b6ca67b03dd6c384702cb496fadaf31d8`,
  python 3.11.16. Per-suite counts and exact commands are in the bundle's `evidence.md`.
- `audits/evidence/2026-09-23T22-53-53Z-e3-stage2-readiness-gate-verdict/` — the gate verdict from
  `python scripts/e3_stage2_readiness_gate.py` (deterministic, 0 provider calls, never enables
  anything itself). All earlier verdict bundles (22:37:29Z, 22:41:57Z) are preserved; nothing was
  overwritten.

**Verdict: Stage 2 NOT ENABLED** (third consecutive gate re-run with the same result). All three
enablement conditions fail:

- **(a) credentials configured — FALSE.** 7/7 still missing (listed above).
- **(b) every readiness criterion objectively satisfied — FALSE.** Five of six criteria are MET with
  fresh evidence: regressions 12/12 suites / 364 tests; real-path production rehearsal **consumed, not
  repeated** (`audits/evidence/2026-09-23T21-32-41Z-e3-production-execution-rehearsal/`, 0 failed
  checks, 7 bounded real provider calls recorded in that prior run); rehearsal-evidence isolation
  fail-closed with production stores byte-identical **including WAL/SHM sidecars**; E1/E2 boundary
  clean with E2 reached only via `governor.record_request()`; qualification evidence-driven
  (`qualified_rows_without_evidence = 0`; codex-cli builder/integrator and deepseek-v41-flash builder
  QUALIFIED, google-nano-banana-2 vision EVALUATING); rollback available (restore path present, 14
  backup dirs with manifest, all E3 modules deployed, orchestration schema v2). The **only** unmet
  criterion remains the Google image worker's real-dispatch intermittency (owner task
  `agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23`),
  declared `INTERMITTENT_NOT_SETTLED` with an open trigger.
- **(c) explicit owner authorization for enablement at this point — NOT SATISFIED.** The owner's
  standing conditional authorization (`a58549c` / `2d5f332` / `d7e718c`) applies only once the provider
  credentials are confirmed configured; they are not, so the authorization does not yet apply.

E4 checkpoint/failover and E5 convergence/safe-mode real-path drills remain **gated behind Stage 2**
and were not run; the harness owned by
`agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23` was not consumed because the contract
gates those drills behind enablement.

*(Superseded 2026-09-24T23:55Z: those drills have now been built and evidenced with injected
provider failures on an isolated database — see §E4/E5 real-path drill harness below. Only the
live-provider variant still waits on Stage 2 and the credentials.)*

**Exact owner action required:** configure the seven provider credentials locally (Windows Credential
Manager targets `mistral`, `glm`, `qwen`, `nous`, `minimax`, `stepfun`, `hunyuan`, or the env vars
`MISTRAL_API_KEY`, `GLM_API_KEY`, `DASHSCOPE_API_KEY`, `NOUS_API_KEY`, `MINIMAX_API_KEY`,
`STEP_API_KEY`, `HUNYUAN_API_KEY`). The successor staged by this run re-probes presence, verifies each
newly configured provider (bounded `/models` identity discovery + one harmless smoke test + E2 linkage
through `governor.record_request()`), then re-runs the gate and enables LOCAL Stage 2 only if all three
conditions hold.

## E4/E5 real-path drill harness (2026-09-24T23:55Z)

Task `agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23`. Evidence bundles:

- `audits/evidence/2026-09-23T23-55-06Z-e4e5-real-path-drill-harness/` (`evidence.json` + `evidence.md`)
  — the drill run itself: **33/33 checks, `real_provider_calls = 0`, `stub_dispatches = 10`,
  live-store SHA-256 unchanged, 0 live E2 rows**.
- `audits/evidence/2026-09-23T23-55-09Z-e4e5-real-path-drills/` — the whole-repo regression:
  **15 suites, 438 collected / 438 passed, 0 failed, 0 errors, 0 skipped, every suite exit 0**
  (code SHA `bd0a7aa`).

New worker: `exec-brain/e4e5_drill_harness.py` (drill driver) plus
`exec-brain/tests/test_e4e5_drills.py` (38 tests, registered in `scripts/evidence_runner.py`).
New E5 capability in `exec-brain/safe_mode.py`: `OWNER_ONLY_TRIGGERS`, `record_owner_override`,
`SafeModeRecovery`.

The harness drives the **real** execution abstractions (`E3ProductionExecutor`,
`ExecutionAdapterRegistry`, `OrchestrationStore` schema v2, `CapabilityRegistry`, `EquivalentFailover`,
`CheckpointManager`, `SafeModeManager`, `ConvergenceEnforcer`, `MalformedOutputHandler`,
`SafeModeRecovery`) against a disposable isolated database, with provider transport replaced by a
recorded in-process stub. Six drills, all PASS:

1. **D1 checkpoint → equivalent failover → state handover.** Checkpoint created and restored
   byte-identical; `deepseek-v41-flash` FAILED with the injected transport outage recorded verbatim;
   `EquivalentFailover` selected `codex-cli` from the drill registry — and the artifact also records
   the **live** registry rows read through a snapshot copy (`codex-cli` builder QUALIFIED 3/3/3,
   `deepseek-v41-flash` builder QUALIFIED 8 recorded/3 first-pass); the replacement was dispatched
   with the restored checkpoint embedded in its objective (proven by objective hash) and reached
   COMPLETE only after a deterministic verification PASS; the persisted state log shows the failed
   cycle then the replacement cycle on the same node.
2. **D2 no equivalent worker → owner escalation.** The registry is asked a real question for role
   `verifier` and truthfully answers `None`; an owner escalation is recorded
   (`no_qualified_worker`, `OWNER_APPROVAL_REQUIRED`) in `decision_rationale_event`; the **quality
   floor is not lowered**.
3. **D3 provider outage.** Both a provider-reported error (HTTP 503) and a raised transport error
   leave the node FAILED with the error verbatim, with the evidence row written; no node reaches
   COMPLETE; **no failover is claimed** for a pure outage.
4. **D4 malformed output.** The shallow structural pre-check flags None/empty/missing-field output and
   is explicitly recorded as *not* the authority (it passes a non-empty garbage string); the
   independent deterministic verifier rejects the malformed output; with a repair budget the node
   converges to a verified COMPLETE via `REWORK`.
5. **D5 repeated-failure convergence cap.** The loop terminates exactly at the cap (3 dispatches, no
   4th) with a single stop marker; convergence events escalate to `quarantine_worker`; the system
   enters DEGRADED then SAFE_MODE.
6. **D6 safe-mode entry, owner-override audit and recovery.** Safe-mode event persisted; recovery is
   **refused** while an owner-only trigger is active without an override, and **refused** when the
   health probe is unhealthy; `record_owner_override` writes both the safe-mode event and a
   `decision_actor='owner'` rationale row; recovery then succeeds → NORMAL with 0 active events, and
   owner-only triggers are resolved with `auto_resolved = 0` (an owner authorisation, not an
   automatic one).

Truth boundaries recorded in the artifact (not glossed over): the evidence kind is
`stubbed_provider_failure` and **no real external provider evidence is claimed**; the failover
equivalence rows are a labelled fixture written only into the disposable drill DB
(`capability_fixture.kind = "drill_fixture_not_qualification_evidence"`); the recovery health probe is
a labelled local stub recorded as `provider_health_verified = false`; Stage 2 is **not** enabled and
nothing was deployed.

Two real defects were found and fixed on the way:

- `OrchestrationStore.connect()` discarded the connection `init_db()` returned, leaking one SQLite
  file handle per store connect and keeping the store DB locked on Windows after `close()`
  (`exec-brain/e3_execution.py`).
- The first revision of the drill harness opened the **live** runtime `orchestration.db` read-only,
  which created stray `orchestration.db-shm` / `-wal` sidecars in the deployed runtime directory and
  broke the E1 `test_t13_no_gateway_modification` directory-hygiene assertion. The harness now reads a
  scratch **snapshot copy** and never opens the live file; the stray sidecars were removed (the live
  store's own mtime was unchanged) and the suite passes again. The intermediate regression bundle is
  preserved with its reason under
  `audits/evidence/superseded/2026-09-23T23-51-09Z-e4e5-real-path-drills-superseded-by-final-drill-run/`.

Still owner-gated: the **live-provider** variant (a real provider failure actually failing a node,
and real provider-health re-verification before leaving safe mode). The harness has **no live-provider
mode** by design, so that is not claimed. The exact post-key sequence and the acceptance decision
needed from Mukund are recorded in `tasks-or-issues/overnight-owner-actions-2026-09-24.md` §8.

## Current blockers / owner dependencies

- E3 Stage 2 local enablement: **blocked — gate re-run 2026-09-23T22:53Z (credential-triggered
  retry): Stage 2 NOT ENABLED.**
  The readiness gate now runs deterministically (`scripts/e3_stage2_readiness_gate.py`); the only
  unmet readiness criterion is the Google image worker's intermittency, and the blocking conditions
  are (a) 0/7 provider credentials configured and (c) owner authorization that is conditional on
  those credentials being configured.
- Google image worker real dispatch: **intermittent** — the identical request failed once (no image
  part) and succeeded on the bounded re-dispatch. The trigger is unknown; a bounded repeat series is
  required. Engineering, not owner action.
- Seven provider credentials / account readiness steps remain owner/provider dependent —
  **re-confirmed 0/7 configured as of 2026-09-23T22:52Z** by two independent presence-only probes
  (Windows Credential Manager target listing and `generic_openai_adapter` auth resolution; all seven
  env vars absent). Secrets are never read into a printed variable and never touch GitHub/queue/logs.
- Deployment architecture: intentionally deferred by owner until local operation is proven. The
  authority records laptop-primary + GitHub control plane + VPS watchdog/failover as the current
  owner *preference*, explicitly not a final decision and not authorization for VPS cutover.
- VPS access/details required before any real deployment/cutover; cutover is not authorized

## CV/cover-letter workflow connected + minimal LinkedIn workflow (2026-09-24T23:40Z)

Task `agent-cv-cover-letter-linkedin-workflows-2026-09-23` (authority: the 2026-09-24 cutover file,
§ CV + cover-letter workflow / § LinkedIn workflow). Evidence:
`audits/evidence/20260923T234310Z-cv-linkedin-workflows/acceptance.json` (+ `.md`) — **23/23 critical
checks pass**, 0 provider calls, 0 external LinkedIn actions, 0 applications.

Reused, not rebuilt: the Career Ops install's `cv.md` / `config/profile.yml` / `config/cv-facts.json`
as canonical source truth; its own `verify-cv-facts.mjs` as the fact gate; its own
`generate-cover-letter.mjs` `buildHtml` as the cover-letter renderer; and Company Watch's
`build_shared_dedupe` / `dedupe_decision` plus `career-ops/tracker_writer.py` for every dedupe key and
workbook write.

- New: `career-ops/cv_workflow.py` (+ `cv_workflow_config.json`, `cv_render_cover.mjs`) — job context
  from Career Ops state → tailored CV draft + cover-letter payload/HTML. Tailoring is **deterministic
  reordering only**: no canonical line is rewritten, summarised, merged or added, every draft line is
  mapped back to its `cv.md` line in `cv_draft_provenance.json`, and posting terms with no canonical
  evidence are reported as `owner_input_required` instead of being claimed.
- New: `career-ops/linkedin_workflow.py` (+ `linkedin_workflow.json`) — read-only signal intake from
  owner-exported local files, dedupe against Career Ops **and** Company Watch, unsent profile/post/
  outreach drafts, and career-ops handoff. **No LinkedIn login, API, scraping, browser or network I/O
  exists in the module** (asserted by test), and `guard` refuses and logs every external action.
- New: `career-ops/run_cv_linkedin_acceptance.py` — representative end-to-end local acceptance.
- Tests: `career-ops/tests/test_cv_workflow.py` 21 passed, `career-ops/tests/test_linkedin_workflow.py`
  34 passed, whole `career-ops/tests/` 88 passed.

Recorded limitations: the acceptance job description is an explicitly labelled **synthetic fixture**
(not a live vacancy, no liveness claimed); PDF cover letters are not produced (headless Chromium, owner
-gated); the live LinkedIn account surface is **owner-gated** and therefore untested against the real
account — only the local read-only/draft interface is proven.

Successor task: **none staged** — `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`
(pending) already covers the whole-company local acceptance test, including the LinkedIn draft/read-only
path and the CV/cover-letter path, so a new task would duplicate it.

## Regional job-search workers + deterministic scheduled execution (2026-09-24T00:14Z) — NEW

Task `agent-regional-job-search-agents-and-schedulers-2026-09-23`. Attempt 1 (00:00–00:20Z) built and
evidenced this work but was cut off by a 1200 s dispatch timeout before it could update state or
commit; attempt 2 verified the uncommitted tree, re-confirmed the evidence, updated state and
committed. No work was recreated or duplicated.

- One implementation, four regions: `career-ops/regional_job_search.py` (sha256 `962d38a9…`). Dedupe,
  the workbook index, the cross-month index and the write path are the **same code the UK lane already
  used** (`tracker_writer.py`) — there is no per-region fork.
- Lane configs for Dubai, Japan and Singapore live in this control plane under
  `career-ops/lanes/<region>/` and are referenced by absolute path, so the owner's Career Ops
  installation is **never modified**. `resolve_lane` reports all four regions `ready: true`.
- Eligibility/policy filtering: `career-ops/regional_policy.json` (sha256 `ed045010…`) applied by
  `evaluate_record` — owner title policy, an explicit region location scope mirroring the scanner's own
  tier order, the owner's clearance/citizenship rejection policy from `config/profile.yml`, a
  multi-year-experience rejection, a mandatory-URL rule, and **fail-closed** behaviour when no region
  scope can be resolved.
- Owner facts are never invented: UK authorisation is `authorised` (Graduate visa to 2027-12-23, from
  `config/profile.yml`); for Dubai/UAE, Japan and Singapore the policy and every accepted record say
  **UNKNOWN** and carry the region tracker's own `visa_pathway` text verbatim (`Visa unknown` /
  `JAPAN WORK VISA UNKNOWN` / `WORK PASS UNKNOWN`).
- Deterministic scheduled execution is **live**: `ChiefCareerScan-UK` 23:45, `-Dubai` 23:50, `-Japan`
  23:55, `-Singapore` 00:00 — all four reported `Ready` by `install_schedules.py --status`. Every
  scheduled run is a bounded **dry-run**: it never writes a tracker and never submits anything.
- Idempotency: `runtime/career-ops/scan-runs/regional-run-state.json` keys each run by a SHA-256 of its
  accepted candidate set, so a replayed run marks candidates `duplicate-prior-run` and emits an empty
  manifest; independently, the shared writer refuses anything already in the workbook, a rotated
  workbook or the cross-month ledger. Dry-run `New offers:` lines carry no URL and are therefore
  reported as `scan_offers_without_url` — they can never become tracker rows on their own.
- Bounded dry-run evidence: two full `run-all` passes 2026-09-24T00:06–00:19Z, every region
  `last_status: ok`, `last_would_append: 0`; UK 93 candidates, Dubai/Japan/Singapore 0 candidates.
- Safe workbook-write acceptance: the write was applied to a **test copy** with a hash-verified
  pre-write backup, verified (headers unchanged, owner columns unchanged, no duplicate URLs, no formula
  errors), and then rolled back to the pre-write hash (`equals_pre_write_hash: true`). Probe rows were
  labelled `NOT A REAL VACANCY` on the reserved `.invalid` domain and exist only in the test copy.
- All four canonical workbooks were re-hashed after the run and are **byte-identical** to the
  acceptance record: UK `84c53dcb…`, Dubai `495edb45…`, Japan `a8c4ef90…`, Singapore `25c7b95b…`.
  `applications_submitted: 0`, `external_messages_sent: 0`. No employer was contacted.
- Tests: `career-ops/tests/test_regional_job_search.py` **32 passed**; whole `career-ops/tests/`
  **120 passed** (re-run in attempt 2 against the final uncommitted tree).

Recorded limitations (truthful): provider coverage is uneven and is stated per region — Singapore is
the only region with first-party providers in the install (MyCareersFuture, Glints SG,
Jobstreet/SEEK `SG-Main`); **no UAE- or Japan-specific provider exists**, so those lanes can only see
postings the global/remote boards happen to label with that location, and a thin Dubai/Japan scan means
"no provider for that region", never "no vacancies there". Live vacancy verification was **not**
performed in this run; results are pre-screen only. No application can be prepared for Dubai, Japan or
Singapore until the owner states a work-authorisation position for those regions.

Owner action recorded (does not block other lanes):
`tasks-or-issues/overnight-owner-actions-2026-09-24.md` item 6 (work-authorisation position for
Dubai/UAE, Japan and Singapore) and item 7 (whether to add a UAE/Japan-specific provider or keep the
agent-driven `search_queries` path).

Successor task: **none staged** — this task's remaining dependencies are owner decisions, not
engineering, and no equivalent regional task is pending. Staging another regional task would duplicate
this one.

## LinkedIn people/network layer: outreach drafts + Interview Prep Agent (2026-09-24T01:30Z)

Task `agent-linkedin-networking-interview-support-2026-09-23` (roster B19, B20, B21, B22).
Evidence: `audits/evidence/20260924T013000Z-linkedin-outreach-interview-prep/` —
`acceptance.json` + `acceptance.md`, **27/27 checks passed, 0 critical failures**.
Roster/worker detail is in `state/full_build_tracker.md` and `state/v1-agent-roster.md`.

Built on top of the existing B19 read-only intake and B20 profile/post drafts (evidenced by
`agent-cv-cover-letter-linkedin-workflows-2026-09-23`), this run adds:

- **B21 outreach drafting** — `linkedin_workflow.build_outreach_drafts()` produces unsent
  `networking`, `recruiter` and `hiring_manager` drafts. Each carries an explicit
  `unsent_state` (`sent`/`sent_at`/`recipient_selected`/`connection_request_created`/
  `message_queued`/`scheduled` all false or null, `attachments_sent: 0`,
  `owner_approval_required: true`) and a `provenance` block with the canonical source hashes
  and exact `cv.md:<line>` refs. The hiring-manager variant names the role and employer only
  from the resolved Career Ops record (`references_job`) and is **omitted** when no job
  context resolves.
- **B22 Interview Prep Agent** — `career-ops/interview_prep.py` (+
  `interview_prep_schema.json`) consumes a canonical JobBrief, an optional cited research
  file, and the canonical `cv.md` / `config/profile.yml` / `config/cv-facts.json` and emits
  technical preparation, behavioural preparation, a likely-question list, evidence-backed
  talking points and an unknown list. Every question is a deterministic template marked
  `employer_supplied: false` with its verbatim posting basis; every talking point quotes a
  canonical CV line verbatim; a requirement with no canonical evidence becomes an explicit
  owner action instead of a claim.

Defect found and fixed in this run: the first revision of the evidence matcher scored any
term overlap, so a mainframe-RACF requirement was reported `evidence_backed` off the word
"security" alone. `evidence_matching.general_terms` now strips domain words before scoring
and a qualification requirement is answered from the canonical qualification headings. The
defect was caught by an explicit test, and the fix is recorded in
`state/full_build_tracker.md`.

Not claimed: any live LinkedIn account access (none exists in this runtime; the live surface
stays owner-gated — owner decision recorded as item 13 in
`tasks-or-issues/overnight-owner-actions-2026-09-24.md`), any real interview, any
employer-supplied question, any live vacancy or company research (the acceptance fixtures are
labelled synthetic), and any external message or application.

## Whole-company local acceptance + morning handover (2026-09-24T03:57Z)

Task `agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`; authority
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`. Evidence:
`audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/` (34 step records with exact
commands/exit codes, 13 sub-artifacts, `roster_account.md/.json`), code SHA `31eecdb`.

- New deterministic driver (roster C01): `scripts/whole_company_acceptance.py`. It runs the **existing**
  verified surfaces (nothing re-implemented), records every real exit code, writes `results.json`
  incrementally, and fails closed: an unavailable/unparsable step is never a pass, and a broken
  evaluator is recorded as `unavailable` (that guard was added after attempt 1 of this run died on its
  own evaluator defect — preserved with a NOTE under
  `audits/evidence/2026-09-24T03-51-07Z-whole-company-acceptance-attempt1-partial/`).
- **Verdict PASS: 34 steps — 33 PASS, 0 FAIL, 1 owner-gated, 0 unavailable.** Owner-gated step is the
  presence-only credential probe (7/7 API worker credentials absent; owner action, not a defect).
- **Safety proven in-run:** `canonical_workbooks_unchanged: true` (SHA-256 of all four canonical
  workbooks identical before/after), 0 external mutations, 0 provider calls, Discord sync dry-run only,
  every write path exercised against copies/dry-runs.
- **Regression:** 21 suites / 579 collected / 579 passed / 0 failed / 0 errors / 0 unavailable, every
  suite exit 0 (`…/regression/evidence.json`). Baseline at the start of the sprint was 15 suites / 438
  tests.
- **E4/E5:** drill harness 36/36 checks, `real_provider_calls = 0`, `stub_dispatches = 10`,
  `evidence_kind = stubbed_provider_failure` (a stubbed failure is never presented as real provider
  evidence).
- **Operator surfaces:** health snapshot `ATTENTION` with `fail_count 0` / 2 attention items; Morning
  Chief Brief `verdict=ATTENTION`, active 2, blocked 12, owner actions 18, escalations 3.
- **Deployment:** preflight verdict **GO** (11 checks, 0 FAIL, 1 WARN = credentials absent);
  backup/restore/rollback drill **PASS** (10 artifacts); persistence read-only validation on 9 tasks
  (2 configured to survive a reboot; a reboot was not performed — prohibited by this contract).
- **Roster account (C02 input):** all **50/50** items accounted for — **47 PASS,
  3 READY_NEEDS_OWNER_CONFIG** (B12 live mailbox OAuth, B14 research provider, C03 cutover
  owner-gated), 0 BLOCKED_EXTERNAL, 0 unmapped, plus 10 supplementary owner-gated/external items.
  Detailed in `state/v1-agent-roster.md` § "Final account".
- **Morning handover produced:** `handovers/2026-09-24-morning-handover.md` — completed engineering,
  exact test/evidence counts, ordered afternoon owner steps, the post-key Stage 2 sequence, deployment
  prerequisites, rollback/no-go criteria, and the exact remaining blockers.
- **Not done, by contract:** local Stage 2 **NOT ENABLED**; no production dispatch; no provider call;
  no VPS cutover; no external publish/submit; no readiness, qualification or verification criterion
  weakened; the 0/7 credential gate was not re-staged (anti-loop directive).
- **Attempt-2 independent verification (2026-09-24T04:03Z):** attempt 1 of this task failed only in its
  response format (`execution_error`), so attempt 2 re-verified instead of rebuilding. The acceptance
  driver is byte-identical between `31eecdb` and `e9f5db8` and no code changed between them; the full
  regression was re-run from scratch at HEAD and reproduced **21/21 suites, 579/579 tests, 0 failed,
  0 unavailable, exit 0** (`audits/evidence/2026-09-24T04-03-58Z-regression-attempt2-verification-at-head/`).
  All 12 blocked queue records carry a `final_reconciliation_2026_09_24` disposition (10 superseded by
  verified successors, 2 parked as deterministic owner/external credential blockers). No new owner
  action; no credential, external, deployment or Stage 2 step executed.


Owner action required: **only the pre-existing owner items** — 7 provider credentials (item 1), the
post-key verification sequence (item 8), the work-authorisation answer, the deployment architecture /
VPS decision, the owner-attended laptop audit, reboot-persistence confirmation, the legacy task
disposition, and the optional decisions listed in the handover §5. No new owner dependency was created
by this task.

## Next non-blocked priority

1. **DONE 2026-09-24T01:44Z** — `agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23`
   (bounded 9-call repeat series through the real path; recurrence measured at **2 of 9** with
   `finishReason=IMAGE_RECITATION` on both; request-shape comparison; size-control probe). See
   § "Google image worker — bounded repeat series + request-protocol conformance" at the end of this
   file. The remaining item from it is the *unresolved trigger of the recitation stop*, which no
   bounded series can settle — recorded, not chased with unbounded generation.
2. **After Mukund configures the remaining provider credentials on 2026-09-24:** re-run the local
   Stage 2 readiness gate (`scripts/e3_stage2_readiness_gate.py` + `scripts/evidence_runner.py`) and,
   only if all three conditions hold (credentials confirmed configured; every readiness criterion
   satisfied; explicit owner authorization for that step), enable local Stage 2. The gate has already
   been re-run three times on 2026-09-23 (22:37Z, 22:41Z and 22:53Z) and returned NOT ENABLED every
   time (0/7 credentials); all three verdicts are recorded in the sections above. Owner action
   required first: configure the seven provider credentials.
3. Extend qualification evidence for the remaining roles/workers as real execution evidence arrives;
   the harness and the bar are now in place, so this is evidence collection, not new engineering.
4. E4 checkpoint/failover and E5 convergence/safe-mode drill evidence on real execution paths
   (**done at the stubbed-failure level** — see §E4/E5 real-path drill harness; the remaining item is
   a *live-provider* drill, which stays gated behind Stage 2 + the provider credentials and is
   recorded as an exact checklist in `tasks-or-issues/overnight-owner-actions-2026-09-24.md` §8).
5. Provider onboarding resumes immediately when owner-local credentials are supplied.
6. Local-first completion work (owner direction: prove local operation before any deployment
   architecture choice).

Do not fabricate qualification/provider evidence, and do not enable Stage 2 or choose a
deployment architecture without the readiness evidence and the owner decisions recorded in the
authority file.

## Career Daily Brief / Pipeline Prioritizer — B23 (2026-09-24, 07:00 daily)

The Career department's outputs are now summarisable in one morning read. `career-ops/daily_brief.py`
(+ `daily_brief_config.json`) is a **read-only aggregator**: it owns no career state, restates what
the canonical artifacts already say, and writes only `runtime/career-ops/daily-brief/` (git-ignored).

- **Evidence:** `audits/evidence/20260924T013238Z-career-daily-brief/` — **34/34 critical checks**,
  0 failures, code SHA `9b414f1` recorded in the artifact; canonical workbook SHA-256s identical
  before/after; `applications_submitted: 0`, `external_messages_sent: 0`, `canonical_workbook_writes: 0`.
  (Attempt 1's `…T033000Z-…`/`…T034000Z-…` runs, 32/32, are preserved as the record of the
  pre-amendment code — see `state/full_build_tracker.md` § "Attempt 2 amendment".)
- **Idempotency is quantized, not instant-based.** The as-of/window clock is floored to
  `window.quantize_minutes` (default 60; `0` disables), so two runs inside the same hour over
  unchanged artifacts are the *same* brief — same `brief_id` and digest — and the second writes no
  bytes; `generated_at` keeps the true run instant and stays out of the content digest. Crossing the
  quantum is a new brief. Verified on the real scheduled path (`run_scheduled_brief.cmd`, run twice:
  second run `wrote: []`, `idempotent: true`, identical `brief_id`).
- **Priority is a declared policy output, not a fact.** Five explicit inputs (deadline, application
  stage, eligibility certainty, freshness, owner flag) with declared weights; UNKNOWN inputs lower
  coverage instead of being imputed, and every item publishes its components and unknowns. The UK
  tracker has no deadline column, so deadline is UNKNOWN for every UK row — stated, not guessed.
- **Scheduled, not delivered:** `ChiefCareerBrief` runs daily at **07:00** (launcher
  `career-ops/run_scheduled_brief.cmd`; `install_schedules.py --install-brief/--remove-brief/--status`).
  `delivery.external_channel_health` is `not_verified` and `external_channels` is empty — nothing
  sends, posts or notifies, and no channel health is assumed.
- **Open owner decision (not blocking, item 14 in `tasks-or-issues/overnight-owner-actions-2026-09-24.md`):**
  keep the brief local-only, or name a channel to deliver it to. The delivery path will stay separate
  from the brief so a broken channel can never make the brief look unhealthy.

## Google image worker — bounded repeat series + request-protocol conformance (2026-09-24T01:44Z)

Task `agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23`, authority
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`. **Stage 2 was NOT enabled and no
production dispatch was enabled by this work.**

- **Evidence:** `audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/` (evidence.json,
  evidence.md, observations.json — the per-call record written as the series ran) and
  `audits/evidence/2026-09-24T01-46-56Z-e3-qualification-from-evidence/`.
- **Stated budget, honoured:** **9** real Google image generations, stated in the evidence artifact
  before the first call (6 identical IMAGE-only repeats, 2 `['TEXT','IMAGE']`, 1
  `['TEXT','IMAGE']+imageConfig`). 9 attempted / 9 recorded; no abort; no metadata call either, so
  the generation count equals the total. Every call ran the real deployed path
  (`ExecutionAdapterRegistry` → `GeminiImageExecutionAdapter` → `generateContent`) and persisted
  schema-v2 `dag_node`/`dag_state_event`/`performance_evidence` rows (google evidence rows 2 → 11).
  E2 telemetry went only through the public `governor.record_request()`; all 9 rows were read back
  from `governor.db` (`all_found: true`) — the two failures record `status=error`,
  `output_tokens=null` (never approximated).
- **Measured recurrence: 2 of 9** (rate 0.2222) — 2/6 on the IMAGE-only shape, 0/2 on `TEXT+IMAGE`,
  0/1 on `TEXT+IMAGE+imageConfig`. This is a measured rate over an executed series, nothing more.
- **New finding (protocol fact):** both recurrences carried a **provider-supplied
  `finishReason=IMAGE_RECITATION`** with an empty response part list, no candidate, and 17 prompt /
  **0** output tokens — the provider's own content-side stop reason for a withheld image, not an
  adapter/transport failure and not a modality-list rejection (the same IMAGE-only shape returned a
  decodable 1024×1024 JPEG on 4 of its 6 calls). The earlier 21:07Z failure recorded no
  `finish_reason`, so its identity with these is an inference from identical usage (17/0) and the
  identical request — not a recorded fact.
- **Still unknown:** what makes the recitation filter fire on some calls and not others for the
  identical prompt. The provider exposes the stop reason but not the filter input. Recorded as an
  open unknown; it was deliberately NOT chased with unbounded generation.
- **Image request shape — complete enough for this model, and now contract-declarable.** The
  adapter previously hard-coded `generationConfig.responseModalities=['IMAGE']`. It now accepts an
  optional contract-declared `response_modalities` and `image_config`, echoing both back on the
  result and in the sanitized dispatch metadata; the **production default shape is unchanged**.
  Measured: the provider accepted IMAGE-only and returned images; it also accepted
  `['TEXT','IMAGE']`; neither shape is rejected.
- **Output size — recorded as a protocol fact, never as a pass.** A size stated only in the prompt is
  **ignored** (objective asked 64×64; every IMAGE-only call returned 1024×1024). The provider's own
  parameter `generationConfig.imageConfig={imageSize:'512'}` was **accepted and changed the output to
  512×512**, so size is controllable through that supported parameter. A literal 64×64 is **not**
  achievable this way (it is a size class, not arbitrary pixels) and remains a **known limitation**.
  No verification contract was changed or weakened: the image node's deterministic contract is still
  "an image part arrived and decodes".
- **Qualification (evidence-driven, bar unchanged):** re-running
  `scripts/e3_qualification_from_evidence.py` moved **`google-nano-banana-2` / vision from EVALUATING
  to QUALIFIED** — 11 recorded executions, 8 verified passes, 8 first-pass passes, all six checks
  pass, `qualified_rows_without_evidence = 0`. **This must not be read as "always returns an image"**:
  the same series measured a 2/9 no-image rate, and the harness bar qualifies recorded dispatch
  repeatability under the declared deterministic contract, not image reliability.
- **Regressions:** full E1/E2/E3/E4/E5 + queue/bridge suite run via `scripts/evidence_runner.py`
  after the change (see `state/full_build_tracker.md` for the exact counts/SHA), plus a new offline
  suite `exec-brain/tests/test_e3_google_image_protocol.py` (18 tests) covering the declared request
  shape, the attempt/persistence path, the no-image-is-not-a-pass rule and the repeat-series
  accounting. Change deployed to the runtime root via `scripts/deploy_e3_runtime.py` (backup
  `exec-brain/backups/e3-deploy-20260924T014415Z`).

## Career Records: tracker writer (B08) + monthly rollover (B09) — 2026-09-24T02:04Z

Task `agent-career-ops-tracker-writer-and-monthly-rollover-2026-09-23` (authority
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`). Scope was limited to the tracker
interface and B09; the regional lanes and Company Watch were left to their own tasks.

**Current state of the Career Records capability (verified now, not assumed):**

- **B07/B08 deterministic interface — committed and green.** `career-ops/career_ops_cli.py` is the
  single Chief entry point (one JSON object per call: `inventory`, `verify`, `dedupe`, `write`,
  `rollover`, `run-health`, `summary`, `scan`, `ledger`). `career-ops/tracker_writer.py` is the
  openpyxl writer that replaced the unsupported `@oai/artifact-tool` dependency. Both were already
  committed at `70dd715`; nothing was reverted, re-written or duplicated.
- **B09 Monthly Tracker Rollover / archive worker — built and evidenced.**
  `career-ops/tracker_rollover.py` rotates one closed month per region into
  `uk-cyber-job-tracker.<YYYY-MM>.xlsx` / `<Region>_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx`.
  The archive is built from a copy of the canonical workbook, so its sheets, table, formulas, number
  formats and data validations are inherited, and every rotated cell — owner columns included — is
  copied verbatim. Because the archive name matches the region's archive glob, every rotated row
  feeds `build_cross_month_index`: re-adding a posting from a previous month is refused as
  `duplicate-cross-month` with 0 appends.
- **Safety, all proven on dated copies:** archive written and verified before the canonical is
  touched; hash-verified backup → temp write → re-open verification → concurrent-modification guard →
  atomic replace; refusal (with owner-action flag) when a row due to rotate carries owner-only
  column state, reporting row/column only and never the value; refusal on a pre-existing archive with
  different content unless `--force` (which backs it up first); `unchanged` on a byte-identical
  re-run; byte-identical restore from the backup. **All four canonical workbooks are SHA-256
  identical before and after the tests and the acceptance run** — nothing in this task wrote to them.
- **Real-data finding (the gate firing on live workbooks).** A read-only `rollover --month 2026-09`
  plan against the current canonical files reports owner-column conflicts that block rotation:
  **uk 26 rows (J×5 application status, K×21 priority), dubai 8 (R), singapore 4 (R), japan 0**.
  Those rows carry the owner's own application state, so rotation was correctly refused instead of
  deleting owner records. This is recorded as an **owner decision**, not a defect.
- **Department run-health (B08 + B09).** `career-ops/dept_run_health.py` writes
  `runtime/career-ops/run-health/tracker-writer.json` and `monthly-rollover.json` — last run, result,
  mode, row counts and the last run per region. `career_ops_cli.py run-health` reads them as one JSON
  object. The documents state `excel_is_source_of_truth: true` and
  `chief_state_role: "orchestration-only"` and are **aggregate only** (no company, title, URL or note
  ever lands there), so they are safe to commit; a test asserts that.
- **Rollover is deliberately not scheduled.** It is an explicit owner-invoked month-end step; the
  regional scans stay as they are. Adding a schedule later is a normal reversible
  `install_schedules.py` step once the rotation policy is settled.
- **Tests:** `career-ops/tests/test_tracker_rollover.py` (32 new tests) → whole `career-ops/tests/`
  suite **332 passed** (was 300). Acceptance: `career-ops/run_rollover_acceptance.py` exit 0,
  `ok: true` for uk/dubai/japan/singapore, evidence
  `audits/evidence/2026-09-24T02-04-31Z-career-ops-monthly-rollover/acceptance-20260924T020431Z.json`.
- **Registry updated:** the `mukund-company-registry` skill references now carry the interface
  (`integration_rules.md` §8), the corrected ownership map rows, the canonical ↔ archive naming
  (`resource_map.md`), the new `career_records_interface` resource (`company_registry.yaml`) and the
  rollover scheduling decision (`schedule_map.md`).

**Open owner decision:** whether to rotate the current month out of the live workbooks, and how to
treat the rows that hold owner application state. No rotation was applied to any canonical workbook.

## Company Watch integration — recovery pass (2026-09-24T02:27Z)

Task `agent-company-watch-recovery-final-pass-2026-09-24`, recovering the Company Watch record that
was claimed 2026-09-23T22:58:06Z and blocked 2026-09-23T23:18:06Z (`execution_error`, 1200 s
dispatch ceiling). Inspected first, rebuilt nothing: the integration had already landed on `main` in
`42a2bec` (the CV/cover-letter + LinkedIn task, which imports Company Watch for its dedupe).

- **Verified, not rebuilt.** `company-watch/` (`company_registry.py`, `ats_endpoints.py`,
  `company_watch.py` CLI, config, aggregate registry summary) is tracked; no partial local work was
  found or assumed. The watch list is still parsed from the owner's recorded history file
  (`uk_application_company_history_18_months.md`) with **zero** declared-vs-parsed mismatches, so the
  historical 203 employers / 18 recruiters / 221 evidenced organisations remain **historical
  re-derivations**, not freshly mailbox-verified numbers.
- **Gap found and closed:** the suite asserted the regional provenance *mapping* but never proved an
  end-to-end regional write. Four new offline tests now write a region-routed finding into a **copy**
  of the Dubai/Japan/Singapore tracker and assert provenance in `Source` (X), unchanged owner columns
  (R,S,T,U,V,Z), 0 appends on repeat, and an unchanged canonical hash — plus a refusal test that a
  Japan-routed finding is never handed to the UK tracker. `company-watch/tests/` **35 passed**
  (was 31).
- **Fresh bounded evidence:** `audits/evidence/2026-09-24T02-27-00Z-company-watch-recovery/`
  (23.2 s, 12 companies, 58 HTTP requests, `budget_exhausted: false`; 19 findings, 0 tracker-eligible
  under the owner's intern-only UK filter; acceptance write on a workbook copy 3 appended → repeat 3
  duplicates; canonical workbook SHA-256 unchanged). The original blocked run's evidence dir
  (`audits/evidence/2026-09-23T23-10-46Z-company-watch-integration/`) is now committed private-safe
  (aggregate files only; per-company findings/resolution stay git-ignored).
- **Still open, owned elsewhere:** the regional scan/schedule lanes; the blocked-record
  reconciliation itself (pending `agent-blocked-work-final-reconciliation-2026-09-24` owns it — the
  blocked JSON was deliberately left untouched because this task is its recorded prerequisite).
- **No external action:** read-only public ATS GETs only; no applications, messages, recruiter or
  company contact, account or LinkedIn mutation. Nothing was pushed to any tracker other than a copy;
  no canonical workbook was modified.

## Historical blocked-work final reconciliation (2026-09-24T02:45Z)

Task `agent-blocked-work-final-reconciliation-2026-09-24`. Authority:
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`. Code SHA at audit: `9bc20a7`.

Every one of the **12** records in `remote-queue/blocked/` was audited against current `main`, the
completed successor records, landed evidence under `audits/evidence/`, and the current pending/running
contracts, then classified. Each record stayed in `blocked/` as preserved historical evidence and
gained an additive `final_reconciliation_2026_09_24` note; a programmatic check confirmed all 12 edits
are strictly additive (parsed JSON at `HEAD` equals parsed JSON now once the added key is removed).

- **10 superseded / resolved** by verified successor evidence — **no rerun needed, none performed**:
  `agent-autonomous-nonblocked-continuation` (617e69cb/aae7d036 + deepseek-utf8 re-verification + later
  E3 tasks), `agent-career-ops-integration-and-tracker-automation` (company-registry audit + B09
  rollover task), `agent-company-watch-job-search-integration` (company-watch-recovery-final-pass),
  `agent-e3-integration-and-truth-reconciliation` (orphaned record, already reconciled),
  `agent-e3-local-production-rehearsal` and `-retry` (execution leg built/executed; rehearsal evidence
  consumed by the readiness gate rerun, sha256 `88212b70…`), `agent-live-queue-recovery` (Nous 429 —
  superseded after the DeepSeek switch), `agent-live-queue-recovery-deepseek` (bridge stream-decode
  failure; hardening `e643fd16`), and both `agent-queue-isolation-and-evidence-recovery*` records
  (deepseek-utf8 recovery + QuickEdit/two-retry hardening `85f604aa`).
- **2 deterministic owner/external blockers, parked**: both
  `agent-e3-stage2-readiness-gate-after-provider-keys-retry*` records. 0/7 provider credentials are
  configured, so Stage 2 remains NOT ENABLED and no same-family retry may be staged while that state
  is unchanged (authority anti-loop directive). Their duplicate retry chain is now closed.

Contract-required verifications, all CONFIRMED: (1) the queue-recovery/UTF-8/QuickEdit failure class is
superseded by the completed DeepSeek UTF-8 recovery and the QuickEdit + audited two-retry hardening;
(2) the E3 integration/rehearsal failures are superseded by the built production-execution leg, the
bounded Google image diagnosis + 9-call repeat series (2/9 `IMAGE_RECITATION`), and the readiness gate
rerun (12 suites / 364 tests / exit 0 at SHA `56d923b`) — **no live or expensive provider rehearsal was
repeated**; (3) the Career Ops broad timeout is closed by the committed interface (33 tests, encoding
fix live-confirmed through the real Task Scheduler path) and the B09 monthly rollover work
(career-ops suite 332 passing, canonical workbooks SHA-256 unchanged).

### Gaps found outside `blocked/` and closed

1. **High — a genuine agent task was silently swallowed.** `poller.handle_task` matched the substring
   `operational` before the `agent-` dispatch branch, so
   `agent-operational-brief-health-backup-persistence-2026-09-23` was claimed at 2026-09-24T01:38:05Z
   and immediately returned `handle_operational_build()`'s hardcoded `in_progress` status: no dispatch,
   no work, no terminal transition. A sweep of every queue id confirmed exactly one genuine agent task
   was affected. Fixed in `remote_queue/poller.py` (agent- dispatch now precedes all legacy placeholder
   routers; unknown non-agent objects still fail closed). New suite
   `remote_queue/tests/test_poller_routing.py` (9 tests, registered in `scripts/evidence_runner.py`).
   The swallowed task was restored to `pending/` with the **same task_id** — no duplicate retry chain.
2. **Medium — the E1 static gate failed on normal runtime debris.** The first evidence run reported E1
   31/32 because the deployed runtime root held `orchestration.db-shm` and a 0-byte
   `orchestration.db-wal` left by an earlier uncleanly-exited worker. `test_t13_no_gateway_modification`
   now accepts only the `-wal`/`-shm` sidecars of databases already on its allow-list; a negative proof
   (a deliberately unexpected file still fails the check) was recorded and the probe deleted. E1 then
   ran **32/32 exit 0**.

### Result

`0` unresolved non-owner recoverable blockers remain; `0` blocked records are left unreconciled.
Whole-company local acceptance (`agent-whole-company-local-acceptance-and-morning-handover-2026-09-23`,
pending) may proceed. Evidence:
`audits/evidence/2026-09-24T02-45-00Z-blocked-work-reconciliation-audit/` (`reconciliation.json`,
`reconciliation.md`) plus the test evidence from `scripts/evidence_runner.py --label
blocked-work-final-reconciliation-final` (17 suites, 465 collected / 465 passed, 0 failed, exit 0,
artifact `audits/evidence/2026-09-24T02-37-18Z-blocked-work-final-reconciliation-final/`).

Owner action required (unchanged dependencies only, no new ones): the seven provider credentials, the
Career Ops rollover-policy decision, and the pre-existing laptop/scheduled-task admin items.

---

## E3 provider content-side stop — truthful attribution + bounded same-request retry

`agent-e3-provider-content-stop-attribution-and-image-retry-policy-2026-09-24`, 2026-09-24, authority
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`. Evidence:
`audits/evidence/2026-09-24T02-59-00Z-e3-provider-content-stop-attribution/`.

The 2/9 `finishReason=IMAGE_RECITATION` outcome recorded in the 2026-09-24T01:44:32Z series is no
longer recorded as a node-level `verification_fail`. The E3 production execution leg now separates
three genuinely different causes, each from provider-returned data only:

| Cause | Attribution | Recovery |
|---|---|---|
| Provider content-side stop (provider `finishReason` withheld the content) | `provider_content_stop` | bounded identical same-request retry, then escalation |
| Transport/provider error (HTTP status, absent credential, raised exception, 200 with no image and no content-side stop reason) | `provider_error` | existing bounded repair budget, then FAILED |
| Delivered, well-formed output that fails its declared contract | `verification_fail` | existing bounded repair budget, then FAILED |

Verified facts (all offline; **0 real provider calls** — the recorded responses are used verbatim as
fixtures; the repeat series was not re-run):

- `DEFAULT_MAX_CONTENT_STOP_RETRIES = 2` (initial dispatch + 2 retries = at most 3 identical
  single-shot calls per node). The bound is the smallest that covers the recorded consecutive-stop
  cluster; it is stated as an inference from the recorded ordering, not a provider guarantee.
- The retry repeats the **identical** request (same objective, same contract-declared shape); it is
  never a reworded repair and never a shape change. The provider finish reason is recorded in the
  persisted DAG transition cause (`provider_content_stop_unrecovered:<finishReason>`), in
  `blocking_reason`, and in the evidence row.
- The unrecovered terminal path is **non-silent**: node `BLOCKED` with
  `failure_attribution=provider_content_stop` plus an E3 escalation
  (`trigger=provider_content_stop`) naming the finish reason and the owner decision. A content-side
  stop is never a pass and never silently a verification failure.
- Worker identity is never changed silently; equivalent-worker failover remains an explicit E4/owner
  decision.
- No unbounded retry path: the node loop carries a hard bound
  `1 + max_repair_attempts + max_content_stop_retries` with a defensive
  `attempt_budget_exhausted` BLOCKED guard. Stage-2 credential gate and deterministic owner/external
  blockers are untouched.
- Deterministic verification contract unchanged: only an independent verification PASS reaches
  `COMPLETE`.
- E4/E5 confirmed unchanged: no fabricated failover; `ConvergenceEnforcer` cap (warn → quarantine →
  stop) still applies and the truthful attribution is visible to repeated-failure convergence.

Tests: new offline suite `exec-brain/tests/test_e3_provider_content_stop.py` (25 tests, exit 0,
0 provider calls) registered in `scripts/evidence_runner.py`. Full regression
`scripts/evidence_runner.py --label regression-post-content-stop` → **19 suites / 19 passed / 0
failed / 0 unavailable / 507 tests collected / 507 passed / exit 0**
(`audits/evidence/2026-09-24T02-56-57Z-regression-post-content-stop/`), beating the 18-suite /
482-test baseline at `d9d1a7f`. E3 Stage 2 remains DISABLED; no production dispatch; no VPS cutover;
no readiness/qualification criterion changed. Owner action required: **none new** (unchanged
dependencies only).

---

## Content-side stop made operationally visible — operator surface, orchestrator boundary, rehearsal

`agent-e3-content-stop-operator-surface-and-rehearsal-integration-2026-09-24`, 2026-09-24T03:08Z–03:12Z
at code SHA `82ddf0081b1de0503d487f901d8bf294a3eaa223`, authority
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`. Evidence:
`audits/evidence/2026-09-24T03-08-34Z-e3-content-stop-operator-surface/`. **0 real provider calls** —
deterministic stub adapters on the real code path plus the response recorded by the predecessor task,
reused verbatim as a fixture.

The attribution described above was previously reachable only through the execution leg's run result
and its unit suite. It is now reachable where an operator actually looks, and the orchestrator boundary
carries it too:

- **Operator surface.** `e3-status` prints a DAG state breakdown plus a **Node Failure Attribution**
  section for every `BLOCKED`/`FAILED` node — state, `failure_attribution`, provider finish reason,
  content-stop retries and the terminal transition cause; `e3-trace` prints the same block for a plan's
  terminal nodes; `e3-why <node>` prints it for one node and still reports an unknown node as unknown.
  Read-only over already-persisted rows: no new schema, no E1/E2 write. Output is capped at 20
  attributed nodes (full count still printed) so a large historical store cannot flood the operator.
  Captured end to end (real execution leg, stub adapter, isolated db) in
  `operator_surface_output.txt`: `Failure attribution: provider_content_stop`, `Provider finish
  reason: IMAGE_RECITATION`, `Terminal transition cause:
  provider_content_stop_unrecovered:IMAGE_RECITATION`.
- **Orchestrator boundary.** `e3_shadow_orchestrator.orchestrate_and_execute` now returns
  `execution_escalations` (the execution leg's escalation records, verbatim) and a clearly attributed
  `content_stop_escalation` (`trigger=provider_content_stop`, `finish_reasons`, `node_ids`,
  `worker_ids`, `content_stop_retries`, `execution_escalation_ids`), `null` on a clean run. The
  existing `trigger=repeated_failure` escalation, the escalation-on-incomplete behaviour and the owner
  gate are unchanged — the change is additive.
- **Rehearsal driver.** `e3_execution_rehearsal.py` scenario `G_content_stop_terminal` (declared
  `stub_only`, so it can never spend a provider call) runs the recorded stop on the real code path and
  records the terminal path, the finish reason and the bounded retry accounting in its artifact:
  `execution_rehearsal_stub_report.json` (produced with stub adapters, isolated db) shows **23/23
  checks true**, 3 stub dispatches, `content_stop_retry_count = 2` against `content_stop_retry_budget
  = 2`, no 4th dispatch, node persisted `BLOCKED` with cause
  `provider_content_stop_unrecovered:IMAGE_RECITATION`, and the escalation
  `trigger=provider_content_stop` / `finish_reason=IMAGE_RECITATION`. The artifact states in-band that
  `provider_calls_actually_spent = 0`.

Tests: new offline suite `exec-brain/tests/test_e3_operator_surface.py` (13 tests, registered in
`scripts/evidence_runner.py`); `test_e3_shadow_orchestrator.py` 13 → 18 (`TestOrchestrateAndExecute
ContentStopEscalation`); `test_e3_execution_rehearsal.py` 22 → 26. Full regression, pre-deploy
`scripts/evidence_runner.py --label regression-post-content-stop-operator-surface` → **20 suites / 20
passed / 0 failed / 0 unavailable / 529 tests / exit 0**
(`audits/evidence/2026-09-24T03-08-19Z-regression-post-content-stop-operator-surface/`), and after
`scripts/deploy_e3_runtime.py` (2026-09-24T03:10:14Z; 4 modules copied, per-file SHA-256 verified
against the repo) the post-deploy re-run was identical: **20 / 20 / 529 / exit 0**
(`audits/evidence/2026-09-24T03-10-22Z-regression-post-content-stop-operator-surface-postdeploy/`), and
a final frozen re-run after the last test edit was identical again: **20 / 20 / 529 / exit 0**
(`audits/evidence/2026-09-24T03-13-53Z-regression-post-content-stop-operator-surface-final/`).
Baseline beaten: 19 suites / 507 tests at `8930572`. E3 Stage 2 remains **NOT ENABLED**; no production
dispatch; no VPS cutover; the 0/7 provider-credential gate was not re-run or re-opened; no readiness,
qualification or verification criterion changed; no unbounded retry path created. One successor is
staged in `remote-queue/pending/` (`agent-e4-provider-content-stop-pressure-visibility-2026-09-24`)
without duplicating or pre-empting the pending whole-company acceptance. Owner action required:
**none new** (unchanged dependencies only).

## E4 resource continuity — recorded provider content-side stop pressure — `agent-e4-provider-content-stop-pressure-visibility-2026-09-24`

Ran 2026-09-24T03:22:46Z–03:30:56Z at code SHA `03ebc74`. Evidence:
`audits/evidence/2026-09-24T03-22-46Z-e4-content-stop-pressure/` (`evidence.md`, `evidence.json`,
`operator_pressure_output.txt`, `deployed_surface_output.txt`, `deployed_hash_verification.txt`).
Provider-call budget: **0 (stated up front)** — stub adapters on the real execution path, isolated
dbs, and the recorded series artifact read verbatim; no provider series re-run.

- **Gap closed.** The E4 resource-continuity view measured only tokens, counts and a cost-derived
  time-to-exhaustion, so a provider that repeatedly withholds content while still consuming prompt
  tokens (`promptTokenCount: 17` on every recorded `IMAGE_RECITATION` call) was reported as *healthy
  capacity* even though the terminal attribution already existed.
- **New view.** `exec-brain/resource_monitor.py` gained `content_stop_pressure()`,
  `evidence_row_ledgers()` (read-only over the recorded `performance_evidence` rows),
  `recorded_series_ledger()` (reads an already-recorded series artifact verbatim),
  `render_content_stop_pressure()`, `build_content_stop_pressure_view()` and
  `ResourceMonitor.get_content_stop_pressure()`. Per worker/provider/model it reports attempts
  observed (classified and unclassified), content-side stops observed, the stop rate **with its
  sample size**, the last observed finishReason, the last recorded stop time and the bounded boolean
  `content_withheld_at_measurable_rate`, with status `unknown` / `clean` /
  `stops_recorded_below_bound` / `pressured`. Sources are never merged, so a recorded series and the
  store rows can never be conflated. No new store schema; no E1/E2 write (the view only SELECTs).
- **Bounded flag.** `MEASURABLE_CONTENT_STOP_RATE = 0.2` (just below the only recorded rate for this
  roster, 2/9 = 0.222) and `MEASURABLE_CONTENT_STOP_MIN_SAMPLE = 5` (the bounded per-node recovery
  path records at most 3 dispatch attempts for one node). Both bounds only bound the flag — the raw
  rate, sample size, finishReason and stop time are always reported; a group with no classified
  attempt reports `unknown`, never a rate and never "clear".
- **Operator surface.** `e3-status` now prints an `E4 Resource Continuity: provider content-side stop
  pressure` section; `e3-status --pressure-series <observations.json>` (repeatable) adds an
  already-recorded provider series as its own source. A missing E4 module degrades to an explicit
  "(unavailable … deploy it with scripts/deploy_e3_runtime.py)" line rather than breaking E3 status.
- **What it reports about the existing recorded state.** Read-only over a copy of the live store:
  `orchestration_store.performance_evidence` → 29 attempts observed, **0 classified** (codex-cli 5,
  deepseek-v41-flash 13, google-nano-banana-2 11) → status `unknown` for all three, because those rows
  were recorded before the content-stop classification existed. They are reported as **unknown, not
  healthy**. Supplying the recorded series artifact surfaces the recorded pressure for the google
  pair: 9 attempts / 2 stops → rate `0.222 (sample size 9)`, last finishReason `IMAGE_RECITATION`,
  `content_withheld_at_measurable_rate = yes`.
- **Observation only.** No automatic worker swap, re-dispatch, failover, retry or safe-mode entry;
  any failover or re-request remains an explicit E4/owner decision. The test
  `test_the_view_writes_nothing_and_acts_on_nothing` proves the table counts are unchanged after the
  view is built.
- **Tests.** New offline suite `exec-brain/tests/test_e4_content_stop_pressure.py` — **31 tests**,
  0 provider calls, registered in `scripts/evidence_runner.py`; covers a clean provider (no pressure),
  a provider whose recorded attempts include content-side stops (truthful rate + finishReason),
  repeated stops across nodes (flagged), zero attempts (`unknown`, never a fabricated rate),
  pre-classification rows (unclassified, never stop-free), the recorded artifact (read, SHA-256
  unchanged, never re-run) and the operator surface.
- **Regression.** Pre-deploy `scripts/evidence_runner.py --label regression-pre-content-stop-pressure`
  → **21 suites / 21 passed / 560 tests / 0 failed / 0 unavailable**
  (`audits/evidence/2026-09-24T03-23-28Z-regression-pre-content-stop-pressure/`). The first
  post-deploy run (`…2026-09-24T03-25-04Z-regression-post-content-stop-pressure-postdeploy/`) failed
  exactly one test — E1 `test_t13_no_gateway_modification`, because the runtime-root allow-list did
  not yet include the newly deployed `resource_monitor.py`; the allow-list was extended by exactly the
  deployed module (additive, with a negative proof: an unexpected probe file still fails the gate and
  the probe was deleted). Final post-deploy run
  `--label regression-post-content-stop-pressure-final-exitcheck` → **21 / 21 / 560 / 0 failed / 0
  unavailable, runner exit code 0 (captured)**
  (`audits/evidence/2026-09-24T03-29-37Z-regression-post-content-stop-pressure-final/`). Baseline
  beaten: 20 suites / 529 tests at `82ddf0`.
- **Deployment.** `scripts/deploy_e3_runtime.py` 2026-09-24T03:24:48Z copied `e3_commands.py`,
  `e3_cli.py` and `resource_monitor.py` (the E4 module was added to the deployed module set because the
  deployed `e3-status` imports it), backup `…\exec-brain\backups\e3-deploy-20260924T032448Z`; repo vs
  deployed SHA-256 `ALL_MATCH` (`e3_commands` `bcd12768…`, `e3_cli` `8c50a33c…`, `resource_monitor`
  `c138c0ec…`; unchanged `e3_execution` `6f625a0a…`, `e3_shadow_orchestrator` `808b092a…`,
  `e3_execution_rehearsal` `b482775f…`). The **deployed** module (runtime root import only) was run
  against the read-only store copy and printed the section, including the recorded series at
  `0.222 (sample size 9)` / `content withheld at a measurable rate: yes`.
- **Not done.** E3 Stage 2 **NOT ENABLED**; no production dispatch; no VPS cutover; the 0/7
  provider-credential gate was not run, re-parameterised or re-opened; no readiness, qualification or
  verification criterion weakened; no automatic failover/re-dispatch path created. Still open and
  deliberately not chased: what makes the recitation filter fire on some identical calls and not
  others. Owner action required: **none new** (unchanged dependencies only).

## E4 provider content-side stop pressure on the operator surfaces — `agent-e4-content-stop-pressure-operator-brief-integration-2026-09-24`

Ran 2026-09-24T03:36Z–03:44Z at code SHA `ed390db`. Evidence:
`audits/evidence/2026-09-24T03-40-43Z-e4-content-stop-pressure-operator-brief-final/`
(`integration_evidence.md`, `operator_surface_output.txt`, `health_snapshot.json/.md`,
`latest.json/.md` (Morning Chief Brief), `evidence.json/.md` (drill harness D7),
`regression/evidence.json`, `source_and_deployed_hashes.txt`, `deploy_dry_run.json`), plus the
pre-commit run `audits/evidence/2026-09-24T03-38-51Z-regression-operator-brief-pressure-integration/`
(21 suites / 579 tests / exit 0 at `13634b3` with the working-tree change).
Provider-call budget: **0 (stated up front)** — recorded rows/artifacts only, stubs and fixtures in
tests, no provider series re-run.

- **Gap closed.** The pressure view existed (`resource_monitor.py`) and printed through `e3-status`,
  but only if the owner ran `e3-status` by hand; the status surfaces the owner actually reads
  (operational-services health snapshot, Morning Chief Brief escalation list, E4/E5 drill artifact)
  did not carry it.
- **Operator surfaces.** `scripts/operational_services.py` gained `content_stop_pressure_status()`
  (reuses `resource_monitor.build_content_stop_pressure_view`; orchestration store opened `mode=ro`;
  the declared recorded series artifact `audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/observations.json`
  is consumed verbatim, overridable with the repeatable `--pressure-series`), `pressure_escalations()`
  and `render_pressure_lines()`. `build_health_snapshot` adds check `resource.content_stop_pressure`
  and a **warning**-grade escalation (`category provider_content_stop_pressure`) naming the
  provider/model, the stop rate, its sample size, the last finishReason and the bounded flag;
  `build_morning_brief` carries the same view inside `resource_status` next to the E2 resource status
  and both `render_*` print it. An unclassified/pre-classification sample reports `unknown` (never
  clear), a rate is never reported from zero attempts, and the pressure check never produces a FAIL
  and never changes a readiness/qualification gate.
- **First real operator output (live, read-only).** Health snapshot check = `ATTENTION`, one warning
  escalation: `google/gemini-3.1-flash-image [worker google-nano-banana-2] stop rate 0.222 at sample
  size 9 classified recorded dispatch attempts (bounds: rate >= 0.2 AND sample >= 5); last
  finishReason IMAGE_RECITATION`, labelled observation only. Store rows still report
  `unknown` (codex-cli 5 / deepseek-v41-flash 13 / google-nano-banana-2 11 attempts, 0 classified →
  29 attempts observed, 0 classified) — unknown, not clear. Verdict `ATTENTION` with `fail_count 0`.
- **Drill harness.** `exec-brain/e4e5_drill_harness.py` gained `D7_content_stop_pressure_observation`:
  the same read-only view recorded over the harness's isolated drill store (like the
  continuity/outage/convergence drills) with `store_rows_written_by_observation = 0` (via
  `Connection.total_changes` before/after), `provider_calls_spent = 0`, unchanged
  `performance_evidence` row counts, and operator lines; **36/36 checks pass**, 0 real provider calls
  (was 33 checks). The drill store's rows classify clean, so D7 raises no warning — the clean case.
- **Tests.** +10 tests in `scripts/tests/test_operational_services.py` (17 → 27) and +9 in
  `exec-brain/tests/test_e4e5_drills.py` (38 → 47), all offline (stub adapters, hand-written
  fixtures, disposable stores): clean provider raises no warning; pre-classification store reports
  UNKNOWN, not clear; zero attempts never yield a fabricated rate; a crossing recorded rate is a
  warning-grade observation with its rate/sample/finishReason/bounded flag; snapshot escalation list
  and markdown; Morning Chief Brief carry + render; the view never writes the store (file hash and
  sidecar checks); absent/undeclared store → UNKNOWN; the declared recorded series is consumed by
  default; an unreadable series artifact is recorded as a source error, never fabricated.
- **Regression.** Post-commit `scripts/evidence_runner.py --label e4-operator-pressure-integration-final`
  → **21 suites / 21 passed / 0 failed / 0 unavailable / 579 tests collected / 579 passed, runner exit
  code 0** (`audits/evidence/2026-09-24T03-40-43Z-e4-content-stop-pressure-operator-brief-final/regression/`).
  No suite lost tests; only this task's own suites grew. Baseline was 21 suites / 560 tests at
  `03ebc74` (20 / 529 at `82ddf0`). Final frozen re-run after the evidence/state commit `7580a30`
  (`--label e4-operator-pressure-integration-final-exitcheck`) → **21 / 21 / 579 / 579, runner exit
  code 0** (`…-operator-brief-final/regression-final-exitcheck/`).
- **Deployment.** None required and none performed: only `scripts/` and the repo-only drill harness
  changed, and `exec-brain/resource_monitor.py` is byte-identical to the deployed runtime copy
  (`c138c0ec…`), so `python scripts/deploy_e3_runtime.py --dry-run` → `copied: []`, exit 0. No runtime
  module, no E1/E2 file, no store schema changed; no E1 runtime-root allow-list change was needed.
- **Not done.** E3 Stage 2 **NOT ENABLED**; no production dispatch; no VPS cutover; the 0/7
  provider-credential gate was not run, re-parameterised or re-opened; no automatic worker swap,
  re-dispatch, failover, retry or safe-mode entry (observation only); no readiness, qualification or
  verification criterion weakened. Still open and deliberately not chased: what makes the recitation
  filter fire on some identical calls and not others. Owner action required: **none new** (the
  pressure warning is informational; any failover stays an explicit E4/owner decision).

## Career high-recall semantic discovery — B25 (2026-09-24, `agent-career-high-recall-semantic-discovery-2026-09-24`)

**Status: BUILT / TESTED / EVIDENCED. Discovery policy default changed in the control plane only.**

- **Change.** Job discovery no longer treats the owner's `portals.yml` title filter
  (`positive = [Intern, Internship]`) as a required gate. New control-plane overlay
  `career-ops/discovery/` implements: broad collection (existing Career Ops scan lane
  + Company Watch) → light deterministic two-tier title prefilter → DeepSeek bulk
  semantic triage → bounded Codex second pass (ambiguous/high-value only) →
  deterministic eligibility/visa/clearance gates → shared dedupe → tracker
  **manifest** / Daily Brief handoff. `--apply` remains the only tracker write.
- **Two-tier policy.** `high_recall` is the default; Tier A accepts a title only with
  both an early-career level signal and a cyber/IT-security/technology-risk discipline
  signal (graduate, junior, analyst/analyst I, L1, SOC, information security, GRC, IAM,
  vulnerability, technology risk, security consulting, IT support …), and rejects
  explicit non-cyber or senior signals. Tier B keeps the owner's negative list verbatim
  (`Senior`, `Principal`, `Lead `, `Manager`, `Director`, `Head of`, `Vice President`,
  `VP `, `Staff Security`) plus a listed addition set. The original strict rule is
  preserved unchanged as `intern_only`, an available narrow mode — not the default.
- **Truth boundary.** Title matching is a prefilter, never the eligibility decision; the
  authoritative gates run after semantic classification and cannot be overridden by a
  model. A model label is evidence about a posting, never a fact about Mukund. Where no
  JD text exists, the record states `jd_available=false` /
  `classification_basis=title_company_location_only` and is explicitly not JD analysis;
  a deterministic guard rejects any classification that asserts a year count, quote or
  fact-class claim (years/sponsorship/clearance/citizenship/degree/visa/salary) absent
  from the source record.
- **Measured evidence (bounded live pass, same 506-candidate captured set).**
  `intern_only`: title pass 3 → **0** tracker candidates. `high_recall`: title pass 15 →
  **4** tracker candidates (**+12 titles / +4 candidates, 0 lost**). Live funnel run:
  `discovered_raw=60`, `after_hard_negative_prefilter=6`, `semantically_reviewed=6`,
  `deepseek_accept=1`, `codex_escalated=3`, `codex_accept=0`,
  `deterministic_eligibility_pass=0`, `tracker_candidates=0`, with the first zero stage
  and its cause recorded. DeepSeek called twice (bulk); Codex once (budget 4).
- **Recorded limitations (not hidden).** (1) The Career Ops scan exposes no JD text or
  posting URL for offers, so semantic labels from that source are title/company/location
  based and explicitly not JD analysis; the contract and fallback path exist so nothing
  is guessed. (2) A live DeepSeek reasoning response can spend its whole completion
  budget and return empty content — the bulk classifier uses an 8192-token budget and a
  one-time half-split retry, and records an empty response as a provider failure rather
  than a zero.
- **Funnel attribution.** Counters `discovered_raw`, `after_hard_negative_prefilter`,
  `semantically_reviewed`, `deepseek_accept`, `codex_escalated`, `codex_accept`,
  `deterministic_eligibility_pass`, `duplicates_removed`, `tracker_candidates`, plus
  `rejections_by_reason`, `not_applicable_stages` (a config-disabled stage is not a zero)
  and `zero_attribution` naming the first empty stage. Company Watch exclusions carry
  their own reasons (`duplicate-in-run`, `routed_other_region:<r>`), so 19 findings can
  no longer silently become "0 jobs".
- **Brief integration.** `collect_discovery_funnel` in `career-ops/daily_brief.py` adds
  aggregate funnel counts, the zero attribution and top accepted semantic candidates,
  labelled as a deterministic **policy output**, not a factual claim about a vacancy; a
  missing run is UNKNOWN, never "no jobs".
- **Safety.** No canonical workbook written during engineering acceptance (four
  workbooks hash-identical before/after), no application, no outreach, no employer or
  recruiter contact, no browser/GUI automation, no account mutation. The owner's external
  Career Ops install was inspected read-only and not modified.
- **Tests.** `career-ops/tests/test_discovery_pipeline.py` 36 passed;
  `career-ops/tests/test_daily_brief.py` 28 passed; `career-ops/tests` 374 passed;
  `career-ops/tests + scripts/tests` 401 passed;
  `python career-ops/run_discovery_acceptance.py` **14/14 checks PASS** (now a step in
  `scripts/whole_company_acceptance.py`, roster B25).
- **Evidence.** `audits/evidence/2026-09-24T04-58-25Z-career-high-recall-discovery/`
  (`evidence.md`, `summary.json` — aggregate, committed) and
  `audits/evidence/20260924T050730Z-career-high-recall-discovery-acceptance/`
  (fixtures-only acceptance). Raw per-posting funnel artifacts stay in the git-ignored
  `runtime/career-ops/discovery/` tree because they name real postings.
- **Owner action.** None new. Enabling the pipeline on the live schedule (rather than on
  demand) is an owner decision and has **not** been made.

## Unified job-discovery surfaces — B11 + B19 successor (2026-09-24, `agent-career-unified-discovery-surfaces-followup-2026-09-24`)

**Status: BUILT / TESTED / EVIDENCED. The running high-recall contract was extended, not forked; no gate weakened.**

- **Change.** Every read-only discovery surface now runs the *same* funnel. Added to
  `career-ops/discovery/pipeline.py`: `SOURCE_REGISTRY` (explicit records, regional
  scan record, Company Watch, recruiter/intermediary watch, LinkedIn export),
  `collect_from_recruiter_watch()` (B11), `collect_from_linkedin()` (B19) and
  `collapse_candidates()` (cross-source canonical identity). No second classifier, no
  second eligibility rule set, no second dedupe engine.
- **B11 Recruiter / intermediary Watch.** A declared read-only findings export
  (intermediary/agency, employer, title, location, URL, `decision`, `region_route`,
  attribution confidence) normalises into the common candidate schema. Findings the watch
  itself excluded stay attributable (`recruiter_watch_decision:duplicate`,
  `routed_other_region:dubai`) instead of becoming a silent zero. No agency or employer is
  contacted, and **no live recruiter-watch feed was scanned** — the collector reads a
  declared export shape and records that boundary.
- **B19 LinkedIn job discovery.** An owner-exported local file is read through the
  *existing* `linkedin_workflow.parse_inbox_file` + `classify` path, so there is exactly one
  LinkedIn export parser. Only `job_signal`s become candidates; company-only signals and
  URL-less lines are reported in coverage and never guessed into postings. No login, API,
  session, scrape, browser, post, message, connection request or application exists in this
  path.
- **One vacancy → one canonical candidate.** Canonical identity is the normalised posting
  URL (`tracker_writer.normalize_url`, the same code the tracker dedupe uses, which now also
  drops any `utm_*` parameter) or, when no URL exists, company + title. The richest copy
  wins, missing fields are filled from the other copies, nothing is invented, and each
  discovery is preserved in the candidate's `provenance` (collection surface, declared
  source, source detail, raw index) with `sources` + `duplicate_discoveries`. Fixture proof:
  `discovered_raw=6` → `canonical_candidates=4` → `cross_source_duplicates_removed=2`, with
  one canonical candidate carrying all three surfaces' provenance.
- **Per-source attribution.** `funnel.by_source[source]` gives each surface its own stage
  counts, its own `rejections_by_reason`, its own `not_applicable_stages` and its own
  `zero_attribution` naming the first empty stage and cause; a shared canonical candidate is
  counted in each source that discovered it and the overlap is recorded explicitly. The run
  also reports `cross_source_dedupe` and `canonical_candidates`, and the summary line lists
  per-source zeroes.
- **Truth boundary.** Collapse is in-run identity only and never replaces the shared
  tracker dedupe; a de-duplication is reported as a de-duplication, never as a market fact.
  The read-only rule is declared in `source_contract` and asserted by tests: no login, no
  account/session, no scraping, no browser/GUI, no posting/messaging/application.
- **Tests.** New `career-ops/tests/test_unified_discovery_sources.py` **24 passed**;
  `test_discovery_pipeline.py` 36 passed; `test_tracker_writer.py` +1 (`utm_*`);
  `career-ops/tests + company-watch/tests + scripts/tests` **461 passed**.
  `career-ops/run_discovery_acceptance.py` **22/22 checks PASS** (was 14/14); the registered
  whole-company step `career_high_recall_discovery` re-runs PASS at HEAD.
- **Safety.** The four canonical workbooks are SHA-256 identical before/after the acceptance
  run and across the full 461-test suite; 0 applications, 0 employer/agency/intermediary
  contacts, no browser/GUI, no account/session, no scraping, no LinkedIn action. The
  successor did not modify the running prerequisite contract's classifier or contract.
- **Owner action.** None new. The live LinkedIn surface stays owner-gated and untested
  against a real account, and no live recruiter/intermediary watch producer exists yet.
- **Evidence.** `audits/evidence/20260924T053909Z-career-high-recall-discovery-acceptance/`
  (fixtures-only acceptance, 22/22 checks) and
  `audits/evidence/2026-09-24T05-29-54Z-unified-discovery-followup-step-verification/`
  (registered whole-company step `career_high_recall_discovery` re-run at HEAD → PASS).
  Attempt-2 resume re-verified the same at HEAD `3c8082b` without changing code:
  `audits/evidence/20260924T054055Z-career-high-recall-discovery-acceptance/` (22/22 PASS) and
  `audits/evidence/2026-09-24T05-43-11Z-whole-company-acceptance/` (step PASS,
  `canonical_workbooks_unchanged: true`); 461 tests passed; workbooks re-hashed unchanged.

## Career open-web research lane — B26 (2026-09-24, `agent-career-codex-style-open-web-job-research-2026-09-24`)

**Status: BUILT / TESTED / EVIDENCED. Read-only, dry-run. No external action, no gate weakened.**

- **What changed.** `career-ops/discovery/web_research.py` adds the owner's successful Codex
  behaviour back as ONE more read-only discovery surface in the same unified funnel: an actively
  *generated* query matrix (role families × configured regions × surfaces, the owner's `site:` ATS
  shapes preserved verbatim, optional company-watchlist hook) is executed by a research worker
  (`codex-web-search` / `captured` / `none`), every result is normalised into the one candidate
  schema with full provenance, and destinations are validated with a polite robots-respecting
  read-only HTTP retrieval. `pipeline.SOURCE_WEB_RESEARCH` = `collect_from_web_research()`.
- **Codex capability, tested.** `codex-cli 0.155.0-alpha.16.3` (resolved from the installed Codex
  bin root) performs real `web_search` calls under `codex exec --json`; a result is accepted only
  when the execution stream contains a `web_search` item for that query, so a memory recall can
  never be recorded as a search. When the CLI is absent the provider says so and contributes zero.
  The `exec --search` flag is not accepted by this build; the native tool needs no flag.
- **Bounded live pass (real).** Final pass at HEAD: 3 queries → 10 results seen → 9 candidate URLs → 2 validated live, 7 failed validation, 7 refused as listing pages; an earlier pass in the same session reached 15 results / 13 candidate URLs. Source classes genuinely reached: `linkedin_jobs`, `indeed`, `employer_careers`. First, failed live attempts (0 results) were recorded as FAIL and kept as history rather than overwritten.
- **New guard from that live data.** Broad search returns the boards' own search pages as readily as postings: 11 of the 13 real URLs from one bounded pass were LinkedIn `/jobs/<keywords>`, Indeed `/q-…` or Reed `…-jobs-in-<place>` listing pages, and before this work 7 of them passed the deterministic gates as tracker candidates. Every URL is now classified from the URL alone
  (`classify_result_kind` → `job_posting` / `search_listing` / `unknown`) and the source-agnostic
  deterministic gate refuses `search_listing`; at HEAD **0** of those 13 could reach a tracker
  candidate (the 2 posting-shaped URLs that did surface failed liveness validation and are refused
  as well). Legacy exports without a declared kind are counted, never guessed.
- **Tests.** `career-ops/tests/test_web_research.py` **72 passed** (55 at first landing);
  `career-ops/tests` **471 passed**. Acceptance runner `career-ops/run_web_research_acceptance.py`
  **21/21** checks fixtures-only and **24/24** with the bounded live pass.
- **Safety.** 0 applications, 0 outreach, 0 employer/recruiter contacts, no login/account,
  no cookie/session, no CAPTCHA bypass, no browser or GUI automation, no scraping behind auth, no
  LinkedIn action. The four canonical workbooks are SHA-256 identical before and after every
  acceptance run; the handoff is a candidate manifest and `--apply` remains the only tracker write.
- **Owner action.** None new. The live research lane stays dry-run/read-only; enabling canonical
  writes or a schedule remains an owner decision. A company watchlist file is optional.
- **Evidence.** `audits/evidence/*-career-open-web-research/` (aggregate only; raw result URLs stay
  under the git-ignored `runtime/career-ops/web-research/`).

## Career owner-company priority watchlist lane — B27 (2026-09-24, `agent-career-priority-company-watchlist-engine-2026-09-24`)

**Status: BUILT / TESTED / EVIDENCED. Read-only, dry-run. No external action, no gate weakened.**

- **What changed.** `career-ops/discovery/watchlist.py` adds the owner's own company short list as ONE
  more read-only discovery surface in the same unified funnel. A plain list of company names (or an
  empty list / a missing file — both explicitly valid) is resolved to deterministic company
  identities, an official careers/ATS surface, and two query families; findings are flagged
  `priority_watchlist` and routed through the SAME prefilter/semantic/eligibility/dedupe.
  `pipeline.SOURCE_PRIORITY_WATCHLIST` = `collect_from_priority_watchlist()`. It is **additive** to
  broad-market discovery, never a replacement.
- **Identity.** Duplicate spellings collapse on exactly three recorded bases (`exact_normalised_name`,
  `legal_form_suffix`, `declared_alias`); distinct companies never merge — no prefix/shared-word/
  similarity rule exists, because merging two distinct companies would attribute one company's
  vacancies to another.
- **Careers / ATS, discovered and verified.** Owner-supplied URL validated by a polite
  robots-respecting retrieval; public structured boards probed with Company Watch's own
  `ats_endpoints.py` (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) and trusted only on name
  confirmation; Workday, Teamtailor, iCIMS, BambooHR, Breezy, Jobvite, Recruitee and the
  region-specific HRMOS/Jobcan surface resolved only when the research lane actually discovers the
  URL. **A company whose careers infrastructure is unreachable or unattributable is labelled
  `unavailable`/`unknown` with the blocking reason — never "no jobs".**
- **Two query families per company.** `official_careers_ats` and `company_role_family_research` are
  always both generated; a query budget is split so it can never drop a whole family.
- **Funnel + brief.** The flag makes a finding prominent in the brief and never bypasses a gate; a
  vacancy found by Company Watch AND the watchlist collapses to one canonical candidate carrying both
  provenances. The brief reports the watchlist as its own section, in the funnel's canonical order and
  independent of the global priority ranking, so a watchlist vacancy stays visible even when it is not
  top-ranked (and even when it did not reach the gates).
- **Tests.** `career-ops/tests/test_watchlist.py` **36 passed** (new); `career-ops/tests/test_daily_brief.py`
  **33 passed** (+5 watchlist-section tests); `career-ops/tests` **512 passed**. Acceptance runner
  `career-ops/run_watchlist_acceptance.py` **32/32** checks fixtures-only, covering the six named
  acceptance fixtures (aliases, ATS discovery, no careers page, resolved surface with zero matching
  roles, Company Watch + watchlist duplicate, watchlist vacancy not top-ranked).
- **Safety.** 0 applications, 0 outreach, 0 employer/recruiter contacts, no login/account, no
  cookie/session, no CAPTCHA bypass, no browser or GUI automation, no scraping behind auth. The four
  canonical workbooks are SHA-256 identical before and after every acceptance run; the handoff is a
  read-only manifest and `--apply` remains the only tracker write.
- **Owner action.** None yet. When ready, supply the company list by copying
  `career-ops/watchlist/company-watchlist.example.json` to the git-ignored
  `runtime/career-ops/watchlist/company-watchlist.json` and adding names — a data edit, not an
  engineering project.
- **Evidence.** `audits/evidence/<stamp>-career-priority-watchlist/` (aggregate only; the owner's
  company list and discovered careers/vacancy URLs stay under the git-ignored
  `runtime/career-ops/watchlist/`).
