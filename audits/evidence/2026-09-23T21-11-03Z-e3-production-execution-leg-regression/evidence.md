# Test evidence — e3-production-execution-leg-regression

- Run started (UTC): 2026-09-23T21:11:03+00:00
- Run finished (UTC): 2026-09-23T21:11:52+00:00
- Code SHA: `6c19a01f9d34914683f4ea7ebd5aabe2aa82f510`
- Python: 3.11.16 (C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe)
- Working directory / import root: `C:\Users\mukun\Documents\mukund-chief-control-plane`

| Suite | Status | Ran | Passed | Failed | Errors | Skipped | Exit | Import root |
|---|---|---|---|---|---|---|---|---|
| E1 executive brain runtime matrix | pass | 32 | 32 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |
| E2 governor / provider adapters | pass | 45 | 45 | 0 | 0 | 0 | 0 | `C:\Users\mukun\AppData\Local\hermes\exec-brain` |
| E3 baseline | pass | 54 | 54 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 extended | pass | 60 | 60 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 shadow orchestrator | pass | 13 | 13 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 production rehearsal (real path, isolation, E1/E2 boundary) | pass | 24 | 24 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 production execution leg (dispatch, verification gating, DAG/evidence persistence) | pass | 18 | 18 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 production execution rehearsal driver (stubbed providers, isolated db) | pass | 10 | 10 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E4 resource continuity + E5 safe mode (combined suite) | pass | 37 | 37 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| Remote queue (isolated: disposable roots, mocked/live-free boundaries) | pass | 30 | 30 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |

Suite totals are recorded per suite only. No cross-suite aggregate is asserted here.

## Exact commands

- E1 executive brain runtime matrix: `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_eb.py`
- E2 governor / provider adapters: `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_governor.py  (PYTHONPATH=C:\Users\mukun\AppData\Local\hermes\exec-brain)`
- E3 baseline: `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E3 extended: `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_extended.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E3 shadow orchestrator: `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_shadow_orchestrator.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E3 production rehearsal (real path, isolation, E1/E2 boundary): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_production_rehearsal.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E3 production execution leg (dispatch, verification gating, DAG/evidence persistence): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_execution.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E3 production execution rehearsal driver (stubbed providers, isolated db): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_execution_rehearsal.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E4 resource continuity + E5 safe mode (combined suite): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e4e5.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- Remote queue (isolated: disposable roots, mocked/live-free boundaries): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\remote_queue\tests\test_queue.py`
