#!/usr/bin/env python3
"""Tests for new E3 orchestration components."""

import os
import sqlite3
import tempfile
import unittest
import importlib.util
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))

from e3_planner import E3Planner
from e3_decomposition_review import DecompositionReview, DecompositionReviewResult
from e3_router import E3Router, MetaSelector, RouterCandidate
from e3_context import ContextCompiler
from e3_permissions import PermissionCompiler, PermissionLevel
from e3_team_assembly import TeamAssembler, TeamAssembly, TeamAssignment
from e3_integrator import E3Integrator, IntegrationIssue
from e3_verifier import IndependentVerifier, AICritic, VerificationMethod, VerificationOutcome
from e3_replan import E3Replanner, ReplanTrigger
from e3_conflict import ConflictHandler, ConflictType
from e3_evidence import E3EvidenceManager, FailureAttribution, EvidenceRecord
from e3_escalate import E3Escalator, EscalationTrigger
from e3_exploration import ExplorationRules, ShadowEvaluation, ExplorationPolicy, ExplorationRequest
from e3_qualification_benchmark import ColdStartBenchmark, TestCase, QualificationResult, QualificationState
from orchestration_db import init_db
from capability_registry import CapabilityRegistry
from task_fingerprint import TaskFingerprint
from execution_dag import ExecutionDAG, DAGNode
from worker_contract import WorkerContract


class TestE3Planner(unittest.TestCase):
    """Test E3 Planner."""

    def setUp(self):
        self.planner = E3Planner()

    def test_single_node_plan_simple_task(self):
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R1")
        plan = self.planner.plan("Simple bug fix", fp)
        self.assertFalse(plan["decomposition"])
        self.assertEqual(len(plan["nodes"]), 1)
        self.assertEqual(plan["nodes"][0]["capability_roles"], ["builder"])

    def test_decomposition_high_reasoning_depth(self):
        fp = TaskFingerprint(
            task_family="code", reasoning_depth=4, risk_class="R2",
            required_roles=["researcher", "architect", "builder"]
        )
        plan = self.planner.plan("Complex system redesign", fp)
        self.assertTrue(plan["decomposition"])
        self.assertGreater(len(plan["nodes"]), 1)

    def test_decomposition_multiple_roles(self):
        fp = TaskFingerprint(
            task_family="code", reasoning_depth=2, risk_class="R1",
            required_roles=["researcher", "builder", "critic"]
        )
        plan = self.planner.plan("Multi-stage task", fp)
        self.assertTrue(plan["decomposition"])
        self.assertGreaterEqual(len(plan["nodes"]), 3)

    def test_build_dag_from_single_node(self):
        fp = TaskFingerprint(task_family="code", reasoning_depth=1, risk_class="R1")
        plan = self.planner.plan("Simple task", fp)
        dag = self.planner.build_dag(plan)
        self.assertEqual(len(dag.nodes), 1)
        self.assertFalse(dag.is_complete())  # Node is PLANNED, not COMPLETE

    def test_build_dag_from_decomposed_plan(self):
        fp = TaskFingerprint(
            task_family="code", reasoning_depth=3, risk_class="R1",
            required_roles=["researcher", "builder"]
        )
        plan = self.planner.plan("Complex task", fp)
        dag = self.planner.build_dag(plan)
        self.assertGreaterEqual(len(dag.nodes), 2)


