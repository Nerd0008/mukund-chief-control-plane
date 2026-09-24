# Scheduled-task definition backups (rollback donor)

Byte-exact exports of the live Windows Task Scheduler definitions, taken **before**
the 2026-09-24 unattended-operation hardening changed them. They exist so the
change is a real rollback rather than a rebuild.

| Directory | What it is |
|---|---|
| `20260924T221712Z-pre-hardening/` | Manual pre-change export of all nine tasks (eight Chief/Hermes tasks + the legacy donor). Taken with `schtasks /Query /TN <name> /XML`, so its line endings are the doubled `CR CR LF` that redirection through the shell produces. It re-imports successfully (verified). |
| `20260924T222131Z-pre-hardening/` | The export `scripts/harden_scheduled_tasks.py --apply` takes automatically before it replaces anything. Same tasks; normalised line endings. This is the authoritative rollback set. |

## Restore

```bash
python scripts/harden_scheduled_tasks.py --restore \
    --backup-dir deployments/service-definitions/backups/20260924T222131Z-pre-hardening
```

The legacy `Mukund Chief of Staff` definition is backed up here but this tool
never imports it (its disposition is an owner decision). To roll the hardening
back by hand instead:

```bash
schtasks /Create /TN <task> /XML <backup>.xml /F
```

## Verified

`audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/reversibility_proof.json`
records a real round trip on `ChiefDiscordSync`: restore from backup brought the
battery gates and the missing `StartWhenAvailable` back, and re-applying the
hardened definition removed them again. `InteractiveToken` was preserved
throughout — no task was ever moved to SYSTEM or another account.

Line endings and the encoding declaration: these files keep the Task Scheduler
XML `encoding="UTF-16"` declaration. That is required, not sloppy — the loader
rejects `encoding="UTF-8"` with `(1,40)::ERROR: unable to switch the encoding`
even when the bytes match the declaration.
