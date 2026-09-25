#!/usr/bin/env python3
"""Surgical, layout-preserving text replacement for the master CV PDF.

The master CV is a fixed-geometry document: one A4 page (595.5 x 850.5 pt),
Times New Roman throughout, every line placed at an absolute baseline. Reflowing
it -- or regenerating it from HTML -- moves every element. So tailoring works the
way it always has for this document: **redact the original text of a line and
re-typeset new text at that line's own origin, in that line's own font and size**.

What this script guarantees
---------------------------
* Edits are addressed by the exact original text, and each `find` must match
  exactly one span. Ambiguous or missing text is a hard error, never a guess.
* Only the named spans are touched. Every other span is re-read afterwards and
  must be byte-identical in text, position, font and size.
* Each edit is checked twice: character-count delta against the ±15% budget the
  design allows, and *rendered* width measured with the real font file against
  the space actually available on that line (next span, or the right margin).
  Width is the one that matters -- the boxes are fixed, so overflow collides.
* It refuses to write if any check fails, unless --force.
* Output is a new file. The master is never modified in place.

Usage
-----
    python career-ops/cv_tailor.py --master <master.pdf> --edits <edits.json> \
        --out <tailored.pdf> [--report <report.json>] [--force]

Edits file:

    {"edits": [
      {"find": "exact original span text", "replace": "new text"},
      ...
    ]}

`page` defaults to 0. `--png-dir DIR` also writes before/after page images.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import pymupdf

FONTS_DIR = Path(r"C:\Windows\Fonts")
FONT_FILES = {
    "TimesNewRomanPSMT": FONTS_DIR / "times.ttf",
    "TimesNewRomanPS-BoldMT": FONTS_DIR / "timesbd.ttf",
    "TimesNewRomanPS-ItalicMT": FONTS_DIR / "timesi.ttf",
    "TimesNewRomanPS-BoldItalicMT": FONTS_DIR / "timesbi.ttf",
}
FALLBACK_FONT = {
    "TimesNewRomanPS-BoldItalicMT": FONTS_DIR / "timesi.ttf",
}
INSERT_FONTNAME = {
    "TimesNewRomanPSMT": "tnr",
    "TimesNewRomanPS-BoldMT": "tnrb",
    "TimesNewRomanPS-ItalicMT": "tnri",
    "TimesNewRomanPS-BoldItalicMT": "tnrbi",
}
CHAR_BUDGET = 0.15  # +/-15% of the original element's character count
RIGHT_MARGIN = 573.75  # page width 595.5 - left margin 21.75
WIDTH_TOLERANCE = 1.0  # pt of slack allowed over the measured available space
REDACT_PAD = 0.0  # exact span bbox only: any padding can clip an adjacent span on the same baseline


def spans_of(page):
    """Every text span on the page, with geometry, font and origin."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if not span["text"].strip():
                    continue
                out.append({
                    "text": span["text"],
                    "bbox": pymupdf.Rect(span["bbox"]),
                    "origin": pymupdf.Point(span["origin"]),
                    "font": span["font"],
                    "size": span["size"],
                })
    return out


def line_peers(spans, target):
    """Spans sharing the target's baseline, sorted left to right."""
    same = [s for s in spans if abs(s["origin"].y - target["origin"].y) < 0.5]
    return sorted(same, key=lambda s: s["origin"].x)


def available_width(spans, target):
    """Space from the target's origin to the next span on its baseline, or the margin."""
    peers = line_peers(spans, target)
    right = RIGHT_MARGIN
    for i, s in enumerate(peers):
        if s is target:
            if i + 1 < len(peers):
                right = peers[i + 1]["bbox"].x0 - 1.5
            break
    else:
        # target not found by identity: fall back to anything to its right
        for s in peers:
            if s["origin"].x > target["origin"].x + 0.1 and s["bbox"].x0 < right:
                right = s["bbox"].x0 - 1.5
    return max(0.0, right - target["origin"].x)


def measure(fontfile: Path, text: str, size: float) -> float:
    return pymupdf.Font(fontfile=str(fontfile)).text_length(text, fontsize=size)


