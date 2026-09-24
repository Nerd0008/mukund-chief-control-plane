# 05 — Backup and restore plan

Verified by `scripts/deployment_backup_restore_drill.py` on 2026-09-24:
**PASS** — 10/10 artifacts, every snapshot integrity-ok and restore-identical to
its snapshot, deployment rollback dry-run clean.
Evidence: `audits/evidence/2026-09-24T02-15-42Z-deployment-backup-restore-drill/`.

Ownership note: this document covers the **deployment-time** backup/restore path.
The scheduled operational backup service, its retention policy and the health
snapshot are owned by `agent-operational-brief-health-backup-persistence-2026-09-23`;
this package deliberately does not duplicate that work.

---

## 1. Backup scope

Must be backed up (see `01-deployment-manifest.md` §3 for the migrate/no-migrate split):

| Unit | Path | Method |
|---|---|---|
| E1 audit DB + chain head | `exec-brain\exec_brain.db` + `chain-head.json` | SQLite online backup API + file copy |
| E2 governor DB + chain head + budget config | `exec-brain\governor.db` + `gov-chain-head.json` + `deepseek-config.json` | same |
| E3 orchestration DB | `exec-brain\orchestration.db` | SQLite online backup API |
| Hermes state DB | `hermes\state.db` | SQLite online backup API |
| Hermes kanban + shared state | `hermes\kanban.db`, `hermes\shared-state.db` | same |
| Cron execution history | `hermes\cron\executions.db` | same |
| Repo checkout | the git repository | git itself (commit + push to the private remote) |
| Runtime-only deploy backups | `exec-brain\backups\e3-deploy-*` | file copy (these are the E3 rollback points) |

Deliberately **not** backed up into any publishable location: Hermes
`auth.json`, Credential Manager contents, `runtime/company-watch/`,
`runtime/linkedin/`, `runtime/career-ops/cv-drafts/`,
`runtime/career-ops/application-status/`, `runtime/career-ops/daily-brief/`.
These are owner-private; they travel only by explicit, owner-approved local copy.

## 2. Snapshot method (proven)

- SQLite databases: `sqlite3.Connection.backup()` — a consistent snapshot even
  while the gateway/poller hold the DB open. A plain file copy of a live WAL
  database is **not** acceptable.
- JSON chain heads: byte copy, recorded with SHA-256.
- Every snapshot is verified with `PRAGMA integrity_check` **plus** a content
  fingerprint (per-table row counts + file SHA-256). A snapshot is not "good"
  until its fingerprint is captured.
- Snapshots are written to a scratch directory **outside the repository**
  (`%TMPDIR%\chief-backup-restore-drill-<stamp>\backup`). A raw database
  snapshot of `state.db` contains owner conversations and must never be committed
  or published.

Run it:

```bash
python scripts/deployment_backup_restore_drill.py
# -> audits/evidence/<stamp>-deployment-backup-restore-drill/
#      backup_restore_report.json   (verdicts, hashes, row counts)
#      backup_restore_report.md     (human summary)
#    snapshots themselves: scratch dir, never in git
```

## 3. Restore procedure (verified, never executed against live state)

1. **Freeze the writers.** Disable `HermesRemoteQueuePoller`, `ChiefDiscordSync`,
   `ChiefCareerBrief`, `ChiefCareerScan-*`; stop `Hermes_Gateway`. Confirm nothing
   is writing (no Chief process holds the DBs).
2. **Snapshot the current state first** — restore is not a substitute for a
   pre-change backup. Run step 2 of §2 against the live paths and keep the report.
3. **Copy the snapshot back**, DB and its chain-head JSON **as a pair**:
   `exec_brain.db`+`chain-head.json`, `governor.db`+`gov-chain-head.json`, then
   `orchestration.db`, `state.db`, `kanban.db`, `shared-state.db`,
   `cron\executions.db`.
4. **Verify** each restored DB: `PRAGMA integrity_check` = `ok`, and per-table row
   counts equal to the report's `backup_fingerprint.row_counts`. Any mismatch is a
   failed restore — do not start services on it.
5. **Restart** in order: `Hermes_Gateway` → `HermesRemoteQueuePoller` →
   the career/scan tasks, then run `09-acceptance-and-health-commands.md` §1–§3.
6. **Record** the restore in `deployments/` evidence with the report path.

RPO/RTO expectation (honest, not a promise): the drill shows restore is fast
(seconds per DB at current sizes) and deterministic; the real constraint is that
task scheduling is interactive-token, so recovery requires the owner to be signed
in. A VPS-primary topology would need a service-account decision before any
unattended RTO claim can be made.

## 4. Retention and rotation

| Item | Retention | Notes |
|---|---|---|
| Deployment E3 backups (`exec-brain\backups\e3-deploy-*`) | keep last 10 per module set, prune older | created automatically by `deploy_e3_runtime.py` on every deploy |
| Ad-hoc drill snapshots (scratch) | transient; pruned when idle | never in the repo, never published |
| Evidence reports (`audits/evidence/*`) | permanent, committed (aggregate only) | contain hashes/counts/verdicts, never raw data |
| Hermes logs (`%LOCALAPPDATA%\hermes\logs`, `gateway-starts.log`) | rotation/retention owned by the operational task | see `06-service-definitions.md` §5 |
| Operational backups | owned by `agent-operational-brief-health-backup-persistence-2026-09-23` | not duplicated here |

Log rotation is **not** configured by this package: no rotator is installed for
`%LOCALAPPDATA%\hermes\logs` or `remote-queue/logs`. That gap is recorded as
pending under the operational-services task and is a deployment checklist item
before the node is left unattended for long periods.

## 5. Integrity guarantees explicitly NOT claimed

- No off-site/off-machine backup exists today. Both topologies need one before
  the node is treated as production; the destination is an owner decision.
- No encryption-at-rest on the snapshots beyond the filesystem's own.
- No restore has been performed against live state (that is a cutover-time,
  owner-authorised action), so "restore works" is evidenced by a verified
  non-destructive drill into a throwaway directory, not by a production restore.
