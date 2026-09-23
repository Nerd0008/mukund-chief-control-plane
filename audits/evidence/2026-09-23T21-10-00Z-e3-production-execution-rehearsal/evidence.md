# E3 production execution leg rehearsal

- Started (UTC): 2026-09-23T21:07:31+00:00
- Finished (UTC): 2026-09-23T21:07:48+00:00
- Stage: E3 production execution leg rehearsal — real worker execution on the local orchestration path; Stage 2 NOT enabled by this run
- Runtime root: `C:\Users\mukun\AppData\Local\hermes\exec-brain`
- Orchestration DB: `C:\Users\mukun\AppData\Local\hermes\exec-brain\orchestration.db` (schema v2)
- Real provider calls: 5 {'deepseek': 3, 'openai': 1, 'google': 1}

| Scenario | Worker | Node state | Dispatches | Verifications | Rejections | Repairs | Outcome |
|---|---|---|---|---|---|---|---|
| A_repair_cycle_deepseek | deepseek-v41-flash | COMPLETE | 2 | 2 | 1 | 1 | EXECUTION_COMPLETE |
| B_first_pass_deepseek | deepseek-v41-flash | COMPLETE | 1 | 1 | 0 | 0 | EXECUTION_COMPLETE |
| C_codex_cli_dispatch | codex-cli | COMPLETE | 1 | 1 | 0 | 0 | EXECUTION_COMPLETE |
| D_google_image_dispatch | google-nano-banana-2 | FAILED | 1 | 1 | 1 | 0 | EXECUTION_FAILED |
| E_non_routable_refusal | mistral-small-4 | BLOCKED | 0 | 0 | 0 | 0 | EXECUTION_BLOCKED |

## Checks

- repair_cycle_rejected_then_repaired: True
- first_pass_complete: True
- codex_cli_complete: True
- google_image_complete: False
- non_routable_refused_without_dispatch: True
- complete_requires_verification: True
- dag_state_and_evidence_persisted: True
- e2_linkage_recorded: True
- runtime_modules_deployed: True
- orchestration_db_is_schema_v2: True
