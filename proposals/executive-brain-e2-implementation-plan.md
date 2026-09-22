# Executive Brain E2 — Implementation Plan (APPROVED)

Status: APPROVED — owner decisions incorporated (2026-09-22)
Baseline: approved-architecture/executive-brain-v2.md (E1 active)
Author: Chief of Staff (Hermes)
Date: 2026-09-22 (approved: 2026-09-22)
Scope: E2 only — deterministic provider telemetry adapters, normalized
multidimensional telemetry ledger, deterministic Daily Resource Brief,
curated resource-status publication to the GitHub control plane. No worker
qualification/performance gating (E3), no predictive exhaustion enforcement
(E4), no protected reserve enforcement (E4), no automatic checkpoints/handover
(E4), no safe mode/owner override UX (E5).

---

## Owner decisions (approved 2026-09-22)

### D1 — Separate governor.db: APPROVED
Keep Resource Governor telemetry physically separate from exec_brain.db.
E1 is stable/audited and must not be put at risk by high-frequency telemetry,
retention cleanup, or future adapter changes. E1 IDs such as
task_id/floor_id may be referenced logically where required, but E1 schema
is NOT modified for E2.

### D2 — DeepSeek credential: APPROVED WITH CHANGE
Windows Credential Manager is the CANONICAL DeepSeek credential store.

Before migration, perform a safe presence/location check only:
- check whether DEEPSEEK_API_KEY env var exists WITHOUT printing its value
- check whether a Windows Credential Manager entry already exists
- check whether existing Hermes config refers to a credential location

Report ONLY: "env var present: yes/no", "Credential Manager entry present:
yes/no", "config reference present: yes/no".

If the key is not already securely stored, STOP and ask the owner to
enter/store it locally. Never request the API key in Discord, ChatGPT,
GitHub, logs, or source. `DEEPSEEK_API_KEY` env var may be supported as a
temporary/local fallback but must never be persisted to GitHub or logs.

### D3 — Codex/Antigravity routability: APPROVED WITH CHANGE
Ship observed-only adapters now, but separate TELEMETRY from ROUTABILITY.

If no reliable programmatic API/CLI exists: adapter exists, operational
observations recorded where deterministically observable, unavailable
capacity fields = UNKNOWN, telemetry confidence reflects the source,
`routable = false`. Do NOT pretend "installed desktop app" means Chief can
automatically route work to it. When a verified CLI/API/automation path
exists later, routability can be enabled without redesigning the E2 schema.

### D4 — Burn trend: APPROVED
Initial burn trend = rolling recent 24h compared with preceding 24h, using
±20% as the material-change threshold. Render: rising | stable | falling |
UNKNOWN (when insufficient history exists). This is telemetry/trend reporting
ONLY — NOT E4 predictive exhaustion logic. Persist enough raw/aggregate
history so a 7-day baseline can be added later without schema redesign.

### D5 — Retention: APPROVED WITH ADDITION
- telemetry snapshots: 90 days
- detailed request/usage events: 30 days
- Daily Resource Briefs: 365 days
- daily aggregated provider usage: 365 days

Retention cleanup must be deterministic and auditable. Detailed
high-frequency events can expire while long-term daily aggregates remain
available for later E3/E4 learning and trend analysis.

### State timestamp discipline: APPROVED
current_company_state.md Timestamp must be regenerated from the actual final
state and updated as the LAST state-writing step immediately before the
rollout commit. Never copy a cached timestamp from an earlier run.

---

## 1. Local environment reconnaissance — actual findings

### 1.1 Nous / LongCat (active provider)

Evidence:
- `config.yaml`: `model.provider=nous`, `model.base_url=https://inference-api.nousresearch.com/v1`,
  `model.default=meituan/longcat-2.0:free`
- `auth.json`: `credential_pool.nous[0]` — OAuth token, `expires_in=3599`,
  `request_count=27`, `obtained_at` present, `expires_at` present
- `provider_models_cache.json`: full model catalog with pricing (prompt,
  completion, cache_read per-token) and context lengths