class TestDecompositionReview(unittest.TestCase):
    """Test Decomposition Review structural checks."""

    def setUp(self):
        self.reviewer = DecompositionReview()

    def test_valid_single_node(self):
        fp = TaskFingerprint(task_family="code", reasoning_depth=1)
        planner = E3Planner()
        plan = planner.plan("Simple task", fp)
        dag = planner.build_dag(plan)
        result = self.reviewer.review(plan, dag)
        self.assertTrue(result.approved)
        self.assertEqual(len(result.structural_issues), 0)

    def test_valid_decomposed_plan(self):
        fp = TaskFingerprint(
            task_family="code", reasoning_depth=3,
            required_roles=["researcher", "builder"]
        )
        planner = E3Planner()
        plan = planner.plan("Complex task", fp)
        dag = planner.build_dag(plan)
        result = self.reviewer.review(plan, dag)
        self.assertTrue(result.approved)

    def test_cycle_detection(self):
        dag = ExecutionDAG()
        n1 = DAGNode(objective="A")
        n2 = DAGNode(objective="B")
        dag.add_node(n1)
        dag.add_node(n2)
        # Manually create cycle
        n1.dependencies = [n2.node_id]
        n2.dependencies = [n1.node_id]
        plan = {"decomposition": True, "nodes": [{"objective": "test", "capability_roles": ["builder"]}]}
        result = self.reviewer.review(plan, dag)
        self.assertFalse(result.approved)
        self.assertTrue(any("cycle" in issue.lower() for issue in result.structural_issues))

    def test_invalid_dependency_reference(self):
        dag = ExecutionDAG()
        n1 = DAGNode(objective="A", dependencies=["nonexistent"])
        dag.add_node(n1)
        plan = {"decomposition": False, "nodes": [{"objective": "test", "capability_roles": ["builder"]}]}
        result = self.reviewer.review(plan, dag)
        self.assertFalse(result.approved)
        self.assertTrue(any("non-existent" in issue for issue in result.structural_issues))

    def test_missing_required_fields(self):
        plan = {
            "decomposition": True,
            "nodes": [{"capability_roles": ["builder"]}]  # Missing objective
        }
        dag = ExecutionDAG()
        result = self.reviewer.review(plan, dag)
        self.assertFalse(result.approved)

    def test_isolated_node_warning(self):
        dag = ExecutionDAG()
        n1 = DAGNode(objective="First", dependencies=[])
        n2 = DAGNode(objective="Second", dependencies=[])
        dag.add_node(n1)
        dag.add_node(n2)
        plan = {
            "decomposition": True,
            "nodes": [
                {"objective": "First", "capability_roles": ["builder"]},
                {"objective": "Second", "capability_roles": ["builder"]},
            ]
        }
        result = self.reviewer.review(plan, dag)
        # Should have warnings about isolated nodes
        self.assertTrue(len(result.warnings) > 0)


