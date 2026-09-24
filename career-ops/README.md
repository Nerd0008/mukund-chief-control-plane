# Career Ops ↔ Chief integration (non-E3 v1 half)

Status: ACTIVE — deterministic interface implemented and evidenced 2026-09-23.
Owner: Mukund. Maintained by: Chief of Staff (this control plane).

## What this is

Career Ops already exists and works. This directory does **not** rebuild it. It adds
the missing deterministic glue between Chief and the existing Career Ops
installation at

    C:\Users\mukun\Documents\ChatGPT\CV customizer\career-ops-career-ops-v1.29.0

and the canonical regional Excel trackers at `C:\Users\mukun\Downloads\codex`.

Reused as-is (not modified, not restructured, git repo untouched):

* the Career Ops scanner (`scan.mjs`), provider layer (`providers/`), filters
  (`portals.yml`), dedupe ledger (`data/scan-history.tsv`), pipeline output
  (`data/pipeline.md`), run history (`data/scan-runs.tsv`), and the regional
  shortlist ledgers (`data/{dubai,japan,singapore}-shortlist-history.md`);
* the four canonical workbooks, including their tables, formulas, conditional
  formatting, data validations, status metadata and row layout.

Replaced:

* `output/.codex-run-2026-09-07/save-main-tracker.mjs`, which depended on the
  unsupported `@oai/artifact-tool` (`SpreadsheetFile`/`FileBlob`) that only
  resolved through a Codex runtime symlink. It is superseded by
  `tracker_writer.py` (Python/openpyxl). The original file is left in place as
  historical evidence; nothing imports it any more.

## Deterministic interface

Single entry point: `career-ops/career_ops_cli.py`. Every subcommand prints exactly
one JSON object on stdout — no prose for Chief to parse.

| Subcommand | Purpose | Writes? |
|---|---|---|
| `inventory` | structural facts + hashes for every regional workbook | no |
| `verify --region R` | integrity verification of a canonical workbook | no |
| `dedupe --region R --manifest F` | dedupe decisions for a manifest | no |
| `write --region R --manifest F [--apply]` | deduplicated append | dry-run unless `--apply` |
| `rollover --region R [--month YYYY-MM] [--apply]` | monthly rollover into a per-region archive workbook (B09) | dry-run unless `--apply` |
| `run-health [--job J]` | deterministic run-health for the Excel workers (B08/B09) | no |
| `summary [--region R]` | Chief-readable tracker summary | no |
| `scan --region R [--record DIR]` | bounded Career Ops scan wrapper | no (always `--dry-run`) |
| `ledger --region R` | cross-month dedupe index provenance | no |

Example:

    python career-ops/career_ops_cli.py write --region uk --manifest jobs.json --apply

### Excel remains the source of truth

Chief stores orchestration and run-health metadata. It never becomes the
application record. Every subcommand reads the workbook; only `write --apply`
changes one, under the rules below.

## Write safety contract

1. **Dry run by default.** `write` without `--apply` computes the plan and returns
   it; the workbook hash is unchanged (verified by test).
2. **Backup before every apply.** A hash-verified copy is written to
   `runtime/career-ops/backups/` before the canonical file is touched.
3. **Temp-write, verify, then atomic replace.** The new workbook is saved to
   `*.write-tmp.xlsx`, re-opened and verified, and only then moved into place.
4. **Concurrent-modification guard.** If the canonical file's SHA-256 changed
   between read and write, the write is abandoned with an explicit error.
5. **Owner columns are never overwritten.** For the UK tracker:
   `J,K,S,T,U,V` (Application Status, Priority, Date Selected, Date Applied,
   Tailored CV Path, Personal Notes). For the regional trackers: `R,S,T,U,V,Z`
   (Application Status, Selected?, CV Status, Cover Letter Status, Applied Date,
   Notes). Verification fails if a pre-existing row's owner columns changed.
6. **A manifest cannot set application state.** New rows receive only the
   profile's safe defaults (e.g. UK `To Review`/`Medium`, Dubai `New`). A manifest
   field such as `application_status: Applied` is ignored — this is asserted by
   test, because fabricating an application is the single worst failure mode here.
7. **Duplicates are skipped, not merged.** Matching is by normalised URL, with a
   company+title fallback for moved posting URLs. Refreshing non-owner metadata on
   a duplicate requires an explicit `--update-existing`.
8. **Cross-month dedupe.** The index unions (a) the canonical workbook,
   (b) rotated/previous-month workbooks matching the region archive glob, and
   (c) the region ledger — `data/scan-history.tsv` for the UK, the
   `data/<region>-shortlist-history.md` files for Dubai/Japan/Singapore. A posting
   already seen in a previous month is not appended again.

## Post-write verification

`verify_workbook` fails the write unless all of the following hold for the saved
file: expected sheet order and sheet set; the table still exists and its `ref`
covers the last data row; header row unchanged; fit-tier formulas intact; every
profile data validation preserved; no `#REF!/#DIV/0!/#VALUE!/#NAME?/#N/A/...`
tokens anywhere; no duplicate URL keys; expected data-row count; owner columns
unchanged. On any failure the canonical workbook is left untouched.

## Monthly Tracker Rollover / archive worker (B09, 2026-09-24)

`career-ops/tracker_rollover.py` rotates one closed month of records out of each
canonical workbook into a per-region **archive workbook**:

    uk        -> uk-cyber-job-tracker.<YYYY-MM>.xlsx
    dubai     -> Dubai_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx
    japan     -> Japan_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx
    singapore -> Singapore_Cybersecurity_Job_Tracker.<YYYY-MM>.xlsx

| Subcommand (standalone or via `career_ops_cli.py rollover`) | Purpose | Writes? |
|---|---|---|
| `plan --region R [--month M]` | read-only: what would rotate, months present, conflicts | no |
| `rollover --region R [--month M]` | dry run of the rollover | no |
| `rollover ... --apply` | archive the month, then rotate those rows out of the canonical workbook | archive + canonical |
| `rollover ... --apply --archive-only` | snapshot the month without touching the canonical workbook | archive only |
| `archives --region R` | the region's archive workbooks (name, hash, row count) | no |

    python career-ops/tracker_rollover.py plan --region uk --month 2026-08
    python career-ops/career_ops_cli.py rollover --region uk --month 2026-08 --apply

**The archive name is deliberate.** It matches the region's archive glob in
`regional_profiles.json`, and `tracker_writer.build_cross_month_index` already
unions every non-canonical workbook matching that glob — so every rotated row
feeds the cross-month dedupe index and a posting seen in a previous month is
refused as `duplicate-cross-month` instead of being appended again.

