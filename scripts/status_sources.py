#!/usr/bin/env python3
"""Shared, read-only reader/validator for the canonical project-status source.

Single truth hierarchy for project status:

    status/canonical-status.json          <- the one canonical machine-readable source
        |
        +-- status/executive-tracker.md                 (GENERATED)
        +-- README.md                                     (GENERATED block)
        +-- state/current_company_state.md                (GENERATED block)
        +-- state/full_build_tracker.md                   (GENERATED block)

Nothing here writes. Every function reads repository artifacts only: no network
call, no provider call, no credential value, no private runtime database.

The checks in this module are what make the generated documents *verifiable*
rather than merely consistent with themselves: the figures in the canonical
source are compared against the recorded evidence artifacts they name, so a
stale or edited number fails rather than silently drifting.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_PATH = REPO_ROOT / "status" / "canonical-status.json"
EVIDENCE_ROOT = REPO_ROOT / "audits" / "evidence"
EXECUTIVE_TRACKER_PATH = REPO_ROOT / "status" / "executive-tracker.md"

MARKER_BEGIN = "<!-- BEGIN GENERATED: executive-status (scripts/status_render.py) -->"
MARKER_END = "<!-- END GENERATED: executive-status (scripts/status_render.py) -->"

# The production blockers the authority file requires to be represented
# explicitly and separately from implementation completion.
REQUIRED_PRODUCTION_BLOCKERS = {
    "provider-credentials-absent",
    "stage2-not-enabled",
    "live-provider-failover-gap",
    "deployment-cutover-decision",
    "offsite-backup-absent",
    "battery-gating",
    "reboot-persistence-unverified",
    "laptop-trust-audit",
}

# Owner-gated / feature-gated items that must NOT be labelled core production
# blockers unless the documented product scope actually requires them.
REQUIRED_OPTIONAL_GATED = {
    "gmail-readonly-oauth",
    "research-provider",
    "linkedin-live-account",
    "recruiter-live-feed",
    "regional-work-authorisation",
}

# Evidence paths the canonical source is expected to cite. Kept explicit so a
# reference is never dropped silently.
REFERENCED_EVIDENCE_PATHS = [
    "audits/evidence/2026-09-24T15-35-35Z-canonical-status-verification/evidence.json",
    "audits/evidence/2026-09-24T15-45-00Z-isolated-release-reproducibility/evidence.json",
    "audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/e4e5-drills/evidence.json",
    "audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/roster_account.json",
    "audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/regression/evidence.json",
    "audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/credential-presence/evidence.json",
    "audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/deployment-preflight/preflight.json",
    "audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/backup-restore/backup_restore_report.json",
    "audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/persistence/persistence.json",
    "audits/evidence/2026-09-24T04-58-25Z-career-high-recall-discovery",
    "audits/evidence/20260924T053909Z-career-high-recall-discovery-acceptance",
    "audits/evidence/2026-09-24T13-22-22Z-career-open-web-research",
    "audits/evidence/2026-09-24T13-58-06Z-career-priority-watchlist",
    "audits/evidence/2026-09-24T14-39-12Z-career-scheduled-orchestrator-cutover/evidence.json",
    "audits/evidence/2026-09-23T22-53-53Z-e3-stage2-readiness-gate-verdict",
    "audits/evidence/2026-09-23T21-32-41Z-e3-production-execution-rehearsal/evidence.json",
    "career-ops/evidence/acceptance-20260924T001500Z.json",
    "tasks-or-issues/overnight-owner-actions-2026-09-24.md",
]

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r'"password"\s*:'),
    re.compile(r'"api_key"\s*:\s*"[^"]+"'),
    re.compile(r'"client_secret"\s*:\s*"[^"]+"'),
]


# --------------------------------------------------------------------------- #
# loading helpers
# --------------------------------------------------------------------------- #
def repo_path(rel: str) -> Path:
    """Resolve a repository-relative path (tolerating a trailing slash)."""
    parts = [p for p in str(rel).rstrip("/").split("/") if p]
    return REPO_ROOT.joinpath(*parts)


def read_json(rel: str) -> dict:
    p = repo_path(rel)
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_canonical(path: Path | None = None) -> dict:
    p = Path(path) if path is not None else CANONICAL_PATH
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def canonical_text() -> str:
    return CANONICAL_PATH.read_text(encoding="utf-8")


def normalise(text: str) -> str:
    """Newline- and trailing-whitespace-insensitive comparison form."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip("\n")


