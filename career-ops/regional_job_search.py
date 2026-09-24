#!/usr/bin/env python3
"""Shared regional job-search worker for UK / Dubai / Japan / Singapore.

One implementation, four regions. Every region goes through the same path:

    lane readiness -> bounded Career Ops scan (dry-run) -> candidate records
      -> shared eligibility/policy filter -> shared dedupe -> run-health +
      idempotency state -> optional manifest for the deterministic tracker writer

Design rules (the integration contract):

* **No fabricated jobs.** A record only ever comes from a Career Ops lane scan,
  a lane pipeline entry, or an explicitly supplied manifest. Nothing is invented
  to make a run look productive.
* **Dry-run by default, always for schedules.** A run never writes a canonical
  workbook and never submits anything. The scheduled entry points pass
  ``--scheduled``, which refuses any non-dry scan.
* **Owner facts are read, never assumed.** Title policy and the UK location
  scope come from the owner's own Career Ops ``portals.yml``; work-authorisation
  facts come from ``config/profile.yml``. A region where the owner has stated
  nothing is marked ``UNKNOWN`` (see ``regional_policy.json``).
* **Shared dedupe.** Cross-region/company/job dedupe, the workbook index and the
  cross-month ledger index all come from ``tracker_writer.py`` — the same code
  the UK lane uses. Nothing is re-implemented per region.
* **Idempotent.** Each run is keyed by a hash of its accepted candidate set; a
  replayed run reports ``duplicate-prior-run`` instead of new rows, and the
  tracker writer independently refuses duplicates against the workbook and the
  cross-month ledgers.

Subcommands
-----------
  policy      [--region R]                     resolved region policy + provenance
  lanes                                        lane readiness for every region
  eligibility --region R (--manifest F | --scan-record F | --records F)
                                               per-record decisions (no writes)
  run         --region R [--record DIR] [--manifest-out F] [--records F]
              [--scan-record F] [--timeout N] [--scheduled] [--fake-scan F]
                                               one deterministic regional run
  run-all     [--record DIR] [--timeout N] [--scheduled]
                                               all four regions, staggered order
  status                                       run-health + state for every region

Safety: no subcommand applies to a workbook. Tracker writes stay an explicit
``career_ops_cli.py write --apply`` step with its own backup and verification.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent
sys.path.insert(0, str(HERE))

import career_ops_cli as cli  # noqa: E402
import tracker_writer as tw  # noqa: E402

SCHEDULES_PATH = HERE / "regional_schedules.json"
POLICY_PATH = HERE / "regional_policy.json"

REGION_ORDER = ("uk", "dubai", "japan", "singapore")

# "  + Company | Title | Location [Trust: 85/100 — flag, flag] [BLACKLISTED — ...]"
SCAN_OFFER_RE = re.compile(
    r"^\s*\+\s+(?P<company>.*?)\s*\|\s*(?P<title>.*?)\s*\|\s*(?P<loc>.*?)\s*$"
)
TRUST_SUFFIX_RE = re.compile(r"\s*\[Trust:\s*(?P<score>\d+)/100(?:\s*[—-]\s*(?P<flags>[^\]]*))?\]\s*$")
BLACKLIST_SUFFIX_RE = re.compile(r"\s*\[BLACKLISTED[^\]]*\]\s*$")

# "  - [ ] https://... | Company | Title | Location | ... " (Career Ops pipeline.md)
PIPELINE_ENTRY_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s*(?P<url>https?://\S+)\s*(?:\|(?P<rest>.*))?$")


# --------------------------------------------------------------------------- #
# io helpers
# --------------------------------------------------------------------------- #

def emit(obj) -> None:
    """Print exactly one JSON object; ASCII-escape if the console code page cannot."""
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = json.dumps(obj, indent=2, ensure_ascii=True, default=str)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_schedules(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or SCHEDULES_PATH).read_text(encoding="utf-8"))


def load_policy(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or POLICY_PATH).read_text(encoding="utf-8"))


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# policy / owner facts
# --------------------------------------------------------------------------- #

def owner_title_filter(profiles: dict) -> dict:
    """The owner's own title filter, read live from the Career Ops install.

    This is the source of truth for ``regional_policy.json#title_policy`` and for
    every lane's ``title_filter``; the test suite fails if they drift.
    """
    import yaml  # local import so --help works even without PyYAML
    portals = Path(profiles["career_ops_root"]) / "portals.yml"
    if not portals.exists():
        return {}
    cfg = yaml.safe_load(portals.read_text(encoding="utf-8")) or {}
    return cfg.get("title_filter") or {}


def owner_location_filter(profiles: dict) -> dict:
    import yaml
    portals = Path(profiles["career_ops_root"]) / "portals.yml"
    if not portals.exists():
        return {}
    cfg = yaml.safe_load(portals.read_text(encoding="utf-8")) or {}
    return cfg.get("location_filter") or {}


def lane_scope(region: str, schedule: dict) -> dict:
    """Location scope actually configured in the region's lane portals.yml."""
    env = (schedule.get("career_ops_env") or {})
    raw = env.get("CAREER_OPS_PORTALS")
    if not raw:
        return {}
    path = Path(raw)
    if not path.is_absolute():
        path = Path(load_schedules()["career_ops_root"]) / raw
    if not path.exists():
        return {}
    import yaml
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return cfg.get("location_filter") or {}


