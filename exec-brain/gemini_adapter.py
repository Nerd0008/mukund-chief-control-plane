#!/usr/bin/env python3
"""E3 Google/Gemini Image ExecutionAdapter — Nano Banana 2 (gemini-3.1-flash-image).

Distinct from E2 telemetry. Uses the locally stored gemini-api credential
(Windows Credential Manager, canonical) via gemini_keyaccess.py.
The key is never printed, logged, or committed.

Usage capture: provider-returned usage fields only, never estimated.
E2 linkage: observed requests reported through governor.record_request()
public interface — never direct SQL writes to governor.db.
"""

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import gemini_keyaccess as gk

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODELS_ENDPOINT = f"{API_BASE}/models"
GENERATE_ENDPOINT = API_BASE + "/models/{model}:generateContent"

GOV_DIR = Path(__file__).parent

# Confirmed by owner 2026-09-23 after live /models discovery:
# gemini-3.1-flash-image is the Flash-tier image model backing the
# Google Nano Banana 2 roster worker.
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image"


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


class GeminiImageExecutionAdapter:
    """E3 ExecutionAdapter for Google/Gemini image generation (Nano Banana 2)."""

    def __init__(self, model: str = DEFAULT_IMAGE_MODEL):
        self.model = model
        self.auth_source = gk.key_source()

    # ─── Interface: health / identity ─────────────────────────────

    def check_health(self) -> Dict[str, Any]:
        """Verify credential presence + API reachability via /models."""
        if not (gk.credential_manager_entry_present() or gk.env_var_present()):
            return {"status": "unhealthy", "reason": "credential_absent",
                    "auth_source": "none"}
        key = gk.get_gemini_key()
        if not key:
            return {"status": "unhealthy", "reason": "credential_unreadable"}
        req = urllib.request.Request(
            MODELS_ENDPOINT + "?pageSize=1",
            headers={"x-goog-api-key": key},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return {"status": "healthy", "auth_source": self.auth_source}
                return {"status": "unhealthy", "reason": f"http_{resp.status}"}
        except urllib.error.HTTPError as e:
            if e.code == 401 or e.code == 403:
                return {"status": "unhealthy", "reason": "authentication_failed"}
            if e.code == 429:
                return {"status": "degraded", "reason": "rate_limited"}
            return {"status": "unhealthy", "reason": f"http_{e.code}"}
        except Exception as e:
            return {"status": "unhealthy", "reason": type(e).__name__}

    def get_identity(self) -> Dict[str, Any]:
        """Identity from OBSERVED provider data only."""
        identity = {
            "provider": "google",
            "display_name": "Google Nano Banana 2",
            "api_model_id": None,
            "observed_models": [],
            "auth_source": self.auth_source,
            "interface": "generativelanguage.googleapis.com/v1beta generateContent",
            "cancellation_support": "SUPPORTED_PROCESS_KILL",
            "e2_usage_linkage": "NOT_VERIFIED",
        }
        key = gk.get_gemini_key()
        if not key:
            return identity
        req = urllib.request.Request(
            MODELS_ENDPOINT + "?pageSize=1000",
            headers={"x-goog-api-key": key},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    mid = m.get("name", "").replace("models/", "")
                    if mid:
                        identity["observed_models"].append(mid)
                if self.model in identity["observed_models"]:
                    identity["api_model_id"] = self.model
        except Exception:
            pass
        return identity

    # ─── Interface: dispatch / retrieve / cancel ──────────────────

    def dispatch(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch an image-generation request. Synchronous."""
        dispatch_id = f"gem-{uuid.uuid4().hex[:12]}"
        contract_id = contract.get("contract_id", "unknown")
        objective = contract.get("objective", "")
        model = contract.get("model", self.model)
        timeout = contract.get("timeout", 120)

        payload = {
            "contents": [
                {"parts": [{"text": objective}]}
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
            },
        }

        key = gk.get_gemini_key()
        if not key:
            return self._error_result(dispatch_id, contract_id, objective,
                                      model, "credential_absent", timeout)

        headers = {
            "x-goog-api-key": key,
            "Content-Type": "application/json",
        }
        url = GENERATE_ENDPOINT.format(model=model)

        start = time.time()
        status, body, resp_headers = _http_post_json(url, payload, headers, timeout)
        elapsed = time.time() - start

        return self._build_result(dispatch_id, contract_id, objective, model,
                                  status, body, resp_headers, elapsed, timeout)

    def retrieve(self, dispatch_id: str) -> Optional[Dict[str, Any]]:
        """Synchronous API — results returned inline by dispatch()."""
        return None

    def cancel(self, dispatch_id: str) -> bool:
        """Cancellation: process-kill only (synchronous request)."""
        return False

    # ─── Result construction ──────────────────────────────────────

    def _build_result(self, dispatch_id, contract_id, objective, model,
                      status, body, resp_headers, elapsed, timeout):
        usage = None
        image_b64 = None
        image_mime = None
        response_model = None
        finish_reason = None
        error = None
        prompt_feedback = None

        if status == 200:
            try:
                data = json.loads(body)
                response_model = data.get("modelVersion")
                usage = data.get("usageMetadata") or None
                candidates = data.get("candidates") or []
                if candidates:
                    cand = candidates[0]
                    finish_reason = cand.get("finishReason")
                prompt_feedback = data.get("promptFeedback")
                # Extract inline image part
                for cand in candidates:
                    for part in (cand.get("content", {}) or {}).get("parts", []):
                        ib = part.get("inlineData") or part.get("inline_data")
                        if ib and ib.get("data"):
                            image_b64 = ib.get("data")
                            image_mime = ib.get("mimeType") or ib.get("mime_type")
                            break
                    if image_b64:
                        break
                if image_b64 is None and not candidates:
                    error = "no_candidates_returned"
                elif image_b64 is None:
                    error = "no_image_part_in_response"
            except json.JSONDecodeError:
                error = "response_json_decode_failed"
        elif status in (400, 401, 403, 404, 422, 429):
            try:
                err_data = json.loads(body)
                error = (err_data.get("error", {}).get("message")
                         or err_data.get("error", {}).get("status")
                         or f"http_{status}")
            except (json.JSONDecodeError, AttributeError):
                error = f"http_{status}"
        else:
            error = f"http_{status}"

        # Decode image for validation metadata (bytes stay in-process)
        image_bytes = None
        image_size = None
        image_dims = None
        image_decode_ok = False
        if image_b64:
            try:
                image_bytes = base64.b64decode(image_b64)
                image_size = len(image_bytes)
                image_decode_ok, image_dims = _decode_image_dims(image_bytes)
            except Exception:
                image_bytes = None
                image_size = None

        completed = (
            status == 200
            and image_bytes is not None
            and image_decode_ok
        )

        return {
            "dispatch_id": dispatch_id,
            "status": "COMPLETED" if completed else "FAILED",
            "provider": "google",
            "model": response_model or model,
            "requested_model": model,
            "content": None,  # no text content expected for IMAGE modality
            "image_b64": image_b64,
            "image_mime": image_mime,
            "image_size_bytes": image_size,
            "image_dims": image_dims,
            "image_decode_ok": image_decode_ok,
            "finish_reason": finish_reason,
            "usage": usage,
            "prompt_feedback": prompt_feedback,
            "error": error,
            "exit_code": 0 if status == 200 else status,
            "runtime_s": elapsed,
            "response_headers": {
                k.lower(): v for k, v in resp_headers.items()
                if k.lower() in ("x-request-id", "request-id",
                                 "content-type", "server")
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
            "provider": "google",
            "model": model,
            "objective_hash": objective_hash,
            "objective_summary": summary,
            "api_endpoint": "generateContent",
            "response_modalities": ["IMAGE"],
            "auth_source": self.auth_source,
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
            "provider": "google",
            "model": model,
            "requested_model": model,
            "content": None,
            "image_b64": None,
            "image_mime": None,
            "image_size_bytes": None,
            "image_dims": None,
            "image_decode_ok": False,
            "finish_reason": None,
            "usage": None,
            "error": reason,
            "exit_code": -1,
            "runtime_s": 0.0,
            "dispatch_metadata": {
                "dispatch_id": dispatch_id,
                "contract_id": contract_id,
                "provider": "google",
                "model": model,
                "objective_hash": objective_hash,
                "auth_source": "none",
                "timeout": timeout,
                "exit_status": reason,
            },
        }


def _decode_image_dims(image_bytes: bytes):
    """Decode image dimensions without external deps.

    Supports PNG / JPEG / GIF / WebP (basic header parsing).
    Returns (ok: bool, (width, height) or None).
    """
    if not image_bytes or len(image_bytes) < 12:
        return False, None
    # PNG
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" and len(image_bytes) >= 24:
        w = int.from_bytes(image_bytes[16:20], "big")
        h = int.from_bytes(image_bytes[20:24], "big")
        return True, (w, h)
    # GIF
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        w = int.from_bytes(image_bytes[6:8], "little")
        h = int.from_bytes(image_bytes[8:10], "little")
        return True, (w, h)
    # JPEG
    if image_bytes[:2] == b"\xff\xd8":
        idx = 2
        while idx < len(image_bytes) - 9:
            if image_bytes[idx] != 0xFF:
                idx += 1
                continue
            marker = image_bytes[idx + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6,
                          0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(image_bytes[idx + 5:idx + 7], "big")
                w = int.from_bytes(image_bytes[idx + 7:idx + 9], "big")
                return True, (w, h)
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                idx += 2
                continue
            seg_len = int.from_bytes(image_bytes[idx + 2:idx + 4], "big")
            idx += 2 + seg_len
        return False, None
    # WebP (VP8/VP8L/VP8X)
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        chunk = image_bytes[12:16]
        if chunk == b"VP8 " and len(image_bytes) >= 30:
            w = int.from_bytes(image_bytes[26:28], "little") & 0x3FFF
            h = int.from_bytes(image_bytes[28:30], "little") & 0x3FFF
            return True, (w, h)
        if chunk == b"VP8L" and len(image_bytes) >= 25:
            b0 = image_bytes[20]
            b1 = image_bytes[21]
            b2 = image_bytes[22]
            b3 = image_bytes[23]
            w = 1 + (((b1 & 0x3F) << 8) | b0)
            h = 1 + (((b3 & 0xF) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
            return True, (w, h)
        if chunk == b"VP8X" and len(image_bytes) >= 30:
            w = 1 + (image_bytes[24] | (image_bytes[25] << 8)
                     | (image_bytes[26] << 16))
            h = 1 + (image_bytes[27] | (image_bytes[28] << 8)
                     | (image_bytes[29] << 16))
            return True, (w, h)
        return False, None
    return False, None


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
    in_tok = usage.get("promptTokenCount")
    # Truth defect fixed 2026-09-23: this previously fell back to
    # `totalTokenCount` when `candidatesTokenCount` was absent, which reports
    # prompt+output as if it were output (observed on a failed image response:
    # 17 prompt tokens recorded as 17 output tokens, obs-20260923-f0913024).
    # Only the provider's own candidate-token count is a valid output figure;
    # when it is absent the value is reported as None rather than approximated.
    out_tok = usage.get("candidatesTokenCount")
    status = "success" if result.get("status") == "COMPLETED" else "error"
    latency_ms = int((result.get("runtime_s") or 0) * 1000)

    con = governor.connect_gov()
    try:
        rid = governor.record_request(
            con,
            provider="google",
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
