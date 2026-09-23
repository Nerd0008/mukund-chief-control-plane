#!/usr/bin/env python3
"""Chief <-> Career Ops CV / cover-letter DRAFT workflow.

Purpose
-------
Wire a job record that already exists in Career Ops state (canonical regional
workbook, the scanner's ``data/pipeline.md``, a scan run-health file, or a
signal record handed over by the LinkedIn workflow) into a *tailored draft* of
the CV and the cover letter — with provenance, and without inventing anything.

It **reuses** the existing Career Ops installation instead of recreating it:

* ``cv.md``, ``config/profile.yml`` and ``config/cv-facts.json`` are the
  canonical source of candidate truth, read-only;
* ``verify-cv-facts.mjs`` is the authoritative fact gate (invoked as a
  subprocess, JSON verdict);
* ``generate-cover-letter.mjs`` ``buildHtml`` is the authoritative cover-letter
  renderer (invoked through ``career-ops/cv_render_cover.mjs``);
* ``openai-tailor.mjs`` is the existing LLM tailoring path — this workflow only
  emits the exact, unexecuted request record for it (it sends cv.md and the job
  description to a third-party endpoint, so it stays owner-gated).

Tailoring model
---------------
Deterministic selection only. Bullets are **re-ordered** by job-description
relevance. No canonical line is rewritten, summarised, merged or added. A
posting's terms that the canonical sources do not evidence are reported as
``owner_input_required`` — never written as a claim.

Hard rules
----------
* No fabricated experience, metrics, certifications, clearance, visa status or
  eligibility. A draft that fails the fact gate is marked BLOCKED and its HTML
  is not written.
* No PDF rendering (that launches headless Chromium), no browser, no network.
* No application submission, no employer/recruiter contact, no external message.
* The canonical CV assets and the canonical workbooks are only ever read.

Subcommands
-----------
  sources                         canonical source paths, hashes, gate availability
  job-context  --region R ...     resolve one job record from Career Ops state
  draft        --region R ...     build the tailored CV/cover-letter drafts
  run                             bounded acceptance over safe fixtures

Usage
-----
  python career-ops/cv_workflow.py sources
  python career-ops/cv_workflow.py job-context --region uk --id J21
  python career-ops/cv_workflow.py draft --region uk --id J21 --jd-file jd.txt
  python career-ops/cv_workflow.py run
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
DEFAULT_CONFIG = CAREER_OPS_DIR / "cv_workflow_config.json"

sys.path.insert(0, str(CAREER_OPS_DIR))

import tracker_writer as tw  # noqa: E402
from run_acceptance import parse_pipeline  # noqa: E402

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{2,}")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
BULLET_RE = re.compile(r"^[-*]\s+(.*?)\s*$")


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #

def emit(obj) -> None:
    """Print exactly one JSON object, never failing on a non-UTF-8 console.

    Same contract as ``career_ops_cli.emit``: Windows Task Scheduler redirects
    stdout to a cp1252 file, where a non-Latin job title would otherwise raise
    UnicodeEncodeError *after* the work succeeded.
    """
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = json.dumps(obj, indent=2, ensure_ascii=True, default=str)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path or DEFAULT_CONFIG)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["_config_path"] = str(p)
    return cfg


def install_root(cfg: dict) -> Path:
    return Path(cfg["career_ops_root"])


def source_paths(cfg: dict) -> dict:
    """Absolute canonical source paths inside the Career Ops install."""
    root = install_root(cfg)
    return {key: root / rel for key, rel in cfg["sources"].items()}


def profiles_path(cfg: dict) -> Path:
    return CONTROL_PLANE / cfg["regional_profiles"]


def runtime_dir(cfg: dict) -> Path:
    d = CONTROL_PLANE / cfg["runtime_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# the install's own fact gate
# --------------------------------------------------------------------------- #

def fact_gate(cfg: dict, text: str, *, label: str, scratch: Path) -> dict:
    """Run the install's ``verify-cv-facts.mjs`` over ``text``.

    Returns the gate's verdict document. ``available: false`` is reported
    truthfully when node or the script is missing — the caller must then treat
    the draft as ungated rather than silently as passing.
    """
    paths = source_paths(cfg)
    script = paths["cv_facts"].parent.parent / "verify-cv-facts.mjs"
    node = cfg.get("renderer", {}).get("node", "node")
    if not script.exists():
        return {"available": False, "reason": f"fact gate script not found: {script}"}
    if shutil.which(node) is None:
        return {"available": False, "reason": f"node interpreter not found: {node}"}

    scratch.mkdir(parents=True, exist_ok=True)
    target = scratch / f"factgate-{label}.txt"
    target.write_text(text, encoding="utf-8")
    cmd = [node, str(script), str(target),
           "--source", str(paths["cv_md"]),
           "--source", str(paths["profile"]),
           "--config", str(paths["cv_facts"]),
           "--json"]
    try:
        proc = subprocess.run(cmd, cwd=str(install_root(cfg)), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=int(cfg.get("renderer", {}).get("timeout_s", 180)))
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    payload = None
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if payload is None:
        return {"available": False, "reason": "fact gate produced no JSON verdict",
                "exit_code": proc.returncode, "stderr_tail": (proc.stderr or "")[-500:]}
    payload["available"] = True
    payload["exit_code"] = proc.returncode
    return payload


# --------------------------------------------------------------------------- #
# job records from Career Ops state
# --------------------------------------------------------------------------- #

JOB_FIELDS = ("company", "title", "location", "url", "posted_date", "fit_score",
              "live_status", "key_requirements", "key_responsibilities",
              "job_type", "work_model", "salary")


def tracker_job(profiles: dict, region: str, *, job_id: str | None = None,
                url: str | None = None, row: int | None = None) -> dict | None:
    """Read one job row out of a canonical regional workbook (read-only)."""
    cfg = dict(tw.region_config(profiles, region))
    cfg["region"] = region
    path = Path(cfg["tracker"])
    if not path.exists():
        return None
    tr = tw.Tracker(path, cfg)
    try:
        field_map = cfg.get("field_map", {})
        id_col = cfg["id"]["column"]
        last = tr.last_data_row()
        hit = None
        for r in range(cfg["first_data_row"], last + 1):
            if row is not None and r == row:
                hit = r
                break
            if job_id is not None and str(tr.ws[f"{id_col}{r}"].value or "").strip() == str(job_id):
                hit = r
                break
            if url is not None and tw.normalize_url(tr.ws[f"{cfg['dedupe']['url_column']}{r}"].value) \
                    == tw.normalize_url(url):
                hit = r
                break
        if hit is None:
            return None
        rowdict = tr.row_dict(hit)
        job = {name: rowdict.get(col) for name, col in field_map.items()}
        job["id"] = rowdict.get(id_col)
        job["_row"] = hit
        job["_tracker"] = str(path)
        job["_sheet"] = cfg["sheet"]
        job["_table"] = cfg["table"]
        job["_region"] = region
        job["_source_kind"] = "career-ops-canonical-workbook"
    finally:
        tr.wb.close()
    return job


def pipeline_jobs(cfg: dict) -> list[dict]:
    """Every entry of the scanner's ``data/pipeline.md``, with provenance."""
    path = source_paths(cfg)["pipeline"]
    out = []
    for entry in parse_pipeline(path):
        out.append({
            "company": entry["company"],
            "title": entry["title"],
            "location": entry["location"],
            "url": entry["url"],
            "fit_score": entry["score"],
            "id": None,
            "_pipeline_raw": entry["raw"],
            "_pipeline_notes": entry["tail"],
            "_region": None,
            "_source_kind": "career-ops-pipeline.md",
            "_source_path": str(path),
        })
    return out


