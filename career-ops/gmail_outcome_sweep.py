#!/usr/bin/env python3
"""Scan Gmail for application outcomes (rejections). Read-only.

Two phases, deliberately separated:

1. FETCH  - list every message in the window, then download the full body of
   every message that belongs to an application thread, caching the text to
   disk. Retries with backoff, because a silent fetch failure in this phase
   looks exactly like "no rejection arrived".
2. CLASSIFY - read the cached text and apply the outcome patterns. Costs no
   network calls, so patterns can be tightened and re-run instantly.

Two earlier single-phase versions failed in instructive ways:

* Classifying on the list snippet found 1 rejection in 1,536 messages, because
  rejection language sits deep in the body and the snippet never contained it.
* Classifying on the fetched body, but excluding anything that mentions an
  interview or an assessment, silently dropped a real rejection whose mail said
  "we have decided not to move forward with your application" further down.

Caching the TEXT rather than the verdict is the same lesson the experience
sweep learned: the fetch is expensive, the judgement is not.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import career_google_auth as auth  # noqa: E402

API = "https://gmail.googleapis.com/gmail/v1/users/me"


def acquire_run_lock(path: pathlib.Path):
    """Take an exclusive lock for the run, or return None if another run holds it.

    Two sweeps used to write the same report file, so the later one silently
    replaced a good report with a partial one - which made the rejection counts
    non-repeatable and could destroy the audit trail a reconciliation was built
    from. The second run now exits cleanly and leaves the existing report alone.
    """
    f = open(path, "a+b")
    try:
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def write_atomic(path: pathlib.Path, text: str) -> None:
    """Write via a temp file + replace so a crash never leaves a truncated report."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

#: Unambiguous rejection language. Decisive on its own, whatever else the mail
#: says.
STRONG_REJECT_RE = re.compile(
    r"not to move forward|not be progressing|not progressing"
    r"|decided not to (?:progress|proceed|move|take)"
    r"|no longer under consideration|not been shortlisted|not shortlisted"
    r"|unable to offer|not able to offer|application has been rejected"
    r"|will not be (?:progressing|taking|moving)|not been successful"
    r"|was not successful|were not successful|unsuccessful on this occasion"
    r"|regret to inform|we regret|unfortunately"
    r"|not been selected|not selected for|other candidates whose"
    r"|more closely match|stronger candidates"
    r"|your application (?:has|was) (?:not|un)"
    r"|position has (?:now )?been filled|role has been filled",
    re.IGNORECASE,
)

#: Softer signals. A rejection only when no positive signal is present.
WEAK_REJECT_RE = re.compile(
    r"keep your (?:details|application) on file|wish you (?:all the )?best"
    r"|thank you for your interest|we appreciate your interest"
    r"|not taking your application further|unsuccessful",
    re.IGNORECASE,
)

#: A positive outcome. Suppresses a WEAK match, never a STRONG one.
POSITIVE_RE = re.compile(
    r"we'?d like to (?:invite|meet)|pleased to (?:inform|invite|offer)"
    r"|congratulations|offer of employment|job offer|invite you to"
    r"|schedule (?:a|your) (?:call|interview)|next stage|assessment centre"
    r"|invitation to interview|shortlisted for|we are delighted",
    re.IGNORECASE,
)

APPLICATION_RE = re.compile(
    r"application|applied|your interest|candidac|candidate|recruit|position"
    r"|vacancy|thank you for|assessment|interview|talent|hiring|role",
    re.IGNORECASE,
)

ATS_SENDER_RE = re.compile(
    r"myworkday|workday|greenhouse|ashby|smartrecruiters|tal\.net|teamtailor"
    r"|successfactors|icims|taleo|breezy|lever|jobtrain|trakstar|oraclecloud"
    r"|hirevue|canditech|\bshl\b|talogy|\.jobs|jobs\.|careers|recruit|talent"
    r"|noreply|no-reply|donotreply|workflow\.mail",
    re.IGNORECASE,
)

NOISE_SUBJECT_RE = re.compile(
    r"newsletter|digest|job alert|new jobs|recommended jobs|weekly|daily"
    r"|unsubscribe|verify your email|security alert|sign-?in|your order"
    r"|receipt for|invoice|password",
    re.IGNORECASE,
)

REJECT_ANY = re.compile(
    f"(?:{STRONG_REJECT_RE.pattern})|(?:{WEAK_REJECT_RE.pattern})", re.IGNORECASE
)


def _get_retry(url, token, attempts=4):
    """GET with backoff. A silent failure here fabricates 'no outcome'."""
    last = None
    for i in range(attempts):
        try:
            return auth.http_json("GET", url, token=token)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch failed after {attempts} attempts: {last}")


def _headers(payload_headers):
    out = {}
    for h in payload_headers or []:
        n = (h.get("name") or "").lower()
        if n in ("subject", "from", "date"):
            out[n] = h.get("value") or ""
    return out


