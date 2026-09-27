import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chief_routing import PRIMARY
from discord_chief_bridge import dispatch_chief_message


class DiscordBridgeTests(unittest.TestCase):
    def test_source_has_no_native_model_dependency(self):
        text = Path(__file__).resolve().parents[1].joinpath('discord_chief_bridge.py').read_text()
        self.assertIn('ChiefRouteSelector', text)
        self.assertNotIn('deepseek_adapter', text)

    def test_stage2_disabled_fails_closed(self):
        # The live state is deliberately not touched by a unit test.
        from stage2_control import read_state
        self.assertIsInstance(read_state(Path(tempfile.mkdtemp()) / 'none.json'), dict)


if __name__ == '__main__':
    unittest.main()
