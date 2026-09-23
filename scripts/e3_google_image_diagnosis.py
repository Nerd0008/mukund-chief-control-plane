#!/usr/bin/env python3
"""Bounded diagnosis of the Google image worker's real-dispatch failure.

Scenario D of the E3 production execution rehearsal dispatched
``google-nano-banana-2`` (``gemini-3.1-flash-image``) once on the real path and
the provider returned **no image part** (``no_image_part_in_response``, 17
prompt tokens, 0 output tokens). The root cause was not determined, because the
attempt record of that run did not yet capture ``finish_reason`` /
``prompt_feedback`` / the response part shape.

This driver spends **exactly one** additional bounded Google image call on the
*same* real path (deployed runtime → ``ExecutionAdapterRegistry`` →
``GeminiImageExecutionAdapter`` → ``generateContent``), and records from the
adapter response:

* HTTP/dispatch status and the provider error string;
* ``finish_reason`` and ``promptFeedback``;
* candidate count and per-candidate ``finishReason`` (sanitized);
* the part shape of every candidate (``text`` / ``inlineData:<mime>``);
* a bounded excerpt of any text part (provider output, truncated, no secrets);
* image mime / dimensions / size and whether the bytes header-decode;
* provider-returned usage (never estimated);
* the deterministic verifier verdict, the persisted DAG state/evidence row and
  the E2 request id written through the public ``governor.record_request()``
  interface.

It writes its findings under ``audits/evidence/<UTC>-e3-google-image-diagnosis/``
and never enables Stage 2, never edits a worker's routability, and never marks a
qualification.

Usage:
    python scripts/e3_google_image_diagnosis.py [--out-dir DIR]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# Runs against the *deployed* runtime modules: that is the path under diagnosis.
sys.path.insert(0, str(RUNTIME_ROOT))

PLANNED_GOOGLE_IMAGE_CALLS = 1


def _diagnose(attempts, scenario):
    """Derive a truthful diagnosis from the recorded attempt fields only."""
    d = {
        "provider_call_spent": len(attempts),
        "verdict": None,
        "deterministic_factors": [],
        "remaining_unknown": None,
    }
    if not attempts:
        d["verdict"] = "NO_DISPATCH_RECORDED"
        d["remaining_unknown"] = (
            "no dispatch attempt reached the adapter; check routing/routability "
            "and credential presence before re-running")
        return d

    a = attempts[0]
    finish = a.get("finish_reason")
    feedback = a.get("prompt_feedback")
    kinds = a.get("response_part_kinds") or []
    cands = a.get("candidate_count")
    decode_ok = a.get("image_decode_ok")
    error = a.get("error")

    d["deterministic_factors"] = [
        f"status={a.get('status')}",
        f"error={error}",
        f"finish_reason={finish}",
        f"candidate_count={cands}",
        f"response_part_kinds={kinds}",
        f"image_decode_ok={decode_ok}",
        f"prompt_feedback={feedback}",
    ]

    if decode_ok:
        d["verdict"] = "IMAGE_PART_PRESENT_AND_DECODED"
        d["failure_reproduced"] = False
        d["remaining_unknown"] = (
            "the earlier no-image response did NOT reproduce on the identical "
            "request: the same objective and the same adapter request path now "
            "returned a decodable inline image with a normal STOP finish and "
            "provider-reported candidate tokens. The cause of the single earlier "
            "'no_image_part_in_response' response (17 prompt tokens, 0 output "
            "tokens, no image part) is therefore intermittent and is NOT "
            "explained by the request shape. Remaining unknown: the trigger of "
            "that intermittent provider response; one observation cannot "
            "distinguish provider-side variability from a transient capacity or "
            "content-moderation condition. Resolving it needs a bounded repeat "
            "series, not an assumption.")
        return d

    if error == "credential_absent":
        d["verdict"] = "CREDENTIAL_ABSENT"
        d["remaining_unknown"] = "no credential available to the adapter"
        return d

    if error and str(error).startswith(("http_", "invalid", "API key")):
        d["verdict"] = "PROVIDER_REJECTED_REQUEST"
        d["remaining_unknown"] = (
            "the provider rejected the request before generation; the error "
            "string above is the provider's own message")
        return d

    if error == "no_candidates_returned" or cands == 0:
        d["verdict"] = "NO_CANDIDATES_RETURNED"
        d["remaining_unknown"] = (
            "the provider returned no candidate at all; prompt_feedback above is "
            "the only provider-supplied reason")
        return d

    if finish in ("IMAGE_SAFETY", "SAFETY", "PROHIBITED_CONTENT", "RECITATION",
                  "BLOCKLIST"):
        d["verdict"] = "PROVIDER_SAFETY_STOP"
        d["remaining_unknown"] = (
            "the provider stopped generation for safety/policy reasons; the "
            "specific policy trigger is not exposed by the API")
        return d

    if kinds == ["text"] or (kinds and all(k == "text" for k in kinds)):
        d["verdict"] = "TEXT_ONLY_RESPONSE"
        d["remaining_unknown"] = (
            "the model answered with text only and produced no image part. The "
            "diagnosed request declared responseModalities=['IMAGE'] with no "
            "TEXT modality and no image output-config; whether this model "
            "version tolerates an IMAGE-only modality list (versus requiring "
            "['TEXT','IMAGE'] or an explicit image output configuration) is the "
            "remaining unknown and must be confirmed by a controlled A/B "
            "dispatch, not assumed here.")
        return d

    if finish == "STOP" and not kinds:
        d["verdict"] = "EMPTY_STOP"
        d["remaining_unknown"] = (
            "candidate finished with STOP but carried no parts; provider-side "
            "behaviour not explained by the response body")
        return d

    d["verdict"] = "UNCLASSIFIED"
    d["remaining_unknown"] = (
        "response shape not covered by the recorded diagnostic rules; the "
        "deterministic factors above are the full evidence")
    return d


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--from-evidence", default=None,
                        help=("re-derive the diagnosis from a previously "
                              "captured response artifact; spends NO provider "
                              "call"))
    args = parser.parse_args()

    started = datetime.now(timezone.utc)

    if args.from_evidence:
        # Re-derivation path. The provider response is already captured in that
        # artifact, so this branch must never dispatch anything.
        report = json.loads(Path(args.from_evidence).read_text(encoding="utf-8"))
        scenario = report["scenario"]
        report["diagnosis"] = _diagnose(scenario.get("dispatch_attempts") or [],
                                        scenario)
        report["rederived"] = {
            "from_evidence": args.from_evidence,
            "rederived_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "extra_provider_calls_spent": 0,
            "note": ("diagnosis re-derived from the provider response already "
                     "captured in that artifact; no additional provider call, "
                     "no new execution"),
        }
        db_path = report.get("orchestration_db")
        out_dir = (Path(args.out_dir) if args.out_dir
                   else Path(args.from_evidence).parent)
        return _write(out_dir, report, scenario, db_path)

    from e3_execution_rehearsal import E3ExecutionRehearsal

    rehearsal = E3ExecutionRehearsal()
    # One bounded real Google image call, on the same path the failing run used.
    scenario = rehearsal.scenario_google_image()
    db_path = str(rehearsal.db_path)

    report = {
        "label": "e3-google-image-diagnosis",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": ("Bounded diagnosis of the Google image worker's real-dispatch "
                  "failure (scenario D). Stage 2 NOT enabled by this run."),
        "runtime_root": str(RUNTIME_ROOT),
        "orchestration_db": str(rehearsal.db_path),
        "objective": scenario.get("objective"),
        "objective_note": ("objective hash only in the adapter metadata; the "
                           "objective text is the same deterministic single-shot "
                           "prompt the failing run used"),
        "usage_plan": {
            "real_google_image_calls": PLANNED_GOOGLE_IMAGE_CALLS,
            "why": ("the failing response captured no finish_reason / "
                    "prompt_feedback / part shape, so exactly one additional "
                    "call on the identical request is the minimum that can "
                    "resolve the failure without guessing"),
        },
        "bounded_usage": {
            "real_google_image_calls": len(scenario.get("dispatch_attempts") or []),
        },
        "scenario": scenario,
        "prior_failing_attempt_reference": {
            "evidence": ("audits/evidence/2026-09-23T21-10-00Z-e3-production-"
                         "execution-rehearsal/evidence.json"),
            "dispatch_id": "gem-d8c43b8cb447",
            "error": "no_image_part_in_response",
            "usage": {"promptTokenCount": 17, "totalTokenCount": 17},
        },
    }
    report["diagnosis"] = _diagnose(scenario.get("dispatch_attempts") or [], scenario)
    report["orchestration_db_after"] = rehearsal.orchestration_db_facts()
    report["e2_linkage"] = rehearsal.e2_linkage_audit()
    report["live_store_contamination"] = rehearsal.live_store_contamination_check()

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-google-image-diagnosis")
    return _write(out_dir, report, scenario, db_path)


def _write(out_dir, report, scenario, db_path):
    """Render the evidence artifacts from a report dict (no provider call)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")

    att = (scenario.get("dispatch_attempts") or [{}])[0]
    md = [
        "# E3 Google image worker — bounded real-dispatch diagnosis",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Runtime root: `{RUNTIME_ROOT}`",
        f"- Orchestration DB: `{db_path}`",
        f"- Real Google image calls spent: {report['bounded_usage']['real_google_image_calls']}"
        f" (planned {PLANNED_GOOGLE_IMAGE_CALLS})",
        f"- Objective (unchanged from the failing run): `{scenario.get('objective')}`",
        "",
        "## Adapter response (provider-returned only)",
        "",
        f"- dispatch_id: `{att.get('dispatch_id')}`",
        f"- status: `{att.get('status')}` / error: `{att.get('error')}`",
        f"- provider/model: `{att.get('provider')}` / `{att.get('model')}`"
        f" (requested `{att.get('requested_model')}`)",
        f"- finish_reason: `{att.get('finish_reason')}`",
        f"- candidate_count: `{att.get('candidate_count')}`"
        f" / candidate_finish_reasons: `{att.get('candidate_finish_reasons')}`",
        f"- response_part_kinds: `{att.get('response_part_kinds')}`",
        f"- response_text_chars: `{att.get('response_text_chars')}`",
        f"- response_text_excerpt: `{att.get('response_text_excerpt')}`",
        f"- prompt_feedback: `{att.get('prompt_feedback')}`",
        f"- image_mime: `{att.get('image_mime')}` / image_dims: `{att.get('image_dims')}`"
        f" / image_size_bytes: `{att.get('image_size_bytes')}`"
        f" / image_decode_ok: `{att.get('image_decode_ok')}`",
        f"- usage: `{json.dumps(att.get('usage'))}`",
        f"- E2 request id (via `governor.record_request()`): `{att.get('e2_request_id')}`",
        "",
        "## Deterministic verifier",
        "",
        f"- final_verification: `{scenario.get('final_verification')}`",
        f"- node_state: `{scenario.get('node_state')}`"
        f" / persisted: `{scenario.get('persisted_node_state')}`",
        f"- evidence_id: `{scenario.get('evidence_id')}`",
        "",
        "## Diagnosis",
        "",
        f"- verdict: **{report['diagnosis']['verdict']}**",
    ]
    for factor in report["diagnosis"]["deterministic_factors"]:
        md.append(f"  - {factor}")
    md += [
        "",
        f"- remaining_unknown: {report['diagnosis']['remaining_unknown']}",
        "",
        "## Observations recorded (no interpretation)",
        "",
        f"- requested by the objective: a 64x64 solid white square; returned "
        f"image: {att.get('image_dims')} {att.get('image_mime')} "
        f"({att.get('image_size_bytes')} bytes). The declared deterministic "
        f"verification contract for this node is 'image decoded', not a "
        f"dimension check, so the PASS above is the contract's verdict and is "
        f"not evidence that the requested dimensions were honoured.",
        f"- provider usage on the successful call: prompt { (att.get('usage') or {}).get('promptTokenCount') } "
        f"/ candidate { (att.get('usage') or {}).get('candidatesTokenCount') } "
        f"(IMAGE modality { ((att.get('usage') or {}).get('candidatesTokensDetails') or [{}])[0].get('tokenCount') }).",
        "",
        ("The worker's routability is unchanged by this run. This run produced "
         "one real successful image execution; whether that is enough to qualify "
         "the worker is decided separately from recorded evidence, never from "
         "this narrative."
         if report["diagnosis"]["verdict"] == "IMAGE_PART_PRESENT_AND_DECODED" else
         "The worker's routability and qualification are untouched by this run; "
         "no successful image execution was recorded and none is claimed."),
        "",
    ]
    (out_dir / "evidence.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "diagnosis": report["diagnosis"],
        "bounded_usage": report["bounded_usage"],
        "node_state": scenario.get("node_state"),
        "final_verification": scenario.get("final_verification"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