def job_from_record(payload: dict, *, source_path: str | None = None) -> dict:
    """Normalise a signal record (e.g. from the LinkedIn workflow) into a job."""
    job = {k: payload.get(k) for k in JOB_FIELDS}
    job["id"] = payload.get("id")
    job["_region"] = payload.get("region")
    job["_source_kind"] = payload.get("source_kind") or "signal-record"
    job["_source_path"] = source_path
    job["_provenance"] = payload.get("provenance")
    job["_signal"] = payload.get("signal")
    return job


def resolve_job(cfg: dict, profiles: dict, *, region: str | None = None,
                job_id: str | None = None, url: str | None = None, row: int | None = None,
                pipeline_index: int | None = None, record_file: str | None = None) -> dict:
    if record_file:
        p = Path(record_file)
        job = job_from_record(json.loads(read_text(p)), source_path=str(p))
        job.setdefault("_region", None)
        if region:
            job["_region"] = region
        return {"ok": True, "job": job, "jd_text": "", "jd_source": None}
    if pipeline_index is not None:
        entries = pipeline_jobs(cfg)
        if not (0 <= pipeline_index < len(entries)):
            return {"ok": False, "reason": f"pipeline index {pipeline_index} out of range "
                                          f"(0..{max(len(entries) - 1, 0)})"}
        return {"ok": True, "job": entries[pipeline_index], "jd_text": "", "jd_source": None}
    if not region:
        return {"ok": False, "reason": "region is required unless --record or --pipeline-index is used"}
    job = tracker_job(profiles, region, job_id=job_id, url=url, row=row)
    if not job:
        return {"ok": False, "reason": "no matching row in the canonical workbook",
                "region": region, "id": job_id, "url": url, "row": row}
    jd_text = ""
    for key in ("key_requirements", "key_responsibilities"):
        value = job.get(key)
        if isinstance(value, str) and value.strip():
            jd_text += ("\n" if jd_text else "") + value.strip()
    return {"ok": True, "job": job, "jd_text": jd_text,
            "jd_source": "canonical workbook requirement columns" if jd_text else None}


