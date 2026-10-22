# Vacancy verification root cause and recovery

The preceding change retained flagged UNKNOWN leads. This follow-up repairs their verification path.

## Reproduced causes

Of the saved 65 UNKNOWN acceptances, 54 were LinkedIn links; 52 were email /comm/jobs/view links. That notification route returned sign-in content or rate limiting. Fetching the canonical public /jobs/view URL for the same exact posting ID returned the JD, employer and location in controlled live tests. The newsletter parser required JobPosting JSON-LD and missed the public LinkedIn top card, so it often supplied no employer/location even when those facts were publicly readable.

The verifier had no targeted search step to recover the employer/ATS destination after an aggregator failed. It also retried the same source-order prefix under the newsletter validation cap, and did not back off a host after HTTP 429. An exact employer vacancy was falsely downgraded because its search-result title contained an employer-name + Jobs prefix.

## Changes

- application_links.py: canonicalize only recognized LinkedIn job ID routes; extract target employer/title/location without asserting OPEN; recognize navigable GET apply forms without executing POST forms; normalize documented search-title wrappers; identify additional aggregators as discovery sources.
- jd_fetcher.py: retrieve canonical public posting URL and carry separately attributed discovered metadata. Reading the JD or metadata alone still does not prove availability.
- discovery/gmail_discovery.py: use canonical posting URLs; retain public top-card metadata separately from validated JSON-LD; spend validation budget on unchecked links first, newest first within that group. Existing Gmail OAuth, scopes and mailbox state are unchanged.
- posting_resolution.py: use the existing observed Codex public-search provider to find the exact employer/ATS vacancy, then independently GET and verify it. Search snippets, copied metadata on another job board, different intake/seniority/location and multiple distinct matching requisitions cannot authorize replacement. Only a unique identity-matched OPEN destination can replace the original URL.
- discovery/pipeline.py and scheduled_orchestrator.py: connect that resolver to the normal production scheduled path; persist progress per region, prioritize unattempted lookups, and defer further host GETs after 429. Resolution errors remain bounded UNKNOWN results. Metadata flows through the existing region builder, gates, candidate manifest and writer.

Recovery is limited to four search calls and 180 elapsed seconds per regional run, with at most three destination GETs per query. It honors the scheduler's remaining deadline. Positive cached resolution expires after 15 minutes; failed lookups are not immediately repeated (one-hour minimum), and unattempted items have priority. The state lives under the existing ignored runtime/career-ops/discovery directory, not Git. A real access block is not bypassed or relabelled OPEN.

## Verified outcome

Three controlled live searches were observed by the existing provider. Two formerly UNKNOWN leads resolved to exact official/ATS postings and verified OPEN. One official destination remained UNKNOWN and was not promoted. A further fresh GET verification using those observed search leads passed employer/title/location, eligibility and canonical dedupe for both recovered postings: two distinct new row proposals, zero duplicates, zero tracker writes. This is not a claim that a full new market search was run or that every inaccessible job can now be verified.

425 focused tests passed, zero failed (resolver, exact identity, intake/seniority, ambiguous requisitions, copied job-board metadata, budgets, persisted progress, rate-limit backoff, end-to-end eligibility/dedupe, newsletter intake, deadlines, regional search, scheduled orchestration and writer). The earlier recorded unrelated baseline rollover/LinkedIn fixture failures were not redesigned in this change.

Private recovery, live details, before-source copies, test XML and final source hashes: C:/Users/mukun/Documents/Codex/verification-recovery-20261022. Committed evidence is aggregate only. Canonical workbook before/after SHA-256: 9340232290bc43b03cadfc0f2169fd33959d44bcc85dcdbb76bc0ee698ec4f36. No application submission, outreach, Gmail/Calendar mutation, CV changes, provider credential/config changes, main merge or unrelated dirty-file commit.
