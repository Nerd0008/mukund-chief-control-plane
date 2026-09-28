# Codex final integration repair — Chief/E3 live-path blockers

Date: 2026-09-28
Owner: Mukund
Repository: `Nerd0008/mukund-chief-control-plane`
Branch: `fix/e3-whole-repo-architecture`
Starting commit: `6c12cf18a5fae8c59c1c96e492b54709648d6743`

## Why this follow-up exists

The whole-repo architecture repair is substantially better and its offline regression is green, but a manual source audit found three release-blocking gaps that the current tests do not cover.

Do NOT deploy or restart the live gateway until these are fixed and re-tested.

## Blocker 1 — Career Ops handoff is still a placeholder

Current file:
`exec-brain/department_dispatch.py`

Current behavior for `career-ops`:
returns `DEPARTMENT_HANDOFF_REQUIRED` with a prose instruction asking for region/status/search.

That preserves ownership but does not actually invoke the existing Career Ops/job-search system.

This would still fail the owner’s real request:
`the whole agent I want 10 jobs from all the job search agents`

Required repair:

- implement a real, deterministic Career Ops department handler;
- reuse existing `career-ops/career_ops_cli.py`, `regional_job_search.py`, the unified scheduled/discovery orchestrator and existing policy/dedupe logic;
- do not reimplement Career Ops inside Chief;
- do not choose a provider/model in the department handler;
- any semantic AI substep must call `E3ApplicationService`;
- support at minimum:
  - status/run-health;
  - read-only job discovery for one region;
  - read-only job discovery across all configured regions;
  - bounded requested-result count (e.g. 10 from each/all agents as requested);
  - existing tracker/manifest summaries;
- preserve all existing mutation/owner-approval gates;
- tests must prove a Career request reaches Career Ops and does NOT become a generic E3 chat completion.

If there are other department placeholders in the repo, inventory them and either bind the existing real workflow or explicitly mark them owner-gated. Do not silently return generic AI prose for a known department workflow.

## Blocker 2 — normal Discord traffic is not wired into the new Chief bridge

Current state:
- `hermes-plugins/e3-discord-router` is observer-only, which correctly stops the old raw-E3 interception.
- `exec-brain/discord_chief_bridge.py` exists and is source-controlled.
- But no repository deployment/integration currently proves that a normal authenticated Discord message actually invokes `dispatch_chief_message()`.

A source-controlled bridge that nothing calls is not a live architecture.

### Preferred integration direction

Inspect current Hermes 2026 plugin/provider extension points before coding.

Hermes supports user model-provider plugins under:
`$HERMES_HOME/plugins/model-providers/<name>/`
and provider profiles can supply custom clients/transports. This is potentially a cleaner architecture than intercepting Discord messages because it preserves Hermes’ authorization, sessions, memory, tool loop and skills while E3 owns model selection.

Preferred architecture if feasible without vendor-core patching:

```
Discord
 -> Hermes auth/session/skills/tools/Chief surface
 -> E3 model-provider boundary
 -> E3 selects eligible Stage-2 worker
 -> underlying provider
 -> Hermes tool loop / final response
```

This is preferable to another `pre_gateway_dispatch` message takeover.

However, do not force a model-provider plugin if it cannot preserve E3’s selection/verification contract and Hermes tool calls safely. Inspect the actual provider plugin/client interfaces and choose the narrowest supported seam.

Acceptance requirements whichever seam is chosen:

- authorization remains Hermes-owned;
- normal session/transcript behavior remains intact;
- tools/skills remain available;
- Chief context is injected before model selection;
- E3 owns automatic provider/model choice;
- native MoA/OpenRouter is not a normal fallback;
- no duplicate response;
- no gateway-vendor source patch unless there is no supported extension point and the change is reversible/owner-approved;
- the integration is source-controlled + deployable + rollbackable.

Add an offline end-to-end test that starts at a normalized/authenticated Discord turn and proves the path reaches Chief, a department when appropriate, and E3 only for AI work.

## Blocker 3 — persistent context is not the real owner memory yet

Current `ChiefContextCompiler._default_sources()` reads:
- `state/current_company_state.md`
- `state/v1-agent-roster.md`
- `state/full_build_tracker.md`

Those are useful project context, but they are not sufficient for the owner’s explicit expectation of persistent personal/Chief memory.

Existing project history records installed local skills:
- `mukund-owner-context`
- `mukund-company-registry`

There is also persisted Discord/Chief history under local/archive/repo surfaces.

Required repair:

- inspect the live Hermes profile and locate the actual installed owner-context/company-registry sources;
- do NOT copy private owner memory into GitHub merely to make tests pass;
- add a runtime context-source adapter that can read approved local Chief context sources;
- add relevant historical Discord/Chief archive retrieval with bounded relevance selection;
- preserve recent session transcript as one source, not the only source;
- keep project/company-state sources;
- include task-specific department records when relevant;
- compile under explicit size/token/character budgets;
- preserve source provenance (source ids + hashes/paths where safe);
- exclude secret-bearing sources/fields;
- memory must be provider-independent.

Offline tests should use synthetic local fixtures representing:
- owner context skill;
- company registry;
- historical Discord archive;
- project state.

Required test:
query equivalent to `Based on all our previous conversations, what do you know about me?`
must compile context from more than the recent transcript/project repo and demonstrate owner-context + history source participation.

Do not assert exact private personal facts in committed fixtures.

## Scheduled job-search tasks

The previous audit measured:
- `ChiefCareerScan-UK`
- `ChiefCareerScan-Dubai`
- `ChiefCareerScan-Japan`
- `ChiefCareerScan-Singapore`

as disabled.

Earlier canonical evidence recorded these as enabled/Ready, so this is a live-state discrepancy.

Inspect WHY they are disabled:
- exact task state;
- last result;
- who/what disabled them if determinable from preserved evidence/logs;
- whether current definitions still point at the unified scheduled orchestrator.

Do not blindly re-enable during offline repair.

Produce a precise re-enable plan. Once the architecture is fixed and the owner approves activation, the four scans should be restored only if their current definitions remain safe/read-only as designed.

## Architecture invariant additions

Extend the architecture audit/tests to fail when:

1. a known department route resolves only to placeholder handoff despite an existing implemented workflow;
2. the source-controlled Chief bridge has no live integration/deployment seam;
3. persistent context contains only project-state sources when owner memory sources are configured;
4. a normal Discord path can fall back to native MoA automatically;
5. a department/business module directly chooses a provider/model;
6. runtime provenance is missing for any Chief/E3 integration module/plugin.

## Provider call budget

ZERO real provider calls for this repair.

Use stubs/fakes, local fixtures, dry-run routing, and read-only runtime inspection only.

## Validation

Run:
- new Chief/department integration tests;
- persistent-context tests;
- Discord/live-path offline test;
- architecture audit;
- Career Ops suite;
- E3 suite;
- status consistency;
- one final full regression/evidence run.

Report exact counts.

Do not deploy live.

## Final completion report

Return:
- exact files/commits;
- real Career Ops dispatcher behavior;
- exact Discord->Chief integration seam selected and why;
- whether Hermes tools/skills/session remain preserved;
- persistent context sources supported;
- schedule discrepancy diagnosis;
- architecture audit result;
- test/regression counts;
- provider calls used (must be 0);
- deployment steps for a separate activation turn.

Do not call Hermes production-ready until the eventual live acceptance proves:
1. `what do you know about me?` uses persistent owner/history context;
2. `I want 10 jobs from all job search agents` reaches Career Ops and returns real workflow output;
3. a generic AI request routes through E3 and shows the selected worker;
4. no native MoA/OpenRouter error appears.
