# E4 resource continuity — recorded provider content-side stop pressure

Task: `agent-e4-provider-content-stop-pressure-visibility-2026-09-24`
Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
Ran: 2026-09-24T03:22:46Z–03:28:45Z (UTC) · code SHA at run time `03ebc74bc6dd799c438893b432f66af9c6be8ed2`
(pre-commit; the code commits for this task are the ones that follow it on `main`).

**Real provider calls spent by this task: 0.** Every value below is read from
evidence already on disk (recorded `performance_evidence` rows and the recorded
IMAGE_RECITATION series) or produced by a deterministic stub adapter running the
real execution path on an isolated scratch db. No provider series was re-run.

## 1. The gap this task closed

`exec-brain/resource_monitor.py` (`ResourceMonitor.get_resource_snapshot` /
`calculate_runway` / `predict_exhaustion`) measured provider usage as tokens,
request counts and a cost-derived time-to-exhaustion. A provider that withholds
content on a content-side stop still consumes prompt tokens
(`promptTokenCount: 17` on every recorded `IMAGE_RECITATION` call), so a
provider that repeatedly withholds content looked like *healthy capacity*: the
failure was invisible in the resource-continuity view even though the terminal
attribution (`provider_content_stop`, the node failure view, the orchestrator
boundary and the rehearsal) already existed.

## 2. Deliverable — recorded-evidence pressure view

`exec-brain/resource_monitor.py` (the E4 resource-continuity surface) gained:

| Element | What it does |
|---|---|
| `content_stop_pressure()` | Pure aggregation of attempt ledgers into a view grouped by `(source, worker_id, provider, model)`. Sources are **never merged**, so a recorded series and the store rows can never be conflated or double-counted. |
| `evidence_row_ledgers(con)` | Read-only read of the recorded `performance_evidence` rows. `attempts` is the per-dispatch ledger the execution leg appends once per dispatch, so its length is the dispatch count; `content_stop_stops` is the recorded count of dispatches classified as a provider content-side stop. A row without that key (recorded before the classification existed) is reported **unclassified**, never stop-free. |
| `recorded_series_ledger(path)` | Reads an already-recorded provider series artifact verbatim (each executed observation = one observed attempt; a stop counts only when the *recorded* `finishReason`/`candidate_finish_reasons`/`promptFeedback` is a documented content-side value, mirroring `e3_execution.content_side_stop_reason`). Provider/model come from the worker roster, then the recorded model value. |
| `render_content_stop_pressure(view)` | Operator lines. Every rate is printed with its sample size; a group with no classified attempt prints `stop rate: unknown (sample size 0 …)`. |
| `ResourceMonitor.get_content_stop_pressure(series_paths=())` | The E4 surface's method for the view. |
| `build_content_stop_pressure_view(con, series_paths=())` | Module-level builder used by the operator surface; a store that cannot be read yields an empty view plus an explicit `source_errors` entry instead of a fabricated one. |

Per worker/provider/model the view reports: **attempts observed** (classified and
unclassified), **content-side stops observed**, **stop rate with its sample
size**, **last observed finishReason**, **last recorded stop time**, and the
bounded boolean **`content_withheld_at_measurable_rate`**, with a status of
`unknown` / `clean` / `stops_recorded_below_bound` / `pressured`.

Bounded flag (both bounds documented in the source):

* `MEASURABLE_CONTENT_STOP_RATE = 0.2` — sits just below the only *recorded*
  rate for this roster (2/9 = 0.222 in the recorded series below), so the one
  real measurement would flag.
* `MEASURABLE_CONTENT_STOP_MIN_SAMPLE = 5` — the bounded per-node recovery path
  records at most 3 dispatch attempts for one node, so a single unlucky node can
  never present its own ratio as a provider-level rate.

The bounds only bound the **flag**: the raw rate, sample size, finishReason and
stop time are always reported whether or not the flag fires.

Observation only: `view["observation_only"] is True` and
`view["decision"]` states there is no automatic worker swap, re-dispatch,
failover, retry or safe-mode entry; any failover/re-request stays an explicit
E4/owner decision. No new store schema, no E1/E2 write (the view only ever
executes `SELECT`s).

## 3. Operator surface

`exec-brain/e3_commands.py` `status()` gained an
`--- E4 Resource Continuity: provider content-side stop pressure ---` section;
`exec-brain/e3_cli.py` added the additive `e3-status --pressure-series
<observations.json>` option (repeatable) to add an already-recorded provider
series as its own source. The section is read-only and degrades to an explicit
"(unavailable: the E4 resource-continuity module could not be imported in this
runtime; deploy it with scripts/deploy_e3_runtime.py)" line rather than breaking
the E3 status command.

`operator_pressure_output.txt` (`operator_pressure_demo.py`, real execution leg +
stub adapter + isolated db + the recorded artifact read verbatim, 0 provider
calls) — store source only:

