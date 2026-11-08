# Codex takeover — E3 selector + Discord bridge repair and release gate

Date: 2026-09-28
Owner: Mukund
Repository: `Nerd0008/mukund-chief-control-plane`
Required branch: `fix/longcat-stage2-emergency`
Known branch head when this handover was written: `79194390`

## Owner intent

Finish the real Hermes model-selector path end to end. Do not ask the owner to shuttle individual failures back and forth. Reproduce, debug, test, and repair the branch autonomously until the offline release gate is clean, or until an owner-only external action is genuinely required.

The desired architecture is:

Discord inbound
→ Hermes `pre_gateway_dispatch`
→ E3 task fingerprint / model selector
→ Stage-2-approved, routable worker
→ provider execution
→ E3 verification
→ reply to the same Discord chat
→ return `{"action":"skip"}` so native Hermes/MoA/OpenRouter does not also run.

Native Hermes Mixture-of-Agents / OpenRouter is NOT the desired normal path.

## Current problem

After the latest selector/Discord-bridge changes, the owner ran:

```powershell
$env:PYTHONPATH = "$PWD\exec-brain"
python exec-brain\tests\test_e3_extended.py
```

and reported that `test_e3_extended.py` failed.

Do not ask the owner for a screenshot first. Reproduce the failure from the branch and diagnose it locally.

One likely test-fixture defect already visible from review: `TestDiscordE3Bridge` creates:

```python
platform = SimpleNamespace(value="discord")
gateway = SimpleNamespace(adapters={platform: adapter}, ...)
```

`types.SimpleNamespace` may be unhashable and therefore unsuitable as a dict key. VERIFY the actual failing traceback before changing it. Do not assume this is the only failure.

## Changes already made on this branch

Recent relevant commits:

- `87bbff61` — selector became roster-aware/evidence/task-fit scored; real provider/model identity instead of `unknown`.
- `edf329bc` — orchestrator passes WorkerRegistry into router and supports explicit gateway reply-content mode.
- `32d5581e` — verified provider content exposed only when an explicit gateway consumer requests it; audit/default surfaces stay redacted.
- `d6df207e` — candidate rankings surfaced for auditability.
- `0100049a` / `72b867a4` — Hermes `e3-discord-router` plugin added.
- `653d56e8` / `4abc592a` — selector/Discord bridge tests added and temp DB fixture corrected.
- `c353fd0c` — reversible bridge installer + LongCat evaluation capability preparation.
- `79194390` — verified-content gateway opt-in regression test.

Earlier branch work already had a clean release gate of 23/23 suites and 616/616 tests before these new selector/bridge changes.

## Files to inspect carefully

Primary:

- `exec-brain/e3_router.py`
- `exec-brain/e3_shadow_orchestrator.py`
- `exec-brain/e3_execution.py`
- `exec-brain/worker_registry.py`
- `exec-brain/capability_registry.py`
- `exec-brain/e3_team_assembly.py`
- `exec-brain/stage2_control.py`
- `hermes-plugins/e3-discord-router/__init__.py`
- `hermes-plugins/e3-discord-router/plugin.yaml`
- `scripts/install_e3_discord_bridge.py`

Tests:

- `exec-brain/tests/test_e3_extended.py`
- `exec-brain/tests/test_e3_execution.py`
- `exec-brain/tests/test_e3_shadow_orchestrator.py`
- any other E3/Stage-2/gateway-adjacent test touched by the changes.

Reference the current upstream Hermes hook contract if needed:
- user plugin directory requires `plugin.yaml` + `__init__.py`
- `pre_gateway_dispatch(event, gateway, session_store, **kwargs)`
- return `{"action":"skip"}` to suppress native agent dispatch
- hook fires before normal auth, so the plugin MUST preserve authorization by checking the existing gateway authorization helper before intercepting
- Discord replies may use `gateway.adapters[platform].send(chat_id, content, reply_to=...)`.

Do not modify NousResearch/hermes-agent itself unless absolutely necessary. Prefer the supported plugin surface.

## Required repair work

### A. Reproduce and fix the failing extended suite

Run from repo root with the correct import path:

```powershell
$env:PYTHONPATH = "$PWD\exec-brain"
python exec-brain\tests\test_e3_extended.py
```

Capture the actual failing test names and tracebacks. Fix root causes, not assertions merely to make them green.

### B. Audit the selector implementation

The selector must NOT be insertion-order / first-row sticky.

Requirements:

