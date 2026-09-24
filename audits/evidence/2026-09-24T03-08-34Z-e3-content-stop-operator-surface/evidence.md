# Provider content-side stop — operator surface + orchestrator boundary + rehearsal integration

Task: `agent-e3-content-stop-operator-surface-and-rehearsal-integration-2026-09-24`
Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
Ran: 2026-09-24T03:08Z–03:12Z (UTC) · code SHA at run time `82ddf0081b1de0503d487f901d8bf294a3eaa223`
**Real provider calls spent by this task: 0.** Every scenario below runs a stub adapter on the real
code path or reads evidence recorded by the predecessor task
(`audits/evidence/2026-09-24T02-59-00Z-e3-provider-content-stop-attribution/`, 0 provider calls).

## 1. What was already true before this task (consumed, not re-derived)

Commit `8930572` (`exec-brain/e3_execution.py`) attributing an unrecovered provider content-side stop
as `provider_content_stop`, retrying the *identical* request at most `DEFAULT_MAX_CONTENT_STOP_RETRIES
= 2` times (<= 3 identical single-shot calls per node), then terminating the node `BLOCKED` with DAG
transition cause `provider_content_stop_unrecovered:<finishReason>`, an evidence row carrying the
attribution, and an E3 escalation with `trigger=provider_content_stop`. That evidence was reachable
only through the execution leg's run result and its unit suite. Nothing in `e3_execution.py` was
changed by this task; the deployed copy still hashes
`6f625a0a05e44b4f195ec1b53c8bc385ad4af389a9f9e2377a379778362d36f3`, identical to the repo source.

## 2. Deliverable (a) — operator surface

`exec-brain/e3_commands.py` now reads the *persisted* facts back out and prints them. No new schema,
no write to any store: the surface is read-only over `dag_node`, `dag_node_state_event`,
`dispatch_attempt`/node output, `performance_evidence`, and `e3_escalation`.

- new helper `finish_reason_from_cause()` (parses `provider_content_stop_unrecovered:<reason>`, both
  the recovered `content_stop_same_request_retry_N_after_<reason>` transition cause and the terminal
  cause) and `node_failure_view()`, which returns state / `failure_attribution` /
  `provider_finish_reason` / `content_stop_retries` / `terminal_cause` for a node.
- `e3-status` gained a DAG-node state breakdown (`SELECT state, COUNT(*) FROM dag_node GROUP BY
  state`) and a **`Node Failure Attribution`** section listing every `BLOCKED`/`FAILED` node
  (`TERMINAL_FAILURE_STATES`) with its failure attribution, provider finish reason, content-stop
  retries and terminal transition cause. Output is capped at `MAX_STATUS_ATTRIBUTION_NODES = 20`
  nodes (the full count is always printed) so a large historical store cannot flood the operator.
- `e3-trace <plan-or-node>` prints the same attribution block for the plan's terminal nodes.
- `e3-why <node>` prints the persisted attribution for that node, including the terminal transition
  cause and the escalation rows, and still prints `No decision found` for an unknown node.
- `exec-brain/e3_cli.py` only forwards the execution leg's extra keys (`outcome`, `plan_id`,
  `team_complete`, `team_assignments`, `execution`, `escalation`) in its JSON dump; the operator
  surface itself lives in `e3_commands.py`.

End-to-end capture (real execution leg, stub adapter, isolated db, 0 provider calls) is in
`operator_surface_output.txt`, produced by `operator_surface_demo.py`:

```
run_outcome: EXECUTION_BLOCKED
node_state: BLOCKED
failure_attribution: provider_content_stop
failure_finish_reason: IMAGE_RECITATION

===== e3-status =====
  BLOCKED: 1
--- Node Failure Attribution ---
    State: BLOCKED
    Failure attribution: provider_content_stop
    Provider finish reason: IMAGE_RECITATION
    Terminal transition cause: provider_content_stop_unrecovered:IMAGE_RECITATION

===== e3-trace =====   (plan-operator-demo)
    State: BLOCKED … Failure attribution: provider_content_stop … finish reason: IMAGE_RECITATION

===== e3-why =====     (node-operator-demo)
State: BLOCKED … Failure attribution: provider_content_stop … finish reason: IMAGE_RECITATION
    Terminal transition cause: provider_content_stop_unrecovered:IMAGE_RECITATION
```

