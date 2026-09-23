#!/usr/bin/env python3
"""Company Watch — canonical watched-company registry.

Builds the Company Watch watch-list from the *historical evidence that already
exists*, instead of inventing organisations. The single source is the recorded
Gmail-derived company history:

    C:\\Users\\mukun\\Documents\\ChatGPT\\CV customizer\\
        uk_application_company_history_18_months.md

That file is owner-private data and is **not** copied into this repository. This
module records its SHA-256 and the parsed structure, and writes the full
company-level registry to a local runtime path (git-ignored). Only aggregate
counts and provenance ever travel to GitHub.

Truth rules enforced here:

* a company exists in the registry only if it appears in the source file;
* the source file's own declared summary counts are parsed and compared with the
  parsed counts — a mismatch is surfaced as an explicit ``count_mismatch`` entry
  rather than being silently reconciled;
* "unverified candidate" rows (candidate account created / no submission
  confirmation found) are kept, but flagged ``prior_application_evidence: false``
  because the source file does not evidence an application.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_SOURCE = Path(
    r"C:\Users\mukun\Documents\ChatGPT\CV customizer\uk_application_company_history_18_months.md"
)

SCHEMA_VERSION = 1

# (heading fragment, evidence_class, prior_application_evidence)
SECTIONS = [
    ("confirmed or strongly evidenced employers", "employer", True),
    ("recruiters and intermediaries", "recruiter", True),
    ("other applications kept separate", "other_application", True),
    ("possible applications needing verification", "unverified_candidate", False),
]

DECLARED_RE = re.compile(r"\*\*(?P<label>[^:*]+):\*\*\s*(?P<count>\d+)")
BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<body>.+?)\s*$")

LEGAL_SUFFIXES = (
    "limited", "ltd", "plc", "group", "holdings", "holding", "technologies",
    "technology", "inc", "incorporated", "corporation", "corp", "llp", "sa", "nv",
)

#: Words that carry no discriminating power when matching a board name to a
#: registry name. Kept deliberately short and explicit.
NOISE_TOKENS = {"the", "and", "of", "for", "services", "solutions", "global", "uk", "group"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_name(value: str) -> str:
    """Casefold and strip everything that is not a letter or digit."""
    return re.sub(r"[^0-9a-z]+", "", (value or "").casefold())


def name_variants(name: str) -> list[str]:
    """Discriminating name forms for a registry company.

    ``AVEVA / ETAP / RIB`` yields the whole string plus each alternative, so a
    board whose payload says ``AVEVA`` can be attributed. Punctuation-only
    differences are absorbed by :func:`normalize_name`.
    """
    parts = [p.strip() for p in re.split(r"[/()]", name or "") if p.strip()]
    variants = []
    whole = normalize_name(name)
    if whole:
        variants.append(whole)
    for part in parts:
        norm = normalize_name(part)
        if len(norm) >= 2 and norm not in variants:
            variants.append(norm)
    return variants


def slug_candidates(name: str) -> list[str]:
    """Deterministic ATS-slug *guesses* derived from the company name only.

    A slug guess is never evidence of attribution — it only decides which public
    board URL is probed. See :func:`ats_endpoints.resolve_company`, which
    requires independent name confirmation before a board is trusted.
    """
    first = re.split(r"[/()]", name or "")[0]
    base = normalize_name(first)
    if not base:
        return []
    out = [base]
    for suffix in LEGAL_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix) + 2:
            out.append(base[: -len(suffix)])
            break
    return out[:2]


def parse_source(path: Path) -> dict:
    """Parse the historical company-history markdown into structured rows."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    companies: list[dict] = []
    sections_found: list[dict] = []
    current: tuple[str, str, bool] | None = None

    for line in lines:
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            current = None
            for fragment, cls, prior in SECTIONS:
                if fragment in heading:
                    current = (cls, line.lstrip("#").strip(), prior)
                    break
            continue
        if current is None:
            continue
        m = BULLET_RE.match(line)
        if not m:
            continue
        body = m.group("body")
        # A company may carry an explanatory clause after an em/en dash.
        parts = re.split(r"\s+[—–]\s+", body, maxsplit=1)
        name = parts[0].strip()
        note = parts[1].strip() if len(parts) > 1 else None
        if not name:
            continue
        cls, section_title, prior = current
        companies.append({
            "name": name,
            "evidence_class": cls,
            "prior_application_evidence": prior,
            "evidence_note": note,
            "source_section": section_title,
        })

    for cls, title, _prior in SECTIONS:
        rows = [c for c in companies if c["source_section"] == title]
        sections_found.append({"section": title, "evidence_class": cls, "parsed": len(rows)})

    declared: dict[str, int] = {}
    for m in DECLARED_RE.finditer(text):
        label = m.group("label").strip()
        if label.casefold() in {"period", "mailbox reviewed", "scope", "method"}:
            continue
        declared[label] = int(m.group("count"))

    # mailbox / period breadcrumbs, recorded as provenance only
    mailbox = re.search(r"\*\*Mailbox reviewed:\*\*\s*(\S+)", text)
    period = re.search(r"\*\*Period:\*\*\s*(.+)", text)

    return {
        "companies": companies,
        "sections": sections_found,
        "declared": declared,
        "mailbox": mailbox.group(1) if mailbox else None,
        "period": period.group(1).strip() if period else None,
    }


