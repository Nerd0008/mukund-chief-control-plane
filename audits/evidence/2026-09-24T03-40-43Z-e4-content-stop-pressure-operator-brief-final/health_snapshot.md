# Operational health snapshot

- Run (UTC): 2026-09-24T03:42:05+00:00 -> 2026-09-24T03:42:06+00:00
- Code SHA: `ed390dbb3f53f499ee5a9a9339fd31289f17d0d6`
- Verdict: **ATTENTION** (fail=0, attention=2, unknown=0)
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
| resource.content_stop_pressure | ATTENTION | google/gemini-3.1-flash-image recorded content-side stop rate 0.222 at sample size 9 (threshold 0.2, minimum sample 5); last finishReason IMAGE_RECITATION; observation only — no automatic worker swap, re-dispatch, failover, retry or safe-mode entry; any failover or re-request stays an explicit E4/owner decision |

## Queue

- pending: 1
- running: 2
- completed: 32
- blocked: 12

## Escalations

- [info/queue] 12 blocked queue task(s): categories=['execution_error', 'external_provider']
- [owner_action/credentials] 7 provider credential(s) absent — owner action (provider keys)
- [warning/provider_content_stop_pressure] provider content-side stop pressure (recorded evidence, observation only): google/gemini-3.1-flash-image [worker google-nano-banana-2] stop rate 0.222 at sample size 9 classified recorded dispatch attempts (bounds: rate >= 0.2 AND sample >= 5); last finishReason IMAGE_RECITATION. observation only — no automatic worker swap, re-dispatch, failover, retry or safe-mode entry; any failover or re-request stays an explicit E4/owner decision

## Provider content-side stop pressure (recorded evidence, observation only)

- Status: ATTENTION — google/gemini-3.1-flash-image recorded content-side stop rate 0.222 at sample size 9 (threshold 0.2, minimum sample 5); last finishReason IMAGE_RECITATION; observation only — no automatic worker swap, re-dispatch, failover, retry or safe-mode entry; any failover or re-request stays an explicit E4/owner decision
-   orchestration_store.performance_evidence openai/unknown [worker codex-cli]: attempts observed 5 (0 classified, 5 without the content-stop ledger), content-side stops observed 0, stop rate unknown (sample size 0 — no classified attempt recorded; no rate is reported from zero attempts), last finishReason none recorded, last stop recorded at none recorded, content withheld at a measurable rate: unknown (status unknown)
-   orchestration_store.performance_evidence deepseek/deepseek-flash [worker deepseek-v41-flash]: attempts observed 13 (0 classified, 13 without the content-stop ledger), content-side stops observed 0, stop rate unknown (sample size 0 — no classified attempt recorded; no rate is reported from zero attempts), last finishReason none recorded, last stop recorded at none recorded, content withheld at a measurable rate: unknown (status unknown)
-   orchestration_store.performance_evidence google/gemini-3.1-flash-image [worker google-nano-banana-2]: attempts observed 11 (0 classified, 11 without the content-stop ledger), content-side stops observed 0, stop rate unknown (sample size 0 — no classified attempt recorded; no rate is reported from zero attempts), last finishReason none recorded, last stop recorded at none recorded, content withheld at a measurable rate: unknown (status unknown)
-   recorded_provider_series:e3-google-image-repeat-series google/gemini-3.1-flash-image [worker google-nano-banana-2]: attempts observed 9 (9 classified, 0 without the content-stop ledger), content-side stops observed 2, stop rate 0.222 (sample size 9 classified attempts; 2/9 classified recorded dispatch attempts), last finishReason IMAGE_RECITATION, last stop recorded at 2026-09-24T01:44:32+00:00, content withheld at a measurable rate: yes (status pressured)
- observation only — no automatic worker swap, re-dispatch, failover, retry or safe-mode entry; any failover or re-request stays an explicit E4/owner decision

## Safety properties

- read-only against live state and databases
- no provider/network call; no credential value read (presence + store only)
- does not change scheduled tasks or services
