#!/usr/bin/env python3
"""DeepSeek credential helper — Windows Credential Manager (canonical) + env fallback.

D2 policy: key is read by reference only, never printed, logged, or committed.
This module exposes presence checks and an in-process getter. Callers must
never write the returned value to disk, logs, or stdout.
"""

import os
import ctypes
import ctypes.wintypes as wt

CRED_TYPE_GENERIC = 1


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


_advapi32 = ctypes.windll.advapi32
_advapi32.CredReadW.restype = wt.BOOL
_advapi32.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
_advapi32.CredFree.argtypes = [ctypes.c_void_p]

CRED_TARGET = "deepseek"


def credential_manager_entry_present(target: str = CRED_TARGET) -> bool:
    """Presence check only — never returns the value."""
    import subprocess
    try:
        r = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, timeout=10)
        return target.lower() in r.stdout.lower()
    except Exception:
        return False


def env_var_present() -> bool:
    """Presence check only — never returns the value."""
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def get_deepseek_key():
    """Return the DeepSeek API key, or None.

    Order: Windows Credential Manager (canonical) -> DEEPSEEK_API_KEY env.
    The returned value must never be printed, logged, or persisted.
    """
    key = _read_from_credential_manager()
    if key:
        return key
    return os.environ.get("DEEPSEEK_API_KEY") or None


def key_source():
    """Report which store holds the key — presence only."""
    if _read_from_credential_manager():
        return "credential_manager"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "env"
    return "none"


def _read_from_credential_manager(target: str = CRED_TARGET):
    """Read generic credential blob via CredReadW. In-process only."""
    cred_ptr = ctypes.POINTER(CREDENTIAL)()
    if not _advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr)):
        return None
    try:
        cred = cred_ptr.contents
        size = cred.CredentialBlobSize
        if size == 0:
            return None
        blob = ctypes.string_at(cred.CredentialBlob, size)
        # cmdkey stores the password as UTF-16LE
        try:
            return blob.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            try:
                return blob.decode("utf-8").rstrip("\x00")
            except UnicodeDecodeError:
                return None
    finally:
        _advapi32.CredFree(cred_ptr)
