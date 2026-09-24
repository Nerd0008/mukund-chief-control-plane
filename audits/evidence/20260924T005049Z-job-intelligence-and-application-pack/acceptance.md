# Job intelligence + application pack acceptance — 20260924T005049Z

Overall: PASS  |  checks 42/42

## Path

1. Job record (synthetic-fixture-job-record): Information Security Analyst @ Crown Agents Bank
2. JobBrief jb-20260924T005049Z-2105e710: {'requirements_essential': 5, 'requirements_desirable': 4, 'responsibilities': 8, 'eligibility': 1, 'keywords': 40, 'source_supported_facts': 18}
3. Research: research_needed without a provider; provided with a cited provider; 1 uncited fact rejected
4. Handoff: 18 source-supported lines, all posting-verbatim
5. CV draft: C:\Users\mukun\Documents\mukund-chief-control-plane\runtime\career-ops\job-intelligence\acceptance\20260924T005049Z\cv-drafts\cv_draft.md
6. Cover letter: C:\Users\mukun\Documents\mukund-chief-control-plane\runtime\career-ops\job-intelligence\acceptance\20260924T005049Z\cv-drafts\cover_letter_draft.html
7. Reviewer verdict: pass_with_owner_input_required (essential coverage 0.6)
8. Reviewer on a tampered pack: block — cv_draft_not_verbatim, cover_letter_free_text, candidate_claim_not_canonical
9. Submission gate: awaiting_owner_approval without approval; approved_pending_owner_manual_submission with a valid external approval; external_action_performed=False
10. Canonical sources and trackers untouched

## Checks

| check | result |
|---|---|
| stage1 node + install fact gate available | PASS |
| stage1 all canonical sources present | PASS |
| stage2 job record resolved into the pipeline | PASS |
| stage3 JobBrief validates against the committed schema | PASS |
| stage3 JobBrief carries no candidate claim | PASS |
| stage3 every extracted line is a verbatim posting line at its cited line number | PASS |
| stage3 desirable posting lines became preferences, never essential requirements | PASS |
| stage3 essential requirements extracted from the fixture posting | PASS |
| stage3 no company fact is asserted without research | PASS |
| stage3 research request list recorded | PASS |
| stage3 JobBrief made no external action | PASS |
| stage3b a region the owner has not stated is 'unknown', not satisfied | PASS |
| stage3b the unknown eligibility produces a blocker risk | PASS |
| stage4 with no provider the brief records research_needed and invents nothing | PASS |
| stage4 a cited provider file yields cited facts | PASS |
| stage4 an uncited fact is rejected and never used | PASS |
| stage4 browser research provider is disabled (owner GUI-safety directive) | PASS |
| stage4 --allow-network without an enabled provider fetches nothing | PASS |
| stage5 every handoff line is verbatim posting text | PASS |
| stage5 the pack brief carries cited company research | PASS |
| stage6 CV + cover-letter drafts produced through the existing workflow | PASS |
| stage6 install fact gate did not block either artifact | PASS |
| stage6 rendered cover-letter HTML exists | PASS |
| stage6 the draft workflow performed no external action | PASS |
| stage7 reviewer did not block an honest pack | PASS |
| stage7 reviewer verified truthfulness | PASS |
| stage7 reviewer found no truthfulness/consistency/formatting blocker | PASS |
| stage7 reviewer reported essential coverage numbers | PASS |
| stage7 reviewer re-checked every posting citation and found no drift | PASS |
| stage7 reviewer surfaced unresolved unknowns to the owner | PASS |
| stage7 reviewer performed no external action | PASS |
| stage8 reviewer blocks a tampered pack | PASS |
| stage8 reviewer detected the invented CV line | PASS |
| stage8 reviewer detected the invented first-person claim | PASS |
| stage9 without owner approval the gate waits and performs nothing | PASS |
| stage9 the gate refuses every external action | PASS |
| stage9 an approval placed inside the repository is refused | PASS |
| stage9 an approval bound to a different pack is refused | PASS |
| stage9 a valid external approval still performs no external action | PASS |
| stage9 an approval for a changed pack is refused | PASS |
| stage9 the gate refuses when truthfulness is not verified | PASS |
| stage10 canonical Career Ops sources untouched | PASS |

## Not performed

- Any interactive browser, GUI application or Windows Search launch
- Any employer, recruiter or candidate-facing message
- Any application submission
- Any claim about the candidate that is not present verbatim in a canonical source
