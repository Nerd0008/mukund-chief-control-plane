"""Laptop OAuth: read-only Gmail and events on calendars owned by the owner.

Secrets stay in Windows Credential Manager. No plaintext import/export path.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import getpass
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from linkedin_auth import read_secret, store_secret

SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events.owned",
)
TARGETS = {k: "chief-career-google-" + k.replace("_", "-") for k in
           ("client_id", "client_secret", "refresh_token", "access_token", "token_state")}
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleError(RuntimeError):
    """Safe diagnostic: never includes response bodies, URLs or tokens."""

    def __init__(self, operation, status=None, reason=None):
        self.status = status
        self.reason = reason
        super().__init__(f"Google {operation} failed" + (f" (HTTP {status})" if status else ""))


def http_json(method, url, *, token=None, data=None, form=False):
    payload = None if data is None else (
        urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode())
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        headers["Content-Type"] = ("application/x-www-form-urlencoded" if form else "application/json")
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        # No redirect may forward an Authorization header to another origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read()).get("error", {})
            reasons = [e.get("reason") for e in body.get("errors", [])]
            reason = next((r for r in reasons if r in {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded", "insufficientPermissions", "forbidden"}), None)
        except (ValueError, TypeError):
            reason = None
        raise GoogleError("request" + (" " + reason if reason else ""), exc.code, reason) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise GoogleError("request") from None


def state():
    try:
        return json.loads(read_secret(TARGETS["token_state"]) or "{}")
    except (ValueError, TypeError):
        return {}


def status():
    present = {key: bool(read_secret(target)) for key, target in TARGETS.items()}
    saved = state()
    return {"storage": "Windows Credential Manager", "present": present,
            "scopes": saved.get("scopes", []), "access_token_expiry": saved.get("expires_at"),
            "oauth_ready": all(present[k] for k in ("client_id", "client_secret", "refresh_token"))
            and set(saved.get("scopes", [])) == set(SCOPES)}


def save_tokens(tokens):
    granted = str(tokens.get("scope") or "").split()
    if set(granted) != set(SCOPES):
        raise GoogleError("consent scopes differ from the two requested scopes")
    if not tokens.get("access_token"):
        raise GoogleError("token response missing access token")
    for key in ("access_token", "refresh_token"):
        if tokens.get(key) and not store_secret(TARGETS[key], tokens[key]):
            raise GoogleError("credential storage")
    expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(tokens.get("expires_in", 0)))
    metadata = {"scopes": granted, "expires_at": expiry.isoformat()}
    if not store_secret(TARGETS["token_state"], json.dumps(metadata)):
        raise GoogleError("credential storage")


def access_token():
    if not status()["oauth_ready"]:
        raise GoogleError("OAuth authorization required")
    saved = state()
    try:
        expires = dt.datetime.fromisoformat(saved["expires_at"])
    except (KeyError, ValueError):
        expires = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    token = read_secret(TARGETS["access_token"])
    if token and expires > dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=90):
        return token
    response = http_json("POST", TOKEN_URL, form=True, data={
        "client_id": read_secret(TARGETS["client_id"]),
        "client_secret": read_secret(TARGETS["client_secret"]),
        "refresh_token": read_secret(TARGETS["refresh_token"]), "grant_type": "refresh_token"})
    # Google may omit scope on refresh; the original verified grant stays authoritative.
    response.setdefault("scope", " ".join(saved["scopes"]))
    save_tokens(response)
    return response["access_token"]


def authorize(timeout=300):
    if not all(read_secret(TARGETS[k]) for k in ("client_id", "client_secret")):
        raise GoogleError("Desktop OAuth client must be stored first")
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Callback URLs include authorization codes. Never log them.

        def do_GET(self):
            parts = urllib.parse.urlsplit(self.path)
            params = urllib.parse.parse_qs(parts.query)
            valid = (parts.path == "/oauth/callback" and
                     secrets.compare_digest(params.get("state", [""])[0], nonce))
            self.send_response(200 if valid else 400)
            self.end_headers()
            self.wfile.write(b"Career Ops authorization received. Return to the terminal." if valid
                             else b"Invalid authorization callback.")
            if valid:
                received.update({"code": params.get("code", [None])[0],
                                 "error": bool(params.get("error"))})

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/oauth/callback"
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": read_secret(TARGETS["client_id"]), "redirect_uri": redirect,
            "response_type": "code", "scope": " ".join(SCOPES), "state": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256",
            "access_type": "offline", "prompt": "consent"})
        if not webbrowser.open(url):
            raise GoogleError("system browser could not be opened")
        print("Complete the two-scope consent in your browser. Waiting up to five minutes.")
        end = time.monotonic() + timeout
        while not received and time.monotonic() < end:
            server.handle_request()
        if not received.get("code") or received.get("error"):
            raise GoogleError("consent denied or timed out")
        tokens = http_json("POST", TOKEN_URL, form=True, data={
            "client_id": read_secret(TARGETS["client_id"]),
            "client_secret": read_secret(TARGETS["client_secret"]),
            "code": received["code"], "code_verifier": verifier,
            "redirect_uri": redirect, "grant_type": "authorization_code"})
        if not tokens.get("refresh_token"):
            raise GoogleError("offline consent did not return a refresh token")
        save_tokens(tokens)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "store-client", "authorize"])
    args = parser.parse_args(argv)
    try:
        if args.command == "store-client":
            for key in ("client_id", "client_secret"):
                value = getpass.getpass(f"Google Desktop OAuth {key} (hidden): ")
                if not value or not store_secret(TARGETS[key], value):
                    raise GoogleError("credential storage")
        elif args.command == "authorize":
            authorize()
        print(json.dumps(status(), indent=2))
        return 0
    except GoogleError as exc:
        print(json.dumps({"ok": False, "reason": str(exc), "secrets_printed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
