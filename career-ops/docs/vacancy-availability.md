# Vacancy availability guard — 2026-10-18

Verified failure: the production reader returned HTTP 200 / validated_live / is_closed=false for L&G jid-6807 ("This vacancy has now expired") and PayPal Prosple cybersecurity-risk-intern-0 ("Opportunity expired"). Both were admitted by the search replay and remained in the daily digest. Existing rows were skipped before re-fetch; the digest sorted past deadlines last rather than withholding them.

Patch:
- Explicit expiry banners and JobPosting validThrough expiry, including timezone-qualified timestamps, take precedence over application controls or rolling wording.
- HTTP success is now fetch_state=fetched. Availability is a separate OPEN / CLOSED / UNKNOWN fact with evidence. Missing content, challenges, errors, generic landing pages and absent positive application controls stay UNKNOWN.
- Positive HTML evidence requires a target job heading and application control. Teamtailor's job-specific overlay must reference the same job ID. Known exact Greenhouse/Lever posting URLs may use one public read-only API fallback, bounded within the fetch timeout. Closed pages cannot be resurrected by a fallback.
- Direct search only hands positively verified OPEN candidates to the canonical writer. Unknown availability remains explicitly review-only in SEARCH_RECONCILIATION; it is not silently treated as expired or open.
- Discovery uses the same vacancy fact. A bot wall alone does not establish availability.
- Daily build_digest is network-free and lists only fresh OPEN evidence. It withholds closed/expired, missing, corrupt or stale evidence without deleting tracker rows. Both stored and newly verified past deadlines override cached OPEN. Found-date labels do not establish validity.
- Daily CLI refresh automatically performs public GET verification before formatting, default maximum 30 records / 60-second budget, per-request cap 8 seconds. --no-refresh reads only existing fresh evidence. Freshness lasts 15 minutes. Unchecked/oldest evidence is refreshed first so the first page cannot monopolise the bounded budget.
- Private evidence: LOCALAPPDATA/hermes/runtime/career-ops/vacancy-status.json. Updates use an exclusive lock plus atomic replacement; cache failure cannot authorize delivery. No credentials, emails or private profile facts are sent. No tracker or schedule changes.

Live acceptance: both concrete expired pages now classify CLOSED and are absent from the actual digest. Waterstons Graduate Security Consultant classifies OPEN from its exact Teamtailor application overlay and remains deliverable. Replaying these three responses through the actual direct-search dry-run admits one and rejects two. Canonical workbook SHA-256 is unchanged. Private evidence: Documents/Codex/expired-job-investigation/fixed-live-acceptance.json. No provider/model calls, Discord test messages, application submission, or recruiter outreach.

Regression: 247 tests across availability, guarded repair/writer, deadlines, search recall, regional search, liveness, digest and discovery. Fixtures now explicitly supply positive open-vacancy evidence and isolate every test cache in pytest temporary storage; old fixture-only jobs no longer get inferred OPEN from HTTP success. No live network is used by semantic-stage test fixtures.

Production scripts import the canonical source in new interpreter invocations. No Hermes gateway restart or cron change is required. Historical workbook rows remain intact; the guard changes recommendation/delivery eligibility, not owner application history. Fresh evidence is time-bounded and does not promise that an employer cannot close a job after a check.