## 3. Deliverable (b) — orchestrator boundary

`exec-brain/e3_shadow_orchestrator.py::orchestrate_and_execute` no longer reports an unrecovered
content-side stop only as a generic `repeated_failure`. It now collects the execution leg's own
escalations (`out["execution_escalations"]`, verbatim) and, when any carries
`trigger=provider_content_stop`, raises a **clearly attributed** escalation and returns it alongside
the existing one:

```
out["content_stop_escalation"] = {
  escalation_id, trigger="provider_content_stop",
  finish_reasons=[...],            # str-cast, sorted, e.g. ["IMAGE_RECITATION"]
  node_ids=[...], worker_ids=[...],# str-cast, sorted
  content_stop_retries=<max seen>, # e.g. 2
  execution_escalation_ids=[...],  # the execution-leg escalation id(s), so the chain is traceable
}
```

`out["escalation"]` keeps its previous `trigger=repeated_failure` semantics and the owner gate is
untouched — the change is additive, and a run that completes returns `content_stop_escalation: null`.

## 4. Deliverable (c) — rehearsal driver

`exec-brain/e3_execution_rehearsal.py` gained scenario **`G_content_stop_terminal`** (declared
`stub_only`, i.e. it can never consume a provider call) which runs the real execution leg against the
recorded stop verbatim: `finishReason=IMAGE_RECITATION`, empty response part list, no image,
0 candidate tokens. `CountingAdapterStub` was extended to serve it, and `run()` records
`content_stop_finish_reason`, `content_stop_retry_budget`, `content_stop_retry_count`,
`content_stop_retries_are_identical_requests`, `content_stop_escalation` and
`content_stop_terminal_path_recorded` in the driver's scenario record, with two new checks
(`content_stop_terminal_path_recorded`, `content_stop_retries_stayed_bounded`). `EXPECTED_BLOCK_SCENARIOS`
now covers G, so the run is expected to be `EXECUTION_BLOCKED`.

The driver's artifact for this task is `execution_rehearsal_stub_report.json`, produced by
`run_stub_execution_rehearsal.py` (the real `E3ExecutionRehearsal.run()` path with every adapter
factory replaced by a deterministic stub, isolated db): **all 23 checks true**, 3 stub dispatches for
scenario G, `content_stop_retry_count = 2` against `content_stop_retry_budget = 2`, escalations
`[{"trigger": "provider_content_stop", "finish_reason": "IMAGE_RECITATION", "content_stop_retries": 2}]`,
node persisted `BLOCKED` with cause `provider_content_stop_unrecovered:IMAGE_RECITATION`. The artifact
states in-band that `provider_calls_actually_spent = 0` and that `bounded_usage.real_provider_calls`
counts dispatches routed through the injected stubs, **not** provider calls spent.

Bounded retry accounting recorded in the artifact (per-node): 3 dispatches, attempts 1–2 are
`same_request_retry` repairs with `retry_index` 1 and 2 against `retry_budget` 2, and no 4th dispatch
is ever made — the hard bound `1 + max_repair_attempts + max_content_stop_retries` holds.

## 5. Tests added (all offline, 0 real provider calls)

| Suite | Before | After | New coverage |
|---|---|---|---|
| `exec-brain/tests/test_e3_operator_surface.py` (new) | — | **13 passed** | drives the real execution leg with a stub adapter into the content-stop terminal path, then asserts `e3-status`/`e3-trace`/`e3-why` print the attribution + finishReason + terminal cause; a COMPLETE node reports no attribution; `finish_reason_from_cause` parsing (recorded retry cause, terminal cause, unrelated cause, blank); unknown node still reported as unknown |
| `exec-brain/tests/test_e3_shadow_orchestrator.py` | 13 | **18 passed** | `TestOrchestrateAndExecuteContentStopEscalation`: the content-stop escalation is returned (not only `repeated_failure`), the `repeated_failure` behaviour is unchanged, the execution-leg escalation is surfaced verbatim by id, the retry accounting is bounded (3 dispatches, 2 retries), and a successful run returns `content_stop_escalation: null` |
| `exec-brain/tests/test_e3_execution_rehearsal.py` | 22 | **26 passed** | scenario G record (`run_outcome`, `node_state`, `failure_attribution`, finish reason, retry budget/count), the two driver checks, and `test_bounded_usage_counts_real_dispatches_only` rewritten to filter `adapter_call_log` by `STUB_ONLY_SCENARIOS` so stub-only scenarios can never be miscounted as real dispatches |

