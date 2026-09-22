# Handover — AI Model / Provider Selection for Executive Brain

Date: 2026-09-22
Owner: Mukund
Purpose: Start a separate ChatGPT thread dedicated to researching, comparing, testing, and deciding the AI model/provider pool that the Executive Brain will later orchestrate.

## Important usage instruction for the next ChatGPT thread

Do NOT rely only on this handover.

At the start of the new chat:
1. Read this file.
2. Read `handovers/2026-09-21-chief-os-sprint-handover.md`.
3. Read `state/current_company_state.md`.
4. Read `decisions/exec-brain-e1-rollout.md`.
5. Read `approved-architecture/executive-brain-v2.md`.
6. Check the latest commits in `Nerd0008/mukund-chief-control-plane` in case implementation state changed after this handover.
7. Treat live repo state as source of truth over this document if there is any conflict.

Private control-plane repo:
`Nerd0008/mukund-chief-control-plane`

This handover describes decisions made in the 2026-09-22 ChatGPT architecture discussion that are NOT yet necessarily implemented or merged into the approved Executive Brain baseline.

---

# 1. Why this separate chat exists

Mukund wants a dedicated thread for deciding which AI providers/models should be available to the Executive Brain.

This thread is NOT the E2/E3 implementation thread.

Its job is to:
- discover realistic model/provider candidates
- research current capabilities and access methods
- compare useful differences
- decide which candidates deserve integration/evaluation
- define initial priors, NOT permanent model-role assignments
- provide inputs needed by E2 telemetry and E3 worker qualification/orchestration

The target is a useful worker portfolio, not a generic model leaderboard.

---

# 2. Current company / Executive Brain state

As of the last verified control-plane state before this handover:

## E1 — COMPLETE AND ACTIVE

E1 is the Executive Brain foundation / constitution.

It provides:
- task classification
- optional decomposition mechanics
- immutable task/subtask quality floors
- route-before-freeze blocking
- reasoning/verification/privacy/egress constraints
- structural route-floor compliance
- owner override recording
- append-only records
- SHA-256 hash-chain integrity
- backup/restore
- audit verification

E1 rollout record:
`decisions/exec-brain-e1-rollout.md`

E1 test status at rollout:
32/32 PASS.

Do not redesign E1 in the model-selection chat.

## E2 — NEXT ACTIVE BUILD PHASE

E2 is Resource Governor telemetry + deterministic Daily Resource Brief.

E2 is intended to determine what resources actually exist right now, including separate capacity dimensions such as:
- request/token windows
- daily/weekly/monthly allowances
- monetary balance/budget
- rate limits
- concurrency/provider credits
- reset/renewal
- provider/API health
- telemetry source + confidence

UNKNOWN must remain UNKNOWN.
It must never be interpreted as zero, unlimited, or healthy.

Planned provider families already discussed:
- Codex / OpenAI
- Antigravity / Google
- DeepSeek API
- Nous / LongCat
- local models later

This list is not final.

DeepSeek API key exists with owner.
The key must remain local in environment/secret storage and must never appear in chat, GitHub, logs, prompts, or source.

## E3 — ARCHITECTURAL DIRECTION DISCUSSED, NOT YET IMPLEMENTED

During the 2026-09-22 discussion, Mukund clarified that E3 must NOT hardcode mappings such as:

`coding -> Codex`
`research -> DeepSeek`
`writing -> LongCat`

Instead, E3 should become an intelligent multi-model management/orchestration layer.

The core idea is:
- understand the exact task
- decompose it into genuinely separate capability-specific subtasks where appropriate
- reason about which model/worker is best for each subtask
- assemble a temporary task-specific team
- run independent work in parallel where legal
- integrate outputs
- independently verify the integrated result
- perform targeted rework where needed
- learn from outcomes so future routing improves

The deterministic Qualification Gate remains the enforcement layer.

AI performs the management/reasoning.
Deterministic controls decide whether the proposed route is allowed.

---

# 3. E3 conceptual definition agreed in discussion

Working definition:

**E3 = Intelligent Multi-Model Orchestration + Dynamic Team Assembly + Worker Qualification**

It should eventually behave more like an AI manager building a temporary organization around each problem than like a model switcher.

Illustrative flow:

```
Original Task
    ↓
E1 classification / frozen quality requirements
    ↓
AI decomposition planner
    ↓
Decomposition quality review
    ↓
Execution DAG
    ↓
Capability requirements per subtask
    ↓
Candidate discovery + historical evidence retrieval
    ↓
AI team / worker selection
    ↓
Central deterministic Qualification Gate
    ↓
Context + permission packaging
    ↓
Specialist workers
    ↓
Dependency monitoring / intelligent replanning
    ↓
Integrator
    ↓
Independent critic / deterministic verification
    ↓
Targeted rework where required
    ↓
Final verified deliverable
    ↓
Performance + failure-attribution learning
```

