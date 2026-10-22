# Career search audit repair — 22 October 2026

Scope: the twenty search defects from the read-only audit, on `fix/e3-whole-repo-architecture`. No main merge, application submission, outreach, canonical workbook repair, or credential/provider configuration change.

## Production paths

- Hermes direct search: `codex_entry_level_search.py` → observed Codex web-search events → shared JD fetcher / `PostingResolver` → shared deterministic gates → canonical writer dry reconciliation → guarded writer.
- UK scheduled search: `run_scheduled_scan.cmd` → `discovery/scheduled_orchestrator.py` → the same verification/gates/writer reconciliation → `promote_manifest.py`, bound to that exact scan report → guarded writer.
- Nightly: `nightly_career_run.py` → scheduled orchestrator `run-all` → exact stdout region/run IDs → fresh matching region manifests → guarded writer.

No alternate XLSX append implementation was added. Owner-confirmed fields, six-column UK schema, deleted-row protection, verified backups, workbook fingerprints and exclusive writer locks remain authoritative.

## Audit closure matrix

| Audit | Defect | Repair / proof |
|---|---|---|
| 1 | Actual batch pinned to zero | `select_batches` executes exactly the logged modulo offset; offsets and wrap-around tested. |
| 2 | Narrow repeated query coverage | Add four ATS batch families; all profile disciplines retained. Site-scoped batches exercised live. Scheduled matrix includes additional ATS and an additive recent-posting query. Rolling/older active posts remain eligible. |
| 3 | Recovery absent from direct path | Both entrypoints construct the existing `PostingResolver`; shared fetcher, identity and host backoff used. |
| 4 | Worker errors look like empty success | Nonzero/error/unobserved execution raises failure; no successful cursor advance or empty-market claim. |
| 5 | No proof of live search | Consume structured web_search events through the existing research provider; model recall alone is rejected. |
| 6 | Smaller arrays lost | Both worker and direct parser combine result arrays; malformed/empty responses distinguished from an observed empty search. |
| 7 | Neutral supported titles rejected early | Analyst/technician/support/security-engineer titles reach JD screening. Discipline, seniority, region and experience still decide eligibility. |
| 8 | Optional/one-year experience blocked | Context on either side of requirement recognized; mandatory multi-year requirements still fail. |
| 9 | Premature “new” claims | Every direct dry run probes canonical writer first; discovered, eligible, duplicate and proposed-new counts separate. |
| 10 | Distinct requisitions collapsed by title | Same-title applications with independently known distinct requisitions survive; unknown identity still conservatively dedupes. Private-copy writer tests prove repeat idempotence. |
| 11 | No successful search cursor | Atomic private cursor advances only after successful direct completion; dry run, explicit offsets, failures and partial runs do not advance it. Known tracker data stays local. |
| 12 | Historical exports presented as current discoveries | Carry source timestamps and historical-seed labels, including newsletters; fresh input is prioritized. Historical seeds still require current vacancy checks, and are never proof of current market size. |
| 13 | Nightly searches fixed first four surfaces | Default/installed nightly query budget raised to 28; scheduled query cursor rotates even smaller budgets through the full matrix. Paused non-UK regions remain paused. |
| 14 | Transport denial treated as vacancy closure | Categorize transport/robots/invalid URL/closure separately; independently verified official destination is assessed on its own evidence. |
| 15 | Related expired vacancy closes target | Mask only identified related/recommended job containers; legitimate deadline sidebars remain. Both JD and initial source checks use it. |
| 16 | Alternate URLs waste duplicate budgets | Normalize LinkedIn posting URLs; collapse known employer-scoped requisitions across hosts before semantic review. Never merge bare IDs across employers. |
| 17 | Divergent policies / misleading provider counts | Direct uses shared discipline/region/gates; provider-neutral semantic_accept and separate Codex/DeepSeek counters. Deadline/status/destination metadata now survives the manifest boundary. |
| 18 | Promotion claims success after writer error | Valid JSON containing an error or nonzero writer exit yields writer-failed; no-op is reported as no-op. Failed direct discoveries retained privately for fresh-verified retry. |
| 19 | Task masks promotion failure | Failed scan stops before promotion; task exits promotion result. |
| 20 | Old/unrelated manifest can apply | Fresh timestamp (max six hours), exact run ID, matching completed latest scan and exact scan stdout report required; failed scan cannot promote. |

Additional live-discovered defect: explicitly decode CLI event streams as UTF-8 and suppress subprocess windows. A regression includes Unicode job titles. Search, model batches/split retries, recovery and verification use bounded elapsed budgets. No unlimited retry loop added.

## Verification limits

