# Test evidence — whole-company-acceptance

- Run started (UTC): 2026-09-24T03:51:12+00:00
- Run finished (UTC): 2026-09-24T03:52:31+00:00
- Code SHA: `a15469cacbd1a4f7ce0c0385cd1c2bb77c1f701d`
- Python: 3.11.16 (C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe)
- Working directory / import root: `C:\Users\mukun\Documents\mukund-chief-control-plane`

| Suite | Status | Ran | Passed | Failed | Errors | Skipped | Exit | Import root |
|---|---|---|---|---|---|---|---|---|
| E1 executive brain runtime matrix | pass | 32 | 32 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |
| E2 governor / provider adapters | pass | 45 | 45 | 0 | 0 | 0 | 0 | `C:\Users\mukun\AppData\Local\hermes\exec-brain` |
| E3 baseline | pass | 54 | 54 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 extended | pass | 60 | 60 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 shadow orchestrator | pass | 18 | 18 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 production rehearsal (real path, isolation, E1/E2 boundary) | pass | 24 | 24 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 production execution leg (dispatch, verification gating, DAG/evidence persistence) | pass | 22 | 22 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 production execution rehearsal driver (stubbed providers, isolated db) | pass | 26 | 26 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 evidence-backed qualification (recorded-evidence harness, isolated db) | pass | 13 | 13 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 Google image request-protocol conformance + repeat-series accounting (offline: stubbed HTTP layer, isolated db) | pass | 18 | 18 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain, C:\Users\mukun\Documents\mukund-chief-control-plane\scripts` |
| E3 provider content-side stop attribution + bounded same-request retry (offline: recorded-response fixtures, stubbed transports, isolated db) | pass | 25 | 25 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E3 operator surface for the content-side stop attribution (offline: stub adapter, isolated db) | pass | 13 | 13 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E4 resource continuity + E5 safe mode (combined suite) | pass | 37 | 37 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E4 provider content-side stop pressure over recorded evidence (offline: real execution leg + stub adapters, recorded series artifact, isolated db) | pass | 31 | 31 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| E4/E5 real-path drill harness (stubbed providers, isolated db, owner override + recovery) | pass | 47 | 47 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain` |
| Operational services (health snapshot, morning brief, backup/retention, persistence; isolated: temp roots, injected inputs) | pass | 27 | 27 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane\scripts` |
| Remote queue (isolated: disposable roots, mocked/live-free boundaries) | pass | 30 | 30 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |
| Remote bridge watchdog/timeout hardening (isolated: fake Hermes child, no live queue) | pass | 12 | 12 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |
| Windows console QuickEdit/Select hardening (isolated: injected console api, fake Hermes child) | pass | 12 | 12 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |
| Bounded recoverable-failure retry, initial + 2 (isolated: disposable queue root, fake handler) | pass | 24 | 24 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |
| Poller dispatch routing: agent tasks always reach Hermes (isolated: stubbed dispatch, disposable queue root) | pass | 9 | 9 | 0 | 0 | 0 | 0 | `C:\Users\mukun\Documents\mukund-chief-control-plane` |

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
- E3 evidence-backed qualification (recorded-evidence harness, isolated db): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_qualification_evidence.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E3 Google image request-protocol conformance + repeat-series accounting (offline: stubbed HTTP layer, isolated db): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_google_image_protocol.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain;C:\Users\mukun\Documents\mukund-chief-control-plane\scripts)`
- E3 provider content-side stop attribution + bounded same-request retry (offline: recorded-response fixtures, stubbed transports, isolated db): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_provider_content_stop.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E3 operator surface for the content-side stop attribution (offline: stub adapter, isolated db): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e3_operator_surface.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E4 resource continuity + E5 safe mode (combined suite): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e4e5.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E4 provider content-side stop pressure over recorded evidence (offline: real execution leg + stub adapters, recorded series artifact, isolated db): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e4_content_stop_pressure.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- E4/E5 real-path drill harness (stubbed providers, isolated db, owner override + recovery): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain\tests\test_e4e5_drills.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\exec-brain)`
- Operational services (health snapshot, morning brief, backup/retention, persistence; isolated: temp roots, injected inputs): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\scripts\tests\test_operational_services.py  (PYTHONPATH=C:\Users\mukun\Documents\mukund-chief-control-plane\scripts)`
- Remote queue (isolated: disposable roots, mocked/live-free boundaries): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\remote_queue\tests\test_queue.py`
- Remote bridge watchdog/timeout hardening (isolated: fake Hermes child, no live queue): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\remote_queue\tests\test_bridge_watchdog.py`
- Windows console QuickEdit/Select hardening (isolated: injected console api, fake Hermes child): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\remote_queue\tests\test_console_quickedit.py`
- Bounded recoverable-failure retry, initial + 2 (isolated: disposable queue root, fake handler): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\remote_queue\tests\test_worker_retry.py`
- Poller dispatch routing: agent tasks always reach Hermes (isolated: stubbed dispatch, disposable queue root): `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe C:\Users\mukun\Documents\mukund-chief-control-plane\remote_queue\tests\test_poller_routing.py`