class TestE3Router(unittest.TestCase):
    """Test E3 Router meta-selector and candidate generation."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.db_path = Path(self.temp) / "test.db"
        self.con = init_db(self.db_path)
        self.registry = CapabilityRegistry(self.con)
        self.router = E3Router(self.registry)

    def tearDown(self):
        self.con.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_meta_selector_returns_none_without_qualified(self):
        ms = MetaSelector(self.registry)
        result = ms.select_router("code")
        self.assertIsNone(result)

    def test_propose_candidates_returns_empty_without_eligible(self):
        node = {"capability_roles": ["builder"]}
        candidates = self.router.propose_candidates(node, "code")
        self.assertEqual(len(candidates), 0)

    def test_router_decision_structure(self):
        candidate = RouterCandidate(
            worker_id="w1", provider="p1", model="m1",
            role="builder", confidence="HIGH",
            reasoning_codes=["QUALIFIED_WORKER", "STRONG_EVIDENCE"],
            concise_rationale="Strong candidate",
            evidence_references=["ev-1"]
        )
        decision = self.router.create_router_decision("plan-1", "node-1", candidate)
        self.assertEqual(decision["plan_id"], "plan-1")
        self.assertEqual(decision["node_id"], "node-1")
        self.assertEqual(decision["confidence"], "HIGH")
        self.assertIsNone(decision["gate_decision"])


class TestContextCompiler(unittest.TestCase):
    """Test Context Compiler."""

    def setUp(self):
        self.compiler = ContextCompiler()

    def test_compile_minimal_context(self):
        contract = WorkerContract(objective="Test", verification_method="test")
        context = self.compiler.compile("Test objective", contract)
        self.assertEqual(context["objective"], "Test objective")
        self.assertIn("output_schema", context)

    def test_compile_with_upstream_outputs(self):
        contract = WorkerContract(objective="Test", verification_method="test")
        upstream = {"output-a": {"data": "value-a"}, "output-b": {"data": "value-b"}}
        context = self.compiler.compile("Test objective", contract, upstream_outputs=upstream)
        self.assertIn("upstream_outputs", context)

    def test_validate_context_size_warning(self):
        large_context = {"data": "x" * 200000}
        warnings = self.compiler.validate_context(large_context)
        self.assertTrue(any("size" in w.lower() for w in warnings))

    def test_validate_context_sensitive_data_warning(self):
        context = {"data": "password=secret123"}
        warnings = self.compiler.validate_context(context)
        self.assertTrue(any("sensitive" in w.lower() for w in warnings))


class TestPermissionCompiler(unittest.TestCase):
    """Test Permission Compiler."""

    def setUp(self):
        self.compiler = PermissionCompiler()

    def test_builder_gets_controlled_write(self):
        perms = self.compiler.compile_permissions(["builder"])
        self.assertEqual(perms["file_write"], PermissionLevel.CONTROLLED_WRITE)
        self.assertEqual(perms["terminal"], PermissionLevel.CONTROLLED_WRITE)

    def test_critic_gets_read_only(self):
        perms = self.compiler.compile_permissions(["critic"])
        self.assertEqual(perms["file_write"], PermissionLevel.NONE)
        self.assertEqual(perms["file_read"], PermissionLevel.READ_ONLY)

    def test_integrator_gets_mixed(self):
        perms = self.compiler.compile_permissions(["integrator"])
        self.assertEqual(perms["file_write"], PermissionLevel.CONTROLLED_WRITE)
        self.assertEqual(perms["test_execution"], PermissionLevel.READ_ONLY)

    def test_multi_role_most_permissive_wins(self):
        perms = self.compiler.compile_permissions(["critic", "builder"])
        self.assertEqual(perms["terminal"], PermissionLevel.CONTROLLED_WRITE)

    def test_validate_permission_request(self):
        requested: Dict[str, Any] = {"file_write": PermissionLevel.FULL}
        allowed: Dict[str, Any] = {"file_write": PermissionLevel.CONTROLLED_WRITE}
        violations = self.compiler.validate_permission_request(requested, allowed)
        self.assertTrue(len(violations) > 0)


class TestTeamAssembler(unittest.TestCase):
    """Test Team Assembly."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.db_path = Path(self.temp) / "test.db"
        self.con = init_db(self.db_path)
        self.registry = CapabilityRegistry(self.con)
        self.assembler = TeamAssembler(self.registry)

    def tearDown(self):
        self.con.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_assemble_empty_plan(self):
        plan = {"plan_id": "p1", "nodes": []}
        assembly = self.assembler.assemble_team(plan)
        self.assertTrue(assembly.complete)
        self.assertEqual(len(assembly.assignments), 0)

    def test_detect_integrator_verifier_conflict(self):
        plan = {"plan_id": "p1", "nodes": [{"node_id": "n1"}, {"node_id": "n2"}]}
        assembly = TeamAssembly("p1")
        assembly.add_assignment(TeamAssignment("n1", "w1", "integrator", "HIGH", "test"))
        assembly.add_assignment(TeamAssignment("n2", "w1", "verifier", "HIGH", "test"))
        conflicts = self.assembler.detect_team_conflicts(assembly)
        self.assertTrue(any(c["type"] == "integrator_verifier_same_worker" for c in conflicts))

    def test_suggest_indifferent_verifier(self):
        plan = {"plan_id": "p1", "nodes": [{"node_id": "n1"}]}
        assembly = TeamAssembly("p1")
        assembly.add_assignment(TeamAssignment("n1", "w1", "integrator", "HIGH", "test"))
        verifier = self.assembler.suggest_independent_verifier(assembly, ["w1", "w2"])
        self.assertEqual(verifier, "w2")


