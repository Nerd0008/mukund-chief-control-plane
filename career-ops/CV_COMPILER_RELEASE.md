# Approved CV flow compiler — 2026-10-09

Owner visual acceptance: "Perfect", followed by authorization to finish Hermes integration.
Source PDF remains unchanged: b5a4e2ae8a845e020661819c7ecaecdd80a9fc793981dec93ea6be4d2cf7db58.
The approved separate template uses 11 pt section headings, upright bold BCA and continuous 11 pt body/bullet spacing.

Native integration: existing `career-cv-golden-guard` plugin now loads `hermes_cv_compiler_guard`.
`career_cv_compile(jd, job_id)` is the production entrypoint. `career_cv_master` returns professional
facts/design rules; `career_cv_build` returns RETIRED, not a glyph-edit renderer. The legacy code/history
remains available for audit but is not registered as the active CV builder.

Content planner uses the existing native Nous provider, LongCat reasoning enabled, and a source-traceable
wording bank. The bank currently offers original/security-oriented and engineering-oriented alternatives;
the model reasons over those choices, not unrestricted unverified paraphrases. No contact details enter
the planner payload. No provider, billing, credentials, E3 or tracker configuration changes.

Budgets: target 120 seconds, compiler hard ceiling 180 seconds (remaining native CV job time), one main
planning call plus at most one targeted shortening call, at most two renders, one compiler invocation
per native job. Native CV turns capped at four. A CV-only daemon watchdog uses Hermes' existing hard
interrupt/process-reaper seam at the job deadline; non-CV budgets remain unchanged.

Delivery requires a PASS report, exact output/dependency hashes, unchanged before/after dependency
hashes and a fresh independent structural/text/font/spacing/pixel verification. The actual lazy-loaded
Discord adapter is guarded via the native platform handler. Renaming an unverified CV does not bypass
the content/name attachment check. Failed intermediate PDFs and master substitution are forbidden.

Validation before deployment: 54 focused compiler/integration tests passed. Eight role-family offline
keyword-selection tests passed, each under one second, without modifying the format engine between JDs.
These are layout/safety tests, not live LLM quality qualification. The previous Allstate native reasoning
test passed in 22.391 seconds. In the newly owner-approved live role-family run, the first SOC test timed
out at 93.219 seconds, with one Nous/LongCat request, zero renders and no PDF delivered. The harness stopped;
the remaining seven live role-family calls were not sent. No blind retry. See private/local live run paths
in the acceptance JSON. This provider availability failure is not represented as a format-engine PASS.

Dependency installed in Hermes Python: reportlab==4.4.9. Runtime deployment/restart and registration
evidence are recorded separately after verification. No main merge and no Discord test message initiated.
