# FINAL ALL-IN RECOVERY — Hermes Chief + E3 + Career Ops + Memory + Discord

Date: 2026-09-28
Owner: Mukund
Repository: `Nerd0008/mukund-chief-control-plane`
Working branch: `fix/e3-whole-repo-architecture`
Starting branch head: `5b9035c61190f7abde08a46d52f7af3fcfda4e92`

## Owner instruction

Fix the ENTIRE Hermes/Chief/E3 stack in one autonomous pass.

Do NOT stop after each ordinary code failure, test failure, import problem, plugin issue, path issue, runtime drift item, or integration defect. Debug and continue autonomously.

The owner does not want another sequence of one-by-one blocker handovers.

Only stop before completion if a genuinely owner-only action is required:
- credential entry,
- provider billing/purchase,
- destructive/irreversible operation,
- external account approval that cannot be completed locally,
- or a safety decision not already covered below.

Everything else is yours to finish.

## Owner approval for this recovery

The owner explicitly wants the system fixed and operational now.

You are authorized to:
- modify and push `fix/e3-whole-repo-architecture`;
- repair all code needed for the target architecture;
- install/update the source-controlled E3 provider/plugin into the supported Hermes user plugin location;
- deploy the tested E3/Chief runtime modules to the local Hermes runtime;
- restart `Hermes_Gateway`;
- clean up the stale E3 plugin copy previously installed into the Hermes vendor/bundled plugin tree, but ONLY after verifying it matches our plugin and backing it up;
- restore/re-enable the four `ChiefCareerScan-*` scheduled tasks IF their live definitions match the audited safe read-only unified launcher and all schedule safety checks below pass;
- perform the bounded live acceptance tests below.

Do NOT:
- buy/configure OpenRouter;
- change provider subscriptions/billing;
- expose/read/print secret values;
- merge to main unless owner separately asks;
- mark workers QUALIFIED without qualification evidence;
- weaken E1/E2/E3 safety/qualification/verification gates;
- create a VPS/cloud cutover;
- enable automatic application submission or tracker mutation beyond existing owner gates.

## Target architecture — must be true in live runtime

```
Discord / scheduled tasks / CLI / queue
        ↓
Hermes auth + session + transcript + tools + skills + approvals
        ↓
Chief intake / E1 policy
        ↓
deterministic department/workflow ownership
        ├─ Career Ops
        ├─ Company Watch
        ├─ application/status workflows
        ├─ tracker/scheduler/brief/queue services
        └─ other deterministic agents
        ↓ only when AI is required
E3 application/model boundary
        ↓
task fingerprint + context + capability/routability/Stage-2 gates
        ↓
E3 worker selection
        ↓
provider adapter/client
        ↓
E2 telemetry + E3 verification
        ↓
calling workflow / Hermes agent loop
        ↓
Discord / output
```

Hard rule:

**Chief/departments own workflows. E3 owns AI model selection and AI execution. Providers never get selected directly by business modules. E3 must never replace the Hermes agent/tool/skill loop.**

## Known history / defects that must all be closed

The following defects were discovered during previous passes. Do not assume any are fixed until verified in the current branch + live runtime.

### A. Old Discord raw-E3 interception
The old `pre_gateway_dispatch` plugin consumed every normal Discord message and sent it directly to E3/LongCat, bypassing Chief/Career Ops/persistent context.

This caused:
- job-search requests to become generic LongCat answers;
- owner-memory questions to use only recent transcript;
- native Chief agents/tools not to run.

The old raw interceptor is retired. Ensure it cannot regain control.

### B. Native Hermes MoA/OpenRouter fallback
Discord previously used native Mixture-of-Agents and failed with:

`No LLM provider configured for task=moa_aggregator provider=openrouter`

OpenRouter is NOT part of the target architecture.

Normal Chief operation must not automatically route to native MoA/OpenRouter.

### C. E3 selector defects
Earlier defects included:
- unknown provider/model identities;
- insertion-order / first-candidate stickiness;
- Stage-2 filtering after team assembly;
- capability rows without routability enforcement.

Verify current tests and code still enforce:
- real provider/model identity;
- deterministic evidence/task-fit scoring;
- WorkerRegistry routability;
- Stage-2 allowlist before selection/execution;
- no disallowed candidate bypass;
- auditable ranking/rationale.

### D. Persistent context dropped
The raw-E3 path only used recent Discord text.

Persistent memory belongs to Chief, not the provider.

