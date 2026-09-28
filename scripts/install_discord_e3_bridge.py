#!/usr/bin/env python3
"""Retired gateway interceptor.

Chief no longer replaces ``_run_agent``. Use the supported reversible
model-provider seam instead:

    python scripts/install_e3_model_provider.py --dry-run

This command intentionally refuses to patch vendor Hermes source.
"""
from __future__ import annotations

import argparse


def main() -> int:
    argparse.ArgumentParser().parse_args()
    raise SystemExit(
        "direct Discord gateway interception is retired; use "
        "scripts/install_e3_model_provider.py"
    )


if __name__ == "__main__":
    main()
