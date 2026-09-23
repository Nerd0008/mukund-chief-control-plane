# E3 production rehearsal evidence

- Started (UTC): 2026-09-23T20:57:41+00:00
- Finished (UTC): 2026-09-23T20:57:42+00:00
- Stage: E3 Stage 1 (shadow/rehearsal) — Stage 2 NOT enabled by this run
- Rehearsal orchestration DB: `C:\Users\mukun\AppData\Local\Temp\e3-rehearsal-0mh6oibq\rehearsal_orchestration.db`
- Rehearsal evidence store: `C:\Users\mukun\AppData\Local\Temp\e3-rehearsal-0mh6oibq\rehearsal_evidence.json`
- Production stores unchanged: True
- E1/E2 boundary clean: True

| Scenario | Outcome | Team complete | Verifier attempts | Rejections | Repairs |
|---|---|---|---|---|---|
| Rehearsal: deterministic validation task | REHEARSAL_PASSED | True | 2 | 1 | 1 |
| Rehearsal: unrepaired rejection task | REHEARSAL_VERIFICATION_FAILED | True | 1 | 0 | 0 |
| Rehearsal: task family with no seeded worker | REHEARSAL_VERIFICATION_FAILED | False | 1 | 0 | 0 |
| Rehearsal: decomposed multi-node task | REHEARSAL_TEAM_INCOMPLETE | False | 1 | 0 | 0 |
| Rehearsal: contradictory multi-node task | REHEARSAL_CONFLICTS | False | 1 | 0 | 0 |
