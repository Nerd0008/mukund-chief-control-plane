"""Tests for the Gmail outcome sweep's run lock and atomic report write.

The lock exists because two concurrent sweeps used to write the same report file:
the later run silently replaced a good report with a partial one, which made the
rejection counts non-repeatable and could have destroyed the audit trail the
tracker reconciliation was built from.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import textwrap
import time

import pytest

HERE = pathlib.Path(__file__).resolve().parent
MOD_PATH = HERE.parent / 'gmail_outcome_sweep.py'

_spec = importlib.util.spec_from_file_location('gos', MOD_PATH)
gos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gos)

HOLDER = textwrap.dedent(
    """
    import importlib.util, pathlib, sys, time
    spec = importlib.util.spec_from_file_location('gos', sys.argv[1])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    f = m.acquire_run_lock(pathlib.Path(sys.argv[2]))
    print('ACQUIRED' if f is not None else 'DENIED', flush=True)
    time.sleep(float(sys.argv[3]))
    """
)


def _run(script, *args, timeout=60):
    return subprocess.run([sys.executable, '-c', script, *[str(a) for a in args]],
                          capture_output=True, text=True, timeout=timeout)


def test_lock_is_exclusive_across_processes(tmp_path):
    """A second sweep must be refused, not allowed to clobber the first run's report."""
    lock = tmp_path / 'sweep.lock'
    hold = subprocess.Popen([sys.executable, '-c', HOLDER, str(MOD_PATH), lock, '6'],
                            stdout=subprocess.PIPE, text=True)
    try:
        first = hold.stdout.readline().strip()
        assert first == 'ACQUIRED', f'first run should hold the lock, got {first!r}'

        second = _run(HOLDER, MOD_PATH, lock, '0')
        assert 'DENIED' in second.stdout, (
            f'second run should be denied the lock, got {second.stdout!r} / {second.stderr!r}')
    finally:
        hold.wait(timeout=30)


def test_lock_is_released_after_the_process_exits(tmp_path):
    lock = tmp_path / 'sweep.lock'
    _run(HOLDER, MOD_PATH, lock, '0')
    time.sleep(0.5)
    again = _run(HOLDER, MOD_PATH, lock, '0')
    assert 'ACQUIRED' in again.stdout, 'lock must be freeable after the holder exits'


def test_write_atomic_leaves_no_temp_file_and_valid_json(tmp_path):
    target = tmp_path / 'report.json'
    gos.write_atomic(target, json.dumps({'ok': True}))
    assert json.loads(target.read_text(encoding='utf-8')) == {'ok': True}
    assert not list(tmp_path.glob('*.tmp')), 'temp file must be renamed away, not left behind'


def test_write_atomic_overwrites_cleanly(tmp_path):
    target = tmp_path / 'report.json'
    target.write_text('{"old": 1}', encoding='utf-8')
    gos.write_atomic(target, '{"new": 2}')
    assert json.loads(target.read_text(encoding='utf-8')) == {'new': 2}


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
