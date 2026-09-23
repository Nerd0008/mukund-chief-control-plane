#!/usr/bin/env python3
"""E3 Orchestration DB — schema, migrations, and versioning."""

import sqlite3

SCHEMA_VERSION = 2

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dag_node (
    node_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    task_subtask_id TEXT,
    objective TEXT NOT NULL,
    capability_roles TEXT NOT NULL,
    dependencies TEXT NOT NULL,
    inputs TEXT,
    expected_outputs TEXT,
    floor_id TEXT,
    allowed_tools TEXT,
    permissions TEXT,
    verification_method TEXT NOT NULL DEFAULT 'test',
    assigned_worker TEXT,
    fallback_candidates TEXT,
    state TEXT NOT NULL DEFAULT 'PLANNED',
    attempts INTEGER NOT NULL DEFAULT 0,
    defect_attempts TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS capability_registry (
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

CREATE TABLE IF NOT EXISTS performance_evidence (
    evidence_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    task_fingerprint TEXT NOT NULL,
    role TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    reasoning_profile TEXT,
    execution_profile TEXT,
    tools TEXT,
    first_pass_success INTEGER,
    final_success INTEGER,
    verification_outcome TEXT,
    deterministic_test_results TEXT,
    retries INTEGER NOT NULL DEFAULT 0,
    corrections INTEGER NOT NULL DEFAULT 0,
    correction_severity TEXT,
    failure_attribution TEXT,
    runtime_s INTEGER,
    usage_tokens INTEGER,
    monetary_cost REAL,
    floor_id TEXT,
    dag_node_id TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_fingerprint_index (
    fingerprint_id TEXT PRIMARY KEY,
    task_family TEXT NOT NULL,
    reasoning_depth INTEGER,
    tool_intensity TEXT,
    risk_class TEXT,
    required_roles TEXT,
    evidence_id TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS router_decision (
    decision_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    proposed_worker TEXT NOT NULL,
    proposed_role TEXT NOT NULL,
    confidence TEXT NOT NULL,
    reasoning TEXT,
    gate_decision TEXT NOT NULL,
    gate_reasons TEXT,
    actual_outcome TEXT,
    outcome_matches_proposal INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conflict_record (
    conflict_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    node_a TEXT NOT NULL,
    node_b TEXT NOT NULL,
    disputed_claim TEXT,
    resolution TEXT,
    resolved_by TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plan_version (
    plan_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    parent_plan_id TEXT,
    trigger TEXT,
    dag_nodes TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS worker_capability_event (
    event_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    task_family TEXT NOT NULL,
    capability_role TEXT NOT NULL,
    previous_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_references TEXT,
    actor TEXT NOT NULL,
    model_identity TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dag_state_event (
    event_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT NOT NULL,
    cause TEXT NOT NULL,
    dispatch_reference TEXT,
    verification_reference TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decision_rationale_event (
    rationale_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    plan_id TEXT,
    node_id TEXT,
    decision_type TEXT NOT NULL,
    decision_actor TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    model_identity TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    objective TEXT NOT NULL,
    chosen_action TEXT NOT NULL,
    alternatives_considered TEXT,
    alternative_rejections TEXT,
    decisive_factors TEXT NOT NULL,
    evidence_references TEXT,
    assumptions TEXT,
    uncertainties TEXT,
    confidence TEXT NOT NULL,
    confidence_justification TEXT NOT NULL,
    expected_tradeoffs TEXT,
    gate_result TEXT NOT NULL,
    next_verification TEXT NOT NULL,
    rationale_codes TEXT NOT NULL,
    concise_rationale TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_outcome_review (
    review_id TEXT PRIMARY KEY,
    rationale_id TEXT NOT NULL,
    plan_id TEXT,
    node_id TEXT,
    actual_outcome TEXT NOT NULL,
    first_pass_success INTEGER,
    verification_result TEXT,
    corrections_required INTEGER DEFAULT 0,
    failure_attribution TEXT,
    decision_quality TEXT NOT NULL,
    lessons TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- E4 Resource Continuity tables
CREATE TABLE IF NOT EXISTS resource_checkpoint (
    checkpoint_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resource_snapshot (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens_24h INTEGER,
    output_tokens_24h INTEGER,
    request_count_24h INTEGER,
    avg_latency_ms REAL,
    runway_hours REAL,
    status TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- E5 Safe Mode tables
CREATE TABLE IF NOT EXISTS safe_mode_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    affected_workers TEXT,
    auto_resolved BOOLEAN DEFAULT 0,
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS failure_drill_log (
    drill_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    injected_failure TEXT NOT NULL,
    detection_time_ms INTEGER,
    recovery_time_ms INTEGER,
    safe_mode_triggered BOOLEAN,
    success BOOLEAN NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS convergence_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id TEXT NOT NULL,
    task_family TEXT NOT NULL,
    failure_count INTEGER NOT NULL,
    action_taken TEXT NOT NULL,
    escalated BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dag_node_state ON dag_node(state);
CREATE INDEX IF NOT EXISTS idx_dag_node_plan ON dag_node(plan_id);
CREATE INDEX IF NOT EXISTS idx_capability_state ON capability_registry(state);
CREATE INDEX IF NOT EXISTS idx_performance_worker ON performance_evidence(worker_id, task_fingerprint);
CREATE INDEX IF NOT EXISTS idx_checkpoint_task ON resource_checkpoint(task_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_provider ON resource_snapshot(provider, model);
CREATE INDEX IF NOT EXISTS idx_safemode_severity ON safe_mode_event(severity);
CREATE INDEX IF NOT EXISTS idx_convergence_worker ON convergence_event(worker_id);
"""


def init_db(path):
    """Create and initialize the orchestration database."""
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")

    # Check current version
    try:
        row = con.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current_version = row[0] if row[0] else 0
    except Exception:
        current_version = 0

    if current_version < SCHEMA_VERSION:
        con.executescript(DDL)
        con.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,)
        )
        con.commit()

    return con
