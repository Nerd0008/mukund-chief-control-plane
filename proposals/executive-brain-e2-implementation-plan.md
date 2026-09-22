# Executive Brain E2 — Implementation Plan (Plan Only)

Status: PLAN (rev 1) — NOT IMPLEMENTED
Baseline: approved-architecture/executive-brain-v2.md (E1 active)
Author: Chief of Staff (Hermes)
Date: 2026-09-22
Scope: E2 only — deterministic provider telemetry adapters, normalized
multidimensional telemetry ledger, deterministic Daily Resource Brief,
curated resource-status publication to the GitHub control plane. No worker
qualification/performance gating (E3), no predictive exhaustion enforcement
(E4), no protected reserve enforcement (E4), no automatic checkpoints/handover
(E4), no safe mode/owner override UX (E5).

---

## 1. Local environment reconnaissance — actual findings

Before designing adapters, the local installed environment was inspected to
determine what telemetry is ACTUALLY obtainable for each target provider.

### 1.1 Nous / LongCat (active provider)

Evidence:
- `config.yaml`: `model.provider=nous`, `model.base_url=https://inference-api.nousresearch.com/v1`,
  `model.default=meituan/longcat-2.0:free`
- `auth.json`: `credential_pool.nous[0]` — OAuth token, `expires_in=3599`,
  `request_count=27`, `obtained_at` present, `expires_at` present
- `provider_models_cache.json`: full model catalog with pricing (prompt,
  completion, cache_read per-token) and context lengths
- `context_length_cache.yaml`: `meituan/longcat-2.0:free` = 1048576 tokens
- Portal at `https://portal.nousresearch.com` — Next.js app with
  `balanceUsd` in client data, but NO public usage/quota API (all `/api/*`
  paths return 404 or redirect to login)

Obtainable:
- Auth token expiry timestamp (HIGH confidence, local read)
- Local request count (HIGH confidence, local counter in credential_pool)
- Inference endpoint reachability (HIGH confidence, TCP/HTTP ping)
- Model catalog + pricing + context lengths (MEDIUM confidence, cached file)
- Token expiry remaining estimate (MEDIUM, inferred from expires_at)

NOT obtainable:
- Quota remaining / quota window (no API) → UNKNOWN
- Quota reset time → UNKNOWN
- Account balance / monetary (portal requires auth, no API) → UNKNOWN
- Rate limit state (not exposed) → UNKNOWN
- Short-window vs weekly vs monthly allowance semantics → UNKNOWN

### 1.2 DeepSeek (metered API, owner has key)

Evidence:
- No local DeepSeek config files found in user profile
- `openai` Python package v2.24.0 installed in hermes-agent venv (DeepSeek
  API is OpenAI-compatible)
- `openai` CLI available at `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\openai`
- DeepSeek models also routable via Nous (`~deepseek/deepseek-flash-latest`,
  `deepseek/deepseek-v4.1-flash`, etc.) but E2 targets the DIRECT DeepSeek
  API using the owner's own key
- DeepSeek API base: `https://api.deepseek.com` (standard)

Obtainable:
- API availability (HIGH confidence, ping `/models` or similar)
- Observed input/output tokens per request (HIGH confidence, from response
  `usage` field)
- Calculated monetary spend (MEDIUM confidence: observed tokens × DeepSeek
  published pricing)
- Rate limit headers if present in responses (MEDIUM confidence)
- Configured owner spending budget (HIGH confidence, local config file)

NOT obtainable:
- Account billing balance (DeepSeek does not expose a free billing API
  without authenticated dashboard) → UNKNOWN
- Quota window / allowance (metered, not quota-based) → N/A
- Rate limit ceilings (headers may not expose limits) → UNKNOWN

### 1.3 Codex (OpenAI Codex desktop app)

