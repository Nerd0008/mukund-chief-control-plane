# Executive Brain v2 — Unified Design (Proposal)

Status: PROPOSAL — not approved, not implemented
Author: Chief of Staff (Hermes)
Date: 2026-09-21 (amended: DeepSeek provider-class assumptions + secret handling, §8;
pre-approval amendments: central Qualification Gate, cold-start states,
multidimensional capacity, routing objective, proactive checkpointing,
stronger evidence model, privacy/egress split, unknown-capacity rules,
brief format, revised pipeline)
Scope: Executive Brain, No-Degradation Invariant, Resource Governor only
Baseline note: No prior on-disk Executive Brain / Resource Governor design was
found (searched Documents trees, Hermes skills, scratch, control-plane repo).
Baseline = the principles in this brief + the Company Registry's integration and
cost rules (reuse > deterministic > cheap > premium; owner is final decision-maker).
The No-Degradation Invariant is preserved verbatim as constitutional.

---

## 1. Executive Brain architecture

The Executive Brain is not a new agent. It is the Chief of Staff's decision
procedure plus persistent state, built on existing primitives: Hermes tools,
delegate_task, `hermes chat` spawning, Codex/Antigravity CLIs, DeepSeek/Nous
APIs, local models. Nothing in this design adds a second Chief.

Pipeline (strict order):

    Understand → Classify → Decompose (optional) → Freeze quality floors
    → Candidate Generation → Provider Router Proposal (per candidate)
    → Central Qualification Gate (Brain-owned) → Resource Governor check
    → Final Route Selection → Execution + monitor + proactive checkpoints
    → Verification → Record + learn

Components:

| Component | Responsibility |
|---|---|
| Task Classifier | Produces the task classification record (§3) |
| Floor Freezer | Freezes per-subtask quality floors (§4) before any resource lookup |
| Decomposer | Splits a request into subtasks under §7 rules |
| Candidate Generation | Builds the candidate worker set (classes, models, workflows) |
| Provider Router (per provider) | PROPOSES model/reasoning/profile + claimed capabilities (§6) |
| Central Qualification Gate | Brain-owned; validates proposals against the frozen floor (§5a) |
| Strategy Selector | Chooses execution strategy (below) |
| Resource Governor | Multidimensional capacity check (§9a); never influences floors |
| Final Route Selection | Ranks QUALIFIED candidates (§5b); picks the route |
| Monitor | Tracks execution, consumption, confidence, checkpoints |
| Verifier | Enforces the verification level from the floor |
| Learner | Writes performance history (§13) |
| Safe Mode | Deterministic fallback (§15) |

Execution strategies (the Brain selects a strategy, not merely a model):

1. deterministic-tool-only — scripts, SQL, Excel, git; no LLM
2. existing-workflow — a registry workflow already proven for this task type
3. single-AI-worker — one qualified model does the whole subtask
4. multiple-specialist-workers — parallel subtasks, different workers
5. staged-multi-model — e.g. scout drafts → architect designs → critic reviews
6. pause / queue — no qualified path now; queue with floor preserved
7. ask-owner — decision, ambiguity, or override needed

Default bias (from registry cost policy): 1 → 2 → 3 with cheapest qualified
model → 4/5 only when the task genuinely benefits.

## 2. No-Degradation Invariant (constitutional)

Ordering is enforced mechanically, not by judgment:

1. classify task
2. determine required capabilities
3. determine reasoning depth
4. determine verification level
5. determine risk/privacy requirements
6. FREEZE the task-specific quality floor
7. only now may the Resource Governor be queried

Rules:

- Quota, cost, latency, availability MUST NOT silently lower a frozen floor.
  The Governor can only FILTER candidates by qualification; it never edits floors.
- If the qualified candidate set is empty: PAUSE (queue with floor preserved).
- The owner may explicitly override after the Chief warns, in writing, that the
  chosen route falls below the frozen floor. Overrides are logged with the
  original floor, the actual route, and the warning text (§18 OverrideRecord).
- A floor may be revised only by: owner instruction, or new task understanding
  that changes the task itself (recorded as a new classification, not an edit).

