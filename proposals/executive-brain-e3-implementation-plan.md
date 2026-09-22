# Executive Brain E3 — Implementation Plan

Status: PROPOSED — not yet approved
Date: 2026-09-22
Author: Chief of Staff (Hermes)
Requires: E3 architecture amendment approval first
Target rollout: staged (shadow → low-risk → qualified orchestration → broad)

---

## 1. Plan purpose

This plan implements the expanded E3 architecture as described in
`architecture-proposals/executive-brain-e3-architecture-amendment.md`.

It assumes the amendment is approved. Do NOT implement until then.

---

## 2. Phase status (read-only context)

| Phase | Status | What it provides E3 |
|---|---|---|
| **E1** | ACTIVE, verified | Classification, frozen quality floors, audit integrity, decomposition mechanics |
| **E2** | ACTIVE, verified | Provider telemetry, capacity dimensions, Daily Resource Brief |
| **E3** | PLANNED | Intelligent orchestration, team assembly, worker qualification |
| **E4** | NOT STARTED | Predictive exhaustion, reserves, resource-driven handover |
| **E5** | NOT STARTED | Safe mode, failure drills, owner override UX |

---

## 3. E3 architecture recap

E3 = **Intelligent Multi-Model Orchestration + Dynamic Team Assembly + Worker Qualification**

- AI proposes teams, plans decompositions, builds contracts
- Deterministic Qualification Gate decides what is allowed
- E1 floors are never lowered by resource pressure or router opinion
- E2 telemetry informs but never overrides qualification

---

## 4. Worker roster

From: `handovers/2026-09-22-e3-model-roster-handover.md` (authority)

| # | Worker | Pool status | Interface |
|---|---|---|---|
| 1 | Codex CLI | LOCKED | CLI |
| 2 | Mistral Small 4 | LOCKED | API |
| 3 | Google Nano Banana 2 | LOCKED | API |
| 4 | DeepSeek V4.1 Flash | LOCKED | API |
| 5 | GLM-5.3 Flash | LOCKED | API |
| 6 | Qwen3.8-27B | LOCKED | API |
| 7 | LongCat 2.0 | EVALUATE | API |
| 8 | MiniMax M3 | BENCHMARK | API |
| 9 | Step 3.7 Flash | BENCHMARK | API |
| 10 | Tencent Hunyuan Hy3 | BENCHMARK | API |

---

## 5. E3 components — full design

### 5.1 AI Task Planner

**Purpose:** Consumes E1 classification + original objective + task context.
Determines whether the task should remain whole or decompose.

**Inputs:**
- E1 classification record (task_type, capability_roles, reasoning_depth, risk_class, etc.)
- Original objective (request_text)
- Current task context (any existing subtasks, decisions)
- Frozen constraints (where applicable)

**Logic:**
- If task is simple / mechanical / single-role → single-node execution
- If task is complex / multi-role / parallelizable → propose decomposition
- Uses AI reasoning (planner model)
- Planner may be same or different from router model (owner decision D-AI-3)

**Output:** Single-node plan OR proposed decomposition

---

### 5.2 Decomposition Quality Gate

**Purpose:** Deterministic review of a proposed decomposition BEFORE execution.

**Checks:**
- Missing deliverables vs original objective
- Incorrect dependencies (circular, invalid order)
- Invalid parallelism (shared mutable state across parallel nodes)
- Unnecessary decomposition (could be one node)
- Floor-dodging decomposition (split to route around a floor)
- Missing integration step
- Missing verification step
- Duplicated work across nodes

**For high-complexity / high-risk plans:** support independent review (secondary critic)

**Output:** APPROVED / REJECTED with reasons

---

### 5.3 Execution DAG

**Purpose:** Represent complex work as a dependency graph.

**Node fields:**

| Field | Type | Description |
|---|---|---|
| node_id | string | Stable node identifier |
| task_subtask_id | string | Logical reference to E1 task/subtask |
| objective | string | Exact objective for this node |
| capability_roles | list | Required roles (builder, critic, etc.) |
| dependencies | list[node_id] | Nodes that must complete before this node |
| inputs | json | Upstream artifacts / context references |
| expected_outputs | json | Artifact spec / schema |
| floor_id | string | Reference to frozen quality floor |
| allowed_tools | list | Tool identifiers permitted |
| permissions | json | Permission compiler output |
| verification_method | enum | test / schema / comparison / critic / owner |
| assigned_worker | string | Worker id (after routing) |
| fallback_candidates | list | Alternative workers |
| state | enum | PLANNED/BLOCKED/READY/RUNNING/VERIFYING/REWORK/COMPLETE/FAILED/PAUSED/CANCELLED |
| attempts | int | Number of execution attempts |

