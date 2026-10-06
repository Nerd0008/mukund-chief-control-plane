"""Evidence-only recruitment parsing. No models, tools, or instructions from mail."""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from application_inbox import parse_gmail_api_message, strip_quoted

UTC = dt.timezone.utc
ZONES = {"BST": dt.timezone(dt.timedelta(hours=1)), "GMT": UTC, "UTC": UTC,
         "JST": dt.timezone(dt.timedelta(hours=9)), "SGT": dt.timezone(dt.timedelta(hours=8)),
         "GST": dt.timezone(dt.timedelta(hours=4))}
MONTHS = {name.lower(): i for i, name in enumerate(
    "January February March April May June July August September October November December".split(), 1)}
PATTERNS = [
    ("deadline_extension", r"deadline (?:has been |is |was )?(?:extended|extension)|extended (?:the |your )?deadline"),
    ("rejection", r"not (?:be )?(?:proceeding|progressing)|unsuccessful|not successful|other candidates|not been selected"),
    ("withdrawal", r"application (?:has been |was |is )?withdrawn|withdrawal of your application"),
    ("offer", r"offer of employment|pleased to offer you|formal offer|conditional offer"),
    ("assessment_centre", r"assessment cent(?:re|er)"),
    ("hirevue_video_interview", r"hirevue|video interview"),
    ("telephone_interview", r"telephone interview|phone interview"),
    ("technical_interview", r"technical interview"),
    ("interview", r"invitation to interview|invite you (?:to|for) (?:an )?interview|interview invitation"),
    ("coding_assessment", r"coding (?:assessment|challenge|test)|codility|hackerrank"),
    ("psychometric_assessment", r"psychometric|situational judg(?:e)?ment|\bsjt\b|numerical (?:assessment|reasoning|test)|verbal (?:assessment|reasoning|test)"),
    ("online_assessment", r"online assessment|complete (?:an |the |your )?assessment|shl|cappfinity|testgorilla"),
    ("application_under_review", r"application (?:is |has been )?(?:under review|being reviewed)|reviewing your application"),
    ("application_received", r"received your application|application (?:has been |was |is )?received|your application for [^\n.!?]{2,180}? has been received"),
    ("application_confirmation", r"thank(?:s| you) for (?:applying|your application)|application (?:confirmation|has been submitted)"),
    ("recruiter_update", r"update (?:on|regarding) your application|application update|recruitment update"),
]


def clean_url(url):
    """Never carry OAuth/session secrets into tracker/report links."""
    parsed = urlsplit(url.rstrip('.,)>'))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        return None
    # Assessment signed URLs can be sensitive. Keep the public route only.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def extract_deadline(text, received_at, message_id, thread_id):
    base = {"source_message_id": message_id, "source_thread_id": thread_id,
            "kind": None, "value": None, "timezone": None, "needs_review": False}
    candidates = []
    # Restrict dates to explicit deadline language rather than newsletter dates.
    expression = (r"(?:complete by|deadline(?: is|:| extended to| has been extended to)?|due(?: by)?|"
                  r"expires(?: on)?|until)\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"
                  r"(?:\s+(?:at\s+)?(\d{1,2}):(\d{2})(?:\s+([A-Z]{2,4}))?)?")
    for match in re.finditer(expression, text, re.I):
        day, month, year, hour, minute, zone = match.groups()
        try:
            date = dt.date(int(year), MONTHS[month.lower()], int(day))
            if hour is None:
                candidates.append({**base, "kind": "EXACT", "value": date.isoformat(),
                                   "date_only": True, "reason": "explicit date-only deadline"})
            else:
                tz = ZONES.get((zone or "").upper())
                if tz is None:
                    return {**base, "needs_review": True, "reason": "deadline time has no unambiguous timezone"}
                stamp = dt.datetime.combine(date, dt.time(int(hour), int(minute)), tz)
                candidates.append({**base, "kind": "EXACT", "value": stamp.isoformat(),
                                   "date_only": False, "timezone": zone.upper(),
                                   "reason": "explicit deadline date, time and timezone"})
        except (ValueError, KeyError):
            return {**base, "needs_review": True, "reason": "invalid or unsupported deadline date"}
    for match in re.finditer(r"within\s+(\d+)\s+(business\s+|working\s+)?days", text, re.I):
        if match.group(2):
            return {**base, "needs_review": True, "reason": "business-day deadline needs a holiday/calendar policy"}
        try:
            received = dt.datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            if received.tzinfo is None:
                raise ValueError("naive received timestamp")
            stamp = received + dt.timedelta(days=int(match.group(1)))
            candidates.append({**base, "kind": "DERIVED", "value": stamp.isoformat(),
                               "date_only": False, "timezone": "UTC" if stamp.utcoffset() == dt.timedelta() else str(stamp.tzinfo),
                               "reason": f"email received timestamp plus {match.group(1)} calendar days"})
        except (ValueError, TypeError, AttributeError):
            return {**base, "needs_review": True, "reason": "relative deadline lacks a reliable received timestamp"}
    values = {c["value"] for c in candidates}
    if len(values) > 1:
        return {**base, "needs_review": True, "reason": "multiple conflicting deadlines; owner review required"}
    if candidates:
        return candidates[0]
    if re.search(r"deadline|complete by|within|as soon as|due\b|expires", text, re.I):
        return {**base, "needs_review": True, "reason": "deadline wording contains no supported unambiguous date"}
    return base


