"""Make the six section-header rules in the master CV a uniform thickness.

ROOT CAUSE
----------
Each section rule is a Form XObject (X6, X7, X8, X9, X14, X15) drawing an opaque
black rectangle. Its VISIBLE band is the intersection of three things:

  * the form's ``/BBox``               (4 or 5 form units tall),
  * a clip rectangle in the page content stream
    (``x y w h re W* n``, 3.1250 .. 3.5771 form units), and
  * the rectangle artwork inside the form's own stream.

The clips were authored at six different heights and at offsets that do not line
up with the forms they clip, so the clip always binds and the six rules render at
five different thicknesses (0.75pt .. 0.86pt of clip, measured 0.78 .. 0.90pt).

This is PRE-EXISTING in the master and in its base - it is NOT introduced by
cv_tailor.py. The master and every tailored output measure identically.

FIX
---
Neutralise the six rule XObjects (so none of the old inconsistent artwork draws)
and draw six fresh plain vector rectangles directly on the page at the positions
measured from the original, all at ONE uniform thickness. Position and width are
preserved; only thickness is normalised.

Usage:
    python career-ops/rule_uniformity_fix.py --check
    python career-ops/rule_uniformity_fix.py --apply
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pymupdf

MASTER = Path(r"C:/Users/mukun/Downloads/codex/CV_FORMAT_MASTER.pdf")
BASE = Path(r"C:/Users/mukun/Downloads/codex/work/base/Mukund_CV_BASE_2026-09-25.pdf")
RULE_XREFS = [20, 21, 22, 23, 24, 25]        # X6, X7, X8, X9, X14, X15

RULE_THICKNESS = 0.96          # points; uniform for all six rules

# label, x_left, x_right, y_top   (page points, top-down origin)
RULES = [
    ("Professional Summary", 21.84, 545.20, 68.00),
    ("Technical Skills", 21.84, 545.20, 128.80),
    ("Education", 21.84, 545.20, 211.20),
    ("Work Experience", 21.84, 545.20, 320.00),
    ("Projects", 20.96, 516.00, 500.00),
    ("Certifications", 21.84, 545.12, 794.48),
]


def measure(path: Path) -> dict[str, float]:
    """Rendered thickness of each section rule, in points.

    Renders a narrow strip centred inside each rule's horizontal span at high
    dpi. Every column of that strip is fully inked where the rule exists, so
    thickness is total ink area divided by strip width.
    """
    doc = pymupdf.open(str(path))
    page = doc[0]
    out: dict[str, float] = {}
    dpi = 2400
    scale = dpi / 72.0
    for label, x0, x1, ytop in RULES:
        xm = (x0 + x1) / 2
        clip = pymupdf.Rect(xm - 40, ytop - 2.5, xm + 40, ytop + 4.5)
        pm = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, clip=clip)
        arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width)
        cov = (255.0 - arr.astype(float)) / 255.0
        out[label] = round((cov.sum() / pm.width) / scale, 4)
    doc.close()
    return out


def apply_fix(path: Path) -> list[str]:
    """Neutralise the old rule XObjects and draw six uniform rules."""
    doc = pymupdf.open(str(path))
    page = doc[0]

    # 1. Empty every rule XObject so the original inconsistent artwork is gone.
    for xref in RULE_XREFS:
        doc.update_stream(xref, b"q Q\n")

    # 2. Draw six fresh rules - identical thickness, original position and width.
    drawn = []
    for label, x0, x1, ytop in RULES:
        rect = pymupdf.Rect(x0, ytop, x1, ytop + RULE_THICKNESS)
        page.draw_rect(rect, color=None, fill=(0, 0, 0), width=0, overlay=True)
        drawn.append(f"{label}: x {x0}-{x1}, y {ytop}-{ytop + RULE_THICKNESS}")

    tmp = path.with_suffix(".rulefix.tmp.pdf")
    doc.save(str(tmp), deflate=True, garbage=0)
    doc.close()
    shutil.move(str(tmp), str(path))
    return drawn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    print("BEFORE - rendered rule thickness (pt):")
    before = measure(MASTER)
    for k, v in before.items():
        print(f"   {k:22} {v:.4f}")
    bvals = sorted(set(round(v, 3) for v in before.values()))
    print(f"   distinct: {bvals}  ({len(bvals)} different thicknesses)")

    if args.check and not args.apply:
        return 0

    stamp = "2026-10-03"
    for p in (MASTER, BASE):
        if p.exists():
            bak = p.with_name(f"{p.stem}_pre-rulefix-{stamp}{p.suffix}")
            if not bak.exists():
                shutil.copy2(p, bak)
                print(f"\nbackup: {bak}")

    src = pymupdf.open(str(MASTER))
    text_before = src[0].get_text()
    spans_before = len(src[0].get_text("words"))
    src.close()

    print("\ndrawing:")
    for line in apply_fix(MASTER):
        print(f"   {line}")

    after = measure(MASTER)
    print("\nAFTER:")
    for k, v in after.items():
        print(f"   {k:22} {v:.4f}")
    avals = [round(v, 3) for v in after.values()]
    print(f"   distinct: {sorted(set(avals))}")

    d = pymupdf.open(str(MASTER))
    text_after = d[0].get_text()
    spans_after = sum(
        len(l["spans"]) for b in d[0].get_text("dict")["blocks"] for l in b.get("lines", [])
    )
    pages = d.page_count
    d.close()

    uniform = len(set(avals)) == 1
    on_target = all(abs(v - RULE_THICKNESS) < 0.03 for v in after.values())
    print(f"\n   UNIFORM:        {uniform}")
    print(f"   all {RULE_THICKNESS}pt:      {on_target}")
    print(f"   text unchanged: {text_before == text_after}")
    print(f"   spans:          {spans_before} -> {spans_after}")
    print(f"   pages:          {pages}")
    return 0 if (uniform and on_target and text_before == text_after) else 1


if __name__ == "__main__":
    raise SystemExit(main())