Important:
E1 already has the mechanical decomposition primitives.
E3 supplies the intelligence that decides HOW to decompose and WHO should receive each piece.

---

# 4. Key E3 ideas relevant to model selection

The model-selection chat must understand these because we are choosing workers for this future system.

## A. No permanent model-role mapping

Do not decide that a model permanently "is" the coding model, research model, etc.

Better phrasing:

"This model appears promising for the builder role based on current evidence and should be evaluated."

The system must be able to change its beliefs over time.

## B. Task-specific capability evidence

Worker qualification should be contextual, approximately:

`worker × task family × capability role`

Example:

```
Model X
large-Python / builder -> QUALIFIED
security-architecture / architect -> EVALUATING
research / researcher -> UNPROVEN
critic -> QUALIFIED
```

No universal model score should exist.

Do NOT reduce providers/models to numbers like:
`Codex 95, DeepSeek 87, LongCat 72`.

## C. Stable capability roles

Working role vocabulary discussed:
- planner
- researcher
- scout
- architect
- builder
- debugger
- critic
- verifier
- integrator
- writer
- classifier
- vision
- data analyst
- compressor/context summarizer

The exact vocabulary may be refined before E3 implementation.

One model may qualify for many roles.
A model may also be excellent in one role and poor in another.

## D. Dynamic multi-model teams

A complex task may use several workers.

Example:

```
Research          -> Worker A
Repo analysis     -> Worker B
Architecture      -> Worker C
Implementation    -> Worker D
Tests             -> deterministic Python/CLI
Security critique -> Worker E
Integration       -> Worker C or another qualified integrator
Final verify      -> independent verifier
```

Model selection should therefore optimize the portfolio as a TEAM OF POSSIBLE WORKERS, not search for one model that does everything.

## E. Integrator is a first-class role

Specialist outputs cannot simply be concatenated.

The integrator must:
- reconcile interfaces
- remove duplication
- preserve original objective
- detect missing pieces
- surface conflicts
- request targeted rework

The integrator must NOT be the only verifier of its own work.

## F. Critic / verifier independence

For important work, the critic should preferably be independent of the worker being reviewed.

Cross-provider criticism may be useful.

Example:

```
Worker A designs
Worker B attacks the design
Worker C implements
deterministic tests verify
Integrator assembles
Independent verifier checks final artifact
```

Provider diversity can therefore have architectural value beyond simple redundancy.

## G. Router/planner intelligence may itself use AI

The model that decides which workers to use may itself be an AI.

Routine routing could potentially use a cheaper competent reasoning model.

Ambiguous/high-impact routing may escalate to a stronger reasoning model or a second routing critic.

Its recommendation still passes deterministic controls.

Therefore this model-selection chat must also consider:
- candidate router/planner models
- whether different routing tiers make sense
- whether an independent routing critic is valuable

---

# 5. How E3 should know which worker is good for a specific task

The system should reason over THREE evidence classes.

## Tier 1 — Provider claims

Examples:
- coding specialization
- reasoning controls
- tool support
- multimodal support
- context window
- structured output support

Useful as initial prior.
Never strong proof by itself.

## Tier 2 — External evidence

Examples:
- independent evaluations
- reputable benchmark results
- technical comparisons
- current provider documentation

Useful during cold start.
Must retain source/provenance and freshness.

## Tier 3 — Internal verified experience

Eventually strongest evidence.

For every real worker assignment E3 should be able to learn from:
- exact task fingerprint
- capability role
- provider/model
- reasoning/execution profile
- tools available
- first-pass success
- deterministic tests
- independent critic outcome
- corrections
- correction severity
- retries
- runtime
- usage/cost
- failure attribution
- verification result

The router should reason over similar historical tasks, not merely broad labels like "coding".

---

# 6. Task fingerprint idea

A task/subtask should eventually carry characteristics such as:
- task family
- domain
- language
- artifact type
- repository size
- context size
- reasoning depth
- ambiguity
- tool intensity
- security sensitivity
- required capability roles
- risk
- verification type
- research freshness requirement
- integration complexity

Then E3 can retrieve prior work that resembles the new task and reason from actual experience.

Example:

"large Python security repository + architecture + heavy terminal use + V3 verification"

is much more useful than:

"coding".

---

# 7. Cold-start handling

A new model should NOT automatically be considered bad.

Initial state:
`UNPROVEN`

