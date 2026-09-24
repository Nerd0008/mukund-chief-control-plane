# Restart / boot persistence validation

- Run (UTC): 2026-09-24T03:52:32+00:00
- Live state modified: False (read-only)

| Task | State | Triggers | StartWhenAvailable | survives boot |
|---|---|---|---|---|
| Hermes_Gateway | Enabled | logon | True | yes |
| HermesRemoteQueuePoller | Enabled | time | False | no |
| ChiefDiscordSync | Enabled | time | False | no |
| ChiefCareerBrief | Enabled | calendar | False | no |
| ChiefCareerScan-UK | Enabled | calendar | False | no |
| ChiefCareerScan-Dubai | Enabled | calendar | False | no |
| ChiefCareerScan-Japan | Enabled | calendar | False | no |
| ChiefCareerScan-Singapore | Enabled | calendar | False | no |
| Mukund Chief of Staff | Enabled | logon | True | yes |

## Owner checklist items

- Hermes_Gateway [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- HermesRemoteQueuePoller [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- HermesRemoteQueuePoller [battery_gating]: DisallowStartIfOnBatteries=true — will not run on battery; owner-aware re-import needed for laptop-primary topology
- HermesRemoteQueuePoller [add_logon_trigger]: no boot/logon trigger and StartWhenAvailable not set — persistence after reboot is unverified; add a logon trigger (small, reversible schtasks /Create /XML re-import)
- ChiefDiscordSync [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefDiscordSync [battery_gating]: DisallowStartIfOnBatteries=true — will not run on battery; owner-aware re-import needed for laptop-primary topology
- ChiefDiscordSync [add_logon_trigger]: no boot/logon trigger and StartWhenAvailable not set — persistence after reboot is unverified; add a logon trigger (small, reversible schtasks /Create /XML re-import)
- ChiefCareerBrief [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerBrief [battery_gating]: DisallowStartIfOnBatteries=true — will not run on battery; owner-aware re-import needed for laptop-primary topology
- ChiefCareerBrief [add_logon_trigger]: no boot/logon trigger and StartWhenAvailable not set — persistence after reboot is unverified; add a logon trigger (small, reversible schtasks /Create /XML re-import)
- ChiefCareerScan-UK [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-UK [battery_gating]: DisallowStartIfOnBatteries=true — will not run on battery; owner-aware re-import needed for laptop-primary topology
- ChiefCareerScan-UK [add_logon_trigger]: no boot/logon trigger and StartWhenAvailable not set — persistence after reboot is unverified; add a logon trigger (small, reversible schtasks /Create /XML re-import)
- ChiefCareerScan-Dubai [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-Dubai [battery_gating]: DisallowStartIfOnBatteries=true — will not run on battery; owner-aware re-import needed for laptop-primary topology
- ChiefCareerScan-Dubai [add_logon_trigger]: no boot/logon trigger and StartWhenAvailable not set — persistence after reboot is unverified; add a logon trigger (small, reversible schtasks /Create /XML re-import)
- ChiefCareerScan-Japan [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-Japan [battery_gating]: DisallowStartIfOnBatteries=true — will not run on battery; owner-aware re-import needed for laptop-primary topology
- ChiefCareerScan-Japan [add_logon_trigger]: no boot/logon trigger and StartWhenAvailable not set — persistence after reboot is unverified; add a logon trigger (small, reversible schtasks /Create /XML re-import)
- ChiefCareerScan-Singapore [keep_signed_in]: runs under the interactive user token; it does not run for a signed-out user (owner-side precondition for unattended operation)
- ChiefCareerScan-Singapore [battery_gating]: DisallowStartIfOnBatteries=true — will not run on battery; owner-aware re-import needed for laptop-primary topology
- ChiefCareerScan-Singapore [add_logon_trigger]: no boot/logon trigger and StartWhenAvailable not set — persistence after reboot is unverified; add a logon trigger (small, reversible schtasks /Create /XML re-import)

Recorded only — no scheduled task was created, modified, started, stopped or deleted by this run.
