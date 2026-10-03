# Pearson — Advanced Associate, Internal Audit, Controls, Compliance and Risk

**Applied:** 2026-10-03 · **Tracker row:** J45 · **Status:** Applied · **Priority:** High · **Fit:** 6.0/10

## Posting

- **Company:** Pearson
- **Role:** Advanced Associate, Internal Audit, Controls, Compliance and Risk (graduate programme)
- **Location:** Belfast or London (hybrid, at least one day a week in office)
- **Salary:** £30,000 London / £28,000 Belfast, plus annual bonus; fully funded ACCA
- **Programme:** 3 years, then permanent role
- **Start date:** by July 2027
- **Closing date:** 6 November 2026 (posting warns it may close earlier based on volume)
- **Assessment centre:** two online tests (numeracy, reasoning), then assessment centre; final meeting with the Head of Internal Audit
- **Requisition:** 1766C20085874415B92B6DA4AA83AA00
- **Official URL:** https://pearson.jobs/belfast-gbr/advanced-associate-internal-audit-controls-compliance-and-risk/1766C20085874415B92B6DA4AA83AA00/job/
- **Verified live:** 2026-10-03

## Clearance / citizenship filter

**PASS — no block.** No security clearance requirement, no citizenship or nationality condition, no UK-residency condition, and no driving licence requirement stated. Checked as the first step of intake per owner instruction 2026-10-03.

## Eligibility

- **Degree:** posting requires a recent graduate or 2027 graduate with a degree in Finance, Accounting, a closely related discipline **or a STEM subject**. Owner meets this via the STEM route: MSc Information Security, Royal Holloway (Merit, 2025) and BCA in computing, MIT-WPU (CGPA 9.17, 2024).
- **No prior accounting qualification required** — the posting states ACCA is funded and supported from day one.
- **Other criteria:** analytical, good problem-solver, careful with detail, clear communicator, curious and proactive, MS Office (Excel, Word, PowerPoint) — all evidenced in the canonical sources.
- Work-authorisation assessment recorded in the tracker manifest per owner instruction; not discussed here.

## Documents

- **CV:** `Mukund_Pearson_Audit_CV.pdf` — 9 layout-preserving edits via the canonical `cv_tailor.py`, one page, geometry unchanged (595.5 × 850.5 pt), 81 → 81 spans, every edit within ±15% character budget and within the master's widest-span width limit.
- **Cover letter:** `Mukund_Pearson_Audit_Cover_Letter.pdf` — 5 paragraphs via the canonical `build_cover.py`, one page, 2 links, no bad characters.
- `cover_spec.json` — replayable cover-letter spec.
- `cv_edits.json`, `cv_report.json` — replayable edit set and tailoring report.
- `cv_delivered.txt`, `cover.txt` — extracted text of the delivered documents (the artifacts that were gated).
- `cv_gate.json`, `cover_gate.json` — fact-gate output.

## Verification

| Check | Result |
|---|---|
| `cv_tailor.py` report | `ok: true`, `edits_applied: 9`, `problems: []` |
| Independent verifier (`verify_cv_tailoring.py`) | **PASS** — geometry, span positions, sizes, bounds, diff count, character profile, pixel bands |
| Pixel diff | 2.27% changed, 8 bands — every band maps to an edited element |
| Fact gate, delivered CV | `warn` — `built`, `achieved` only (both genuinely evidenced) |
| Fact gate, cover letter | `warn` — `advanced`, `built` only. `advanced` is Pearson's own job title in the heading; `built` is evidenced |
| Tracker | J45 appended, 45 data rows, `ok: true`, no duplicate URLs, headers unchanged, owner columns intact |
| Applied sheet | refreshed, Jobs sheet unchanged, `sheetnames[0]` still `Jobs` |

## Gap assessment (honest)

This is an internal audit role inside a finance-led function, and the owner's background is information security and IT support. The domain gap is real and is not papered over.

**Genuinely evidenced and used as the bridge:** operating controls and evidencing them — the access-request workflow (verify business approval, grant time-limited permissions, document the access period and extensions), weekly store-wide risk assessments, daily compliance checks, incident documentation and escalation, data analysis, Excel/Word/PowerPoint, and AI tool use with output validation.

**Not evidenced, and not claimed anywhere in the documents:** internal audit experience, ACCA or any accounting qualification, audit workpaper preparation, financial statement or financial process audit exposure, corporate governance and risk management coursework, RIBA or project management exposure, and formal presentation of findings to senior stakeholders.

The cover letter states plainly that reporting and stakeholder work is the area with most to build, rather than implying audit experience the owner does not have. The STEM degree route is explicitly permitted by the posting, and no prior accounting qualification is expected because ACCA is funded from day one — so the realistic gap is domain familiarity, not eligibility.

## Files

```
jd.txt                                    owner-supplied JD text
cv_master_2026-10-03.pdf                  master CV as sent by owner
Mukund_Pearson_Audit_CV.pdf               tailored CV
Mukund_Pearson_Audit_Cover_Letter.pdf     cover letter
cover_spec.json
cv_edits.json / cv_report.json
cv_delivered.txt / cover.txt              gated artifacts
cv_gate.json / cover_gate.json
tracker_manifest.json
```