```
--- E4 Resource Continuity: provider content-side stop pressure ---
  bounds: rate >= 0.2 AND sample >= 5 recorded dispatch attempts (bounded flag)
  source: orchestration_store.performance_evidence (attempts observed 3, classified 3, content-side stops 3)
    google/gemini-3.1-flash-image [worker google-nano-banana-2]
      attempts observed: 3 (3 classified, 0 without the content-stop ledger)
      content-side stops observed: 3
      stop rate: 1.000 (sample size 3 classified attempts; 3/3 classified recorded dispatch attempts)
      last observed finishReason: IMAGE_RECITATION
      last stop recorded at: 2026-09-24 03:23:00
      content withheld at a measurable rate: no (status: stops_recorded_below_bound)
  content_stop_pressure_detected: no
```

and with `--pressure-series audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/observations.json`
(the recorded series, consumed verbatim — never re-run):

```
  source: recorded_provider_series:e3-google-image-repeat-series (attempts observed 9, classified 9, content-side stops 2)
    google/gemini-3.1-flash-image [worker google-nano-banana-2]
      stop rate: 0.222 (sample size 9 classified attempts; 2/9 classified recorded dispatch attempts)
      last observed finishReason: IMAGE_RECITATION
      last stop recorded at: 2026-09-24T01:44:32+00:00
      content withheld at a measurable rate: yes (status: pressured)
  content_stop_pressure_detected: yes
```

## 4. What the view reports about the *existing* recorded state

The same operator lines were produced against a **read-only copy** of the live
runtime store (`deployed_surface_output.txt`, `deployed_hash_verification.txt`):

```
  source: orchestration_store.performance_evidence (attempts observed 29, classified 0, content-side stops 0)
    codex-cli        openai/unknown                5 attempts  0 classified  → status unknown
    deepseek-v41-flash deepseek/deepseek-flash    13 attempts  0 classified  → status unknown
    google-nano-banana-2 google/gemini-3.1-flash-image 11 attempts 0 classified → status unknown
```

Those rows were recorded **before** the content-stop classification existed, so
their attempts are reported as unclassified and their rate as `unknown` — the
view never reports them as clean/healthy. Supplying the recorded series as its
own source surfaces the recorded 2/9 pressure for the google pair. This is the
truthful maximum available from the recorded evidence, and it is stated as
`unknown`, not as fabricated data.

## 5. Deterministic offline tests

`exec-brain/tests/test_e4_content_stop_pressure.py` — **31 tests**, registered in
`scripts/evidence_runner.py`. 0 real provider calls (stub adapters on the real
execution leg + isolated dbs + the recorded artifact read from disk).

| Requirement | Test |
|---|---|
| a clean provider reports no pressure | `PurePressureAggregationTests.test_clean_provider_reports_no_pressure`, `StoreBackedPressureTests.test_clean_provider_group_reports_no_pressure` |
| recorded content-side stops report the truthful rate and finishReason | `PurePressureAggregationTests.test_recorded_stops_report_the_truthful_rate_and_reason`, `StoreBackedPressureTests.test_content_stop_rows_report_the_truthful_rate_and_finish_reason`, `RecordedSeriesTests.test_recorded_series_reports_its_recorded_stop_rate` |
| zero attempts report unknown, never a fabricated rate | `PurePressureAggregationTests.test_zero_attempts_report_unknown_never_a_rate`, `RecordedSeriesTests.test_an_empty_recorded_series_is_unknown_not_clean`, `StoreBackedPressureTests.test_an_empty_store_reports_unknown_not_clear`, `MonitorApiTests.test_resource_monitor_without_connections_reports_unknown` |
| every rate carries its sample size | `PurePressureAggregationTests.test_every_reported_rate_carries_its_sample_size` |
| pre-classification rows are not silently counted as stop-free | `StoreBackedPressureTests.test_a_row_without_the_content_stop_ledger_is_unknown_not_clean`, `PurePressureAggregationTests.test_attempts_without_the_content_stop_ledger_are_counted_but_unclassified` |
| repeated stops across nodes flag the measurable rate | `StoreBackedPressureTests.test_repeated_stops_across_nodes_flag_the_measurable_rate` |
| the view is an observation, not an action | `StoreBackedPressureTests.test_the_view_writes_nothing_and_acts_on_nothing` (table counts unchanged for `performance_evidence`, `dag_node`, `dag_state_event`, `safe_mode_event`, `resource_checkpoint`, `resource_snapshot`, `convergence_event`) |
| the recorded artifact is read, not modified/re-run | `RecordedSeriesTests.test_reading_the_recorded_series_does_not_modify_it` (SHA-256 before == after) |
| sources never merge | `RecordedSeriesTests.test_two_recorded_series_never_merge_into_one_sample`, `PurePressureAggregationTests.test_sources_are_never_merged` |
| operator surface | `OperatorSurfacePressureTests` (section present, rate + sample size + finishReason rendered, `unknown` rather than clear with no rows, `--pressure-series` adds the recorded source, a missing artifact is reported not invented, CLI option parses) |