Current target context sources include:
- live `mukund-owner-context` skill;
- live `mukund-company-registry` skill/reference;
- local owner memory/profile when present;
- canonical project/company state;
- bounded relevant Discord/Chief archive history;
- recent Hermes transcript;
- department/task-specific state.

Context must be:
- bounded;
- relevant;
- source-provenanced;
- provider-independent;
- secret-redacted;
- facts separated from inferences.

Do not hard-code owner facts into prompts or GitHub fixtures.

### E. Career Ops direct provider bypasses
Historical Career Ops code directly constructed DeepSeek/Codex adapters.

All semantic AI work must now use the shared E3 boundary.

Re-audit production code and leave zero unexplained business-layer direct provider imports/selection.

### F. Career Ops placeholder / plan-only routing
Past `DefaultDepartmentDispatcher` returned placeholder handoffs.
Later code recognized Career Ops but only returned a discovery plan.

Live Chief must actually execute the EXISTING unified read-only Career Ops discovery workflow when explicitly requested.

### G. Chief bridge/runtime source drift
Historically some Chief bridge modules existed only in runtime.

All production-owned Chief/E3 modules must:
- be source-controlled;
- be included in deployment manifest;
- have runtime provenance checks;
- support rollback.

### H. Wrong E3 provider install target
A previous installer copied the plugin into:

`C:\Users\mukun\AppData\Local\hermes\hermes-agent\plugins\model-providers\e3`

That is the bundled/vendor tree.

The supported third-party provider location is the active Hermes user/profile home:

`<HERMES_HOME>\plugins\model-providers\e3`

Fix installer and live installation.

### I. Wrong E3 runtime path in provider plugin
The plugin previously derived an invalid `exec-brain` path from its own plugin location.

Use:
1. explicit `HERMES_E3_RUNTIME_ROOT` if configured;
2. otherwise the authoritative deployed E3 runtime root;
3. validate required modules before client construction.

### J. Fake-only Hermes tool-loop proof
A previous unit test faked `tool_calls` from E3, but real `E3ApplicationService` only returned verified text.

The REAL E3-backed Hermes provider boundary must preserve:
- full `messages`;
- `tools`;
- `tool_choice`;
- valid assistant `tool_calls`;
- tool-result rows;
- next-iteration model call;
- selected worker/provider/model metadata;
- E2/E3 telemetry;
- verification rules that accept valid tool-call-only responses.

### K. Chief routing disappeared from provider seam
A previous provider plugin constructed `E3ApplicationService` directly with task family `other/builder`, bypassing `ChiefRouteSelector` and deterministic departments.

The live provider boundary must retain Chief intake/department ownership.

### L. Career schedules disabled
Live read-only inspection found:
- `ChiefCareerScan-UK` disabled
- `ChiefCareerScan-Dubai` disabled
- `ChiefCareerScan-Japan` disabled
- `ChiefCareerScan-Singapore` disabled

Definitions still pointed to the unified read-only launcher.

Previous results:
- UK last result `0xC000013A` / interrupted
- Dubai 0
- Japan 0
- Singapore 0

No actor who disabled them is recoverable.

These should be restored only after validating current definitions/safety gates.

## PHASE 1 — exhaustive repo + live architecture audit

Before mutating live runtime, perform one final audit of:

- `exec-brain/`
- `career-ops/`
- `company-watch/`
- `hermes-plugins/`
- `scripts/`
- `remote_queue/`
- scheduled launchers/XML
- current deployed E3 runtime
- current Hermes user plugin tree
- stale vendor plugin tree
- gateway/provider config
- Stage-2 state
- task scheduler states

Inventory every production path capable of:
- model/provider selection;
- LLM execution;
- Chief dispatch;
- department dispatch;
- scheduled AI work.

Require:
- 0 unexplained business direct-provider bypasses;
- 0 default raw Discord→E3 bypass;
- 0 normal MoA/OpenRouter fallback path;
- 0 runtime-only Chief/E3 production modules without repo provenance;
- 0 stale deployment assumptions;
- 0 provider plugin path ambiguity.

Do not spend provider calls.

## PHASE 2 — finish the E3-backed Hermes provider boundary

Use current Hermes model-provider plugin API as the supported integration seam.

The target must preserve Hermes' normal agent loop.

Implement/fix a provider boundary that:

1. receives full Hermes normalized chat request:
   - messages
   - tools
   - tool_choice
   - model/session/provider metadata as available;

2. runs Chief intake for the FIRST human-turn model invocation where appropriate;

3. deterministic department requests:
   - execute department workflow without a model call if no AI subtask is needed;
   - return a valid assistant response into Hermes;
   - do not repeat the deterministic action on subsequent tool/model iterations of the same turn;

