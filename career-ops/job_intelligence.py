#!/usr/bin/env python3
"""Job intelligence: JobBrief (B13 JD analyzer) + company/role research brief (B14).

Design rules encoded here (they are the point of the module, not comments):

  * EXTRACTIVE ONLY. Every requirement, responsibility, keyword and eligibility
    condition is a *verbatim line of the posting text* carrying its 1-based
    source line number and the section it came from. Nothing is summarised,
    merged, reworded, ranked by a model, or invented.
  * PREFERENCES ARE NOT FACTS. A line the posting marks desirable/preferred is
    recorded as kind='desirable' and mirrored into ``preferences`` with an
    explicit note. It is never promoted to an essential requirement and never
    turned into a statement about the candidate.
  * NO CANDIDATE CLAIMS. The brief carries ``candidate_claims: []`` and a
    first-person-claim scanner that fails the build if one ever appears.
    Candidate truth lives only in the canonical Career Ops sources.
  * NO RESEARCH GUESSES. Company/role facts are accepted *only* from an approved
    research provider and *only* with a citation. With no provider available the
    brief records ``research.status = "research_needed"`` and the exact list of
    what it wanted. The interactive-browser provider is recorded as disabled by
    the owner's GUI-safety directive and is never launched.
  * HANDOFF IS EXPLICIT. ``source_supported_facts`` is the only part of the
    brief handed to the CV / cover-letter workflows; a caller that wants
    something else has to add it deliberately.

CLI
  python career-ops/job_intelligence.py schema
  python career-ops/job_intelligence.py brief --jd-file JD.txt [--record REC.json]
                                       [--region uk --id ID | --url URL | --row N
                                        | --pipeline-index N] [--research-file F]
                                       [--out DIR] [--stamp S]
  python career-ops/job_intelligence.py research --brief BRIEF.json [--research-file F]
  python career-ops/job_intelligence.py validate --brief BRIEF.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import cv_workflow as cvw  # noqa: E402
import tracker_writer as tw  # noqa: E402

CONFIG_PATH = CAREER_OPS_DIR / "job_intelligence_config.json"
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{1,}")
BULLET_RE = re.compile(r"^\s*(?:[-*\u2022\u2013\u2014]|\d+[.)])\s+(.*)$")
# Labelled lines that describe the POSTING (where/when/how the role is done),
# not something the applicant must evidence. They are routed to the location or
# eligibility buckets so they can never appear as an applicant requirement.
LOCATION_LINE_RE = re.compile(
    r"^\s*(location|locations|based in|based at|office|work model|working pattern|"
    r"working hours|hybrid|remote|on-?site|contract|duration|salary|compensation|"
    r"start date|reporting to)\b", re.I)

# First-person / candidate-side claim patterns. The JobBrief must never contain
# one: these are exactly the phrasings that would turn a posting requirement
# into a claim about Mukund.
CANDIDATE_CLAIM_PATTERNS = (
    r"\bI have\b", r"\bI am\b", r"\bI've\b", r"\bmy experience\b", r"\bmy skills\b",
    r"\bI led\b", r"\bI built\b", r"\bI managed\b", r"\byears of my\b",
)


def emit(obj) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    path = Path(path)
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    cfg = json.loads(read_text(p))
    cfg["_config_path"] = str(p)
    return cfg


def load_workflow_config(cfg: dict) -> dict:
    return cvw.load_config(CONTROL_PLANE / cfg["cv_workflow_config"])


def profiles_path(cfg: dict) -> Path:
    return CONTROL_PLANE / cfg["regional_profiles"]


def runtime_dir(cfg: dict) -> Path:
    return CONTROL_PLANE / cfg["runtime_dir"]


def schema_path(cfg: dict) -> Path:
    return CONTROL_PLANE / cfg["brief_schema"]


# --------------------------------------------------------------------------- #
# owner-side canonical evidence (used ONLY to classify posted conditions)
# --------------------------------------------------------------------------- #

def owner_sources(cfg: dict) -> dict:
    """Read the canonical owner sources. Read-only; never modified, never copied."""
    wf = load_workflow_config(cfg)
    paths = cvw.source_paths(wf)
    profile_text = read_text(paths["profile"])
    cv_text = read_text(paths["cv_md"])
    out: dict = {
        "profile_path": str(paths["profile"]),
        "profile_sha256": sha256_text(profile_text),
        "cv_path": str(paths["cv_md"]),
        "cv_sha256": sha256_text(cv_text),
        "authorized_in": [],
        "authorized_in_lines": [],
        "full_name": None,
        "education_lines": [],
    }
    try:
        import yaml  # noqa: PLC0415
        doc = yaml.safe_load(profile_text) or {}
        loc = doc.get("location") or {}
        authorized = loc.get("authorized_in") or []
        out["authorized_in"] = [str(a) for a in authorized]
        for no, raw in enumerate(profile_text.splitlines(), start=1):
            if re.match(r"^\s*authorized_in\s*:", raw):
                out["authorized_in_lines"].append(no)
        cand = doc.get("candidate") or {}
        name = cand.get("full_name")
        if isinstance(name, str) and name.strip():
            out["full_name"] = name.strip()
    except ImportError:  # pragma: no cover - PyYAML is present in this environment
        out["profile_parse"] = "PyYAML unavailable"
    in_edu = False
    for no, raw in enumerate(cv_text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            heading = re.sub(r"^#+\s*", "", stripped)
            in_edu = heading.casefold().startswith("education")
            if in_edu:
                out["education_lines"].append({"line": no, "text": heading})
            continue
        if in_edu and stripped:
            out["education_lines"].append(
                {"line": no, "text": re.sub(r"^#+\s*", "", stripped)})
    return out


# --------------------------------------------------------------------------- #
# deterministic posting extraction
# --------------------------------------------------------------------------- #

def _normalise_line(raw: str) -> str:
    m = BULLET_RE.match(raw)
    return (m.group(1) if m else raw).strip()


def _heading_candidate(stripped: str) -> str | None:
    """A heading is a short line with no sentence-ending punctuation, or '**x**'."""
    s = stripped.strip()
    if s.startswith("**") and s.endswith("**") and len(s) > 4:
        return s.strip("*").strip()
    if s.endswith(":") and len(s) <= 60 and s.count(" ") <= 7:
        return s.rstrip(":").strip()
    if len(s) <= 60 and s.count(" ") <= 7 and not s.endswith(".") and not s.endswith(","):
        # bare title-case-ish line, e.g. "Essential requirements"
        letters = re.sub(r"[^A-Za-z ]", "", s)
        if letters and (s.istitle() or s.isupper() or s[0].isupper()):
            return s
    return None


def classify_section(heading: str, rules: list[dict]) -> str | None:
    text = (heading or "").casefold().strip(" :*")
    if not text:
        return None
    for rule in rules:
        if re.search(rule["pattern"], text):
            return rule["kind"]
    return None


def extract_items(jd_text: str, rules_doc: dict) -> dict:
    """Split posting text into provenance-carrying items. Pure function."""
    rules = rules_doc["section_rules"]
    inline_desirable = [m.casefold() for m in rules_doc["inline_desirable_markers"]]
    elig_markers = [m.casefold() for m in rules_doc["eligibility_markers"]]

    items = {"responsibilities": [], "requirements": [], "eligibility": [],
             "benefits": [], "about_company": [], "location": [], "other": []}
    current_kind: str | None = None
    current_label: str | None = None

    for no, raw in enumerate(jd_text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        heading = _heading_candidate(stripped) if not BULLET_RE.match(raw) else None
        if heading:
            kind = classify_section(heading, rules)
            if kind:
                current_kind = kind
                current_label = heading
                continue
        text = _normalise_line(raw)
        if not text:
            continue
        entry = {"text": text, "source_line": no, "source_section": current_label}
        low = text.casefold()

        # A condition about the posting (right to work / clearance / degree) or a
        # labelled location/terms line is NOT an applicant requirement: route it
        # out of the requirements bucket before section routing happens.
        if any(m in low for m in elig_markers):
            if not any(e["source_line"] == no for e in items["eligibility"]):
                items["eligibility"].append(entry)
            continue
        if LOCATION_LINE_RE.match(text):
            items["location"].append(entry)
            continue

        if current_kind == "requirements":
            if any(m in low for m in inline_desirable):
                items["requirements"].append(
                    {**entry, "kind": "desirable", "kind_source": "inline desirable marker"})
            else:
                items["requirements"].append(
                    {**entry, "kind": "essential", "kind_source": "essential section"})
        elif current_kind == "desirable":
            items["requirements"].append(
                {**entry, "kind": "desirable", "kind_source": "desirable section"})
        elif current_kind == "eligibility":
            items["eligibility"].append(entry)
        elif current_kind == "responsibilities":
            items["responsibilities"].append(entry)
        elif current_kind == "benefits":
            items["benefits"].append(entry)
        elif current_kind == "about_company":
            items["about_company"].append(entry)
        elif current_kind == "location":
            items["location"].append(entry)
        else:
            items["other"].append(entry)
    return items


def _category_for(text: str) -> str:
    low = text.casefold()
    if any(m in low for m in ("right to work", "work permit", "visa", "sponsor",
                              "eligible to work", "sponsorship")):
        return "right_to_work"
    if any(m in low for m in ("security clearance", "sc clearance", "dbs",
                              "background check", "vetting")):
        return "clearance"
    if any(m in low for m in ("degree", "bachelor", "master", "bsc", "msc", "phd")):
        return "degree"
    if any(m in low for m in ("based in", "commutable", "on-site", "onsite", "hybrid",
                              "relocat", "office")):
        return "location"
    return "other"


DISCIPLINE_TOKENS = ("information security", "cyber", "security", "computing",
                     "computer science", "computer", "it ", "information technology",
                     "data", "engineering", "mathematics", "science")


def classify_eligibility(entry: dict, owner: dict) -> dict:
    """Attach a status to a posted eligibility condition.

    'satisfied_by_owner_source' is used ONLY when a canonical owner source states
    the condition. Everything else is 'unknown': an unstated owner position must
    never be assumed, and a posting that does not state a condition at all is
    recorded as 'not_stated' rather than silently treated as satisfied.
    """
    text = entry["text"]
    low = text.casefold()
    category = _category_for(text)
    out = {**entry, "category": category, "status": "unknown", "owner_source": None,
           "owner_source_line": None, "note": None}

    if category == "right_to_work":
        places = [p for p in ("united kingdom", "uk", "england", "scotland", "wales",
                              "uae", "united arab emirates", "dubai", "japan",
                              "singapore", "european union", "eu")
                  if p in low]
        authorised = [a.casefold() for a in owner.get("authorized_in", [])]
        covered = bool(places) and all(
            any(a in p or p in a for a in authorised) for p in places)
        if covered:
            out["status"] = "satisfied_by_owner_source"
            out["owner_source"] = f"{owner['profile_path']}#location.authorized_in"
            out["owner_source_line"] = (owner.get("authorized_in_lines") or [None])[0]
            out["note"] = ("The posting's right-to-work condition names only locations the "
                           "owner's own profile lists as authorised. This is an owner-stated "
                           "fact, not an inference; the CV/cover letter may not claim more "
                           "than the owner source states.")
        elif places:
            out["status"] = "unknown"
            out["note"] = (f"The posting names {', '.join(places)} and the owner profile lists "
                           f"only {', '.join(owner.get('authorized_in', [])) or 'no location'}. "
                           "No owner-stated right to work there — owner decision required.")
        else:
            out["status"] = "unknown"
            out["note"] = ("The posting requires a right to work but names no location, so it "
                           "cannot be matched against any owner-stated authorisation.")
    elif category == "clearance":
        out["status"] = "unknown"
        out["note"] = ("No canonical owner source states any security clearance/vetting "
                       "position. Must be treated as unrecognised, never as satisfied.")
    elif category == "degree":
        hits = []
        for line in owner.get("education_lines", []):
            if any(tok in line["text"].casefold() for tok in DISCIPLINE_TOKENS):
                hits.append(line)
        if hits:
            out["status"] = "satisfied_by_owner_source"
            out["owner_source"] = f"{owner['cv_path']}#Education"
            out["owner_source_line"] = hits[0]["line"]
            out["note"] = (f"Canonical CV education line {hits[0]['line']} names a related "
                           "discipline. Verbatim only — do not restate or embellish it.")
        else:
            out["status"] = "unknown"
            out["note"] = "No canonical education line matches the posted degree discipline."
    elif category == "location":
        loc = low
        authorised = [a.casefold() for a in owner.get("authorized_in", [])]
        if any(a in loc for a in authorised):
            out["status"] = "satisfied_by_owner_source"
            out["owner_source"] = f"{owner['profile_path']}#location.authorized_in"
            out["owner_source_line"] = (owner.get("authorized_in_lines") or [None])[0]
            out["note"] = "Posting location is one the owner's profile lists as authorised."
        else:
            out["status"] = "unknown"
            out["note"] = "Posting location is not matched by an owner-stated authorisation."
    else:
        out["note"] = "Condition recorded as stated; no owner source can classify it."
    return out


def extract_keywords(items: dict, generic_terms: list[str], limit: int) -> list[dict]:
    """The posting's own vocabulary, from requirement and responsibility lines.

    Eligibility/location lines are excluded: they describe the posting's terms,
    not the role's skills, and would only add noise to a keyword ranking.
    """
    generic = {str(t).casefold() for t in generic_terms}
    counts: dict[str, dict] = {}
    pools = (("requirements", items["requirements"]),
             ("responsibilities", items["responsibilities"]))
    for label, entries in pools:
        for e in entries:
            for tok in WORD_RE.findall(e["text"]):
                term = tok.strip(".,;:()[]\"'").casefold()
                if len(term) < 3 or term in generic or term.isdigit():
                    continue
                slot = counts.setdefault(term, {"term": term, "occurrences": 0, "sources": []})
                slot["occurrences"] += 1
                if label not in slot["sources"]:
                    slot["sources"].append(label)
    ordered = sorted(counts.values(), key=lambda s: (-s["occurrences"], s["term"]))
    return ordered[:limit]


# --------------------------------------------------------------------------- #
# JobBrief
# --------------------------------------------------------------------------- #

def build_risks(items: dict, eligibility: list[dict], jd_text: str) -> list[dict]:
    risks: list[dict] = []
    if not jd_text.strip():
        risks.append({
            "kind": "job_description_missing", "severity": "blocker",
            "detail": "No posting text is available, so requirements, responsibilities and "
                      "keyword coverage cannot be established.",
            "action": "Supply the posting text (--jd-file) before producing an application pack.",
        })
    unknown = [e for e in eligibility if e["status"] == "unknown"]
    for e in unknown:
        risks.append({
            "kind": f"eligibility_{e['category']}_unknown",
            "severity": "blocker" if e["category"] in ("right_to_work", "clearance") else "major",
            "detail": f"Posting states: \"{e['text']}\" (line {e['source_line']}). {e.get('note') or ''}".strip(),
            "action": "Owner must state the position explicitly; the build will not infer it.",
        })
    if not any(e["category"] == "right_to_work" for e in eligibility):
        risks.append({
            "kind": "right_to_work_not_stated", "severity": "major",
            "detail": "The posting does not state a right-to-work or sponsorship condition.",
            "action": "Confirm sponsorship/right-to-work position with the employer before applying; "
                      "do not assume either way.",
        })
    desirable = [r for r in items["requirements"] if r["kind"] == "desirable"]
    if desirable:
        risks.append({
            "kind": "desirable_items_present", "severity": "info",
            "detail": f"{len(desirable)} posting lines are desirable/preferred, not essential. "
                      "They are recorded as preferences and must never be presented as met.",
            "action": "Report coverage separately from essential requirements.",
        })
    return risks


def candidate_claim_violations(brief: dict) -> list[dict]:
    """Fail loudly if any first-person candidate claim reached the brief."""
    violations: list[dict] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            for pat in CANDIDATE_CLAIM_PATTERNS:
                if re.search(pat, node):
                    violations.append({"path": path, "pattern": pat, "text": node[:200]})

    walk(brief, "$")
    if brief.get("candidate_claims"):
        violations.append({"path": "$.candidate_claims", "pattern": "non-empty",
                           "text": json.dumps(brief["candidate_claims"])[:200]})
    return violations


def validate_brief(brief: dict, cfg: dict | None = None) -> dict:
    """Structural validation against the committed schema's required contract."""
    cfg = cfg or load_config()
    schema_file = schema_path(cfg)
    errors: list[str] = []
    schema = None
    if schema_file.exists():
        try:
            schema = json.loads(read_text(schema_file))
        except json.JSONDecodeError as exc:
            errors.append(f"schema file unparsable: {exc}")
    if schema is None:
        errors.append(f"schema file missing: {schema_file}")
        return {"ok": False, "errors": errors, "schema": str(schema_file)}

    for key in schema.get("required", []):
        if key not in brief:
            errors.append(f"missing required top-level key: {key}")

    def type_ok(value, spec) -> bool:
        if isinstance(spec, list):
            return any(type_ok(value, s) for s in spec)
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(spec, True)

    for key, spec in (schema.get("properties") or {}).items():
        if key in brief and not type_ok(brief[key], spec.get("type")):
            errors.append(f"{key}: expected {spec.get('type')}, got {type(brief[key]).__name__}")

    for entry in brief.get("requirements", []):
        if entry.get("kind") not in ("essential", "desirable"):
            errors.append(f"requirement kind not essential/desirable: {entry.get('kind')!r}")
        if not entry.get("source_line"):
            errors.append(f"requirement without a source_line: {entry.get('text')!r}")
    for entry in brief.get("responsibilities", []):
        if not entry.get("source_line"):
            errors.append(f"responsibility without a source_line: {entry.get('text')!r}")
    for key in ("candidate_claims", "external_actions_taken"):
        if brief.get(key):
            errors.append(f"{key} must be empty")
    return {"ok": not errors, "errors": errors, "schema": str(schema_file),
            "schema_id": (schema or {}).get("$id")}


