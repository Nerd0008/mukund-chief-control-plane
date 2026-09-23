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
