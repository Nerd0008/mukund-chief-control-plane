"""Separate completed search from deferred Excel delivery; never bypass a file lock."""
from pathlib import Path
import os

class WorkbookBusyError(OSError):
    pass

def workbook_busy(path):
    if os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    api.CreateFileW.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    # Request DELETE access without deleting anything. Atomic replacement needs
    # existing holders to permit delete sharing. ACL/missing-file errors are NOT busy.
    handle=api.CreateFileW(str(Path(path)),0x10000,7,None,3,0,None)
    if handle == ctypes.c_void_p(-1).value:
        return ctypes.get_last_error() in (32,33)
    api.CloseHandle(handle)
    return False

def write_or_defer(write, tracker, records, retain, advance):
    try:
        if workbook_busy(tracker):
            raise WorkbookBusyError('workbook is open without replace sharing')
        return write(),None
    except OSError as exc:
        # Recheck after a failed commit: Excel can open between preflight/replace.
        if not isinstance(exc,WorkbookBusyError) and not workbook_busy(tracker):
            raise
        queued=retain(records)  # Durable retention MUST succeed before progress advances.
        advance()
        return None,{'status':'DEFERRED','reason':'workbook_in_use','applied':False,
            'candidate_records':len(records),'queue_path':str(queued),
            'requires_fresh_verification':True,'tracker_writes':0}