The new suite is registered in `scripts/evidence_runner.py` (19 → 20 suites).

## 6. Regression + deployment

| Run | Command | Result | Artifact |
|---|---|---|---|
| Pre-deploy | `python scripts/evidence_runner.py --label regression-post-content-stop-operator-surface` | **20 suites run / 20 passed / 0 failed / 0 unavailable / 529 tests / 529 passed / exit 0** | `audits/evidence/2026-09-24T03-08-19Z-regression-post-content-stop-operator-surface/` |
| Deploy | `python scripts/deploy_e3_runtime.py` | 4 modules copied (`e3_commands.py`, `e3_cli.py`, `e3_shadow_orchestrator.py`, `e3_execution_rehearsal.py`), backup `…\exec-brain\backups\e3-deploy-20260924T031014Z`, `eb_py` already-patched, exit 0 | deploy stdout (2026-09-24T03:10:14Z) |
| Post-deploy | `python scripts/evidence_runner.py --label regression-post-content-stop-operator-surface-postdeploy` | **20 / 20 / 0 failed / 0 unavailable / 529 / 529 / exit 0** | `audits/evidence/2026-09-24T03-10-22Z-regression-post-content-stop-operator-surface-postdeploy/` |
| Final frozen re-run | `python scripts/evidence_runner.py --label regression-post-content-stop-operator-surface-final` | **20 / 20 / 0 failed / 0 unavailable / 529 / 529 / exit 0** | `audits/evidence/2026-09-24T03-13-53Z-regression-post-content-stop-operator-surface-final/` |

The final re-run was made after the last test-file edit so the recorded regression matches the
committed source exactly.

Baseline beaten: 19 suites / 507 tests at `8930572` → 20 suites / 529 tests (+13 new suite, +5
orchestrator, +4 rehearsal), same exit code 0, and the post-deploy re-run is identical to the
pre-deploy run.

Deployed-vs-repo SHA-256 (verified after deploy, all **match**):

```
e3_commands.py            79ecb6bca428461022753c3223278cdd1358836d05547ee63ec5113c85033dce
e3_cli.py                 7f8744fe9a7e8c7fb7953d11ee14b4a095e9e2cd8b55a7be096b7be7ac33e551
e3_shadow_orchestrator.py 808b092a59b2a1e848ab653ce2c8579b0af4b340707653c15d55282367746185
e3_execution_rehearsal.py b482775f732eb105e2b85bb8d49e098720e6a25cb3c4a8f3ec2234fdb4461b2b
e3_execution.py           6f625a0a05e44b4f195ec1b53c8bc385ad4af389a9f9e2377a379778362d36f3  (unchanged)
```

## 7. Boundaries respected (no criterion weakened)

- E3 Stage 2 **NOT ENABLED**, no production dispatch, no VPS cutover, no deployment architecture
  decision. The 0/7 provider-credential gate was not re-run, re-parameterised or re-opened.
- Verification, readiness and qualification criteria unchanged: only an independent deterministic
  verification PASS reaches `COMPLETE`; the content-stop path still terminates `BLOCKED` and never
  passes.
- No unbounded retry path: 3 identical single-shot dispatches per node, hard bound intact.
- E4 resource continuity and E5 convergence behaviour untouched (their suites stayed green in both
  regression runs).
- No new store schema, no direct write to E1/E2 stores, no secret or credential value read,
  no raw runtime database content copied into the repository.
- Not chased and still open (deliberately): what makes the recitation filter fire on some identical
  calls and not others; the provider exposes the stop reason but not the filter input, and no
  unbounded generation may be used to chase it.