Safe evaluation work can move it to:
`EVALUATING`

Sufficient independently verified evidence can move a specific capability to:
`QUALIFIED`

A serious verified failure may move that specific capability to:
`SUSPENDED`

This means the model-selection chat is establishing:
- candidate pool
- current priors
- useful evaluation hypotheses

It is NOT establishing permanent truth.

---

# 8. Exploration vs exploitation

The future system should avoid becoming permanently locked to whichever models got early evidence.

For high-risk work:
- favour proven workers.

For low-risk, objectively verifiable work:
- occasionally evaluate promising new workers.

Possible future shadow evaluation:

```
Production worker -> proven model
Shadow worker     -> promising new model

Only production output is used.
Shadow output is verified afterwards.
Result contributes evidence.
```

This should be resource-aware, not constant.

---

# 9. Decomposition and management ideas already identified

These are relevant because model capabilities should be assessed against them.

## Decomposition Quality Gate

The planner's plan itself may be wrong.

A review pass should check:
- omissions
- illegal floor-dodging splits
- dependency mistakes
- incorrect parallelization
- missing integration
- missing verification path

## Execution DAG

Complex work should be represented as dependency graphs, not flat agent lists.

Possible node states:
- PLANNED
- BLOCKED
- READY
- RUNNING
- VERIFYING
- REWORK
- COMPLETE
- FAILED
- PAUSED
- CANCELLED

## Worker contracts

Each worker should receive structured objectives, inputs, output expectations, permissions, verification requirements, and definition of done.

## Context Compiler

Workers should receive only the minimum sufficient context for their assignment rather than automatically receiving whole conversations/repos.

## Permission Compiler

Different workers should have different powers:
- research: web + read-only
- architect: read-only repo
- builder: controlled worktree + tests
- critic: read-only diff/artifacts
- integrator: approved artifacts / controlled writes

## Conflict resolution

If workers disagree, the system should isolate the disputed assumption and use evidence/critique rather than allowing the integrator to silently choose.

## Intelligent replanning

If execution reveals that the original task understanding was wrong, E3 can version the plan, preserve valid completed work, create new subtasks/floors, cancel obsolete nodes, and continue.

This is different from E4 resource-driven handover.

## Targeted rework

Verification failure should reopen only affected nodes where possible, not restart the entire workflow.

## Failure attribution

Learning must identify whether failure came from:
- planning
- decomposition
- factual research
- reasoning
- implementation
- tool use
- integration
- context
- verification miss
- environment/external dependency

Do not penalize a worker for a failure it did not cause.

## Router self-evaluation

The system should eventually learn whether its MODEL SELECTION decisions were good, not only whether individual workers were good.

---

# 10. Relationship of phases

Keep these boundaries clear.

## E1 — Constitution / quality

Question:
"What quality and constraints must this task satisfy?"

Already active.

## E2 — Resource awareness

Question:
"What providers/resources/capacity do we actually have right now?"

Next implementation phase.

## E3 — Intelligent management

Question:
"How should this task be structured, which workers should do each part, how should they collaborate, and what can we learn from the outcome?"

Current architectural direction discussed in ChatGPT; not implemented yet.

## E4 — Continuity/resource strategy

Expected to own:
- predictive exhaustion
- protected reserves
- proactive resource checkpoints
- equivalent-worker handover
- resource-driven continuity

Do not accidentally assign these responsibilities to E3.

## E5 — Resilience/governance

Expected to own:
- safe mode
- failure drills
- owner override UX / resilience behaviours

---

# 11. Model-selection chat mission

The separate chat should build a CURRENT, REALISTIC candidate worker inventory.

Because model availability/specs/pricing/capabilities change quickly, use current web research and official provider documentation where possible.

For every serious candidate investigate:

- provider
- exact current model/model family
- access method: API / CLI / subscription tool / Hermes route / local
- whether Mukund realistically has access
- whether it can run unattended/automated
- API maturity
- tool use
- coding ability
- repository-scale capability
- planning/architecture reasoning
- research/web ability
- critique/review ability
- synthesis/integration ability
- structured output
- context window
- vision/multimodal capability
- latency
- pricing / metering
- quotas / limits
- rate limits
- E2 telemetry availability
- privacy/data handling implications
- model/version stability
- reasoning controls
- known strengths
- known weaknesses
- external evidence
- redundancy with other candidates
- proposed roles to EVALUATE, not permanently assign

---

# 12. Candidate provider families

At minimum investigate current realistic options around:

