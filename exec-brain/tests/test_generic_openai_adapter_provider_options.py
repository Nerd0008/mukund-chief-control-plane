"""Offline coverage for opt-in generic-provider request options."""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

import generic_openai_adapter as goa  # noqa: E402


class ProviderRequestOptionsTests(unittest.TestCase):
    def setUp(self):
        self.original_post = goa._http_post_json
        self.adapter = goa.GenericOpenAIAdapter("longcat")
        self.adapter._key = "offline-test-key"
        self.adapter._auth_source = "test"
        self.payloads = []

        def fake_post(url, payload, headers, timeout):
            self.payloads.append(payload)
            return 200, json.dumps({
                "model": "LongCat-2.0",
                "choices": [{"message": {"content": "READY"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                          "total_tokens": 2},
            }), {}

        goa._http_post_json = fake_post
        self.addCleanup(self._restore)

    def _restore(self):
        goa._http_post_json = self.original_post

    def test_longcat_visible_response_default_is_sent(self):
        result = self.adapter.dispatch({
            "contract_id": "offline-default-options", "objective": "x",
        })
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(self.payloads[0]["thinking"], {"type": "disabled"})

    def test_contract_options_override_the_provider_default(self):
        result = self.adapter.dispatch({
            "contract_id": "offline-options", "objective": "x",
            "provider_request_options": {"thinking": {"type": "enabled"}},
        })
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(self.payloads[0]["thinking"], {"type": "enabled"})
        self.assertEqual(self.payloads[0]["model"], "LongCat-2.0")

    def test_invalid_options_fail_before_network_dispatch(self):
        result = self.adapter.dispatch({
            "contract_id": "offline-invalid", "objective": "x",
            "provider_request_options": "disabled",
        })
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"], "invalid_provider_request_options")
        self.assertEqual(self.payloads, [])


if __name__ == "__main__":
    unittest.main()
