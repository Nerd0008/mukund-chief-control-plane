---
name: job-application-intake
description: Use when Mukund sends a CV or JD. Log and archive it.
version: 1.0.0
metadata:
  hermes:
    tags: [mukund, career, tracker, applications, excel, intake]
    category: operations
---

# Job application intake

Trigger: Mukund sends a CV and/or a JD, or says a role has been applied for.

## Standing owner instruction (2026-10-03): security-clearance and citizenship filter

> "with any JD I give filter if I need security clearance or UK citizenship if I do stop immediately we cant apply for those roles"

**Run this filter FIRST, before locating the URL, before building anything.** It is the first
step of intake, not a later eligibility note.

Scan the posting text for any of:

- security clearance of any level — BPSS, SC, DV/Developed Vetting, CTC, eDV, "must be able to obtain
  clearance"
- citizenship or nationality conditions — "sole UK national", "no dual nationality", "British citizen",
  "UK national only", "5-year UK residency", "10-year UK residency"
- related gating: defence/national-security clients, "must have lived in the UK for the last N years"

**On a hit: STOP IMMEDIATELY.** Do not build a CV, do not build a cover letter, do not append an
Applied row, do not locate the URL. Report the exact sentence from the posting that triggered it, in
one or two lines, and stop there. Mukund cannot satisfy these conditions, so producing documents
wastes his time and his attention.

- A **desirable** mention is not a hit ("interest in security clearance" is not a requirement); an
  explicit requirement is.
- A **driving licence** requirement is not a clearance hit — report it as a normal gap.
- Do not soften the finding, do not suggest applying anyway, and do not offer to try. "We can't apply"
  is a settled owner decision.
- Do not re-raise it as a question or ask for confirmation. State the hit and stop.
- Record the hit factually in the skill's own history if it is a recurring employer, but keep the
  reply to the triggering sentence.

Worked example — Tetra Tech Graduate Security Consultant (2026-10-03): posting states "This role
requires UK Government security clearance. To be considered, you must be able to obtain UK Developed
Vetting, be a sole UK national (no dual nationality), and have been a UK resident for at least the last
10 years." → stop, no documents, no tracker row.

## Standing owner instruction (2026-09-25)

> "for every cv generated and JD given consider the job applied and maintain an excel
tracker with relevant details including the date applied."

So a supplied CV + JD pair = **Applied**, dated the day it was supplied, recorded in the
canonical regional tracker. Do not ask whether to log it; log it, then report.

## Authoritative resources (never replace these)

- Canonical UK tracker: `C:\Users\mukun\Downloads\codex\uk-cyber-job-tracker.xlsx`
  (also Dubai / Japan / Singapore workbooks in the same directory).
- Append rows: `career-ops/career_ops_cli.py write --region uk --manifest F [--apply]`
- Set application state: `career-ops/application_state.py` (owner-instruction writer)
- Refresh the read-only **Applied** sheet: `career-ops/applied_view.py [--apply]`
- Cover letters: `career-ops/build_cover.py --spec <spec.json>` (locked format, spec-driven)
- School-level education for application forms: `career-ops/records/education/school_education.json`
  (+ the CBSE mark sheets beside it). Not for the CV — used only to answer form fields.
- Profiles/schema: `career-ops/regional_profiles.json`
- All of the above live in `C:\Users\mukun\Documents\mukund-chief-control-plane`.

## Procedure

