#!/usr/bin/env python3
"""Minimal LinkedIn workflow for Chief OS v1 — read-only intake + drafts.

What this is
------------
LinkedIn is treated as two things only:

1. a **read-only signal source** — an owner-exported/local file of saved jobs,
   job alerts or followed companies is parsed for job/company signals;
2. a **draft surface** — profile, post and outreach text is *drafted* for owner
   review from canonical Career Ops facts.

What this is NOT
----------------
There is no LinkedIn login, no session reuse, no API call, no scraping, no
browser and no network I/O of any kind. ``guard`` exists as an explicit,
permanent refusal: posting, messaging, connecting, following, reacting, editing
the profile or applying is owner-gated and no code path here performs it.

Reused, not rebuilt
-------------------
* ``career-ops/tracker_writer.py`` — every dedupe key and every workbook write;
* ``career-watch/company_watch.py`` — the shared dedupe index, the regional
  provenance-column policy and the Career Ops handoff invoker;
* ``company_registry.py`` — the watched-company registry (name + variant keys);
* ``career-ops/cv_workflow.py`` — the install's fact gate
  (``verify-cv-facts.mjs``) and the canonical CV markdown parser.

Truth rules
-----------
* A LinkedIn signal is only ever what the input file says. No employer, title,
  location, salary, clearance or eligibility is inferred.
* Drafts contain canonical Career Ops text verbatim plus structural connective
  phrasing; every draft runs the install's fact gate and is blocked if it fails.
* A draft is ``draft_unsent``. Nothing is published, sent or scheduled.
* The canonical regional workbooks are read-only unless ``--apply`` is passed
  explicitly, and the acceptance run always writes to a COPY.

Subcommands (each prints exactly one JSON object on stdout)
    intake   --inbox DIR [--record FILE]
    dedupe   --region R [--inbox DIR] [--record FILE]
    draft    [--inbox DIR] [--stamp S] [--region R]
             [--id ID | --url URL | --row N | --pipeline-index N | --job-record REC.json]
    guard    --action NAME
    handoff  --region R [--inbox DIR] [--apply] [--tracker COPY]
    status

``draft`` produces an unsent profile draft, unsent posts and three unsent
outreach drafts (networking, recruiter, and — only when a job context resolves —
hiring manager). Passing no job flag simply omits the hiring-manager draft; no
role or employer is ever guessed.

Usage
    python career-ops/linkedin_workflow.py intake --inbox career-ops/tests/fixtures/linkedin
    python career-ops/linkedin_workflow.py dedupe --region uk --inbox career-ops/tests/fixtures/linkedin
    python career-ops/linkedin_workflow.py draft --job-record REC.json
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
DEFAULT_CONFIG = CAREER_OPS_DIR / "linkedin_workflow.json"

sys.path.insert(0, str(CAREER_OPS_DIR))

import tracker_writer as tw  # noqa: E402
import cv_workflow as cvw  # noqa: E402

COMPANY_WATCH_DIR = CONTROL_PLANE / "company-watch"
if str(COMPANY_WATCH_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANY_WATCH_DIR))

import company_watch as cw  # noqa: E402
import company_registry as creg  # noqa: E402

LINKEDIN_PROVENANCE_PREFIX = "LINKEDIN"
LINK_RE = re.compile(r"\[([^\]\n]{1,240})\]\((https?://[^)\s]+)\)")
BARE_URL_RE = re.compile(r"https?://[^\s)\]<>\"']+")
NAME_SPLIT_RE = re.compile(r"\s+[—–]\s+|\s+-\s+")

# Every line a draft body may contain that is NOT verbatim canonical source text.
# These are structural connective phrasings only: they introduce canonical text,
# they never assert anything about the owner. The list is exported so the tests
# assert against the same definition instead of a copy of it.
STRUCTURAL_PHRASES = (
    # profile / post framings
    "Notes from a recent project:",
    "Certifications on record:",
    "Where I am right now:",
    "Tools I have been working in:",
    # shared salutation / sign-off
    "Hello,",
    "Thank you for your time.",
    # networking (peer / alumni / community) outreach
    "I would be glad to connect and hear how you came to work in this area. If you have a "
    "moment, I would value your view on entering cyber security or IT support in the UK at "
    "my stage.",
    # recruiter / agency outreach
    "I am looking for a first role in cyber security or IT support in the UK, and I would be "
    "glad to be considered for anything on your books that suits a graduate at my stage.",
    "I am happy to share my CV on request.",
    # hiring-manager outreach
    "I would be glad to know whether this team is likely to suit a graduate at my stage, and "
    "what would make an application stand out.",
    # the original generic outreach phrasing, kept for continuity
    "I am looking for a first role in cyber security or IT support in the UK. "
    "If you have a moment, I would be glad to know whether anything on your team "
    "is likely to suit a graduate at that stage.",
)

emit = cvw.emit
sha256_file = cvw.sha256_file
now_utc = cvw.now_utc
read_text = cvw.read_text


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #

def load_config(path: str | Path | None = None) -> dict:
    p = Path(path or DEFAULT_CONFIG)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["_config_path"] = str(p)
    return cfg


def cw_config(cfg: dict) -> dict:
    return cw.load_config(CONTROL_PLANE / cfg["company_watch_config"])


def cv_config(cfg: dict) -> dict:
    """The CV workflow's own config: canonical source paths + fact-gate settings."""
    return cvw.load_config(CAREER_OPS_DIR / "cv_workflow_config.json")


def inbox_dir(cfg: dict) -> Path:
    return CONTROL_PLANE / cfg["inbox_dir"]


