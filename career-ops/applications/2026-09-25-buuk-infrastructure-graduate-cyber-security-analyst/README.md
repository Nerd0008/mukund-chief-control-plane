# Application package — BUUK Infrastructure, Graduate Cyber Security Analyst

**Status:** Applied (recorded on owner instruction)
**Date applied:** 2026-09-25
**Tracker row:** `uk-cyber-job-tracker.xlsx` → Jobs → `J35`

## Vacancy

| Field | Value |
|---|---|
| Employer | BUUK Infrastructure (BUUK Group / GTC) |
| Role | Graduate Cyber Security Analyst |
| Team | ICT – Information Security, reporting to the Information Security Manager |
| Location | Woolpit, Suffolk (head office); Bury St Edmunds. Travel between company locations may be required. Hybrid for eligible roles. |
| Salary | £33,270 |
| Contract | Permanent |
| Posting end date | 09/10/2026 |
| Official URL | https://careers.bu-uk.co.uk/job/Graduate-Cyber-Security-Analyst/1523-en_GB |
| ATS platform | careers.bu-uk.co.uk (jobs2web) |
| URL verified live by Chief | 2026-09-25 |

## Process

Three-stage: telephone interview → Assessment Centre → final stage.
The only currently scheduled Assessment Centre is **Thursday 3 December 2026** at the
Woolpit, Suffolk head office.

## Eligibility assessment (Chief, 2026-09-25)

- No sponsorship, security clearance, citizenship or UK-residency requirement is stated.
- Graduate visa (Mukund) valid to 23 Dec 2027 — covers the role term; the employer does
  not address future sponsorship.
- Degree requirement is a relevant bachelor's degree **or equivalent qualification with
  demonstrable interest**; Mukund holds an MSc Information Security (Merit).
- The JD states explicitly: **"No previous full-time cyber security experience is required."**
- Two of the listed desirable certifications are already held: CompTIA Security+ and
  ISC2 Certified in Cybersecurity (CC).
- Weighted towards governance, risk, compliance, privacy, ISO 27001 evidence and
  data-protection work — the branch of security with the strongest existing evidence base.
- Key gap (desirable-only): evidenced Microsoft 365 / Azure / Microsoft Sentinel /
  Defender / Entra ID exposure.

## Files in this package

| File | What it is |
|---|---|
| `jd_buuk_graduate_cyber_security_analyst.pdf` | Job description as supplied by the owner, 2026-09-25 |
| `jd.txt` | Extracted text of the JD |
| `cv_mukund_didwania_2026-09-25.pdf` | CV as supplied by the owner, 2026-09-25 |
| `cv.txt` | Extracted text of the CV |
| `tracker_manifest.json` | Manifest consumed by `career-ops/tracker_writer.py` |
| `README.md` | This file |

## Provenance

- JD and CV supplied by the owner via Discord on 2026-09-25.
- Row appended with `career-ops/career_ops_cli.py write --region uk --apply`
  (hash-verified backup, re-open verification, cross-month dedupe: 154 keys checked).
- Owner columns (J/K/S/T/U/V) written with `career-ops/application_state.py --apply`
  on explicit owner instruction, with backup and re-open verification.

## Owner instruction recorded 2026-09-25

> "for every cv generated and JD given consider the job applied and maintain an excel
> tracker with relevant details including the date applied."

Standing rule: whenever the owner supplies a CV and a JD together, the role is recorded
as **Applied** in the canonical regional tracker with the date of supply as the date
applied, and the CV + JD are archived in a package directory under `career-ops/applications/`.

## CV tailoring (2026-09-25)

Owner instruction: *"change what you need in the CV, it's the master CV which you can change
based on JD but maintain format exactly as this to the same pixels and character count
similar where it doesn't affect any spacing or format issues."*

Applied the established redact-and-retypeset method (`career-ops/cv_tailor.py`) rather than
regenerating the CV from HTML, because the master is a fixed-geometry document: A4
595.5 x 850.5 pt, Times New Roman throughout, every line on an absolute baseline.

**Nine text elements changed, all in place — no element moved, no line re-wrapped into a
different structure.**

| # | Element | Change |
|---|---|---|
| 1-3 | Professional Summary | Re-targeted from "seeking a cybersecurity internship" to a graduate cyber security analyst role; now leads on security operations, alert investigation, governance, risk and data protection |
| 4 | Security Analysis | "Phishing analysis, ..." -> "Alert triage, phishing analysis, Windows Event Logs, MITRE ATT&CK" |
| 5 | Systems & Support | "endpoint configuration" -> "Active Directory, account administration" |
| 6 | Skills label | "Framework Familiarity:" -> "Governance & Privacy:" |
| 7 | Framework list | "ISO27001, Cyber Essentials, GDPR, NIST CSF" -> "ISO 27001, UK GDPR, NIST CSF, Cyber Essentials" |
| 8 | Communication & Support | leads with "Documentation", adds "policy compliance" |
| 9 | Colourful Aura bullet 2 | leads with "Triage and investigate" |

**Verification (report: `cv_tailor_report.json`)**

- All 9 edits within the +/-15% character budget and within the measured rendered width of
  each line (script refuses to write otherwise).
- 72 untouched spans: all re-read after the write, identical in text, position, font and size.
- Page geometry unchanged: 595.5 x 850.5 pt, 1 page, 81 -> 81 spans.
- Pixel diff against the master at 150 dpi: **2.077% of page pixels differ**, and every
  changed band maps to an edited line (summary y 74-110, skills y 131-151 and y 176-197,
  bullet y 359-368). Nothing else on the page moved.
- Non-breaking spaces: 4 before, 4 after (parity with the master; inserted text was CMap-
  normalised so no new U+00A0 entered the document).
- Fonts: the two inserted Times New Roman fonts arrive whole (~640 KB each); subsetting them
  takes the file from 1,502,681 to 230,032 bytes with a **zero-pixel-difference** render,
  text unchanged.

**Outputs**

- `cv_tailored_buuk.pdf` (this package)
- `C:\Users\mukun\Downloads\codex\_CVs\Mukund_Didwania_BUUK_Infrastructure_Graduate_Cyber_Security_Analyst_CV.pdf`
- `cv_edits.json` — the edit specification, replayable
- `preview/before.png`, `preview/after.png`, `preview/side_by_side.png`, `preview/diff_mask.png`
- `cv_tailor_report.json` — measurements, verification, provenance

