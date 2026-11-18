#!/usr/bin/env python3
"""Daily Google Calendar sync for the owner's task list.

Runs at 04:00 local, before the new day. It:
  1. reads owner additions + completed items + tracker deadlines + live assessments
  2. removes completed/past tasks from the calendar
  3. ranks the rest by urgency (assessments first, then deadlines, then everything else)
  4. writes one event per task across the working window 11:00-22:00

Deterministic, idempotent: re-running the same day produces the same calendar.
Never touches events it did not create (owner-owned events are left alone).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from career_google_auth import access_token, http_json, GoogleError  # noqa: E402

CALENDAR = "https://www.googleapis.com/calendar/v3/calendars"
CONTROL_PLANE = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
TASK_LIST_DIR = CONTROL_PLANE / "runtime" / "task-list"
ADDITIONS = TASK_LIST_DIR / "owner-additions.md"
COMPLETED = TASK_LIST_DIR / "completed.md"
STATE = TASK_LIST_DIR / "calendar-state.json"

WINDOW_START = 11  # 11:00 local
WINDOW_END = 22    # 22:00 local
STEP_MINUTES = 30
MAX_ASSESSMENTS = 8
MAX_TASKS = 21     # 11:00-22:00 at 30 min = 22 slots; keep one spare

# Only events carrying this private property are ours to delete.
OWNER_TAG = "mukundChiefTaskList"


def _tz():
    """Local timezone from the machine, so 11:00 means 11:00 for the owner."""
    return dt.datetime.now().astimezone().tzinfo


def _today_local(now=None):
    return (now or dt.datetime.now()).astimezone().date()


def _iso(local_dt):
    return local_dt.isoformat()


def _load_completed():
    """Completed task keys, one per line: '- <key> — <note>'."""
    done = []
    if not COMPLETED.exists():
        return done
    for line in COMPLETED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- "):
            done.append(line[2:].strip())
    return done


def _load_additions():
    """Owner additions from the markdown file, newest section first."""
    if not ADDITIONS.exists():
        return []
    text = ADDITIONS.read_text(encoding="utf-8")
    items = []
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current:
            items.append({"date": current, "text": stripped[2:].strip()})
    return items


def _key(text):
    """Stable identity for a task so completion can be matched across days."""
    import re
    return re.sub(r"\s+", " ", text.strip().lower())[:80]


def _parse_tracker(path):
    """UK tracker rows with a real deadline, plus counts."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Jobs"]
    rows = list(ws.iter_rows(values_only=True))
    out, counts = [], {}
    for r in rows[2:]:
        if not r[1]:
            continue
        status = r[5] or "None"
        counts[status] = counts.get(status, 0) + 1
        if not r[4]:
            continue
        deadline = r[4]
        if not isinstance(deadline, dt.datetime):
            continue
        if deadline.date() < _today_local():
            continue
        out.append({"company": r[1], "role": r[2], "deadline": deadline,
                    "status": status, "link": r[3]})
    out.sort(key=lambda x: x["deadline"])
    return out, counts


#: Assessments Mukund has confirmed done, or that are closed. Never re-listed.
DONE_ASSESSMENTS = {
    "shell", "bdo", "national highways", "pwc", "revolut", "fti consulting",
    "tpp group", "barclays", "natwest", "turnkey", "wtw",
}


def _parse_assessments(pending_review_path):
    """Assessment records from the Gmail monitor's pending-review file.

    Only records with a live future deadline, or no deadline at all but received
    recently, are kept. Done/closed employers are dropped.
    """
    if not pending_review_path.exists():
        return []
    data = json.loads(pending_review_path.read_text(encoding="utf-8"))
    today = _today_local()
    out = []
    for mid, rec in data.items():
        atype = rec.get("assessment_type")
        stage = (rec.get("current_stage") or "").lower()
        if not atype and "assessment" not in stage and "interview" not in stage:
            continue
        if atype == "assessment_completed" or stage == "assessment_completed":
            continue

        company = (rec.get("company") or "").strip()
        role = (rec.get("role") or "").strip()
        # Drop known-done employers.
        if company and company.split()[0].lower() in DONE_ASSESSMENTS:
            continue
        if not company and role and role.split()[0].lower() in DONE_ASSESSMENTS:
            continue

        dl = rec.get("deadline") or {}
        deadline = _to_dt(dl.get("value"))
        received = _to_dt(rec.get("assessment_received_date") or rec.get("last_update_timestamp"))

        # A deadline in the past means closed unless the employer explicitly
        # invited a late completion (those carry no deadline value).
        if deadline and deadline.date() < today:
            continue
        # With no deadline, only keep it if the invite is recent (14 days).
        if not deadline and received and received.date() < today - dt.timedelta(days=14):
            continue

        out.append({
            "id": mid,
            "company": company or "Unknown company",
            "role": role or "Role not stated in the email",
            "type": atype or stage,
            "deadline": dl.get("value"),
            "deadline_kind": dl.get("kind"),
            "link": rec.get("assessment_interview_link"),
            "received": rec.get("assessment_received_date") or rec.get("last_update_timestamp"),
        })
    out.sort(key=lambda x: (str(x["deadline"] or "9999"), str(x["received"])))
    return out


def _rank(tasks, today):
    """Assessments first, then by deadline proximity, then everything else."""
    def score(t):
        if t["kind"] == "assessment":
            base = 0
        elif t["deadline"]:
            days = (t["deadline"] - dt.datetime.combine(today, dt.time())).days
            base = 100 + max(days, 0)
        else:
            base = 500
        return (base, t["deadline"] or dt.datetime.max.replace(tzinfo=None))

    return sorted(tasks, key=score)


