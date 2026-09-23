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
* The UK lane is wired to the existing `portals.yml`/`data/pipeline.md`/
  `data/scan-history.tsv` and runs daily at 23:45 local, matching the historical
  ~23:48 window visible in `data/scan-runs.tsv`.
* Dubai/Japan/Singapore have **no lane config in the Career Ops install** (only the
  UK `portals.yml` exists; the other regions were driven by their shortlist-history
  ledgers). The runner *refuses* rather than scanning UK portals under a regional
  label and records the dependency. Creating those lanes belongs to the pending
  `agent-regional-job-search-agents-and-schedulers-2026-09-23` task.
* Registration is idempotent and reversible:
  `install_schedules.py --install` / `--status` / `--remove`.

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

## Explicit non-goals / gates

* No application submission, no employer or recruiter contact, no external
  messages — by construction and by owner policy.
* Tracker writes are never performed unattended; `--apply` is an explicit call.
* The Career Ops git repository is not initialised, restructured or committed to.
