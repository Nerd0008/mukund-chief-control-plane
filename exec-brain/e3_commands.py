#!/usr/bin/env python3
"""E3 CLI Commands — Stage 1 shadow operations."""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Support both package import (eb.py dispatch) and direct script execution
try:
    from .orchestration_db import init_db
    from .capability_registry import CapabilityRegistry, CAPABILITY_ROLES, WORKER_STATES
    from .worker_registry import WorkerRegistry
    from .task_fingerprint import TaskFingerprint, compute_similarity
    from .decision_rationale import DecisionRationale, DecisionOutcomeReview, DECISION_TYPES, CONFIDENCE_LEVELS, GATE_RESULTS
    from .execution_dag import ExecutionDAG, DAGNode, NODE_STATES
    from .worker_contract import WorkerContract
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from orchestration_db import init_db
    from capability_registry import CapabilityRegistry, CAPABILITY_ROLES, WORKER_STATES
    from worker_registry import WorkerRegistry
    from task_fingerprint import TaskFingerprint, compute_similarity
    from decision_rationale import DecisionRationale, DecisionOutcomeReview, DECISION_TYPES, CONFIDENCE_LEVELS, GATE_RESULTS
    from execution_dag import ExecutionDAG, DAGNode, NODE_STATES
    from worker_contract import WorkerContract


# ─── persisted failure attribution (operator surface) ───────────────
#
# The production execution leg persists a node's terminal failure entirely
# through the existing schema-v2 columns. These helpers only read that state
# back for the operator; they never write, infer or fabricate an attribution.
#
#   * ``dag_node.state``                   → the terminal node state (BLOCKED/FAILED)
#   * ``dag_state_event.cause``            → the transition cause, e.g.
#         ``provider_content_stop_unrecovered:IMAGE_RECITATION``
#         ``content_stop_same_request_retry_1_after_IMAGE_RECITATION``
#   * ``performance_evidence.failure_attribution`` → e.g. ``provider_content_stop``
#   * ``performance_evidence.deterministic_test_results`` → the bounded retry
#         accounting (``content_stop_retries``, ``content_stop_stops``,
#         ``content_stop_finish_reasons``)

CONTENT_STOP_UNRECOVERED_CAUSE = "provider_content_stop_unrecovered"
CONTENT_STOP_RETRY_CAUSE = "content_stop_same_request_retry"
FAILURE_ATTRIBUTION_PROVIDER_CONTENT_STOP = "provider_content_stop"

# Node states reported as terminal failures by the attribution surface.
TERMINAL_FAILURE_STATES = ("BLOCKED", "FAILED")

# Cap on the number of attributed nodes printed by ``e3-status`` (a store can
# hold many historical nodes; the total count is still reported).
MAX_STATUS_ATTRIBUTION_NODES = 20


def finish_reason_from_cause(cause):
    """The provider finishReason named in a content-stop cause, else ``None``.

    Only values the execution leg actually persisted are returned; an
    unrecognised cause yields ``None`` rather than a guess.
    """
    if not isinstance(cause, str) or not cause:
        return None
    if cause.startswith(CONTENT_STOP_UNRECOVERED_CAUSE + ":"):
        return cause.split(":", 1)[1] or None
    if cause.startswith(CONTENT_STOP_RETRY_CAUSE):
        marker = "_after_"
        idx = cause.find(marker)
        if idx == -1:
            return None
        return cause[idx + len(marker):] or None
    return None


