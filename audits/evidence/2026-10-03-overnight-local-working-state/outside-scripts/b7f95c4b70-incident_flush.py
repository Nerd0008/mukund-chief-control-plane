#!/usr/bin/env python3
"""Wrapper: run the control plane's incident flush.

Cron resolves relative script paths under ~/AppData/Local/hermes/scripts/, so
this thin wrapper invokes the real script in the control plane, which is where
the incident log and the rest of the tooling live.
"""
import subprocess
import sys
from pathlib import Path

CONTROL_PLANE = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
SCRIPT = CONTROL_PLANE / "career-ops" / "incident_flush.py"
PYTHON = Path(r"C:\Users\mukun\Desktop\Pythob Bot\chief_of_staff_bot"
              r"\.venv\Scripts\python.exe")

interpreter = PYTHON if PYTHON.exists() else Path(sys.executable)
proc = subprocess.run([str(interpreter), str(SCRIPT)],
                      capture_output=True, text=True, encoding="utf-8",
                      errors="replace", cwd=str(CONTROL_PLANE))
if proc.stdout:
    print(proc.stdout, end="")
if proc.returncode != 0:
    # A failing flush must be visible, not silent.
    print(f"incident_flush failed (exit {proc.returncode})")
    if proc.stderr:
        print(proc.stderr[-800:])
