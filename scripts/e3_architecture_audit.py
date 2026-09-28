#!/usr/bin/env python3
"""Offline architectural invariant audit for production Python sources."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUSINESS_ROOTS = ("career-ops", "company-watch", "hermes-plugins", "scripts")
ADAPTER_MODULES = {"deepseek_adapter", "codex_adapter", "gemini_adapter", "generic_openai_adapter"}
ALLOWED_DIAGNOSTIC_SCRIPTS = {
    "scripts/codex_identity_contract_check.py", "scripts/deployment_inventory.py",
    "scripts/deployment_preflight.py", "scripts/e3_credential_presence_probe.py",
    "scripts/e3_provider_bounded_smoke.py", "scripts/e3_provider_live_identity_probe.py",
    "scripts/e3_provider_rate_limit_diagnostic.py", "scripts/e3_stage2_readiness_gate.py",
    "scripts/e3_tencent_endpoint_reprobe.py", "scripts/operational_services.py",
    "scripts/set_provider_key.py",
}


def _imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"syntax:{exc.msg}"]
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [name.name.split(".")[0] for name in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            hits.append(node.module.split(".")[0])
    return hits


def audit() -> dict:
    failures = []
    checked = []
    for root_name in BUSINESS_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if "/tests/" in f"/{relative}" or relative in ALLOWED_DIAGNOSTIC_SCRIPTS:
                continue
            checked.append(relative)
            bad = sorted(set(_imports(path)) & ADAPTER_MODULES)
            if bad:
                failures.append({"path": relative, "kind": "direct_adapter_import", "modules": bad})
    plugin = (ROOT / "hermes-plugins/e3-discord-router/__init__.py").read_text(encoding="utf-8")
    if "orchestrate_and_execute" in plugin or '"action": "skip"' in plugin:
        failures.append({"path": "hermes-plugins/e3-discord-router/__init__.py",
                         "kind": "normal_discord_consumed_before_chief"})
    for relative in ("exec-brain/chief_routing.py", "exec-brain/discord_chief_bridge.py",
                     "exec-brain/department_dispatch.py", "exec-brain/chief_context.py",
                     "exec-brain/e3_service.py",
                     "scripts/e3_runtime_provenance.py"):
        if not (ROOT / relative).is_file():
            failures.append({"path": relative, "kind": "missing_chief_e3_provenance"})
    deploy_source = (ROOT / "scripts/deploy_e3_runtime.py").read_text(encoding="utf-8")
    for module in ("e3_service.py", "chief_routing.py", "discord_chief_bridge.py",
                   "department_dispatch.py", "chief_context.py"):
        if module not in deploy_source:
            failures.append({"path": "scripts/deploy_e3_runtime.py",
                             "kind": "missing_runtime_deployment_module", "module": module})
    return {"checked": len(checked), "failures": failures,
            "pass": not failures, "provider_calls": 0}


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
