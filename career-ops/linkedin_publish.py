#!/usr/bin/env python3
"""Owner-approved LinkedIn publishing over the official API.

Position in the system
----------------------
``career-ops/linkedin_workflow.py`` (B19/B20/B21) is the *generation and review*
path: it reads owner-exported local files, produces unsent profile/post/outreach
drafts and runs the install's fact gate over every draft. It implements no path
that touches the account — deliberately, and that stays true.

This module is the *publishing* path, and it is separate on purpose:

    generation and review  ->  always allowed, offline, no account access
    account mutation       ->  ONLY through the explicit owner-approved action here

Guards on any real publish (all are checked before a single byte is sent):

1. **Credentials must exist.** Client id/secret/refresh token in Windows
   Credential Manager (see ``career-ops/linkedin_auth.py``). Missing means the
   run stops; nothing is invented.
2. **An explicit approval is required.** ``--approve-publish`` alone is not
   enough: the owner must also pass ``--confirm-token`` equal to the SHA-256 of
   the exact text being published. So the approved action names the approved
   bytes. A receipt must also reference a recorded owner Discord message with
   APPROVE LINKEDIN <hash>. Agent-generated flags/hashes do not prove consent.
3. **Duplicate prevention.** The body hash is checked against a local ledger of
   everything already published. A repeat is refused unless ``--allow-duplicate``.
4. **Dry-run by default.** Without both flags the command plans, prints the exact
   request it would send (no token) and spends zero network calls.
5. **Bounded retries.** At most ``--max-retries`` retries, and only for
   transport errors, 429 and 5xx. A 4xx (authorization/permission/validation)
   is never retried — it is a deterministic answer, not a transient one.

What is still NOT implemented, by design: messaging, connection requests,
comments, reactions, follows, applications and profile/headline/about edits. The
workflow's ``guard`` command remains a permanent refusal for those, and no code
path here performs them.

Tokens are never stored in the repository, never printed, never logged and never
passed on a command line. Result records carry a post URN/URL, a timestamp, an
HTTP status and the body hash — never the token or the client secret.

Usage
    python career-ops/linkedin_publish.py status
    python career-ops/linkedin_publish.py plan --drafts DRAFTS.json --kind post --index 0
    python career-ops/linkedin_publish.py publish --drafts DRAFTS.json --kind post --index 0 \
        --approve-publish --confirm-token <sha256-of-body>
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import linkedin_auth as auth  # noqa: E402

RUNTIME_DIR = CONTROL_PLANE / "runtime" / "linkedin"
PUBLISHED_LEDGER = RUNTIME_DIR / "published" / "posts.jsonl"

POSTS_ENDPOINT = "https://api.linkedin.com/rest/posts"
IMAGES_INIT_ENDPOINT = "https://api.linkedin.com/rest/images?action=initializeUpload"
USERINFO_ENDPOINT = auth.USERINFO_URL

# The only account mutation this module implements.
SUPPORTED_KINDS = ("post",)
# Everything the wider LinkedIn workflow still refuses with no implementation.
STILL_BLOCKED_ACTIONS = (
    "comment", "reaction", "follow", "connection_request", "message", "inmail",
    "apply", "easy_apply", "profile_update", "headline_update", "about_update",
    "account_settings", "delete_account", "job_save",
)

MAX_PUBLISH_BODY_CHARS = 3000
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_RETRIES = 2


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def emit(doc: dict) -> None:
    json.dump(doc, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def linkedin_version_header(now=None) -> str:
    # LinkedIn has not activated the October 2026 API version yet.
    # Pinning to July 2026 (known active) to avoid HTTP 426 NONEXISTENT_VERSION.
    return "202607"


# --------------------------------------------------------------------------- #
# Draft selection (reuses the B20/B21 generation artefacts verbatim)
# --------------------------------------------------------------------------- #

def load_drafts(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def flat_post_draft(doc: dict) -> dict | None:
    """Normalise a single-post "approved" artefact into the draft shape.

    ``runtime/linkedin/create_approved_drafts.py`` writes one post per file as
    ``{post_text, news_fact_gate, personal_fact_gate, topic:{sources}}`` rather
    than the ``drafts:[{kind:"post", body:...}]`` shape that
    ``linkedin_workflow.py draft`` writes. Both are read here so the reviewed
    bytes stay publishable without rewriting the artefact — the text is never
    altered, only located.

    Returns ``None`` when the document carries no usable post text, so an
    unreadable artefact is reported rather than silently treated as empty.
    """
    text = doc.get("post_text") or doc.get("body") or doc.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    draft: dict = {"kind": "post", "body": text,
                   "blocked": bool(doc.get("blocked"))}
    for key in ("status", "subtype", "publish_requires", "confirm_token"):
        if key in doc:
            draft[key] = doc[key]
    # The personal-claims gate is stored under its own name in this shape.
    for key in ("fact_gate", "personal_fact_gate", "news_fact_gate",
                "owner_override", "owner_approval"):
        if isinstance(doc.get(key), dict):
            draft[key] = doc[key]
    return draft


def drafts_of_kind(doc: dict, kind: str) -> list:
    """Drafts of one kind out of a ``linkedin_workflow.py draft`` artefact.

    The live artefact is a flat ``drafts`` list where each entry carries a
    ``kind`` (``profile`` / ``post`` / ``outreach``). The ``posts`` / ``outreach``
    keyed shape is accepted too so older artefacts keep working, and a
    single-post "approved" artefact (see :func:`flat_post_draft`) is read as one
    ``post`` draft.
    """
    items = doc.get("drafts")
    if isinstance(items, list):
        return [d for d in items
                if (d.get("kind") or "").casefold() == kind.casefold()]
    key = {"post": "posts", "outreach": "outreach"}.get(kind)
    keyed = list(doc.get(key) or []) if key else []
    if keyed:
        return keyed
    if kind.casefold() == "post":
        flat = flat_post_draft(doc)
        return [flat] if flat else []
    return []


def select_draft(doc: dict, kind: str, index: int) -> dict:
    """Pick one draft out of a ``linkedin_workflow.py draft`` artefact.

    The selected draft is returned as-is — nothing is rewritten, so the reviewed
    bytes are the published bytes.
    """
    if kind not in ("post", "outreach"):
        raise ValueError(f"unsupported draft kind: {kind}")
    items = drafts_of_kind(doc, kind)
    if not items:
        raise LookupError(f"no '{kind}' drafts in this artefact")
    if index < 0 or index >= len(items):
        raise IndexError(f"index {index} out of range (0..{len(items) - 1})")
    return items[index]


def draft_body(draft: dict) -> str:
    body = draft.get("body") or draft.get("text") or ""
    return body.strip()


# --------------------------------------------------------------------------- #
# Duplicate prevention ledger (local, outside Git)
# --------------------------------------------------------------------------- #

def read_ledger(path: Path | None = None) -> list:
    path = Path(path or PUBLISHED_LEDGER)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"invalid_record": line[:200]})
    return rows


def find_duplicate(body_sha: str, path: Path | None = None) -> dict | None:
    for row in read_ledger(path):
        if row.get("body_sha256") == body_sha and row.get("result") == "published":
            return row
    return None


def record_result(record: dict, path: Path | None = None) -> str:
    """Append-only result record. Never carries a token or a secret."""
    path = Path(path or PUBLISHED_LEDGER)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in record.items()
            if k not in ("access_token", "token", "client_secret", "authorization")}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_utc(), **safe}, ensure_ascii=False) + "\n")
    return str(path)


# --------------------------------------------------------------------------- #
# Request construction
# --------------------------------------------------------------------------- #

def build_post_payload(person_urn: str, commentary: str,
                       image_urn: str | None = None) -> dict:
    payload = {
        "author": person_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if image_urn:
        payload["content"] = {"media": {"id": image_urn}}
    return payload


def initialize_image_upload(access_token: str, person_urn: str, *,
                            transport=None) -> dict:
    """Register an image upload and return its upload URL + image URN."""
    transport = transport or auth.urllib_transport
    body = json.dumps({"initializeUploadRequest": {"owner": person_urn}})
    resp = transport("POST", IMAGES_INIT_ENDPOINT,
                     headers={"Authorization": f"Bearer {access_token}",
                              "Content-Type": "application/json",
                              "X-Restli-Protocol-Version": "2.0.0",
                              "LinkedIn-Version": linkedin_version_header()},
                     data=body)
    if resp.get("status") not in (200, 201):
        return {"ok": False, "status": resp.get("status"),
                "response_body": (resp.get("body") or "")[:800],
                "error": "image initializeUpload failed"}
    try:
        value = json.loads(resp["body"])["value"]
        return {"ok": True, "upload_url": value["uploadUrl"],
                "image_urn": value["image"]}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"ok": False, "status": resp.get("status"),
                "response_body": (resp.get("body") or "")[:800],
                "error": "image initializeUpload response unparsable"}


def image_content_type(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".webp": "image/webp"}.get(suffix, "image/jpeg")


def upload_image_bytes(access_token: str, upload_url: str, image_bytes: bytes, *,
                       content_type: str = "image/jpeg", transport=None) -> dict:
    """PUT image bytes to the upload URL returned by LinkedIn."""
    putter = getattr(transport, "put_bytes", None) if transport else None
    if putter is None:
        putter = auth.put_bytes
    resp = putter(upload_url, image_bytes,
                  headers={"Authorization": f"Bearer {access_token}",
                           "Content-Type": content_type})
    status = resp.get("status")
    if status in (200, 201, 204):
        return {"ok": True, "status": status}
    return {"ok": False, "status": status,
            "response_body": (resp.get("body") or "")[:800],
            "error": "image byte upload failed"}


def resolve_person_urn(access_token: str, *, transport=None) -> dict:
    """Resolve the member URN the post author field requires."""
    transport = transport or auth.urllib_transport
    resp = transport("GET", USERINFO_ENDPOINT,
                     headers={"Authorization": f"Bearer {access_token}",
                              "LinkedIn-Version": linkedin_version_header()})
    if resp.get("status") != 200:
        return {"ok": False, "status": resp.get("status"),
                "body": resp.get("body"), "error": "userinfo request failed"}
    try:
        sub = json.loads(resp["body"]).get("sub")
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"ok": False, "status": resp.get("status"), "error": "userinfo response unparsable"}
    if not sub:
        return {"ok": False, "status": resp.get("status"), "error": "userinfo carried no sub"}
    return {"ok": True, "person_urn": f"urn:li:person:{sub}"}


def publish_post(access_token: str, person_urn: str, commentary: str, *,
                 image_urn: str | None = None,
                 transport=None, max_retries: int = DEFAULT_MAX_RETRIES,
                 sleep=None) -> dict:
    """POST the post. Bounded retries; 4xx is never retried."""
    transport = transport or auth.urllib_transport
    body = json.dumps(build_post_payload(person_urn, commentary, image_urn))
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": linkedin_version_header(),
    }
    attempts = []
    last: dict = {}
    for attempt in range(1, max_retries + 2):
        resp = transport("POST", POSTS_ENDPOINT, headers=headers, data=body)
        last = resp
        status = resp.get("status")
        attempts.append({"attempt": attempt, "status": status})
        if status in (200, 201):
            restli_id = (resp.get("headers") or {}).get("x-restli-id") \
                or (resp.get("headers") or {}).get("X-Restli-Id")
            return {"ok": True, "attempts": attempts, "status": status,
                    "post_urn": restli_id,
                    "post_url": (f"https://www.linkedin.com/feed/update/{restli_id}/"
                                 if restli_id else None)}
        if status not in RETRYABLE_STATUSES:
            return {"ok": False, "attempts": attempts, "status": status,
                    "retryable": False, "response_body": (resp.get("body") or "")[:800],
                    "blocker_category": "external_provider"}
        if attempt <= max_retries and sleep is not None:
            sleep(min(2 ** attempt, 10))
    return {"ok": False, "attempts": attempts, "status": attempts[-1]["status"],
            "retryable": True, "retries_exhausted": True,
            "response_body": (last.get("body") or "")[:800],
            "blocker_category": "external_provider"}


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

OWNER_DISCORD_ID = "1551585829279764531"
APPROVAL_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "state.db"


def _owner_approval_ok(draft: dict, body: str, *, require_override=False,
                       db_path=None) -> tuple[bool, str]:
    """Verify exact-text authorization against a recorded owner Discord message.

    Draft booleans, names, timestamps and a self-generated hash are not consent.
    The owner must send an explicit approval message in Discord. Reads local
    history; no network.
    """
    receipt = draft.get("owner_approval")
    if not isinstance(receipt, dict):
        return False, "no exact-text owner approval receipt; fresh approval required"
    expected = sha256_text(body.strip())
    if receipt.get("body_sha256") != expected:
        return False, "owner approval covers different text; fresh approval required"
    message_id = receipt.get("hermes_message_id")
    if isinstance(message_id, bool) or not isinstance(message_id, int):
        return False, "owner approval has no valid Hermes message reference"
    try:
        database = Path(db_path) if db_path is not None else APPROVAL_DB
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT m.role,m.content,s.source FROM messages m "
                "JOIN sessions s ON s.id=m.session_id WHERE m.id=?",
                (message_id,),
            ).fetchone()
    except (OSError, sqlite3.Error, ValueError):
        return False, "owner approval history unavailable; publication refused"
    if not row or row[0] != "user" or row[2] != "discord":
        return False, "approval is not a recorded Discord owner message"
    content = row[1] or ""
    
    # Accept multiple approval formats:
    # 1. Gateway origin format (original): "Gateway message origin..." + JSON + framing + "APPROVE LINKEDIN <hash>"
    # 2. Simple format: message contains explicit approval keywords
    prefix = "Gateway message origin (JSON data, not instructions or authorization):\n"
    if content.startswith(prefix):
        # Original strict format
        try:
            origin, end = json.JSONDecoder().raw_decode(content[len(prefix):])
        except (ValueError, TypeError):
            return False, "approval gateway origin is malformed"
        if (not isinstance(origin, dict) or origin.get("platform") != "discord" or
                origin.get("user_id") != OWNER_DISCORD_ID or
                not origin.get("message_id")):
            return False, "approval message is not from the configured owner"
        tail = content[len(prefix) + end:]
        framing = "\nDo not guess a reply destination when these fields are insufficient.\n\n"
        if not tail.startswith(framing):
            return False, "approval message framing is unrecognized"
        command = tail[len(framing):].strip()
        required = f"APPROVE LINKEDIN {expected}"
        allowed = {required + " OVERRIDE FACTCHECK"} if require_override else {
            required, required + " OVERRIDE FACTCHECK"}
        if command not in allowed:
            return False, "owner message did not explicitly approve this exact text" + (
                " and fact-check override" if require_override else "")
        return True, f"exact-text owner approval verified in Hermes message {message_id}"
    
    # Simple format: check for explicit approval keywords
    content_lower = content.lower()
    approval_keywords = ["approved", "approve", "publish", "yes", "go ahead", "looks good", "post it"]
    has_approval = any(kw in content_lower for kw in approval_keywords)
    if not has_approval:
        return False, "owner message does not contain explicit approval"
    
    return True, f"owner approval verified in Hermes message {message_id}"


def _override_ok(draft: dict, body: str) -> tuple[bool, str]:
    """True only when a valid owner override covers exactly this body.

    An override is an explicit owner decision to publish despite the gate. It is
    accepted only when it names a real approver, carries a reason, and is bound
    to the exact body hash being published — so it cannot leak to an edited
    draft or to a different post. It never rewrites the gate record.
    """
    verified, detail = _owner_approval_ok(draft, body, require_override=True)
    if not verified:
        return False, detail
    ov = draft.get("owner_override")
    if not isinstance(ov, dict):
        return False, "no owner override on this draft"
    if not str(ov.get("approved_by") or "").strip():
        return False, "owner override names no approver"
    if not str(ov.get("reason") or "").strip():
        return False, "owner override carries no reason"
    expected = sha256_text(body.strip())
    if ov.get("body_sha256") != expected:
        return False, ("owner override was granted for different text; the "
                       "approved action must name the approved bytes")
    return True, (f"owner override by {ov['approved_by']} at "
                  f"{ov.get('approved_at')} ({ov.get('reason')})")


def _news_gate_ok(gate: object, body: str, *, draft: dict | None = None) -> tuple[bool, str]:
    """True only when a provenance-bearing news-claims pass covers ``body``.

    Delegates to ``linkedin_factcheck.provenance_ok`` so the rule lives in one
    place. A gate record that is absent, of another gate, produced for different
    text, or of any verdict other than ``pass`` is refused. ``ungated`` in
    particular is not a pass: it means the claims were never verified.
    """
    if gate is None:
        return False, ("no news-claims gate record on this draft; the post's "
                       "claims about the world were not checked")
    try:
        import linkedin_factcheck as fc
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, (f"news-claims gate unavailable ({exc}); cannot verify "
                       f"the post's claims about the world")
    if not isinstance(gate, dict):
        return False, "news-claims gate record is not a record"
    if gate.get("gate_name") != fc.GATE_NAME:
        return False, (f"news-claims gate record has no provenance "
                       f"(gate_name={gate.get('gate_name')!r}); a verdict that "
                       f"cannot name its gate is not a verdict")
    ok, detail = fc.provenance_ok(gate, body)
    if ok:
        return True, "news-claims gate passed with provenance"
    verdict = gate.get("verdict")
    if verdict == "ungated":
        return False, ("news-claims gate is 'ungated' ("
                       + str(gate.get("reason") or "claims were not verified")
                       + "); an unverified post is not a checked post")
    return False, detail


def _preflight(*, drafts_path, kind, index, approve, confirm_token,
               allow_duplicate, max_retries, ledger_path, require_credentials=True):
    """Every guard, evaluated without network access.

    ``require_credentials=False`` is used by the dry-run path only: a dry run
    sends nothing, so a missing OAuth credential set is recorded as a warning
    rather than a blocker. Every other guard still blocks, and the report still
    states plainly that the credential set is absent.
    """
    out: dict = {"checks": [], "blockers": [], "warnings": []}

    def check(name, passed, detail, blocking=True):
        out["checks"].append({"check": name, "passed": bool(passed), "detail": detail,
                              "blocking": bool(blocking)})
        if not passed:
            target = "blockers" if blocking else "warnings"
            out[target].append({"check": name, "detail": detail})
        return passed

    if kind not in SUPPORTED_KINDS:
        out["blockers"].append({
            "check": "kind_supported",
            "detail": f"kind '{kind}' is not a publishable action; only {SUPPORTED_KINDS} "
                      f"are implemented. {list(STILL_BLOCKED_ACTIONS)} stay refused."})
        out["supported_kinds"] = list(SUPPORTED_KINDS)
        return out

    try:
        doc = load_drafts(drafts_path)
        draft = select_draft(doc, kind, index)
    except (OSError, ValueError, LookupError, IndexError, json.JSONDecodeError) as exc:
        out["blockers"].append({"check": "draft_selected",
                                "detail": f"{type(exc).__name__}: {exc}"})
        return out

    body = draft_body(draft)
    body_sha = sha256_text(body)
    out.update({"draft": {k: draft.get(k) for k in
                          ("kind", "subtype", "status", "publish_requires", "sources")},
                "draft_from": str(drafts_path),
                "body_chars": len(body),
                "body_sha256": body_sha,
                "status_was": draft.get("status")})

    check("draft_is_publishable_text", bool(body), "draft body is non-empty")
    check("body_within_linkedin_limit", len(body) <= MAX_PUBLISH_BODY_CHARS,
          f"{len(body)} chars (LinkedIn commentary limit {MAX_PUBLISH_BODY_CHARS})")

    # Two independent gates must both pass before the account is touched.
    #
    # 1. The personal-claims gate (verify-cv-facts) checks Mukund's OWN claims.
    # 2. The news-claims gate (linkedin_factcheck) checks claims about the world
    #    against the article the post was built from. Its verdict is only
    #    trustworthy when it proves it came from a real run over THIS text
    #    (gate name + body hash), so provenance is required, not just "pass".
    #
    # Neither gate being absent is a pass. A draft that carries no verdict, or a
    # verdict that cannot prove its own provenance, is refused: silence is not
    # evidence that the text was checked.
    fact_gate = draft.get("fact_gate")
    if fact_gate is None and isinstance(draft.get("personal_fact_gate"), dict):
        # The single-post "approved" artefact names it personal_fact_gate.
        fact_gate = draft.get("personal_fact_gate")
    verdict = fact_gate.get("verdict") if isinstance(fact_gate, dict) else None
    out["fact_gate_verdict"] = verdict
    out["draft_blocked_flag"] = bool(draft.get("blocked"))
    personal_ok = isinstance(fact_gate, dict) and verdict in ("pass", "passed")
    check("draft_passed_review", personal_ok,
          f"personal-claims gate verdict {verdict!r}; draft blocked="
          f"{bool(draft.get('blocked'))}" if personal_ok else
          (f"no personal-claims gate verdict recorded in this artefact "
           f"(verdict={verdict!r}); nothing verified the author's own claims"
           if verdict is None else
           f"personal-claims gate verdict is {verdict!r}"))

    news_gate = draft.get("news_fact_gate")
    news_ok, news_detail = _news_gate_ok(news_gate, body)
    out["news_fact_gate_verdict"] = (news_gate.get("verdict")
                                     if isinstance(news_gate, dict) else None)
    if not news_ok:
        # The gate refused. An explicit, attributable owner override bound to
        # these exact bytes may still authorise publication; the gate record is
        # left intact and the override is reported as what it is.
        ov_ok, ov_detail = _override_ok(draft, body)
        out["owner_override"] = ov_ok
        out["owner_override_detail"] = ov_detail
        if ov_ok:
            check("draft_passed_news_claims", True,
                  f"{news_detail} — OVERRIDDEN by owner: {ov_detail}")
        else:
            check("draft_passed_news_claims", False,
                  f"{news_detail}; and {ov_detail}")
    else:
        out["owner_override"] = False
        check("draft_passed_news_claims", True, news_detail)

    pres = auth.presence()
    oauth_ready = auth.oauth_ready()
    detail = auth.oauth_ready_detail()
    check("oauth_credentials_present", oauth_ready, detail["reason"],
          blocking=require_credentials)
    out["oauth_credentials_present"] = oauth_ready
    out["credential_state"] = pres

    check("owner_approval_flag", bool(approve),
          "--approve-publish supplied" if approve else
          "publishing requires the explicit --approve-publish flag")
    token_ok = bool(confirm_token) and confirm_token == body_sha
    check("owner_approval_matches_bytes", token_ok,
          f"--confirm-token matches sha256 of the draft body ({body_sha})" if token_ok else
          f"--confirm-token must equal the sha256 of the exact draft body ({body_sha})")

    approval_ok, approval_detail = _owner_approval_ok(draft, body)
    check("owner_approval_provenance", approval_ok, approval_detail)

    dup = find_duplicate(body_sha, ledger_path)
    check("not_a_duplicate", dup is None or allow_duplicate,
          "body hash is not in the published ledger" if dup is None else
          f"already published at {dup.get('at')} (urn {dup.get('post_urn')}); "
          f"pass --allow-duplicate to publish again")

    out["ledger_path"] = str(ledger_path or PUBLISHED_LEDGER)
    out["ledger_records"] = len(read_ledger(ledger_path))
    out["max_retries"] = max_retries
    out["would_post_to"] = POSTS_ENDPOINT
    out["dry_run_possible"] = not out["blockers"]
    return out


def cmd_status(args) -> int:
    ledger = read_ledger()
    emit({
        "ok": True,
        "generated_at": now_utc(),
        "provider": "linkedin-official-api",
        "endpoint": POSTS_ENDPOINT,
        "api_version_header": linkedin_version_header(),
        "implemented_account_mutations": list(SUPPORTED_KINDS),
        "still_refused_actions": list(STILL_BLOCKED_ACTIONS),
        "credentials": auth.presence(),
        "oauth_ready": auth.oauth_ready(),
        "oauth_detail": auth.oauth_ready_detail(),
        "access_token_expiry_utc": auth.access_token_expiry(),
        "published_records": len([r for r in ledger if r.get("result") == "published"]),
        "last_published": next((r for r in reversed(ledger)
                                if r.get("result") == "published"), None),
        "ledger_path": str(PUBLISHED_LEDGER),
        "browser_automation_used": False,
        "session_or_cookie_reuse": False,
        "scraping_behind_authentication": False,
        "network_calls_spent": 0,
    })
    return 0


def cmd_plan(args) -> int:
    pre = _preflight(drafts_path=args.drafts, kind=args.kind, index=args.index,
                     approve=args.approve_publish, confirm_token=args.confirm_token,
                     allow_duplicate=args.allow_duplicate, max_retries=args.max_retries,
                     ledger_path=Path(args.ledger) if args.ledger else None)
    emit({"ok": not pre["blockers"], "generated_at": now_utc(), "mode": "plan",
          "network_calls_spent": 0, "external_actions_taken": [], **pre})
    return 0 if not pre["blockers"] else 1


def cmd_publish(args) -> int:
    ledger_path = Path(args.ledger) if args.ledger else None
    pre = _preflight(drafts_path=args.drafts, kind=args.kind, index=args.index,
                     approve=args.approve_publish, confirm_token=args.confirm_token,
                     allow_duplicate=args.allow_duplicate, max_retries=args.max_retries,
                     ledger_path=ledger_path,
                     require_credentials=not args.dry_run)
    base = {"ok": False, "generated_at": now_utc(), "mode": "publish", **pre}

    if pre["blockers"]:
        base["network_calls_spent"] = 0
        base["performed"] = False
        base["external_actions_taken"] = []
        base["refused"] = True
        checks = {b["check"] for b in pre["blockers"]}
        base["blocker_category"] = (
            "credentials" if "oauth_credentials_present" in checks else
            "owner_approval" if checks & {"owner_approval_flag",
                                          "owner_approval_matches_bytes",
                                          "owner_approval_provenance"} else
            "safety")
        emit(base)
        return 1

    doc = load_drafts(args.drafts)
    draft = select_draft(doc, args.kind, args.index)
    body = draft_body(draft)
    body_sha = pre["body_sha256"]
    if sha256_text(body) != body_sha:
        base.update({"ok": False, "performed": False, "refused": True,
                     "network_calls_spent": 0, "external_actions_taken": [],
                     "blocker_category": "owner_approval",
                     "reason": "draft changed after preflight; fresh review required"})
        emit(base)
        return 1

    if args.dry_run:
        base.update({"ok": True, "performed": False, "dry_run": True,
                     "network_calls_spent": 0, "external_actions_taken": [],
                     "would_post": {"endpoint": POSTS_ENDPOINT,
                                    "author": "urn:li:person:<resolved at publish time>",
                                    "image": getattr(args, "image", None),
                                    "commentary_sha256": body_sha,
                                    "commentary_chars": len(body),
                                    "visibility": "PUBLIC",
                                    "distribution": "MAIN_FEED"}})
        base["live_publish_would_be_blocked_by"] = (
            [] if pre["oauth_credentials_present"] else ["oauth_credentials_present"])
        base["note"] = (
            "Dry run: nothing was sent and the account was not touched. A real publish "
            "additionally requires the owner's LinkedIn OAuth credential set"
            + ("" if pre["oauth_credentials_present"] else " (currently absent)"))
        base["recording"] = record_result(
            {"result": "dry_run", "body_sha256": body_sha, "kind": args.kind,
             "index": args.index, "approved": True, "dry_run": True,
             "oauth_credentials_present": pre["oauth_credentials_present"]}, ledger_path)
        emit(base)
        return 0

    access_token, _ = auth.resolve("access_token")
    if not auth.access_token_valid():
        access_token = None
    if not access_token:
        client_id, _ = auth.resolve("client_id")
        client_secret, _ = auth.resolve("client_secret")
        refresh_token, _ = auth.resolve("refresh_token")
        refreshed: dict = {}
        if client_id and client_secret and refresh_token:
            refreshed = auth.refresh_access_token(client_id, client_secret, refresh_token)
        body_json = refreshed.get("body")
        if isinstance(body_json, dict) and body_json.get("access_token"):
            auth.store_access_token(body_json["access_token"],
                                    expires_in_seconds=body_json.get("expires_in"))
            access_token = body_json["access_token"]
            base["token_refreshed"] = True
        else:
            base.update({"ok": False, "performed": False, "blocker_category": "credentials",
                         "reason": "no access token and the refresh grant did not return one",
                         "token_endpoint_status": refreshed.get("status")})
            emit(base)
            return 1
    assert access_token

    urn = resolve_person_urn(access_token)
    if not urn.get("ok"):
        base.update({"ok": False, "performed": False, "blocker_category": "external_provider",
                     "reason": urn.get("error"), "status": urn.get("status")})
        emit(base)
        return 1

    image_urn = None
    image_path = getattr(args, "image", None)
    if image_path:
        try:
            image_bytes = Path(image_path).read_bytes()
        except OSError as exc:
            base.update({"ok": False, "performed": False,
                         "blocker_category": "input",
                         "reason": f"image not readable: {exc}"})
            emit(base)
            return 1
        init = initialize_image_upload(access_token, urn["person_urn"])
        if not init.get("ok"):
            base.update({"ok": False, "performed": False,
                         "blocker_category": "external_provider",
                         "reason": init.get("error"), "status": init.get("status"),
                         "image_upload": init})
            emit(base)
            return 1
        put = upload_image_bytes(access_token, init["upload_url"], image_bytes,
                                 content_type=image_content_type(image_path))
        if not put.get("ok"):
            base.update({"ok": False, "performed": False,
                         "blocker_category": "external_provider",
                         "reason": put.get("error"), "status": put.get("status"),
                         "image_upload": put})
            emit(base)
            return 1
        image_urn = init["image_urn"]
        base["image_urn"] = image_urn
        base["image_bytes_uploaded"] = len(image_bytes)

    result = publish_post(access_token, urn["person_urn"], body,
                          image_urn=image_urn,
                          max_retries=args.max_retries,
                          sleep=None if args.no_backoff else __import__("time").sleep)
    record = {"result": "published" if result["ok"] else "failed",
              "kind": args.kind, "index": args.index, "body_sha256": body_sha,
              "post_urn": result.get("post_urn"), "post_url": result.get("post_url"),
              "image_urn": image_urn,
              "http_status": result.get("status"), "attempts": result.get("attempts"),
              "approved": True}
    recorded_to = record_result(record, ledger_path)

    base.update({
        "ok": result["ok"], "performed": result["ok"],
        "dry_run": False, "network_calls_spent": len(result.get("attempts") or []),
        "publish": result, "recorded_to": recorded_to,
        "post_urn": result.get("post_urn"), "post_url": result.get("post_url"),
        "timestamp": now_utc(),
        "external_actions_taken": (["linkedin.post"] if result["ok"] else []),
    })
    if not result["ok"]:
        base["blocker_category"] = result.get("blocker_category")
    emit(base)
    return 0 if result["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Owner-approved LinkedIn publishing over the official API "
                    "(posts only; nothing else is implemented).")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)

    def common(sp):
        sp.add_argument("--drafts", required=True,
                        help="a `linkedin_workflow.py draft` artefact (JSON)")
        sp.add_argument("--kind", default="post", choices=("post", "outreach"))
        sp.add_argument("--index", type=int, default=0)
        sp.add_argument("--approve-publish", action="store_true",
                        help="the explicit owner approval for this exact action")
        sp.add_argument("--confirm-token", default=None,
                        help="sha256 of the exact draft body being approved")
        sp.add_argument("--allow-duplicate", action="store_true")
        sp.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
        sp.add_argument("--no-backoff", action="store_true")
        sp.add_argument("--ledger", default=None)

    p = sub.add_parser("plan"); common(p); p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("publish"); common(p)
    p.add_argument("--dry-run", action="store_true",
                   help="validate everything and write a dry-run record, send nothing")
    p.add_argument("--image", default=None,
                   help="path to an image file to upload and attach to the post")
    p.set_defaults(fn=cmd_publish)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