# --------------------------------------------------------------------------- #
# deterministic CV selection
# --------------------------------------------------------------------------- #

def parse_cv_markdown(text: str) -> list[dict]:
    """Split the canonical CV markdown into ordered blocks.

    A block starts at every heading. Within a block, lines keep their canonical
    order and carry their 1-based source line number, so provenance survives
    re-ordering.
    """
    sections: list[dict] = []
    current = {"heading": None, "level": 0, "lines": []}
    for no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        m = HEADING_RE.match(stripped)
        if m:
            if current["heading"] is not None or current["lines"]:
                sections.append(current)
            current = {"heading": m.group(2).strip(), "level": len(m.group(1)), "lines": []}
            continue
        if not stripped:
            current["lines"].append({"no": no, "kind": "blank", "text": ""})
            continue
        b = BULLET_RE.match(stripped)
        if b:
            current["lines"].append({"no": no, "kind": "bullet", "text": b.group(1)})
        else:
            current["lines"].append({"no": no, "kind": "text", "text": stripped})
    if current["heading"] is not None or current["lines"]:
        sections.append(current)
    return sections


def _clean_token(token: str) -> str:
    return token.strip("./-,;:()[]\"'").casefold()


def jd_terms(cfg: dict, jd_text: str, exclude: set[str] | None = None) -> list[str]:
    """Job-description terms worth ranking on (deterministic, no model).

    ``exclude`` carries the posting's own company/title vocabulary: those words
    describe which employer the posting belongs to, not what the role requires,
    so reporting them as "terms with no canonical evidence" would be noise.
    """
    generic = {str(t).casefold() for t in cfg.get("tailoring", {}).get("generic_terms", [])}
    exclude = {_clean_token(t) for t in (exclude or set()) if t}
    seen: dict[str, int] = {}
    for raw in WORD_RE.findall(jd_text or ""):
        key = _clean_token(raw)
        if not key or key in generic or key in exclude or key.isdigit() or len(key) < 3:
            continue
        seen[key] = seen.get(key, 0) + 1
    return sorted(seen, key=lambda k: (-seen[k], k))