def region_policy(region: str, policy: dict | None = None) -> dict:
    policy = policy or load_policy()
    if region not in policy["regions"]:
        raise KeyError(f"unknown region '{region}'; known: {sorted(policy['regions'])}")
    return policy["regions"][region]


# --------------------------------------------------------------------------- #
# location and title policy (mirrors scan.mjs semantics, kept in one place)
# --------------------------------------------------------------------------- #

def _compile_location_keyword(keyword: str):
    escaped = re.escape(keyword)
    starts_word = bool(re.match(r"[a-z0-9]", keyword[:1] or ""))
    ends_word = bool(re.match(r"[a-z0-9]", keyword[-1:] or ""))
    prefix = r"(?<![a-z0-9])" if starts_word else ""
    suffix = r"(?![a-z0-9])" if ends_word else ""
    rx = re.compile(prefix + escaped + suffix)
    return lambda lower: bool(rx.search(lower))


REMOTE_TITLE_RE = re.compile(r"(?<![a-z])remote(?=$|\s*[^a-z\s]|\s+in\b)")
REMOTE_NEGATED_RE = re.compile(r"\b(?:non|not|no)[^a-z]*remote")


def title_signals_remote(title) -> bool:
    if not isinstance(title, str) or not title.strip():
        return False
    lower = title.lower()
    if REMOTE_NEGATED_RE.search(lower):
        return False
    return bool(REMOTE_TITLE_RE.search(lower))


def location_hint_from_url(url) -> str:
    """Same narrow recovery scan.mjs does: only the path segment after /job/."""
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        from urllib.parse import unquote, urlsplit
        segments = [s for s in urlsplit(url).path.split("/") if s]
    except ValueError:
        return ""
    if "job" not in segments:
        return ""
    idx = len(segments) - 1 - segments[::-1].index("job")
    if idx == len(segments) - 1:
        return ""
    segment = segments[idx + 1]
    try:
        segment = unquote(segment)
    except Exception:
        pass
    return re.sub(r"\s+", " ", segment.replace("-", " ").replace("_", " ").replace("+", " ")).strip().lower()


def location_matches(scope: dict, location, title, url,
                     require_explicit_region: bool = False) -> tuple[bool, str]:
    """Mirror of scan.mjs ``buildLocationFilter`` (order of tiers matters).

    ``require_explicit_region`` is the regional-worker's stricter mode: a
    non-UK region's tracker is country-scoped, so a posting must actually name
    the region. Two scan.mjs leniencies are therefore disabled there —

      * the "no location data → pass" rule, and
      * the "title says Remote → rescue" rule,

    because measured on 2026-09-24 those let ``Personalized Internet Assessor -
    Remote`` / ``USA`` and ``Anywhere in India`` through the Dubai and Japan
    lanes. A bare remote posting is not evidence of the region.
    """
    if not scope:
        return True, "no location scope configured"
    always = [_compile_location_keyword(k.lower()) for k in _as_list(scope.get("always_allow"))]
    allow = [_compile_location_keyword(k.lower()) for k in _as_list(scope.get("allow"))]
    block = [_compile_location_keyword(k.lower()) for k in _as_list(scope.get("block"))]
    block_hard = [_compile_location_keyword(k.lower()) for k in _as_list(scope.get("block_hard"))]

    lower = location.strip().lower() if isinstance(location, str) else ""
    hint = location_hint_from_url(url)
    if lower == "" and hint == "":
        if require_explicit_region:
            return False, ("no location data — the region is not evidenced, and a non-UK region tracker "
                           "requires an explicit region match")
        return True, "no location data (not penalised)"

    def matches(m):
        return (lower != "" and m(lower)) or (hint != "" and m(hint))

    if block_hard and any(matches(m) for m in block_hard):
        return False, f"block_hard match in '{location or hint}'"
    if always and any(matches(m) for m in always):
        return True, f"always_allow match in '{location or hint}'"
    if block and any(matches(m) for m in block):
        return False, f"blocked location '{location or hint}'"
    if not allow:
        return True, "no allow list"
    if any(matches(m) for m in allow):
        return True, f"allow match in '{location or hint}'"
    if require_explicit_region:
        return False, (f"location '{location or hint}' does not name the region; a bare 'remote' "
                       "posting is not region-eligible without an explicit location")
    if title_signals_remote(title):
        return True, "title marks the role remote (rescued by the allow list)"
    return False, f"location '{location or ''}' outside the region scope"


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, (str, int, float))]
    return [str(value)]


