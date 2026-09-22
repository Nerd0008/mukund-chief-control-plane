# Executive Brain E3 — Architecture Amendment Proposal

Status: PROPOSED — revised per owner decisions D-AI-1 through D-AI-7 and corrections A1–A7
Date: 2026-09-22
Author: Chief of Staff (Hermes)
Supersedes: approved-architecture/executive-brain-v2.md §19 E3 description (narrow)
Target: approved-architecture/executive-brain-v2.md (NOT modified until approved)

---

## 1. Why this amendment exists

The currently approved baseline (executive-brain-v2.md) defines E3 narrowly:

> Phase E3: performance history + worker-state gating (UNPROVEN/EVALUATING/
> QUALIFIED/SUSPENDED) + Qualification Gate + handover records

That definition is now **insufficient**. During the 2026-09-22 architecture
discussion, the owner explicitly expanded E3 to:

> **E3 = Intelligent Multi-Model Orchestration + Dynamic Team Assembly + Worker Qualification**

This amendment proposes the expanded architecture and asks the owner to
approve it before implementation begins.

---

## 2. Baseline E3 components (still valid, kept from v2)

The following v2 E3 components remain valid and are **absorbed unchanged** into
the expanded design:

- Performance-learning schema (v2 §13)
- Worker states: UNPROVEN / EVALUATING / QUALIFIED / SUSPENDED (v2 §4)
- Cold-start qualification path (v2 §4b)
- Evidence tiers (provider claims, external benchmarks, internal verified)
- Minimum sample thresholds with coarse precision
- No universal model leaderboard
- Recency decay of stale evidence

These are **preserved**, not replaced.

---

## 3. Expanded E3 — new architecture

### 3.1 Core concept

E3 is **not** a model switcher and **not** a static router. It is a
temporary-team assembly system around each task.

Analogy: more like an AI manager building a temporary organization around a
problem than a model selector.

The AI proposes. The deterministic Qualification Gate decides.

### 3.2 E3 responsibilities (expanded)

| # | Responsibility | New in E3 | Previously in v2 |
|---|---|---|---|
| 1 | Task planner / decomposer | **new** | E1 had mechanics only |
| 2 | Decomposition quality gate (hybrid) | **new** | — |
| 3 | Execution DAG engine | **new** | — |
| 4 | Worker contract builder | **new** | — |
| 5 | Capability registry | **new** | — |
| 6 | Task fingerprinting | **new** | — |
| 7 | Historical similarity / experience retrieval | **new** | — |
| 8 | Three-evidence-class router | expanded | partial (§13) |
| 9 | AI routing / team assembly (advisory) | **new** | — |
| 10 | Central Qualification Gate (deterministic) | kept | §5a |
| 11 | Worker states + cold-start path | kept | §4 |
| 12 | Context compiler | **new** | — |
| 13 | Permission compiler | **new** | — |
| 14 | Multi-worker execution engine | **new** | — |
| 15 | Conflict detection / resolution | **new** | — |
| 16 | Integrator role (separate capability) | **new** | — |
| 17 | Independent verification path | **new** | — |
| 18 | Targeted rework | **new** | — |
| 19 | Intelligent replanning (logical) | **new** | — |
| 20 | Failure attribution | expanded | — |
| 21 | Performance learning + evidence storage | kept | §13 |
| 22 | Model identity / version drift handling | **new** | — |
| 23 | Exploration vs exploitation policy | **new** | — |
| 24 | Shadow evaluation (E3, not E4) | **new** | — |
| 25 | Router self-evaluation | **new** | — |
| 26 | Structured escalation / ask-owner | **new** | — |
| 27 | Logical convergence / loop prevention (risk-sensitive) | **new** | — |
| 28 | Event-sourced governance state | **new** | — |

### 3.3 What E3 does NOT absorb (phase boundaries preserved)

