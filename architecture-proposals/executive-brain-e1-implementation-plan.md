# Executive Brain E1 — Implementation Plan (Plan Only)

Status: PLAN — not implemented
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
    CREATE TABLE task_record (
      task_id        TEXT PRIMARY KEY,          -- eb-<yyyymmdd>-<shortuuid>
      created_at     TEXT NOT NULL,             -- ISO-8601 UTC
      request_text   TEXT NOT NULL,             -- verbatim owner words
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
      frozen_at      TEXT NOT NULL,
      min_reasoning_depth INTEGER NOT NULL,
      required_roles TEXT NOT NULL,             -- JSON {role: state}
      min_verification TEXT NOT NULL,
      risk_constraints TEXT,
      egress_constraints TEXT,
      strategy_constraints TEXT,
      record_sha256  TEXT NOT NULL,             -- hash of canonical fields
      prev_sha256    TEXT,                      -- hash-chain link
      schema_version INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE strategy_decision (
      decision_id    TEXT PRIMARY KEY,
      floor_id       TEXT NOT NULL REFERENCES quality_floor(floor_id),
      decided_at     TEXT NOT NULL,
      strategy       TEXT NOT NULL,             -- 1..7 per §1
      chosen_class   TEXT,                      -- specialist class (manual)
      chosen_worker  TEXT,                      -- model/workflow (manual)
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
      actual_route   TEXT NOT NULL,
      warning_text   TEXT NOT NULL,             -- Chief's written warning
      owner_confirmation TEXT NOT NULL,         -- how owner approved (verbatim
                                                 -- quote of owner message/id)
      schema_version INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE audit_log (
      audit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
      ts             TEXT NOT NULL,
      event          TEXT NOT NULL,             -- classify|decompose|freeze|
                                                 -- route|override|reject
      task_id        TEXT, floor_id TEXT, decision_id TEXT,
      detail         TEXT NOT NULL,             -- no secrets, no full content
      schema_version INTEGER NOT NULL DEFAULT 1
    );

## 4. Immutable floor-freeze — technical enforcement

Three layers, all deterministic:

1. Schema-level: quality_floor has no UPDATE/DELETE path in the CLI. The
   sqlite connection opens with `PRAGMA query_only` for reads; the writer
   code path contains exactly one INSERT into quality_floor (code review
   gate: any PR raising a second one is rejected).
2. Hash chain: each floor's canonical field set is SHA-256 hashed
   (record_sha256); each row stores the previous floor's hash
   (prev_sha256, genesis = NULL). `eb audit --verify` recomputes the chain;
   any tampering (row edited/deleted/reordered) breaks the chain and is
   reported. This makes silent floor mutation detectable, not just forbidden.
3. Order enforcement: the ONLY function that can create a StrategyDecision
   first checks `SELECT 1 FROM quality_floor WHERE task_id=? / subtask_id=?`.
   No floor → the route command exits non-zero with
   "FLOOR REQUIRED BEFORE ROUTING" and writes a `reject` audit row. The
   Governor/telemetry does not exist in E1, so nothing CAN be consulted
   before freeze — the invariant is enforced by construction.

Floor revision: not an UPDATE. A changed understanding creates a NEW
TaskRecord + new floor (per §2 rule), linked via audit trail. The old floor
stays forever.

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
- writes OverrideRecord + audit row; only then may `eb route` accept a
  sub-floor route for that floor (gate_result records the override id)

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
- DB locked (concurrent Chief turns) → sqlite busy_timeout 5s, then clean
  failure; retry is safe (commands are idempotent by design: re-running
  classify creates a new task, never corrupts an old one).
- Hash-chain verification failure on `eb audit --verify` → loud report;
  routing for affected tasks is blocked until the owner is informed
  (invariant: never route on an unverified floor).

## 10. Rollback / recovery

- E1 is additive: one directory + one skill + repo doc edits.
- Full rollback: delete exec-brain\ directory, delete skill folder, revert
  the two repo files (git revert of the rollout commit). No data migration
  was performed, so nothing else needs recovery.
- DB corruption: exec_brain.db is rebuildable for audit purposes from the
  control-plane curated summaries (floors/decisions published there);
  worst case, history is lost but operation is unaffected (E1 keeps no
  runtime dependencies on old rows except the freeze-before-route check,
  which only needs the current task's floor).

## 11. Test matrix

| # | Test | Expected |
|---|---|---|
| T1 | eb classify with valid enums | TaskRecord written, audit row, exit 0 |
| T2 | eb classify with invalid enum/task_type | refused, exit != 0, no row |
| T3 | eb decompose before classify | refused (no task) |
| T4 | eb freeze after classify | floor written, hash chain extends, audit |
| T5 | eb freeze twice on same subtask | second floor allowed ONLY as new revision (new floor_id, old intact) |
| T6 | eb route WITHOUT freeze | refused: FLOOR REQUIRED BEFORE ROUTING, reject audit row |
| T7 | eb route after freeze, floor-consistent | StrategyDecision written, gate accept |
| T8 | eb route sub-floor WITHOUT override | refused |
| T9 | eb override with empty warning/confirmation | refused |
| T10 | eb override with warning+confirmation, then sub-floor route | accepted, OverrideRecord linked |
| T11 | tamper a floor row directly in SQLite | eb audit --verify reports chain break |
| T12 | concurrent classify x2 (two processes) | one succeeds, other retries/clean-fails; no corruption |
| T13 | Discord gateway + scheduled ChiefDiscordSync still work after install | unchanged (no gateway files touched) |
| T14 | curated summary generation | only allowed fields, no request_text of P2/P3 tasks, no secrets |
| T15 | full pipeline dry-run on a real small task | classify→decompose→freeze→route in order, audit shows sequence |

## 12. Migration impact on existing Chief

None at runtime: no existing file is modified, no hook/gateway/cron change,
no provider code. The Chief gains one skill + one CLI. Behaviour change is
procedural only: from rollout on, management/routing tasks should run the EB
discipline (skill enforces habit; audit trail verifies). Existing workflows
(Career Ops, sync tasks, Discord capture) untouched.

## 13. Complexity estimate

- eb.py (CLI + 6 tables + hash chain + audit): ~450–600 lines, stdlib only
- tests: ~250–350 lines, 15 cases
- SKILL.md: ~80 lines
- repo docs: small
- Total: roughly one focused implementation session; LOW–MEDIUM complexity;
  deterministic, no external deps, no network. Main risk is discipline
  adoption (human/process), not code.

## Risks

1. Discipline bypass (Chief routes without running freeze) — mitigated by
   skill + audit visibility; cannot be fully prevented in E1 by code alone.
2. Hash chain adds ~no cost but audit --verify must be run to be useful —
   add to weekly review habit.
3. SQLite single-writer contention if two Chief turns run EB simultaneously —
   rare; busy_timeout + clean failure.
4. Over-classification noise for trivial tasks — skill includes a
   de-minimis rule (R0/V0/P0 one-step tasks may be logged in a single
   lightweight classify+freeze combined call).

## Recommended implementation order

1. eb.py: schema DDL + classify + audit (T1–T3)
2. freeze + hash chain + audit --verify (T4, T5, T11)
3. route gate + override (T6–T10)
4. curated-summary export + repo docs (T14)
5. SKILL.md + install + T13/T15 end-to-end
6. Rollout decision record in decisions/ + state update

---

STOP — plan only. Awaiting owner approval to implement E1.
