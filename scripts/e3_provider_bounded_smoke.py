#!/usr/bin/env python3
"""Bounded real-provider smoke + live model-identity check for the E3 generic workers.

One minimal chat completion per worker, through the *deployed* execution adapter
(the same object the E3 execution path uses), so the result proves:

1. the credential resolves and is accepted by the provider at the configured
   endpoint;
2. the configured API model ID is really served — the provider-returned
   ``model`` field is recorded and compared with the configured id;
3. the adapter's provider-returned usage parsing works on a real response;
4. the E2 linkage actually writes a row through ``governor.record_request()``
   (the public E2 interface — never a direct SQL write).

Budget: one call per worker, ``max_tokens=16``, ``temperature=0``, single
attempt, no retry loop. A failing provider is recorded with its exact failure
and is simply not re-tried.

Secret handling: the credential is resolved in-process and used only as an
``Authorization`` header. It is never printed, logged, written to evidence or
passed as a shell argument. Only the store name is recorded.

Usage:
    python scripts/e3_provider_bounded_smoke.py [--out-dir DIR] [--only WORKER]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

sys.path.insert(0, str(RUNTIME_ROOT))
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

WORKERS = [
    "mistral-small-4", "glm-53-flash", "qwen38-27b", "longcat-2.0",
    "minimax-m3", "step-37-flash", "tencent-hunyuan-hy3",
]

MAX_TOKENS = 16
TIMEOUT = 90
PROMPT = "Reply with the single word: READY"

AUTH_STATUSES = (401, 403)


def _sanitize(text, limit=200):
    """Mask anything credential-shaped before it can reach evidence."""
    if not text:
        return None
    t = str(text).strip().replace("\n", " ")
    # a provider may echo a partially masked key in an error message
    out = []
    for token in t.split(" "):
        if len(token) > 12 and any(ch.isdigit() for ch in token) \
                and any(ch.isalpha() for ch in token):
            out.append("[redacted]")
        else:
            out.append(token)
    return " ".join(out)[:limit] or None


def probe_worker(worker_id: str) -> dict:
    import generic_openai_adapter as goa

    rec: dict = {"worker_id": worker_id}
    try:
        adapter = goa.get_adapter(worker_id)
    except Exception as exc:
        rec.update({"adapter_created": False, "reason": type(exc).__name__})
        return rec

    rec["adapter_created"] = True
    rec["provider_key"] = adapter.provider_key
    rec["display_name"] = adapter.config.get("display_name")
    rec["configured_api_model_id"] = adapter.config.get("api_model_id")
    rec["chat_endpoint"] = adapter.config.get("chat_endpoint")
    rec["models_endpoint"] = adapter.config.get("models_endpoint")

    key, source = adapter._resolve_auth()
    rec["credential_present"] = key is not None
    rec["auth_source"] = source
    del key
    if not rec["credential_present"]:
        rec.update({"dispatch_status": "SKIPPED", "reason": "credential_absent"})
        return rec

    contract = {
        "contract_id": f"smoke-{worker_id}-2026-09-24",
        "objective": PROMPT,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "timeout": TIMEOUT,
    }
    # LongCat enables reasoning by default.  With this smoke's deliberately
    # tiny 16-token budget that can exhaust the response before user-visible
    # content is emitted.  Disable reasoning only for this fixed one-word
    # compatibility probe; normal worker contracts retain provider defaults.
    if worker_id == "longcat-2.0":
        contract["provider_request_options"] = {"thinking": {"type": "disabled"}}
    result = adapter.dispatch(contract)
    meta = result.get("dispatch_metadata") or {}
    content = result.get("content")
    returned_model = result.get("provider_returned_model")
    rec.update({
        "dispatch_status": result.get("status"),
        "http_status": meta.get("http_status"),
        "configured_model_sent": meta.get("model"),
        "provider_returned_model_field": returned_model,
        # Identity is only confirmed when the provider itself returned the model
        # field on a successful completion. A failed call echoes the requested id
        # back through the adapter and must not be read as confirmation.
        "model_identity_confirmed_by_provider": bool(
            result.get("status") == "COMPLETED"
            and returned_model == adapter.config.get("api_model_id")),
        "finish_reason": result.get("finish_reason"),
        "usage": result.get("usage"),
        "usage_source": "provider-returned usage object (never estimated)",
        # the smoke prompt is a fixed non-sensitive string; the reply is a
        # one-word acknowledgement, captured truncated purely as proof of a real
        # completion.
        "content_preview": (content or "")[:60] or None,
        "error": _sanitize(result.get("error")),
        "provider_error_body": result.get("provider_error_body"),
        "runtime_s": round(result.get("runtime_s") or 0.0, 3),
        "max_tokens_requested": MAX_TOKENS,
    })

    # ── E2 linkage through the public interface ──────────────────────
    if result.get("status") == "COMPLETED":
        try:
            rid = goa.report_usage_to_e2(result)
            rec["e2_linkage"] = {"result": "recorded", "request_row_id": rid}
        except Exception as exc:
            rec["e2_linkage"] = {"result": "failed", "error": type(exc).__name__}
    else:
        # still report the failed attempt: usage may be null but the provider
        # error is real E2 telemetry.
        try:
            rid = goa.report_usage_to_e2(result)
            rec["e2_linkage"] = {"result": "recorded_failure",
                                 "request_row_id": rid}
        except Exception as exc:
            rec["e2_linkage"] = {"result": "failed", "error": type(exc).__name__}

    # ── live catalogue identity (GET /models) ────────────────────────
    try:
        identity = adapter.get_identity()
        rec["catalogue"] = {
            "observed_model_count": len(identity.get("observed_models") or []),
            "configured_model_in_catalogue": (
                adapter.config["api_model_id"] in
                [m.get("id") for m in identity.get("observed_models") or []]),
        }
    except Exception as exc:
        rec["catalogue"] = {"error": type(exc).__name__}

    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--only", default=None)
    args = parser.parse_args()

    workers = [args.only] if args.only else WORKERS
    started = datetime.now(timezone.utc)

    results = [probe_worker(w) for w in workers]

    finished = datetime.now(timezone.utc)
    completed = [r["worker_id"] for r in results
                 if r.get("dispatch_status") == "COMPLETED"]
    failed = [r["worker_id"] for r in results
              if r.get("dispatch_status") == "FAILED"]
    skipped = [r["worker_id"] for r in results
               if r.get("dispatch_status") == "SKIPPED"]
    identity_confirmed = [r["worker_id"] for r in results
                          if r.get("model_identity_confirmed_by_provider")]

    report = {
        "label": "e3-provider-bounded-smoke",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": finished.isoformat(timespec="seconds"),
        "stage": ("bounded real-provider smoke + live model-identity check "
                  "(one call per worker, max_tokens=16, no retries)"),
        "budget": {"max_tokens_per_worker": MAX_TOKENS, "timeout_s": TIMEOUT,
                   "attempts_per_worker": 1},
        "credential_handling": ("resolved in-process, used only as an "
                                "Authorization header; never printed, logged, "
                                "stored or passed as a shell argument"),
        "workers": results,
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "model_identity_confirmed": identity_confirmed,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-provider-bounded-smoke")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    (out_dir / "evidence.md").write_text(_render_md(report), encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "model_identity_confirmed": identity_confirmed,
        "per_worker": {
            r["worker_id"]: {
                "dispatch": r.get("dispatch_status"),
                "http": r.get("http_status"),
                "sent_model": r.get("configured_model_sent"),
                "returned_model_field": r.get("provider_returned_model_field"),
                "identity_confirmed": r.get("model_identity_confirmed_by_provider"),
                "provider_error_body": r.get("provider_error_body"),
                "error": r.get("error"),
                "e2": (r.get("e2_linkage") or {}).get("result"),
            } for r in results
        },
    }, indent=2))
    return 0


def _render_md(report: dict) -> str:
    lines = [
        "# E3 bounded real-provider smoke + live model identity",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Budget: {report['budget']}",
        f"- Credential handling: {report['credential_handling']}",
        f"- Completed: {report['completed']}",
        f"- Failed: {report['failed']}",
        f"- Skipped: {report['skipped']}",
        "",
        "| Worker | Endpoint | HTTP | Model sent | Returned model field | "
        "Identity confirmed | Tokens (in/out) | E2 linkage | Error |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["workers"]:
        usage = r.get("usage") or {}
        tokens = f"{usage.get('prompt_tokens')}/{usage.get('completion_tokens')}"
        lines.append(
            f"| {r['worker_id']} | {r.get('provider_key')} | "
            f"{r.get('http_status')} | `{r.get('configured_api_model_id')}` | "
            f"`{r.get('provider_returned_model_field')}` | "
            f"{r.get('model_identity_confirmed_by_provider')} | {tokens} | "
            f"{(r.get('e2_linkage') or {}).get('result')} | "
            f"{r.get('provider_error_body') or r.get('error') or ''} |")
    lines += ["", "## Per-worker detail", ""]
    for r in report["workers"]:
        lines += [f"### {r['worker_id']}", "",
                  f"```json\n{json.dumps(r, indent=2)}\n```", ""]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
