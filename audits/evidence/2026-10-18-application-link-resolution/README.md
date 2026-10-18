# Original application-link resolution

The former checker recognised a narrow set of literal Apply anchor labels. It did not follow aggregator outbound links, preserve HTTP redirect destinations, read job-bound application fragments, or verify Workday requisitions. Therefore a missing recognised button was reported as UNKNOWN even when an original employer route was in the page. UNKNOWN never establishes that a job is open or expired.

## Change

`application_links.py` extracts target-specific application anchors (including Apply for job / Apply on employer site), ignores navigation/recommendations and category pages, and retains source-to-destination provenance. `jd_fetcher.py` follows at most two outbound hops within its existing elapsed request budget. It requires employer and title/intake agreement and positive destination availability; expiry still takes precedence. Workday verification requires the exact requisition plus posted=true and canApply=true. A declared employer application fragment is recognised only when its form is bound to the exact structured posting ID. GET only: the form action is never submitted. Structured JobPosting descriptions are retained for clearance/eligibility checks.

Direct search, discovery-to-writer records, and daily delivery use verified original posting URLs. Resolved destinations are deduplicated against current tracker URLs and within the run. Candidate semantic IDs retain the source identity. Source transport flags are superseded only by a positively verified exact destination; category results and other eligibility gates still block. Search instructions now require original individual vacancy URLs where retrievable and prohibit cross-associating adjacent listings.

## Live results: 2026-10-18

- Barclays: original Workday requisition JR-0000129173 verified posted/applicable; deadline 2026-11-01.
- Addleshaw Goddard: original employer vacancy verified with job-bound application fragment.
- Actica Consulting: original Pinpoint vacancy verified with matching title and application control. Availability is separate from eligibility.
- American Express: original Oracle requisition 26013778 found; availability remains UNKNOWN from the JavaScript shell. Direct-search title policy separately rejects this title for lacking an explicit entry-level marker; that policy was not widened in this change.
- Deloitte: blank hrefs in public HTML; browser Apply opens Bright Network sign-up. No account creation or credentials were entered.
- Equilibrium: employer page readable with production headers, but no identifiable application control. UNKNOWN retained.
- HP: supplied URL is a category page, not a posting. The Information Security Engineer entry belongs to American Express; HP's entry is a different role. No guessed replacement.

## Validation

283 passed, 0 failed across application links, availability, tracker repair/writer, deadlines, search recall/liveness, regional search, daily links and discovery pipeline (36 resolver tests). Production replay of the seven reported leads used a stubbed discovery result set but actual public HTTP verification and the normal canonical-tracker read/dedupe path: 2 already tracked, 3 review-only, 1 proposed new candidate, 1 title rejection. This replay is not a fresh market search. No model calls, tracker writes or application submissions. Workbook before/after SHA-256 identical; details in verification.json.

## Remaining limits

This adds bounded HTTP/ATS resolution, not a universal browser/login resolver. JavaScript-only and membership-gated destinations remain UNKNOWN. No availability threshold was lowered, no CAPTCHA/authentication was bypassed, and no unverified rows were added.

## Scope

Feature branch only. No main merge; no Gmail, Calendar, LinkedIn, CV, provider or scheduled-task changes. Raw HTML, temporary probes, runtime cache and private recovery copies are excluded from this evidence.
