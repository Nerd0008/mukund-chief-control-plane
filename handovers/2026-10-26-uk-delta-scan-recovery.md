# Recurring UK delta scan recovery — 26 October 2026

Branch: `fix/e3-whole-repo-architecture`. No main merge.

## Verified failure chain

Cron `5a66e1129e58` runs the existing Hermes Python launcher `hermes/scripts/career_job_scan_delta.py`, which invokes canonical `career-ops/job_scan_delta.py`. The launcher returned code 3 because its search child returned code 2. The public posting URL shown in the notification was an arbitrary stdout tail, not the error cause.

The four saved failures were inspected separately:

- 04:24: both attempted batches completed their search coverage; the writer reported lock/access-denied markers. This is distinct from routing failure. No workbook lock file was present during final investigation.
- 06:36: the second batch contained a router CLI failure, so coverage was incomplete.
- 08:42: two of six query authorizations timed out.
- 10:48: four of six query authorizations timed out; two queries completed. Router receipts recorded approximately 45.3 seconds, `TIMEOUT`, exit -1. No raw provider bodies or credentials were copied into this evidence.

The exact upstream reason a historical CLI process stopped responding cannot be recovered from these sanitized receipts. A fresh router-only probe for a failed public query passed in 9.532 seconds. No claim is made that the provider was persistently down or that future upstream outages are impossible. Process metadata did not establish current orphaned search workers; no owner process was killed.

The workflow amplified transient failures: every query requested another brain decision for the same sole permitted search worker; successful query progress was discarded with an incomplete batch; the cursor correctly remained on that batch, causing the next cycle to repeat successful work; failure copy hid the category behind a raw JSON tail.

## Repairs

- One router-brain decision authorizes an exact bounded batch. The scope binds query membership, executable, model, sandbox, working directory and elapsed-time deadline. Out-of-scope work fails closed. Standalone calls still require authorization. No worker/provider/model configuration changed.
- Every requested query still requires its own observed web-search evidence. An authorization is not evidence that a query executed.
- Successful query results/receipts are privately retained with a prompt/model signature, original observation timestamps and six-hour expiry. Retries rerun missing/failed queries; stale, future-dated, malformed, mismatched and unobserved progress is rejected. Reusing evidence never refreshes its age and never authorizes tracker writes.
- A routing block stops further worker attempts in that batch. Zero observed successes retain the previous RuntimeError contract, now with structured incomplete-coverage evidence for diagnostics.
- Incomplete coverage still blocks writes and cursor advancement. Retrieved candidates are revalidated through the existing deadline, eligibility, canonical dedupe and guarded writer before any delivery. Completed progress is cleared only on successful normal completion. Dry runs never persist or clear it.
- Cron failures report query completion and safe error categories instead of the last 400 characters of provider output. Historical failure counters were not falsified/reset, and the schedule was not paused.

## Additional independently reproduced regression boundaries

The broad combined suite revealed an existing test isolation defect: a temporary-workbook test read four real pending candidates from owner retry state, causing an extra real employer in its fixture rows. Direct-search state is now isolated per test, preventing production retry state from being consumed or deleted by tests.

The same broad run exposed nine image protocol/content-stop test failures from `ctypes.ArgumentError`: Gemini and DeepSeek helpers used `ctypes.windll.advapi32`, whose cached `CredReadW` function shares mutable argument types. Each helper declares a distinct CREDENTIAL structure, so import order could replace another helper's pointer signature. Each now owns an independent WinDLL function object. Regression coverage mutates a foreign shared prototype and verifies neither helper changes, without reading any credential. Keys, scopes, provider selection, HTTP endpoints and account configuration are unchanged.

## Validation evidence

- Initial focused search/recovery/boundary suite: 184 passed.
- Follow-up exact-failure and compatibility suite: 161 passed.
- One live canonical production-path acceptance: `job_scan_delta.py --dry-run --max-batches 1 --timeout 480 --budget-seconds 1000`, exit 0, 259.45 seconds. No newly reportable roles. Success required complete query coverage.
- Canonical UK workbook, scan cursor and delivery ledger hashes unchanged across live acceptance; no query-progress files created. No application, outreach, Gmail mutation or Calendar action.
- Private captures and recovery patches: `Documents/Codex/job-scan-repair-20261026`. No private scan transcripts, job lists or credential material are committed.
- Final combined regression: **2,327 passed, 0 failed**, 253.91 seconds. Seventeen existing warnings (Pillow deprecation and a helper-class collection warning).
- Cron remains enabled every 120 minutes; next scheduled occurrence recorded as 2026-10-26 12:48:38 UTC (London). Historical error status was not reset.
- Runtime-copy activation of the two independently reproduced credential ABI fixes is recorded after deployment; the search cron already invokes canonical repository source directly.