- `context_length_cache.yaml`: `meituan/longcat-2.0:free` = 1048576 tokens
- Portal at `https://portal.nousresearch.com` — NO public usage/quota API

Obtainable: auth token expiry, local request count, inference endpoint
reachability, model catalog + pricing.
NOT obtainable: quota, reset, balance, rate limits → UNKNOWN.

### 1.2 DeepSeek (metered API, owner has key)

Evidence: No local DeepSeek config files. `openai` Python v2.24.0 in
hermes-agent venv. DeepSeek API base: `https://api.deepseek.com`.
Credential stored in Windows Credential Manager (canonical) with
DEEPSEEK_API_KEY as temporary fallback.

Obtainable: API availability, observed tokens per request, calculated
spend (tokens × DeepSeek published pricing), rate limit headers if present.
NOT obtainable: billing balance, rate limit ceilings → UNKNOWN.

### 1.3 Codex (desktop app only)

Evidence: `OpenAI.Codex_26.915.4065.0` MSIX installed. Desktop app at
`%LOCALAPPDATA%\Microsoft\WindowsApps\OpenAI.Codex_*`. NO CLI on PATH.

Obtainable: installed version, process running state.
NOT obtainable: all capacity dimensions → UNKNOWN. routable = false.

### 1.4 Antigravity (desktop app only)

Evidence: `Google.Antigravity` v2.15.1 installed. Electron app at
`%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe`. Credential in
Windows Credential Manager (`LegacyGeneric:target=gemini:antigravity`).

Obtainable: installed version, process state, credential presence.
NOT obtainable: all capacity dimensions → UNKNOWN. routable = false.

### 1.5 Summary

| Provider      | Availability | Token Usage | Monetary  | Quota     | Rate Limits | Reset   | Routable |
|---------------|-------------|-------------|-----------|-----------|-------------|---------|----------|
| Nous/LongCat  | YES (ping)  | LOCAL COUNT | UNKNOWN   | UNKNOWN   | UNKNOWN     | UNKNOWN | true     |
| DeepSeek      | YES (ping)  | YES (obs)   | CALCULATED| N/A       | UNKNOWN     | N/A     | true     |
| Codex         | YES (proc)  | UNKNOWN     | UNKNOWN   | UNKNOWN   | UNKNOWN     | UNKNOWN | false    |
| Antigravity   | YES (proc)  | UNKNOWN     | UNKNOWN   | UNKNOWN   | UNKNOWN     | UNKNOWN | false    |

---

## 2. Proposed architecture

E2 extends the local exec-brain package with a Governor subsystem. It does
NOT modify E1's schemas, E1's CLI commands, or E1's skill.

    E1 (unchanged)                                     E2 (new)
    exec_brain.db                                      governor.db
    task_record              (logical reference        provider_snapshot
    subtask_record            only in E3+)             capacity_dimension
    quality_floor                                     observed_request
    strategy_decision                                 daily_brief_log
    override_record                                   daily_aggregate
    audit_log

    CLI: eb classify/decompose/freeze/                 CLI: eb telemetry/brief/
         route/override/audit/backup/                      record-request/
         restore/summary                                   gov-status/gov-verify

### 2.1 Adapter interface

All adapters implement:

```python
class ProviderAdapter:
    provider_id: str          # "nous" | "deepseek" | "codex" | "antigravity"
    routable: bool            # false for desktop-app-only providers
    def probe(self) -> TelemetrySnapshot
```

`TelemetrySnapshot`:
    provider: str
    captured_at: str           # ISO-8601 UTC
    operational: str           # up | degraded | down | unknown
    routable: bool             # D3: separate telemetry from routability
    available_models: list     # [{id, roles, pricing, context_length}] | []
    dimensions: list           # [CapacityDimension]
    rate_limit_state: str      # ok | throttled | cooldown-until | unknown
    last_success_at: str | None
    telemetry_source: str      # provider-api | observed-only | mixed
    telemetry_confidence: str  # high | medium | low
    quota_semantics: str       # provider-specific note or "unknown"
    errors: list               # [str] non-fatal errors during probe

