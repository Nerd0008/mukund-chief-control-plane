# Final native Hermes provider hotfix — exact root cause

Date: 2026-09-28
Branch: `fix/e3-whole-repo-architecture`
Current live acceptance commit: `29b7a128bf6f133cfb19cebffcdf4e183a7d03b1`

## Exact root cause

The installed E3 model-provider plugin registers:

```python
auth_type="none"
```

Current Hermes `ProviderProfile` does NOT support `auth_type="none"`.

Hermes' documented/runtime-supported auth contracts include:
- api_key
- oauth variants
- aws_sdk
- external_process
(and other explicitly implemented built-in contracts)

The native agent loop resolves credentials/runtime BEFORE `ProviderProfile.create_client()` is used. Because `e3` advertises an unsupported auth type, provider resolution returns no usable LLM route and the native Hermes loop fails with:

`No LLM provider configured`

This is why:
- Chief persistent-context acceptance passed;
- Career Ops acceptance passed;
- native Hermes tool-loop acceptance failed before tool invocation.

Do not debug Career Ops, context, Stage 2, Google, or OpenRouter again unless this exact provider fix exposes a separate concrete failure.

## Required fix

Use a SUPPORTED Hermes provider auth/runtime contract for the local in-process E3 client.

Preferred solution for the installed Hermes version:

- use the supported custom-client / non-HTTP provider seam;
- `ProviderProfile.create_client()` must remain the actual client factory;
- no real HTTP endpoint is required;
- no secret credential should be invented;
- no vendor Hermes source patch.

If the installed Hermes version's supported seam is `external_process` for non-HTTP custom clients, it is acceptable to register E3 with that supported contract while `create_client()` returns the in-process E3 client. Use a guaranteed local executable for the launch-check (prefer the running Hermes Python executable / `sys.executable`) and do NOT actually spawn an unrelated process from `create_client()`.

Do not use `auth_type="none"`.

## Explicit Hermes model binding

After provider resolution is fixed, verify the active Chief Hermes profile is actually configured as:

- provider: `e3`
- model: `e3-auto`

Do not merely assert that the plugin is enabled.

Use Hermes' supported model/provider persistence path or the same config API it uses internally. Back up the existing model/provider configuration first.

Verify BOTH:
1. provider plugin is discoverable;
2. runtime resolution for `e3/e3-auto` returns a usable route/client.

## Mandatory local preflight BEFORE Discord

ZERO real provider calls.

On the live Hermes installation, run a deterministic preflight that proves:

1. `get_provider_profile("e3")` returns the E3 profile;
2. its auth type is one Hermes actually supports;
3. `resolve_runtime_provider("e3", target_model="e3-auto")` succeeds;
4. provider-supplied `create_client()` returns `E3ModelClient`;
5. native `AIAgent`/equivalent agent initialization with provider=e3, model=e3-auto succeeds without:
   - `No LLM provider configured`
   - OpenRouter fallback
   - network/provider call;
6. tool definitions survive into the client request using fake E3/worker adapters.

If any one of these fails, fix it BEFORE restarting/testing Discord.

Add/extend repo tests so `auth_type="none"` can never regress unnoticed.

## Deployment

Once preflight passes:

1. back up current user E3 provider plugin;
2. install repaired plugin into active `HERMES_HOME/plugins/model-providers/e3`;
3. deploy any changed source-controlled E3 runtime modules;
4. verify runtime provenance;
5. persist provider=e3, model=e3-auto for the Chief profile;
6. restart `Hermes_Gateway` ONCE;
7. inspect startup/runtime logs for provider resolution errors BEFORE sending Discord.

Do not change:
- Stage 2 allowlist (`longcat-2.0` only);
- Google image routing;
- Career Ops;
- schedules;
- OpenRouter state;
unless the provider fix itself proves one is directly involved.

## Live acceptance

Do NOT repeat the already-passed persistent-context or Career Ops tests.

Send exactly ONE bounded acceptance request: the read-only Hermes tool-loop status check.

PASS requires:
- native Hermes agent initializes using e3/e3-auto;
- first LongCat/E3 model call occurs;
- Hermes invokes at least one real read-only tool;
- tool result is returned to the agent loop;
- second model iteration completes final text;
- selected worker/provider/model recorded;
- no OpenRouter;
- no duplicate Discord response.

Maximum live provider-call budget: 2 LongCat calls for the tool-call + post-tool iteration. No blind retry.

## Completion

Return only:
- exact code commit;
- provider auth/runtime contract chosen;
- local preflight results;
- active provider/model;
- gateway state;
- tool-loop acceptance PASS/FAIL;
- tool invocation count;
- LongCat provider-call count;
- final verdict.

If this passes, mark Chief/E3 OPERATIONAL. Do not reopen already-passed acceptance categories.
