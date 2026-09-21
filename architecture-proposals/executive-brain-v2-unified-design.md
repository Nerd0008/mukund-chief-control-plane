# Executive Brain v2 — Unified Design (Proposal)

Status: PROPOSAL — not approved, not implemented
Author: Chief of Staff (Hermes)
Date: 2026-09-21 (amended same day: DeepSeek provider-class assumptions + secret handling, §8)
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
    → Select strategy → Select specialist class → Provider routing
    → Execute + monitor → Verify → Record + learn

Components:

| Component | Responsibility |
|---|---|
| Task Classifier | Produces the task classification record (§3) |
| Floor Freezer | Freezes per-subtask quality floors (§4) before any resource lookup |
| Decomposer | Splits a request into subtasks under §7 rules |
| Strategy Selector | Chooses execution strategy (below) |
| Executive Router | Chooses specialist class (§5) |
| Governor Interface | Queries qualified capacity; never influences floors |
| Monitor | Tracks execution, consumption, confidence signals |
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
    deadline           hard | soft | none (+ datetime)
    idempotent         bool (safe to retry?)
    context_size       small | medium | large
    known_workflows    registry workflows matching this type (reuse first)

Classification confidence is recorded. Low confidence → escalate per §14
before any execution, because everything downstream inherits the floor.

## 4. Quality-floor schema (frozen record)

    floor_id           per task/subtask
    task_id / subtask_id
    frozen_at          timestamp
    min_reasoning_depth      (from classification; may exceed, never below)
    required_roles           with evidence tier per role:
                             PROVEN(task_type) | UNPROVEN
    min_verification         V0–V3
    risk_constraints         e.g. R2+ requires owner pre-approval
    privacy_constraints      e.g. P3 forbids external providers entirely
    strategy_constraints     e.g. "deterministic only" or "existing workflow only"
    immutable          true after freeze

Evidence tiers: a provider+model is PROVEN for a task type only through
performance history (§13). Everything else is UNPROVEN. UNPROVEN workers may
run low-risk subtasks; R2+ or V3 subtasks require PROVEN or owner approval.

## 5. Hierarchical routing design

Two levels, explicit contract between them:

    Executive Brain
      → specialist class: deterministic-tools | Codex | Antigravity | DeepSeek |
        Nous/LongCat | local-models | future-providers
        → provider router (provider-owned, §6)
          → capability profile: scout | builder | architect | researcher |
            critic | classifier | writer | vision | compressor
            → model + reasoning level + execution profile

- The executive level chooses the CLASS based on: floor qualification,
  performance history, Governor capacity, cost policy.
- The provider level may freely choose model/reasoning/profile INTERNALLY, but
  must return a self-declared qualification against the floor, and refusal is a
  first-class answer.
- Capability roles are stable vocabulary; model names are not. Routers translate
  roles → concrete models, so model churn never touches the Brain's logic.

## 6. Provider-router contract

Input (from Brain):  capability role, frozen floor, task context summary,
                     verification needs, budget hints (advisory only).
Output (from router): model id, reasoning level, execution profile,
                     qualified: yes/no (against the floor),
                     estimated usage (tokens/cost), confidence.
Obligations:
- MUST refuse when the floor cannot be met; never silently substitute.
- Any substitution (model unavailable mid-task) re-checks the floor and
  notifies the Brain; a substitution that breaks the floor triggers §12.
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

    provider            class id
    operational         up | degraded | down | unknown
    available_models    [ids] (+ roles each can serve, per history)
    reported_remaining  provider-stated quota/credits | UNKNOWN
    reset_time          provider-stated | UNKNOWN
    protected_reserve   Governor-held reserve (§11)
    effective_usable    reported_remaining − protected_reserve (never negative)
    burn_rate_recent    usage/hour over trailing window (observed)
    projected_exhaustion earliest time effective_usable hits 0 at burn rate
    task_consumption    usage charged to current running task
    estimated_remaining estimated usage to finish current task + verification
    cost_rate           per-unit provider/API cost
    rate_limit_state    ok | throttled | cooldown-until
    last_success_at     timestamp of last successful request
    telemetry_source    provider API | observed-only | mixed
    telemetry_confidence high | medium | low
    quota_semantics     provider-specific note (e.g. 5h-window vs daily vs
                        monthly credits) — preserved verbatim, never flattened

All numeric fields carry provenance. "Do not pretend estimates are exact" is
enforced by labelling: every projected number renders with its confidence.

## 10. Predictive exhaustion algorithm