# --------------------------------------------------------------------------- #
# research brief (B14)
# --------------------------------------------------------------------------- #

def provider_state(cfg: dict) -> dict:
    out = {}
    for name, spec in (cfg.get("research", {}).get("providers") or {}).items():
        out[name] = {"enabled": bool(spec.get("enabled")),
                     "kind": spec.get("kind"),
                     "reason": spec.get("reason") or spec.get("note")}
    return out


def validate_research_facts(payload, provider: str) -> tuple[list[dict], list[dict]]:
    """Accept a fact ONLY with a source and a citation. Anything else is rejected."""
    accepted: list[dict] = []
    rejected: list[dict] = []
    facts = payload.get("facts") if isinstance(payload, dict) else payload
    if not isinstance(facts, list):
        return [], [{"reason": "research payload has no 'facts' list", "raw": str(payload)[:200]}]
    for i, fact in enumerate(facts):
        if not isinstance(fact, dict):
            rejected.append({"index": i, "reason": "not an object", "raw": str(fact)[:200]})
            continue
        missing = [k for k in ("claim", "value", "source", "citation")
                   if not str(fact.get(k) or "").strip()]
        if missing:
            rejected.append({"index": i, "reason": f"missing {', '.join(missing)}",
                             "claim": fact.get("claim"), "raw": str(fact)[:200]})
            continue
        accepted.append({
            "claim": str(fact["claim"]).strip(),
            "value": str(fact["value"]).strip(),
            "source": str(fact["source"]).strip(),
            "citation": str(fact["citation"]).strip(),
            "provider": str(fact.get("provider") or provider),
            "retrieved_at": fact.get("retrieved_at"),
        })
    return accepted, rejected


