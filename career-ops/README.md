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
| `draft [--out DIR]` | profile/post/outreach drafts from canonical facts, fact-gated, `draft_unsent` | only under `runtime/linkedin/drafts/` (git-ignored) |
| `handoff --region R [--apply]` | hand eligible new signals to the Career Ops writer | dry-run unless `--apply` |
| `guard --action NAME` | refuse an external LinkedIn action, and log the refusal | log only |
| `status` | configuration + last-run summary | no |
| `run` (see the acceptance runner) | end-to-end acceptance path | evidence only |

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

## Acceptance runner

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

## Tests

    python -m pytest career-ops/tests/ -q                      # 88 passed
    python -m pytest career-ops/tests/test_cv_workflow.py -q    # 21 passed
    python -m pytest career-ops/tests/test_linkedin_workflow.py -q  # 34 passed
    python -m pytest career-ops/tests/test_regional_job_search.py -q  # 30 passed

Offline and non-destructive: the canonical CV assets and the canonical workbooks
are only ever read, and every write in a test goes to `tmp_path`.

## Explicit non-goals / gates

* No application submission, no employer or recruiter contact, no external
  messages — by construction and by owner policy.
* Tracker writes are never performed unattended; `--apply` is an explicit call.
* The Career Ops git repository is not initialised, restructured or committed to.
