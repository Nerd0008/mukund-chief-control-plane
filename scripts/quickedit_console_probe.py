#!/usr/bin/env python3
"""Real-console probe for the QuickEdit hardening (no global settings touched).

Prints the truthful per-console result record for THIS interpreter's console.
Run with:  python scripts/quickedit_console_probe.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from remote_queue import visible_worker as vw


def main() -> int:
    outcome = vw.disable_quick_edit_for_this_console()
    print(json.dumps(outcome, indent=2))
    print("ENABLE_QUICK_EDIT_MODE bit value:", vw.ENABLE_QUICK_EDIT_MODE)
    print("hardening applied:", outcome["applied"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
