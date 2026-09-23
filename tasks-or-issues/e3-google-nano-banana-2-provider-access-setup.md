# Task — Configure Google Nano Banana 2 for E3 execution

Status: ACTIVE
Created: 2026-09-23
Owner: Mukund / Executive Brain E3
Worker: Google Nano Banana 2
Stage: Pre-Stage-2 provider readiness

## Identity

Human/roster label:
- Google Nano Banana 2

Current official Gemini API model ID:
- `gemini-3.1-flash-image`

This ID must still be confirmed live from the provider before being treated as authoritative runtime identity.

## Readiness checklist

- [ ] Local Google/Gemini API credential presence checked without exposing value
- [ ] Credential stored in approved local secret store
- [ ] API authentication verified
- [ ] Live model discovery/availability check succeeds
- [ ] Exact API model ID confirmed
- [ ] E3 Google image ExecutionAdapter implemented
- [ ] Minimal harmless image-generation smoke test PASS
- [ ] Returned provider/model identity recorded
- [ ] Provider-returned usage captured where available
- [ ] E2 `record-request` linkage PASS
- [ ] Generated smoke-test artifact stored only in temporary/local test path
- [ ] No credential or raw secret appears in logs/GitHub
- [ ] Worker registry updated truthfully
- [ ] E1 regression PASS
- [ ] E2 regression PASS
- [ ] E3 regression PASS
- [ ] Stage-2 readiness documented

## Current policy

Until all execution-readiness requirements are met:

- `routable = false`
- qualification = `UNPROVEN`

Roster inclusion does not imply routability or qualification.

## Credential policy

- Never paste the API key into ChatGPT, Discord, GitHub, source, prompts, or logs.
- Store the API key locally using the approved Windows secret-storage pattern.
- Environment variables may be supported only as a fallback where required.
- Presence checks report yes/no only.

## API / execution expectations

Use the current official Gemini API image-generation interface for Nano Banana 2.

Expected model:
- `gemini-3.1-flash-image`

Current official API supports image generation through Gemini native image generation / generate-content style interfaces.

The adapter must be distinct from E2 telemetry.

It should capture, when provider-returned:
- model ID
- response/request ID
- prompt/input token usage
- output token/image token usage
- total usage
- finish/status
- runtime
- provider error class
- output MIME/type
- generated artifact metadata

Do not estimate usage if the provider returns actual usage.

## Smoke test

Run one harmless deterministic-enough image-generation test.

Suggested prompt:
`Create a plain white square image containing one centered black circle. No text, no other objects.`

Validation should check at minimum:
- request succeeds
- image bytes are returned
- MIME/type is image
- artifact is decodable
- dimensions are non-zero
- provider/model identity is captured

Do not treat subjective visual quality as qualification at this stage.

Smoke-test success proves execution readiness only.

## E2 linkage

Actual execution must be reported through the E2 public `record-request` interface.

E3 must not directly SQL-write to governor.db.

Monetary cost remains UNKNOWN unless deterministically available from existing E2/provider configuration.

## Close condition

Close only after:
- authentication works,
- correct live model is confirmed,
- E3 execution adapter works,
- smoke test passes,
- provider usage/metadata is captured where exposed,
- E2 linkage passes,
- registry state is truthful,
- regressions pass,
- commit is pushed.

Qualification remains UNPROVEN after setup.