Evidence:
- `OpenAI.Codex_26.915.4065.0` MSIX package installed via winget
- Desktop app at `C:\Users\mukun\AppData\Local\Microsoft\WindowsApps\OpenAI.Codex_*`
- Local data at `C:\Users\mukun\AppData\Local\OpenAI\Codex\` (bin/, runtimes/,
  chrome-native-hosts-v2.json)
- NO `codex` CLI on PATH — the architecture's assumed "Codex CLI" is not
  installed; only the desktop app exists

Obtainable:
- Installed version (HIGH confidence, read from app manifest/package)
- Process running state (HIGH confidence, OS process check)
- Local app data presence (HIGH confidence, filesystem check)

NOT obtainable:
- Quota / token usage / allowance (desktop app, no API) → UNKNOWN
- Monetary spend → UNKNOWN
- Rate limits → UNKNOWN
- Model availability (internal to app) → UNKNOWN

### 1.4 Antigravity (Google Gemini desktop app)

Evidence:
- `Google.Antigravity` v2.15.1 installed via winget
- Electron desktop app at `C:\Users\mukun\AppData\Local\Programs\antigravity\Antigravity.exe`
- Credential stored in Windows Credential Manager as
  `LegacyGeneric:target=gemini:antigravity`
- NO CLI on PATH — desktop app only

Obtainable:
- Installed version (HIGH confidence, read from app manifest)
- Process running state (HIGH confidence, OS process check)
- Credential presence in Windows Credential Manager (HIGH confidence)

NOT obtainable:
- Quota / token usage / allowance (desktop app, no API) → UNKNOWN
- Monetary spend → UNKNOWN
- Rate limits → UNKNOWN
- Model availability → UNKNOWN

### 1.5 Summary of obtainability

| Provider      | Availability | Token Usage | Monetary  | Quota     | Rate Limits | Reset   |
|---------------|-------------|-------------|-----------|-----------|-------------|---------|
| Nous/LongCat  | YES (ping)  | LOCAL COUNT | UNKNOWN   | UNKNOWN   | UNKNOWN     | UNKNOWN |
| DeepSeek      | YES (ping)  | YES (obs)   | CALCULATED| N/A       | UNKNOWN     | N/A     |
| Codex         | YES (proc)  | UNKNOWN     | UNKNOWN   | UNKNOWN   | UNKNOWN     | UNKNOWN |
| Antigravity   | YES (proc)  | UNKNOWN     | UNKNOWN   | UNKNOWN   | UNKNOWN     | UNKNOWN |

This table drives the adapter design: every adapter exposes the SAME
normalized interface, but returns UNKNOWN for dimensions it cannot observe.
No adapter fabricates a value where none exists.

---

## 2. Proposed architecture

E2 extends the local exec-brain package with a Governor subsystem. It does
NOT modify E1's schemas, E1's CLI commands, or E1's skill. E2 adds new
commands to the existing `eb` CLI and a new SQLite database for telemetry.

    ┌─ E1 (unchanged) ──────────────────────────────────────────┐
    │  exec_brain.db  task_record | subtask_record | quality_floor │
    │               strategy_decision | override_record | audit_log │
    └────────────────────────────────────────────────────────────┘
                       │ read-only future integration (E3+)
                       ▼
    ┌─ E2 (new) ────────────────────────────────────────────────┐
    │  governor.db    provider_snapshot | capacity_dimension      │
    │                 observed_request | daily_brief_log           │
    │                                                             │
    │  eb telemetry  → poll all adapters → write snapshot         │
    │  eb brief      → read ledger → render text report (no LLM)  │
    │  eb publish    → render curated summary → write to repo     │
    └────────────────────────────────────────────────────────────┘
                       │ curated summary only
                       ▼
    ┌─ GitHub control plane ────────────────────────────────────┐
    │  resource-status/daily-brief-<YYYY-MM-DD>.md               │
    │  resource-status/latest-brief.md  (symlink/copy)           │
    │  resource-status/provider-state.json  (non-sensitive)       │
    └────────────────────────────────────────────────────────────┘

### 2.1 E1 integration boundary

E2 does NOT write to E1's exec_brain.db. E2 reads nothing from E1 in this
phase. The integration boundary is:

- E2 records which providers are available and their capacity state
- In E3+, E1's `eb route` will consult E2's governor.db before finalizing
  a route (Governor check per §2 of the architecture)
- For E2, the two systems run independently; the only shared artifact is
  the `exec-brain/` directory on disk

### 2.2 Adapter interface (abstract)

All adapters implement one interface:

```python
class ProviderAdapter:
    provider_id: str          # "nous" | "deepseek" | "codex" | "antigravity"
    def probe(self) -> TelemetrySnapshot
```

`TelemetrySnapshot` is a dataclass:

    provider: str
    captured_at: str           # ISO-8601 UTC
    operational: str           # up | degraded | down | unknown
    available_models: list     # [{id, roles, pricing, context_length}] | []
    dimensions: list           # [CapacityDimension]
    rate_limit_state: str      # ok | throttled | cooldown-until | unknown
    last_success_at: str | None
    telemetry_source: str      # provider-api | observed-only | mixed
    telemetry_confidence: str  # high | medium | low
    quota_semantics: str       # provider-specific note or "unknown"
    errors: list               # [str] non-fatal errors during probe

`CapacityDimension`:

    dimension_kind: str        # request_window | token_window |
                               # daily_allowance | weekly_allowance |
                               # monthly_allowance | monetary_balance |
                               # concurrency | rate_limit | provider_credit
    remaining: str             # "<value> <unit>" | "unknown"
    unit: str                  # "tokens" | "requests" | "USD" | "credits" | "concurrent"
    reserve: str               # "NOT_ENFORCED" (E4 placeholder)
    effective_usable: str      # "NOT_ENFORCED" (E4 placeholder)
    reset_renewal: str         # ISO-8601 timestamp | "unknown"
    source: str                # provider-api | observed | inferred
    confidence: str            # high | medium | low

Rules:
- If a provider does NOT expose a dimension, the adapter OMITS it from the
  dimensions list entirely (no placeholder, no zero, no "unlimited")
- `remaining` is a STRING carrying both value and unit, e.g. "1500 tokens",
  "27 requests", "unknown". Never a bare numeric that loses its unit.
- `reserve` and `effective_usable` are ALWAYS the literal string
  "NOT_ENFORCED" in E2. E4 will replace these with real values.
- `confidence` reflects the source: provider-api=high, observed=medium,
  inferred=low

---

## 3. Provider adapter designs

### 3.1 NousAdapter

Source type: mixed (local config + ping + cached catalog)

Probe sequence:
1. Read `auth.json` credential_pool.nous[0]:
   - `expires_at` → auth_token_expiry dimension (monetary_balance equivalent:
     token-validity window, unit="seconds-remaining")
   - `request_count` → local_request_count dimension (observed, unit="requests")
2. Ping `https://inference-api.nousresearch.com/v1/models` (or `/`):
   - 200 → operational=up
   - 5xx → operational=degraded
   - timeout/conn-refused → operational=down
3. Read `provider_models_cache.json` for model catalog:
   - available_models list with pricing and context_lengths
