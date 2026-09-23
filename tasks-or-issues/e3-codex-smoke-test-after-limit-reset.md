# TODO — Re-run Codex CLI Stage 2 readiness smoke test

Status: PENDING_EXTERNAL_RESET
Created: 2026-09-23
Owner: Mukund / Executive Brain E3
Blocking: Codex ChatGPT usage limit

## Current verified state

- Codex CLI installed and authenticated.
- E3 Codex ExecutionAdapter implemented and hardened.
- Safe execution profile is the default.
- Exact underlying model identity remains UNKNOWN until observed deterministically.
- E2 usage linkage remains NOT_VERIFIED.
- Qualification remains UNPROVEN.
- `routable = false`.
- Previous smoke test result: `BLOCKED_USAGE_LIMIT`.
- E1/E2/E3 regressions: 117/117 PASS at last verification.

## Action when usage limit resets

1. Run one harmless deterministic Codex CLI execution smoke test.
2. Confirm the execution completes successfully.
3. Capture only supported provider/model identity metadata.
4. Do not infer or hardcode model identity if it remains unavailable.
5. Record observed execution usage through the E2 public `record-request` interface where data is available.
6. Do not fabricate token usage if Codex does not expose it.
7. Verify sanitized dispatch metadata contains no raw sensitive task content or credentials.
8. Re-run E3 tests and E1/E2 regressions.
9. Only after successful smoke test + required linkage checks may Codex execution readiness move toward `routable = true`.
10. Qualification remains UNPROVEN until cold-start evaluation evidence exists.

## Close condition

Close this TODO only after:
- smoke test PASS,
- adapter remains safe,
- E2 execution linkage is verified or truthfully documented as unavailable,
- registry status is updated,
- resulting commit is pushed and verified.