`CapacityDimension`:
    dimension_kind: str
    remaining: str             # "<value> <unit>" | "unknown"
    unit: str                  # tokens | requests | USD | credits | concurrent
    reserve: str               # "NOT_ENFORCED"
    effective_usable: str      # "NOT_ENFORCED"
    reset_renewal: str         # ISO-8601 | "unknown"
    source: str                # provider-api | observed | inferred
    confidence: str            # high | medium | low

Rules:
- If a provider does NOT expose a dimension, the adapter OMITS it (no
  placeholder, no zero, no "unlimited")
- `remaining` is a STRING carrying value + unit, e.g. "1500 tokens", "unknown"
- `reserve` and `effective_usable` are ALWAYS "NOT_ENFORCED" in E2
- `confidence` reflects the source

---

## 3. Provider adapter designs

### 3.1 NousAdapter

Source: mixed (local config + ping + cached catalog)
Routable: true

Probe:
1. Read `auth.json` credential_pool.nous[0]: `expires_at`,
   `request_count`
2. Ping `https://inference-api.nousresearch.com/v1/models`
3. Read `provider_models_cache.json` for model catalog
4. Read `context_length_cache.yaml` for active model context length

Dimensions: `provider_credit` (token validity, seconds), `request_window`
(local counter). All others OMITTED.

### 3.2 DeepSeekAdapter

Source: provider-api (local secret reference)
Routable: true

Probe:
1. Resolve API key by REFERENCE (never value):
   a. env var DEEPSEEK_API_KEY (presence check only — D2)
   b. Windows Credential Manager target `deepseek:api`
   c. If neither → operational=unknown, error="api-key-not-configured"
2. Ping `https://api.deepseek.com/v1/models`
3. Read configured spending budget from `deepseek-config.json`
4. Read observed token usage + calculated spend from local ledger

Dimensions: `monetary_balance` (budget - calculated spend), `rate_limit_state`
(from headers), `token_window` (metered; no token quota).

Secret handling: key never stored in ledger, logs, brief, or GitHub.
`deepseek-config.json` contains only the budget (a number).

### 3.3 CodexAdapter

Source: observed-only
Routable: false (desktop app, no API/CLI)

Probe:
1. Check if `OpenAI.Codex` package is registered
2. Check if `Codex.exe` process is running
3. Read installed version from app manifest

Dimensions: `concurrency` only (remaining="unknown", confidence=low,
note="desktop app; no programmatic telemetry"). All others OMITTED.

operational: up (running) | degraded (installed, not running) |
down (not installed) | unknown.

### 3.4 AntigravityAdapter

Source: observed-only
Routable: false (desktop app, no API/CLI)

Probe:
1. Check if `Google.Antigravity` package is registered
2. Check if `Antigravity.exe` process is running
3. Check Windows Credential Manager for `gemini:antigravity` presence only
4. Read installed version from app manifest

Dimensions: `concurrency` only (remaining="unknown", confidence=low).

operational: up (running + credential present) | degraded (running no
credential, or installed not running) | down | unknown.

---

## 4. Normalized telemetry ledger — SQLite schema

Database: `%LOCALAPPDATA%\hermes\exec-brain\governor.db`
Schema version: 1 (PRAGMA user_version = 1)