**Schema preservation.** The archive is built from a *copy of the canonical
workbook*, so its sheets, table, header row, data validations, number formats and
column layout are inherited rather than re-created; the data block is then
replaced with exactly the rotated rows, and any row-number-dependent formula
(`formula_map`, e.g. the fit-tier column) is re-templated for its new row. Each
cell of each rotated row is copied verbatim, **owner columns included** — the
archive is the faithful record of what left the live workbook.

**Rotation safety (the same path as the tracker writer).**

1. Dry run by default; nothing is written without `--apply`.
2. The archive is written, verified and only then atomically moved into place —
   **before** the canonical workbook is touched.
3. A canonical write takes a hash-verified backup first, is written to a
   `*.rollover-tmp.xlsx` file, is re-opened and verified (expected row count +
   owner columns unchanged at their new positions), is re-checked against a
   concurrent-modification hash guard, and is only then atomically replaced.
4. **Owner state is never silently deleted.** If a row due to rotate carries a
   value in an owner-only column that is not the profile's own automation default
   (an `Applied` status, a tailored CV path, an applied date), the whole run is
   refused and the offending rows are reported **by row and column letter only**
   — the value is never read into the result, because owner columns can hold
   private notes. `--allow-owner-state-removal` overrides it after owner approval.
5. An existing archive with different content is refused unless `--force`, which
   backs it up hash-verified first.
6. Re-running the same month is deterministic: byte-identical archive content is
   reported as `unchanged` and nothing is rewritten.

**Honest limits (recorded, not hidden).** A row whose `date_found` is not a real
date or ISO date string (for example the free text `"Posted 30+ days ago"`) is
reported as `undated` and **never rotated**. The regional profiles map the
manifest's `notes` field to column `Z` while also declaring `Z` an owner column,
so `Z` is *automation-writable* and cannot be attributed to the owner from the
data alone: the guard reports it in `owner_columns_automation_writable` instead of
pretending to protect it, and always protects the genuinely owner-only columns
(application status, selected flag, CV/cover-letter status, applied date).
Overview sheets (for example the UK `Summary`) are not rewritten; their formulas
use whole-column ranges (`Jobs!$A$10:$A$500`) and recompute over the remaining
rows when the workbook is opened.

## Department run-health (roster B08 / B09)

`career-ops/dept_run_health.py` is the single deterministic place where the Excel
workers' **orchestration** metadata is written and read back:

    runtime/career-ops/run-health/tracker-writer.json      (B08)
    runtime/career-ops/run-health/monthly-rollover.json    (B09)

Each document records the worker, its roster id, `runs_recorded`, the last run
(time, region, status, mode, result) and the last run per region, with row counts,
hashes and file names. `career_ops_cli.py run-health [--job J]` prints it as one
JSON object. Both the `write` and `rollover` commands record a run automatically
(`--state-dir` overrides the location, which the tests use).

**Excel stays authoritative.** Every document states
`excel_is_source_of_truth: true` and `chief_state_role: "orchestration-only"`, and
the documents are **aggregate only** — no company, title, URL, note or other
workbook content is ever stored there, which is why they are safe to commit.
A test asserts the state files contain no URL or workbook text.

## Regional schedules

`regional_schedules.json` + `install_schedules.py` define and register Windows
scheduled tasks (`ChiefCareerScan-UK`, `-Dubai`, `-Japan`, `-Singapore`).

* Scheduled runs are **bounded dry-run scans only** — they never write a tracker
  and never submit anything, so overlapping runs cannot duplicate rows.
* Every region has a real lane config (2026-09-24):
  * `uk` reuses the owner's existing install lane (`portals.yml`,
    `data/pipeline.md`, `data/scan-history.tsv`) and runs daily at 23:45 local,
    matching the historical ~23:48 window in `data/scan-runs.tsv`;
  * `dubai`/`japan`/`singapore` lanes live in this control plane under
    `career-ops/lanes/<region>/` and are referenced by absolute path, so the
    owner's Career Ops installation is never modified. `resolve_lane` now reports
    every region `ready: true`.
* Registration is idempotent and reversible:
  `install_schedules.py --install` / `--status` / `--remove`.

## Regional job-search workers (2026-09-24)

One implementation, four regions: `career-ops/regional_job_search.py`. UK, Dubai,
Japan and Singapore never diverge into four codebases.

    lane readiness -> bounded Career Ops scan (dry-run) -> candidate records
      -> shared eligibility/policy filter -> shared dedupe -> run-health +
      idempotency state -> optional manifest for the deterministic tracker writer

| Subcommand | Purpose | Writes? |
|---|---|---|
| `policy [--region R]` | resolved region policy + provenance + drift check | no |
| `lanes` | lane readiness, configured scope, provider coverage | no |
| `eligibility --region R (--manifest\|--records\|--scan-record F)` | per-record decisions | no |
| `run --region R [--record DIR] [--manifest-out F] [--scheduled]` | one deterministic regional run | run-health + state only |
| `run-all [--record DIR] [--scheduled]` | all four regions in scheduled order | run-health + state only |
| `status` | run-health + state per region | no |

**Shared primitives, no per-region forks.** Dedupe, the workbook index, the
cross-month index and the write path all come from `tracker_writer.py` (the same
code the UK lane uses). The region's lane `portals.yml` is the single source of
the location scope, and the owner's own install `portals.yml` is the single
source of the title policy — `regional_policy.json` mirrors both and a test fails
if any of them drift.

**Eligibility/policy filtering** (`career-ops/regional_policy.json`, applied by
`evaluate_record`): owner title policy, explicit region location scope
(mirroring the scanner's `block_hard`/`always_allow`/`block`/`allow` tier order
and its remote-title rescue), the owner's clearance/citizenship rejection policy
from `config/profile.yml`, a multi-year-experience rejection, a mandatory-URL
rule, and **fail-closed** behaviour when no region scope can be resolved.

**Owner facts are never invented.** Work authorisation is `authorised` for the UK
only (Graduate visa to 23 Dec 2027, from `config/profile.yml`). For Dubai/UAE,
Japan and Singapore the file and every accepted record say **UNKNOWN** — the
owner has never stated a right to work there, so the region's tracker
`visa_pathway` default (`Visa unknown` / `JAPAN WORK VISA UNKNOWN` /
`WORK PASS UNKNOWN`) is recorded verbatim instead.

**Provider coverage is stated honestly.** Singapore is the only region with
first-party providers in the install (MyCareersFuture, Glints SG, Jobstreet
SEEK `SG-Main`). No UAE or Japan provider exists, so those lanes run the
global/remote boards under their region scope, and their `search_queries` carry
the agent-driven Japanese/ATS source list for that path. A thin Dubai/Japan scan
means "no provider for that region", never "no vacancies there".

