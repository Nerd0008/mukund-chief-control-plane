# Backup / restore verification drill

- Run (UTC): 2026-09-24T03:59:41+00:00 -> 2026-09-24T03:59:43+00:00
- Verdict: **PASS**
- Live state modified: False
- Network calls spent: 0

| Artifact | Kind | integrity_check | restore == backup | Status |
|---|---|---|---|---|
| e1-e2-exec-brain | sqlite | ok | True | PASS |
| e2-governor | sqlite | ok | True | PASS |
| e3-orchestration | sqlite | ok | True | PASS |
| hermes-state | sqlite | ok | True | PASS |
| hermes-kanban | sqlite | ok | True | PASS |
| hermes-shared-state | sqlite | ok | True | PASS |
| hermes-cron-executions | sqlite | ok | True | PASS |
| e1-chain-head | json | - | True | PASS |
| e2-gov-chain-head | json | - | True | PASS |
| e2-deepseek-config | json | - | True | PASS |

## Deployment rollback availability

- `python scripts/deploy_e3_runtime.py --dry-run` -> exit 0, status PASS
- wrote nothing: True

## Restore procedure (verified by this drill)

1. Stop the writers: disable `HermesRemoteQueuePoller`, `ChiefDiscordSync`, `ChiefCareerBrief`, `ChiefCareerScan-*` and stop `Hermes_Gateway`.
2. Copy the snapshot's `.db` files back over the live paths listed in `deployments/01-deployment-manifest.md`.
3. For each restored database run `PRAGMA integrity_check` and compare the per-table row counts with the snapshot's `backup_fingerprint`.
4. Re-enable the tasks and confirm the gateway restarts and one health/acceptance command passes.

This drill is non-destructive; it never performs step 2 against live state.