```sql
CREATE TABLE IF NOT EXISTS provider_snapshot (
  snapshot_id    TEXT PRIMARY KEY,
  provider       TEXT NOT NULL,
  captured_at    TEXT NOT NULL,
  operational    TEXT NOT NULL,
  routable       INTEGER NOT NULL DEFAULT 0,    -- D3: telemetry ≠ routability
  rate_limit_state TEXT NOT NULL,
  last_success_at TEXT,
  telemetry_source TEXT NOT NULL,
  telemetry_confidence TEXT NOT NULL,
  quota_semantics TEXT NOT NULL,
  available_models TEXT NOT NULL DEFAULT '[]',   -- JSON array
  errors TEXT NOT NULL DEFAULT '[]',              -- JSON array
  seq            INTEGER NOT NULL UNIQUE,
  record_sha256  TEXT NOT NULL,
  prev_sha256    TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS capacity_dimension (
  dimension_id   TEXT PRIMARY KEY,
  snapshot_id    TEXT NOT NULL REFERENCES provider_snapshot(snapshot_id),
  provider       TEXT NOT NULL,
  dimension_kind TEXT NOT NULL,
  remaining      TEXT NOT NULL,
  unit           TEXT NOT NULL,
  reserve        TEXT NOT NULL DEFAULT 'NOT_ENFORCED',
  effective_usable TEXT NOT NULL DEFAULT 'NOT_ENFORCED',
  reset_renewal  TEXT NOT NULL,
  source         TEXT NOT NULL,
  confidence     TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS observed_request (
  request_id     TEXT PRIMARY KEY,
  provider       TEXT NOT NULL,
  model          TEXT,
  requested_at   TEXT NOT NULL,
  input_tokens   INTEGER,
  output_tokens  INTEGER,
  total_tokens   INTEGER,
  monetary_cost  TEXT,
  status         TEXT NOT NULL,
  error_code     TEXT,
  latency_ms     INTEGER,
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_brief_log (
  brief_id       TEXT PRIMARY KEY,
  generated_at   TEXT NOT NULL,
  rendered_text  TEXT NOT NULL,
  published_to_github INTEGER NOT NULL DEFAULT 0,
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_aggregate (
  aggregate_id   TEXT PRIMARY KEY,               -- da-<YYYYMMDD>-<provider>
  provider       TEXT NOT NULL,
  aggregate_date TEXT NOT NULL,                  -- YYYY-MM-DD
  request_count  INTEGER NOT NULL DEFAULT 0,
  total_input_tokens INTEGER NOT NULL DEFAULT 0,
  total_output_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens   INTEGER NOT NULL DEFAULT 0,
  total_spend_usd TEXT NOT NULL DEFAULT '0.00',
  error_count    INTEGER NOT NULL DEFAULT 0,
  UNIQUE(provider, aggregate_date),
  schema_version INTEGER NOT NULL DEFAULT 1
);

-- Append-only triggers
CREATE TRIGGER IF NOT EXISTS trg_snapshot_no_update BEFORE UPDATE ON provider_snapshot
  BEGIN SELECT RAISE(ABORT, 'provider_snapshot is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_snapshot_no_delete BEFORE DELETE ON provider_snapshot
  BEGIN SELECT RAISE(ABORT, 'provider_snapshot is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_dimension_no_update BEFORE UPDATE ON capacity_dimension
  BEGIN SELECT RAISE(ABORT, 'capacity_dimension is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_dimension_no_delete BEFORE DELETE ON capacity_dimension
  BEGIN SELECT RAISE(ABORT, 'capacity_dimension is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_observed_no_update BEFORE UPDATE ON observed_request
  BEGIN SELECT RAISE(ABORT, 'observed_request is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_observed_no_delete BEFORE DELETE ON observed_request
  BEGIN SELECT RAISE(ABORT, 'observed_request is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_brief_no_update BEFORE UPDATE ON daily_brief_log
  BEGIN SELECT RAISE(ABORT, 'daily_brief_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_brief_no_delete BEFORE DELETE ON daily_brief_log
  BEGIN SELECT RAISE(ABORT, 'daily_brief_log is append-only'); END;
```

### 4.1 Chain-head anchor

`exec-brain/gov-chain-head.json`:

```json
{
  "provider_snapshot": [seq, "sha256"],
  "capacity_dimension": [seq, "sha256"]
}
```

observed_request, daily_brief_log, and daily_aggregate are append-only via
triggers only (not hash-chained).

### 4.2 Retention policy (D5)

| Table               | Retention        |
|---------------------|------------------|
| provider_snapshot   | 90 days          |
| capacity_dimension  | 90 days          |
| observed_request    | 30 days          |
| daily_brief_log     | 365 days         |
| daily_aggregate     | 365 days         |