## 3. Task classification schema

    task_id            stable id
    request_text       owner's words (verbatim)
    task_type          enum: code | review | research | analysis | writing |
                       data-processing | ops | monitoring | decision-support |
                       extraction | summarization | verification | other
    capability_roles   [scout|builder|architect|researcher|critic|classifier|
                        writer|vision|compressor] (+ multiplicity)
    reasoning_depth    0 mechanical | 1 routine | 2 analytical |
                       3 architectural | 4 novel/uncertain
    verification_level V0 none | V1 self-check | V2 deterministic check/tests |
                       V3 independent critic or owner review
    risk_class         R0 read-only | R1 reversible-local | R2 reversible-public/
                       financial | R3 irreversible/high-impact
    privacy_class      P0 public | P1 internal | P2 personal | P3 secrets-adjacent
    egress_policy      data-egress rule, owner-controlled, separate from
                       privacy_class (§4a): LOCAL_ONLY |
                       APPROVED_PROVIDERS_ONLY | REDACT_BEFORE_EXTERNAL |
                       EXTERNAL_ALLOWED | OWNER_APPROVAL_REQUIRED
    deadline           hard | soft | none (+ datetime)
    idempotent         bool (safe to retry?)
    context_size       small | medium | large
    known_workflows    registry workflows matching this type (reuse first)

Classification confidence is recorded. Low confidence → escalate per §14
before any execution, because everything downstream inherits the floor.

### 4a. Privacy / data-egress policy

privacy_class (what the data IS) and egress_policy (where it may GO) are
separate fields. The owner controls egress policy; it is not inferred from
sensitivity alone. Defaults:

- secrets/credentials → LOCAL_ONLY always (hard default, not configurable
  away by policy short of explicit owner instruction recorded as an
  OverrideRecord)
- P2 personal → OWNER_APPROVAL_REQUIRED before any external egress unless
  the owner has set a standing policy (e.g. APPROVED_PROVIDERS_ONLY with a
  named provider list)
- REDACT_BEFORE_EXTERNAL requires a deterministic redaction step with its own
  verification before external routing

Provider credentials themselves never enter prompts, logs, GitHub, reports,
or any egress path (§8 secret handling).

## 4. Quality-floor schema (frozen record)

    floor_id           per task/subtask
    task_id / subtask_id
    frozen_at          timestamp
    min_reasoning_depth      (from classification; may exceed, never below)
    required_roles           with worker state per role (§4):
                             UNPROVEN | EVALUATING | QUALIFIED | SUSPENDED
    min_verification         V0–V3
    risk_constraints         e.g. R2+ requires owner pre-approval
    egress_constraints       from the task's egress_policy (§4a); e.g.
                             LOCAL_ONLY forbids every external class
    strategy_constraints     e.g. "deterministic only" or "existing workflow only"
    immutable          true after freeze

Evidence tiers (worker states, per (task_type, capability_role) pair):

    UNPROVEN    no verified evidence yet
    EVALUATING  running controlled evaluation tasks (§4b)
    QUALIFIED   task-specific verified evidence meets the threshold (§13)
    SUSPENDED   serious verified failure; excluded until re-qualified

UNPROVEN/EVALUATING workers may run only low-risk subtasks (see §4b);
R2+ or V3 subtasks require QUALIFIED workers or owner approval.

### 4b. Cold-start qualification path

The bootstrap problem: new models/providers/profiles have no evidence, but
without tasks they can never earn any. Resolution — controlled evaluation:

An UNPROVEN worker may be routed ONLY to evaluation tasks where:
- risk is low (R0/R1)
- the result can be independently verified (deterministic check, test suite,
  or independent critic — not the worker assessing itself)
- failure has no material consequence
- production output is not relied upon without that verification

Evaluation tasks are real work that happens to be verifiable (test-coverage
runs, doc extraction against a source, refactor behind tests) — not
synthetic benchmarks, and not owner-override gateways. No owner override is
needed merely to gather safe qualification evidence; the owner IS notified
when evaluation runs happen and sees promotion decisions.

Promotion EVALUATING → QUALIFIED requires task-specific verified evidence
(§13): independently verified outcomes, first-pass success rate, correction
severity, across a minimum sample. A serious verified failure at any point
→ SUSPENDED immediately.

## 5. Hierarchical routing design

Two levels, explicit contract between them:

    Executive Brain
      → specialist class: deterministic-tools | Codex | Antigravity | DeepSeek |
        Nous/LongCat | local-models | future-providers
        → provider router (provider-owned, §6) PROPOSES a worker:
          capability profile: scout | builder | architect | researcher |
          critic | classifier | writer | vision | compressor
          → model + reasoning level + execution profile
        → central Qualification Gate (Brain-owned, §5a) validates the proposal
          against the frozen floor → accept / reject
        → Final Route Selection (§5b) among gate-accepted candidates

