"""Recruitment Gmail -> canonical tracker -> owned Google Calendar deadlines.

Default and initial live acceptance are dry-run. Automatic writes require an
explicit owner approval of the private reconciliation report first.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile

from career_google_auth import GoogleError, access_token, status
from career_google_clients import GmailReader, DeadlineCalendar
from career_mail_parser import parse_message, stable_id, calendar_event, identity_key, identity_text
from career_mail_tracker import WorkbookTracker

REPO = Path(__file__).resolve().parent.parent
CONFIG = Path(__file__).with_name("career_mail_config.json")
RUNTIME = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "hermes" / "runtime" / "career-ops" / "gmail-monitor"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def read_json(path, default):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else default


def pair(record):
    return tuple(identity_key(record.get(k)) for k in ("company", "role"))


def canonical_candidates(signal, raw, records):
    """Require both exact normalized employer and full role evidence.

    No sender-domain guesses, substring job matches, or single-company matches.
    Ambiguous regions/application identities remain review-only.
    """
    text = " " + identity_key(identity_text(raw)) + " "
    matches = []
    for record in records:
        company, role = pair(record)
        if not company or not role:
            continue
        if signal.get("application_identity") and record.get("application_identity") and signal["application_identity"] != record["application_identity"]:
            continue
        if signal.get("region") and record.get("region") != signal["region"]:
            continue
        if signal.get("company"):
            company_matches = identity_key(signal["company"]) == company
        else:
            company_matches = len(company) >= 3 and " " + company + " " in text
        if signal.get("role"):
            role_matches = identity_key(signal["role"]) == role
        else:
            role_matches = len(role) >= 5 and " " + role + " " in text
        if company_matches and role_matches:
            matches.append(record)
    return matches


def time_key(stamp):
    try:
        value = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("missing timezone")
        return value.timestamp()
    except (ValueError, TypeError):
        return 0


def reconcile(messages, existing, processed=()):
    records = copy.deepcopy(existing)
    seen = set(processed)
    changed, review, events, new_ids = {}, [], {}, set()
    for record in records:
        if record.get("calendar_pending"):
            event = calendar_event(record)
            if event:
                changed[record["application_id"]] = record
                events[record["application_id"]] = event
    counts = {"messages_read": len(messages), "likely_applications": 0, "matched_existing": 0,
              "proposed_new_rows": 0, "assessments_interviews": 0, "ignored": 0,
              "duplicates": 0, "exact_deadlines": 0, "derived_deadlines": 0,
              "ambiguous_deadlines": 0}
    for raw in sorted(messages, key=lambda m: int(m.get("internalDate") or 0) if "payload" in m
                      else time_key(m.get("received_at")) * 1000):
        signal = parse_message(raw)
        if signal is None:
            counts["ignored"] += 1
            continue
        counts["likely_applications"] += 1
        mid, thread = signal["gmail_message_id"], signal["gmail_thread_id"]
        new_ids.add(mid)
        if mid in seen or any(mid in r.get("seen_message_ids", []) for r in records):
            counts["duplicates"] += 1
            continue
        if signal.get("assessment_type"):
            counts["assessments_interviews"] += 1
        extracted_deadline = signal["deadline"]
        if extracted_deadline.get("needs_review"):
            counts["ambiguous_deadlines"] += 1
        elif extracted_deadline.get("kind"):
            counts[extracted_deadline["kind"].lower() + "_deadlines"] += 1
        candidates = [r for r in records if thread in r.get("thread_ids", [])]
        if not candidates:
            candidates = canonical_candidates(signal, raw, records)
        if len(candidates) > 1:
            signal["needs_review"] = True
            signal["review_reason"] = "multiple canonical applications match"
            review.append(signal)
            continue
        if candidates:
            record = candidates[0]
            if any(signal.get(key) and identity_key(signal[key]) != identity_key(record.get(key))
                   for key in ("company", "role", "region")):
                signal.update(needs_review=True, review_reason="thread conflicts with company/role/region evidence")
                review.append(signal)
                continue
            counts["matched_existing"] += 1
            signal.setdefault("identity_evidence", []).append("unique canonical company/full-role or Gmail thread match")
            signal.update(company=record["company"], role=record["role"], region=record["region"])
            signal["needs_review"] = bool(signal["deadline"]["needs_review"])
        elif not all(signal.get(k) for k in ("company", "role", "region")) or signal["region"] not in {"uk", "dubai", "japan", "singapore"}:
            signal.update(needs_review=True, review_reason="company, role or canonical region unresolved")
            review.append(signal)
            continue
        else:
            record = {"company": signal["company"], "role": signal["role"], "region": signal["region"],
                      "application_id": stable_id(signal["company"], signal["role"],
                                                  signal.get("application_identity") or thread),
                      "seen_message_ids": [], "thread_ids": [], "owner_confirmed_fields": []}
            records.append(record)
            counts["proposed_new_rows"] += 1
        record.setdefault("seen_message_ids", []).append(mid)
        if thread not in record.setdefault("thread_ids", []):
            record["thread_ids"].append(thread)
        seen.add(mid)
        if time_key(signal["last_update_timestamp"]) < time_key(record.get("last_update_timestamp")):
            changed[record["application_id"]] = record
            continue  # stale mail never rolls state or deadlines backwards
        protected = set(record.get("owner_confirmed_fields", [])) | {"company", "role", "region"}
        previous_deadline = copy.deepcopy(record.get("deadline"))
        for key, value in signal.items():
            if key not in protected and value is not None and key != "deadline":
                if key == "application_date" and record.get(key):
                    continue
                record[key] = value
        deadline = signal["deadline"]
        if "deadline" not in protected and (deadline.get("value") or deadline.get("needs_review")):
            record["deadline"] = deadline
        elif previous_deadline:
            record["deadline"] = previous_deadline
        if not time_key(signal["last_update_timestamp"]):
            record["needs_review"] = True
            record["review_reason"] = "received timestamp is unavailable"
        record["confidence"] = "high" if not record.get("needs_review") else "needs_review"
        if record.get("needs_review"):
            review.append(copy.deepcopy(record))
        changed[record["application_id"]] = record
        event = calendar_event(record)
        if event:
            events[record["application_id"]] = event
        else:
            events.pop(record["application_id"], None)
    return {"counts": counts, "proposed_records": list(changed.values()),
            "needs_review": review, "proposed_calendar_events": list(events.values()),
            "processed_ids": sorted(new_ids), "gmail_mutations": 0,
            "model_calls": 0, "tracker_writes": 0, "calendar_writes": 0}


def report_hash(report):
    return hashlib.sha256(json.dumps({k: v for k, v in report.items() if k != "report_id"},
                                     sort_keys=True).encode()).hexdigest()


def apply_report(report, tracker, calendar, audit_path):
    """No checkpoint commit until workbook+calendar receipts have been saved.

    Deterministic event IDs and workbook application IDs make partial failure
    replay safe; do not claim distributed atomicity.
    """
    event_index = {e["extendedProperties"]["private"]["careerOpsApplication"]: e
                   for e in report["proposed_calendar_events"]}
    receipt = []
    for record in report["proposed_records"]:
        event = event_index.get(record["application_id"])
        record["calendar_pending"] = bool(event)
        write = tracker.upsert(record)
        receipt.append({"application_id": record["application_id"], "message_id": record.get("gmail_message_id"),
                        "workbook": write})
        atomic_json(audit_path, receipt)
        event = event_index.get(record["application_id"])
        if event:
            response = calendar.ensure(event)
            if response.get("id") != event["id"]:
                raise GoogleError("calendar receipt ID mismatch")
            record["calendar_event_id"] = response["id"]
            record["calendar_pending"] = False
            saved = tracker.upsert(record)
            receipt[-1].update(calendar_event_id=response["id"], calendar_status="confirmed",
                               event_id_workbook=saved)
            atomic_json(audit_path, receipt)
    return receipt


def run_scan(config, runtime, *, apply=False, reader=None, calendar=None, tracker=None):
    runtime = Path(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / "scan.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        approved = read_json(runtime / "write-approval.json", {})
        if apply and not approved.get("approved_report_id"):
            raise ValueError("automatic writes disabled: owner must approve the initial dry-run report")
        state = read_json(runtime / "checkpoint.json", {})
        if tracker is None:
            profiles = read_json(REPO / config["regional_profiles"], {})
            tracker = WorkbookTracker(profiles, runtime / "backups")
        records, fingerprints = tracker.read()
        if reader is None:
            reader = GmailReader(access_token)
            calendar = DeadlineCalendar(access_token, config["calendar_id"])
        window = reader.read_window(state.get("history_id"), days=config["backfill_days"],
                                    max_messages=config["max_messages"])
        report = reconcile(window["messages"], records, state.get("processed_ids", []))
        report.update(mode="apply" if apply else "dry-run", scan_mode=window["mode"],
                      checkpoint_proposed=window["checkpoint"], workbook_fingerprints=fingerprints,
                      generated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        report["report_id"] = report_hash(report)
        if not apply:
            # Private report only: never commit the read checkpoint or write a tracker/event.
            atomic_json(runtime / "last-dry-run.json", report)
            return report
        receipt = apply_report(report, tracker, calendar, runtime / (report["report_id"] + "-audit.json"))
        report["tracker_writes"] = len(receipt)
        report["calendar_writes"] = sum("calendar_event_id" in r for r in receipt)
        atomic_json(runtime / "checkpoint.json", {
            "history_id": window["checkpoint"],
            "processed_ids": sorted(set(state.get("processed_ids", [])) | set(report["processed_ids"])),
            "last_completed_at": report["generated_at"]})
        atomic_json(runtime / "last-applied.json", report)
        return report
    finally:
        os.close(fd)
        lock.unlink()


def schedule_plan(config):
    return {"task_name": "ChiefCareerGmailMonitor", "install_enabled": False,
            "interval_minutes": config["scan_interval_minutes"],
            "interpreter": str(Path(os.environ.get("LOCALAPPDATA", "")) / "hermes/hermes-agent/venv/Scripts/python.exe"),
            "arguments": f'"{Path(__file__).resolve()}" scan --apply', "working_directory": str(REPO),
            "principal": "current owner, interactive token", "overlap": "refuse overlapping scan",
            "note": "Do not install/enable before OAuth and approved initial dry-run."}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "scan", "enable-writes", "schedule-plan"])
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--runtime", default=str(RUNTIME))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve-report")
    args = parser.parse_args(argv)
    config = read_json(args.config, {})
    root = Path(args.runtime)
    try:
        if args.command == "status":
            result = {"oauth": status(), "automatic_writes_enabled": bool(read_json(root / "write-approval.json", {}).get("approved_report_id")),
                      "scan_interval_minutes": config["scan_interval_minutes"], "gmail_read_only": True}
        elif args.command == "schedule-plan":
            result = schedule_plan(config)
        elif args.command == "enable-writes":
            report = read_json(root / "last-dry-run.json", {})
            if not args.approve_report or args.approve_report != report.get("report_id") or report_hash(report) != args.approve_report:
                raise ValueError("review the live dry-run report and supply its exact report ID")
            atomic_json(root / "write-approval.json", {"approved_report_id": args.approve_report,
                                                      "approved_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            result = {"writes_enabled": True, "tracker_writes": 0, "calendar_writes": 0}
        else:
            report = run_scan(config, root, apply=args.apply)
            # Summary stdout has counts only. Detailed private report stays local.
            result = {k: report[k] for k in ("mode", "scan_mode", "report_id", "counts", "gmail_mutations",
                                           "model_calls", "tracker_writes", "calendar_writes")}
            result["private_report"] = str(root / ("last-applied.json" if args.apply else "last-dry-run.json"))
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        # Arbitrary exceptions may contain credential or mailbox data. Do not echo.
        reason = str(exc) if isinstance(exc, GoogleError) else "Local scan/configuration failed; checkpoint not advanced"
        print(json.dumps({"ok": False, "reason": reason, "error_type": type(exc).__name__,
                          "gmail_mutations": 0, "secrets_printed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