def location_scope_comparable(scope: dict) -> dict:
    """Strip provenance metadata so a scope can be compared with the owner's file."""
    if not scope:
        return {}
    keys = ("always_allow", "allow", "block", "block_hard")
    return {k: scope[k] for k in keys if k in scope}


def title_decision(title: str, title_policy: dict) -> tuple[bool, str]:
    """Mirror of the owner's positive/negative title policy (positive = required)."""
    lower = (title or "").lower()
    for kw in _as_list(title_policy.get("negative")):
        if kw.lower() in lower:
            return False, f"title policy excludes '{kw.strip()}'"
    positives = _as_list(title_policy.get("positive"))
    if positives and not any(kw.lower() in lower for kw in positives):
        return False, f"title matches none of the owner's positive terms {positives}"
    return True, "title passes the owner's title policy"


CLEARANCE_TOKEN_RE = re.compile(
    r"\b(?:SC|DV|CTC|NPPV|UKSV|BPSS)\b|security clearance|national security clearance|"
    r"police clearance|british citizen|british citizenship|indefinite leave to remain|"
    r"indefinite right to work",
    re.IGNORECASE,
)


def clearance_hits(text: str) -> list:
    return sorted({m.group(0).strip().lower() for m in CLEARANCE_TOKEN_RE.finditer(text or "")})


# --------------------------------------------------------------------------- #
# eligibility — the single shared filter all four regions call
# --------------------------------------------------------------------------- #

def evaluate_record(region: str, record: dict, policy: dict, title_policy: dict,
                    scope: dict) -> dict:
    """Decide one candidate record. Never invents an owner fact."""
    rp = region_policy(region, policy)
    reasons: list[str] = []
    flags: list[str] = []

    url = tw.extract_url(record.get("url"))
    if not url or not url.lower().startswith(("http://", "https://")):
        return {
            "decision": "rejected",
            "reasons": ["no usable application URL — a posting without a URL is not writable state"],
            "flags": [],
            "work_authorisation": _work_auth_block(rp),
        }

    ok, why = title_decision(str(record.get("title") or ""), title_policy)
    if not ok:
        reasons.append(why)
    else:
        flags.append(why)

    if not scope:
        # Fail closed: with no resolvable region scope the filter cannot tell a
        # Dubai posting from a London one, so nothing is accepted.
        reasons.append("region location scope unavailable (lane config missing) — refusing to accept "
                       "records that cannot be region-checked")
        return {
            "decision": "rejected",
            "reasons": reasons,
            "flags": flags,
            "work_authorisation": _work_auth_block(rp),
        }

    ok, why = location_matches(scope, record.get("location"), record.get("title"), url,
                               require_explicit_region=(region != "uk"))
    if not ok:
        reasons.append(why)
    else:
        flags.append(why)

    blob = " ".join(str(record.get(k) or "") for k in
                    ("title", "company", "location", "summary", "description"))
    hits = clearance_hits(blob)
    if hits:
        reasons.append(f"clearance/citizenship requirement stated: {', '.join(hits)}")

    exp = record.get("experience_required")
    if isinstance(exp, (int, float)) and exp >= 2:
        reasons.append(f"states {exp} years of required experience; owner targets internships/entry level")
    elif isinstance(exp, str) and re.search(r"\b([2-9]|1[0-9])\+?\s*(?:years|yrs)\b", exp, re.IGNORECASE):
        reasons.append(f"states a multi-year experience requirement ('{exp}')")

    work_auth = _work_auth_block(rp)
    if work_auth["status"] == "UNKNOWN":
        flags.append(
            f"work authorisation for {rp['display_name']} is UNKNOWN — no owner-stated right to work; "
            "visa pathway must be verified by the owner"
        )

    return {
        "decision": "rejected" if reasons else "accepted",
        "reasons": reasons,
        "flags": flags,
        "work_authorisation": work_auth,
    }


def _work_auth_block(rp: dict) -> dict:
    w = rp.get("work_authorisation") or {}
    return {
        "status": w.get("status"),
        "basis": w.get("basis"),
        "current_permission": w.get("current_permission"),
        "sponsorship_now": w.get("sponsorship_now"),
        "tracker_visa_pathway": w.get("tracker_visa_pathway"),
    }


