# Decision: Executive Brain E2 Rollout

- Date: 2026-09-22
- Decision: Implement and activate Executive Brain E2 (owner-approved)
- Baseline: approved-architecture/executive-brain-v2.md
- Spec: architecture-proposals/executive-brain-e2-implementation-plan.md (rev 2, approved)

## What was implemented

- CLI: Extended `%LOCALAPPDATA%\hermes\exec-brain\eb.py` with E2 subcommands:
  - `eb telemetry` — poll all provider adapters, write snapshot to governor.db
  - `eb brief` — generate deterministic Daily Resource Brief (no LLM)
  - `eb record-request` — log an observed API request
  - `eb gov-status` — show governor.db status
  - `eb gov-verify` — verify governor.db integrity + chain
  - `eb gov-init` — initialize governor.db
- Governor database: `%LOCALAPPDATA%\hermes\exec-brain\governor.db`
  - Schema v1: provider_snapshot, capacity_dimension, observed_request, daily_brief_log, daily_aggregate
  - All tables append-only via SQLite triggers
  - Hash-chained provider_snapshot (seq, record_sha256, prev_sha256)
  - Chain-head anchor: `gov-chain-head.json`
- Provider adapters (4): Nous, DeepSeek, Codex, Antigravity
  - All adapters return UNKNOWN for unobservable dimensions
  - D3: routable flag separates telemetry from routability
  - D2: DeepSeek key read by reference only, never printed/logged
- Daily Resource Brief: deterministic text report, no LLM
  - Per-provider: operational state, dimensions, yesterday usage, burn trend
  - Summary: provider counts, NOT_ENFORCED markers, UNKNOWN for omitted dims
- Publication: `eb brief --publish` writes to control-plane repo
  - resource-status/daily-brief-<YYYY-MM-DD>.md
  - resource-status/latest-brief.md
  - resource-status/provider-state.json
  - Secret redaction before write (aborts if secrets detected)
- Retention policy (D5):
  - Snapshots: 90 days
  - Observed requests: 30 days
  - Briefs: 365 days
  - Daily aggregates: 365 days
- Tests: 45/45 passed (test_governor.py)
- E1 regression: 32/32 passed (test_eb.py)

## Owner decisions incorporated

- D1: Separate governor.db (APPROVED)
- D2: Windows Credential Manager canonical for DeepSeek (APPROVED WITH CHANGE)
- D3: Observed-only Codex/Antigravity, routability separated (APPROVED WITH CHANGE)
- D4: Burn trend = 24h vs 24h, ±20% threshold (APPROVED)
- D5: Retention with daily_aggregate 365d (APPROVED WITH ADDITION)
- State timestamp discipline (APPROVED)

## Acceptance verification

- 45/45 E2 tests: PASS
- 32/32 E1 tests: PASS (no regression)
- `eb gov-verify`: PASS
- `eb brief`: renders correctly with UNKNOWN/NOT_ENFORCED
- `eb telemetry`: 4 snapshots written (one per provider)
- No secrets in output files or GitHub
- E1 schema unchanged (separate governor.db)

## Scope confirmed NOT implemented (E3+)

- Worker qualification / performance gating (E3)
- Central Qualification Gate (E3)
- Predictive exhaustion enforcement (E4)
- Protected reserve enforcement (E4)
- Automatic checkpoints / handover (E4)
- Safe mode / owner override UX (E5)
- Provider/model quality claims
- Automatic model selection
- Provider API routing (sending requests)
