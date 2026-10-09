# Approved CV flow compiler â€” 2026-10-09

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

Final validation: 86 focused compiler/integration/legacy-safety tests passed (16 historical Pillow
deprecation warnings, zero failures). Eight role-family offline
keyword-selection tests passed, each under 1.4 seconds, without modifying the format engine between JDs.
These are layout/safety tests, not live LLM quality qualification. The previous Allstate native reasoning
test passed in 22.391 seconds. The newly owner-approved live role-family tests made eight requests total,
one per distinct JD, no shortening and no retries. GRC, risk/audit, IT support, graduate digital technology,
and security engineering passed in 60.656â€“83.703 seconds. SOC, consulting and general cyber graduate timed
out in 92.032â€“93.219 seconds, with zero renders and no PDF delivered. Failed cases were not retried.
These provider availability failures are not represented as format-engine PASS results.

Dependency installed in Hermes Python: reportlab==4.4.9. Plugin/skill backups are private under
`%LOCALAPPDATA%/hermes/runtime/career-ops/cv-compiler-backups/`. Initial gateway restart loaded the
compiler. A supported plugin reload did not confirm live adapter rewiring, so a final clean restart
proved the actual lazy Discord adapter guard active, source prefix `0dad524f6b18`. Gateway PID 26288,
Discord connected. The registered native tool passed an offline invocation in 1.141 seconds; no
provider call or message in that check. A real Discord CV generation/delivery has not been tested.
No main merge. No Discord test message initiated, no application submission, tracker write or outreach.

Current status: deployed and locally verified; live provider acceptance PARTIAL (5/8). Provider outages
still cause a bounded failure; this release does not promise every CV request succeeds. The format engine
is not patched per JD. JD text, CV requests and employer job URLs all enter the bounded CV guard.

## CV wording reference (2026-10-09)
Every CV planning/shortening pass must consult the reviewed local policy in
`career-ops/cv-template-prototype/cv_writing_policy.py`, derived from
https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing.
Use specific, factual professional wording; avoid inflated claims, canned filler,
chatbot boilerplate and placeholders. This is writing guidance, not an AI detector.
The compiler enforces narrow wording checks before delivery and protects the policy
as an immutable dependency. Do not change layout, invent facts, or enter a repair
loop to satisfy these checks. The local reference avoids a web dependency in each
three-minute CV job; future source updates require a reviewed policy revision.
Offline validation: 64 passed, 0 failed; zero provider calls.

2026-10-09 wording correction: revised curated sentence boundaries and summary; reject generic self-praise, vague impact, inflated filler, chatbot text, placeholders, contrived contrasts and owner-disallowed semicolons/em dashes. Numeric ranges remain permitted. Both full wording-bank variants fit the unchanged layout. 67 focused tests passed; zero provider calls. Capacity-only fixtures now use two provenance-backed punctuation-compliant bullets so they continue isolating shortening behavior. Existing PDFs are not rewritten.


Encoding incident: owner screenshot showed UTF-8 en-dash bytes decoded as Windows-1252 in numeric ranges. Curated source text repaired. Independent content and extracted-PDF checks reject mojibake, replacement characters and invalid controls even when source and PDF match. 71 tests passed, zero provider calls. Gateway logs prove vision analysis completed at 12:47 despite the subsequent assistant claim that it was locked.


Workday upload recovery: original Allstate and container-only rewrite rejected with blank alert; Turnkey control accepted; Unicode CID font serialization accepted in the same session. Production serialization preserves every character origin from the completed ReportLab flow layout, font family/size and rules, with explicit Unicode maps and deterministic IDs. Existing verification remains mandatory. 72 offline tests passed; no provider call. No application submitted. Workday's internal rejection reason is unavailable; font serialization is the tested compatibility remedy.