- The executive level chooses the CLASS based on: floor qualification,
  performance history, Governor capacity, cost policy.
- The provider level may freely choose model/reasoning/profile INTERNALLY, but
  its choice is a PROPOSAL, not a self-certification. Refusal is a
  first-class answer; acceptance is not.
- Capability roles are stable vocabulary; model names are not. Routers translate
  roles → concrete models, so model churn never touches the Brain's logic.

### 5a. Central Qualification Gate (Brain-owned)

A provider router may PROPOSE model, reasoning level, execution profile, and
claimed capabilities — but it may NOT be the final authority on whether its
own choice meets the frozen quality floor. A provider cannot self-certify
itself into a task.

The Gate (owned by the Executive Brain) validates every proposal using:

- task-specific performance history (§13)
- capability registry (roles each worker has QUALIFIED for, by task type)
- verification history (V-level outcomes, not self-assessment)
- known model/tool constraints (context limits, tool support, licensing)
- current provider state (Governor, §9a)

Provider self-description is evidence, not proof. Output: accept | reject
(with reason, recorded). A rejected proposal may be followed by another
proposal from the same or another provider; the Gate re-validates each.

### 5b. Routing objective (after the quality gate)

Quality is primary. After all candidates below the floor are REMOVED, the
remaining QUALIFIED candidates are ranked by:

1. expected verified task quality (history-weighted)
2. probability of successful completion without handover
3. continuity/resource risk (Governor dimensions, §9a)
4. verification strength available for this task
5. latency, when the task is latency-sensitive
6. cost

Cost must not outrank expected quality among materially different qualified
candidates unless owner policy explicitly permits it. The Brain must not
automatically choose the cheapest qualified model when evidence suggests
another qualified worker materially improves the expected verified result.
Ties or near-equivalents → cheaper wins (registry cost policy applies).

## 6. Provider-router contract

Input (from Brain):  capability role, frozen floor, task context summary,
                     verification needs, budget hints (advisory only).
Output (from router): PROPOSAL — model id, reasoning level, execution profile,
                     claimed capabilities, estimated usage (tokens/cost),
                     confidence. (The router's qualified:yes is an opinion the
                     Gate must confirm; it is not acceptance.)
Obligations:
- MUST refuse when the router believes the floor cannot be met; never silently
  substitute.
- Any substitution (model unavailable mid-task) re-checks the floor via the
  Gate and notifies the Brain; a substitution that breaks the floor triggers
  §12 handover.
- Estimates are labelled estimates; no fabricated precision.

## 7. Task-decomposition rules

- Decomposition happens BEFORE floor freezing; each subtask gets its own floor.
  Different subtasks may legitimately carry different floors:
  repository architecture → strongest qualified model; mechanical edits →
  cheapest qualified worker; tests → deterministic tools; final review →
  qualified critic. This is legal because they are distinct subtasks.
- It is ILLEGAL to split one unit of work into pieces merely to route around a
  floor (e.g. "rewrite the CV" cannot become 20 mechanical edits to dodge a
  writer-role floor). Test: would a human expert treat the pieces as separate
  deliverables with separate verification? If no, don't split.
- Subtask DAG recorded with dependencies; merge/verification step is itself a
  subtask with its own floor.
- Never downgrade the same task because resources are low — pause instead.

## 8. Resource Governor architecture

The Governor is a passive telemetry layer + qualification filter. It has no
authority over floors, strategies, or task content.

    Governor
    ├── Provider Adapters (one per specialist class)
    │     Codex | Antigravity | DeepSeek | Nous/LongCat | local | future
    ├── Capacity Ledger (per provider, per window)
    ├── Reserve Manager (§11)
    ├── Burn/Risk Model (§10)
    └── Report Generator (§16)

Adapter duties: poll/parse provider-reported state where an API exists
(quota, reset, rate limits), record observed events (requests, failures,
429s), and expose one normalized view. Where a provider reports nothing
(e.g. some free tiers), the adapter says UNKNOWN and the Governor marks
telemetry confidence low — estimates are never presented as facts.

### Provider-class assumptions (amendment 2026-09-21 — DeepSeek)

DeepSeek is an API-backed provider:

- accessed through its API using an existing owner-held API key
- a paid, metered resource — capacity is bounded by spending budget, not a
  free-tier quota window
- a provider with its own internal model router (chooses DeepSeek model +
  reasoning level per the §6 contract; may refuse when the floor is unmet)
