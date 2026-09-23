# Superseded rehearsal run — 2026-09-23T21-31-09Z

This run is preserved, not deleted, but it is **superseded** by
`audits/evidence/2026-09-23T21-32-41Z-e3-production-execution-rehearsal/` and must
not be used as the authoritative production-rehearsal evidence.

Why it was superseded: in this run the optional Google image scenario was not
requested (`--include-google` was not passed), but the driver reported
`checks.google_image_complete: true` for the omitted scenario — the "not
requested" branch of the check returned success instead of "not evaluated". The
machine-readable check therefore could have been misread as evidence that the
Google image real-dispatch path passes, which it does not (it is an unresolved
provider-side failure owned by
`agent-e3-image-diagnosis-and-multiworker-execution-2026-09-23`).

Everything else in this run is consistent with the authoritative run: the same
five scenarios were exercised, the same 7 bounded real provider calls were spent
(deepseek 5, codex-cli 2), all DAG/verification/isolation/contamination evidence
is present, and every other check is `true`.

The driver was fixed so an unrequested optional scenario reports as
`null` (not evaluated) and a `scenarios_requested` map is written into the
report; the rehearsal was then re-run. The re-run, not this directory, is the
evidence of record.
