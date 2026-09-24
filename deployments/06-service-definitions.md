# 06 — Service definitions

Status: **inventoried and exportable, unchanged.** No task was created, modified,
deleted, started or stopped by this task.

Exported task definitions (Windows Task Scheduler XML, live-exported
2026-09-24) live in `deployments/service-definitions/*.xml`. They are the
authoritative, re-importable definitions:

```bash
schtasks /Create /XML deployments/service-definitions/Hermes_Gateway.xml /TN Hermes_Gateway /F
```

Line endings: keep these `.xml` files CRLF (Task Scheduler imports tolerate
either, but the `.cmd` launchers they reference require CRLF).

---

## 1. Service inventory

| Task | Action | Trigger | Repetition | Restart on failure | Runs on battery | Start when available |
|---|---|---|---|---|---|---|
| `Hermes_Gateway` | `wscript.exe //B //Nologo %LOCALAPPDATA%\hermes\gateway-service\Hermes_Gateway.vbs` | **logon** (+30 s delay) | — | **yes**, every 1 min, count 999 | **yes** (allowed) | **yes** |
| `HermesRemoteQueuePoller` | `wscript.exe //B remote_queue\run_poller_hidden.vbs` → `poller.py --once` | time 21:08 + **logon** | every **2 min** | no | **yes** (allowed, since 2026-09-24) | **yes** |
| `ChiefDiscordSync` | `venv\Scripts\python.exe scripts\scheduled_sync_chief.py` | time 21:06 + **logon** | every **30 min** | no | **yes** (since 2026-09-24) | **yes** |
| `ChiefCareerBrief` | `career-ops\run_scheduled_brief.cmd` | daily 07:00 | 1 day | no | **yes** (since 2026-09-24) | **yes** |
| `ChiefCareerScan-UK` | `career-ops\run_scheduled_scan.cmd uk` | daily 23:45 | 1 day | no | **yes** (since 2026-09-24) | **yes** |
| `ChiefCareerScan-Dubai` | `career-ops\run_scheduled_scan.cmd dubai` | daily 23:50 | 1 day | no | **yes** (since 2026-09-24) | **yes** |
| `ChiefCareerScan-Japan` | `career-ops\run_scheduled_scan.cmd japan` | daily 23:55 | 1 day | no | **yes** (since 2026-09-24) | **yes** |
| `ChiefCareerScan-Singapore` | `career-ops\run_scheduled_scan.cmd singapore` | daily 00:00 | 1 day | no | **yes** (since 2026-09-24) | **yes** |
| `ChiefOperationalBackup` | `scripts\run_scheduled_ops.cmd backup` | daily 02:30 | 1 day | no | **yes** | **yes** |
| `ChiefLogRotation` | `scripts\run_scheduled_ops.cmd logs` | daily 03:00 | 1 day | no | **yes** | **yes** |
| `ChiefMorningBrief` | `scripts\run_scheduled_ops.cmd brief` | daily 06:30 | 1 day | no | **yes** | **yes** |
| `ChiefHealthSnapshot` | `scripts\run_scheduled_ops.cmd health` | daily 08:00 | 1 day | no | **yes** | **yes** |
| `Mukund Chief of Staff` | legacy superseded stack | logon | — | — | — | — (**Disabled**, kept as donor) |

All run as `mukun` with `<LogonType>InteractiveToken</LogonType>`
(`Interactive only`) and `MultipleInstancesPolicy: IgnoreNew`. The poller runs
with `RunLevel: HighestAvailable`; all others default.

`ExecutionTimeLimit`: gateway `PT0S` (unlimited, it is a daemon); the rest carry
the scheduler default (~72 h) — the scan launchers are themselves bounded (the
unified orchestrator's `--budget-seconds 2700` with `--scan-timeout 900`, and it
holds a lock so a second instance exits without running).

The four `ChiefCareerScan-*` tasks each run
`career-ops/run_scheduled_scan.cmd <region>`, which invokes the unified scheduled
orchestrator (`career-ops/discovery/scheduled_orchestrator.py run --scheduled
--require-live-web --mode high_recall`). Behaviour, outputs, source-coverage
matrix, rollback and no-go criteria: `career-ops/scheduled_orchestrator.md`.
A run without an operational current-web search mechanism exits 3 (recorded
blocker, no fixture fallback), which Task Scheduler reports as a non-zero last
result by design.

## 2. Deployment findings (state after the 2026-09-24 hardening)

**(a) Battery gating — RESOLVED 2026-09-24.** Seven of eight tasks had
`DisallowStartIfOnBatteries = true` and `StopIfGoingOnBatteries = true`, so on a
laptop running on battery the queue poller, Discord sync, the daily brief and
all four regional scans would not start, and would stop if the machine went on
battery while they ran. The owner approved the service change and
`scripts/harden_scheduled_tasks.py --apply` set both to `false` on all seven,
cleared `StopOnIdleEnd` and added `StartWhenAvailable`; the two light periodic
tasks also gained a logon trigger. Byte-exact pre-change definitions are kept
under `deployments/service-definitions/backups/20260924T221712Z-pre-hardening/`
and the round-trip restore was verified, so the change is fully reversible
(`python scripts/harden_scheduled_tasks.py --restore --backup-dir <dir>`).

