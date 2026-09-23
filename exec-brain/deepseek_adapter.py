#!/usr/bin/env python3
"""E3 DeepSeek ExecutionAdapter — chat completions via DeepSeek API.

Distinct from E2 telemetry (probe_deepseek). Reuses only:
- key access helper (deepseek_keyaccess.py, D2 policy)
- provider configuration (deepseek-config.json budget)

Usage capture: provider-returned usage fields only, never estimated.
E2 linkage: observed requests reported through governor.record_request()
public interface — never direct SQL writes to governor.db.
"""

import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import deepseek_keyaccess as dc

API_BASE = "https://api.deepseek.com"
MODELS_ENDPOINT = f"{API_BASE}/models"
CHAT_ENDPOINT = f"{API_BASE}/chat/completions"

GOV_DIR = Path(__file__).parent


def _http_post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str],
                    timeout: int) -> tuple:
    """Safe HTTP POST returning (status, body, response_headers)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)
    except Exception as e:
        return -1, json.dumps({"error": f"{type(e).__name__}: {e}"}), {}


class DeepSeekExecutionAdapter:
    """E3 ExecutionAdapter for DeepSeek chat completions."""

    def __init__(self, model: str = "deepseek-flash"):
        self.model = model
        self.auth_source = dc.key_source()

    # ─── Interface: health / identity ─────────────────────────────

    def check_health(self) -> Dict[str, Any]:
        """Verify credential presence + API reachability via /models."""
        present = dc.credential_manager_entry_present() or dc.env_var_present()
        if not present:
            return {"status": "unhealthy", "reason": "credential_absent",
                    "auth_source": "none"}
        status, body, _ = self._list_models_raw()
        if status == 200:
            return {"status": "healthy", "auth_source": self.auth_source}
        if status == 401:
            return {"status": "unhealthy", "reason": "authentication_failed"}
        if status == 429:
            return {"status": "degraded", "reason": "rate_limited"}
        return {"status": "unhealthy", "reason": f"http_{status}"}

    def get_identity(self) -> Dict[str, Any]:
        """Identity from OBSERVED provider data only."""
        identity = {
            "provider": "deepseek",
            "display_name": "DeepSeek V4.1 Flash",
            "api_model_id": None,  # observed from /models or generation
            "observed_models": [],
            "auth_source": self.auth_source,
            "interface": "https://api.deepseek.com/chat/completions",
            "cancellation_support": "SUPPORTED_PROCESS_KILL",
            "e2_usage_linkage": "NOT_VERIFIED",
        }
        status, body, _ = self._list_models_raw()
        if status == 200:
            try:
                data = json.loads(body)
                for m in data.get("data", []):
                    identity["observed_models"].append({
                        "id": m.get("id"),
                        "owned_by": m.get("owned_by"),
                    })
                ids = [m["id"] for m in identity["observed_models"] if m.get("id")]
                if self.model in ids:
                    identity["api_model_id"] = self.model
            except json.JSONDecodeError:
                pass
        return identity

    # ─── Interface: dispatch / retrieve / cancel ──────────────────

    def dispatch(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a chat completion. Synchronous (blocking) call."""
        dispatch_id = f"ds-{uuid.uuid4().hex[:12]}"
        contract_id = contract.get("contract_id", "unknown")
        objective = contract.get("objective", "")
        model = contract.get("model", self.model)
        timeout = contract.get("timeout", 120)
        max_tokens = contract.get("max_tokens", 1024)
        temperature = contract.get("temperature", 0.0)

        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": objective}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        key = dc.get_deepseek_key()
        if not key:
            return self._error_result(dispatch_id, contract_id, objective,
                                      "credential_absent", timeout)

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        start = time.time()
        status, body, resp_headers = _http_post_json(
            CHAT_ENDPOINT, payload, headers, timeout
        )
        elapsed = time.time() - start

        return self._build_result(dispatch_id, contract_id, objective, model,
                                  status, body, resp_headers, elapsed, timeout)

    def retrieve(self, dispatch_id: str) -> Optional[Dict[str, Any]]:
        """Synchronous API — results are returned inline by dispatch()."""
        return None

    def cancel(self, dispatch_id: str) -> bool:
        """Cancellation: process-kill only (synchronous request).

        The HTTP call runs inside dispatch(); there is no server-side
        job to cancel. TIMEOUT is enforced client-side.
        """
        return False

    # ─── Telemetry capture (provider-returned values only) ────────

    def _build_result(self, dispatch_id, contract_id, objective, model,
                      status, body, resp_headers, elapsed, timeout):
        usage = None
        content = None
        finish_reason = None
        response_model = None
        reasoning_tokens = None
        prompt_cache_hit = None
        prompt_cache_miss = None
        error = None

        if status == 200:
            try:
                data = json.loads(body)
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content")
                    finish_reason = choices[0].get("finish_reason")
                response_model = data.get("model")
                raw_usage = data.get("usage") or {}
                usage = {
                    "prompt_tokens": raw_usage.get("prompt_tokens"),
                    "completion_tokens": raw_usage.get("completion_tokens"),
                    "total_tokens": raw_usage.get("total_tokens"),
                    "reasoning_tokens": (
                        raw_usage.get("prompt_tokens_details", {}).get("reasoning_tokens")
                        if isinstance(raw_usage.get("prompt_tokens_details"), dict)
                        else raw_usage.get("reasoning_tokens")
                    ),
                    "prompt_cache_hit_tokens": (
                        raw_usage.get("prompt_cache_hit_tokens")
                        or raw_usage.get("prompt_tokens_details", {}).get(
                            "cached_tokens")
                        if isinstance(raw_usage.get("prompt_tokens_details"), dict)
                        or raw_usage.get("prompt_cache_hit_tokens")
                        else None
                    ),
                    "prompt_cache_miss_tokens": raw_usage.get("prompt_cache_miss_tokens"),
                }
            except json.JSONDecodeError:
                error = "response_json_decode_failed"
        elif status in (400, 401, 402, 403, 422, 429):
            try:
                err_data = json.loads(body)
                error = (err_data.get("error", {}).get("message")
                         or err_data.get("error") or f"http_{status}")
            except (json.JSONDecodeError, AttributeError):
                error = f"http_{status}"
        else:
            error = f"http_{status}"

        return {
            "dispatch_id": dispatch_id,
            "status": "COMPLETED" if status == 200 and content is not None else "FAILED",
            "provider": "deepseek",
            "model": response_model or model,
            "content": content,
            "finish_reason": finish_reason,
            "usage": usage,
            "error": error,
            "exit_code": 0 if status == 200 else status,
            "runtime_s": elapsed,
            "response_headers": {
                k.lower(): v for k, v in resp_headers.items()
                if k.lower() in ("x-request-id", "request-id")
            },
            "dispatch_metadata": self._sanitized_metadata(
                dispatch_id, contract_id, objective, model, elapsed,
                status, timeout
            ),
        }

    def _sanitized_metadata(self, dispatch_id, contract_id, objective,
                            model, elapsed, status, timeout):
        """Sanitized dispatch metadata — no raw objective, no secrets."""
        objective_hash = hashlib.sha256(objective.encode()).hexdigest()[:12]
        summary = objective[:50] + "..." if len(objective) > 50 else objective
        return {
            "dispatch_id": dispatch_id,
            "contract_id": contract_id,
            "provider": "deepseek",
            "model": model,
            "objective_hash": objective_hash,
            "objective_summary": summary,
            "api_endpoint": CHAT_ENDPOINT,
            "auth_source": self.auth_source,
            "timeout": timeout,
            "elapsed_seconds": elapsed,
            "http_status": status,
            "exit_status": "ok" if status == 200 else f"http_{status}",
        }

    def _error_result(self, dispatch_id, contract_id, objective, reason, timeout):
        objective_hash = hashlib.sha256(objective.encode()).hexdigest()[:12]
        return {
            "dispatch_id": dispatch_id,
            "status": "FAILED",
            "provider": "deepseek",
            "model": self.model,
            "content": None,
            "usage": None,
            "error": reason,
            "exit_code": -1,
            "runtime_s": 0.0,
            "dispatch_metadata": {
                "dispatch_id": dispatch_id,
                "contract_id": contract_id,
                "provider": "deepseek",
                "model": self.model,
                "objective_hash": objective_hash,
                "auth_source": "none",
                "timeout": timeout,
                "exit_status": reason,
            },
        }

    def _list_models_raw(self):
        """GET /models with in-process credential. Never logs the key."""
        key = dc.get_deepseek_key()
        if not key:
            return -1, json.dumps({"error": "credential_absent"}), {}
        req = urllib.request.Request(
            MODELS_ENDPOINT, headers={"Authorization": f"Bearer {key}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), dict(e.headers)
        except Exception as e:
            return -1, json.dumps({"error": f"{type(e).__name__}"}), {}


# ─── E2 linkage (public interface only) ──────────────────────────

def report_usage_to_e2(result: Dict[str, Any], db_path: Optional[Path] = None):
    """Report observed usage through E2 governor.record_request().

    E3 must never SQL-write governor.db directly — this calls the
    public E2 function only.
    """
    import sys
    sys.path.insert(0, str(GOV_DIR))
    import governor

    usage = result.get("usage") or {}
    in_tok = usage.get("prompt_tokens")
    out_tok = usage.get("completion_tokens")
    status = "success" if result.get("status") == "COMPLETED" else "error"
    latency_ms = int((result.get("runtime_s") or 0) * 1000)

    con = governor.connect_gov()
    try:
        rid = governor.record_request(
            con,
            provider="deepseek",
            model=result.get("model"),
            input_tokens=in_tok,
            output_tokens=out_tok,
            monetary_cost="unknown",  # never estimated when provider data absent
            status=status,
            error_code=result.get("error") if status == "error" else None,
            latency_ms=latency_ms,
        )
        return rid
    finally:
        con.close()
