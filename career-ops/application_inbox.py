#!/usr/bin/env python3
"""Read-only Application Inbox / Status Monitor for Chief OS v1.

What this is
------------
A deterministic, read-only monitor that turns application / recruiter status
signals into three auditable things:

1. a classified signal record with provenance (which file, which line/message,
   which phrase matched);
2. a **proposed** reconciliation against the canonical Career Ops regional
   workbooks — proposed, never applied, because Excel remains authoritative for
   application state;
3. a list of owner actions, because nothing here ever replies to anyone.

What this is NOT
----------------
* No send, reply, forward, archive, delete, move, label, mark-read or
  unsubscribe. ``guard`` refuses each of them and logs the refusal. There is no
  code path that performs one.
* No write to any canonical workbook. Not behind a flag, not anywhere.
* No application record is ever created from a message. A message that does not
  match an existing canonical row is reported as *unmatched* and goes to human
  review; the store records that decision, not an invention.
* No network access on the ingest path (asserted by test). The only network
  adapter is ``gmail_readonly``, which is disabled and unconfigured on this
  machine and reports itself as UNVERIFIED.

Sources
-------
``local_mailbox`` (implemented, tested, active)
    An owner-provided local export directory. Parses ``.eml``, ``.mbox``,
    ``.json`` / ``.jsonl`` (generic message records *or* Gmail API message
    objects), ``.csv`` and ``.md`` / ``.txt``.

``gmail_readonly`` (interface implemented, credentials absent, UNVERIFIED)
    Read-only Gmail API adapter. See ``career-ops/gmail_readonly.py`` and the
    owner action recorded in
    ``tasks-or-issues/overnight-owner-actions-2026-09-24.md``.

Status model
------------
A signal maps to a status in the region's *own* vocabulary (``status_map`` in
``application_inbox_config.json``, drift-checked against
``regional_profiles.json`` validations by the test suite). Where a region has no
accurate equivalent, no status is proposed and the owner decides. A proposal for
a row whose tracker status says no application has been made yet is marked
``requires_owner_confirmation`` — the message implies an application the tracker
does not record, and this monitor does not assume it happened.

Idempotency
-----------
``signals.jsonl`` is keyed by ``signal_id`` (a hash of the message's stable
identity), ``status-events.jsonl`` by ``event_id``. Re-ingesting the same mailbox
changes neither file nor ``current-state.json``; the test suite proves it by
hash. Run metadata goes to the separate append-only ``run-log.jsonl``.

Subcommands (each prints exactly one JSON object on stdout)
    adapters
    ingest   [--inbox DIR] [--source NAME] [--runtime-dir DIR] [--record FILE]
    summary  [--runtime-dir DIR] [--record FILE]
    status   [--runtime-dir DIR]
    guard    --action NAME
    run      [--inbox DIR] [--source NAME] [--runtime-dir DIR]

Usage
    python career-ops/application_inbox.py adapters
    python career-ops/application_inbox.py run --inbox career-ops/tests/fixtures/application-inbox \\
        --runtime-dir runtime/career-ops/application-status-trial
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import email
import email.policy
import hashlib
import io
import json
import mailbox
import re
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
DEFAULT_CONFIG = CAREER_OPS_DIR / "application_inbox_config.json"

sys.path.insert(0, str(CAREER_OPS_DIR))

import cv_workflow as cvw  # noqa: E402  reuse emit/hash/read helpers
import tracker_writer as tw  # noqa: E402  canonical workbook reading only
import gmail_readonly  # noqa: E402  interface + credential probe (no ingest dependency)

emit = cvw.emit
sha256_file = cvw.sha256_file
sha256_text = cvw.sha256_text
now_utc = cvw.now_utc
read_text = cvw.read_text

URL_RE = re.compile(r"https?://[^\s<>\"')\]}]+")
QUOTE_CUTS = ("-----original message-----", "________________________________", "on ")
QUOTE_LINE_RE = re.compile(r"^\s*>")
HTML_TAG_RE = re.compile(r"<[^>]{1,200}>")
#: A candidate canonical reference. Deliberately excludes '.' and '/' so a
#: sentence-final reference ("reference: J21.") is read as "J21", and requires
#: at least 3 characters so a two-character id can never be matched by accident.
#: Consequence, documented rather than hidden: UK ids J1..J9 (2 characters) can
#: never be matched by reference; those rows must be matched by posting URL.
ID_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{2,}")
STOPWORDS = {
    "and", "the", "for", "with", "you", "your", "our", "are", "job", "role",
    "the", "of", "in", "to", "at", "a", "an", "we", "is", "be", "will", "have",
}


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #

def load_config(path: str | Path | None = None) -> dict:
    p = Path(path or DEFAULT_CONFIG)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["_config_path"] = str(p)
    return cfg


def profiles_path(cfg: dict) -> Path:
    return CONTROL_PLANE / cfg["regional_profiles"]


def load_profiles(cfg: dict) -> dict:
    return tw.load_profiles(str(profiles_path(cfg)))


def runtime_dir(cfg: dict, override: str | Path | None = None) -> Path:
    d = Path(override) if override else CONTROL_PLANE / cfg["runtime_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def inbox_dir(cfg: dict, override: str | Path | None = None) -> Path:
    return Path(override) if override else CONTROL_PLANE / cfg["inbox_dir"]


# --------------------------------------------------------------------------- #
# text preparation and classification
# --------------------------------------------------------------------------- #

def strip_quoted(text: str) -> str:
    """Remove quoted reply history so an old message is not re-classified.

    A reply that quotes an earlier acknowledgement would otherwise be read as a
    fresh acknowledgement. Only the newest content counts.
    """
    kept: list[str] = []
    for line in (text or "").splitlines():
        if QUOTE_LINE_RE.match(line):
            continue
        lowered = line.strip().casefold()
        if any(lowered.startswith(cut) for cut in QUOTE_CUTS if cut != "on ") and lowered:
            break
        if lowered.startswith("from:") and kept:
            break
        kept.append(line)
    return "\n".join(kept)


def normalize_text(text: str) -> str:
    text = (text or "").replace("\u00a0", " ").replace("\u2019", "'")
    text = HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_message(subject: str | None, body: str | None, cfg: dict) -> dict:
    """Deterministic phrase classification of one message. Unknowns stay unknown."""
    spec = cfg["classification"]
    body_text = body or ""
    stripped = strip_quoted(body_text)
    raw = f"{subject or ''}\n{stripped}"
    analysed = normalize_text(raw)
    haystack = analysed.casefold()
    quoted_removed = len(normalize_text(body_text)) > len(normalize_text(stripped))

    hits: dict[str, list[dict]] = {}
    for kind, kdef in spec["kinds"].items():
        for tier, phrase in kdef.get("patterns", []):
            if phrase.casefold() in haystack:
                hits.setdefault(kind, []).append({"tier": tier, "phrase": phrase})

    strong = [k for k, v in hits.items() if any(h["tier"] == "strong" for h in v)]
    ordered = [k for k in spec["priority"] if k in hits]
    contradictions = []
    for a, b in spec.get("contradictions", []):
        if a in strong and b in strong:
            contradictions.append([a, b])

    if contradictions:
        kind = "unknown"
        ambiguous = True
        basis = ("contradictory strong signals matched: "
                 + ", ".join(f"{a} vs {b}" for a, b in contradictions))
    elif strong:
        kind = ordered[0]
        ambiguous = False
        basis = f"priority-ordered first strong match: {kind}"
    elif ordered:
        kind = "unknown"
        ambiguous = True
        basis = ("only contextual (weak) phrases matched and none decides a status: "
                 + ", ".join(ordered))
    else:
        kind = "unknown"
        ambiguous = False
        basis = "no configured phrase matched"

    return {
        "kind": kind,
        "label": spec["kinds"].get(kind, {}).get("label", "Unclassified"),
        "ambiguous": ambiguous,
        "requires_human_review": ambiguous or kind == "unknown",
        "matched": hits,
        "strong_kinds": strong,
        "contradictions": contradictions,
        "basis": basis,
        "analysed_chars": len(analysed),
        "quoted_content_removed": quoted_removed,
    }


def extract_urls(text: str, *, limit: int) -> list[str]:
    out: list[str] = []
    for match in URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:)")
        if url and url not in out:
            out.append(url)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- #
# canonical index (read-only)
# --------------------------------------------------------------------------- #

def normalize_row(region: str, row_number: int, *, id=None, company=None, title=None,
                  location=None, url=None, application_status=None) -> dict:
    """One canonical row in the shape the matcher consumes (keys derived here only)."""
    row = {"region": region, "row": row_number, "id": id, "company": company, "title": title,
           "location": location, "url": tw.extract_url(url), "application_status": application_status}
    row["url_key"] = tw.normalize_url(row["url"])
    row["company_key"] = tw.key_text(row["company"])
    row["pair_key"] = tw.pair_key(row["company"], row["title"])
    return row


def index_rows(rows: list[dict], index: dict) -> None:
    """Add rows to the by_url / by_company / by_id lookup maps."""
    for row in rows:
        if row["url_key"]:
            index["by_url"].setdefault(row["url_key"], []).append(row)
        if row["company_key"]:
            index["by_company"].setdefault(row["company_key"], []).append(row)
        if row["id"]:
            index["by_id"].setdefault(str(row["id"]).strip().casefold(), []).append(row)


def build_canonical_index(cfg: dict, profiles: dict | None = None,
                          regions: list[str] | None = None) -> dict:
    """Read every canonical workbooks' rows. Read-only; never writes."""
    profiles = profiles or load_profiles(cfg)
    regions = regions or list(profiles["regions"])
    index: dict = {"regions": {}, "by_url": {}, "by_company": {}, "by_id": {}}
    for region in regions:
        cfg_r = dict(tw.region_config(profiles, region))
        cfg_r["region"] = region
        path = Path(cfg_r["tracker"])
        entry = {"region": region, "tracker": str(path), "available": path.exists(),
                 "sha256": None, "rows": []}
        if not path.exists():
            index["regions"][region] = entry
            continue
        entry["sha256"] = sha256_file(path)
        fm = cfg_r.get("field_map", {})
        id_col = cfg_r["id"]["column"]
        status_col = cfg_r["status_columns"]["application_status"]
        tr = tw.Tracker(path, cfg_r)
        try:
            for r in range(cfg_r["first_data_row"], tr.last_data_row() + 1):
                d = tr.row_dict(r)
                entry["rows"].append(normalize_row(
                    region, r, id=d.get(id_col), company=d.get(fm.get("company")),
                    title=d.get(fm.get("title")), location=d.get(fm.get("location")),
                    url=d.get(fm.get("url")), application_status=d.get(status_col)))
        finally:
            tr.wb.close()
        index_rows(entry["rows"], index)
        index["regions"][region] = entry
    return index