**(b) Reboot persistence — configured 2026-09-24; the reboot itself is still
unobserved.** Every owned task now has `StartWhenAvailable` and the two light
periodic tasks have a logon trigger, so a read-only assessment reports
`unverified_after_reboot = []`. Engineering must not reboot the owner's laptop,
so no survival claim is made. Owner checklist:
`deployments/11-owner-reboot-acceptance-checklist.md`.

**(c) Interactive-token constraint — deliberately preserved.** Every task runs
under the owner's interactive logon. None of them runs for a signed-out user.
The hardening deliberately did **not** switch any task to SYSTEM or another
account, because the provider keys live in the owner's user-scoped Windows
Credential Manager and a different account could not read them. Changing this is
an owner decision (canonical blocker `unattended-interactive-token`).

## 3. Re-provisioning (idempotent, reversible)

Career/brief tasks have a first-class installer:

```bash
python career-ops/install_schedules.py --status                 # confirm registration
python career-ops/install_schedules.py --install                # register all regional scans
python career-ops/install_schedules.py --install-brief          # register the daily brief
python career-ops/install_schedules.py --remove --region uk     # reversible per region
python career-ops/install_schedules.py --remove-brief
```

Note the launcher constraint documented in the installer: `schtasks` rejects a
`/TR` longer than 261 characters, which is why interpreter path + log redirect
live inside `career-ops/run_scheduled_scan.cmd`.

Gateway / poller / Discord-sync: re-import the exported XML (see the command at
the top). The committed XML contains the machine-specific
`<UserId>S-1-5-21-…-1001</UserId>` and `<Author>MISTY\mukun</Author>`; substitute
the destination machine's account when re-importing (or drop the `<Principals>`
block and pass `/RU`).

## 4. Start / stop / restart procedure (maintenance and restore)

Stop order (writers first, daemon last):

```bash
schtasks /End /TN HermesRemoteQueuePoller
schtasks /End /TN ChiefDiscordSync
schtasks /End /TN ChiefCareerBrief
for r in UK Dubai Japan Singapore; do schtasks /End /TN "ChiefCareerScan-$r"; done
# gateway is a daemon: stop it deliberately, not as part of an unattended script
```

Disable (so nothing restarts mid-maintenance) — reversible with `/Change /ENABLE`:

```bash
schtasks /Change /TN <task> /DISABLE
```

Start order (daemon first, writers after):

```bash
schtasks /Run /TN Hermes_Gateway
schtasks /Run /TN HermesRemoteQueuePoller
schtasks /Run /TN ChiefDiscordSync
for r in UK Dubai Japan Singapore; do schtasks /Run /TN "ChiefCareerScan-$r"; done
schtasks /Run /TN ChiefCareerBrief
```

Gateway-only restart: `schtasks /End /TN Hermes_Gateway && schtasks /Run /TN Hermes_Gateway`
(its failure-restart policy also recovers it automatically within 1 minute).

Do **not** touch `Mukund Chief of Staff`: its disposition is an owner decision.

## 5. Logging

| Log | Path | Rotation |
|---|---|---|
| Gateway starts | `%LOCALAPPDATA%\hermes\gateway-starts.log` | none configured — **gap** |
| Hermes logs | `%LOCALAPPDATA%\hermes\logs\` | none configured — **gap** |
| Queue log | `remote-queue\logs\queue.log` | none configured — **gap** |
| Regional scan stdout | `runtime\career-ops\scan-runs\<region>-last-stdout.json` | overwritten per run (self-limiting) |
| Daily brief | `runtime\career-ops\daily-brief\latest.{md,json}` | overwritten per run |
| Cron executions | `%LOCALAPPDATA%\hermes\cron\executions.db` | DB, no pruning configured |

Log rotation/retention is **not** configured by this package. It is implemented
by `agent-operational-brief-health-backup-persistence-2026-09-23` as
`scripts/operational_services.py backup --rotate-logs` (plan) / `--apply-logs`
(apply) — see `10-operational-services.md` §5 — but it is not yet scheduled; that
remains a small engineering step before the node is left unattended for long
periods (this document records the state, it does not change it).

## 6. Service dependencies

```
Hermes_Gateway  →  hermes-agent venv, %LOCALAPPDATA%\hermes\auth.json, network 443
HermesRemoteQueuePoller → hermes-agent venv, git CLI + GitHub remote, remote-queue/ queue dir
ChiefDiscordSync → hermes-agent venv, Discord archive dir, scripts\sync_discord_chief.py
ChiefCareer*    → hermes-agent venv, career-ops/ config + runtime/career-ops/, openpyxl
E3 runtime      → E3 modules in %LOCALAPPDATA%\hermes\exec-brain + its DBs (see manifest §3)
```

Nothing depends on the VPS, and nothing depends on a listening port.