**State transitions:**
- PLANNED → BLOCKED (dependencies not met)
- BLOCKED → READY (all dependencies COMPLETE)
- READY → RUNNING (dispatched to worker)
- RUNNING → VERIFYING (worker returned output)
- RUNNING → FAILED (worker error / timeout)
- VERIFYING → COMPLETE (verification passed)
- VERIFYING → REWORK (defect found, targeted rework)
- REWORK → RUNNING (retry with affected node)
- * → PAUSED (no qualified route / escalation)
- * → CANCELLED (replan invalidated this node)

---

### 5.4 Worker Contract

**Purpose:** Structure each assignment so workers receive exact objectives, not vague prompts.

**Fields:**
- exact_objective
- relevant_inputs
- required_output_schema / artifact_spec
- constraints
- quality_floor_reference
- allowed_tools
- permission_scope
- verification_method
- definition_of_done

---

### 5.5 Capability Registry

**Purpose:** Track worker capabilities contextually.

**Key shape:** `worker × task-family/fingerprint × capability-role`

**Initial role vocabulary:**
planner, researcher, scout, architect, builder, debugger, critic, verifier, integrator, writer, classifier, vision, data-analyst, context-compressor

**Fields per entry:**
- worker_id
- task_family (fuzzy match key)
- capability_role
- state: UNPROVEN | EVALUATING | QUALIFIED | SUSPENDED
- evidence_count
- first_pass_success_rate
- last_qualified_at
- last_failure_at
- failure_severity_if_suspended

**No universal model score.** A model may be QUALIFIED for builder and UNPROVEN for architect.

---

### 5.6 Task Fingerprinting

**Purpose:** Machine-readable task characterization for similarity matching.

**Dimensions:**
- task_family: enum (from E1 task_type)
- domain: string
- language: string
- artifact_type: enum (code, doc, config, analysis, etc.)
| repository_size: enum (none, small, medium, large)
| context_size: enum (small, medium, large)
| reasoning_depth: 0–4
| ambiguity: low | medium | high
| tool_intensity: none | light | heavy
| required_roles: list
| security_privacy_class: P0–P3
| risk_class: R0–R3
| verification_type: deterministic | critic | owner
| research_freshness: stale-tolerant | current-required
| integration_complexity: none | low | medium | high

Categorical, not scalar. Avoid false precision.

---

### 5.7 Historical Similarity / Experience Retrieval

**Purpose:** Before worker selection, retrieve relevant prior executions.

**Storage:** Performance rows in orchestration.db (see §6 schema).

**Retrieval approach (v1 — deterministic, no vector DB):**

1. Extract task fingerprint from current task
2. Query prior executions matching on:
   - task_family (exact match)
   - reasoning_depth (±1)
   - tool_intensity (exact or adjacent)
   - required_roles (overlap)
   - risk_class (exact or adjacent)
3. Score similarity by weighted dimension match
4. Return top-K most similar prior executions with outcomes

**Why no vector DB for v1:** The dataset is small (<1000 rows initially),
similarity is on categorical dimensions, and deterministic SQL queries are
auditable. Vector DB can be added later if categorical matching proves insufficient.

---

### 5.8 Three Evidence Classes

| Tier | Source | Weight |
|---|---|---|
| TIER 1 — provider claims | Model cards, provider docs, marketing | Lowest |
| TIER 2 — external evidence | Benchmarks, independent evals, comparisons | Medium |
| TIER 3 — internal verified experience | E3 execution outcomes, deterministic tests | Highest |

Rules:
- Provider marketing alone NEVER establishes QUALIFIED
- External evidence alone NEVER establishes QUALIFIED
- Internal verified experience is the strongest operational weight
- Evidence decays over time (recency matters)

---

### 5.9 AI Routing / Team Assembly

**Purpose:** Given a task fingerprint + required roles + constraints,
propose candidate workers.

