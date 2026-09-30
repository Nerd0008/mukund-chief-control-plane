# Final local fix — remove stale CHIEF_E3_DISCORD_BRIDGE vendor interception

Date: 2026-09-30
Status: APPROVED REPAIR

## Proven symptom

Latest native Nous rollback acceptance showed:

- Discord message received: yes
- AIAgent/session created: no
- provider=nous resolved: no
- Nous credential resolved: no
- model request built: no
- model calls: 0
- gateway still logged: `response ready ... api_calls=0`

This proves the request is being completed/intercepted before Hermes' native `_run_agent()` path.

## Historical patch that explains the symptom

Commit `029ea7bef7385ec195c809d0a990fc17b3c81f72` installed a vendor-source patch into:

`%LOCALAPPDATA%\hermes\hermes-agent\gateway\run_turn.py`

Marker:

`# CHIEF_E3_DISCORD_BRIDGE`

The patch inserted:

```python
bridge_result = await self._hmwa_try_chief_e3_dispatch(message_text, source)
if bridge_result is not None:
    agent_result = bridge_result
else:
    agent_result = await self._run_agent(...)
```

The helper intercepts ordinary Discord messages for Chief and can return an
`agent_result` with `api_calls=0`, preventing `_run_agent()` from ever
creating AIAgent or resolving the configured native provider.

The source-controlled installer was later retired, but retirement of the
installer does NOT remove an already-applied vendor patch.

## Required repair

NO PROVIDER CALLS.

1. Stop `Hermes_Gateway`.
2. Back up the CURRENT live:
   `%LOCALAPPDATA%\hermes\hermes-agent\gateway\run_turn.py`
3. Inspect it for:
   - `CHIEF_E3_DISCORD_BRIDGE`
   - `_hmwa_try_chief_e3_dispatch`
   - `bridge_result = await self._hmwa_try_chief_e3_dispatch`
4. If absent, STOP and report that this diagnosis is disproven. Do not edit anything.
5. If present, restore the original native gateway source.

Preferred restoration order:
- use the exact pre-patch backup created by the installer under:
  `%LOCALAPPDATA%\hermes\hermes-agent\gateway\backups\chief-e3-bridge-*\run_turn.py`
- choose the backup corresponding to the installed patch after comparing file content/timestamps;
- verify the restored file contains the ordinary native:
  `agent_result = await self._run_agent(...)`
  and contains NONE of the three stale bridge markers.

If a trustworthy pre-patch backup cannot be identified, do NOT hand-edit blindly.
Instead recover `run_turn.py` from the exact installed Hermes version/package
and compare before replacing.

6. Do not change:
   - provider/model config
   - Nous auth
   - E3 runtime
   - Career Ops
   - tool parsers
   - schedules
   - OpenRouter
7. Start `Hermes_Gateway` once.

## Zero-call preflight

Before sending Discord or making any provider call, verify:

- active provider = `nous`
- active model = `meituan/longcat-2.0:free`
- E3 provider shim inactive
- live `run_turn.py` has no `CHIEF_E3_DISCORD_BRIDGE`
- no `_hmwa_try_chief_e3_dispatch`
- normal message handling reaches the native `self._run_agent(...)` branch structurally
- gateway imports/starts without syntax/import error

## One live acceptance

Only after the zero-call preflight is green, send exactly ONE read-only Discord
tool-loop request.

Maximum model budget: 2 native Nous/LongCat turns.

PASS requires:
- AIAgent/session created
- provider=nous resolved
- model request built
- first model turn occurs
- native Hermes recognizes a tool request
- one real read-only tool executes
- tool result returns to agent
- second model turn returns final response
- no E3 model-provider shim
- no OpenRouter

If AIAgent is still not created after the stale bridge is removed, STOP and
report the next pre-agent interception point from logs; do not spend extra calls.
