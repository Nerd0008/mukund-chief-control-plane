# Restart / boot persistence validation

- Run (UTC): 2026-09-24T22:21:52+00:00
- Live state modified: False (read-only)

| Task | State | Triggers | StartWhenAvailable | survives boot |
|---|---|---|---|---|
| Hermes_Gateway | Enabled | logon | True | yes |
| HermesRemoteQueuePoller | Enabled | logon,time | True | yes |
| ChiefDiscordSync | Enabled | logon,time | True | yes |
| ChiefCareerBrief | Enabled | calendar | True | yes |
| ChiefCareerScan-UK | Enabled | calendar | True | yes |
| ChiefCareerScan-Dubai | Enabled | calendar | True | yes |
| ChiefCareerScan-Japan | Enabled | calendar | True | yes |
| ChiefCareerScan-Singapore | Enabled | calendar | True | yes |
| ChiefOperationalBackup | Enabled | calendar | True | yes |
| ChiefLogRotation | Enabled | calendar | True | yes |
| ChiefMorningBrief | Enabled | calendar | True | yes |
| ChiefHealthSnapshot | Enabled | calendar | True | yes |
| Mukund Chief of Staff | Disabled | logon | True | yes |

## Owner checklist items

- Hermes_Gateway [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- HermesRemoteQueuePoller [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefDiscordSync [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerBrief [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-UK [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-Dubai [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-Japan [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-Singapore [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefOperationalBackup [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefLogRotation [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefMorningBrief [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefHealthSnapshot [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)

Recorded only — no scheduled task was created, modified, started, stopped or deleted by this run.