def load_research_file(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "reason": f"research file not found: {p}"}
    try:
        payload = json.loads(read_text(p))
    except json.JSONDecodeError as exc:
        return {"ok": False, "reason": f"research file is not valid JSON: {exc}"}
    return {"ok": True, "payload": payload, "path": str(p), "sha256": sha256_file(p)}


def research_brief(cfg: dict, job: dict, *, research_file: str | Path | None = None,
                   allow_network: bool = False) -> dict:
    """Company/role research brief.

    Never guesses. With an approved, cited source it returns facts; otherwise it
    returns status='research_needed' plus the exact list of what it wanted.
    """
    rcfg = cfg.get("research", {})
    providers = provider_state(cfg)
    notes: list[str] = []
    accepted: list[dict] = []
    rejected: list[dict] = []
    sources: list[dict] = []

    if research_file:
        loaded = load_research_file(research_file)
        if not loaded.get("ok"):
            notes.append(loaded["reason"])
        else:
            facts, bad = validate_research_facts(loaded["payload"], "file")
            accepted.extend(facts)
            rejected.extend(bad)
            sources.append({"provider": "file", "path": loaded["path"],
                            "sha256": loaded["sha256"],
                            "facts_accepted": len(facts), "facts_rejected": len(bad)})
            if bad:
                notes.append(f"{len(bad)} research fact(s) rejected for missing citation fields; "
                             "rejected facts are never used.")
    else:
        notes.append("No research provider was supplied, so no company fact could be cited.")

    for name in ("http", "browser"):
        if not providers.get(name, {}).get("enabled"):
            notes.append(f"provider '{name}' is disabled: {providers.get(name, {}).get('reason')}")

    if allow_network:
        enabled = [n for n, p in providers.items() if p.get("enabled") and n != "file"]
        if not enabled:
            notes.append("--allow-network was requested but no network research provider is "
                         "enabled in the configuration; nothing was fetched.")
    if rejected:
        notes.append("Rejected facts: " + json.dumps(rejected, ensure_ascii=False)[:600])

    status = "research_needed" if not accepted else ("partial" if rejected else "provided")
    return {
        "status": status,
        "requested": list(rcfg.get("requested_defaults", [])) + [
            f"company legal/registered identity for {job.get('company') or 'the employer'}",
            f"role-specific expectations for {job.get('title') or 'the role'} not stated in the posting",
        ],
        "providers": providers,
        "sources": sources,
        "rejected_facts": rejected,
        "notes": notes,
        "facts": accepted,
    }


