# Telent — Graduate Network Engineer (Farnborough)

**Applied:** 2026-10-03 · **Tracker row:** J44 · **Status:** Applied · **Priority:** High · **Fit:** 6.5/10

## Posting

- **Company:** Telent Technology Services Ltd, part of M Group
- **Role:** Graduate Network Engineer
- **Location:** Farnborough (Telecom division)
- **Salary:** £29,000 per annum plus benefits
- **Closing date:** 30 October 2026
- **Official URL:** https://jobs.mgroupltd.com/vacancies/49768/graduate-network-engineer.html
- **Verified live:** 2026-10-03
- **Programme:** two-year graduate programme, six-month rotations, mentorship toward IET accreditation

## Provenance

Owner-supplied JD text via Discord 2026-10-03. The official M Group vacancies board URL was located by Chief and verified live the same day (requisition 49768).

Locating it required driving the site's ASP.NET postback search form: the M Group board ignores query-string keyword parameters entirely (`?Keywords=`, `?q=`, `?SearchTerm=` all return the unfiltered 455-vacancy list). The search must be submitted through the form's `ctl00_ContentContainer_TopSearch_btnSearch` control. Recorded here because it will recur on every M Group subsidiary posting.

## Eligibility

- **Degree:** posting requires a minimum 2:2 Honours Degree in a relevant STEM subject, achieved within the last two years. Owner meets this: MSc Information Security, Royal Holloway (Merit, September 2025) and BCA in computing, MIT-WPU (CGPA 9.17, September 2024) — both STEM, both inside the two-year window.
- **Clearance:** none stated.
- **Other criteria:** strong organisational skills, communication and team working, self-motivation, practical Microsoft Office use — all evidenced in the canonical sources.
- Work-authorisation assessment recorded in the tracker manifest per owner instruction; not discussed here.

## Documents

- **CV:** `Mukund_Didwania_Telent_Graduate_Network_Engineer_CV.pdf` — 7 layout-preserving edits via the canonical `cv_tailor.py`, one page, geometry unchanged (595.5 × 850.5 pt), 81 → 81 spans, all edits within ±15% character budget.
- **Cover letter:** `Mukund_Didwania_Telent_Graduate_Network_Engineer_Cover_Letter.pdf` — 5 paragraphs via the canonical `build_cover.py`, one page, 2 links, no bad characters.
- `cover_spec.json` — replayable cover-letter spec.
- `cv_delivered.txt`, `cover.txt` — extracted text of the delivered documents (the artifacts that were gated).
- `cv_gate.json`, `cover_gate.json` — fact-gate output.

## Verification

| Check | Result |
|---|---|
| `cv_tailor.py` report | `ok: true`, `edits_applied: 7`, `problems: []` |
| Independent verifier (`verify_cv_tailoring.py`) | **PASS** — geometry, span positions, sizes, bounds, diff count, character profile, pixel bands |
| Pixel diff | 1.60% changed, 6 bands — every band maps to an edited element |
| Fact gate, delivered CV | `warn` — `built`, `achieved` only (both genuinely evidenced in canonical sources) |
| Fact gate, cover letter | `pass` |
| Tracker | J44 appended, 44 data rows, `ok: true`, no duplicate URLs, headers unchanged |
| Applied sheet | refreshed, Jobs sheet unchanged, `sheetnames[0]` still `Jobs` |

## Gap assessment (honest)

The role is operational network and infrastructure engineering. The owner's nearest genuine evidence is IT support with network-adjacent duties — network and website-access controls, server health monitoring, access requests through on-premises Active Directory, endpoint troubleshooting — plus security fundamentals from the MSc and his certifications.

**Not evidenced, and not claimed anywhere in the documents:** enterprise routing and switching configuration (Cisco/Juniper), CCNA or equivalent networking certification, firewall administration, cloud networking deployment (AWS/Azure), network automation tooling (Ansible/Terraform), IET accreditation progress.

The CV and cover letter therefore lead on troubleshooting method, security-aware reasoning and documented operational support rather than implying configuration depth. The MSc module list (Network Security, Critical Infrastructure Security) is real and is used as supporting context, not as a substitute for hands-on networking.

## Files

```
jd.txt                                            owner-supplied JD text
jd source                                         doc_1ba9d7546bc2_message.txt
cv_mukund_didwania_2026-10-03.pdf                 master CV as sent by owner
cv.txt                                            extracted master CV text
Mukund_Didwania_Telent_Graduate_Network_Engineer_CV.pdf
Mukund_Didwania_Telent_Graduate_Network_Engineer_Cover_Letter.pdf
cover_spec.json
cv_delivered.txt / cover.txt                      gated artifacts
cv_gate.json / cover_gate.json
tracker_manifest.json
```
