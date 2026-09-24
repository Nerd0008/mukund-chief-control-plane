#!/usr/bin/env python3
"""E3 Generic OpenAI-Compatible ExecutionAdapter.

Reuses the DeepSeek adapter pattern for any provider that speaks the
OpenAI /chat/completions JSON shape over HTTP.

Distinct from E2 telemetry. Per-worker differences are supplied via
ProviderConfig — this file contains no provider-specific branching.

Usage capture: provider-returned usage fields only, never estimated.
E2 linkage: observed requests reported through governor.record_request()
public interface — never direct SQL writes to governor.db.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

GOV_DIR = Path(__file__).parent

# ─── Provider registry ───────────────────────────────────────────
# Base URLs and model IDs. Auth is resolved per-worker at runtime
# through the key_resolver callback (credential manager / env).

PROVIDER_CONFIGS: Dict[str, Dict[str, Any]] = {
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "models_endpoint": "https://api.mistral.ai/v1/models",
        "chat_endpoint": "https://api.mistral.ai/v1/chat/completions",
        "api_model_id": "mistral-small-4",
        "display_name": "Mistral Small 4",
        "cancellation_support": "SUPPORTED_PROCESS_KILL",
        "env_var": "MISTRAL_API_KEY",
        "credential_target": "mistral",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models_endpoint": "https://open.bigmodel.cn/api/paas/v4/models",
        "chat_endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "api_model_id": "glm-5.3-flash",
        "display_name": "GLM-5.3 Flash",
        "cancellation_support": "SUPPORTED_PROCESS_KILL",
        "env_var": "GLM_API_KEY",
        "credential_target": "glm",
    },
    "minimax": {
        "base_url": "https://api.minimax.io/v1",
        "models_endpoint": "https://api.minimax.io/v1/models",
        "chat_endpoint": "https://api.minimax.io/v1/chat/completions",
        "api_model_id": "minimax-m3",
        "display_name": "MiniMax M3",
        "cancellation_support": "SUPPORTED_PROCESS_KILL",
        "env_var": "MINIMAX_API_KEY",
        "credential_target": "minimax",
    },
    "stepfun": {
        "base_url": "https://api.stepfun.com/v1",
        "models_endpoint": "https://api.stepfun.com/v1/models",
        "chat_endpoint": "https://api.stepfun.com/v1/chat/completions",
        "api_model_id": "step-3.7-flash",
        "display_name": "Step 3.7 Flash",
        "cancellation_support": "SUPPORTED_PROCESS_KILL",
        "env_var": "STEP_API_KEY",
        "credential_target": "stepfun",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models_endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        "chat_endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "api_model_id": "qwen3.8-27b",
        "display_name": "Qwen3.8-27B",
        "cancellation_support": "SUPPORTED_PROCESS_KILL",
        "env_var": "DASHSCOPE_API_KEY",
        "credential_target": "qwen",
    },
    "hunyuan": {
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models_endpoint": "https://api.hunyuan.cloud.tencent.com/v1/models",
        "chat_endpoint": "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
        "api_model_id": "hunyuan-hy3",
        "display_name": "Tencent Hunyuan Hy3",
        "cancellation_support": "SUPPORTED_PROCESS_KILL",
        "env_var": "HUNYUAN_API_KEY",
        "credential_target": "hunyuan",
    },
    "longcat": {
        "base_url": "https://api.longcat.chat/openai",
        "models_endpoint": "https://api.longcat.chat/v1/models",
        "chat_endpoint": "https://api.longcat.chat/openai/v1/chat/completions",
        "api_model_id": "LongCat-2.0",
        "display_name": "LongCat 2.0",
        "cancellation_support": "SUPPORTED_PROCESS_KILL",
        "env_var": "LONGCAT_API_KEY",
        "credential_target": "longcat",
    },
}


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


def _resolve_key(config: Dict[str, Any]) -> tuple:
    """Resolve API key from credential manager or env var.

    Returns (key, source) or (None, "none").
    Order: Windows Credential Manager -> env var.
    """
    target = config.get("credential_target")
    if target:
        key = _read_from_credential_manager(target)
        if key:
            return key, "credential_manager"

    env_var = config.get("env_var")
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val, "env"

    return None, "none"


def _read_from_credential_manager(target: str):
    """Read generic credential blob via CredReadW. In-process only."""
    import ctypes
    import ctypes.wintypes as wt

    CRED_TYPE_GENERIC = 1

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wt.DWORD),
            ("Type", wt.DWORD),
            ("TargetName", wt.LPWSTR),
            ("Comment", wt.LPWSTR),
            ("LastWritten", wt.FILETIME),
            ("CredentialBlobSize", wt.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wt.DWORD),
            ("AttributeCount", wt.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wt.LPWSTR),
            ("UserName", wt.LPWSTR),
        ]

    advapi32 = ctypes.windll.advapi32
    advapi32.CredReadW.restype = wt.BOOL
    advapi32.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                    ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    advapi32.CredFree.argtypes = [ctypes.c_void_p]

    cred_ptr = ctypes.POINTER(CREDENTIAL)()
    if not advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr)):
        return None
    try:
        cred = cred_ptr.contents
        size = cred.CredentialBlobSize
        if size == 0:
            return None
        blob = ctypes.string_at(cred.CredentialBlob, size)
        try:
            return blob.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            try:
                return blob.decode("utf-8").rstrip("\x00")
            except UnicodeDecodeError:
                return None
    finally:
        advapi32.CredFree(cred_ptr)


class GenericOpenAIAdapter:
    """E3 ExecutionAdapter for any OpenAI-compatible /chat/completions provider.

    Provider-specific behavior is entirely driven by ProviderConfig.
    No provider-specific branching exists in this class.
    """

    def __init__(self, provider_key: str):
        if provider_key not in PROVIDER_CONFIGS:
            raise ValueError(f"Unknown provider: {provider_key}")
        self.provider_key = provider_key
        self.config = PROVIDER_CONFIGS[provider_key]
        self.model = self.config["api_model_id"]
        self._key = None
        self._auth_source = None

    def _resolve_auth(self):
        """Lazy auth resolution."""
        if self._key is None:
            self._key, self._auth_source = _resolve_key(self.config)
        return self._key, self._auth_source

    # ─── Interface: health / identity ─────────────────────────────

    def check_health(self) -> Dict[str, Any]:
        """Verify credential presence + API reachability via /models."""
        key, source = self._resolve_auth()
        if not key:
            return {"status": "unhealthy", "reason": "credential_absent",
                    "auth_source": "none"}
        status, body, _ = self._list_models_raw()
        if status == 200:
            return {"status": "healthy", "auth_source": source}
        if status == 401:
            return {"status": "unhealthy", "reason": "authentication_failed"}
        if status == 429:
            return {"status": "degraded", "reason": "rate_limited"}
        return {"status": "unhealthy", "reason": f"http_{status}"}

    def get_identity(self) -> Dict[str, Any]:
        """Identity from OBSERVED provider data only."""
        key, source = self._resolve_auth()
        identity = {
            "provider": self.provider_key,
            "display_name": self.config["display_name"],
            "api_model_id": None,
            "observed_models": [],
            "auth_source": source,
            "interface": self.config["chat_endpoint"],
            "cancellation_support": self.config["cancellation_support"],
            "e2_usage_linkage": "NOT_VERIFIED",
        }
        if not key:
            return identity
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
        dispatch_id = f"{self.provider_key[:2]}-{uuid.uuid4().hex[:12]}"
        contract_id = contract.get("contract_id", "unknown")
        objective = contract.get("objective", "")
        model = contract.get("model", self.model)
        timeout = contract.get("timeout", 120)
        max_tokens = contract.get("max_tokens", 1024)
        temperature = contract.get("temperature", 0.0)

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": objective}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        key, source = self._resolve_auth()
        if not key:
            return self._error_result(dispatch_id, contract_id, objective,
                                      model, "credential_absent", timeout)

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        start = time.time()
        status, body, resp_headers = _http_post_json(
            self.config["chat_endpoint"], payload, headers, timeout
        )
        elapsed = time.time() - start

        return self._build_result(dispatch_id, contract_id, objective, model,
                                  status, body, resp_headers, elapsed, timeout,
                                  source)

    def retrieve(self, dispatch_id: str) -> Optional[Dict[str, Any]]:
        """Synchronous API — results are returned inline by dispatch()."""
        return None

    def cancel(self, dispatch_id: str) -> bool:
        """Cancellation: process-kill only (synchronous request)."""
        return False

    # ─── Result construction ──────────────────────────────────────

    def _build_result(self, dispatch_id, contract_id, objective, model,
                      status, body, resp_headers, elapsed, timeout, source):
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
                        or raw_usage.get("prompt_tokens_details", {}).get("cached_tokens")
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
            "provider": self.provider_key,
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
                status, timeout, source
            ),
        }

    def _sanitized_metadata(self, dispatch_id, contract_id, objective,
                            model, elapsed, status, timeout, source):
        """Sanitized dispatch metadata — no raw objective, no secrets."""
        objective_hash = hashlib.sha256(objective.encode()).hexdigest()[:12]
        summary = objective[:50] + "..." if len(objective) > 50 else objective
        return {
            "dispatch_id": dispatch_id,
            "contract_id": contract_id,
            "provider": self.provider_key,
            "model": model,
            "objective_hash": objective_hash,
            "objective_summary": summary,
            "api_endpoint": self.config["chat_endpoint"],
            "auth_source": source,
            "timeout": timeout,
            "elapsed_seconds": elapsed,
            "http_status": status,
            "exit_status": "ok" if status == 200 else f"http_{status}",
        }

    def _error_result(self, dispatch_id, contract_id, objective, model,
                      reason, timeout):
        objective_hash = hashlib.sha256(objective.encode()).hexdigest()[:12]
        return {
            "dispatch_id": dispatch_id,
            "status": "FAILED",
            "provider": self.provider_key,
            "model": model,
            "content": None,
            "usage": None,
            "error": reason,
            "exit_code": -1,
            "runtime_s": 0.0,
            "dispatch_metadata": {
                "dispatch_id": dispatch_id,
                "contract_id": contract_id,
                "provider": self.provider_key,
                "model": model,
                "objective_hash": objective_hash,
                "auth_source": "none",
                "timeout": timeout,
                "exit_status": reason,
            },
        }

    def _list_models_raw(self):
        """GET /models with in-process credential. Never logs the key."""
        key, _ = self._resolve_auth()
        if not key:
            return -1, json.dumps({"error": "credential_absent"}), {}
        req = urllib.request.Request(
            self.config["models_endpoint"],
            headers={"Authorization": f"Bearer {key}"}
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
            provider=result.get("provider", "unknown"),
            model=result.get("model"),
            input_tokens=in_tok,
            output_tokens=out_tok,
            monetary_cost="unknown",
            status=status,
            error_code=result.get("error") if status == "error" else None,
            latency_ms=latency_ms,
        )
        return rid
    finally:
        con.close()


# ─── Convenience: per-worker adapter instances ───────────────────

def get_adapter(worker_id: str) -> GenericOpenAIAdapter:
    """Get the adapter instance for a worker ID."""
    mapping = {
        "mistral-small-4": "mistral",
        "glm-53-flash": "glm",
        "qwen38-27b": "qwen",
        "longcat-2.0": "longcat",
        "minimax-m3": "minimax",
        "step-37-flash": "stepfun",
        "tencent-hunyuan-hy3": "hunyuan",
    }
    provider_key = mapping.get(worker_id)
    if not provider_key:
        raise ValueError(f"No adapter mapping for worker: {worker_id}")
    return GenericOpenAIAdapter(provider_key)


def check_credential_present(worker_id: str) -> bool:
    """Check if a credential is present for a worker. Presence only."""
    try:
        adapter = get_adapter(worker_id)
        key, _ = adapter._resolve_auth()
        return key is not None
    except Exception:
        return False


def run_smoke_test(worker_id: str) -> Dict[str, Any]:
    """Run a minimal smoke test for a worker.

    Returns dict with passed, health, identity, and routable state.
    Does NOT fabricate success — blocked workers report blocked.
    """
    try:
        adapter = get_adapter(worker_id)
    except Exception as e:
        return {
            "passed": False,
            "blocked_reason": "adapter_creation_failed",
            "blocked_detail": str(e),
            "routable": False,
            "qualification": "UNPROVEN",
        }

    health = adapter.check_health()
    if health["status"] == "unhealthy":
        return {
            "passed": False,
            "blocked_reason": health.get("reason", "unhealthy"),
            "health": health,
            "routable": False,
            "qualification": "UNPROVEN",
        }

    identity = adapter.get_identity()

    return {
        "passed": True,
        "health": health,
        "identity": identity,
        "routable": True,
        "qualification": "UNPROVEN",  # smoke test != capability qualification
    }
