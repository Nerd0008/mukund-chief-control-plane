# JD-based application deadlines and rolling priority

The authoritative parser is application_deadlines.extract_application_deadline. It reads available full JD text, not search-result dates or job start dates. The output contains EXACT / ROLLING / UNKNOWN, an explicit date where reliable, the matching wording, JD provenance and source URL. An inaccessible JD stays UNKNOWN.

Exact dates require an explicit application-closing anchor and a complete date. Missing years, ambiguous numeric dates, conflicting closing dates and invalid dates are UNKNOWN. Assessment/interview deadlines are not application closing dates. The date-only jd_fetcher.extract_deadline API delegates to this parser; it no longer invents a current year.

Rolling classification requires explicit application-related rolling/as-received/open-until-filled/early-close wording. Missing deadlines are never assumed rolling. If a rolling process also states an exact backstop, retain the exact date and rolling flag. Explicitly passed deadlines and closed JDs fail the discovery gate.

Priority is: fixed deadlines within seven days (earliest first), rolling opportunities, later fixed deadlines (earliest first), UNKNOWN. Expired tracker rows rank last; existing owner records are not deleted or changed by this repair. Existing date/ID ordering is retained inside equal priority groups.

Connected paths: fetched JD metadata -> direct Codex search reconciliation and new-row deadline cells; discovery accepted candidates -> deterministic gates -> regional record -> existing canonical writer; daily digest -> existing deadline column and priority sort. No extra workbook columns, live searches, provider calls, schedules or canonical workbook writes were made for this repair. Fresh script invocations load the source; no Hermes restart is needed. Existing tracker rows are not backfilled.

Validation: 157 passed across application deadlines, direct-search recall, liveness, regional search, daily digest and discovery pipeline suites. Full-JD fetches were stubbed; workbook writes were restricted to pytest temporary workbooks. A broader run including tracker_writer produced 204 passed / 5 failed: the current UK baseline has missing hyperlinks beginning D225 and copy-based writer verification also fails. tracker_writer.py is unchanged by this repair; no tests were weakened to hide workbook failures. New direct UK rows now explicitly attach each hyperlink to their own visible URL, verified in the temporary workbook acceptance.

Prior source copies were preserved under Documents/Codex/deadline-recovery/20261017-224040 before editing. No main merge, application submission, outreach, Gmail mutation or provider configuration change.
