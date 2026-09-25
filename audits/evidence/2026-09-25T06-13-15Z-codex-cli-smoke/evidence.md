# Codex CLI worker — fresh smoke re-verification (2026-09-25)

- Task: `agent-codex-cli-smoke-2026-09-25` (verification only)
- Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
- Captured: 2026-09-25T06:13:15Z (dispatch 06:13:25Z) on the local Hermes host
- Verdict: **PASS — execution readiness only.** Qualification unchanged: `UNPROVEN`.

## Scope actually exercised

- Worktree inspected before starting: `git worktree list` shows a single worktree
  (`C:/Users/mukun/Documents/mukund-chief-control-plane 891a344 [main]`); no agent-* worker
  process was running (`codex.exe`, `python.exe`, `node.exe` all absent); the only other entry in
  `remote-queue/running/` is the umbrella placeholder `full-operational-build-2026-09-24.json`.
- Provider configuration was NOT changed. E3 Stage 2 was NOT enabled. No production dispatch path
  was touched. No retries, and exactly one Codex model execution was spent.
- Adapter used unchanged: `%LOCALAPPDATA%\hermes\exec-brain\codex_adapter.py`,
  SHA-256 `4926464a5dd30f25543caee3e5607d090b822a61f7f980a5f9c3f7752e5c4e83`, byte-identical to
  the repo copy `exec-brain/codex_adapter.py` (same SHA-256). No code was rewritten.

## Sanitized evidence

- Resolved executable: `%LOCALAPPDATA%\hermes\node\codex.CMD` (resolved via PATH by the existing
  resolver; the validated `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe` candidates remain the
  documented fallback). Health check: `healthy`.
- CLI version: `codex-cli 0.156.1` (the 2026-09-23 evidence recorded `0.155.0-alpha.16.3`; the CLI
  has been updated on this host since).
- Authentication presence: `codex doctor --json` → auth configured, auth mode `chatgpt`, storage
  mode `File`, stored API key `false`; `scripts/codex_identity_contract_check.py` →
  `codex login store present=True (content never read)`. No token, credential value, or
  secret-store content was read, logged, or committed.
- Identity (only what is directly exposed): provider `openai`
  (`observed:network.websocket_reachability`), observed provider name `OpenAI`. Served model stays
  **UNKNOWN** (`server model present=false`) — the config declaration `gpt-5.6-terra` is recorded
  only as `configured_model` and is never promoted to execution identity.
- Execution: one non-interactive `codex exec --json` under the **safe** profile
  (`--sandbox workspace-write`, `--skip-git-repo-check`), objective `Reply exactly CODEX_SMOKE_OK`,
  working directory `%LOCALAPPDATA%\hermes\cache\scratch\codex_smoke_2026-09-25` (isolated scratch),
  timeout 180 s, contract id `codex-cli-smoke-2026-09-25`.
  - exit code `0`, status `COMPLETED`, runtime `7.80 s`
  - final assistant message: `CODEX_SMOKE_OK` (exact match)
  - dispatch id `codex-15356c594d58`, thread `01a0d732-7f48-7370-bdec-08231bc7d236`
  - stdout event types: `thread.started`, `turn.started`, `item.completed`, `turn.completed`,
    `item.completed` item type `agent_message`
  - `stderr_present = true`; the stderr stream was not persisted in this run (content not captured
    — see limitations)
- Provider-returned usage **exposed** on `turn.completed` and captured: `input_tokens 19201`,
  `cached_input_tokens 12032`, `cache_write_input_tokens 0`, `output_tokens 9`,
  `reasoning_output_tokens 0`. Nothing estimated or fabricated.
- E2 linkage result: **VERIFIED** — `governor.record_request()` (public E2 interface, no direct E3
  SQL write) returned request id `obs-20260925-39ed6ee5`; read-back (read-only) confirms the row
  exists, provider `openai-codex-cli`, status `success`, latency 7799 ms. See `e2-readback.json`.
- `routable` computed `true` (execution readiness + verified linkage). **No canonical
  qualification or production state was changed by this task**; qualification remains `UNPROVEN`.

## Findings / honest residual

1. **Proven adapter defect (usage key mismatch), NOT fixed here.** `report_usage_to_e2()`
   (exec-brain/codex_adapter.py:562) reads `result["usage"]`, but `dispatch()` stores the
   provider-returned usage under `result["usage_tokens"]` (codex_adapter.py:347). Consequence: the
   E2 row for this request has `input_tokens`/`output_tokens` NULL and `total_tokens` 0 even though
   the provider DID return usage and the adapter DID capture it. This task's scope forbade
   rewriting the adapter, and the single permitted execution had already been spent, so the defect
   is reported rather than fixed. Recommended follow-up: one-line key fix plus a unit test that
   asserts the E2 payload carries the exposed token values (verifiable offline from the recorded
   JSONL fixture, no Codex spend).
2. `stderr` was non-empty but its content was not persisted by this run's capture script. The
   adapter's terminal status was `COMPLETED`, `exit_code 0`, and no error item appeared in the
   event stream, so this is not an execution failure; the exact text is simply unavailable.
3. Resolver order (PATH first) now selects the `node\codex.CMD` shim rather than the installed
   `OpenAI\Codex\bin\<hash>\codex.exe` build. Both validate via `--version`; the shim works, so this
   is recorded as an observation, not a defect.
4. Smoke PASS proves execution readiness only. Qualification remains `UNPROVEN` — no cold-start /
   task-role benchmark evidence was produced by this task.
5. E3 Stage 2 remains NOT ENABLED; production dispatch unchanged.

## Artifacts

- `evidence.json` — full sanitized run record
- `codex-exec-jsonl.jsonl` — the Codex event stream (4 events; no secrets)
- `e2-readback.json` — read-only verification of the E2 row