4. Read `context_length_cache.yaml` for active model context length

Dimensions emitted:
- `provider_credit` (token validity): remaining=<seconds-until-expiry>,
  reset_renewal=<expires_at>, source=local-observation, confidence=high
- `request_window` (local counter): remaining=<request_count>,
  source=observed, confidence=high, quota_semantics="local counter only; provider quota unknown"

All other dimensions: OMITTED (unknown).

Error handling:
- auth.json unreadable → operational=unknown, error logged, continue
- Ping fails → operational=down, dimensions still emitted from local data
- Cache file missing → available_models=[], confidence=low

### 3.2 DeepSeekAdapter

Source type: provider-api (with local secret reference)

Probe sequence:
1. Resolve API key from local secret storage by REFERENCE (never by value):
   - Check env var `DEEPSEEK_API_KEY`
   - If absent, check Windows Credential Manager target `deepseek:api`
   - If absent → operational=unknown, error="api-key-not-configured", return
2. Ping `https://api.deepseek.com/v1/models` with key:
   - 200 → operational=up, parse model list
   - 401 → operational=degraded (key invalid)
   - 429 → rate_limit_state=throttled, operational=degraded
   - 5xx → operational=degraded
   - timeout → operational=down
3. Read configured spending budget from local config file
   (`exec-brain/deepseek-config.json`, field `spending_budget_usd`)
4. Read observed token usage and calculated spend from local ledger
   (DeepSeek does not expose a usage API, so we track what WE send)

Dimensions emitted:
- `monetary_balance`: remaining=<budget - calculated_spend> USD,
  source=observed, confidence=medium,
  quota_semantics="owner-configured budget; spend calculated from observed requests"
- `rate_limit_state`: from last response headers if present, else "unknown",
  source=provider-api or "unknown"
- `token_window`: remaining=unknown (DeepSeek is metered, not token-windowed),
  source=provider-api, confidence=high, quota_semantics="metered provider; no token quota"

Error handling:
- Key not found → operational=unknown, single error, no dimensions
- API unreachable → operational=down, error logged
- Budget not configured → monetary_balance remaining="unknown",
  error="spending-budget-not-configured"

Secret handling:
- The key is read by the adapter at probe time, used in the HTTP request,
  and NEVER stored in the telemetry ledger, logs, brief, or GitHub
- `deepseek-config.json` contains only the budget (a number), never the key
- If the key is in Windows Credential Manager, the adapter reads it via
  `cmdkey /list` + PowerShell interop or a small credential-reading helper;
  the key value is never printed or logged

### 3.3 CodexAdapter

Source type: observed-only (desktop app, no API)

Probe sequence:
1. Check if `OpenAI.Codex` package is registered (winget list or MSIX query)
2. Check if any `Codex.exe` / `OpenAI.Codex.exe` process is running
   (via `tasklist` or `ps`)
3. Read installed version from app manifest if accessible

Dimensions emitted:
- `concurrency`: remaining="unknown", source=observed, confidence=low,
  quota_semantics="desktop app; no programmatic telemetry"

All other dimensions: OMITTED.

operational:
- process running → up
- installed but not running → degraded
- not installed → down
- check failed → unknown

### 3.4 AntigravityAdapter

Source type: observed-only (desktop app, no API)

Probe sequence:
1. Check if `Google.Antigravity` package is registered
2. Check if `Antigravity.exe` process is running
3. Check Windows Credential Manager for `LegacyGeneric:target=gemini:antigravity`
4. Read installed version from app manifest if accessible

Dimensions emitted:
- `concurrency`: remaining="unknown", source=observed, confidence=low,
  quota_semantics="desktop app; no programmatic telemetry"

All other dimensions: OMITTED.

operational:
- process running + credential present → up
- process running, no credential → degraded
- installed, not running → degraded
- not installed → down

---

## 4. Normalized telemetry ledger — SQLite schema

New database: `%LOCALAPPDATA%\hermes\exec-brain\governor.db`

Rationale for separate DB: telemetry is high-frequency (polls every 30 min)
while E1 task records are low-frequency (per task). Separate DBs allow
independent retention, backup, and pruning.