def _build_tasks(today, additions, completed_keys, tracker_rows, assessments):
    tasks, seen = [], set()

    def add(kind, title, detail, deadline=None, link=None, key=None):
        k = key or _key(title)
        if k in seen or k in completed_keys:
            return
        seen.add(k)
        tasks.append({"kind": kind, "title": title, "detail": detail,
                      "deadline": deadline, "link": link, "key": k})

    for a in additions:
        add("owner", a["text"], f"Added by Mukund on {a['date']}",
            key=_key("owner:" + a["text"]))

    # Assessments always rank first; cap so the day stays workable.
    for a in assessments[:MAX_ASSESSMENTS]:
        company = a["company"] or "Unknown company"
        role = a["role"] or "Role not stated in the email"
        atype = a["type"] or "assessment"
        dl = a["deadline"]
        detail = f"Assessment type: {atype}"
        if dl:
            detail += f" · Deadline: {dl}"
        if a["link"]:
            detail += f" · Link: {a['link']}"
        add("assessment", f"ASSESSMENT — {company} — {role}", detail,
            deadline=_to_dt(dl), link=a["link"], key=_key("assessment:" + company + role))

    for r in tracker_rows:
        if r["status"] == "Applied":
            continue
        title = f"{r['company']} — {r['role']}"
        detail = f"Status: {r['status']} · Deadline: {r['deadline'].date()}"
        if r["link"]:
            detail += f" · {r['link']}"
        add("apply", title, detail, deadline=r["deadline"], link=r["link"])

    return tasks


def _to_dt(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _slot(start, index):
    slot = start + dt.timedelta(minutes=STEP_MINUTES * index)
    return slot, slot + dt.timedelta(minutes=STEP_MINUTES)


def _event(task, start, end, calendar_id):
    eid = "task" + __import__("hashlib").sha256(
        (OWNER_TAG + task["key"] + str(start.date())).encode()).hexdigest()[:32]
    body = {
        "id": eid,
        "summary": task["title"][:180],
        "description": "\n".join([task["detail"], f"Task key: {task['key']}"]),
        "start": {"dateTime": _iso(start.astimezone())},
        "end": {"dateTime": _iso(end.astimezone())},
        "extendedProperties": {"private": {"ownerTag": OWNER_TAG, "taskKey": task["key"]}},
        "reminders": {"useDefault": False,
                      "overrides": [{"method": "popup", "minutes": 15}]},
    }
    return body


def _list_owned(calendar_id, token):
    """Events on the target day that carry our private tag."""
    tz = _tz()
    day = _today_local()
    start = dt.datetime.combine(day, dt.time(WINDOW_START)).astimezone(tz)
    end = dt.datetime.combine(day, dt.time(23, 59)).astimezone(tz)
    url = f"{CALENDAR}/{calendar_id}/events?" + __import__("urllib.parse", fromlist=["urlencode"]).urlencode({
        "timeMin": start.isoformat(), "timeMax": end.isoformat(),
        "singleEvents": "true", "maxResults": 250,
    })
    resp = http_json("GET", url, token=token)
    owned = []
    for ev in resp.get("items", []):
        priv = (ev.get("extendedProperties") or {}).get("private") or {}
        if priv.get("ownerTag") == OWNER_TAG:
            owned.append(ev)
    return owned


def _delete(calendar_id, event_id, token):
    url = f"{CALENDAR}/{calendar_id}/events/{event_id}?sendUpdates=none"
    return http_json("DELETE", url, token=token)


def _upsert(calendar_id, body, token):
    eid = body["id"]
    url = f"{CALENDAR}/{calendar_id}/events/{eid}?sendUpdates=none"
    try:
        return http_json("PUT", url, token=token, data=body)
    except GoogleError as exc:
        if exc.status != 404:
            raise
        url = f"{CALENDAR}/{calendar_id}/events?sendUpdates=none"
        return http_json("POST", url, token=token, data=body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--calendar-id", default="primary")
    args = ap.parse_args()

    today = _today_local()
    tz = _tz()
    additions = _load_additions()
    completed_keys = {_key(c) for c in _load_completed()}

    tracker_path = Path(r"C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx")
    tracker_rows, counts = ([], {})
    if tracker_path.exists():
        tracker_rows, counts = _parse_tracker(tracker_path)

    import os
    pending = Path(os.path.expandvars(
        r"%LOCALAPPDATA%\hermes\runtime\career-ops\gmail-monitor\pending-review.json"))
    assessments = _parse_assessments(pending)

    tasks = _build_tasks(today, additions, completed_keys, tracker_rows, assessments)
    tasks = _rank(tasks, today)[:MAX_TASKS]

    start = dt.datetime.combine(today, dt.time(WINDOW_START))
    events = []
    for i, t in enumerate(tasks):
        s, e = _slot(start, i)
        if s.hour >= WINDOW_END:
            break
        events.append(_event(t, s, e, args.calendar_id))

    result = {
        "date": today.isoformat(),
        "tasks_total": len(tasks),
        "events_planned": len(events),
        "dropped_completed": len(completed_keys),
        "tracker_counts": counts,
        "assessments_found": len(assessments),
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        result["plan"] = [{"time": ev["start"]["dateTime"], "summary": ev["summary"]}
                          for ev in events]
        print(json.dumps(result, indent=2, default=str))
        return 0

    token = access_token()
    owned = _list_owned(args.calendar_id, token)
    keep_ids = {ev["id"] for ev in events}
    removed = 0
    for ev in owned:
        if ev["id"] not in keep_ids:
            _delete(args.calendar_id, ev["id"], token)
            removed += 1

    written = 0
    for ev in events:
        _upsert(args.calendar_id, ev, token)
        written += 1

    result.update({"events_written": written, "events_removed": removed,
                   "calendar": args.calendar_id})
    STATE.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