def _tokens(text: str | None) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (text or "").casefold())
            if t not in STOPWORDS}


def title_overlap(title: str | None, text: str | None) -> float:
    """How much of a canonical *title* is present in the message text.

    Coverage of the title's own significant words, not a union/Jaccard score:
    a message that mentions the title *and* a company name, a greeting and a
    signature must not be penalised for the extra words, or a company+title
    agreement would be misread as ambiguous.
    """
    tt, tx = _tokens(title), _tokens(text)
    if not tt:
        return 0.0
    return round(len(tt & tx) / len(tt), 3)


def _short(row: dict) -> dict:
    return {"region": row["region"], "row": row["row"], "id": row["id"],
            "company": row["company"], "title": row["title"],
            "application_status": row["application_status"]}


def match_signal(text: str, index: dict, cfg: dict) -> dict:
    """Conservative evidence-only matching of one message against canonical rows."""
    m = cfg["matching"]
    urls = extract_urls(text, limit=int(m["max_urls_scanned_per_message"]))
    for url in urls:
        key = tw.normalize_url(url)
        rows = index["by_url"].get(key) if key else None
        if rows:
            return {"status": "matched", "confidence": "high", "basis": "posting_url_in_message",
                    "matched_url": url, "candidates": [_short(r) for r in rows[:1]],
                    "row": _short(rows[0])}
    if urls:
        url_note = "message carries posting URL(s) that match no canonical row"
    else:
        url_note = None

    # explicit canonical id token (e.g. J21, SG-GRAD-260909-01, DUBAI-2026-09-01-03).
    # A token must contain a letter to be considered at all, so a bare number in
    # prose can never be read as a reference.
    folded = (text or "").casefold()
    id_hits: list[dict] = []
    matched_refs: list[str] = []
    for token in ID_TOKEN_RE.findall(text or ""):
        if not re.search(r"[A-Za-z]", token):
            continue
        rows = index["by_id"].get(token.strip().casefold())
        if rows:
            if token not in matched_refs:
                matched_refs.append(token)
            for r in rows:
                if r not in id_hits:
                    id_hits.append(r)
    if id_hits:
        return {"status": "matched", "confidence": "high",
                "basis": "explicit_canonical_reference_in_message",
                "matched_reference": matched_refs[0],
                "candidates": [_short(r) for r in id_hits[:int(m["max_candidates_reported"])]],
                "row": _short(id_hits[0])}

    # company (+ optional title) agreement
    min_len = int(m["min_company_key_length"])
    company_hits: list[dict] = []
    for key, rows in index["by_company"].items():
        if len(key) < min_len:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", folded):
            for r in rows:
                if r not in company_hits:
                    company_hits.append(r)
    if company_hits:
        scored = []
        for r in company_hits:
            score = title_overlap(r["title"], text)
            if score >= float(m["title_overlap_threshold"]):
                scored.append((score, r))
        if len(scored) == 1:
            score, row = scored[0]
            return {"status": "matched", "confidence": "medium",
                    "basis": "company_and_title_agreement", "title_overlap": score,
                    "candidates": [_short(row)], "row": _short(row)}
        return {"status": "ambiguous",
                "confidence": "ambiguous",
                "basis": ("company named in the message maps to more than one canonical row"
                          if len(company_hits) > 1 else
                          "company named in the message matches exactly one canonical row but "
                          "the title does not agree closely enough"),
                "candidates": [_short(r) for r in company_hits[:int(m["max_candidates_reported"])]],
                "row": None,
                "requires_human_review": True,
                "note": "no state is proposed until a human picks the row"}

    return {"status": "unmatched", "confidence": "none",
            "basis": url_note or "no canonical reference, id or company name found in the message",
            "candidates": [], "row": None, "requires_human_review": True,
            "note": "no application record exists for this message; nothing is invented"}