def read_source(path: Path) -> str:
    """Read a worktree file without newline translation."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def extract_block(text: str) -> str | None:
    """Return the generated block (markers stripped) or None when absent."""
    start = text.find(MARKER_BEGIN)
    end = text.find(MARKER_END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start + len(MARKER_BEGIN):end]


def git_head() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_object_exists(sha: str) -> bool:
    try:
        out = subprocess.run(["git", "cat-file", "-e", sha], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=60)
    except Exception:
        return False
    return out.returncode == 0


def git_is_ancestor(sha: str, ref: str = "HEAD") -> bool:
    try:
        out = subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref],
                             cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
    except Exception:
        return False
    return out.returncode == 0


def newer_evidence_dirs(as_of: str) -> list[str]:
    """Evidence directory stamps strictly newer than `as_of`.

    Directory stamps look like ``2026-09-24T15-45-00Z-<label>`` or
    ``20260924T053909Z-<label>``; both are normalised to ``YYYYMMDDTHHMMSS``.
    """
    if not EVIDENCE_ROOT.is_dir():
        return []
    cutoff = _normalise_stamp(as_of)
    if cutoff is None:
        return []
    newer: list[str] = []
    for child in sorted(EVIDENCE_ROOT.iterdir()):
        if not child.is_dir() or child.name == "superseded":
            continue
        candidate = _normalise_stamp(child.name)
        if candidate is not None and candidate > cutoff:
            newer.append(child.name)
    return newer


def _normalise_stamp(value: str) -> str | None:
    """Normalise a stamp (dir name or ISO Z) to YYYYMMDDTHHMMSS for comparison."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})Z", value)
    if m:
        return "".join(m.groups())
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z", value)
    if m:
        return "".join(m.groups())
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", value)
    if m:
        return "".join(m.groups())
    return None