# --------------------------------------------------------------------------- #
# the brief command
# --------------------------------------------------------------------------- #

def build_brief(cfg: dict, *, job: dict, jd_text: str, jd_source: str | None,
                research_file: str | Path | None = None,
                allow_network: bool = False, stamp: str | None = None,
                brief_id: str | None = None) -> dict:
    stamp = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rules = cfg["extraction"]
    items = extract_items(jd_text, rules)
    owner = owner_sources(cfg)

    requirements = items["requirements"][: int(rules.get("max_requirements", 80))]
    responsibilities = items["responsibilities"][: int(rules.get("max_responsibilities", 80))]
    eligibility = [classify_eligibility(e, owner) for e in items["eligibility"]]
    preferences = [{"text": r["text"], "source_line": r["source_line"],
                    "note": "Employer preference/desirable item. A property of the posting, "
                            "never a fact about the candidate."}
                   for r in requirements if r["kind"] == "desirable"]

    wf_cfg = load_workflow_config(cfg)
    generic = (wf_cfg.get("tailoring", {}).get("generic_terms")
               or cfg.get("generic_terms_fallback") or [])
    keywords = extract_keywords(items, generic, int(rules.get("max_keywords", 40)))

    research = research_brief(cfg, job, research_file=research_file,
                              allow_network=allow_network)

    source_supported = (
        [{"text": r["text"], "source_line": r["source_line"],
          "source_section": r["source_section"], "role": "requirement"} for r in requirements]
        + [{"text": r["text"], "source_line": r["source_line"],
            "source_section": r["source_section"], "role": "responsibility"}
           for r in responsibilities]
        + [{"text": e["text"], "source_line": e["source_line"],
            "source_section": e["source_section"], "role": "eligibility"} for e in eligibility]
    )

    brief = {
        "schema_version": cfg.get("schema_version", 1),
        "brief_id": brief_id or f"jb-{stamp}-{sha256_text(jd_text)[:8]}",
        "generated_at": now_utc(),
        "generator": "career-ops/job_intelligence.py",
        "job": {
            "id": job.get("id"), "company": job.get("company"), "title": job.get("title"),
            "location": job.get("location"), "url": job.get("url"),
            "region": job.get("_region"), "source_kind": job.get("_source_kind"),
            "source_path": job.get("_source_path"),
        },
        "provenance": {
            "job_record": {"source_kind": job.get("_source_kind"),
                           "source_path": job.get("_source_path"),
                           "region": job.get("_region"),
                           "tracker": job.get("_tracker"),
                           "workbook_row": job.get("_row")},
            "job_description": {
                "available": bool(jd_text.strip()), "source": jd_source,
                "kind": "provided posting text", "sha256": sha256_text(jd_text) if jd_text else None,
                "chars": len(jd_text), "lines": len(jd_text.splitlines()),
            },
            "canonical_owner_sources": {
                "cv.md": {"path": owner["cv_path"], "sha256": owner["cv_sha256"]},
                "config/profile.yml": {"path": owner["profile_path"],
                                       "sha256": owner["profile_sha256"]},
            },
            "extraction": "deterministic, extractive, verbatim lines with source_line",
        },
        "requirements": requirements,
        "responsibilities": responsibilities,
        "eligibility": eligibility,
        "preferences": preferences,
        "keywords": keywords,
        "risks_unknowns": build_risks(items, eligibility, jd_text),
        "company_facts": research["facts"],
        "research": {k: v for k, v in research.items() if k != "facts"},
        "source_supported_facts": source_supported,
        "candidate_claims": [],
        "sections_detected": {
            "benefits": items["benefits"], "about_company": items["about_company"],
            "location": items["location"], "other": items["other"],
        },
        "not_performed": cfg.get("not_performed", []),
        "external_actions_taken": [],
    }
    brief["validation"] = validate_brief(brief, cfg)
    brief["candidate_claim_violations"] = candidate_claim_violations(brief)
    return brief


