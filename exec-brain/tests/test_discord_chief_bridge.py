import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from discord_chief_bridge import dispatch_chief_message


class _E3:
    def __init__(self):
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "COMPLETED", "content": "hello", "worker_id": "stub"}


class _Career:
    def __init__(self):
        self.calls = []

    def dispatch(self, department, message, **kwargs):
        self.calls.append((department, message, kwargs))
        return {"status": "DEPARTMENT_COMPLETED", "department": department,
                "provider_call_made": False, "content": "career workflow"}


class DiscordBridgeTests(unittest.TestCase):
    def test_source_has_no_native_model_dependency(self):
        text = Path(__file__).resolve().parents[1].joinpath("discord_chief_bridge.py").read_text()
        self.assertIn("ChiefRouteSelector", text)
        self.assertNotIn("deepseek_adapter", text)
        self.assertNotIn("ExecutionAdapterRegistry", text)

    def test_authenticated_bridge_uses_injected_chief_e3_service(self):
        e3 = _E3()
        result = dispatch_chief_message("Hi", service=e3)
        self.assertEqual(result["content"], "hello")
        self.assertEqual(e3.calls[0]["required_role"], "builder")
        self.assertIn("chief_context", e3.calls[0]["context"])
        self.assertTrue(e3.calls[0]["context"]["chief_context"]["source_manifest"])

    def test_normalized_authenticated_discord_turn_reaches_department_or_e3(self):
        e3, career = _E3(), _Career()
        result = dispatch_chief_message(
            "I want 10 jobs from all the job search agents",
            context={"platform": "discord", "authenticated": True,
                     "hermes_session_preserved": True, "hermes_tools_preserved": True,
                     "hermes_skills_preserved": True},
            service=e3,
            department_dispatcher=career,
            dry_run=True,
        )
        self.assertEqual(result["status"], "DEPARTMENT_COMPLETED")
        self.assertEqual(career.calls[0][0], "career-ops")
        self.assertEqual(e3.calls, [])
        self.assertTrue(career.calls[0][2]["context"]["chief_context"]["source_manifest"])


if __name__ == "__main__":
    unittest.main()