def _body_text(msg):
    """Concatenate the text parts of a message."""
    import base64

    chunks = []

    def walk(part):
        if not isinstance(part, dict):
            return
        mt = part.get("mimeType") or ""
        data = (part.get("body") or {}).get("data")
        if data and mt in ("text/plain", "text/html", ""):
            try:
                chunks.append(base64.urlsafe_b64decode(data + "===")
                              .decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
        for sub in part.get("parts") or []:
            walk(sub)

    walk(msg.get("payload") or {})
    return "\n".join(chunks)


def strip_html(text):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    return " ".join(text.split())


def _candidate(subject, snippet, sender):
    blob = f"{subject} {snippet}"
    if REJECT_ANY.search(blob) or APPLICATION_RE.search(blob):
        return True
    return bool(ATS_SENDER_RE.search(sender or ""))


# --------------------------------------------------------------------------- #
# Phase 1: fetch and cache bodies
# --------------------------------------------------------------------------- #
def fetch_bodies(days, cache_path, token):
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache = {}

    ids, page = [], None
    while True:
        url = f"{API}/messages?q=newer_than:{days}d&maxResults=500"
        if page:
            url += f"&pageToken={page}"
        resp = _get_retry(url, token)
        ids.extend(m.get("id") for m in (resp.get("messages") or []))
        page = resp.get("nextPageToken")
        if not page or len(ids) > 8000:
            break
    print(f"messages in window: {len(ids)}", flush=True)

    todo = [i for i in ids if i not in cache]
    print(f"already cached: {len(ids) - len(todo)} | to fetch: {len(todo)}", flush=True)

    def one(mid):
        try:
            m = _get_retry(f"{API}/messages/{mid}?format=full", token)
            h = _headers((m.get("payload") or {}).get("headers"))
            return mid, {"subject": h.get("subject", ""), "from": h.get("from", ""),
                         "date": h.get("date", ""), "snippet": m.get("snippet", ""),
                         "text": strip_html(_body_text(m))}
        except Exception as exc:  # noqa: BLE001
            return mid, {"error": str(exc)}

    done = 0
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        for mid, rec in pool.map(one, todo):
            cache[mid] = rec
            done += 1
            if done % 100 == 0:
                print(f"  fetched {done}/{len(todo)}", flush=True)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                write_atomic(cache_path, json.dumps(cache, ensure_ascii=False))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(cache_path, json.dumps(cache, ensure_ascii=False))
    errors = sum(1 for r in cache.values() if r.get("error"))
    print(f"cached {len(cache)} messages ({errors} fetch errors)", flush=True)
    return cache


# --------------------------------------------------------------------------- #
# Phase 2: classify from cache
# --------------------------------------------------------------------------- #
def classify(cache):
    rejections, near = [], []
    for mid, rec in cache.items():
        if rec.get("error"):
            continue
        subj = rec.get("subject", "")
        sender = rec.get("from", "")
        snippet = rec.get("snippet", "")
        if NOISE_SUBJECT_RE.search(subj):
            continue
        if not _candidate(subj, snippet, sender):
            continue
        hay = f"{subj} {rec.get('text', '')}"
        entry = {"id": mid, "subject": subj, "from": sender,
                 "date": rec.get("date", ""), "snippet": snippet[:300]}
        m = STRONG_REJECT_RE.search(hay)
        if m:
            entry["confidence"] = "strong"
        else:
            m = WEAK_REJECT_RE.search(hay)
            if not m or POSITIVE_RE.search(hay):
                entry["excerpt"] = rec.get("text", "")[:300]
                near.append(entry)
                continue
            entry["confidence"] = "weak"
        entry["evidence"] = hay[max(0, m.start() - 170):m.end() + 210]
        rejections.append(entry)
    return rejections, near


def main() -> int:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    runtime = HERE.parent / "runtime" / "career-ops"
    cache_path = runtime / f"gmail-bodies-{days}d.json"
    out_path = runtime / f"gmail-outcomes-{days}d.json"

    lock = acquire_run_lock(runtime / f".gmail-outcome-sweep-{days}d.lock")
    if lock is None:
        print(f"another sweep for {days}d is already running; leaving "
              f"{out_path.name} untouched")
        return 0

    token = auth.access_token()
    if not token:
        print(json.dumps({"ok": False, "reason": "no access token"}))
        return 1

    cache = fetch_bodies(days, cache_path, token)
    rejections, near = classify(cache)

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_days": days,
        "messages_cached": len(cache),
        "rejections_confirmed": len(rejections),
        "rejections": rejections,
        "near_misses": near,
    }
    write_atomic(out_path, json.dumps(report, ensure_ascii=False, indent=2))
    print(f"confirmed rejections: {len(rejections)}")
    print(f"written {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
