#!/usr/bin/env python3
"""Bounded live endpoint + model-identity probe for the E3 generic providers.

Purpose: establish, from the provider's own API rather than from a marketing
name or a stale hard-coded string, *which* base URL answers and *which* model
IDs that account can actually see.

Properties (all deliberate):
* read-only — GET /models only. No chat/completion call is made here, so this
  script spends no provider tokens;
* bounded — one attempt per candidate endpoint, no retry loop, short timeout;
* secret-safe — the credential is resolved in-process and used only as an
  ``Authorization`` header. It is never printed, logged, written to evidence or
  passed as a shell argument. Only the *store name* is recorded;
* truthful — an endpoint that does not answer is recorded with its exact HTTP
  status or exception class, never smoothed over.

Usage:
    python scripts/e3_provider_live_identity_probe.py [--out-dir DIR]
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# Deployed runtime first (what actually executes), repo second (source of truth).
sys.path.insert(0, str(RUNTIME_ROOT))
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

import generic_openai_adapter as goa  # noqa: E402

# Candidate ``/models`` endpoints per provider. The first entry per provider is
# the currently configured registry value; the rest are the plausible
# international/regional variants that must be discriminated by evidence rather
# than assumed.
CANDIDATE_ENDPOINTS = {
    "mistral": [
        ("configured", "https://api.mistral.ai/v1/models"),
    ],
    "glm": [
        ("z_ai_configured", "https://api.z.ai/api/paas/v4/models"),
        ("bigmodel_cn_alternate", "https://open.bigmodel.cn/api/paas/v4/models"),
    ],
    "qwen": [
        ("dashscope_intl_configured", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models"),
        ("dashscope_cn_alternate", "https://dashscope.aliyuncs.com/compatible-mode/v1/models"),
    ],
    "minimax": [
        ("configured_minimax_io", "https://api.minimax.io/v1/models"),
        ("minimaxi_cn_alternate", "https://api.minimaxi.com/v1/models"),
    ],
    "longcat": [
        ("configured_openai_path", "https://api.longcat.chat/openai/v1/models"),
        ("direct_openai_root_alternate", "https://api.longcat.chat/v1/models"),
    ],
    "stepfun": [
        ("stepfun_global_configured", "https://api.stepfun.ai/v1/models"),
        ("stepfun_cn_alternate", "https://api.stepfun.com/v1/models"),
    ],
    "hunyuan": [
        ("tokenhub_intl_configured", "https://tokenhub-intl.tencentcloudmaas.com/v1/models"),
        ("tokenhub_guangzhou_cn", "https://tokenhub.tencentcloudmaas.com/v1/models"),
        ("tokenhub_us_siliconvalley", "https://tokenhub-us.tencentcloudmaas.com/v1/models"),
        ("legacy_lkeap_cn", "https://api.lkeap.cloud.tencent.com/v1/models"),
        ("legacy_hunyuan_cloud_cn", "https://api.hunyuan.cloud.tencent.com/v1/models"),
    ],
}

TIMEOUT = 20
MAX_MODELS_RECORDED = 400

# Where a provider's credential is rejected by every reachable host, the
# configured endpoint/model mapping must still be derived from something
# authoritative rather than typed. These are the provider's own documentation
# pages that establish the mapping.
DOCUMENTATION_CITATIONS = {
    "hunyuan": {
        "endpoint": ("https://www.tencentcloud.com/document/product/1300/78941 "
                     "— TokenHub API domain table (Singapore/global: "
                     "https://tokenhub-intl.tencentcloudmaas.com)"),
        "model_id": ("https://www.tencentcloud.com/document/product/1300/80632 "
                     "— supported-model table: Hy3 -> `hy3`"),
    },
}

# Never store provider error prose for authentication failures: some providers
# echo a partially masked credential back in the message. The classification is
# what carries evidence value; the raw text does not.
AUTH_STATUSES = (401, 403)

_SUSPECT = re.compile(
    r"(?=[A-Za-z0-9_\-]*[A-Z])(?=[A-Za-z0-9_\-]*[a-z])(?=[A-Za-z0-9_\-]*[0-9])"
    r"[A-Za-z0-9_\-]{10,}"
    r"|\*{3,}"
    r"|sk-[A-Za-z0-9_\-]+"
    r"|[Bb]earer\s+\S+")


def _sanitize(text):
    """Mask anything credential-shaped before it can reach evidence."""
    if not text:
        return None
    t = _SUSPECT.sub("[redacted]", text.strip().replace("\n", " "))
    return (t[:200] or None)


def _classify_error(body: str) -> str:
    """Extract the provider's own short error code/type, without prose."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return "unparsable_error_body"
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        for field in ("code", "type"):
            val = err.get(field)
            if isinstance(val, str) and val:
                return val[:60]
        return "error_object_without_code"
    if isinstance(err, str):
        return "error_string"
    for field in ("code", "type", "message"):
        val = data.get(field)
        if isinstance(val, str) and val:
            return val[:60]
    return "unknown_error_shape"