Positive OPEN evidence requires a current job-bound application route or an exact supported ATS record. Supported read-only API paths include Greenhouse, Lever, SmartRecruiters, Workday, and the documented public Ashby/Workable published-job feeds. Missing/partial feeds, 403/429, robots refusals and ambiguous identities stay UNKNOWN. Absence from a feed never invents closure. No CAPTCHA, authentication or anti-bot bypass was implemented.

Official API references:
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page

The owner-approved policy admits explicitly flagged UNKNOWN leads, while confirmed CLOSED, disallowed-clearance, wrong-region, senior/experience-ineligible and listing-page records remain blocked. UNKNOWN does not mean OPEN. The search cannot guarantee that every run discovers a new suitable vacancy.

## State, privacy and recovery

Source/task backup and raw acceptance evidence remain private under `Documents/Codex/career-search-full-repair-20261022`. Known tracker rows are not sent in search prompts. No raw mailbox bodies, OAuth material, private caches, runtime databases or tracker workbooks are committed.

Direct writer failures retain records in `LOCALAPPDATA/hermes/runtime/career-ops/direct-search/<region>-blocked-candidates.json`. Next execution re-fetches and re-runs eligibility/dedupe; saved OPEN/deadline claims are never replayed as authority. Successful processing clears that queue. Blocked writes preserve it.

During engineering, only the previously enabled ChiefCareerNightly and ChiefCareerScan-UK were temporarily held. Their prior XML/settings and the nightly VBS were backed up. The nightly installed wrapper changed only --web-queries 4 to --web-queries 28. Final task states and acceptance counts are recorded below after verification.


## Final acceptance

- Focused search, verification, writer and scheduling: **601 passed, 0 failed**, across 20 modules, including 63 audit regression cases.
- Entire Career Ops: **1,442 passed, 26 failed**. The same 26 failures were independently reproduced with committed writer/direct-search source loaded only in the test process; **no new failure remains**. Older mailbox-layout/snapshot, LinkedIn publishing/handoff, rollover and recovery failures remain outside this repair. Whole-Career-Ops regression is not green.
- Final bounded scheduled-entrypoint dry run: **170 model classifications, 55 semantic accepts, 21 eligibility passes, 4 duplicates, 17 proposed new rows**. **11 confirmed closed postings** rejected. Missing-employer and job-board-as-employer signals stay review-only. The 17 new proposals are flagged unverified leads, not 17 proven-open vacancies.
- Elapsed **265.23 seconds**, exit **0**. Two rotating live queries, structured regional worker explicitly skipped: this is a diagnostic acceptance through the normal orchestrator, not a full 28-query nightly benchmark. Earlier live evidence also demonstrated exact Workday/SmartRecruiters checks and original-employer recovery. Direct ATS search exercised actual batches 8 and 9 and produced three new flagged proposals.
- Current direct worker separately proved an observed public query and actual search result. Worker and direct parsers combine arrays; absent final output fails rather than becoming a successful zero.
- Live snapshot source and canonical tracker hashes were unchanged. Canonical UK before/after SHA-256: `72ae3ce74bc18869d4ff1e8d6e226178dc3a4a0bcf113e43593edf6b5da646d5`.
- **Private-copy apply:** 21 manifest records produced **17 appends, 4 duplicates**, verification PASS; replay produced **0 appends, 21 duplicates**. Passed/listing deletions **0**; an owner row marked Passed was preserved. No canonical apply was performed.
- Automatic promotions explicitly pass `--preserve-existing-rows`; stronger incoming listing checks cannot sweep existing owner rows. Manual cleanup remains separate. Scheduled research reserves half its remaining budget for classification/verification and defaults to 32-item classification batches.
- Both UK tasks restored **Enabled / Ready**, original owner principals verified by SID. Other regions remain disabled. No task was manually started. The maintenance hold crossed one nightly trigger; no stale manifest was replayed.
- Recorded next runs (London): **ChiefCareerScan-UK: 22 October 23:45 BST**; **ChiefCareerNightly: 23 October 23:30 BST**. The installed nightly VBS differs from its backup only by --web-queries 4 becoming 28.
- No application, outreach, Gmail mutation, Calendar/CV/credential change or main merge. Private workbooks, raw reports, caches and recovery data are excluded from Git.

## Evidence locations

The accompanying committed JSON contains aggregate counters/hashes only. Full JUnit, committed-baseline comparison, observed-query evidence, raw reports, task XML, backups and the private-copy apply remain at:

`C:/Users/mukun/Documents/Codex/career-search-full-repair-20261022`

The original read-only audit is at `Documents/Codex/career-search-readonly-audit-20261022/audit.md`. Evidence distinguishes reproduced defects from inferred market impact. It does not claim exhaustive discovery or that blocked vacancies were proven open.