class TestE3Integrator(unittest.TestCase):
    """Test E3 Integrator."""

    def setUp(self):
        self.integrator = E3Integrator()

    def test_integrate_empty_outputs(self):
        result = self.integrator.integrate("test", {})
        self.assertFalse(result.complete)
        self.assertTrue(result.has_blocking_issues())

    def test_integrate_single_output(self):
        result = self.integrator.integrate("test", {"node-1": {"data": "value"}})
        self.assertTrue(result.complete)
        self.assertFalse(result.has_blocking_issues())

    def test_detect_contradictions(self):
        outputs = {
            "node-1": {"recommendation": "use-library-A"},
            "node-2": {"recommendation": "use-library-B"},
        }
        result = self.integrator.integrate("test", outputs)
        self.assertTrue(len(result.contradictions) > 0)

    def test_combine_outputs(self):
        outputs = {
            "node-1": {"key-a": "value-a"},
            "node-2": {"key-b": "value-b"},
        }
        result = self.integrator.integrate("test", outputs)
        self.assertIn("key-a", result.integrated_output)
        self.assertIn("key-b", result.integrated_output)

    def test_identify_duplication(self):
        outputs = {
            "node-1": "This is a detailed analysis of the performance characteristics",
            "node-2": "This is a detailed analysis of the performance characteristics",
        }
        duplications = self.integrator.identify_duplication(outputs)
        self.assertTrue(len(duplications) > 0)

    def test_missing_deliverables(self):
        result = self.integrator.integrate(
            "test",
            {"node-1": {"key-a": "value-a"}},
            original_requirements={"expected_outputs": {"key-a": "", "key-b": ""}}
        )
        self.assertTrue(len(result.missing_pieces) > 0)


class TestIndependentVerifier(unittest.TestCase):
    """Test Independent Verifier."""

    def test_verify_by_schema_valid(self):
        verifier = IndependentVerifier(
            expected_schema={"required": ["status", "data"]}
        )
        result = verifier.verify({"status": "ok", "data": "test"}, VerificationMethod.SCHEMA)
        self.assertTrue(result.passed)

    def test_verify_by_schema_missing_field(self):
        verifier = IndependentVerifier(
            expected_schema={"required": ["status", "data"]}
        )
        result = verifier.verify({"status": "ok"}, VerificationMethod.SCHEMA)
        self.assertFalse(result.passed)
        self.assertTrue(len(result.issues) > 0)

    def test_verify_by_tests_all_pass(self):
        verifier = IndependentVerifier(
            test_cases=[
                {"name": "test1", "field": "status", "expected": "ok"},
                {"name": "test2", "field": "count", "expected": 42},
            ]
        )
        result = verifier.verify({"status": "ok", "count": 42}, VerificationMethod.TEST)
        self.assertTrue(result.passed)

    def test_verify_by_tests_partial(self):
        verifier = IndependentVerifier(
            test_cases=[
                {"name": "test1", "field": "status", "expected": "ok"},
                {"name": "test2", "field": "count", "expected": 42},
            ]
        )
        result = verifier.verify({"status": "ok", "count": 0}, VerificationMethod.TEST)
        self.assertEqual(result.outcome, VerificationOutcome.PARTIAL)

    def test_critic_requires_worker(self):
        critic = AICritic()
        self.assertFalse(critic.can_criticize())
        result = critic.review("test", {"data": "value"})
        self.assertEqual(result.outcome, VerificationOutcome.UNCERTAIN)


class TestE3Replanner(unittest.TestCase):
    """Test E3 Replanner."""

    def setUp(self):
        self.replanner = E3Replanner(max_replan_depth=3)

    def test_replan_preserves_complete_nodes(self):
        dag = ExecutionDAG()
        n1 = DAGNode(objective="Completed", dependencies=[])
        n1.state = "COMPLETE"
        n2 = DAGNode(objective="Failed", dependencies=[n1.node_id])
        n2.state = "FAILED"
        dag.add_node(n1)
        dag.add_node(n2)

        record = self.replanner.replan(dag, ReplanTrigger.FUNDAMENTAL_FLAW, "Test replan", [n2.node_id])
        self.assertIsNotNone(record)
        self.assertIn(n1.node_id, record.nodes_preserved)
        self.assertIn(n2.node_id, record.nodes_cancelled)
        self.assertEqual(n2.state, "CANCELLED")

    def test_replan_depth_limit(self):
        dag = ExecutionDAG()
        n1 = DAGNode(objective="Failed", dependencies=[])
        n1.state = "FAILED"
        dag.add_node(n1)

        # Exhaust replan depth
        records = []
        for _ in range(3):
            record = self.replanner.replan(dag, ReplanTrigger.FUNDAMENTAL_FLAW, "Test", [n1.node_id])
            if record is not None:
                records.append(record)

        # Fourth replan should be rejected
        result = self.replanner.replan(dag, ReplanTrigger.FUNDAMENTAL_FLAW, "Test", [n1.node_id])
        self.assertIsNone(result)

    def test_can_replan_check(self):
        self.assertTrue(self.replanner.can_replan())


