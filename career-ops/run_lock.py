"""Cross-process run lock and atomic file write, shared by the scheduled jobs.

Two scheduled runs of the same job used to write the same output file, so the
later run silently replaced a good artifact with a partial one. That made counts
non-repeatable and could destroy evidence another job had already consumed.

`acquire_run_lock` makes the second concurrent run back off instead; `write_atomic`
makes a crash unable to leave a truncated file behind.
"""
from __future__ import annotations

import os
import pathlib


def acquire_run_lock(path: pathlib.Path):
    """Take an exclusive lock for the run, or return None if another run holds it.

    The caller keeps the returned handle open for the run's lifetime; the OS
    releases the lock when the process exits, including on a crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")
    try:
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def write_atomic(path: pathlib.Path, text: str) -> None:
    """Write via a temp file + replace so a crash never leaves a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