**Idempotency.** Each run is keyed by a SHA-256 of its accepted candidate set
(stored in `runtime/career-ops/scan-runs/regional-run-state.json`). A replayed
run marks every candidate `duplicate-prior-run` and produces an empty manifest;
independently, the shared writer refuses anything already in the workbook, in a
rotated workbook or in the cross-month ledger. A scan's dry-run "New offers:"
lines carry **no URL**, so they are reported as `scan_offers_without_url` and can
never become tracker rows on their own — only URL-bearing candidates (lane
pipeline entries or an explicit records file) can be accepted.

**No applications.** No subcommand submits, messages, or contacts anyone; the
worker never applies to a workbook. Tracker writes stay the explicit
`career_ops_cli.py write --apply` step with hash-verified backup + verification.

    python career-ops/regional_job_search.py lanes
    python career-ops/regional_job_search.py run-all --record runtime/career-ops/scan-runs --scheduled
    python career-ops/regional_job_search.py run --region singapore --manifest-out /tmp/sg.json
    python career-ops/regional_job_search.py status

## Regional profiles

`regional_profiles.json` is the integration contract: sheet name, table name,
header row, first data row, ID convention, dedupe columns, owner columns,
field map, formulas, defaults, number formats, data validations and ledger source
for each region. These values were derived by reading the canonical workbooks; the
test suite re-checks them against the real files so the profile cannot silently
drift.

## Tests

    python -m pytest career-ops/tests/test_tracker_writer.py -v

Covers: structural/integrity verification of all four canonical workbooks,
profile-vs-workbook drift, absence of the artifact-tool dependency, URL
normalisation (tracking params and `=HYPERLINK(...)`), duplicate detection in
every region, cross-month dedupe from an archive workbook and from the UK scan
ledger, manifest-cannot-set-application-state, dry-run-changes-nothing, full
append→verify→backup→rollback acceptance for all four regions, and idempotency of
a repeated run. Tests only ever write to copies; the canonical workbooks are
opened read-only by the suite.

`career-ops/tests/test_tracker_rollover.py` (32 tests) covers the monthly
rollover worker: archive naming vs the profile's archive globs, month parsing
(including free-text dates that must not rotate), read-only planning, dry runs
that write nothing, archive+rotation on a copy in all four regions with schema,
formula and data-validation preservation and verbatim cell copies, cross-month
dedupe for every rotated row, first-run refusal on existing archive content and
the `--force` backup path, refusal on owner-column state (with an assertion that
the owner's value never appears in the refusal), `--archive-only` leaving the
canonical untouched, `unchanged` on a deterministic re-run, backup-based rollback,
and run-health recording for both workers (asserting the state files hold no
workbook content or URLs).

## CV + cover-letter draft workflow (2026-09-24)

`career-ops/cv_workflow.py` wires a job record that already exists in Career Ops
state into a **tailored draft** of the CV and the cover letter. It reuses the
existing Career Ops installation rather than recreating it:

* canonical source of candidate truth, read-only: `cv.md`, `config/profile.yml`,
  `config/cv-facts.json` in the Career Ops install;
* authoritative fact gate: the install's own `verify-cv-facts.mjs` (invoked as a
  subprocess, JSON verdict);
* authoritative cover-letter renderer: the install's own
  `generate-cover-letter.mjs` `buildHtml`, driven by
  `career-ops/cv_render_cover.mjs`;
* the existing LLM tailoring path (`openai-tailor.mjs`) is recorded as an
  unexecuted request record — it sends `cv.md` and the job description to a
  third-party endpoint, so it stays owner-gated.

| Subcommand | Purpose | Writes? |
|---|---|---|
| `sources` | canonical source paths/hashes + fact-gate availability | no |
| `job-context --region R (--id\|--url\|--row\|--pipeline-index\|--record)` | resolve one job record from Career Ops state, with provenance | no (optional `--record`) |
| `draft ... [--jd-file F]` | build the tailored CV draft + cover-letter payload/HTML | only under `runtime/career-ops/cv-drafts/` (git-ignored) |

    python career-ops/cv_workflow.py sources
    python career-ops/cv_workflow.py job-context --region uk --id J21
    python career-ops/cv_workflow.py draft --region uk --pipeline-index 0 --jd-file jd.txt

**Tailoring model — deterministic selection only.** Bullets are **re-ordered** by
job-description relevance; no canonical line is rewritten, summarised, merged or
added. `cv_draft_provenance.json` maps every draft line back to its `cv.md` line
number, section, relevance score and matched terms. Posting terms that nothing in
the canonical sources evidences are reported as `owner_input_required` and never
written as a claim. A draft that fails the fact gate is marked `blocked_fact_gate`
and its HTML is not produced.

**Not performed:** PDF rendering (the install's `generate-pdf.mjs` launches
headless Chromium), LLM tailoring, and any application submission or contact.

## LinkedIn workflow (2026-09-24)

`career-ops/linkedin_workflow.py` is the v1 LinkedIn surface. LinkedIn is treated
as exactly two things: a **read-only signal source** (an owner-exported local file
of saved jobs / job alerts / followed companies) and a **draft surface**.

**There is no LinkedIn login, no session reuse, no API call, no scraping, no
browser and no network I/O at all.** A test asserts the module imports no network
or browser library. `guard` is a permanent, recorded refusal: posting, messaging,
connecting, following, reacting, editing the profile and applying are owner-gated
and no code path performs them.

| Subcommand | Purpose | Writes? |
|---|---|---|
| `intake --inbox DIR [--record FILE]` | parse local read-only signal files into job/company signals | no |
| `dedupe --region R --inbox DIR` | dedupe signals against Career Ops + Company Watch | no |
| `draft [--out DIR] [--job-record REC.json \| --id ID \| --url URL \| --row N \| --pipeline-index N]` | profile/post/outreach drafts from canonical facts, fact-gated, `draft_unsent` | only under `runtime/linkedin/drafts/` (git-ignored) |
| `handoff --region R [--apply]` | hand eligible new signals to the Career Ops writer | dry-run unless `--apply` |
| `guard --action NAME` | refuse an external LinkedIn action, and log the refusal | log only |
| `status` | configuration + last-run summary | no |

Accepted inbox formats: `.json`, `.jsonl`, `.csv`, `.md`/`.txt`. A text line
carrying no URL is reported as `unclassified` rather than guessed into a company
or a posting. Every signal carries file + sha256 + line provenance.

**Dedupe is shared, never reimplemented.** `company_watch.build_shared_dedupe` /
`dedupe_decision` are imported, so a LinkedIn signal cannot create a row Career
Ops would consider new state. In addition the workflow dedupes against:

* the Company Watch company registry (name + variant keys — a **review signal**,
  never a company-wide block);
* Company Watch handoff manifests (a posting Company Watch already handed over is
  `duplicate-company-watch`);
* the same intake batch (one posting re-shared with a tracking parameter is one
  posting; the richer copy's detail is **merged into** the kept record and
  eligibility is recomputed, so a detailed copy arriving second is not lost).