# --------------------------------------------------------------------------- #
# scan output parsing
# --------------------------------------------------------------------------- #

def _int_after(text: str, label: str):
    m = re.search(re.escape(label) + r"\s*([0-9]+)", text or "")
    return int(m.group(1)) if m else None


def parse_scan_offers(stdout: str) -> list:
    """Parse the dry-run 'New offers:' block.

    These lines carry company/title/location but **not** a URL, so they can never
    become tracker rows on their own; they are reported as needing URL resolution.
    """
    offers = []
    in_block = False
    for line in (stdout or "").splitlines():
        if line.strip().startswith("New offers:"):
            in_block = True
            continue
        if not in_block:
            continue
        m = SCAN_OFFER_RE.match(line)
        if not m:
            if line.strip() == "":
                if offers:
                    break
                continue
            break
        rest = m.group("loc")
        trust = None
        flags = []
        bm = BLACKLIST_SUFFIX_RE.search(rest)
        blacklisted = bool(bm)
        if bm:
            rest = rest[: bm.start()].rstrip()
        tm = TRUST_SUFFIX_RE.search(rest)
        if tm:
            trust = int(tm.group("score"))
            flags = [f.strip() for f in (tm.group("flags") or "").split(",") if f.strip()]
            rest = rest[: tm.start()].rstrip()
        offers.append({
            "company": m.group("company").strip(),
            "title": m.group("title").strip(),
            "location": rest.strip(),
            "trust_score": trust,
            "trust_flags": flags,
            "blacklisted": blacklisted,
            "url": None,
        })
    return offers


def parse_scan_counters(stdout: str) -> dict:
    return {
        "jobs_found": _int_after(stdout, "Total jobs found:"),
        "filtered_title": _int_after(stdout, "Filtered by title:"),
        "filtered_location": _int_after(stdout, "Filtered by location:"),
        "filtered_age": _int_after(stdout, "Filtered by age:"),
        "duplicates": _int_after(stdout, "Duplicates:"),
        "new_offers_added": _int_after(stdout, "New offers added:"),
        "errors": _int_after(stdout, "Errors ("),
    }


def parse_pipeline_entries(path: Path) -> list:
    """URL-bearing candidates from a lane's own pipeline inbox."""
    out = []
    if not path or not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = PIPELINE_ENTRY_RE.match(line)
        if not m:
            continue
        rest = [p.strip() for p in (m.group("rest") or "").split("|") if p.strip()]
        out.append({
            "url": m.group("url").strip(),
            "company": rest[0] if len(rest) > 0 else "",
            "title": rest[1] if len(rest) > 1 else "",
            "location": rest[2] if len(rest) > 2 else "",
            "source": f"lane pipeline: {path}",
        })
    return out


# --------------------------------------------------------------------------- #
# idempotency state
# --------------------------------------------------------------------------- #

def state_path(override: str | None = None) -> Path:
    if override:
        return Path(override)
    sched = load_schedules()
    return Path(sched.get("state_file") or (CONTROL_PLANE / "runtime" / "career-ops" / "scan-runs" / "regional-run-state.json"))


def load_state(override: str | None = None) -> dict:
    p = state_path(override)
    if not p.exists():
        return {"schema_version": 1, "updated_at": None, "regions": {}}
    return read_json(p)


def run_key(region: str, accepted: list) -> str:
    urls = sorted({tw.normalize_url(r.get("url")) for r in accepted if tw.normalize_url(r.get("url"))})
    return sha256_text(region + "\n" + "\n".join(urls))[:32]


# --------------------------------------------------------------------------- #
# record building
# --------------------------------------------------------------------------- #

