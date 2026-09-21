#!/usr/bin/env python3
"""Sync Chief-channel Discord archive to the private control-plane repo.

Reads local append-only daily JSONL from the Discord archive, filters and
redacts, and publishes curated batches to conversations/discord/<date>-chief.jsonl
in mukund-chief-control-plane. Commits once per run (batched, not per message).
A local checkpoint file records the last synced archive line offset + content
hash per day so repeated syncs never duplicate records.

Usage:  python sync_discord_chief.py [--dry-run]
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ARCHIVE_DIR = Path(r"C:\Users\mukun\DiscordArchive\chief")
REPO = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
DEST_DIR = REPO / "conversations" / "discord"
CHECKPOINT = ARCHIVE_DIR / ".sync-checkpoint.json"
CHIEF_CHANNEL_ID = "1551586294382067762"

# Credential-like patterns: records containing these are REJECTED (skipped), not published.
REJECT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"bot[_ -]?token", r"api[_ -]?key", r"\bsecret\b", r"password\s*[:=]",
        r"passwd", r"\bbearer\s+[a-z0-9._-]{16,}", r"authorization:\s*\S+",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\b(ghp|gho|ghu|ghs|xox[baprs]|sk-|sk_|AKIA|AGNT)[A-Za-z0-9_-]{16,}\b",
        r"mfa\.\w{20,}", r"\b\d{3}-\d{3}-\d{3}-\d{3}\b",  # Discord/MFA token shapes
        r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.",  # JWT
    ]
]
# Inline redaction of obvious secrets inside otherwise-fine messages.
REDACT_PATTERNS = [
    (re.compile(r"\b(ghp|gho|ghu|ghs|xox[baprs]|sk-|sk_|AKIA)[A-Za-z0-9_-]{16,}\b", re.IGNORECASE), "[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED JWT]"),
    (re.compile(r"mfa\.\w{20,}"), "[REDACTED]"),
]


def load_checkpoint():
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_checkpoint(cp):
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(cp, indent=1), encoding="utf-8")


def scan(text):
    """Return (redacted_text, rejected)."""
    for pat in REJECT_PATTERNS:
        if pat.search(text):
            return text, True
    out = text
    for pat, repl in REDACT_PATTERNS:
        out = pat.sub(repl, out)
    return out, False


def git(*args, check=True):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not ARCHIVE_DIR.exists():
        print("No archive directory yet; nothing to sync.")
        return 0

    cp = load_checkpoint()
    published = {}  # day -> list of records
    rejected = 0

    for path in sorted(ARCHIVE_DIR.glob("*-chief.jsonl")):
        day = path.name[:10]
        state = cp.get(day, {"lines": 0, "last_hash": None})
        lines = path.read_text(encoding="utf-8").splitlines()
        new = lines[state["lines"]:]
        if not new:
            continue
        out_records = []
        for line in new:
            line = line.strip()
            if not line:
                state["lines"] += 1
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                state["lines"] += 1
                continue  # append-only archive; skip corrupt line
            if str(rec.get("channel_id")) != CHIEF_CHANNEL_ID:
                state["lines"] += 1
                continue  # never publish non-chief channels
            content, bad = scan(str(rec.get("content") or ""))
            state["lines"] += 1
            if bad:
                rejected += 1
                print(f"REJECTED credential-like record ({day}) — not published.")
                continue
            rec["content"] = content
            # strip anything not in the approved field set
            allowed = ["timestamp", "direction", "channel_id", "channel_name",
                       "thread_id", "session_id", "author_role", "message_id", "content"]
            rec = {k: rec.get(k) for k in allowed}
            out_records.append(rec)
        if out_records:
            published[day] = out_records
        state["last_hash"] = hashlib.sha256(
            "\n".join(lines[: state["lines"]]).encode("utf-8")).hexdigest()
        cp[day] = state

    if not published:
        print("Nothing new to sync.")
        return 0

    if args.dry_run:
        for day, recs in published.items():
            print(f"would publish {len(recs)} records to conversations/discord/{day}-chief.jsonl")
        print(f"rejected: {rejected}")
        return 0

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    changed = []
    for day, recs in published.items():
        dest = DEST_DIR / f"{day}-chief.jsonl"
        existing = []
        if dest.exists():
            try:
                existing = [json.loads(l) for l in dest.read_text(encoding="utf-8").splitlines() if l.strip()]
            except Exception:
                existing = []
        merged = existing + recs
        # Dedupe: identity = direction + message_id when message_id is present
        # (a Discord message ID appears only once per direction); fallback identity
        # = timestamp + direction + content hash. Content matching alone never
        # dedupes distinct messages.
        seen_ids, seen_fb, uniq = set(), set(), []
        for r in merged:
            mid = r.get("message_id")
            if mid:
                key = (r.get("direction"), str(mid))
                if key in seen_ids:
                    continue
                seen_ids.add(key)
            else:
                key = (r.get("timestamp"), r.get("direction"), hashlib.sha256(str(r.get("content")).encode()).hexdigest())
                if key in seen_fb:
                    continue
                seen_fb.add(key)
            uniq.append(r)
        dest.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in uniq) + "\n", encoding="utf-8")
        changed.append(dest)

    total = sum(len(r) for r in published.values())
    git("add", *[str(c.relative_to(REPO)) for c in changed])
    # Nothing-to-commit is OK: every new record was already published (e.g. a
    # previous run committed but crashed before the checkpoint advanced). Treat
    # as success so the checkpoint can advance; push still runs below.
    cr = git("commit", "-m",
             f"sync: Chief Discord transcript {', '.join(sorted(published))} ({total} msgs)",
             check=False)
    if cr.returncode != 0 and "nothing to commit" not in (cr.stdout or "") + (cr.stderr or "") \
            and "no changes added to commit" not in (cr.stdout or "") + (cr.stderr or ""):
        raise RuntimeError(f"git commit: {(cr.stderr or cr.stdout).strip()}")
    # Push must succeed before the checkpoint advances; if the local branch is
    # already in sync with origin (record pushed by an earlier recovery), that
    # also counts as success.
    pr = git("push", check=False)
    if pr.returncode != 0 and "Everything up-to-date" not in (pr.stdout or "") + (pr.stderr or ""):
        raise RuntimeError(f"git push: {pr.stderr.strip()}")
    save_checkpoint(cp)
    print(f"Published {total} records across {len(published)} day-file(s); rejected {rejected}. Pushed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
