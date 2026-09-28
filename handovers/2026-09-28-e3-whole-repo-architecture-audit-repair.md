# Codex takeover — whole-repository E3 architecture audit and repair

Date: 2026-09-28
Owner: Mukund
Repository: `Nerd0008/mukund-chief-control-plane`
Starting branch: `fix/longcat-stage2-emergency`

## Owner intent

Audit and repair the ENTIRE repository and live local Hermes/Chief runtime for architectural consistency with E3.

This is not a Career Ops-only task and not a Discord-only task.

The owner wants E3 to be the common AI model/orchestration brain across Chief OS while preserving deterministic agents, departments, schedules, tools and trackers. No subsystem should silently bypass E3 to pick a provider/model itself, and E3 must not replace deterministic business/workflow agents.

Do the audit and repair autonomously. Do not ask the owner to relay individual test failures. Stop only for a genuinely owner-only external action.

## Correct target architecture

The intended layering is:

```
External interface (Discord / scheduled task / CLI / queue)
        ↓
Chief / E1 intake + classification + policy
        ↓
Department / deterministic workflow / tool / scheduled worker
        ↓
Does this step require an LLM?
      ├── NO → execute deterministic/tool path directly
      └── YES
             ↓
            E3
       planner/router/context/permissions/team/verification
             ↓
       Stage-2-approved worker/model
             ↓
       provider adapter execution
             ↓
       E2 telemetry + E3 verification/evidence
             ↓
       calling workflow / Chief
             ↓
       external response/output
```

Key rule:

**E3 chooses/executes AI workers. E3 does NOT replace Chief, Career Ops, Company Watch, schedulers, tracker writers, approval gates, inbox monitors, deterministic services, or other business/workflow agents.**

Provider/model selection should happen in one architectural layer only: E3.

## Known inconsistencies already found

### 1. Discord bridge is above Chief instead of below it

Current:
`hermes-plugins/e3-discord-router/__init__.py`

It intercepts all authorized non-slash Discord text at `pre_gateway_dispatch`, executes raw E3, replies itself and returns `{"action":"skip"}`.

Observed live symptom:
A job-search request reached `longcat-2.0`, which answered that it had no prior job-search context and could not run persistent/scheduled agents. The response footer proved E3 executed:
`_E3 worker: longcat-2.0_`.

This proves the bridge bypassed the Chief/Career Ops layer.

Repair principle:
- normal Discord turns must reach Chief/E1/department routing first;
- only AI subtasks from Chief/departments should call E3;
- native Hermes MoA/OpenRouter must still not become the default model selector;
- preserve Discord auth, thread routing, transcript, tools and Chief continuity.

Do NOT merely special-case “job search” keywords in the E3 gateway plugin. Fix the architectural layer.

### 2. Career Ops has direct provider bypasses

Confirmed repo hits:

`career-ops/discovery/classifiers.py`
- imports `deepseek_adapter`
- creates `DeepSeekExecutionAdapter(...)`
- imports `codex_adapter`
- creates `CodexExecutionAdapter()`

`career-ops/discovery/web_research.py`
- imports/resolves `codex_adapter` directly

`career-ops/discovery/pipeline.py`
- carries direct DeepSeek adapter injection paths

These business/workflow modules may select/use models outside E3.

Repair principle:
- keep deterministic collection/filter/dedupe/safety logic in Career Ops;
- replace AI execution with an E3-facing service/interface;
- task family/role/context must be explicit;
- E3 decides actual worker/provider;
- tests must stub the E3 interface, not provider-specific adapters.

### 3. Discord plugin duplicates intake classification

Current plugin contains its own keyword classifier:
`_classify_text(...)`

This duplicates Chief/E1 classification and can disagree with the real system.

Repair principle:
- one intake/task classification contract;
- reuse Chief/E1 task fingerprinting or a shared classification adapter;
- no separate Discord-only taxonomy deciding AI roles.

### 4. Critical Chief bridge source/runtime drift

Repo search does NOT find source files:
- `chief_routing.py`
- `discord_chief_bridge.py`

Yet the 2026-09-28 E1 runtime-boundary patch explicitly recognizes those as deployed Chief bridge runtime modules.

This suggests critical live orchestration code may exist only in:
`%LOCALAPPDATA%\hermes\exec-brain`

Repair principle:
- inspect the live runtime files;
- establish provenance and hashes;
- source-control the authoritative implementation in the repo if it is production-owned code;
- deploy it through a reproducible deployment script;
- do not leave the Chief architecture dependent on untracked runtime-only code;
- do not overwrite runtime files blindly before preserving backups/diffs.

### 5. Existing acceptance does not enforce architecture