| Absorbed by | Responsibility |
|---|---|
| **E1** | Classification, immutable quality floors, decomposition mechanics, override recording, audit integrity |
| **E2** | Provider telemetry, capacity dimensions, Daily Resource Brief |
| **E4** | Predictive exhaustion enforcement, protected reserves, proactive resource-driven checkpoints, automatic resource-driven handover, runway calculations, equivalent-worker continuity under exhaustion |
| **E5** | Safe mode, failure drills, mature owner override UX |

---

## 4. E3 execution flow (proposed)

```
Task arrives
    ↓
E1 classifies → frozen quality floor (reasoning, verification, roles, risk, privacy, egress)
    ↓
E3 AI Planner: should this decompose?
    ├─ No  → single-node execution
    └─ Yes → propose subtask decomposition
              ↓
         Decomposition Quality Gate (HYBRID)
         ├─ Deterministic structural checks (DAG acyclic, deps valid, floors exist, fields exist,
         │  no illegal transitions, no unsafe shared-write parallelism, integration node exists,
         │  verification node exists)
         └─ Semantic decomposition review (AI critic): missing deliverables, unnecessary
            decomposition, semantic duplication, floor-dodging, bad capability separation,
            incorrect conceptual dependency
              ↓
         Build Execution DAG (nodes + dependencies)
              ↓
         For each node:
           - compute task fingerprint
           - retrieve historical similar executions
           - Deterministic meta-selector chooses router worker
           - AI Router proposes MULTIPLE candidate teams (advisory)
           - Central Qualification Gate validates each proposal (deterministic)
           - Context + Permission compilers package inputs
              ↓
         Execute per DAG state machine:
           PLANNED → BLOCKED → READY → RUNNING → VERIFYING
                     ↑                                  ↓
                     └──── REWORK ← FAILED ←───────────┘
                                 ↓
                            COMPLETE / PAUSED / CANCELLED
              ↓
         Integrator combines specialist outputs
              ↓
         Independent critic / deterministic verification
              ↓
         Targeted rework if defect found (risk-sensitive convergence)
              ↓
         Final verified deliverable
              ↓
         Failure attribution + performance learning + router self-evaluation
              ↓
         Evidence stored for future routing
```

If at any point the system gets stuck, has unresolvable conflict, hits a
broken dependency, repeatedly fails, cannot meet the floor, or requires an
owner decision → **ESCALATE / ASK OWNER** (never silently loop or downgrade).

---

## 5. Worker roster (from handover authority)

Handover file: `handovers/2026-09-22-e3-model-roster-handover.md`

This is the model-selection authority, not the ChatGPT discussion.

| # | Worker | Status | Notes |
|---|---|---|---|
| 1 | Codex CLI | LOCKED | Coding, repo work, implementation, debugging |
| 2 | Mistral Small 4 | LOCKED | General reasoning, instruction following, coding, FC, agents |
| 3 | Google Nano Banana 2 | LOCKED | Dedicated image generation/editing |
| 4 | DeepSeek V4.1 Flash | LOCKED | High-capability, low-cost reasoning/coding/long-context |
| 5 | GLM-5.3 Flash | LOCKED | Cheap high-volume reasoning/tool-use, parallel work |
| 6 | Qwen3.8-27B | LOCKED | Multimodal / vision-heavy, screenshots, GUI understanding |
| 7 | LongCat 2.0 | EVALUATE / KEEP | Existing Chief/Hermes model; retain until benchmarked |
| 8 | MiniMax M3 | BENCHMARK | Low-cost general/agent candidate |
| 9 | Step 3.7 Flash | BENCHMARK | Fast reasoning/agent, potential low-latency parallel worker |
| 10 | Tencent Hunyuan Hy3 | BENCHMARK | Very inexpensive reasoning/coding/tool-use, provider diversity |

Critical rules:
- "LOCKED" = included in initial pool, **not** qualified for any role
- No worker receives production capability qualification merely by roster inclusion
- Qualification remains evidence-based per (worker × task-family × capability-role)
- **Stage 2 clarification:** Any UNPROVEN worker executing Stage 2 work runs as **EVALUATION_ONLY** under cold-start rules. It does not become production-qualified simply because it belongs to the LOCKED roster.

---

## 6. Capability registry — initial role vocabulary