def handoff_jd_text(brief: dict) -> str:
    """The ONLY text handed to the CV / cover-letter workflows.

    Verbatim posting lines from ``source_supported_facts`` in source-line order,
    so downstream tailoring can never rank on a line the posting does not contain.
    """
    facts = sorted(brief.get("source_supported_facts", []),
                   key=lambda f: (f.get("source_line") or 0, f.get("role") or ""))
    return "\n".join(f["text"] for f in facts)


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def _resolve_job(cfg: dict, args) -> dict:
    wf_cfg = load_workflow_config(cfg)
    profiles = tw.load_profiles(str(profiles_path(cfg)))
    return cvw.resolve_job(wf_cfg, profiles, region=args.region, job_id=args.id,
                           url=args.url, row=args.row,
                           pipeline_index=args.pipeline_index, record_file=args.record)


def cmd_schema(args) -> int:
    cfg = load_config(args.config)
    path = schema_path(cfg)
    emit({"schema_path": str(path), "exists": path.exists(),
          "schema": json.loads(read_text(path)) if path.exists() else None,
          "config_path": cfg["_config_path"]})
    return 0 if path.exists() else 1


def cmd_brief(args) -> int:
    cfg = load_config(args.config)
    resolved = _resolve_job(cfg, args)
    if not resolved.get("ok"):
        emit(resolved)
        return 1
    job = resolved["job"]
    jd_text = ""
    jd_source = None
    if args.jd_file:
        p = Path(args.jd_file)
        if not p.exists():
            emit({"ok": False, "reason": f"job-description file not found: {p}"})
            return 1
        jd_text = read_text(p)
        jd_source = f"explicit file {p}"
    else:
        jd_text = resolved.get("jd_text") or ""
        jd_source = resolved.get("jd_source")
    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    brief = build_brief(cfg, job=job, jd_text=jd_text, jd_source=jd_source,
                        research_file=args.research_file,
                        allow_network=args.allow_network, stamp=stamp)
    run_dir = Path(args.out) if args.out else (runtime_dir(cfg) / stamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    brief_path = run_dir / "job_brief.json"
    brief["brief_path"] = str(brief_path)
    brief_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False, default=str),
                          encoding="utf-8")
    brief["handoff_jd_text_path"] = None
    out = dict(brief)
    out["ok"] = brief["validation"]["ok"] and not brief["candidate_claim_violations"]
    if args.record:
        Path(args.record).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str),
                                     encoding="utf-8")
        out["recorded_to"] = args.record
    emit(out)
    return 0 if out["ok"] else 1