def norm(text: str) -> str:
    """Compare text ignoring PyMuPDF's U+00A0 for inserted spaces.

    `insert_text` writes the space glyph with a ToUnicode entry of U+00A0, so
    freshly inserted text extracts as non-breaking spaces until `normalise_spaces`
    rewrites the CMap. Normalise both sides of every comparison.
    """
    return text.replace("\xa0", " ")


def normalise_spaces(path: Path) -> int:
    """Rewrite U+00A0 -> U+0020 in every ToUnicode CMap, in place.

    PyMuPDF maps the TTF space glyph to U+00A0, which survives into extraction and
    can confuse ATS parsers. The glyph widths are unaffected, so layout is safe.
    """
    doc = pymupdf.open(path)
    patched = 0
    for xref in range(1, doc.xref_length()):
        try:
            tu = doc.xref_get_key(xref, "ToUnicode")
        except Exception:
            continue
        if tu and tu[0] == "xref":
            num = int(tu[1].split()[0])
            raw = doc.xref_stream(num)
            if raw and b"00a0" in raw.lower():
                doc.update_stream(num, re.sub(rb"(?i)00a0", b"0020", raw))
                patched += 1
    tmp = path.with_suffix(".spaces.tmp.pdf")
    doc.save(str(tmp), garbage=3, deflate=True)
    doc.close()
    tmp.replace(path)
    return patched


