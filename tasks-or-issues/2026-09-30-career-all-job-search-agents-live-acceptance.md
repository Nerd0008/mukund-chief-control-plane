# Career Ops — all job-search agents live acceptance

Date: 2026-09-30
Owner intent: test every job-search/discovery agent end-to-end now that native Hermes/Discord is operational.

## Scope

This acceptance covers the discovery/search stack only:

- B01 Career Ops Manager / Chief integration
- B02 UK Job Search Agent
- B03 Dubai Job Search Agent
- B04 Japan Job Search Agent
- B05 Singapore Job Search Agent
- B06 Eligibility / role-policy filter
- B07 Shared dedupe-state manager
- B10 Company Watch
- B11 Recruiter / intermediary Watch
- B19 LinkedIn Job Discovery intake
- B24 Regional Scheduler / run-health monitor
- B25 High-recall semantic discovery funnel
- B26 Open-Web Research Agent

B08 tracker writer may be exercised only in dry-run/manifest mode. Do not write a canonical workbook.

Not in scope: CV tailoring, cover letters, application submission, LinkedIn posting/outreach, interview prep, inbox mutation, employer/recruiter contact.

## Safety / mutation rules

READ-ONLY acceptance.

Must remain zero for the entire run:
- applications submitted
- employer/recruiter contacts
- LinkedIn mutations
- canonical tracker/workbook writes
- Gmail mutations
- browser form submissions

Do not fabricate a PASS for a source that is unavailable. A source with no configured/live input must report UNAVAILABLE or NO_INPUT with its exact reason.

## Test plan

### 1. Chief -> Career Ops routing

Issue the test from Discord #chief while Hermes Gateway is connected.

Prove:
Discord -> native Hermes -> Chief -> Career Ops Manager.
Do not bypass Chief directly into a script.

### 2. Regional agents B02-B05

Run one bounded live/read-only discovery cycle for each:
- UK
- Dubai
- Japan
- Singapore

For each region report:
- worker invoked
- source classes attempted
- raw results seen
- URLs validated
- candidates accepted by regional eligibility
- candidates rejected + top rejection reasons
- duplicates removed
- candidate IDs/titles/companies for up to 3 accepted results
- zero canonical writes / zero applications

A zero-result region is not automatically FAIL. Distinguish:
source failure vs no accessible results vs validation rejection vs policy rejection vs dedupe.

### 3. B06 Eligibility

Exercise at least:
- one candidate that passes
- one candidate rejected for senior/experience mismatch
- one candidate rejected or flagged for location/work-authorisation uncertainty
- one clearance/citizenship requirement case if naturally observed or use an existing fixture

No invented owner facts.

### 4. B07 Dedupe

Feed at least one duplicate candidate observed across two discovery surfaces if available.
If live duplicate not naturally found, use an existing captured fixture.

Prove one canonical identity with provenance retained from both surfaces.

### 5. B10 Company Watch

Run bounded read-only company-watch discovery against the existing watchlist.
Report:
- companies checked
- ATS/career sources reached
- live vacancies found
- eligible candidates
- inaccessible/zero companies with reason

No outreach and no tracker write.

### 6. B11 Recruiter Watch

Exercise recruiter/intermediary discovery intake from its currently supported read-only input.
If there is no live producer/input, report NO_INPUT truthfully and run its fixture acceptance only.
Do not contact recruiters.

### 7. B19 LinkedIn Job Discovery

Use only the currently supported LinkedIn read-only input path.
Do not log in, scrape, post, connect, message, or apply.

If an owner export/input exists, exercise intake -> job_signal classification -> shared funnel.
If no current input exists, report NO_INPUT and run fixture acceptance.

### 8. B25 high-recall semantic funnel

Run a bounded end-to-end funnel over the live/captured candidates from this acceptance:
broad collection -> light title prefilter -> semantic triage -> deterministic eligibility -> dedupe -> manifest.

Report:
- discovered_raw
- title_pass / title_reject
- semantically_reviewed
- eligibility_pass
- duplicates_collapsed
- tracker_candidates/manifest candidates
- explicit zero-attribution reasons

No canonical workbook write.

### 9. B26 Open-Web Research

Run a small bounded live research test sufficient to prove the worker can reach public search result classes.
Target max:
- 1-2 queries per region
- up to 3 validated posting-shaped candidates per region

Report source classes actually reached (e.g. employer careers / ATS / LinkedIn Jobs / Indeed when available).
Reject search/listing pages as tracker candidates.

### 10. B24 scheduler/run-health

Read-only inspect:
- ChiefCareerScan-UK
- ChiefCareerScan-Dubai
- ChiefCareerScan-Japan
- ChiefCareerScan-Singapore

Report task state, last run, next run, and most recent regional run-health.

Do not alter schedules.

## Final verdict format

Return one table:

| Agent | Live/Fixture | Invocation | Result | Candidates/results | Blocker/notes |

Then totals:
- agents tested
- PASS
- PASS_WITH_LIMITATION
- NO_INPUT/UNAVAILABLE
- FAIL
- raw results
- validated postings
- accepted candidates
- duplicates collapsed
- provider/model calls by worker
- canonical workbook writes
- applications submitted
- external contacts/actions

Overall verdict:
- OPERATIONAL if every configured live search path works and unsupported/no-input surfaces are truthfully identified
- PARTIALLY_OPERATIONAL if one or more configured paths fail
- BLOCKED only if Career Ops cannot perform bounded discovery at all

Preserve evidence under a fresh audits/evidence timestamped directory. Do not change production code unless a reproducible defect is found; report defects before fixing them.
