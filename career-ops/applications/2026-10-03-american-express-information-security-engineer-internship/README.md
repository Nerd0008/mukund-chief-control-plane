# Application package — American Express, Undergraduate Information Security Engineer Internship 2027 (Burgess Hill)

**Status:** Applied (recorded on owner standing instruction)
**Date applied:** 2026-10-03
**Tracker row:** `uk-cyber-job-tracker.xlsx` → Jobs → `J41`

## Vacancy

| Field | Value |
|---|---|
| Employer | American Express (AMEX Sussex House) |
| Role | Campus - Internship Programme - Undergraduate - Information Security Engineer - 2027 |
| Team | Enterprise Technology Services — Cybersecurity |
| Location | Burgess Hill, West Sussex, RH15 9AQ (Hybrid) |
| Salary | Competitive base salary (not published) |
| Contract | 10-week Summer Internship Programme |
| Posting date | 14/09/2026 |
| Apply before | 23/10/2026 |
| Job identification | 26013761 |
| Official URL | https://careers.americanexpress.com/en/sites/CX_1/job/26013761/ |
| ATS platform | Workday-hosted careers.americanexpress.com |
| URL verified live by Chief | 2026-10-03 |
| Conditions | Offer conditional on a background verification check |

## Fit assessment

**Strong mapping — the posting's responsibilities describe work already evidenced:**

- *Support secure network, endpoint, identity and access management activities* → daily Active
  Directory access requests with approval verification, time-limited permissions and documented
  access periods and extensions; endpoint support for 15 employees across 15–20 devices.
- *Security documentation, assessment findings, remediation tracking and reporting* → Co-op PIC
  weekly risk assessments, daily compliance checks, assessment records, incident documentation
  through internal reporting systems, corrective actions and escalation of unresolved risks.
- *Threat research and analysis* → phishing investigation at 4–5 emails per day checking sender and
  link domains for impersonation; MITRE ATT&CK mapping in InboxDefender.
- *AI-enabled tooling to support detection, triage and investigation, validating outputs before
  escalation* → InboxDefender uses an LLM with MITRE ATT&CK mappings, keeps sensitive email data
  local, and keeps every result for human validation before action.
- *Scripting and automation* → Python, PowerShell, SQL, API integration; 25+ detection patterns and
  150+ manual test cases at 93.7% accuracy in SafePaste.
- *Foundational knowledge of IAM, data privacy, data protection, secure development* → MSc modules
  in Security Management (ISO 27001), Critical Infrastructure Security, Secure Business
  Architectures, Digital Forensics and Network Security; ISO 27001 / Cyber Essentials / GDPR /
  NIST CSF familiarity.
- Certifications held: CompTIA Security+, ISC2 Certified in Cybersecurity (CC).

**Not evidenced — do not claim:** cloud security engineering, DevSecOps, secure coding review,
application security testing, vulnerability management tooling, SOC tooling (SIEM/EDR), Bash.

## Files in this package

| File | What it is |
|---|---|
| `jd.txt` | Job description text as supplied by the owner, 2026-10-03 |
| `cv_mukund_didwania_2026-10-03.pdf` | Base CV (byte-identical to the owner-designated base) |
| `cv.txt` | Extracted text of the base CV |
| `cv_edits.json` | The 7 layout-preserving edits, replayable |
| `cv_tailor_report.json` | `cv_tailor.py` gate report: 7 edits, 0 problems, all verifications true |
| `cv_tailored_amex.pdf` | Tailored CV (copy of the delivered file) |
| `cover_spec.json` | Spec consumed by `build_cover.py` |
| `cover_letter_amex.pdf` | Cover letter (copy of the delivered file) |
| `job_record.json` | Job record used to run `cv_workflow.py draft` |
| `tracker_manifest.json` | Manifest consumed by `career-ops/tracker_writer.py` |
| `preview/before.png`, `preview/after.png`, `preview/cover.png` | Rendered QA images |
| `README.md` | This file |

## Delivered files

- CV: `C:\Users\mukun\Downloads\codex\_CVs\Mukund_Didwania_AmericanExpress_Information_Security_Engineer_Intern_CV.pdf`
- Cover letter: `C:\Users\mukun\Downloads\codex\_cover\Mukund_Didwania_AmericanExpress_Information_Security_Engineer_Intern_Cover_Letter.pdf`

## Format verification (independently re-checked)

- Page count 1 → 1; page geometry 595.5 × 850.5 pt identical.
- Spans 81 → 81 (89 with whitespace/continuation spans); `untouched_spans_unchanged: true`,
  `all_replacements_present: true`, `moved: []`, `missing: []`.
- Independent span-level diff: exactly **14 changed lines = the 7 edits**.
- Positional drift between master and output spans: **none**.
- Non-ASCII census identical (NBSP ×4, en dash, bullet); no soft hyphens, no U+037E.
- Character budget per element: −11.0% to +13.0% (all within ±15%); every line inside its box.
- Both rendered pages visually inspected: no overflow, overlap, clipping or section shift.

## Fact gate

- CV: `{"verdict":"warn","invented":[],"unsupportedFacts":[],"forbidden":[]}`
- Cover letter: `{"verdict":"warn","invented":[],"unsupportedFacts":[],"forbidden":[]}`

The first cover-letter draft was **blocked** by the gate: the tool extractor read
`using Python, the Gmail API and an LLM, ... and every output left` as a single tool claim of
`every output left`. The sentence was reworded to remove the `using …` trigger, the letter was
rebuilt, and the gate then passed. The block was fixed in the text, not worked around.

## Provenance

- JD text supplied by the owner via Discord on 2026-10-03.
- Official Workday URL located by Chief and verified live: Job Identification 26013761,
  posting date 14/09/2026, Apply Before 23/10/2026.
- CV tailored with `career-ops/cv_tailor.py` (canonical gated path). Cover letter built with
  `career-ops/build_cover.py` (format-locked, spec-driven).
- No application was submitted, and no employer or recruiter was contacted.
