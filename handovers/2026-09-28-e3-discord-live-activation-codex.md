# Codex live activation — E3 Discord model selector

Date: 2026-09-28
Owner: Mukund
Repository: `Nerd0008/mukund-chief-control-plane`
Branch: `fix/longcat-stage2-emergency`

## Verified offline release state

Offline recovery is complete.

Code commits:
- `8b37fe8` — E3 selector and Discord bridge hardening
- `7fffaa3` — watchdog fallback fix
- `28f7b01` — E1 runtime-boundary recognition

Evidence/status commits:
- `3e8bc24` — clean release evidence
- `872dfdc` — canonical status reconciliation

Authoritative clean evidence:
`audits/evidence/2026-09-28T09-25-15Z-e3-discord-bridge-codex-release/evidence.json`

Verified result:
- 23 suites run
- 23 suites passed
- 0 suites failed
- 0 suites unavailable
- 628 tests collected
- 628 tests passed

The evidence is bound to code SHA `28f7b018e95028a35f8305a1e4fe8f029822a027`. Later commits only add evidence/status reconciliation.

Owner authorization:
`tasks-or-issues/2026-09-25-discord-e3-selector-authorization.md`
contains `## LOCAL E3 STAGE 2 ENABLEMENT AUTHORIZED` and explicitly authorizes Discord→E3 integration and Stage 2 allowlist expansion for workers with current successful live execution evidence.

## Goal

Activate the already-tested architecture on Mukund's local host:

Discord inbound
→ Hermes `pre_gateway_dispatch`
→ E3
→ Stage 2 model selector
→ LongCat for general text
→ E3 verification
→ reply to same Discord conversation/thread
→ native Hermes/MoA skipped.

For this emergency activation, Stage 2 should contain:
- `longcat-2.0`
- `google-nano-banana-2`

Do NOT add Codex because owner currently wants Codex available for engineering/debugging rather than the normal production text route. Do NOT add DeepSeek because the previous live Hermes path was failing. Other providers can be added later after separate live readiness confirmation.

## Hard limits

- Do not buy/configure OpenRouter.
- Do not change provider subscriptions/billing.
- Do not read/print/export any secret values.
- Do not mark LongCat QUALIFIED. It remains EVALUATING.
- Do not run another full regression; 628/628 is the release evidence.
- Do not make unrelated repo/code changes during activation.
- Zero provider calls during setup/verification.
- Exactly ONE live provider execution is allowed for the final Discord acceptance message.
- If that one provider execution fails, stop and report rather than retrying/spending more quota.

## Step 1 — synchronize the activation worktree

Use a dedicated worktree already tracking `origin/fix/longcat-stage2-emergency`, or create one safely.

Fetch origin and ensure the code contains `872dfdc` (or a later documentation-only activation handover commit). Do not overwrite unrelated owner changes.

Record:
- repo/worktree path
- HEAD
- git status

## Step 2 — capture rollback state BEFORE mutation

Runtime:
`%LOCALAPPDATA%\hermes\exec-brain`

Create a timestamped activation backup directory outside the deployed module set, for example:
`%LOCALAPPDATA%\hermes\exec-brain\backups\discord-e3-activation-<timestamp>`

Back up, if present:
- `e3-stage2-state.json`
- `orchestration.db`
- existing user plugin directory `$HERMES_HOME/plugins/e3-discord-router` or `~/.hermes/plugins/e3-discord-router`

Do not copy/read secret stores.

## Step 3 — deploy the tested E3 runtime

From the release branch worktree:

```powershell
python scripts\deploy_e3_runtime.py --dry-run
python scripts\deploy_e3_runtime.py
```

Capture the deployment backup directory printed by the deployer.

Confirm deployed SHA-256/source manifest reports the new:
- `e3_router.py`
- `e3_shadow_orchestrator.py`
- `e3_execution.py`
- `worker_registry.py`
- `stage2_control.py`
- other normal E3 module set

Do not modify E2/governor secrets or credentials.

## Step 4 — install the Discord E3 bridge + LongCat EVALUATING rows

First:

```powershell
python scripts\install_e3_discord_bridge.py --dry-run
```

Verify the plugin target matches the Hermes home used by the live gateway.

Then:

```powershell
python scripts\install_e3_discord_bridge.py
```

This must:
- install `e3-discord-router`;
- back up an existing plugin if present;
- register LongCat capability rows as EVALUATING only;
- NOT alter Stage 2.