LinkedIn handoff manifests are written inside `runtime/linkedin/handoffs/`, never
in Company Watch's runtime directory — Company Watch reads its own handoff
manifests as "already handed off", so writing there would make LinkedIn's signals
look like Company Watch duplicates.

`owner_filter_eligible` uses the owner's own configured filters, read live from the
Career Ops install's `portals.yml` (the same file the UK scan lane uses). A signal
whose location, title or freshness cannot satisfy those filters is **not** eligible,
and only region-routed eligible signals are handed off. A manifest never carries
application status (and the writer would ignore it).

### Networking / recruiter / hiring-manager outreach drafts (B21, 2026-09-24)

`draft` produces three unsent outreach variants alongside the profile and post
drafts:

| Variant | Recipient kind | Notes |
|---|---|---|
| `networking` | peer / alumni / community contact | chat request framing |
| `recruiter` | recruiter or agency contact | carries the canonical Certifications line; no CV is attached or transmitted |
| `hiring_manager` | hiring manager for one posting | produced **only** when a job context resolves from Career Ops state |

Every variant is `draft_unsent` with an explicit `unsent_state` block —
`sent: false`, `sent_at: null`, `recipient_selected: false`, `recipient: null`,
`connection_request_created: false`, `message_queued: false`, `scheduled: false`,
`attachments_sent: 0`, `owner_approval_required: true` — plus a `provenance` block
carrying the canonical source hashes and the exact `cv.md:<line>` refs used.

Two rules keep the drafts honest:

* **Only structural connective phrasing is generated.** `linkedin_workflow.STRUCTURAL_PHRASES`
  is the exhaustive, exported list of every line a draft body may contain that is not
  verbatim canonical text, and the test suite asserts draft bodies against that same
  list. Everything substantive is a canonical CV line quoted verbatim.
* **No role or employer is ever guessed.** The hiring-manager draft names the role and
  employer only from the resolved Career Ops record, and records that record
  (`references_job`: id, title, company, location, source kind, source path) so the
  claim can be checked. With no job context the variant is simply omitted.

No recipient is chosen, nothing is queued, no connection request is created and the
install's fact gate must not block the drafts.

## Application Inbox / Status Monitor (2026-09-24)

`career-ops/application_inbox.py` is the read-only intake for application and
recruiter status signals. It classifies a message, reconciles it against the
canonical regional workbooks, and writes an **idempotent local status store of
proposed changes and owner actions**. It never sends, replies, forwards,
archives, deletes, moves, labels or marks anything read; it never writes to a
workbook; it never creates an application record.

| Subcommand | Purpose | Writes? |
|---|---|---|
| `adapters` | adapter readiness + the exact owner step for the Gmail path | no |
| `ingest [--inbox DIR] [--source NAME] [--runtime-dir DIR]` | classify, match, store | local store only |
| `summary [--runtime-dir DIR]` | Chief summary: changed statuses, owner actions, review queue | no |
| `status [--runtime-dir DIR]` | store + adapter + refusal counts | no |
| `guard --action NAME` | refuse a mailbox mutation, and log the refusal | log only |
| `run [--inbox DIR]` | `ingest` + `summary` in one document | local store only |

    python career-ops/application_inbox.py adapters
    python career-ops/application_inbox.py run --inbox career-ops/tests/fixtures/application-inbox
    python career-ops/application_inbox.py summary

**Classification is deterministic phrase matching, not a model.** Kinds:
application acknowledgement, rejection, interview invitation, assessment
invitation, follow-up/document request, offer, recruiter outreach — otherwise
**unknown**. Strong patterns decide; weak (contextual) patterns never decide on
their own; two contradictory strong signals (e.g. an offer *and* a rejection in
one message) resolve to `unknown` and go to human review. Quoted reply history
is stripped first, so an old acknowledgement inside a thread cannot be
re-classified as new. Every match records which phrase matched and at which tier.

**Matching is conservative and evidence-only.** Only three bases can match:

1. a posting URL that appears verbatim in the message **and** in a canonical row
   (high confidence);
2. an explicit canonical reference in the message (`J11`, `SG-GRAD-260909-01`)
   (high confidence; a bare number is never a reference, and a reference shorter
   than three characters is never matched — a documented limitation for UK
   J1–J9, which must match by URL instead);
3. company name **plus** title agreement (medium confidence).

A company name on its own is **always** ambiguous — it lists the candidate rows
and asks a human. A message that matches nothing is `unmatched` and no record is
created from it, ever.

**Status is proposed, never applied.** A signal maps to a status in the region's
*own* vocabulary (from `regional_profiles.json` validations; the test suite fails
if the map drifts). Where a region has no accurate equivalent — a Japan rejection,
an assessment invite anywhere — no status is proposed and the owner decides. If
the row's current status says no application was made, the proposal is flagged
`requires_owner_confirmation` with the reason recorded: the message implies an
application the tracker does not record, and the monitor does not assume it
happened. Excel stays authoritative; `state_written` is always `false`.

**Idempotent local store** (`runtime/career-ops/application-status/`, git-ignored):
`signals.jsonl` (keyed by `signal_id`), `status-events.jsonl` (keyed by
`event_id` = region+row+kind), `current-state.json` (derived projection, holds no
run timestamp) and the append-only `run-log.jsonl`. Re-ingesting the same mailbox
is byte-identical and reports zero new signals (asserted by test and by the
acceptance run).

**Adapters.**

* `local_mailbox` — **implemented, tested, active.** Parses an owner-provided
  export directory: `.eml`, `.mbox`, `.json`/`.jsonl` (generic records *or*
  Gmail API message objects, base64 bodies decoded), `.csv`. A `.md`/`.txt` file
  is reported as skipped rather than guessed into a message.
* `gmail_readonly` (`career-ops/gmail_readonly.py`) — **interface implemented,
  disabled, no credentials, UNVERIFIED.** Read-only scope
  `gmail.readonly` only. It reports credential/token *presence* (never contents),
  and refuses to fetch until the owner completes the OAuth step recorded in
  `tasks-or-issues/overnight-owner-actions-2026-09-24.md`. The HTTP fetch path is
  implemented but **has never been executed on this machine** and is reported as
  `UNVERIFIED` / `fetch_path_executed: false` everywhere. The Gmail payload →
  signal conversion *is* covered by fixtures, so only the HTTP call is untested.

**Evidence.** `python career-ops/run_application_inbox_acceptance.py` runs 33
checks: the repo fixture mailbox, a synthetic mailbox generated at run time from
the canonical workbooks' own rows (so real matching and real proposals are
exercised without copying owner records into the repo), idempotent replay,
workbook-hash verification, the guard refusals and the Gmail refusal. It writes
`audits/evidence/<stamp>-application-inbox-status-monitor/acceptance.json` + `.md`;
raw signals stay in the git-ignored `status-store/`. Evidence modes are labelled
separately and **no live-mailbox evidence is claimed**.

