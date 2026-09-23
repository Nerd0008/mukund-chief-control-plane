# Hermes GitHub Remote Task Queue

Status: READY_TO_IMPLEMENT
Created: 2026-09-23
Owner: Mukund
Purpose: Allow trusted control-plane collaborators to enqueue structured Hermes tasks while Mukund is away.

## Security model

This is NOT an arbitrary shell-command queue.

Hermes may consume only structured task objects that:
- reference an approved authority file or existing task,
- define a bounded objective and allowed scope,
- pass normal Hermes/E1/E2/E3 policy checks,
- do not bypass owner-approval gates,
- do not include secrets,
- do not request raw chain-of-thought,
- are uniquely identified and idempotent.

## Directories

- remote-queue/pending/
- remote-queue/running/
- remote-queue/completed/
- remote-queue/blocked/

## Required task fields

- task_id
- created_at
- objective
- authority
- priority
- allowed_scope
- requires_owner_approval
- status

Optional:
- depends_on
- stop_conditions
- notes

## Hermes poller behaviour

1. Poll every 2 minutes.
2. Acquire a local single-instance lock.
3. Safely fetch/pull latest main.
4. Validate each pending task against schema and approved authority.
5. Atomically claim ONE task by moving it to running.
6. Execute only through normal Hermes/control-plane mechanisms.
7. Never execute arbitrary shell strings supplied by the queue.
8. Never weaken E1/E2/E3/E4/E5 policy gates.
9. If owner action is required, move task to blocked with:
   - blocker category
   - exact owner action needed
   - what work can continue without it
10. On completion, write structured result summary and commit status transition.
11. Deduplicate by task_id.
12. Survive reboot/logon through Windows Task Scheduler.
13. Provide a local kill switch and documented disable procedure.
14. Never commit credentials, secrets, raw CoT, local databases, or temp artifacts.

## Failure behaviour

- Git conflict -> stop claiming new tasks, write blocked state if safely possible.
- Invalid task schema -> block task, do not execute.
- Authority missing/not approved -> block task.
- Owner approval required -> block task until owner explicitly approves.
- Provider credential/billing/account action required -> block task and continue independent queued work if available.
- Repeated execution failure -> obey existing convergence rules; no infinite loop.

## Initial validation

After implementation:
1. enqueue one harmless test job,
2. prove claim/deduplication,
3. prove execution,
4. prove completed transition,
5. prove blocked-owner-action transition,
6. prove kill switch,
7. run relevant regressions,
8. commit/push results.

## Current deadline authority

Primary build authority:
`tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`

This queue exists to accelerate that plan, not replace its safety/approval requirements.