Stable roles (machine-readable, extensible):

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
- data-analyst
- context-compressor
- **router** (itself a capability role — D-AI-2)

Qualification key shape: `worker × task-family/fingerprint × capability-role`

A single model may qualify differently for different roles. There is NO
universal model score.

---

## 7. Task fingerprint (proposed dimensions)

Machine-readable dimensions for matching similar prior work:

- task_family
- domain
- language
- artifact_type
- repository_size
- context_size
- reasoning_depth (0–4)
- ambiguity (low / medium / high)
- tool_intensity (none / light / heavy)
- required_roles (list)
- security_privacy_class (P0–P3)
- risk_class (R0–R3)
- verification_type (deterministic / critic / owner)
- research_freshness (stale-tolerant / current-required)
- integration_complexity (none / low / medium / high)

Avoid false numerical precision. These are structured categorical dimensions,
not scalar scores.

---

## 8. Storage recommendation — separate orchestration database

### 8.1 Recommendation: **separate `orchestration.db`** (D-AI-1 APPROVED)

### 8.2 Analysis

Arguments for **extending exec_brain.db**:
- One database to manage
- E1 task IDs already there

Arguments against extending exec_brain.db:
- E1 is audited, immutable, append-only with hash chains
- E3 evidence is high-frequency, mutable (worker state changes), and noisy
- E3 retention policies differ from E1
- Qualification state changes would bloat E1 tables
- E2 precedent already established separation for telemetry

Arguments for **separation**:
- Protect E1 audit integrity from high-frequency E3 mutations
- Different retention: E1 immutable, E3 has decay/cleanup
- E2 precedent (governor.db separate from exec_brain.db) confirmed by owner
- Logical references to E1 IDs (task_id, floor_id) maintained via foreign-key-like fields without FK enforcement across databases
- Easier independent backup/restore/migration

Arguments against separation:
- Cross-db joins are manual (but this is local, single-process, acceptable)

### 8.3 Verdict

Use a **separate `orchestration.db`** with its own schema version,
independent migration path, and logical references to E1 IDs.

E3 can read E1 data (read-only access to exec_brain.db) but never writes to it.

---

## 9. AI vs deterministic boundary (preserved from v2)

The v2 architecture established a clean separation. E3 maintains it:

| AI does (advisory) | Deterministic Brain does (authoritative) |
|---|---|
| Propose decomposition | Accept/reject decomposition via quality gate |
| Propose candidate workers | Qualification Gate accept/reject |
| Build execution DAG | Enforce DAG state machine transitions |
| Compile context packages | Validate context against permission scope |
| Integrate outputs | Require independent verification |
| Decide rework needed | Confirm rework attribution before retry |

A provider or router CANNOT self-certify. AI proposals are EVIDENCE, not proof.
The Central Qualification Gate is the Brain-owned authority.

---

## 10. Owner decisions incorporated

### D-AI-1 — APPROVED: Separate orchestration.db

E1 exec_brain.db remains authoritative and protected.
E2 governor.db remains separate.
E3 orchestration/evidence state belongs in orchestration.db with logical references to E1 IDs.

### D-AI-2 — ROUTER AI: NO PERMANENT MODEL

"Router" is itself a capability role.

Architecture:
```
Deterministic meta-selector
    ↓
chooses an eligible router worker
    ↓
Router AI reasons about team assembly
    ↓
Qualification Gate checks its proposals
```

Avoid recursive "AI chooses the AI that chooses the AI".

For cold start / Stage 1:
- The currently operational Hermes inference worker may act as the BOOTSTRAP router
- It remains UNPROVEN for the router/planner capability
- Stage 1 is shadow-only, so it cannot authorize production execution
- Its routing decisions are reviewed and become evidence

Once qualified routing workers exist, the deterministic meta-selector chooses among them using:
- qualification evidence
- task requirements
- model/provider constraints
- E2 state
- uncertainty

The bootstrap worker must remain configurable; it is not permanent architecture.

### D-AI-3 — PLANNER AND ROUTER ARE SEPARATE LOGICAL ROLES

