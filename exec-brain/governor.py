#!/usr/bin/env python3
"""Executive Brain E2 — Resource Governor.

Deterministic provider telemetry adapters, normalized multidimensional
telemetry ledger, Daily Resource Brief generation, curated publication.

Stdlib-only. Part of the exec-brain package (D1: separate governor.db).
"""

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

GOV_DIR = Path(os.environ.get("EB_HOME", Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"))
GOV_DB_PATH = GOV_DIR / "governor.db"
GOV_CHAIN_HEAD_PATH = GOV_DIR / "gov-chain-head.json"
GOV_PRUNE_LOG_PATH = GOV_DIR / "prune.log"
GOV_TELEMETRY_LOG_PATH = GOV_DIR / "telemetry.log"
GOV_LOCK_PATH = GOV_DIR / "telemetry.lock"
DEEPSEEK_CONFIG_PATH = GOV_DIR / "deepseek-config.json"
SCHEMA_VERSION = 1

# Retention periods in days
RETENTION_SNAPSHOTS = 90
RETENTION_REQUESTS = 30
RETENTION_BRIEFS = 365
RETENTION_AGGREGATES = 365

# DeepSeek published pricing for cost calculation (USD per 1M tokens)
DEEPSEEK_PRICING = {
    "deepseek-chat": {"prompt": 0.27, "completion": 1.10},
    "deepseek-reasoner": {"prompt": 0.55, "completion": 2.19},
}

PROVIDERS = ["nous", "deepseek", "codex", "antigravity"]

DIMENSION_KINDS = {
    "request_window", "token_window", "daily_allowance", "weekly_allowance",
    "monthly_allowance", "monetary_balance", "concurrency", "rate_limit",
    "provider_credit"
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def short_id():
    return uuid.uuid4().hex[:8]


def connect_gov(path=None):
    p = Path(path) if path else GOV_DB_PATH
    if not p.exists():
        raise SystemExit(f"governor: database not found at {p} (run: eb telemetry --init)")
    con = sqlite3.connect(str(p), timeout=5)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


DDL = """
CREATE TABLE IF NOT EXISTS provider_snapshot (
  snapshot_id    TEXT PRIMARY KEY,
  provider       TEXT NOT NULL,
  captured_at    TEXT NOT NULL,
  operational    TEXT NOT NULL,
  routable       INTEGER NOT NULL DEFAULT 0,
  rate_limit_state TEXT NOT NULL,
  last_success_at TEXT,
  telemetry_source TEXT NOT NULL,
  telemetry_confidence TEXT NOT NULL,
  quota_semantics TEXT NOT NULL,
  available_models TEXT NOT NULL DEFAULT '[]',
  errors TEXT NOT NULL DEFAULT '[]',
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
  aggregate_id   TEXT PRIMARY KEY,
  provider       TEXT NOT NULL,
  aggregate_date TEXT NOT NULL,
  request_count  INTEGER NOT NULL DEFAULT 0,
  total_input_tokens INTEGER NOT NULL DEFAULT 0,
  total_output_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens   INTEGER NOT NULL DEFAULT 0,
  total_spend_usd TEXT NOT NULL DEFAULT '0.00',
  error_count    INTEGER NOT NULL DEFAULT 0,
  schema_version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(provider, aggregate_date)
);

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
"""


def init_db(path=None):
    """Create governor.db with schema."""
    p = Path(path) if path else GOV_DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return str(p)
    con = sqlite3.connect(str(p))
    # Use executescript for proper multi-statement DDL handling
    con.executescript(DDL)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.commit()
    con.close()
    return str(p)


# ─── Chain-head helpers ────────────────────────────────────────────

def update_chain_head(con, table, seq, record_sha256):
    """Update chain-head anchor for a table."""
    heads = {}
    if GOV_CHAIN_HEAD_PATH.exists():
        try:
            heads = json.loads(GOV_CHAIN_HEAD_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            heads = {}
    heads[table] = [seq, record_sha256]
    GOV_CHAIN_HEAD_PATH.write_text(json.dumps(heads, indent=1), encoding="utf-8")


def get_chain_head(table):
    """Get chain-head for a table."""
    if not GOV_CHAIN_HEAD_PATH.exists():
        return None
    try:
        heads = json.loads(GOV_CHAIN_HEAD_PATH.read_text(encoding="utf-8"))
        return heads.get(table)
    except (json.JSONDecodeError, IOError):
        return None


# ─── Snapshot writing ──────────────────────────────────────────────

def write_snapshot(con, snapshot):
    """Write a provider snapshot and its dimensions to governor.db."""
    cur = con.execute("SELECT COALESCE(MAX(seq),0) FROM provider_snapshot")
    seq = cur.fetchone()[0] + 1

    prev_row = con.execute(
        "SELECT record_sha256 FROM provider_snapshot ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    prev_sha = prev_row[0] if prev_row else None

    snapshot_id = f"gov-{datetime.now(timezone.utc):%Y%m%d}-{short_id()}"

    # Canonical fields for hashing
    canon = json.dumps({
        "snapshot_id": snapshot_id,
        "provider": snapshot["provider"],
        "captured_at": snapshot["captured_at"],
        "operational": snapshot["operational"],
        "routable": snapshot.get("routable", False),
        "rate_limit_state": snapshot["rate_limit_state"],
        "last_success_at": snapshot.get("last_success_at"),
        "telemetry_source": snapshot["telemetry_source"],
        "telemetry_confidence": snapshot["telemetry_confidence"],
        "quota_semantics": snapshot["quota_semantics"],
        "available_models": snapshot.get("available_models", []),
        "errors": snapshot.get("errors", []),
        "seq": seq,
    }, sort_keys=True, ensure_ascii=False)
    record_sha = sha256(canon)

    con.execute(
        "INSERT INTO provider_snapshot (snapshot_id,provider,captured_at,operational,"
        "routable,rate_limit_state,last_success_at,telemetry_source,telemetry_confidence,"
        "quota_semantics,available_models,errors,seq,record_sha256,prev_sha256,schema_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (snapshot_id, snapshot["provider"], snapshot["captured_at"],
         snapshot["operational"], 1 if snapshot.get("routable") else 0,
         snapshot["rate_limit_state"], snapshot.get("last_success_at"),
         snapshot["telemetry_source"], snapshot["telemetry_confidence"],
         snapshot["quota_semantics"],
         json.dumps(snapshot.get("available_models", [])),
         json.dumps(snapshot.get("errors", [])),
         seq, record_sha, prev_sha, SCHEMA_VERSION)
    )

    # Write dimensions
    for dim in snapshot.get("dimensions", []):
        dim_id = f"cd-{short_id()}"
        con.execute(
            "INSERT INTO capacity_dimension (dimension_id,snapshot_id,provider,"
            "dimension_kind,remaining,unit,reserve,effective_usable,reset_renewal,"
            "source,confidence,schema_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (dim_id, snapshot_id, snapshot["provider"],
             dim["dimension_kind"], dim["remaining"], dim["unit"],
             dim.get("reserve", "NOT_ENFORCED"),
             dim.get("effective_usable", "NOT_ENFORCED"),
             dim["reset_renewal"], dim["source"], dim["confidence"],
             SCHEMA_VERSION)
        )

    con.commit()
    update_chain_head(con, "provider_snapshot", seq, record_sha)
    return snapshot_id


# ─── Observed requests ─────────────────────────────────────────────

def record_request(con, provider, model=None, input_tokens=None,
                   output_tokens=None, monetary_cost=None, status="success",
                   error_code=None, latency_ms=None):
    """Record an observed API request."""
    request_id = f"obs-{datetime.now(timezone.utc):%Y%m%d}-{short_id()}"
    total = (input_tokens or 0) + (output_tokens or 0)
    con.execute(
        "INSERT INTO observed_request (request_id,provider,model,requested_at,"
        "input_tokens,output_tokens,total_tokens,monetary_cost,status,"
        "error_code,latency_ms,schema_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (request_id, provider, model, now(),
         input_tokens, output_tokens, total,
         monetary_cost or "unknown", status, error_code, latency_ms,
         SCHEMA_VERSION)
    )
    con.commit()
    return request_id


# ─── Daily aggregate ───────────────────────────────────────────────

def aggregate_day(con, date_str):
    """Aggregate observed_request rows for a given date into daily_aggregate."""
    start = f"{date_str}T00:00:00+00:00"
    end = f"{date_str}T23:59:59+00:00"
    rows = con.execute(
        "SELECT provider, COUNT(*), COALESCE(SUM(input_tokens),0), "
        "COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0), "
        "SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) "
        "FROM observed_request WHERE requested_at BETWEEN ? AND ? "
        "GROUP BY provider",
        (start, end)
    ).fetchall()

    for row in rows:
        provider, req_count, in_tokens, out_tokens, total_tokens, errors = row
        # Calculate spend from monetary_cost field
        spend_rows = con.execute(
            "SELECT monetary_cost FROM observed_request "
            "WHERE provider=? AND requested_at BETWEEN ? AND ? AND status='success'",
            (provider, start, end)
        ).fetchall()
        total_spend = 0.0
        for sr in spend_rows:
            try:
                cost_str = sr[0] if sr[0] != "unknown" else "0.00"
                # Parse "0.0023 USD" format
                total_spend += float(cost_str.replace(" USD", ""))
            except (ValueError, AttributeError):
                pass

        agg_id = f"da-{date_str}-{provider}"
        con.execute(
            "INSERT OR REPLACE INTO daily_aggregate "
            "(aggregate_id,provider,aggregate_date,request_count,"
            "total_input_tokens,total_output_tokens,total_tokens,"
            "total_spend_usd,error_count,schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (agg_id, provider, date_str, req_count, in_tokens, out_tokens,
             total_tokens, f"{total_spend:.4f}", errors, SCHEMA_VERSION)
        )
    con.commit()


# ─── Pruning ───────────────────────────────────────────────────────

def prune(con):
    """Delete rows older than retention periods."""
    now_ts = datetime.now(timezone.utc)
    results = {}

    thresholds = [
        ("provider_snapshot", RETENTION_SNAPSHOTS),
        ("capacity_dimension", RETENTION_SNAPSHOTS),
        ("observed_request", RETENTION_REQUESTS),
        ("daily_brief_log", RETENTION_BRIEFS),
        ("daily_aggregate", RETENTION_AGGREGATES),
    ]

    for table, days in thresholds:
        cutoff = (now_ts - timedelta(days=days)).isoformat(timespec="seconds")
        if table == "capacity_dimension":
            # Use snapshot_id to determine age via join
            cur = con.execute(
                f"DELETE FROM {table} WHERE snapshot_id IN "
                f"(SELECT snapshot_id FROM provider_snapshot WHERE captured_at < ?)",
                (cutoff,)
            )
        elif table == "observed_request":
            cur = con.execute(f"DELETE FROM {table} WHERE requested_at < ?", (cutoff,))
        elif table == "daily_aggregate":
            cutoff_date = (now_ts - timedelta(days=days)).strftime("%Y-%m-%d")
            cur = con.execute(f"DELETE FROM {table} WHERE aggregate_date < ?", (cutoff_date,))
        elif table == "daily_brief_log":
            cur = con.execute(f"DELETE FROM {table} WHERE generated_at < ?", (cutoff,))
        else:
            cur = con.execute(f"DELETE FROM {table} WHERE captured_at < ?", (cutoff,))
        results[table] = cur.rowcount

    # Log prune event
    with open(GOV_PRUNE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{now()} prune: {json.dumps(results)}\n")

    # Update chain head to new tail (only provider_snapshot is hash-chained)
    row = con.execute(
        "SELECT seq, record_sha256 FROM provider_snapshot ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row:
        update_chain_head(con, "provider_snapshot", row[0], row[1])

    con.commit()
    return results


# ─── Verification ──────────────────────────────────────────────────

def verify_db(con):
    """Verify governor.db integrity and chain. Returns (ok: bool, issues: list)."""
    issues = []

    # Integrity check
    ic = con.execute("PRAGMA integrity_check").fetchone()[0]
    if ic != "ok":
        issues.append(f"integrity_check: {ic}")
        return False, issues

    # Verify chains (only provider_snapshot has seq/record_sha256/prev_sha256)
    table = "provider_snapshot"
    prev = None
    try:
        for row in con.execute(f"SELECT seq, record_sha256, prev_sha256 FROM {table} ORDER BY seq"):
            if row[2] != prev:
                issues.append(f"{table}: chain break at seq={row[0]}")
            prev = row[1]
    except sqlite3.OperationalError:
        issues.append(f"{table}: chain verification failed")

    # Verify chain-head anchor (only provider_snapshot has hash chain anchor)
    anchor = get_chain_head("provider_snapshot")
    if anchor:
        row = con.execute(
            "SELECT record_sha256 FROM provider_snapshot WHERE seq=?", (anchor[0],)
        ).fetchone()
        if not row or row[0] != anchor[1]:
            issues.append("provider_snapshot: head anchor MISMATCH")

    return len(issues) == 0, issues


# ─── Brief generation ──────────────────────────────────────────────

def get_latest_snapshots(con):
    """Get most recent snapshot per provider."""
    rows = con.execute(
        "SELECT ps.* FROM provider_snapshot ps "
        "INNER JOIN (SELECT provider, MAX(seq) as max_seq FROM provider_snapshot "
        "GROUP BY provider) latest ON ps.provider = latest.provider "
        "AND ps.seq = latest.max_seq ORDER BY ps.provider"
    ).fetchall()
    columns = ["snapshot_id", "provider", "captured_at", "operational", "routable",
               "rate_limit_state", "last_success_at", "telemetry_source",
               "telemetry_confidence", "quota_semantics", "available_models",
               "errors", "seq", "record_sha256", "prev_sha256", "schema_version"]
    return [dict(zip(columns, r)) for r in rows]


def get_dimensions_for_snapshot(con, snapshot_id):
    """Get dimensions for a snapshot."""
    rows = con.execute(
        "SELECT dimension_kind, remaining, unit, reserve, effective_usable, "
        "reset_renewal, source, confidence FROM capacity_dimension "
        "WHERE snapshot_id=? ORDER BY dimension_kind", (snapshot_id,)
    ).fetchall()
    return [
        {
            "dimension_kind": r[0], "remaining": r[1], "unit": r[2],
            "reserve": r[3], "effective_usable": r[4], "reset_renewal": r[5],
            "source": r[6], "confidence": r[7]
        }
        for r in rows
    ]


def get_yesterday_aggregates(con, date_str=None):
    """Get yesterday's aggregate data."""
    if not date_str:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")
    rows = con.execute(
        "SELECT provider, request_count, total_input_tokens, total_output_tokens, "
        "total_tokens, total_spend_usd, error_count FROM daily_aggregate "
        "WHERE aggregate_date=? ORDER BY provider", (date_str,)
    ).fetchall()
    return [
        {
            "provider": r[0], "request_count": r[1], "total_input_tokens": r[2],
            "total_output_tokens": r[3], "total_tokens": r[4],
            "total_spend_usd": r[5], "error_count": r[6]
        }
        for r in rows
    ]


def compute_burn_trend(con, provider):
    """Compute burn trend for a provider (D4: 24h vs 24h, ±20%)."""
    now_ts = datetime.now(timezone.utc)
    trailing_start = (now_ts - timedelta(hours=24)).isoformat(timespec="seconds")
    preceding_start = (now_ts - timedelta(hours=48)).isoformat(timespec="seconds")

    trailing = con.execute(
        "SELECT COUNT(*) FROM observed_request WHERE provider=? AND requested_at >= ?",
        (provider, trailing_start)
    ).fetchone()[0]

    preceding = con.execute(
        "SELECT COUNT(*) FROM observed_request WHERE provider=? AND requested_at >= ? AND requested_at < ?",
        (provider, preceding_start, trailing_start)
    ).fetchone()[0]

    if trailing == 0 and preceding == 0:
        return "stable"
    if preceding == 0 and trailing > 0:
        return "rising"
    if preceding > 0:
        if trailing > preceding * 1.2:
            return "rising"
        if trailing < preceding * 0.8:
            return "falling"
    return "stable"


def generate_brief(con, date_str=None):
    """Generate the Daily Resource Brief (deterministic, no LLM)."""
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    generated_at = now()
    snapshots = get_latest_snapshots(con)
    yesterday_aggs = {a["provider"]: a for a in get_yesterday_aggregates(con, date_str)}

    lines = []
    lines.append("=" * 80)
    lines.append(f"  DAILY RESOURCE BRIEF — {date_str} {generated_at[11:16]} UTC")
    lines.append(f"  Executive Brain E2 — DETERMINISTIC (no LLM)")
    lines.append("=" * 80)
    lines.append("")

    routable_providers = []
    operational_counts = {"up": 0, "down": 0, "unknown": 0, "degraded": 0}
    most_constrained = None
    highest_confidence_routable = None

    for snap in snapshots:
        provider = snap["provider"]
        operational = snap["operational"]
        routable = bool(snap["routable"])
        operational_counts[operational] = operational_counts.get(operational, 0) + 1

        if routable:
            routable_providers.append(provider)
            if highest_confidence_routable is None:
                highest_confidence_routable = (provider, snap["telemetry_confidence"])

        lines.append(f"PROVIDER: {provider}    [{operational}]    [routable: {'yes' if routable else 'no'}]")
        lines.append(f"  Telemetry source: {snap['telemetry_source']}  Confidence: {snap['telemetry_confidence']}")
        lines.append(f"  Last success: {snap['last_success_at'] or 'never'}")
        lines.append("")

        # Dimensions
        dims = get_dimensions_for_snapshot(con, snap["snapshot_id"])
        lines.append("  Dimensions:")
        if dims:
            for dim in dims:
                lines.append(f"    {dim['dimension_kind']}: {dim['remaining']} {dim['unit']}")
                lines.append(f"      reserve: {dim['reserve']} | effective_usable: {dim['effective_usable']}")
                lines.append(f"      reset/renewal: {dim['reset_renewal']}")
                lines.append(f"      source: {dim['source']}  confidence: {dim['confidence']}")
        else:
            lines.append("    (none observed — all capacity dimensions UNKNOWN)")
        lines.append("")

        # Yesterday
        agg = yesterday_aggs.get(provider, None)
        lines.append("  Yesterday:")
        if agg:
            spend_str = f"{agg['total_spend_usd']} USD" if agg['total_spend_usd'] != '0.0000' else "unknown"
            lines.append(f"    Requests observed: {agg['request_count']}")
            lines.append(f"    Tokens (in/out/total): {agg['total_input_tokens']}/{agg['total_output_tokens']}/{agg['total_tokens']}")
            lines.append(f"    Calculated spend: {spend_str}")
        else:
            lines.append("    No observed requests in the preceding 24h window.")

        # Burn trend
        trend = compute_burn_trend(con, provider)
        lines.append(f"    Burn trend: {trend}")
        lines.append("")

        # Quota semantics
        lines.append(f"  Quota semantics: {snap['quota_semantics']}")
        lines.append(f"  Reset/renewal: unknown")
        lines.append("")
        lines.append("  ---")
        lines.append("")

    # Summary
    lines.append("=" * 80)
    lines.append("  SUMMARY")
    lines.append("=" * 80)
    total = len(snapshots) if snapshots else 1
    lines.append(f"  Providers up:     {operational_counts.get('up', 0)}/{total}")
    lines.append(f"  Providers unknown: {operational_counts.get('unknown', 0)}/{total}")
    lines.append(f"  Providers down:   {operational_counts.get('down', 0)}/{total}")
    lines.append(f"  Providers degraded: {operational_counts.get('degraded', 0)}/{total}")
    lines.append(f"  Routable:         {', '.join(routable_providers) if routable_providers else 'none'}")
    lines.append("")
    if highest_confidence_routable:
        lines.append(f"  Highest-confidence routable: {highest_confidence_routable[0]} ({highest_confidence_routable[1]})")
    lines.append("")
    lines.append("  NOT_ENFORCED (E4): reserve, effective_usable, projected_exhaustion,")
    lines.append("                     checkpoint_handover, protected_reserve,")
    lines.append("                     expected_today_demand")
    lines.append("  UNKNOWN: all dimensions not explicitly listed above")
    lines.append("")
    lines.append(f"  Generated by: eb brief (deterministic)")
    lines.append(f"  Ledger: governor.db  Schema: {SCHEMA_VERSION}")
    lines.append("=" * 80)

    brief_text = "\n".join(lines)

    # Store in daily_brief_log
    brief_id = f"brief-{date_str}"
    con.execute(
        "INSERT OR REPLACE INTO daily_brief_log (brief_id,generated_at,rendered_text,"
        "published_to_github,schema_version) VALUES (?,?,?,?,?)",
        (brief_id, generated_at, brief_text, 0, SCHEMA_VERSION)
    )
    con.commit()

    return brief_text


# ─── Publication ───────────────────────────────────────────────────

SECRET_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),
    re.compile(r'Bearer\s+\S+', re.IGNORECASE),
    re.compile(r'api[_-]?key\s*[:=]\s*\S+', re.IGNORECASE),
    re.compile(r'token\s*[:=]\s*\S+', re.IGNORECASE),
    re.compile(r'password\s*[:=]\s*\S+', re.IGNORECASE),
]


def check_secrets(text):
    """Check text for secret patterns. Returns list of matches."""
    matches = []
    for pattern in SECRET_PATTERNS:
        found = pattern.findall(text)
        matches.extend(found)
    return matches


def generate_provider_state_json(con):
    """Generate provider-state.json content."""
    snapshots = get_latest_snapshots(con)
    providers = {}
    for snap in snapshots:
        dims = get_dimensions_for_snapshot(con, snap["snapshot_id"])
        providers[snap["provider"]] = {
            "operational": snap["operational"],
            "routable": bool(snap["routable"]),
            "captured_at": snap["captured_at"],
            "telemetry_source": snap["telemetry_source"],
            "telemetry_confidence": snap["telemetry_confidence"],
            "dimensions": dims,
            "quota_semantics": snap["quota_semantics"],
            "available_models": json.loads(snap["available_models"]) if snap["available_models"] else [],
            "errors": json.loads(snap["errors"]) if snap["errors"] else []
        }

    state = {
        "generated_at": now(),
        "schema_version": SCHEMA_VERSION,
        "deterministic": True,
        "providers": providers,
        "not_enforced": ["reserve", "effective_usable", "projected_exhaustion",
                        "checkpoint_handover", "protected_reserve",
                        "expected_today_demand"],
        "unknown_dimensions": "see per-provider dimensions[]; omitted = unknown"
    }
    return json.dumps(state, indent=2, ensure_ascii=False)


def publish_brief(con, repo_dir):
    """Write brief and provider-state to local control-plane repo."""
    from pathlib import Path
    repo_path = Path(repo_dir)
    if not repo_path.exists():
        raise SystemExit(f"publish-brief: repo dir not found: {repo_path}")

    resource_status_dir = repo_path / "resource-status"
    resource_status_dir.mkdir(exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Generate brief
    brief_text = generate_brief(con, date_str)

    # Check for secrets
    secrets_found = check_secrets(brief_text)
    if secrets_found:
        raise SystemExit(f"publish-brief: SECRETS DETECTED — aborting write")

    # Write dated brief
    dated_path = resource_status_dir / f"daily-brief-{date_str}.md"
    dated_path.write_text(brief_text, encoding="utf-8")

    # Write latest
    latest_path = resource_status_dir / "latest-brief.md"
    latest_path.write_text(brief_text, encoding="utf-8")

    # Generate and write provider-state.json
    state_json = generate_provider_state_json(con)
    state_secrets = check_secrets(state_json)
    if state_secrets:
        raise SystemExit(f"publish-brief: SECRETS in state JSON — aborting write")

    state_path = resource_status_dir / "provider-state.json"
    state_path.write_text(state_json, encoding="utf-8")

    # Note: daily_brief_log is append-only, so we don't update it
    # The brief was already logged when generated

    return {
        "dated_brief": str(dated_path),
        "latest_brief": str(latest_path),
        "provider_state": str(state_path)
    }