def identity_key(value):
    """Normalize typography only; never fuzzy-match different jobs/employers."""
    import unicodedata
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"[^\W_]+", value))


def identity_text(raw):
    mail = parse_gmail_api_message(raw) if "payload" in raw else dict(raw)
    return (mail.get("subject") or "") + "\n" + strip_quoted(mail.get("body") or "")


def extract_identity(text):
    company = role = None
    evidence = []
    for field, value in re.findall(r"(?im)^\s*(company|employer|role|position|job title)\s*:\s*([^\n]+)", text):
        if field.lower() in {"company", "employer"}:
            company = value.strip()[:200]
        else:
            role = value.strip()[:200]
        evidence.append("explicit " + field.lower() + " field")
    # Bound captures to one sentence/line. 'at' in a later paragraph is not an employer.
    match = re.search(r"(?:applying|application)\s+(?:for|to)\s+(?:(?:the|our)\s+)?([^\n.!?]{2,180}?)\s+(?:role\s+)?(?:at|with)\s+([^\n.!?]{2,100})(?=[.!?\n]|$)", text, re.I)
    if match:
        role = role or match.group(1).strip()
        company = company or match.group(2).strip()
        evidence.append("bounded application role at employer phrase")
    if not role:
        match = re.search(r"(?:applying|application)\s+for\s+(?:(?:the|our)\s+)?([^\n.!?]{2,180}?)\s+(?:opportunity|position|role)(?=[.!?\n]|$)", text, re.I)
        if match:
            role = match.group(1).strip()
            evidence.append("bounded application role phrase")
    if not company:
        match = re.search(r"thank(?:s| you) for applying (?:to|at|with)\s+([^\n.!?]{2,100})(?=[.!?\n]|$)", text, re.I)
        if match:
            company = match.group(1).strip()
            evidence.append("explicit applying to employer phrase")
    return company, role, evidence


