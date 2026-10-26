# Overnight UK discovery activation — 26 October 2026

Owner authorized repeated UK job discovery and canonical tracker updates until the next morning or Codex weekly exhaustion. Native automation `overnight-uk-career-discovery` is ACTIVE, every 20 minutes. Searches stop by 08:00 London on 27 October; a final report-only heartbeat may run afterward. No reset credit redemption or purchases are authorized. Initial account metadata showed 88% weekly remaining; the reset-credit expiry differs from weekly-window reset.

The campaign uses current Hermes professional references and the existing profile loader. Initial canonical UK workbook: 165 rows, integrity PASS. Actual writes use `job_scan_delta.py` / the guarded shared writer; no new workbook layout, provider configuration or application workflow was introduced.

## Initial write blocker

The first search completed 6/6 queries, retrieved 41 records and proposed one new row. Windows denied replacing the workbook. Excel held the target open; it reported Saved=True. A private SHA-verified copy was taken and only that saved target workbook was closed. No unsaved changes were discarded, no other workbook was closed, and Excel was not killed.

## Reproduced retry-country defect

A city-only candidate carried explicit country evidence in its original discovered record. `collected` and `writer_records` serialization discarded that country before the pending retry. The weak pending copy ran before the fresh result and marked the posting seen, hiding stronger source evidence. The inverse case also mattered: fresh records with missing country could shadow richer retained source data.

The fix preserves country/country_code in private retry provenance, carries explicit country_code into the current candidate, processes fresh records first and fills missing country evidence only from a retained record with the EXACT same posting key, company and title. A fresh explicit country is never replaced, including a conflicting foreign country. No location inference, weakened geographic rule, identity merge, saved OPEN claim or deadline replay was added. Pending candidates still pass every current gate and canonical dedupe before writing.

Twelve new regressions cover both evidence directions, complete/partial batches, country/code forms, mismatched company/title/URL and a fresh foreign country. Initial reproduction failed before the fix. Focused search/deadline/availability/identity/recovery suites: 186 passed. A broad Career Ops run passed 1,708 tests but two assertions against the live workbook hash were invalidated by a concurrent status change; both were rerun within the full rollover suite, 32 passed. The concurrent status change was preserved, never restored from the campaign backup. No claim is made that the tests caused or owned that change.

Private campaign logs, original source evidence, workbook backup and per-run outcomes are under Documents/Codex/uk-search-overnight-20261026. None are committed. The originally found candidate was requeued from its original public discovery evidence with fresh verification required; it is not an application submission or restoration of a deleted owner row.

No main merge, Gmail mutation, outreach, applications, CV generation, Calendar action, LinkedIn publishing, quota reset redemption or provider change.