def cmd_research(args) -> int:
    cfg = load_config(args.config)
    if not args.brief:
        emit({"ok": False, "reason": "--brief is required"})
        return 1
    brief = json.loads(read_text(args.brief))
    job = brief.get("job") or {}
    research = research_brief(cfg, job, research_file=args.research_file,
                              allow_network=args.allow_network)
    emit({"ok": True, "job": job, "research": {k: v for k, v in research.items() if k != "facts"},
          "facts": research["facts"], "external_actions_taken": []})
    return 0


def cmd_validate(args) -> int:
    cfg = load_config(args.config)
    brief = json.loads(read_text(args.brief))
    result = validate_brief(brief, cfg)
    result["candidate_claim_violations"] = candidate_claim_violations(brief)
    result["ok"] = bool(result["ok"]) and not result["candidate_claim_violations"]
    emit(result)
    return 0 if result["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="JobBrief + company/role research brief (B13/B14)")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("schema"); p.set_defaults(fn=cmd_schema)

    p = sub.add_parser("brief")
    p.add_argument("--region")
    p.add_argument("--id")
    p.add_argument("--url")
    p.add_argument("--row", type=int)
    p.add_argument("--pipeline-index", type=int)
    p.add_argument("--record")
    p.add_argument("--jd-file")
    p.add_argument("--research-file")
    p.add_argument("--allow-network", action="store_true")
    p.add_argument("--out")
    p.add_argument("--stamp")
    p.set_defaults(fn=cmd_brief)

    for name, fn in (("research", cmd_research), ("validate", cmd_validate)):
        p = sub.add_parser(name)
        p.add_argument("--brief")
        p.add_argument("--research-file")
        p.add_argument("--allow-network", action="store_true")
        p.set_defaults(fn=fn)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
