# 08 — Rollback criteria and no-go checklist

---

## Part 1 — No-go checklist

Cutover must not start (and must be aborted mid-run) if **any** box is unclear.

### Hard no-go (any one blocks the cutover)

- [ ] `python scripts/deployment_preflight.py` does not print `verdict: GO`.
- [ ] `python scripts/deployment_backup_restore_drill.py` does not print `status: PASS`.
- [ ] A pre-cutover backup report does not exist for the **source** node, or its
      fingerprint verification did not pass.
- [ ] Any database fails `PRAGMA integrity_check`, or a restored DB's row counts
      differ from its snapshot fingerprint.
- [ ] `scripts/evidence_runner.py` reports any failing suite, error or skipped
      test (verified 2026-09-24T03:57:34Z: **21 suites / 579 tests, all passing, 0 unavailable,
      SHA `31eecdb`** — the whole-company acceptance run).
- [ ] E4/E5 drill harness is not **36/36**, or reports `real_provider_calls > 0` or a
      non-empty `live_stores_changed`.
- [ ] A credential is unresolved **and** the destination would need it: 10/10
      roster workers must show `credential_present: true`, or the missing worker
      must be consciously accepted as non-routable in writing.
- [ ] Any credential would have to travel through GitHub, chat, a queue job or a
      file in the repository to reach the destination.
- [ ] The deployment topology is still undecided, or the cutover is not
      explicitly authorised by Mukund.
- [ ] The rollback path (Part 2) is not available and rehearsed.
- [ ] The owner-attended laptop security audit has not cleared the machine as a
      production host (required for any laptop-primary role).
- [ ] Rollback would be impossible because the destination would become the only
      copy of the state set.
- [ ] A raw `state.db` / owner-private runtime artifact would be published,
      committed or copied to a non-approved location.
- [ ] Any step would require exposing a secret value on a command line, in a log,
      or in a transcript.

### Soft no-go (documented risk; owner may accept explicitly, in writing)

- [x] Battery gating (`06` §2a) fixed 2026-09-24 on the laptop; re-check on any new node.
- [x] Log rotation/retention implemented 2026-09-24 and scheduled daily 03:00.
- [ ] Reboot persistence configured for every owned task, but the reboot itself is still unobserved — run `deployments/11-owner-reboot-acceptance-checklist.md`.
- [ ] No off-site backup.
- [ ] Live-provider failover drill not performed (only the stubbed-failure drill
      plus the real-path rehearsal exist).
- [ ] Legacy `Mukund Chief of Staff` task still enabled and undecided.

### Not a no-go, but must be recorded truthfully

- Codex usage-limit state, Nous Portal rate limiting, and any provider that
  returns an external blocker: record as UNKNOWN/blocked, never as healthy/zero.
- Vendor model IDs and usage figures: only provider-returned values may be
  recorded.

---

## Part 2 — Rollback criteria and commands

### Trigger criteria (roll back immediately if any occurs)

1. E1/E2/E3 integrity verification fails on the destination node.
2. A worker is marked routable without execution evidence, or qualification is
   asserted without evidence.
3. Any credential exposure (committed, logged, printed, or sent anywhere).
4. Unbounded retry/repair loop observed (a task not converging and not escalating).
5. Any E1/E2 database write from E3 outside the public interface.
6. Acceptance criterion unmet at the agreed checkpoint (see Part 3).
7. Destination node instability (repeated crash/restart, unexplained process loss).
8. Loss of the rollback path itself (e.g. the source node's state is overwritten).

### Rollback mechanisms (in order of preference)

**R1 — Code rollback (seconds).** Restore the previous E3 module set:

```bash
python scripts/deploy_e3_runtime.py --restore <runtime-root>/backups/e3-deploy-<stamp>
```

Each deploy writes a manifest with per-file SHA-256 before/after plus the source
git commit, so a restore is byte-for-byte provable.

**R2 — Git rollback (minutes).** Revert to the last known-good commit on the
private remote and re-run Phase 2.3 of the runbook.

**R3 — State rollback (minutes).** Restore the databases from the pre-cutover
snapshot per `05` §3, pairing each DB with its chain-head JSON, then verify.

**R4 — Topology rollback (minutes to hours).**
- From 3A (VPS watchdog) → stop the VPS watch role; the laptop was never demoted.
- From 3B (VPS primary) → stop the VPS writers, re-enable the laptop tasks, restore
  the laptop state from the **source** snapshot taken before the migration, and
  run `09` §1–§3 on the laptop.

**R5 — Full stop.** Disable all Chief tasks (`schtasks /Change /TN <task> /DISABLE`),
leave the state intact, and escalate to Mukund. Nothing is deleted.

### Non-rollbackable actions (need explicit authorisation; none performed)

- Deleting a database, backup, git history, or evidence.
- Overwriting the last remaining copy of the state set.
- Revoking/rotating a credential that something else depends on.
- Publishing anything external (posting, messaging, applying).

---

## Part 3 — Rollback decision points

| Checkpoint | Decide |
|---|---|
| After Phase 2 (deployment, before cutover) | If any Phase 0 check regressed → roll back R1/R3 and stop. |
| First 15 min after cutover | If any trigger criterion fires → immediate R4/R5, no "wait and see". |
| End of observation period | Promote fully, or roll back permanently (R4). |

Default posture when uncertain: **stop and escalate**, never continue on a
half-verified state. Preserving the rollback path outranks finishing on schedule.
