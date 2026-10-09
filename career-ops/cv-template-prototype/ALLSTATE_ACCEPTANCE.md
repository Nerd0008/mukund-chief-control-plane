# Reasoning-enabled Allstate sample - 2026-10-09

Owner visually accepted the original-content template: "its perfect".
Owner supplied the Allstate Graduate Product Engineer Opportunities 2027 JD:
https://www.allstate.jobs/job/23947981/graduate-product-engineer-opportunities-2027/

Owner explicitly approved sending JD requirements and CV professional facts
(excluding contact details) to the existing Nous/LongCat binding. Initial
automatic approval-review rejection caused ZERO requests; approval was obtained
before proceeding. No credentials or contact details entered the model prompt.

## Actual live evidence

1. Initial plan: truncated, 61.547 s, no render/delivery. Thinking controls were
   absent and 2,200 completion tokens did not produce a complete JSON plan.
2. Corrected non-thinking diagnostic: PASS, 7.188 s, one model call/render.
3. Owner required reasoning retained. Reasoning-enabled revalidation: PASS,
   22.391 s total; planning 21.250 s; render 0.094 s; validation 0.125 s;
   one call, one render, no shortening; 692 reported reasoning tokens;
   finish_reason=stop. Nous / meituan/longcat-2.5-preview:free.

Total live calls across these engineering tests: THREE. No blind retries.
Each request was a separate bounded run; only failed truncated output was
blocked. No failed PDF or untailored-master substitution was delivered.
The last accepted output byte hash equals the diagnostic output despite
reasoning being enabled. Model selects engineering variants for the same JD.

## Current contract

The planning model uses native Hermes credential/provider resolution, reading
the existing explicit binding; it cannot select OpenRouter/E3/MoA transport.
No general Hermes reasoning/configuration setting was changed. CV helper
requests explicitly enable low-effort reasoning plus LongCat thinking; total
completion allowance 8,192, request timeout 90 s, compiler hard wall 180 s.
Low effort is a request setting, not a claim that the provider enforces a
specific reasoning-token cap. Parent process cancellation enforces elapsed cap.

All 22 editable slots receive a plan in one call. Text is resolved from curated
source-grounded wording; 21 slots differ from the master. Skills labels are
bold by template rule, values flow immediately after them, and new wording
does not introduce any unsupported employer/qualification/metric.
fact_bank.json traces every alternative to exact source-slot IDs. Paraphrases
were curated during engineering, not generated as new unchecked facts during
an application. This bank currently covers original and engineering wording;
broad free-form tailoring quality across all role families is NOT proven.

New checks reject missing skill labels, incomplete profile sentences and
underfilled slots leaving unexpected blank lines. Existing typography,
geometry, ATS, outside-edit pixel, immutable-dependency and deadline gates
remain. Code/template/master/font hashes stayed equal during the live job.
No format/layout.json changes were made between prototype approval and sample.

32 focused offline tests pass, 0 fail. Final PDF inspected visually. No Gemini,
Discord, application submission, tracker write or live CV-route deployment.
Existing Hermes production route remains unchanged. This is a reviewed sample
plus a bounded native planner prototype, NOT a completed production rollout.

## Artifacts

output/Mukund_Didwania_Allstate_Product_Engineer_CV.pdf
output/allstate-sample-report.json
output/allstate-content.json
approval.json

Next work: expand/qualify the evidence-selection contract across required JD
families, independently bind current PASS evidence to delivery, and integrate
the single compiler tool with Hermes only after those gates are proven.
