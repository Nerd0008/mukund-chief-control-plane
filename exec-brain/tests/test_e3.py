#!/usr/bin/env python3
"""E3 Tests — deterministic test suite for Stage 1."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add parent to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from orchestration_db import init_db, SCHEMA_VERSION
from capability_registry import CapabilityRegistry, CAPABILITY_ROLES, WORKER_STATES
from worker_registry import WorkerRegistry, WORKER_ROSTER
from task_fingerprint import TaskFingerprint, compute_similarity, TASK_FAMILIES
from decision_rationale import DecisionRationale, DecisionOutcomeReview, DECISION_TYPES
from execution_dag import ExecutionDAG, DAGNode, NODE_STATES
from worker_contract import WorkerContract
from qualification_gate import QualificationGate, GateResult, RejectionReason


class TestOrchestrationDB(unittest.TestCase):
    """Test orchestration.db schema and initialization."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.db_path = Path(self.temp) / 'test_orchestration.db'
        self.con = init_db(self.db_path)

    def tearDown(self):
        self.con.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_schema_version(self):
        """Schema version is set correctly."""
        row = self.con.execute("SELECT version FROM schema_version").fetchone()
        self.assertEqual(row[0], SCHEMA_VERSION)

    def test_tables_exist(self):
        """All required tables exist."""
        tables = [
            'dag_node', 'capability_registry', 'performance_evidence',
            'task_fingerprint_index', 'router_decision', 'conflict_record',
            'plan_version', 'worker_capability_event', 'dag_state_event',
            'decision_rationale_event', 'decision_outcome_review'
        ]
        for table in tables:
            self.con.execute(f"SELECT 1 FROM {table} LIMIT 0")

    def test_dag_node_insert(self):
        """Can insert a DAG node."""
        self.con.execute(
            """INSERT INTO dag_node (node_id, plan_id, objective, capability_roles, dependencies)
               VALUES (?, ?, ?, ?, ?)""",
            ('node-1', 'plan-1', 'Test objective', '["builder"]', '[]')
        )
        self.con.commit()
        row = self.con.execute("SELECT objective FROM dag_node WHERE node_id='node-1'").fetchone()
        self.assertEqual(row[0], 'Test objective')

    def test_capability_registry_insert(self):
        """Can insert capability registry entry."""
        self.con.execute(
            """INSERT INTO capability_registry (worker_id, task_family, capability_role, state)
               VALUES (?, ?, ?, ?)""",
            ('worker-1', 'code', 'builder', 'UNPROVEN')
        )
        self.con.commit()
        row = self.con.execute(
            "SELECT state FROM capability_registry WHERE worker_id='worker-1'"
        ).fetchone()
        self.assertEqual(row[0], 'UNPROVEN')


class TestCapabilityRegistry(unittest.TestCase):
    """Test CapabilityRegistry operations."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.db_path = Path(self.temp) / 'test.db'
        self.con = init_db(self.db_path)
        self.registry = CapabilityRegistry(self.con)

    def tearDown(self):
        self.con.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_register_worker(self):
        """Registering a worker creates registry entries."""
        self.registry.register_worker('w1', 'provider1', 'model1', roles=['builder'])
        cap = self.registry.get_capability('w1', 'general', 'builder')
        self.assertEqual(cap['state'], 'UNPROVEN')
        self.assertEqual(cap['evidence_count'], 0)

    def test_update_capability_state(self):
        """Can update capability state."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        self.registry.update_capability_state('w1', 'general', 'builder', 'QUALIFIED')
        cap = self.registry.get_capability('w1', 'general', 'builder')
        self.assertEqual(cap['state'], 'QUALIFIED')
        self.assertIsNotNone(cap['last_qualified_at'])

    def test_suspend_capability(self):
        """Can suspend a capability."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        self.registry.update_capability_state('w1', 'general', 'builder', 'SUSPENDED', 'serious')
        cap = self.registry.get_capability('w1', 'general', 'builder')
        self.assertEqual(cap['state'], 'SUSPENDED')
        self.assertEqual(cap['failure_severity'], 'serious')

    def test_find_qualified_workers(self):
        """Find qualified workers returns only qualified."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        self.registry.register_worker('w2', 'p2', 'm2', roles=['builder'])
        self.registry.update_capability_state('w1', 'general', 'builder', 'QUALIFIED')
        qualified = self.registry.find_qualified_workers('general', 'builder')
        self.assertIn('w1', qualified)
        self.assertNotIn('w2', qualified)

    def test_find_eligible_workers_low_risk(self):
        """Low-risk tasks can use QUALIFIED or EVALUATING workers."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        self.registry.register_worker('w2', 'p2', 'm2', roles=['builder'])
        self.registry.update_capability_state('w1', 'general', 'builder', 'QUALIFIED')
        self.registry.update_capability_state('w2', 'general', 'builder', 'EVALUATING')
        eligible = self.registry.find_eligible_workers('general', 'builder', 'R0')
        self.assertEqual(len(eligible), 2)

    def test_find_eligible_workers_high_risk(self):
        """High-risk tasks only use QUALIFIED workers."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        self.registry.register_worker('w2', 'p2', 'm2', roles=['builder'])
        self.registry.update_capability_state('w1', 'general', 'builder', 'QUALIFIED')
        self.registry.update_capability_state('w2', 'general', 'builder', 'EVALUATING')
        eligible = self.registry.find_eligible_workers('general', 'builder', 'R2')
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]['worker_id'], 'w1')


