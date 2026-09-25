#!/usr/bin/env python3
"""Generic, format-locked cover-letter builder.

Reproduces the established one-page A4 letter format exactly:
    A4 595.28 x 841.89 | left margin x=65 | Times New Roman 11pt | leading 12pt
    bold heading | "Dear <X> Recruitment Team," | 5 benefit-driven paragraphs |
    left-aligned closing with linked (blue) email and LinkedIn.

Usage:
    python career-ops/build_cover.py --spec <spec.json> [--qa <png>]

Spec:
    {
      "heading":    "Application for <Role>",
      "salutation": "Dear <Company> Recruitment Team,",
      "out":        "<absolute pdf path>",
      "paragraphs": ["...", "..."]
    }

Every paragraph is the author's responsibility to ground in owner-asserted evidence;
this script only guarantees the format. It refuses to write if any line overflows the
measure, if the result is not one page, or if content runs into the bottom margin.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cv_tailor import CMAP_FIXES  # noqa: E402  (shared CMap repair definitions)

FONT_REG = r"C:\Windows\Fonts\times.ttf"
FONT_BOLD = r"C:\Windows\Fonts\timesbd.ttf"

PAGE = (595.28, 841.89)
X = 65.0
WIDTH = 465.0
SIZE = 11.0
LEADING = 12.0
PARA_GAP = 17.0
CLOSING_LEADING = 16.0
Y_HEADING = 58.7
Y_SALUTATION = 82.7
Y_BODY = 106.2
SIGN_OFF_GAP = 53.3
BLUE = (5 / 255, 99 / 255, 145 / 255)
EMAIL = "mukunddidwania3@gmail.com"
LINKEDIN = "https://www.linkedin.com/in/mukund-didwania-612771166"


def wrap(text: str, font, size: float = SIZE, width: float = WIDTH) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = word if not cur else f"{cur} {word}"
        if font.text_length(cand, fontsize=size) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def repair_and_subset(path: Path) -> dict:
    """Subset the embedded fonts, then repair the inserted font's bad CMap entries.

    Order matters: PyMuPDF's embedded-TTF path writes U+00A0 for a space, U+00AD for a
    hyphen and U+037E for a semicolon. Those survive into extraction and silently break
    ATS keyword matching, so they must be fixed after the glyph ids are finalised.
    """
    doc = pymupdf.open(path)
    doc.subset_fonts()
    tmp = path.with_suffix(".sub.tmp.pdf")
    doc.save(str(tmp), garbage=4, deflate=True, clean=True)
    doc.close()
    tmp.replace(path)

    import re
    doc = pymupdf.open(path)
    entry = re.compile(rb"<([0-9A-Fa-f]{2,4})>\s*<([0-9A-Fa-f]{4,8})>")

    def _sub(m):
        src, dst = m.group(1), m.group(2)
        if len(dst) < 4:
            return m.group(0)
        new = CMAP_FIXES.get(dst[:4].lower().decode())
        return m.group(0) if not new else b"<" + src + b"> <" + new.encode() + dst[4:] + b">"

    patched = 0
    for page in doc:
        for fo in page.get_fonts(full=True):
            tu = doc.xref_get_key(fo[0], "ToUnicode")
            if not tu or tu[0] != "xref":
                continue
            num = int(tu[1].split()[0])
            raw = doc.xref_stream(num)
            if not raw:
                continue
            fixed = entry.sub(_sub, raw)
            if fixed != raw:
                doc.update_stream(num, fixed)
                patched += 1
    tmp = path.with_suffix(".cmap.tmp.pdf")
    doc.save(str(tmp), garbage=4, deflate=True, clean=True)
    doc.close()
    tmp.replace(path)
    return {"bytes": path.stat().st_size, "cmap_streams_patched": patched}


def build(spec: dict) -> int:
    reg = pymupdf.Font(fontfile=FONT_REG)
    bold = pymupdf.Font(fontfile=FONT_BOLD)

    out = Path(spec["out"])
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE[0], height=PAGE[1])
    page.insert_font(fontname="REG", fontfile=FONT_REG)
    page.insert_font(fontname="BOLD", fontfile=FONT_BOLD)

    page.insert_text((X, Y_HEADING), spec["heading"], fontname="BOLD", fontsize=SIZE, color=(0, 0, 0))
    page.insert_text((X, Y_SALUTATION), spec["salutation"], fontname="REG", fontsize=SIZE, color=(0, 0, 0))

    y = Y_BODY
    lines_rendered = 0
    for para in spec["paragraphs"]:
        for line in wrap(para, reg):
            w = reg.text_length(line, fontsize=SIZE)
            if w > WIDTH:
                print(f"!! line overflows by {w - WIDTH:.1f}pt: {line!r}")
                return 1
            page.insert_text((X, y), line, fontname="REG", fontsize=SIZE, color=(0, 0, 0))
            y += LEADING
            lines_rendered += 1
        y += PARA_GAP - LEADING

    y += SIGN_OFF_GAP - PARA_GAP + LEADING
    closing = [("Kind regards,", (0, 0, 0), None),
               ("Mukund Didwania", (0, 0, 0), None),
               (EMAIL, BLUE, f"mailto:{EMAIL}"),
               ("LinkedIn", BLUE, LINKEDIN)]
    last_y = y
    for text, colour, link in closing:
        page.insert_text((X, y), text, fontname="REG", fontsize=SIZE, color=colour)
        if link:
            w = reg.text_length(text, fontsize=SIZE)
            page.insert_link({"kind": pymupdf.LINK_URI,
                              "from": pymupdf.Rect(X, y - LEADING + 2, X + w, y + 3),
                              "uri": link})
        last_y = y
        y += CLOSING_LEADING

    print(f"body lines: {lines_rendered} | last baseline y={last_y:.1f} of {PAGE[1]}")
    if last_y > PAGE[1] - 60:
        print(f"!! content runs into the bottom margin (y={last_y:.1f})")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.pdf")
    doc.save(str(tmp), garbage=3, deflate=True)
    doc.close()

    stats = repair_and_subset(tmp)
    tmp.replace(out)

    q = pymupdf.open(out)
    txt = q[0].get_text()
    if q.page_count != 1:
        print(f"!! page count {q.page_count}, expected 1")
        return 1
    bad = {c: txt.count(c) for c in ("\u00ad", "\u037e", "\u00a0") if txt.count(c)}
    print(f"pages: {q.page_count} | chars: {len(txt)} | links: {len(q[0].get_links())} | {stats}")
    print(f"bad characters remaining: {bad or 'none'}")
    if bad:
        print("!! ToUnicode repair incomplete")
        return 1
    if spec.get("qa"):
        q[0].get_pixmap(dpi=150).save(spec["qa"])
        print(f"QA {spec['qa']}")
    q.close()
    print(f"WROTE {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--qa")
    args = ap.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if args.qa:
        spec["qa"] = args.qa
    return build(spec)


if __name__ == "__main__":
    raise SystemExit(main())
