#!/usr/bin/env python3
"""One bounded diagnostic call to capture non-secret provider rate-limit headers.

Purpose (task ``agent-provider-debug-qwen-tencent-entitlement-2026-09-24``): the
two recorded Mistral 429 responses carried only the provider message text
(``Rate limit exceeded``) and no rate-limit metadata, so the evidence could not
distinguish a transient per-request rate limit from an account/tier/monthly
quota. This script spends exactly ONE minimal chat completion
(``max_tokens<=16``, single attempt, no retry) through the *deployed* generic
adapter and records the provider's own non-secret response headers
(``Retry-After`` / ``x-ratelimit-*`` / ``ratelimit-*`` / request ids).

It never prints, logs, stores or shell-passes the credential: the key is resolved
in-process through the deployed adapter and used only as an ``Authorization``
header. Only an explicit allow-list of non-secret header names is persisted.

Usage:
    python scripts/e3_provider_rate_limit_diagnostic.py --worker mistral-small-4
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

# Non-secret, rate-limit-relevant response headers. Kept to an explicit
# allow-list so nothing unexpected can reach evidence.
ALLOWED_HEADERS = (
    "retry-after",
    "retry-after-ms",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "x-request-id",
    "request-id",
    "x-should-retry",
)

MAX_TOKENS = 16
TIMEOUT = 90
PROMPT = "Reply with the single word: READY"


def _sanitize(text, limit=200):
    """Mask anything credential-shaped before it can reach evidence."""
    if not text:
        return None
    t = str(text).strip().replace("\n", " ")
    out = []
    for token in t.split(" "):
        if len(token) > 12 and any(ch.isdigit() for ch in token) \
                and any(ch.isalpha() for ch in token):
            out.append("[redacted]")
        else:
            out.append(token)
    return " ".join(out)[:limit] or None


def probe(worker_id: str) -> dict:
    import generic_openai_adapter as goa

    rec: dict = {
        "worker_id": worker_id,
        "budget": {"max_tokens": MAX_TOKENS, "attempts": 1, "retry": False,
                   "timeout_s": TIMEOUT},
        "credential_handling": ("resolved in-process via the deployed adapter; used "
                                "only as an Authorization header; never printed, "
                                "logged, stored or passed as a shell argument"),
        "header_allowlist": list(ALLOWED_HEADERS),
    }
    adapter = goa.get_adapter(worker_id)
    rec["provider_key"] = adapter.provider_key
    rec["chat_endpoint"] = adapter.config.get("chat_endpoint")
    rec["api_model_id"] = adapter.config.get("api_model_id")

    key, source = adapter._resolve_auth()
    rec["credential_present"] = key is not None
    rec["auth_source"] = source
    if not key:
        rec["dispatch_status"] = "SKIPPED"
        rec["reason"] = "credential_absent"
        return rec

    payload = {
        "model": adapter.config["api_model_id"],
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    del key

    status, body, resp_headers = goa._http_post_json(
        adapter.config["chat_endpoint"], payload, headers, TIMEOUT)

    rec["http_status"] = status
    rec["provider_returned_headers"] = {
        k.lower(): v for k, v in (resp_headers or {}).items()
        if k.lower() in ALLOWED_HEADERS
    }
    rec["rate_limit_headers_present"] = sorted(rec["provider_returned_headers"])
    rec["provider_error_body_sanitized"] = _sanitize(
        goa._sanitize_error_body(body, status) if status != 200 else body)

    # provider-returned model field / usage, only if the call actually completed
    rec["provider_returned_model_field"] = None
    rec["usage"] = None
    if status == 200:
        try:
            data = json.loads(body)
            rec["provider_returned_model_field"] = data.get("model")
            raw = data.get("usage") or {}
            rec["usage"] = {
                "prompt_tokens": raw.get("prompt_tokens"),
                "completion_tokens": raw.get("completion_tokens"),
                "total_tokens": raw.get("total_tokens"),
            }
        except json.JSONDecodeError:
            rec["parse_error"] = "json_decode_failed"

    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    record = probe(args.worker)
    finished = datetime.now(timezone.utc)

    report = {
        "label": "e3-provider-rate-limit-diagnostic",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": finished.isoformat(timespec="seconds"),
        "stage": ("single bounded diagnostic call to capture non-secret "
                  "provider rate-limit headers (max_tokens<=16, one attempt, no retry)"),
        "record": record,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-provider-rate-limit-diagnostic")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    (out_dir / "evidence.md").write_text(_render_md(report), encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "worker_id": record["worker_id"],
        "http_status": record.get("http_status"),
        "rate_limit_headers_present": record.get("rate_limit_headers_present"),
        "provider_returned_headers": record.get("provider_returned_headers"),
        "provider_error_body_sanitized": record.get("provider_error_body_sanitized"),
    }, indent=2))
    return 0


def _render_md(report: dict) -> str:
    r = report["record"]
    lines = [
        "# E3 provider rate-limit diagnostic (one bounded call)",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Worker: `{r['worker_id']}` (provider `{r.get('provider_key')}`)",
        f"- Model: `{r.get('api_model_id')}`",
        f"- Budget: {r.get('budget')}",
        f"- Credential handling: {r.get('credential_handling')}",
        f"- Header allow-list: {r.get('header_allowlist')}",
        "",
        f"- HTTP status: `{r.get('http_status')}`",
        f"- Non-secret rate-limit headers captured: `{r.get('rate_limit_headers_present')}`",
        f"- Provider error (sanitized): `{r.get('provider_error_body_sanitized')}`",
        f"- Provider-returned model field: `{r.get('provider_returned_model_field')}`",
        f"- Usage: `{r.get('usage')}`",
        "",
        "```json",
        json.dumps(r, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
