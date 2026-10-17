# Hermes English response enforcement — 2026-10-17

The previous native `run_conversation` wrapper injected an English policy at API time but did not validate returned text. Existing tests verified prompt injection, not model compliance. Discord also exposed a separate raw reasoning callback. Coherent Chinese prose is not evidence of a Windows code-page problem.

The updated wrapper retains API-time policy and owner-context retrieval. It checks final and interim response text, buffers streaming segments before display (including single-character deltas), and disables raw reasoning delivery during the turn. Explicit current requests to respond in Chinese/Mandarin are allowed. Quoted source blocks, fenced code and incidental names are preserved. Callback and prompt state are restored on success/failure.

This is a bounded Chinese-prose guard, not a universal language detector or a translator. If triggered it returns a truthful English notice, retains native task history, and records only an original-response hash in result metadata. It does not regenerate, rerun tools, repeat writes, or change task completion evidence. No automatic translation/model call was added. Streaming text is buffered until a complete segment/end of turn for validation; tool lifecycle notifications remain available.

Validation: 38 tests passed across test_hermes_response_language.py, test_hermes_gmail_tools.py and test_hermes_owner_context.py. No live test messages or provider calls were made. Gateway was gracefully drained while active_agents=0 and restarted once through the existing hidden Hermes_Gateway scheduled launcher. The enabled career-gmail-local plugin imports the canonical repository source.

Scope: only response-language enforcement and tests. No provider, tracker, Gmail permissions, CV compiler or application-agent deployment changes. Unrelated dirty files were preserved. Original guard backup is private under Documents/Codex/language-recovery/20261017-205800/.

Owner correction: preserve native reasoning display and gate its text as well. All displayed channels now require English, including reasoning; explicit Chinese requests do not bypass the runtime guard. Native English reasoning is forwarded unchanged. No translation or additional provider call is added.

Follow-up: short-line/bullet loophole confirmed and closed with a strict Han-script check across the entire displayed payload, including quotes/code and single characters. This deliberately also blocks Han-script proper names. The native gateway image enrichment prompt allowed Chinese or English; changed to English only after a verified backup. This is a plausible language-drift contributor, not proven attribution for every incident. A versioned patch is retained at career-ops/patches/hermes-english-vision-prompt.patch; future Hermes upgrades must retain/revalidate it. Native vision method is exercised offline with a stub, with zero vision/provider calls.
