# Application package — BDO LLP, 2027 Audit Technology Graduate Programme (London)

**Status:** Applied (recorded on owner instruction) — **but see the eligibility blocker below before submitting**
**Date applied:** 2026-10-03
**Tracker row:** `uk-cyber-job-tracker.xlsx` → Jobs → `J39`

## Vacancy

| Field | Value |
|---|---|
| Employer | BDO LLP |
| Role | 2027 Audit Technology Graduate Programme — London |
| Team | Technology Risk Assurance (TRA): Data Analytics or IT Controls |
| Location | London; must live within commutable distance. Relocation support is **not** provided |
| Salary | £33,000 per annum |
| Contract | 3-year training contract; programme starts Monday 20 September 2027 |
| Qualifications funded | CFAB, ICAEW PowerBI Certification, CISA, Data Camp courses |
| Closing date | Sunday 15 November 2026 |
| Official URL | https://careers.bdo.co.uk/job/london/2027-audit-technology-graduate-programme/1469/45085583424 |
| ATS platform | careers.bdo.co.uk (Radancy) |
| URL verified live by Chief | 2026-10-03 |

## Eligibility assessment (Chief, 2026-10-03)

Assessed against the posting's stated criteria. Per owner instruction, work-authorisation status is
not discussed — the posting's own wording is recorded here for the file and nothing further is raised.

Criteria — all met:

- Minimum 2:2 in any discipline — Mukund holds MSc Information Security (Merit) and BCA (CGPA 9.17).
- Three A-levels A*–C or equivalent — CBSE Class XII is A-level standard; three A-levels are not
  literally held, so **the equivalent route must be evidenced** (see `school_education.json`).
  Class XII all-six-subjects percentage 78.5%; English 91%; Computer Science 82%; Mathematics 64%.
- GCSE Maths and English grade 4+ — no GCSEs (educated in India). Class X is the GCSE stage:
  overall 83.5%, English 80%, Mathematics 71%. State the equivalent, never leave blank.
- No clearance, citizenship or residency requirement stated.

## Fit assessment

**Controls team — strong match on evidence:**

- IT General Controls / access management: daily Active Directory access requests with approval
  verification, time-limited permissions and documented access periods (current role).
- Cyber security risk assessments: weekly store-wide risk assessments and daily compliance checks
  against operational controls, with records and corrective-action escalation (Co-op PIC).
- Control testing and documentation: 150+ manual test cases to 93.7% accuracy with deliberate
  false-positive checking (SafePaste).
- Framework familiarity: ISO 27001 (MSc Security Management module), Cyber Essentials, GDPR, NIST CSF.
- Windows Event Log analysis, PowerShell, Python.

**Data team — partial match, one real gap:**

- Python and SQL are held; methodical validation and documentation are well evidenced.
- **No evidenced Alteryx, Databricks or SAS experience.** These are named tools in the JD. They must
  not be claimed; they would need honest framing as "not yet used, willing to learn".

**Genuinely absent (do not claim):** audit or ITGC testing tooling, financial statement audit
experience, visualisation/dashboard delivery (Power BI, Tableau).

## Files in this package

| File | What it is |
|---|---|
| `jd.txt` | Job description text as supplied by the owner, 2026-10-03 |
| `cv_mukund_didwania_2026-10-03.pdf` | Base CV as supplied by the owner (byte-identical to the 2026-09-25 base) |
| `cv.txt` | Extracted text of the base CV |
| `cv_edits.json` | The 7 layout-preserving edits, replayable |
| `cv_tailor_report.json` | `cv_tailor.py` gate report: 7 edits applied, 0 problems, all verifications true |
| `cv_tailored_bdo.pdf` | Tailored CV (copy of the delivered file) |
| `cover_spec.json` | Spec consumed by `build_cover.py` |
| `cover_letter_bdo.pdf` | Cover letter (copy of the delivered file) |
| `job_record.json` | Job record used to run `cv_workflow.py draft` |
| `tracker_manifest.json` | Manifest consumed by `career-ops/tracker_writer.py` |
| `preview/before.png`, `preview/after.png`, `preview/cover.png` | Rendered QA images |
| `README.md` | This file |

## Delivered files

- CV: `C:\Users\mukun\Downloads\codex\_CVs\Mukund_Didwania_BDO_Audit_Technology_Graduate_CV.pdf`
- Cover letter: `C:\Users\mukun\Downloads\codex\_cover\Mukund_Didwania_BDO_Audit_Technology_Graduate_Cover_Letter.pdf`

## Format verification (independently re-checked, not taken on trust)

- Page count 1 → 1; page geometry 595.5 × 850.5 pt unchanged.
- Spans 81 → 81 (89 including whitespace/continuation spans); `untouched_spans_unchanged: true`,
  `all_replacements_present: true`, `moved: []`, `missing: []`.
- An independent span-level diff shows exactly **14 changed lines = the 7 edits**, nothing else.
- Non-ASCII census identical to the master (NBSP ×4, en dash, bullet); no soft hyphens and no
  U+037E, so the ToUnicode repair held and ATS keyword matching is intact.
- Character budget per element: −9.4% to +9.5% (all within ±15%); rendered width comfortably inside
  the measured box in every case.
- Rendered page visually inspected: no overflow, overlap, clipping or section shift.

## Fact gate

Re-run on the rewritten text after the edits (a rewrite is an unverified claim until re-gated):

- CV: `{"verdict":"warn","invented":[],"unsupportedFacts":[],"forbidden":[]}`
- Cover letter: `{"verdict":"warn","invented":[],"unsupportedFacts":[],"forbidden":[]}`

`warn` is the expected verdict for the words "built" and "achieved" (both evidenced in the canonical
sources). Nothing invented, unsupported or forbidden.

## Provenance

- JD text and base CV supplied by the owner via Discord on 2026-10-03.
- The supplied CV is byte-identical (md5 `c32ec752153847ec5e8f05fc60ec53e9`) to
  `Mukund_CV_BASE_2026-09-25.pdf` and `CV_FORMAT_MASTER.pdf` — no re-baselining was needed.
- Official ATS URL located from the `careers.bdo.co.uk/sitemap.xml` job list and verified live.
- CV tailored with `career-ops/cv_tailor.py` (the canonical gated path). No parallel builder was used.
- Cover letter built with `career-ops/build_cover.py` (format-locked, spec-driven).
- Draft pipeline (`career-ops/cv_workflow.py draft`) run for term ranking and the gap list; output at
  `runtime/career-ops/cv-drafts/bdo-audit-technology-2027/`.
- No application was submitted, and no employer or recruiter was contacted.
