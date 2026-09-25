# TODO — Re-run Codex CLI Stage 2 readiness smoke test

Status: CLOSED 2026-09-23 — smoke PASS; readiness re-validated
Created: 2026-09-23
Closed: 2026-09-23
Owner: Mukund / Executive Brain E3
Blocking: (resolved) Codex ChatGPT usage limit

## Result (agent-codex-reset-revalidation-2026-09-23)

- Executable: stable resolver replaced the stale hash-specific path. Resolved at
  `%LOCALAPPDATA%\OpenAI\Codex\bin\80f78947ad880e6e\codex.exe`, version `0.155.0-alpha.16.3`.
  The old `bin/247581e40ee272fb/codex.exe` no longer exists (Codex update) — hypothesis confirmed.
- Auth: `codex doctor --json` reports auth configured, auth mode `chatgpt`, storage mode File,
  stored API key `false`. No credentials or tokens were read, logged, or committed.
- Smoke: one harmless deterministic non-interactive `codex exec --json` returned `READY`
  (exit 0, thread `01a0cffb-4ca1-7052-babc-3db7a233ddac`, ~6.0 s, harmless prompt, no tools).
- Identity: provider `openai` deterministically reported. Served model NOT exposed
  (`server model present = false`) → execution model identity remains UNKNOWN.
  Local config declares `gpt-6-astra`; recorded only as `configured_model`, never as evidence.
- Usage: exposed by the CLI on `turn.completed` (16207 in / 5 out / 13184 cached). The E2 row
  was written before the extractor fix was verified, so its token columns are null; no second
  request was spent to correct it — the next real Codex execution will record tokens correctly.
- E2 linkage: VERIFIED — `obs-20260923-d42e34a5` recorded through the public
  `governor.record_request()` interface (no direct E3 SQL write into E1/E2 databases).
- Routable: `true` (execution readiness + linkage only). Qualification: `UNPROVEN`.
- Regressions: 271 collected / 271 passed / 0 errors across 7 suites
  (`audits/evidence/2026-09-23T20-38-25Z-codex-reset-revalidation/`).

## Honest residual / limitations

- Exactly two Codex executions were spent, not one: the first proved execution worked but exposed
  a parser defect in our own adapter (assistant text is emitted as an `item.completed` item of
  type `agent_message`, not `message`; usage is on `turn.completed`). The fix was then verified
  against the recorded real stdout, and the second run produced the canonical PASS evidence.
- Qualification remains UNPROVEN: no cold-start / task-role benchmark evidence exists yet.
- A stale copy of the pre-fix adapter still exists outside the repo at
  `%LOCALAPPDATA%\hermes\exec-brain\codex_adapter.py`. Nothing under the E3 test import root
  imports it; it should be resynced at the next deployment step.
- E3 Stage 2 remains NOT APPROVED / not enabled.

## Close condition

Met: smoke PASS; adapter safe; E2 linkage verified; registry status updated; commit pushed.

## Re-verification — agent-codex-cli-smoke-2026-09-25 (fresh smoke)

Status: CLOSED (re-verified 2026-09-25) — smoke PASS, execution readiness reconfirmed; qualification
still UNPROVEN; one adapter defect newly proven (not fixed in this verification-only task).

- Executable/version: resolved `%LOCALAPPDATA%\hermes\node\codex.CMD` via PATH by the unchanged
  resolver; `codex-cli 0.156.1` (host CLI updated since the 0.155.0-alpha.16.3 record). Health
  `healthy`; no code was rewritten (adapter SHA-256 `4926464a5dd30f…` identical to the repo copy).
- Auth: `codex doctor --json` auth configured / mode `chatgpt` / storage `File` / stored API key
  `false`; login store present (content never read). No credentials read, logged, or committed.
- Smoke: exactly ONE harmless non-interactive `codex exec --json` (safe `workspace-write` profile,
  bounding timeout 180 s, isolated scratch cwd, objective `Reply exactly CODEX_SMOKE_OK`) →
  exit 0, `COMPLETED`, final message `CODEX_SMOKE_OK`, 7.80 s, thread
  `01a0d732-7f48-7370-bdec-08231bc7d236`. No retries. Provider usage exposed and captured
  (19201 in / 12032 cached / 9 out).
- E2 linkage: VERIFIED — `obs-20260925-39ed6ee5` via the public `governor.record_request()`
  interface; read-only read-back confirms provider `openai-codex-cli`, status `success`.
- Routable `true` (readiness + linkage only). Qualification `UNPROVEN`. E3 Stage 2 not enabled;
  no production dispatch or provider configuration changed.
- Bounded check: `exec-brain/tests/test_e3.py -k Codex` → 10 passed / 49 deselected / exit 0.
- Open defect found (recorded, deliberately not fixed here): `report_usage_to_e2()` reads
  `result["usage"]` while `dispatch()` returns usage under `result["usage_tokens"]`, so the E2 row
  carries NULL token columns despite exposed usage. One-line fix + offline fixture test recommended
  as a separate task.
- Evidence: `audits/evidence/2026-09-25T06-13-15Z-codex-cli-smoke/` (`evidence.json`,
  `evidence.md`, `codex-exec-jsonl.jsonl`, `e2-readback.json`).
