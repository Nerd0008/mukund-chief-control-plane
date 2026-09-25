#!/usr/bin/env python3
"""One-shot, bounded Codex CLI smoke for agent-codex-cli-smoke-2026-09-25.

Uses the EXISTING deployed exec-brain Codex adapter/resolver unchanged
(hash-verified identical to exec-brain/codex_adapter.py in the repo).

Exactly ONE Codex model execution is performed. No retries.
Evidence recorded is sanitized: executable path/version, exit code, final
assistant message, runtime, identity fields only if directly exposed,
provider-returned usage only if exposed, E2 linkage result.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

RUNTIME = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "exec-brain"
REPO = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
SCRATCH = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "cache" / "scratch" / "codex_smoke_2026-09-25"
OUT = REPO / "audits" / "evidence" / f"{time.strftime('%Y-%m-%dT%H-%M-%SZ', time.gmtime())}-codex-cli-smoke"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(RUNTIME))
import codex_adapter as ca  # noqa: E402

evidence = {
    "task": "agent-codex-cli-smoke-2026-09-25",
    "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "host": "mukund-local-hermes-host",
    "adapter": {
        "path_used": str(RUNTIME / "codex_adapter.py"),
        "sha256": hashlib.sha256((RUNTIME / "codex_adapter.py").read_bytes()).hexdigest(),
        "repo_copy_sha256": hashlib.sha256((REPO / "exec-brain" / "codex_adapter.py").read_bytes()).hexdigest(),
        "rewritten": False,
    },
    "execution_profile": "safe",
    "smoke_objective": "Reply exactly CODEX_SMOKE_OK",
    "executions_spent": 0,
    "retries": 0,
}

# 1. Resolver + version + health (read-only; no model execution)
try:
    exe = ca._resolve_codex_executable()
    evidence["resolver"] = {"resolved": "ok", "executable": str(exe)}
except Exception as e:  # noqa: BLE001
    evidence["resolver"] = {"resolved": "failed", "error_class": type(e).__name__, "error": str(e)}
    (OUT / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "resolver", "result": evidence["resolver"]}))
    raise SystemExit(0)

adapter = ca.CodexExecutionAdapter(execution_profile="safe")
health = adapter.check_health()
evidence["health"] = health

# 2. Identity / auth presence (sanitized; no secret values read or logged)
identity = adapter.get_identity()
evidence["identity_probe"] = identity

# 3. EXACTLY ONE bounded non-interactive execution
contract = {
    "contract_id": "codex-cli-smoke-2026-09-25",
    "objective": evidence["smoke_objective"],
    "timeout": 180,
    "working_directory": str(SCRATCH),
}
started = time.time()
result = adapter.dispatch(contract)
evidence["executions_spent"] = 1
elapsed = time.time() - started

final_message = (result.get("final_message") or "").strip()
usage = result.get("usage_tokens")
passed = (
    result.get("status") == "COMPLETED"
    and not result.get("error")
    and final_message == "CODEX_SMOKE_OK"
)

evidence["execution"] = {
    "passed": passed,
    "exact_reply_match": final_message == "CODEX_SMOKE_OK",
    "final_message": final_message,
    "status": result.get("status"),
    "exit_code": result.get("exit_code"),
    "error": result.get("error"),
    "runtime_s": result.get("runtime_s"),
    "wall_clock_s": elapsed,
    "dispatch_id": result.get("dispatch_id"),
    "codex_thread_id": result.get("codex_thread_id"),
    "provider_field_from_adapter": result.get("provider"),
    "model_field_from_adapter": result.get("model"),
    "usage_exposed": usage is not None,
    "usage_provider_returned": usage,
    "dispatch_metadata": result.get("dispatch_metadata"),
    "stdout_event_types": sorted({
        str(line.get("type")) for line in (result.get("raw_output") or []) if isinstance(line, dict)
    }),
    "stderr_present": bool((result.get("stderr") or "").strip()),
}

# raw jsonl (already only Codex event stream; no credentials)
(OUT / "codex-exec-jsonl.jsonl").write_text(
    "\n".join(json.dumps(l) for l in (result.get("raw_output") or [])), encoding="utf-8"
)

# 4. E2 linkage through the public governor.record_request() interface
e2_request_id = None
e2_error = None
if passed:
    try:
        e2_request_id = ca.report_usage_to_e2(result)
        if e2_request_id is None:
            e2_error = "E2 governor runtime not found"
    except Exception as e:  # noqa: BLE001
        e2_error = f"{type(e).__name__}: {e}"

evidence["e2"] = {
    "usage_linkage": "VERIFIED" if e2_request_id else "NOT_VERIFIED",
    "e2_request_id": e2_request_id,
    "e2_error": e2_error,
}

evidence["qualification"] = "UNPROVEN"
evidence["routable"] = bool(passed and e2_request_id)
evidence["verdict"] = "PASS (execution readiness only)" if passed else "FAIL"

(OUT / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

print(json.dumps({
    "evidence_dir": str(OUT),
    "passed": passed,
    "exit_code": evidence["execution"]["exit_code"],
    "final_message": final_message,
    "runtime_s": evidence["execution"]["runtime_s"],
    "status": evidence["execution"]["status"],
    "error": evidence["execution"]["error"],
    "usage_exposed": evidence["execution"]["usage_exposed"],
    "e2": evidence["e2"],
    "identity_summary": {
        "provider": identity.get("provider"),
        "provider_provenance": identity.get("provider_provenance"),
        "configured_model": identity.get("configured_model"),
        "auth_configured": identity.get("auth_configured"),
        "auth_mode": identity.get("auth_mode"),
        "cli_version": identity.get("cli_version"),
    },
    "executions_spent": 1,
}, indent=2))
