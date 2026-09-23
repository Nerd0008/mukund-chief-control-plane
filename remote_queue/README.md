# Hermes GitHub Remote Task Queue

A structured task queue allowing trusted collaborators to enqueue work for Hermes while Mukund is away.

**Not a shell-command queue** — only structured task objects that pass validation.

## Quick Start

```bash
# Run one poll cycle
python remote_queue/poller.py --once

# Start continuous polling (every 2 minutes)
python remote_queue/poller.py --loop

# Check queue status
python remote_queue/poller.py --status

# Install as Windows Task Scheduler job (survives reboot)
remote_queue/install_poller.bat install

# Stop/start the poller remotely
python remote_queue/poller.py --kill
python remote_queue/poller.py --resume
```

## Directory Structure

```
remote_queue/
├── pending/          # Tasks awaiting execution (*.json)
├── running/          # Currently executing tasks
├── completed/        # Finished tasks with results
├── blocked/          # Tasks requiring owner action
├── logs/             # Poller event log (queue.log)
├── poller.py         # Main poller script
├── queue_schema.py   # Schema validation and atomic operations
├── tests/            # Test suite
├── install_poller.bat # Windows Task Scheduler installer
└── __init__.py
```

## Task Schema

Required fields:
- `task_id` — unique identifier (alphanumeric, hyphens, underscores)
- `created_at` — creation timestamp
- `objective` — task description (no secrets/credentials)
- `authority` — approved authority file reference
- `priority` — critical, high, medium, low
- `allowed_scope` — list of permitted actions
- `requires_owner_approval` — boolean
- `status` — pending, running, completed, blocked

Optional:
- `depends_on` — list of prerequisite task IDs
- `stop_conditions` — conditions to halt execution
- `notes` — additional context

## Security Model

1. Tasks validated against schema before execution
2. Authority must be in the approved list
3. `requires_owner_approval: true` → blocked until explicit approval
4. No raw secrets in objectives
5. Only ONE task claimed per poll cycle
6. Deduplication by task_id
7. Single-instance lock prevents concurrent pollers
8. Kill switch for emergency stop

## Failure Behavior

- Schema validation failed → blocked, continue other tasks
- Authority not approved → blocked
- Owner approval required → blocked
- Execution error → blocked with details

## Tests

```bash
python -m unittest remote_queue.tests.test_queue -v
```
