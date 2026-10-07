# Hourly Gmail Career Ops activation — 2026-10-07

Owner approval enables only the existing Career Ops Gmail automation. Gmail is read-only, Calendar uses owned-event scope, and matching/deadline rules are unchanged.

Task `ChiefCareerGmailMonitor` is enabled under `MISTY\mukun` using an interactive token (owner SID verified; not SYSTEM). Action:

```
C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
"C:\Users\mukun\Documents\mukund-chief-control-plane\career-ops\career_mail_monitor.py" scan --apply
```

Working directory is the canonical repository. Hourly trigger `PT1H`, owner-logon trigger, `StartWhenAvailable`, and `IgnoreNew` overlapping-instance policy are installed. The normal exclusive scan lock remains. Recoverable scan exceptions release the lock and do not advance the checkpoint; Task Scheduler does not spawn retry loops. Missed executions resume when the owner session/laptop is available.

Fresh dry-run approval ID: `8ea70b89b478e7e16e4a66eb1969e5352b8a55ca115854da79e16162110dec58`. OAuth readiness, canonical fingerprints, 20 historical duplicates and 45 historical review holds were verified before calling the existing `enable-writes --approve-report` command.

Activation found concrete apply guard gaps. The initial apply now uses the already hash-verified baseline rather than unnecessarily repeating the whole backfill. Automatic writes filter out uncertain/unconfirmed proposals, check canonical fingerprint drift before applying, and retain review records in a private durable queue. Historical review holds cannot be promoted automatically. No classification/deadline threshold was relaxed. Explicit `--baseline-report` remains dry-run-only. The normal CLI remains dry by default; only this approved task passes `--apply`.

Exactly one scheduled acceptance was triggered. Task Scheduler returned 0; task is Ready/enabled. First run: 2026-10-07 21:49:31 BST. Next run at verification: 22:49:30 BST. Incremental scan inspected 30 messages: 9 recruitment signals, 1 existing match, 21 ignored, 0 new application rows. One authorised existing-record metadata update occurred; Calendar writes 0, Gmail mutations 0, model calls 0. Existing three REVIEW events remain present; no duplicate rows/events were created.

Checkpoint previously absent; completed apply committed history cursor `1022094` and 9 processed recruitment message IDs. All 20 historically authorised signals still deduplicate to zero repeat writes. The 45 historical review-only signals plus 8 new signals are held privately (53 total). Snapshot dependency remains removed.

Safety validation: 779 Career Ops tests passed, 0 failed, including six activation tests covering review-only exclusions, confident existing updates, concurrent drift, verified baseline, failure/checkpoint behavior and permanent historical review holds. Detailed mailbox/application evidence, approvals, receipts and checkpoint stay local under the private Gmail monitor runtime directory. Only aggregate activation evidence is committed.

No main merge, applications, outreach, LinkedIn publishing, or Gmail mutation occurred.