### Tests

    python -m pytest career-ops/tests/test_application_inbox.py -q   # 87 passed
    python -m pytest career-ops/tests/ -q                            # 207 passed

## JobBrief + company/role research (2026-09-24)

Roster **B13** (Job Description Analyzer) and **B14** (Company/Role Research Brief).

    python career-ops/job_intelligence.py schema
    python career-ops/job_intelligence.py brief --job-record REC.json --jd-file JD.txt \
        [--research-file RESEARCH.json] [--out DIR] [--out-record FILE] [--stamp S]
    python career-ops/job_intelligence.py research --brief JOB_BRIEF.json [--research-file F]
    python career-ops/job_intelligence.py validate --brief JOB_BRIEF.json

`--job-record` / `--jd-file` / `--research-file` are **inputs** and are never
written to; `--out` / `--out-record` are outputs. The command refuses to run if an
output path would overwrite one of its own inputs.

`job_brief_schema.json` is the committed JobBrief contract; `brief` refuses to
report success unless the brief validates against it and contains no
first-person candidate claim.

Truthfulness rules the analyzer enforces:

* **Extractive only.** Every requirement, responsibility, eligibility condition
  and keyword is a verbatim posting line with its 1-based `source_line` and the
  section it came from. Lines the posting presents in a desirable/preferred
  section (or marks inline) become `kind: "desirable"`, are mirrored into
  `preferences` with an explicit note, and can never appear as an essential
  requirement. Labelled posting terms (`Location: …`, `Right to work: …`) are
  routed out of the requirements bucket entirely.
* **No candidate claims.** The brief carries `candidate_claims: []`, a
  first-person-claim scanner, and no candidate data except provenance hashes of
  the canonical `cv.md` / `config/profile.yml`.
* **Eligibility is never assumed.** A posted right-to-work/clearance/degree
  condition is `satisfied_by_owner_source` only when a canonical owner source
  states it (citing that file and line); anything else is `unknown` and raises a
  blocker risk. A region the owner has not stated (e.g. a UAE work permit) stays
  unknown.
* **Research never guesses.** Company facts are accepted only from a provider
  file and only with `source` + `citation`; uncited facts are rejected and
  listed. With no provider the brief records `research.status =
  "research_needed"` plus the exact list of what it wanted. The `http` provider
  is disabled (no owner-approved endpoint) and the `browser` provider is
  disabled by the owner's GUI-safety directive, and neither is ever launched.
* **Handoff is explicit.** `source_supported_facts` is the only content handed
  to the CV / cover-letter workflows; `handoff_jd_text()` joins those verbatim
  lines in source order.

## Application Pack Reviewer + Submission Gate (2026-09-24)

Roster **B17** (independent truth & completeness gate) and **B18** (deterministic
owner submission gate).

    python career-ops/application_pack_review.py review --brief JOB_BRIEF.json \
        --cv-draft CV.md --cover-payload PAYLOAD.json [--cover-html HTML] \
        [--draft-result JSON] [--jd-file JD.txt] [--handoff-text T.txt] [--out DIR]

    python career-ops/submission_gate.py actions
    python career-ops/submission_gate.py guard --action submit_application
    python career-ops/submission_gate.py status --review PACK_REVIEW.json [--approval F]

The reviewer is a **separate module** that re-reads the artifacts, the posting
file and the canonical sources and re-derives every verdict itself. It is
independent *re-derivation*, not a second model or an independent AI opinion, and
not a substitute for owner review — that limit is recorded in its own output.
It reports five areas: truthfulness (verbatim-only drafts, no invented metric or
first-person claim, install fact-gate verdicts), requirement coverage
(essential vs desirable kept separate), consistency (job identity, every posting
citation re-checked against the posting, handoff composition, candidate name),
formatting/export readiness, and unresolved unknowns. Verdict is `pass`,
`pass_with_owner_input_required` or `block`; only truthfulness / consistency /
formatting defects can block.

The submission gate implements **no submission path**. It refuses on a blocked
review, on unverified truthfulness, on a missing approval, on an approval that
does not bind this exact pack (`pack_id` + `pack_sha256`), on a pack that changed
after approval, on an unacknowledged unresolved unknown, and on an approval file
located inside the repository (a committed file is not an owner action). A valid
approval from outside the repository yields
`approved_pending_owner_manual_submission` plus an owner checklist — and
`external_action_performed: false` on every decision. Every decision is appended
to `runtime/career-ops/job-intelligence/submission-gate-log.jsonl`.

### Acceptance runner

    python career-ops/run_job_intelligence_acceptance.py [--stamp S]

Runs the whole path on labelled synthetic fixtures: job record -> JobBrief ->
research (no provider / cited / uncited) -> handoff -> CV + cover-letter drafts
-> reviewer -> tamper proof (a deliberately falsified pack must be blocked) ->
submission gate (no approval / forged in-repo / stale / valid external). It
writes `audits/evidence/<stamp>-job-intelligence-and-application-pack/` and fails
unless every critical check holds.

### Tests

    python -m pytest career-ops/tests/test_job_intelligence.py -q   # 38 passed

## Interview Prep Agent (B22, 2026-09-24)

`career-ops/interview_prep.py` turns a canonical JobBrief plus the canonical owner
sources into a role-specific preparation pack. It is deterministic: no model call,
no network call, no browser.

    python career-ops/interview_prep.py pack --brief JOB_BRIEF.json [--research-file F] \
        [--out DIR] [--stamp S]
    python career-ops/interview_prep.py from-job --region uk --jd-file JD.txt \
        [--job-record REC.json | --id ID | --url URL | --row N | --pipeline-index N] \
        [--research-file F] [--out DIR] [--stamp S]
    python career-ops/interview_prep.py validate --pack PACK.json
    python career-ops/interview_prep.py schema
    python career-ops/interview_prep.py status

`from-job` resolves the job from Career Ops state, builds the JobBrief with
`job_intelligence.build_brief`, and then builds the pack. `pack` takes an existing
brief. `--brief` / `--jd-file` / `--job-record` / `--research-file` are inputs and
are never written to; the command refuses to run if an output path would overwrite
one of its own inputs. The contract is committed as `interview_prep_schema.json`.

Sections produced (`interview_prep_pack.json` + `.md`):

| Section | Content |
|---|---|
| `technical_prep` | one preparation prompt per essential requirement and per responsibility |
| `behavioural_prep` | themes, each tied to a posting responsibility when one matches, otherwise labelled a standard theme |
| `likely_questions` | the bounded union of the above plus motivation and eligibility prompts |
| `evidence_backed_talking_points` | `cv.md` lines quoted verbatim with `cv.md:<line>` refs, or an explicit owner action |
| `questions_to_ask_employer` | drawn only from the brief's own unknowns |
| `unknowns` | eligibility unknowns, brief risks, missing research, requirements with no canonical evidence |