1. `E3Router._get_provider()` and `_get_model()` must resolve real values from WorkerRegistry.
2. Non-routable workers must not be proposed for production selection merely because capability rows exist.
3. Ranking must be deterministic and auditable.
4. Task fit must contribute to ranking.
5. Capability state/evidence must contribute.
6. Provider health may contribute only from evidence actually available; never fabricate health.
7. Stable worker-id tie-break is allowed only after meaningful score terms tie.
8. Stage-2 allowlist filtering must still occur before team assembly/execution.
9. A disallowed higher-ranked DeepSeek/Codex candidate must not bypass Stage 2.

Do not falsely mark any worker QUALIFIED.

### C. Audit the Discord bridge

The bridge must:

1. intercept Discord text messages via `pre_gateway_dispatch`;
2. leave slash commands/native control messages alone;
3. NOT bypass Hermes authorization (hook fires before auth);
4. load recent transcript context safely;
5. run E3 in a worker thread rather than block the gateway event loop;
6. use live Stage 2 state and E3 execution path;
7. return only content that passed E3 verification;
8. reply to the same Discord destination;
9. append the handled user/assistant turn to transcript because native dispatch is skipped;
10. return `{"action":"skip"}` after successful E3 handling;
11. also skip native Hermes after an E3-owned failure response so MoA/OpenRouter does not duplicate the turn;
12. fail safely if the E3 runtime is missing/unavailable;
13. never expose secrets/credential values;
14. retain a visible selected-worker footer during initial acceptance so the owner can prove routing; this can be made optional later.

Check whether Discord thread routing needs `chat_id`, `thread_id`, or adapter metadata on this Hermes version. Use the actual Hermes contract rather than guessing.

### D. Audit verified-content handling

Default execution/audit JSON must remain raw-content-redacted.

Only explicit gateway/UI consumers may request verified content. Content must only be returned when:
- node state is COMPLETE, and
- final verification is PASS, and
- provider content is non-empty.

Add/fix tests as needed.

### E. Audit installer

`scripts/install_e3_discord_bridge.py` must:
- make no provider calls,
- never read/print credential values,
- back up an existing plugin before replacement,
- install under the correct user Hermes plugin root,
- prepare LongCat capability rows as EVALUATING only,
- not silently enable/change Stage 2,
- refuse capability preparation if deployed LongCat is not routable.

## Testing sequence

After repair, run at minimum:

```powershell
$env:PYTHONPATH = "$PWD\exec-brain"
python exec-brain\tests\test_e3_extended.py
python exec-brain\tests\test_e3_execution.py
python exec-brain\tests\test_e3_shadow_orchestrator.py
python scripts\tests\test_status_consistency.py
```

Then run the full release regression ONCE:

```powershell
python scripts\evidence_runner.py --label e3-discord-bridge-codex-release
```

If canonical-status evidence reconciliation creates the known self-referential newer-evidence failure, reconcile/supersede diagnostic evidence properly. Do not enter an endless evidence-run loop. The final clean release run should be the final full regression.

Expected test count may now be greater than 616 because new tests were added. Report exact suite/test counts rather than assuming a number.

## Git / worktree discipline

- Work only from `fix/longcat-stage2-emergency` or a dedicated worktree based on it.
- Do not overwrite unrelated owner changes.
- Keep commits focused and descriptive.
- Push repaired commits to `origin/fix/longcat-stage2-emergency`.
- Do not merge to main unless owner explicitly asks.
- Do not delete evidence; diagnostic runs may be moved to the established superseded area when appropriate.
- Do not rewrite history unless required for the existing emergency-worktree workflow and safe to do so.

## Production safety / stop conditions

DO NOT:
- paste/read/export provider secret values;
- change provider billing/subscriptions;
- buy/configure OpenRouter;
- spend provider calls merely for debugging;
- enable or alter Stage 2 production state during the repair phase;
- restart/modify Discord production gateway until offline tests and full regression are clean;
- mark LongCat or any worker QUALIFIED based on smoke/readiness alone;
- use Codex to make unrelated Career Ops changes.

Provider calls during the repair phase: ZERO unless an existing test unexpectedly performs one; if so, stop and fix the test/harness instead.

## Terminal success result

Codex should finish by reporting:

1. exact root cause(s) of the original `test_e3_extended.py` failure;
2. files changed and commits pushed;
3. focused test results;
4. full regression exact suite/test counts with zero failures/unavailable;
5. selector behavior now proven by tests;
6. Discord bridge behavior now proven offline;
7. whether any owner action is required;
8. exact next activation steps, BUT DO NOT execute activation yet.

Only owner-only external blockers justify stopping early. Otherwise continue debugging autonomously until the offline release gate is clean.