Then inspect:

```powershell
hermes plugins list
```

Confirm `e3-discord-router` is discovered. If it is explicitly disabled, enable only that plugin with the supported Hermes CLI and re-list it. Do not modify unrelated plugins.

## Step 5 — activate the emergency Stage 2 pool

Use the tested authorization/evidence:

```powershell
python exec-brain\e3_cli.py e3-stage2-enable `
  --approval-record "tasks-or-issues/2026-09-25-discord-e3-selector-authorization.md" `
  --regression-evidence "audits/evidence/2026-09-28T09-25-15Z-e3-discord-bridge-codex-release/evidence.json" `
  --allowed-worker longcat-2.0 `
  --allowed-worker google-nano-banana-2 `
  --confirm
```

Then:

```powershell
python exec-brain\e3_cli.py e3-stage2-status
```

Hard acceptance:
- `enabled: true`
- allowed workers are exactly `longcat-2.0` and `google-nano-banana-2`
- approval record is the Discord E3 selector authorization
- regression evidence is the 2026-09-28 clean 628/628 evidence

If anything differs, STOP before gateway restart.

## Step 6 — zero-call local routing checks

No provider calls yet.

Run:

```powershell
python exec-brain\e3_cli.py e3-execute `
  --objective "Return a short confirmation that the E3 text route is operational." `
  --family other `
  --role builder `
  --reasoning 1 `
  --risk R1 `
  --max-repair-attempts 0 `
  --timeout 90
```

WITHOUT `--confirm`.

Expected:
- dry-run message;
- routable Stage 2 pool includes LongCat;
- no provider request is made.

Also perform a read-only capability/selector inspection proving `longcat-2.0` is EVALUATING for `other/builder` and is the eligible text worker for a normal low-risk text task. Do not mutate state during this inspection.

## Step 7 — restart gateway once

Use the existing scheduled task, not a new service:

```powershell
SCHTASKS /End /TN Hermes_Gateway
SCHTASKS /Run /TN Hermes_Gateway
```

Wait for the gateway to report Discord connected.

Check gateway/plugin logs for:
- plugin discovery/registration;
- no import error for `e3-discord-router`;
- no immediate Stage 2 error.

Do NOT send a model request during startup checks.

## Step 8 — final owner acceptance: exactly one live provider call

At this point, tell the owner exactly:

> Send **one** normal Discord message to Hermes: `Reply with: E3 LIVE OK`

Do not use `/model`, `/retry`, or native MoA commands.

Observe the single turn.

PASS requires ALL of the following:
1. Discord message is intercepted by the E3 bridge.
2. Source is authorized through Hermes' existing authorization helper.
3. E3 candidate/assignment selects `longcat-2.0`.
4. Exactly one LongCat provider execution occurs.
5. E3 verification PASS is recorded.
6. Discord receives the verified response in the same conversation/thread.
7. Reply visibly contains the temporary acceptance footer:
   `E3 worker: longcat-2.0`
8. Native Hermes does not also respond.
9. No `moa_aggregator` / OpenRouter error is emitted for the turn.
10. Transcript receives the user + assistant turn.

If the provider execution was attempted and any PASS item fails, DO NOT retry. Preserve logs/evidence and stop with the exact failure stage.

If the failure happens strictly before any provider execution (e.g. plugin import/discovery), it is safe to debug the local integration without provider spend, but do not trigger a provider call until the local fault is fixed.

## Step 9 — rollback on failure

If live activation must be rolled back:
- restore the pre-activation `e3-stage2-state.json`;
- restore `orchestration.db`;
- restore/remove the user plugin to its pre-activation state;
- if runtime deployment itself caused the failure, use `scripts/deploy_e3_runtime.py --restore <deployment-backup-dir>`;
- restart `Hermes_Gateway`;
- verify the pre-activation state is restored.

Do not delete logs/evidence from the failed activation.

## Final report

Return:
- deployed git/code SHA
- runtime deployment backup path
- plugin target + discovery/enabled state
- exact Stage 2 state
- zero-call preflight result
- gateway restart result
- whether the single Discord acceptance was sent
- selected worker/provider/model
- E3 verification result
- Discord delivery/thread result
- proof native MoA/OpenRouter did not run
- provider calls consumed (must be 0 before acceptance and <=1 total)
- PASS/FAIL
- rollback state if FAIL

Do not call Hermes production-ready unless the real Discord end-to-end acceptance passes.
