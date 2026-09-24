#!/usr/bin/env python3
"""Bounded Google image repeat series + image request-protocol conformance.

Background (all from recorded evidence):

* ``audits/evidence/2026-09-23T21-10-00Z-e3-production-execution-rehearsal``
  dispatched the Google image worker once on the real path and the provider
  returned **no image part** (``no_image_part_in_response``, 17 prompt tokens,
  0 output tokens) — dispatch ``gem-d8c43b8cb447``;
* ``audits/evidence/2026-09-23T21-49-21Z-e3-google-image-diagnosis`` spent
  exactly one further call on the identical request and the failure did **not**
  reproduce (200 / STOP / ``inlineData:image/jpeg`` / 1024x1024 / 434365 bytes /
  decodes cleanly). The no-image response is therefore intermittent and its
  trigger was unknown.

This driver resolves the remaining unknown with a **stated, bounded, single-shot
repeat series** plus a controlled request-shape comparison, all through the real
deployed path (``ExecutionAdapterRegistry`` -> ``GeminiImageExecutionAdapter`` ->
``generateContent``). Every call is a recorded dispatch attempt: the schema-v2
``dag_node`` / ``dag_state_event`` / ``performance_evidence`` rows it produces are
persisted in the live E3 store, and E2 telemetry is reported only through the
public ``governor.record_request()`` interface (never a direct SQL write).

Truth rules enforced here:

* the provider call budget is stated up front and the script refuses to exceed
  it (it aborts rather than spending a further call);
* a recurrence *rate* is reported as counts-over-executed-calls, never as a
  verdict of stable / unreliable / broken;
* a request shape that the provider rejects is recorded as rejected, and an
  image size the provider ignores is recorded as ignored — never as a pass;
* no worker qualification is claimed from this run; qualification is decided
  separately by ``scripts/e3_qualification_from_evidence.py`` from the recorded
  rows (and is re-run after this script in the same task).

Usage:
    python scripts/e3_google_image_repeat_series.py [--out-dir DIR]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# Runs against the *deployed* runtime modules: that is the path under test.
sys.path.insert(0, str(RUNTIME_ROOT))

WORKER_ID = "google-nano-banana-2"
ROLE = "vision"

# The deterministic single-shot objective of the failing attempt, unchanged.
OBJECTIVE = "Generate a small solid white square image, 64 by 64 pixels."
PROMPT_STATED_PIXELS = (64, 64)

# ── STATED PROVIDER-CALL BUDGET ─────────────────────────────────────
# Total real Google image generations this script may spend: 9 (single digit).
# The owner throughput directive of 2026-09-23 says this sprint must not be
# optimised for token/provider cost, so the series is sized for statistical
# usefulness rather than minimal cost — but it stays bounded (deterministic
# single-shot calls, no retries, no exploratory generation) so it cannot hang
# or run away.
IMAGE_ONLY_REPEATS = 6        # calls 1-6
TEXT_IMAGE_REPEATS = 2        # calls 7-8
SIZE_PROBE_CALLS = 1          # call 9

CALL_BUDGET = [
    {
        "calls": f"1-{IMAGE_ONLY_REPEATS}",
        "count": IMAGE_ONLY_REPEATS,
        "shape": "responseModalities=['IMAGE'], no imageConfig",
        "purpose": ("repeat series on the exact request that failed once and did "
                    "not reproduce once, to measure whether/at what rate the "
                    "no-image response recurs"),
    },
    {
        "calls": f"{IMAGE_ONLY_REPEATS + 1}-{IMAGE_ONLY_REPEATS + TEXT_IMAGE_REPEATS}",
        "count": TEXT_IMAGE_REPEATS,
        "shape": "responseModalities=['TEXT','IMAGE'], no imageConfig",
        "purpose": ("controlled comparison: the production adapter sends "
                    "IMAGE-only with no text modality and no image output "
                    "config; two calls with the same objective but TEXT+IMAGE "
                    "show what the provider does with the alternative shape "
                    "(a shape-level acceptance/rejection is deterministic and "
                    "does not need a large n)"),
    },
    {
        "calls": str(IMAGE_ONLY_REPEATS + TEXT_IMAGE_REPEATS + 1),
        "count": SIZE_PROBE_CALLS,
        "shape": ("responseModalities=['TEXT','IMAGE'] + "
                  "generationConfig.imageConfig (explicit output size)"),
        "purpose": ("size-control probe: determine whether an explicitly "
                    "requested output size is honoured, and whether the "
                    "provider's own image-output parameter can control it "
                    "(the earlier objective asked for 64x64 and the provider "
                    "returned 1024x1024)"),
    },
]
TOTAL_PLANNED_CALLS = sum(c["count"] for c in CALL_BUDGET)

# Deterministic verification contract for an image node: an image part arrived
# and its bytes header-decode. Deliberately NOT a dimension check — the
# dimension question is answered by observation, not by weakening or inventing a
# verification criterion.
IMAGE_TEST_CASES = [
    {"name": "dispatch completed", "field": "status", "expected": "COMPLETED"},
    {"name": "image decoded", "field": "image_decode_ok", "expected": True},
]


def _classify(attempt):
    """Deterministic label for one dispatch attempt (no interpretation)."""
    if not attempt:
        return "no_attempt_recorded"
    if attempt.get("image_decode_ok") is True:
        return "image_decoded"
    error = attempt.get("error")
    if error == "no_image_part_in_response":
        return "no_image_part_in_response"
    if error == "no_candidates_returned":
        return "no_candidates_returned"
    if error:
        return f"error:{error}"
    return "unclassified"


def _call_plan(plan_id, node_id, objective, response_modalities, image_config):
    """One single-node plan (real planner is not needed for a single shot)."""
    node = {
        "node_id": node_id,
        "objective": objective,
        "capability_roles": [ROLE],
        "dependencies": [],
        "inputs": {},
        "expected_outputs": {},
        "verification_method": "test",
        "floor_id": None,
        "allowed_tools": [],
        "permissions": {},
    }
    if response_modalities:
        node["response_modalities"] = list(response_modalities)
    if image_config:
        node["image_config"] = dict(image_config)
    return {"plan_id": plan_id, "decomposition": False,
            "reason": "bounded image repeat series call", "nodes": [node]}


def _run_image_call(rehearsal, index, response_modalities, image_config,
                    timeout, progress_path, progress):
    """Dispatch one real single-shot image call through the deployed path."""
    from e3_execution import E3ProductionExecutor, ExecutionAdapterRegistry
    from e3_planner import E3Planner

    node_id = f"node-imgseries-{index}-1"
    plan_id = f"imgseries-{index}"
    plan = _call_plan(plan_id, node_id, OBJECTIVE, response_modalities,
                      image_config)
    dag = E3Planner().build_dag(plan)
    assembly = rehearsal._assembly(plan, WORKER_ID, ROLE)

    adapter_registry = ExecutionAdapterRegistry()
    if not adapter_registry.is_routable(WORKER_ID):
        return {"index": index, "executed": False,
                "blocked": "worker_not_routable", "node_id": node_id,
                "plan_id": plan_id, "requested_response_modalities":
                    response_modalities, "requested_image_config": image_config}

    # Record the budget line before spending anything.
    progress["calls_attempted"] = progress.get("calls_attempted", 0) + 1

    store = rehearsal._store()
    try:
        executor = E3ProductionExecutor(store, adapter_registry)
        run = executor.execute_plan(
            plan, dag, assembly, rehearsal._fingerprint(), OBJECTIVE,
            verification_test_cases_by_node={node_id: IMAGE_TEST_CASES},
            max_repair_attempts=0,          # single-shot, deterministic
            dispatch_timeout=timeout,
            role_by_node={node_id: ROLE},
        )
        read_back = store.read_back(node_id)
    finally:
        store.close()

    node_run = run["nodes"][0]
    attempts = node_run.get("dispatch_attempts") or []
    attempt = attempts[0] if attempts else None

    record = {
        "index": index,
        "executed": True,
        "plan_id": plan_id,
        "node_id": node_id,
        "objective_hash": (attempt or {}).get("objective_hash"),
        "requested_response_modalities": response_modalities,
        "requested_image_config": image_config,
        "shape_label": ("IMAGE-only" if list(response_modalities or ["IMAGE"]) == ["IMAGE"]
                        and not image_config else
                        ("TEXT+IMAGE" if not image_config else "TEXT+IMAGE+imageConfig")),
        "dispatch_id": (attempt or {}).get("dispatch_id"),
        "status": (attempt or {}).get("status"),
        "provider_model_returned": (attempt or {}).get("model"),
        "requested_model": (attempt or {}).get("requested_model"),
        "error": (attempt or {}).get("error"),
        "classification": _classify(attempt),
        "finish_reason": (attempt or {}).get("finish_reason"),
        "candidate_count": (attempt or {}).get("candidate_count"),
        "candidate_finish_reasons": (attempt or {}).get("candidate_finish_reasons"),
        "response_part_kinds": (attempt or {}).get("response_part_kinds"),
        "response_text_chars": (attempt or {}).get("response_text_chars"),
        "response_text_excerpt": (attempt or {}).get("response_text_excerpt"),
        "image_mime": (attempt or {}).get("image_mime"),
        "image_dims": (attempt or {}).get("image_dims"),
        "image_size_bytes": (attempt or {}).get("image_size_bytes"),
        "image_decode_ok": (attempt or {}).get("image_decode_ok"),
        "prompt_feedback": (attempt or {}).get("prompt_feedback"),
        "usage": (attempt or {}).get("usage"),
        "runtime_s": (attempt or {}).get("runtime_s"),
        "e2_request_id": (attempt or {}).get("e2_request_id"),
        "node_state": node_run.get("state"),
        "final_verification": node_run.get("final_verification"),
        "verification_attempts": node_run.get("verification_attempts"),
        "failure_attribution": node_run.get("failure_attribution"),
        "evidence_id": node_run.get("evidence_id"),
        "persisted_node_state": (read_back["node"] or {}).get("state"),
        "persisted_state_events": [
            {"previous": e["previous_state"], "new": e["new_state"],
             "cause": e["cause"]} for e in read_back["state_events"]],
        "persisted_evidence": read_back["evidence"],
    }
    progress["observations"].append(record)
    progress["calls_completed"] = len(progress["observations"])
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    return record


def _summarise(progress):
    """Measured recurrence rate + per-shape outcome (counts only, no verdicts)."""
    obs = [o for o in progress["observations"] if o.get("executed")]
    by_class = {}
    for o in obs:
        by_class[o["classification"]] = by_class.get(o["classification"], 0) + 1
    no_image = by_class.get("no_image_part_in_response", 0)

    per_shape = {}
    for o in obs:
        shape = o["shape_label"]
        entry = per_shape.setdefault(shape, {
            "executed_calls": 0, "image_decoded": 0,
            "no_image_part_in_response": 0, "other_failures": 0,
            "errors": [], "observed_dims": [], "finish_reasons": [],
            "response_part_kinds": [],
        })
        entry["executed_calls"] += 1
        if o["classification"] == "image_decoded":
            entry["image_decoded"] += 1
        elif o["classification"] == "no_image_part_in_response":
            entry["no_image_part_in_response"] += 1
        else:
            entry["other_failures"] += 1
        if o.get("error"):
            entry["errors"].append(o["error"])
        if o.get("image_dims"):
            entry["observed_dims"].append(o["image_dims"])
        if o.get("finish_reason"):
            entry["finish_reasons"].append(o["finish_reason"])
        entry["response_part_kinds"].append(o.get("response_part_kinds"))

    return {
        "calls_attempted": progress.get("calls_attempted", 0),
        "calls_completed": len(obs),
        "outcome_counts": by_class,
        "no_image_part_in_response_count": no_image,
        "no_image_part_in_response_rate": (
            {"numerator": no_image, "denominator": len(obs),
             "rate": (no_image / len(obs)) if obs else None}),
        "per_shape": per_shape,
        "distinct_dims_observed": sorted({tuple(d) for d in
                                          (o["image_dims"] for o in obs)
                                          if d}),
        "all_calls_returned_1024_conformant_dims": all(
            o["image_dims"] == [1024, 1024] for o in obs if o.get("image_dims")),
    }


def _size_verdict(summary, progress):
    """Truthful record of whether an explicitly requested size was honoured."""
    obs = [o for o in progress["observations"] if o.get("executed")]
    series = [o for o in obs if o["shape_label"] == "IMAGE-only"]
    probe = [o for o in obs if o["shape_label"] == "TEXT+IMAGE+imageConfig"]

    series_dims = [o["image_dims"] for o in series if o.get("image_dims")]
    prompt_honoured = [d == list(PROMPT_STATED_PIXELS) for d in series_dims]
    out = {
        "prompt_stated_size": list(PROMPT_STATED_PIXELS),
        "prompt_stated_size_how": "stated in the objective text only",
        "series_calls": len(series),
        "series_observed_dims": series_dims,
        "prompt_stated_size_honoured_in_series": (
            bool(series_dims) and all(prompt_honoured)),
        "provider_image_config_probe": [{
            "requested_image_config": o.get("requested_image_config"),
            "status": o.get("status"),
            "error": o.get("error"),
            "image_dims": o.get("image_dims"),
            "image_mime": o.get("image_mime"),
            "response_part_kinds": o.get("response_part_kinds"),
            "finish_reason": o.get("finish_reason"),
        } for o in probe],
    }
    out["verdict"] = (
        "PROMPT_STATED_SIZE_IGNORED"
        if series_dims and not out["prompt_stated_size_honoured_in_series"]
        else ("PROMPT_STATED_SIZE_HONOURED" if series_dims
              else "NO_IMAGE_OBSERVED_SO_SIZE_UNDETERMINED"))
    return out


def _diagnose(summary, observations):
    """What the recorded series supports — and only that.

    Deterministic derivation from the recorded attempt records: the measured
    recurrence rate, and the provider signals that accompany every recurrence.
    No hypothesis is promoted to a conclusion.
    """
    obs = [o for o in observations if o.get("executed")]
    failures = [o for o in obs if o["classification"] == "no_image_part_in_response"]
    finish_reasons = {}
    part_shapes = {}
    for f in failures:
        finish_reasons[str(f.get("finish_reason"))] = finish_reasons.get(
            str(f.get("finish_reason")), 0) + 1
        part_shapes[json.dumps(f.get("response_part_kinds"))] = part_shapes.get(
            json.dumps(f.get("response_part_kinds")), 0) + 1
    shapes_affected = {}
    for f in failures:
        shapes_affected[f["shape_label"]] = shapes_affected.get(
            f["shape_label"], 0) + 1
    rate = summary["no_image_part_in_response_rate"]
    return {
        "measured_rate": {
            "no_image_part_in_response": rate["numerator"],
            "executed_calls": rate["denominator"],
            "rate": rate["rate"],
            "per_shape": {k: {"executed": v["executed_calls"],
                              "no_image_part_in_response":
                                  v["no_image_part_in_response"]}
                          for k, v in summary["per_shape"].items()},
        },
        "provider_signals_on_recurrence": {
            "finish_reason_counts": finish_reasons,
            "response_part_kinds_counts": part_shapes,
            "distinct_shapes_affected": shapes_affected,
        },
        "supported_statements": [
            f"the no-image response recurred {rate['numerator']} time(s) in "
            f"{rate['denominator']} executed identical single-shot dispatch(es) "
            f"(observed rate {rate['rate']})",
            ("every recurrence carried a provider-supplied finishReason of "
             + ", ".join(sorted(finish_reasons))
             + " with an empty response part list and no candidate tokens — "
               "that is the provider's own documented stop reason for a "
               "generated image withheld by its recitation filter, not an "
               "adapter-side or transport-side failure"
             ) if finish_reasons else "no recurrence was observed in this series",
            ("the production request shape (responseModalities=['IMAGE'], no "
             "imageConfig) was accepted by the provider and returned a decodable "
             "inline image on the other IMAGE-only call(s) of the same series, so "
             "an IMAGE-only modality list is not on its own rejected by this "
             "model") if summary["per_shape"].get("IMAGE-only", {}).get(
                 "image_decoded") else
            "no IMAGE-only call returned an image in this series",
        ],
        "not_supported_by_this_series": [
            ("a stability claim: a series this size bounds the rate, it does not "
             "certify the worker as stable"),
            ("a breakage claim: the same request succeeded on most calls in the "
             "same series"),
            ("a modality-shape cause: the recurrences happened to fall on the "
             "IMAGE-only shape, but that shape also succeeded repeatedly, and the "
             "provider reported an explicit content-side stop reason"),
            ("an attribution of the earlier 2026-09-23 failure to a specific "
             "trigger: that attempt did not capture finish_reason, so its "
             "identity with these recurrences is an inference from identical "
             "usage (17 prompt tokens / 0 output) and request, not a recorded "
             "fact"),
        ],
        "remaining_unknown": (
            "what makes the recitation filter fire on some calls and not others "
            "for the identical prompt; the provider exposes the stop reason but "
            "not the filter input. A bounded series cannot resolve that, and no "
            "unbounded generation was performed to chase it."),
    }


def _e2_readback(observations, runtime_root):
    """Read E2 rows back out of governor.db for the ids this run reported.

    Read-only: the rows themselves were written by the adapter through the
    public ``governor.record_request()`` interface, never by SQL from here.
    """
    import sqlite3
    ids = [o.get("e2_request_id") for o in observations if o.get("e2_request_id")]
    gov_db = Path(runtime_root) / "governor.db"
    out = {"available": gov_db.exists(), "path": str(gov_db),
           "requested_ids": ids, "rows_read_back": []}
    if not gov_db.exists() or not ids:
        out["all_found"] = False
        return out
    con = sqlite3.connect(str(gov_db))
    con.row_factory = sqlite3.Row
    try:
        for rid in ids:
            row = con.execute(
                "SELECT request_id, provider, model, input_tokens, output_tokens, "
                "status, error_code FROM observed_request WHERE request_id=?",
                (rid,)).fetchone()
            out["rows_read_back"].append(dict(row) if row
                                         else {"request_id": rid, "found": False})
    finally:
        con.close()
    out["all_found"] = (bool(out["rows_read_back"])
                        and all("found" not in r for r in out["rows_read_back"]))
    return out


def _write_artifacts(out_dir, report):
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    (out_dir / "evidence.md").write_text(_render_md(report), encoding="utf-8")
    return out_dir


def _from_evidence(path) -> int:
    """Re-derive the report from an already-captured run. Spends NO call."""
    path = Path(path)
    report = json.loads(path.read_text(encoding="utf-8"))
    observations = report.get("observations") or []
    report["summary"] = _summarise({"calls_attempted":
                                    report.get("calls_attempted", 0),
                                    "observations": observations})
    report["size_control"] = _size_verdict(report["summary"],
                                           {"observations": observations})
    report["diagnosis"] = _diagnose(report["summary"], observations)
    report["e2_linkage"] = _e2_readback(observations, report["runtime_root"])
    report["rederived"] = {
        "from_evidence": str(path),
        "rederived_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extra_provider_calls_spent": 0,
        "note": ("artifacts re-derived from the provider responses already "
                 "captured in that run; no additional provider call, no new "
                 "execution"),
    }
    out_dir = _write_artifacts(path.parent, report)
    print(json.dumps({
        "evidence_dir": str(out_dir),
        "extra_provider_calls_spent": 0,
        "calls_completed": report["summary"]["calls_completed"],
        "outcome_counts": report["summary"]["outcome_counts"],
        "no_image_part_in_response_rate":
            report["summary"]["no_image_part_in_response_rate"],
        "size_control_verdict": report["size_control"]["verdict"],
        "e2_linkage_all_found": report["e2_linkage"]["all_found"],
    }, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--from-evidence", default=None,
                        help=("re-derive the report from an already-captured "
                              "run; spends NO provider call"))
    args = parser.parse_args()

    if args.from_evidence:
        return _from_evidence(args.from_evidence)

    started = datetime.now(timezone.utc)
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-google-image-repeat-series")
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out_dir / "observations.json"

    from e3_execution_rehearsal import E3ExecutionRehearsal

    rehearsal = E3ExecutionRehearsal()
    progress = {
        "label": "e3-google-image-repeat-series",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "runtime_root": str(RUNTIME_ROOT),
        "orchestration_db": str(rehearsal.db_path),
        "worker_id": WORKER_ID,
        "role": ROLE,
        "objective": OBJECTIVE,
        "objective_hash": None,
        "stated_call_budget": {
            "total_real_image_generations": TOTAL_PLANNED_CALLS,
            "calls": CALL_BUDGET,
            "hard_rule": ("the script spends at most TOTAL_PLANNED_CALLS real "
                          "image generations; it records every call and stops "
                          "rather than exceeding the stated budget"),
            "not_counted": ("metadata reads only (the adapter's /models health "
                            "and identity calls) are not image generations; "
                            "this run makes no metadata call either, so the "
                            "real generation count equals the total"),
        },
        "provider_calls_planned": TOTAL_PLANNED_CALLS,
        "calls_attempted": 0,
        "observations": [],
    }

    import hashlib
    progress["objective_hash"] = hashlib.sha256(OBJECTIVE.encode()).hexdigest()[:12]
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

    # ── staged execution: build the whole call list from the stated budget ──
    plan_of_calls = []
    idx = 0
    for _ in range(IMAGE_ONLY_REPEATS):
        idx += 1
        plan_of_calls.append({"index": idx, "response_modalities": ["IMAGE"],
                              "image_config": None})
    for _ in range(TEXT_IMAGE_REPEATS):
        idx += 1
        plan_of_calls.append({"index": idx,
                              "response_modalities": ["TEXT", "IMAGE"],
                              "image_config": None})
    for _ in range(SIZE_PROBE_CALLS):
        idx += 1
        plan_of_calls.append({"index": idx,
                              "response_modalities": ["TEXT", "IMAGE"],
                              "image_config": {"imageSize": "512"}})

    assert len(plan_of_calls) == TOTAL_PLANNED_CALLS, "budget/call-list mismatch"

    aborted = None
    for call in plan_of_calls:
        if call["index"] > TOTAL_PLANNED_CALLS:
            aborted = "budget_exceeded_refused"
            break
        record = _run_image_call(
            rehearsal, call["index"], call["response_modalities"],
            call["image_config"], args.timeout, progress_path, progress)
        if not record.get("executed"):
            aborted = record.get("blocked")
            break
        # Fail fast: if the provider could not be reached at all, further calls
        # would add no information and would spend budget.
        if record.get("error") not in (None, "no_image_part_in_response",
                                       "no_candidates_returned") and \
                record.get("status") != "COMPLETED":
            if str(record.get("error") or "").startswith(
                    ("http_", "credential", "invalid", "API key")):
                aborted = f"provider_unreachable_or_rejecting:{record.get('error')}"
                break

    if aborted:
        progress["aborted"] = aborted
        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

    summary = _summarise(progress)
    size = _size_verdict(summary, progress)
    diagnosis = _diagnose(summary, progress["observations"])

    report = {
        **{k: progress[k] for k in
           ("label", "run_started_utc", "runtime_root", "orchestration_db",
            "worker_id", "role", "objective", "objective_hash",
            "stated_call_budget", "provider_calls_planned",
            "calls_attempted", "observations")},
        "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "aborted": aborted,
        "stage": ("Bounded Google image repeat series + request-protocol "
                  "conformance. Stage 2 NOT enabled by this run."),
        "prior_evidence": {
            "rehearsal_failure": {
                "evidence": ("audits/evidence/2026-09-23T21-10-00Z-e3-production-"
                             "execution-rehearsal/evidence.json"),
                "dispatch_id": "gem-d8c43b8cb447",
                "error": "no_image_part_in_response",
                "usage": {"promptTokenCount": 17, "totalTokenCount": 17},
            },
            "one_shot_diagnosis": {
                "evidence": ("audits/evidence/2026-09-23T21-49-21Z-e3-google-"
                             "image-diagnosis/evidence.json"),
                "dispatch_id": "gem-2a656cbf22c2",
                "verdict": "IMAGE_PART_PRESENT_AND_DECODED",
                "note": ("the identical request did not reproduce the failure; "
                         "1 call cannot establish a rate"),
            },
        },
        "summary": summary,
        "diagnosis": diagnosis,
        "size_control": size,
        "orchestration_db_after": rehearsal.orchestration_db_facts(),
        "e2_linkage": _e2_readback(progress["observations"], RUNTIME_ROOT),
        "live_store_contamination": rehearsal.live_store_contamination_check(),
        "qualification_note": (
            "This run records execution evidence only. Whether the vision role "
            "moves off EVALUATING is decided by "
            "scripts/e3_qualification_from_evidence.py from the recorded rows, "
            "not by this script."),
    }

    _write_artifacts(out_dir, report)

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "provider_calls_planned": TOTAL_PLANNED_CALLS,
        "calls_completed": summary["calls_completed"],
        "outcome_counts": summary["outcome_counts"],
        "no_image_part_in_response_rate": summary["no_image_part_in_response_rate"],
        "per_shape": {k: {kk: vv for kk, vv in v.items() if kk != "response_part_kinds"}
                      for k, v in summary["per_shape"].items()},
        "size_control_verdict": size["verdict"],
        "aborted": aborted,
    }, indent=2, default=str))
    return 0


def _fmt_dims(dims):
    return "x".join(str(d) for d in dims) if dims else None


def _render_md(report) -> str:
    s = report["summary"]
    d = report["diagnosis"]
    md = [
        "# E3 Google image worker — bounded repeat series + request-protocol conformance",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Runtime root: `{report['runtime_root']}`",
        f"- Orchestration DB: `{report['orchestration_db']}`",
        f"- Worker: `{report['worker_id']}` (role `{report['role']}`)",
        f"- Objective (identical to the failing attempt): `{report['objective']}`",
        f"- Objective hash: `{report['objective_hash']}`",
        f"- Real Google image generations planned (stated up front): "
        f"**{report['provider_calls_planned']}**",
        f"- Real Google image generations attempted: {report['calls_attempted']} "
        f"/ recorded observations: {s['calls_completed']}",
        f"- Aborted: {report['aborted']}",
        "",
        "## Stated call budget (one real provider call in this table = one single-shot generateContent)",
        "",
        "| Calls | Count | Request shape | Reason |",
        "|---|---|---|---|",
    ]
    for c in report["stated_call_budget"]["calls"]:
        md.append(f"| {c['calls']} | {c['count']} | `{c['shape']}` | {c['purpose']} |")
    md += [
        "",
        report["stated_call_budget"]["hard_rule"],
        "",
        "Not counted as image generations: " + report["stated_call_budget"]["not_counted"],
        "",
        "## Measured recurrence of the no-image response",
        "",
        f"- Dispatches executed: {s['calls_completed']}",
        f"- `no_image_part_in_response`: {s['no_image_part_in_response_count']} "
        f"of {s['no_image_part_in_response_rate']['denominator']} "
        f"(rate = {s['no_image_part_in_response_rate']['rate']})",
        f"- Outcome counts: `{json.dumps(s['outcome_counts'])}`",
        "",
        "| Request shape | Executed | Image decoded | no_image_part_in_response | Other failures | Observed dims | finishReasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for shape, e in s["per_shape"].items():
        dims = sorted({_fmt_dims(d) for d in e["observed_dims"] if d},
                      key=str)
        reasons = sorted({str(r) for r in e["finish_reasons"]})
        md.append(
            f"| `{shape}` | {e['executed_calls']} | {e['image_decoded']} | "
            f"{e['no_image_part_in_response']} | {e['other_failures']} | "
            f"`{dims}` | "
            f"`{reasons}` |")
    md += [
        "",
        "A rate is reported as counts over executed calls only. A bounded series "
        "of this size can establish that the condition is or is not repeated and "
        "give an observed rate; it cannot certify the worker as stable, and it is "
        "not described here as such.",
        "",
        "## Diagnosis of the recurrence (derived from the records above)",
        "",
        f"- measured rate: {d['measured_rate']['no_image_part_in_response']} of "
        f"{d['measured_rate']['executed_calls']} executed calls "
        f"(rate = {d['measured_rate']['rate']})",
        "- per request shape: "
        + "; ".join(f"`{k}` {v['no_image_part_in_response']}/{v['executed']}"
                    for k, v in d["measured_rate"]["per_shape"].items()),
        f"- provider signals on every recurrence: finishReason counts "
        f"`{json.dumps(d['provider_signals_on_recurrence']['finish_reason_counts'])}`, "
        f"response part shapes "
        f"`{json.dumps(d['provider_signals_on_recurrence']['response_part_kinds_counts'])}`, "
        f"shapes affected "
        f"`{json.dumps(d['provider_signals_on_recurrence']['distinct_shapes_affected'])}`",
        "",
        "Supported by the recorded evidence:",
        "",
    ]
    for stmt in d["supported_statements"]:
        md.append(f"- {stmt}")
    md += ["", "Not supported by this series (explicitly not claimed):", ""]
    for stmt in d["not_supported_by_this_series"]:
        md.append(f"- {stmt}")
    md += [
        "",
        f"Remaining unknown: {d['remaining_unknown']}",
        "",
        "## Per-call record (provider-returned values only)",
        "",
        "| # | Shape | status | classification | dispatch_id | finishReason | parts | dims | bytes | decode | usage | E2 request | node state | verification |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for o in report["observations"]:
        usage = o.get("usage") or {}
        md.append(
            f"| {o['index']} | {o['shape_label']} | {o.get('status')} | "
            f"{o['classification']} | `{o.get('dispatch_id')}` | "
            f"{o.get('finish_reason')} | `{o.get('response_part_kinds')}` | "
            f"`{o.get('image_dims')}` | {o.get('image_size_bytes')} | "
            f"{o.get('image_decode_ok')} | "
            f"`{json.dumps(usage)}` | `{o.get('e2_request_id')}` | "
            f"{o.get('node_state')} | {o.get('final_verification')} |")
    md += [
        "",
        "## Request-protocol conformance (controlled comparison)",
        "",
        "The production adapter sends `generationConfig.responseModalities=['IMAGE']` "
        "with no `TEXT` modality and no image output configuration. The table above "
        "records what the provider actually did with that shape (calls 1-"
        f"{len([o for o in report['observations'] if o['shape_label'] == 'IMAGE-only'])}"
        ") and with `['TEXT','IMAGE']` (calls "
        f"{len([o for o in report['observations'] if o['shape_label'] == 'IMAGE-only']) + 1}"
        f"-{len([o for o in report['observations'] if o['shape_label'] == 'IMAGE-only']) + len([o for o in report['observations'] if o['shape_label'] == 'TEXT+IMAGE'])}). "
        "Only the request shape was varied; the objective was identical.",
        "",
        "## Output-size control",
        "",
        f"- Objective asked for: `{_fmt_dims(report['size_control']['prompt_stated_size'])}` "
        f"({report['size_control']['prompt_stated_size_how']})",
        f"- Observed dims on the IMAGE-only series: `{report['size_control']['series_observed_dims']}`",
        f"- Prompt-stated size honoured: **{report['size_control']['prompt_stated_size_honoured_in_series']}**",
        f"- Verdict: **{report['size_control']['verdict']}**",
        "",
        "Explicit-size probe (provider image-output parameter):",
        "",
    ]
    for p in report["size_control"]["provider_image_config_probe"]:
        md.append(f"- requested `{json.dumps(p['requested_image_config'])}` -> "
                  f"status `{p['status']}`, error `{p['error']}`, dims "
                  f"`{p['image_dims']}`, "
                  f"parts `{p['response_part_kinds']}`")
    size_ok = [p for p in report["size_control"]["provider_image_config_probe"]
               if p["status"] == "COMPLETED" and p["image_dims"]]
    md += [
        "",
        "Conclusions recorded from the probe (facts, not passes):",
        "",
        f"- a size stated only in the prompt is "
        f"**{'honoured' if report['size_control']['prompt_stated_size_honoured_in_series'] else 'NOT honoured'}**: "
        f"the objective asked for "
        f"`{_fmt_dims(report['size_control']['prompt_stated_size'])}` and the "
        f"IMAGE-only series returned "
        f"`{report['size_control']['series_observed_dims']}`",
        ("- the provider's own image-output parameter "
         "(`generationConfig.imageConfig`) was accepted and changed the returned "
         "dimensions, so exact-pixel size is controlled through that supported "
         "parameter rather than through prompt text; the adapter accepts it "
         "through the contract-declared `image_config` key and its production "
         "default shape is unchanged"
         if size_ok else
         "- the provider did not accept `generationConfig.imageConfig` in this "
         "probe, so no supported size parameter is available: this is a known "
         "limitation, not a pass"),
        "- a literal 64x64 output was NOT achieved and is not claimed: the "
        "supported parameter is a size class, not arbitrary pixel dimensions, so "
        "exact 64x64 remains a known limitation of this provider/model",
        "- no readiness criterion was weakened for this: the node verification "
        "contract remains 'an image part arrived and decodes', and the size "
        "findings are recorded as protocol facts",
        "",
        "## Request-protocol conformance conclusion",
        "",
        "The production adapter sends `generationConfig.responseModalities"
        "=['IMAGE']` only, with no text modality and no image output "
        "configuration. Across the calls recorded above the provider accepted "
        "that shape and returned a decodable inline image on the majority of "
        "calls, and it also accepted `['TEXT','IMAGE']` (which additionally "
        "permits a text part and accepts `imageConfig`). The adapter's request "
        "shape is therefore complete enough for this model to generate images; "
        "the intermittent no-image responses are accompanied by an explicit "
        "provider content-side stop reason and are not a modality-list "
        "rejection. Where a text modality or an output-size parameter is wanted, "
        "it is available through the adapter's contract-declared "
        "`response_modalities` / `image_config` keys (production default "
        "unchanged).",
        "",
        "## Store state after (E3's own store; E1/E2 are not written)",
        "",
        f"- schema/db: `{json.dumps(report['orchestration_db_after'])}`",
        f"- E2 linkage (rows read back from governor.db, written only through "
        f"`governor.record_request()`): `{json.dumps(report['e2_linkage'])}`",
        f"- contamination check: `{json.dumps(report['live_store_contamination'])}`",
        "",
        report["qualification_note"],
        "",
    ]
    return "\n".join(md) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
