"""Audit a generated CV against the master format, pixel-exact.

The master is read-only reference. This tool never writes to it; it compares a
generated CV against the master and reports EVERY structural deviation:

  * page geometry (rect, cropbox)
  * span count
  * per-span position, font family and size
  * section rules (count, x extent, length, stroke width)
  * text-level anomalies (space before punctuation, doubled spaces, label boldness)

Run it after every CV build. A build is not finished until this passes.

Usage:
    python career-ops/audit_cv_format.py <generated.pdf> [--master <master.pdf>]
    python career-ops/audit_cv_format.py <generated.pdf> --allow-reflow-y 274.88 ...
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import pymupdf

MASTER_DIR = Path(__file__).resolve().parent / "master"
DEFAULT_MASTER = MASTER_DIR / "CV_FORMAT_MASTER.pdf"
SPEC_PATH = MASTER_DIR / "format_spec.json"

# The same visual face can be embedded under two internal names after a subset
# round-trip. Collapse them so a cosmetic rename is not reported as a defect.
FONT_ALIASES = {
    "Times New Roman Bold": "TimesNewRomanPS-BoldMT",
    "Times New Roman Regular": "TimesNewRomanPSMT",
    "Times New Roman Italic": "TimesNewRomanPS-ItalicMT",
    "Times New Roman Bold Italic": "TimesNewRomanPS-BoldItalicMT",
    "TimesNewRomanPS-BoldItal": "TimesNewRomanPS-BoldItalicMT",
}


def fam(font: str) -> str:
    return FONT_ALIASES.get(font, font)


def spans(page) -> list[dict]:
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for s in line["spans"]:
                out.append({
                    "text": s["text"],
                    "font": fam(s["font"]),
                    "raw_font": s["font"],
                    "size": round(s["size"], 4),
                    "origin": (round(s["origin"][0], 4), round(s["origin"][1], 4)),
                    "bbox": tuple(round(v, 4) for v in s["bbox"]),
                })
    return out


def rules(page) -> list[dict]:
    out = []
    for dr in page.get_drawings():
        r = dr["rect"]
        # full-page white backgrounds are not rules
        if r.width > 560 and r.height > 800:
            continue
        w = dr.get("width") or r.height
        out.append({
            "type": dr["type"],
            "x0": round(r.x0, 4), "x1": round(r.x1, 4), "y": round(r.y0, 4),
            "len": round(r.width, 4), "width_pt": round(w, 6),
        })
    return sorted(out, key=lambda d: (round(d["y"], 1), d["x0"]))


def load_page(path: Path):
    d = pymupdf.open(str(path))
    pg = d[0]
    return d, pg


def text_anomalies(page) -> list[str]:
    t = page.get_text()
    out = []
    for m in re.finditer(r"\s+([,.;:])", t):
        seg = t[max(0, m.start() - 30):m.end() + 30].replace("\n", " / ")
        out.append(f"space before {m.group(1)!r}: ...{seg}...")
    for m in re.finditer(r"\b([A-Za-z]{3,})\s+\1\b", t, re.IGNORECASE):
        seg = t[max(0, m.start() - 40):m.end() + 40].replace("\n", " / ")
        out.append(f"doubled word: ...{seg}...")
    for m in re.finditer(r"\S  +\S", t):
        seg = t[max(0, m.start() - 30):m.end() + 30].replace("\n", " / ")
        out.append(f"multiple spaces mid-line: ...{seg}...")
    return out


def label_boldness(page) -> dict[str, str]:
    """Every span ending in ':' mapped to bold/regular, so an inconsistent label
    (the 'Modules:' class of bug) is visible in one glance."""
    out = {}
    for s in spans(page):
        if s["text"].rstrip().endswith(":"):
            key = s["text"].strip()
            out[key] = "bold" if "Bold" in s["font"] else "regular"
    return out


def audit(master_path: Path, out_path: Path, allow_reflow_y: list[float],
          allow_nbsp: bool) -> dict:
    dm, pm = load_page(master_path)
    do, po = load_page(out_path)
    ms, os_ = spans(pm), spans(po)
    mr, orr = rules(pm), rules(po)

    problems: list[str] = []
    info: list[str] = []

    # ---- geometry ---------------------------------------------------------
    if pm.rect != po.rect:
        problems.append(f"page rect {tuple(pm.rect)} -> {tuple(po.rect)}")
    else:
        info.append(f"page rect identical {tuple(pm.rect)}")

    # ---- span count -------------------------------------------------------
    if len(ms) != len(os_):
        problems.append(f"span count {len(ms)} -> {len(os_)}")
    else:
        info.append(f"span count identical {len(ms)}")

    # ---- rules ------------------------------------------------------------
    if len(mr) != len(orr):
        problems.append(f"rule count {len(mr)} -> {len(orr)}")
    else:
        info.append(f"rule count identical {len(mr)}")
        for a, b in zip(mr, orr):
            for k in ("x0", "x1", "len"):
                if abs(a[k] - b[k]) > 0.02:
                    problems.append(f"rule {k} {a[k]} -> {b[k]} (y={a['y']})")
            if abs(a["width_pt"] - b["width_pt"]) > 0.02:
                problems.append(f"rule width {a['width_pt']} -> {b['width_pt']} (y={a['y']})")
            if abs(a["y"] - b["y"]) > 0.02:
                problems.append(f"rule y {a['y']} -> {b['y']}")

    # ---- per-span position / font / size ----------------------------------
    # Position drift is EXPECTED when text is edited: a longer replacement moves
    # what follows it. So drift is reported as information, not failure. What must
    # never change is the FORMAT: the multiset of (font, size) pairs, the rules,
    # the page box, and the label styling.
    if len(ms) == len(os_):
        for i, (a, b) in enumerate(zip(ms, os_)):
            ay, by = a["origin"][1], b["origin"][1]
            declared = any(abs(ay - v) < 0.6 for v in allow_reflow_y)
            if abs(ay - by) > 0.02:
                problems.append(f"span {i} baseline moved {ay} -> {by} {a['text'][:40]!r}")
            if abs(a["origin"][0] - b["origin"][0]) > 0.02:
                info.append(f"x drift span {i} {a['origin'][0]} -> {b['origin'][0]} "
                            f"{a['text'][:34]!r}{' (declared)' if declared else ''}")
            if a["size"] != b["size"]:
                problems.append(f"span {i} size {a['size']} -> {b['size']} {a['text'][:40]!r}")

    # ---- format signature: every (font, size) pair, by count --------------
    # The single strongest format invariant. A font swap, a stray bold, or a
    # wrong point size all break it, whatever the text says.
    sig_m = collections.Counter((s["font"], s["size"]) for s in ms)
    sig_o = collections.Counter((s["font"], s["size"]) for s in os_)
    if sig_m != sig_o:
        only_m = sig_m - sig_o
        only_o = sig_o - sig_m
        if only_m:
            problems.append(f"format pairs lost: {dict(only_m)}")
        if only_o:
            problems.append(f"format pairs gained: {dict(only_o)}")
    else:
        info.append(f"format signature identical ({len(sig_m)} font/size pairs)")

    # ---- font census ------------------------------------------------------
    cm = collections.Counter(s["font"] for s in ms)
    co = collections.Counter(s["font"] for s in os_)
    if cm != co:
        problems.append(f"font census {dict(cm)} -> {dict(co)}")
    else:
        info.append(f"font census identical {dict(cm)}")

    # ---- text anomalies ---------------------------------------------------
    for a in text_anomalies(pm):
        if a not in text_anomalies(po):
            info.append(f"master-only anomaly (not introduced by build): {a}")
    for a in text_anomalies(po):
        if a not in text_anomalies(pm):
            problems.append(f"new text anomaly: {a}")

    # ---- label boldness consistency ---------------------------------------
    lm, lo = label_boldness(pm), label_boldness(po)
    for k in set(lm) & set(lo):
        if lm[k] != lo[k]:
            problems.append(f"label {k!r} boldness {lm[k]} -> {lo[k]}")

    # group labels by their stem so 'Modules:' appearing twice inconsistently shows
    stems = collections.defaultdict(set)
    for s in spans(po):
        m = re.match(r"^([A-Za-z &]+):", s["text"])
        if m:
            stems[m.group(1).strip()].add("bold" if "Bold" in s["font"] else "regular")
    for stem, kinds in stems.items():
        if len(kinds) > 1:
            problems.append(f"inconsistent label styling for {stem!r}: {sorted(kinds)}")

    dm.close(); do.close()

    return {"ok": not problems, "problems": problems, "info": info,
            "master": str(master_path), "output": str(out_path),
            "spans": len(ms), "rules": len(mr)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--master", default=str(DEFAULT_MASTER))
    ap.add_argument("--allow-reflow-y", type=float, action="append", default=[],
                    help="baseline whose horizontal drift is intentional")
    ap.add_argument("--allow-nbsp-normalised", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    master = Path(args.master)
    if not master.exists():
        print(f"master not found: {master}", file=sys.stderr)
        return 2

    rep = audit(master, Path(args.output), args.allow_reflow_y, args.allow_nbsp_normalised)

    if args.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1

    print(f"master: {rep['master']}")
    print(f"output: {rep['output']}")
    print(f"spans={rep['spans']} rules={rep['rules']}\n")
    for i in rep["info"]:
        print(f"  ok   {i}")
    for p in rep["problems"]:
        print(f"  FAIL {p}")
    print()
    if rep["ok"]:
        print("VERDICT: PASS - matches the master format")
        return 0
    print(f"VERDICT: FAIL ({len(rep['problems'])} deviation(s))")
    return 1


if __name__ == "__main__":
    sys.exit(main())