**Inputs:**
- Task fingerprint
- Required roles
- E1 frozen floor
- Worker registry (capability states)
- Historical evidence (similar past executions)
- Provider/model constraints (context limits, tool support)
- E2 telemetry (provider capacity)
- Cost / latency / uncertainty hints

**Output:** MULTIPLE candidate proposals ranked:

```
candidate A: confidence HIGH
  - worker: DeepSeek V4.1 Flash
  - role: builder
  - why: strong evidence on similar tasks, E2 provider healthy, cost low
  
candidate B: confidence MEDIUM
  - worker: GLM-5.3 Flash
  - role: builder
  - why: cheaper but less evidence on this task family

candidate C: confidence LOW / evaluation
  - worker: Step 3.7 Flash
  - role: builder
  - why: benchmark candidate, no production evidence yet
```

Router is **advisory.** The Qualification Gate decides.

---

### 5.10 Central Qualification Gate

**Purpose:** Brain-owned deterministic gate that decides whether each
router proposal is allowed.

**Inputs:**
- Router proposal (worker, role, confidence)
- E1 frozen floor (min_reasoning_depth, required_roles, verification_level, risk, egress)
- Worker state (UNPROVEN/EVALUATING/QUALIFIED/SUSPENDED)
- Task risk class
- Verification requirement
- Privacy / egress constraints
- Tool support requirements
- Context constraints
- Model identity (provider + model id + version)
- Provider state from E2

**Outputs:** ACCEPT | REJECT | EVALUATION_ONLY | OWNER_APPROVAL_REQUIRED

**Rejection reasons (machine-readable):**
- FLOOR_REASONING_TOO_LOW
- FLOOR_VERIFICATION_TOO_LOW
- WORKER_SUSPENDED
- WORKER_UNPROVEN_ON_HIGH_RISK
- PROVIDER_NOT_ROUTABLE
- PROVIDER_CAPACITY_UNKNOWN
- EGRESS_VIOLATION
- TOOL_SUPPORT_INSUFFICIENT
- CONTEXT_WINDOW_INSUFFICIENT
- OWNER_POLICY_REJECTION

---

### 5.11 Worker States

| State | Meaning | Allowed work |
|---|---|---|
| UNPROVEN | No verified evidence | Evaluation only (R0/R1 + independent verification) |
| EVALUATING | Running controlled evaluation | Evaluation only |
| QUALIFIED | Task-specific verified evidence meets threshold | Production work within qualified scope |
| SUSPENDED | Serified verified failure | Excluded from routing |

Qualification is task/role specific:
- Worker X: large-Python/builder → QUALIFIED
- Worker X: security/architect → EVALUATING
- Worker X: research/researcher → UNPROVEN

A serious VERIFIED failure → immediate SUSPENDED for that specific (task_family, role) pair.

---

### 5.12 Context Compiler

**Purpose:** Build the minimum sufficient context package for each worker.

**Include only:**
- Original objective (where relevant)
- Worker contract
- Necessary upstream outputs
- Selected source files (not whole repo unless justified)
- Relevant decisions
- Constraints and assumptions

**Do NOT dump:**
- Complete chat history
- Whole repositories
- Irrelevant outputs
- Unrelated personal data
- Secrets

Prefer deterministic context packaging (file lists, line ranges, schemas).

---

### 5.13 Permission Compiler

**Purpose:** Different workers get different permissions.

**Policy shapes:**

| Role | Permissions |
|---|---|
| researcher | web access + read-only inputs |
| architect | repository read-only |
| builder | controlled worktree + terminal + tests |
| critic | read-only artifacts / diff / test results |
| integrator | approved artifacts + controlled write scope |

Enforce technically where possible (worktree isolation, read-only mounts,
network policies), not just prompt text.

---

### 5.14 Multi-Worker Execution

**Supported modes:**

1. **Sequential** — Node B runs after Node A completes
2. **Independent parallel** — Nodes with no shared mutable state run concurrently
3. **Staged** — Phase 1 (research) → Phase 2 (design) → Phase 3 (build)
4. **Multiple-specialist** — Different workers for different roles in same phase

**Constraint:** Never parallelize nodes that can corrupt shared mutable state.

---

### 5.15 Conflict Detection / Resolution

**Trigger:** Specialist outputs conflict.

**Procedure:**
1. Identify the disputed claim/assumption
2. Gather relevant evidence
3. Use an independent critic where useful
4. Resolve explicitly (record decision)
5. Update downstream work

