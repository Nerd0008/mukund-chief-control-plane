# Activation blockers — execute Career Ops and preserve Hermes agent loop

Date: 2026-09-28
Branch: `fix/e3-whole-repo-architecture`
Starting commit: `029ea7bef7385ec195c809d0a990fc17b3c81f72`

Do not deploy yet. Two concrete live-path defects remain.

## Blocker A — Career Ops discovery only returns a plan

Current `exec-brain/department_dispatch.py` correctly recognizes Career Ops requests and parses regions/counts, but the read-only-discovery branch only returns a plan:

- workflow = `discovery.scheduled_orchestrator`
- regions/count
- read_only=true
- mode = offline-plan or live-activation-required

It never invokes the actual unified discovery workflow, even when `allow_external=True`.

Owner acceptance request:
`the whole agent I want 10 jobs from all the job search agents`

After activation, this must execute the existing bounded read-only discovery/orchestrator for UK/Dubai/Japan/Singapore and return actual workflow results, not prose saying a plan was created.

Requirements:
- reuse existing Career Ops unified scheduled/discovery orchestrator;
- preserve existing source budgets, dedupe, eligibility, read-only/tracker/application gates;
- no automatic tracker write/application;
- `dry_run=True` remains zero-network/zero-provider;
- live read-only mode may use its already-approved external search surfaces;
- semantic stages must still call E3, never choose provider/model directly;
- requested result count must bound returned results;
- all-region request must invoke all configured lanes through the unified workflow, not four ad-hoc reimplementations;
- errors must report per-region/source truthfully.

Add tests proving `allow_external=True` actually invokes an injected/real orchestrator interface and returns jobs/results, while dry-run never does.

## Blocker B — Chief bridge bypasses Hermes tools/skills agent loop

Current `scripts/install_discord_e3_bridge.py` patches the authenticated gateway at:

`agent_result = await self._run_agent(...)`

and replaces that with a direct call to `dispatch_chief_message()` for the Chief Discord channel.

This means the outer Hermes session/transcript machinery survives, but the actual Hermes agent/tool/skill loop is skipped for Chief turns. Setting context flags such as:
- `hermes_session_preserved=True`
- `hermes_tools_preserved=True`
- `hermes_skills_preserved=True`

does not make tools/skills available; those flags are metadata only.

This is not acceptable. Chief must retain Hermes tools, skills, approvals and agent loop while E3 owns model selection.

### Required architecture

Preferred:

```
authenticated Discord
 -> Hermes normal _run_agent / agent loop / tools / skills / approvals
 -> E3 model-selection/provider boundary
 -> selected Stage-2 worker
 -> result returned to Hermes agent loop
 -> tool iterations as needed
 -> final Discord reply
```

Do NOT intercept the whole turn and replace `_run_agent`.

Inspect current Hermes model-provider plugin/runtime provider extension interfaces first. Use the supported provider/plugin seam if it can preserve tool-call protocol and E3 verification. A model-provider plugin or equivalent E3-backed provider is strongly preferred over patching gateway message dispatch.

If provider-plugin integration is not sufficient, integrate E3 inside the agent's LLM/provider selection boundary, not above the agent loop. Any vendor patch must be:
- minimal;
- reversible;
- source-shape guarded;
- backed up;
- covered by exact-version tests.

Hard acceptance:
- normal Chief turn still enters Hermes agent loop;
- Hermes tools remain callable;
- Hermes skills/system context remain present;
- approval flow remains intact;
- E3 chooses the underlying Stage-2 worker/model;
- no native MoA/OpenRouter automatic fallback;
- no duplicate provider dispatch;
- transcript/session behavior remains normal;
- selected E3 worker/provider/model is observable in metadata/footer/logs.

Add an offline test with a fake Hermes agent/tool loop proving a Chief request can require a tool iteration and still route every model call through E3.

## Persistent context

Do not regress `ChiefContextCompiler` from `029ea7b`.
Before activation, add a zero-provider local preflight that reports only source IDs/counts/hashes (not private content) and confirms the live host resolves at least:
- owner context/local owner memory source;
- company registry;
- project state;
- Discord/Chief history when present.

If configured `HERMES_HOME` differs from the compiler fallback path, use Hermes' authoritative home-resolution logic or a deployment-provided explicit path rather than silently missing the sources.

## Validation

Zero real provider calls.

Run:
- focused department dispatcher tests;
- Chief/Discord integration tests;
- tool/skill preservation test;
- persistent-context source preflight test with synthetic/local metadata only;
- architecture audit;
- Career Ops tests relevant to unified discovery;
- E3 tests;
- final full regression once.

Do not mask the known unrelated Windows inherited-handle harness failures; report them separately if still present.

## Completion report

Push to the same branch and report:
- final commit;
- exact E3-in-Hermes integration seam;
- proof Hermes agent/tool/skill loop is retained;
- proof live-enabled Career Ops dispatcher actually executes unified read-only discovery;
- persistent context preflight result;
- focused/full test counts;
- provider calls = 0;
- exact deployment/rollback commands for the next activation turn.

Do NOT deploy/restart or re-enable career schedules in this repair.