Run before accepting any new subtask, and periodically during execution:

    runway = effective_usable
    need   = estimated_remaining_task_usage
           + verification_requirement (floor V-level cost estimate)
           + checkpoint_handover_reserve (§11)

    if runway >= need: proceed
    else:
      1. stop assigning new noncritical work on that provider
      2. reach a safe checkpoint (commit state, write partial results)
      3. preserve state (task record + context + floor)
      4. prepare handover (HandoverRecord, §18)
      5. find equivalent qualified worker (same floor, other provider/model)
      6. continue only if the SAME quality floor is met by the replacement
      7. otherwise PAUSE and notify owner

Thresholds are conservative: warn when projected exhaustion < need + 20%
margin; act when runway < need.

## 11. Protected-reserve system

Per provider, the Governor holds reserves that are NOT working capacity:

    reserve = checkpoint_reserve + handover_reserve + verification_reserve
              + critical_owner_reserve

- checkpoint/handover reserve: enough tokens/requests to stop gracefully mid-task
- verification reserve: enough to run the floor V-level on current work
- critical owner reserve: small buffer for owner-flagged urgent requests

Daily reporting shows three distinct numbers per provider: provider-reported
remaining | protected reserve | effective usable capacity. Reserve is released
only when the task completes or pauses cleanly; stale reserves time out.

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
    verification_outcome (V-level + pass/fail) | retries | owner_corrections
    runtime_s | usage (tokens/requests) | monetary_cost
    floor_id | notes

Rules:
- Evidence is task-type-specific. No universal model leaderboard exists or is
  built; a model may be excellent for one task type and poor for another.
- PROVEN status requires N ≥ 3 consecutive successful, verified executions for
  a (task_type, capability_role) pair, including the floor verification.
- Any owner correction demotes the pair to UNPROVEN (re-earned via N again).
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
    - run known verified workflows only (registry PROVEN entries)
    - execute deterministic tools (scripts, git, SQL)
    - queue tasks with their frozen floors intact
    - notify owner that safe mode is active

Safe mode must NOT improvise ambiguous high-impact work. R2+ tasks queue,
never execute, in safe mode. Exit requires the owner or a verified self-test
of the routing path.

## 16. Daily Resource Brief (morning report)

Per configured provider:
availability | reported remaining | protected reserve | effective usable |
reset time | previous-day usage | burn trend | expected today demand |
projected exhaustion risk | active handovers | conserve/reserved state

Plus: important expected tasks today, likely assigned providers, capacity
risks, next important resets. Rendered with confidence labels; UNKNOWN shown
as UNKNOWN, never as zero. Delivered via existing morning channels.

## 17. Failure modes (design-level)

| Failure | Behaviour |
|---|---|
| Governor telemetry missing | qualification falls back to history-only; low confidence shown; no fabrication |
| Provider misreports quota | observed counters (429s, failures) override reported numbers; confidence drops |
| Floor-freeze bypass attempt | mechanical ordering: Governor queried only after freeze; code path cannot see pre-freeze state |
| Decomposition abuse (floor dodging) | §7 legality test + critic spot-check on split tasks |
| Brain itself broken | safe mode (§15) |
| Reserve leak (task never completes) | reserves time out and release after task terminal state |
| Handover loop (A→B→A) | handover chain length capped; then pause + owner |
| Estimate drift | every estimate carries confidence; low confidence triggers conservative action |

## 18. Data schemas (persistent state)

    TaskRecord, SubtaskRecord, QualityFloor (immutable), StrategyDecision,
    OverrideRecord (owner), ProviderTelemetry (time-series), ReserveState,
    HandoverRecord, PerformanceRow, SafeModeEvent, DailyBrief

Storage: local JSON/SQLite under Hermes home (raw, high-frequency) with
curated summaries published to the control-plane repo (state/,
resource-status/, decisions/) — consistent with the existing local/GitHub split.

## 19. Implementation phases (proposal only)

- Phase E1: schemas + floor-freeze ordering + manual routing discipline
  (Brain procedure documented; Governor as manual checklist)
- Phase E2: provider adapters + telemetry ledger + daily brief (deterministic)
- Phase E3: performance history + PROVEN/UNPROVEN gating + handover records
- Phase E4: predictive exhaustion + reserves (enforced, not advisory)
- Phase E5: safe mode + failure-mode drills + owner override UX

Each phase lands only after the previous is verified. No phase may weaken the
invariant; a phase that cannot enforce it ships disabled by default.

---

Owner decision requested: approve as baseline, amend, or reject. Nothing in
this document changes the running system.