Truthfulness rules the agent enforces:

* **A generated question is never presented as an employer's question.** Every
  question carries `employer_supplied: false`, the verbatim posting line and source
  line it was derived from, and a note saying it was generated by template.
* **Talking points quote, they do not paraphrase.** Each quote is a canonical CV
  line verified against `cv.md` at the line it claims; `quote_violations` must be
  empty. A deliberately altered quote fails the check (tested).
* **A match on a general domain word is not evidence.** `evidence_matching.general_terms`
  (security, data, analysis, …) are removed before scoring, so a line that only
  shares "security" with a requirement is not dressed up as evidence. A qualification
  requirement is answered from the canonical qualification headings instead
  (`qualification_section_patterns`).
* **Nothing is invented for a gap.** Where the posting asks for something the
  canonical sources do not evidence, the item is `owner_input_required` with an
  explicit owner action.
* **Company context is cited or absent.** Facts come only from the brief's cited
  research; with no provider the pack records `research_needed`.
* **No candidate claim.** `candidate_claims` and `external_actions_taken` are empty,
  a first-person-claim scanner runs over every generated (non-quoted) field, and
  `interview_scheduled` / `interview_attended` are always `false`.

### Acceptance runner

    python career-ops/run_interview_prep_acceptance.py [--stamp S]

27 checks over labelled synthetic fixtures: LinkedIn read-only intake contract,
the three outreach variants with their unsent state and provenance, the owner action
gate refusals, the pack build from Brief + cited research + canonical sources,
an independent re-read of `cv.md` confirming every quote, tamper detection
(quote / injected claim / employer-supplied question), the honest-unknowns path
(unmatched requirement → owner action, UAE eligibility staying `unknown` with no
invented right-to-work statement), determinism, and a before/after hash proof that
no canonical source or tracker changed. Writes
`audits/evidence/<stamp>-linkedin-outreach-interview-prep/`.

## Acceptance runner

    python career-ops/run_rollover_acceptance.py [--stamp S] [--month YYYY-MM]

The reversible B09 acceptance run, on a dated **copy** of every canonical
workbook (the canonical files are only read):

    tracker writer append (2 probe rows, .invalid) -> rollover plan (read-only)
      -> archive written + verified -> month rotated out of the copy
      -> rotated rows present in the cross-month index and re-added postings
         refused as duplicate-cross-month -> second run changes nothing
      -> copy restored byte-identically from the rollover backup, then the
         archive removed and its keys gone from the index
      -> run-health for both workers

It writes `audits/evidence/<stamp>-career-ops-monthly-rollover/acceptance-<stamp>.json`
(aggregate only — counts, statuses, hashes, file names) and fails unless every
region reached `written`, every archive verified with the canonical sheet set,
every rotated row was refused as `duplicate-cross-month` with zero appends, the
rollback restored the copy byte-identically, the run-health documents stayed
aggregate-only, and all four canonical workbooks are hash-identical before and
after.

## Acceptance runner (CV + LinkedIn)

    python career-ops/run_cv_linkedin_acceptance.py [--region uk] [--stamp S]

Exercises the representative path end to end with fixtures:

    Career Ops job record -> tailored CV draft + cover-letter draft (+ install fact gate)
                          -> LinkedIn read-only intake + drafts (unsent)
                          -> dedupe against Career Ops + Company Watch
                          -> tracker handoff (dry-run, then a dated COPY)
                          -> Chief summary

It writes `audits/evidence/<stamp>-cv-linkedin-workflows/acceptance.json` + `.md`
and fails unless every critical check holds. Encoded guarantees: every CV draft
line is verbatim `cv.md` text; the fact gate did not block; the cover letter was
rendered by the install's own renderer (with no browser launched); the read-only
contract holds (`network_used=false`, `urls_fetched=0`, `browser_launched=false`,
`account_mutations=0`); every external LinkedIn action is refused; the canonical
workbooks are hash-identical before and after; the append happened on a copy with a
hash-verified backup and a verified rollback; and a replayed LinkedIn posting is
deduped.

## Career Daily Brief / Pipeline Prioritizer (B23, 2026-09-24)

`career-ops/daily_brief.py` + `career-ops/daily_brief_config.json`. A **read-only
aggregator**: it does not own any career state, it restates what the other
workers already recorded, and it writes nothing outside its own runtime
directory (`runtime/career-ops/daily-brief/`, git-ignored).

    python career-ops/daily_brief.py inputs
    python career-ops/daily_brief.py policy
    python career-ops/daily_brief.py build [--window-hours 24] [--now ISO] [--dry-run]
    python career-ops/daily_brief.py summary [--latest | --brief FILE]
    python career-ops/daily_brief.py status

**Inputs (all read-only, each labelled present/absent with a hash):**

| input | owner | used for |
|---|---|---|
| `runtime/career-ops/scan-runs/regional-run-state.json` + run-health files | regional job-search workers | scan health, accepted/rejected, duplicates, new offers |
| canonical regional workbooks via `tracker_writer.py` | Career Ops (Excel) | row counts, status counts, deadline column, newly added rows |
| `runtime/company-watch/findings-uk-latest.json` (+ registry, aggregate only) | Company Watch | findings counts and freshness |
| Application Inbox monitor stores via `application_inbox.build_summary()` | Application Inbox | status-change proposals, monitor-raised owner actions |
| Interview Prep packs | `interview_prep.py` | interview/follow-up artifacts |
| `tasks-or-issues/overnight-owner-actions-2026-09-24.md` | owner | open owner actions |
| JobBriefs, LinkedIn handoffs, submission-gate log | the workflows above | output counts only |

**Priority policy (declared, deterministic, versioned).** Five explicit inputs
with declared weights — deadline 40, application stage 20, eligibility certainty
15, freshness 15, owner flag 10. The score is taken over the **full** policy
weight, so an UNKNOWN input lowers the score rather than being imputed; each item
reports its `components` (value, weight, contribution, observed value), its
`coverage_pct`, its UNKNOWN inputs, and any override that fired:

* `urgent_deadline` — a deadline within 3 days raises the class to at least P2;
* `owner_action_min_class` — an item only the owner can action is raised to at least P2;
* `unscoreable` — no known policy input at all is reported at P4 *and labelled*, never silently scored.

The brief records `score_semantics.kind = "deterministic_policy_output"`: the
score is a policy output, **not** a claim about the vacancy or the candidate.
Statuses outside the declared vocabulary, trackers with no deadline column, and
regions with no recorded work-authorisation position all become named UNKNOWNs —
the UK tracker has no deadline column, so deadline is UNKNOWN for every UK row,
and Dubai/Japan/Singapore work authorisation stays UNKNOWN on every record.

