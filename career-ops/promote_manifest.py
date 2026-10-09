"""Promote a discovery manifest into the canonical regional tracker.

Owner instruction (2026-10-09):
  "Any role you discover from any tracker or pipeline if it's for the uk I want
   it in that tracker."

The scheduled discovery orchestrator is bounded and read-only by design: it
writes a candidate manifest under runtime/career-ops/discovery/ and stops. That
left a real gap — the nightly UK run found roles, recorded them as
``tracker_candidates``, and nothing ever moved them into the workbook. The
owner only saw whatever the separate 07:45 Codex search happened to add.

This is the missing handoff. It applies a manifest to the canonical workbook
through the existing, verified writer (career_ops_cli.py write --apply), so the
duplicate detection, hash-checked backup and post-write verification all still
apply. It adds no new write path of its own.

Usage:
    python career-ops/promote_manifest.py --region uk                # dry run
    python career-ops/promote_manifest.py --region uk --apply        # write

Exit codes: 0 ok (including "nothing new"), 2 refused, 3 manifest missing.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CONTROL_PLANE = Path(__file__).resolve().parent.parent
CAREER_OPS = CONTROL_PLANE / "career-ops"
CLI = CAREER_OPS / "career_ops_cli.py"
RUNTIME = CONTROL_PLANE / "runtime" / "career-ops"
MANIFEST_DIR = RUNTIME / "discovery" / "unified"
LOG_DIR = RUNTIME / "promote"

# The owner wants UK roles in the UK tracker. Non-UK regions keep their own
# layouts and are not promoted by the UK nightly task.
DEFAULT_REGIONS = ("uk",)


def manifest_path(region: str) -> Path:
    return MANIFEST_DIR / region / "manifest-latest.json"


def clean_company(value: str | None) -> str:
    """Strip the discovery lane's ' | source' suffix from an employer name.

    The pipeline records ``"Tencent UK | Prosple UK"`` (employer plus the lane
    that found it). The owner wants a readable tracker, so the employer alone
    goes in the Company column; the source stays in the manifest for provenance.
    """
    text = (value or "").strip()
    if " | " in text:
        text = text.split(" | ", 1)[0].strip()
    return text


def read_manifest(region: str) -> dict | None:
    p = manifest_path(region)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface the parse failure truthfully
        print(f"[{region}] manifest unreadable: {exc}", file=sys.stderr)
        return None


def normalized_manifest(region: str, doc: dict) -> Path:
    """Write a copy of the manifest with readable employer names.

    The writer is fed this copy rather than the original so the Company column
    holds ``Tencent UK`` instead of ``Tencent UK | Prosple UK``. The original
    manifest is left untouched for provenance.
    """
    records = []
    for rec in doc.get("records") or []:
        clean = dict(rec)
        clean["company"] = clean_company(rec.get("company"))
        records.append(clean)
    normalized = dict(doc)
    normalized["records"] = records
    normalized["_normalized_for_tracker"] = True
    target = MANIFEST_DIR / region / "manifest-for-tracker.json"
    target.write_text(json.dumps(normalized, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    return target


def promote(region: str, *, apply: bool) -> dict:
    doc = read_manifest(region)
    if doc is None:
        return {"region": region, "state": "manifest-missing",
                "path": str(manifest_path(region))}

    records = doc.get("records") or []
    generated = doc.get("generated_at")
    if not records:
        return {"region": region, "state": "nothing-to-promote",
                "manifest_generated_at": generated, "records": 0,
                "note": "the manifest carried no eligible records"}

    # Rows with no employer cannot be deduped or read back usefully; the
    # canonical writer would reject them anyway. Report the count honestly.
    usable = [r for r in records if clean_company(r.get("company"))]
    skipped_unnamed = len(records) - len(usable)

    source_manifest = normalized_manifest(region, doc)
    cmd = [sys.executable, str(CLI), "write", "--region", region,
           "--manifest", str(source_manifest)]
    if apply:
        cmd.append("--apply")
    run = subprocess.run(cmd, capture_output=True, text=True, cwd=str(CONTROL_PLANE))
    try:
        result = json.loads(run.stdout)
    except Exception:  # noqa: BLE001 - the writer's stdout is the contract
        return {"region": region, "state": "writer-failed", "exit_code": run.returncode,
                "stdout_tail": (run.stdout or "")[-800:],
                "stderr_tail": (run.stderr or "")[-800:]}

    counts = result.get("counts") or {}
    return {
        "region": region,
        "state": "applied" if apply else "dry-run",
        "manifest_generated_at": generated,
        "records_in_manifest": len(records),
        "skipped_unnamed_employer": skipped_unnamed,
        "counts": counts,
        "tracker": result.get("tracker"),
        "appended_rows": [
            {"company": o.get("company"), "title": o.get("title"),
             "url": o.get("url"), "id": o.get("id")}
            for o in (result.get("outcomes") or [])
            if o.get("decision") == "appended"
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Promote a discovery manifest into the canonical regional tracker.")
    ap.add_argument("--region", action="append", dest="regions",
                    help="region to promote (repeatable); default uk")
    ap.add_argument("--apply", action="store_true",
                    help="write to the canonical tracker (default: dry run)")
    args = ap.parse_args()

    regions = args.regions or list(DEFAULT_REGIONS)
    reports = [promote(r, apply=args.apply) for r in regions]

    total = sum((r.get("counts") or {}).get("appended", 0) for r in reports)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "applied": bool(args.apply),
        "regions": reports,
        "total_appended": total,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (LOG_DIR / f"promote-{stamp}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    if any(r.get("state") == "writer-failed" for r in reports):
        return 2
    if all(r.get("state") == "manifest-missing" for r in reports):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
