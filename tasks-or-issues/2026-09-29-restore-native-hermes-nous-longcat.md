# Owner decision — restore known-good native Hermes Nous/LongCat provider path

Date: 2026-09-29
Owner: Mukund
Status: APPROVED

## Reason

The custom Hermes `provider=e3 / model=e3-auto` path has repeatedly failed at the native Hermes tool-call boundary.

Repository history records a previously operational native Hermes setup on 2026-09-21:

- `model.provider=nous`
- `model.base_url=https://inference-api.nousresearch.com/v1`
- `model.default=meituan/longcat-2.0:free`
- Hermes/Discord gateway recorded as working

Historical evidence also records why that path later stopped working on 2026-09-23:
- Hermes launched successfully and reported `meituan/longcat-2.0:free`
- Nous OAuth refresh-token exchange failed
- a fresh Nous device-code login then hit HTTP 429

That was an authentication/session failure, not evidence that Hermes' native tool loop itself was architecturally incompatible with LongCat.

## Decision

Restore the native Hermes provider path instead of continuing to emulate Hermes' chat/tool protocol through the custom E3 provider.

Active Hermes inference target:

```
provider = nous
base_url = https://inference-api.nousresearch.com/v1
model = meituan/longcat-2.0:free
```

Use Hermes' native Nous provider/auth/model-selection flow. Do not implement another custom parser, provider shim, or E3-as-provider compatibility layer.

## What stays

Do NOT roll back the whole project.

Keep:
- Chief persistent context assets
- E1/E2
- E3 planner/router/qualification/execution architecture
- Career Ops and regional workflows
- current schedules
- Google Nano Banana as separate image capability
- source-controlled provider evidence
- Stage-2 state/history
- Discord gateway
- owner/company/project context
- OpenRouter disabled as an automatic fallback

E3 remains the orchestration/selection layer for explicit AI subtasks and department workflows. It is NOT the active Hermes LLM transport.

## What changes

1. Back up current Hermes config/auth state.
2. Remove the active binding `provider=e3 / model=e3-auto` from the live Chief profile.
3. Restore native Hermes Nous binding:
   - provider `nous`
   - base URL `https://inference-api.nousresearch.com/v1`
   - model `meituan/longcat-2.0:free`
4. Disable the user E3 model-provider plugin from active selection. Do not delete its source code or history.
5. Resolve Nous auth only through Hermes' supported native auth flow.
6. If the existing Nous credential/session refreshes successfully, continue.
7. If Nous auth is expired/broken, perform only the native Nous re-authentication flow. Do not modify E3/tool parsing code.
8. Do not enable OpenRouter/MoA fallback.

## Preflight before any live acceptance

Zero model calls if possible.

Verify:
- Hermes resolves provider `nous`
- model resolves to `meituan/longcat-2.0:free`
- native Hermes agent initializes
- native Hermes tool definitions are present
- gateway config reads the restored provider/model
- E3 provider plugin is not selected
- no OpenRouter provider selected

If native Nous authentication requires an interactive owner login, stop only for that login and report the exact action required.

## Live acceptance

After native provider/auth preflight passes:

Send exactly ONE read-only Hermes tool-loop acceptance through Discord #chief.

Do not repeat Career Ops or persistent-memory acceptance.

PASS requires:
- Hermes native Nous/LongCat model turn
- native Hermes tool call recognized without E3 parsing shim
- at least one real read-only Hermes tool executes
- tool result returns to the native agent loop
- final response completes
- no OpenRouter
- no E3 provider shim on the model transport path

Maximum live test budget: 2 model turns (tool request + post-tool final response). No blind retry.

## Architecture after restoration

```
Discord
  -> Hermes native agent/tool loop
  -> Nous / meituan/longcat-2.0:free
  -> Hermes tools/skills/approvals

Chief / departments / workflows
  -> deterministic ownership
  -> E3 when an explicit AI subtask needs routing/selection
  -> approved worker
```

E3 must not replace Hermes' native chat transport.

## Completion

Return:
- active provider/model
- auth status
- gateway PID/state
- tool invocation count
- model call count
- whether E3 provider shim is inactive
- final OPERATIONAL/BLOCKED verdict

Do not redesign the architecture unless the restored native path itself produces a new reproducible failure.
