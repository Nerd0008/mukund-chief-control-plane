# Superseded — passed, but before the `brief_id` fix

This run passed **34/34** and is a truthful record of the code at that moment. It
was superseded because completing the same unfinished unit exposed one more defect:
`brief_id` was still stamped with the raw run clock while the as-of was floored to
the quantum, so two runs over an identical content digest published different ids
(`cdb-…T013130Z-62b8de90` vs `cdb-…T013136Z-62b8de90`). The id is now stamped with
the brief's own `as_of`.

Superseded by: `audits/evidence/20260924T013238Z-career-daily-brief/` (34/34, with
the added `sub_quantum_run_same_brief_id` assertion, code SHA `9b414f1`).