4. generic/semantic model calls:
   - construct an E3 task fingerprint;
   - select only Stage-2 eligible+routable workers;
   - dispatch full messages/tool schema through the selected worker;
   - preserve tool protocol;

5. response supports:
   - normal assistant text;
   - assistant tool_calls with empty text;
   - correct finish_reason;
   - worker/provider/model metadata;
   - usage when available;

6. next Hermes iteration:
   - sees assistant tool-call row + tool-result row;
   - E3 selects worker again according to policy;
   - returns final answer/tool continuation correctly;

7. valid tool-call-only responses are not rejected merely because text content is empty;

8. native MoA/OpenRouter is not an automatic fallback.

Do not create a second independent router.

## PHASE 3 — make Chief context actually live

Resolve the authoritative active Hermes profile/home.

Context compiler must find live sources on THIS host.

Run metadata-only preflight; do not print private content.

Pass requirements:
- owner context present from at least one live owner source;
- company registry present;
- project state present;
- Discord/Chief history present when the archive exists;
- no context validation warnings;
- bounded size;
- no secret leakage.

Also verify existing Hermes memory/system messages remain in the full message list supplied to E3.

Provider swap must not alter context content selected by Chief.

## PHASE 4 — Career Ops must really execute

Live Chief request examples:

- `career status`
- `show tracker summary`
- `find jobs in uk`
- `I want jobs from all the job search agents`

Must route to Career Ops.

Implement/verify a real live read-only dispatcher using the existing unified scheduled/discovery orchestrator.

Requirements:
- owner request count bounds returned jobs;
- all-region uses UK/Dubai/Japan/Singapore through existing unified workflow;
- source budgets/timeouts/retries remain bounded;
- existing eligibility/dedupe preserved;
- no automatic canonical tracker write;
- no applications submitted;
- semantic stages use E3;
- per-region/source failures remain visible;
- dry-run path makes no network/provider call;
- live path uses the existing approved read-only external search behavior.

Do not recreate four separate job agents in Chief.

## PHASE 5 — plugin installation + stale-copy cleanup

Fix installer to use active:

`<HERMES_HOME>\plugins\model-providers\e3`

with:
- `--hermes-home` override;
- backup before replacement;
- restore command;
- no bundled/vendor tree mutation.

Current stale copy:
`C:\Users\mukun\AppData\Local\hermes\hermes-agent\plugins\model-providers\e3`

Before removing:
- hash/compare it to our E3 plugin;
- back it up;
- only remove if confirmed to be our stale copy.

Never delete any unrelated Hermes bundled provider.

## PHASE 6 — tests before deployment

No real provider calls.

Run all relevant focused suites, including:
- E3 router/execution/orchestrator;
- real E3-provider protocol using fake worker adapters;
- first model call → tool_call → tool result → second call;
- Chief intake/department routing;
- Career Ops live-enabled dispatcher with injected fake orchestrator;
- context compilation/provider-independence/boundedness/provenance;
- provider installer/path/rollback;
- Discord/Hermes integration;
- architecture audit;
- Career Ops focused suites;
- E1/E2/E3 boundary tests;
- status consistency.

Then run ONE final full regression/evidence run.

If unrelated pre-existing Windows inherited-handle tests still fail:
- distinguish them explicitly;
- fix them if they block the production path and can be corrected safely;
- do not mask/skip failures just to claim green.

The final release gate must have zero unexplained failures.

## PHASE 7 — controlled live deployment

After all offline gates pass:

### 7.1 Backups
Create timestamped rollback backups for:
- E3 runtime modules/state;
- orchestration DB;
- user E3 provider plugin;
- stale vendor E3 plugin copy;
- relevant Hermes config/model selection;
- scheduled task definitions/states.

Do not copy secret stores.

### 7.2 Deploy runtime
Deploy repo-tested E3/Chief modules with the source-controlled deployer.

Run runtime provenance and require zero drift for deployed production modules.

### 7.3 Install provider plugin
Install into the active user/profile model-provider directory.

Verify Hermes discovers provider `e3` / `chief-e3`.

Do not yet send a provider request.

### 7.4 Stage 2
Preserve/activate the approved emergency pool:
- `longcat-2.0`
- `google-nano-banana-2`

LongCat remains EVALUATING unless stronger existing qualification evidence says otherwise.

Do not add blocked providers.

Verify exact Stage-2 state.

### 7.5 Select E3 as Hermes automatic model backend
Configure the Chief profile/channel to use the E3 provider/model:
- provider: e3
- model: e3-auto