```sql
-- Schema version tracked via PRAGMA user_version
-- governor.db schema_version = 1

CREATE TABLE IF NOT EXISTS provider_snapshot (
  snapshot_id    TEXT PRIMARY KEY,            -- gov-<YYYYMMDD>-<shortuuid>
  provider       TEXT NOT NULL,               -- nous | deepseek | codex | antigravity
  captured_at    TEXT NOT NULL,               -- ISO-8601 UTC
  operational    TEXT NOT NULL,               -- up | degraded | down | unknown
  rate_limit_state TEXT NOT NULL,             -- ok | throttled | cooldown-until | unknown
  last_success_at TEXT,                       -- ISO-8601 UTC or NULL
  telemetry_source TEXT NOT NULL,             -- provider-api | observed-only | mixed
  telemetry_confidence TEXT NOT NULL,         -- high | medium | low
  quota_semantics TEXT NOT NULL,              -- provider-specific note
  available_models TEXT NOT NULL DEFAULT '[]', -- JSON array
  errors TEXT NOT NULL DEFAULT '[]',          -- JSON array of error strings
  seq            INTEGER NOT NULL UNIQUE,     -- deterministic chain order
  record_sha256  TEXT NOT NULL,               -- hash of canonical fields
  prev_sha256    TEXT,                        -- hash-chain link
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS capacity_dimension (
  dimension_id   TEXT PRIMARY KEY,            -- cd-<shortuuid>
  snapshot_id    TEXT NOT NULL REFERENCES provider_snapshot(snapshot_id),
  provider       TEXT NOT NULL,
  dimension_kind TEXT NOT NULL,               -- request_window | token_window | ...
  remaining      TEXT NOT NULL,               -- "<value> <unit>" | "unknown"
  unit           TEXT NOT NULL,               -- tokens | requests | USD | credits | concurrent
  reserve        TEXT NOT NULL DEFAULT 'NOT_ENFORCED',  -- E4 placeholder
  effective_usable TEXT NOT NULL DEFAULT 'NOT_ENFORCED', -- E4 placeholder
  reset_renewal  TEXT NOT NULL,               -- ISO-8601 | "unknown"
  source         TEXT NOT NULL,               -- provider-api | observed | inferred
  confidence     TEXT NOT NULL,               -- high | medium | low
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS observed_request (
  request_id     TEXT PRIMARY KEY,            -- obs-<YYYYMMDD>-<shortuuid>
  provider       TEXT NOT NULL,
  model          TEXT,
  requested_at   TEXT NOT NULL,               -- ISO-8601 UTC
  input_tokens   INTEGER,
  output_tokens  INTEGER,
  total_tokens   INTEGER,
  monetary_cost  TEXT,                        -- "<value> USD" | "unknown"
  status         TEXT NOT NULL,               -- success | error | timeout
  error_code     TEXT,
  latency_ms     INTEGER,
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_brief_log (
  brief_id       TEXT PRIMARY KEY,            -- brief-<YYYYMMDD>
  generated_at   TEXT NOT NULL,               -- ISO-8601 UTC
  rendered_text  TEXT NOT NULL,               -- full brief text (local only)
  published_to_github INTEGER NOT NULL DEFAULT 0,  -- 0/1
  schema_version INTEGER NOT NULL DEFAULT 1
);

-- Append-only enforcement: no UPDATE/DELETE on historical tables
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

`exec-brain/gov-chain-head.json` — mirrors E1's chain-head pattern:

```json
{
  "provider_snapshot": [seq, "sha256"],
  "capacity_dimension": [seq, "sha256"]
}
```

(observed_request and daily_brief_log are high-frequency/low-audit and are
NOT hash-chained; they are append-only via triggers only.)

### 4.2 Retention policy

| Table               | Retention        | Rationale                                  |
|---------------------|------------------|--------------------------------------------|
| provider_snapshot   | 90 days          | Burn trend analysis, daily brief history   |
| capacity_dimension  | 90 days          | Bound to snapshots                         |
| observed_request    | 30 days          | High volume; 30d sufficient for burn rate  |
| daily_brief_log     | 365 days         | Historical brief archive                   |

Pruning: `eb telemetry --prune` deletes rows older than retention. Pruning
is a HARD DELETE (the only permitted DELETE) and is logged to the prune log
file. Chain-head anchor is updated to the new tail after prune.

### 4.3 Append-only / audit behavior

- All four tables are append-only via triggers (UPDATE/DELETE rejected)
- The ONLY delete path is the prune command, which:
  1. Runs outside a transaction (DELETEs fire no triggers on some SQLite
     configs — verified at test time)
  2. Logs the prune event (table, rows_deleted, timestamp) to
     `exec-brain/prune.log`
  3. Updates `gov-chain-head.json` to the new chain tail
- Direct SQL UPDATE/DELETE through any tool is rejected by triggers

---

## 5. Deterministic Daily Resource Brief

### 5.1 Generation (no LLM)

Command: `eb brief [--date YYYY-MM-DD] [--no-publish]`

The brief is generated by deterministic Python code that:
1. Queries governor.db for the most recent snapshot per provider
2. Queries yesterday's snapshots for comparison
3. Queries observed_request for the trailing 24h burn calculation
4. Renders a fixed text template

No LLM is called. The output is fully determined by the ledger contents.

### 5.2 Brief format

```
================================================================================
  DAILY RESOURCE BRIEF — <YYYY-MM-DD> <HH:MM> UTC
  Executive Brain E2 — DETERMINISTIC (no LLM)
================================================================================

PROVIDER: <provider_id>    [<operational>]
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
    Burn trend: <increasing | decreasing | stable | unknown>

  Reset/renewal: <next known reset | unknown"

  ---
  (repeated per provider)

================================================================================
  SUMMARY
================================================================================
  Providers up:     <n>/<n>
  Providers unknown: <n>/<n>
  Providers down:   <n>/<n>

  Highest-confidence provider: <id> (<confidence>)
  Most constrained dimension: <provider>:<kind> (<remaining> <unit>)

  NOT_ENFORCED (E4): reserve, effective_usable, projected_exhaustion,
                     checkpoint_handover, protected_reserve
  UNKNOWN: all dimensions not explicitly listed above

  Generated by: eb brief (deterministic)
  Ledger: governor.db  Schema: 1
  Chain head: provider_snapshot=<seq>:<sha12> capacity_dimension=<seq>:<sha12>
