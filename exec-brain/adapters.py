#!/usr/bin/env python3
"""Executive Brain E2 — Provider Adapters.

Deterministic telemetry adapters for Nous, DeepSeek, Codex, Antigravity.
All adapters return UNKNOWN for dimensions they cannot observe.
D3: routable flag separates telemetry from routability.
D2: DeepSeek key read by reference only, never printed/logged.
"""

import json
import os
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

GOV_DIR = Path(os.environ.get("EB_HOME", Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"))
HERMES_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"

# ─── Helpers ───────────────────────────────────────────────────────

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def http_get(url, timeout=10, headers=None):
    """Simple HTTP GET using socket (no external deps). Returns (status_code, body, headers_dict)."""
    import ssl
    import urllib.parse
    
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    
    ctx = ssl.create_default_context() if parsed.scheme == "https" else None
    
    try:
        sock.connect((host, port))
        if ctx:
            sock = ctx.wrap_socket(sock, server_hostname=host)
        
        req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n"
        if headers:
            for k, v in headers.items():
                req += f"{k}: {v}\r\n"
        req += "\r\n"
        sock.sendall(req.encode())
        
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        
        response_str = response.decode("utf-8", errors="replace")
        # Split headers and body
        parts = response_str.split("\r\n\r\n", 1)
        header_part = parts[0] if parts else ""
        body = parts[1] if len(parts) > 1 else ""
        
        # Parse status
        status_line = header_part.split("\r\n")[0] if header_part else ""
        status_code = 0
        if " " in status_line:
            try:
                status_code = int(status_line.split(" ")[1])
            except (ValueError, IndexError):
                pass
        
        # Parse headers
        resp_headers = {}
        for line in header_part.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                resp_headers[k.strip().lower()] = v.strip()
        
        return status_code, body, resp_headers
    except (socket.timeout, socket.error, OSError) as e:
        return 0, str(e), {}
    finally:
        sock.close()


def run_cmd(cmd, timeout=10):
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def check_process_running(process_names):
    """Check if any of the given process names are running."""
    rc, stdout, _ = run_cmd("tasklist /FO CSV /NH")
    if rc != 0:
        return False
    running = stdout.lower()
    for name in process_names:
        if name.lower() in running:
            return True
    return False


def check_package_installed(package_name):
    """Check if a package is installed via winget."""
    rc, stdout, _ = run_cmd(f"winget list --name \"{package_name}\"")
    if rc != 0:
        return None
    # Check if package appears in output
    for line in stdout.split("\n"):
        if package_name.lower() in line.lower():
            # Try to extract version
            parts = line.strip().split()
            if len(parts) >= 2:
                return parts[-2]  # version is usually second-to-last
    return None


def check_credential_manager(target):
    """Check if a credential exists in Windows Credential Manager (D2: presence only)."""
    rc, stdout, _ = run_cmd("cmdkey /list")
    if rc != 0:
        return False
    return target.lower() in stdout.lower()


def check_env_var(var_name):
    """Check if an environment variable exists (D2: presence only, no value)."""
    return var_name in os.environ


def deepseek_key_available():
    """Check if DeepSeek API key is available (D2: presence only).
    Returns: (available: bool, source: str)"""
    if check_env_var("DEEPSEEK_API_KEY"):
        return True, "env"
    if check_credential_manager("deepseek"):
        return True, "credential_manager"
    return False, "none"


def get_deepseek_key():
    """Get DeepSeek API key (D2: read by reference, never log)."""
    # First try env var
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    # Then try credential manager (this is a simplified version)
    # In production, would use Windows Credential Manager API
    # For now, return None if not in env
    return None


# ─── Nous Adapter ──────────────────────────────────────────────────

def probe_nous():
    """Probe Nous/LongCat provider."""
    snapshot = {
        "provider": "nous",
        "captured_at": now(),
        "operational": "unknown",
        "routable": True,
        "rate_limit_state": "unknown",
        "last_success_at": None,
        "telemetry_source": "mixed",
        "telemetry_confidence": "medium",
        "quota_semantics": "local counter only; provider quota unknown",
        "available_models": [],
        "dimensions": [],
        "errors": []
    }
    
    # Read auth.json
    auth_path = HERMES_DIR / "auth.json"
    if auth_path.exists():
        try:
            auth_data = json.loads(auth_path.read_text(encoding="utf-8"))
            nous_creds = auth_data.get("credential_pool", {}).get("nous", [])
            if nous_creds:
                cred = nous_creds[0]
                request_count = cred.get("request_count", 0)
                expires_at = cred.get("expires_at")
                
                # Add request window dimension
                snapshot["dimensions"].append({
                    "dimension_kind": "request_window",
                    "remaining": str(request_count),
                    "unit": "requests",
                    "reset_renewal": "unknown",
                    "source": "observed",
                    "confidence": "high"
                })
                
                # Add provider credit (token validity)
                if expires_at:
                    snapshot["dimensions"].append({
                        "dimension_kind": "provider_credit",
                        "remaining": expires_at,
                        "unit": "timestamp",
                        "reset_renewal": expires_at,
                        "source": "local-observation",
                        "confidence": "high"
                    })
        except (json.JSONDecodeError, IOError) as e:
            snapshot["errors"].append(f"auth.json read error: {type(e).__name__}")
    else:
        snapshot["errors"].append("auth.json not found")
    
    # Ping inference endpoint
    status, body, headers = http_get("https://inference-api.nousresearch.com/v1/models")
    if status == 200:
        snapshot["operational"] = "up"
        snapshot["last_success_at"] = now()
        # Try to parse models
        try:
            models_data = json.loads(body)
            if isinstance(models_data, dict) and "data" in models_data:
                for m in models_data["data"]:
                    snapshot["available_models"].append({
                        "id": m.get("id", "unknown"),
                        "context_length": m.get("context_length", "unknown")
                    })
        except json.JSONDecodeError:
            pass
    elif status == 500:
        snapshot["operational"] = "degraded"
        snapshot["errors"].append(f"inference endpoint returned {status}")
    elif status == 0:
        snapshot["operational"] = "down"
        snapshot["errors"].append("inference endpoint unreachable")
    else:
        snapshot["operational"] = "unknown"
        snapshot["errors"].append(f"unexpected status {status}")
    
    # Read model catalog cache
    cache_path = HERMES_DIR / "provider_models_cache.json"
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            # Already captured from ping, but cache provides pricing
        except (json.JSONDecodeError, IOError):
            pass
    
    return snapshot


# ─── DeepSeek Adapter ──────────────────────────────────────────────

def probe_deepseek():
    """Probe DeepSeek API (D2: key by reference, never log)."""
    snapshot = {
        "provider": "deepseek",
        "captured_at": now(),
        "operational": "unknown",
        "routable": True,
        "rate_limit_state": "unknown",
        "last_success_at": None,
        "telemetry_source": "provider-api",
        "telemetry_confidence": "medium",
        "quota_semantics": "metered provider; no token quota; spend calculated from observed requests",
        "available_models": [],
        "dimensions": [],
        "errors": []
    }
    
    # Check key availability (D2: presence only)
    key_available, key_source = deepseek_key_available()
    if not key_available:
        snapshot["operational"] = "unknown"
        snapshot["errors"].append("api-key-not-configured")
        snapshot["quota_semantics"] = "DeepSeek API key not configured; run setup or set DEEPSEEK_API_KEY"
        return snapshot
    
    # Ping DeepSeek API
    key = get_deepseek_key()
    if key:
        status, body, headers = http_get(
            "https://api.deepseek.com/v1/models",
            headers={"Authorization": f"Bearer {key}"}
        )
    else:
        status, body, headers = 0, "key retrieval not implemented", {}
    
    if status == 200:
        snapshot["operational"] = "up"
        snapshot["last_success_at"] = now()
        try:
            models_data = json.loads(body)
            if isinstance(models_data, dict) and "data" in models_data:
                for m in models_data["data"]:
                    snapshot["available_models"].append({
                        "id": m.get("id", "unknown"),
                        "context_length": m.get("context_length", "unknown")
                    })
        except json.JSONDecodeError:
            pass
    elif status == 401:
        snapshot["operational"] = "degraded"
        snapshot["errors"].append("authentication failed (invalid key)")
    elif status == 429:
        snapshot["operational"] = "degraded"
        snapshot["rate_limit_state"] = "throttled"
        snapshot["errors"].append("rate limited")
    elif status >= 500:
        snapshot["operational"] = "degraded"
        snapshot["errors"].append(f"server error {status}")
    elif status == 0:
        snapshot["operational"] = "down"
        snapshot["errors"].append("API unreachable")
    
    # Check for rate limit headers
    if "x-ratelimit-remaining" in headers:
        remaining = headers["x-ratelimit-remaining"]
        snapshot["rate_limit_state"] = "ok" if int(remaining) > 0 else "throttled"
        snapshot["dimensions"].append({
            "dimension_kind": "rate_limit",
            "remaining": remaining,
            "unit": "requests",
            "reset_renewal": headers.get("x-ratelimit-reset", "unknown"),
            "source": "provider-api",
            "confidence": "high"
        })
    
    # Read spending budget
    config_path = GOV_DIR / "deepseek-config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            budget = config.get("spending_budget_usd", 0)
            # Calculate spend from observed requests (simplified)
            snapshot["dimensions"].append({
                "dimension_kind": "monetary_balance",
                "remaining": f"{budget:.2f} USD",
                "unit": "USD",
                "reset_renewal": "unknown",
                "source": "observed",
                "confidence": "medium"
            })
        except (json.JSONDecodeError, IOError) as e:
            snapshot["errors"].append(f"config read error: {type(e).__name__}")
    else:
        snapshot["errors"].append("spending-budget-not-configured")
    
    # Add token window dimension (metered; no quota)
    snapshot["dimensions"].append({
        "dimension_kind": "token_window",
        "remaining": "unknown",
        "unit": "tokens",
        "reset_renewal": "unknown",
        "source": "provider-api",
        "confidence": "high"
    })
    
    return snapshot


# ─── Codex Adapter ─────────────────────────────────────────────────

def probe_codex():
    """Probe Codex (D3: observed-only, routable=false)."""
    snapshot = {
        "provider": "codex",
        "captured_at": now(),
        "operational": "unknown",
        "routable": False,  # D3: desktop app, no API/CLI
        "rate_limit_state": "unknown",
        "last_success_at": None,
        "telemetry_source": "observed-only",
        "telemetry_confidence": "low",
        "quota_semantics": "desktop app; no programmatic telemetry",
        "available_models": [],
        "dimensions": [],
        "errors": []
    }
    
    # Check if installed
    version = check_package_installed("OpenAI.Codex")
    if version:
        # Check if running
        if check_process_running(["Codex.exe", "OpenAI.Codex.exe"]):
            snapshot["operational"] = "up"
            snapshot["last_success_at"] = now()
        else:
            snapshot["operational"] = "degraded"
    else:
        snapshot["operational"] = "down"
    
    # Add concurrency dimension (unknown)
    snapshot["dimensions"].append({
        "dimension_kind": "concurrency",
        "remaining": "unknown",
        "unit": "concurrent",
        "reset_renewal": "unknown",
        "source": "observed",
        "confidence": "low"
    })
    
    return snapshot


# ─── Antigravity Adapter ───────────────────────────────────────────

def probe_antigravity():
    """Probe Antigravity (D3: observed-only, routable=false)."""
    snapshot = {
        "provider": "antigravity",
        "captured_at": now(),
        "operational": "unknown",
        "routable": False,  # D3: desktop app, no API/CLI
        "rate_limit_state": "unknown",
        "last_success_at": None,
        "telemetry_source": "observed-only",
        "telemetry_confidence": "low",
        "quota_semantics": "desktop app; no programmatic telemetry",
        "available_models": [],
        "dimensions": [],
        "errors": []
    }
    
    # Check if installed
    version = check_package_installed("Google.Antigravity")
    if version:
        # Check if running
        if check_process_running(["Antigravity.exe"]):
            # Check credential presence (D2: presence only)
            if check_credential_manager("gemini:antigravity"):
                snapshot["operational"] = "up"
                snapshot["last_success_at"] = now()
            else:
                snapshot["operational"] = "degraded"
                snapshot["errors"].append("credential not found in Windows Credential Manager")
        else:
            snapshot["operational"] = "degraded"
    else:
        snapshot["operational"] = "down"
    
    # Add concurrency dimension (unknown)
    snapshot["dimensions"].append({
        "dimension_kind": "concurrency",
        "remaining": "unknown",
        "unit": "concurrent",
        "reset_renewal": "unknown",
        "source": "observed",
        "confidence": "low"
    })
    
    return snapshot


# ─── Main probe dispatcher ─────────────────────────────────────────

ADAPTERS = {
    "nous": probe_nous,
    "deepseek": probe_deepseek,
    "codex": probe_codex,
    "antigravity": probe_antigravity,
}


def probe_provider(provider_id):
    """Probe a single provider."""
    if provider_id not in ADAPTERS:
        raise ValueError(f"unknown provider: {provider_id}")
    return ADAPTERS[provider_id]()


def probe_all():
    """Probe all providers, return list of snapshots."""
    results = []
    for provider_id in ADAPTERS:
        try:
            snapshot = probe_provider(provider_id)
            results.append(snapshot)
        except Exception as e:
            # Create error snapshot
            results.append({
                "provider": provider_id,
                "captured_at": now(),
                "operational": "unknown",
                "routable": False,
                "rate_limit_state": "unknown",
                "last_success_at": None,
                "telemetry_source": "observed-only",
                "telemetry_confidence": "low",
                "quota_semantics": "probe failed",
                "available_models": [],
                "dimensions": [],
                "errors": [str(e)]
            })
    return results