def term_hits(text: str, terms: list[str]) -> list[str]:
    folded = text.casefold()
    return [t for t in terms if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", folded)]


def reorder_section(section: dict, terms: list[str]) -> dict:
    """Keep lead lines canonical; re-order the bullets by relevance only."""
    scored = []
    for line in section["lines"]:
        score = len(term_hits(line["text"], terms)) if line["text"] else 0
        hits = term_hits(line["text"], terms) if line["text"] else []
        scored.append({**line, "relevance": score, "matched_terms": hits})

    lead = [l for l in scored if l["kind"] != "bullet"]
    bullets = [l for l in scored if l["kind"] == "bullet"]
    ordered_bullets = sorted(bullets, key=lambda l: (-l["relevance"], l["no"]))
    return {"heading": section["heading"], "level": section["level"],
            "lines": lead + ordered_bullets,
            "bullets_reordered": [l["no"] for l in ordered_bullets] != [l["no"] for l in bullets]}


def build_cv_draft(cfg: dict, cv_text: str, terms: list[str], *, job: dict) -> dict:
    sections = parse_cv_markdown(cv_text)
    out_sections = [reorder_section(s, terms) for s in sections]

    lines: list[str] = []
    provenance: list[dict] = []
    header = [
        "<!--",
        "  CAREER OPS CV DRAFT — generated by career-ops/cv_workflow.py",
        f"  generated_at: {now_utc()}",
        f"  posting: {job.get('title') or 'unknown title'}",
        f"  tailoring: bullet order ranked by job-description relevance",
        "  NO canonical text was rewritten, summarised, merged or added.",
        "  This is a DRAFT for owner review. Nothing was submitted or sent.",
        "-->",
        "",
    ]
    lines.extend(header)
    for section in out_sections:
        if section["heading"] is not None:
            lines.append(f"{'#' * section['level']} {section['heading']}")
        for line in section["lines"]:
            if line["kind"] == "blank":
                lines.append("")
                continue
            lines.append(f"- {line['text']}" if line["kind"] == "bullet" else line["text"])
            provenance.append({
                "draft_line": len(lines),
                "source": "cv.md",
                "source_line": line["no"],
                "kind": line["kind"],
                "section": section["heading"],
                "text": line["text"],
                "relevance": line["relevance"],
                "matched_terms": line["matched_terms"],
            })
    return {"text": "\n".join(lines) + "\n", "provenance": provenance,
            "sections": [s["heading"] for s in out_sections],
            "bullets_total": sum(1 for s in sections for l in s["lines"] if l["kind"] == "bullet"),
            "bullets_reordered_sections": [s["heading"] for s in out_sections if s["bullets_reordered"]]}


# --------------------------------------------------------------------------- #
# cover-letter draft (existing renderer contract)
# --------------------------------------------------------------------------- #

def profile_facts(cfg: dict) -> dict:
    """Candidate contact/credential facts, read from the canonical sources."""
    paths = source_paths(cfg)
    facts: dict = {"credentials": []}
    profile_text = read_text(paths["profile"])
    try:
        import yaml  # noqa: PLC0415
        doc = yaml.safe_load(profile_text) or {}
        candidate = doc.get("candidate") or {}
        for key in ("full_name", "email", "phone", "location", "linkedin", "github"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                facts[key] = value.strip()
        facts["_profile_sha256"] = sha256_text(profile_text)
    except ImportError:
        facts["_profile_sha256"] = sha256_text(profile_text)
        facts["_profile_parse"] = "PyYAML unavailable"

    cv_text = read_text(paths["cv_md"])
    in_certs = False
    for line in cv_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_certs = stripped.casefold().startswith("## certifications")
            continue
        if in_certs and stripped:
            facts["credentials"] = [c.strip() for c in stripped.split("|") if c.strip()]
            break
    return facts


def canonical_profile_paragraph(cv_text: str) -> str:
    sections = parse_cv_markdown(cv_text)
    for section in sections:
        if (section["heading"] or "").casefold() == "profile":
            parts = [l["text"] for l in section["lines"] if l["kind"] == "text" and l["text"]]
            if parts:
                return " ".join(parts)
    return ""


def build_cover_payload(cfg: dict, *, job: dict, jd_text: str, facts: dict,
                        evidence_bullets: list[dict], unmatched_terms: list[str]) -> dict:
    """Build a payload for the install's own ``generate-cover-letter.mjs``.

    Only structural connective text (the application sentence, the closing, the
    valediction) is written by this function; every substantive sentence is
    reproduced verbatim from the canonical sources and carries a source ref.
    """
    title = (job.get("title") or "").strip()
    company = (job.get("company") or "").strip()
    location = (job.get("location") or "").strip()
    city = location.split(",")[0].strip() if location else ""

    opening = (f"I am writing to apply for the {title} position at {company}."
               if title and company else
               "I am writing to apply for this position.")
    profile_intro = canonical_profile_paragraph(read_text(source_paths(cfg)["cv_md"]))

    footnotes: list[dict] = []
    if evidence_bullets:
        footnotes.append({"marker": "", "text":
                          "Supporting evidence, reproduced verbatim from the canonical CV "
                          "(no rewriting; source line shown):"})
        for b in evidence_bullets:
            footnotes.append({"marker": "", "text": f"{b['text']}  [cv.md:{b['source_line']}]"})

    gaps = []
    if not jd_text.strip():
        gaps.append("No job-description text is available from Career Ops for this posting; "
                    "paste the posting text before sending so keyword coverage is real.")
    if unmatched_terms:
        gaps.append("Posting terms with no canonical evidence: "
                    + ", ".join(unmatched_terms)
                    + " — do not claim these; add real evidence or leave them out.")
    gaps.append("DRAFT ONLY — owner review required. No application has been submitted and "
                "nothing has been sent to the employer.")
    problems_section = " ".join(gaps)

    payload = {
        "status": "draft_unreviewed",
        "generated_at": now_utc(),
        "generator": "career-ops/cv_workflow.py",
        "candidate": {
            "name": facts.get("full_name", ""),
            "email": facts.get("email", ""),
            "phone": facts.get("phone", ""),
            "location": facts.get("location", ""),
            "linkedin": facts.get("linkedin", ""),
            "github": facts.get("github", ""),
            "credentials": facts.get("credentials", []),
        },
        "letter": {
            "company": company,
            "city": city,
            "role_title": title,
            "date": dt.date.today().isoformat(),
            "opening": opening,
            "profile_intro": profile_intro,
            "problems_section": problems_section,
            "closing": "Thank you for considering this application.",
            "signature": {"valediction": "Sincerely,", "name": facts.get("full_name", "")},
            "footnotes": footnotes,
        },
        "provenance": {
            "posting": {"title": title, "company": company, "region": job.get("_region"),
                        "job_id": job.get("id"), "source_kind": job.get("_source_kind"),
                        "url": job.get("url")},
            "verbatim_sources": {
                "cv.md": sha256_file(source_paths(cfg)["cv_md"]),
                "config/profile.yml": sha256_file(source_paths(cfg)["profile"]),
                "config/cv-facts.json": sha256_file(source_paths(cfg)["cv_facts"]),
            },
            "rewrite_policy": "structural connective text only; all substantive text verbatim",
        },
        "owner_input_required": gaps,
    }
    return payload


# --------------------------------------------------------------------------- #
# the draft command
# --------------------------------------------------------------------------- #

def build_drafts(cfg: dict, profiles: dict, *, job: dict, jd_text: str,
                 jd_source: str | None, stamp: str, run_dir: Path | None = None) -> dict:
    run_dir = run_dir or (runtime_dir(cfg) / stamp)
    scratch = run_dir / "factgate"
    run_dir.mkdir(parents=True, exist_ok=True)

    paths = source_paths(cfg)
    cv_text = read_text(paths["cv_md"])
    posting_words = set(WORD_RE.findall(f"{job.get('company') or ''} {job.get('title') or ''}"))
    terms = jd_terms(cfg, jd_text, exclude=posting_words)

    cv_draft = build_cv_draft(cfg, cv_text, terms, job=job)

    # Evidence bullets for the letter: canonical bullets with the strongest real
    # overlap with the posting, taken verbatim.
    line_index = {l["no"]: l["text"] for s in parse_cv_markdown(cv_text) for l in s["lines"]}
    bullets = [p for p in cv_draft["provenance"] if p["kind"] == "bullet" and p["relevance"] > 0]
    bullets.sort(key=lambda p: (-p["relevance"], p["source_line"]))
    evidence = [{"text": line_index[p["source_line"]], "source_line": p["source_line"],
                 "matched_terms": p["matched_terms"]}
                for p in bullets[:4]]

    # Terms the posting uses that nothing in the canonical sources evidences.
    source_text = cv_text + "\n" + read_text(paths["profile"])
    max_terms = int(cfg.get("tailoring", {}).get("max_reported_unmatched_terms", 25))
    unmatched = [t for t in terms if len(t) >= 4 and not term_hits(source_text, [t])][:max_terms]

    facts = profile_facts(cfg)
    payload = build_cover_payload(cfg, job=job, jd_text=jd_text, facts=facts,
                                  evidence_bullets=evidence, unmatched_terms=unmatched)

    # ---- write artifacts, then gate them -------------------------------- #
    cv_path = run_dir / "cv_draft.md"
    cv_path.write_text(cv_draft["text"], encoding="utf-8")
    (run_dir / "cv_draft_provenance.json").write_text(
        json.dumps({"generated_at": now_utc(), "job": {"title": job.get("title"),
                                                       "company": job.get("company")},
                    "jd_terms_ranked": terms[:60], "lines": cv_draft["provenance"]},
                   indent=2, ensure_ascii=False), encoding="utf-8")

    payload_path = run_dir / "cover_letter_payload.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    letter_text = "\n".join(str(payload["letter"].get(k) or "") for k in
                            ("opening", "profile_intro", "problems_section", "closing"))
    letter_text += "\n" + "\n".join(f["text"] for f in payload["letter"]["footnotes"])

    cv_gate = fact_gate(cfg, cv_draft["text"], label="cv", scratch=scratch)
    letter_gate = fact_gate(cfg, letter_text, label="cover", scratch=scratch)

    gate_ok = all(not (g.get("available") and g.get("verdict") == "block")
                  for g in (cv_gate, letter_gate))

    render = {"rendered": False, "reason": "fact gate blocked the draft"}
    html_path = run_dir / "cover_letter_draft.html"
    if gate_ok:
        render = render_cover(cfg, payload_path, html_path)

    next_step = None
    if gate_ok and render.get("rendered"):
        slug = re.sub(r"[^a-z0-9]+", "-", (job.get("company") or "company").casefold()).strip("-")
        role = re.sub(r"[^a-z0-9]+", "-", (job.get("title") or "role").casefold()).strip("-")[:30]
        next_step = (f'node generate-cover-letter.mjs --payload "{payload_path}" '
                     f'--out output/drafts/{stamp}/{slug}-{role}-cover.pdf   '
                     f"(run from {install_root(cfg)}; launches headless Chromium, so it is "
                     f"owner-gated and NOT run here)")

    result = {
        "ok": bool(gate_ok),
        "status": "draft_ready_for_owner_review" if gate_ok else "blocked_fact_gate",
        "run_dir": str(run_dir),
        "generated_at": now_utc(),
        "job": {k: v for k, v in job.items() if not k.startswith("_")} | {
            "source_kind": job.get("_source_kind"), "source_path": job.get("_source_path")},
        "job_description": {
            "available": bool(jd_text.strip()),
            "source": jd_source,
            "chars": len(jd_text),
            "terms_ranked": len(terms),
            "terms_absent_from_canonical_sources": unmatched,
        },
        "cv_draft": {
            "path": str(cv_path),
            "sha256": sha256_file(cv_path),
            "sections": cv_draft["sections"],
            "bullets_total": cv_draft["bullets_total"],
            "sections_with_reordered_bullets": cv_draft["bullets_reordered_sections"],
            "provenance_path": str(run_dir / "cv_draft_provenance.json"),
            "rewriting": "none — selection/reordering of canonical lines only",
        },
        "cover_letter": {
            "payload_path": str(payload_path),
            "html_path": str(html_path) if render.get("rendered") else None,
            "render": render,
            "evidence_bullets": len(evidence),
        },
        "fact_gate": {"cv_draft": cv_gate, "cover_letter": letter_gate},
        "owner_input_required": payload["owner_input_required"],
        "next_step_owner_gated": next_step,
        "llm_tailor_request": {
            "executed": False,
            "reason": "sends cv.md and the job description to a third-party endpoint; "
                      "requires a provider key and explicit owner authorization",
            "command": (f'node openai-tailor.mjs --jd <jd.txt> --report <report.md>   '
                        f"(run from {install_root(cfg)}; set OPENAI_API_KEY/OPENAI_BASE_URL/"
                        f"OPENAI_MODEL first)"),
        },
        "not_performed": cfg.get("not_performed", []),
        "external_actions_taken": [],
    }
    (run_dir / "draft_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def render_cover(cfg: dict, payload_path: Path, html_path: Path) -> dict:
    """Render the payload through the install's own buildHtml + fact gate."""
    rcfg = cfg.get("renderer", {})
    node = rcfg.get("node", "node")
    script = CONTROL_PLANE / rcfg.get("script", "career-ops/cv_render_cover.mjs")
    if not script.exists():
        return {"rendered": False, "reason": f"renderer driver not found: {script}"}
    if shutil.which(node) is None:
        return {"rendered": False, "reason": f"node interpreter not found: {node}"}
    paths = source_paths(cfg)
    cmd = [node, str(script), "--install", str(install_root(cfg)),
           "--payload", str(payload_path), "--out", str(html_path),
           "--source", str(paths["cv_md"]), "--source", str(paths["profile"]),
           "--config", str(paths["cv_facts"])]
    try:
        proc = subprocess.run(cmd, cwd=str(CONTROL_PLANE), capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=int(rcfg.get("timeout_s", 180)))
    except (OSError, subprocess.SubprocessError) as exc:
        return {"rendered": False, "reason": f"{type(exc).__name__}: {exc}"}
    payload = None
    for line in reversed((proc.stdout or "").strip().splitlines()):
        if line.strip().startswith("{"):
            try:
                payload = json.loads(line.strip())
                break
            except json.JSONDecodeError:
                continue
    if payload is None:
        return {"rendered": False, "reason": "renderer produced no JSON",
                "exit_code": proc.returncode, "stderr_tail": (proc.stderr or "")[-500:]}
    payload["exit_code"] = proc.returncode
    return payload


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_sources(args) -> int:
    cfg = load_config(args.config)
    paths = source_paths(cfg)
    root = install_root(cfg)
    out = {
        "generated_at": now_utc(),
        "config": cfg["_config_path"],
        "career_ops_root": str(root),
        "career_ops_root_exists": root.exists(),
        "sources": {},
        "node_available": shutil.which(cfg.get("renderer", {}).get("node", "node")) is not None,
        "renderer_driver": str(CONTROL_PLANE / cfg.get("renderer", {}).get("script", "")),
    }
    for key, p in paths.items():
        out["sources"][key] = {"path": str(p), "exists": p.exists(),
                               "sha256": sha256_file(p) if p.exists() else None}
    out["fact_gate_script"] = str(root / "verify-cv-facts.mjs")
    out["fact_gate_ready"] = (root / "verify-cv-facts.mjs").exists() and out["node_available"]
    out["canonical_workbooks_opened"] = False
    out["writes_performed"] = []
    emit(out)
    return 0


def _job_and_jd(args, cfg, profiles):
    resolved = resolve_job(cfg, profiles, region=args.region, job_id=args.id, url=args.url,
                           row=args.row, pipeline_index=args.pipeline_index,
                           record_file=args.record)
    if not resolved.get("ok"):
        return resolved
    jd_text = resolved.get("jd_text") or ""
    jd_source = resolved.get("jd_source")
    if args.jd_file:
        p = Path(args.jd_file)
        if not p.exists():
            return {"ok": False, "reason": f"job description file not found: {p}"}
        jd_text = read_text(p)
        jd_source = f"explicit file {p}"
    resolved["jd_text"] = jd_text
    resolved["jd_source"] = jd_source
    return resolved


def cmd_job_context(args) -> int:
    cfg = load_config(args.config)
    profiles = tw.load_profiles(str(profiles_path(cfg)))
    resolved = _job_and_jd(args, cfg, profiles)
    if not resolved.get("ok"):
        emit(resolved)
        return 1
    job = resolved["job"]
    out = {
        "ok": True,
        "generated_at": now_utc(),
        "job": {k: v for k, v in job.items() if not k.startswith("_")} | {
            "source_kind": job.get("_source_kind"), "source_path": job.get("_source_path")},
        "missing_fields": [k for k in ("company", "title", "location", "url")
                           if not job.get(k)],
        "job_description": {
            "available": bool(resolved["jd_text"].strip()),
            "source": resolved["jd_source"],
            "chars": len(resolved["jd_text"]),
            "head": resolved["jd_text"].strip()[:600],
        },
        "provenance": {"resolver": "career-ops/cv_workflow.py",
                       "canonical_profiles": str(profiles_path(cfg)),
                       "region": job.get("_region"),
                       "tracker": job.get("_tracker")},
        "writes_performed": [],
    }
    if args.record:
        p = Path(args.record).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        out["recorded_to"] = str(p)
    emit(out)
    return 0


def cmd_draft(args) -> int:
    cfg = load_config(args.config)
    profiles = tw.load_profiles(str(profiles_path(cfg)))
    resolved = _job_and_jd(args, cfg, profiles)
    if not resolved.get("ok"):
        emit(resolved)
        return 1
    stamp = args.stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(args.out) if args.out else (runtime_dir(cfg) / stamp)
    result = build_drafts(cfg, profiles, job=resolved["job"], jd_text=resolved["jd_text"],
                          jd_source=resolved["jd_source"], stamp=stamp, run_dir=run_dir)
    emit(result)
    return 0 if result["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chief <-> Career Ops CV / cover-letter draft workflow")
    ap.add_argument("--config", default=None, help="path to cv_workflow_config.json")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sources"); p.set_defaults(fn=cmd_sources)

    for name, fn in (("job-context", cmd_job_context), ("draft", cmd_draft)):
        p = sub.add_parser(name)
        p.add_argument("--region")
        p.add_argument("--id")
        p.add_argument("--url")
        p.add_argument("--row", type=int)
        p.add_argument("--pipeline-index", type=int)
        p.add_argument("--record")
        p.add_argument("--jd-file")
        p.add_argument("--out")
        p.add_argument("--stamp")
        p.set_defaults(fn=fn)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