================================================================================
```

### 5.3 Yesterday's observed usage

Computed from `observed_request` WHERE `requested_at` BETWEEN
`now - 48h` AND `now - 24h`. If no rows exist, renders "No observed
requests in the preceding 24h window."

### 5.4 Burn trend

Computed from two windows: trailing 24h vs preceding 24h.
- If both windows have 0 requests → "stable (no activity)"
- If only trailing has requests → "increasing (from zero)"
- If trailing > preceding by >20% → "increasing"
- If trailing < preceding by >20% → "decreasing"
- Otherwise → "stable"
- If insufficient data → "unknown"

### 5.5 Expected today demand

NOT COMPUTED in E2. Renders: "expected_today_demand: NOT_ENFORCED (E4)".

### 5.6 Projected exhaustion risk

NOT COMPUTED in E2. Renders: "projected_exhaustion: NOT_ENFORCED (E4)".

---

## 6. Curated resource-status publication to GitHub

### 6.1 What gets published

Command: `eb publish-brief` (or `eb brief --publish`)

Writes to the local control-plane repo (NOT directly to GitHub — push
follows existing sync discipline):

    mukund-chief-control-plane/
      resource-status/
        daily-brief-<YYYY-MM-DD>.md     full brief text, dated
        latest-brief.md                 copy of most recent brief
        provider-state.json             machine-readable non-sensitive state

### 6.2 What does NOT get published

- Raw governor.db (local only)
- observed_request rows (local only)
- Any API key, token, credential, or secret
- Any error message that might contain internal paths or config details
- Internal chain-head SHA values (the chain head IS published for
  verification, but not individual record SHAs)

### 6.3 provider-state.json format

```json
{
  "generated_at": "2026-09-22T08:00:00Z",
  "schema_version": 1,
  "deterministic": true,
  "providers": {
    "nous": {
      "operational": "up",
      "captured_at": "2026-09-22T07:30:00Z",
      "telemetry_source": "mixed",
      "telemetry_confidence": "medium",
      "dimensions": [
        {
          "dimension_kind": "provider_credit",
          "remaining": "3599 seconds",
          "unit": "seconds",
          "reserve": "NOT_ENFORCED",
          "effective_usable": "NOT_ENFORCED",
          "reset_renewal": "2026-09-22T09:04:05Z",
          "source": "local-observation",
          "confidence": "high"
        }
      ]
    },
    "deepseek": {
      "operational": "up",
      "captured_at": "2026-09-22T07:30:00Z",
      "telemetry_source": "provider-api",
      "telemetry_confidence": "medium",
      "dimensions": [
        {
          "dimension_kind": "monetary_balance",
          "remaining": "47.32 USD",
          "unit": "USD",
          "reserve": "NOT_ENFORCED",
          "effective_usable": "NOT_ENFORCED",
          "reset_renewal": "unknown",
          "source": "observed",
          "confidence": "medium"
        }
      ]
    },
    "codex": {
      "operational": "degraded",
      "captured_at": "2026-09-22T07:30:00Z",
      "telemetry_source": "observed-only",
      "telemetry_confidence": "low",
      "dimensions": [],
      "note": "desktop app; no programmatic telemetry"
    },
    "antigravity": {
      "operational": "up",
      "captured_at": "2026-09-22T07:30:00Z",
      "telemetry_source": "observed-only",
      "telemetry_confidence": "low",
      "dimensions": [],
      "note": "desktop app; no programmatic telemetry"
    }
  },
  "not_enforced": ["reserve", "effective_usable", "projected_exhaustion",
                   "checkpoint_handover", "protected_reserve",
                   "expected_today_demand"],
  "unknown_dimensions": "see per-provider dimensions[]; omitted = unknown"
}
```

### 6.4 Publication safety rules

- `eb publish-brief` writes to the local repo working directory only
- It does NOT commit or push — that follows existing sync discipline
  (ChiefDiscordSync scheduled task or manual `git push`)
- Before writing, it redacts any string matching known secret patterns
  (regex: `sk-*`, `Bearer `, `key=`, `token=`, `password=`)
- If redaction triggers, the write is ABORTED and an error is raised
- `latest-brief.md` is a full copy (not a symlink) for portability

---

## 7. CLI commands

All E2 commands are added to the existing `eb` CLI (same `eb.py` file,
new subcommands). Stdlib-only, consistent with E1.

| Command                | Purpose                                              |
|------------------------|------------------------------------------------------|
| `eb telemetry`         | Poll all adapters, write snapshot to governor.db     |
| `eb telemetry --prune` | Prune rows older than retention policy               |
| `eb brief`             | Generate Daily Resource Brief (no LLM)               |
| `eb brief --publish`   | Generate brief + write to local control-plane repo   |
| `eb record-request`    | Log an observed request (tokens, cost, status)       |
| `eb gov-status`        | Show governor.db status (row counts, chain head)     |
| `eb gov-verify`        | Verify governor.db integrity + chain                 |

### 7.1 eb telemetry

```
eb telemetry [--provider <id>] [--dry-run]
```

- Polls all adapters (or one if `--provider` given)
- Writes one provider_snapshot + N capacity_dimension rows
- `--dry-run` prints the snapshot without writing
- Exit code: 0 = all adapters polled, 1 = partial failure, 2 = total failure
- Logs to `exec-brain/telemetry.log` (not the DB audit log)

### 7.2 eb brief

```
eb brief [--date YYYY-MM-DD] [--no-publish] [--output <path>]
```

- Generates the Daily Resource Brief
- `--date` generates for a specific date (defaults to today)
- `--no-publish` skips writing to the control-plane repo
- `--output` writes to a file instead of stdout
- Renders with NO LLM — pure Python string formatting

### 7.3 eb record-request

```
eb record-request --provider <id> [--model <m>] [--input-tokens <n>]
                   [--output-tokens <n>] [--cost <amount>]
                   [--status success|error|timeout] [--error-code <c>]
                   [--latency-ms <n>]
