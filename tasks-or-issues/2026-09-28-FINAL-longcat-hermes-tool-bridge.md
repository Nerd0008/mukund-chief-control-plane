# FINAL tool-loop repair — bridge LongCat serialized tool markup into native Hermes tool_calls

Date: 2026-09-28
Branch: `fix/e3-whole-repo-architecture`
Starting live code commit: `a842de783881d1e5f6f096d6a1ea1b7c9359ed07`

## Scope

Fix ONLY the remaining Hermes tool-loop failure.

Already PASS and must not be reopened:
- persistent Chief owner/project context;
- Career Ops deterministic routing;
- Stage 2 LongCat-only enablement;
- E3 provider discovery/auth/runtime initialization;
- OpenRouter disabled;
- Career schedules.

## Exact failure

Native Hermes agent now initializes with:
- provider=e3
- model=e3-auto

One live LongCat call occurred.

LongCat returned serialized tool-call markup as ordinary assistant text. Because the E3 provider returned that text as `message.content` and did not expose native `message.tool_calls`, Hermes treated it as a final answer and executed zero tools.

## Important source finding

Hermes already contains a production bridge designed for providers/backends without a native OpenAI tool-call channel:

`agent/acp_openai_bridge.py`

Public helpers:
- `render_tool_bridge_sections(tools, tool_choice)`
- `extract_tool_calls_from_text(text)`
- `tool_specs_from_openai_tools(...)`
- `build_openai_tool_call(...)`

Reuse this bridge. Do NOT invent a second regex/parser.

## Required implementation

### 1. Render Hermes tool contract deliberately

In `exec-brain/hermes_e3_provider.py`, when Hermes supplies `tools`:

- call `render_tool_bridge_sections(tools, tool_choice)`;
- include those sections explicitly in the E3 objective/prompt sent to LongCat;
- do not rely on Python `repr(context)` as the tool contract;
- preserve Chief/persistent context and the Hermes conversation.

For the current and subsequent tool-loop iterations, include a bounded normalized transcript sufficient for LongCat to see:
- system/Chief context already permitted for this turn;
- user request;
- prior assistant tool-call intent;
- tool result rows;
- current available tool schema.

Do not duplicate massive prompts unnecessarily.

### 2. Convert LongCat tool markup to native Hermes tool_calls

After `E3ApplicationService.execute()` returns text:

If Hermes supplied tools:
- call `extract_tool_calls_from_text(result["content"])`;
- if valid tool calls are extracted:
  - validate each function name exists in the tools Hermes offered for THIS request;
  - preserve/normalize JSON-string arguments;
  - reject malformed or unknown tool names as ordinary text / safe failure — NEVER execute an unavailable tool;
  - set assistant content to the cleaned text returned by the bridge;
  - expose the extracted OpenAI `ChatCompletionMessageToolCall` objects as `message.tool_calls`;
  - set `finish_reason="tool_calls"`.

Do not execute tools inside E3. Hermes must remain the executor/approval owner.

Do not convert arbitrary prose into tool calls. Only use Hermes' existing parser and the current-request allowlist.

### 3. Preserve the second iteration

When Hermes appends:
- assistant tool call
- tool result

and calls the E3 client again:

- do NOT rerun deterministic Chief/Career Ops action;
- use the existing `_has_tool_iteration()` branch;
- ensure the rendered bounded transcript includes the tool result;
- send the continuation through E3/LongCat;
- return the final assistant text normally.

### 4. Do not require native LongCat API tools for this repair

The current LongCat public Chat Completions docs do not document `tools` / `tool_choice` request fields even though the model release notes describe tool-calling capability.

Therefore:
- use Hermes' supported text bridge now;
- do not add unverified LongCat API fields merely because OpenAI-compatible providers sometimes accept them;
- do not switch endpoint/protocol;
- do not spend calls probing unrelated LongCat formats.

A later capability probe can test native API tool fields separately, but it is NOT required to make Hermes operational.

## Tests — ZERO provider calls

Add production-boundary tests using the REAL `E3ModelClient` path, not a fake-only shortcut.

Test A:
- Hermes supplies one safe tool schema, e.g. `status`;
- fake E3 returns:
  `<tool_call>{"id":"call_1","type":"function","function":{"name":"status","arguments":"{}"}}</tool_call>`
- E3 client returns:
  - content cleaned;
  - one native tool_calls entry;
  - finish_reason=tool_calls.

Test B:
- fake E3 returns a call for a tool NOT offered by Hermes;
- it must NOT become executable native tool_calls.

Test C:
- append assistant tool_call + tool result;
- second E3 invocation sees the tool result;
- deterministic Chief/Career action is not rerun;
- final text response uses finish_reason=stop.

Test D:
- malformed markup remains non-executable text.

Test E:
- existing persistent context/Career routing tests remain green.

Run:
- focused E3 provider/tool bridge tests;
- Hermes agent-loop tests;
- architecture audit;
- one final regression only if code touched shared E3 behavior.

## Deploy

After offline green:
- deploy changed E3 runtime module(s);
- reinstall user E3 provider only if plugin files changed;
- provenance drift must be 0;
- retain provider=e3 / model=e3-auto;
- Stage 2 remains `["longcat-2.0"]`;
- restart gateway once only if required.

## Live acceptance

Do not repeat memory or Career Ops tests.

Send exactly one read-only tool-loop request.

Budget:
- max 2 LongCat calls:
  1. tool-call turn;
  2. post-tool final turn.
- no blind retries.

PASS:
- first LongCat output is converted to native Hermes tool_calls;
- Hermes executes at least one real read-only tool;
- approval/tool policy remains Hermes-owned;
- tool result is returned to E3/LongCat;
- second LongCat response becomes final text;
- 0 OpenRouter calls;
- no duplicate response.

If the exact live markup shape differs from the standard Hermes ACP bridge format, capture a SECRET-FREE sanitized fixture from the response and extend the EXISTING Hermes bridge-compatible conversion only if it can be validated safely. Do not build a permissive parser.

## Final verdict

If the one bounded live tool-loop acceptance passes:
- mark Chief/E3 OPERATIONAL;
- do not reopen already-passed categories.

Return:
- commit;
- tests;
- tool invocation count;
- LongCat call count;
- gateway state;
- final verdict.