Planner and router are separate capabilities. A worker may perform both if independently qualified for both.

For high-complexity/high-risk decomposition: the decomposition reviewer/critic should be independent of the planner where a qualified alternative exists.

### D-AI-4 — SHADOW EVALUATION BELONGS TO E3

Shadow evaluation is worker qualification/learning and therefore belongs to E3 (not E4).

Implement support in E3 v1, but:
- Disabled by default
- Only usable for R0/R1 tasks
- Only where independent/deterministic verification exists
- Shadow output must never become authoritative production output merely because it exists
- Activation can be manual/owner-policy controlled during Stage 2

### D-AI-5 — EXPLORATION POLICY: CONSERVATIVE, POLICY-BASED

Do not hardcode an arbitrary exploration percentage.

Eligibility:
- R0/R1 only
- Objectively verifiable
- Failure has no material consequence
- Adequate E2 resource/cost state
- No secret/privacy violation

Default v1 limit:
- At most one experimental/shadow worker per eligible production task
- No exploration on R2/R3 production work
- Owner may tighten/disable exploration

Record exploration cost and outcome.

### D-AI-6 — CONVERGENCE / RETRY POLICY: RISK-SENSITIVE

Do not use a universal "N=3 reworks" rule. Use risk-sensitive convergence.

| Risk | Initial attempt | Recovery | Escalation |
|---|---|---|---|
| R0/R1 | 1 | Up to 2 targeted recovery attempts | Then stronger worker / REPLAN / ESCALATE |
| R2 | 1 | Maximum 1 autonomous targeted repair | Subsequent verified failure → stronger qualified route or ASK OWNER |
| R3 | 1 | No repeated autonomous repair loop after material verified failure | ASK OWNER / replan under owner-approved path |

The same defect surviving repeated attempts must cause escalation/replanning rather than prompt-looping.

Track attempts per defect, not merely total calls.

### D-AI-7 — INTEGRATOR IS A SEPARATE CAPABILITY ROLE

Do not hardcode the integrator model. Select integrators dynamically from workers qualified for the integrator role.

The same worker MAY be router/planner/integrator if independently qualified, but architecture must not assume this.

The integrator MUST NOT be the sole verifier of its own output.

For V3 / high-risk work, use an independent verifier/critic, preferably a different worker and where practical a different provider/model family.

---

## 11. Required architecture corrections

### A1 — DECOMPOSITION GATE MUST BE HYBRID

The decomposition gate is split into two layers:

**Layer 1: Deterministic structural checks**
- DAG acyclic
- Dependencies valid
- Referenced floors exist
- Required node fields exist
- No illegal state transitions
- No unsafe declared shared-write parallelism
- Integration node exists when multiple outputs require assembly
- Verification node/method exists where floor requires it

**Layer 2: Semantic decomposition review (AI critic)**
- Missing deliverables
- Unnecessary decomposition
- Semantic duplication
- Floor-dodging by artificial splitting
- Bad capability separation
- Incorrect conceptual dependency

The deterministic Brain still makes the final allow/reject decision based on the structured review result.

### A2 — E2 TELEMETRY ADAPTERS ≠ E3 EXECUTION ADAPTERS

Do NOT treat DeepSeek/Nous E2 telemetry adapters as already capable of dispatch.

E2 rollout explicitly did NOT implement provider API request routing.

Create a distinct E3 execution adapter interface for ALL workers.

Shared provider credential/config/client utilities may be reused, but dispatch capability must be independently implemented and tested.

Required interface includes at minimum:
- dispatch
- result retrieval
- timeout
- cancellation where supported
- structured error mapping
- observed usage
- provider/model identity
- execution metadata
- idempotency/retry semantics
- tool/permission enforcement where applicable

A provider becomes E3 routable only after its EXECUTION adapter passes qualification/smoke tests.

### A3 — E1/E2 PUBLIC INTERFACE BOUNDARY

"E3 never writes E1/E2 DB" means: E3 must not perform direct SQL writes to those databases.

But E3 MUST invoke the owning subsystem when required:

- For new/replanned subtasks: E3 → E1 public interface → classify/decompose/freeze. E1 remains sole writer to exec_brain.db.
- For every actual AI/provider execution: E3 execution adapter → E2 public record-request interface. E2 remains sole writer to governor.db.

This keeps E2 usage telemetry accurate.

### A4 — EVENT-SOURCED GOVERNANCE-CRITICAL STATE

Do not rely solely on mutable capability_registry rows and dag_node.state.

Add append-only event history:

**worker_capability_event**
- UNPROVEN → EVALUATING → QUALIFIED → SUSPENDED transitions
- Reason
- Evidence references
- Actor
- Timestamp
- Model identity

**dag_state_event**
- Node
- Previous state
- New state
- Cause
- Dispatch/verification reference
- Timestamp

Current-state tables/views may exist for fast reads but must be rebuildable from authoritative event history.

No silent rewriting of qualification history.

### A5 — UNKNOWN E2 CAPACITY SEMANTICS

Do NOT automatically reject a worker only because capacity is UNKNOWN.

UNKNOWN means unknown. Gate behaviour must consider:
- Risk
- Expected duration
- Task value
- Telemetry confidence
- Recent observed success/failure
- Alternative qualified routes

Possible outcomes:
- ACCEPT_WITH_LOW_RESOURCE_CONFIDENCE
- REJECT
- PAUSE
- OWNER_APPROVAL_REQUIRED

depending on policy.

Never reinterpret UNKNOWN as zero, unlimited, or healthy.

### A6 — LONG-TERM EVIDENCE RETENTION

Detailed execution artifacts may expire according to retention policy.

But do not discard the system's verified learning after 365 days.

Preserve indefinitely, or as a compact permanent evidence summary:
- Qualification transitions
- Serious failures
- Model identity/version
- Aggregate verified outcomes
- First-pass history
- Correction severity history
- Suspension/requalification events

Recency may reduce ROUTING WEIGHT without deleting historical provenance.

### A7 — ROUTER / PERFORMANCE DATA PRIVACY

Do not store raw chain-of-thought or unrestricted task content in router_decision.reasoning.

Store:
- Structured rationale codes
- Evidence references
- Concise non-sensitive rationale
- Confidence
- Candidate comparison metadata

No secrets. No provider credentials. No raw sensitive prompts in GitHub. Apply local privacy/retention constraints to orchestration.db.

---

## 12. Boundaries — E3 must NOT implement

- Worker qualification bypass
- Predictive exhaustion enforcement (E4)
- Protected reserve enforcement (E4)
- Automatic checkpoints/handover driven by resources (E4)
- Runway calculations (E4)
- Safe mode automation (E5)
- Permanent model-role mapping
- Universal model score / leaderboard
- Provider marketing as qualification evidence
- Shadow evaluation as production authority

Forward-compatibility with E4/E5 schemas is acceptable. Implementing their
behavior is not.

---

## 13. Conflicts discovered with E1/E2

### 13.1 With E1
- **No conflicts.** E1 schema remains authoritative. E3 reads E1 data via E1 public interface, never writes directly. Decomposition in E3 uses E1's decomposition records/floor discipline as its foundation. E3 does not mutate E1 history or frozen floors.
- New/replanned subtasks go through the E1 floor process before worker routing.

### 13.2 With E2
- **No conflicts.** E2 telemetry is consumed by E3 as routing evidence via E2 public interface. Resource scarcity may change WHICH qualified worker is selected, but NEVER lowers the E1 quality floor. This is already enforced by the No-Degradation Invariant.
- Codex and Antigravity are observed-only / non-routable in E2. E3 must handle this truthfully — do not dispatch to a provider with no automation path.
- E2 UNKNOWN telemetry must not be interpreted as routable/unroutable by itself. E3 uses its own capability registry + qualification evidence for routing, with UNKNOWN handled per A5.

---

## 14. Provider execution adapters required

For the 10-worker roster to be dispatchable, E3 requires a distinct execution adapter interface (per A2):