- eligible for task-specific routing ONLY when it meets the frozen quality
  floor — payment ability never substitutes for qualification

DeepSeek adapter tracks (in addition to the §9 contract):

    api_availability      API up | degraded | down | unknown
    selected_model        DeepSeek model chosen by its router for the task
    token_usage           input tokens / output tokens (observed per request)
    monetary_cost         actual metered spend (observed, per request + total)
    spending_budget       configured budget for the period (owner-set)
    rate_limit_state      ok | throttled | cooldown-until
    burn_rate_recent      spend/hour over trailing window
    projected_spend       projected spend to end of period at current burn
    historical_quality    task-specific performance history (§13 evidence)
    telemetry_confidence  high | medium | low (API-reported vs observed)

For a metered provider, "exhaustion" (§10) means projected spend reaching
the configured budget, and effective_usable = remaining budget − protected
reserve. Budget is a Governor input, never a floor input: a low budget
pauses/reroutes DeepSeek work; it never lowers the floor.

### Secret handling (DeepSeek key, and any provider credential)

- The API key stays LOCAL: environment/secret storage only.
- It never enters GitHub, logs, reports, prompts, or source code.
- No design artifact, brief, or telemetry record contains the key.
- The Chief does not request, display, or echo the key; adapters read it from
  secret storage at call time by name, never by value.

## 9. Provider telemetry contract (per provider, per window)

Provider capacity is NOT one scalar when the provider has multiple
independent limits. Capacity is tracked as separate DIMENSIONS (§9a), each
with its own remaining/reserve/runway/reset/source/confidence. The fields
below are the per-provider summary; §9a holds the dimension table.

    provider            class id
    operational         up | degraded | down | unknown
    available_models    [ids] (+ roles each can serve, per history)
    dimensions          [CapacityDimension] (§9a) — the authoritative view
    rate_limit_state    ok | throttled | cooldown-until
    last_success_at     timestamp of last successful request
    telemetry_source    provider API | observed-only | mixed
    telemetry_confidence high | medium | low
    quota_semantics     provider-specific note (e.g. 5h-window vs daily vs
                        monthly credits) — preserved verbatim, never flattened

All numeric fields carry provenance. "Do not pretend estimates are exact" is
enforced by labelling: every projected number renders with its confidence.
Never mathematically subtract or combine incompatible units (requests,
tokens, credits, currency are never merged into one number).

### 9a. Multidimensional capacity

Each provider exposes zero or more capacity dimensions:

    dimension_kind      request_window | token_window | daily_allowance |
                        weekly_allowance | monthly_allowance |
                        monetary_balance | concurrency | rate_limit |
                        provider_credit
    remaining           current remaining (unit-labelled) | UNKNOWN
    reserve             protected reserve in this dimension (§11)
    effective_usable    remaining − reserve (never negative; unit-preserved)
    reset_renewal       when this dimension renews | UNKNOWN
    source              provider API | observed | inferred
    confidence          high | medium | low

A task may proceed ONLY if ALL binding dimensions have adequate runway
(§10 evaluated per dimension). Incompatible dimensions are never summed or
averaged; each renders separately.

DeepSeek dimensions (per amendment): monetary budget | account/billing
availability | API rate limits | token usage — four separate dimensions,
never compressed into one.

### 9b. Unknown capacity

When quota/capacity telemetry is UNKNOWN, it is NEVER interpreted as zero,
unlimited, or healthy. Instead the Governor uses: observed recent usage,
provider errors (429s, failures), historical behavior, and conservative
estimates — all labelled with confidence.

For long or high-value tasks, insufficient capacity confidence may justify:
- routing to another qualified provider
- checkpoint-first execution (§10a)
- an owner warning
- pause

It must never lower the quality floor.

## 10. Predictive exhaustion algorithm

Run before accepting any new subtask, and periodically during execution —
EVALUATED PER CAPACITY DIMENSION (§9a), never on a merged scalar:

    runway(d) = effective_usable(d)          for each binding dimension d
    need(d)   = estimated_remaining_task_usage(d)
              + verification_requirement(d)  (floor V-level cost estimate)
              + checkpoint_handover_reserve(d) (§11)

    if runway(d) >= need(d) for ALL binding d: proceed
    else (any dimension short):
      1. stop assigning new noncritical work on that provider
      2. reach the latest checkpoint (§10a) — or create one now
      3. preserve state (task record + context + floor)
      4. prepare handover (HandoverRecord, §18)
      5. find equivalent qualified worker (same floor, other provider/model)
      6. continue only if the SAME quality floor is met by the replacement
      7. otherwise PAUSE and notify owner