Current integration/whole-company acceptance proves many components exist/work, but does not assert:
- business modules do not import execution adapters directly;
- all AI execution flows through E3;
- E3 does not replace department/workflow ownership;
- live runtime source matches repo source.

Add deterministic architecture tests so this class of regression cannot recur.

## Scope: audit the entire repository

Do not limit the search to known files.

Build an inventory of every path that can initiate AI/model/provider execution.

Search source code (not historical evidence as a defect source) for at least:

- `deepseek_adapter`
- `codex_adapter`
- `gemini_adapter`
- `generic_openai_adapter`
- `DeepSeekExecutionAdapter`
- `CodexExecutionAdapter`
- `GeminiExecutionAdapter`
- `GenericOpenAIAdapter`
- provider endpoints/model IDs
- direct OpenAI-compatible HTTP completion calls
- `codex exec`
- `hermes chat`
- native model selection
- `/model`
- MoA/OpenRouter assumptions
- `ExecutionAdapterRegistry`
- `E3Router`
- `orchestrate_and_execute`
- any model/provider argument accepted by business code
- any scheduled worker that calls an LLM/provider directly
- any plugin/hook that suppresses Chief execution
- any department-specific AI selector/scheduler
- any test that blesses a direct-provider architecture

Classify each hit as one of:

1. **E3 core execution — allowed**
2. **provider diagnostics/readiness/smoke — allowed but must never be imported as business execution**
3. **tests/fixtures — allowed**
4. **business/workflow direct-provider bypass — architectural defect**
5. **historical evidence/docs only — no code defect**
6. **unclear — inspect**

Audit at least these repo areas:

- `exec-brain/`
- `career-ops/`
- `company-watch/`
- `scripts/`
- `hermes-plugins/`
- remote queue execution/worker code
- Chief/Discord/archive/sync integration
- operational services / morning brief
- LinkedIn workflows
- application inbox/status monitor
- job intelligence/research
- CV/cover-letter/interview workflows
- scheduled workers
- deployment scripts/manifests
- status/inventory/acceptance code

Also inspect the live runtime:

- `%LOCALAPPDATA%\hermes\exec-brain`
- live Hermes user plugins
- Hermes scheduled-task launchers
- ChiefDiscordSync / gateway integration files

Do not read secret values.

## Required architectural repair

### A. Create one reusable E3 application-facing dispatch interface

Business/workflow code should not instantiate provider adapters.

Create a stable interface/module for callers such as:

```python
result = e3_service.execute(
    objective=...,
    task_family=...,
    required_role=...,
    risk_class=...,
    context=...,
    verification=...,
)
```

Exact API is your design decision, but requirements are:

- Stage 2 fail-closed for real provider execution;
- E3 capability/routability/allowlist enforcement;
- caller declares task semantics, never provider/model;
- returns selected worker/provider/model metadata and verified output;
- preserves E2 usage linkage;
- supports dependency injection/stub mode for tests;
- no secret material in result/errors;
- can be used by Chief and by scheduled/background departments;
- does not require Discord/Hermes gateway context;
- supports a zero-call/dry-run or injected fake registry for tests.

Do not create a second E3 router implementation.

### B. Put E3 underneath Chief

Locate the real Chief routing path. If authoritative modules currently exist only in runtime:
- back them up;
- compare them with historical/source references;
- bring production-owned source into the repo;
- add deployment support;
- add tests.

Normal Discord flow should become conceptually:

```
Discord → Hermes gateway/auth/session → Chief intake/E1 → department/tool routing
                                            ↓ only when AI needed
                                           E3
                                            ↓
                                      verified AI output
                                            ↓
                                         Chief
                                            ↓
                                        Discord
```

The current `e3-discord-router` plugin must no longer consume every normal text message before Chief.

Acceptable outcomes include:
- replacing the plugin with a thin Chief bridge that invokes the normal Chief path;
- moving E3 invocation into the Chief AI-execution boundary;
- restricting the E3 gateway plugin to an explicit diagnostic/manual E3 command only.

Do not leave two default model selectors in competition.

Native Hermes MoA/OpenRouter:
- may remain available only as an explicit/manual fallback if useful;
- must not be the normal automatic model routing path;
- must not be required for Chief operation.

### C. Migrate every business direct-provider bypass to E3

At minimum repair the confirmed Career Ops paths.

For every other bypass found, either:
- migrate it to the shared E3 service; or
- document why it is a diagnostics-only exception and enforce that in tests/import boundaries.

Preserve deterministic parts of those workflows.

Do not turn deterministic workers into LLM agents unnecessarily.

### D. Preserve agent/workflow ownership

