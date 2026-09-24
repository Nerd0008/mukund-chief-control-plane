# Unified scheduled Career discovery orchestrator

Worker: `career-ops/discovery/scheduled_orchestrator.py`
Launcher (per region): `career-ops/run_scheduled_scan.cmd <region>`
Scheduled tasks: `ChiefCareerScan-UK`, `-Dubai`, `-Japan`, `-Singapore`
Status: **active** (2026-09-24 cutover). Owner approval required for anything that
writes a canonical tracker — this worker never does.

---

## 1. What changed and why

Before this cutover each scheduled task ran one command:

```
"%PY%" "%CP%\career-ops\regional_job_search.py" run --region %REGION% --scheduled \
        --timeout 1800 --record "%LOGDIR%"
```

That worker reads the owner's Career Ops lane, whose only discovery gate is the
Intern/Internship title filter (`portals.yml#title_filter.positive`). Used as the
sole gate it returns zero whenever no internship is posted — the false-zero the
owner reported (Company Watch found 19 new postings, 0 tracker-eligible).

The scheduled path now runs the unified orchestrator, which combines six
read-only surfaces into one funnel:

| Lane | Worker | Notes |
|---|---|---|
| structured regional provider scan | `career-ops/regional_job_search.py run --scheduled` | unchanged worker, invoked by subprocess with a bounded timeout |
| open-web / Codex-style research | `career-ops/discovery/web_research.py` query matrix + live provider | bounded queries per region, URL validation with live timestamps |
| Company Watch findings | `company-watch/company_watch.py` export `findings-<region>-latest.json` | ingested read-only; freshness recorded |
| priority company watchlist findings | `career-ops/discovery/watchlist.py` export `watchlist-<region>-latest.json` | the owner's own list is optional; an absent list is a valid state |
| recruiter/intermediary watch | export `runtime/career-ops/recruiter-watch/recruiter-watch-<region>-latest.json` | only when present |
| LinkedIn job-discovery intake | owner-exported file `runtime/linkedin/inbox/linkedin-jobs-<region>.json` | only when present; no login, no session, no browser |

Funnel, gates, dedupe and manifest come from the existing discovery pipeline, so
there is one eligibility policy, one dedupe engine (`tracker_writer.py`) and one
candidate schema.

**Discovery policy.** The scheduled path uses `high_recall` (Tier A: early-career
level signal + cyber/IT discipline signal; Tier B: senior/leadership hard
negatives). The owner's Intern/Internship-only rule still exists, unchanged, as an
explicit diagnostic:

```
python career-ops/discovery/scheduled_orchestrator.py run --region uk \
    --mode intern_only --compare  --skip-regional-scan --no-live
```

Without `--compare` the CLI refuses to run the diagnostic mode (exit 2), so the
narrow rule cannot become the production discovery gate by accident.

---

## 2. Run commands

```
# one region, production policy, bounded dry run (what the scheduled task does)
python career-ops/discovery/scheduled_orchestrator.py run --region uk --scheduled \
    --require-live-web --mode high_recall --budget-seconds 2700 --scan-timeout 900 \
    --web-queries 8 --max-urls 24 --retries 1

# all four regions, one unified manifest + one unified funnel document
python career-ops/discovery/scheduled_orchestrator.py run-all --scheduled --require-live-web

# offline replay (no live pass; never valid as live proof)
python career-ops/discovery/scheduled_orchestrator.py run --region uk --no-live \
    --provider captured --captured <export.json> --no-validate --skip-regional-scan

# diagnostic compare mode (the owner's old narrow rule)
python career-ops/discovery/scheduled_orchestrator.py run --region uk \
    --mode intern_only --compare

# operational views
python career-ops/discovery/scheduled_orchestrator.py policy      # declared policy + budgets + rollback
python career-ops/discovery/scheduled_orchestrator.py coverage    # per-region source-class states
python career-ops/discovery/scheduled_orchestrator.py status      # last run per region + rollback
python career-ops/discovery/scheduled_orchestrator.py selftest    # offline structural checks
```