```

- Records an observed API request for burn tracking
- Called by the Chief (or future E3 router) after each provider call
- Monetary cost is a STRING ("0.0023 USD" or "unknown")

### 7.4 eb gov-verify

```
eb gov-verify [--repair]
```

- Runs `PRAGMA integrity_check`
- Verifies hash chains on provider_snapshot and capacity_dimension
- Verifies gov-chain-head.json anchor
- `--repair` updates chain-head if it's a valid prefix (same as E1 audit)
- Prints verify: PASS / FAIL

---

## 8. Polling cadence

### 8.1 Scheduled polling

A Windows Scheduled Task (consistent with existing ChiefDiscordSync pattern):

- Task name: `ExecBrainTelemetry`
- Trigger: every 30 minutes, survives logon/reboot
- Action: `python %LOCALAPPDATA%\hermes\exec-brain\eb.py telemetry`
- Lock file: `exec-brain/telemetry.lock` (prevents concurrent runs)
- Log: `exec-brain/telemetry.log`
- On failure: logs error, does NOT retry (next scheduled run handles it)

### 8.2 Manual polling

`eb telemetry` can be run on demand. The lock file prevents overlap with
the scheduled task.

### 8.3 Failure handling

| Failure mode                  | Behavior                                           |
|-------------------------------|----------------------------------------------------|
| Single adapter throws         | Log error, mark provider down/unknown, continue    |
| All adapters fail             | Exit code 2, log critical, no snapshot written     |
| DB write fails                | Exit code 1, log error, snapshot lost              |
| Lock file exists              | Exit code 0 (silent — another poll is running)     |
| Stale lock (>10 min)          | Break lock, proceed, log warning                   |
| Prune during scheduled poll   | Skip prune (prune only via explicit --prune)       |

---

## 9. Secret / redaction rules

1. **DeepSeek API key** is NEVER:
   - Printed to stdout or stderr
   - Logged to telemetry.log or any other log
   - Stored in governor.db
   - Included in the Daily Resource Brief
   - Written to provider-state.md or provider-state.json
   - Committed to GitHub
   - Passed as a CLI argument (read from env or credential store by name)

2. **Key resolution order** (DeepSeek):
   a. Environment variable `DEEPSEEK_API_KEY`
   b. Windows Credential Manager target `deepseek:api`
   c. If neither → adapter returns operational=unknown with error
      "api-key-not-configured" (no crash, no partial state)

3. **Redaction in publish-brief**:
   - Before writing any file to the control-plane repo, scan for patterns:
     `sk-[a-zA-Z0-9]{20,}`, `Bearer\s+\S+`, `api[_-]?key\s*[:=]\s*\S+`,
     `token\s*[:=]\s*\S+`, `password\s*[:=]\s*\S+`
   - If any match → ABORT write, raise error, do NOT commit

4. **Nous token** (OAuth access_token in auth.json):
   - The adapter reads `expires_at` and `request_count` only
   - The token value itself is never read by the adapter
   - (The token is managed by Hermes's existing auth system, not by E2)

5. **Windows Credential Manager** (Antigravity credential):
   - The adapter checks for PRESENCE only (does not read the credential value)
   - Presence is reported as a dimension note, not the value

---

## 10. Storage paths summary

```
%LOCALAPPDATA%\hermes\exec-brain\
  eb.py                        E1 CLI (extended with E2 commands)
  exec_brain.db                E1 database (unchanged)
  chain-head.json              E1 chain anchor (unchanged)
  governor.db                  E2 telemetry ledger (NEW)
  gov-chain-head.json          E2 chain anchor (NEW)
  telemetry.log                E2 polling log (NEW)
  telemetry.lock               E2 polling lock (NEW)
  prune.log                    E2 prune audit log (NEW)
  deepseek-config.json         E2 DeepSeek budget config (NEW, no secrets)
  backups\                     E1 backups (unchanged)
  tests\
    test_eb.py                 E1 tests (unchanged)
    test_governor.py           E2 tests (NEW)