After repair, these must still exist as first-class services/workers rather than prompts inside LongCat:

- Chief of Staff
- Career Ops Manager
- UK/Dubai/Japan/Singapore job-search workers
- eligibility/dedupe/tracker writer
- Company Watch / recruiter watch
- application inbox/status monitor
- CV/cover-letter/application-pack workflows
- LinkedIn draft/publish gates
- Career Daily Brief
- remote queue/watchdog
- operational services/morning brief
- scheduled-task manager
- any other rostered deterministic worker

E3 is their AI compute/router dependency, not their replacement.

### E. Add architectural invariants/tests

Add an offline test/audit that fails if production business code directly imports/constructs provider adapters.

Example policy:
- provider adapter imports allowed only under:
  - `exec-brain/` core execution/adapters
  - explicit provider diagnostic scripts
  - tests
  - immutable historical evidence
- denied in:
  - `career-ops/` production code
  - `company-watch/` production code
  - Chief business/workflow modules
  - operational services
  - plugins other than the E3 core integration layer

Also assert:
- normal Discord request does not get consumed by raw E3 before Chief;
- deterministic Chief/department path can run without any provider call;
- an AI-required Chief subtask invokes E3 exactly once;
- selected worker is Stage-2 allowed/routable/eligible;
- native MoA does not also execute;
- scheduled Career Ops AI semantic stages use E3;
- runtime-owned Chief bridge modules have repo source + deployment provenance;
- source/runtime manifest detects drift.

### F. Whole-repo architecture map

Add a concise source-controlled architecture document, e.g.
`docs/E3_ARCHITECTURE.md`, recording:

- ownership/layer boundaries;
- allowed direct adapter locations;
- Chief → E3 contract;
- background/scheduled worker → E3 contract;
- deterministic-vs-AI decision boundary;
- Stage 2 semantics;
- E2 telemetry;
- E4/E5 relationship;
- Discord path;
- prohibited bypass examples;
- rollback/fallback behavior.

This document must describe actual tested code after the repair, not an aspiration.

## Live state / scheduled agents

Inspect, do not assume, current Windows scheduled-task state for all Chief-owned tasks.

Especially verify:
- `ChiefCareerScan-UK`
- `ChiefCareerScan-Dubai`
- `ChiefCareerScan-Japan`
- `ChiefCareerScan-Singapore`
- `Hermes_Gateway`
- `ChiefDiscordSync`
- `HermesRemoteQueuePoller`

Report current status/last result/next run.

Do not trigger real job-search web/provider scans just for this architecture audit unless an existing deterministic status command requires zero provider calls.

## Provider-call budget

During architecture audit and repair:

**ZERO real provider calls.**

All validation must use:
- unit tests,
- stubs/fakes,
- dry-runs,
- read-only status,
- existing recorded evidence.

Do not re-smoke LongCat/DeepSeek/Codex/etc.

After the entire repo is green, stop and present the live acceptance plan. Do not perform a new live provider acceptance without owner confirmation.

## Git discipline

Create a dedicated repair branch from the latest:
`origin/fix/longcat-stage2-emergency`

Suggested:
`fix/e3-whole-repo-architecture`

Do not work directly on main.

Preserve unrelated owner changes.
Keep commits focused.
Push all repair commits.
Do not merge without owner instruction.

Preserve failed diagnostic evidence under the established superseded convention; do not delete it merely to make tests green.

## Validation

Run targeted tests while repairing, then:

1. E3 suites
2. Career Ops suites
3. Company Watch suites if present
4. scripts/architecture/integration tests
5. E1/E2/E3 boundaries
6. status consistency
7. whole-company/local acceptance where zero-provider safe
8. one final full repository regression/evidence run

No provider calls.

Report exact counts.

Also run the new architecture audit and require:
- 0 unexplained business direct-provider bypasses
- 0 runtime-only production Chief modules without repo provenance
- 0 default Discord paths that bypass Chief
- 0 competing automatic provider/model selectors in the normal path

## Success definition

Do NOT call this complete merely because tests pass.

Final report must show:

1. full AI-execution call graph before vs after;
2. every direct-provider bypass found and disposition;
3. Chief/Discord layering corrected;
4. Career Ops and other departments preserved;
5. E3 shared service implemented and used by business AI paths;
6. source/runtime Chief bridge drift resolved;
7. architecture invariants added;
8. scheduled-agent live status measured;
9. full regression counts;
10. zero real provider calls during repair;
11. exact remaining owner actions, if any;
12. deployment/activation plan — but do not deploy automatically.

The owner specifically requested a whole-repository E3 architecture audit, not a narrow job-search fix.
