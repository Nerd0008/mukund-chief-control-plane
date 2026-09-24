#!/usr/bin/env python3
"""Read-only Gmail API adapter — interface + credential probe, no owner OAuth yet.

Status of this module (truthful, 2026-09-24)
-------------------------------------------
* **The interface and the credential probe are implemented and tested.**
* **The HTTP fetch path has NEVER been executed on this machine.** No Gmail
  credentials or token exist here, so it is reported as
  ``fetch_path_executed: false`` / ``verification: "UNVERIFIED"`` everywhere it
  appears. It must not be described as working until it has actually run.
* Nothing in this module is imported by the mailbox->signal parser: the payload
  shape a fetch returns is identical to a Gmail API JSON export, and
  ``application_inbox.parse_gmail_api_message`` is what converts it. That split
  is deliberate — the conversion is tested from fixtures, so only the HTTP call
  itself is unverified.

Capability boundary
-------------------
Read-only scope only (``gmail.readonly``). This module cannot send, reply,
forward, archive, delete, move, label or mark anything read; there is no code
path for those actions and ``application_inbox.guard_action`` refuses them.

Owner step (recorded in tasks-or-issues/overnight-owner-actions-2026-09-24.md)
----------------------------------------------------------------------------
1. In Google Cloud Console create/select a project, enable **Gmail API**.
2. Configure the OAuth consent screen as ``External`` / ``Testing`` and add
   Mukund's own address as a test user.
3. Create an OAuth client of type **Desktop app** and download the client JSON.
4. Save it to the ``credential_path`` in
   ``career-ops/application_inbox_config.json#adapters.gmail_readonly``
   (default ``C:\\Users\\mukun\\AppData\\Local\\hermes\\secrets\\gmail-readonly\\credentials.json``).
   Never commit it; the repo path is outside the repository.
5. Authorise the scope ``https://www.googleapis.com/auth/gmail.readonly`` once
   and place the resulting refresh token JSON at ``token_path``.
6. Set ``adapters.gmail_readonly.enabled`` to ``true``.

Until step 5 is done the adapter returns ``available: false`` and the monitor
continues on the owner-exported local mailbox path.

This module deliberately never reads or prints credential *contents*: only the
existence of the files is reported.
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
    cred = credential_path(cfg)
    tok = token_path(cfg)
    credentials_present = bool(str(cred)) and cred.exists()
    token_present = bool(str(tok)) and tok.exists()
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
    "Complete the Gmail read-only OAuth step: create a Desktop-app OAuth client with the "
    "Gmail API enabled, save its client JSON to the adapter's credential_path "
    "(C:\\Users\\mukun\\AppData\\Local\\hermes\\secrets\\gmail-readonly\\credentials.json), "
    "authorise the scope https://www.googleapis.com/auth/gmail.readonly once and save the "
    "resulting refresh token to token_path (token.json), then set "
    "adapters.gmail_readonly.enabled=true. Only the owner can do this; it is the one step "
    "that cannot be engineered around safely."
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _access_token(cfg: dict) -> str:
    """Exchange the stored refresh token for an access token.

    Never executed on this machine (no token exists). Only the token endpoint is
    contacted; no credential value is logged or returned to a caller that
    reports it.
    """
    import urllib.parse
    import urllib.request

    client = _read_json(credential_path(cfg))
    block = client.get("installed") or client.get("web") or client
    token = _read_json(token_path(cfg))
    refresh = token.get("refresh_token")
    if not refresh:
        raise RuntimeError("stored token has no refresh_token; re-run the owner OAuth step")
    payload = urllib.parse.urlencode({
        "client_id": block["client_id"],
        "client_secret": block["client_secret"],
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode("ascii")
    req = urllib.request.Request(TOKEN_ENDPOINT, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https endpoint
        body = json.loads(resp.read().decode("utf-8"))
    return body["access_token"]


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
