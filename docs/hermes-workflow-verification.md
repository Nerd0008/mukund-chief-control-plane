# Verify Hermes context and worker handoffs

Run with the existing Hermes virtual environment from the repository:

```powershell
& "$env:LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" scripts/verify_hermes_workflow.py
```

This is an offline acceptance suite, not a claim of live model or Discord acceptance. It tests real request assembly, full-reference delivery, continuation across recreated sessions, missing sources, private/public boundaries, qualification, and stage handoffs. Providers are replaced with fixtures in these tests. Its JSON explicitly reports `live_model_acceptance: false`.

Inspect the most recent real lead request separately:

```powershell
& "$env:LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" scripts/verify_hermes_workflow.py --latest
```

Use `--session-id <native-session-id>` to restrict that inspection. It reads code-written context events and matching worker receipts. A missing source creates a failed event before routing. Old evidence is marked stale after 30 minutes. A completed worker and verified context produce `PATH_VERIFIED_ANSWER_NOT_GRADED`, not a claim that the answer is correct. Raw profile text is never included in this output.

For a human memory check, choose a detail that appears only in an old saved reference, not the current chat or memory summary. Ask for that detail and its original source. Then use a vague follow-up, recreate/resume the session and ask again. Independently compare the answer against the original source. A remembered career goal already repeated in the current conversation is not a useful holdout.

## Changed behavior

- Native controller admission uses Hermes token/multimodal accounting, explicit output reservation and a conservative safety margin. It never removes tools or truncates messages to manufacture compatibility. Actual capacity failures use native context-overflow recovery; output-budget and protocol failures are separate.
- The configured primary requires the same current qualification as its alternatives. Withdrawn, expired or unqualified models cannot bypass that gate.
- Owner-reference requirements persist per native session. Pre-upgrade sessions can bootstrap from actual owner turns, never assistant or tool text. Public workflows exclude private personal context. Delegated children receive only the context the lead supplies explicitly.
- Full selected source bytes must be present in the native system/developer request before dispatch. Code records coverage and hashes without storing private source text in telemetry.
- Chief's older context compiler distinguishes full-source identity from included-content hashes, omitted sources and coverage. Explicit required sources cannot pass validation when truncated. This does not activate the older E3 provider or expand Stage-2 permissions.
- LinkedIn research and writing have different transport contracts. Codex research requires an observed native search event; Google research requires matching grounding metadata. An unavailable or failed researcher is not reported as an empty list of topics.
- Research output hashes bind writing handoffs. Changed/invented handoffs stop before the writer. Existing source caching, factual checks, approval and publishing guards remain authoritative. A nonempty draft passes only the writing-stage shape check; it is not approval or factual acceptance.
- LinkedIn professional context uses the existing authoritative references rather than an older independent persona file. No fabricated numeric quality scores are emitted.

## Boundaries

Hermes remains the session/tool-loop controller. The RouterBrain remains a provider-neutral selector, not the owner-memory store. Native function-call protocols are not emulated through a plain CLI. Domain adapters perform explicit bounded stages. This change does not make every arbitrary third-party script into a fully coordinated multi-stage workflow, replace model-quality evaluation, enable audio, change the default provider, alter CV rendering, or publish anything.

Failure checks must be retained when changing retrieval, request assembly, routing or workflow wrappers. Fresh live tests and deployment/hash evidence are separate from green unit tests. No passing test authorizes a post or application submission.

The existing two-minute routing-decision cache ignores moving success/latency counters. It still checks current health on every selection and dispatch, invalidates on failure, and binds task family, task, permission/capability contract and eligible candidates. This avoids paying for a fresh brain decision on each successful round of an unchanged stage.

Use the guarded gateway CLI for lifecycle operations:

```powershell
& "$env:LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" "$env:LOCALAPPDATA/hermes/exec-brain/hermes_cli.main_router.py" gateway restart
```

The native Windows CLI intentionally spawns its standard entrypoint rather than executing a registered task wrapper. The guarded CLI pins the shared Windows launcher to the mandatory router wrapper, preserving profile arguments and hidden-process handling. A changed native launcher contract is refused. The existing `Hermes_Gateway` scheduled launcher also points at this wrapper. Do not substitute an unguarded native start when testing deployment.

The persisted context contract includes the active owner request, not a generated answer. A history-free continuation therefore retains its purpose as well as required sources. Starting public work resets private workflow objectives. Reference blocks have an explicit closing frame so native system-message whitespace normalization cannot silently remove source bytes or cause a false coverage failure.