| Worker | Interface | E2 telemetry adapter | E3 execution adapter |
|---|---|---|---|
| Codex CLI | CLI | observed-only | CLI automation adapter (new) |
| Mistral Small 4 | API (OpenAI-compatible) | — | API adapter (new) |
| Google Nano Banana 2 | API (Google) | — | API adapter (new) |
| DeepSeek V4.1 Flash | API (DeepSeek) | routable | Execution adapter (new, may reuse credential/config utilities) |
| GLM-5.3 Flash | API (OpenAI-compatible) | — | API adapter (new) |
| Qwen3.8-27B | API | — | API adapter (new) |
| LongCat 2.0 | API (Nous) | routable | Execution adapter (new, may reuse credential/config utilities) |
| MiniMax M3 | API | — | API adapter (new) |
| Step 3.7 Flash | API | — | API adapter (new) |
| Tencent Hunyuan Hy3 | API | — | API adapter (new) |

Key insight: E2 adapters provide telemetry, not dispatch. Each worker needs an independent E3 execution adapter that passes qualification/smoke tests before becoming routable.

---

## 15. Amendment acceptance criteria

This amendment is approved when the owner confirms:

1. E3 = Intelligent Multi-Model Orchestration + Dynamic Team Assembly + Worker Qualification
2. Separate `orchestration.db` (D-AI-1)
3. All 28 E3 responsibilities listed above
4. Router AI has no permanent model; bootstrap router is configurable (D-AI-2)
5. Planner and router are separate logical roles (D-AI-3)
6. Shadow evaluation belongs to E3, disabled by default (D-AI-4)
7. Exploration policy is conservative, policy-based (D-AI-5)
8. Convergence is risk-sensitive, not universal N=3 (D-AI-6)
9. Integrator is a separate capability role (D-AI-7)
10. Decomposition gate is hybrid (A1)
11. E2 telemetry adapters ≠ E3 execution adapters (A2)
12. E3 invokes E1/E2 public interfaces, never writes directly (A3)
13. Event-sourced governance state for capability and DAG transitions (A4)
14. UNKNOWN capacity handled per policy, not auto-rejected (A5)
15. Long-term evidence retention preserves learning (A6)
16. Router/performance data privacy enforced (A7)
17. E4/E5 boundaries preserved
18. E1/E2 integration rules preserved
19. Provider adapter roster and interface strategy accepted

Once approved, the amendment is applied to `approved-architecture/executive-brain-v2.md`
and the E3 implementation plan is written.

---

## 16. Summary of architecture changes proposed

| Area | Current v2 | Proposed E3 |
|---|---|---|
| E3 scope | Narrow (history + gating + handover records) | Full orchestration + team assembly + qualification |
| Storage | Not specified | Separate orchestration.db |
| AI role | Not specified | AI proposes, deterministic gate decides |
| Router | Not specified | Capability role, no permanent model, bootstrap configurable |
| Planner | Not present | First-class AI task planner, separate from router |
| DAG | Not present | Full DAG state machine with event-sourced transitions |
| Context compiler | Not present | Minimum sufficient context packaging |
| Permission compiler | Not present | Per-role permission scoping |
| Integrator | Not present | First-class capability role, dynamically selected |
| Verification | V-level in floor | Independent critic + deterministic checks |
| Replan | Not present | Versioned logical replanning |
| Escalation | §14 partial | Structured ask-owner with risk-sensitive loop prevention |
| Router self-eval | Not specified | Routing decision evidence |
| Model identity drift | Not specified | Bounded evidence to model identity |
| Shadow evaluation | Not present | E3-owned, disabled by default |
| Decomposition gate | Not specified | Hybrid: deterministic structural + AI semantic review |
| E1/E2 boundary | Not specified | Public interface invocation, no direct writes |
| Governance state | Not specified | Event-sourced append-only history |
| UNKNOWN handling | Not specified | Policy-based, not auto-reject |
| Evidence retention | Not specified | Long-term permanent evidence summary |
| Data privacy | Not specified | Structured rationale only, no raw CoT |

---

This document does not modify any running system. It is a proposal awaiting
owner approval.