def parse_message(raw):
    mail = parse_gmail_api_message(raw) if "payload" in raw else dict(raw)
    mid = mail.get("_gmail_id") or mail.get("message_id")
    thread = mail.get("_gmail_thread") or mail.get("thread_id")
    received = mail.get("received_at") or ""
    text = (mail.get("subject") or "") + "\n" + strip_quoted(mail.get("body") or "")
    if re.search(r"job alerts?|newsletter|unsubscribe|recommended jobs|jobs you may|marketing", text, re.I):
        # An unsubscribe footer alone is not enough to reject an explicit receipt.
        if not re.search(r"your application|thank you for applying|invitation to interview", text, re.I):
            return None
    kind = next((name for name, pattern in PATTERNS if re.search(pattern, text, re.I)), None)
    if not kind or not mid or not thread:
        return None
    company, role, identity_evidence = extract_identity(text)
    region = mail.get("region")
    if not region:
        named = re.findall(r"(?im)^\s*(?:region|location)\s*:\s*([^\n]+)", text)
        for name in named:
            for key, pattern in {"uk": r"\buk\b|united kingdom|london", "dubai": r"dubai|\buae\b",
                                 "japan": r"japan|tokyo", "singapore": r"singapore"}.items():
                if re.search(pattern, name, re.I):
                    region = key
    identity = re.search(r"(?:application|candidate|requisition|job)\s+(?:id|reference|ref)\s*[:#]\s*([A-Za-z0-9_-]+)", text, re.I)
    assessment = kind if "assessment" in kind or "interview" in kind else None
    provider = next((name for name in ("SHL", "Cappfinity", "HireVue", "TestGorilla", "Codility", "HackerRank")
                     if re.search(r"\b" + name + r"\b", text, re.I)), None)
    urls = [clean_url(u) for u in re.findall(r"https?://[^\s<>\"']+", text)]
    deadline = extract_deadline(text, received, mid, thread)
    return {"company": company, "role": role, "region": region, "identity_evidence": identity_evidence, "latest_status": kind,
            "current_stage": "assessment" if assessment and "assessment" in assessment else
            "interview" if assessment else kind,
            "assessment_type": assessment, "assessment_provider": provider,
            "assessment_received_date": received if assessment else None,
            "application_date": received[:10] if kind.startswith("application_") and kind != "application_under_review" else None,
            "application_identity": identity.group(1) if identity else None,
            "source_application_channel": provider or "Gmail recruitment notification",
            "assessment_interview_link": next((u for u in urls if u), None),
            "recruiter_contact": mail.get("from"), "gmail_message_id": mid,
            "gmail_thread_id": thread, "last_update_timestamp": received,
            "deadline": deadline, "confidence": "high" if company and role else "low",
            "needs_review": bool(deadline["needs_review"] or not company or not role),
            "classification_reason": "explicit recruitment phrase; no model inference"}


def stable_id(company, role, identity):
    text = "|".join(re.sub(r"\s+", " ", str(v or "").strip().casefold()) for v in (company, role, identity))
    return hashlib.sha256(text.encode()).hexdigest()


def calendar_event(record):
    deadline = record.get("deadline") or {}
    if record.get("needs_review") or not deadline.get("value") or deadline.get("needs_review"):
        return None
    if not record.get("company") or not record.get("role"):
        return None
    eid = record.get("calendar_event_id") or "career" + record["application_id"][:48]
    # Hex application IDs + base32hex-compatible prefix are accepted by Calendar.
    event = {"id": eid, "summary": f"DEADLINE — {record['company']} — {record['role']}",
             "description": "\n".join([
                 f"Company: {record['company']}", f"Role: {record['role']}",
                 f"Type: {record.get('assessment_type') or record['latest_status']}",
                 f"Actual deadline: {deadline['value']} ({deadline.get('timezone') or 'date-only'})",
                 f"Deadline evidence: {deadline['kind']} — {deadline.get('reason', '')}",
                 f"Link: {record.get('assessment_interview_link') or 'not supplied'}",
                 f"Gmail message ID: {deadline['source_message_id']}",
                 f"Gmail thread ID: {deadline['source_thread_id']}"]),
             "reminders": {"useDefault": False, "overrides": [
                 {"method": "popup", "minutes": 1440}, {"method": "popup", "minutes": 180}]},
             "extendedProperties": {"private": {"careerOpsApplication": record["application_id"]}}}
    if deadline.get("date_only"):
        date = dt.date.fromisoformat(deadline["value"])
        event.update(start={"date": date.isoformat()}, end={"date": (date + dt.timedelta(days=1)).isoformat()})
    else:
        stamp = dt.datetime.fromisoformat(deadline["value"])
        event.update(start={"dateTime": stamp.isoformat()},
                     end={"dateTime": (stamp + dt.timedelta(minutes=1)).isoformat()})
    return event
