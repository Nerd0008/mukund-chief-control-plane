# Gmail job-alert discovery

Owner-authorized read-only newsletter discovery is separate from application reconciliation. `career_job_mail.py scan --days 30 --max-messages 150` performs bounded backfill using existing Credential Manager OAuth. No new scopes. No message mutations, application tracker writes, Calendar events, browsing, model calls or outreach.

The existing hourly approved monitor calls `compile_list` on its incremental messages before committing its checkpoint. Job-list IDs are deterministic URL hashes; repeated messages collapse while source IDs remain private. Interrupted persistence does not advance the mail checkpoint and replay is idempotent. A separate exclusive job-list lock prevents concurrent backfill/monitor writes.

Private outputs: `%LOCALAPPDATA%/hermes/runtime/career-ops/gmail-job-alerts/{jobs.json,job-list.md,summary.json}`. Raw bodies, credentials and query tokens are not persisted. Public job-ID query parameters are allowlisted; tracking redirects and unsubscribe links are excluded. Titles only come from explicit link labels; unknown employer/title remains review-needed. Postings are unverified, not accepted applications. This extraction cannot resolve every mail format or redirect-only alert; public-posting verification is a separate discovery step.

The first backfill may hit its message cap; it fails without partial output. Use a smaller time window to partition a larger mailbox. No new scheduled task or changes to existing cadence are needed.
