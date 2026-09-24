# Superseded — false negative from a check that was itself wrong

This 34/34 run is **not** a product failure. Its `acceptance.json` records
`critical_checks_failed: ["stage4 a run inside the same declared quantum is the
same brief and writes nothing"]`, and that failure was a defect in the *new*
stage-4 check, not in the brief.

The check compared every file in the brief's output directory before and after a
sub-quantum rerun — including the append-only `run-log.jsonl`, which is *supposed*
to grow on every run. The product behaved correctly (the sub-quantum rerun
produced the same content digest and an empty `writes` list); the comparison was
wrong. The check now excludes the run log, matching the unit test.

Superseded by: `audits/evidence/20260924T013238Z-career-daily-brief/` (34/34, same
checks plus `brief_id` stability, code SHA `9b414f1`).

Kept rather than deleted so the false negative stays auditable.
