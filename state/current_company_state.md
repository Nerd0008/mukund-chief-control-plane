# Current Company State

- Timestamp: 2026-09-23T22:44:00Z
- Latest evidence run: 2026-09-23T22:41:57Z — E3 Stage 2 readiness gate re-run (credential-triggered
  continuation, task `agent-e3-stage2-readiness-gate-after-provider-keys-2026-09-24`)
  (`audits/evidence/2026-09-23T22-41-57Z-e3-stage2-readiness-gate-verdict/`, 0 provider calls) and
  its regression input (`audits/evidence/2026-09-23T22-40-55Z-e3-stage2-readiness-gate-rerun/`,
  code SHA `88af27a`). Previous run: 2026-09-23T22:37:29Z at code SHA `56d923b`.
- Evidence files (this run):
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
- Recorded, deliberately unfixed defect: `poller.handle_task` routes any task id containing
  "operational" to `handle_operational_build()`, which returns a hardcoded status with no
  execution evidence. It must not be read as evidence of executed work.
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

## Current blockers / owner dependencies

- E3 Stage 2 local enablement: **blocked — gate re-run 2026-09-23T22:41Z (credential-triggered):
  Stage 2 NOT ENABLED.**
  The readiness gate now runs deterministically (`scripts/e3_stage2_readiness_gate.py`); the only
  unmet readiness criterion is the Google image worker's intermittency, and the blocking conditions
  are (a) 0/7 provider credentials configured and (c) owner authorization that is conditional on
  those credentials being configured.
- Google image worker real dispatch: **intermittent** — the identical request failed once (no image
  part) and succeeded on the bounded re-dispatch. The trigger is unknown; a bounded repeat series is
  required. Engineering, not owner action.
- Seven provider credentials / account readiness steps remain owner/provider dependent —
  **confirmed 0/7 configured as of 2026-09-23T22:36Z** (presence-only probe; never via
  GitHub/queue/logs)
- Deployment architecture: intentionally deferred by owner until local operation is proven. The
  authority records laptop-primary + GitHub control plane + VPS watchdog/failover as the current
  owner *preference*, explicitly not a final decision and not authorization for VPS cutover.
- VPS access/details required before any real deployment/cutover; cutover is not authorized

## Next non-blocked priority

1. The successor staged by this run —
   `agent-e3-google-image-intermittency-and-protocol-conformance-2026-09-23` (pending): a bounded
   repeat series to measure how often the no-image response recurs, a controlled comparison of the
   image request shape, and the truth about whether a requested image size can be honoured. Then
   re-run the evidence-backed qualification for the vision role.
2. **After Mukund configures the remaining provider credentials on 2026-09-24:** re-run the local
   Stage 2 readiness gate (`scripts/e3_stage2_readiness_gate.py` + `scripts/evidence_runner.py`) and,
   only if all three conditions hold (credentials confirmed configured; every readiness criterion
   satisfied; explicit owner authorization for that step), enable local Stage 2. The gate was already
   re-run twice on 2026-09-23 (22:37Z and 22:41Z) and returned NOT ENABLED both times (0/7
   credentials); both verdicts are recorded in the sections above. Owner action required first:
   configure the seven provider credentials.
3. Extend qualification evidence for the remaining roles/workers as real execution evidence arrives;
   the harness and the bar are now in place, so this is evidence collection, not new engineering.
4. E4 checkpoint/failover and E5 convergence/safe-mode drill evidence on real execution paths
   (currently gated: the contract only asks for these if Stage 2 is enabled, which it is not).
5. Provider onboarding resumes immediately when owner-local credentials are supplied.
6. Local-first completion work (owner direction: prove local operation before any deployment
   architecture choice).

Do not fabricate qualification/provider evidence, and do not enable Stage 2 or choose a
deployment architecture without the readiness evidence and the owner decisions recorded in the
authority file.
