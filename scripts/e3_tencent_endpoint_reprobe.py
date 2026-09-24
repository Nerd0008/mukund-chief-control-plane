#!/usr/bin/env python3
"""One bounded re-probe of the Tencent TokenHub endpoint (GET /v1/models only).

Task ``agent-provider-debug-qwen-tencent-entitlement-2026-09-24``: inspect the
exact TokenHub endpoint/key-product evidence and re-probe ``GET /v1/models`` at
most once with the stored key. No chat completion is attempted unless
authentication succeeds.

This does exactly ONE HTTPS GET to the *configured* models endpoint of the given
worker (no candidate fan-out, no completion call). The credential is resolved
in-process through the deployed adapter and used only as an ``Authorization``
header; it is never printed, logged, stored or passed as a shell argument. Only
the provider's own short error code/type is persisted for auth failures.

Usage:
    python scripts/e3_tencent_endpoint_reprobe.py --worker tencent-hunyuan-hy3
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

sys.path.insert(0, str(RUNTIME_ROOT))
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))


def reprobe(worker_id: str) -> dict:
    import generic_openai_adapter as goa

    adapter = goa.get_adapter(worker_id)
    rec = {
        "worker_id": worker_id,
        "provider_key": adapter.provider_key,
        "configured_models_endpoint": adapter.config.get("models_endpoint"),
        "configured_chat_endpoint": adapter.config.get("chat_endpoint"),
        "configured_api_model_id": adapter.config.get("api_model_id"),
        "calls": {"models_get": 1, "chat_completions": 0},
        "credential_handling": ("resolved in-process; used only as an Authorization "
                                "header; never printed, logged, stored or passed as "
                                "a shell argument"),
    }

    key, source = adapter._resolve_auth()
    rec["credential_present"] = key is not None
    rec["auth_source"] = source
    del key
    if not rec["credential_present"]:
        rec["result"] = "credential_absent"
        return rec

    status, body, _ = adapter._list_models_raw()
    rec["http_status"] = status
    rec["model_count"] = None
    rec["error_code"] = None
    rec["error_message_sanitized"] = None
    if status == 200:
        try:
            data = json.loads(body)
            ids = [m.get("id") for m in data.get("data", [])]
            rec["model_count"] = len(ids)
            rec["model_ids"] = ids
        except json.JSONDecodeError:
            rec["error_message_sanitized"] = "json_decode_failed"
    else:
        # never persist a raw auth body verbatim; keep the provider's short code
        try:
            data = json.loads(body)
            err = data.get("error") or {}
            if isinstance(err, dict):
                rec["error_code"] = err.get("code") or err.get("type")
                rec["error_message_sanitized"] = (err.get("message") or "")[:200] or None
            else:
                rec["error_code"] = data.get("code")
                rec["error_message_sanitized"] = str(data.get("message") or "")[:200] or None
        except json.JSONDecodeError:
            rec["error_message_sanitized"] = None

    # Authentication gate: a completion is only attempted when GET /models
    # authenticated (HTTP 200). It never is here, so no chat call is spent.
    rec["chat_completion_attempted"] = False
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    record = reprobe(args.worker)
    finished = datetime.now(timezone.utc)

    report = {
        "label": "e3-tencent-endpoint-reprobe",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": finished.isoformat(timespec="seconds"),
        "stage": ("single bounded GET /v1/models re-probe of the Tencent TokenHub "
                  "endpoint; no chat completion unless authentication succeeds"),
        "record": record,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-tencent-endpoint-reprobe")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    (out_dir / "evidence.md").write_text(_render_md(report), encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "worker_id": record["worker_id"],
        "models_endpoint": record.get("configured_models_endpoint"),
        "http_status": record.get("http_status"),
        "error_code": record.get("error_code"),
        "error_message_sanitized": record.get("error_message_sanitized"),
        "chat_completion_attempted": record.get("chat_completion_attempted"),
    }, indent=2))
    return 0


def _render_md(report: dict) -> str:
    r = report["record"]
    return "\n".join([
        "# E3 Tencent TokenHub endpoint re-probe (one GET /v1/models)",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Worker: `{r['worker_id']}` (provider `{r.get('provider_key')}`)",
        f"- Configured models endpoint: `{r.get('configured_models_endpoint')}`",
        f"- Configured chat endpoint: `{r.get('configured_chat_endpoint')}`",
        f"- Configured model id: `{r.get('configured_api_model_id')}`",
        f"- Calls: {r.get('calls')}",
        f"- Credential handling: {r.get('credential_handling')}",
        "",
        f"- HTTP status: `{r.get('http_status')}`",
        f"- Provider error code: `{r.get('error_code')}`",
        f"- Provider error message (sanitized): `{r.get('error_message_sanitized')}`",
        f"- Chat completion attempted: `{r.get('chat_completion_attempted')}`",
        "",
        "```json",
        json.dumps(r, indent=2),
        "```",
        "",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
