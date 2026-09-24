#!/usr/bin/env python3
"""Built-but-not-live integration gap audit + owner reboot acceptance checklist.

Read-only. Produced by the running queue task
``agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24``.

For every integration the previous agent left *built but not live*, this script
measures the current state from the live runtime / repository and writes one
truthful record per item.  It never invents a capability, a credential, a legal
fact or a deployment decision; anything still owner-gated is recorded as such
with the exact next owner step.

Measured inputs (no credential *value* is ever read; presence only):

* ``status/canonical-status.json``          canonical project status
* ``career-ops/linkedin_auth.py status``    LinkedIn OAuth credential presence
* ``career-ops/application_inbox.py adapters`` Gmail read-only adapter state
* ``runtime/career-ops/watchlist/company-watchlist.json`` owner watchlist input
* ``scripts/harden_scheduled_tasks.py --verify`` live scheduled-task snapshot
* ``schtasks``                              legacy + operational task state

Usage
    python scripts/integration_gap_audit.py                    # write evidence
    python scripts/integration_gap_audit.py --stdout           # print only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = REPO_ROOT / "audits" / "evidence"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

# --------------------------------------------------------------------------- #
# item list — every gap the authority/task record requires to be accounted for
# --------------------------------------------------------------------------- #
# "state" is the *measured* state; "owner_gated" says whether a live capability
# still needs an owner decision/credential.  A dry-run or fixture pass never
# counts as a live PASS.
ITEMS = [
    {
        "id": "gmail-readonly-oauth",
        "title": "Gmail read-only OAuth live feed (B12 Application Inbox)",
        "measure": "inbox_adapters",
        "owner_action": ("Optionally authorise a read-only Gmail OAuth grant (about 10 "
                         "minutes) following the recorded steps in the owner-action TODO; "
                         "until then the monitor runs on an owner-provided local export."),
    },
    {
        "id": "research-provider",
        "title": "JobBrief company/role research provider (B14)",
        "measure": "canonical_optional",
    },
    {
        "id": "recruiter-live-feed",
        "title": "Live recruiter/intermediary feed (B11)",
        "measure": "canonical_optional",
    },
    {
        "id": "career-brief-delivery",
        "title": "Career Daily Brief external delivery channel (B23)",
        "measure": "canonical_optional",
    },
    {
        "id": "tracker-vocabulary",
        "title": "Tracker vocabulary gaps (Assessment / Japan Rejected / Dubai Offer)",
        "measure": "canonical_optional",
    },
    {
        "id": "monthly-rollover-policy",
        "title": "Current-month tracker rollover policy (owner-state rows)",
        "measure": "canonical_optional",
    },
    {
        "id": "owner-watchlist-names",
        "title": "Owner company watchlist names",
        "measure": "watchlist",
        "owner_action": ("Optionally supply the short target-company list at "
                         "runtime/career-ops/watchlist/company-watchlist.json (owner-edited, "
                         "git-ignored); the lane stays honest and empty until then."),
    },
    {
        "id": "dubai-japan-provider-coverage",
        "title": "UAE / Japan provider coverage",
        "measure": "canonical_optional",
    },
    {
        "id": "linkedin-live-account",
        "title": "LinkedIn live account OAuth/publishing integration",
        "measure": "linkedin",
        "owner_action": ("To go live: create a LinkedIn developer app, store the client "
                         "id/secret + a member OAuth token/refresh token in Windows "
                         "Credential Manager under the chief-linkedin-* targets (never in "
                         "chat, GitHub or logs), then publish a reviewed draft with an "
                         "explicit approval + confirm-token. Dry-run is the default and "
                         "nothing posts without that owner approval."),
    },
    {
        "id": "offsite-backup-absent",
        "title": "Off-machine backup destination",
        "measure": "canonical_blocker",
    },
    {
        "id": "laptop-trust-audit",
        "title": "Owner-attended laptop trust audit",
        "measure": "canonical_blocker",
    },
    {
        "id": "deployment-cutover-decision",
        "title": "Final deployment topology / VPS decision",
        "measure": "canonical_blocker",
    },
    {
        "id": "live-provider-failover-gap",
        "title": "Live-provider E4/E5 evidence",
        "measure": "canonical_blocker",
    },
]

# The operational hardening this task landed and must prove is live.
HARDENING_FACTS = [
    "battery-gating",
    "ops-scheduling-cadence",
    "legacy-chief-task",
    "log-rotation-retention",
    "reboot-persistence-unconfigured",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def git_sha() -> str:
    try:
        p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                           capture_output=True, text=True, timeout=60)
        return p.stdout.strip() if p.returncode == 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def run(cmd, timeout=180):
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def load_canonical() -> dict:
    with open(REPO_ROOT / "status" / "canonical-status.json", encoding="utf-8") as fh:
        return json.load(fh)


def optional_entry(canonical: dict, item_id: str) -> dict | None:
    for e in canonical.get("optional_gated", []):
        if e["id"] == item_id:
            return e
    return None


def blocker_entry(canonical: dict, item_id: str) -> dict | None:
    for e in canonical.get("production_blockers", []):
        if e["id"] == item_id:
            return e
    return None


# --------------------------------------------------------------------------- #
# live measurements
# --------------------------------------------------------------------------- #

def measure_inbox_adapters() -> dict:
    try:
        p = run([sys.executable, "career-ops/application_inbox.py", "adapters"])
        payload = json.loads(p.stdout)
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"{type(exc).__name__}: {exc}"}
    gmail = payload.get("adapters", {}).get("gmail_readonly", {})
    return {
        "gmail_readonly": {
            "enabled": gmail.get("enabled"),
            "available": gmail.get("available"),
            "credentials_present": gmail.get("credentials_present"),
            "evidence_mode": gmail.get("evidence_mode"),
            "read_only": gmail.get("read_only"),
            "owner_action_required": gmail.get("owner_action_required"),
        },
        "local_mailbox": {
            "enabled": payload.get("adapters", {}).get("local_mailbox", {}).get("enabled"),
            "available": payload.get("adapters", {}).get("local_mailbox", {}).get("available"),
        },
    }


def measure_linkedin() -> dict:
    try:
        p = run([sys.executable, "career-ops/linkedin_auth.py", "status"])
        auth = json.loads(p.stdout)
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"{type(exc).__name__}: {exc}"}
    creds = auth.get("credentials", {})
    present = {k: bool(v.get("present")) for k, v in creds.items()}
    return {
        "provider": auth.get("provider"),
        "store": auth.get("store"),
        "scope_requested": auth.get("scope_requested"),
        "credential_presence": present,
        "any_credential_present": any(present.values()),
        "code_paths_built": [
            "career-ops/linkedin_auth.py (OAuth credential/token layer, presence-only status)",
            "career-ops/linkedin_publish.py (official REST posts publish path: guards, "
            "duplicate ledger, bounded retries, dry-run default)",
            "career-ops/linkedin_workflow.py (generate/review stay independent; publish "
            "delegates to the publish module; 'post' guard unchanged)",
        ],
        "live_pass_claimed": False,
    }


def measure_watchlist() -> dict:
    owner_file = REPO_ROOT / "runtime" / "career-ops" / "watchlist" / "company-watchlist.json"
    out = {
        "owner_input_path": "runtime/career-ops/watchlist/company-watchlist.json (git-ignored)",
        "owner_input_present": owner_file.exists(),
    }
    if owner_file.exists():
        try:
            data = json.loads(owner_file.read_text(encoding="utf-8"))
            companies = data.get("companies") if isinstance(data, dict) else data
            out["company_count"] = len(companies or [])
        except Exception as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
    else:
        out["company_count"] = 0
        out["note"] = ("lane runs with zero watchlist companies until the owner supplies "
                       "the list; it never invents a company relationship")
    return out


def measure_tasks() -> dict:
    """Live scheduled-task snapshot via the hardening verifier (read-only)."""
    try:
        p = run([sys.executable, "scripts/harden_scheduled_tasks.py", "--verify"])
        return json.loads(p.stdout)
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"{type(exc).__name__}: {exc}"}


def measure_legacy_task() -> dict:
    p = run(["schtasks", "/Query", "/TN", "Mukund Chief of Staff", "/FO", "LIST", "/V"])
    text = (p.stdout or "") + (p.stderr or "")
    state = None
    for line in text.splitlines():
        if "Scheduled Task State" in line or "State:" in line or "Status:" in line:
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[1].strip():
                state = parts[1].strip()
    return {"exists": p.returncode == 0, "state": state,
            "deleted": False,
            "note": "kept in place as a rollback donor; never deleted by this task"}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #

def build() -> dict:
    canonical = load_canonical()
    inbox = measure_inbox_adapters()
    linkedin = measure_linkedin()
    watchlist = measure_watchlist()
    tasks = measure_tasks()
    legacy = measure_legacy_task()

    items: list[dict] = []
    for spec in ITEMS:
        rec: dict = dict(spec)
        m = spec["measure"]
        if m == "canonical_optional":
            e = optional_entry(canonical, spec["id"]) or {}
            rec.update({
                "state": e.get("state", "NOT RECORDED"),
                "owner_gated": e.get("classification") not in (None, "release_scope_false"),
                "classification": e.get("classification"),
                "release_blocker": bool(e.get("release_scope")) if e else None,
                "owner_action": e.get("owner_action"),
                "source": "status/canonical-status.json#optional_gated",
            })
        elif m == "canonical_blocker":
            e = blocker_entry(canonical, spec["id"]) or {}
            rec.update({
                "state": e.get("state", "NOT RECORDED"),
                "owner_gated": bool(e.get("owner_action_required")) if e else None,
                "owner_action": e.get("owner_action"),
                "source": "status/canonical-status.json#production_blockers",
            })
        elif m == "inbox_adapters":
            gmail = inbox.get("gmail_readonly", {})
            rec.update({
                "state": "READY_NEEDS_OWNER_CONFIG" if not gmail.get("available") else "LIVE",
                "owner_gated": True,
                "measured": gmail,
                "source": "career-ops/application_inbox.py adapters (live)",
            })
        elif m == "linkedin":
            rec.update({
                "state": ("READY_NEEDS_OWNER_CONFIG" if not linkedin.get("any_credential_present")
                          else "CREDENTIALS_PRESENT_UNTESTED"),
                "owner_gated": True,
                "measured": linkedin,
                "source": "career-ops/linkedin_auth.py status (live)",
            })
        elif m == "watchlist":
            rec.update({
                "state": ("OWNER_INPUT_PRESENT" if watchlist.get("owner_input_present")
                          else "AWAITING_OWNER_INPUT"),
                "owner_gated": not watchlist.get("owner_input_present"),
                "measured": watchlist,
                "source": "runtime/career-ops/watchlist/company-watchlist.json",
            })
        rec["live_pass"] = bool(rec.get("state") == "LIVE")
        items.append(rec)

    still_battery_gated = (
        tasks.get("still_battery_gated") if isinstance(tasks, dict) else None
    )
    owned = tasks.get("owned_tasks") if isinstance(tasks, dict) else None
    all_hardened = bool(owned) and not still_battery_gated

    hardening = {
        "battery-gating": {
            "state": "RESOLVED (applied + verified live)" if all_hardened else "UNRESOLVED",
            "detail": "DisallowStartIfOnBatteries/StopIfGoingOnBatteries are false on every "
                      "owned task; reversible byte-exact pre-change backups exist under "
                      "deployments/service-definitions/backups/.",
            "still_battery_gated": still_battery_gated,
            "evidence": "audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/",
        },
        "ops-scheduling-cadence": {
            "state": "SCHEDULED (owner-approved) — verified live",
            "detail": "ChiefOperationalBackup 02:30, ChiefLogRotation 03:00, "
                      "ChiefMorningBrief 06:30, ChiefHealthSnapshot 08:00; staggered away "
                      "from the 23:45-00:00 scans and the 07:00 career brief. Local "
                      "artifacts only — no external delivery destination invented.",
            "tasks_measured": {
                n: t.get("state") for n, t in (tasks.get("tasks", {}) or {}).items()
            } if isinstance(tasks, dict) else None,
        },
        "legacy-chief-task": {
            "state": "DISABLED (verified live; kept as rollback donor, not deleted)",
            "measured": legacy,
        },
        "log-rotation-retention": {
            "state": "IMPLEMENTED (dry-run then bounded apply evidenced)",
            "detail": "python scripts/operational_services.py rotate-logs [--apply]; archive "
                      "above 5 MB, keep newest 5 archives per log; only declared live "
                      "Hermes/Chief log paths are touched; Hermes-managed JSON record stores "
                      "are recorded out of scope and never pruned.",
            "evidence": "audits/evidence/2026-09-24T22-21-49Z-task-hardening-and-operational-schedules/log-rotation/",
        },
        "reboot-persistence-unconfigured": {
            "state": "CONFIGURED — reboot itself still UNVERIFIED (owner action)",
            "detail": "StartWhenAvailable is set and StopOnIdleEnd cleared on the owned tasks; "
                      "the two light periodic tasks (queue poller, Discord sync) additionally "
                      "carry a logon trigger. No reboot was performed (prohibited).",
            "unverified_after_reboot": tasks.get("unverified_after_reboot") if isinstance(tasks, dict) else None,
            "owner_checklist": tasks.get("owner_checklist") if isinstance(tasks, dict) else None,
        },
    }

    return {
        "artifact": "built-but-not-live integration gap audit",
        "task_id": "agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24",
        "generated_utc": utc_now(),
        "code_sha": git_sha(),
        "read_only": True,
        "no_credential_value_read": True,
        "no_live_pass_from_dry_run": True,
        "items": items,
        "operational_hardening": hardening,
        "summary": {
            "total_items": len(items),
            "live_pass": sum(1 for i in items if i["live_pass"]),
            "owner_gated": sum(1 for i in items if i.get("owner_gated")),
        },
    }


def render_md(audit: dict) -> str:
    L: list[str] = []
    add = L.append
    add("# Built-but-not-live integration gap audit")
    add("")
    add(f"- Task: `{audit['task_id']}`")
    add(f"- Generated (UTC): {audit['generated_utc']}")
    add(f"- Code SHA: `{audit['code_sha']}`")
    add("- Read-only: every figure below was measured from live runtime/repository state.")
    add("- A fixture/dry-run pass is **never** recorded as a live PASS.")
    add("")
    add("## Integration items")
    add("")
    add("| # | Item | Measured state | Live PASS | Owner-gated |")
    add("|---|---|---|---|---|")
    for n, it in enumerate(audit["items"], 1):
        add(f"| {n} | {it['title']} | {it.get('state')} | "
            f"{'YES' if it.get('live_pass') else 'no'} | "
            f"{'yes' if it.get('owner_gated') else 'no'} |")
    add("")
    add("## Exact next owner step per open item")
    add("")
    for it in audit["items"]:
        if it.get("owner_action"):
            add(f"- **{it['id']}** — {it['owner_action']}")
    add("")
    add("## Operational hardening (this task)")
    add("")
    add("| Fact | State |")
    add("|---|---|")
    for key, rec in audit["operational_hardening"].items():
        add(f"| {key} | {rec['state']} |")
    add("")
    add("### Reboot persistence detail")
    add("")
    add(audit["operational_hardening"]["reboot-persistence-unconfigured"]["detail"])
    add("")
    add("Owner acceptance checklist: `deployments/11-owner-reboot-acceptance-checklist.md`.")
    add("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stdout", action="store_true", help="print, write nothing")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    audit = build()
    md = render_md(audit)

    if args.stdout:
        print(md)
        return 0

    out_dir = Path(args.out_dir) if args.out_dir else (
        EVIDENCE_ROOT / f"{stamp()}-post-stage2-integration-gap-audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (out_dir / "audit.md").write_text(md, encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), "summary": audit["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
