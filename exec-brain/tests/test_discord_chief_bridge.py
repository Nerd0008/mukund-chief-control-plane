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


if __name__ == "__main__":
    unittest.main()