**The Integrator may NOT silently choose between important contradictory outputs.**
Conflicts must be surfaced.

---

### 5.16 Integrator Role

**Responsibilities:**
- Combine specialist outputs
- Reconcile interfaces
- Remove duplication
- Preserve original objective
- Identify missing pieces
- Detect contradictions
- Request targeted rework

**Critical rule:** Integrator cannot self-certify the final result.
Independent verification is required.

**Integrator is itself a capability role** with accumulated evidence.

---

### 5.17 Independent Verification

**Order of preference:**
1. Deterministic verification (tests, schema validation, compiler/type checks, source comparison, data validation, static analysis)
2. AI critic (independent worker, different from integrator)
3. Owner review (for V3 or high-risk tasks)

After integration:
- Integrator → independent critic (where required) → deterministic verification → done

---

### 5.18 Targeted Rework

**Purpose:** Don't restart the entire DAG after one defect.

**Procedure:**
1. Verification identifies affected node(s)
2. Only the affected worker/node returns to REWORK
3. Downstream reintegration/reverification
4. Preserve unaffected completed work

---

### 5.19 Intelligent Replanning

**Trigger:** Execution reveals the plan itself was wrong.

**Allowed when:**
- Hidden dependency discovered
- Assumption invalidated
- New required work appears
- Upstream artifact changes requirements

**Procedure:**
- Preserve valid completed work
- Record trigger
- Version the plan
- Create/cancel nodes
- Freeze new required floors using E1
- Re-run qualification for changed assignments

**This is logical/task replanning. NOT resource-driven checkpoint/handover (E4).**

---

### 5.20 Failure Attribution

**Categories:**

| Category | Meaning |
|---|---|
| planning | Plan itself was wrong |
| decomposition | Decomposition missed something |
| factual_error | Worker produced wrong facts |
| reasoning | Logic was wrong |
| implementation | Code/artifact was wrong |
| tool-use | Tool misuse |
| context | Missing or wrong context |
| integration | Assembly failed |
| verification_miss | Verifier failed to catch defect |
| environment | External system failure |
| external_dependency | Third-party failure |

**Rules:**
- Only attributable failures affect worker qualification evidence
- Verifier receives positive evidence if it correctly catches another worker's defect

---

### 5.21 Performance Learning

**Record per worker assignment:**

| Field | Type |
|---|---|
| worker_id | string |
| task_fingerprint | json |
| role | string |
| model | string |
| provider | string |
| reasoning_profile | string |
| execution_profile | string |
| tools | list |
| first_pass_success | bool |
| final_success | bool |
| verification_outcome | enum |
| deterministic_test_results | json |
| retries | int |
| corrections | int |
| correction_severity | enum |
| failure_attribution | enum |
| runtime_s | int |
| usage_tokens | int |
| monetary_cost | float |
| floor_id | string |
| timestamp | datetime |

This becomes evidence for future team assembly.

---

### 5.22 Model Identity Drift

**Bind evidence to:**
- provider
- model id
- model/version/snapshot where exposed
- reasoning profile
- tool environment
- date range

A materially changed model must NOT automatically inherit full confidence
from historical evidence. Detect drift via version/snapshot changes and
reset affected evidence toward UNPROVEN.

---

### 5.23 Exploration vs Exploitation

| Risk | Policy |
|---|---|
| High-risk / critical | Prefer strong proven evidence |
| Low-risk objectively verifiable | Allow controlled evaluation of promising workers |

Future shadow evaluation support (production + shadow workers) designed
into schema but NOT enabled for E3 v1 (owner decision D-AI-4).

---

### 5.24 Router Self-Evaluation

**Record:** Did the routing decision itself prove good?

- Router selected worker A → A succeeded first pass → positive routing evidence
- Router ignored stronger evidence and selected B → B required rework → poor routing evidence

Allows future improvement of management logic.

---

### 5.25 Structured Escalation

**Trigger when E3:**
- Gets stuck
- Encounters unexplained error
- Has conflicting evidence it cannot resolve
- Repeatedly fails
- Hits broken dependency
- Cannot meet the quality floor
- Requires an owner decision

**Never silently:**
- Loop
- Downgrade
- Guess
- Hide failure

Escalation is a first-class state: `ESCALATED → owner responds → continue/replan/cancel`

---

### 5.26 Logical Convergence Rules