def probe_endpoint(models_url: str, key: str) -> dict:
    """One bounded GET /models. Never logs the credential."""
    req = urllib.request.Request(
        models_url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
    except Exception as e:  # network/DNS/timeout — record the exact class
        return {"http_status": None, "exception": type(e).__name__,
                "detail": str(e)[:200], "model_ids": [], "model_count": None,
                "body_excerpt": None}

    model_ids = []
    parse_error = None
    try:
        data = json.loads(body)
        entries = data.get("data") if isinstance(data, dict) else None
        if entries is None and isinstance(data, dict):
            entries = data.get("models")
        for m in (entries or []):
            if isinstance(m, dict):
                mid = m.get("id") or m.get("model") or m.get("name")
                if mid:
                    model_ids.append(mid)
            elif isinstance(m, str):
                model_ids.append(m)
    except json.JSONDecodeError:
        parse_error = "response_not_json"

    excerpt = None
    error_class = None
    if status is not None and status != 200:
        if status in AUTH_STATUSES:
            # never persist provider prose for auth failures (key echo risk)
            error_class = _classify_error(body)
        else:
            error_class = _classify_error(body)
            excerpt = _sanitize(body)

    return {
        "http_status": status,
        "exception": None,
        "detail": None,
        "model_count": len(model_ids),
        "model_ids": model_ids[:MAX_MODELS_RECORDED],
        "model_ids_truncated": len(model_ids) > MAX_MODELS_RECORDED,
        "parse_error": parse_error,
        "error_class": error_class,
        "body_excerpt": excerpt,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    results = {}
    touched_models = set()

    for provider_key, candidates in CANDIDATE_ENDPOINTS.items():
        config = goa.PROVIDER_CONFIGS[provider_key]
        key, source = goa._resolve_key(config)
        configured_model = config.get("api_model_id")
        entry = {
            "provider_key": provider_key,
            "configured_base_url": config.get("base_url"),
            "configured_models_endpoint": config.get("models_endpoint"),
            "configured_chat_endpoint": config.get("chat_endpoint"),
            "configured_api_model_id": configured_model,
            "credential_present": key is not None,
            "auth_source": source,
            "credential_target": config.get("credential_target"),
            "env_var": config.get("env_var"),
            "candidates": [],
        }
        del key  # presence was all we needed before the loop; re-resolved below

        for label, url in candidates:
            key, source = goa._resolve_key(config)
            if key is None:
                entry["candidates"].append({
                    "label": label, "models_url": url,
                    "http_status": None, "exception": "credential_absent",
                    "model_ids": [], "model_count": None})
                continue
            res = probe_endpoint(url, key)
            del key
            res.update({"label": label, "models_url": url})
            entry["candidates"].append(res)

        reachable = [c for c in entry["candidates"] if c.get("http_status") == 200]
        entry["reachable_candidates"] = [c["label"] for c in reachable]
        entry["configured_endpoint_reachable"] = any(
            "configured" in c["label"] and c.get("http_status") == 200
            for c in entry["candidates"])
        entry["configured_model_observed"] = any(
            configured_model in c.get("model_ids", []) for c in reachable)
        entry["observed_catalogue_size"] = max(
            [c.get("model_count") or 0 for c in reachable] or [0])
        citations = DOCUMENTATION_CITATIONS.get(provider_key)
        entry["documentation_citations"] = citations or None
        # Only claim documentation backing when live catalogue observation is not
        # available for this provider.
        entry["authoritative_documentation_backed"] = bool(
            citations) and not (entry["configured_endpoint_reachable"]
                                and entry["configured_model_observed"])
        results[provider_key] = entry

    finished = datetime.now(timezone.utc)
    report = {
        "label": "e3-provider-live-identity-probe",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": finished.isoformat(timespec="seconds"),
        "stage": ("bounded live GET /models endpoint + model-identity probe for "
                  "the E3 generic providers — read-only, no completion calls"),
        "provider_chat_calls_spent": 0,
        "credential_handling": ("resolved in-process, used only as an "
                                "Authorization header; no value printed, logged, "
                                "stored or passed as a shell argument"),
        "providers": results,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-provider-live-identity-probe")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    (out_dir / "evidence.md").write_text(_render_md(report), encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "summary": {
            p: {
                "reachable": v["reachable_candidates"],
                "configured_endpoint_reachable": v["configured_endpoint_reachable"],
                "configured_model_observed": v["configured_model_observed"],
                "configured_model": v["configured_api_model_id"],
                "catalogue_size": v["observed_catalogue_size"],
            } for p, v in results.items()
        },
    }, indent=2))
    return 0


def _render_md(report: dict) -> str:
    lines = [
        "# E3 provider live endpoint / model-identity probe",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Provider completion calls spent: {report['provider_chat_calls_spent']}",
        f"- Credential handling: {report['credential_handling']}",
        "",
    ]
    for p, v in report["providers"].items():
        lines += [
            f"## {p}",
            "",
            f"- credential present: `{v['credential_present']}` "
            f"(source `{v['auth_source']}`, target `{v['credential_target']}`)",
            f"- configured model id: `{v['configured_api_model_id']}`",
            f"- configured endpoint reachable: `{v['configured_endpoint_reachable']}`",
            f"- configured model id observed in catalogue: "
            f"`{v['configured_model_observed']}`",
            f"- authoritative-documentation backed: "
            f"`{v.get('authoritative_documentation_backed')}`",
            "",
            "| Candidate | /models URL | HTTP | Models | Note |",
            "|---|---|---|---|---|",
        ]
        for c in v["candidates"]:
            note = (c.get("exception") or c.get("error_class")
                    or c.get("parse_error") or c.get("body_excerpt") or "")
            lines.append(
                f"| {c['label']} | `{c['models_url']}` | {c.get('http_status')} | "
                f"{c.get('model_count')} | {note} |")
        lines.append("")
        if v["observed_catalogue_size"]:
            all_ids = []
            for c in v["candidates"]:
                for mid in c.get("model_ids") or []:
                    if mid not in all_ids:
                        all_ids.append(mid)
            lines.append("Observed model IDs: " +
                         ", ".join(f"`{m}`" for m in all_ids[:60]))
            lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
