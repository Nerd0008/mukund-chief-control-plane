#!/usr/bin/env python3
"""Gemini API key access helper — Windows Credential Manager (canonical) + env fallback.

Presence checks never expose values. The key is read in-process only and
must never be printed, logged, or committed.
"""

import ctypes
import ctypes.wintypes as wt
import os

CRED_TYPE_GENERIC = 1
CRED_TARGET = "gemini-api"

ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY",
            "GOOGLE_GENERATIVE_AI_API_KEY")


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


def credential_manager_entry_present(target: str = CRED_TARGET) -> bool:
    """Presence check only — never returns the value."""
    import subprocess
    try:
        r = subprocess.run(["cmdkey", "/list"], capture_output=True,
                           text=True, timeout=10)
        return target.lower() in r.stdout.lower()
    except Exception:
        return False


def env_var_present() -> bool:
    """Presence check only — never returns the value."""
    return any(os.environ.get(v) for v in ENV_VARS)


def get_gemini_key():
    """Return the Gemini API key, or None.

    Order: Windows Credential Manager (canonical) -> env vars.
    Returned value must never be printed, logged, or persisted.
    """
    key = _read_from_credential_manager()
    if key:
        return key
    for v in ENV_VARS:
        val = os.environ.get(v)
        if val:
            return val
    return None


def key_source():
    """Report which store holds the key — presence only."""
    if _read_from_credential_manager():
        return "credential_manager"
    for v in ENV_VARS:
        if os.environ.get(v):
            return f"env:{v}"
    return "none"


def _read_from_credential_manager(target: str = CRED_TARGET):
    """Read generic credential blob via CredReadW. In-process only."""
    cred_ptr = ctypes.POINTER(CREDENTIAL)()
    if not _advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0,
                               ctypes.byref(cred_ptr)):
        return None
    try:
        cred = cred_ptr.contents
        size = cred.CredentialBlobSize
        if size == 0:
            return None
        blob = ctypes.string_at(cred.CredentialBlob, size)
        try:
            return blob.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            try:
                return blob.decode("utf-8").rstrip("\x00")
            except UnicodeDecodeError:
                return None
    finally:
        _advapi32.CredFree(cred_ptr)
