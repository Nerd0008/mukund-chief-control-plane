import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from department_dispatch import CareerOpsDepartment, DefaultDepartmentDispatcher


class CareerDepartmentTests(unittest.TestCase):
    def test_all_agents_request_reaches_real_read_only_workflow(self):
        result = DefaultDepartmentDispatcher().dispatch(
            "career-ops", "I want 10 jobs from all the job search agents", dry_run=True
        )
        self.assertEqual(result["status"], "DEPARTMENT_COMPLETED")
        self.assertEqual(result["department"], "career-ops")
        self.assertEqual(result["workflow"], "discovery.scheduled_orchestrator")
        self.assertEqual(result["regions"], ["uk", "dubai", "japan", "singapore"])
        self.assertEqual(result["requested_count"], 10)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["provider_call_made"])
        self.assertNotIn("DEPARTMENT_HANDOFF_REQUIRED", result["content"])

    def test_status_uses_run_health_without_provider(self):
        result = CareerOpsDepartment().dispatch("career ops status", dry_run=True)
        self.assertEqual(result["operation"], "run-health")
        self.assertFalse(result["provider_call_made"])
        self.assertTrue(result["read_only"])

    def test_dry_run_never_invokes_unified_orchestrator(self):
        class Fake:
            def __init__(self): self.calls = 0
            def run_all(self, **kwargs): self.calls += 1; return {"canonical_candidates": []}
        fake = Fake()
        result = CareerOpsDepartment(allow_external=True, orchestrator=fake).dispatch(
            "10 jobs from all regions", dry_run=True)
        self.assertFalse(result["executed"] if "executed" in result else False)
        self.assertEqual(fake.calls, 0)

    def test_activation_invokes_unified_orchestrator_and_bounds_results(self):
        class Fake:
            def __init__(self): self.calls = []
            def run_all(self, **kwargs):
                self.calls.append(kwargs)
                return {"canonical_candidates": [{"id": i} for i in range(99)],
                        "read_only": True, "provider_call_made": False}
        fake = Fake()
        result = CareerOpsDepartment(allow_external=True, orchestrator=fake).dispatch(
            "I want 2 jobs from all the job search agents", dry_run=False)
        self.assertTrue(result["executed"])
        self.assertEqual(len(result["result"]["canonical_candidates"]), 8)
        self.assertEqual(fake.calls[0]["regions"], ["uk", "dubai", "japan", "singapore"])
        self.assertFalse(result["provider_call_made"])


if __name__ == "__main__":
    unittest.main()
