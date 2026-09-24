#!/usr/bin/env python3
"""Store a provider credential in Windows Credential Manager — owner-run only.

This tool exists so the owner's manual credential step never puts a key on a
command line (and therefore never into shell history, a log, chat, GitHub or a
queue job). It is **run by Mukund, interactively, at his own keyboard**:

    python scripts/set_provider_key.py --worker mistral-small-4

The key is read with `getpass` (no echo), written straight into the Windows
Credential Manager as a generic credential (UTF-16LE blob, which is what
`generic_openai_adapter._read_from_credential_manager()` and
`deepseek_keyaccess`/`gemini_keyaccess` expect), and immediately discarded. It is
never printed, never logged, never written to a file, and never echoed back —
success is reported by *presence*, not by value.

Safe read-only modes (no prompt, no write, no network):

    python scripts/set_provider_key.py --status
    python scripts/set_provider_key.py --check mistral-small-4

This script performs no network call and spends no provider quota.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import getpass
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

sys.path.insert(0, str(REPO_ROOT / "exec-brain"))
sys.path.insert(0, str(RUNTIME_ROOT))

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wt.DWORD),
        ("Type", wt.DWORD),
        ("TargetName", wt.LPWSTR),
        ("Comment", wt.LPWSTR),
        ("LastWritten", wt.FILETIME),
        ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wt.DWORD),
        ("AttributeCount", wt.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wt.LPWSTR),
        ("UserName", wt.LPWSTR),
    ]


def write_generic_credential(target: str, secret: str, comment: str = "") -> bool:
    """Store a generic credential. The secret never leaves this call."""
    blob = secret.encode("utf-16-le")
    buf = ctypes.create_string_buffer(blob, len(blob))
    cred = CREDENTIAL()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.Comment = comment or f"Chief control plane provider credential ({target})"
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.TargetAlias = None
    cred.UserName = target

    advapi32 = ctypes.windll.advapi32
    advapi32.CredWriteW.restype = wt.BOOL
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wt.DWORD]
    return bool(advapi32.CredWriteW(ctypes.byref(cred), 0))


def credential_targets():
    """worker_id -> (provider, credential_target, env_var) from live adapters."""
    mapping = {}
    try:
        import generic_openai_adapter as goa
        for provider, config in goa.PROVIDER_CONFIGS.items():
            mapping[provider] = (config.get("credential_target"),
                                 config.get("env_var"))
        from worker_registry import WorkerRegistry
        workers = WorkerRegistry().get_all_workers()
        out = {}
        for wid, worker in workers.items():
            provider = worker.get("provider")
            target, env_var = mapping.get(provider, (None, None))
            out[wid] = {"provider": provider, "interface": worker.get("interface"),
                        "credential_target": target, "env_var": env_var}
        return out
    except Exception as exc:
        print(f"error: could not load adapters: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return {}


def presence(worker_id, provider=None):
    """Presence only — the resolved key is discarded immediately."""
    try:
        import generic_openai_adapter as goa
        adapter = goa.get_adapter(worker_id)
        key, source = adapter._resolve_auth()
        present = key is not None
        del key
        return {"worker_id": worker_id, "credential_present": present,
                "auth_source": source,
                "credential_target": adapter.config.get("credential_target"),
                "env_var": adapter.config.get("env_var")}
    except Exception as exc:
        first_error = f"{type(exc).__name__}: {exc}"

    # DeepSeek and Gemini have dedicated adapters/key helpers rather than the
    # generic OpenAI-compatible one. Probe them through their own resolvers.
    try:
        if provider in ("deepseek",) or worker_id.startswith("deepseek"):
            import deepseek_keyaccess as ka
            source = ka.key_source()
            return {"worker_id": worker_id,
                    "credential_present": source != "none",
                    "auth_source": source,
                    "credential_target": ka.CRED_TARGET,
                    "env_var": "DEEPSEEK_API_KEY",
                    "resolver": "deepseek_keyaccess"}
        if provider in ("google",) or worker_id.startswith("google"):
            import gemini_keyaccess as ka
            present = bool(ka.key_source() != "none")
            return {"worker_id": worker_id, "credential_present": present,
                    "auth_source": ka.key_source(),
                    "credential_target": ka.CRED_TARGET,
                    "env_var": "GEMINI_API_KEY|GOOGLE_API_KEY|"
                               "GOOGLE_GENERATIVE_AI_API_KEY",
                    "resolver": "gemini_keyaccess"}
    except Exception as exc:
        return {"worker_id": worker_id,
                "error": first_error,
                "secondary_error": f"{type(exc).__name__}: {exc}"}
    return {"worker_id": worker_id, "error": first_error}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", help="roster worker id to provision")
    parser.add_argument("--target", help="store directly under this credential target")
    parser.add_argument("--status", action="store_true",
                        help="read-only: show every API worker and presence")
    parser.add_argument("--check", help="read-only: presence for one worker id")
    args = parser.parse_args()

    workers = credential_targets()

    if args.status:
        for wid, info in sorted(workers.items()):
            rec = {"worker_id": wid, **info}
            if info.get("interface") == "api":
                rec.update(presence(wid, info.get("provider")))
            else:
                rec["note"] = "non-API interface; credential handled by its own CLI"
            print(rec)
        return 0

    if args.check:
        print(presence(args.check, (workers.get(args.check) or {}).get("provider")))
        return 0

    if not (args.worker or args.target):
        parser.error("one of --worker / --target / --status / --check is required")

    if args.worker:
        info = workers.get(args.worker)
        if not info:
            print(f"error: unknown worker '{args.worker}'", file=sys.stderr)
            return 2
        target = info.get("credential_target")
        if not target:
            print(f"error: no credential target is declared for worker "
                  f"'{args.worker}' (interface={info.get('interface')})",
                  file=sys.stderr)
            return 2
    else:
        target = args.target

    existing = presence(args.worker) if args.worker else {}
    if existing.get("credential_present"):
        print(f"note: a credential for target '{target}' is already present; "
              f"this run will overwrite it.")

    secret = getpass.getpass(f"paste the API key for '{target}' (no echo): ")
    if not secret.strip():
        print("error: empty input; nothing stored", file=sys.stderr)
        return 2
    ok = write_generic_credential(target, secret)
    del secret
    if not ok:
        print(f"error: CredWriteW failed for target '{target}'", file=sys.stderr)
        return 1
    print(f"stored generic credential '{target}'.")

    if args.worker:
        after = presence(args.worker)
        print({"worker_id": args.worker,
               "credential_present": after.get("credential_present"),
               "auth_source": after.get("auth_source")})
        print("next: run `python scripts/e3_credential_presence_probe.py` for the "
              "full 7/7 check, then the post-key verification sequence in "
              "tasks-or-issues/overnight-owner-actions-2026-09-24.md item 8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