**Idempotency.** The brief content is digested with `generated_at`, `brief_id`,
`content_digest` and the `delivery` block excluded. Where the content digest
matches, the existing digest-named file is left untouched: a repeat run over
unchanged inputs writes **no new bytes**, only appends to `run-log.jsonl`, and
reports `idempotent: true`.

The brief's identity is "the state as of the end of a window", not "the state at
the instant this process happened to run", so the as-of clock is floored to
`window.quantize_minutes` (default **60**, `0` disables it). Two runs inside the
same quantum over unchanged artifacts are therefore the *same* brief — same
`brief_id` (stamped with the brief's own `as_of`, not the run clock) and same
digest — and the second writes no bytes; `generated_at` keeps the true run
instant and is excluded from the digest. Crossing a quantum boundary moves the
window, which is genuinely different content and therefore a new brief.

The digest-named file and the `latest.*` pointers keep the rendering (and so the
`brief_id`/`generated_at`) of the run that first produced a given content digest:
a re-run over the same content recognises it as the same brief and restamps
nothing. Under the current revision that is a fixed point — identical content
implies an identical id — so a stored brief never names a brief the code would no
longer produce.

**Delivery.** Local file only, verified by sha256 read-back: `brief-<digest>.json`
(machine-readable), `chief-summary-<digest>.md`, plus `latest.json` / `latest.md`.
`delivery.external_channel_health` is `not_verified` — nothing sends, posts or
notifies, and no messaging channel is assumed healthy.

**Scheduling.** `ChiefCareerBrief` runs daily at **07:00** via
`career-ops/run_scheduled_brief.cmd`:

    python career-ops/install_schedules.py --install-brief
    python career-ops/install_schedules.py --remove-brief
    python career-ops/install_schedules.py --status          # includes the brief task

The schedule makes the brief *available* in the morning; it is not a delivery
channel and does not claim one.

**Acceptance runner**

    python career-ops/run_daily_brief_acceptance.py [--stamp S]

Writes `audits/evidence/<stamp>-career-daily-brief/acceptance.json` + `.md` —
**34/34 critical checks** at the time of writing. Encoded guarantees: the live
brief validates structurally; an empty-input run still builds and labels every
absent input (never as healthy or as zero); a partial-input run names the missing
sources and invents no owner action; a repeat run is byte-neutral and
idempotent **and a run inside the same declared as-of quantum is the same brief**;
every score equals the sum of its declared components with no unknown
input also reported as known; every required section (scan health, newly added
jobs, duplicates suppressed, application-status changes, interview/follow-up
items, owner actions) is present, with unavailable ones saying so; canonical
workbooks are hash-identical before and after; zero submissions/messages/writes;
no external channel claimed; the Chief summary is concise; and the morning
schedule + launcher exist with the task state read from Task Scheduler.

## High-recall semantic discovery pipeline (B25, 2026-09-24)

**Why it exists.** The owner's own `portals.yml` title filter is
`positive = [Intern, Internship]`. Used as a *required discovery gate* it is a
precision filter, and it produced the reported false zero: a UK scan processed
~2861 postings and Company Watch found 19 new ones, while 0 were tracker-eligible
because no title contained the literal word "Intern". Standalone Codex found
roles in the same market. The fix is not to drop the deterministic controls; it
is to put the semantics back in the middle of the funnel.

```
broad collection (existing Career Ops lanes + Company Watch)
  -> light deterministic prefilter        career-ops/discovery/title_policy.py
  -> DeepSeek bulk semantic triage        career-ops/discovery/classifiers.py
  -> bounded Codex second pass            (ambiguous / high-value only)
  -> deterministic eligibility gates      location, work authorisation, clearance,
                                          mandatory experience, application URL
  -> shared dedupe                        career-ops/tracker_writer.py primitives
  -> tracker manifest / Chief brief       manifest only; --apply stays explicit
```

**Two-tier title policy.** `high_recall` is the default discovery mode; the
owner's original rule stays available unchanged as `intern_only`.

* Tier A (recall) accepts a title only when it carries **both** an early-career
  level signal (graduate / junior / analyst / analyst I / L1 / intern / trainee /
  associate / apprentice / …) **and** a cyber/IT-security/technology-risk
  discipline signal (SOC, cyber security, information security, GRC, IAM,
  vulnerability, technology risk, security consulting, IT support, …).
  The generic word "security" alone is never sufficient, and explicit non-cyber
  signals (physical security, security guard, sales, marketing, credit risk, …)
  reject the title.
* Tier B (hard negatives) rejects clearly senior/leadership titles. The owner's
  own negative list is kept verbatim (`Senior`, `Principal`, `Lead `, `Manager`,
  `Director`, `Head of`, `Vice President`, `VP `, `Staff Security`) plus a small
  explicitly listed addition set (`chief`, `ciso`, `executive`, `team lead`,
  `technical lead`, `group manager`).
* The prefilter is **not** the eligibility decision: the authoritative gates run
  after semantic classification and cannot be overridden by a model.

**Semantic contract.** One closed label set —
`strong_entry_level_match`, `plausible_entry_level`, `ambiguous_review`,
`too_senior`, `wrong_discipline`, `hard_eligibility_block`. Every classification
carries its source fields, reasons, uncertainty, confidence (or an explicit
`null`), and provider/model provenance including whether the model identity was
observed. A deterministic guard rejects any classification that asserts a number,
quoted text or fact-class claim (years / sponsorship / clearance / citizenship /
degree / visa / salary) that is not in the source record. Where no JD text exists
the record says `jd_available=false` and
`classification_basis=title_company_location_only`, and the classification is
explicitly **not** semantic JD analysis.

**Provider routing.** DeepSeek is the bulk classifier for the whole pool (batched,
provider-reported usage only). Codex is called **only** for candidates that meet
the declared escalation conditions (`ambiguous_review`,
`deepseek_confidence_below_0.60`, `high_value_plausible_without_jd_text`) and only
up to `--codex-budget` (default 8) per run; candidates dropped for budget are
recorded as such. The second-pass verdict replaces the first-pass label and the
first pass is preserved on the record (`reviewed_first_pass`).

**Funnel metrics make a zero explainable.** `discovered_raw`,
`after_hard_negative_prefilter`, `semantically_reviewed`, `deepseek_accept`,
`codex_escalated`, `codex_accept`, `deterministic_eligibility_pass`,
`duplicates_removed`, `tracker_candidates`, plus `rejections_by_reason`,
`not_applicable_stages` (a stage disabled by configuration is not a funnel zero)
and `zero_attribution` naming the first empty stage with its cause. A run limit is
recorded as a limit, never as a market fact.

**Company Watch is in the same funnel.** Its findings enter as candidates; the
findings excluded beforehand are counted with their own Company Watch reason
(`duplicate-in-run`, `routed_other_region:<r>`), so 19 findings cannot silently
become "0 jobs".

**Every remaining read-only discovery surface is in the same funnel too (2026-09-24).**
`SOURCE_REGISTRY` names the surfaces — explicit records, regional scan record, Company
Watch, **recruiter/intermediary watch** (B11) and **LinkedIn owner export** (B19) — and
each one is added as a *collector* that returns the same collection-block shape. No
surface gets a second classifier, a second eligibility rule set or a second dedupe
engine.

* `collect_from_recruiter_watch()` reads a **declared** read-only findings export
  (intermediary/agency, employer, title, location, URL, `decision`, `region_route`,
  attribution confidence). Findings the watch itself excluded keep their own reason
  (`recruiter_watch_decision:<d>`, `routed_other_region:<r>`). No agency or employer is
  ever contacted, and **no live recruiter-watch feed was scanned** — the collector reads
  a declared export shape and records that boundary.
* `collect_from_linkedin()` reads an **owner-exported** `.json/.jsonl/.csv/.md/.txt` file
  through the *existing* `linkedin_workflow.parse_inbox_file` + `classify` path, so there
  is exactly one LinkedIn parser. Only `job_signal`s become candidates; company-only
  signals and URL-less lines are counted in coverage and never guessed into postings.
  There is no login, API, session, scrape, browser, post, message, connection request or
  application anywhere in this path.

**One vacancy → one canonical candidate.** `collapse_candidates()` runs first: canonical
identity is the normalised posting URL (`tracker_writer.normalize_url` — the same code the
tracker dedupe uses, which now also drops any `utm_*` parameter) or, when no URL exists,
company + title. The richest copy wins, missing fields are filled from the other copies,
nothing is invented, and every discovery is preserved in the candidate's `provenance`
(collection surface, declared source, source detail, raw index) beside `sources` and
`duplicate_discoveries`. The collapse is reported as `cross_source_dedupe` and is in-run
identity only — it never replaces the shared tracker dedupe, and it is never presented as a
market fact.

**Per-source funnel metrics.** `funnel.by_source[source]` carries that surface's own stage
counts, its own `rejections_by_reason`, its own `not_applicable_stages` and its own
`zero_attribution` naming the first empty stage and cause, so a source that produced zero
tracker candidates says where *it* went to zero. A canonical candidate discovered by
several surfaces is counted once in each of them and the overlap is recorded explicitly in
`funnel.shared_candidates`.

### Commands

    python career-ops/discovery/pipeline.py policy               # modes + contract + source registry
    python career-ops/discovery/pipeline.py selftest             # title regression fixtures
    python career-ops/discovery/pipeline.py run --region uk \\
        --scan-record runtime/career-ops/scan-runs/regional-run-uk-*.json \\
        --company-watch runtime/company-watch/findings-uk-latest.json \\
        --recruiter-watch <recruiter-watch-findings-export.json> \\
        --linkedin <owner-exported-linkedin-jobs.json> \\
        --semantic deepseek --codex-budget 4 --max-candidates 60

    python career-ops/discovery/pipeline.py compare-modes --region uk \\
        --records <captured-candidate-set.json>

`compare-modes` runs the old strict intern-only policy and the new high-recall
pipeline over the **same** candidate set and reports the recall delta without
writing a canonical workbook, a manifest or a tracker probe.

### Measured evidence (2026-09-24, bounded live pass)

`audits/evidence/2026-09-24T04-58-25Z-career-high-recall-discovery/` — over the
same 506-candidate captured set: `intern_only` title pass 3 → **0** tracker
candidates; `high_recall` title pass 15 → **4** tracker candidates (+12 titles,
+4 candidates, 0 lost). The funnel run itself: `discovered_raw=60`,
`after_hard_negative_prefilter=6`, `semantically_reviewed=6`, `deepseek_accept=1`,
`codex_escalated=3`, `codex_accept=0`, `deterministic_eligibility_pass=0`,
`tracker_candidates=0` with the first zero stage and its cause recorded. DeepSeek
was called twice (bulk), Codex once (bounded). No canonical workbook, application,
contact, browser or account action.

Two limitations are recorded, not hidden: (1) the Career Ops scan exposes no
job-description text or posting URL for offers, so semantic labels there are
title/company/location-based and explicitly not JD analysis — the contract and
the fallback path exist so nothing is guessed; (2) a live DeepSeek response can
consume its whole completion budget on reasoning and return empty content, so the
bulk classifier now uses an 8192-token budget and retries a failed batch once in
halves, recording an empty response as a provider failure rather than a zero.

### Acceptance runner

    python career-ops/run_discovery_acceptance.py     # 22/22 checks, fixtures only

It proves the recall fixtures, the preserved narrow mode, the contract guard, the
escalation budget cap, the full counter set with per-rejection reasons, the
`compare-modes` delta, the unified read-only surfaces (B11 + B19 normalising into the
same schema and funnel), the cross-source collapse of one vacancy to one canonical
candidate with its provenance preserved, the per-source counters and zero attribution,
and that the four canonical workbooks are byte-identical before and after. No live
source and no provider call.

### Tests

    python -m pytest career-ops/tests/test_unified_discovery_sources.py -q  # 24 passed
    python -m pytest career-ops/tests/test_discovery_pipeline.py -q  # 36 passed

## Tests

    python -m pytest career-ops/tests/ -q                      # 399 passed (2026-09-24)
    python -m pytest career-ops/tests/test_cv_workflow.py -q    # 21 passed
    python -m pytest career-ops/tests/test_daily_brief.py -q    # 28 passed (B23 + discovery funnel section)
    python -m pytest career-ops/tests/test_interview_prep.py -q    # 26 passed
    python -m pytest career-ops/tests/test_job_intelligence.py -q  # 41 passed
    python -m pytest career-ops/tests/test_linkedin_workflow.py -q  # 38 passed
    python -m pytest career-ops/tests/test_regional_job_search.py -q  # 32 passed
    python -m pytest career-ops/tests/test_tracker_rollover.py -q  # 32 passed (B09)
    python -m pytest career-ops/tests/test_unified_discovery_sources.py -q  # 24 passed (B11 + B19 funnel)

Offline and non-destructive: the canonical CV assets and the canonical workbooks
are only ever read, and every write in a test goes to `tmp_path`.

## Explicit non-goals / gates

* No application submission, no employer or recruiter contact, no external
  messages — by construction and by owner policy.
* Tracker writes are never performed unattended; `--apply` is an explicit call.
* The Career Ops git repository is not initialised, restructured or committed to.
