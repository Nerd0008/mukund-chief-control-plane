# Executive Brain E1 — Implementation Plan (Plan Only)

Status: PLAN (rev 3, final pre-implementation corrections) — not implemented
Baseline: approved-architecture/executive-brain-v2.md (commit 545b59a)
Author: Chief of Staff (Hermes)
Date: 2026-09-21
Scope: E1 only — schemas, classification, immutable floors, ordering
enforcement, manual routing discipline, audit logging. No provider APIs, no
Governor telemetry, no exhaustion/reserves, no performance learning, no
automatic handovers, no safe-mode automation.

---

## 1. Proposed architecture

E1 is a local, deterministic Python package + CLI + one Hermes skill. No new
agent, no gateway changes, no second state system. The Chief (this session or
a Discord turn) invokes the EB CLI/skill at decision time; everything else in
Hermes keeps working exactly as today.

    ┌─ Hermes Chief (existing, unchanged) ─────────────────────┐
    │  owner request → invokes EB procedure (skill or CLI)     │
    └──────────────┬───────────────────────────────────────────┘
                   ▼
    exec_brain/ (new local package, no dependencies)
      eb classify   → TaskRecord(s)          [SQLite, append-only]
      eb decompose  → SubtaskRecord(s)       [SQLite, append-only]
      eb freeze     → QualityFloor(s)        [SQLite, IMMUTABLE + hash-chained]
      eb route      → StrategyDecision       [SQLite; REFUSES before freeze]
      eb override   → OverrideRecord         [SQLite, owner-only field]
      eb audit      → human-readable audit trail
                   ▼
    curated summaries → control-plane repo (state/, decisions/) via existing
    manual/scheduled sync discipline (raw rows NEVER leave the machine)

The E1 "router" is manual-routing discipline: `eb route` records the Chief's
chosen strategy/worker and VALIDATES it against the frozen floor (rejects
sub-floor routes unless an OverrideRecord exists). No automatic provider
selection happens in E1.

## 2. Exact file plan

New (local, outside repo — raw/high-frequency state stays local):

    C:\Users\mukun\AppData\Local\hermes\exec-brain\
      eb.py                  single-file CLI (stdlib only: sqlite3, json,
                             argparse, hashlib, datetime, uuid)
      exec_brain.db          SQLite database (created on first run)
      tests\test_eb.py       stdlib unittest suite (no external deps)

New (Hermes skill — the discipline layer):

    %LOCALAPPDATA%\hermes\skills\operations\executive-brain-e1\SKILL.md
      Loads on management/routing tasks; instructs the Chief to run the EB
      CLI in the §2 constitutional order; encodes the manual routing
      checklist and override rules.

Modified (control-plane repo — curated summaries only):

    mukund-chief-control-plane\
      state\current_company_state.md        add "Executive Brain: E1 active
                                            (classification + floors + manual
                                            routing discipline)" when landed
      decisions\exec-brain-e1-rollout.md    rollout decision record (new)
      .gitignore                            add exec_brain.db pattern (safety,
                                            even though it lives outside repo)

Nothing else changes. No gateway files, no hooks, no cron, no provider code.