def build_record(region: str, candidate: dict, policy: dict, run_id: str, scan: dict) -> dict:
    rp = region_policy(region, policy)
    cfg = dict(tw.region_config(tw.load_profiles(), region))
    today = dt.date.today().isoformat()
    rec = {
        "company": candidate.get("company") or "",
        "title": candidate.get("title") or "",
        "location": candidate.get("location") or "",
        "url": tw.extract_url(candidate.get("url")),
        "date_found": today,
        "posted_date": candidate.get("posted_date"),
        "salary": candidate.get("salary"),
        "source": f"Career Ops lane scan ({rp['display_name']}) run {run_id}",
    }
    if "last_checked" in cfg.get("field_map", {}):
        rec["last_checked"] = today
    if "visa_pathway" in cfg.get("field_map", {}):
        # The region has a visa-pathway column: an UNKNOWN owner fact is recorded
        # explicitly. Never upgraded to "sponsored" without evidence.
        rec["visa_pathway"] = rp["work_authorisation"].get("tracker_visa_pathway") or "Visa unknown"
    if "why_it_fits" in cfg.get("field_map", {}):
        rec["why_it_fits"] = (
            f"Passed the shared regional eligibility filter for {rp['display_name']} "
            "(owner title policy + region location scope + clearance policy)."
        )
    if "main_gap" in cfg.get("field_map", {}):
        if rp["work_authorisation"]["status"] == "UNKNOWN":
            rec["main_gap"] = (
                f"Work authorisation / visa eligibility for {rp['display_name']} is UNKNOWN — "
                "the owner has stated no right to work there. Requires owner decision before applying."
            )
        else:
            rec["main_gap"] = "Posting sponsorship and live status not re-verified in this run."
    if "key_gap" in cfg.get("field_map", {}):
        rec["key_gap"] = "Live vacancy not re-verified in this run (pre-screen only)."
    if "recommendation" in cfg.get("field_map", {}):
        rec["recommendation"] = (
            f"Discovered by the {rp['display_name']} regional worker (run {run_id}); "
            "pre-screened only — live verification and owner decision outstanding."
        )
    if "discovery" in cfg.get("field_map", {}):
        rec["discovery"] = f"REGIONAL WORKER {region.upper()} {run_id} (pre-screen only)"
    if "live_status" in cfg.get("field_map", {}):
        rec["live_status"] = "Uncertain"
    if "clearance_check" in cfg.get("field_map", {}):
        rec["clearance_check"] = "Pass — no clearance stated"
    if "work_authorisation_risk" in cfg.get("field_map", {}):
        rec["work_authorisation_risk"] = (
            "Owner holds UK work authorisation to 23 Dec 2027; posting sponsorship not verified in this run"
            if rp["work_authorisation"]["status"] == "authorised"
            else f"UNKNOWN — no owner-stated right to work in {rp['display_name']}"
        )
    rec["_scan"] = scan
    return rec


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_policy(args) -> int:
    policy = load_policy(args.policy_file)
    profiles = tw.load_profiles()
    regions = [args.region] if args.region else list(policy["regions"])
    out = {"generated_at": now_utc(), "policy_file": str(POLICY_PATH), "regions": {}}
    for region in regions:
        rp = region_policy(region, policy)
        sch = load_schedules().get("regions", {}).get(region, {})
        out["regions"][region] = {
            "display_name": rp["display_name"],
            "lane_kind": rp.get("lane_kind"),
            "location_scope": rp["location_scope"],
            "work_authorisation": rp["work_authorisation"],
            "provider_coverage": rp.get("provider_coverage"),
            "scheduled_task": sch.get("task_name"),
            "scheduled_time": sch.get("time"),
        }
    out["title_policy"] = policy["title_policy"]
    live_titles = owner_title_filter(profiles)
    out["owner_title_filter_live"] = live_titles
    out["drift"] = {
        "title_policy_matches_owner_file": live_titles == {"positive": policy["title_policy"]["positive"],
                                                           "negative": policy["title_policy"]["negative"]},
        "uk_location_scope_matches_owner_file": location_scope_comparable(owner_location_filter(profiles))
        == location_scope_comparable(policy["regions"]["uk"]["location_scope"]),
    }
    emit(out)
    return 0


def cmd_lanes(args) -> int:
    profiles = tw.load_profiles()
    schedules = load_schedules()
    out = {"generated_at": now_utc(), "career_ops_root": profiles["career_ops_root"], "regions": {}}
    for region, spec in schedules["regions"].items():
        lane = cli.resolve_lane(region, profiles)
        scope = lane_scope(region, spec)
        out["regions"][region] = {
            "task_name": spec["task_name"],
            "time": spec["time"],
            "lane_kind": spec.get("lane_kind"),
            "ready": lane["ready"],
            "missing": lane["missing"],
            "env": lane["env"],
            "location_scope_configured": bool(scope),
            "location_allow": scope.get("allow"),
            "provider_coverage": spec.get("provider_coverage"),
            "mode": "bounded dry-run scan; never writes a tracker, never submits",
        }
    emit(out)
    return 0


