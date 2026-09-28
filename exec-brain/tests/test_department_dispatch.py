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


if __name__ == "__main__":
    unittest.main()