Pruning: `eb telemetry --prune` hard-deletes rows older than retention.
The only permitted DELETE path. Logs to `exec-brain/prune.log`. Updates
chain-head anchor after prune.

daily_aggregate is UPSERTed (idempotent) — re-aggregating a day overwrites
the aggregate row. Aggregates are NOT pruned until 365d.

### 4.3 Aggregation

After each `eb telemetry` run (or via `eb telemetry --aggregate`), the
previous day's observed_request rows are aggregated into daily_aggregate
(request_count, tokens, spend, errors). Once aggregated, detailed rows
are eligible for 30d pruning while the aggregate persists for 365d.

---

## 5. Deterministic Daily Resource Brief

### 5.1 Generation (no LLM)

Command: `eb brief [--date YYYY-MM-DD] [--no-publish]`

Deterministic Python: queries ledger → renders fixed text template.
No LLM called.

### 5.2 Brief format

```
================================================================================
  DAILY RESOURCE BRIEF — <YYYY-MM-DD> <HH:MM> UTC
  Executive Brain E2 — DETERMINISTIC (no LLM)
================================================================================

PROVIDER: <provider_id>    [<operational>]    [routable: yes/no]
  Telemetry source: <source>  Confidence: <confidence>
  Last success: <timestamp | "never">

  Dimensions:
    <dimension_kind>: <remaining> <unit>
      reserve: NOT_ENFORCED | effective_usable: NOT_ENFORCED
      reset/renewal: <timestamp | unknown>
      source: <source>  confidence: <confidence>

  Yesterday:
    Requests observed: <n>
    Tokens (in/out/total): <n>/<n>/<n>
    Calculated spend: <amount> USD | unknown
    Burn trend: rising | stable | falling | unknown

  Reset/renewal: <next known reset | unknown>

  --- (per provider)

================================================================================
  SUMMARY
================================================================================
  Providers up:     <n>/<n>
  Providers unknown: <n>/<n>
  Providers down:   <n>/<n>
  Routable:         <list of routable provider ids>

  Highest-confidence routable: <id> (<confidence>)
  Most constrained dimension: <provider>:<kind> (<remaining> <unit>)

  NOT_ENFORCED (E4): reserve, effective_usable, projected_exhaustion,
                     checkpoint_handover, protected_reserve,
                     expected_today_demand
  UNKNOWN: all dimensions not explicitly listed above

  Generated by: eb brief (deterministic)
  Ledger: governor.db  Schema: 1
================================================================================
```

### 5.3 Burn trend (D4)

Trailing 24h vs preceding 24h, ±20% threshold:
- trailing > preceding × 1.2 → rising
- trailing < preceding × 0.8 → falling
- otherwise → stable
- insufficient data → unknown

Persisted in daily_aggregate so 7-day baseline can be added later.

### 5.4 E4 placeholders

- expected_today_demand: NOT_ENFORCED (E4)
- projected_exhaustion: NOT_ENFORCED (E4)
- reserve / effective_usable: NOT_ENFORCED

---

## 6. Curated resource-status publication to GitHub

Command: `eb publish-brief` (or `eb brief --publish`)

Writes to local control-plane repo (push follows existing sync discipline):

    resource-status/
      daily-brief-<YYYY-MM-DD>.md
      latest-brief.md
      provider-state.json

Does NOT publish: raw governor.db, observed_request rows, secrets, internal
paths. Redacts patterns: `sk-*`, `Bearer `, `api[_-]?key`, `token`, `password`.
If redaction triggers → ABORT write.

provider-state.json: machine-readable per-provider state with `routable`
flag, dimensions, NOT_ENFORCED markers, UNKNOWN for omitted dimensions.

---

## 7. CLI commands

All added to existing `eb` CLI. Stdlib-only.