# --------------------------------------------------------------------------- #
# adapters: local mailbox export
# --------------------------------------------------------------------------- #

def _normalize_message(raw: dict, *, adapter: str, path: Path, file_sha: str,
                       index_no: int, line: int | None = None,
                       source_format: str | None = None) -> dict:
    def pick(*names):
        for n in names:
            v = raw.get(n)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    provenance = {"adapter": adapter, "format": source_format,
                  "file": str(path), "file_sha256": file_sha, "index": index_no}
    if line is not None:
        provenance["line"] = line
    if raw.get("_gmail_id"):
        provenance["gmail_message_id"] = raw["_gmail_id"]
    if raw.get("_gmail_thread"):
        provenance["gmail_thread_id"] = raw["_gmail_thread"]
    return {
        "message_id": pick("message_id", "id", "message-id", "Message-ID"),
        "thread_id": pick("thread_id", "threadId", "thread-id", "Thread-Id"),
        "received_at": pick("received_at", "received", "date", "Date", "internal_date"),
        "sender": pick("from", "sender", "From"),
        "recipients": pick("to", "recipient", "To"),
        "subject": pick("subject", "Subject"),
        "body": raw.get("body") or raw.get("text") or raw.get("snippet") or "",
        "source": pick("source") or adapter,
        "provenance": provenance,
    }


def _gmail_header(payload: dict, name: str) -> str | None:
    for header in (payload or {}).get("headers") or []:
        if str(header.get("name", "")).casefold() == name.casefold():
            return header.get("value")
    return None


def _gmail_body(payload: dict) -> str:
    """Extract text/plain (preferred) or de-tagged text/html from a Gmail payload."""
    plain: list[str] = []
    html: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType") or ""
        data = (part.get("body") or {}).get("data")
        if data:
            try:
                decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                    "utf-8", errors="replace")
            except (ValueError, TypeError):
                decoded = ""
            if mime.startswith("text/plain"):
                plain.append(decoded)
            elif mime.startswith("text/html"):
                html.append(HTML_TAG_RE.sub(" ", decoded))
        for sub in part.get("parts") or []:
            walk(sub)

    walk(payload or {})
    return "\n".join(plain) if plain else "\n".join(html)


