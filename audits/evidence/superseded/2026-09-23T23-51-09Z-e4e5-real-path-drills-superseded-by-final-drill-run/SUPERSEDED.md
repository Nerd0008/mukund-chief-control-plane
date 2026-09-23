# SUPERSEDED — 2026-09-23T23:51:09Z e4e5-real-path-drills regression run

Status: **SUPERSEDED, do not cite as current evidence.**

Reason: this regression run was taken on an intermediate code revision while
`exec-brain/e4e5_drill_harness.py` still opened the *live* runtime
`orchestration.db` read-only for its capability-registry grounding read. Opening
the live WAL database created stray `orchestration.db-shm` / `-wal` sidecars in
`LOCALAPPDATA/hermes/exec-brain/`, which made the E1 runtime matrix
`test_t13_no_gateway_modification` fail (unexpected file in the deployed runtime
directory) — recorded here as `E1 executive brain runtime matrix | fail | 32 ran /
31 passed / 1 failed`.

Nothing about the E1/E2 data was modified (the live store's own mtime was
unchanged), and the failure was a directory-hygiene assertion, not a data or
governance defect. The harness was then changed to read a scratch **snapshot
copy** of the registry and never open the live file; the stray sidecars created
by this run were removed; the failing suite and the drill suite both pass on the
final revision.

The authoritative run for this task is the final `e4e5-real-path-drills`
regression bundle recorded in `state/full_build_tracker.md`.
