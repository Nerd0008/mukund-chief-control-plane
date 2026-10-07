# Read-only Gmail second-pass reconciliation

The initial 30-day report is preserved. A second pass reuses its 67 recruitment-query message identities, including the 61 unresolved signals, without advancing the Gmail checkpoint or enabling writes.

Matching ranks explicit application/requisition ID, consistent Gmail thread, complete company/role, and normalized complete role. Employer suffixes and supported title wording are normalized; cohort, duration, specialism and conflicting locations remain significant. Candidate/person IDs are not application IDs. A shared Gmail thread cannot merge contradictory roles. Multiple canonical rows remain review-only. Portal sender names, privacy footers, employer names, recruitment slogans and umbrella schemes do not establish a specific application.

Deadline parsing recognizes bounded action dates/times, explicit timezones, date-only deadlines and received-email relative hours/days. It rejects missing years/timezones, ambiguous anchors and business-day assumptions. Duplicate invitation copies retain their original received anchor. Employer response estimates, completion notices and future hiring-stage descriptions are not current action deadlines.

Validation: 205 tests passed, 0 failed across test_career_mail_monitor.py, test_career_mail_second_pass.py and test_application_inbox.py using the Hermes Python interpreter. No model calls were used.

Original 61 unresolved signals: 11 confident existing matches, 15 likely-new signals (14 company/role pairs), 22 uncertain existing recruitment events, 11 owner-review items, 2 generic/false positives. Across all 67 reanalyzed messages: 16 existing matches, 19 assessment signals, 1 interview signal, 0 exact deadlines, 7 derived signals representing 4 timestamps, 6 explicitly ambiguous timing signals, 0 calendar proposals. Likely-new signals are not approved tracker insertions.

An independent UK tracker writer changed the workbook during the audit. Matching uses the preserved private frozen snapshot; the final live workbook fingerprint differs, so future writes require fresh reconciliation. This audit made zero tracker/calendar/Gmail mutations and zero checkpoint advances. Existing unrelated schedules/processes were not changed.

The complete private owner review contains all likely-new applications, all assessment/interview signals and the per-message failure ledger. Private mailbox evidence is not committed. Report ID: c974caa787d82e6f31176e57dbab4d725bf4ed595e673ceeaceda4c906cb339f.

Automatic Gmail writes remain disabled. Owner review and fresh source reconciliation are required before any later write activation.