1. **Extract the documents.** PDFs sent via Discord land in
   `%LOCALAPPDATA%\hermes\cache\documents\`. Use
   `pdftotext -layout <in.pdf> "C:/Users/mukun/AppData/Local/hermes/cache/scratch/out.txt"`.
   Native tools do not understand MSYS paths — pass `C:/...` forward-slash paths, and do
   not write to a bare `/tmp` (TMPDIR here is `/tmp` but is not a real writable dir in
   this shell; `$LOCALAPPDATA/hermes/cache/scratch` always works).
2. **Find the official vacancy URL.** The canonical tracker dedupes on URL and rejects a
   record with no usable URL. Owner-supplied JD PDFs are usually prints of
   `careers.bu-uk.co.uk`-style pages and contain no URL. Get the real one:
   - `https://careers.bu-uk.co.uk/search/?q=&locationsearch=&searchResultView=LIST` lists
     jobs as `careers.bu-uk.co.uk/job/<Slug>/<id>-en_GB`; read it with the browser
     (the ATS `*.jobs2web.com` host is blocked by the fetch tool as a private address).
   - Prefer the employer/ATS URL. Aggregators (LinkedIn, Indeed, Bright Network,
     Glassdoor) are secondary evidence only.
   - Verify the page is still live and re-read the posting end date from it.
   - **Some ATS search forms are ASP.NET postbacks that ignore query strings.** The M Group board
     (`jobs.mgroupltd.com`, which carries Telent and every other M Group subsidiary) returns the full
     455-vacancy list for `?Keywords=`, `?q=`, `?SearchTerm=` and `?keyword=` — the parameters are
     silently dropped. Set the field and click the form's own button instead:
     `document.getElementById('ctl00_ContentContainer_TopSearch_Keywords').value = '<term>'`, then
     click `#ctl00_ContentContainer_TopSearch_btnSearch`. Job URLs come back as
     `jobs.mgroupltd.com/vacancies/<id>/<slug>.html`. If a keyword search returns the unfiltered
     count, suspect a postback form rather than an absent vacancy.
   - **When the site's own search is broken, read its sitemap.** `careers.bdo.co.uk/search/` returns
     an error page for every query, but `careers.bdo.co.uk/sitemap.xml` lists every `/job/<slug>/<id>`
     URL; filter the `<loc>` values in Python. This found the BDO Audit Technology posting in seconds
     after the search UI and the category listings both failed to surface it. Try the sitemap before
     falling back to aggregators.
   - `Page.printToPDF` over CDP times out at 5s on long pages. To archive a posting, use
     `web_extract` (its full text is saved to `%LOCALAPPDATA%\hermes\cache\web\<host>-<hash>.md`)
     rather than driving a print.
3. **Archive the package** at
   `career-ops/applications/<YYYY-MM-DD>-<company-slug>-<role-slug>/` containing
   `jd_*.pdf`, `cv_*.pdf`, `jd.txt`, `cv.txt`, `tracker_manifest.json`, `README.md`.
   The README carries the eligibility assessment and the provenance chain.
4. **Append the row** (dry-run first, then `--apply`). Expect `appended: 1`, a
   hash-verified backup under `runtime/career-ops/backups/`, and `verification.ok: true`.
5. **Set owner state** — the writer deliberately cannot:

       python career-ops/application_state.py --region uk --id J35 \
         --status Applied --priority High \
         --date-selected YYYY-MM-DD --date-applied YYYY-MM-DD \
         --cv-path <relative package path> --notes "..." --fit-score 8.0 --apply

6. **Verify by reading the row back** with openpyxl, and run
   `career_ops_cli.py verify --region uk`. Report the row ID, the tracker hash before/after
   and the backup path.
7. **Refresh the `Applied` sheet** — the owner's at-a-glance list of applied jobs:

       python career-ops/applied_view.py          # dry run
       python career-ops/applied_view.py --apply  # writes, with backup + re-verify

   It is a *derived* view of the Jobs sheet, so never hand-edit it and never create a second
   tracker file. `applied_view.py` snapshots every Jobs cell before and after and aborts if
   anything drifts; it appends the sheet LAST so `sheetnames[0]` stays `"Jobs"`, which
   `tracker_writer.py` asserts. Re-run `career_ops_cli.py verify --region uk` afterwards —
   `ok: true`, `headers_unchanged: true` and the J/K validations intact prove the writer still
   accepts the workbook.

## Pitfalls

- **One tracker, not two.** The owner asked for "a tracker"; a second workbook would recreate
  exactly the problem the September audit flagged (trackers in five locations, no single source
  of truth). Satisfy "create a tracker" by making the *existing* canonical workbook easier to
  read — the `Applied` sheet — never by adding a competing file.
- **A manifest cannot set application state.** `tracker_writer.py` ignores
  `application_status: Applied` by design — "fabricating an application is the single worst
  failure mode here". Owner columns (UK: J, K, S, T, U, V) are written only by
  `application_state.py`, which demands an explicit date and takes a backup.
- **`last_data_row` in `regional_profiles.json` goes stale** as soon as a row is appended.
  Search to `ws.max_row`, not to the profile value.
- **openpyxl holds data validations on the worksheet** (`ws.data_validations.dataValidation`),
  not on the cell; `cell.data_validation` raises AttributeError.
- **Date comparison**: openpyxl returns `datetime` for date-formatted cells, so a naive
  `cell.value != date` re-writes an identical value on every run. Normalise before comparing
  to keep the writer idempotent.
- **Never write the tracker from a scan.** Scheduled discovery is bounded dry-run only.
- The write guard refuses a workbook that changed between read and write — do not fight it,
  re-read and re-apply.

## CV tailoring — immutable golden master

The sole authoritative PDF is `career-ops/master/CV_FORMAT_MASTER.pdf`; its versioned span/layout manifest is `career-ops/master/cv_master_manifest.json`. Never regenerate, edit, redact/reinsert, or repair this master. Do not use the historical Downloads master.

