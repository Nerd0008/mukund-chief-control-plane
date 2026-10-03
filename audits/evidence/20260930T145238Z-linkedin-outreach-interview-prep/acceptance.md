# LinkedIn outreach + interview prep acceptance — 20260930T145238Z

Overall: PASS

## Checks

| check | result |
|---|---|
| stage1 canonical Career Ops sources are present | PASS |
| stage2 LinkedIn intake contract holds | PASS |
| stage3 outreach drafts exist for networking, recruiter and hiring manager | PASS |
| stage3 every outreach draft has an explicit unsent state | PASS |
| stage3 every outreach draft carries provenance to cv.md lines | PASS |
| stage3 the hiring-manager draft names the role ONLY from the Career Ops record | PASS |
| stage3 the install fact gate did not block the outreach drafts | PASS |
| stage3 no message was queued, no connection created, nothing sent | PASS |
| stage4 every external LinkedIn action is refused and unperformed | PASS |
| stage5 interview prep pack is structurally valid | PASS |
| stage5 technical + behavioural prep produced from the posting | PASS |
| stage5 likely-question list produced | PASS |
| stage5 cited research is carried, not guessed | PASS |
| stage5 at least one evidence-backed talking point exists | PASS |
| stage6 every talking-point quote is verbatim at its cv.md line | PASS |
| stage6 no candidate claim appears in generated text | PASS |
| stage6 no question claims to be employer-supplied | PASS |
| stage6 candidate_claims and external_actions_taken are empty | PASS |
| stage6 independent re-read of cv.md confirms every quote | PASS |
| stage6 a tampered quote is detected | PASS |
| stage6 an injected first-person claim is detected | PASS |
| stage6 a question claiming employer origin is rejected | PASS |
| stage7 a requirement with no canonical evidence becomes an owner action | PASS |
| stage7 the UAE fixture's eligibility stays unknown | PASS |
| stage7 no right-to-work position is invented for the owner | PASS |
| stage8 the same brief yields the same pack twice | PASS |
| stage9 no canonical Career Ops source changed | PASS |

## Path

1. LinkedIn intake: {'files': 3, 'signals': 10, 'job_signals': 6, 'company_signals': 4, 'unclassified': 3}
2. Outreach drafts: {'total': 8, 'profile': 1, 'post': 4, 'outreach': 3, 'outreach_networking': 1, 'outreach_recruiter': 1, 'outreach_hiring_manager': 1} (fact gate warn)
3. JobBrief: jb-20260930T145238Z-2105e710 (validation ok)
4. Interview prep pack: ip-20260930T145238Z-ebbf62da -> C:\Users\mukun\Documents\mukund-chief-control-plane\runtime\career-ops\interview-prep\acceptance\20260930T145238Z\interview-prep\interview_prep_pack.json
5. Counts: {"technical_prep": 13, "behavioural_prep": 7, "likely_questions": 23, "talking_points": 6, "talking_points_evidence_backed": 5, "talking_points_owner_input_required": 1, "questions_to_ask_employer": 1, "unknowns": 3, "source_lines_quoted": 9}

## Not performed

- Any contact with an employer, recruiter, agency or interviewer
- Any LinkedIn or other social-platform action
- Any application submission
- Any claim about the candidate that is not verbatim canonical source text with a source line
- Any invented interview question, interviewer name, panel format or interview process detail
- Any interactive browser, GUI application or network research call
- Any LinkedIn login, session use, API call or scraping performed by this workflow
- Any browser launch or GUI interaction
- Any automatic posting: publishing exists ONLY as the separate explicit owner-approved action in career-ops/linkedin_publish.py, and this workflow never posts
- Any messaging, connection request, reaction, follow or profile mutation
- Any application submission or employer/recruiter contact
