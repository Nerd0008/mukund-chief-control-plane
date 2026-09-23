# E3 production execution leg rehearsal

- Started (UTC): 2026-09-23T21:31:09+00:00
- Finished (UTC): 2026-09-23T21:31:28+00:00
- Stage: E3 production execution leg rehearsal — real worker execution on the local orchestration path; Stage 2 NOT enabled by this run
- Runtime root: `C:\Users\mukun\AppData\Local\hermes\exec-brain`
- Orchestration DB: `C:\Users\mukun\AppData\Local\hermes\exec-brain\orchestration.db` (schema v2)
- Real provider calls: 7 {'deepseek': 5, 'openai': 2} (planned 7)
- Rehearsal-evidence isolation from production stores: True (all production writes refused: True)
- E1/E2 boundary clean: True

| Scenario | Node | Worker | Node state | Dispatches | Verifications | Rejections | Repairs |
|---|---|---|---|---|---|---|---|
| A_repair_cycle_deepseek | node-execleg-A_repair_cycle_deepseek-1 | deepseek-v41-flash | COMPLETE | 2 | 2 | 1 | 1 |
| B_first_pass_deepseek | node-execleg-B_first_pass_deepseek-1 | deepseek-v41-flash | COMPLETE | 1 | 1 | 0 | 0 |
| C_codex_cli_dispatch | node-execleg-C_codex_cli_dispatch-1 | codex-cli | COMPLETE | 1 | 1 | 0 | 0 |
| F_decomposed_multi_worker | node-plan-0001-1 | deepseek-v41-flash | COMPLETE | 2 | 2 | 1 | 1 |
| F_decomposed_multi_worker | node-plan-0001-2 | codex-cli | COMPLETE | 1 | 1 | 0 | 0 |
| E_non_routable_refusal | node-execleg-E_non_routable_refusal-1 | mistral-small-4 | BLOCKED | 0 | 0 | 0 | 0 |

## Checks

- repair_cycle_rejected_then_repaired: True
- first_pass_complete: True
- codex_cli_complete: True
- multi_node_plan_is_decomposed: True
- multi_node_all_nodes_complete: True
- multi_worker_two_distinct_routable_workers: True
- multi_node_per_node_deterministic_verification: True
- multi_node_rejection_then_repair: True
- multi_node_dependency_gate_observed: True
- multi_node_dag_state_and_evidence_persisted: True
- google_image_complete: True
- non_routable_refused_without_dispatch: True
- complete_requires_verification: True
- dag_state_and_evidence_persisted: True
- e2_linkage_recorded: True
- rehearsal_evidence_isolated_from_production_stores: True
- no_simulated_evidence_in_live_stores: True
- e1_e2_boundary_clean: True
- runtime_modules_deployed: True
- orchestration_db_is_schema_v2: True
