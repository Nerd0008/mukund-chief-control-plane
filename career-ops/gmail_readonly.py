#!/usr/bin/env python3
"""Legacy read-only adapter using Career Ops Windows Credential Manager OAuth.
See docs/gmail-application-monitor.md. Plaintext credential files are not used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REQUIRED_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

#: Set by ``fetch`` when the HTTP path actually runs. Never set by tests.
FETCH_PATH_EXECUTED = False

UNVERIFIED_NOTE = (
    "The HTTP fetch path is implemented but has never been executed on this machine "
    "(no credentials/token present); it is UNVERIFIED and must not be treated as working."
)


def _resolve(cfg: dict, key_path: str, key_env: str) -> Path:
    env_value = os.environ.get(cfg.get(key_env) or key_env)
    value = env_value or cfg.get(key_path)
    return Path(value) if value else Path("")


def credential_path(cfg: dict) -> Path:
    return _resolve(cfg, "credential_path", "credential_path_env")


def token_path(cfg: dict) -> Path:
    return _resolve(cfg, "token_path", "token_path_env")


def adapter_status(cfg: dict) -> dict:
    """Truthful readiness report. Reports presence, never contents."""
    from career_google_auth import status as oauth_status
    secure = oauth_status()
    cred, tok = Path(""), Path("")
    credentials_present = secure["present"]["client_id"] and secure["present"]["client_secret"]
    token_present = secure["oauth_ready"]
    enabled = bool(cfg.get("enabled"))
    if not enabled:
        reason = ("adapter is disabled in configuration; the owner-exported local mailbox "
                  "path is the active one")
    elif not credentials_present:
        reason = f"OAuth client file not found at {cred} (owner step 4 not done)"
    elif not token_present:
        reason = f"OAuth token not found at {tok} (owner step 5 not done)"
    else:
        reason = "configured; the HTTP fetch path is implemented but UNVERIFIED on this machine"
    available = enabled and credentials_present and token_present
    return {
        "adapter": "gmail_readonly",
        "kind": cfg.get("kind"),
        "enabled": enabled,
        "available": available,
        "credentials_present": credentials_present,
        "token_present": token_present,
        "credential_path": str(cred),
        "token_path": str(tok),
        "required_scope": cfg.get("required_scope") or REQUIRED_SCOPE,
        "query": cfg.get("query"),
        "fetch_path_executed": FETCH_PATH_EXECUTED,
        "verification": "UNVERIFIED" if not FETCH_PATH_EXECUTED else "EXECUTED",
        "reason": reason,
        "owner_action_required": not available,
        "owner_action": None if available else OWNER_ACTION,
        "note": UNVERIFIED_NOTE,
    }


OWNER_ACTION = (
    "Enable Gmail and Calendar APIs, create a Desktop OAuth client, run "
    "career_google_auth.py store-client (hidden prompts), then authorize. "
    "Credentials are stored only in Windows Credential Manager."
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _access_token(cfg: dict) -> str:
    """Use secure shared OAuth; never read plaintext credentials."""
    from career_google_auth import access_token
    return access_token()



def fetch(cfg: dict, *, limit: int | None = None) -> dict:
    """Read-only message fetch.

    Refuses with a truthful reason whenever the adapter is disabled or
    unconfigured — that is the state on this machine, and no network call is
    made in that case. The ``available`` branch has never run here.
    """
    global FETCH_PATH_EXECUTED
    status = adapter_status(cfg)
    if not status["available"]:
        return {"ok": False, "adapter": "gmail_readonly", "available": False,
                "network_used": False, "messages": [], "fetch_path_executed": False,
                "reason": status["reason"], "owner_action_required": True,
                "owner_action": OWNER_ACTION, "verification": "UNVERIFIED"}

    import urllib.parse
    import urllib.request

    max_messages = int(limit or cfg.get("max_messages") or 200)
    token = _access_token(cfg)
    query = urllib.parse.urlencode({
        "q": cfg.get("query") or "",
        "maxResults": min(max_messages, 500),
    })
    req = urllib.request.Request(f"{API_BASE}/messages?{query}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https endpoint
        listing = json.loads(resp.read().decode("utf-8"))

    messages = []
    for stub in (listing.get("messages") or [])[:max_messages]:
        q = urllib.parse.urlencode({"format": "full"})
        req = urllib.request.Request(f"{API_BASE}/messages/{stub['id']}?{q}",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https endpoint
            messages.append(json.loads(resp.read().decode("utf-8")))
    FETCH_PATH_EXECUTED = True
    return {"ok": True, "adapter": "gmail_readonly", "available": True, "network_used": True,
            "messages": messages, "count": len(messages), "fetch_path_executed": True,
            "query": cfg.get("query"), "verification": "EXECUTED",
            "read_only": True, "scope": status["required_scope"],
            "mutations_performed": 0}