def cmd_eligibility(args) -> int:
    policy = load_policy(args.policy_file)
    profiles = tw.load_profiles()
    schedules = load_schedules()
    region = args.region
    records = _candidate_records(args, region, schedules)
    title_policy = owner_title_filter(profiles)
    scope = lane_scope(region, schedules["regions"][region])
    decisions = []
    for rec in records:
        verdict = evaluate_record(region, rec, policy, title_policy, scope)
        decisions.append({**{k: v for k, v in rec.items() if not k.startswith("_")}, **verdict})
    accepted = [d for d in decisions if d["decision"] == "accepted"]
    emit({
        "region": region,
        "display_name": region_policy(region, policy)["display_name"],
        "generated_at": now_utc(),
        "counts": {"input": len(decisions), "accepted": len(accepted),
                   "rejected": len(decisions) - len(accepted)},
        "work_authorisation": _work_auth_block(region_policy(region, policy)),
        "policy_sources": {
            "title_filter": "career-ops-install:portals.yml#title_filter (live)",
            "location_scope": "lane portals.yml location_filter (live)",
            "clearance": "config/profile.yml#location.clearance_filter",
            "work_authorisation": region_policy(region, policy)["work_authorisation"]["basis"],
        },
        "decisions": decisions,
        "writes_performed": False,
    })
    return 0


def load_records_file(path) -> list:
    """Read a records/manifest file: either a bare list or {"records": [...]}."""
    data = read_json(Path(path))
    if isinstance(data, dict):
        return data.get("records", [])
    return data


def _candidate_records(args, region: str, schedules: dict) -> list:
    """Resolve candidate records from the CLI's explicit inputs (no scan)."""
    for attr in ("records", "manifest"):
        value = getattr(args, attr, None)
        if value:
            return load_records_file(value)
    if getattr(args, "scan_record", None):
        return offers_to_candidates(read_json(Path(args.scan_record)))
    lane_pipe = _lane_pipeline_path(region, schedules)
    return parse_pipeline_entries(lane_pipe)


def _lane_pipeline_path(region: str, schedules: dict) -> Path:
    spec = schedules["regions"][region]
    raw = (spec.get("career_ops_env") or {}).get("CAREER_OPS_PIPELINE", "")
    p = Path(raw)
    if not p.is_absolute():
        p = Path(schedules.get("career_ops_root", "")) / raw
    return p


def offers_to_candidates(scan_record: dict) -> list:
    """Scan offers carry no URL — they are candidates-needing-resolution only."""
    offers = scan_record.get("offers") or parse_scan_offers(scan_record.get("stdout_tail") or "")
    out = []
    for o in offers:
        out.append({**o, "needs_url_resolution": o.get("url") is None})
    return out


def _do_scan(region: str, args, schedules: dict) -> dict:
    """Run the bounded Career Ops scan through career_ops_cli and capture its JSON."""
    ns = argparse.Namespace(region=region, company=None, timeout=args.timeout,
                           record=args.record, force=False, profiles=None)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_scan(ns)
    try:
        record = json.loads(buf.getvalue())
    except json.JSONDecodeError:
        record = {"region": region, "ok": False, "exit_code": rc,
                  "reason": "scan wrapper produced no parseable JSON",
                  "raw_stdout": buf.getvalue()[:2000]}
    record["wrapper_exit_code"] = rc
    return record