def _declared_lookup(declared: dict, fragment: str) -> int | None:
    for label, count in declared.items():
        if fragment in label.casefold():
            return count
    return None


def build_registry(source: Path = DEFAULT_SOURCE, generated_at: str | None = None) -> dict:
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"company history source not found: {source}")

    parsed = parse_source(source)
    companies = parsed["companies"]

    by_class: dict[str, int] = {}
    for c in companies:
        by_class[c["evidence_class"]] = by_class.get(c["evidence_class"], 0) + 1

    employers = by_class.get("employer", 0)
    recruiters = by_class.get("recruiter", 0)
    other = by_class.get("other_application", 0)
    unverified = by_class.get("unverified_candidate", 0)
    # The source keeps "other applications" (mentorship / volunteering / academy /
    # programme enquiries) separate from the job-search total, so the
    # application/CV-evidence total is employers + recruiters only. Deriving it
    # any other way would overstate the evidence base.
    with_evidence = employers + recruiters

    declared = parsed["declared"]
    declared_checks = {
        "confirmed_employers": (_declared_lookup(declared, "employers"), employers),
        "recruiters": (_declared_lookup(declared, "recruiters"), recruiters),
        "other_applications": (_declared_lookup(declared, "other"), other),
        "unverified_candidates": (_declared_lookup(declared, "verification"), unverified),
        "organizations_with_application_or_cv_evidence": (
            _declared_lookup(declared, "total job-search organisations"), with_evidence),
    }
    count_mismatch = {
        key: {"declared": d, "parsed": p}
        for key, (d, p) in declared_checks.items()
        if d is not None and d != p
    }

    registry_companies = []
    for c in companies:
        registry_companies.append({
            **c,
            "name_variants": name_variants(c["name"]),
            "ats_slug_candidates": slug_candidates(c["name"]),
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or now_utc(),
        "owner_data": True,
        "storage_note": (
            "Full company-level registry is owner-private job-search history. It is written "
            "to a local git-ignored runtime path; only aggregate counts and provenance are "
            "committed to the shared control plane."
        ),
        "source": {
            "path": str(source),
            "sha256": sha256_file(source),
            "mailbox": parsed["mailbox"],
            "period": parsed["period"],
            "bytes": source.stat().st_size,
            "note": "historical Gmail-derived evidence; re-verified by re-parsing this file",
        },
        "counts": {
            "parsed_total_rows": len(companies),
            "parsed_employers": employers,
            "parsed_recruiters": recruiters,
            "parsed_other_applications": other,
            "parsed_unverified_candidates": unverified,
            "parsed_organizations_with_application_or_cv_evidence": with_evidence,
            "parsed_by_class": by_class,
            "declared_in_source": declared,
            "declared_vs_parsed": {k: {"declared": d, "parsed": p} for k, (d, p) in declared_checks.items()},
            "count_mismatch": count_mismatch,
        },
        "companies": registry_companies,
    }


def summary(registry: dict) -> dict:
    """Aggregate view safe to commit (no company names)."""
    counts = registry["counts"]
    return {
        "schema_version": registry["schema_version"],
        "generated_at": registry["generated_at"],
        "source_path": registry["source"]["path"],
        "source_sha256": registry["source"]["sha256"],
        "source_period": registry["source"]["period"],
        "counts": counts,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Company Watch canonical registry")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--out", default=None, help="where to write the full registry JSON")
    ap.add_argument("--summary-out", default=None, help="where to write the committable summary")
    args = ap.parse_args(argv)

    registry = build_registry(Path(args.source))
    payload = registry if args.out is None else None

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.summary_out:
        s = Path(args.summary_out)
        s.parent.mkdir(parents=True, exist_ok=True)
        s.write_text(json.dumps(summary(registry), indent=2, ensure_ascii=False), encoding="utf-8")

    doc = summary(registry)
    doc["written_to"] = args.out
    doc["summary_written_to"] = args.summary_out
    json.dump(doc, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if not registry["counts"]["count_mismatch"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