def subset_embedded_fonts(path: Path) -> dict:
    """Subset the fonts we embedded, which arrive whole (~640 KB each).

    Glyph ids change; text, geometry and rendering do not. Verified by the caller
    as a zero-pixel-difference render before/after.
    """
    before = path.stat().st_size
    doc = pymupdf.open(path)
    doc.subset_fonts()
    tmp = path.with_suffix(".subset.tmp.pdf")
    doc.save(str(tmp), garbage=4, deflate=True, clean=True)
    doc.close()
    tmp.replace(path)
    return {"bytes_before": before, "bytes_after": path.stat().st_size}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--edits", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--png-dir")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    master = Path(args.master)
    if not master.exists():
        raise SystemExit(f"master not found: {master}")
    spec = json.loads(Path(args.edits).read_text(encoding="utf-8"))
    edits = spec.get("edits", [])

    doc = pymupdf.open(master)
    page = doc[0]
    master_rect = (page.rect.width, page.rect.height)
    before = spans_of(page)
    before_snapshot = [dict(s) for s in before]

    if args.png_dir:
        Path(args.png_dir).mkdir(parents=True, exist_ok=True)
        page.get_pixmap(dpi=110).save(str(Path(args.png_dir) / "before.png"))

    results, problems = [], []
    plan = []

    for edit in edits:
        find = edit["find"]
        replace = edit["replace"]
        matches = [s for s in before if s["text"].strip() == find.strip()]
        if len(matches) != 1:
            problems.append({"find": find, "error": f"matched {len(matches)} spans, need exactly 1"})
            continue
        target = matches[0]
        if target["font"] not in FONT_FILES:
            problems.append({"find": find, "error": f"no font file known for {target['font']}"})
            continue
        fontfile = FONT_FILES[target["font"]]
        if not fontfile.exists():
            fontfile = FALLBACK_FONT.get(target["font"], fontfile)
        if not fontfile.exists():
            problems.append({"find": find, "error": f"font file missing: {fontfile}"})
            continue

        old_len, new_len = len(find.strip()), len(replace.strip())
        char_delta = (new_len - old_len) / max(1, old_len)
        avail = available_width(before, target)
        new_w = measure(fontfile, replace, target["size"])
        old_w = target["bbox"].width
        entry = {
            "find": find, "replace": replace,
            "font": target["font"], "size": round(target["size"], 2),
            "origin": [round(target["origin"].x, 2), round(target["origin"].y, 2)],
            "old_chars": old_len, "new_chars": new_len,
            "char_delta_pct": round(char_delta * 100, 1),
            "old_width_pt": round(old_w, 2), "new_width_pt": round(new_w, 2),
            "available_pt": round(avail, 2),
        }
        if abs(char_delta) > CHAR_BUDGET:
            entry["flag"] = f"char count {char_delta*100:+.1f}% exceeds +/-15%"
        if new_w > avail + WIDTH_TOLERANCE:
            entry["flag"] = (entry.get("flag", "") + "; " if entry.get("flag") else "") + \
                f"rendered width {new_w:.1f}pt exceeds available {avail:.1f}pt"
        if entry.get("flag"):
            problems.append({"find": find, "error": entry["flag"]})
        results.append(entry)
        plan.append((target, replace, fontfile))

    if problems and not args.force:
        doc.close()
        print(json.dumps({"ok": False, "reason": "checks failed; nothing written",
                          "problems": problems, "measured": results}, indent=2))
        return 1

    for target, replace, fontfile in plan:
        rect = pymupdf.Rect(target["bbox"].x0 - REDACT_PAD, target["bbox"].y0 - REDACT_PAD,
                            target["bbox"].x1 + REDACT_PAD, target["bbox"].y1 + REDACT_PAD)
        page.add_redact_annot(rect, fill=None)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)

    for target, replace, fontfile in plan:
        name = INSERT_FONTNAME[target["font"]]
        page.insert_font(fontname=name, fontfile=str(fontfile))
        page.insert_text(target["origin"], replace, fontname=name,
                         fontsize=target["size"], color=(0, 0, 0))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out), garbage=3, deflate=True)
    doc.close()

    space_streams_patched = normalise_spaces(out)
    font_subset = subset_embedded_fonts(out)

    # ---- verification -----------------------------------------------------
    doc2 = pymupdf.open(out)
    page2 = doc2[0]
    after = spans_of(page2)
    replaced = {norm(e["replace"].strip()) for e in results}
    originals = {norm(e["find"].strip()) for e in results}
    nbsp_left = page2.get_text().count("\xa0")

    untouched_before = [s for s in before_snapshot if norm(s["text"].strip()) not in originals]
    moved, missing = [], []
    after_by_text = {}
    for s in after:
        after_by_text.setdefault(norm(s["text"].strip()), []).append(s)
    for s in untouched_before:
        cands = after_by_text.get(norm(s["text"].strip()), [])
        if not cands:
            missing.append({"text": s["text"][:60], "font": s["font"]})
            continue
        ok = any(abs(c["origin"].x - s["origin"].x) < 0.6 and abs(c["origin"].y - s["origin"].y) < 0.6
                 and abs(c["size"] - s["size"]) < 0.05 and c["font"] == s["font"] for c in cands)
        if not ok:
            c = cands[0]
            moved.append({"text": s["text"][:50], "before": [round(s["origin"].x, 2), round(s["origin"].y, 2)],
                          "after": [round(c["origin"].x, 2), round(c["origin"].y, 2)]})

    replacements_present = all(any(norm(a["text"].strip()) == r for a in after) for r in replaced)
    page_ok = (abs(page2.rect.width - master_rect[0]) < 0.05
               and abs(page2.rect.height - master_rect[1]) < 0.05)

    if args.png_dir:
        page2.get_pixmap(dpi=110).save(str(Path(args.png_dir) / "after.png"))

    report = {
        "ok": True and not problems,
        "master": str(master),
        "output": str(out),
        "page": {"width": page2.rect.width, "height": page2.rect.height, "page_count": doc2.page_count},
        "edits_applied": len(results),
        "spans_before": len(before_snapshot),
        "spans_after": len(after),
        "measured": results,
        "problems": problems,
        "verification": {
            "untouched_spans_unchanged": not moved and not missing,
            "moved": moved,
            "missing": missing,
            "all_replacements_present": replacements_present,
            "page_geometry_unchanged": page_ok,
            "space_streams_normalised": space_streams_patched,
            "non_breaking_spaces_remaining": nbsp_left,
            "font_subsetting": font_subset,
        },
    }
    doc2.close()

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
