# UK search reliability repair — 23 October 2026

## Problem and resulting behaviour

The two-hour scan bundled six queries into one model request, stopped after a duplicate-only batch, rejected some UK city-only records before country verification, mistook employer biography and scheme duration for applicant experience, and used a company/title notification key that could suppress another requisition. Its tracker-delta reporting could attribute another run's additions to itself. The nightly and direct paths also applied conflicting collection scopes.

The repair executes each requested query separately and records its completion, error and public result records. A successful batch advances a persistent cursor; duplicate-only or availability-unverified batches continue within a three-batch, 1,200-second cap. A failed batch does not advance. Neither pathway claims market exhaustion. All requested live queries and bounded verification must complete before automatic promotion or direct writing. An observed zero-result query is distinguished from missing or timed-out search.

UK collection uses the existing production high_recall scope through an isolated per-run portal overlay, then applies shared evidence gates. The installed owner portal configuration is unchanged. The older internship-only policy conflict is explicitly recorded; candidate education, visa and clearance facts are unchanged. Non-UK query scope remains inherited.

Country evidence is retained from vacancy metadata. London/Manchester/Bristol with explicit GB metadata can pass geography; city names without country evidence remain unresolved. London, Ontario remains blocked even with a conflicting GB hint. Experience screening distinguishes employer statements, technical project proficiency and programme duration from actual employment requirements. Explicit current-student requirements need confirmation and remain review-only where the profile does not establish current enrolment.

Writer and reporter use posting/requisition identity. A year-suffixed title matching an existing role without distinct requisition evidence requires review. A publisher without an identified employer requires review. Reports attribute only this invocation's confirmed writer outcomes, and label availability-unverified leads. Full public JD inputs and their hashes are retained privately for replay; no CV or credential content is added to these evidence files.

## Reproductions and controls

* Menzies employer biography: the same text triggered an experience rejection before and does not after. A candidate requirement for three years' professional experience still triggers.
* NFU Mutual: the same 13,841-character employer JD previously matched “Scheme length — 3 years” as experience; after the repair it produces no experience hit. This proves the experience fix, not complete applicant eligibility.
* Six-query reproduction: one aggregate worker before; six individually observed workers after. An old production log with nine records but no per-query receipts cannot certify six completed queries.
* Distinct employer requisitions with the same company/title survive the former notification-ledger suppression. Existing intake/title variants without distinct identity do not become new rows.
* Final live-path negative control reproduced an incomplete search writing to a private workbook and returning success. After correction it returns nonzero, retains candidates for fresh verification and neither writes nor advances the cursor. The reliability module has 44 passing controls.

## Bounded live acceptance and limits

The first real public-web batch completed 6/6 queries and retrieved 19 records. Its two initial “new” proposals were not valid proof of new vacancies: a G-Research intake/title variant and an intermediary listing with no identified employer. Replaying those same proposals against the same private workbook with the corrected writer gives zero proposed appends and two explicit review reasons.

A second live batch deliberately used a shorter 180-second budget. Only 3/6 queries completed; the run returned exit 2 with no writer call. It retrieved NFU Mutual and CGI records and exposed the scheme-duration error above. Incomplete coverage was not reported as a healthy zero. The canonical tracker and both private input snapshots remained unchanged during these acceptance runs.

These tests prove the reproduced failures and safety controls are corrected. They do not establish exhaustive LinkedIn or market coverage, nor demonstrate a genuinely new, fully eligible vacancy. Missing source feeds, blocked ATS retrieval, current student status and source freshness remain visible constraints. Historical source records are counted separately from current retrievals; proposed/unverified rows are not presented as confirmed-open new jobs.

## Validation

Final frozen full suite: **1581 tests passed**, including all 44 search-reliability controls. JUnit: `search_fix/final-frozen-suite.xml`. Existing Pillow deprecation warnings remain unrelated to the repair.

Private reproduction JSON, public JD evidence, live receipts and JUnit results are stored in the owner's workspace under `search_fix/`; raw workbooks, runtime logs and full source articles are not part of this source change. Both temporarily held Windows tasks were restored to their original enabled state after validation. Their actions and triggers were compared and are unchanged. A fresh UK scheduled scan was requested to replace the held cycle; its result is not counted as a completed acceptance run. Other regional tasks were not changed.