Thresholds are conservative: warn when projected exhaustion < need + 20%
margin; act when runway < need (in any binding dimension).

### 10a. Proactive checkpointing

The first checkpoint is NOT created at exhaustion time. Long, expensive, or
high-risk tasks checkpoint periodically based on:

- task duration (time-based cadence for long runs)
- task phase (natural boundaries — see below)
- risk class (R2+ checkpoints more often)
- estimated provider runway (checkpoint more often when telemetry confidence
  is low or runway is tight)
- artifact maturity (checkpoint when a coherent artifact exists)

Phase-boundary checkpoints, e.g.:
- architecture decision completed
- code phase completed
- tests completed
- major research stage completed

Predictive exhaustion uses the LATEST checkpoint, making handover cheap and
reliable: a handover resumes from the checkpoint with (completed steps,
artifacts, context digest, verification state, next step) rather than
restarting.

Changing provider, model, or reasoning profile mid-task is a CONTINUITY
EVENT: state must be preserved across it (checkpoint written before the
change, HandoverRecord after), regardless of why the change happened.

## 11. Protected-reserve system

Per provider, the Governor holds reserves that are NOT working capacity.
Reserves are held PER CAPACITY DIMENSION (§9a), never as one merged number:

    reserve(d) = checkpoint_reserve(d) + handover_reserve(d)
               + verification_reserve(d) + critical_owner_reserve(d)

- checkpoint/handover reserve: enough to stop gracefully mid-task
- verification reserve: enough to run the floor V-level on current work
- critical owner reserve: small buffer for owner-flagged urgent requests

Daily reporting shows, per dimension: reported remaining | protected
reserve | effective usable — three distinct numbers, never compressed into
one percentage. Reserve is released only when the task completes or pauses
cleanly; stale reserves time out.

## 12. Handover trigger logic

Handover fires when any of:
- predictive exhaustion (§10) says runway < need
- provider goes down/degraded mid-task
- provider router reports it can no longer meet the floor (substitution failed)
- execution confidence collapses (§14) and a stronger worker is qualified

Procedure: checkpoint → HandoverRecord (task, floor, completed steps,
artifacts, context digest, verification state, next step) → select replacement
under the SAME floor → resume → verify from checkpoint, not from scratch.
If no replacement qualifies: pause + owner notification.

## 13. Performance-learning schema

One row per executed subtask:

    subtask_id | task_type | provider | model | reasoning_level
    execution_profile | strategy | success (bool) | first_pass_success (bool)
    verification_outcome (V-level + pass/fail) | verification_independent (bool)
    retries | owner_corrections | correction_severity (minor|major|rework)
    deterministic_test_results (where applicable)
    task_complexity (floor reasoning_depth as proxy)
    recency (timestamp) | sample_count (running, per pair)
    failure_severity (none | minor | serious)
    runtime_s | usage (tokens/requests) | monetary_cost
    floor_id | notes

Qualification evidence model (replaces simple N ≥ 3 consecutive successes):

QUALIFIED status for a (task_type, capability_role) pair requires, at a
minimum evidence threshold:
- independently verified outcomes (self-assessment alone NEVER establishes
  QUALIFIED — verification must be V2+ or an independent critic)
- a first-pass success rate above threshold over the sample
- no unaddressed major owner corrections in the sample
- recency: stale evidence decays toward UNPROVEN (an old success does not
  certify a changed model)

Weighting considers severity, not just counts: a minor correction and a
rework are different evidence. A serious VERIFIED failure suspends the pair
immediately (QUALIFIED → SUSPENDED); re-qualification restarts evidence
gathering.

Rules:
- Evidence is task-type-specific. No universal model leaderboard exists or is
  built; a model may be excellent for one task type and poor for another.
- Minimum thresholds exist but avoid false precision: thresholds are coarse
  (e.g. "small / adequate / strong sample"), not pseudo-numeric scores.
- Unknown capability = UNPROVEN. Absence of evidence is never evidence.

## 14. Confidence and escalation logic

Confidence is tracked at two points:
- routing confidence: does classification + history support this worker?
- output confidence: did verification pass, and how strongly?