def parse_gmail_api_message(msg: dict) -> dict:
    """Convert one Gmail API message object into a raw message record.

    Used both for exported Gmail API JSON and for the (never-yet-executed) live
    fetch, so the conversion itself is covered by fixtures.
    """
    payload = msg.get("payload") or {}
    internal = msg.get("internalDate")
    received = None
    if internal:
        try:
            received = dt.datetime.fromtimestamp(int(internal) / 1000, dt.timezone.utc)\
                .replace(microsecond=0).isoformat()
        except (ValueError, TypeError, OSError):
            received = None
    return {
        "message_id": _gmail_header(payload, "Message-ID") or msg.get("id"),
        "thread_id": msg.get("threadId"),
        "received_at": received or _gmail_header(payload, "Date"),
        "from": _gmail_header(payload, "From"),
        "to": _gmail_header(payload, "To"),
        "subject": _gmail_header(payload, "Subject"),
        "body": _gmail_body(payload) or msg.get("snippet") or "",
        "_gmail_id": msg.get("id"),
        "_gmail_thread": msg.get("threadId"),
    }


def _eml_to_raw(message) -> dict:
    body = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                body += part.get_content()
    else:
        body = message.get_content()
    return {
        "message_id": message.get("Message-ID"),
        "thread_id": None,
        "received_at": message.get("Date"),
        "from": message.get("From"),
        "to": message.get("To"),
        "subject": message.get("Subject"),
        "body": body,
    }


def parse_json_messages(text: str) -> list[dict]:
    doc = json.loads(text)
    if isinstance(doc, dict):
        for key in ("messages", "items", "signals", "emails"):
            if isinstance(doc.get(key), list):
                return [d for d in doc[key] if isinstance(d, dict)]
        if "payload" in doc or "id" in doc:
            return [doc]
        return []
    if isinstance(doc, list):
        return [d for d in doc if isinstance(d, dict)]
    raise ValueError("JSON message file must be an array or an object with a messages array")