Acceptance runner (offline structural checks + `--live` per-region bounded live
pass + one broad all-source-class live pass + whole-company regression; canonical
tracker hashes compared before/after every run):

```
python career-ops/run_scheduled_orchestrator_acceptance.py --live --json
python career-ops/run_scheduled_orchestrator_acceptance.py --live \
    --live-queries 2 --broad-queries 4 --broad-region uk
```

The bounded per-region pass uses a 2-query budget per region (round-robin, so
public LinkedIn Jobs and Indeed are exercised first); the broad pass gives one
region enough queries that round-robin reaches **every** required source class
(public LinkedIn Jobs, public Indeed, Google/web index, ATS/employer careers).
Results are written to `audits/evidence/<stamp>-career-scheduled-orchestrator-cutover/`
(aggregate only); raw result URLs stay under the git-ignored `runtime/` tree.

---

## 3. Outputs (all under the git-ignored runtime tree)

| Path | Content |
|---|---|
| `runtime/career-ops/discovery/unified/<region>/latest.json` | that region's full run document |
| `runtime/career-ops/discovery/unified/<region>/manifest-latest.json` | that region's candidate manifest |
| `runtime/career-ops/discovery/unified-latest.json` | whole-company aggregated funnel document |
| `runtime/career-ops/discovery/unified-manifest-latest.json` | ONE unified nightly candidate manifest (all regions) |
| `runtime/career-ops/discovery/latest.json` | the path the Career Daily Brief reads (`daily_brief_config.json#discovery.latest`) |
| `runtime/career-ops/discovery/unified-run-state.json` | last run id / run key / counts per region (idempotency) |
| `runtime/career-ops/discovery/unified-run.lock` | concurrency lock (present only while a run is in flight) |
| `runtime/career-ops/scan-runs/<region>-unified-last-stdout.json` | the launcher's captured stdout |
| `runtime/career-ops/scan-runs/regional-run-<region>-<ts>.json` | the structured worker's own run-health record (unchanged) |
| `runtime/career-ops/web-research/web-research-<region>-<id>.json` | raw research export (result URLs are owner-private) |
| `runtime/career-ops/scan-runs/regional-run-state.json` | the structured worker's own state (unchanged) |

Nothing outside `runtime/` is written. No canonical workbook is opened for
writing, no application is submitted, nobody is contacted, and no LinkedIn,
browser, login or session surface is ever used (see the `safety` block on every
artifact, and `no_browser_or_gui_imports` in the acceptance runner).

---

## 4. Source-coverage matrix

Four source classes must be attempted and truthfully recorded on every live pass.
Each carries a state derived only from that run's own evidence:

| State | Meaning (evidence rule) |
|---|---|
| `reached` | at least one result URL of this class was discovered by an executed query whose live search was observed |
| `blocked` | the query ran and a live search was observed, but the class's own destinations refused retrieval (HTTP 401/403/429, robots.txt) or every discovered URL failed validation — recorded as blocked, never as empty |
| `unavailable` | no live-search mechanism was available for that class's queries in this run (provider unavailable / no search event observed) |
| `not_applicable` | the class was not attempted in this run (configuration, budget, or the data arrived through another lane) |
| `searched_no_results` | the class's queries executed with an observed live search and returned no result URL of that class — a fact about this run's search, never a claim that the source is empty |

Classes and the surfaces that belong to them:

| Class | Surfaces |
|---|---|
| `public_linkedin_jobs` | `linkedin_jobs` (public/indexed LinkedIn Jobs results — no login, cookie or browser) |
| `public_indeed` | `indeed` |
| `web_index` | `google_index` (Google / web-indexed vacancy discovery) |
| `ats_employer_careers` | `greenhouse`, `lever`, `ashby`, `workday`, `workable`, `smartrecruiters`, `icims`, `teamtailor`, `employer_careers` |

Per class the artifact also records `queries_targeting`,
`queries_with_observed_live_search`, `result_urls_discovered`,
`job_posting_urls`, `validated_live`, `validation_failed` and
`blocking_evidence`, plus the per-source funnel counters
(`funnel.by_source[source].counts` / `zero_attribution`).

