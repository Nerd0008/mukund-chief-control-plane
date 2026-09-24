#!/usr/bin/env python3
"""Presence-only credential probe for the E3 local Stage 2 readiness gate.

Deterministic. Makes **no network call** and reads **no credential value** into a
variable that is printed, logged or stored. It answers exactly one question per
provider: *is a credential configured locally right now?* — and the auth-source
label (store name), never the secret.

Three independent presence paths are used so a negative is corroborated rather
than assumed:

1. ``GenericOpenAIAdapter._resolve_auth()`` per worker — the exact resolver the
   E3 execution path uses (Windows Credential Manager -> env var). The returned
   key is discarded immediately after the ``is not None`` test.
2. ``CredEnumerateW`` — enumerates *target names only* of generic credentials
   currently present in the Windows Credential Manager. Blobs are never read.
3. Direct environment-variable presence for each provider's declared env var.

Usage:
    python scripts/e3_credential_presence_probe.py [--out-dir DIR]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

sys.path.insert(0, str(RUNTIME_ROOT))
sys.path.insert(0, str(REPO_ROOT / "exec-brain"))

# The seven providers that were credential-missing at the 2026-09-23T22:53:53Z
# verdict, in roster order.
CREDENTIAL_MISSING_WORKERS = [
    "mistral-small-4", "glm-53-flash", "qwen38-27b", "longcat-2.0",
    "minimax-m3", "step-37-flash", "tencent-hunyuan-hy3",
]


def enumerate_credential_targets():
    """List generic-credential *target names* from Windows Credential Manager.

    Presence only: the credential blob is never dereferenced.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
    except Exception as exc:  # pragma: no cover - non-Windows
        return {"supported": False, "note": type(exc).__name__, "targets": []}

    CRED_TYPE_GENERIC = 1
    CRED_ENUMERATE_ALL_CREDENTIALS = 0x1

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wt.DWORD),
            ("Type", wt.DWORD),
            ("TargetName", wt.LPWSTR),
            ("Comment", wt.LPWSTR),
            ("LastWritten", wt.FILETIME),
            ("CredentialBlobSize", wt.DWORD),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", wt.DWORD),
            ("AttributeCount", wt.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wt.LPWSTR),
            ("UserName", wt.LPWSTR),
        ]

    advapi32 = ctypes.windll.advapi32
    advapi32.CredEnumerateW.restype = wt.BOOL
    advapi32.CredEnumerateW.argtypes = [
        wt.LPCWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD),
        ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(CREDENTIAL))),
    ]
    advapi32.CredFree.argtypes = [ctypes.c_void_p]

    count = wt.DWORD(0)
    creds_ptr = ctypes.POINTER(ctypes.POINTER(CREDENTIAL))()
    if not advapi32.CredEnumerateW(None, CRED_ENUMERATE_ALL_CREDENTIALS,
                                   ctypes.byref(count),
                                   ctypes.byref(creds_ptr)):
        err = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else None
        return {"supported": True, "enumerated": False, "error_code": err,
                "targets": []}
    targets = []
    try:
        for i in range(count.value):
            cred = creds_ptr[i].contents
            if cred.Type == CRED_TYPE_GENERIC and cred.TargetName:
                targets.append(cred.TargetName)
    finally:
        advapi32.CredFree(creds_ptr)
    return {"supported": True, "enumerated": True,
            "targets": sorted(t for t in targets if t)}


def probe_worker(worker_id: str) -> dict:
    """Presence-only probe through the live E3 auth resolver."""
    import generic_openai_adapter as goa
    from worker_registry import WorkerRegistry

    record = {"worker_id": worker_id}
    worker = WorkerRegistry().get_worker(worker_id) or {}
    record["provider"] = worker.get("provider")
    record["routable_in_registry"] = bool(worker.get("routable"))
    try:
        adapter = goa.get_adapter(worker_id)
    except Exception as exc:  # pragma: no cover - defensive
        record.update({"credential_present": False, "auth_source": "none",
                       "resolver": "adapter_creation_failed",
                       "resolver_error": type(exc).__name__})
        return record

    config = adapter.config
    env_var = config.get("env_var")
    cred_target = config.get("credential_target")

    key, source = adapter._resolve_auth()
    present = key is not None
    del key  # never retained beyond the presence test
    record.update({
        "credential_present": present,
        "auth_source": source,
        "resolver": "generic_openai_adapter._resolve_auth()",
        "credential_manager_target": cred_target,
        "env_var": env_var,
        "env_var_present": bool(os.environ.get(env_var)) if env_var else False,
        "api_models_endpoint": config.get("models_endpoint"),
    })
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    targets = enumerate_credential_targets()
    target_names = set(targets.get("targets") or [])

    workers = []
    for w in CREDENTIAL_MISSING_WORKERS:
        rec = probe_worker(w)
        rec["credential_manager_target_listed"] = bool(
            rec.get("credential_manager_target")
            and rec["credential_manager_target"] in target_names)
        workers.append(rec)

    still_missing = [w["worker_id"] for w in workers
                     if not w["credential_present"]]
    newly_configured = [w["worker_id"] for w in workers
                        if w["credential_present"]]

    report = {
        "label": "e3-credential-presence-probe",
        "run_started_utc": started.isoformat(timespec="seconds"),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": ("presence-only credential probe for the Stage 2 readiness "
                  "gate — no network call, no credential value read or logged"),
        "real_provider_calls_spent": 0,
        "network_calls_spent": 0,
        "note": ("only presence and store name are recorded; credential values "
                 "are never read into a printed variable, logged or stored"),
        "windows_credential_manager": targets,
        "env_var_presence_note": ("env vars are probed in this process "
                                  "environment; absence here is corroborated by "
                                  "the credential-manager enumeration"),
        "workers": workers,
        "still_missing_count": len(still_missing),
        "still_missing_workers": still_missing,
        "newly_configured_workers": newly_configured,
        "all_seven_configured": len(still_missing) == 0,
    }

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "audits" / "evidence"
        / f"{started.strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-credential-presence-probe")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")

    lines = [
        "# E3 credential presence probe (presence only)",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Network calls spent: {report['network_calls_spent']}",
        f"- Provider calls spent: {report['real_provider_calls_spent']}",
        f"- Windows Credential Manager targets enumerated: "
        f"{len(target_names)}",
        "",
        f"## Result: {len(still_missing)}/7 still missing",
        "",
        "| Worker | Provider | Credential present | Auth source | "
        "CredMgr target listed | Env var | Env present |",
        "|---|---|---|---|---|---|---|",
    ]
    for w in workers:
        lines.append(
            f"| {w['worker_id']} | {w.get('provider')} | "
            f"{w['credential_present']} | {w['auth_source']} | "
            f"{w.get('credential_manager_target_listed')} | "
            f"{w.get('env_var')} | {w.get('env_var_present')} |")
    lines += [
        "",
        "Credential-manager generic targets currently present:",
        "",
    ]
    for t in sorted(target_names):
        lines.append(f"- `{t}`")
    lines += [
        "",
        "No credential value was read, logged or stored by this probe. The "
        "auth source column is the store name only.",
        "",
    ]
    (out_dir / "evidence.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "evidence_dir": str(out_dir),
        "still_missing_count": len(still_missing),
        "still_missing_workers": still_missing,
        "newly_configured_workers": newly_configured,
        "credential_manager_targets": sorted(target_names),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
