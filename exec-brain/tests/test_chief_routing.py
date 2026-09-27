import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chief_routing import ChiefRouteSelector, DISABLED_WORKERS


class _Workers:
    def __init__(self, ids):
        self.rows = {wid: {"routable": True} for wid in ids}
    def get_worker(self, wid): return self.rows.get(wid)


class _Adapter:
    def __init__(self, result): self.result = result
    def dispatch(self, contract): return dict(self.result)


class _Adapters:
    def __init__(self, results): self.results = results; self.reported = []
    def is_routable(self, wid): return wid in self.results
    def adapter_for(self, wid): return _Adapter(self.results[wid])
    def report_usage(self, wid, result): self.reported.append(wid)


def _ok(worker):
    return {"status": "COMPLETED", "content": "ok", "provider": worker,
            "model": worker, "usage": {}}


class ChiefRoutingTests(unittest.TestCase):
    def selector(self, results):
        return ChiefRouteSelector(_Workers(results), _Adapters(results), allowed_workers=results)

    def test_general_prefers_longcat(self):
        selector = self.selector({"longcat-2.0": _ok("longcat")})
        self.assertEqual(selector.dispatch("Hi")['worker_id'], "longcat-2.0")

    def test_deepseek_failure_falls_back_to_codex(self):
        selector = self.selector({
            "deepseek-v41-flash": {"status": "FAILED", "error": "http_402 insufficient credit"},
            "codex-cli": _ok("codex"),
        })
        # LongCat unavailable causes DeepSeek to be tried; its 402 cannot kill Chief.
        result = selector.dispatch("Hi")
        self.assertEqual(result['worker_id'], "codex-cli")
        self.assertEqual(result['attempts'][0]['worker_id'], "deepseek-v41-flash")
        self.assertTrue(result['attempts'][0]['provider_failure'])

    def test_image_uses_google_only(self):
        selector = self.selector({"google-nano-banana-2": _ok("google")})
        self.assertEqual(selector.dispatch("Generate an image of a cat")['worker_id'], "google-nano-banana-2")

    def test_image_completion_without_text_is_successful(self):
        selector = self.selector({"google-nano-banana-2": {
            "status": "COMPLETED", "content": None, "image_b64": "aW1hZ2U=",
            "image_mime": "image/png", "provider": "google", "model": "image",
        }})
        self.assertEqual(selector.dispatch("Draw an image")['worker_id'], "google-nano-banana-2")

    def test_engineering_uses_codex(self):
        selector = self.selector({"codex-cli": _ok("codex")})
        self.assertEqual(selector.dispatch("Debug this GitHub repository")['worker_id'], "codex-cli")

    def test_discontinued_workers_never_enter_candidate_list(self):
        selector = self.selector({wid: _ok(wid) for wid in DISABLED_WORKERS})
        decision = selector.select("Hi")
        self.assertEqual(decision.candidates, [])


if __name__ == '__main__':
    unittest.main()
