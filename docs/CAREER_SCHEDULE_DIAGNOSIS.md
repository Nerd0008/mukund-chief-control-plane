# Career Scan schedule diagnosis (offline repair)

Read-only inspection on 2026-09-28 found `ChiefCareerScan-UK`, `-Dubai`,
`-Japan`, and `-Singapore` in Windows Task Scheduler with `State=Disabled` and
`Next Run Time=N/A`. Their definitions still point to the shared
`career-ops/run_scheduled_scan.cmd <region>` launcher and retain the intended
interactive-user token; no definition has been replaced or deleted.

The preserved scheduler facts are:

| Task | Last run | Last result | Interpretation |
| --- | --- | ---: | --- |
| UK | 2026-09-24 23:45:01 | `-1073741510` (`0xC000013A`) | interrupted/terminated process |
| Dubai | 2026-09-24 23:50:01 | `0` | previous run completed before disable |
| Japan | 2026-09-24 23:55:01 | `0` | previous run completed before disable |
| Singapore | 2026-09-25 00:00:01 | `0` | previous run completed before disable |

Windows task metadata and the available repository evidence do not retain the
identity of the actor or command that changed `Enabled` to `false`. The only
supported causal evidence is that the UK process was interrupted and the
remaining regions share the unified-run lock; a prior Chief archive describes
this cycle as degraded, with the tasks subsequently left disabled. This is
reported as an owner/runtime state, not silently corrected during repair.

Re-enable plan for a separate owner-approved activation turn:

1. Confirm the four XML definitions still target the unified read-only launcher
   and that the unified orchestrator lock/state is healthy.
2. Confirm the interactive owner session/credential-store requirement is
   acceptable for unattended execution; the current definitions intentionally
   use the interactive token.
3. Enable the four tasks together, preserving the existing staggered times
   (UK, Dubai, Japan, Singapore), and do not trigger them manually in the same
   change.
4. Observe one full staggered cycle: exit code, run-health record, lock release,
   source coverage, and `canonical_workbooks_unchanged=true`.

No task was re-enabled by this offline repair.