| Command                | Purpose                                          |
|------------------------|--------------------------------------------------|
| `eb telemetry`         | Poll all adapters, write snapshot                |
| `eb telemetry --prune` | Prune rows older than retention                  |
| `eb telemetry --aggregate` | Aggregate yesterday into daily_aggregate     |
| `eb brief`             | Generate Daily Resource Brief (no LLM)           |
| `eb brief --publish`   | Generate brief + write to local control-plane    |
| `eb record-request`    | Log an observed request                          |
| `eb gov-status`        | Show governor.db status (row counts, chain head) |
| `eb gov-verify`        | Verify governor.db integrity + chain             |

Exit codes: 0 = success, 1 = partial, 2 = total failure.

---

## 8. Polling cadence

Windows Scheduled Task: `ExecBrainTelemetry`
- Trigger: every 30 min, survives logon/reboot
- Lock file: `exec-brain/telemetry.lock`
- Log: `exec-brain/telemetry.log`
- Stale lock (>10 min): break + warn

---

## 9. Secret / redaction rules (D2)

1. DeepSeek key NEVER printed, logged, stored in DB, or committed
2. Resolution order: env var `DEEPSEEK_API_KEY` (presence check only) →
   Windows Credential Manager `deepseek:api`
3. If neither found → STOP, ask owner to store securely
4. `deepseek-config.json`: budget only, no key
5. Nous token: read `expires_at`/`request_count` only, never token value
6. Antigravity credential: presence check only (yes/no), never read value
7. publish-brief: scan output for secret patterns → ABORT if match

---

## 10. Storage paths

```
%LOCALAPPDATA%\hermes\exec-brain\
  eb.py                        E1 + E2 CLI
  exec_brain.db                E1 database (unchanged)
  chain-head.json              E1 chain anchor (unchanged)
  governor.db                  E2 telemetry ledger (NEW)
  gov-chain-head.json          E2 chain anchor (NEW)
  telemetry.log                E2 polling log (NEW)
  telemetry.lock               E2 polling lock (NEW)
  prune.log                    E2 prune audit log (NEW)
  deepseek-config.json         E2 DeepSeek budget config (NEW, no secrets)
  tests\test_governor.py       E2 tests (NEW)
```

---

## 11. Forward-compatibility

E3/E4 add new tables or columns. E2 schema supports this:
- `routable` flag ready for E3 Qualification Gate
- `reserve`/`effective_usable` columns exist as NOT_ENFORCED
- `daily_aggregate` persists 365d for E3/E4 learning
- `provider` string id is stable
- `dimension_kind` uses §9a enum (extensible)

---

## 12. Test matrix — 45 tests

All tests are stdlib `unittest`, no external dependencies. Run via:
`python -m unittest tests.test_governor -v`