The master is a visual template and a source of verified professional facts, not a wording template. Tailor content freely to each JD, including skill labels and experience/project descriptions; no character-count similarity to original wording is required. Preserve the layout and truthful facts.

Normal application jobs MUST NOT edit cv_tailor.py, cv_golden.py, hermes_cv_guard.py, the manifest or font/layout configuration. Do not extend the renderer during a job, use --force, geometry overrides, font substitution, manual reinsertion, a parallel PDF builder, or an open-ended visual repair loop.

Use the bounded workspace `%LOCALAPPDATA%/hermes/runtime/career-ops/cv-output/<application-job>/` only. Read the JD and immutable manifest; produce `cv_edits.json` with `edits: [{span_id, replace, alternatives}]`. Each original editable span has its own fixed font, origin, rendered-width limits. Supply at most two content-only alternatives. There are at most THREE fit attempts per span, persisted across command re-entry, and ONE PDF render per job. The native CV agent budget is eight turns. Failure ends the job; do not rename the output or launch a new job to evade the budget.

PREFERRED HERMES PATH: call `career_cv_master`, select editable span IDs using the JD, then call `career_cv_build` with content-only edits and up to two alternatives. This tool creates the workspace/edits JSON and invokes the verified renderer directly. No shell commands, git checks, code inspection, execute_code or renderer unlock are required. Do not look for removed include_blanks/bold_prefix/char_budget_exempt/--force repair markers.

CLI maintenance alternative: Run the exact Hermes Python interpreter and canonical absolute `career-ops/cv_tailor.py` entrypoint with --edits and --out. No shell chains. The pipeline takes a fresh master copy, changes only approved glyph streams, then independently verifies all text/geometry/fonts and pixels outside approved span regions. Protected files are held read-only on Windows and hashed before/after.

Deliver ONLY the PDF with a valid adjacent `.verification.json` containing status PASS. The Discord attachment guard independently rechecks the actual artifact. On failure report `CV generation failed`, affected span/element and reason; never attach the intermediate candidate or patch renderer code. Structural/visual verification cannot be waived by owner approval or `ok: true`.

## Application forms — what the owner types in each box

When Mukund asks "what do I write here", answer with **paste-ready strings per box**, short
enough to fit a narrow single-line field, then the reasoning in one line. Do not hand him a
long explanation first.

- **Subjects are filtered to the JD plus the mandatory pair.** Selection rule he set:
  *"it should be relevant to the JD — will HR hiring for cyber sec look at social science?"*
  So list only **English** and **Maths** (every UK scheme filters on these regardless of role)
  plus the domain subjects the JD actually names — IT, Computer Science — and drop Hindi,
  Social Science, Music, Chemistry, Physics unless the role calls for them. All figures must be
  his real marks; selecting which to show is fine, inventing is not.
- **Indian Class X = GCSE stage, Class XII = A-level stage.** UK universities publish the
  equivalence (Class X at 60%+ = GCSE grade 5/B). Say **"No GCSEs - India"** and give the
  equivalent in the same box — a blank reads as *not held*, which is untrue and worse.
- **Quote one consistent Class XII percentage.** CBSE permits best-five (higher) as well as the
  all-subjects figure; pick the conservative all-subjects number and use it everywhere, or a
  recruiter comparing two forms will ask why they differ.

## CV review mode (when a CV is supplied)

Mukund stated on 2026-09-25 that everything on the current CV is real, 100%. Do **not**
re-open disavowed-role questions or push removal of the Colourful Aura entry. Assess fit,
and ask for measurement method only where a figure would have to be defended in an
interview. One question, once.

Useful checks when a JD arrives with a CV:
- eligibility: sponsorship, clearance, citizenship, residency, degree wording
- **Do not raise visa status with the owner.** Owner instruction 2026-10-03: *"do not ever discuss
  my visa status for any application."* Record the eligibility assessment factually in the package
  README for the institutional record, then move on — never put it in the reply, never frame it as a
  blocker or a decision he must make, and never re-raise it. A settled eligibility question is a
  settled owner decision.
- **Never use a clarify prompt in an intake or tailoring run.** Owner instruction 2026-10-03:
  *"auto approve for what you think is best choice."* Choose the best option, state the choice and
  the reason in the return, and keep going. He can reverse a decision he can see; a stalled run
  just costs him time.
- deadline, and whether the process has a fixed assessment-centre date
- whether the posting publishes AI-usage guidance for candidates (BUUK does) — read it
  before any AI-assisted application text is finalised
- which named desirable criteria the CV already evidences, and which are genuinely absent
