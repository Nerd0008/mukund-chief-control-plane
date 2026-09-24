#!/usr/bin/env python3
"""Multi-stage high-recall discovery pipeline (control-plane, non-destructive).

    broad collection
      -> light deterministic prefilter (two-tier title policy)
      -> DeepSeek bulk semantic triage (structured contract)
      -> bounded Codex second pass (ambiguous / high-value only)
      -> deterministic eligibility gates (region, work authorisation, clearance,
         mandatory experience, application URL) — authoritative, never overridden
      -> shared dedupe (career-ops/tracker_writer.py, the same code Career Ops uses)
      -> tracker manifest / Chief brief handoff

Subcommands
-----------
  policy                         the two-tier title policy + semantic contract
  selftest                       run the regression fixtures (positive + negative)
  run        --region R [--records F | --scan-record F | --company-watch F]
                                 one bounded funnel run; writes only run evidence
  compare-modes --region R ...   old strict intern-only policy vs the new
                                 high-recall pipeline over the SAME candidate set

Safety
------
* A run never writes a canonical workbook: dedupe is a probe and the handoff is
  a manifest. Applying stays the explicit ``career_ops_cli.py write --apply``.
* Codex escalation is capped by ``--codex-budget`` (default 8) and only fires on
  the deterministic conditions in ``classifiers.escalation_reason``.
* Nothing here submits an application, contacts an employer or opens a browser.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAREER_OPS = HERE.parent
CONTROL_PLANE = CAREER_OPS.parent
for _p in (str(HERE), str(CAREER_OPS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regional_job_search as rjs  # noqa: E402
import tracker_writer as tw  # noqa: E402
from classifiers import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_CODEX_BUDGET,
    DEFAULT_MAX_TOKENS,
    codex_escalate,
    deepseek_bulk_classify,
    deepseek_probe,
    deterministic_classify,
)
from funnel import Funnel  # noqa: E402
from semantic_contract import (  # noqa: E402
    ACCEPT_LABELS,
    contract_document,
    dumps as contract_dumps,
    candidate_id,
    jd_available,
)
from title_policy import (  # noqa: E402
    DEFAULT_MODE,
    MODES,
    MODE_HIGH_RECALL,
    MODE_INTERN_ONLY,
    policy_document,
    tier_b_hits,
    title_decision,
)

SCHEMA_VERSION = 1
DEFAULT_SEMANTIC = "auto"          # auto -> deepseek when healthy, else deterministic
DEFAULT_RUNTIME_DIR = CONTROL_PLANE / "runtime" / "career-ops" / "discovery"

#: source label used for explicitly supplied candidate records
SOURCE_EXPLICIT = "explicit records file"
SOURCE_SCAN_RECORD = "regional run-health scan record"
SOURCE_COMPANY_WATCH = "company-watch findings"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def emit(obj) -> None:
    rjs.emit(obj)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #

CANDIDATE_FIELDS = ("company", "title", "location", "url", "description", "summary",
                    "posted_date", "salary", "experience_required", "employment_type",
                    "vendor")


def normalise_candidate(raw: dict, source: str) -> dict:
    rec = {k: raw.get(k) for k in CANDIDATE_FIELDS if raw.get(k) not in (None, "")}
    rec["source"] = raw.get("source") or source
    rec["_collection_source"] = source
    rec["needs_url_resolution"] = not bool(tw.extract_url(rec.get("url")))
    return rec


def collect_from_records(path: Path) -> dict:
    data = read_json(path)
    if isinstance(data, dict):
        rows = data.get("records") or data.get("candidates") or []
    else:
        rows = data
    return {"available": True, "path": str(path), "candidates":
            [normalise_candidate(r, SOURCE_EXPLICIT) for r in rows if isinstance(r, dict)],
            "coverage": {"kind": "explicit candidate records",
                         "note": "supplied by the caller; this pipeline did not collect them"}}


def collect_from_scan_record(path: Path) -> dict:
    """Candidates from a regional run-health record (offers + scan counters)."""
    doc = read_json(path)
    scan = doc.get("scan") or {}
    offers = doc.get("scan_offers")
    if offers is None:
        offers = rjs.parse_scan_offers(scan.get("stdout_tail") or "")
    candidates = []
    for offer in offers or []:
        rec = normalise_candidate(offer, SOURCE_SCAN_RECORD)
        rec["needs_url_resolution"] = True   # scan offers never carry a URL
        candidates.append(rec)
    counters = scan.get("counters") or rjs.parse_scan_counters(scan.get("stdout_tail") or "")
    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "career-ops lane scan (offers block)",
            "region": doc.get("region"),
            "run_id": doc.get("run_id"),
            "scan_ok": scan.get("ok"),
            "scan_refused": bool(scan.get("refused")),
            "scan_reason": scan.get("warning") or (doc.get("status")),
            "counters": counters,
            "note": ("offers carry company/title/location only: no posting URL and no "
                     "description text, so they cannot become tracker rows on their own and "
                     "any semantic label for them is not JD analysis"),
        },
    }


def collect_from_company_watch(path: Path, region: str) -> dict:
    doc = read_json(path)
    findings = doc.get("findings") or []
    candidates, excluded = [], Counter()
    for f in findings:
        reason = f.get("decision") or "unknown"
        if f.get("region_route") not in (None, region):
            excluded[f"routed_other_region:{f.get('region_route')}"] += 1
            continue
        if reason != "new":
            excluded[f"company_watch_decision:{reason}"] += 1
            continue
        rec = normalise_candidate(f, SOURCE_COMPANY_WATCH)
        rec["company_watch"] = {
            "decision": reason,
            "decision_reason": f.get("decision_reason"),
            "owner_filter_eligible": f.get("owner_filter_eligible"),
            "title_rule_pass": f.get("title_rule_pass"),
            "link_engine_eligible": f.get("tracker_eligible"),
            "attribution_confidence": f.get("attribution_confidence"),
            "url_quality": f.get("url_quality"),
        }
        candidates.append(rec)
    return {
        "available": True,
        "path": str(path),
        "candidates": candidates,
        "coverage": {
            "kind": "company-watch findings",
            "findings_total": len(findings),
            "findings_entering_this_funnel": len(candidates),
            "findings_excluded_before_the_funnel": dict(sorted(excluded.items())),
            "generated_at": doc.get("generated_at"),
            "region": doc.get("region"),
            "note": ("findings excluded before the funnel are counted with their own Company "
                     "Watch reason, so a 'new' finding can never silently become zero jobs"),
        },
    }


CONTENT_FIELD_ORDER = ("description", "summary")


def jd_gap_report(candidates: list) -> dict:
    with_jd = [c for c in candidates if jd_available(c)]
    return {
        "candidates": len(candidates),
        "with_job_description_text": len(with_jd),
        "without_job_description_text": len(candidates) - len(with_jd),
        "limitation": ("no candidate carried a job-description body, so classifications are "
                       "derived from title/company/location (and any other supplied fields) only "
                       "and are explicitly NOT semantic JD analysis"
                       if candidates and not with_jd else None),
    }


# --------------------------------------------------------------------------- #
# stage 2 — light deterministic prefilter
# --------------------------------------------------------------------------- #

def prefilter(candidates: list, *, mode: str, funnel: Funnel) -> dict:
    kept, decisions = [], []
    for rec in candidates:
        decision = title_decision(str(rec.get("title") or ""), mode)
        entry = {"candidate_id": candidate_id(rec), "company": rec.get("company"),
                 "title": rec.get("title"), "location": rec.get("location"),
                 "mode": mode, "decision": decision["decision"], "tier": decision.get("tier"),
                 "reason": decision["reason"], "signals": decision.get("signals")}
        decisions.append(entry)
        if decision["decision"] == "pass":
            kept.append(rec)
        else:
            funnel.reject(("tier_b_hard_negative: " if decision.get("tier") == "B"
                           else "tier_a_no_recall_signal: ") + decision["reason"])
    funnel.set("after_hard_negative_prefilter", len(kept))
    return {"mode": mode, "counts": {"input": len(candidates), "kept": len(kept),
                                     "removed": len(candidates) - len(kept)},
            "decisions": decisions}


# --------------------------------------------------------------------------- #
# stage 5 — deterministic eligibility gates (authoritative)
# --------------------------------------------------------------------------- #

def deterministic_gates(region: str, rec: dict, policy: dict, scope: dict) -> dict:
    """Region/location, work authorisation, clearance, experience and URL validity.

    These gates run AFTER semantic classification and cannot be overridden by a
    model: a title/AI verdict never substitutes for them.
    """
    rp = rjs.region_policy(region, policy)
    reasons: list = []
    flags: list = []

    url = tw.extract_url(rec.get("url"))
    if not url or not url.lower().startswith(("http://", "https://")):
        reasons.append("no usable application URL — a posting without a URL is not writable state")
    else:
        flags.append("application URL present")

    hits = tier_b_hits(str(rec.get("title") or ""))
    if hits:
        reasons.append(f"tier B hard negative re-check: {', '.join(hits)}")

    if not scope:
        reasons.append("region location scope unavailable (lane config missing) — refusing to "
                       "accept records that cannot be region-checked")
        return {"decision": "rejected", "reasons": reasons, "flags": flags,
                "work_authorisation": rjs._work_auth_block(rp)}

    ok, why = rjs.location_matches(scope, rec.get("location"), rec.get("title"), url,
                                   require_explicit_region=(region != "uk"))
    if ok:
        flags.append(why)
    else:
        reasons.append(why)

    blob = " ".join(str(rec.get(k) or "") for k in
                    ("title", "company", "location", "summary", "description"))
    clearance = rjs.clearance_hits(blob)
    if clearance:
        reasons.append(f"clearance/citizenship requirement stated: {', '.join(clearance)}")

    exp = rec.get("experience_required")
    if isinstance(exp, (int, float)) and exp >= 2:
        reasons.append(f"states {exp} years of required experience; owner targets entry level")
    elif isinstance(exp, str) and rjs.re.search(r"\b([2-9]|1[0-9])\+?\s*(?:years|yrs)\b", exp,
                                                rjs.re.IGNORECASE):
        reasons.append(f"states a multi-year experience requirement ('{exp}')")

    work_auth = rjs._work_auth_block(rp)
    if work_auth["status"] == "UNKNOWN":
        flags.append(f"work authorisation for {rp['display_name']} is UNKNOWN — no owner-stated "
                     "right to work; visa pathway must be verified by the owner")
    return {"decision": "rejected" if reasons else "accepted", "reasons": reasons,
            "flags": flags, "work_authorisation": work_auth}


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #

def _semantic_stage(candidates: list, *, semantic: str, deepseek_model: str,
                    batch_size: int, timeout: int, mode: str,
                    max_tokens: int | None = None,
                    deepseek_adapter=None) -> dict:
    max_tokens = max_tokens or DEFAULT_MAX_TOKENS
    if semantic == "off":
        return {"provider": "none", "requested": "off",
                "limitation": "semantic stage disabled by the caller",
                "classifications": {}, "probe": None}
    if semantic in ("auto", "deepseek"):
        probe = deepseek_probe(deepseek_model)
        if probe["available"]:
            doc = deepseek_bulk_classify(candidates, model=deepseek_model,
                                         batch_size=batch_size, timeout=timeout,
                                         max_tokens=max_tokens,
                                         adapter=deepseek_adapter, mode=mode)
            doc["requested"] = semantic
            doc["probe"] = probe
            if doc.get("classifications"):
                return doc
            fallback = {candidate_id(c): deterministic_classify(c, mode=mode) for c in candidates}
            return {"provider": "none", "requested": semantic, "probe": probe,
                    "classifications": fallback,
                    "limitation": ("deepseek answered but produced no usable classifications; "
                                   "the declared deterministic rule classifier was used "
                                   "instead — this is NOT a model pass"),
                    "deepseek_attempt": {k: doc.get(k) for k in
                                         ("requests", "errors", "limitation", "usage")}}
        if semantic == "deepseek":
            raise SystemExit("--semantic deepseek requested but the provider is not healthy: "
                             + str(probe.get("reason")))
        fallback = {candidate_id(c): deterministic_classify(c, mode=mode) for c in candidates}
        return {"provider": "none", "requested": semantic, "probe": probe,
                "classifications": fallback,
                "limitation": (f"deepseek unavailable ({probe.get('status')}: "
                               f"{probe.get('reason')}); the declared deterministic rule "
                               "classifier was used instead — this is NOT a model pass")}
    if semantic == "deterministic":
        return {"provider": "none", "requested": semantic, "probe": None,
                "limitation": "deterministic rule classifier selected by the caller",
                "classifications": {candidate_id(c): deterministic_classify(c, mode=mode)
                                    for c in candidates}}
    raise SystemExit(f"unknown semantic provider '{semantic}'")


def run_funnel(candidates: list, *, region: str, mode: str, semantic: str,
               deepseek_model: str, batch_size: int, codex_budget: int,
               codex_enabled: bool, timeout: int, run_id: str,
               max_tokens: int | None = None,
               deepseek_adapter=None, codex_adapter=None,
               codex_workdir: str | None = None,
               collection: list | None = None) -> dict:
    policy = rjs.load_policy()
    schedules = rjs.load_schedules()
    profiles = tw.load_profiles()
    funnel = Funnel()
    for src, n in _source_counts(collection or []).items():
        funnel.discover(src, n)

    for note in _coverage_notes(collection or []):
        funnel.note(note)

    # 1. prefilter --------------------------------------------------------- #
    pre = prefilter(candidates, mode=mode, funnel=funnel)
    kept = [c for c, d in zip(candidates, pre["decisions"]) if d["decision"] == "pass"]

    # 2. semantic ----------------------------------------------------------- #
    semantic_doc = _semantic_stage(kept, semantic=semantic, deepseek_model=deepseek_model,
                                   batch_size=batch_size, timeout=timeout, mode=mode,
                                   max_tokens=max_tokens, deepseek_adapter=deepseek_adapter)
    classifications = semantic_doc.get("classifications") or {}
    funnel.set("semantically_reviewed", len(classifications))
    for cls in classifications.values():
        if not cls.get("valid"):
            funnel.reject("semantic_contract_guard_rejected: "
                          + "; ".join(cls.get("guard", {}).get("violations", [])[:2]))
    if semantic_doc.get("requested") == "off":
        # No semantic triage was requested: the prefiltred candidates go straight to the
        # deterministic gates, and the semantic counters are marked not-applicable rather
        # than reported as the place the funnel died.
        accepted = list(kept)
        funnel.skip("semantically_reviewed",
                    "semantic stage disabled by the caller (--semantic off)")
        funnel.skip("deepseek_accept",
                    "semantic stage disabled by the caller (--semantic off)")
        funnel.set("deepseek_accept", 0)
    else:
        accepted = [c for c in kept if classifications.get(candidate_id(c), {}).get("accepted")]
        if semantic_doc.get("provider") == "deepseek":
            funnel.set("deepseek_accept", len(accepted))
        else:
            funnel.set("deepseek_accept", 0)
            funnel.skip("deepseek_accept",
                        f"no DeepSeek pass was made in this run (provider: "
                        f"{semantic_doc.get('provider')}); the declared deterministic rule "
                        "classifier or an explicit provider choice was used instead")

    # 3. bounded Codex second pass ------------------------------------------ #
    codex_doc = {"provider": "openai-codex-cli", "requested": codex_enabled, "requests": 0,
                 "classifications": {}, "limitation": "codex escalation disabled by the caller",
                 "escalated": [], "dropped_due_to_budget": []}
    if codex_enabled:
        codex_doc = codex_escalate(kept, classifications, budget=codex_budget,
                                   timeout=timeout, adapter=codex_adapter,
                                   workdir=codex_workdir)
        codex_cls = codex_doc.get("classifications") or {}
        effective = dict(classifications)
        effective.update(codex_cls)
        classifications = effective
        accepted = [c for c in kept if classifications.get(candidate_id(c), {}).get("accepted")]
    funnel.set("codex_escalated", len(codex_doc.get("escalated") or []))
    funnel.set("codex_accept", sum(1 for c in accepted
                                   if classifications.get(candidate_id(c), {}).get("classifier")
                                   == "codex_second_pass"))
    if not codex_enabled:
        funnel.skip("codex_escalated", "Codex escalation disabled by the caller (--codex off)")
        funnel.skip("codex_accept", "Codex escalation disabled by the caller (--codex off)")
    elif not codex_doc.get("eligible_for_escalation"):
        funnel.skip("codex_escalated",
                    "no candidate met the deterministic escalation conditions, so no Codex "
                    "call was made (see codex.limitation)")
        funnel.skip("codex_accept", "no Codex second pass was run in this run")

    # 4. deterministic gates ------------------------------------------------ #
    scope = rjs.lane_scope(region, schedules["regions"][region])
    if semantic_doc.get("requested") != "off":
        for rec in kept:
            cls = classifications.get(candidate_id(rec)) or {}
            if not cls.get("accepted"):
                funnel.reject(f"semantic_label: {cls.get('primary_label') or 'unclassified'}"
                              f" ({cls.get('classifier') or 'no classifier'})")
    if not accepted:
        funnel.explain(
            "deterministic_eligibility_pass",
            "no candidate was left accepted by the semantic stage (DeepSeek bulk pass, plus any "
            "Codex second pass) — so no candidate reached the deterministic gates; see the "
            "classification labels and rejections_by_reason for the per-candidate reason")
    gated = []
    for rec in accepted:
        verdict = deterministic_gates(region, rec, policy, scope)
        entry = {"candidate_id": candidate_id(rec), "company": rec.get("company"),
                 "title": rec.get("title"), "location": rec.get("location"),
                 "url": rec.get("url"), "semantic_label":
                     classifications.get(candidate_id(rec), {}).get("primary_label"),
                 **verdict}
        gated.append(entry)
        if verdict["decision"] != "accepted":
            for reason in verdict["reasons"]:
                funnel.reject("deterministic_gate: " + reason)
    passed = [g for g in gated if g["decision"] == "accepted"]
    funnel.set("deterministic_eligibility_pass", len(passed))

    # 5. shared dedupe ------------------------------------------------------ #
    records = []
    for entry in passed:
        rec = next((c for c in accepted if candidate_id(c) == entry["candidate_id"]), None)
        if rec is None:
            continue
        records.append(rjs.build_record(region, rec, policy, run_id, {"stage": "discovery"}))
    probe = tw.write_records(profiles, region, records, apply=False) if records else (
        {"tracker": str(tw.region_config(profiles, region)["tracker"]), "counts": {},
         "cross_month_index": {}, "outcomes": [], "applied": False})
    counts = probe.get("counts") or {}
    duplicates = sum(v for k, v in counts.items() if k in ("duplicates", "duplicate",
                                                           "duplicate-cross-month"))
    funnel.set("duplicates_removed", int(duplicates or 0))
    new_rows = [o for o in probe.get("outcomes", []) if o.get("decision") == "appended"]
    funnel.set("tracker_candidates", len(new_rows))
    for outcome in probe.get("outcomes", []):
        if outcome.get("decision") != "appended":
            funnel.reject("dedupe: " + str(outcome.get("reason") or outcome.get("decision")))

    return {
        "run_id": run_id,
        "region": region,
        "title_policy_mode": mode,
        "semantic": {k: v for k, v in semantic_doc.items() if k != "classifications"},
        "codex": {k: v for k, v in codex_doc.items() if k != "classifications"},
        "prefilter": {"counts": pre["counts"], "mode": pre["mode"]},
        "classifications": [classifications[candidate_id(c)] for c in kept
                            if candidate_id(c) in classifications],
        "eligibility": {"input": len(accepted), "decisions": gated,
                        "passed": len(passed)},
        "dedupe": {"engine": "career-ops/tracker_writer.py (shared with Career Ops)",
                   "tracker": probe.get("tracker"), "counts": counts,
                   "cross_month_index": probe.get("cross_month_index"),
                   "outcomes": probe.get("outcomes", [])[:25], "applied": False},
        "funnel": funnel.document(),
        "jd_gap": jd_gap_report(candidates),
        "collection": collection or [],
        "safety": {
            "canonical_workbook_written": False,
            "applications_submitted": 0,
            "employer_contacts": 0,
            "browser_used": False,
            "handoff": "manifest only; applying stays career_ops_cli.py write --apply",
        },
    }


def _source_counts(collection: list) -> Counter:
    out: Counter = Counter()
    for block in collection:
        out[block.get("source") or "unknown"] += len(block.get("candidates") or [])
    return out


def _coverage_notes(collection: list) -> list:
    notes = []
    for block in collection:
        cov = block.get("coverage") or {}
        notes.append(f"source {block.get('source')}: {json.dumps(cov, ensure_ascii=False)}")
    return notes


# --------------------------------------------------------------------------- #
# compare modes
# --------------------------------------------------------------------------- #

def compare_modes(candidates: list, *, region: str, semantic: str,
                  deepseek_model: str, batch_size: int, timeout: int,
                  deepseek_adapter=None) -> dict:
    """Old strict intern-only policy vs the new high-recall pipeline.

    Runs over the SAME candidate set. Never writes a canonical tracker: no
    manifest, no dedupe probe, no workbook access beyond reading the region
    config for scope.
    """
    policy = rjs.load_policy()
    schedules = rjs.load_schedules()
    scope = rjs.lane_scope(region, schedules["regions"][region])
    results = {}
    for mode in (MODE_INTERN_ONLY, MODE_HIGH_RECALL):
        rows = []
        for rec in candidates:
            title_gate = title_decision(str(rec.get("title") or ""), mode)
            gates = deterministic_gates(region, rec, policy, scope)
            rows.append({
                "candidate_id": candidate_id(rec), "company": rec.get("company"),
                "title": rec.get("title"), "location": rec.get("location"),
                "title_decision": title_gate["decision"], "title_tier": title_gate.get("tier"),
                "title_reason": title_gate["reason"],
                "deterministic_decision": gates["decision"], "gate_reasons": gates["reasons"],
                "would_reach_tracker": bool(title_gate["decision"] == "pass"
                                            and gates["decision"] == "accepted"),
            })
        results[mode] = {
            "title_pass": sum(1 for r in rows if r["title_decision"] == "pass"),
            "title_reject": sum(1 for r in rows if r["title_decision"] != "pass"),
            "would_reach_tracker": sum(1 for r in rows if r["would_reach_tracker"]),
            "rows": rows,
        }

    old, new = results[MODE_INTERN_ONLY], results[MODE_HIGH_RECALL]
    old_pass = {r["candidate_id"] for r in old["rows"] if r["title_decision"] == "pass"}
    new_pass = {r["candidate_id"] for r in new["rows"] if r["title_decision"] == "pass"}
    regained = [r for r in new["rows"]
                if r["candidate_id"] in (new_pass - old_pass)]
    regressed = [r for r in new["rows"]
                 if r["candidate_id"] in (old_pass - new_pass)]
    delta = {
        "title_pass_delta": new["title_pass"] - old["title_pass"],
        "tracker_candidate_delta": (new["would_reach_tracker"] - old["would_reach_tracker"]),
        "recall_regained_titles": [{"candidate_id": r["candidate_id"], "company": r["company"],
                                    "title": r["title"],
                                    "deterministic_decision": r["deterministic_decision"],
                                    "gate_reasons": r["gate_reasons"]} for r in regained],
        "recall_lost_titles": [{"candidate_id": r["candidate_id"], "title": r["title"],
                                "reason": r["title_reason"]} for r in regressed],
        "note": ("titles regained by high-recall are only 'recall' if the deterministic gates "
                 "also pass; both counts are reported separately so a title-policy delta is "
                 "never presented as a tracker delta"),
    }

    semantic_doc = {"requested": semantic}
    if semantic in ("deepseek", "auto"):
        doc = _semantic_stage([r for r in candidates
                               if title_decision(str(r.get("title") or ""),
                                                 MODE_HIGH_RECALL)["decision"] == "pass"],
                              semantic="auto" if semantic == "auto" else "deepseek",
                              deepseek_model=deepseek_model, batch_size=batch_size,
                              timeout=timeout, mode=MODE_HIGH_RECALL,
                              deepseek_adapter=deepseek_adapter)
        semantic_doc = {k: v for k, v in doc.items() if k != "classifications"}
        semantic_doc["labels"] = dict(Counter(
            c.get("primary_label") for c in (doc.get("classifications") or {}).values()))

    return {
        "region": region,
        "candidate_set": {"candidates": len(candidates)},
        "modes": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in results.items()},
        "recall_delta": delta,
        "semantic": semantic_doc,
        "safety": {"canonical_workbook_written": False, "manifest_written": False,
                   "tracker_probe_run": False, "applications_submitted": 0},
    }


# --------------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------------- #

FIXTURE_PATH = CAREER_OPS / "tests" / "fixtures" / "discovery" / "title-fixtures.json"


def load_fixtures(path: Path | None = None) -> dict:
    return read_json(Path(path or FIXTURE_PATH))


def selftest(path: Path | None = None) -> dict:
    fixtures = load_fixtures(path)
    rows, failures = [], []
    for entry in fixtures["titles"]:
        decision = title_decision(entry["title"], entry["mode"] if "mode" in entry
                                  else MODE_HIGH_RECALL)
        expected = entry["expect"]
        ok = decision["decision"] == expected
        rows.append({"title": entry["title"], "expected": expected,
                     "decision": decision["decision"], "tier": decision.get("tier"),
                     "reason": decision["reason"], "family": entry.get("family"),
                     "ok": ok})
        if not ok:
            failures.append({"title": entry["title"], "expected": expected,
                             "got": decision["decision"], "reason": decision["reason"]})
    return {"fixtures": str(path or FIXTURE_PATH), "counts": {"total": len(rows),
                                                             "passed": len(rows) - len(failures),
                                                             "failed": len(failures)},
            "failures": failures, "rows": rows, "ok": not failures}


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_policy(args) -> int:
    emit({"generated_at": now_utc(), "title_policy": policy_document(),
          "semantic_contract": contract_document(),
          "codex_budget_default": DEFAULT_CODEX_BUDGET,
          "deepseek_batch_size_default": DEFAULT_BATCH_SIZE,
          "deepseek_probe": deepseek_probe(args.model)})
    return 0


def cmd_selftest(args) -> int:
    doc = selftest(args.fixtures)
    emit(doc)
    return 0 if doc["ok"] else 1


MAX_CLASSIFICATIONS_IN_RUN = 200


def cmd_run(args) -> int:
    run_id = f"discovery-{args.region}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    collection, candidates = [], []
    if args.records:
        block = collect_from_records(Path(args.records)); block["source"] = SOURCE_EXPLICIT
        collection.append(block); candidates.extend(block["candidates"])
    if args.scan_record:
        block = collect_from_scan_record(Path(args.scan_record))
        block["source"] = SOURCE_SCAN_RECORD
        collection.append(block); candidates.extend(block["candidates"])
    if args.company_watch:
        block = collect_from_company_watch(Path(args.company_watch), args.region)
        block["source"] = SOURCE_COMPANY_WATCH
        collection.append(block); candidates.extend(block["candidates"])
    if not collection:
        emit({"ok": False, "reason": "no candidate source supplied; pass --records, "
                                     "--scan-record or --company-watch",
              "run_id": run_id, "region": args.region})
        return 2

    total_candidates = sum(len(b["candidates"]) for b in collection)
    if total_candidates > args.max_candidates:
        remaining = args.max_candidates
        for block in collection:
            block.setdefault("coverage", {})["candidates_before_max_candidate_limit"] = len(block["candidates"])
            block["candidates"] = block["candidates"][:max(0, remaining)]
            remaining -= len(block["candidates"])
        candidates = [c for b in collection for c in b["candidates"]]
        collection.append({"source": "run limits", "candidates": [],
                           "coverage": {"max_candidates": args.max_candidates,
                                        "candidates_before_limit": total_candidates,
                                        "candidates_after_limit": len(candidates),
                                        "note": ("the funnel counters below describe the limited "
                                                 "candidate set actually processed; the pre-limit "
                                                 "count is recorded here so a limit is never "
                                                 "presented as a market fact")}})

    doc = run_funnel(candidates, region=args.region, mode=args.title_mode,
                     semantic=args.semantic, deepseek_model=args.model,
                     batch_size=args.batch_size, codex_budget=args.codex_budget,
                     codex_enabled=(args.codex != "off"), timeout=args.timeout,
                     run_id=run_id, codex_workdir=str(args.workdir or CONTROL_PLANE),
                     max_tokens=args.max_tokens, collection=collection)
    doc["schema_version"] = SCHEMA_VERSION
    doc["started_at"] = None
    doc["finished_at"] = now_utc()
    doc["policy_sha256"] = policy_document()["policy_sha256"]
    doc["contract_version"] = contract_document()["contract_version"]
    doc["summary_line"] = _summary_line(doc)
    if len(doc["classifications"]) > MAX_CLASSIFICATIONS_IN_RUN:
        doc["classifications_truncated"] = len(doc["classifications"])
        doc["classifications"] = doc["classifications"][:MAX_CLASSIFICATIONS_IN_RUN]
    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_RUNTIME_DIR
    health_path = out_dir / f"{run_id}.json"
    latest = out_dir / "latest.json"
    write_json_atomic(health_path, doc)
    write_json_atomic(latest, doc)
    doc["run_health_file"] = str(health_path)
    if args.manifest_out:
        records = [rjs.build_record(args.region, c, rjs.load_policy(), run_id,
                                    {"stage": "discovery-manifest"})
                   for c in candidates
                   if c.get("url") and candidate_id(c) in
                   {d["candidate_id"] for d in doc["eligibility"]["decisions"]
                    if d["decision"] == "accepted"}]
        write_json_atomic(Path(args.manifest_out),
                          {"schema_version": 1, "generated_at": now_utc(),
                           "region": args.region, "run_id": run_id,
                           "records": records})
        doc["manifest_written_to"] = str(args.manifest_out)
    emit(doc)
    return 0


def _summary_line(doc: dict) -> str:
    c = doc["funnel"]["counts"]
    head = (f"discovered_raw={c['discovered_raw']} "
            f"after_hard_negative_prefilter={c['after_hard_negative_prefilter']} "
            f"semantically_reviewed={c['semantically_reviewed']} "
            f"deepseek_accept={c['deepseek_accept']} "
            f"codex_escalated={c['codex_escalated']} codex_accept={c['codex_accept']} "
            f"deterministic_eligibility_pass={c['deterministic_eligibility_pass']} "
            f"duplicates_removed={c['duplicates_removed']} "
            f"tracker_candidates={c['tracker_candidates']}")
    z = doc["funnel"]["zero_attribution"]
    if z.get("first_zero_stage"):
        return f"{head} :: funnel first reached zero at {z['first_zero_stage']} ({z['reason']})"
    return head


def cmd_compare(args) -> int:
    candidates = []
    if args.records:
        candidates.extend(collect_from_records(Path(args.records))["candidates"])
    if args.scan_record:
        candidates.extend(collect_from_scan_record(Path(args.scan_record))["candidates"])
    if args.company_watch:
        candidates.extend(collect_from_company_watch(Path(args.company_watch), args.region)["candidates"])
    if not candidates:
        emit({"ok": False, "reason": "no candidate source supplied"})
        return 2
    doc = compare_modes(candidates, region=args.region,
                        semantic=("none" if args.semantic == "off" else args.semantic),
                        deepseek_model=args.model, batch_size=args.batch_size,
                        timeout=args.timeout)
    doc["generated_at"] = now_utc()
    if args.out_dir:
        write_json_atomic(Path(args.out_dir) / "compare-modes-latest.json", doc)
    emit(doc)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="High-recall multi-stage Career discovery pipeline")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("policy")
    p.add_argument("--model", default="deepseek-flash")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("selftest")
    p.add_argument("--fixtures")
    p.set_defaults(fn=cmd_selftest)

    p = sub.add_parser("run")
    p.add_argument("--region", required=True)
    p.add_argument("--records")
    p.add_argument("--scan-record")
    p.add_argument("--company-watch")
    p.add_argument("--title-mode", choices=list(MODES), default=DEFAULT_MODE)
    p.add_argument("--semantic", choices=("auto", "deepseek", "deterministic", "off"),
                   default=DEFAULT_SEMANTIC)
    p.add_argument("--codex", choices=("on", "off"), default="on")
    p.add_argument("--codex-budget", type=int, default=DEFAULT_CODEX_BUDGET)
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                   help="completion budget per bulk request (a reasoning model can otherwise "
                        "return an empty response after spending the whole budget on reasoning)")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--max-candidates", type=int, default=400)
    p.add_argument("--out-dir")
    p.add_argument("--manifest-out")
    p.add_argument("--workdir")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("compare-modes")
    p.add_argument("--region", required=True)
    p.add_argument("--records")
    p.add_argument("--scan-record")
    p.add_argument("--company-watch")
    p.add_argument("--semantic", choices=("off", "auto", "deepseek"), default="off")
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_compare)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
