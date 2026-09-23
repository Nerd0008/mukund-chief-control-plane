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

        # Schema version
        try:
            row = con.execute("SELECT version FROM schema_version").fetchone()
            print(f"Schema version: {row[0] if row else 'unknown'}")
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
            return

        for i, row in enumerate(rows, 1):
            print(f"Step {i}: {row[2]} decided {row[1]}")
            print(f"  Action: {row[3]}")
            print(f"  Confidence: {row[4]}")
            print(f"  Gate: {row[5]}")
            print(f"  Time: {row[6]}")
            print()

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

        if row:
            print(f"=== Why: {node_id} ===")
            print(f"Objective: {row[5]}")
            print(f"Decision: {row[0]}")
            print(f"Action: {row[1]}")
            print(f"Rationale: {row[2]}")
            print(f"Confidence: {row[3]}")
            print(f"Gate: {row[4]}")
            print(f"Assigned worker: {row[6]}")
        else:
            print(f"No decision found for node: {node_id}")

    def verify_db(self, args):
        """Verify orchestration.db integrity."""
        con = self._connect()
        issues = []

        # Check schema version
        try:
            row = con.execute("SELECT version FROM schema_version").fetchone()
            if row:
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