def cmd_run(args) -> int:
    policy = load_policy(args.policy_file)
    profiles = tw.load_profiles()
    schedules = load_schedules()
    region = args.region
    if region not in schedules["regions"]:
        emit({"ok": False, "region": region, "reason": "unknown region"})
        return 2
    spec = schedules["regions"][region]
    run_id = f"{region}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    lane = cli.resolve_lane(region, profiles)
    out = {
        "run_id": run_id,
        "region": region,
        "display_name": region_policy(region, policy)["display_name"],
        "started_at": now_utc(),
        "dry_run": True,
        "applications_submitted": 0,
        "employer_contacts": 0,
        "canonical_workbook_written": False,
        "lane_kind": spec.get("lane_kind"),
        "lane_ready": lane["ready"],
        "lane_missing": lane["missing"],
        "scheduled": bool(args.scheduled),
    }

    # 1. bounded scan ------------------------------------------------------- #
    if args.fake_scan:
        scan = read_json(Path(args.fake_scan))
    elif args.scan_record:
        scan = read_json(Path(args.scan_record))
    elif lane["ready"]:
        scan = _do_scan(region, args, schedules)
    else:
        scan = {"region": region, "ok": False, "refused": True,
                "reason": "regional lane config missing", "missing": lane["missing"]}
    out["scan"] = {
        "ok": scan.get("ok"),
        "refused": bool(scan.get("refused")),
        "exit_code": scan.get("exit_code"),
        "duration_s": scan.get("duration_s"),
        "dry_run": scan.get("dry_run", True),
        "stdout_capture_ok": scan.get("stdout_capture_ok"),
        "command": scan.get("command"),
        "lane_env": scan.get("lane_env"),
        "recorded_to": scan.get("recorded_to"),
        "warning": scan.get("warning"),
        "counters": parse_scan_counters(scan.get("stdout_tail") or ""),
        "stdout_tail": (scan.get("stdout_tail") or "")[-2000:],
        "stderr_tail": (scan.get("stderr_tail") or "")[-1000:],
    }

    # 2. candidates --------------------------------------------------------- #
    offers = parse_scan_offers(scan.get("stdout_tail") or "") if scan.get("stdout_tail") else []
    if args.records:
        candidates = load_records_file(args.records)
    else:
        candidates = parse_pipeline_entries(_lane_pipeline_path(region, schedules))
    out["candidates"] = {
        "scan_offers_without_url": len(offers),
        "url_bearing_candidates": len(candidates),
        "source": str(args.records) if args.records else str(_lane_pipeline_path(region, schedules)),
        "note": ("scan offers carry no posting URL, so they are reported for URL resolution and can never "
                 "become tracker rows on their own; only URL-bearing candidates can be accepted"),
    }

    # 3. eligibility -------------------------------------------------------- #
    title_policy = owner_title_filter(profiles)
    scope = lane_scope(region, spec)
    decisions = []
    for rec in candidates:
        verdict = evaluate_record(region, rec, policy, title_policy, scope)
        decisions.append({**{k: v for k, v in rec.items() if not k.startswith("_")}, **verdict})
    accepted = [d for d in decisions if d["decision"] == "accepted"]
    pre_replay_accepted = len(accepted)

    # 4. idempotency -------------------------------------------------------- #
    state = load_state(args.state_file)
    key = run_key(region, accepted)
    prev = (state.get("regions", {}).get(region) or {})
    replay = bool(prev.get("last_run_key")) and prev.get("last_run_key") == key and key != ""
    out["idempotency"] = {
        "run_key": key,
        "previous_run_key": prev.get("last_run_key"),
        "replay_of_previous_run": replay,
        "state_file": str(state_path(args.state_file)),
        "note": ("a replayed run marks every accepted candidate duplicate-prior-run; the shared tracker dedupe "
                 "independently refuses anything already in the workbook or a cross-month ledger"),
    }
    if replay:
        for d in decisions:
            if d["decision"] == "accepted":
                d["decision"] = "duplicate-prior-run"
                d["reason"] = "identical accepted candidate set already processed in a previous run"
        accepted = []

    out["eligibility"] = {
        "input": len(decisions),
        "accepted": len(accepted),
        "accepted_before_idempotency": pre_replay_accepted,
        "rejected": sum(1 for d in decisions if d["decision"] == "rejected"),
        "duplicate_prior_run": sum(1 for d in decisions if d["decision"] == "duplicate-prior-run"),
        "rejected_sample": [{"company": d["company"], "title": d["title"], "reasons": d["reasons"]}
                            for d in decisions if d["decision"] == "rejected"][:10],
    }

    # 5. dedupe probe through the shared writer (never applies) ------------- #
    records = [build_record(region, d, policy, run_id, out["scan"]["counters"]) for d in accepted]
    probe = tw.write_records(profiles, region, records, apply=False)
    out["dedupe"] = {
        "engine": "career-ops/tracker_writer.py (shared with the UK lane)",
        "tracker": probe["tracker"],
        "counts": probe["counts"],
        "cross_month_index": probe["cross_month_index"],
        "outcomes": probe["outcomes"][:20],
        "applied": False,
    }

    new_rows = [o for o in probe["outcomes"] if o["decision"] == "appended"]
    out["would_append"] = len(new_rows)
    out["manifest_written_to"] = None
    if args.manifest_out:
        plan_records = []
        by_key = {tw.normalize_url(r["url"]): r for r in records}
        for o in new_rows:
            rec = by_key.get(tw.normalize_url(o["url"]))
            if rec:
                plan_records.append(rec)
        manifest = {
            "schema_version": 1,
            "generated_at": now_utc(),
            "region": region,
            "run_id": run_id,
            "provenance": {
                "worker": "career-ops/regional_job_search.py",
                "lane": spec.get("career_ops_env", {}).get("CAREER_OPS_PORTALS"),
                "scan_dry_run": out["scan"]["dry_run"],
                "eligibility": "shared regional filter (regional_policy.json)",
                "dedupe": "tracker_writer.build_cross_month_index + workbook index",
            },
            "counts": {"candidates": len(candidates), "accepted": len(records),
                       "would_append": len(plan_records)},
            "records": plan_records,
        }
        Path(args.manifest_out).parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(Path(args.manifest_out), manifest)
        out["manifest_written_to"] = str(args.manifest_out)

    # 6. run-health + state ------------------------------------------------- #
    out["finished_at"] = now_utc()
    out["work_authorisation"] = _work_auth_block(region_policy(region, policy))
    out["status"] = ("ok" if out["scan"]["ok"] and not out["scan"]["refused"] else
                     "refused" if out["scan"]["refused"] else "scan-failed")
    out["writes"] = {"canonical_workbook": False, "tracker_dry_run_only": True,
                     "run_health_files": True, "state_file": str(state_path(args.state_file))}

    record_dir = Path(args.record) if args.record else (CONTROL_PLANE / "runtime" / "career-ops" / "scan-runs")
    record_dir.mkdir(parents=True, exist_ok=True)
    health_file = record_dir / f"regional-run-{run_id}.json"
    write_json_atomic(health_file, out)
    out["run_health_file"] = str(health_file)

    state.setdefault("regions", {})[region] = {
        "last_run_id": run_id,
        "last_run_key": key,
        "last_run_at": out["finished_at"],
        "last_status": out["status"],
        "last_candidates": len(candidates),
        "last_accepted": len(records),
        "last_would_append": len(new_rows),
        "runs": int(prev.get("runs") or 0) + 1,
    }
    state["schema_version"] = 1
    state["updated_at"] = out["finished_at"]
    write_json_atomic(state_path(args.state_file), state)

    emit(out)
    return 0 if out["status"] == "ok" else 1


