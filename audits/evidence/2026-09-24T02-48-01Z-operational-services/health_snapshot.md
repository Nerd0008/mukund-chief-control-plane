# Operational health snapshot

- Run (UTC): 2026-09-24T02:49:26+00:00 -> 2026-09-24T02:49:27+00:00
- Code SHA: `5440f08dc6e38593d8fd656620a2c5bce5b3a21a`
- Verdict: **ATTENTION** (fail=0, attention=1, unknown=0)
- Live state modified: False

| Check | Status | Detail |
|---|---|---|
| db.e1-e2-exec-brain | PASS | ok |
| db.e2-governor | PASS | ok |
| db.e3-orchestration | PASS | ok |
| db.hermes-state | PASS | ok |
| db.hermes-kanban | PASS | ok |
| db.hermes-shared-state | PASS | ok |
| db.hermes-cron-executions | PASS | ok |
| queue.valid | PASS | 0 invalid task envelopes |
| credentials.presence | ATTENTION | configured=2 missing=7 |
| brief.resource | PASS | renders from live governor state |
| brief.career | PASS | latest.json exists=True |
| tasks.present | PASS | 8 chief tasks; missing=none |

## Queue

- pending: 2
- running: 2
- completed: 28
- blocked: 12

## Escalations

- [info/queue] 12 blocked queue task(s): categories=['execution_error', 'external_provider']
- [owner_action/credentials] 7 provider credential(s) absent — owner action (provider keys)

## Safety properties

- read-only against live state and databases
- no provider/network call; no credential value read (presence + store only)
- does not change scheduled tasks or services
