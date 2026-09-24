# Company Watch (Career)

Status: BUILT + EVIDENCED 2026-09-23. Owner: Mukund. Maintained by: Chief of Staff.
Parent authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md` § Company Watch.

## What this is

Company Watch watches the organisations Mukund **already has recorded application/CV
evidence for**, checks their public structured ATS/career endpoints for new
postings, dedupes those postings against the canonical Career Ops state, and hands
eligible findings to the existing deterministic tracker writer.

It exists because the history was already there: the recorded Gmail review
(`uk_application_company_history_18_months.md`) names 203 confirmed/strongly
evidenced employers, 18 recruiters/intermediaries and 4 further rows — 229 rows in
total, of which 221 organisations carry application/CV evidence. Company Watch
re-parses that file and re-verifies those counts on every refresh; it never invents
an organisation.

## Layout

| Path | Role |
|---|---|
| `company_registry.py` | Parses the recorded company history into the watched-company registry |
| `ats_endpoints.py` | Bounded public ATS/JSON endpoints (greenhouse, ashby, lever, workable, smartrecruiters) + attribution rules |
| `company_watch.py` | CLI: `registry`, `resolve`, `scan`, `handoff`, `workbook`, `run` |
| `company_watch_config.json` | Watch configuration (paths, bounds, routing, workbook) |
| `registry/company_watch_registry_summary.json` | Committable aggregate view (counts + source hash, no company names) |
| `tests/test_company_watch.py` | 35 offline tests (all network paths stubbed) |

Owner-private data policy: the **full company-level registry** and per-posting
findings name Mukund's job-search history, so they are written to
`runtime/company-watch/` which is git-ignored. Only aggregate counts, hashes and
verification results are committed.

## Reused, not rebuilt

* the historical company history (single source of truth for the watch list);
* the owner's own search filters, read live from the Career Ops install's
  `portals.yml` (`location_filter`, `title_filter`, `max_posting_age_days`) — the
  same file the UK scan lane uses, so eligibility cannot drift from the owner's
  configured intent;
* `career-ops/tracker_writer.py` for **all** dedupe and workbook writes — Company
  Watch imports `normalize_url`, `pair_key`, `build_cross_month_index` and the
  `Tracker`/verification path rather than reimplementing them.

## Non-negotiables enforced in code

1. **No invented organisations or jobs.** The watch list is parsed from the recorded
   history; findings come from vendor JSON.
2. **Slug guesses are not attribution.** A guessed ATS slug may belong to an
   unrelated company (observed live: slug `wise` resolves to "Wise Worksite Field
   Sales"; slug `disney` resolves to an unrelated band). A board is trusted only when
   the vendor payload names the company, or when the vendor's board page contains the
   company name as a standalone token of at least 5 characters. Everything else is
   `attribution_confidence: "low"`, `manual_attribution_required: true`, and its jobs
   are discarded rather than mis-attributed.
3. **Constructed URLs are not evidence.** Where a vendor API returns no public
   posting URL (SmartRecruiters), the documented public pattern is used but flagged
   `url_quality: "derived_public"` and fetched once; a non-200 makes the finding
   ineligible. Raw API endpoints are `api_endpoint` and never tracker-eligible.
4. **Word-boundary matching.** `Intern` must not match `Internal Audit`; `UK` must not
   match `Ukraine`.
5. **Unverifiable means ineligible.** A finding with no posting date cannot satisfy the
   owner's freshness rule, so it is not tracker-eligible (`age_rule_pass: null`).
6. **Shared dedupe, canonical state untouched by default.** `scan`/`run` hand off
   through `career_ops_cli.py write` (dry-run against the canonical workbook unless
   `--apply` is passed explicitly). The acceptance write is performed against a
   **copy** of the canonical workbook.
7. **Unknowns stay unknown.** A manifest carries only what was observed: no
   clearance, salary, work-authorisation or gap claim is ever synthesised, and the
   regional trackers' owner columns (UK `J,K,S,T,U,V`; regional `R,S,T,U,V,Z`) are
   never written by Company Watch.
8. **No external action.** No applications, no messages, no recruiter/company
   contact, no account actions, no browser automation, no cookies, no LLM tokens.

## Command surface

    python company-watch/company_registry.py            # parse + verify the history counts
    python company-watch/company_watch.py registry      # aggregate view of the watch list
    python company-watch/company_watch.py resolve --limit 60 --budget-s 400
    python company-watch/company_watch.py scan --region uk
    python company-watch/company_watch.py handoff --region uk            # dry-run
    python company-watch/company_watch.py workbook --month 2026-09
    python company-watch/company_watch.py run --region uk --limit 60 \
        --acceptance-copy runtime/company-watch/acceptance

`resolve`/`scan`/`run` are the only commands that touch the network, they are bounded
by `--budget-s` (a run that hits the budget reports `budget_exhausted: true`), and
every request is recorded in the run's HTTP call log. `run --task-id <id>` records
which task the evidence belongs to (defaults to the task that specified the
integration), so a later acceptance/recovery run can produce evidence under its own
id without editing the module.

## Sweep order

`ordered_companies` walks the registry deterministically: employers, then recruiters,
then other recorded classes, alphabetically. `--start-index` advances through the
registry so consecutive bounded nightly runs cover new ground instead of re-probing
the same slice.

## Monthly operational workbook

`Company_Watch_<YYYY-MM>.xlsx` in `C:\Users\mukun\Downloads\codex\company-watch\`
(sheets: README, Watch List, Findings, Tracker Handoff, Run Log).

It is never application state: it contains no application-status column, its filename
cannot match a regional tracker archive glob (`write_workbook` refuses outright if a
misconfigured template collides), and it is never read back by the Career Ops dedupe
index. Excel regional trackers stay authoritative.

## Regional tracking

* UK: `discovery` (Q) carries the Company Watch provenance string; `prior_company_signal`
  (R) records that a prior application/CV is on file as a *review signal* (never a
  company-wide block).
* Dubai/Japan/Singapore: provenance goes to `Source` (X). Those trackers have no
  non-owner prior-signal column, so the prior signal is recorded in the handoff
  manifest and this workbook instead of being written into an owner column.
  `test_regional_handoff_writes_provenance_to_a_tracker_copy` proves this end to end
  per region against a workbook copy: the finding appends once with provenance in
  `Source`, re-applying appends nothing, existing owner columns (R,S,T,U,V,Z) are
  byte-identical, and the canonical regional workbook hash is unchanged.
* Regional scan/schedule lanes are **not** Company Watch's to build — they belong to
  `agent-regional-job-search-agents-and-schedulers-2026-09-23`. A non-UK finding is
  routed (`region_route`) but is not handed off unless its region is explicitly
  requested.

## Tests

    python -m pytest company-watch/tests/test_company_watch.py -v     # 35 passed, offline

Covers: registry parsing/verification and mismatch detection, "never invents a
company", real-source counts (203/18/221), name variants and slug candidates,
word-boundary matching, URL classification, owner-filter sourcing and the minimal
portals parser vs PyYAML, attribution confirmation/refusal, malformed payloads,
budget stop, owner filters + age, API-endpoint refusal, unattributed-board discard,
shared dedupe (URL, company+title, cross-month ledger), manifest has no application
state, provenance refusal when a region has no non-owner provenance column, the full
handoff→append→verify→repeat-dedupe cycle on a workbook copy with the canonical file
proven untouched, **the same end-to-end regional handoff per region (dubai/japan/
singapore) including owner-column immutability and refusal to hand a finding to a
region that was not requested**, monthly workbook creation/conflict refusal, and
deterministic sweep ordering.
