# Tool-loop forensic takeover — stop live guessing, reproduce from fixture

Date: 2026-09-29
Branch: `fix/e3-whole-repo-architecture`
Frozen starting head: `b52b2402e4ef3321205e6d404f04644e7b08977d`

## Current truth

Working and already live-proven:
- Chief routing
- persistent owner/project context
- Career Ops deterministic routing
- E3 provider registration and binding
- provider=e3 / model=e3-auto
- Stage 2 enabled for longcat-2.0 only
- OpenRouter disabled
- gateway connectivity

Still failing:
- native Hermes tool/skill loop
- live symptom: LongCat emits tool intent, but Hermes executes zero tools

Do NOT reopen or redesign working subsystems.

## Mandatory strategy

No more speculative live patches.

Do not spend another provider call until the exact failed live response path is reproduced offline from a sanitized fixture.

## Step 1 — freeze and collect evidence

From the most recent failed tool-loop run, collect without making a new provider call:

1. Gateway log lines for that request.
2. E3/LongCat dispatch record for that request.
3. The exact sanitized LongCat assistant response body/content as received by the adapter.
4. The exact Python object returned by the E3 provider client to Hermes.
5. Whether Hermes called the client with stream=True or non-streaming mode.
6. Any stream/chunk normalization performed after E3ModelClient returns.
7. The exact point where tool intent is lost:
   - adapter response parse
   - E3 service return
   - E3ModelClient normalization
   - Hermes completion/stream wrapper
   - agent turn parser
   - tool executor gate

Never record secrets or raw credentials.

## Step 2 — create a fixture

Create a repo fixture containing only the sanitized failed provider response and required metadata.

The fixture must preserve:
- exact tag name
- exact JSON shape
- surrounding text if any
- finish_reason if present
- whether the response was streamed
- model/provider identity

No invented or simplified shape.

## Step 3 — reproduce through the REAL production parsing stack

Build one offline test that feeds the captured fixture through the same path used live:

LongCat response
→ generic_openai_adapter result
→ E3 chat transport
→ E3ModelClient
→ any Hermes streaming/completion adapter
→ Hermes agent turn parser
→ native tool_calls detection

The test must fail at the same point as live before any fix is made.

Do not use a fake E3 result that starts after the broken layer.

## Step 4 — fix only the proven loss point

Once the offline fixture reproduces the live failure, patch the smallest proven boundary.

Requirements:
- only current-request offered tools may become executable
- malformed/unknown tool markup remains non-executable
- Hermes remains the tool/approval executor
- second post-tool iteration remains intact
- no permissive parser
- no provider or architecture redesign unless the fixture proves it is necessary

## Step 5 — offline gate

Run:
- the new captured-fixture regression
- Hermes/E3 tool-loop tests
- E3 chat transport tests
- architecture audit
- directly affected tests only

Zero provider calls.

Do not deploy until the captured-fixture regression passes through the full production parser path.

## Step 6 — one final live acceptance

Only after offline reproduction is green:

- deploy the minimal changed runtime files
- provenance drift = 0
- provider=e3
- model=e3-auto
- Stage 2 = longcat-2.0 only
- OpenRouter disabled
- restart gateway once
- send exactly one read-only tool-loop request

Live call budget: maximum 2 LongCat calls total.

PASS requires:
1. first model turn produces native Hermes tool_calls
2. Hermes executes a real read-only tool
3. tool result returns into the conversation
4. second LongCat turn returns final text
5. no OpenRouter
6. no duplicate response

If the fixture cannot reproduce the live failure, stop and report the missing runtime evidence instead of making another speculative patch.

## Contributor instruction

The next contributor should treat this as a forensic debugging task, not an architecture rebuild.

Do not modify:
- Career Ops
- persistent context
- Google image routing
- schedules
- Stage 2 policy
- provider auth
unless the captured fixture proves one of them is directly involved.