If either is below the floor requirement:
- obtain more evidence (scout probe, router justification)
- use an independent critic (different provider class, not same-model echo)
- escalate to a stronger qualified worker (re-check floor)
- ask the owner when: ambiguity is owner-decidable, all qualified paths are
  busy, or an override below floor is being considered
- or pause

Never disguise uncertainty as confidence: low-confidence findings render with
their confidence label; the Brain may not round uncertainty up.

## 15. Safe mode

If intelligent routing fails (bug, missing telemetry, own error):

    deterministic safe mode:
    - inspect and report state (files, git, trackers, gateway status)
    - run known verified workflows only (registry-verified entries)
    - execute deterministic tools (scripts, git, SQL)
    - queue tasks with their frozen floors intact
    - notify owner that safe mode is active

Safe mode must NOT improvise ambiguous high-impact work. R2+ tasks queue,
never execute, in safe mode. Exit requires the owner or a verified self-test
of the routing path.

## 16. Daily Resource Brief (morning report)

Per configured provider, resource dimensions are shown SEPARATELY —
fundamentally different limits are never compressed into one misleading
percentage. Example shapes:

    Codex
    - short-window allowance: remaining | reserve | effective | reset | confidence
    - weekly allowance:       remaining | reserve | effective | reset | confidence
    - telemetry confidence per dimension

    DeepSeek
    - configured spending budget | actual spend | projected spend
    - API/rate-limit health
    - billing/account health
    - token usage (input/output) | telemetry confidence

Plus, for every provider: availability, previous-day usage, burn trend,
expected today demand, projected exhaustion risk (per dimension), active
handovers, conserve/reserved state.

Also reported: important expected tasks today, likely assigned providers,
capacity risks, next important resets. Rendered with confidence labels;
UNKNOWN shown as UNKNOWN, never as zero. Delivered via existing morning
channels.

## 17. Failure modes (design-level)

| Failure | Behaviour |
|---|---|
| Governor telemetry missing | qualification falls back to history-only; low confidence shown; no fabrication; UNKNOWN never read as zero/unlimited/healthy (§9b) |
| Provider misreports quota | observed counters (429s, failures) override reported numbers; confidence drops |
| Floor-freeze bypass attempt | mechanical ordering: Governor queried only after freeze; code path cannot see pre-freeze state |
| Decomposition abuse (floor dodging) | §7 legality test + critic spot-check on split tasks |
| Provider self-certification attempt | Qualification Gate (§5a) rejects; provider proposals are evidence, never acceptance |
| Cold-start bypass (UNPROVEN on high-risk work) | §4b gates: only R0/R1 independently-verifiable evaluation tasks |
| Brain itself broken | safe mode (§15) |
| Reserve leak (task never completes) | reserves time out and release after task terminal state |
| Handover loop (A→B→A) | handover chain length capped; then pause + owner |
| Estimate drift | every estimate carries confidence; low confidence triggers conservative action |
| Mid-task model/profile switch | continuity event (§10a): checkpoint + HandoverRecord; floor re-checked via Gate |

## 18. Data schemas (persistent state)

    TaskRecord, SubtaskRecord, QualityFloor (immutable), StrategyDecision,
    QualificationDecision (Gate accept/reject + reasons),
    WorkerCapability (pair state: UNPROVEN|EVALUATING|QUALIFIED|SUSPENDED),
    OverrideRecord (owner), ProviderTelemetry (time-series, per dimension),
    CapacityDimension, ReserveState (per dimension), CheckpointRecord,
    HandoverRecord, PerformanceRow, SafeModeEvent, DailyBrief

Storage: local JSON/SQLite under Hermes home (raw, high-frequency) with
curated summaries published to the control-plane repo (state/,
resource-status/, decisions/) — consistent with the existing local/GitHub split.

## 19. Implementation phases (proposal only)

- Phase E1: schemas + floor-freeze ordering + manual routing discipline
  (Brain procedure documented; Governor as manual checklist)
- Phase E2: provider adapters + telemetry ledger + daily brief (deterministic)
- Phase E3: performance history + worker-state gating (UNPROVEN/EVALUATING/
  QUALIFIED/SUSPENDED) + Qualification Gate + handover records
- Phase E4: predictive exhaustion + reserves (enforced, not advisory)
- Phase E5: safe mode + failure-mode drills + owner override UX

Each phase lands only after the previous is verified. No phase may weaken the
invariant; a phase that cannot enforce it ships disabled by default.

---

Owner decision requested: approve as baseline, amend, or reject. Nothing in
this document changes the running system.
