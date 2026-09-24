# E4 recorded provider content-side stop pressure → operator surfaces (evidence)

- Task: `agent-e4-content-stop-pressure-operator-brief-integration-2026-09-24`
- Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
- Code SHA at run: `ed390db` (this task's change commit)
- Evidence dir: `audits/evidence/2026-09-24T03-40-43Z-e4-content-stop-pressure-operator-brief-final/`
- Evidence kind: **recorded/offline** — 0 real provider calls, stubs and recorded
  artifacts only, no store schema change, no E1/E2 write, no deployment of a new
  runtime module, observation only (no automatic swap/re-dispatch/failover/retry/
  safe-mode entry).

(`evidence.md` / `evidence.json` in this directory are the drill harness's own
artifact; this file is the task-level summary.)

## What changed

| File | sha256 | Role |
|---|---|---|
| `scripts/operational_services.py` | `3c5b0189f227ac60e8067fece2b9d1e9d1194c643026a1d46198c231052145ca` | `content_stop_pressure_status()`, `pressure_escalations()`, `render_pressure_lines()`; `build_health_snapshot` check + warning escalation; `build_morning_brief` resource-status entry + rendering; repeatable `--pressure-series` |
| `exec-brain/e4e5_drill_harness.py` | `c4a9059cfe4f94014670b766ceec295b709aea0dc8c62af0b04cf9a99606f4b8` | D7 read-only pressure observation over the isolated drill store + 3 checks |
| `scripts/tests/test_operational_services.py` | (committed) | +10 offline operator-surface tests |
| `exec-brain/tests/test_e4e5_drills.py` | (committed) | +9 offline drill-harness tests |

Unchanged (proves the E4 view itself was not touched/re-parameterised):

- `exec-brain/resource_monitor.py` = `c138c0ecdce5011c8bc889a429cbf6cd5917311f778fe5b6f8148616f29e2688`,
  identical to the deployed runtime copy → **no runtime module changed, nothing to deploy**
  (`scripts/deploy_e3_runtime.py --dry-run` → `copied: []`, exit 0, see `deploy_dry_run.json`).
  Bounds stay `MEASURABLE_CONTENT_STOP_RATE = 0.2`, `MEASURABLE_CONTENT_STOP_MIN_SAMPLE = 5`.

## Exact commands and results

1. Full regression (E1/E2/E3/E4/E5 + queue + bridge), after the change commit:

   `python scripts/evidence_runner.py --label e4-operator-pressure-integration-final --out-dir audits/evidence/2026-09-24T03-40-43Z-e4-content-stop-pressure-operator-brief-final/regression`

   → exit `0`; **21 suites / 21 passed / 0 failed / 0 unavailable / 579 tests collected / 579 passed**
   (`regression/evidence.json`, `regression/evidence.md`).
   Pre-change baseline at `82ddf0`: 20 suites / 529 tests; previous task's baseline
   `03ebc74`: 21 suites / 560 tests. Per-suite comparison: no suite lost tests; the
   only increases are this task's own suites (`test_operational_services.py` 17 → 27,
   `test_e4e5_drills.py` 38 → 47). A pre-commit run of the same suites at `13634b3`
   with these working-tree changes is kept at
   `audits/evidence/2026-09-24T03-38-51Z-regression-operator-brief-pressure-integration/`
   (same 21/579/exit 0).

2. Operator surfaces (live, read-only; evidence written to this directory only):

   - `python scripts/operational_services.py health-snapshot --no-tasks --out-dir <evidence dir>` → exit `0`
   - `python scripts/operational_services.py morning-brief --no-tasks --out-dir <evidence dir>` → exit `0`
   - `python exec-brain/e4e5_drill_harness.py --out-dir <evidence dir> --json` → exit `0`
   - `python scripts/deploy_e3_runtime.py --dry-run` → exit `0`, `copied: []`

   Raw output: `operator_surface_output.txt`; snapshots `health_snapshot.json/.md`,
   brief `latest.json/.md`, drill `evidence.json/.md`.

## Observed facts (recorded evidence only, verbatim from the runs)

- Health snapshot check `resource.content_stop_pressure` = **ATTENTION**, and the
  escalation list carries exactly one **warning**-grade item, category
  `provider_content_stop_pressure`:
  `google/gemini-3.1-flash-image [worker google-nano-banana-2] stop rate 0.222 at
  sample size 9 classified recorded dispatch attempts (bounds: rate >= 0.2 AND
  sample >= 5); last finishReason IMAGE_RECITATION` — explicitly labelled
  observation only, any action an explicit E4/owner decision.
- Morning Chief Brief: the same view next to the E2 Daily Resource Brief line under
  "Resource status", and the same warning item in "Failure escalation".
- Unclassified store rows (no content-stop ledger recorded) are reported as
  `unknown` with `content withheld at a measurable rate: unknown` and
  `stop rate: unknown (sample size 0 — no classified attempt recorded; no rate is
  reported from zero attempts)` — never as clear: `codex-cli` 5 attempts / 0
  classified, `deepseek-v41-flash` 13 / 0, `google-nano-banana-2` 11 / 0
  (29 attempts observed on the store, 0 classified).
- Recorded series source `recorded_provider_series:e3-google-image-repeat-series`
  reports 9 attempts / 9 classified / 2 content-side stops → rate **0.222**,
  finishReason `IMAGE_RECITATION`, last stop recorded at `2026-09-24T01:44:32+00:00`
  (consumed from the already-recorded artifact; the series was **not** re-run).
- Drill harness D7 over its isolated store: view recorded, `content_stop_pressure_detected: no`,
  3 new checks PASS, `checks_passed 36 / checks_total 36`, `real_provider_calls 0`,
  `store_rows_written_by_observation 0`, `evidence_rows_before == evidence_rows_after`,
  `source_errors []`. The drill store's rows classify clean (0 stops), so it raises
  no warning.
- Health snapshot verdict `ATTENTION` with `fail_count 0` (attention sources:
  credentials presence + this pressure observation); the pressure check adds no FAIL
  and changes no readiness/qualification/verification gate.

## Tests added (all offline: stubs, fixtures, disposable stores, 0 provider calls)

- Operator surfaces: clean provider raises no warning; pre-classification store
  reports UNKNOWN, not clear; zero attempts never yield a fabricated rate; a
  crossing recorded rate is a warning-grade observation carrying rate + sample size
  + finishReason + bounded flag; health-snapshot escalation list and markdown;
  Morning Chief Brief carry + render; the view never writes the store (hash and
  sidecar checks); absent/undeclared store reports UNKNOWN; the declared recorded
  series is consumed by default; an unreadable series artifact is recorded as a
  source error, never fabricated.
- Drill harness: D7 view recorded over the isolated store; clean drill store raises
  no warning; no rate without a recorded sample; nothing written and nothing acted
  on; operator lines never print a rate without a sample; plus isolated-store unit
  cases (pre-classification → unknown, zero attempts → unknown, clean classified →
  clean, empty store → "pressure unknown, not clear").

## Limits / still open (unchanged, not chased)

- Why the provider's recitation filter fires on some identical calls and not others
  is still unexplained; the provider exposes the stop reason but not the filter
  input, and no unbounded generation was used to chase it.
- No failover, worker swap, re-dispatch, retry or safe mode was triggered by this
  view, by design; a flagged group stays an E4/owner decision. Stage 2 remains
  disabled and the 0/7 provider-credential gate was not touched or re-parameterised.
- No VPS cutover, no deployment-architecture finalisation, no new store schema.