class TestWorkerRegistry(unittest.TestCase):
    """Test WorkerRegistry."""

    def test_roster_has_10_workers(self):
        """Roster contains exactly 10 workers."""
        registry = WorkerRegistry()
        self.assertEqual(len(registry.get_all_workers()), 10)

    def test_all_workers_unproven_initially(self):
        """All workers start as UNPROVEN (LOCKED != QUALIFIED)."""
        registry = WorkerRegistry()
        for wid, w in registry.get_all_workers().items():
            self.assertIn(w['pool_status'], ('LOCKED', 'EVALUATE', 'BENCHMARK'))

    def test_pool_summary(self):
        """Pool summary groups workers by status."""
        registry = WorkerRegistry()
        summary = registry.get_pool_summary()
        self.assertIn('LOCKED', summary)
        self.assertIn('EVALUATE', summary)
        self.assertIn('BENCHMARK', summary)

    def test_routable_workers(self):
        """Codex CLI is NOT routable (E2 observed-only)."""
        registry = WorkerRegistry()
        routable = registry.get_routable_workers()
        self.assertNotIn('codex-cli', routable)

    def test_deepseek_is_routable(self):
        """DeepSeek IS routable — smoke test PASS + E2 linkage VERIFIED.

        E3 DeepSeek setup 2026-09-23: adapter implemented, auth via
        Credential Manager (D2), smoke test passed with observed
        provider telemetry, usage recorded through E2 record-request.
        Routability = execution readiness only; qualification remains
        UNPROVEN.
        """
        registry = WorkerRegistry()
        routable = registry.get_routable_workers()
        worker = registry.get_worker('deepseek-v41-flash')
        self.assertIn('deepseek-v41-flash', routable)
        self.assertEqual(worker['api_model_id'], 'deepseek-flash')  # observed
        self.assertEqual(worker['smoke_test'], 'PASS')
        self.assertEqual(worker['e2_usage_linkage'], 'VERIFIED')
        self.assertEqual(worker['qualification'], 'UNPROVEN')


class TestTaskFingerprint(unittest.TestCase):
    """Test TaskFingerprint."""

    def test_valid_fingerprint(self):
        """Valid fingerprint passes validation."""
        fp = TaskFingerprint(
            task_family='code',
            reasoning_depth=2,
            risk_class='R1',
            required_roles=['builder']
        )
        errors = fp.validate()
        self.assertEqual(len(errors), 0)

    def test_invalid_task_family(self):
        """Invalid task family fails validation."""
        fp = TaskFingerprint(task_family='invalid')
        errors = fp.validate()
        self.assertTrue(any('task_family' in e for e in errors))

    def test_invalid_reasoning_depth(self):
        """Invalid reasoning depth fails validation."""
        fp = TaskFingerprint(task_family='code', reasoning_depth=5)
        errors = fp.validate()
        self.assertTrue(any('reasoning_depth' in e for e in errors))

    def test_compute_hash(self):
        """Fingerprint hash is deterministic."""
        fp1 = TaskFingerprint(task_family='code', reasoning_depth=2)
        fp2 = TaskFingerprint(task_family='code', reasoning_depth=2)
        self.assertEqual(fp1.compute_hash(), fp2.compute_hash())

    def test_similarity_identical(self):
        """Identical fingerprints have similarity 1.0."""
        fp1 = TaskFingerprint(task_family='code', reasoning_depth=2, risk_class='R1')
        fp2 = TaskFingerprint(task_family='code', reasoning_depth=2, risk_class='R1')
        sim = compute_similarity(fp1, fp2)
        self.assertAlmostEqual(sim, 1.0, places=1)

    def test_similarity_different(self):
        """Different fingerprints have lower similarity."""
        fp1 = TaskFingerprint(task_family='code', reasoning_depth=0, risk_class='R0')
        fp2 = TaskFingerprint(task_family='research', reasoning_depth=4, risk_class='R3')
        sim = compute_similarity(fp1, fp2)
        self.assertLess(sim, 0.5)


