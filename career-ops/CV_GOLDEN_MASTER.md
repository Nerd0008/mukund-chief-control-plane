# Immutable CV production

The owner-designated authoritative master is `master/CV_FORMAT_MASTER.pdf`. Its derived and versioned `master/cv_master_manifest.json` records every span, original text, bounding box, baseline/origin, font/size, rendered width boundary, neighbours, section and editability. The master must not be regenerated. Its original embedded fonts are the font/layout source; no external font substitution occurs.

Pipeline: JD/evidence analysis -> cv_edits.json -> deterministic per-span fit -> fresh master -> one native glyph-stream edit -> structural/ATS verification -> visual verification -> verified delivery. Only content may be shortened. Initial content plus at most two alternatives/callback rewrites gives three attempts per affected span. A persistent job ledger prevents command re-entry resetting the budget. Each job gets one render and eight native agent turns; no visual repair loop. Stop and name the affected span on failure.

Outputs live only in `%LOCALAPPDATA%/hermes/runtime/career-ops/cv-output/<job>/`. Windows read-only handles deny concurrent modification/deletion of master, manifest, renderer, verification implementation, runtime guard and layout config during generation. Before/after SHA-256s must agree. The native CV hook blocks renderer patches, parallel builders, unknown tools and writes outside that one job's edits JSON.

The renderer updates only the approved original PDF text object's glyph instructions, preserving its font resource, font size, text matrix, graphics and every other object. It does not redact, reconstruct surrounding text, subset/reinsert fonts or alter geometry. Missing glyphs, unsupported text objects, overflow or ambiguous span selection fail closed.

Verification compares page count/rect/media/crop/rotation and every expected span's text, font, size and origin. It renders master/output at 144 DPI, masks only approved span regions (not sections/pages), and requires zero changed RGB pixels outside them. Documented mask rounding allows one pixel at region edges; channel tolerance is zero. The strict independent audit accepts no reflow exemption. PDF extraction must contain the intended text without replacement characters.

Discord delivery independently checks the output hash, protected dependency hashes, PASS sidecar and reruns structural/visual verification. The connect/reload handler binds to the actual Hermes lazy-loaded Discord adapter. Renaming a CV does not bypass verification. Failure sends a reason without the candidate PDF. Non-CV documents retain their normal handling.

Deployment sources: `hermes-plugins/career-cv-golden-guard/` and `hermes-skills/job-application-intake/SKILL.md`. Install the plugin under Hermes home, enable with `hermes plugins enable career-cv-golden-guard`, copy the versioned skill and restart the native gateway when source changes. Maintenance/code repair is separate from normal application generation; never patch implementation to make a single application pass.

Regression: `python -m pytest career-ops/tests/test_cv_golden.py -q`. Cover-letter compatibility retains CMAP_FIXES but does not permit a second CV renderer. cv_workflow's markdown content drafting is not a PDF renderer or delivery bypass.

## Owner confirmation — supplied PDF on 2026-10-09

`C:/Users/mukun/Downloads/Mukund Didwania CV.pdf` SHA-256 is 01643b073e63cce3d8d71b3cd0ebbc2d521bd3b74cb438de2da06e6e8a23039b, identical to the canonical master. It is the fixed visual template and professional-information source for future JD tailoring. The owner explicitly requires exact character counts and master-identical spacing/layout; differing wording is permitted, not arbitrary shorter labels or shifted value anchors.

Replacement character counts equal the original editable non-whitespace text. Native whitespace objects remain untouched and are independently verified byte-for-byte along with all non-edit streams. Skill label advance-width must remain within 0.5 point of the original so the fixed following value anchor retains its gap. No font shrink, layout reflow or blank padding workaround. The previous permissive content-length policy is superseded.