Discovering a public LinkedIn result URL requires no session: the query matrix
contains `site:linkedin.com/jobs ...` and results are classified by the ATS/host
they point to (`classify_surface`). A LinkedIn *search/collection* page is
labelled `search_listing` and can never be written as a vacancy; only a
`/jobs/view/...` result is treated as a posting.

---

## 5. Bounds, retries and concurrency

| Bound | Default | Effect |
|---|---|---|
| `--budget-seconds` | 2700 | overall wall clock; the per-query timeout shrinks to fit the remaining budget |
| `--scan-timeout` | 900 | structured worker timeout (the launcher also passes `--timeout` to the lane scan) |
| `--web-queries` | 8 | queries per region, selected round-robin across surfaces so every required class is attempted first |
| `--limit-per-query` | 5 | results kept per query |
| `--max-urls` | 24 | URL validation budget per region (a hostile site cannot consume the whole scan) |
| `--per-query-timeout` | 180 | one research call |
| `--retries` | 1 | retries for the bounded subprocess lane (initial + 1), each attempt recorded |
| `--ingest-stale-hours` | 48 | an older lane export is still reported but flagged stale, never presented as fresh |
| lock file | always on for scheduled runs | a second instance that finds a fresh lock exits 0 with `status: overlap_skipped` |
| idempotency | per region | `run_key` = hash of region + mode + canonical candidate set + coverage states; a repeat is reported as `idempotent_replay` |

Staggering is declared in `regional_schedules.json`: UK 23:45, Dubai 23:50, Japan
23:55, Singapore 00:00, plus the lock and per-region run keys.

---

## 6. Daily Brief integration

`career-ops/daily_brief.py#collect_discovery_funnel` reads the unified
`runtime/career-ops/discovery/latest.json` and reports:

* raw results, semantic pass, eligibility pass, duplicates and tracker candidates
  (the funnel's own counters, unchanged);
* **source coverage**: per-source `discovered`/stage counters/zero attribution and
  the per-region source-class states;
* the live research mechanism state and whether the lane is production-ready
  (plus the `no_go` text when it is not);
* the unified manifest record count;
* the priority-watchlist block and its own zero attribution;
* explicit zero attribution (`funnel.zero_attribution`, per-source
  `zero_attribution`, and `not_applicable_stages` for disabled stages).

An absent or stale run is UNKNOWN, never "no jobs".

---

## 7. Rollback to the old scheduler

The launcher path (`career-ops/run_scheduled_scan.cmd`) is unchanged, so rollback
needs no `schtasks` re-registration. Replace the orchestrator line in the launcher
with the previous single-worker line:

```
"%PY%" "%CP%\career-ops\regional_job_search.py" run --region %REGION% --scheduled --timeout 1800 --record "%LOGDIR%"
```

Keep CRLF line endings in the `.cmd`. Nothing else has to change: the structured
worker, its state file and its run-health records are untouched by this cutover,
so an old record and a new record can coexist. The orchestrator's own artifacts
stay in `runtime/career-ops/discovery/` and can simply be ignored after a rollback.
Full rollback also includes reverting `career-ops/regional_schedules.json`,
`career-ops/install_schedules.py` (documentation strings only) and the Daily Brief
coverage block if the old behaviour is preferred.

---

## 8. No-go criteria

Do **not** treat the scheduled path as cut over (and do not report the lane as
production-ready) when any of these holds:

1. no current-web search mechanism was proven operational in the run — the
   launcher exits 3, `production_ready: false` and `no_go` are recorded, and a
   fixture capture is never accepted as proof;
2. a canonical workbook hash changed during a scheduled run (the acceptance
   runner compares before/after SHA-256 for all four regions);
3. a run could not bound itself (missing budget/lock, unbounded retry);
4. any step would need an application, outreach, LinkedIn mutation, account login,
   cookie/session use or a browser/GUI action;
5. the owner's priority-watchlist or Company Watch exports are stale — they may be
   reported, but they must not be presented as fresh findings.

Owner evaluation gates that remain untouched: applying a manifest to a canonical
tracker (`career_ops_cli.py write --apply`), any application submission, any
outreach message, and any public/published content.
