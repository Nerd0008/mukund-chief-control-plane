# Executive Brain E3 — Architecture Amendment Proposal

Status: PROPOSED — not yet approved
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
| 2 | Decomposition quality gate | **new** | — |
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
| 16 | Integrator role | **new** | — |
| 17 | Independent verification path | **new** | — |
| 18 | Targeted rework | **new** | — |
| 19 | Intelligent replanning (logical) | **new** | — |
| 20 | Failure attribution | expanded | — |
| 21 | Performance learning + evidence storage | kept | §13 |
| 22 | Model identity / version drift handling | **new** | — |
| 23 | Exploration vs exploitation policy | **new** | — |
| 24 | Router self-evaluation | **new** | — |
| 25 | Structured escalation / ask-owner | **new** | — |
| 26 | Logical convergence / loop prevention | **new** | — |

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
         Decomposition Quality Gate (deterministic review)
              ↓
         Build Execution DAG (nodes + dependencies)
              ↓
         For each node:
           - compute task fingerprint
           - retrieve historical similar executions
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
         Targeted rework if defect found
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

### 8.1 Recommendation: **separate `orchestration.db`**

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

## 10. Boundaries — E3 must NOT implement

- Worker qualification bypass
- Predictive exhaustion enforcement (E4)
- Protected reserve enforcement (E4)
- Automatic checkpoints/handover driven by resources (E4)
- Runway calculations (E4)
- Safe mode automation (E5)
- Permanent model-role mapping
- Universal model score / leaderboard
- Provider marketing as qualification evidence

Forward-compatibility with E4/E5 schemas is acceptable. Implementing their
behavior is not.

---

## 11. Unresolved owner decisions

These need explicit owner approval before implementation:

| # | Decision |
|---|---|
| D-AI-1 | Separate `orchestration.db` approved? (recommended: yes) |
| D-AI-2 | Router AI model: which model class performs team assembly reasoning? (candidate: a strong reasoning model, not necessarily premium) |
| D-AI-3 | Planner AI model: same as router, or separate? |
| D-AI-4 | Shadow evaluation in E3 v1, or deferred to E4? |
| D-AI-5 | Exploration rate for cold-start evaluation: how aggressive? |
| D-AI-6 | Convergence retry limits: what are the justified numbers? |
| D-AI-7 | Integrator model: same model class as router, or separate role-specific model? |

---

## 12. Conflicts discovered with E1/E2

### 12.1 With E1
- **No conflicts.** E1 schema remains authoritative. E3 reads E1 data,
  never writes. Decomposition in E3 uses E1's decomposition records/floor
  discipline as its foundation. E3 does not mutate E1 history or frozen floors.
- New/replanned subtasks go through the E1 floor process before worker routing.

### 12.2 With E2
- **No conflicts.** E2 telemetry is consumed by E3 as routing evidence.
  Resource scarcity may change WHICH qualified worker is selected, but NEVER
  lowers the E1 quality floor. This is already enforced by the No-Degradation
  Invariant.
- Codex and Antigravity are observed-only / non-routable in E2. E3 must handle
  this truthfully — do not dispatch to a provider with no automation path.
- E2 UNKNOWN telemetry must not be interpreted as routable/unroutable by itself.
  E3 uses its own capability registry + qualification evidence for routing.

---

## 13. Provider execution adapters required

For the 10-worker roster to be dispatchable, E3 requires:

| Worker | Interface | Adapter status in E2 | E3 requirement |
|---|---|---|---|
| Codex CLI | CLI spawn | observed-only | CLI automation adapter |
| Mistral Small 4 | API (OpenAI-compatible) | — | API adapter |
| Google Nano Banana 2 | API (Google) | — | API adapter |
| DeepSeek V4.1 Flash | API (DeepSeek) | routable | existing E2 adapter reuse |
| GLM-5.3 Flash | API (OpenAI-compatible) | — | API adapter |
| Qwen3.8-27B | API | — | API adapter |
| LongCat 2.0 | API (Nous) | routable | existing E2 adapter reuse |
| MiniMax M3 | API | — | API adapter |
| Step 3.7 Flash | API | — | API adapter |
| Tencent Hunyuan Hy3 | API | — | API adapter |

Key insight: E2 already has DeepSeek and Nous adapters. Codex/Antigravity need
CLI/API enablement before they become routable. The remaining 6 require new
adapters.

---

## 14. Amendment acceptance criteria

This amendment is approved when the owner confirms:

1. E3 = Intelligent Multi-Model Orchestration + Dynamic Team Assembly + Worker Qualification
2. Separate `orchestration.db` (not extending exec_brain.db)
3. All 26 E3 responsibilities listed above
4. E4/E5 boundaries preserved
5. E1/E2 integration rules preserved
6. Provider adapter roster and interface strategy accepted
7. All D-AI-* decisions resolved

Once approved, the amendment is applied to `approved-architecture/executive-brain-v2.md`
and the E3 implementation plan is written.

---

## 15. Summary of architecture changes proposed

| Area | Current v2 | Proposed E3 |
|---|---|---|
| E3 scope | Narrow (history + gating + handover records) | Full orchestration + team assembly + qualification |
| Storage | Not specified | Separate orchestration.db |
| AI role | Not specified | AI proposes, deterministic gate decides |
| Planner | Not present | First-class AI task planner |
| DAG | Not present | Full DAG state machine |
| Context compiler | Not present | Minimum sufficient context packaging |
| Permission compiler | Not present | Per-role permission scoping |
| Integrator | Not present | First-class capability role |
| Verification | V-level in floor | Independent critic + deterministic checks |
| Replan | Not present | Versioned logical replanning |
| Escalation | §14 partial | Structured ask-owner with loop prevention |
| Router self-eval | Not present | Routing decision evidence |
| Model identity drift | Not present | Bounded evidence to model identity |

---

This document does not modify any running system. It is a proposal awaiting
owner approval.