- OpenAI / Codex
- Google / Gemini / Antigravity
- DeepSeek
- Nous / LongCat
- Anthropic if integration is practical and worthwhile
- other API providers only if they add material capability/value
- local/open-weight models where they offer privacy, cost, speed, classification, compression, or other useful niches

Do NOT add providers merely for variety.

Every provider adds:
- integration complexity
- telemetry work
- credentials
- failure modes
- maintenance
- E3 qualification work

A provider should earn its place.

---

# 13. Portfolio philosophy

The goal is NOT "collect every strong model".

The goal is an effective worker portfolio with useful specialization and redundancy.

Potential portfolio functions:
- high-end planner/architect
- strong coding/builder
- strong critic/reviewer
- strong research worker
- strong integrator/synthesizer
- cheap high-volume worker
- fast classifier/scout
- long-context specialist
- vision specialist
- local/private worker

One worker may cover several functions.

Do not force one model per category.

Avoid redundant paid providers unless they materially improve quality, independence, continuity, cost, privacy, or coverage.

---

# 14. Cost philosophy

Existing company principle:

```
existing resource
→ deterministic Python/PowerShell/SQL/Excel/etc.
→ cheap/free qualified AI
→ premium AI when materially useful
```

But cost may NEVER silently lower the frozen E1 quality floor.

Among materially different qualified candidates:
expected verified quality should outrank cost.

Among near-equivalent candidates:
cheaper generally wins.

---

# 15. What the model-selection chat should eventually produce

Create an initial proposed Model/Provider Registry.

Suggested record shape:

```
Provider:
Worker/model:
Access method:
Automation path:
Current availability:
Pricing/metering:
Telemetry available to E2:
Context/tool features:
Potential roles to evaluate:
External evidence:
Known limitations:
Privacy/egress notes:
Initial evidence state:
Recommended evaluation tasks:
Redundancy/unique value:
```

Initial evidence state will generally be UNPROVEN unless we already have valid internal evidence.

The chat should distinguish:
FACTS
from
HYPOTHESES TO TEST.

---

# 16. Questions the separate chat must answer

Before final recommendation, answer:

1. Which providers are worth integrating at all?
2. Which exact models should Chief initially be allowed to consider?
3. Which candidates are redundant?
4. Which model(s) are promising as planner/router intelligence?
5. Which candidates deserve evaluation for planner?
6. Researcher?
7. Architect?
8. Builder/debugger?
9. Critic/verifier?
10. Integrator?
11. Writer?
12. Vision?
13. Cheap classifier/scout/data roles?
14. Which providers/models should be treated as premium resources?
15. Which are good candidates for cheap/high-volume work?
16. Which local/private workers are worth adding now vs later?
17. What real-world low-risk evaluation tasks should qualify each candidate?
18. What E2 telemetry adapter requirements arise from the selected providers?
19. Which providers add meaningful independence for cross-model criticism?
20. Which access methods can be automated reliably from Mukund's current Windows/Hermes environment?

---

# 17. Important warning about "best model" conclusions

Do not finish this chat with claims like:

"Model X is permanently the coding model."

Instead conclude things like:

"Model X has strong current external evidence for repository coding and should enter E3 as an UNPROVEN/EVALUATING builder candidate, with these specific qualification tasks."

The future Executive Brain must be able to discover that:
- a model is better as architect than builder
- a model is better as critic than primary worker
- a new model overtakes an old model
- a worker's quality changes after provider updates
- different task fingerprints need different teams

The worker registry is a starting prior, not permanent routing policy.

---

# 18. Current implementation deadline context

Whole-system v1 target remains 24 September 2026.

Do not allow the model-selection research to block E2 implementation unless a provider decision is actually needed for an E2 adapter.

This model-selection thread may research deeply in parallel, but implementation work should continue in the main build thread.

Avoid unnecessary provider proliferation before v1.

---

# 19. First action for the new ChatGPT thread

After reading this handover and live control-plane state:

1. Confirm E1/E2/E3 status from the repo.
2. Do NOT modify the Executive Brain implementation.
3. Use current web research because model/provider details are time-sensitive.
4. Build a broad-but-realistic candidate pool first.
5. Separate verified facts from hypotheses.
6. Do NOT select permanent role winners yet.
7. Identify which candidates add distinct value versus redundancy.
8. Present the candidate registry for discussion with Mukund.
9. Make model/provider decisions interactively with Mukund.
10. Only write final decisions to the control plane after Mukund explicitly approves them.

Suggested first user message for that chat:

"Use handovers/2026-09-22-ai-model-selection-handover.md from my GitHub control plane. Read the linked control-plane state it tells you to read, check whether anything changed, then start the model/provider audit. Do not choose permanent winners yet — build the candidate pool first."