def parse_file(path: Path, cfg: dict) -> dict:
    """Parse one local mailbox file. Never fetches, never opens a URL."""
    ext = path.suffix.lower()
    supported = [e.lower() for e in cfg["supported_extensions"]]
    if ext not in supported:
        return {"path": str(path), "sha256": None, "messages": [], "skipped":
                f"unsupported extension {ext or '(none)'}"}
    file_sha = sha256_file(path)
    raw_items: list[dict] = []
    if ext in (".json", ".jsonl"):
        if ext == ".json":
            raw_items = parse_json_messages(read_text(path))
        else:
            for i, line in enumerate(read_text(path).splitlines(), start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                item = json.loads(line)
                item["_line"] = i
                raw_items.append(item)
        raw_items = [parse_gmail_api_message(m) if "payload" in m else m for m in raw_items]
    elif ext == ".csv":
        raw_items = [dict(r) for r in csv.DictReader(io.StringIO(read_text(path)))]
    elif ext == ".eml":
        raw_items = [_eml_to_raw(email.message_from_string(read_text(path), policy=email.policy.default))]
    elif ext == ".mbox":
        raw_items = [_eml_to_raw(m) for m in mailbox.mbox(path)]
    else:
        return {"path": str(path), "sha256": file_sha, "messages": [], "skipped":
                f"{ext} has no message envelope; use .eml/.mbox/.json/.jsonl/.csv so no field "
                "is guessed"}

    messages = []
    for i, item in enumerate(raw_items):
        messages.append(_normalize_message(item, adapter="local_mailbox", path=path,
                                           file_sha=file_sha, index_no=i,
                                           line=item.get("_line"), source_format=ext))
    return {"path": str(path), "sha256": file_sha, "messages": messages, "skipped": None}


def collect_local_mailbox(cfg: dict, inbox: Path) -> dict:
    if not inbox.exists():
        return {"ok": False, "reason": f"inbox not found: {inbox}", "files": [], "messages": [],
                "counts": {}}
    files = sorted(p for p in inbox.rglob("*") if p.is_file())
    parsed = [parse_file(p, cfg) for p in files]
    messages = [m for doc in parsed for m in doc["messages"]]
    return {
        "ok": True,
        "adapter": "local_mailbox",
        "evidence_mode": "fixture",
        "inbox": str(inbox),
        "files": [{"path": d["path"], "sha256": d["sha256"], "messages": len(d["messages"]),
                   "skipped": d["skipped"]} for d in parsed],
        "counts": {"files": len(files), "messages": len(messages),
                   "skipped_files": sum(1 for d in parsed if d["skipped"])},
        "messages": messages,
        "read_only_contract": {
            "network_used": False,
            "urls_fetched": 0,
            "browser_launched": False,
            "mailbox_authenticated": False,
            "mailbox_mutations": 0,
            "messages_sent": 0,
            "note": "Messages are parsed from owner-provided local files. Every URL is an "
                    "opaque string; nothing is requested or opened.",
        },
    }


def collect_gmail(cfg: dict, *, limit: int | None = None) -> dict:
    """Delegate to the read-only Gmail adapter, which refuses when unconfigured."""
    acfg = cfg["adapters"]["gmail_readonly"]
    result = gmail_readonly.fetch(acfg, limit=limit)
    if not result.get("ok"):
        return {"ok": False, "adapter": "gmail_readonly", "reason": result["reason"],
                "files": [], "messages": [], "counts": {}, "adapter_status": result,
                "read_only_contract": {"network_used": False, "mailbox_mutations": 0,
                                       "messages_sent": 0}}
    messages = []
    for i, msg in enumerate(result["messages"]):
        messages.append(_normalize_message(parse_gmail_api_message(msg),
                                           adapter="gmail_readonly",
                                           path=Path("<gmail-api>"), file_sha="",
                                           index_no=i, source_format="gmail_api_live"))
    return {"ok": True, "adapter": "gmail_readonly", "evidence_mode": "live",
            "inbox": "<gmail-api>", "files": [], "counts": {"files": 0, "messages": len(messages)},
            "messages": messages,
            "read_only_contract": {"network_used": True, "mailbox_mutations": 0,
                                   "messages_sent": 0, "scope": result.get("scope")}}


# --------------------------------------------------------------------------- #
# status store (idempotent, local, proposal-only)
# --------------------------------------------------------------------------- #

STORE_FILES = ("signals.jsonl", "status-events.jsonl", "current-state.json", "run-log.jsonl")


def store_paths(root: Path) -> dict:
    return {name.split(".")[0].replace("-", "_"): root / name for name in STORE_FILES}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _append_jsonl(path: Path, records: list[dict]) -> None:
    if not records:
        return
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def signal_id(message: dict, classification: dict) -> str:
    prov = message.get("provenance") or {}
    identity = "|".join(str(x or "") for x in (
        prov.get("gmail_message_id") or message.get("message_id"),
        message.get("thread_id"),
        message.get("received_at"),
        message.get("sender"),
        message.get("subject"),
        sha256_text(str(message.get("body") or ""))[:32],
    ))
    return "sig-" + sha256_text(identity)[:24]


def event_id(region: str, row_id: str, kind: str) -> str:
    return "evt-" + sha256_text(f"{region}|{row_id}|{kind}")[:24]


def proposal_for(kind: str, region: str, current_status: str | None, cfg: dict) -> dict:
    """Map a signal kind to a proposed status in the region's own vocabulary."""
    mapping = (cfg["status_map"].get(region) or {}).get(kind)
    pre_states = [s.casefold() for s in cfg["pre_application_states"].get(region, [])]
    current = (str(current_status).strip() if current_status not in (None, "") else None)
    implies = bool(cfg["classification"]["kinds"].get(kind, {}).get("implies_application"))
    unrecorded = implies and (current is None or current.casefold() in pre_states)
    if mapping is None:
        return {
            "proposed_status": None,
            "proposal_state": "owner_decision_required",
            "reason": (f"the {region} tracker vocabulary has no status that matches a "
                       f"'{kind}' signal; no status is proposed"),
            "requires_owner_confirmation": False,
            "implied_application_not_yet_recorded": unrecorded,
        }
    if mapping == current:
        return {
            "proposed_status": None,
            "proposal_state": "already_reflected",
            "reason": f"tracker already records '{current}'; nothing to change",
            "requires_owner_confirmation": False,
            "implied_application_not_yet_recorded": unrecorded,
        }
    reason = f"'{kind}' maps to the {region} status '{mapping}'"
    if unrecorded:
        reason += (" — but the tracker shows '" + str(current or "no status") +
                   "', so this message implies an application the tracker does not record. "
                   "The owner must confirm before the state is set.")
    return {
        "proposed_status": mapping,
        "proposal_state": "pending_owner_confirmation",
        "reason": reason,
        "requires_owner_confirmation": unrecorded,
        "implied_application_not_yet_recorded": unrecorded,
    }


def owner_action(kind: str, *, row: dict | None, match: dict, cfg: dict) -> dict:
    """The owner-facing action for one classified signal. Never performed here."""
    template = cfg["owner_action_kinds"].get(kind) or cfg["owner_action_kinds"]["unknown"]
    needs_action = kind in ("interview_invite", "assessment_invite", "offer",
                            "follow_up_request", "recruiter_outreach", "unknown")
    if kind == "rejection":
        needs_action = False
    if kind == "application_acknowledgement":
        needs_action = True  # confirm the tracker state; never a reply
    if match.get("status") == "ambiguous":
        needs_action = True
    where = None
    if row:
        where = (f"{row.get('region')} tracker row {row.get('row')} ({row.get('id')}) — "
                 f"{row.get('company')}")
    return {
        "kind": kind,
        "owner_action_required": bool(needs_action),
        "action": template,
        "where": where,
        "reply_sent": False,
        "never_performed_by_this_monitor": True,
    }


def ingest(cfg: dict, collected: dict, root: Path) -> dict:
    """Classify, match and store. Idempotent; writes only to the local store."""
    paths = store_paths(root)
    existing_signals = {r["signal_id"]: r for r in _read_jsonl(paths["signals"])}
    existing_events = {r["event_id"]: r for r in _read_jsonl(paths["status_events"])}
    index = build_canonical_index(cfg)

    new_signals, new_events = [], []
    counts = {"messages": 0, "already_ingested": 0, "new_signals": 0, "unknown": 0,
              "ambiguous_classification": 0, "matched_high": 0, "matched_medium": 0,
              "ambiguous_match": 0, "unmatched": 0, "status_events": 0,
              "no_status_events": 0, "already_recorded_events": 0, "owner_actions": 0,
              "review_items": 0}

    for message in collected.get("messages", []):
        counts["messages"] += 1
        cls = classify_message(message.get("subject"), message.get("body"), cfg)
        analysed = normalize_text(f"{message.get('subject') or ''}\n{strip_quoted(message.get('body') or '')}")
        match = match_signal(analysed, index, cfg)
        sid = signal_id(message, cls)
        record = {
            "signal_id": sid,
            "received_at": message.get("received_at"),
            "sender": message.get("sender"),
            "subject": message.get("subject"),
            "classification": {k: v for k, v in cls.items() if k != "matched"},
            "matched_phrases": cls["matched"],
            "match": match,
            "provenance": message.get("provenance"),
            "source": message.get("source"),
        }
        if cls["kind"] == "unknown":
            counts["unknown"] += 1
        if cls["ambiguous"]:
            counts["ambiguous_classification"] += 1
        if match["status"] == "matched":
            counts["matched_high" if match["confidence"] == "high" else "matched_medium"] += 1
        elif match["status"] == "ambiguous":
            counts["ambiguous_match"] += 1
        else:
            counts["unmatched"] += 1

        if sid in existing_signals:
            counts["already_ingested"] += 1
            continue
        new_signals.append(record)
        counts["new_signals"] += 1

        row = match.get("row")
        if row:
            prop = proposal_for(cls["kind"], row["region"], row["application_status"], cfg)
            eid = event_id(row["region"], str(row["id"]), cls["kind"])
            record["proposal"] = prop
            record["region"] = row["region"]
            record["row_id"] = row["id"]
            if eid in existing_events:
                counts["already_recorded_events"] += 1
            else:
                # A reconciliation event is recorded for EVERY matched signal, even
                # when no status can be proposed, so "we looked and deliberately
                # proposed nothing" is auditable rather than silently dropped.
                new_events.append({
                    "event_id": eid,
                    "signal_id": sid,
                    "event_kind": ("status_proposal" if prop["proposed_status"] else
                                   prop["proposal_state"]),
                    "region": row["region"],
                    "tracker": index["regions"][row["region"]]["tracker"],
                    "row": row["row"],
                    "row_id": row["id"],
                    "company": row["company"],
                    "title": row["title"],
                    "signal_kind": cls["kind"],
                    "status_in_workbook_at_reconcile": row["application_status"],
                    "proposed_status": prop["proposed_status"],
                    "proposal_reason": prop["reason"],
                    "requires_owner_confirmation": prop["requires_owner_confirmation"],
                    "implied_application_not_yet_recorded":
                        prop["implied_application_not_yet_recorded"],
                    "evidence": {"sender": message.get("sender"),
                                 "received_at": message.get("received_at"),
                                 "subject": message.get("subject"),
                                 "matched_phrases": cls["matched"],
                                 "match_basis": match["basis"]},
                    "state_written": False,
                    "authoritative_system": "excel",
                })
                counts["status_events" if prop["proposed_status"] else "no_status_events"] += 1

    _append_jsonl(paths["signals"], new_signals)

    # one authoritative pass: rebuild the projection from the store, so an
    # unrecorded or half-written state is never left behind
    all_signals = _read_jsonl(paths["signals"])
    events = _merge_events(_read_jsonl(paths["status_events"]), new_events)
    _write_events(paths["status_events"], events)

    review, actions, state = _project(cfg, index, all_signals, events)
    counts["review_items"] = len(review)
    counts["owner_actions"] = sum(1 for a in actions if a["owner_action_required"])
    state_doc = {
        "schema_version": 1,
        "note": ("Proposals only. Excel remains authoritative for application state; this "
                 "store never writes to a workbook and never sends mail."),
        "canonical_workbooks": {
            region: {"tracker": e["tracker"], "sha256": e["sha256"], "rows": len(e["rows"])}
            for region, e in index["regions"].items()},
        "regions": state,
        "review_queue": review,
        "owner_actions": actions,
    }
    paths["current_state"].write_text(json.dumps(state_doc, indent=2, ensure_ascii=False,
                                                 default=str), encoding="utf-8")
    run = {"at": now_utc(), "adapter": collected.get("adapter"),
           "evidence_mode": collected.get("evidence_mode"), "counts": counts}
    _append_jsonl(paths["run_log"], [run])
    return {"counts": counts, "state": state_doc, "store": {k: str(v) for k, v in paths.items()}}


def _merge_events(existing: list[dict], new: list[dict]) -> list[dict]:
    by_id = {e["event_id"]: e for e in existing}
    for e in new:
        by_id.setdefault(e["event_id"], e)
    return sorted(by_id.values(), key=lambda e: (e["region"], str(e["row_id"]), e["signal_kind"]))


def _write_events(path: Path, events: list[dict]) -> None:
    """Rewrite the event log deterministically (append-only in effect: keys never change)."""
    path.write_text("".join(json.dumps(e, ensure_ascii=False, default=str) + "\n"
                            for e in events), encoding="utf-8")


def _project(cfg: dict, index: dict, signals: list[dict], events: list[dict]) -> tuple:
    """Rebuild review queue, owner actions and per-row state from the store."""
    by_signal = {s["signal_id"]: s for s in signals}
    regions: dict[str, dict] = {}
    review: list[dict] = []
    actions: list[dict] = []

    for e in events:
        sig = by_signal.get(e["signal_id"]) or {}
        bucket = regions.setdefault(e["region"], {})
        entry = bucket.setdefault(str(e["row_id"]), {
            "row": e["row"], "row_id": e["row_id"], "company": e["company"], "title": e["title"],
            "status_in_workbook_at_reconcile": e["status_in_workbook_at_reconcile"],
            "proposed_status": None, "proposal_state": None, "proposal_reasons": [],
            "signal_kinds": [], "signal_ids": [], "requires_owner_confirmation": False,
            "implied_application_not_yet_recorded": False, "last_signal_at": None,
            "state_written": False, "authoritative_system": "excel",
        })
        if e["signal_kind"] not in entry["signal_kinds"]:
            entry["signal_kinds"].append(e["signal_kind"])
        if e["signal_id"] not in entry["signal_ids"]:
            entry["signal_ids"].append(e["signal_id"])
        entry["requires_owner_confirmation"] = (entry["requires_owner_confirmation"]
                                                or bool(e.get("requires_owner_confirmation")))
        entry["implied_application_not_yet_recorded"] = (
            entry["implied_application_not_yet_recorded"]
            or bool(e.get("implied_application_not_yet_recorded")))
        if e.get("proposal_reason"):
            entry["proposal_reasons"].append(e["proposal_reason"])
        if e["proposed_status"]:
            entry["proposed_status"] = e["proposed_status"]
            entry["proposal_state"] = ("pending_owner_confirmation"
                                       if entry["requires_owner_confirmation"]
                                       else "proposed")
        elif entry["proposal_state"] is None:
            entry["proposal_state"] = e.get("event_kind") or "owner_decision_required"
        when = sig.get("received_at")
        if when and (entry["last_signal_at"] is None or str(when) > str(entry["last_signal_at"])):
            entry["last_signal_at"] = when

    # owner actions are derived from EVERY signal, matched or not: a matched row
    # can still need an owner reply (follow-up request, interview invite), and any
    # signal the monitor cannot place needs a human.
    for s in signals:
        cls = s.get("classification") or {}
        match = s.get("match") or {}
        kind = cls.get("kind") or "unknown"
        row = match.get("row")
        actions.append({
            "signal_id": s["signal_id"],
            "region": (row or {}).get("region"),
            "row_id": (row or {}).get("id"),
            "company": (row or {}).get("company"),
            "match_status": match.get("status"),
            **owner_action(kind, row=row, match=match, cfg=cfg),
        })
        if match.get("status") == "matched" and not cls.get("requires_human_review"):
            continue
        review.append({
            "signal_id": s["signal_id"],
            "received_at": s.get("received_at"),
            "sender": s.get("sender"),
            "classification_kind": kind,
            "classification_basis": cls.get("basis"),
            "match_status": match.get("status"),
            "match_basis": match.get("basis"),
            "candidates": match.get("candidates", []),
            "reason": ("no canonical record matched — nothing invented; a human decides"
                       if match.get("status") == "unmatched" else
                       "more than one possible canonical record — a human must pick"
                       if match.get("status") == "ambiguous" else
                       "row matched, but the message could not be classified with confidence"),
            "owner_action_required": True,
            "state_written": False,
        })
    return review, actions, regions


def build_summary(cfg: dict, root: Path, index: dict | None = None) -> dict:
    paths = store_paths(root)
    signals = _read_jsonl(paths["signals"])
    events = _read_jsonl(paths["status_events"])
    state_path = paths["current_state"]
    state = json.loads(read_text(state_path)) if state_path.exists() else {
        "regions": {}, "review_queue": [], "owner_actions": []}
    index = index or build_canonical_index(cfg)

    changed, pending = [], []
    for region, rows in (state.get("regions") or {}).items():
        for row_id, entry in rows.items():
            if entry.get("proposed_status"):
                (pending if entry.get("requires_owner_confirmation") else changed).append({
                    "region": region, "row_id": row_id, "company": entry.get("company"),
                    "title": entry.get("title"),
                    "workbook_status": entry.get("status_in_workbook_at_reconcile"),
                    "proposed_status": entry.get("proposed_status"),
                    "signal_kinds": entry.get("signal_kinds"),
                    "requires_owner_confirmation": entry.get("requires_owner_confirmation"),
                    "state_written": False,
                })
    kinds: dict[str, int] = {}
    for s in signals:
        k = ((s.get("classification") or {}).get("kind")) or "unknown"
        kinds[k] = kinds.get(k, 0) + 1
    match_counts: dict[str, int] = {}
    for s in signals:
        m = ((s.get("match") or {}).get("status")) or "unknown"
        match_counts[m] = match_counts.get(m, 0) + 1
    all_actions = state.get("owner_actions", [])
    actions = [a for a in all_actions if a.get("owner_action_required")]
    no_action = [a for a in all_actions if not a.get("owner_action_required")]
    return {
        "generated_at": now_utc(),
        "store": str(root),
        "counts": {
            "signals_ingested": len(signals),
            "status_events": len(events),
            "status_changes_ready_for_owner": len(pending),
            "status_changes_not_requiring_confirmation": len(changed),
            "owner_actions_required": len(actions),
            "signals_recorded_with_no_action_needed": len(no_action),
            "review_items": len(state.get("review_queue", [])),
        },
        "signals_by_kind": kinds,
        "signals_by_match": match_counts,
        "proposed_status_changes": pending + changed,
        "owner_actions": actions,
        # reported so the owner can see a message was reconciled and needs no reply
        "no_action_required": no_action,
        "review_queue": state.get("review_queue", []),
        "canonical_workbooks": state.get("canonical_workbooks", {}),
        "safety": {
            "emails_sent": 0, "replies_sent": 0, "mailbox_mutations": 0,
            "workbooks_written": 0, "applications_created": 0,
            "state_written_to_canonical_workbook": False,
            "proposals_only": True, "excel_authoritative": True,
        },
    }


# --------------------------------------------------------------------------- #
# action guard (owner gate)
# --------------------------------------------------------------------------- #

def guard_action(cfg: dict, action: str, root: Path) -> dict:
    key = (action or "").strip().casefold()
    blocked = {a.casefold() for a in cfg["blocked_actions"]}
    allowed = key not in blocked
    result = {
        "action": action,
        "allowed": allowed,
        "owner_gated": not allowed,
        "performed": False,
        "reason": ("mailbox mutation / outbound message is owner-gated; this monitor "
                   "implements no path that performs it" if not allowed else
                   "action is not a mailbox mutation or an outbound message (read/propose only)"),
        "policy": cfg["external_action_policy"],
        "available_paths": ["adapters (read-only)", "ingest (read-only)", "summary", "status",
                            "run (read-only)"],
    }
    log = root / "action-gate-log.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_utc(), **result}) + "\n")
    result["logged_to"] = str(log)
    return result


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def _collect(cfg: dict, args) -> dict:
    source = getattr(args, "source", None) or "local_mailbox"
    if source == "gmail_readonly":
        return collect_gmail(cfg, limit=getattr(args, "limit", None))
    if source != "local_mailbox":
        return {"ok": False, "reason": f"unknown adapter '{source}'", "messages": []}
    return collect_local_mailbox(cfg, inbox_dir(cfg, getattr(args, "inbox", None)))


def cmd_adapters(args) -> int:
    cfg = load_config(args.config)
    out = {"generated_at": now_utc(), "adapters": {}}
    for name, acfg in cfg["adapters"].items():
        if acfg.get("kind") == "local_file":
            d = inbox_dir(cfg, None)
            out["adapters"][name] = {
                "adapter": name, "kind": acfg["kind"], "enabled": bool(acfg.get("enabled")),
                "available": bool(acfg.get("enabled")),
                "evidence_mode": acfg.get("evidence_mode"),
                "inbox": str(d), "inbox_exists": d.exists(),
                "supported_extensions": cfg["supported_extensions"],
                "read_only": True, "owner_action_required": False,
                "note": "Implemented and tested; owner provides the export directory.",
            }
        else:
            out["adapters"][name] = {**gmail_readonly.adapter_status(acfg), "adapter": name}
    out["active_adapter"] = next((n for n, a in out["adapters"].items() if a.get("available")),
                                None)
    out["not_performed"] = cfg["not_performed"]
    emit(out)
    return 0


def cmd_ingest(args) -> int:
    cfg = load_config(args.config)
    collected = _collect(cfg, args)
    if not collected.get("ok"):
        emit({"ok": False, **collected, "emails_sent": 0, "workbooks_written": 0})
        return 1
    root = runtime_dir(cfg, getattr(args, "runtime_dir", None))
    result = ingest(cfg, collected, root)
    out = {
        "ok": True, "generated_at": now_utc(), "adapter": collected["adapter"],
        "evidence_mode": collected.get("evidence_mode"),
        "inbox": collected.get("inbox"),
        "file_counts": collected.get("counts"),
        "read_only_contract": collected.get("read_only_contract"),
        "counts": result["counts"], "store": result["store"],
        "safety": {"emails_sent": 0, "replies_sent": 0, "mailbox_mutations": 0,
                   "workbooks_written": 0, "applications_created": 0,
                   "proposals_only": True, "excel_authoritative": True},
    }
    if args.record:
        p = Path(args.record)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        out["recorded_to"] = str(p)
    emit(out)
    return 0


def cmd_summary(args) -> int:
    cfg = load_config(args.config)
    root = runtime_dir(cfg, getattr(args, "runtime_dir", None))
    doc = build_summary(cfg, root)
    if args.record:
        p = Path(args.record)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        doc["recorded_to"] = str(p)
    emit(doc)
    return 0


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    root = runtime_dir(cfg, getattr(args, "runtime_dir", None))
    paths = store_paths(root)
    log = root / "action-gate-log.jsonl"
    refusals = 0
    for line in _read_jsonl(log):
        if line.get("owner_gated"):
            refusals += 1
    runs = _read_jsonl(paths["run_log"])
    emit({
        "ok": True, "generated_at": now_utc(), "config": cfg["_config_path"],
        "store": str(root),
        "store_files": {k: {"path": str(v), "exists": v.exists(),
                            "bytes": v.stat().st_size if v.exists() else 0}
                        for k, v in paths.items()},
        "signals": len(_read_jsonl(paths["signals"])),
        "status_events": len(_read_jsonl(paths["status_events"])),
        "runs": len(runs), "last_run": runs[-1] if runs else None,
        "action_gate_refusals_logged": refusals,
        "blocked_actions": cfg["blocked_actions"],
        "external_action_policy": cfg["external_action_policy"],
        "not_performed": cfg["not_performed"],
    })
    return 0


def cmd_guard(args) -> int:
    cfg = load_config(args.config)
    root = runtime_dir(cfg, getattr(args, "runtime_dir", None))
    emit({"ok": True, **guard_action(cfg, args.action, root)})
    return 0


def cmd_run(args) -> int:
    """Ingest then summarise in one document (still read-only)."""
    cfg = load_config(args.config)
    collected = _collect(cfg, args)
    if not collected.get("ok"):
        emit({"ok": False, **collected, "emails_sent": 0, "workbooks_written": 0})
        return 1
    root = runtime_dir(cfg, getattr(args, "runtime_dir", None))
    result = ingest(cfg, collected, root)
    summary = build_summary(cfg, root)
    out = {"ok": True, "generated_at": now_utc(), "adapter": collected["adapter"],
           "evidence_mode": collected.get("evidence_mode"), "inbox": collected.get("inbox"),
           "file_counts": collected.get("counts"), "counts": result["counts"],
           "read_only_contract": collected.get("read_only_contract"),
           "summary": summary, "store": result["store"]}
    emit(out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only Application Inbox / Status Monitor")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("adapters"); p.set_defaults(fn=cmd_adapters)

    for name, fn, needs_source in (("ingest", cmd_ingest, True), ("run", cmd_run, True)):
        p = sub.add_parser(name)
        if needs_source:
            p.add_argument("--source", default="local_mailbox",
                           choices=["local_mailbox", "gmail_readonly"])
            p.add_argument("--inbox")
            p.add_argument("--limit", type=int)
            p.add_argument("--runtime-dir")
        if name == "ingest":
            p.add_argument("--record")
        p.set_defaults(fn=fn)

    p = sub.add_parser("summary")
    p.add_argument("--runtime-dir"); p.add_argument("--record")
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("status")
    p.add_argument("--runtime-dir")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("guard")
    p.add_argument("--action", required=True); p.add_argument("--runtime-dir")
    p.set_defaults(fn=cmd_guard)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
