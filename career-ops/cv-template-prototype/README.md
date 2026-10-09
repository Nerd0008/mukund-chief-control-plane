# CV flow-template prototype - design accepted, deployment pending

Date: 2026-10-09. Branch: fix/e3-whole-repo-architecture. No deployment.

UPDATE: Mukund accepted the reproduction ("its perfect"). See approval.json
and ALLSTATE_ACCEPTANCE.md for the reasoning-enabled native Allstate sample:
22.391 seconds, one call/render, PASS. General Hermes reasoning is unchanged.
The model chooses source-grounded wording variants; arbitrary fact invention
is still rejected. This is a prototype, not a live route replacement.

Permanent owner content rule: every tailored professional summary must promote
MSc Information Security, CompTIA Security+ and ISC2 Certified in Cybersecurity
(CC). This is enforced locally, not merely requested in the model prompt.
The Allstate summary was updated locally with these credentials foregrounded;
no additional provider call was necessary. The approved layout remains intact.

Owner typography revision: all six section headings are standardized to exactly
11 pt Times New Roman Bold (layout v2). This deliberately supersedes the supplied
PDF's varying heading sizes, including its smaller Certifications heading.
The source PDFs remain unchanged; body/role/name font sizes remain unchanged.

## Corrected source

The owner superseded the previous CV_FORMAT_MASTER.pdf with
Downloads/Mukund_Didwania_Tencent_Cyber_Security_Intern_CV.pdf.pdf.
SHA-256: b5a4e2ae8a845e020661819c7ecaecdd80a9fc793981dec93ea6be4d2cf7db58.
source-master.pdf is a byte-identical separate reference copy. Neither source
nor the previously deployed master is overwritten. The old live CV route is
unchanged and remains unaccepted by the owner.

## Architecture

layout.json is the versioned editable specification: 49 logical paragraph
slots, 22 variable slots, seven regions (including header), six fixed section
headings, fixed positions, embedded Times New Roman font/style rules and
rendered line/height/width capacities. The model never supplies geometry,
markup, fonts or section order. ReportLab Paragraph performs genuine word
flow within slots; skill values follow labels directly. No PDF redaction,
absolute glyph replacement or original character-count requirement.

extract_template.py is a ONE-TIME authoring utility, not an application tool.
It joins source lines into logical paragraphs. This version reproduces the
original content, including the source qualifications and chronology.
Education's source line break is retained; variable body paragraphs flow.

## Evidence and limits

output/original-content-reproduction.pdf contains the full original content.
output/side-by-side.png shows owner source left and reconstruction right.
output/structural-comparison.json compares page size/count, section order,
source content and typography. Text equality normalizes extraction whitespace
and punctuation spacing, not words or qualifications. Visual resemblance is
not pixel identity: some word wrap, rule placement and bullet spacing differ.
Owner visual acceptance of this reproduction was recorded in approval.json.
Automated PASS is not production deployment approval or varied-JD qualification.

output/varied-jd-offline-timings.json records eight zero-provider role-family
exercises: six existing application JDs, one existing SOC fixture and one
explicit synthetic security-consulting fixture. A deterministic extractive
selector chooses a source sentence for the profile. This proves bounded flow
and stability for those changes ONLY, not full LLM tailoring quality. The same
renderer hash is checked throughout. No provider calls, live tool registrations,
Discord messages or runtime config changes occurred.

## Bounded compiler harness

cv_compile_prototype.py isolates an injected content adapter in a killable
spawned process. One initial content call, at most one targeted shortening
call, at most two renders (currently one after fit), no re-entry into an
occupied job workspace. Default hard budget 180 seconds, never increasable;
target 120 seconds. Parent termination cancels the worker at the deadline.
Analysis and returned content drafts persist; failure/timeout never returns a
PDF path or substitutes the master. Only approved slot content can shorten.
Windows deny-write handles and before/after hashes protect source, template,
compiler and fonts for the job. No renderer/tool repair loop is exposed.

The provenance validator permits source text plus engineering-curated,
source-traceable alternatives in fact_bank.json. Arbitrary unverified
paraphrases and new claims fail closed. A native model planner selects wording
for all editable slots in one call. The Allstate acceptance measures actual
provider latency; broad free-form generation is not yet implemented/qualified.
The generic adapter injection is an offline engineering seam, not an exposed
Hermes tool or sandbox for arbitrary untrusted Python.

## Validation

Checks include intended vs extracted text for every slot, page dimensions and
count, capacity by actual wrapped lines/width, slot bounds, fonts/sizes, normal
bullet/profile emphasis, immutable template run emphasis and baseline spacing.
Static pixels are compared to the reproduction, masking only changed slot
regions at 144 DPI. Documented raster tolerance: RGB difference <=16 and a
one-pixel mask boundary. This reference is NOT yet an owner-approved baseline.
Tests inject missing neighbour text, font changes, moved baselines, overflows,
arbitrary bold and extra pages; actual unexpected pixels fail verification.
No output is registered for live Discord delivery.

Dependencies: Python 3.11+, ReportLab 4.4.9, PyMuPDF, Pillow, pytest for tests;
Windows Times New Roman fonts. Prototype runs used bundled artifact dependencies
and the existing Hermes pytest environment. No dependency install/runtime
deployment occurred. Tests run without real provider calls.

## Next gate

The reproduction was accepted. Qualify the content contract against varied
JDs and the independent delivery gate before deliberately replacing Hermes
CV routing. Do not call this production-ready or deploy it on tests alone.
## Current runtime status — 2026-10-09

The owner approved the final spacing/typography and authorized integration. The existing Hermes
CV plugin now registers `career_cv_compile(jd, job_id)` through `hermes_cv_compiler_guard`.
The production release/limitations are documented in `../CV_COMPILER_RELEASE.md` and
`output/hermes-deployment-acceptance.json`. Historical prototype flags/evidence below describe
earlier checkpoints, not the current gateway state. Final focused regression: 86 passed.
Eight offline role families pass; live qualification is partial (five passed, three provider
timeouts, eight requests, no retries). Timeout/error never authorizes delivering an intermediate
PDF or substituting the master. Do not interpret deployment as a guarantee of provider availability.