| Condition | Action |
|---|---|
| Verification PASS | → COMPLETE |
| Specific defect found | → TARGETED REWORK |
| Same defect survives N attempts | → stronger worker or REPLAN |
| Fundamental assumption invalid | → REPLAN |
| No qualified route exists | → PAUSE |
| Owner-decidable ambiguity | → ASK OWNER |

Retry limits: justified, not arbitrary. N=3 default for REWORK attempts
before escalation (owner decision D-AI-6).

---

## 6. Storage design

### 6.1 Recommendation: separate `orchestration.db`

See architecture amendment §8 for analysis. Approved by owner decision D-AI-1.

### 6.2 Local paths

```
%LOCALAPPDATA%\hermes\exec-brain\
  orchestration.db        — E3 orchestration + evidence
  orchestration-chain-head.json  — audit chain anchor
  eb.py                   — extended with E3 commands
  adapters.py             — provider adapters (extended)
  governor.py             — E2 governor (unchanged)
  governor.db             — E2 governor DB (unchanged)
  exec_brain.db           — E1 DB (unchanged)
```

### 6.3 GitHub curated publication

```
mukund-chief-control-plane/
  resource-status/            — E2 continues
  orchestration-status/       — E3 curated summaries
    team-assembly-log.md      — last routing decisions
    worker-qualification.md   — current worker states
    execution-summary.md      — recent DAG executions
    evidence-stats.md         — evidence counts per worker
  decisions/
    exec-brain-e3-rollout.md
```

### 6.4 Schemas

#### orchestration.db tables

```sql
-- DAG node tracking
CREATE TABLE dag_node (
    node_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    task_subtask_id TEXT,
    objective TEXT NOT NULL,
    capability_roles TEXT NOT NULL,  -- JSON list
    dependencies TEXT NOT NULL,      -- JSON list of node_ids
    inputs TEXT,                     -- JSON
    expected_outputs TEXT,           -- JSON artifact spec
    floor_id TEXT,                   -- references E1 floor
    allowed_tools TEXT,              -- JSON list
    permissions TEXT,                -- JSON
    verification_method TEXT NOT NULL DEFAULT 'test',
    assigned_worker TEXT,
    fallback_candidates TEXT,        -- JSON list
    state TEXT NOT NULL DEFAULT 'PLANNED',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Worker capability registry
CREATE TABLE capability_registry (
    worker_id TEXT NOT NULL,
    task_family TEXT NOT NULL,
    capability_role TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'UNPROVEN',
    evidence_count INTEGER NOT NULL DEFAULT 0,
    first_pass_successes INTEGER NOT NULL DEFAULT 0,
    first_pass_attempts INTEGER NOT NULL DEFAULT 0,
    last_qualified_at TEXT,
    last_failure_at TEXT,
    failure_severity TEXT,
    PRIMARY KEY (worker_id, task_family, capability_role)
);

-- Performance evidence rows
CREATE TABLE performance_evidence (
    evidence_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    task_fingerprint TEXT NOT NULL,  -- JSON
    role TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    reasoning_profile TEXT,
    execution_profile TEXT,
    tools TEXT,                      -- JSON list
    first_pass_success INTEGER,
    final_success INTEGER,
    verification_outcome TEXT,
    deterministic_test_results TEXT, -- JSON
    retries INTEGER NOT NULL DEFAULT 0,
    corrections INTEGER NOT NULL DEFAULT 0,
    correction_severity TEXT,
    failure_attribution TEXT,
    runtime_s INTEGER,
    usage_tokens INTEGER,
    monetary_cost REAL,
    floor_id TEXT,                   -- references E1 floor
    dag_node_id TEXT,                -- references dag_node
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Historical task similarity cache (deterministic matching metadata)
CREATE TABLE task_fingerprint_index (
    fingerprint_id TEXT PRIMARY KEY,
    task_family TEXT NOT NULL,
    reasoning_depth INTEGER,
    tool_intensity TEXT,
    risk_class TEXT,
    required_roles TEXT,             -- JSON list
    evidence_id TEXT,                -- links to performance_evidence
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Router decisions (for self-evaluation)
CREATE TABLE router_decision (
    decision_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    proposed_worker TEXT NOT NULL,
    proposed_role TEXT NOT NULL,
    confidence TEXT NOT NULL,        -- HIGH / MEDIUM / LOW
    reasoning TEXT,
    gate_decision TEXT NOT NULL,     -- ACCEPT / REJECT / EVALUATION_ONLY / OWNER_APPROVAL_REQUIRED
    gate_reasons TEXT,               -- JSON list of rejection codes
    actual_outcome TEXT,             -- SUCCESS / FAILURE / REWORK / ESCALATED
    outcome_matches_proposal INTEGER, -- did router get it right?
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Conflict records
CREATE TABLE conflict_record (
    conflict_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    node_a TEXT NOT NULL,
    node_b TEXT NOT NULL,
    disputed_claim TEXT,
    resolution TEXT,
    resolved_by TEXT,                -- worker id or 'owner'
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Plan versions (for replanning)
CREATE TABLE plan_version (
    plan_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    parent_plan_id TEXT,
    trigger TEXT,                    -- why replanned
    dag_nodes TEXT NOT NULL,         -- JSON: current node set
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 6.5 Append-only / audit tables

Append-only tables (never UPDATE/DELETE):
- performance_evidence
- router_decision
- conflict_record
- plan_version

Mutable tables:
- dag_node (state transitions are updates)
- capability_registry (state transitions are updates)

### 6.6 Chain integrity

Hash-chained tables: performance_evidence, router_decision
- seq INTEGER PRIMARY KEY AUTOINCREMENT
- record_sha256 TEXT NOT NULL (SHA-256 of canonical JSON of the row)
- prev_sha256 TEXT (SHA-256 of previous row, for chain verification)
- Chain head anchor: `orchestration-chain-head.json`

### 6.7 Retention policy

| Data | Retention |
|---|---|
| DAG node records | 90 days |
| Capability registry | indefinite (mutable, small) |
| Performance evidence | 365 days |
| Task fingerprint index | 365 days |
| Router decisions | 365 days |
| Conflict records | 365 days |
| Plan versions | 365 days |

---

## 7. Provider execution adapters

### 7.1 Adapter interface

Each adapter must implement:

```python
class ProviderAdapter:
    def dispatch(contract: WorkerContract) -> DispatchResult
    def cancel(dispatch_id: str) -> bool
    def check_health() -> HealthStatus
    def get_capabilities() -> CapabilityProfile
