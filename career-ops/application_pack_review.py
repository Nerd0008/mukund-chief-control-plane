#!/usr/bin/env python3
"""Application Pack Reviewer (roster B17) — independent truth & completeness gate.

Independence, stated truthfully: this is a *separate module* that re-reads the
on-disk artifacts and the canonical owner sources and re-derives every verdict
with its own logic. It does not import the generator's verdicts, does not trust
the JobBrief's own ``validation`` block, and re-checks every extracted posting
line against the posting file itself. Both the generator and this reviewer are
deterministic software, so this is independent *re-derivation*, NOT a second
model, a second opinion, or a substitute for owner review. Saying otherwise
would overstate the guarantee.

What it checks (five areas):

  truthfulness          every draft line is verbatim canonical text; no invented
                        metric, certification, date or first-person claim; the
                        install's own fact gate did not block.
  requirement_coverage  essential vs desirable requirements, each classified
                        covered / partial / uncovered against canonical sources.
                        Coverage is reported, never asserted as a claim.
  consistency           brief job identity == letter identity; every extracted
                        requirement/eligibility line matches the posting's own
                        line that it cites; the handoff text is composed only of
                        posting lines; the candidate name is the canonical one.
  formatting            artifacts present, non-empty, no unresolved placeholders,
                        export path explicit (PDF intentionally not produced).
  unresolved_unknowns   research gaps, risks and owner-input items that a
                        submission gate must see.

Verdict: "pass" | "pass_with_owner_input_required" | "block".
Only truthfulness / consistency / formatting defects can "block"; an unresolved
unknown that needs an owner fact produces "pass_with_owner_input_required",
because a missing owner fact is not a defect in the pack.

CLI
  python career-ops/application_pack_review.py review --brief JOB_BRIEF.json \
      --cv-draft CV.md --cover-payload PAYLOAD.json [--cover-html HTML] \
      [--draft-result JSON] [--jd-file JD.txt] [--handoff-text T.txt] \
      [--job-record REC.json] [--out DIR]
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

CONFIG_PATH = CAREER_OPS_DIR / "job_intelligence_config.json"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{3,}")
BULLET_RE = re.compile(r"^\s*(?:[-*\u2022\u2013\u2014]|\d+[.)])\s+")
HEADING_RE = re.compile(r"^#{1,6}\s+")
PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|TODO|TBD|XXX|PLACEHOLDER|<insert", re.I)
DIGIT_TOKEN_RE = re.compile(r"\b[A-Za-z0-9]*\d[A-Za-z0-9%.,+-]*\b")

# The only text this pipeline is allowed to author itself. Everything else in a
# draft must exist verbatim in a canonical owner source.
META_PREFIXES = (
    "I am writing to apply for",
    "Thank you for considering this application.",
    "Sincerely,",
    "Supporting evidence, reproduced verbatim from the canonical CV",
    "No job-description text is available from Career Ops for this posting",
    "Posting terms with no canonical evidence:",
    "DRAFT ONLY",
    "DRAFT ONLY \u2014 owner review required",
    "No application has been submitted",
)
# Source-reference suffixes the pipeline itself writes, e.g. "[cv.md:48]".
SOURCE_REF_RE = re.compile(r"\[[A-Za-z0-9_.\\/-]+:\d+\]")
FIRST_PERSON_RE = re.compile(
    r"\bI have\b|\bI am a\b|\bI am an\b|\bI've\b|\bmy experience\b|\bI led\b|"
    r"\bI built\b|\bI managed\b|\bI hold\b|\bmy skills\b", re.I)

REQUIRED_PAYLOAD_KEYS = ("candidate", "letter", "provenance")
REQUIRED_LETTER_KEYS = ("company", "role_title", "opening", "profile_intro",
                        "problems_section", "closing", "signature")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    cfg = json.loads(read_text(p))
    cfg["_config_path"] = str(p)
    return cfg


def workflow_config(cfg: dict) -> dict:
    return cvw.load_config(CONTROL_PLANE / cfg["cv_workflow_config"])


def canonical_sources(cfg: dict) -> dict:
    """Read the canonical owner sources directly (read-only)."""
    wf = workflow_config(cfg)
    paths = cvw.source_paths(wf)
    cv_text = read_text(paths["cv_md"])
    profile_text = read_text(paths["profile"])
    name = None
    email = None
    try:
        import yaml  # noqa: PLC0415
        doc = yaml.safe_load(profile_text) or {}
        cand = doc.get("candidate") or {}
        name = cand.get("full_name")
        email = cand.get("email")
    except ImportError:  # pragma: no cover
        pass
    return {
        "cv_text": cv_text, "profile_text": profile_text,
        "cv_path": str(paths["cv_md"]), "profile_path": str(paths["profile"]),
        "cv_sha256": sha256_text(cv_text), "profile_sha256": sha256_text(profile_text),
        "canonical_name": name, "canonical_email": email,
        "facts": cvw.profile_facts(wf),
    }


def canonical_line_set(cv_text: str, profile_text: str) -> set[str]:
    """Every canonical line in every plausible surface form."""
    out: set[str] = set()
    for text in (cv_text, profile_text):
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            out.add(stripped)
            out.add(BULLET_RE.sub("", stripped))
            out.add(HEADING_RE.sub("", stripped))
            out.add(re.sub(r"^[-*]\s+", "", stripped))
    return out


def normalise_posting_line(raw: str) -> str:
    return BULLET_RE.sub("", raw.strip()).strip()


def posting_lines(jd_text: str) -> dict[int, str]:
    return {no: normalise_posting_line(raw)
            for no, raw in enumerate(jd_text.splitlines(), start=1)}


# --------------------------------------------------------------------------- #
# area checks
# --------------------------------------------------------------------------- #

def check_truthfulness(pack: dict, canon: dict, lines: set[str]) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    facts: dict = {}

    draft = pack.get("cv_draft_text") or ""
    bad: list[dict] = []
    in_comment = False
    for no, raw in enumerate(draft.splitlines(), start=1):
        line = raw.strip()
        if in_comment:
            if line.endswith("-->"):
                in_comment = False
            continue
        if line.startswith("<!--"):
            # a comment may open and close on the same line
            if not line.endswith("-->"):
                in_comment = True
            continue
        if not line:
            continue
        bare = BULLET_RE.sub("", HEADING_RE.sub("", line)).strip()
        if bare not in lines:
            bad.append({"draft_line": no, "text": line[:200]})
    facts["cv_draft_lines_not_verbatim"] = bad
    if bad:
        findings.append({
            "id": "cv_draft_not_verbatim", "area": "truthfulness", "severity": "blocker",
            "detail": f"{len(bad)} CV draft line(s) do not exist verbatim in the canonical "
                      "owner sources. The draft workflow may reorder canonical lines only.",
            "evidence": bad[:10],
        })

    payload = pack.get("payload") or {}
    letter = payload.get("letter") or {}
    suspicious: list[dict] = []

    def flag_sentence(where: str, sentence: str) -> None:
        s = sentence.strip()
        if not s or len(s) < 3:
            return
        if any(s.startswith(p) for p in META_PREFIXES):
            return
        if re.match(r"^I am writing to apply for the .+ position at .+\.$", s):
            return
        if s in lines:
            return
        stripped = re.sub(r"\s*\[cv\.md:\d+\]\s*$", "", s).strip()
        if stripped and stripped in lines:
            return
        if s.startswith("Posting terms with no canonical evidence:") or s.startswith("DRAFT ONLY"):
            return
        suspicious.append({"where": where, "text": s[:240]})

    for key in ("opening", "profile_intro", "closing"):
        value = letter.get(key)
        if isinstance(value, str) and value.strip():
            flag_sentence(f"letter.{key}", value)
    sig = (letter.get("signature") or {})
    if isinstance(sig.get("valediction"), str):
        flag_sentence("letter.signature.valediction", sig["valediction"])
    if isinstance(sig.get("name"), str) and sig["name"].strip():
        if canon.get("canonical_name") and sig["name"].strip() != canon["canonical_name"]:
            findings.append({
                "id": "letter_name_mismatch", "area": "truthfulness", "severity": "blocker",
                "detail": "The letter's signature name is not the canonical profile name.",
                "evidence": {"letter": sig["name"].strip(),
                             "canonical": canon["canonical_name"]},
            })
    problems = letter.get("problems_section")
    if isinstance(problems, str) and problems.strip():
        for sentence in re.split(r"(?<=\.)\s+", problems.strip()):
            flag_sentence("letter.problems_section", sentence)
    for i, foot in enumerate(letter.get("footnotes") or []):
        if isinstance(foot, dict) and isinstance(foot.get("text"), str):
            flag_sentence(f"letter.footnotes[{i}]", foot["text"])

    facts["letter_text_not_traceable"] = suspicious
    if suspicious:
        findings.append({
            "id": "cover_letter_free_text", "area": "truthfulness", "severity": "blocker",
            "detail": f"{len(suspicious)} cover-letter fragment(s) are neither recognised "
                      "structural text nor verbatim canonical text.",
            "evidence": suspicious[:10],
        })

    # invented metrics: every digit-bearing token must exist in a canonical source.
    # Source-reference suffixes the pipeline writes itself ([cv.md:48]) are
    # provenance, not claims, so they are removed before scanning.
    invented: list[dict] = []
    for where, value in facts_scope_letter(letter).items():
        scanned = SOURCE_REF_RE.sub(" ", value)
        for tok in sorted(set(DIGIT_TOKEN_RE.findall(scanned))):
            if tok in line_text(canon):
                continue
            invented.append({"where": where, "token": tok})
    facts["digit_tokens_absent_from_canonical"] = invented
    if invented:
        findings.append({
            "id": "invented_metric", "area": "truthfulness", "severity": "blocker",
            "detail": "The cover letter contains numbers that do not appear in any canonical "
                      "owner source — a metric must never be invented.",
            "evidence": invented[:10],
        })

    # first-person claims must be canonical
    claims: list[dict] = []
    for where, value in facts_scope_letter(letter).items():
        for m in FIRST_PERSON_RE.finditer(value):
            sentence = value[max(0, m.start() - 40):m.start() + 120]
            if sentence.strip() not in lines:
                claims.append({"where": where, "match": m.group(0), "context": sentence})
    facts["first_person_claims_not_canonical"] = claims
    if claims:
        findings.append({
            "id": "candidate_claim_not_canonical", "area": "truthfulness", "severity": "blocker",
            "detail": "The pack makes a first-person claim about the candidate that is not "
                      "verbatim in a canonical owner source.",
            "evidence": claims[:10],
        })

    facts["install_fact_gate"] = pack.get("fact_gate")
    for label, gate in (pack.get("fact_gate") or {}).items():
        if not isinstance(gate, dict):
            continue
        if not gate.get("available"):
            findings.append({
                "id": f"fact_gate_unavailable_{label}", "area": "truthfulness",
                "severity": "major",
                "detail": f"The Career Ops install fact gate did not run for '{label}'; the "
                          "pack has not been verified by the workflow's own gate.",
                "evidence": gate,
            })
        elif gate.get("verdict") == "block":
            findings.append({
                "id": f"fact_gate_block_{label}", "area": "truthfulness", "severity": "blocker",
                "detail": f"The Career Ops install fact gate blocked the '{label}' artifact.",
                "evidence": gate,
            })
    return findings, facts


def facts_scope_letter(letter: dict) -> dict:
    scope = {}
    for key in ("opening", "profile_intro", "problems_section", "closing"):
        if isinstance(letter.get(key), str):
            scope[f"letter.{key}"] = letter[key]
    for i, foot in enumerate(letter.get("footnotes") or []):
        if isinstance(foot, dict) and isinstance(foot.get("text"), str):
            scope[f"letter.footnotes[{i}]"] = foot["text"]
    return scope


def line_text(canon: dict) -> str:
    return canon["cv_text"] + "\n" + canon["profile_text"]


def check_coverage(brief: dict, canon: dict) -> tuple[list[dict], dict]:
    wf = workflow_config(load_config())
    generic = {str(t).casefold() for t in
               (wf.get("tailoring", {}).get("generic_terms") or [])}
    source = (canon["cv_text"] + "\n" + canon["profile_text"]).casefold()

    def classify(entry: dict) -> dict:
        tokens = {t.casefold() for t in TOKEN_RE.findall(entry.get("text") or "")}
        distinctive = sorted(t for t in tokens if t and t not in generic)
        matched = [t for t in distinctive if t in source]
        missing = [t for t in distinctive if t not in source]
        ratio = round(len(matched) / len(distinctive), 3) if distinctive else 0.0
        if not distinctive:
            status = "uncovered"
        elif ratio >= 0.5:
            status = "covered"
        elif matched:
            status = "partial"
        else:
            status = "uncovered"
        return {"text": entry.get("text"), "source_line": entry.get("source_line"),
                "status": status, "match_ratio": ratio, "matched_terms": matched[:12],
                "missing_terms": missing[:12]}

    essential = [classify(r) for r in brief.get("requirements", []) if r.get("kind") == "essential"]
    desirable = [classify(r) for r in brief.get("requirements", []) if r.get("kind") == "desirable"]
    counts: dict = {
        "essential_total": len(essential),
        "essential_covered": sum(1 for e in essential if e["status"] == "covered"),
        "essential_partial": sum(1 for e in essential if e["status"] == "partial"),
        "essential_uncovered": sum(1 for e in essential if e["status"] == "uncovered"),
        "desirable_total": len(desirable),
        "desirable_covered": sum(1 for e in desirable if e["status"] == "covered"),
    }
    counts["essential_coverage_ratio"] = (
        round(counts["essential_covered"] / counts["essential_total"], 3)
        if counts["essential_total"] else None)
    counts["note"] = ("Coverage means the posting's own vocabulary overlaps text that exists in "
                      "the canonical sources. It is a ranking aid, not evidence that any specific "
                      "requirement is met. Desirable items are reported separately and are never "
                      "folded into essential coverage.")

    findings: list[dict] = []
    uncovered = [e for e in essential if e["status"] == "uncovered"]
    if uncovered:
        findings.append({
            "id": "essential_requirements_uncovered", "area": "requirement_coverage",
            "severity": "major",
            "detail": f"{len(uncovered)} essential requirement(s) have no canonical-source "
                      "overlap at all. They must be surfaced to the owner, never claimed.",
            "evidence": uncovered[:10],
        })
    partial = [e for e in essential if e["status"] == "partial"]
    if partial:
        findings.append({
            "id": "essential_requirements_partial", "area": "requirement_coverage",
            "severity": "info",
            "detail": f"{len(partial)} essential requirement(s) have only partial canonical "
                      "overlap.",
            "evidence": partial[:10],
        })
    return findings, {"essential": essential, "desirable": desirable, "counts": counts}


def check_consistency(brief: dict, pack: dict, canon: dict) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    facts: dict = {}
    payload = pack.get("payload") or {}
    letter = payload.get("letter") or {}
    job = brief.get("job") or {}

    mismatches = []
    for field, got in (("company", letter.get("company")), ("title", letter.get("role_title"))):
        want = job.get(field)
        if (want or "") != (got or ""):
            mismatches.append({"field": field, "brief": want, "letter": got})
    posting = (payload.get("provenance") or {}).get("posting") or {}
    for field in ("company", "title"):
        if (job.get(field) or "") != (posting.get(field) or ""):
            mismatches.append({"field": f"provenance.{field}", "brief": job.get(field),
                               "payload": posting.get(field)})
    facts["identity_mismatches"] = mismatches
    if mismatches:
        findings.append({
            "id": "job_identity_mismatch", "area": "consistency", "severity": "blocker",
            "detail": "The brief's job identity and the cover-letter payload's identity differ.",
            "evidence": mismatches,
        })

    facts["brief_validation"] = brief.get("validation")
    if brief.get("validation") and not brief["validation"].get("ok"):
        findings.append({
            "id": "brief_invalid", "area": "consistency", "severity": "blocker",
            "detail": "The JobBrief failed its own schema validation.",
            "evidence": brief["validation"].get("errors"),
        })
    if brief.get("candidate_claims"):
        findings.append({
            "id": "brief_candidate_claims", "area": "consistency", "severity": "blocker",
            "detail": "The JobBrief contains candidate claims; it must contain none.",
            "evidence": brief["candidate_claims"][:5],
        })

    # every extracted line must match the posting line it cites
    lines = pack.get("jd_lines")
    cited_mismatch: list[dict] = []
    if lines:
        for bucket in ("requirements", "responsibilities", "eligibility"):
            for entry in brief.get(bucket, []):
                no = entry.get("source_line")
                want = entry.get("text")
                got = lines.get(no)
                if got is None:
                    cited_mismatch.append({"bucket": bucket, "source_line": no,
                                           "problem": "line does not exist in the posting",
                                           "text": want})
                elif normalise_posting_line(want or "") != got:
                    cited_mismatch.append({"bucket": bucket, "source_line": no,
                                           "problem": "does not match the posting line",
                                           "brief": want, "posting": got})
    facts["posting_citation_mismatches"] = cited_mismatch
    if cited_mismatch:
        findings.append({
            "id": "posting_citation_mismatch", "area": "consistency", "severity": "blocker",
            "detail": "One or more JobBrief lines do not match the posting line they cite — "
                      "the brief has drifted from its source.",
            "evidence": cited_mismatch[:10],
        })

    handoff = pack.get("handoff_text")
    handoff_bad: list[str] = []
    if handoff and lines:
        known = set(lines.values())
        for raw in handoff.splitlines():
            s = normalise_posting_line(raw)
            if s and s not in known:
                handoff_bad.append(s[:200])
    facts["handoff_lines_not_in_posting"] = handoff_bad
    if handoff_bad:
        findings.append({
            "id": "handoff_not_source_supported", "area": "consistency", "severity": "blocker",
            "detail": "The text handed to the CV/cover-letter workflows contains lines that are "
                      "not in the posting.",
            "evidence": handoff_bad[:10],
        })

    canonical_name = canon.get("canonical_name")
    payload_name = (payload.get("candidate") or {}).get("name")
    facts["candidate_name"] = {"payload": payload_name, "canonical": canonical_name,
                               "ok": (not canonical_name) or payload_name == canonical_name}
    if canonical_name and payload_name != canonical_name:
        findings.append({
            "id": "payload_name_mismatch", "area": "consistency", "severity": "blocker",
            "detail": "The pack's candidate name is not the canonical profile name.",
            "evidence": facts["candidate_name"],
        })
    return findings, facts


def check_formatting(pack: dict) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    facts: dict = {}
    draft = pack.get("cv_draft_text") or ""
    payload = pack.get("payload") or {}
    html = pack.get("cover_html_text")

    facts["cv_draft"] = {
        "chars": len(draft),
        "headings": len([l for l in draft.splitlines() if l.strip().startswith("#")]),
        "bullets": len([l for l in draft.splitlines() if l.strip().startswith("- ")]),
        "ends_with_newline": draft.endswith("\n"),
        "placeholders": PLACEHOLDER_RE.findall(draft)[:10],
    }
    if not draft.strip() or facts["cv_draft"]["headings"] == 0 or facts["cv_draft"]["bullets"] == 0:
        findings.append({"id": "cv_draft_incomplete", "area": "formatting", "severity": "blocker",
                         "detail": "The CV draft is empty or missing headings/bullets.",
                         "evidence": facts["cv_draft"]})
    if facts["cv_draft"]["placeholders"]:
        findings.append({"id": "cv_draft_placeholder", "area": "formatting", "severity": "blocker",
                         "detail": "The CV draft still contains placeholder tokens.",
                         "evidence": facts["cv_draft"]["placeholders"]})

    missing_payload = [k for k in REQUIRED_PAYLOAD_KEYS if k not in payload]
    missing_letter = [k for k in REQUIRED_LETTER_KEYS if k not in (payload.get("letter") or {})]
    empty_letter = [k for k in REQUIRED_LETTER_KEYS
                    if not str((payload.get("letter") or {}).get(k) or "").strip()]
    facts["payload"] = {"missing_top_level": missing_payload, "missing_letter_keys": missing_letter,
                        "empty_letter_values": empty_letter}
    if missing_payload or missing_letter or empty_letter:
        findings.append({"id": "payload_incomplete", "area": "formatting", "severity": "blocker",
                         "detail": "The cover-letter payload is missing required structure.",
                         "evidence": facts["payload"]})

    facts["cover_html"] = {
        "present": bool(html),
        "chars": len(html or ""),
        "looks_like_html": bool(html and re.search(r"<html|<!DOCTYPE", html, re.I)),
        "placeholders": PLACEHOLDER_RE.findall(html or "")[:10],
        "mentions_undefined": bool(html and "undefined" in html),
    }
    if html:
        if not facts["cover_html"]["looks_like_html"]:
            findings.append({"id": "html_not_html", "area": "formatting", "severity": "blocker",
                             "detail": "The rendered cover letter is not HTML.",
                             "evidence": facts["cover_html"]})
        if facts["cover_html"]["placeholders"] or facts["cover_html"]["mentions_undefined"]:
            findings.append({"id": "html_placeholder", "area": "formatting", "severity": "blocker",
                             "detail": "The rendered cover letter contains unresolved template "
                                       "output.",
                             "evidence": facts["cover_html"]})
    else:
        findings.append({
            "id": "cover_html_absent", "area": "formatting", "severity": "major",
            "detail": "No rendered cover-letter HTML was supplied. The pack is not export-ready "
                      "until the install renderer has produced it.",
            "evidence": pack.get("cover_html_path"),
        })

    facts["pdf_exported"] = False
    facts["pdf_note"] = ("PDF export is intentionally NOT performed: the install's "
                         "generate-pdf.mjs launches headless Chromium, which the owner's "
                         "GUI-safety directive forbids. The exact owner command is recorded in "
                         "the draft result instead.")
    return findings, facts


def check_unknowns(brief: dict, pack: dict) -> tuple[list[dict], dict, list[str]]:
    findings: list[dict] = []
    facts: dict = {}
    owner_input: list[str] = []

    research = brief.get("research") or {}
    facts["research_status"] = research.get("status")
    if research.get("status") != "provided":
        owner_input.append(
            "Company/role research is " + str(research.get("status")) +
            ": no cited company facts are available. Requested: " +
            "; ".join(research.get("requested") or [])[:400])
        findings.append({
            "id": "research_incomplete", "area": "unresolved_unknowns", "severity": "major",
            "detail": f"research.status = {research.get('status')!r}; the pack carries "
                      f"{len(brief.get('company_facts') or [])} cited company fact(s).",
            "evidence": {"providers": research.get("providers"), "notes": research.get("notes")},
        })
    if research.get("rejected_facts"):
        findings.append({
            "id": "research_facts_rejected", "area": "unresolved_unknowns", "severity": "info",
            "detail": "Research facts without a citation were rejected and are not used.",
            "evidence": research["rejected_facts"][:5],
        })

    risks = brief.get("risks_unknowns") or []
    facts["risks"] = risks
    for risk in risks:
        severity = risk.get("severity", "info")
        if severity in ("blocker", "major"):
            owner_input.append(f"[{severity}] {risk.get('detail')} -> {risk.get('action')}")
            findings.append({
                "id": f"risk_{risk.get('kind')}", "area": "unresolved_unknowns",
                "severity": severity, "detail": risk.get("detail"),
                "evidence": risk.get("action"),
            })

    facts["unsupported_terms"] = pack.get("unsupported_terms") or []
    if facts["unsupported_terms"]:
        owner_input.append(
            "Posting terms with no canonical evidence: " +
            ", ".join(facts["unsupported_terms"][:25]) +
            " — do not claim these; add real evidence or leave them out.")
    facts["owner_input_required"] = owner_input
    return findings, facts, owner_input


# --------------------------------------------------------------------------- #
# review
# --------------------------------------------------------------------------- #

def review(cfg: dict, *, brief: dict, cv_draft_path: Path, payload_path: Path,
           html_path: Path | None = None, draft_result_path: Path | None = None,
           jd_path: Path | None = None, handoff_path: Path | None = None,
           job_record_path: Path | None = None) -> dict:
    canon = canonical_sources(cfg)
    lines = canonical_line_set(canon["cv_text"], canon["profile_text"])
    jd_lines = posting_lines(read_text(jd_path)) if jd_path and Path(jd_path).exists() else None
    payload = json.loads(read_text(payload_path))
    draft_result = json.loads(read_text(draft_result_path)) if (
        draft_result_path and Path(draft_result_path).exists()) else {}
    pack = {
        "cv_draft_path": str(cv_draft_path),
        "cv_draft_text": read_text(cv_draft_path),
        "payload_path": str(payload_path),
        "payload": payload,
        "cover_html_path": str(html_path) if html_path else None,
        "cover_html_text": read_text(html_path) if html_path and Path(html_path).exists() else None,
        "jd_lines": jd_lines,
        "handoff_text": read_text(handoff_path) if handoff_path and Path(handoff_path).exists() else None,
        "fact_gate": (draft_result.get("fact_gate") or {}),
        "unsupported_terms": ((draft_result.get("job_description") or {})
                              .get("terms_absent_from_canonical_sources") or []),
    }

    findings: list[dict] = []
    areas: dict = {}
    checks: tuple[tuple[str, object], ...] = (
        ("truthfulness", lambda: check_truthfulness(pack, canon, lines)),
        ("requirement_coverage", lambda: check_coverage(brief, canon)),
        ("consistency", lambda: check_consistency(brief, pack, canon)),
        ("formatting", lambda: check_formatting(pack)),
        ("unresolved_unknowns", lambda: check_unknowns(brief, pack)),
    )
    for name, fn in checks:
        got = fn()
        findings.extend(got[0])
        areas[name] = got[1]

    owner_input = list(areas["unresolved_unknowns"].get("owner_input_required") or [])
    for finding in findings:
        if finding.get("area") == "unresolved_unknowns":
            continue
        if finding.get("severity") in ("blocker", "major"):
            owner_input.append(f"[{finding['severity']}] {finding['id']}: {finding.get('detail')} "
                               f"-> {finding.get('evidence')}")
    areas["unresolved_unknowns"]["owner_input_required_all"] = owner_input

    blockers = [f for f in findings if f.get("severity") == "blocker"
                and f.get("area") in ("truthfulness", "consistency", "formatting")]
    if blockers:
        verdict = "block"
    elif owner_input:
        verdict = "pass_with_owner_input_required"
    else:
        verdict = "pass"

    artifact_hashes = {
        "job_brief": sha256_text(json.dumps(brief, sort_keys=True, default=str)),
        "cv_draft": sha256_file(cv_draft_path),
        "cover_payload": sha256_file(payload_path),
        "cover_html": sha256_file(html_path) if html_path else None,
    }
    pack_sha = sha256_text(json.dumps(artifact_hashes, sort_keys=True))
    return {
        "reviewer": "career-ops/application_pack_review.py",
        "reviewer_role": "B17 Application Pack Reviewer / truth & completeness gate",
        "independence": {
            "statement": ("Separate module; re-reads the on-disk artifacts plus the canonical "
                          "sources and the posting file, and re-derives every verdict with its "
                          "own logic. It does not import or trust the generator's verdicts."),
            "limitation": ("Both the generator and this reviewer are deterministic software, so "
                           "this is independent re-derivation, NOT a second model or an "
                           "independent AI opinion, and NOT a substitute for owner review."),
            "reads": ["job_brief.json", "cv_draft.md", "cover_letter_payload.json",
                      "cover_letter_draft.html", "draft_result.json", "posting file (--jd-file)",
                      "canonical cv.md + config/profile.yml (read-only)"],
        },
        "reviewed_at": now_utc(),
        "brief_id": brief.get("brief_id"),
        "job": brief.get("job"),
        "pack_id": f"pack-{pack_sha[:12]}",
        "artifact_hashes": artifact_hashes,
        "pack_sha256": pack_sha,
        "checks": areas,
        "findings": findings,
        "blockers": blockers,
        "owner_input_required": owner_input,
        "verdict": verdict,
        "truthfulness_verified": not any(f["area"] == "truthfulness" for f in blockers),
        "external_actions_taken": [],
        "not_performed": ["PDF export (headless Chromium, owner-gated)",
                          "application submission", "employer/recruiter contact"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Application Pack Reviewer (B17)")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("review")
    p.add_argument("--brief", required=True)
    p.add_argument("--cv-draft", required=True)
    p.add_argument("--cover-payload", required=True)
    p.add_argument("--cover-html")
    p.add_argument("--draft-result")
    p.add_argument("--jd-file")
    p.add_argument("--handoff-text")
    p.add_argument("--job-record")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_review)
    args = ap.parse_args(argv)
    return args.fn(args)


def cmd_review(args) -> int:
    cfg = load_config(args.config)
    brief = json.loads(read_text(args.brief))
    result = review(cfg, brief=brief,
                    cv_draft_path=Path(args.cv_draft),
                    payload_path=Path(args.cover_payload),
                    html_path=Path(args.cover_html) if args.cover_html else None,
                    draft_result_path=Path(args.draft_result) if args.draft_result else None,
                    jd_path=Path(args.jd_file) if args.jd_file else None,
                    handoff_path=Path(args.handoff_text) if args.handoff_text else None,
                    job_record_path=Path(args.job_record) if args.job_record else None)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "pack_review.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        result["recorded_to"] = str(out_dir / "pack_review.json")
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n")
    return 0 if result["verdict"] != "block" else 1


if __name__ == "__main__":
    raise SystemExit(main())
