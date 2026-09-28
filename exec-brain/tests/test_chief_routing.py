import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chief_routing import ChiefRouteSelector


class _E3:
    def __init__(self):
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "COMPLETED", "content": "ok", "worker_id": "stub"}


class _Department:
    def __init__(self):
        self.calls = []

    def dispatch(self, department, message, **kwargs):
        self.calls.append((department, message, kwargs))
        return {"status": "DEPARTMENT_COMPLETED", "provider_call_made": False}


class ChiefRoutingTests(unittest.TestCase):
    def test_general_request_is_declared_to_e3_without_provider_selection(self):
        e3 = _E3()
        result = ChiefRouteSelector(e3).dispatch("Hi")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(e3.calls[0]["task_family"], "other")
        self.assertEqual(e3.calls[0]["required_role"], "builder")
        self.assertNotIn("provider", e3.calls[0])
        self.assertEqual(result["chief_department"], "chief")
        self.assertIn("chief_context", e3.calls[0]["context"])
        self.assertGreater(len(e3.calls[0]["context"]["chief_context"]["source_manifest"]), 0)

    def test_image_and_engineering_intents_are_semantic_not_provider_names(self):
        e3 = _E3()
        selector = ChiefRouteSelector(e3)
        selector.dispatch("Generate an image of a cat")
        selector.dispatch("Debug this GitHub repository")
        self.assertEqual((e3.calls[0]["task_family"], e3.calls[0]["required_role"]), ("other", "vision"))
        self.assertEqual((e3.calls[1]["task_family"], e3.calls[1]["required_role"]), ("code", "builder"))

    def test_career_request_never_bypasses_its_department_to_e3(self):
        e3, department = _E3(), _Department()
        result = ChiefRouteSelector(e3, department_dispatcher=department).dispatch("find me ten jobs")
        self.assertEqual(result["status"], "DEPARTMENT_COMPLETED")
        self.assertEqual(department.calls[0][0], "career-ops")
        self.assertEqual(e3.calls, [])

    def test_missing_department_handler_fails_closed(self):
        e3 = _E3()
        result = ChiefRouteSelector(e3).dispatch("review my CV")
        self.assertEqual(result["status"], "DEPARTMENT_OWNER_GATE_REQUIRED")
        self.assertFalse(result["provider_call_made"])
        self.assertEqual(e3.calls, [])


if __name__ == "__main__":
    unittest.main()
