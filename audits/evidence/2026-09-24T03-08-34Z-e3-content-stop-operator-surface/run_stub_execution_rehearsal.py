#!/usr/bin/env python3
"""Offline stub-provider run of the E3 production-execution rehearsal driver.

Drives the *real* ``E3ExecutionRehearsal.run()`` code path (scenario construction,
dispatch, DAG/evidence persistence read-back, bounded-usage accounting, the
decomposed multi-worker plan, the refusal scenario and the provider
content-side stop terminal scenario) with deterministic stub execution adapters
injected for the routable workers.

* 0 real provider calls, 0 credentials read, 0 network use.
* The orchestration DB is an isolated scratch store outside the live runtime
  root; the live rehearsal-evidence isolation proof still runs unchanged.
* This artifact is a *stub-provider* rehearsal. It is not a real-provider
  rehearsal and must never be reported as one.

Usage: python run_stub_execution_rehearsal.py [--out PATH]
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import e3_execution  # noqa: E402
import e3_execution_rehearsal as R  # noqa: E402

TOKENS = (R.TOKEN_REPAIR, R.TOKEN_FIRSTPASS, R.TOKEN_CODEX,
          R.TOKEN_NODE_BUILDER, R.TOKEN_NODE_INTEGRATOR)


class StubAdapter:
    """Deterministic stub standing in for a real worker adapter."""

    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.calls = []

    def dispatch(self, contract):
        self.calls.append(dict(contract))
        objective = contract["objective"]
        token = next((t for t in TOKENS if t in objective), None)
        if self.worker_id == "google-nano-banana-2":
            return {"dispatch_id": "gem-1", "status": "COMPLETED",
                    "provider": "google", "model": "gemini-3.1-flash-image",
                    "content": None, "image_size_bytes": 128,
                    "image_decode_ok": True, "usage": {"totalTokenCount": 10},
                    "error": None, "exit_code": 0, "runtime_s": 1.0}
        # The first deepseek call of the run deliberately never matches, so the
        # rejection -> targeted repair -> re-verify path is exercised.
        if self.worker_id == "deepseek-v41-flash" and len(self.calls) == 1:
            content = "I am an assistant."
        else:
            content = token or ""
        return {"dispatch_id": f"stub-{len(self.calls)}", "status": "COMPLETED",
                "provider": "openai" if self.worker_id == "codex-cli" else "deepseek",
                "model": "stub-model", "content": content,
                "usage": {"total_tokens": 11}, "error": None, "exit_code": 0,
                "runtime_s": 0.1}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    saved_factory = e3_execution._default_adapter_factory
    saved_reporter = e3_execution._default_usage_reporter
    adapters = {}

    def factory(spec):
        key = spec["class"]
        worker_id = {"DeepSeekExecutionAdapter": "deepseek-v41-flash",
                     "CodexExecutionAdapter": "codex-cli",
                     "GeminiImageExecutionAdapter": "google-nano-banana-2",
                     }.get(key, key)

        def build():
            if key not in adapters:
                adapters[key] = StubAdapter(worker_id)
            return adapters[key]
        return build

    e3_execution._default_adapter_factory = factory
    e3_execution._default_usage_reporter = (
        lambda spec: (lambda result: "gov-stub-1"))
    try:
        tmp = Path(tempfile.mkdtemp(prefix="e3-exec-reh-stub-"))
        rehearsal = R.E3ExecutionRehearsal(db_path=tmp / "orchestration.db",
                                          scratch_root=tmp / "scratch")
        report = rehearsal.run(include_codex=True, include_google=True,
                               include_multi_node=True)
    finally:
        e3_execution._default_adapter_factory = saved_factory
        e3_execution._default_usage_reporter = saved_reporter

    report["artifact_note"] = (
        "STUB-PROVIDER run: every adapter was an injected deterministic stub. "
        "0 real provider calls, no credential read, no network use. This is not "
        "a real-provider rehearsal. ``bounded_usage.real_provider_calls`` below "
        "counts dispatches routed through the injected stubs, NOT provider "
        "calls spent; ``provider_calls_actually_spent`` is 0.")
    report["provider_calls_actually_spent"] = 0
    report["injected_stub_adapters"] = True
    out_path = Path(args.out) if args.out else (Path(__file__).resolve().parent /
                                                "execution_rehearsal_stub_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str),
                        encoding="utf-8")

    by_name = {s["scenario"]: s for s in report["scenarios"]}
    content_stop = by_name.get("G_content_stop_terminal", {})
    summary = {
        "artifact": str(out_path),
        "provider_calls_actually_spent": 0,
        "dispatches_through_injected_stubs":
            report["bounded_usage"]["real_provider_calls"],
        "stub_only_dispatch_count": report["bounded_usage"]["stub_only_dispatch_count"],
        "checks_all_true": all(v for v in report["checks"].values()
                               if v is not None),
        "checks_false": [k for k, v in report["checks"].items() if v is False],
        "content_stop_terminal_path_recorded":
            content_stop.get("content_stop_terminal_path_recorded"),
        "content_stop_finish_reason": content_stop.get("content_stop_finish_reason"),
        "content_stop_retry_budget": content_stop.get("content_stop_retry_budget"),
        "content_stop_retry_count": content_stop.get("content_stop_retry_count"),
        "content_stop_stub_dispatch_calls": content_stop.get("stub_dispatch_calls"),
        "content_stop_node_state": content_stop.get("node_state"),
        "content_stop_failure_attribution": content_stop.get("failure_attribution"),
        "content_stop_blocking_reason": content_stop.get("blocking_reason"),
        "content_stop_escalation": content_stop.get("content_stop_escalation"),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0 if (summary["content_stop_terminal_path_recorded"]
                 and summary["checks_all_true"]
                 and summary["provider_calls_actually_spent"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