## 6. Regression (full `scripts/evidence_runner.py`)

| Run | Command | Result |
|---|---|---|
| pre-deploy | `python scripts/evidence_runner.py --label regression-pre-content-stop-pressure --out-dir audits/evidence/2026-09-24T03-23-28Z-regression-pre-content-stop-pressure` | **21 suites / 21 passed / 560 collected / 560 passed / 0 failed / 0 unavailable**, every suite's recorded `exit_code` 0 (`run_started_utc 2026-09-24T03:23:28Z`, finished 03:24:46Z — i.e. before the 03:24:48Z deploy) |
| post-deploy, before the E1 allow-list was extended | `… --out-dir audits/evidence/2026-09-24T03-25-04Z-regression-post-content-stop-pressure-postdeploy` | **20/21 suites, 559/560 tests, E1 `test_t13_no_gateway_modification` FAILED** (`exit_code` 1) — the E1 static gate rejects any file in the runtime root outside its allow-list, and the newly deployed `resource_monitor.py` was not yet listed. No test was skipped or re-parameterised; the E1 allow-list was extended by exactly the deployed module (see below) and the failure is recorded here as it happened. |
| post-deploy, final (aggregate exit code captured) | `python scripts/evidence_runner.py --label regression-post-content-stop-pressure-final-exitcheck --out-dir audits/evidence/2026-09-24T03-29-37Z-regression-post-content-stop-pressure-final` | **21 suites / 21 passed / 560 collected / 560 passed / 0 failed / 0 unavailable, runner exit code 0 (captured)** (`run_started_utc 2026-09-24T03:29:37Z`, finished 03:30:56Z) |

An earlier post-deploy green run at `2026-09-24T03:27:28Z` is preserved under
`audits/evidence/superseded/2026-09-24T03-27-28Z-regression-post-content-stop-pressure-postdeploy-final-superseded-by-exit-verified-rerun/`
(superseded only because its aggregate exit code was not captured; its per-suite
records are identical, 21 suites / 560 tests / 0 failed).

Baseline before this task: **20 suites / 529 tests / exit 0** at `82ddf0` (pre-deploy)
and its post-deploy re-run. This task adds one suite (+31 tests) and regresses
nothing (core suites unchanged: `test_e4e5.py` 37/37, `test_e3_operator_surface.py`
13/13, `test_e3_provider_content_stop.py` 25/25 — all inside the 21 suites above).

E1 gate integrity (negative proof, same method as the earlier GAP-2 fix): with a
probe file `probe_unexpected_file.py` placed in the runtime root,
`TestMatrix.test_t13_no_gateway_modification` **failed** with
`unexpected file …probe_unexpected_file.py`; the probe was then deleted and the
suite re-ran green (32/32). The criterion is unchanged: only the deployed module
set is accepted, everything else still fails.

## 7. Deployment

`python scripts/deploy_e3_runtime.py` at `2026-09-24T03:24:48Z`
(backup `…\exec-brain\backups\e3-deploy-20260924T032448Z`), `eb_py`
`already-patched`:

* copied: `e3_commands.py`, `e3_cli.py`, **`resource_monitor.py`** (added to the
  deployed module set because the deployed `e3-status` imports it for the
  pressure view);
* `deployed_hash_verification.txt` — repo vs deployed SHA-256 all match:
  `e3_commands.py bcd1276896f7db12286c8e4f51c28eea550bd908b9b4e0bf15e702f4c3a89f96`,
  `e3_cli.py 8c50a33c93b55262987a3cd1e89bc52628e83786217293b8e72e514aabc5bf85`,
  `resource_monitor.py c138c0ecdce5011c8bc889a429cbf6cd5917311f778fe5b6f8148616f29e2688`,
  and the unchanged `e3_execution.py 6f625a0a…`, `e3_shadow_orchestrator.py 808b092a…`,
  `e3_execution_rehearsal.py b482775f…` → `ALL_MATCH`;
* `deployed_surface_output.txt` — the **deployed** `e3_commands.py`
  (`…\exec-brain\e3_commands.py`, imported from the runtime root only) prints the
  E4 section against the read-only store copy, including the recorded series
  source at `0.222 (sample size 9)` / `content withheld at a measurable rate: yes`.

## 8. Not done (deliberately), and what remains open

* No automatic worker swap, re-dispatch, failover, retry or safe-mode entry: the
  view is an observation. Any failover remains an explicit E4/owner decision.
* E3 Stage 2 / production dispatch / VPS cutover: **not enabled / not performed**.
  The 0/7 provider-credential gate was not run, re-parameterised or re-opened, and
  no readiness, qualification or verification criterion was changed or weakened.
* Still open and deliberately not chased: what makes the provider's recitation
  filter fire on some identical calls and not others (the provider exposes the
  stop reason but not the filter input; no unbounded generation may be used).
* `state/current_company_state.md` and `state/full_build_tracker.md` updated with
  the verified facts above.