Use the supported Hermes config/model path.
Do not configure OpenRouter.

### 7.6 Restart gateway once
Restart `Hermes_Gateway` once.

Verify:
- Discord connected;
- E3 provider loaded;
- no plugin import errors;
- no native MoA startup dependency;
- Stage 2 available;
- persistent context source preflight passes.

## PHASE 8 — restore scheduled Career Ops

Owner has authorized restoration IF all safety conditions pass.

Before enabling confirm:
- each task still runs `career-ops/run_scheduled_scan.cmd <region>`;
- launcher still targets unified scheduled orchestrator;
- read-only/no automatic canonical tracker mutation;
- interactive-token requirement unchanged;
- shared lock/state healthy;
- no stale running scan process/lock.

Then enable:
- `ChiefCareerScan-UK`
- `ChiefCareerScan-Dubai`
- `ChiefCareerScan-Japan`
- `ChiefCareerScan-Singapore`

Preserve existing staggered schedule.

Do NOT manually run all four immediately.

Record final state and next run times.

If safety check fails, leave all four disabled and report exact blocker; do not partially enable.

## PHASE 9 — bounded live acceptance

Avoid another token-burning session.

### Provider-call budget
Before live acceptance: 0 real provider calls during engineering/testing.

During acceptance:
- maximum 3 normal Chief LLM turns unless a tool iteration inherently requires a second provider call;
- no blind retries;
- if a provider call fails, diagnose logs/state first;
- do not loop.

### Acceptance A — persistent memory
From Discord Chief channel send:

`Based on our previous conversations and Chief context, summarise what you know about me and the current project. Separate retrieved facts from any inference.`

PASS:
- Chief/E3 path used;
- owner/project/history context source manifest present in logs/metadata;
- answer clearly contains persistent context beyond recent Discord lines;
- no “I have no stored context” claim;
- no native MoA/OpenRouter error.

### Acceptance B — deterministic Career Ops
Use a bounded live request to minimize external spend:

`Use Career Ops to find 1 suitable job from each configured regional job-search agent. Read-only; do not apply or write canonical trackers.`

PASS:
- Chief classifies Career Ops;
- unified Career Ops workflow runs;
- UK/Dubai/Japan/Singapore lanes represented;
- actual result records returned, not a plan;
- no duplicate generic E3 chat answer;
- mutation/applications = 0;
- semantic model work, if needed, uses E3 only.

Do not use 10-per-region for the acceptance run; 1 per region is enough to prove the live path. The normal request parser must still support higher bounded counts afterward.

### Acceptance C — generic Hermes tool loop through E3
Use a safe read-only tool-requiring request such as:

`Check the current Chief system status using the available read-only tools and summarise it.`

PASS:
- Hermes agent loop invokes a real tool;
- E3 handles each model turn;
- tool call + tool result + final response work;
- selected worker/provider/model observable;
- no native MoA/OpenRouter path;
- session/transcript persists.

## PHASE 10 — final system acceptance

After the three live cases:

Verify:
- gateway healthy;
- no duplicate responses;
- no OpenRouter/MoA errors;
- Chief memory works;
- Career Ops works;
- generic tool loop works;
- E3 selector logs real worker selection;
- Stage 2 unchanged except approved pool;
- schedules enabled safely or exact blocker recorded;
- rollback backups available;
- provider-call count recorded.

Run no extra full regression after live acceptance unless code changed during live debugging.

## Automatic rollback rules

If live activation breaks the gateway or normal Chief path:

1. stop further live provider calls;
2. restore prior Hermes provider/model setting;
3. restore user E3 plugin backup;
4. restore runtime module/state backup if needed;
5. restore scheduler enabled/disabled states;
6. restart gateway once;
7. verify previous usable state;
8. preserve all failure logs/evidence.

Do not leave Hermes half-switched.

## Final report format

Return ONE final report only when the entire recovery is complete or an owner-only blocker remains.

Include:

- final branch + commit;
- all architecture defects found and fixed;
- full AI/model call graph;
- direct-provider bypass audit result;
- E3 provider install target;
- stale vendor-copy disposition;
- runtime provenance result;
- Stage-2 state;
- Chief persistent context source IDs (metadata only);
- Career Ops actual live execution result;
- Hermes tool-loop live result;
- Discord memory live result;
- scheduler final states;
- focused test counts;
- full regression counts;
- live provider calls consumed;
- rollback backup paths;
- final verdict: OPERATIONAL or BLOCKED;
- if BLOCKED, exactly one concise owner action required.

Do not call the system operational unless ALL relevant live acceptance conditions pass.