class TestConflictHandler(unittest.TestCase):
    """Test Conflict Handler."""

    def setUp(self):
        self.handler = ConflictHandler()

    def test_detect_conflict_same_key_different_values(self):
        output_a = {"recommendation": "use-A"}
        output_b = {"recommendation": "use-B"}
        conflict = self.handler.detect_conflict("n1", output_a, "n2", output_b)
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.node_a, "n1")
        self.assertEqual(conflict.node_b, "n2")

    def test_no_conflict_for_identical_outputs(self):
        output_a = {"recommendation": "use-A"}
        output_b = {"recommendation": "use-A"}
        conflict = self.handler.detect_conflict("n1", output_a, "n2", output_b)
        self.assertIsNone(conflict)

    def test_resolve_conflict(self):
        conflict = self.handler.detect_conflict(
            "n1", {"rec": "A"}, "n2", {"rec": "B"}
        )
        self.assertIsNotNone(conflict)
        self.handler.resolve_conflict(conflict, "Chose A based on evidence", "critic-1")
        self.assertTrue(conflict.resolved)
        self.assertEqual(conflict.resolved_by, "critic-1")

    def test_escalate_conflict(self):
        conflict = self.handler.detect_conflict(
            "n1", {"rec": "A"}, "n2", {"rec": "B"}
        )
        self.assertIsNotNone(conflict)
        escalation = self.handler.escalate_conflict(conflict, "cannot determine correct answer")
        self.assertTrue(escalation["owner_decision_required"])


class TestE3EvidenceManager(unittest.TestCase):
    """Test E3 Evidence Manager."""

    def setUp(self):
        self.mgr = E3EvidenceManager()

    def test_record_evidence(self):
        fp = TaskFingerprint(task_family="code", reasoning_depth=2)
        ev = EvidenceRecord("w1", fp, "builder", "p1", "m1")
        ev_id = self.mgr.record_evidence(ev)
        self.assertTrue(ev_id.startswith("evidence-"))

    def test_record_outcome(self):
        fp = TaskFingerprint(task_family="code", reasoning_depth=2)
        ev = EvidenceRecord("w1", fp, "builder", "p1", "m1")
        ev_id = self.mgr.record_evidence(ev)
        self.mgr.record_outcome(ev_id, True, True, "PASS")
        self.assertTrue(ev.first_pass_success)
        self.assertTrue(ev.final_success)

    def test_compute_first_pass_rate(self):
        fp = TaskFingerprint(task_family="code", reasoning_depth=2)
        ev1 = EvidenceRecord("w1", fp, "builder", "p1", "m1")
        ev1.first_pass_success = True
        ev2 = EvidenceRecord("w1", fp, "builder", "p1", "m1")
        ev2.first_pass_success = False
        self.mgr.record_evidence(ev1)
        self.mgr.record_evidence(ev2)
        rate = self.mgr.compute_first_pass_rate("w1")
        self.assertAlmostEqual(rate, 0.5)

    def test_attribute_failure(self):
        fp = TaskFingerprint(task_family="code", reasoning_depth=2)
        ev = EvidenceRecord("w1", fp, "builder", "p1", "m1")
        result = self.mgr.attribute_failure(ev, FailureAttribution.REASONING, "Logic error")
        self.assertEqual(result["category"], "reasoning")


