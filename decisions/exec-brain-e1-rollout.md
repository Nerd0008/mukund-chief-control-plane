# Decision: Executive Brain E1 Rollout

- Date: 2026-09-21
- Decision: Implement and activate Executive Brain E1 (owner-approved)
- Baseline: approved-architecture/executive-brain-v2.md
- Spec: architecture-proposals/executive-brain-e1-implementation-plan.md (rev 3)

## What was implemented

- CLI: %LOCALAPPDATA%\hermes\exec-brain\eb.py (stdlib-only; init, classify,
  decompose, freeze, route, override, audit, backup, restore, summary)
- SQLite schema v1: task_record, subtask_record, quality_floor,
  strategy_decision, override_record, audit_log — all append-only via
  12 ABORT triggers; PRAGMA foreign_keys=ON on every connection
- Immutable floors: classification_key UNIQUE (task:<id> / subtask:<id>),
  SHA-256 hash chains with deterministic seq order, chain-head anchor
  (exec-brain\chain-head.json, mirrored in curated summary)
- Structural route gate: reasoning/verification/egress/strategy/roles/
  approval checks against the frozen floor; low classification confidence
  blocks routing; overrides bound to an exact route fingerprint
- Idempotency: UNIQUE(source_system, source_event_id); retry reuses the
  existing TaskRecord
- Backup/restore: SQLite online backup to exec-brain\backups\ (keep 10),
  restore verifies integrity + chain before swapping
- Curated summary export: non-sensitive fields only (no request_text)
- Hermes skill: operations/executive-brain-e1 (discipline carrier)

## Test result

Full rev-3 matrix: 32/32 tests PASSED (28 numbered matrix tests plus
sub-variants), including duplicate-freeze refusal (task + subtask),
reclassification lineage, direct SQL UPDATE/DELETE rejection on all six
tables, tail-deletion anchor detection, below-floor route rejections
(reasoning/verification/LOCAL_ONLY/strategy/roles), low-confidence block,
FK enforcement, concurrent independent + duplicate classify, backup/restore,
and no-raw-text summary.

## Acceptance verification

- eb audit --verify: PASS (fresh live DB)
- backup + restore: PASS (test T21 + live backup taken)
- Discord gateway: running, discord connected (unmodified)
- ChiefDiscordSync: Last Result 0, log clean (unmodified)
- No existing workflow modified: gateway, Discord archive hook, sync script,
  Career Ops, trackers untouched
- No secrets or raw task text in GitHub: summary excludes request_text;
  raw DB local-only

## Scope confirmed NOT implemented (E2+)

Provider API routing, Codex/Antigravity/DeepSeek calls, automatic model
selection, Resource Governor telemetry, predictive exhaustion, protected
reserves, performance learning, automatic handovers, safe-mode automation.
