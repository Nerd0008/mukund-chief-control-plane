# Application package — TTP Group, Graduate Consultant - Software Engineering 2027 (Melbourn)

**Status:** Applied (recorded on owner standing instruction)
**Date applied:** 2026-10-03
**Tracker row:** `uk-cyber-job-tracker.xlsx` → Jobs → `J43`

## Vacancy

| Field | Value |
|---|---|
| Employer | TTP Group (TTP plc) — employee-owned technology and product development consultancy |
| Role | Graduate Consultant - Software Engineering - 2027 |
| Location | Melbourn, Royston, UK — south of Cambridge. **On-site five days a week required** |
| Contract | Permanent, full-time, graduate |
| Start | September 2027 |
| Salary | Not published |
| Benefits | Profit-related bonus, virtual shares, 10% employer pension, private medical, free onsite lunch, life insurance, 25 days holiday, relocation support if applicable |
| Recruitment | **Rolling — no deadline**; advert closes once spaces are filled |
| Official URL | https://jobs.smartrecruiters.com/TTP1/744000149037789-graduate-consultant-software-engineering-2027 |
| ATS platform | SmartRecruiters (TTP1 tenant) |
| URL verified live by Chief | 2026-10-03 |

## Fit assessment

**A stretch application, recorded honestly.** The posting asks for *"a minimum 2:1 in Computer
Science, Software Engineering or a closely related discipline, with strong accompanying A-Levels
(or equivalent)"*. The owner holds a BCA in computer applications (CGPA 9.17) and an MSc in
Information Security (Merit) but **no A-Levels**, and has no software engineering employment.

**Genuine transferable evidence:**

- *Prototype design and iteration* → a Chrome extension built in JavaScript with 25+ detection
  patterns; a Python phishing-analysis prototype with the Gmail API and an LLM.
- *Rigorous testing* → 150+ manual test cases at 93.7% accuracy with deliberate false-positive
  checking and iterative rule refinement.
- *Multi-language, multi-domain academic base* → Python, Java, JavaScript, C++, C, MySQL, AI & ML
  across the BCA; Secure Business Architectures and Critical Infrastructure Security in the MSc.
- *Requirements gathering and client-facing communication* → 4–5 access requests a day taken from
  colleagues, clarified and documented; control requirements explained to 7–8 colleagues per shift.
- *Systems thinking* → Windows Event Log analysis, server health monitoring, debugging via error
  codes and DLL analysis.

**Genuine gaps — do not claim:** no formal software engineering role; no project leadership or
client-relationship ownership; no manufacturing or hardware transfer experience; no exposure to the
domains named (drug delivery devices, DMTA, 5G NTN antennas); no evidence against the "strong
A-Levels" wording.

## Related opportunity flagged to the owner

TTP runs a **Graduate Consultant - Cyber / AI - 2027** at the same Melbourn campus
(`https://jobs.smartrecruiters.com/TTP1/744000149036450-graduate-consultant-cyber-ai-2027`), plus a
Cyber/AI summer internship. Given the owner's security background, the Cyber/AI graduate role is a
closer match than the Software Engineering one. Flagged on 2026-10-03; not applied for unless the
owner supplies that JD.

## Files in this package

| File | What it is |
|---|---|
| `jd.txt` | Job description text as supplied by the owner, 2026-10-03 |
| `cv_mukund_didwania_2026-10-03.pdf` | Base CV (byte-identical to the owner-designated base) |
| `cv.txt` | Extracted text of the base CV |
| `cv_edits.json` | The 7 layout-preserving edits, replayable |
| `cv_tailor_report.json` | `cv_tailor.py` gate report: 7 edits, 0 problems, all verifications true |
| `cv_tailored_ttp.pdf` | Tailored CV (copy of the delivered file) |
| `cover_spec.json` | Spec consumed by `build_cover.py` |
| `cover_letter_ttp.pdf` | Cover letter (copy of the delivered file) |
| `tracker_manifest.json` | Manifest consumed by `career-ops/tracker_writer.py` |
| `preview/before.png`, `preview/after.png`, `preview/cover.png` | Rendered QA images |
| `README.md` | This file |

## Delivered files

- CV: `C:\Users\mukun\Downloads\codex\_CVs\Mukund_Didwania_TTP_Graduate_Software_Engineering_Consultant_CV.pdf`
- Cover letter: `C:\Users\mukun\Downloads\codex\_cover\Mukund_Didwania_TTP_Graduate_Software_Engineering_Consultant_Cover_Letter.pdf`

## Format verification (independently re-checked)

- Page count 1 → 1; page geometry identical (`rect` equal); spans 81 → 81 (89 with whitespace).
- `untouched_spans_unchanged: true`, `all_replacements_present: true`, `moved: []`, `missing: []`.
- Independent span-level diff: exactly **14 changed lines = the 7 edits**; no font-size changes.
- Positional drift: **none**. Non-ASCII census identical (NBSP ×4, en dash, bullet); no U+037E.
- Character budget per element: −13.6% to +2.4% (all within ±15%).
- **Objective geometry checks (both master and output):** no span past the right margin, no span
  past the left margin, no overlapping spans on any baseline.
- **Pixel diff at 150 dpi: 1.88% of the page changed**, in 6 bands only — summary lines (73.9–109.9pt),
  Security Analysis + Systems & Support lines (131.5–150.7pt), Framework line (176.2–185.3pt),
  Communication line (187.7–196.8pt). Every band maps to an edited element; nothing else moved.

## Fact gate

- CV: `{"verdict":"warn","invented":[],"unsupportedFacts":[],"forbidden":[]}` (warnings "built", "achieved")
- Cover letter: `{"verdict":"pass","invented":[],"unsupportedFacts":[],"forbidden":[],"warnings":[]}`

The first cover draft was **blocked**: `using twenty-five detection patterns` was parsed by the
tool extractor as a tool claim. Reworded to `with twenty-five detection patterns` and rebuilt; the
letter then returned a clean `pass` with zero warnings.

## Provenance

- JD text supplied by the owner via Discord on 2026-10-03.
- Official SmartRecruiters URL located by Chief and verified live (TTP1 tenant, req 744000149037789).
- CV tailored with `career-ops/cv_tailor.py` (canonical gated path). Cover letter built with
  `career-ops/build_cover.py` (format-locked, spec-driven).
- No application was submitted, and no employer or recruiter was contacted.