```

### 7.2 Adapter requirements per worker

| Worker | Adapter type | E2 status | E3 requirement |
|---|---|---|---|
| Codex CLI | CLI | observed-only | CLI automation adapter |
| Mistral Small 4 | API (OpenAI-compatible) | — | New API adapter |
| Google Nano Banana 2 | API (Google) | — | New API adapter |
| DeepSeek V4.1 Flash | API | routable | Reuse E2 adapter |
| GLM-5.3 Flash | API (OpenAI-compatible) | — | New API adapter |
| Qwen3.8-27B | API | — | New API adapter |
| LongCat 2.0 | API (Nous) | routable | Reuse E2 adapter |
| MiniMax M3 | API | — | New API adapter |
| Step 3.7 Flash | API | — | New API adapter |
| Tencent Hunyuan Hy3 | API | — | New API adapter |

### 7.3 Adapter interface for unknown providers

For providers where no automation path exists:
- Adapter exists as stub
- `dispatch()` returns NOT_IMPLEMENTED
- `check_health()` returns UNKNOWN
- `routable = false`
- No pretense of dispatch capability

---

## 8. CLI commands

Extend `eb.py` with E3 subcommands:

| Command | Purpose |
|---|---|
| `eb e3-plan` | Plan a task: classify, decompose, build DAG |
| `eb e3-route` | Run AI router: propose candidate workers |
| `eb e3-gate` | Run Qualification Gate on proposals |
| `eb e3-dispatch` | Dispatch a node to assigned worker |
| `eb e3-execute` | Execute a full DAG (with monitoring) |
| `eb e3-verify` | Run verification on node output |
| `eb e3-integrate` | Integrate specialist outputs |
| `eb e3-rework` | Trigger targeted rework |
| `eb e3-replan` | Replan with version increment |
| `eb e3-status` | Show DAG / plan status |
| `eb e3-workers` | Show worker capability registry |
| `eb e3-evidence` | Show performance evidence summary |
| `eb e3-escalate` | Structured escalation |
| `eb e3-verify-db` | Verify orchestration.db integrity |
| `eb e3-init` | Initialize orchestration.db |

---

## 9. Owner escalation interface

Escalation is a first-class state. When E3 cannot proceed:

```
ESCALATION
  trigger: <reason category>
  context: <what was attempted>
  proposals considered: <list>
  why each failed: <list>
  owner decision needed: <specific question>
  recommended action: <suggestion, not binding>
  floor preserved: <yes/no>
