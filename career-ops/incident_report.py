#!/usr/bin/env python3
"""Report a failure to the Discord #incidents channel.

Why this exists
---------------
Standing owner instruction: never falsify outputs or errors. If something is
not running or breaks, say so. Silent failure is the thing to avoid.

What this does NOT do
---------------------
It does not swallow a failure. Every function returns a truthful result; when
the alert cannot be delivered, the caller is told, so the caller can report
that too. An alert that was never sent must never be reported as sent.

Delivery is by Discord webhook (``CHIEF_INCIDENTS_WEBHOOK``) or by the Hermes
cron delivery path. When neither is configured the alert is written to a local
incident log and the caller is told it was not delivered.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONTROL_PLANE = Path(__file__).resolve().parent.parent
INCIDENT_LOG = CONTROL_PLANE / "runtime" / "incidents" / "incidents.jsonl"
INCIDENTS_CHANNEL_ID = "1551586416260161699"
WEBHOOK_ENV = "CHIEF_INCIDENTS_WEBHOOK"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def build_message(*, source: str, summary: str, detail: str = "",
                  severity: str = "error") -> str:
    lines = [f"**[{severity.upper()}] {source}**", "", summary.strip()]
    if detail.strip():
        lines += ["", "```", detail.strip()[:1500], "```"]
    lines += ["", f"_reported {now_utc()}_"]
    return "\n".join(lines)


def log_incident(record: dict) -> str:
    """Append-only local record, so an incident survives a failed delivery."""
    INCIDENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with INCIDENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(INCIDENT_LOG)


def post_to_discord(webhook_url: str, content: str, *, timeout: float = 20.0) -> dict:
    payload = json.dumps({"content": content[:1900]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, method="POST", data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"delivered": True, "status": resp.status}
    except urllib.error.HTTPError as exc:
        return {"delivered": False, "status": exc.code,
                "error": exc.read().decode("utf-8", "replace")[:300]}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"delivered": False, "status": 0, "error": f"{type(exc).__name__}: {exc}"}


def report(*, source: str, summary: str, detail: str = "",
           severity: str = "error", webhook_url: str | None = None) -> dict:
    """Report an incident. Returns the TRUTH about whether it was delivered."""
    message = build_message(source=source, summary=summary, detail=detail,
                            severity=severity)
    record: dict = {"at": now_utc(), "source": source, "summary": summary,
              "detail": detail[:2000], "severity": severity,
              "channel_id": INCIDENTS_CHANNEL_ID}

    webhook = webhook_url or os.environ.get(WEBHOOK_ENV, "").strip()
    delivery = (post_to_discord(webhook, message) if webhook
                else {"delivered": False, "status": None,
                      "error": f"{WEBHOOK_ENV} not configured"})

    record["delivered"] = bool(delivery.get("delivered"))
    record["delivery"] = delivery
    record["log"] = log_incident(record)

    if not record["delivered"]:
        # Never pretend it was sent. Print the truth to stderr as well, so a
        # caller that only captures output still surfaces the failure.
        print(f"INCIDENT NOT DELIVERED to #incidents: {delivery.get('error')}",
              file=sys.stderr)
        print(message, file=sys.stderr)
    return record


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Report an incident to Discord #incidents")
    ap.add_argument("--source", required=True, help="what broke, e.g. 'linkedin weekly posts'")
    ap.add_argument("--summary", required=True, help="one-line description")
    ap.add_argument("--detail", default="", help="error text or context")
    ap.add_argument("--severity", default="error",
                    choices=("info", "warning", "error", "critical"))
    args = ap.parse_args(argv)
    result = report(source=args.source, summary=args.summary,
                    detail=args.detail, severity=args.severity)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["delivered"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