class TestE3Escalator(unittest.TestCase):
    """Test E3 Escalator."""

    def setUp(self):
        self.escalator = E3Escalator()

    def test_escalate_stuck(self):
        record = self.escalator.escalate(
            EscalationTrigger.STUCK.value,
            "Cannot resolve conflict after 3 attempts",
            proposals_considered=["try worker A", "try worker B"],
            why_each_failed=["A unavailable", "B insufficient context"],
            owner_decision_needed="Which worker to try next?"
        )
        self.assertFalse(record.resolved)
        self.assertEqual(len(record.proposals_considered), 2)

    def test_resolve_escalation(self):
        record = self.escalator.escalate(
            EscalationTrigger.STUCK.value,
            "Cannot proceed"
        )
        self.escalator.resolve_escalation(record.escalation_id, "Owner chose to replan")
        self.assertTrue(record.resolved)

    def test_get_active_escalations(self):
        self.escalator.escalate(EscalationTrigger.STUCK.value, "Issue 1")
        self.escalator.escalate(EscalationTrigger.REPEATED_FAILURE.value, "Issue 2")
        active = self.escalator.get_active_escalations()
        self.assertEqual(len(active), 2)


class TestExplorationRules(unittest.TestCase):
    """Test Exploration/Shadow Rules."""

    def setUp(self):
        self.rules = ExplorationRules(ExplorationPolicy.CONSERVATIVE)

    def test_exploration_approved_for_r0(self):
        request = ExplorationRequest(
            task_id="t1", candidate_worker_id="w2",
            primary_worker_id="w1", task_family="code",
            risk_class="R0"
        )
        decision = self.rules.evaluate(request)
        self.assertTrue(decision.approved)

    def test_exploration_rejected_for_r2(self):
        request = ExplorationRequest(
            task_id="t1", candidate_worker_id="w2",
            primary_worker_id="w1", task_family="code",
            risk_class="R2"
        )
        decision = self.rules.evaluate(request)
        self.assertFalse(decision.approved)

    def test_exploration_disabled_policy(self):
        rules = ExplorationRules(ExplorationPolicy.DISABLED)
        request = ExplorationRequest(
            task_id="t1", candidate_worker_id="w2",
            primary_worker_id="w1", task_family="code",
            risk_class="R0"
        )
        decision = rules.evaluate(request)
        self.assertFalse(decision.approved)

    def test_same_worker_rejected(self):
        request = ExplorationRequest(
            task_id="t1", candidate_worker_id="w1",
            primary_worker_id="w1", task_family="code",
            risk_class="R0"
        )
        decision = self.rules.evaluate(request)
        self.assertFalse(decision.approved)

    def test_shadow_evaluation_rules(self):
        shadow = ShadowEvaluation()
        self.assertTrue(shadow.can_shadow("R0", True))
        self.assertFalse(shadow.can_shadow("R2", True))
        self.assertFalse(shadow.can_shadow("R0", False))


class TestE3RouterDeterministicSelection(unittest.TestCase):
    """The selector must use roster identity/task fit, not SQL insertion order."""

    class _Workers:
        def __init__(self):
            self.rows = {
                "generic-first": {
                    "worker_id": "generic-first", "provider": "generic",
                    "model": "generic-model", "api_model_id": "generic-model",
                    "routable": True, "capability_hints": ["reasoning"],
                },
                "code-fit": {
                    "worker_id": "code-fit", "provider": "code-provider",
                    "model": "code-model", "api_model_id": "code-model-v2",
                    "routable": True,
                    "capability_hints": ["coding", "repository", "debugging"],
                },
            }

        def get_worker(self, worker_id):
            return self.rows.get(worker_id)

    def test_task_fit_beats_insertion_order_and_identity_is_real(self):
        con = sqlite3.connect(":memory:")
        init_db(con)
        reg = CapabilityRegistry(con)
        # Deliberately insert the generic worker first.
        reg.register_worker("generic-first", "generic", "generic-model",
                            roles=["builder"], state="EVALUATING",
                            task_family="code")
        reg.register_worker("code-fit", "code-provider", "code-model",
                            roles=["builder"], state="EVALUATING",
                            task_family="code")
        router = E3Router(reg, worker_registry=self._Workers())
        node = {"capability_roles": ["builder"]}
        candidates = router.propose_candidates(node, "code")
        self.assertEqual([c.worker_id for c in candidates][:2],
                         ["code-fit", "generic-first"])
        self.assertEqual(candidates[0].provider, "code-provider")
        self.assertEqual(candidates[0].model, "code-model-v2")
        self.assertGreater(candidates[0].score, candidates[1].score)
        self.assertIn("score=", candidates[0].concise_rationale)
        con.close()


