#!/usr/bin/env python3
"""Run the DEPLOYED e3-status on an isolated store copy and print the E4 section.

Loads ``e3_commands`` from the runtime root *only* (never the repo checkout), so
it proves the operator-facing E4 content-side stop pressure section works through
the deployed runtime modules. Reads a store copy read-only and optionally the
recorded provider series artifact; makes no provider call and writes no store.

Usage: python deployed_surface_check.py --db PATH [--series PATH] [--out PATH]
"""

import argparse
import contextlib
import io
import os
import sys
from pathlib import Path

RUNTIME_ROOT = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "exec-brain"
SECTION = "--- E4 Resource Continuity: provider content-side stop pressure ---"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--series", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(RUNTIME_ROOT))
    import e3_commands  # noqa: E402  (deployed module under test)

    cmd = e3_commands.E3Commands(args.db)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd.status(argparse.Namespace(
            pressure_series=[args.series] if args.series else None))
    out = buf.getvalue()
    cmd.con.close()

    lines = [
        f"deployed module under test: {e3_commands.__file__}",
        f"runtime root (import root): {RUNTIME_ROOT}",
        f"store read: {args.db}",
        f"recorded series supplied: {args.series or 'none'}",
        "",
    ]
    parts = out.split(SECTION)
    if len(parts) > 1:
        lines.append(SECTION + parts[1].rstrip("\n"))
    else:
        lines.append("SECTION MISSING from the deployed e3-status output")
    text = "\n".join(lines) + "\n"

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "deployed_surface_output.txt")
    out_path.write_text(text, encoding="utf-8")
    print(text)
    print(f"written to {out_path}")
    ok = (len(parts) > 1
          and "content-side stops observed" in parts[1]
          and "stop rate:" in parts[1]
          and "sample size" in parts[1]
          and "decision: observation only" in parts[1])
    if args.series:
        ok = ok and "content withheld at a measurable rate: yes" in parts[1]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
