# CV/cover-letter + LinkedIn acceptance — 20260930T144557Z

Region: uk  |  Overall: PASS

## Checks

| check | result |
|---|---|
| stage1 node + install fact gate available | PASS |
| stage2 job record resolved from Career Ops state | PASS |
| stage3 CV/cover-letter drafts produced | PASS |
| stage3 every CV draft line is verbatim canonical text | PASS |
| stage3 install fact gate did not block | PASS |
| stage3 cover letter rendered by the install's own renderer | PASS |
| stage4 LinkedIn intake read-only contract holds | PASS |
| stage4 signals classified from fixtures | PASS |
| stage5 canonical tracker untouched by dedupe | PASS |
| stage5 LinkedIn jobs deduped against Career Ops + Company Watch | PASS |
| stage5 a same-posting LinkedIn duplicate was detected and merged | PASS |
| stage6 LinkedIn drafts produced and fact-gated | PASS |
| stage6 every LinkedIn draft is unsent | PASS |
| stage6 no post/send performed | PASS |
| stage7 every external LinkedIn action refused and unperformed | PASS |
| stage7 a read/draft action is not blocked | PASS |
| stage8 dry-run handoff did not touch the canonical tracker | PASS |
| stage8 handoff applied to the TEST COPY | PASS |
| stage8 canonical tracker untouched by the applied handoff | PASS |
| stage8 LinkedIn provenance recorded in a non-owner column | PASS |
| stage9 a LinkedIn posting already written is deduped on replay | PASS |
| stage9b rollback restores the pre-write copy | PASS |
| stage10 Chief summary produced | PASS |

## Path

1. Job record from Career Ops (career-ops-pipeline.md): Information Security Analyst @ Crown Agents Bank
2. CV draft: C:\Users\mukun\Documents\mukund-chief-control-plane\runtime\linkedin\acceptance\20260930T144557Z\cv-drafts\cv_draft.md
3. Cover-letter draft (install renderer): C:\Users\mukun\Documents\mukund-chief-control-plane\runtime\linkedin\acceptance\20260930T144557Z\cv-drafts\cover_letter_draft.html
4. Career Ops fact gate: {'cv_draft': 'warn', 'cover_letter': 'pass'}
5. LinkedIn intake: {'files': 3, 'signals': 10, 'job_signals': 6, 'company_signals': 4, 'unclassified': 3}
6. Dedupe: {'job_signals': 3, 'company_signals': 4, 'new': 3, 'duplicates': 0, 'blocked_by_owner_filter': 2}
7. LinkedIn drafts: {'total': 7, 'profile': 1, 'post': 4, 'outreach': 2, 'outreach_networking': 1, 'outreach_recruiter': 1, 'outreach_hiring_manager': 0} (gate warn)
8. Handoff to a workbook COPY: applied=True, counts={'input': 1, 'appended': 1, 'duplicates': 0, 'rejected': 0, 'refreshed': 0}
9. Canonical tracker untouched: True

## Not performed

- Any LinkedIn login, session use, API call or scraping performed by this workflow
- Any browser launch or GUI interaction
- Any automatic posting: publishing exists ONLY as the separate explicit owner-approved action in career-ops/linkedin_publish.py, and this workflow never posts
- Any messaging, connection request, reaction, follow or profile mutation
- Any application submission or employer/recruiter contact
- PDF rendering (the install's generate-pdf.mjs launches headless Chromium; not run by this workflow)
- LLM CV tailoring via openai-tailor.mjs (sends cv.md + the job description to a third-party endpoint; owner-gated and requires a provider key)
- Application submission, employer/recruiter contact, or any external message
