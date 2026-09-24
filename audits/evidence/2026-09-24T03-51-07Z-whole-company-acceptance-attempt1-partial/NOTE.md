# Partial attempt-1 record

This run was killed by a defect in the acceptance runner itself: the persistence-step
evaluator assumed `persistence.json#tasks` was a list, but it is a keyed object
(`{task_name: {...}}`), so the evaluator raised `AttributeError` after 9 of the ~30 steps
(**all 9 PASS**: E1 intake/audit, E2 brief/verify/telemetry, E3 status/verify-db, E4/E5
drills 36/36, and the full 21-suite / 579-test regression).

The partial results are preserved here as the honest record of that defect. The runner
evaluator was fixed (and a guard added so a broken evaluator can never read as a pass),
and the authoritative acceptance run is the sibling directory
`*-whole-company-acceptance-final`.
