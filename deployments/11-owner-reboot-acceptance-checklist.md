# 11 — Owner reboot acceptance checklist

Owner-facing checklist for the one acceptance step that engineering is
**prohibited** from performing: rebooting the laptop to prove the Chief
scheduled tasks resume.

- Prepared: 2026-09-24 (task `agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24`)
- Reboot performed by engineering: **no** (the task's stop conditions forbid
  rebooting, signing out or power-cycling the owner's laptop).
- Reason this is owner-gated: only the owner may reboot the machine.

## What is already verified (read-only, before the reboot)

Measured live with `python scripts/harden_scheduled_tasks.py --verify`
(evidence: `audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/`):

| Task | Triggers | StartWhenAvailable | Runs on battery | Logon type | Survives boot (configuration) |
|---|---|---|---|---|---|
| Hermes_Gateway | logon | true | yes (no gate) | InteractiveToken | yes |
| HermesRemoteQueuePoller | logon + time | true | yes | InteractiveToken | yes |
| ChiefDiscordSync | logon + time | true | yes | InteractiveToken | yes |
| ChiefCareerBrief | calendar (daily 07:00) | true | yes | InteractiveToken | yes |
| ChiefCareerScan-UK | calendar (daily 23:45) | true | yes | InteractiveToken | yes |
| ChiefCareerScan-Dubai | calendar (daily 23:50) | true | yes | InteractiveToken | yes |
| ChiefCareerScan-Japan | calendar (daily 23:55) | true | yes | InteractiveToken | yes |
| ChiefCareerScan-Singapore | calendar (daily 00:00) | true | yes | InteractiveToken | yes |
| ChiefOperationalBackup | calendar (daily 02:30) | true | yes | InteractiveToken | yes |
| ChiefLogRotation | calendar (daily 03:00) | true | yes | InteractiveToken | yes |
| ChiefMorningBrief | calendar (daily 06:30) | true | yes | InteractiveToken | yes |
| ChiefHealthSnapshot | calendar (daily 08:00) | true | yes | InteractiveToken | yes |

- `DisallowStartIfOnBatteries` / `StopIfGoingOnBatteries` are `false` on every
  owned task; `StopOnIdleEnd` is cleared (an idle laptop no longer stops a run).
- The two light periodic tasks additionally carry a **logon trigger** so they
  resume immediately after a restart.
- The legacy `Mukund Chief of Staff` task is **Disabled** and is kept in place as
  a rollback donor. It must **not** be deleted.
- Every task keeps `<LogonType>InteractiveToken</LogonType>` for the owner's own
  SID, so the owner's user-scoped Windows Credential Manager secrets stay
  readable. **No** task was switched to SYSTEM or another account.

## What remains genuinely unverified

The reboot itself. "Survives boot (configuration)" above is a read-only
assessment of the task definition, **not** an observed survival. No claim is
made either way until the owner reboots.

## Acceptance checklist (after the next owner-initiated reboot)

Run these in a normal user session, signed in as Mukund.

1. `schtasks /query /fo CSV | findstr /i "chief hermes"` — every owned task above
   should report `Ready` or `Running` (not `Disabled`, not `Could Not Start`).
2. `python scripts/harden_scheduled_tasks.py --verify` — expect
   `"unverified_after_reboot": []` and `"still_battery_gated": []`.
3. `python scripts/operational_services.py validate-persistence` — expect the
   same verdicts and a fresh `persistence.json` under `runtime/chief/`.
4. Wait for the two fast tasks (~5 minutes after sign-in) and confirm
   `runtime/chief/logs/operational-services.log` and the Discord sync log show a
   post-reboot run.
5. Confirm `Hermes_Gateway` came back: `schtasks /query /tn Hermes_Gateway` and
   the gateway log under `%LOCALAPPDATA%\hermes\logs\gateway.log`.
6. Confirm the new operational services fired at their next window
   (02:30 backup, 03:00 log rotation, 06:30 morning brief, 08:00 health) or, if
   the reboot happened after those times, that `Next Run Time` has advanced.
7. Confirm the legacy task is still `Disabled` (do **not** enable or delete it).

## If a task did not survive

Nothing is lost — every definition is reversible.

- Re-import the preserved definition:
  `schtasks /Create /TN <TaskName> /XML deployments/service-definitions/<TaskName>.xml /F`
- Or roll the whole hardening back from the byte-exact pre-change backup:
  `python scripts/harden_scheduled_tasks.py --restore --backup-dir deployments/service-definitions/backups/20260924T221712Z-pre-hardening`
- Then record the failure in `tasks-or-issues/overnight-owner-actions-2026-09-24.md`.

## Known owner-side precondition (not a defect)

All tasks run under the interactive user token by design, so the laptop must be
**powered on and signed in** for them to run. Choosing a service-account /
credential change to run signed-out is a separate owner decision
(canonical blocker `unattended-interactive-token`) and was deliberately **not**
taken, because it would risk losing access to the owner's user-scoped credential
store.
