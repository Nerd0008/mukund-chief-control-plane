#!/usr/bin/env python3
"""Zero-provider preflight for the live persistent Chief context sources."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "exec-brain"))
from chief_context import ChiefContextCompiler  # noqa: E402


def main() -> int:
    compiler = ChiefContextCompiler(root=ROOT)
    package = compiler.compile("Based on all our previous conversations, what do you know about me?")
    manifest = package["source_manifest"]
    ids = {row["source_id"] for row in manifest}
    required = {"owner-context", "company-registry", "project-state"}
    # Local sources may be absent on a different host; report that explicitly.
    local_owner = {"owner-context-local", "owner-memory", "owner-profile"}
    local_history = "discord-chief-history" in ids
    report = {
        "provider_calls": 0,
        "source_count": len(manifest),
        "source_ids": sorted(ids),
        "source_manifest": [{k: row[k] for k in ("source_id", "kind", "sha256", "chars_included")}
                            for row in manifest],
        "owner_context_present": bool(ids & local_owner),
        "company_registry_present": bool(ids & {"company-registry", "company-registry-local", "company-registry-reference"}),
        "project_state_present": bool(ids & {"project-state", "owner-context"}),
        "discord_history_present": local_history,
        "context_warnings": compiler.validate(package),
    }
    report["pass"] = (not report["context_warnings"] and report["owner_context_present"]
                       and report["company_registry_present"] and report["project_state_present"])
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
