"""Allowlisted API clients. Gmail has GET-only methods; Calendar has no delete."""
from __future__ import annotations

import datetime as dt
import re
import hashlib
import json
import time
from urllib.parse import quote, urlencode

from career_google_auth import GoogleError, http_json

RECRUITMENT_QUERY = "{application assessment interview recruiter candidate hirevue shl cappfinity testgorilla deadline offer rejection unsuccessful withdrawal}"

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars"


class GmailReader:
    def __init__(self, token, transport=http_json, *, request_interval=1.0, clock=time.monotonic, sleep=time.sleep):
        self._token, self._transport = token, transport
        self._interval, self._clock, self._sleep = request_interval, clock, sleep
        self._last_request = None
        self._quota_recoveries = 0

    def _get(self, path, **params):
        if path.rsplit("/", 1)[-1] in {"send", "modify", "batchModify", "batchDelete", "trash", "untrash", "insert", "import"} or not re.fullmatch(r"/(profile|messages|history|messages/[a-zA-Z0-9_-]+)", path):
            raise ValueError("Gmail path is not allowlisted")
        now = self._clock()
        if self._last_request is not None:
            delay = self._interval - (now - self._last_request)
            if delay > 0:
                self._sleep(delay)
        self._last_request = self._clock()
        while True:
            try:
                return self._transport("GET", GMAIL + path + ("?" + urlencode(params) if params else ""),
                                       token=self._token() if callable(self._token) else self._token)
            except GoogleError as exc:
                if exc.reason not in {"rateLimitExceeded", "userRateLimitExceeded"} or self._quota_recoveries >= 2:
                    raise
                self._quota_recoveries += 1
                self._sleep(60)
                self._last_request = self._clock()

    def read_window(self, checkpoint=None, *, days=30, max_messages=2000, now=None):
        """Complete pagination or fail without advancing the caller's checkpoint.

        Capture profile history BEFORE backfill to avoid losing arrivals during it.
        Expired history falls back to the configured window, with ID dedupe.
        """
        profile = self._get("/profile")
        baseline = profile["historyId"]
        ids, seen = [], set()
        mode = "incremental" if checkpoint else "backfill"

        def add(items):
            for item in items:
                mid = item["id"]
                if mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
                if len(ids) > max_messages:
                    raise GoogleError("scan safety cap reached; checkpoint not advanced")

        if checkpoint:
            page = None
            try:
                while True:
                    params = {"startHistoryId": checkpoint, "historyTypes": "messageAdded", "maxResults": 500}
                    if page:
                        params["pageToken"] = page
                    result = self._get("/history", **params)
                    for h in result.get("history", []):
                        add([m["message"] for m in h.get("messagesAdded", [])])
                    page = result.get("nextPageToken")
                    if not page:
                        break
            except GoogleError as exc:
                if exc.status != 404:
                    raise
                mode = "expired_history_backfill"
                checkpoint = None
                ids, seen = [], set()
        if not checkpoint:
            cutoff = int(((now or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=days)).timestamp())
            page = None
            while True:
                params = {"q": f"after:{cutoff} " + RECRUITMENT_QUERY, "maxResults": 500, "includeSpamTrash": "false"}
                if page:
                    params["pageToken"] = page
                result = self._get("/messages", **params)
                add(result.get("messages", []))
                page = result.get("nextPageToken")
                if not page:
                    break
        # IDs only come from Google, never email content or tool instructions.
        messages = [self._get("/messages/" + mid, format="full") for mid in ids]
        return {"messages": messages, "checkpoint": str(baseline), "mode": mode,
                "messages_read": len(messages), "gmail_mutations": 0}


class DeadlineCalendar:
    def __init__(self, token, calendar_id="primary", transport=http_json):
        self._token, self.calendar_id, self._transport = token, calendar_id, transport

    def _call(self, method, event_id, body=None):
        if method not in {"GET", "POST", "PATCH"} or not re.fullmatch(r"[a-v0-9]+", event_id):
            raise ValueError("Calendar operation is not allowlisted")
        base = CALENDAR + "/" + quote(self.calendar_id, safe="") + "/events"
        url = base if method == "POST" else base + "/" + event_id
        if method != "GET":
            url += "?sendUpdates=none"
        return self._transport(method, url, token=self._token() if callable(self._token) else self._token, data=body)

    def ensure(self, event):
        """Deterministic client event ID recovers insert-success/local-save failure."""
        event = json.loads(json.dumps(event))
        digest = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
        event["extendedProperties"]["private"]["careerOpsDigest"] = digest
        eid = event["id"]
        try:
            old = self._call("GET", eid)
        except GoogleError as exc:
            if exc.status != 404:
                raise
            try:
                return self._call("POST", eid, event)
            except GoogleError as conflict:
                if conflict.status != 409:
                    raise
                old = self._call("GET", eid)
        private = (old.get("extendedProperties") or {}).get("private") or {}
        if private.get("careerOpsApplication") != event["extendedProperties"]["private"]["careerOpsApplication"]:
            raise GoogleError("calendar event ownership mismatch")
        if private.get("careerOpsDigest") == digest:
            return old
        return self._call("PATCH", eid, {k: v for k, v in event.items() if k != "id"})
