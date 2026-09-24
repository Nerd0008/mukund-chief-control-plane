# Deployment package — Chief control plane

Created: 2026-09-24 (overnight engineering cutoff)
Task: `agent-deployment-prep-manifest-and-owner-admin-checklist-2026-09-23`
Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`

Purpose: make Mukund's manual session **only** key/OAuth/admin configuration, and
make the later deployment session a runbook execution rather than a design
exercise — **without** choosing or performing the final architecture/cutover.

## What is in here

| File | Contents |
|---|---|
| `01-deployment-manifest.md` | Complete manifest: host/runtime, artifacts, state, services, network, topology variants, what must migrate vs stay local |
| `02-access-and-account-checklist.md` | Every credential/account/OAuth/admin item **by name** (never a value), where it lives, who provisions it, and the verification command |
| `03-owner-action-todo.md` | Every manual owner action, in exact execution order, with the "why owner-only" reason |
| `04-dependency-and-runtime-inventory.md` | Runtime versions, third-party packages, background jobs, ports/network requirements |
| `05-backup-and-restore-plan.md` | Backup scope, snapshot method, restore procedure, retention, and the verified drill |
| `06-service-definitions.md` | Service/scheduled-task definitions, restart/rollback commands, boot-persistence status |
| `07-cutover-runbook.md` | Ordered cutover runbook, with topology-specific steps marked PENDING OWNER DECISION |
| `08-rollback-and-no-go-checklist.md` | Rollback criteria/commands and the no-go list |
| `09-acceptance-and-health-commands.md` | Health checks, acceptance commands, expected results |
| `inventory-<stamp>.json` | Machine-generated read-only inventory evidence (`scripts/deployment_inventory.py`) |

## Executable parts (run these; they are the evidence)

```bash
# 1. Machine inventory (read-only, no network, no secrets)
python scripts/deployment_inventory.py --out deployments/inventory-<stamp>.json

# 2. Preflight / go-no-go (read-only; exit 0 = GO)
python scripts/deployment_preflight.py

# 3. Backup + restore verification drill (non-destructive; snapshots go to scratch)
python scripts/deployment_backup_restore_drill.py

# 4. Credential presence only (no value, no network)
python scripts/e3_credential_presence_probe.py
```

Each writes an evidence directory under `audits/evidence/<UTC-stamp>-<label>/`.

## Current state (verified 2026-09-24, not assumed)

- Preflight verdict: **GO** — 0 failures, 1 owner-gated warning
  (`audits/evidence/2026-09-24T02-14-49Z-deployment-preflight/`).
- Backup/restore drill: **PASS** — 10/10 artifacts, integrity ok, restore matches
  backup, deployment rollback dry-run clean
  (`audits/evidence/2026-09-24T02-15-42Z-deployment-backup-restore-drill/`).
- Full regression (run `deployment-prep-regression`, code SHA `b6329b7`):
  **16/16 suites passed, 456/456 tests, 0 failed, 0 errors, 0 skipped**
  (`audits/evidence/2026-09-24T02-18-54Z-deployment-prep-regression/`).
- E4/E5 drills: **33/33 checks, real provider calls 0**
  (`audits/evidence/2026-09-24T02-18-21Z-e4e5-real-path-drills/`).
- E3 orchestration DB verify: **PASSED**, schema version 2 (`eb.py e3-verify-db`).
- Credential presence: **7 of the 10 roster workers still have no local
  credential** (Mistral, GLM, Qwen, LongCat, MiniMax, Step, Tencent Hunyuan).
  This is the single owner-gated blocker; it is an owner action, not an
  execution failure.

## Scope boundaries honoured by this package

- No architecture was finalised. Laptop-primary and VPS-primary variants are
  both described; every topology-specific step is marked
  `PENDING OWNER DECISION`.
- No VPS login, no cutover, no service was changed, no scheduled task was
  created/modified/deleted.
- No secret value is recorded anywhere in this directory — credentials appear
  **by store name and env-var name only**.
- Raw database snapshots are never written into the repository.
- Operational backup service, health snapshots and reboot-persistence checks are
  owned by `agent-operational-brief-health-backup-persistence-2026-09-23`; this
  package only prepares the deployment-time backup/restore path and cites that
  work rather than duplicating it.