def cmd_run_all(args) -> int:
    results = {}
    rc = 0
    for region in REGION_ORDER:
        ns = argparse.Namespace(**vars(args))
        ns.region = region
        buf = io.StringIO()
        with redirect_stdout(buf):
            r = cmd_run(ns)
        try:
            results[region] = json.loads(buf.getvalue())
        except json.JSONDecodeError:
            results[region] = {"status": "error", "raw": buf.getvalue()[:500]}
        rc = rc or r
    emit({
        "generated_at": now_utc(),
        "mode": "run-all",
        "regions": {r: {"status": v.get("status"), "run_key": (v.get("idempotency") or {}).get("run_key"),
                        "would_append": v.get("would_append"),
                        "run_health_file": v.get("run_health_file"),
                        "work_authorisation": (v.get("work_authorisation") or {}).get("status")}
                    for r, v in results.items()},
    })
    return rc


def cmd_status(args) -> int:
    state = load_state(args.state_file)
    schedules = load_schedules()
    profiles = tw.load_profiles()
    regions = {}
    for region, spec in schedules["regions"].items():
        lane = cli.resolve_lane(region, profiles)
        st = (state.get("regions") or {}).get(region, {})
        runs = sorted((CONTROL_PLANE / "runtime" / "career-ops" / "scan-runs").glob(f"regional-run-{region}-*.json"))
        regions[region] = {
            "task_name": spec["task_name"],
            "scheduled_time": spec["time"],
            "lane_ready": lane["ready"],
            "mode": "bounded dry-run scan; never writes a tracker, never submits",
            "last_run_id": st.get("last_run_id"),
            "last_run_at": st.get("last_run_at"),
            "last_status": st.get("last_status"),
            "last_accepted": st.get("last_accepted"),
            "last_would_append": st.get("last_would_append"),
            "runs_recorded": int(st.get("runs") or 0),
            "run_health_files": [p.name for p in runs[-3:]],
            "work_authorisation": region_policy(region)["work_authorisation"]["status"],
        }
    emit({"generated_at": now_utc(), "state_file": str(state_path(args.state_file)),
          "regions": regions})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Shared regional job-search worker (UK / Dubai / Japan / Singapore)")
    ap.add_argument("--policy-file")
    ap.add_argument("--state-file")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("policy"); p.add_argument("--region"); p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("lanes"); p.set_defaults(fn=cmd_lanes)

    p = sub.add_parser("eligibility")
    p.add_argument("--region", required=True)
    p.add_argument("--records"); p.add_argument("--manifest"); p.add_argument("--scan-record")
    p.set_defaults(fn=cmd_eligibility)

    p = sub.add_parser("run")
    p.add_argument("--region", required=True)
    p.add_argument("--record")
    p.add_argument("--manifest-out")
    p.add_argument("--records", help="explicit candidate records file (bypasses the lane pipeline)")
    p.add_argument("--scan-record", help="reuse an existing scan run-health JSON instead of scanning")
    p.add_argument("--fake-scan", help="alias of --scan-record for offline replay")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--scheduled", action="store_true",
                   help="scheduled-mode flag: dry-run only, no lane mutation, no tracker write")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("run-all")
    p.add_argument("--record"); p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--records"); p.add_argument("--scan-record"); p.add_argument("--fake-scan")
    p.add_argument("--manifest-out"); p.add_argument("--scheduled", action="store_true")
    p.set_defaults(fn=cmd_run_all)

    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
