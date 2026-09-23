# E3 worker qualification from recorded execution evidence

- Started (UTC): 2026-09-23T21:52:08+00:00
- Finished (UTC): 2026-09-23T21:52:08+00:00
- Harness: `exec-brain/e3_qualification_benchmark.py::EvidenceBackedBenchmark`
- Orchestration DB: `C:\Users\mukun\AppData\Local\hermes\exec-brain\orchestration.db`
- Real provider calls spent: 0 (evaluates evidence already recorded)
- Bar: >= 2 verified passes over >= 2 recorded executions, with >= 1 first-pass pass

| Worker | Role | Recorded | Verified passes | First-pass passes | Failures | Result | Registry state |
|---|---|---|---|---|---|---|---|
| codex-cli | builder | 3 | 3 | 3 | 0 | pass | QUALIFIED |
| codex-cli | integrator | 2 | 2 | 2 | 0 | pass | QUALIFIED |
| deepseek-v41-flash | builder | 8 | 8 | 3 | 0 | pass | QUALIFIED |
| google-nano-banana-2 | vision | 2 | 1 | 1 | 1 | inconclusive | EVALUATING |

## Per-check detail

### codex-cli / builder — pass

- recorded-real-execution: `pass` — 3 recorded row(s); 0 without a real provider / DAG node reference
- deterministic-verification-gating: `pass` — 0 row(s) with no recorded deterministic verdict
- dag-state-corroborated: `pass` — 0 verified pass(es) not corroborated by COMPLETE in dag_node
- capability-demonstrated: `pass` — 3 verified COMPLETE execution(s) recorded
- repeatability: `pass` — 3 verified pass(es) over 3 recorded execution(s); bar is >= 2 passes over >= 2 executions with >= 1 first-pass pass(es)
- latest-execution-not-failing: `pass` — latest recorded execution evidence-f530f9ca759b -> final_success=1, verification=PASS

- evidence references: `['evidence-791966050006', 'evidence-162513079ebb', 'evidence-f530f9ca759b']`
- evidence-backed: `True` (a result that is not evidence-backed can never map to QUALIFIED)

### codex-cli / integrator — pass

- recorded-real-execution: `pass` — 2 recorded row(s); 0 without a real provider / DAG node reference
- deterministic-verification-gating: `pass` — 0 row(s) with no recorded deterministic verdict
- dag-state-corroborated: `pass` — 0 verified pass(es) not corroborated by COMPLETE in dag_node
- capability-demonstrated: `pass` — 2 verified COMPLETE execution(s) recorded
- repeatability: `pass` — 2 verified pass(es) over 2 recorded execution(s); bar is >= 2 passes over >= 2 executions with >= 1 first-pass pass(es)
- latest-execution-not-failing: `pass` — latest recorded execution evidence-947fe76eafdd -> final_success=1, verification=PASS

- evidence references: `['evidence-f00a495bef1f', 'evidence-947fe76eafdd']`
- evidence-backed: `True` (a result that is not evidence-backed can never map to QUALIFIED)

### deepseek-v41-flash / builder — pass

- recorded-real-execution: `pass` — 8 recorded row(s); 0 without a real provider / DAG node reference
- deterministic-verification-gating: `pass` — 0 row(s) with no recorded deterministic verdict
- dag-state-corroborated: `pass` — 0 verified pass(es) not corroborated by COMPLETE in dag_node
- capability-demonstrated: `pass` — 8 verified COMPLETE execution(s) recorded
- repeatability: `pass` — 8 verified pass(es) over 8 recorded execution(s); bar is >= 2 passes over >= 2 executions with >= 1 first-pass pass(es)
- latest-execution-not-failing: `pass` — latest recorded execution evidence-100f9ed4e648 -> final_success=1, verification=PASS

- evidence references: `['evidence-cefec061aec2', 'evidence-dccac639b86e', 'evidence-1a52c94c3b35', 'evidence-98267aa0b374', 'evidence-f7fc508c1fc3', 'evidence-96631a0f9975', 'evidence-3819ff902042', 'evidence-100f9ed4e648']`
- evidence-backed: `True` (a result that is not evidence-backed can never map to QUALIFIED)

### google-nano-banana-2 / vision — inconclusive

- recorded-real-execution: `pass` — 2 recorded row(s); 0 without a real provider / DAG node reference
- deterministic-verification-gating: `pass` — 0 row(s) with no recorded deterministic verdict
- dag-state-corroborated: `pass` — 0 verified pass(es) not corroborated by COMPLETE in dag_node
- capability-demonstrated: `pass` — 1 verified COMPLETE execution(s) recorded
- repeatability: `inconclusive` — 1 verified pass(es) over 2 recorded execution(s); bar is >= 2 passes over >= 2 executions with >= 1 first-pass pass(es)
- latest-execution-not-failing: `pass` — latest recorded execution evidence-7a719e3b4623 -> final_success=1, verification=PASS

- evidence references: `['evidence-53374aa1dde4', 'evidence-7a719e3b4623']`
- evidence-backed: `True` (a result that is not evidence-backed can never map to QUALIFIED)

## Store state after

- `qualified_rows_without_evidence`: 0
- capability_registry: `{"worker_id": "codex-cli", "task_family": "code", "capability_role": "builder", "state": "QUALIFIED", "evidence_count": 3, "first_pass_successes": 3, "first_pass_attempts": 3, "last_qualified_at": "2026-09-23T21:52:08.733388"}`
- capability_registry: `{"worker_id": "codex-cli", "task_family": "code", "capability_role": "integrator", "state": "QUALIFIED", "evidence_count": 2, "first_pass_successes": 2, "first_pass_attempts": 2, "last_qualified_at": "2026-09-23T21:52:08.740896"}`
- capability_registry: `{"worker_id": "deepseek-v41-flash", "task_family": "code", "capability_role": "builder", "state": "QUALIFIED", "evidence_count": 8, "first_pass_successes": 3, "first_pass_attempts": 8, "last_qualified_at": "2026-09-23T21:52:08.743900"}`
- capability_registry: `{"worker_id": "google-nano-banana-2", "task_family": "code", "capability_role": "vision", "state": "EVALUATING", "evidence_count": 2, "first_pass_successes": 1, "first_pass_attempts": 2, "last_qualified_at": null}`
- worker_capability_event: `{"event_id": "capev-3f65e7084e84", "worker_id": "codex-cli", "capability_role": "builder", "previous_state": "UNPROVEN", "new_state": "QUALIFIED", "actor": "e3-qualification-from-evidence", "timestamp": "2026-09-23 21:52:08"}`
- worker_capability_event: `{"event_id": "capev-198177118ee7", "worker_id": "codex-cli", "capability_role": "integrator", "previous_state": "UNPROVEN", "new_state": "QUALIFIED", "actor": "e3-qualification-from-evidence", "timestamp": "2026-09-23 21:52:08"}`
- worker_capability_event: `{"event_id": "capev-ab724f262295", "worker_id": "deepseek-v41-flash", "capability_role": "builder", "previous_state": "UNPROVEN", "new_state": "QUALIFIED", "actor": "e3-qualification-from-evidence", "timestamp": "2026-09-23 21:52:08"}`
- worker_capability_event: `{"event_id": "capev-a35a50a21c23", "worker_id": "google-nano-banana-2", "capability_role": "vision", "previous_state": "UNPROVEN", "new_state": "EVALUATING", "actor": "e3-qualification-from-evidence", "timestamp": "2026-09-23 21:52:08"}`

Smoke readiness is not qualification. No worker is marked QUALIFIED here unless the record above shows it cleared every evidence check, and no provider call was spent to produce these decisions.