def _deterministic_results(raw):
    """Parse the evidence row's structured results, tolerating absence."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def node_failure_view(con, node_id):
    """Persisted failure/terminal attribution for one DAG node, or ``None``.

    ``None`` means the node is not in this store at all. Every other field is
    read verbatim from the store; a value the execution leg never persisted is
    reported as ``None`` (rendered as "none recorded"), never inferred.
    """
    node = con.execute(
        "SELECT node_id, plan_id, state, assigned_worker, objective "
        "FROM dag_node WHERE node_id=?", (node_id,)).fetchone()
    if node is None:
        return None
    events = con.execute(
        "SELECT previous_state, new_state, cause FROM dag_state_event "
        "WHERE node_id=? ORDER BY rowid", (node_id,)).fetchall()
    evidence = con.execute(
        "SELECT evidence_id, failure_attribution, verification_outcome, retries, "
        "corrections, final_success, deterministic_test_results "
        "FROM performance_evidence WHERE dag_node_id=? ORDER BY timestamp",
        (node_id,)).fetchall()

    attribution = None
    verification_outcome = None
    retries = None
    stops = None
    finish_reasons = []
    for row in evidence:
        if not attribution and row["failure_attribution"]:
            attribution = row["failure_attribution"]
        if verification_outcome is None and row["verification_outcome"]:
            verification_outcome = row["verification_outcome"]
        det = _deterministic_results(row["deterministic_test_results"])
        for reason in det.get("content_stop_finish_reasons") or []:
            if reason and reason not in finish_reasons:
                finish_reasons.append(reason)
        if retries is None and det.get("content_stop_retries") is not None:
            retries = det["content_stop_retries"]
        if stops is None and det.get("content_stop_stops") is not None:
            stops = det["content_stop_stops"]

    state = node["state"]
    terminal_cause = None
    if state in TERMINAL_FAILURE_STATES and events:
        terminal_cause = events[-1]["cause"]
    # A content-stop cause is recorded on the retry (REWORK) events as well as
    # on the terminal BLOCKED event, so scan all of them; the terminal cause
    # wins for reporting when present.
    cause_reason = None
    for event in events:
        reason = finish_reason_from_cause(event["cause"])
        if reason:
            cause_reason = reason
    if cause_reason and cause_reason not in finish_reasons:
        finish_reasons.append(cause_reason)

    return {
        "node_id": node["node_id"],
        "plan_id": node["plan_id"],
        "state": state,
        "assigned_worker": node["assigned_worker"],
        "objective": node["objective"],
        "failure_attribution": attribution,
        "verification_outcome": verification_outcome,
        "provider_finish_reason": finish_reasons[0] if finish_reasons else None,
        "provider_finish_reasons": finish_reasons,
        "content_stop_retries": retries,
        "content_stop_stops": stops,
        "terminal_cause": terminal_cause,
        # Derived, for filtering only: a content-stop cause/attribution was
        # persisted. The verbatim values above are the evidence.
        "content_stop": bool(finish_reasons) or (
            attribution == FAILURE_ATTRIBUTION_PROVIDER_CONTENT_STOP),
    }


def _print_failure_view(view):
    """Render one :func:`node_failure_view` record for the operator."""
    print(f"  Node: {view['node_id']}  (plan {view['plan_id']})")
    print(f"    State: {view['state']}")
    print(f"    Assigned worker: {view['assigned_worker']}")
    print(f"    Failure attribution: "
          f"{view['failure_attribution'] or 'none recorded'}")
    print(f"    Provider finish reason: "
          f"{view['provider_finish_reason'] or 'none recorded'}")
    print(f"    Verification outcome: "
          f"{view['verification_outcome'] or 'none recorded'}")
    if view["content_stop_retries"] is not None:
        print(f"    Content-stop retries used: {view['content_stop_retries']} "
              f"(stops recorded: {view['content_stop_stops']})")
    if len(view["provider_finish_reasons"]) > 1:
        print("    Provider finish reasons recorded: "
              + ", ".join(view["provider_finish_reasons"]))
    if view["terminal_cause"]:
        print(f"    Terminal transition cause: {view['terminal_cause']}")


class E3Commands:
    """E3 command implementations."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.con = None
        self.registry = None
        self.workers = None

    def _connect(self):
        """Connect to orchestration.db."""
        if self.con is None:
            self.con = sqlite3.connect(str(self.db_path))
            self.con.row_factory = sqlite3.Row
        return self.con

    def _get_registry(self):
        """Get capability registry."""
        if self.registry is None:
            self.registry = CapabilityRegistry(self._connect())
        return self.registry

    def _get_workers(self):
        """Get worker registry."""
        if self.workers is None:
            self.workers = WorkerRegistry()
        return self.workers

    def init(self, args):
        """Initialize orchestration.db."""
        self._connect()
        init_db(self.db_path)
        try:
            row = self.con.execute("SELECT MAX(version) FROM schema_version").fetchone()
            version = row[0] if row and row[0] is not None else "unknown"
        except Exception:
            version = "unknown"
        print(f"E3 orchestration.db initialized at {self.db_path}")
        print(f"Schema version: {version}")
        print("Tables: dag_node, capability_registry, performance_evidence,")
        print("        task_fingerprint_index, router_decision, conflict_record,")
        print("        plan_version, worker_capability_event, dag_state_event,")
        print("        decision_rationale_event, decision_outcome_review")

    def register_workers(self, args):
        """Register the 10-worker pool."""
        con = self._connect()
        registry = self._get_registry()
        workers = self._get_workers()

        registered = 0
        for wid, w in workers.get_all_workers().items():
            registry.register_worker(
                wid, w['provider'], w['model'],
                roles=[],  # No qualifications fabricated
                state='UNPROVEN'
            )
            registered += 1

        print(f"Registered {registered} workers from roster")
        print("All workers start as UNPROVEN (LOCKED = included, not QUALIFIED)")

    def status(self, args):
        """Show E3 status."""
        con = self._connect()
        workers = self._get_workers()
        registry = self._get_registry()

        print("=== E3 Orchestration Status ===")
        print(f"Database: {self.db_path}")
        print()

        # Schema version — MAX(version) is the applied schema level; an
        # unordered SELECT returns the oldest migration row and understates it.
        try:
            row = con.execute("SELECT MAX(version) FROM schema_version").fetchone()
            print(f"Schema version: {row[0] if row and row[0] is not None else 'unknown'}")
        except Exception:
            print("Schema version: not initialized")

        # Worker pool
        print("\n--- Worker Pool ---")
        pool = workers.get_pool_summary()
        for status, wids in pool.items():
            print(f"  {status}: {len(wids)} workers")
            for wid in wids:
                w = workers.get_worker(wid)
                routable = "routable" if w.get('routable') else "NOT routable"
                print(f"    - {wid} ({w['provider']}/{w['model']}) [{routable}]")

        # Capability registry
        print("\n--- Capability Registry ---")
        try:
            rows = con.execute(
                "SELECT capability_role, state, COUNT(*) FROM capability_registry "
                "GROUP BY capability_role, state"
            ).fetchall()
            for row in rows:
                print(f"  {row[0]}: {row[1]} ({row[2]})")
        except Exception:
            print("  (empty)")

        # DAG nodes
        print("\n--- DAG Nodes ---")
        try:
            rows = con.execute(
                "SELECT state, COUNT(*) FROM dag_node GROUP BY state"
            ).fetchall()
            for row in rows:
                print(f"  {row[0]}: {row[1]}")
        except Exception:
            print("  (empty)")

        # Persisted terminal failure attribution (e.g. a provider content-side
        # stop). Read back from the existing store; nothing new is written.
        print("\n--- Node Failure Attribution ---")
        try:
            node_ids = [r[0] for r in con.execute(
                "SELECT node_id FROM dag_node WHERE state IN ('BLOCKED','FAILED') "
                "UNION "
                "SELECT dag_node_id FROM performance_evidence "
                "WHERE failure_attribution IS NOT NULL "
                "AND dag_node_id IS NOT NULL "
                "ORDER BY node_id").fetchall()]
        except Exception:
            node_ids = []
        shown = 0
        for node_id in node_ids[:MAX_STATUS_ATTRIBUTION_NODES]:
            view = node_failure_view(con, node_id)
            if view and (view["failure_attribution"] or view["content_stop"]
                         or view["state"] in TERMINAL_FAILURE_STATES):
                _print_failure_view(view)
                shown += 1
        if not node_ids or shown == 0:
            print("  (none)")
        elif len(node_ids) > MAX_STATUS_ATTRIBUTION_NODES:
            print(f"  ... {len(node_ids) - MAX_STATUS_ATTRIBUTION_NODES} more")

    def plan(self, args):
        """Plan a task (shadow only)."""
        con = self._connect()
        workers = self._get_workers()
        registry = self._get_registry()

        # Parse task from args
        task_text = getattr(args, 'task', None) or "Example task"
        task_family = getattr(args, 'family', 'other')
        reasoning_depth = int(getattr(args, 'reasoning', 2))
        risk_class = getattr(args, 'risk', 'R1')

        print(f"=== E3 Task Planning (SHADOW) ===")
        print(f"Task: {task_text}")
        print(f"Family: {task_family}, Reasoning: {reasoning_depth}, Risk: {risk_class}")
        print()

        # Create fingerprint
        fp = TaskFingerprint(
            task_family=task_family,
            reasoning_depth=reasoning_depth,
            risk_class=risk_class,
            required_roles=['builder']
        )
        print(f"Task fingerprint: {fp.compute_hash()[:16]}...")

        # Determine if decomposition is needed
        should_decompose = reasoning_depth >= 2 and len(fp.required_roles) > 1
        print(f"\nDecomposition recommended: {should_decompose}")

        if should_decompose:
            print("\nProposed decomposition:")
            print("  1. Research/Analysis (reasoning_depth=2)")
            print("  2. Implementation (reasoning_depth=1)")
            print("  3. Verification (reasoning_depth=1)")
        else:
            print("\nSingle-node execution recommended")

        # Find candidate workers
        print("\n--- Candidate Workers ---")
        routable = workers.get_routable_workers()
        for wid, w in routable.items():
            cap = registry.get_capability(wid, task_family, 'builder')
            print(f"  {wid}: {cap['state']} (evidence: {cap['evidence_count']})")

        # Generate decision rationale
        rationale = DecisionRationale(
            task_id=f"task-{fp.compute_hash()[:8]}",
            decision_type='decomposition',
            decision_actor='e3-planner',
            objective=f"Plan task: {task_text}",
            chosen_action="decompose" if should_decompose else "single-node",
            provider='internal',
            model='e3-planner'
        )
        rationale.concise_rationale = (
            f"Task complexity ({reasoning_depth}) and roles ({fp.required_roles}) "
            f"{'warrant decomposition' if should_decompose else 'allow single-node execution'}"
        )
        rationale.confidence = 'MEDIUM'
        rationale.gate_result = 'ACCEPT'
        rationale.next_verification = 'shadow-review'

        print(f"\n--- Decision Rationale ---")
        print(f"  ID: {rationale.rationale_id}")
        print(f"  Type: {rationale.decision_type}")
        print(f"  Confidence: {rationale.confidence}")
        print(f"  Rationale: {rationale.concise_rationale}")

        print("\n[SHADOW ONLY — no execution dispatched]")

    def route(self, args):
        """Run AI router (shadow only)."""
        con = self._connect()
        workers = self._get_workers()
        registry = self._get_registry()

        task_id = getattr(args, 'task_id', 'task-unknown')
        task_family = getattr(args, 'family', 'code')
        role = getattr(args, 'role', 'builder')

        print(f"=== E3 Router (SHADOW) ===")
        print(f"Task: {task_id}")
        print(f"Family: {task_family}, Role: {role}")
        print()

        # Find eligible workers
        eligible = registry.find_eligible_workers(task_family, role)
        routable = workers.get_routable_workers()

        candidates = []
        for e in eligible:
            wid = e['worker_id']
            if wid in routable:
                w = routable[wid]
                candidates.append({
                    'worker_id': wid,
                    'provider': w['provider'],
                    'model': w['model'],
                    'state': e['state'],
                    'confidence': 'HIGH' if e['state'] == 'QUALIFIED' else 'MEDIUM'
                })

        print(f"Found {len(candidates)} candidate workers:")
        for c in candidates:
            print(f"  {c['worker_id']}: {c['confidence']} ({c['state']})")

        if not candidates:
            print("\nNo qualified candidates found.")
            print("Gate result: REJECT (no qualified route)")
            print("Action: ESCALATE to owner")

        print("\n[SHADOW ONLY — no execution dispatched]")

    def rationale(self, args):
        """Show decision rationale."""
        con = self._connect()
        decision_id = getattr(args, 'decision_id', None)

        if decision_id:
            row = con.execute(
                "SELECT * FROM decision_rationale_event WHERE rationale_id=?",
                (decision_id,)
            ).fetchone()
            if row:
                print(f"=== Decision Rationale: {decision_id} ===")
                for key in row.keys():
                    print(f"  {key}: {row[key]}")
            else:
                print(f"Rationale not found: {decision_id}")
        else:
            print("Recent decisions:")
            rows = con.execute(
                "SELECT rationale_id, decision_type, confidence, timestamp "
                "FROM decision_rationale_event ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
            for row in rows:
                print(f"  {row[0]} | {row[1]} | {row[2]} | {row[3]}")

    def trace(self, args):
        """Reconstruct decision history for a task."""
        con = self._connect()
        task_id = getattr(args, 'task_id', None)

        if not task_id:
            print("Usage: eb e3-trace <task_id>")
            return

        print(f"=== Decision Trace: {task_id} ===\n")

        # Get all decisions for this task
        rows = con.execute(
            """SELECT rationale_id, decision_type, decision_actor, 
                      chosen_action, confidence, gate_result, timestamp
               FROM decision_rationale_event 
               WHERE task_id=? ORDER BY timestamp""",
            (task_id,)
        ).fetchall()

        if not rows:
            print("No decisions found for this task.")
        else:
            for i, row in enumerate(rows, 1):
                print(f"Step {i}: {row[2]} decided {row[1]}")
                print(f"  Action: {row[3]}")
                print(f"  Confidence: {row[4]}")
                print(f"  Gate: {row[5]}")
                print(f"  Time: {row[6]}")
                print()

        # Execution-leg nodes persist their outcome in the DAG/evidence tables
        # rather than as a decision rationale event, so surface the persisted
        # terminal failure attribution for this task id / plan id here too.
        self._print_node_attributions(con, "plan_id=? OR node_id=?",
                                      (task_id, task_id))

    def _print_node_attributions(self, con, where, params):
        """Print persisted failure attribution for the matching DAG nodes."""
        try:
            node_ids = [r[0] for r in con.execute(
                f"SELECT node_id FROM dag_node WHERE {where} ORDER BY node_id",
                params).fetchall()]
        except Exception:
            return
        views = []
        for node_id in node_ids:
            view = node_failure_view(con, node_id)
            if view and (view["failure_attribution"] or view["content_stop"]
                         or view["state"] in TERMINAL_FAILURE_STATES):
                views.append(view)
        if views:
            print("--- Node failure attribution ---")
            for view in views:
                _print_failure_view(view)

    def why(self, args):
        """Show why a node was decided a certain way."""
        node_id = getattr(args, 'node_id', None)
        if not node_id:
            print("Usage: eb e3-why <node_id>")
            return

        con = self._connect()
        row = con.execute(
            """SELECT dr.decision_type, dr.chosen_action, dr.concise_rationale,
                      dr.confidence, dr.gate_result, dn.objective, dn.assigned_worker
               FROM decision_rationale_event dr
               JOIN dag_node dn ON dr.node_id = dn.node_id
               WHERE dr.node_id=?""",
            (node_id,)
        ).fetchone()

        view = node_failure_view(con, node_id)

        if row:
            print(f"=== Why: {node_id} ===")
            print(f"Objective: {row[5]}")
            print(f"Decision: {row[0]}")
            print(f"Action: {row[1]}")
            print(f"Rationale: {row[2]}")
            print(f"Confidence: {row[3]}")
            print(f"Gate: {row[4]}")
            print(f"Assigned worker: {row[6]}")
        elif view:
            # A production execution-leg node records its outcome in the DAG
            # state/evidence tables, not as a decision rationale event.
            print(f"=== Why: {node_id} ===")
            print(f"Objective: {view['objective']}")
            print("Decision: none recorded for this node (execution-leg node)")
            print(f"State: {view['state']}")
            print(f"Assigned worker: {view['assigned_worker']}")
        else:
            print(f"No decision found for node: {node_id}")
            return

        if view and (view["failure_attribution"] or view["content_stop"]
                     or view["state"] in TERMINAL_FAILURE_STATES):
            print()
            print("--- Persisted failure attribution ---")
            _print_failure_view(view)

    def verify_db(self, args):
        """Verify orchestration.db integrity."""
        con = self._connect()
        issues = []

        # Check schema version (highest applied migration = current level)
        try:
            row = con.execute("SELECT MAX(version) FROM schema_version").fetchone()
            if row and row[0] is not None:
                print(f"Schema version: {row[0]}")
            else:
                issues.append("No schema version found")
        except Exception as e:
            issues.append(f"Schema version check failed: {e}")

        # Check tables exist
        required_tables = [
            'dag_node', 'capability_registry', 'performance_evidence',
            'task_fingerprint_index', 'router_decision', 'conflict_record',
            'plan_version', 'worker_capability_event', 'dag_state_event',
            'decision_rationale_event', 'decision_outcome_review'
        ]
        for table in required_tables:
            try:
                con.execute(f"SELECT 1 FROM {table} LIMIT 0")
            except Exception:
                issues.append(f"Table missing: {table}")

        if issues:
            print(f"\nVerification FAILED ({len(issues)} issues):")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("\nVerification PASSED")
            print("All required tables present")
            print("Schema version valid")