## 3. Schema plan (SQLite DDL)

    -- append-only: rows are never UPDATEd or DELETEd by the app
    -- lineage: a changed understanding NEVER edits this row; it creates a
    -- new TaskRecord with supersedes_task_id pointing here.
    CREATE TABLE task_record (
      task_id        TEXT PRIMARY KEY,          -- eb-<yyyymmdd>-<shortuuid>
      supersedes_task_id TEXT REFERENCES task_record(task_id),
                                             -- NULL = original lineage
      reclassification_reason TEXT,            -- required when supersedes is set
      created_at     TEXT NOT NULL,             -- ISO-8601 UTC
      request_text   TEXT NOT NULL,             -- verbatim owner words
      source_system  TEXT,                      -- e.g. discord | cli | cron
      source_event_id TEXT,                     -- source's stable event id
                                             -- (Discord: real inbound
                                             -- message_id when available)
      -- idempotency: a retry with the same non-null source identity returns
      -- the EXISTING TaskRecord instead of creating a duplicate. NULL
      -- (manual/CLI) tasks always create new records intentionally.
      UNIQUE(source_system, source_event_id),
      task_type      TEXT NOT NULL,             -- enum §3
      capability_roles TEXT NOT NULL,           -- JSON array
      reasoning_depth INTEGER NOT NULL,         -- 0..4
      verification_level TEXT NOT NULL,         -- V0..V3
      risk_class     TEXT NOT NULL,             -- R0..R3
      privacy_class  TEXT NOT NULL,             -- P0..P3
      egress_policy  TEXT NOT NULL,             -- §4a enum
      deadline       TEXT,                      -- hard|soft|none + datetime
      idempotent     INTEGER NOT NULL,          -- 0/1
      context_size   TEXT NOT NULL,             -- small|medium|large
      known_workflows TEXT,                     -- JSON array
      classification_confidence TEXT NOT NULL,  -- high|medium|low
      schema_version INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE subtask_record (
      subtask_id     TEXT PRIMARY KEY,
      task_id        TEXT NOT NULL REFERENCES task_record(task_id),
      parent_subtask_id TEXT,                   -- NULL = top level
      title          TEXT NOT NULL,
      order_index    INTEGER NOT NULL,
      legality_note  TEXT,                       -- §7 decomposition test
      created_at     TEXT NOT NULL,
      schema_version INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE quality_floor (
      floor_id       TEXT PRIMARY KEY,          -- fl-<taskid>-<n>
      task_id        TEXT NOT NULL REFERENCES task_record(task_id),
      subtask_id     TEXT REFERENCES subtask_record(subtask_id),
      -- deterministic classification key: SQLite UNIQUE treats NULLs as
      -- distinct, so UNIQUE(task_id, subtask_id) could NOT guarantee one
      -- floor for a top-level task (subtask_id NULL). classification_key
      -- closes that hole for BOTH task-level and subtask floors.
      classification_key TEXT NOT NULL UNIQUE,  -- 'task:<task_id>' or
                                             -- 'subtask:<subtask_id>'
      frozen_at      TEXT NOT NULL,
      seq            INTEGER NOT NULL UNIQUE,   -- deterministic chain order
      min_reasoning_depth INTEGER NOT NULL,
      required_roles TEXT NOT NULL,             -- JSON {role: state}
      min_verification TEXT NOT NULL,
      risk_constraints TEXT,
      egress_constraints TEXT,
      strategy_constraints TEXT,
      record_sha256  TEXT NOT NULL,             -- hash of canonical fields
      prev_sha256    TEXT,                      -- hash-chain link
      schema_version INTEGER NOT NULL DEFAULT 1
      -- ONE floor per classification, enforced by classification_key UNIQUE:
      -- a second freeze of the same task OR subtask is a constraint violation
    );

    CREATE TABLE strategy_decision (
      decision_id    TEXT PRIMARY KEY,
      floor_id       TEXT NOT NULL REFERENCES quality_floor(floor_id),
      decided_at     TEXT NOT NULL,
      strategy       TEXT NOT NULL,             -- 1..7 per §1
      chosen_class   TEXT,                      -- specialist class (manual)
      chosen_worker  TEXT,                      -- model/workflow (manual)
      -- proposed execution properties: what the E1 gate can mechanically
      -- compare against the frozen floor (see §4a)
      proposed_reasoning_depth INTEGER NOT NULL,
      proposed_verification   TEXT NOT NULL,    -- V0..V3 + plan summary
      execution_scope TEXT NOT NULL,            -- local | external
      proposed_egress TEXT NOT NULL,            -- egress behaviour of route
      claimed_roles  TEXT NOT NULL,             -- JSON array
      qualification_evidence TEXT NOT NULL,     -- JSON: cited evidence or
                                             -- the literal string "UNPROVEN"
      risk_approval  TEXT,                      -- owner approval reference
                                             -- when floor requires it
      ranked_candidates TEXT,                   -- JSON §5b ranking evidence
      gate_result    TEXT NOT NULL,             -- accept|reject
      gate_reasons   TEXT,
      schema_version INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE override_record (
      override_id    TEXT PRIMARY KEY,
      floor_id       TEXT NOT NULL REFERENCES quality_floor(floor_id),
      overridden_at  TEXT NOT NULL,
      original_floor_summary TEXT NOT NULL,
      -- the override authorizes EXACTLY ONE below-floor exception, not every
      -- future below-floor route on this floor. route_fingerprint is the
      -- SHA-256 of the canonical proposed-route fields (strategy,
      -- chosen_class, chosen_worker, proposed_reasoning_depth,
      -- proposed_verification, execution_scope, proposed_egress,
      -- claimed_roles). `eb route` may use an override ONLY when the proposed
      -- route's fingerprint matches. A materially different below-floor route
      -- (different worker, reasoning, egress, ...) requires a NEW override.
      route_fingerprint TEXT NOT NULL,
      actual_route   TEXT NOT NULL,              -- human-readable route desc
      warning_text   TEXT NOT NULL,             -- Chief's written warning
      owner_confirmation TEXT NOT NULL,         -- how owner approved (verbatim
                                                 -- quote of owner message/id)
      schema_version INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE audit_log (
      audit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
      ts             TEXT NOT NULL,
      seq            INTEGER NOT NULL UNIQUE,   -- deterministic chain order
      event          TEXT NOT NULL,             -- classify|decompose|freeze|
                                                 -- route|override|reject
      task_id        TEXT, floor_id TEXT, decision_id TEXT,
      detail         TEXT NOT NULL,             -- no secrets, no full content
      record_sha256  TEXT NOT NULL,             -- audit chain hash
      prev_sha256    TEXT,                      -- audit chain link
      schema_version INTEGER NOT NULL DEFAULT 1
    );

    -- Database-level immutability: triggers reject UPDATE/DELETE on ALL
    -- historical/audit records. PRAGMA foreign_keys = ON on EVERY connection.
    CREATE TRIGGER trg_task_record_no_update BEFORE UPDATE ON task_record
      BEGIN SELECT RAISE(ABORT, 'task_record is append-only'); END;
    CREATE TRIGGER trg_task_record_no_delete BEFORE DELETE ON task_record
      BEGIN SELECT RAISE(ABORT, 'task_record is append-only'); END;
    CREATE TRIGGER trg_subtask_no_update BEFORE UPDATE ON subtask_record
      BEGIN SELECT RAISE(ABORT, 'subtask_record is append-only'); END;
    CREATE TRIGGER trg_subtask_no_delete BEFORE DELETE ON subtask_record
      BEGIN SELECT RAISE(ABORT, 'subtask_record is append-only'); END;
    CREATE TRIGGER trg_quality_floor_no_update BEFORE UPDATE ON quality_floor
      BEGIN SELECT RAISE(ABORT, 'quality_floor is immutable'); END;
    CREATE TRIGGER trg_quality_floor_no_delete BEFORE DELETE ON quality_floor
      BEGIN SELECT RAISE(ABORT, 'quality_floor is immutable'); END;
    CREATE TRIGGER trg_strategy_no_update BEFORE UPDATE ON strategy_decision
      BEGIN SELECT RAISE(ABORT, 'strategy_decision is append-only'); END;
    CREATE TRIGGER trg_strategy_no_delete BEFORE DELETE ON strategy_decision
      BEGIN SELECT RAISE(ABORT, 'strategy_decision is append-only'); END;
    CREATE TRIGGER trg_override_no_update BEFORE UPDATE ON override_record
      BEGIN SELECT RAISE(ABORT, 'override_record is append-only'); END;
    CREATE TRIGGER trg_override_no_delete BEFORE DELETE ON override_record
      BEGIN SELECT RAISE(ABORT, 'override_record is append-only'); END;
    CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_log
      BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
    CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_log
      BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

## 4. Immutable floor-freeze — technical enforcement

Four layers, all deterministic:

1. Database-level (primary): the triggers above ABORT any UPDATE/DELETE on
   task_record, subtask_record, quality_floor, strategy_decision,
   override_record, and audit_log — including direct SQL attempts through
   any connection that has the schema loaded.
   `PRAGMA foreign_keys = ON` on every connection also rejects orphaned
   references (e.g. a route pointing at a nonexistent floor).
2. Application-level: the CLI contains no UPDATE/DELETE code path for these
   tables; the writer opens one transaction per command (single INSERT).
3. One-floor-per-classification: classification_key TEXT NOT NULL UNIQUE
   ('task:<task_id>' | 'subtask:<subtask_id>'). A plain
   UNIQUE(task_id, subtask_id) was rejected in review because SQLite treats
   NULLs as distinct — it would allow multiple task-level floors when
   subtask_id IS NULL. classification_key makes a second freeze of the same
   classification impossible for BOTH task-level and subtask floors.
   A changed understanding REQUIRES a new TaskRecord (supersedes_task_id +
   reclassification_reason) and a new floor. There are no floor "revisions" —
   only new lineages. The previous task/floor rows remain immutable forever.
4. Hash chain: each floor's canonical fields are SHA-256 hashed
   (record_sha256); each row stores the previous floor's hash (prev_sha256).
   A monotonic `seq` column gives deterministic chain order — verification
   never depends on ambiguous row ordering (rowid, timestamps, or ids).
   `eb audit --verify` recomputes the chain in seq order and reports any
   break. The audit_log carries its own parallel chain (seq + hashes).

Chain-head anchor: after every verified `eb audit --verify`, the latest
chain head (floor seq + hash, audit seq + hash — small, non-sensitive) is
written to exec-brain\chain-head.json (local) and included in the curated
GitHub summary. Deleting the FINAL tail row of a chain is otherwise not
detectable by the chain alone; the external head anchor closes that gap.
No cryptographic signing in E1 — SHA-256 chaining + anchors is enough.

Detectable-but-not-preventable (residual): someone editing the SQLite file
with an external tool that drops/recreates the triggers, or rewriting the
whole file, can mutate rows. The hash chain + external head anchor makes
this DETECTABLE (recomputation fails), not impossible. Fully preventing
file-owner tampering is out of scope for E1 (and for any local DB).

### 4a. Route validation (E1 scope) — structural floor compliance

`eb route` records the proposed execution properties (strategy_decision
columns above) and the gate deterministically rejects:

- proposed_reasoning_depth < floor.min_reasoning_depth
- proposed_verification below floor.min_verification
- LOCAL_ONLY / egress_constraints violated by an external execution_scope
  or incompatible proposed_egress
- strategy violating floor.strategy_constraints
- a floor-required capability role missing from claimed_roles
- floor risk_constraints requiring owner approval when risk_approval is absent
- no floor for the task/subtask (ordering violation)
- classification_confidence = low (see below)

What E1 does NOT validate: worker QUALITY. qualification_evidence is
recorded (cited evidence or the literal "UNPROVEN") but E1 has no
performance-history store, so it cannot prove a model is good — that is E3
(Qualification Gate) work. E1 enforces STRUCTURAL/FLOOR COMPLIANCE only;
provider-quality qualification is explicitly out of scope and never claimed.

### 4b. Classification-confidence gate

If classification_confidence = low:
- the floor MAY be stored (audit value)
- `eb route` is BLOCKED for that task until either (a) a reclassification
  (new TaskRecord via supersedes, with reason) raises confidence, or
  (b) an explicit owner OverrideRecord is filed per §7
- normal route execution from a low-confidence classification is impossible
  by construction (the gate checks confidence before every accept)

## 5. Exact execution order (state flow)

    owner request
      → eb classify          writes TaskRecord (+audit)
      → eb decompose (opt.)  writes SubtaskRecords (+audit)
      → eb freeze            writes QualityFloor(s) (+audit, hash-chained)
      → eb route             writes StrategyDecision; HARD FAILS if no floor
      → execution (existing Hermes tools — unchanged)
      → verification per floor V-level (manual in E1)
      → curated summary to control-plane repo (manual in E1)

## 6. How routing is prevented before freeze

- `eb route` requires --floor-id; the command verifies the floor exists and
  is hash-chain valid before recording any decision.
- No other E1 command writes StrategyDecision.
- The skill instructs the Chief never to name a worker/model before running
  freeze; the audit trail makes violations visible post-hoc (route row with
  no preceding freeze row for the same task).
- Provider integrations do not exist in E1, so there is no code path that
  could route around the discipline.

## 7. Owner overrides

`eb override --floor-id F --route R --warning W --confirmation C`:
- requires the Chief's written warning (W) that the route falls below the
  frozen floor — the command refuses an empty warning
- requires owner confirmation evidence C (verbatim owner message quote or
  message id); empty C is refused
- computes route_fingerprint = SHA-256 over the canonical proposed-route
  fields (strategy, chosen_class, chosen_worker, proposed_reasoning_depth,
  proposed_verification, execution_scope, proposed_egress, claimed_roles)
- writes OverrideRecord + audit row
- `eb route` may use an override ONLY when the proposed route's fingerprint
  EXACTLY matches the override's route_fingerprint. The override authorizes
  that single approved exception — not every future below-floor route on the
  floor. Any materially different below-floor route (different worker,
  reasoning, verification, scope, egress, or roles) requires a NEW owner
  override. (gate_result records the override id used.)

## 8. Interaction with existing Hermes sessions/tools

- No gateway/hook changes; Discord/Telegram/CLI sessions unaffected.
- The Chief calls `eb` via the terminal tool, exactly like any script today.
- The skill (executive-brain-e1) loads the discipline into future Chief
  sessions; it is the E1 "manual routing discipline" carrier.
- Reuse: local SQLite under Hermes home follows the existing local/GitHub
  split (raw local, curated to repo) — no duplicate state system; state.db
  and other Hermes stores are untouched.
- delegate_task/subagent usage unchanged; E1 does not route anything itself.

## 9. Failure behavior

- Any CLI error (locked db, bad enum, missing floor) → non-zero exit +
  human-readable error + audit row where possible; no partial writes
  (single INSERT per command inside one transaction).
- Concurrency: two INDEPENDENT valid classify operations both succeed —
  SQLite serializes writers under locking/busy_timeout (5s), so each waits
  its turn. A clean failure happens only after timeout expiry, and retry is
  safe. For DUPLICATE retries carrying the same (source_system,
  source_event_id): UNIQUE(source_system, source_event_id) guarantees
  exactly one TaskRecord — the retry returns the existing record instead of
  creating a second one. Manual/CLI tasks without a source_event_id
  intentionally create new TaskRecords each time.
- Hash-chain verification failure on `eb audit --verify` → loud report;
  routing for affected tasks is blocked until the owner is informed
  (invariant: never route on an unverified floor).

## 10. Rollback / recovery

- E1 is additive: one directory + one skill + repo doc edits.
- Full rollback: delete exec-brain\ directory, delete skill folder, revert
  the two repo files (git revert of the rollout commit). No data migration
  was performed, so nothing else needs recovery.
- Deterministic local recovery (exec_brain.db is the system of record):
  1. `eb audit --verify` runs SQLite `PRAGMA integrity_check` plus hash-chain
     recomputation; reports corruption or chain break precisely.
  2. Local backup: `eb backup` copies exec_brain.db (+ chain-head.json) to
     exec-brain\backups\<timestamp>\ via SQLite's backup API (online, safe);
     kept N most recent (default 10). Deterministic, stdlib-only.
  3. Schema is versioned (schema_version column + user_version pragma);
     future migrations are additive and tested forward-only.
  4. Optional periodic backup outside the repo (e.g. a second local disk
     path or the existing machine backup routine) — configured, not built
     into E1 automation.
- Curated GitHub records are RECOVERY AIDS, not a guaranteed complete
  reconstruction: raw/local state intentionally contains information
  (verbatim request_text, P2/P3 task details) that must NOT be pushed to
  GitHub merely for recoverability. No secrets or raw sensitive task text
  ever leave the machine for backup reasons.
- Worst case (db lost + no backup): E1 keeps no runtime dependency on old
  rows except the freeze-before-route check for CURRENT tasks; history is
  lost, operation resumes with fresh classifications.

## 11. Test matrix

| # | Test | Expected |
|---|---|---|
| T1 | eb classify with valid enums | TaskRecord written, audit row, exit 0 |
| T2 | eb classify with invalid enum/task_type | refused, exit != 0, no row |
| T3 | eb decompose before classify | refused (no task) |
| T4 | eb freeze after classify | floor written, hash chain extends, audit |
| T5 | eb freeze twice on the SAME task (task-level, subtask_id NULL) | REFUSED (classification_key 'task:<id>' UNIQUE); no "revision" path exists |
| T5a | reclassification after changed understanding | new TaskRecord with supersedes_task_id + reason; new subtasks; new floor; old rows untouched |
| T5b | eb freeze twice on the SAME subtask | REFUSED (classification_key 'subtask:<id>' UNIQUE) |
| T6 | eb route WITHOUT freeze | refused: FLOOR REQUIRED BEFORE ROUTING, reject audit row |
| T7 | eb route after freeze, floor-consistent | StrategyDecision written, gate accept |
| T8 | eb route sub-floor WITHOUT override | refused |
| T9 | eb override with empty warning/confirmation | refused |
| T10 | eb override with warning+confirmation, then sub-floor route with EXACTLY matching fingerprint | accepted, OverrideRecord linked |
| T10a | below-floor route with DIFFERENT worker/reasoning/egress than the approved override | refused — old override does not authorize the new exception |
| T10b | classify retried with same (source_system, source_event_id) | returns EXISTING TaskRecord; no duplicate |
| T10c | classify with a different source_event_id | new TaskRecord allowed |
| T11 | tamper a floor row directly in SQLite (UPDATE) | trigger ABORTs; row unchanged |
| T11a | tamper a floor row by direct DELETE | trigger ABORTs; row unchanged |
| T11b | tamper task_record / subtask_record / strategy_decision / override_record / audit_log by UPDATE/DELETE | triggers ABORT all |
| T11c | delete final chain-tail floor row with triggers dropped externally | chain alone OK but head anchor mismatch reported |
| T12 | two INDEPENDENT valid classify operations, two processes | BOTH succeed serially under busy_timeout; clean failure only after timeout; no corruption |
| T12a | duplicate classify retry, same source_event_id, two processes | exactly ONE TaskRecord exists afterwards |
| T13 | Discord gateway + scheduled ChiefDiscordSync still work after install | unchanged (no gateway files touched) |
| T14 | curated summary generation | only allowed fields, no request_text of P2/P3 tasks, no secrets |
| T15 | full pipeline dry-run on a real small task | classify→decompose→freeze→route in order, audit shows sequence |
| T16 | route with proposed_reasoning_depth below floor | refused with reason |
| T17 | route with proposed_verification below floor | refused with reason |
| T18 | LOCAL_ONLY task routed with execution_scope=external | refused with reason |
| T19 | low-confidence classification, normal route attempt | blocked; only reclassification or owner override unblocks |
| T20 | route referencing nonexistent floor_id (FK violation) | rejected by PRAGMA foreign_keys |
| T21 | eb backup + restore into fresh dir; integrity_check + chain verify | backup restores, verification passes |
| T22 | strategy violating strategy_constraints | refused with reason |
| T23 | floor-required role missing from claimed_roles | refused with reason |

## 12. Migration impact on existing Chief

None at runtime: no existing file is modified, no hook/gateway/cron change,
no provider code. The Chief gains one skill + one CLI. Behaviour change is
procedural only: from rollout on, management/routing tasks should run the EB
discipline (skill enforces habit; audit trail verifies). Existing workflows
(Career Ops, sync tasks, Discord capture) untouched.

## 13. Complexity estimate

- eb.py (CLI + 6 tables + triggers + hash chain + audit + backup): ~600–750
  lines, stdlib only
- tests: ~400–500 lines, 28 cases
- SKILL.md: ~80 lines
- repo docs: small
- Total: one to two focused implementation sessions; MEDIUM complexity;
  deterministic, no external deps, no network. Main risk is discipline
  adoption (human/process), not code.

## Risks

1. Discipline bypass (Chief routes without running freeze) — mitigated by
   skill + audit visibility; cannot be fully prevented in E1 by code alone.
2. Residual tamper window: an external editor that drops triggers can mutate
   rows; detectable via chain + head anchor, not preventable (§4).
3. Hash chain adds ~no cost but audit --verify must be run to be useful —
   add to weekly review habit; chain-head anchor written on every verify.
4. SQLite single-writer contention if two Chief turns run EB simultaneously —
   rare; busy_timeout + clean failure.
5. Over-classification noise for trivial tasks — skill includes a
   de-minimis rule (R0/V0/P0 one-step tasks may be logged in a single
   lightweight classify+freeze combined call).
6. E1 route gate checks STRUCTURE only; a route can be structurally
   compliant yet executed poorly — worker-quality validation is E3, and E1
   records qualification_evidence honestly (often "UNPROVEN") instead of
   pretending otherwise.

## Recommended implementation order

1. eb.py: schema DDL + classify + audit (T1–T3)
2. freeze + hash chain + audit --verify (T4, T5, T11)
3. route gate + override (T6–T10)
4. curated-summary export + repo docs (T14)
5. SKILL.md + install + T13/T15 end-to-end
6. Rollout decision record in decisions/ + state update

---

STOP — plan only. Awaiting owner approval to implement E1.