```

---

## 11. Schema versioning and forward-compatibility

### 11.1 E2 → E3 migration path

E3 adds: WorkerCapability, QualificationDecision, PerformanceRow,
CheckpointRecord, HandoverRecord. These are NEW tables in governor.db (or
exec_brain.db — TBD in E3 plan). E2's schema is forward-compatible because:
- `provider_snapshot.provider` is a stable string id
- `capacity_dimension.dimension_kind` uses the §9a enum (extensible)
- `reserve` and `effective_usable` columns exist as NOT_ENFORCED placeholders
- E3 can add a `qualification_state` column to provider_snapshot if needed

### 11.2 E2 → E4 migration path

E4 adds: enforced reserves, predictive exhaustion, checkpoint enforcement.
E4 will:
- Replace `reserve` NOT_ENFORCED with real values
- Replace `effective_usable` NOT_ENFORCED with real values
- Add exhaustion projection columns to provider_snapshot
- Add a `reserve_policy` config table

E2's schema supports this because the columns exist; E4 only changes their
content and adds enforcement logic.

### 11.3 Schema version bumps

- governor.db `schema_version` starts at 1
- Each migration increments by 1
- `eb gov-verify` checks schema_version and warns if running older code
  against newer DB

---

## 12. State timestamp discipline correction

`state/current_company_state.md` has a stale top Timestamp (19:00 UTC while
containing ~22:00 E1 rollout data). This is a control-plane hygiene issue.

Correction in E2 rollout:
- The E2 rollout decision record MUST use the actual commit/rollout timestamp
- `current_company_state.md` Timestamp MUST be updated to the time of the
  edit, not a cached earlier value
- Future rollouts: the Timestamp field is updated as the LAST step of the
  rollout, immediately before committing

This is included in the E2 rollout procedure (§14) but is not a separate
cleanup task.

---

## 13. Complete deterministic test matrix

All tests are stdlib `unittest`, no external dependencies. Run via:
`python -m unittest tests.test_governor -v`

### 13.1 Adapter unit tests (mocked)

| #  | Test                                              | Provider     |
|----|---------------------------------------------------|--------------|
| T1 | NousAdapter: reads auth.json, emits dimensions   | nous         |
| T2 | NousAdapter: ping success → operational=up        | nous         |
| T3 | NousAdapter: ping timeout → operational=down      | nous         |
| T4 | NousAdapter: missing auth.json → error, continues | nous         |
| T5 | DeepSeekAdapter: reads key from env, pings API    | deepseek     |
| T6 | DeepSeekAdapter: missing key → unknown, no crash  | deepseek     |
| T7 | DeepSeekAdapter: 429 response → throttled         | deepseek     |
| T8 | DeepSeekAdapter: spend calculated from observed   | deepseek     |
| T9 | CodexAdapter: installed+running → up              | codex        |
| T10| CodexAdapter: installed, not running → degraded   | codex        |
| T11| CodexAdapter: not installed → down                | codex        |
| T12| AntigravityAdapter: credential present → up       | antigravity  |
| T13| AntigravityAdapter: no credential → degraded      | antigravity  |

### 13.2 Ledger / DB tests

| #  | Test                                              |
|----|---------------------------------------------------|
| T14| governor.db init creates all tables + triggers    |
| T15| provider_snapshot append-only (UPDATE rejected)   |
| T16| provider_snapshot append-only (DELETE rejected)   |
| T17| capacity_dimension append-only (UPDATE rejected)  |
| T18| capacity_dimension append-only (DELETE rejected)  |
| T19| Hash chain: seq order + sha256 links valid        |
| T20| Chain-head anchor: prefix verification            |
| T21| Prune: rows deleted, prune.log written, anchor updated |

### 13.3 CLI command tests

| #  | Test                                              |
|----|---------------------------------------------------|
| T22| `eb telemetry --dry-run` prints, does not write   |
| T23| `eb telemetry` writes snapshot + dimensions       |
| T24| `eb brief` renders without LLM, contains UNKNOWN  |
| T25| `eb brief --date` renders historical brief        |
| T26| `eb record-request` writes observed_request row   |
| T27| `eb gov-verify` PASS on fresh DB                  |
| T28| `eb gov-verify` FAIL on chain break               |

### 13.4 Brief generation tests

| #  | Test                                              |
|----|---------------------------------------------------|
| T29| Brief: UNKNOWN rendered for unobservable dims     |
| T30| Brief: NOT_ENFORCED rendered for E4 fields        |
| T31| Brief: yesterday usage from observed_request      |
| T32| Brief: burn trend increasing/decreasing/stable    |

### 13.5 Publication tests

| #  | Test                                              |
|----|---------------------------------------------------|
| T33| publish-brief: writes daily-brief + latest + json |
| T34| publish-brief: redacts secret patterns, aborts    |
| T35| publish-brief: provider-state.json valid schema   |

### 13.6 Integration tests

| #  | Test                                              |
|----|---------------------------------------------------|
| T36| Full cycle: telemetry → brief → publish            |
| T37| Concurrent telemetry: lock file prevents overlap  |
| T38| Stale lock: broken after timeout, warning logged  |

**Total: 38 tests**

---

## 14. Rollout procedure

### 14.1 Pre-rollout

1. E1 is ACTIVE and verified (done — 32/32 tests, audit PASS)
2. Review and approve this E2 plan
3. Create feature branch `exec-brain/e2` from main
4. Implement E2 (NOT YET — plan only)

### 14.2 Rollout steps

1. **Merge plan** to main (this commit — plan only, no code)
2. **Implement** on `exec-brain/e2` branch:
   - Extend `eb.py` with E2 commands
   - Create `tests/test_governor.py` (38 tests)
   - Create `deepseek-config.json` template (budget only, no key)
3. **Test**: run full matrix on feature branch
4. **Update** `current_company_state.md`:
   - Fix Timestamp to actual edit time
   - Add "Executive Brain: E2 IMPLEMENTED (provider telemetry + daily brief)"
5. **Update** `decisions/exec-brain-e2-rollout.md` (new decision record)
6. **Merge** to main
7. **Enable** scheduled task `ExecBrainTelemetry` (30-min cadence)
8. **Run** `eb telemetry` manually to verify first snapshot
9. **Run** `eb brief --publish` to verify first brief + GitHub sync
10. **Verify**: `eb gov-verify` PASS, brief renders, no secrets in repo

### 14.3 Rollback procedure

If E2 causes issues:
1. Disable `ExecBrainTelemetry` scheduled task
2. Delete/rename `governor.db` (telemetry data is disposable)
3. Revert `eb.py` to E1 version (git revert)
4. Re-run E1 test matrix to confirm E1 still works (32/32)
5. Update `current_company_state.md` Timestamp + E2 status
6. Commit rollback

E1 is unaffected by E2 rollback because:
- E2 uses a separate governor.db
- E2 adds new commands but does not modify E1 commands
- E2 does not alter E1's exec_brain.db schema

---

## 15. Acceptance criteria

E2 is accepted when:

1. **38/38 tests pass** on the rev-1 test matrix
2. **`eb gov-verify` PASS** on a fresh governor.db after one poll cycle
3. **`eb brief` renders** for all four providers with:
   - UNKNOWN for all unobservable dimensions
   - NOT_ENFORCED for reserve/effective_usable/exhaustion fields
   - No synthetic "overall capacity %"
4. **`eb brief --publish`** writes three files to the control-plane repo
   with NO secrets, NO raw DB content, NO internal paths
5. **DeepSeek key** is never printed, logged, or committed (verified by
   grep of all output files + git diff)
6. **E1 regression**: `eb audit --verify` still PASS, E1 test matrix 32/32
   still green
7. **Scheduled task** `ExecBrainTelemetry` runs every 30 min, survives
   reboot, logs cleanly
8. **`current_company_state.md` Timestamp** is correct (time of edit)
9. **Chain verification**: provider_snapshot and capacity_dimension hash
   chains are valid after 7 days of polling
10. **Prune**: `eb telemetry --prune` removes rows older than retention,
    writes prune.log, updates chain-head

---

## 16. Design decisions needing owner approval

The following decisions in this plan should be confirmed by the owner
before implementation:

### D1. Separate governor.db vs. extending exec_brain.db

**Proposed**: Separate `governor.db` for telemetry (high-frequency,
independent retention). E1's `exec_brain.db` is unchanged.

**Alternative**: Add E2 tables to `exec_brain.db` (single DB, single backup).

**Tradeoff**: Separate = cleaner retention, independent pruning, no risk to
E1 data. Unified = single backup/restore story, simpler deployment.

### D2. DeepSeek key storage location

**Proposed**: Read from env var `DEEPSEEK_API_KEY` first, then Windows
Credential Manager target `deepseek:api`.

**Question**: Where is the owner's DeepSeek API key currently stored? The
plan must match the actual storage location. If it's in a different
credential store or file, the adapter's resolution order must be updated.

### D3. Codex and Antigravity — desktop apps with no API

**Proposed**: Adapters check process state + installed version only. Most
dimensions are UNKNOWN.

**Question**: Is this sufficient for E2, or should Codex/Antigravity be
deferred until a CLI/API becomes available? The architecture assumes CLIs
exist, but only desktop apps are installed. Options:
- (a) Ship "observed-only" adapters now (process check + UNKNOWN)
- (b) Defer Codex/Antigravity to a later phase when CLIs are available
- (c) Mark Codex/Antigravity as "not yet routable" in the brief

### D4. Burn trend calculation window

**Proposed**: Trailing 24h vs preceding 24h, with >20% threshold for
"increasing"/"decreasing".

**Alternative**: 7-day trailing window for smoother trends.

### D5. Retention periods

**Proposed**: snapshots 90d, requests 30d, briefs 365d.

**Question**: Acceptable, or should the owner prefer different periods?

---

## 17. Out of scope (confirmed NOT implemented in E2)

- Worker qualification / performance gating (E3)
- Central Qualification Gate (E3)
- Predictive exhaustion enforcement (E4)
- Protected reserve enforcement (E4)
- Automatic checkpoints / handover (E4)
- Safe mode / owner override UX (E5)
- Provider/model quality claims
- Automatic model selection
- Provider API routing (the actual sending of requests to providers)
- Real-time exhaustion alerts
- Reserve policy configuration UI
- Multi-model staged execution

Schema columns for these (reserve, effective_usable) exist as
NOT_ENFORCED placeholders but are not computed or enforced.

---

## 18. File plan summary

New files (local, outside repo — raw/high-frequency state stays local):

    %LOCALAPPDATA%\hermes\exec-brain\
      governor.db                created on first `eb telemetry` run
      gov-chain-head.json        created on first `eb telemetry` run
      telemetry.log              created on first `eb telemetry` run
      telemetry.lock             created during poll, removed after
      prune.log                  created on first prune
      deepseek-config.json       created by owner (budget template)
      tests\test_governor.py     38-test stdlib unittest suite

Modified files:

    %LOCALAPPDATA%\hermes\exec-brain\
      eb.py                      extended with E2 subcommands (telemetry,
                                 brief, record-request, gov-status,
                                 gov-verify, publish-brief)

New files (control-plane repo — curated summaries only):

    mukund-chief-control-plane\
      resource-status\
        daily-brief-<YYYY-MM-DD>.md    dated brief (generated)
        latest-brief.md                copy of latest (generated)
        provider-state.json            machine-readable state (generated)
      decisions\
        exec-brain-e2-rollout.md       rollout decision record (new)
      architecture-proposals\
        executive-brain-e2-implementation-plan.md  (this file)
      proposals\
        executive-brain-e2-implementation-plan.md  (unchanged review copy)

Modified files (control-plane repo):

    mukund-chief-control-plane\
      state\current_company_state.md   Timestamp fix + E2 status

---

## 19. Amendment history

- rev 1 (2026-09-22): Initial plan. Based on local reconnaissance of
  installed providers. Codex and Antigravity are desktop apps (no CLI);
  Nous and DeepSeek are API-accessible. 38-test matrix. 5 owner decisions
  identified (D1–D5).