| #  | Test                                              | Category      |
|----|---------------------------------------------------|---------------|
| T1 | NousAdapter: reads auth.json, emits dimensions    | adapter       |
| T2 | NousAdapter: ping success → operational=up        | adapter       |
| T3 | NousAdapter: ping timeout → operational=down      | adapter       |
| T4 | NousAdapter: missing auth.json → error, continues | adapter       |
| T5 | DeepSeekAdapter: key from CM, pings API           | adapter       |
| T6 | DeepSeekAdapter: missing key → unknown, no crash  | adapter       |
| T7 | DeepSeekAdapter: 429 response → throttled         | adapter       |
| T8 | DeepSeekAdapter: spend calculated from observed   | adapter       |
| T9 | CodexAdapter: installed+running → up              | adapter       |
| T10| CodexAdapter: installed, not running → degraded   | adapter       |
| T11| CodexAdapter: not installed → down                | adapter       |
| T12| CodexAdapter: routable=false                      | adapter       |
| T13| AntigravityAdapter: credential present → up       | adapter       |
| T14| AntigravityAdapter: no credential → degraded      | adapter       |
| T15| AntigravityAdapter: routable=false                | adapter       |
| T16| governor.db init creates all tables + triggers    | ledger        |
| T17| provider_snapshot append-only (UPDATE rejected)   | ledger        |
| T18| provider_snapshot append-only (DELETE rejected)   | ledger        |
| T19| capacity_dimension append-only (UPDATE rejected)  | ledger        |
| T20| capacity_dimension append-only (DELETE rejected)  | ledger        |
| T21| observed_request append-only (UPDATE rejected)    | ledger        |
| T22| daily_brief_log append-only (DELETE rejected)     | ledger        |
| T23| Hash chain: seq order + sha256 links valid        | ledger        |
| T24| Chain-head anchor: prefix verification            | ledger        |
| T25| Prune: rows deleted, prune.log written, anchor ok | ledger        |
| T26| daily_aggregate: idempotent UPSERT                | ledger        |
| T27| daily_aggregate: correct rollup from observed     | ledger        |
| T28| `eb telemetry --dry-run` prints, no write         | cli           |
| T29| `eb telemetry` writes snapshot + dimensions       | cli           |
| T30| `eb brief` renders without LLM, shows UNKNOWN     | cli           |
| T31| `eb brief --date` renders historical brief        | cli           |
| T32| `eb record-request` writes observed_request row   | cli           |
| T33| `eb gov-verify` PASS on fresh DB                  | cli           |
| T34| `eb gov-verify` FAIL on chain break               | cli           |
| T35| Brief: UNKNOWN for unobservable dims              | brief         |
| T36| Brief: NOT_ENFORCED for E4 fields                 | brief         |
| T37| Brief: yesterday usage from observed_request      | brief         |
| T38| Brief: burn trend rising/stable/falling/unknown   | brief         |
| T39| Brief: routable flag shown correctly              | brief         |
| T40| publish-brief: writes 3 files to repo             | publication   |
| T41| publish-brief: redacts secrets, aborts            | publication   |
| T42| publish-brief: provider-state.json valid schema   | publication   |
| T43| Full cycle: telemetry → brief → publish            | integration   |
| T44| Concurrent telemetry: lock prevents overlap       | integration   |
| T45| Stale lock: broken after timeout, warning logged  | integration   |

**Total: 45 tests** (expanded from 38 due to D3 routable, D5 aggregate)

---

## 13. Rollout procedure

1. This plan committed (PLAN ONLY) — DONE
2. Owner decisions approved — DONE
3. Create `exec-brain/e2` branch
4. Implement: eb.py extensions, test_governor.py, deepseek-config.json template
5. Run 45/45 tests on feature branch
6. Update current_company_state.md (Timestamp = last step)
7. Create decisions/exec-brain-e2-rollout.md
8. Merge to main
9. Enable ExecBrainTelemetry scheduled task
10. Run `eb telemetry` manually (first snapshot)
11. Run `eb brief --publish` (first brief + sync)
12. Verify: gov-verify PASS, brief renders, no secrets in repo

Rollback: disable task, delete governor.db, revert eb.py, re-verify E1 32/32.

---

## 14. Acceptance criteria

1. 45/45 tests pass
2. `eb gov-verify` PASS after one poll cycle
3. `eb brief` renders: UNKNOWN for unobservable, NOT_ENFORCED for E4,
   no synthetic overall capacity %
4. `eb brief --publish` writes 3 files, no secrets, no internal paths
5. DeepSeek key never printed/logged/committed
6. E1 regression: 32/32 green, audit PASS
7. Scheduled task runs every 30 min, survives reboot
8. current_company_state.md Timestamp correct
9. Chain valid after 7 days of polling
10. Prune deterministic + auditable

---

## 15. Out of scope (E2 only)

- Worker qualification / performance gating (E3)
- Central Qualification Gate (E3)
- Predictive exhaustion enforcement (E4)
- Protected reserve enforcement (E4)
- Automatic checkpoints / handover (E4)
- Safe mode / owner override UX (E5)
- Provider/model quality claims
- Automatic model selection
- Provider API routing (sending requests)

Schema columns for these exist as NOT_ENFORCED placeholders only.

---

## 16. Amendment history

- rev 1 (2026-09-22): Initial plan.
- rev 2 (2026-09-22): Owner decisions D1–D5 incorporated. Added routable
  flag (D3), daily_aggregate table (D5), CM credential handling (D2),
  burn trend states (D4). Test matrix expanded 38→45. Status → APPROVED.