# --------------------------------------------------------------------------- #
# checks — each returns a list of (level, message)
# --------------------------------------------------------------------------- #
def check_required_keys(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    required = [
        "schema_version", "as_of", "code_identity", "latest_evidence",
        "executive_brain", "roster", "regressions", "career_discovery",
        "queue_service", "provider_credentials", "stage2", "deployment",
        "production_blockers", "optional_gated", "unknowns", "history",
    ]
    for key in required:
        if key not in canonical:
            problems.append(("FAIL", f"canonical status is missing required section `{key}`"))
    for phase in ("E1", "E2", "E3", "E4", "E5"):
        if phase not in canonical.get("executive_brain", {}):
            problems.append(("FAIL", f"canonical status is missing Executive Brain phase `{phase}`"))
    return problems


def check_evidence_references() -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    for rel in REFERENCED_EVIDENCE_PATHS:
        if not repo_path(rel).exists():
            problems.append(("FAIL", f"referenced evidence path does not exist: {rel}"))
    for entry in load_canonical().get("history", []):
        rel = f"audits/evidence/{entry['id']}"
        if not repo_path(rel).exists():
            problems.append(("FAIL", f"history entry evidence directory does not exist: {rel}"))
    return problems


def check_code_identity(canonical: dict) -> list[tuple[str, str]]:
    """The recorded commit SHAs must be real objects in this repository."""
    problems: list[tuple[str, str]] = []
    ci = canonical["code_identity"]
    for key in ("authoring_head_sha", "verified_evidence_sha"):
        sha = ci.get(key)
        if not sha:
            problems.append(("FAIL", f"code_identity.{key} is missing"))
        elif not git_object_exists(sha):
            problems.append(("FAIL", f"code_identity.{key} {sha} is not a git object in this repository"))
    return problems


def check_latest_evidence(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    ev = read_json(canonical["code_identity"]["source"]["path"])
    latest = canonical["latest_evidence"]
    if ev.get("code_sha") != latest.get("code_sha"):
        problems.append(("FAIL", "latest_evidence.code_sha disagrees with the evidence artifact"))
    if ev.get("code_sha") != canonical["code_identity"]["verified_evidence_sha"]:
        problems.append(("FAIL", "code_identity.verified_evidence_sha disagrees with the evidence artifact"))
    finished = (ev.get("run_finished_utc") or "")[:19] + "Z"
    if finished != canonical["as_of"]:
        problems.append(("FAIL", f"as_of {canonical['as_of']} != newest evidence run_finished {finished}"))
    if latest.get("run_finished_utc") != canonical["as_of"]:
        problems.append(("FAIL", "latest_evidence.run_finished_utc disagrees with as_of"))
    return problems


def check_regression(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    ev = read_json(canonical["code_identity"]["source"]["path"])
    summary = ev.get("unittest_summary", {})
    reg = canonical["regressions"]
    for key, art_key in (("suites_run", "suites_run"), ("suites_passed", "suites_passed"),
                         ("suites_failed", "suites_failed"), ("suites_unavailable", "suites_unavailable"),
                         ("tests_collected", "tests_collected"), ("tests_passed", "tests_passed")):
        if summary.get(art_key) != reg.get(key):
            problems.append(("FAIL", f"regressions.{key}={reg.get(key)} != evidence {summary.get(art_key)}"))
    if reg.get("tests_failed"):
        problems.append(("FAIL", "canonical status records failed tests"))
    return problems


def check_roster(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    account = read_json(canonical["roster"]["source"]["path"])
    roster = account["roster"]
    counts = {"PASS": 0, "READY_NEEDS_OWNER_CONFIG": 0, "BLOCKED_EXTERNAL": 0}
    for row in roster:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    declared = canonical["roster"]
    total = declared["pass"] + declared["ready_needs_owner_config"] + declared["blocked_external"]
    if total != declared["total"] or len(roster) != declared["total"]:
        problems.append(("FAIL", "roster totals disagree with roster_account.json"))
    if counts["PASS"] != declared["pass"]:
        problems.append(("FAIL", "roster PASS count disagrees with roster_account.json"))
    if counts["READY_NEEDS_OWNER_CONFIG"] != declared["ready_needs_owner_config"]:
        problems.append(("FAIL", "roster READY_NEEDS_OWNER_CONFIG count disagrees with roster_account.json"))
    if counts["BLOCKED_EXTERNAL"] != declared["blocked_external"]:
        problems.append(("FAIL", "roster BLOCKED_EXTERNAL count disagrees with roster_account.json"))
    expected_non_pass = {r["id"] for r in roster if r["status"] != "PASS"}
    declared_non_pass = {r["id"] for r in declared["non_pass_items"]}
    if expected_non_pass != declared_non_pass:
        problems.append(("FAIL", f"non-PASS roster items disagree: evidence {sorted(expected_non_pass)} vs declared {sorted(declared_non_pass)}"))
    return problems


def check_credentials(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    ev = read_json(canonical["provider_credentials"]["source"]["path"])
    creds = canonical["provider_credentials"]
    if ev.get("still_missing_count") != creds["credentials_absent"]:
        problems.append(("FAIL", "credentials_absent disagrees with the presence probe"))
    if sorted(ev.get("still_missing_workers", [])) != sorted(creds["absent_workers"]):
        problems.append(("FAIL", "absent_workers disagrees with the presence probe"))
    if ev.get("all_seven_configured") and creds["credentials_absent"]:
        problems.append(("FAIL", "presence probe reports all seven configured but the status claims they are absent"))
    if creds["credentials_present"] + creds["credentials_absent"] != creds["roster_workers"]:
        problems.append(("FAIL", "provider credential counts do not add up to the roster worker count"))
    return problems


def check_preflight(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    pf = read_json(canonical["deployment"]["preflight"]["evidence"])
    dep = canonical["deployment"]["preflight"]
    if pf.get("verdict") != dep["verdict"]:
        problems.append(("FAIL", "deployment preflight verdict disagrees with preflight.json"))
    if pf.get("fail_count") != dep["checks"]["fail"]:
        problems.append(("FAIL", "deployment preflight fail count disagrees with preflight.json"))
    if pf.get("warn_count") != dep["checks"]["warn"]:
        problems.append(("FAIL", "deployment preflight warn count disagrees with preflight.json"))
    return problems


def check_drills(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    ev = read_json("audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/e4e5-drills/evidence.json")
    if ev.get("checks_passed") != ev.get("checks_total"):
        problems.append(("FAIL", "recorded E4/E5 drill run did not pass every check"))
    if ev.get("real_provider_calls"):
        problems.append(("FAIL", "recorded E4/E5 drill run spent real provider calls; evidence_kind claim invalid"))
    if ev.get("stage2_enabled"):
        problems.append(("FAIL", "recorded E4/E5 drill run had Stage 2 enabled"))
    for phase in ("E4", "E5"):
        if f"{ev.get('checks_passed')} checks passed / {ev.get('checks_total')} total" not in canonical["executive_brain"][phase]["test_counts"]:
            problems.append(("FAIL", f"executive_brain.{phase}.test_counts disagrees with the drill artifact"))
    return problems


def check_persistence(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    pers = read_json("audits/evidence/2026-09-24T03-57-34Z-whole-company-acceptance-final/persistence/persistence.json")
    unverified = pers.get("unverified_after_reboot", [])
    tasks = canonical["queue_service"]["scheduled_tasks"]
    if pers.get("live_state_modified"):
        problems.append(("FAIL", "persistence evidence reports live state was modified"))
    if len(unverified) != 7:
        problems.append(("WARN", f"persistence evidence lists {len(unverified)} reboot-unverified tasks, status says 7"))
    if len(tasks["names"]) != tasks["owned_tasks"]:
        problems.append(("FAIL", "scheduled task name list does not match owned_tasks"))
    return problems


def check_blockers(canonical: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    blocker_ids = {b["id"] for b in canonical["production_blockers"]}
    optional_ids = {o["id"] for o in canonical["optional_gated"]}
    missing = REQUIRED_PRODUCTION_BLOCKERS - blocker_ids
    if missing:
        problems.append(("FAIL", f"required production blockers missing: {sorted(missing)}"))
    missing_optional = REQUIRED_OPTIONAL_GATED - optional_ids
    if missing_optional:
        problems.append(("FAIL", f"required optional/feature-gated items missing: {sorted(missing_optional)}"))
    mislabelled = REQUIRED_OPTIONAL_GATED & blocker_ids
    if mislabelled:
        problems.append(("FAIL", f"optional/feature-gated items wrongly labelled production blockers: {sorted(mislabelled)}"))
    for entry in canonical["production_blockers"]:
        if not entry.get("evidence"):
            problems.append(("FAIL", f"production blocker `{entry['id']}` has no evidence reference"))
    return problems


def check_no_ready_claim(canonical: dict) -> list[tuple[str, str]]:
    """Stop condition: never claim production-ready while blockers remain."""
    problems: list[tuple[str, str]] = []
    open_blockers = [b for b in canonical["production_blockers"] if b["state"] == "OPEN"]
    dep_state = canonical["deployment"]["state"]
    stage2 = canonical["stage2"]["state"]
    if open_blockers and dep_state not in ("NOT DEPLOYED", "BLOCKED"):
        problems.append(("FAIL", "production blockers remain open but deployment is not recorded as not-deployed"))
    if open_blockers and canonical["deployment"]["cutover"] == "authorised":
        problems.append(("FAIL", "production blockers remain open but cutover is recorded as authorised"))
    if canonical["code_identity"]["verified_evidence_sha"] and stage2 == "NOT ENABLED":
        e3 = canonical["executive_brain"]["E3"]
        if e3.get("stage2_enabled") or e3.get("production_dispatch_enabled"):
            problems.append(("FAIL", "E3 is marked Stage-2-enabled/production-dispatch while the stage2 section says NOT ENABLED"))
    return problems


def incorporated_evidence_ids(canonical: dict) -> set[str]:
    """Every evidence directory name the canonical source already references."""
    ids: set[str] = {entry["id"] for entry in canonical.get("history", [])}
    ids.add(canonical["latest_evidence"]["id"])
    for value in _walk_strings(canonical):
        prefix = "audits/evidence/"
        if value.startswith(prefix):
            ids.add(value[len(prefix):].split("/")[0])
    return ids


def _walk_strings(node) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for value in node.values():
            found += _walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            found += _walk_strings(value)
    elif isinstance(node, str):
        found.append(node)
    return found


def check_unincorporated_evidence(canonical: dict) -> list[tuple[str, str]]:
    newer = newer_evidence_dirs(canonical["as_of"])
    incorporated = incorporated_evidence_ids(canonical)
    newer = [n for n in newer if n not in incorporated]
    if newer:
        return [("WARN", f"evidence directories newer than as_of {canonical['as_of']} are not incorporated: {newer}")]
    return []


def check_no_secrets(*texts: str) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    for text in texts:
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(("FAIL", f"possible secret material matched {pattern.pattern} in generated status output"))
    return problems


def run_all_checks(canonical: dict | None = None,
                   include_block_checks: bool = True) -> list[tuple[str, str]]:
    """Run every source-level check. Returns a list of (level, message)."""
    if canonical is None:
        canonical = load_canonical()
    problems: list[tuple[str, str]] = []
    problems += check_required_keys(canonical)
    problems += check_evidence_references()
    problems += check_code_identity(canonical)
    problems += check_latest_evidence(canonical)
    problems += check_regression(canonical)
    problems += check_roster(canonical)
    problems += check_credentials(canonical)
    problems += check_preflight(canonical)
    problems += check_drills(canonical)
    problems += check_persistence(canonical)
    problems += check_blockers(canonical)
    problems += check_no_ready_claim(canonical)
    problems += check_unincorporated_evidence(canonical)
    if include_block_checks:
        from status_render import build_outputs  # local import: rendering lives elsewhere
        for target, rendered in build_outputs(canonical).items():
            if target == "executive-tracker":
                problems += check_no_secrets(rendered)
                continue
            problems += check_no_secrets(rendered)
    return problems
