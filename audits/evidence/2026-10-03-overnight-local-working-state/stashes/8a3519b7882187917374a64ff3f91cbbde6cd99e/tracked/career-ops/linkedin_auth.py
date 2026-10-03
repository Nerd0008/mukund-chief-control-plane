#!/usr/bin/env python3
"""Owner-authenticated LinkedIn OAuth support for Chief OS v1.

What this adds
--------------
The v1 LinkedIn workflow (B19/B20/B21) was deliberately read-only plus
drafts: it parsed owner-exported local files and wrote unsent drafts, and it
implemented no path that touched the account. This module adds the *credential
and token* layer needed for an official-API publish path, and nothing else.

What this still refuses
-----------------------
* No browser automation, no cookie/session reuse, no scraping behind
  authentication, no CAPTCHA anything. The owner opens the authorization URL in
  whatever client he likes; this code never launches or drives a browser.
* No token, secret or code is ever printed, logged, written into the repository,
  or placed on a command line. Presence is reported as a boolean.
* Nothing here posts, messages, connects, follows, reacts, applies or edits a
  profile. Account mutation lives behind the explicit owner-approved action in
  ``career-ops/linkedin_publish.py``.

Where the secrets live
----------------------
Windows Credential Manager, as generic credentials under the owner's own user
profile — outside the repository, outside Git, outside this process's argv.
Resolution order is Credential Manager first, then an environment variable of
the same purpose for a non-Windows host (a VPS), never a file in the repo.

Live flow (LinkedIn OAuth 2.0, three-legged authorization code):

    python career-ops/linkedin_auth.py authorize-url     # prints a URL
    # owner opens it, approves, copies the ?code=... from the redirect
    python career-ops/linkedin_auth.py exchange --code CODE
    python career-ops/linkedin_auth.py status            # presence only

``exchange`` (and ``refresh``) are the only commands that read a secret value,
and they only ever send it to LinkedIn's token endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

# The minimum scope set for "sign in and publish a member post". Publishing a
# post requires w_member_social; openid/profile are needed to resolve the
# member URN (``sub``) the post author field requires.
SCOPES = ("openid", "profile", "w_member_social")

# Windows Credential Manager generic-credential target names. Purpose-named so
# they are recognisable in the Credential Manager UI and never mistaken for a
# provider API key.
CRED_TARGETS = {
    "client_id": "chief-linkedin-client-id",
    "client_secret": "chief-linkedin-client-secret",
    "refresh_token": "chief-linkedin-refresh-token",
    "access_token": "chief-linkedin-access-token",
}

# Environment fallbacks for a non-Windows host. Same purpose, different store.
ENV_VARS = {
    "client_id": "CHIEF_LINKEDIN_CLIENT_ID",
    "client_secret": "CHIEF_LINKEDIN_CLIENT_SECRET",
    "refresh_token": "CHIEF_LINKEDIN_REFRESH_TOKEN",
    "access_token": "CHIEF_LINKEDIN_ACCESS_TOKEN",
}

# Access tokens are short-lived. Persist the expiry alongside the token so a
# refresh happens before an API call rather than as a failed call.
DEFAULT_TOKEN_LIFETIME_DAYS = 60
EXPIRY_TARGET = "chief-linkedin-access-token-expiry-utc"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Windows Credential Manager (generic credentials, owner user profile)
# --------------------------------------------------------------------------- #

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


def _credentials_api():
    """Load the Win32 credential API, or None off Windows."""
    if os.name != "nt":
        return None
    import ctypes
    import ctypes.wintypes as wt

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR),
            ("Comment", wt.LPWSTR), ("LastWritten", wt.FILETIME),
            ("CredentialBlobSize", wt.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD),
            ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
            ("UserName", wt.LPWSTR),
        ]

    advapi32 = ctypes.windll.advapi32
    advapi32.CredWriteW.restype = wt.BOOL
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wt.DWORD]
    advapi32.CredReadW.restype = wt.BOOL
    advapi32.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                   ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    advapi32.CredDeleteW.restype = wt.BOOL
    advapi32.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
    advapi32.CredFree.restype = None
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    return {"ctypes": ctypes, "CREDENTIAL": CREDENTIAL, "api": advapi32}


def store_secret(target: str, secret: str) -> bool:
    """Write a generic credential. The value never leaves this call."""
    api = _credentials_api()
    if api is None:
        raise RuntimeError("Windows Credential Manager is unavailable on this host")
    ctypes = api["ctypes"]
    blob = secret.encode("utf-16-le")
    buf = ctypes.create_string_buffer(blob, len(blob))
    cred = api["CREDENTIAL"]()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.Comment = f"Chief control plane LinkedIn OAuth ({target})"
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.TargetAlias = None
    cred.UserName = target
    return bool(api["api"].CredWriteW(ctypes.byref(cred), 0))


def read_secret(target: str) -> str | None:
    """Read a generic credential. The caller must not print or log the result."""
    api = _credentials_api()
    if api is None:
        return None
    ctypes = api["ctypes"]
    ptr = ctypes.POINTER(api["CREDENTIAL"])()
    if not api["api"].CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
        return None
    try:
        cred = ptr.contents
        size = int(cred.CredentialBlobSize)
        if size <= 0:
            return ""
        raw = ctypes.string_at(cred.CredentialBlob, size)
    finally:
        api["api"].CredFree(ptr)
    try:
        return raw.decode("utf-16-le").rstrip("\x00")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace")


def delete_secret(target: str) -> bool:
    api = _credentials_api()
    if api is None:
        return False
    return bool(api["api"].CredDeleteW(target, CRED_TYPE_GENERIC, 0))


def resolve(purpose: str) -> tuple[str | None, str]:
    """Return (value, source) for a logical credential purpose.

    ``source`` is one of ``credential_manager``, ``env:<VAR>`` or ``none``. The
    value is returned only to the caller that needs to send it to LinkedIn.
    """
    target = CRED_TARGETS[purpose]
    value = read_secret(target)
    if value:
        return value, "credential_manager"
    var = ENV_VARS[purpose]
    value = os.environ.get(var)
    if value:
        return value, f"env:{var}"
    return None, "none"


def presence() -> dict:
    """Presence-only view. No secret value is read out of the store here."""
    out = {}
    for purpose in CRED_TARGETS:
        source = "none"
        target = CRED_TARGETS[purpose]
        if read_secret(target):
            source = "credential_manager"
        elif os.environ.get(ENV_VARS[purpose]):
            source = f"env:{ENV_VARS[purpose]}"
        out[purpose] = {"target": target, "env_var": ENV_VARS[purpose],
                        "present": source != "none", "source": source}
    return out


def access_token_expiry() -> str | None:
    value = read_secret(EXPIRY_TARGET) or os.environ.get(
        "CHIEF_LINKEDIN_ACCESS_TOKEN_EXPIRY_UTC")
    return value or None


def store_access_token(token: str, *, lifetime_days: int = DEFAULT_TOKEN_LIFETIME_DAYS,
                       expires_in_seconds: int | None = None) -> str:
    """Persist a fresh access token and its expiry. Returns the expiry (ISO)."""
    if expires_in_seconds:
        expiry = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_seconds))
    else:
        expiry = datetime.now(timezone.utc) + timedelta(days=lifetime_days)
    expiry_iso = expiry.replace(microsecond=0).isoformat()
    store_secret(CRED_TARGETS["access_token"], token)
    store_secret(EXPIRY_TARGET, expiry_iso)
    return expiry_iso


# --------------------------------------------------------------------------- #
# HTTP transport (injectable so tests never touch the network)
# --------------------------------------------------------------------------- #

def urllib_transport(method: str, url: str, *, headers=None, data=None,
                     timeout: float = 30.0) -> dict:
    """Return {"status", "headers", "body"} — a plain, testable shape."""
    req = urllib.request.Request(url, method=method.upper(),
                                 data=data.encode("utf-8") if data else None,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status,
                    "headers": dict(resp.headers.items()),
                    "body": resp.read().decode("utf-8", "replace")}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code,
                "headers": dict(exc.headers.items()) if exc.headers else {},
                "body": exc.read().decode("utf-8", "replace")}
    except urllib.error.URLError as exc:
        return {"status": 0, "headers": {}, "body": f"transport error: {exc.reason}"}


# --------------------------------------------------------------------------- #
# OAuth
# --------------------------------------------------------------------------- #

def authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {"response_type": "code", "client_id": client_id,
              "redirect_uri": redirect_uri, "state": state,
              "scope": " ".join(SCOPES)}
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def _token_request(form: dict, transport) -> dict:
    resp = transport("POST", TOKEN_URL,
                     headers={"Content-Type": "application/x-www-form-urlencoded"},
                     data=urllib.parse.urlencode(form))
    raw = resp.get("body") or ""
    try:
        parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw}
    except json.JSONDecodeError:
        parsed = {"raw": raw}
    return {"status": resp.get("status"), "body": parsed}


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str,
                  *, transport=None) -> dict:
    form = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri, "client_id": client_id,
            "client_secret": client_secret}
    return _token_request(form, transport or urllib_transport)


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str,
                         *, transport=None) -> dict:
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": client_id, "client_secret": client_secret}
    return _token_request(form, transport or urllib_transport)


def parse_callback_url(url: str) -> dict:
    """Pull ``code``/``state``/``error`` out of the URL the owner pastes back."""
    query = urllib.parse.urlparse(url.strip()).query or url.strip()
    params = urllib.parse.parse_qs(query)
    return {k: v[0] for k, v in params.items()
            if k in ("code", "state", "error", "error_description")}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _emit(doc: dict) -> None:
    json.dump(doc, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def cmd_status(args) -> int:
    pres = presence()
    _emit({
        "ok": True,
        "generated_at": now_utc(),
        "provider": "linkedin-official-api",
        "store": "Windows Credential Manager (generic credentials) / CHIEF_LINKEDIN_* env",
        "scope_requested": list(SCOPES),
        "credentials": pres,
        "client_id_present": pres["client_id"]["present"],
        "client_secret_present": pres["client_secret"]["present"],
        "refresh_token_present": pres["refresh_token"]["present"],
        "access_token_present": pres["access_token"]["present"],
        "access_token_expiry_utc": access_token_expiry(),
        "oauth_ready": all(pres[k]["present"]
                           for k in ("client_id", "client_secret", "refresh_token")),
        "secret_values_read": False,
        "note": ("Presence only: no secret value is read, printed or logged. A missing "
                 "credential means the owner has not completed LinkedIn app/OAuth setup "
                 "yet; nothing is invented to fill the gap."),
    })
    return 0


def cmd_authorize_url(args) -> int:
    client_id, source = resolve("client_id")
    if not client_id:
        _emit({"ok": False, "blocked": True, "blocker_category": "credentials",
               "reason": ("no LinkedIn client id is stored; create a LinkedIn app and run "
                          "`linkedin_auth.py set-client-id` first"),
               "credential_target": CRED_TARGETS["client_id"]})
        return 1
    state = args.state or os.urandom(16).hex()
    url = authorization_url(client_id, args.redirect_uri, state)
    _emit({
        "ok": True, "generated_at": now_utc(),
        "authorization_url": url,
        "redirect_uri": args.redirect_uri,
        "state": state,
        "scopes": list(SCOPES),
        "owner_instructions": [
            "Open the URL in your own browser (this tool never launches one).",
            "Approve the requested scopes for the LinkedIn app.",
            f"You will be redirected to {args.redirect_uri}?code=...&state=...",
            "Copy the whole redirected URL (or just the code) and run:",
            "  python career-ops/linkedin_auth.py exchange --callback-url \"<url>\"",
        ],
        "client_id_source": source,
        "browser_launched_by_this_tool": False,
        "network_calls_spent": 0,
    })
    return 0


def cmd_exchange(args) -> int:
    client_id, _ = resolve("client_id")
    client_secret, _ = resolve("client_secret")
    if not client_id or not client_secret:
        _emit({"ok": False, "blocked": True, "blocker_category": "credentials",
               "reason": "client id and/or client secret not stored"})
        return 1
    assert client_id and client_secret
    code = args.code
    if args.callback_url:
        parsed = parse_callback_url(args.callback_url)
        if parsed.get("error"):
            _emit({"ok": False, "blocked": True, "blocker_category": "external_provider",
                   "reason": f"LinkedIn returned {parsed['error']}: "
                             f"{parsed.get('error_description', '')}".strip()})
            return 1
        code = parsed.get("code") or code
    if not code:
        _emit({"ok": False, "blocked": True, "blocker_category": "owner_approval",
               "reason": "no authorization code supplied"})
        return 1
    result = exchange_code(client_id, client_secret, code, args.redirect_uri)
    body = result["body"]
    ok = isinstance(body, dict) and bool(body.get("access_token"))
    out = {"ok": ok, "generated_at": now_utc(),
           "token_endpoint_status": result["status"],
           "granted_scope": body.get("scope") if isinstance(body, dict) else None,
           "token_type": body.get("token_type") if isinstance(body, dict) else None,
           "expires_in_seconds": body.get("expires_in") if isinstance(body, dict) else None,
           "secret_values_stored": False,
           "access_token_printed": False}
    if ok:
        out["access_token_expiry_utc"] = store_access_token(
            body["access_token"], expires_in_seconds=body.get("expires_in"))
        if body.get("refresh_token"):
            store_secret(CRED_TARGETS["refresh_token"], body["refresh_token"])
            out["refresh_token_stored"] = True
        else:
            out["refresh_token_stored"] = False
        out["secret_values_stored"] = True
    else:
        out["provider_error"] = (body.get("error") if isinstance(body, dict) else None)
        out["provider_error_description"] = (
            body.get("error_description") if isinstance(body, dict) else None)
        out["blocker_category"] = "external_provider"
    _emit(out)
    return 0 if ok else 1


def cmd_refresh(args) -> int:
    client_id, _ = resolve("client_id")
    client_secret, _ = resolve("client_secret")
    refresh_token, _ = resolve("refresh_token")
    if not all((client_id, client_secret, refresh_token)):
        _emit({"ok": False, "blocked": True, "blocker_category": "credentials",
               "reason": "client id, client secret and refresh token are all required"})
        return 1
    assert client_id and client_secret and refresh_token
    result = refresh_access_token(client_id, client_secret, refresh_token)
    body = result["body"]
    ok = isinstance(body, dict) and bool(body.get("access_token"))
    out = {"ok": ok, "generated_at": now_utc(),
           "token_endpoint_status": result["status"],
           "access_token_printed": False}
    if ok:
        out["access_token_expiry_utc"] = store_access_token(
            body["access_token"], expires_in_seconds=body.get("expires_in"))
        if body.get("refresh_token"):
            store_secret(CRED_TARGETS["refresh_token"], body["refresh_token"])
    else:
        out["provider_error"] = (body.get("error") if isinstance(body, dict) else None)
        out["blocker_category"] = "external_provider"
    _emit(out)
    return 0 if ok else 1


def cmd_set(args) -> int:
    """Owner-run, interactive, no echo. Never accepts a secret as an argument."""
    import getpass
    purpose = args.set_client_id or args.set_client_secret or args.set_refresh_token
    if purpose == "client_id":
        value = input("LinkedIn client id (visible: it is not a secret): ").strip()
    else:
        value = getpass.getpass(f"LinkedIn {purpose.replace('_', ' ')} (no echo): ").strip()
    if not value:
        _emit({"ok": False, "reason": "empty value; nothing stored"})
        return 1
    store_secret(CRED_TARGETS[purpose], value)
    _emit({"ok": True, "generated_at": now_utc(), "stored": purpose,
           "credential_target": CRED_TARGETS[purpose],
           "value_echoed": False, "value_logged": False})
    return 0


def cmd_clear(args) -> int:
    removed = []
    for purpose in args.clear:
        if purpose not in CRED_TARGETS:
            continue
        if delete_secret(CRED_TARGETS[purpose]):
            removed.append(purpose)
    if "access_token" in (args.clear or []):
        delete_secret(EXPIRY_TARGET)
    _emit({"ok": True, "generated_at": now_utc(), "removed": removed})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Owner-authenticated LinkedIn OAuth credential/token support "
                    "(no browser automation, no session reuse, no scraping).")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)

    p = sub.add_parser("authorize-url")
    p.add_argument("--redirect-uri",
                   default="https://localhost:8443/linkedin/callback",
                   help="must exactly match a redirect URI registered on the LinkedIn app")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=cmd_authorize_url)

    p = sub.add_parser("exchange")
    p.add_argument("--code", default=None)
    p.add_argument("--callback-url", default=None)
    p.add_argument("--redirect-uri", default="https://localhost:8443/linkedin/callback")
    p.set_defaults(fn=cmd_exchange)

    p = sub.add_parser("refresh"); p.set_defaults(fn=cmd_refresh)

    p = sub.add_parser("set-client-id"); p.set_defaults(fn=cmd_set, set_client_id="client_id",
                                                        set_client_secret=None,
                                                        set_refresh_token=None)
    p = sub.add_parser("set-client-secret"); p.set_defaults(
        fn=cmd_set, set_client_id=None, set_client_secret="client_secret",
        set_refresh_token=None)
    p = sub.add_parser("set-refresh-token"); p.set_defaults(
        fn=cmd_set, set_client_id=None, set_client_secret=None,
        set_refresh_token="refresh_token")

    p = sub.add_parser("clear")
    p.add_argument("--clear", action="append", required=True, choices=list(CRED_TARGETS))
    p.set_defaults(fn=cmd_clear)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