```

Owner can respond: CONTINUE | REPLAN | CANCEL | OVERRIDE

---

## 10. E1 / E2 integration

### 10.1 E1 integration boundary

E3 READS E1 data (exec_brain.db):
- Classification records
- Quality floors
- Override records
- Decomposition records

E3 NEVER WRITES to E1 database. Any new/replanned subtask goes through
the E1 floor process before worker routing.

### 10.2 E2 integration boundary

E3 CONSUMES E2 telemetry:
- Provider operational state
- Capacity dimensions
- Rate-limit state

E3 NEVER WRITES to E2 database.

Resource scarcity may change WHICH qualified worker is selected,
but NEVER lowers the E1 quality floor (No-Degradation Invariant).

Codex/Antigravity observed-only status in E2 is respected —
E3 does not dispatch to non-routable providers.

---

## 11. GitHub curated publication

### 11.1 Files

```
orchestration-status/
  team-assembly-log.md       — last 10 routing decisions
  worker-qualification.md   — current worker states (all 10)
  execution-summary.md      — last 5 DAG executions
  evidence-stats.md         — evidence counts per worker
```

### 11.2 Update rules

- Published by `eb e3-status --publish` command
- Contains no raw task text, no secrets, no provider credentials
- Append-only log format for team-assembly-log
- Curated summary refresh on demand

---

## 12. Rollout strategy

### Stage 1: Shadow planning (no execution)

- `eb e3-plan` and `eb e3-route` work
- Proposals are generated but NOT executed
- Human reviews every proposal
- Purpose: validate planner + router logic
- No workers are dispatched
- Gate can be in permissive mode (log-only)

### Stage 2: Low-risk R0/R1 objectively verifiable execution

- Single-worker execution only (no multi-worker DAG)
- Workers: LOCKED pool only
- Only tasks with deterministic verification
- Shadow evaluation of BENCHMARK workers allowed
- Gate enforces E1 floors
- All outcomes recorded as evidence

### Stage 3: Qualified multi-worker orchestration

- Multi-worker DAG execution
- Parallel execution where safe
- Integrator + independent critic path
- Replanning enabled
- Full evidence accumulation

### Stage 4: Broader complex workflows

- All E3 features active
- Exploration/exploitation policies active
- Router self-evaluation feeding back
- Future shadow evaluation (if owner approves D-AI-4)

---

## 13. Test matrix

### 13.1 Deterministic test categories

| # | Category | Test count |
|---|---|---|
| T-A1 | Decomposition logic | 4 |
| T-A2 | Decomposition review (floor-dodging rejection) | 3 |
| T-B1 | DAG dependency resolution | 4 |
| T-B2 | Parallel-safe execution | 3 |
| T-C1 | Candidate generation (multiple proposals) | 3 |
| T-C2 | Router proposal validation | 3 |
| T-D1 | Qualification Gate (all outcomes) | 5 |
| T-D2 | Worker states (UNPROVEN/EVALUATING/QUALIFIED/SUSPENDED) | 4 |
| T-D3 | Cold-start evaluation rules | 3 |
| T-E1 | Privacy / egress enforcement | 3 |
| T-E2 | Context scoping | 2 |
| T-E3 | Permission enforcement | 3 |
| T-F1 | Provider unroutable state handling | 2 |
| T-F2 | E2 UNKNOWN telemetry handling | 3 |
| T-G1 | Multi-worker execution (sequential + parallel) | 4 |
| T-G2 | Integration logic | 3 |
| T-G3 | Conflict detection | 2 |
| T-H1 | Independent verification path | 3 |
| T-H2 | Targeted rework | 3 |
| T-I1 | Versioned replanning | 3 |
| T-I2 | Failure attribution | 3 |
| T-J1 | Performance evidence recording | 3 |
| T-J2 | Model identity drift detection | 2 |
| T-K1 | Router self-evaluation | 2 |
| T-K2 | Convergence / loop prevention | 3 |
| T-L1 | Owner escalation | 3 |
| T-M1 | Secret leakage prevention | 2 |
| T-M2 | Audit integrity | 3 |
| T-N1 | E1 regression (no mutation) | 4 |
| T-N2 | E2 regression (no mutation) | 3 |
| T-O1 | Rollback (DB restore) | 2 |
| | **Total** | **~85** |

---

## 14. E1 / E2 regression requirements

### 14.1 E1 regression

- `eb audit --verify` still PASS (32/32 existing tests)
- exec_brain.db schema UNCHANGED
- E1 CLI commands UNCHANGED
- No new writes to exec_brain.db
- E1 frozen floors remain immutable

### 14.2 E2 regression

- `eb gov-verify` still PASS (45/45 existing tests)
- governor.db schema UNCHANGED
- E2 CLI commands UNCHANGED
- No new writes to governor.db
- E2 adapters unchanged

---

## 15. Rollback procedure

1. Stop all E3 execution
2. Restore orchestration.db from backup (if corruption detected)
3. Disable E3 commands in eb.py (revert to E1+E2 only)
4. Publish rollback decision to control-plane
5. E1/E2 continue unaffected (separate databases)

E1/E2 rollback independent of E3 rollback.

---

## 16. Acceptance criteria

### Stage 1 acceptance
- `eb e3-plan` produces valid decomposition for 5 diverse test tasks
- `eb e3-route` produces ≥2 candidate proposals per task
- Router logs reasoning for each proposal
- Zero executions dispatched
- Human confirms proposals are reasonable

### Stage 2 acceptance
- 10 low-risk R0/R1 tasks executed with deterministic verification
- All outcomes recorded as evidence
- E1/E2 regression: 100% pass
- No worker dispatched above its qualification state
- Shadow evaluation data collected for BENCHMARK workers

### Stage 3 acceptance
- 3 multi-worker DAG executions completed
- Integrator + critic path working
- Replan triggered at least once correctly
- Evidence accumulation functional

### Stage 4 acceptance
- All test categories passing (~85 tests)
- Router self-evaluation logging active
- Full audit trail verified
- Owner sign-off

---

## 17. Migration / versioning

- orchestration.db schema version: 1
- Independent schema_version table
- Forward-compatible with E4 (reserve fields present but NOT_ENFORCED)
- No migration needed from E1/E2 (separate databases)

---

## 18. Files to create / modify

### Create (local)
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\orchestration.db`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_router.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_planner.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_gate.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_dag.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_context.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_permissions.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_integrator.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_verify.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_replan.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_escalate.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\e3_evidence.py`
- `C:\Users\mukun\AppData\Local\hermes\exec-brain\tests\test_e3.py`

### Create (control-plane repo)
- `decisions/exec-brain-e3-rollout.md`
- `orchestration-status/` directory with initial files

### Modify (local)
- `eb.py` — extend with E3 subcommands
- `adapters.py` — add new provider adapters

### Modify (control-plane repo)
- `state/current_company_state.md` — update with E3 status

---

## 19. Unresolved owner decisions

| # | Decision | Options |
|---|---|---|
| D-AI-1 | Separate orchestration.db | **Recommended: yes** |
| D-AI-2 | Router AI model class | Strong reasoning model (which one?) |
| D-AI-3 | Planner model = router model? | Same or separate |
| D-AI-4 | Shadow evaluation in E3 v1? | Defer to E4 |
| D-AI-5 | Exploration rate for cold-start | Conservative / moderate / aggressive |
| D-AI-6 | Convergence retry limits | Default 3, or other |
| D-AI-7 | Integrator model class | Same as router or separate |

---

## 20. Conflicts with E1/E2

**None discovered.** See architecture amendment §12 for detailed analysis.

E1 schema is not modified. E2 schema is not modified. E3 reads both,
writes neither. E1 floors remain authoritative. E2 telemetry informs
but never overrides qualification.

---

## 21. Out of scope (E4/E5)

The following are explicitly NOT implemented in E3:

- Predictive exhaustion enforcement (E4)
- Protected reserve enforcement (E4)
- Proactive resource-driven checkpoints (E4)
- Automatic resource-driven handover (E4)
- Runway calculations (E4)
- Safe mode automation (E5)
- Failure drills (E5)
- Mature owner override UX (E5)

Schema may be forward-compatible but behaviors remain disabled.

---

This document does not modify any running system. It is a plan awaiting
owner approval of the architecture amendment first.