class TestDecisionRationale(unittest.TestCase):
    """Test DecisionRationale."""

    def test_create_rationale(self):
        """Can create a decision rationale."""
        r = DecisionRationale(
            task_id='task-1',
            decision_type='decomposition',
            decision_actor='planner',
            objective='Plan task',
            chosen_action='decompose'
        )
        self.assertIsNotNone(r.rationale_id)
        self.assertEqual(r.decision_type, 'decomposition')

    def test_validate_requires_objective(self):
        """Validation fails without objective."""
        r = DecisionRationale(
            task_id='task-1',
            decision_type='decomposition',
            decision_actor='planner',
            objective='',
            chosen_action='decompose'
        )
        errors = r.validate()
        self.assertTrue(any('objective' in e for e in errors))

    def test_validate_requires_concise_rationale(self):
        """Validation fails without concise_rationale (A7)."""
        r = DecisionRationale(
            task_id='task-1',
            decision_type='decomposition',
            decision_actor='planner',
            objective='Plan task',
            chosen_action='decompose'
        )
        errors = r.validate()
        self.assertTrue(any('concise_rationale' in e for e in errors))

    def test_validate_valid(self):
        """Valid rationale passes."""
        r = DecisionRationale(
            task_id='task-1',
            decision_type='decomposition',
            decision_actor='planner',
            objective='Plan task',
            chosen_action='decompose'
        )
        r.concise_rationale = 'Task complexity warrants decomposition'
        errors = r.validate()
        self.assertEqual(len(errors), 0)

    def test_outcome_review(self):
        """Can create outcome review."""
        r = DecisionRationale(
            task_id='task-1',
            decision_type='decomposition',
            decision_actor='planner',
            objective='Plan task',
            chosen_action='decompose'
        )
        review = DecisionOutcomeReview(r.rationale_id)
        review.actual_outcome = 'SUCCESS'
        review.decision_quality = 'SUPPORTED'
        review.lessons = 'Decomposition was appropriate'
        self.assertEqual(review.rationale_id, r.rationale_id)


class TestExecutionDAG(unittest.TestCase):
    """Test ExecutionDAG."""

    def test_create_dag(self):
        """Can create a DAG."""
        dag = ExecutionDAG()
        self.assertIsNotNone(dag.plan_id)
        self.assertEqual(len(dag.nodes), 0)

    def test_add_node(self):
        """Can add nodes to DAG."""
        dag = ExecutionDAG()
        node = DAGNode(objective='Test', capability_roles=['builder'])
        nid = dag.add_node(node)
        self.assertIn(nid, dag.nodes)

    def test_get_ready_nodes(self):
        """Ready nodes have all dependencies complete."""
        dag = ExecutionDAG()
        n1 = DAGNode(objective='Step 1', dependencies=[])
        n1.state = 'COMPLETE'
        n2 = DAGNode(objective='Step 2', dependencies=[n1.node_id])
        n2.state = 'BLOCKED'
        dag.add_node(n1)
        dag.add_node(n2)
        ready = dag.get_ready_nodes()
        self.assertIn(n2.node_id, ready)

    def test_is_complete(self):
        """DAG is complete when all nodes are complete."""
        dag = ExecutionDAG()
        n1 = DAGNode(objective='Step 1')
        n1.state = 'COMPLETE'
        dag.add_node(n1)
        self.assertTrue(dag.is_complete())

    def test_is_failed(self):
        """DAG is failed when any node is failed."""
        dag = ExecutionDAG()
        n1 = DAGNode(objective='Step 1')
        n1.state = 'FAILED'
        dag.add_node(n1)
        self.assertTrue(dag.is_failed())