class TestDiscordE3Bridge(unittest.IsolatedAsyncioTestCase):
    """Authorized Discord traffic is handled by E3 and native Hermes is skipped."""

    @staticmethod
    def _load_bridge():
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "hermes-plugins" / "e3-discord-router" / "__init__.py"
        spec = importlib.util.spec_from_file_location("test_e3_discord_router", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    async def test_authorized_discord_message_is_sent_then_skipped(self):
        bridge = self._load_bridge()
        bridge._run_e3_sync = lambda text, context: {
            "ok": True,
            "content": "E3 says hello",
            "workers": ["longcat-2.0"],
            "family": "other",
            "role": "builder",
        }

        class Adapter:
            def __init__(self):
                self.sent = []
            async def send(self, chat_id, content, reply_to=None, metadata=None):
                self.sent.append((chat_id, content, reply_to))
                return SimpleNamespace(success=True)

        class Store:
            def __init__(self):
                self.rows = []
            def get_or_create_session(self, source):
                return SimpleNamespace(session_id="sid-1")
            def load_transcript(self, session_id):
                return [{"role": "assistant", "content": "prior"}]
            def append_to_transcript(self, session_id, message, skip_db=False):
                self.rows.append((session_id, message))

        platform = SimpleNamespace(value="discord")
        source = SimpleNamespace(platform=platform, chat_id="chan-1")
        event = SimpleNamespace(source=source, text="hello", message_id="msg-1")
        adapter = Adapter()
        gateway = SimpleNamespace(
            adapters={platform: adapter},
            _is_user_authorized_for_source=lambda src: True,
        )
        store = Store()

        result = await bridge._handle_gateway_message(
            event, gateway, store)

        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "handled-by-e3")
        self.assertEqual(len(adapter.sent), 1)
        self.assertIn("E3 says hello", adapter.sent[0][1])
        self.assertIn("longcat-2.0", adapter.sent[0][1])
        self.assertEqual([row[1]["role"] for row in store.rows],
                         ["user", "assistant"])

    async def test_unauthorized_message_falls_through_to_hermes_auth(self):
        bridge = self._load_bridge()
        platform = SimpleNamespace(value="discord")
        source = SimpleNamespace(platform=platform, chat_id="chan-1")
        event = SimpleNamespace(source=source, text="hello", message_id="msg-1")
        gateway = SimpleNamespace(
            adapters={},
            _is_user_authorized_for_source=lambda src: False,
        )
        result = await bridge._handle_gateway_message(
            event, gateway, SimpleNamespace())
        self.assertIsNone(result)


class TestColdStartBenchmark(unittest.TestCase):
    """Test Cold-Start Benchmark / Qualification Harness."""

    def setUp(self):
        self.benchmark = ColdStartBenchmark()

    def test_create_qualification_suite(self):
        suite = self.benchmark.create_qualification_suite("w1", "code", "builder")
        self.assertEqual(len(suite), 4)
        self.assertTrue(all(isinstance(t, TestCase) for t in suite))

    def test_run_qualification(self):
        result = self.benchmark.run_qualification("w1", "code", "builder")
        self.assertEqual(result.worker_id, "w1")
        self.assertEqual(result.task_family, "code")
        self.assertEqual(result.role, "builder")
        self.assertGreater(len(result.test_results), 0)
        self.assertIn(result.overall_state, [QualificationState.PASS, QualificationState.INCONCLUSIVE])

    def test_qualification_result_rate(self):
        result = QualificationResult("w1", "code", "builder")
        result.add_test_result("t1", True)
        result.add_test_result("t2", True)
        result.add_test_result("t3", False)
        self.assertAlmostEqual(result.first_pass_rate, 2/3)

    def test_benchmark_history(self):
        self.benchmark.run_qualification("w1", "code", "builder")
        history = self.benchmark.get_benchmark_history("w1")
        self.assertGreaterEqual(len(history), 1)


if __name__ == "__main__":
    unittest.main()
