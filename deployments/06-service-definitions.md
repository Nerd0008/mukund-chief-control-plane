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
| `HermesRemoteQueuePoller` | `wscript.exe //B remote_queue\run_poller_hidden.vbs` → `poller.py --once` | time 21:08 | every **2 min** | no | **no** (blocked) | no |
| `ChiefDiscordSync` | `venv\Scripts\python.exe scripts\scheduled_sync_chief.py` | time 21:06 | every **30 min** | no | **no** | no |
| `ChiefCareerBrief` | `career-ops\run_scheduled_brief.cmd` | daily 07:00 | 1 day | no | **no** | no |
| `ChiefCareerScan-UK` | `career-ops\run_scheduled_scan.cmd uk` | daily 23:45 | 1 day | no | **no** | no |
| `ChiefCareerScan-Dubai` | `career-ops\run_scheduled_scan.cmd dubai` | daily 23:50 | 1 day | no | **no** | no |
| `ChiefCareerScan-Japan` | `career-ops\run_scheduled_scan.cmd japan` | daily 23:55 | 1 day | no | **no** | no |
| `ChiefCareerScan-Singapore` | `career-ops\run_scheduled_scan.cmd singapore` | daily 00:00 | 1 day | no | **no** | no |
| `Mukund Chief of Staff` | legacy superseded stack | logon | — | — | — | — |

All run as `mukun` with `<LogonType>InteractiveToken</LogonType>`
(`Interactive only`) and `MultipleInstancesPolicy: IgnoreNew`. The poller runs
with `RunLevel: HighestAvailable`; all others default.

`ExecutionTimeLimit`: gateway `PT0S` (unlimited, it is a daemon); the rest carry
the scheduler default (~72 h) — the scan launchers are themselves bounded
(`--timeout 1800`).

## 2. Two material deployment findings (recorded, not changed)

**(a) Battery gating.** Seven of eight tasks have
`DisallowStartIfOnBatteries = true` and `StopIfGoingOnBatteries = true`. On a
laptop running on battery, the queue poller, Discord sync, the daily brief and
all four regional scans will not start, and will stop if the machine goes on
battery while they run. Only `Hermes_Gateway` is exempt. For any unattended
laptop-primary topology this must be changed to `false` (a small, reversible
`schtasks /Create /XML` re-import) — it is **not** changed here because it is a
service change and the topology is undecided.

**(b) Reboot persistence is unverified for everything but the gateway.** Only
`Hermes_Gateway` has a logon trigger; `HermesRemoteQueuePoller` and
`ChiefDiscordSync` have time triggers with no logon/boot trigger and no
`StartWhenAvailable`, so their survival across a reboot is **not verified**.
Proving it needs an owner-initiated reboot, which this task's stop conditions
prohibit. Recorded as owner-actions item 6.

**(c) Interactive-token constraint.** Every task runs under the owner's
interactive logon. None of them runs for a signed-out user. No engineering change
can alter that without an owner-approved service-account/credential change — this
is a hard constraint on unattended operation.

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