class TestWorkerContract(unittest.TestCase):
    """Test WorkerContract."""

    def test_create_contract(self):
        """Can create a worker contract."""
        c = WorkerContract(
            objective='Implement feature X',
            relevant_inputs={'spec': 'details'},
            verification_method='test'
        )
        self.assertIsNotNone(c.contract_id)
        self.assertEqual(c.objective, 'Implement feature X')

    def test_validate_requires_objective(self):
        """Validation fails without objective."""
        c = WorkerContract(objective='')
        errors = c.validate()
        self.assertTrue(any('objective' in e for e in errors))

    def test_validate_invalid_verification(self):
        """Validation fails with invalid verification method."""
        c = WorkerContract(objective='Test', verification_method='invalid')
        errors = c.validate()
        self.assertTrue(any('verification_method' in e for e in errors))


class TestQualificationGate(unittest.TestCase):
    """Test QualificationGate."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.db_path = Path(self.temp) / 'test.db'
        self.con = init_db(self.db_path)
        self.registry = CapabilityRegistry(self.con)
        self.gate = QualificationGate(self.registry)

    def tearDown(self):
        self.con.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_accept_qualified_worker(self):
        """Qualified worker is accepted."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        self.registry.update_capability_state('w1', 'general', 'builder', 'QUALIFIED')
        proposal = {'worker_id': 'w1', 'role': 'builder', 'reasoning_level': 2}
        floor = {'task_family': 'general', 'min_reasoning_depth': 1}
        result, reasons = self.gate.validate_proposal(proposal, floor)
        self.assertEqual(result, GateResult.ACCEPT)

    def test_reject_suspended_worker(self):
        """Suspended worker is rejected."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        self.registry.update_capability_state('w1', 'general', 'builder', 'SUSPENDED')
        proposal = {'worker_id': 'w1', 'role': 'builder'}
        floor = {'task_family': 'general'}
        result, reasons = self.gate.validate_proposal(proposal, floor)
        self.assertEqual(result, GateResult.REJECT)
        self.assertIn(RejectionReason.WORKER_SUSPENDED.value, reasons)

    def test_evaluation_only_for_unproven_low_risk(self):
        """Unproven worker on low-risk task gets EVALUATION_ONLY."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        proposal = {'worker_id': 'w1', 'role': 'builder'}
        floor = {'task_family': 'general'}
        result, reasons = self.gate.validate_proposal(proposal, floor, 'R0')
        self.assertEqual(result, GateResult.EVALUATION_ONLY)

    def test_reject_unproven_high_risk(self):
        """Unproven worker on high-risk task is rejected."""
        self.registry.register_worker('w1', 'p1', 'm1', roles=['builder'])
        proposal = {'worker_id': 'w1', 'role': 'builder'}
        floor = {'task_family': 'general'}
        result, reasons = self.gate.validate_proposal(proposal, floor, 'R3')
        self.assertEqual(result, GateResult.REJECT)
        self.assertIn(RejectionReason.WORKER_UNPROVEN_ON_HIGH_RISK.value, reasons)


class TestE1Regression(unittest.TestCase):
    """E1 regression tests — ensure E1 schema is untouched."""

    def test_e1_tables_exist(self):
        """E1 tables still exist."""
        eb_path = Path(__file__).parent / 'exec_brain.db'
        if eb_path.exists():
            con = sqlite3.connect(str(eb_path))
            tables = [
                'task_record', 'subtask_record', 'quality_floor',
                'strategy_decision', 'override_record', 'audit_log'
            ]
            for table in tables:
                con.execute(f"SELECT 1 FROM {table} LIMIT 0")
            con.close()


class TestE2Regression(unittest.TestCase):
    """E2 regression tests — ensure E2 schema is untouched."""

    def test_e2_tables_exist(self):
        """E2 tables still exist."""
        gov_path = Path(__file__).parent / 'governor.db'
        if gov_path.exists():
            con = sqlite3.connect(str(gov_path))
            tables = [
                'provider_snapshot', 'capacity_dimension', 'observed_request',
                'daily_brief_log', 'daily_aggregate'
            ]
            for table in tables:
                con.execute(f"SELECT 1 FROM {table} LIMIT 0")
            con.close()


if __name__ == '__main__':
    unittest.main()