def runtime_dir(cfg: dict) -> Path:
    d = CONTROL_PLANE / cfg["runtime_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# read-only intake
# --------------------------------------------------------------------------- #

def _normalize_raw(item: dict, *, path: Path, file_sha: str, index: int,
                   line: int | None = None) -> dict:
    def pick(*names):
        for n in names:
            v = item.get(n)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    return {
        "company": pick("company", "employer", "organisation", "organization", "name"),
        "title": pick("title", "role", "position", "job_title"),
        "location": pick("location", "place", "geo"),
        "url": pick("url", "link", "job_url", "posting_url"),
        "posted_at": pick("posted_at", "posted", "date", "posted_date"),
        "kind_hint": pick("kind", "signal_kind", "type"),
        "source": pick("source") or "linkedin-inbox",
        "source_detail": pick("source_detail", "note", "notes", "detail"),
        "provenance": {
            "file": str(path),
            "file_sha256": file_sha,
            "index": index,
            **({"line": line} if line is not None else {}),
        },
    }


def parse_json_signals(text: str, *, path: Path) -> list[dict]:
    doc = json.loads(text)
    if isinstance(doc, dict):
        for key in ("signals", "items", "jobs", "results"):
            if isinstance(doc.get(key), list):
                doc = doc[key]
                break
        else:
            doc = [doc]
    if not isinstance(doc, list):
        raise ValueError("JSON signal file must be an array or an object with a signals/items array")
    return [d for d in doc if isinstance(d, dict)]


def parse_jsonl_signals(text: str) -> list[dict]:
    out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        out.append(json.loads(raw))
    return out


def parse_csv_signals(text: str) -> list[dict]:
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def parse_text_signals(text: str) -> tuple[list[dict], list[dict]]:
    """Best-effort parse of an exported alert file.

    A line is a job signal only when it actually carries a URL. A line without a
    URL is returned as ``unclassified`` rather than being guessed into a company
    or a posting.
    """
    found: list[dict] = []
    unclassified: list[dict] = []
    for no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        link = LINK_RE.search(line)
        if link:
            label, url = link.group(1).strip(), link.group(2).strip()
            parts = [p.strip() for p in NAME_SPLIT_RE.split(label) if p.strip()]
            if len(parts) >= 2:
                title, company = parts[0], parts[1]
            else:
                title, company = label, None
            found.append({"title": title, "company": company, "url": url,
                          "_line": no, "_raw": line})
            continue
        bare = BARE_URL_RE.search(line)
        if bare:
            url = bare.group(0).strip()
            label = (line[:bare.start()] + line[bare.end():]).strip(" -|—\t")
            label = re.sub(r"^\[|\]$", "", label)
            parts = [p.strip() for p in NAME_SPLIT_RE.split(label) if p.strip()]
            title = parts[0] if parts else None
            company = parts[1] if len(parts) >= 2 else None
            found.append({"title": title, "company": company, "url": url,
                          "_line": no, "_raw": line})
            continue
        unclassified.append({"reason": "line carries no URL; not guessed into a signal",
                             "_line": no, "_raw": line[:300]})
    return found, unclassified


def parse_inbox_file(path: Path, cfg: dict) -> dict:
    """Parse one inbox file. Never fetches, never follows, never mutates."""
    ext = path.suffix.lower()
    supported = [e.lower() for e in cfg.get("supported_inbox_extensions", [])]
    if supported and ext not in supported:
        return {"path": str(path), "sha256": None, "signals": [], "unclassified": [],
                "skipped": f"unsupported extension {ext or '(none)'}"}
    text = read_text(path)
    file_sha = sha256_file(path)
    raw_items: list[dict] = []
    unclassified: list[dict] = []
    if ext == ".json":
        raw_items = parse_json_signals(text, path=path)
    elif ext == ".jsonl":
        raw_items = parse_jsonl_signals(text)
    elif ext == ".csv":
        raw_items = parse_csv_signals(text)
    else:
        raw_items, unclassified = parse_text_signals(text)
    signals = [_normalize_raw(item, path=path, file_sha=file_sha, index=i,
                              line=item.get("_line"))
               for i, item in enumerate(raw_items)]
    for u in unclassified:
        u["provenance"] = {"file": str(path), "file_sha256": file_sha, "line": u.get("_line")}
    return {"path": str(path), "sha256": file_sha, "signals": signals,
            "unclassified": unclassified, "skipped": None}


def classify(signal: dict) -> dict:
    """Classify a normalised signal. Unknowns stay unknown."""
    url = signal.get("url")
    company = signal.get("company")
    title = signal.get("title")
    hint = (signal.get("kind_hint") or "").casefold()
    if url and (title or company):
        kind = "job_signal"
    elif company:
        kind = "company_signal"
    else:
        kind = "unclassified"
    if hint in ("company", "company_signal") and kind == "job_signal":
        # A company follow that happens to carry a URL is still a company signal.
        kind = "company_signal"
    return {**signal, "signal_kind": kind,
            "classification_basis": ("posting URL + company/title" if kind == "job_signal"
                                     else "company name without a posting URL"
                                     if kind == "company_signal"
                                     else "neither a URL nor a company name")}


def collect_signals(cfg: dict, inbox: Path) -> dict:
    if not inbox.exists():
        return {"ok": False, "reason": f"inbox not found: {inbox}", "files": [], "signals": [],
                "counts": {}}
    files = sorted(p for p in inbox.iterdir() if p.is_file())
    parsed = [parse_inbox_file(p, cfg) for p in files]
    signals, unclassified = [], []
    for doc in parsed:
        for s in doc["signals"]:
            signals.append(classify(s))
        for u in doc["unclassified"]:
            unclassified.append({**u, "signal_kind": "unclassified"})
    counts = {
        "files": len(files),
        "signals": len(signals),
        "job_signals": sum(1 for s in signals if s["signal_kind"] == "job_signal"),
        "company_signals": sum(1 for s in signals if s["signal_kind"] == "company_signal"),
        "unclassified": len(unclassified),
    }
    return {
        "ok": True,
        "generated_at": now_utc(),
        "inbox": str(inbox),
        "files": [{"path": d["path"], "sha256": d["sha256"], "signals": len(d["signals"]),
                   "unclassified": len(d["unclassified"]), "skipped": d["skipped"]}
                  for d in parsed],
        "counts": counts,
        "signals": signals,
        "unclassified": unclassified,
        "read_only_contract": {
            "network_used": False,
            "urls_fetched": 0,
            "browser_launched": False,
            "linkedin_authenticated": False,
            "account_mutations": 0,
            "note": "Signals are parsed from owner-provided local files. Every URL is treated "
                    "as an opaque string; nothing is requested or opened.",
        },
    }


# --------------------------------------------------------------------------- #
# dedupe: Career Ops (shared writer rules) + Company Watch
# --------------------------------------------------------------------------- #

def company_watch_reference(cfg: dict) -> dict:
    """Company-level and posting-level Company Watch state, read-only."""
    cc = cw_config(cfg)
    out = {"registry_available": False, "registry_companies": 0,
           "name_keys": [], "variant_keys": [], "handoff_url_keys": [], "handoff_files": [],
           "detail": {}}
    try:
        registry = cw.load_registry(cc)
        names, variants = [], set()
        for company in registry.get("companies", []):
            name = company.get("name")
            if not name:
                continue
            names.append(name)
            variants.add(creg.normalize_name(name))
            for variant in creg.name_variants(name):
                variants.add(creg.normalize_name(variant))
        out.update({"registry_available": True, "registry_companies": len(names),
                    "name_keys": sorted({creg.normalize_name(n) for n in names if n}),
                    "variant_keys": sorted(v for v in variants if v),
                    "detail": {"registry_source_sha256": (registry.get("source") or {}).get("sha256")}})
    except Exception as exc:  # noqa: BLE001 - registry is owner-private and may be absent
        out["detail"]["registry_error"] = f"{type(exc).__name__}: {exc}"

    runtime = CONTROL_PLANE / cc["runtime_dir"]
    handoff_keys: set[str] = set()
    handoff_files = []
    if runtime.exists():
        for path in sorted(runtime.glob("handoff-*.json")):
            try:
                doc = json.loads(read_text(path))
            except json.JSONDecodeError:
                continue
            n = 0
            for rec in doc.get("records", []):
                key = tw.normalize_url(rec.get("url"))
                if key:
                    handoff_keys.add(key)
                    n += 1
            handoff_files.append({"path": str(path), "records": n})
    out["handoff_url_keys"] = sorted(handoff_keys)
    out["handoff_files"] = handoff_files
    return out


def dedupe_signals(cfg: dict, region: str, signals: list[dict],
                   *, tracker_override: str | None = None,
                   extra_archive_dirs: list[str] | None = None) -> dict:
    """Dedupe LinkedIn job/company signals against Career Ops + Company Watch."""
    cc = cw_config(cfg)
    tw_mod, profiles, region_cfg = cw.resolve_region_config(cc, region)
    shared = cw.build_shared_dedupe(cc, region, tracker_override=tracker_override,
                                    extra_archive_dirs=extra_archive_dirs)
    reference = company_watch_reference(cfg)
    variant_keys = set(reference["variant_keys"])
    handoff_keys = set(reference["handoff_url_keys"])
    canonical_companies = shared["canonical_companies"]
    filters = cw.load_owner_filters(cc, region)

    decisions, company_signals = [], []
    by_url: dict[str, dict] = {}
    for signal in signals:
        if signal["signal_kind"] == "company_signal":
            key = creg.normalize_name(signal.get("company"))
            in_cw = bool(key) and key in variant_keys
            in_tracker = bool(key) and any(key == creg.normalize_name(c)
                                           for c in canonical_companies if c)
            company_signals.append({
                "company": signal.get("company"),
                "provenance": signal.get("provenance"),
                "known_to_company_watch": in_cw,
                "already_in_career_ops_workbook": in_tracker,
                "decision": "duplicate" if (in_cw or in_tracker) else "new-company-signal",
                "reason": ("company already watched/tracked — review signal only, no tracker row"
                           if (in_cw or in_tracker) else
                           "company not present in Career Ops or Company Watch"),
            })
            continue
        if signal["signal_kind"] != "job_signal":
            continue

        finding = {"company": signal.get("company"), "title": signal.get("title"),
                   "location": signal.get("location"), "url": signal.get("url")}
        decision, reason = cw.dedupe_decision(finding, shared, tw_mod)
        url_key = tw_mod.normalize_url(signal.get("url"))
        cw_url_hit = bool(url_key) and url_key in handoff_keys
        if decision == "new" and cw_url_hit:
            decision, reason = "duplicate-company-watch", \
                "already handed to Career Ops by Company Watch"

        company_key = creg.normalize_name(signal.get("company"))
        cw_company_hit = bool(company_key) and company_key in variant_keys
        route = cw.route_region(signal.get("location"), cc, filters, region)
        eligible, why = owner_filter_decision(signal, filters, region, route)

        # Same-batch duplicates: one posting re-shared with a tracking parameter
        # (or repeated across two exports) is ONE posting. Rather than dropping
        # the later — usually less detailed — copy, its extra detail is merged
        # into the kept record and eligibility is recomputed, so a rich copy
        # arriving second is not lost behind a bare first copy.
        first = by_url.get(url_key) if url_key else None
        if first is not None:
            if first["decision"] == "new":
                for field in ("company", "title", "location", "posted_at"):
                    if not first.get(field) and signal.get(field):
                        first[field] = signal.get(field)
                first["merged_signals"] = first.get("merged_signals", 0) + 1
                first.setdefault("merged_provenance", []).append(signal.get("provenance"))
                re_route = cw.route_region(first.get("location"), cc, filters, region)
                re_elig, re_why = owner_filter_decision(first, filters, region, re_route)
                first["region_route"] = re_route
                first["owner_filter_eligible"] = re_elig
                first["owner_filter_reasons"] = re_why
                first["url"] = first.get("url") or tw_mod.extract_url(signal.get("url"))
            else:
                decisions.append({
                    "company": signal.get("company"), "title": signal.get("title"),
                    "location": signal.get("location"), "posted_at": signal.get("posted_at"),
                    "url": tw_mod.extract_url(signal.get("url")),
                    "source_kind": signal.get("source"),
                    "provenance": signal.get("provenance"),
                    "decision": "duplicate-in-batch",
                    "reason": "same posting already present earlier in this LinkedIn intake batch",
                    "region_route": route,
                    "owner_filter_eligible": eligible,
                    "owner_filter_reasons": why,
                    "company_known_to_company_watch": cw_company_hit,
                    "already_handed_off_by_company_watch": cw_url_hit,
                })
            continue

        entry = {
            "company": signal.get("company"),
            "title": signal.get("title"),
            "location": signal.get("location"),
            "posted_at": signal.get("posted_at"),
            "url": tw_mod.extract_url(signal.get("url")),
            "source_kind": signal.get("source"),
            "provenance": signal.get("provenance"),
            "decision": decision,
            "reason": reason,
            "region_route": route,
            "owner_filter_eligible": eligible,
            "owner_filter_reasons": why,
            "company_known_to_company_watch": cw_company_hit,
            "already_handed_off_by_company_watch": cw_url_hit,
        }
        if url_key:
            by_url[url_key] = entry
        decisions.append(entry)

    return {
        "region": region,
        "tracker": shared["tracker"],
        "tracker_sha256": shared["tracker_sha256"],
        "canonical_url_keys": len(shared["canonical_url_keys"]),
        "canonical_pair_keys": len(shared["canonical_pair_keys"]),
        "cross_month_keys": len(shared["cross_month_keys"]),
        "cross_month_sources": shared["cross_month_sources"],
        "company_watch": {k: v for k, v in reference.items()
                          if k in ("registry_available", "registry_companies",
                                   "handoff_files", "detail")},
        "company_watch_registry_companies": reference["registry_companies"],
        "company_watch_handoff_url_keys": len(reference["handoff_url_keys"]),
        "dedupe_engine": "company_watch.build_shared_dedupe + career-ops/tracker_writer.py",
        "owner_filters_available": bool(filters.get("available")),
        "owner_filters_source": filters.get("path"),
        "counts": {
            "job_signals": len(decisions),
            "company_signals": len(company_signals),
            "new": sum(1 for d in decisions if d["decision"] == "new"),
            "duplicates": sum(1 for d in decisions if d["decision"].startswith("duplicate")),
            "blocked_by_owner_filter": sum(1 for d in decisions
                                           if d["decision"] == "new" and not d["owner_filter_eligible"]),
        },
        "job_decisions": decisions,
        "company_decisions": company_signals,
    }


def owner_filter_decision(signal: dict, filters: dict, region: str,
                          route: str | None) -> tuple[bool, list[str]]:
    """Apply the owner's own configured filters; unknown stays ineligible."""
    reasons: list[str] = []
    if not filters.get("available"):
        return False, ["no owner filter config for this region; refusing to judge eligibility"]
    location = signal.get("location") or ""
    allow = list(filters.get("location_always_allow") or []) + list(filters.get("location_allow") or [])
    if not cw.any_term_in_text(allow, location):
        reasons.append(f"location '{location or 'not stated'}' not in the owner's allow list")
    if filters.get("location_block") and cw.any_term_in_text(filters["location_block"], location):
        reasons.append("location matches the owner's block list")
    title = signal.get("title") or ""
    if filters.get("title_negative") and cw.any_term_in_text(filters["title_negative"], title):
        reasons.append("title matches the owner's negative title filter")
    positives = list(filters.get("title_positive") or [])
    if positives and not cw.any_term_in_text(positives, title):
        reasons.append("title has no positive match in the owner's title filter")
    if route is None:
        reasons.append("location does not route to the requested region")
    elif route != region:
        reasons.append(f"location routes to region '{route}', not '{region}'")
    max_age = filters.get("max_posting_age_days")
    if max_age:
        age = cw.parse_age_days(signal.get("posted_at"), dt.datetime.now(dt.timezone.utc))
        if age is None:
            reasons.append("posting date not stated, so the owner's freshness rule cannot be met")
        elif age > float(max_age):
            reasons.append(f"posting is {age} days old (owner limit {max_age})")
    return (not reasons), reasons


# --------------------------------------------------------------------------- #
# handoff into Career Ops
# --------------------------------------------------------------------------- #

def build_handoff_manifest(cfg: dict, region: str, dedupe: dict, *,
                           include_ineligible_as_test: bool = False,
                           limit: int = 0) -> dict:
    cc = cw_config(cfg)
    tw_mod, profiles, region_cfg = cw.resolve_region_config(cc, region)
    targets = cw.provenance_targets(region_cfg)
    if not targets["provenance"]:
        return {"ok": False, "region": region,
                "reason": f"region '{region}' has no non-owner provenance column; refusing to "
                          "hand off without provenance",
                "records": []}
    selected = []
    for d in dedupe.get("job_decisions", []):
        if d.get("decision") != "new":
            continue
        if d.get("region_route") != region:
            continue
        if d.get("owner_filter_eligible") is True:
            selected.append((d, False))
        elif include_ineligible_as_test:
            selected.append((d, True))
    if limit:
        selected = selected[:limit]

    records = []
    for d, is_test in selected:
        marker = (f"{LINKEDIN_PROVENANCE_PREFIX} TEST ROW — " if is_test
                  else f"{LINKEDIN_PROVENANCE_PREFIX} — ")
        prov = d.get("provenance") or {}
        provenance = (
            f"{marker}read-only LinkedIn signal intake ('{d.get('source_kind')}') from "
            f"{Path(str(prov.get('file'))).name} (sha256 {str(prov.get('file_sha256'))[:12]}); "
            f"posting date {d.get('posted_at') or 'not stated'}; "
            f"deduped {d['decision']} against the canonical {region} workbook, the cross-month "
            f"ledger and Company Watch; NOT human-verified, NOT live-verified — review before "
            f"shortlisting"
        ) + ("; acceptance-test row written to a workbook copy only" if is_test else "")
        record = {
            "company": d.get("company"),
            "title": d.get("title"),
            "location": d.get("location"),
            "url": d.get("url"),
            targets["provenance"]: provenance,
        }
        if targets["posted_date"] and d.get("posted_at"):
            record[targets["posted_date"]] = str(d["posted_at"])[:10]
        if targets["last_checked"]:
            record[targets["last_checked"]] = dt.date.today().isoformat()
        records.append(record)

    return {"ok": True, "region": region, "provenance_column": targets["provenance"],
            "provenance_targets": targets,
            "counts": {"selected": len(selected),
                       "included_as_test_rows": sum(1 for _d, t in selected if t)},
            "records": records,
            "application_state_written": False,
            "note": "A manifest carries no application status; the writer ignores any such field."}


def handoff(cfg: dict, region: str, manifest: dict, *, tracker: str | None = None,
            apply: bool = False, backup_dir: str | None = None,
            manifest_path: str | None = None) -> dict:
    """Invoke the existing Career Ops handoff invoker (dry-run unless ``apply``).

    The manifest is written inside the *LinkedIn* runtime directory, never in
    Company Watch's. Company Watch reads its own handoff manifests as
    "already handed off", so letting a LinkedIn run write there would make
    LinkedIn's own signals look like Company Watch duplicates on the next pass.
    """
    cc = cw_config(cfg)
    if manifest_path is None:
        d = runtime_dir(cfg) / "handoffs"
        d.mkdir(parents=True, exist_ok=True)
        path: str = str(d / (f"linkedin-handoff-{region}-"
                             f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.json"))
    else:
        path = str(manifest_path)
    return cw.handoff_to_career_ops(cc, region, manifest, tracker=tracker, apply=apply,
                                    backup_dir=backup_dir, manifest_path=path)


# --------------------------------------------------------------------------- #
# action guard (owner gate)
# --------------------------------------------------------------------------- #

def guard_action(cfg: dict, action: str) -> dict:
    action_key = (action or "").strip().casefold()
    blocked = {a.casefold() for a in cfg.get("blocked_actions", [])}
    allowed = action_key not in blocked
    result = {
        "action": action,
        "allowed": allowed,
        "owner_gated": not allowed,
        "performed": False,
        "reason": ("external LinkedIn action is owner-gated; this workflow implements no path "
                   "that performs it" if not allowed else
                   "action is not an external LinkedIn mutation (read/draft only)"),
        "policy": cfg.get("external_action_policy"),
        "available_paths": ["intake (read-only)", "dedupe (read-only)", "draft (unsent)",
                            "handoff (dry-run unless --apply)"],
    }
    log = runtime_dir(cfg) / "action-gate-log.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_utc(), **result}) + "\n")
    result["logged_to"] = str(log)
    return result


# --------------------------------------------------------------------------- #
# drafts
# --------------------------------------------------------------------------- #

def canonical_blocks(cfg: dict) -> dict:
    """Canonical Career Ops text used to build drafts, with source line numbers."""
    root = Path(cv_config(cfg)["career_ops_root"])
    cv_text = read_text(root / "cv.md")
    sections = cvw.parse_cv_markdown(cv_text)
    out: dict = {"cv_text": cv_text, "sections": []}
    for section in sections:
        out["sections"].append({
            "heading": section["heading"],
            "level": section["level"],
            "lines": [{"no": l["no"], "kind": l["kind"], "text": l["text"]}
                      for l in section["lines"] if l["text"]],
        })
    out["facts"] = cvw.profile_facts(cv_config(cfg))
    profile_text = read_text(root / "config" / "profile.yml")
    out["profile_text"] = profile_text
    headline = ""
    for line in profile_text.splitlines():
        if line.strip().startswith("headline:"):
            headline = line.split(":", 1)[1].strip().strip('"\'')
            break
    out["headline"] = headline
    return out


def section_named(blocks: dict, *names: str) -> dict | None:
    wanted = {n.casefold() for n in names}
    for section in blocks["sections"]:
        if (section["heading"] or "").casefold() in wanted:
            return section
    return None


def _source(line: dict, section: str) -> dict:
    return {"source": "cv.md", "line": line["no"], "section": section, "text": line["text"]}


OUTREACH_VARIANTS = ("networking", "recruiter", "hiring_manager")


def build_outreach_drafts(cfg: dict, blocks: dict, *, job: dict | None = None) -> list[dict]:
    """Networking / recruiter / hiring-manager outreach DRAFTS.

    Every variant is ``draft_unsent``: no recipient is chosen, no connection
    request is created, no message is queued and nothing is scheduled. The only
    prose this function contributes is structural connective phrasing from
    ``STRUCTURAL_PHRASES``; everything substantive is a canonical CV line quoted
    verbatim with its source line. The hiring-manager variant is only produced
    when a job context is supplied, and the job reference it carries is
    attributed to the Career Ops record it came from.
    """
    facts = blocks["facts"]
    profile_section = section_named(blocks, "Profile")
    cert_section = section_named(blocks, "Certifications")
    intro_lines = [l for l in (profile_section["lines"] if profile_section else []) if l["text"]]
    cert_lines = [l for l in (cert_section["lines"] if cert_section else []) if l["text"]]
    intro = intro_lines[0] if intro_lines else None
    name = facts.get("full_name", "")
    voice = cfg.get("voice_sources", [])

    def salutation_and_intro() -> tuple[list[str], list[dict]]:
        body = ["Hello,", ""]
        sources: list[dict] = []
        if intro:
            body.append(intro["text"])
            body.append("")
            sources.append(_source(intro, "Profile"))
        return body, sources

    drafts: list[dict] = []

    # 1. networking — peer / alumni / community contact ----------------------- #
    body, sources = salutation_and_intro()
    body += [
        "I would be glad to connect and hear how you came to work in this area. If you have a "
        "moment, I would value your view on entering cyber security or IT support in the UK at "
        "my stage.",
        "", "Thank you for your time.", "", name,
    ]
    drafts.append({
        "kind": "outreach",
        "subtype": "networking",
        "status": "draft_unsent",
        "sent": False,
        "recipient": None,
        "recipient_kind": "networking contact (peer, alumni or community). No recipient is chosen.",
        "channel": "LinkedIn message or connection note (owner-sent only)",
        "body": "\n".join(body).strip(),
        "sources": sources,
        "voice_sources": voice,
        "notes": ["No recipient is chosen, no connection request is generated and nothing is sent.",
                  "The introduction paragraph is the canonical Profile line verbatim; the rest is "
                  "structural phrasing that makes no claim about experience."],
        "publish_requires": "explicit owner authorization",
    })

    # 2. recruiter / agency outreach ------------------------------------------ #
    body, sources = salutation_and_intro()
    body += [
        "I am looking for a first role in cyber security or IT support in the UK, and I would be "
        "glad to be considered for anything on your books that suits a graduate at my stage.",
    ]
    if cert_lines and cert_lines[0]["text"]:
        body += ["", "Certifications on record:", cert_lines[0]["text"]]
        sources.append(_source(cert_lines[0], "Certifications"))
    body += ["", "I am happy to share my CV on request.",
             "", "Thank you for your time.", "", name]
    drafts.append({
        "kind": "outreach",
        "subtype": "recruiter",
        "status": "draft_unsent",
        "sent": False,
        "recipient": None,
        "recipient_kind": "recruiter or agency contact. No recipient is chosen.",
        "channel": "LinkedIn message (owner-sent only)",
        "body": "\n".join(body).strip(),
        "sources": sources,
        "voice_sources": voice,
        "notes": ["Nothing is sent, queued or scheduled, and no CV is attached or transmitted.",
                  "Certification text is the canonical Certifications line verbatim."],
        "publish_requires": "explicit owner authorization",
    })

    # 3. hiring manager — only with a job context ----------------------------- #
    if job:
        title = (job.get("title") or "").strip()
        company = (job.get("company") or "").strip()
        if title and company:
            opening = f"I am writing about the {title} role at {company}."
        elif title:
            opening = f"I am writing about the {title} role."
        else:
            opening = "I am writing about a role your team has advertised."
        body, sources = salutation_and_intro()
        body += [
            opening,
            "I would be glad to know whether this team is likely to suit a graduate at my stage, "
            "and what would make an application stand out.",
            "", "Thank you for your time.", "", name,
        ]
        drafts.append({
            "kind": "outreach",
            "subtype": "hiring_manager",
            "status": "draft_unsent",
            "sent": False,
            "recipient": None,
            "recipient_kind": "hiring manager for the referenced posting. No recipient is chosen.",
            "channel": "LinkedIn message (owner-sent only)",
            "body": "\n".join(body).strip(),
            "sources": sources,
            "references_job": {
                "id": job.get("id"), "title": title or None, "company": company or None,
                "location": job.get("location"), "region": job.get("_region"),
                "source_kind": job.get("_source_kind"), "source_path": job.get("_source_path"),
                "provenance": "job context read from the Career Ops record above; the role and "
                              "employer names are the record's own values, not inferred",
            },
            "voice_sources": voice,
            "notes": ["No recipient is chosen, nothing is sent and no connection request is created.",
                      "The role/employer reference comes from the Career Ops job record and is "
                      "recorded in references_job so it can be checked."],
            "publish_requires": "explicit owner authorization",
        })
    return drafts


def _attach_provenance_and_unsent_state(cfg: dict, drafts: list[dict]) -> list[dict]:
    """Give every draft a provenance block and an explicit unsent state."""
    cv_paths = cvw.source_paths(cv_config(cfg))
    canon = {}
    for key in ("cv_md", "profile", "cv_facts"):
        path = cv_paths[key]
        canon[str(path)] = sha256_file(path) if Path(path).exists() else None
    for draft in drafts:
        draft["provenance"] = {
            "generator": "career-ops/linkedin_workflow.py",
            "generated_at": now_utc(),
            "canonical_sources": canon,
            "source_lines": [f"cv.md:{s['line']}" for s in draft.get("sources", [])],
            "rule": "substantive text is canonical source text verbatim; only structural "
                    "connective phrasing is generated",
        }
        draft["unsent_state"] = {
            "status": draft["status"],
            "sent": False,
            "sent_at": None,
            "recipient_selected": False,
            "recipient": None,
            "channel": draft.get("channel"),
            "connection_request_created": False,
            "message_queued": False,
            "scheduled": False,
            "attachments_sent": 0,
            "owner_approval_required": True,
            "note": "Nothing has been sent, queued, scheduled or connected. This is a draft only; "
                    "the owner sends it manually or not at all.",
        }
    return drafts


def build_linkedin_drafts(cfg: dict, *, out_dir: Path, scratch: Path,
                          job: dict | None = None) -> dict:
    """Profile / post / outreach drafts from canonical facts, fact-gated."""
    blocks = canonical_blocks(cfg)
    max_per_kind = int(cfg.get("max_drafts_per_kind", 4))

    profile_section = section_named(blocks, "Profile")
    skills_section = section_named(blocks, "Technical Skills")
    cert_section = section_named(blocks, "Certifications")
    project_sections = [s for s in blocks["sections"]
                        if (s["heading"] or "").casefold().startswith(
                            ("safepaste", "inboxdefender", "attacksurfaceiq"))]

    drafts: list[dict] = []

    # --- profile --------------------------------------------------------- #
    about_parts, about_sources = [], []
    if profile_section:
        for line in profile_section["lines"]:
            about_parts.append(line["text"])
            about_sources.append(_source(line, "Profile"))
    if skills_section:
        for line in skills_section["lines"]:
            about_parts.append(line["text"])
            about_sources.append(_source(line, "Technical Skills"))
    drafts.append({
        "kind": "profile",
        "status": "draft_unsent",
        "applies_to": "LinkedIn headline and About section",
        "headline": blocks["headline"],
        "headline_source": "config/profile.yml narrative.headline (verbatim)",
        "about": "\n".join(about_parts),
        "sources": about_sources,
        "voice_sources": cfg.get("voice_sources", []),
        "notes": ["About text is canonical CV text verbatim; add nothing that the canonical "
                  "sources do not state.",
                  "Update the live profile only in the owner's own browser session — this "
                  "workflow never signs in."],
        "publish_requires": "explicit owner authorization",
    })

    # --- posts ----------------------------------------------------------- #
    post_framings = [
        ("project evidence", "Notes from a recent project:"),
        ("certification", "Certifications on record:"),
        ("current study", "Where I am right now:"),
        ("tools in practice", "Tools I have been working in:"),
    ]
    post_specs = []
    if project_sections:
        first = project_sections[0]
        lines = [l for l in first["lines"] if l["kind"] == "bullet"] or first["lines"][:1]
        post_specs.append((post_framings[0], lines, first["heading"]))
    if cert_section:
        post_specs.append((post_framings[1], cert_section["lines"], None))
    if profile_section:
        post_specs.append((post_framings[2], profile_section["lines"], None))
    if skills_section:
        post_specs.append((post_framings[3], skills_section["lines"], None))

    for (label, framing), lines, heading in post_specs[:max_per_kind]:
        body_lines = [framing]
        sources = []
        if heading:
            body_lines.append("")
            body_lines.append(heading)
        for line in lines:
            body_lines.append("")
            body_lines.append(line["text"])
            sources.append(_source(line, heading or label))
        drafts.append({
            "kind": "post",
            "topic": label,
            "status": "draft_unsent",
            "body": "\n".join(body_lines).strip(),
            "sources": sources,
            "voice_sources": cfg.get("voice_sources", []),
            "notes": ["Framing line is structural; every substantive sentence is verbatim "
                      "canonical text with its source line.",
                      "Add the owner's own reflection before publishing if desired — but do not "
                      "add claims about experience, metrics or outcomes."],
            "publish_requires": "explicit owner authorization",
        })

    # --- outreach (networking / recruiter / hiring manager) --------------- #
    drafts.extend(build_outreach_drafts(cfg, blocks, job=job))

    drafts = drafts[:2 + max_per_kind + 3]
    drafts = _attach_provenance_and_unsent_state(cfg, drafts)

    # ---- fact gate over every draft ------------------------------------- #
    combined = "\n\n".join(d.get("body") or d.get("about") or "" for d in drafts)
    combined += "\n" + " ".join(d.get("headline") or "" for d in drafts)
    gate = cvw.fact_gate(cv_config(cfg), combined, label="linkedin-drafts", scratch=scratch)
    gate_ok = not (gate.get("available") and gate.get("verdict") == "block")
    for draft in drafts:
        draft["fact_gate"] = gate
        draft["blocked"] = not gate_ok
        if not gate_ok:
            draft["status"] = "blocked_fact_gate"
            draft["unsent_state"]["status"] = draft["status"]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "linkedin_drafts.json").write_text(
        json.dumps({"generated_at": now_utc(), "fact_gate": gate, "drafts": drafts},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    md = ["# LinkedIn drafts (unsent)", "",
          f"Generated: {now_utc()}",
          f"Fact gate: {gate.get('verdict') if gate.get('available') else 'unavailable'}",
          "", "Nothing here has been posted, sent or scheduled.", ""]
    for draft in drafts:
        label = draft["kind"] + (f" / {draft['subtype']}" if draft.get("subtype") else "")
        label += (f" — {draft.get('topic')}" if draft.get("topic") else "")
        md += [f"## {label}", "", draft.get("body") or draft.get("about") or "", ""]
        if draft.get("headline"):
            md += [f"Headline: {draft['headline']}", ""]
        if draft.get("references_job"):
            ref = draft["references_job"]
            md += [f"References job: {ref.get('title')} @ {ref.get('company')} "
                   f"(Career Ops record {ref.get('id')})", ""]
        md += ["Sources: " + ", ".join(f"cv.md:{s['line']}" for s in draft.get("sources", [])), ""]
    (out_dir / "linkedin_drafts.md").write_text("\n".join(md), encoding="utf-8")

    return {
        "ok": gate_ok,
        "status": "drafts_ready_for_owner_review" if gate_ok else "blocked_fact_gate",
        "counts": {"total": len(drafts),
                   "profile": sum(1 for d in drafts if d["kind"] == "profile"),
                   "post": sum(1 for d in drafts if d["kind"] == "post"),
                   "outreach": sum(1 for d in drafts if d["kind"] == "outreach"),
                   "outreach_networking": sum(1 for d in drafts
                                              if d.get("subtype") == "networking"),
                   "outreach_recruiter": sum(1 for d in drafts
                                             if d.get("subtype") == "recruiter"),
                   "outreach_hiring_manager": sum(1 for d in drafts
                                                  if d.get("subtype") == "hiring_manager")},
        "fact_gate": gate,
        "job_context": ({k: v for k, v in job.items() if not k.startswith("_")} if job else None),
        "drafts_path": str(out_dir / "linkedin_drafts.json"),
        "drafts_markdown": str(out_dir / "linkedin_drafts.md"),
        "drafts": drafts,
        "sends_performed": 0,
        "posts_performed": 0,
        "messages_queued": 0,
        "connection_requests_created": 0,
    }


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def _collect(args, cfg) -> dict:
    inbox = Path(args.inbox) if args.inbox else inbox_dir(cfg)
    doc = collect_signals(cfg, inbox)
    if args.record:
        p = Path(args.record)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        doc["recorded_to"] = str(p)
    return doc


def cmd_intake(args) -> int:
    cfg = load_config(args.config)
    doc = _collect(args, cfg)
    emit(doc)
    return 0 if doc.get("ok") else 1


def cmd_dedupe(args) -> int:
    cfg = load_config(args.config)
    doc = _collect(args, cfg)
    if not doc.get("ok"):
        emit(doc)
        return 1
    dedupe = dedupe_signals(cfg, args.region, doc["signals"],
                            tracker_override=args.tracker,
                            extra_archive_dirs=args.archive_dir)
    out = {
        "ok": True,
        "generated_at": now_utc(),
        "inbox": doc["inbox"],
        "intake_counts": doc["counts"],
        "read_only_contract": doc["read_only_contract"],
        "dedupe": dedupe,
        "canonical_tracker_untouched": True,
        "writes_performed": [],
        "external_actions_taken": [],
    }
    if args.record:
        p = Path(args.record)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        out["recorded_to"] = str(p)
    emit(out)
    return 0


def draft_job_context(cfg: dict, args) -> tuple[dict | None, dict]:
    """Resolve the optional Career Ops job context for the outreach drafts.

    Returns ``(job, status)``. A resolution failure is reported truthfully and
    simply omits the hiring-manager draft — no role or employer is ever guessed.
    """
    wanted = {"job_record": getattr(args, "job_record", None),
              "id": getattr(args, "id", None), "url": getattr(args, "url", None),
              "row": getattr(args, "row", None),
              "pipeline_index": getattr(args, "pipeline_index", None)}
    if not any(v is not None for v in wanted.values()):
        return None, {"requested": False,
                      "reason": "no job context requested; the hiring-manager outreach draft "
                                "is omitted rather than invented"}
    region = getattr(args, "region", None) or "uk"
    cc = cw_config(cfg)
    cv_cfg = cvw.load_config(CONTROL_PLANE / cc["cv_workflow_config"]) \
        if "cv_workflow_config" in cc else cv_config(cfg)
    profiles = tw.load_profiles(str(CONTROL_PLANE / cv_cfg["regional_profiles"]))
    resolved = cvw.resolve_job(cv_cfg, profiles, region=region, job_id=wanted["id"],
                               url=wanted["url"], row=wanted["row"],
                               pipeline_index=wanted["pipeline_index"],
                               record_file=wanted["job_record"])
    if not resolved.get("ok"):
        return None, {"requested": True, "resolved": False, "region": region,
                      "reason": resolved.get("reason"),
                      "note": "no job context available, so no role or employer is named in any "
                              "draft"}
    return resolved["job"], {"requested": True, "resolved": True, "region": region,
                             "source_kind": (resolved["job"] or {}).get("_source_kind"),
                             "source_path": (resolved["job"] or {}).get("_source_path")}


def cmd_draft(args) -> int:
    cfg = load_config(args.config)
    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path(args.out) if args.out else (runtime_dir(cfg) / cfg["drafts_subdir"] / stamp)
    job, job_status = draft_job_context(cfg, args)
    result = build_linkedin_drafts(cfg, out_dir=base, scratch=base / "factgate", job=job)
    emit({"ok": result["ok"], "generated_at": now_utc(), **result,
          "job_context_status": job_status,
          "external_actions_taken": []})
    return 0 if result["ok"] else 1


def cmd_guard(args) -> int:
    cfg = load_config(args.config)
    emit({"ok": True, **guard_action(cfg, args.action)})
    return 0


def cmd_handoff(args) -> int:
    cfg = load_config(args.config)
    doc = _collect(args, cfg)
    if not doc.get("ok"):
        emit(doc)
        return 1
    dedupe = dedupe_signals(cfg, args.region, doc["signals"],
                            tracker_override=args.tracker,
                            extra_archive_dirs=args.archive_dir)
    manifest = build_handoff_manifest(cfg, args.region, dedupe,
                                      include_ineligible_as_test=args.include_ineligible_as_test,
                                      limit=args.limit)
    if not manifest.get("ok"):
        emit(manifest)
        return 1
    result = handoff(cfg, args.region, manifest, tracker=args.tracker, apply=args.apply,
                     backup_dir=args.backup_dir, manifest_path=args.manifest)
    emit({
        "ok": True,
        "generated_at": now_utc(),
        "region": args.region,
        "mode": "apply" if args.apply else "dry-run",
        "intake_counts": doc["counts"],
        "dedupe_counts": dedupe["counts"],
        "manifest_counts": manifest["counts"],
        "provenance_column": manifest["provenance_column"],
        "handoff": result,
        "application_state_written": False,
        "external_actions_taken": [],
        "read_only_contract": doc["read_only_contract"],
    })
    return 0


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    cc = cw_config(cfg)
    root = Path(cc["career_ops_root"])
    runtime = runtime_dir(cfg)
    drafts_root = runtime / cfg["drafts_subdir"]
    runs = sorted(drafts_root.glob("*/linkedin_drafts.json")) if drafts_root.exists() else []
    log = runtime / "action-gate-log.jsonl"
    refusals = 0
    if log.exists():
        for line in read_text(log).splitlines():
            try:
                if json.loads(line).get("owner_gated"):
                    refusals += 1
            except json.JSONDecodeError:
                continue
    emit({
        "ok": True,
        "generated_at": now_utc(),
        "config": cfg["_config_path"],
        "career_ops_root": str(root),
        "career_ops_root_exists": root.exists(),
        "inbox": str(inbox_dir(cfg)),
        "inbox_exists": inbox_dir(cfg).exists(),
        "runtime_dir": str(runtime),
        "draft_runs": len(runs),
        "latest_draft_run": str(runs[-1]) if runs else None,
        "action_gate_refusals_logged": refusals,
        "blocked_actions": cfg["blocked_actions"],
        "external_action_policy": cfg["external_action_policy"],
        "not_performed": cfg["not_performed"],
    })
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Minimal LinkedIn workflow (read-only intake + drafts)")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("intake")
    p.add_argument("--inbox"); p.add_argument("--record")
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("dedupe")
    p.add_argument("--region", required=True)
    p.add_argument("--inbox"); p.add_argument("--record")
    p.add_argument("--tracker"); p.add_argument("--archive-dir", action="append")
    p.set_defaults(fn=cmd_dedupe)

    p = sub.add_parser("draft")
    p.add_argument("--inbox"); p.add_argument("--out"); p.add_argument("--stamp")
    p.add_argument("--region", default=None)
    p.add_argument("--id"); p.add_argument("--url"); p.add_argument("--row", type=int)
    p.add_argument("--pipeline-index", type=int); p.add_argument("--job-record")
    p.set_defaults(fn=cmd_draft)

    p = sub.add_parser("guard")
    p.add_argument("--action", required=True)
    p.set_defaults(fn=cmd_guard)

    p = sub.add_parser("handoff")
    p.add_argument("--region", required=True)
    p.add_argument("--inbox"); p.add_argument("--record"); p.add_argument("--tracker")
    p.add_argument("--archive-dir", action="append"); p.add_argument("--backup-dir")
    p.add_argument("--manifest")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--include-ineligible-as-test", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_handoff)

    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
