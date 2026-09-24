#!/usr/bin/env python3
"""Submission Gate (roster B18) — deterministic owner-approval gate.

The one rule that matters: **no external application action ever happens from
this system**. This gate implements no code path that submits, emails, uploads,
messages, connects or creates an account anywhere. What it does is decide,
deterministically, whether a reviewed application pack is *eligible to be
presented* to the owner for a manual submission, and produce an owner checklist.

It refuses, always, for any of:
  * the reviewer's verdict is "block";
  * the reviewer did not verify truthfulness;
  * no owner approval record exists;
  * the approval record does not bind to this exact pack (pack_id + pack_sha256);
  * the pack changed after approval (the recorded hash no longer matches);
  * the pack still has unresolved owner-input items and the approval does not
    explicitly acknowledge them;
  * the approval record is sourced from inside the repository (a committed file
    is not an owner action).

Every decision is logged to a JSONL action-gate log, and every decision records
``external_action_performed: false``.

CLI
  python career-ops/submission_gate.py actions
  python career-ops/submission_gate.py guard --action submit_application
  python career-ops/submission_gate.py status --review PACK_REVIEW.json [--approval F]
                                         [--out DIR] [--pack-dir DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

CONFIG_PATH = CAREER_OPS_DIR / "job_intelligence_config.json"

# Every action that would leave this machine or touch an employer/recruiter
# account. All are owner-gated; none has an implementation here.
EXTERNAL_ACTIONS = (
    "submit_application", "apply", "easy_apply", "linkedin_apply",
    "upload_cv", "upload_cover_letter", "email_employer", "send_cv",
    "recruiter_contact", "message_employer", "create_employer_account",
    "post_application", "accept_offer", "sign_contract",
)

POLICY = (
    "External application actions are OWNER-GATED without exception. This gate "
    "implements no submission path: with a valid owner approval it produces an "
    "owner checklist and stops. Nothing is submitted, sent, uploaded or accepted."
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    cfg = json.loads(read_text(p))
    cfg["_config_path"] = str(p)
    return cfg


def runtime_dir(cfg: dict) -> Path:
    return CONTROL_PLANE / cfg["runtime_dir"]


def log_path(cfg: dict) -> Path:
    return runtime_dir(cfg) / "submission-gate-log.jsonl"


def _log(cfg: dict, record: dict) -> str:
    path = log_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return str(path)


def guard_action(cfg: dict, action: str) -> dict:
    """Refuse every external action, deterministically, and record the refusal."""
    key = (action or "").strip().casefold()
    is_external = key in EXTERNAL_ACTIONS
    result = {
        "action": action,
        "external": is_external,
        "allowed": False,
        "owner_gated": True,
        "performed": False,
        "status": "refused" if is_external else "not_an_external_action",
        "reason": (POLICY if is_external else
                   "not a recognised external application action; still not performed"),
        "available_paths": ["brief", "review", "owner checklist", "dry-run"],
        "logged_to": None,
        "at": now_utc(),
    }
    result["logged_to"] = _log(cfg, result)
    return result


def _approval_problems(approval: dict, review: dict, approval_path: Path | None) -> list[str]:
    problems: list[str] = []
    required = ("approved_by", "approved_at", "pack_id", "pack_sha256", "approved_action")
    missing = [k for k in required if not str(approval.get(k) or "").strip()]
    if missing:
        problems.append(f"approval record is missing required field(s): {', '.join(missing)}")
    action = str(approval.get("approved_action") or "").strip().casefold()
    if action and action not in EXTERNAL_ACTIONS:
        problems.append(f"approved_action {approval.get('approved_action')!r} is not a "
                        "recognised external application action")
    if approval.get("pack_id") != review.get("pack_id"):
        problems.append(f"approval binds pack_id {approval.get('pack_id')!r} but the reviewed "
                        f"pack is {review.get('pack_id')!r}")
    if approval.get("pack_sha256") != review.get("pack_sha256"):
        problems.append("approval binds a different pack hash — the pack changed after approval, "
                        "or the approval belongs to another pack")
    if review.get("verdict") == "pass_with_owner_input_required":
        if not approval.get("acknowledged_unknowns"):
            problems.append("the pack still has unresolved owner-input items and the approval "
                            "does not set acknowledged_unknowns: true")
    if approval_path is not None:
        try:
            Path(approval_path).resolve().relative_to(CONTROL_PLANE.resolve())
            problems.append("the approval record is sourced from inside the repository; a "
                            "committed file is not an owner action")
        except ValueError:
            pass
    return problems


def decide(cfg: dict, review: dict, *, approval: dict | None = None,
           approval_path: Path | None = None, pack_dir: Path | None = None,
           checklist_path: Path | None = None) -> dict:
    blockers = review.get("blockers") or []
    base = {
        "gate": "career-ops/submission_gate.py",
        "gate_role": "B18 Submission Gate / owner-approval handoff",
        "policy": POLICY,
        "decided_at": now_utc(),
        "pack_id": review.get("pack_id"),
        "pack_sha256": review.get("pack_sha256"),
        "brief_id": review.get("brief_id"),
        "job": review.get("job"),
        "reviewer_verdict": review.get("verdict"),
        "external_action_performed": False,
        "external_actions_taken": [],
    }

    if review.get("verdict") == "block" or blockers:
        result = {**base, "status": "refused", "submission_eligible": False,
                  "reason": "the reviewer blocked this pack; truthfulness/consistency/formatting "
                            "defects must be fixed before any owner decision",
                  "blockers": blockers,
                  "owner_action_required": None}
        result["logged_to"] = _log(cfg, result)
        return result

    if review.get("truthfulness_verified") is not True:
        result = {**base, "status": "refused", "submission_eligible": False,
                  "reason": "the reviewer did not verify truthfulness for this pack",
                  "owner_action_required": None}
        result["logged_to"] = _log(cfg, result)
        return result

    if not approval:
        result = {
            **base, "status": "awaiting_owner_approval", "submission_eligible": False,
            "reason": "no owner approval record exists for this exact pack",
            "owner_input_required": review.get("owner_input_required") or [],
            "owner_action_required": (
                "Review the pack yourself, then approve this exact pack "
                f"({review.get('pack_id')}, sha256 {str(review.get('pack_sha256'))[:16]}…) by "
                "creating an approval record OUTSIDE this repository, e.g. "
                "%LOCALAPPDATA%\\hermes\\secrets\\application-approvals\\<pack>.json with "
                "{\"approved_by\": \"Mukund\", \"approved_at\": ISO8601, "
                f"\"pack_id\": \"{review.get('pack_id')}\", "
                f"\"pack_sha256\": \"{review.get('pack_sha256')}\", "
                "\"approved_action\": \"submit_application\", "
                "\"acknowledged_unknowns\": true|false}. Then re-run: python "
                "career-ops/submission_gate.py status --review <pack_review.json> "
                "--approval <that file>"),
            "note": "This gate performs no submission itself; a valid approval produces an owner "
                    "checklist only.",
        }
        result["logged_to"] = _log(cfg, result)
        return result

    problems = _approval_problems(approval, review, approval_path)
    if problems:
        result = {**base, "status": "refused", "submission_eligible": False,
                  "reason": "the supplied approval record is not valid for this pack",
                  "approval_problems": problems,
                  "owner_action_required": "Re-issue a valid approval record bound to this pack.",
                  "approval": {k: v for k, v in approval.items() if k != "pack_sha256"}}
        result["logged_to"] = _log(cfg, result)
        return result

    checklist = {
        "pack_id": review.get("pack_id"),
        "pack_sha256": review.get("pack_sha256"),
        "job": review.get("job"),
        "approved_by": approval.get("approved_by"),
        "approved_at": approval.get("approved_at"),
        "approved_action": approval.get("approved_action"),
        "artifacts": review.get("artifact_hashes"),
        "owner_input_required": review.get("owner_input_required") or [],
        "manual_steps": [
            "Open the CV draft and the rendered cover letter and read them as the owner.",
            "Confirm every substantive sentence is something you can stand behind.",
            "Check the posting is still live before applying.",
            "Submit manually through the employer's own channel — the system will not do it.",
            "Record the application in the Career Ops tracker afterwards.",
        ],
        "not_performed": ["PDF export (headless Chromium, owner-gated)",
                          "application submission", "employer/recruiter contact"],
    }
    if pack_dir:
        checklist["pack_dir"] = str(pack_dir)
    out_path = checklist_path or (
        runtime_dir(cfg) / "checklists" / f"{review.get('pack_id')}-owner-checklist.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(checklist, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    result = {
        **base, "status": "approved_pending_owner_manual_submission",
        "submission_eligible": True,
        "reason": "a valid owner approval binds this exact pack; the system still performs no "
                  "external action — submission is a manual owner step",
        "checklist": checklist,
        "checklist_path": str(out_path),
        "owner_action_required": ("Submit the application manually through the employer's channel; "
                                 "the system will not submit it. Then record the application in "
                                 "the Career Ops tracker."),
        "approval": {k: v for k, v in approval.items() if k != "pack_sha256"},
    }
    result["logged_to"] = _log(cfg, result)
    return result


def cmd_actions(args) -> int:
    sys.stdout.write(json.dumps({
        "external_actions": list(EXTERNAL_ACTIONS),
        "policy": POLICY,
        "any_implemented": False,
        "note": "Every action above is refused; see guard_action / `guard`.",
        "external_actions_taken": [],
    }, indent=2) + "\n")
    return 0


def cmd_guard(args) -> int:
    cfg = load_config(args.config)
    sys.stdout.write(json.dumps(guard_action(cfg, args.action), indent=2, ensure_ascii=False) + "\n")
    return 0


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    review = json.loads(read_text(args.review))
    approval = None
    if args.approval:
        approval = json.loads(read_text(args.approval))
    result = decide(cfg, review, approval=approval,
                    approval_path=Path(args.approval) if args.approval else None,
                    pack_dir=Path(args.pack_dir) if args.pack_dir else None,
                    checklist_path=Path(args.checklist) if args.checklist else None)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "submission_gate.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        result["recorded_to"] = str(out_dir / "submission_gate.json")
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n")
    return 0 if result["status"] != "refused" else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Submission Gate (B18)")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("actions"); p.set_defaults(fn=cmd_actions)
    p = sub.add_parser("guard"); p.add_argument("--action", required=True); p.set_defaults(fn=cmd_guard)
    p = sub.add_parser("status")
    p.add_argument("--review", required=True)
    p.add_argument("--approval")
    p.add_argument("--checklist")
    p.add_argument("--pack-dir")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_status)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
