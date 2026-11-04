# Application document workflow repair — 4 November 2026

The screenshot attempts at 08:56 and 08:58 completed a single LongCat response with no tool calls. The CV wrapper discarded the final explanation, persisted an empty active application record, then gave the same receipt-only failure on retry. Neither compiler had run.

## Implementation

- `career-ops/application_package_flow.py` saves intake/JD identity before work, checks explicit student eligibility, retrieves all five authoritative owner references, requests a structured plan through the existing workflow router, then directly invokes the existing approved CV and cover compilers.
- Owner instructions and worker preferences are separated from attached employer text. Uploaded cached PDF/DOCX/TXT JDs are supported; arbitrary local paths are refused.
- Receipt schema 2 records intake, JD hash, current phase, eligibility, plan, routing, owner-reference evidence, document results and a bounded phase history. Legacy empty receipts recover the latest JD from history or ask for missing input. Explicit owner clarification resumes the same application without silently changing global profile facts.
- A valid saved document is reused. Failure of the CV does not stop an independently buildable cover. Failed stages retain their precise result and never attach an unverified PDF.
- Directly dispatched turns return `agent_persisted=False`, so the actual gateway saves user/assistant history rather than assuming a bypassed agent loop persisted it.
- Legacy conversational/feedback paths retain safe explanatory text instead of losing it during output transformation. Finished foreground context no longer restricts background memory tools.
- Per-session OS locking prevents duplicate builds. Checkpoint replacement retries only bounded Windows sharing errors; persistent failures remain visible. Existing PDF bytes and receipts survive retry.
- Each application has a 300-second total stage budget: planning at most 60 seconds, existing CV compiler at most its existing 180-second limit, cover rendering at most its existing 45-second limit, all constrained by remaining application time. No unbounded retry loop or provider configuration change was introduced.

The CV renderer/templates, routing-selection policy, factual-gate configuration, tracker, Gmail, LinkedIn and application submission behavior were not changed by this repair. CV-only/cover-only selection and worker preference remain owner-controlled.

## Validation

Private evidence: `C:/Users/mukun/Documents/ChatGPT/CV customizer/output/application-flow-repair-20261104`.

- Focused regression sets passed at 87, 117, 118 and 120 cases as coverage expanded. The final `tests-acceptance.xml` records the final suite including a real Windows read-handle/replacement/release scenario.
- Real-renderer offline test produces two one-page PDFs and simulates a process restart, refusing any rebuild of previously accepted documents.
- The actual gateway transcript persistence method is exercised with a private test store; both user and assistant rows are written with `skip_db=False` for direct dispatch.
- The actual G-Research R3795 JD returns OWNER_INPUT_REQUIRED with the current-student / sandwich-degree / 2029 evidence, without calling either compiler.
- Live private acceptance used the real router and real document compilers for an explicitly fictional eligible role. Both documents returned PASS and verified as one-page PDFs. All five owner references were recorded. Fresh-process retry preserved both SHA-256 values and finalized DOCUMENTS_READY without regenerating either document.
- Live final evidence: `live-acceptance/acceptance-final.json`. CV SHA-256: `47d6d8bad04637c59bb888f6d26ebea8ccbba770891ab255d10fd16cc75bd967`; cover SHA-256: `e365fe46d89c04b60956322d14686061193d28fc7b77d89d621ac2488b9285ab`.

The acceptance process exposed and corrected missing owner-instruction delivery to the planner. It also exposed a Windows test-script multiprocessing entrypoint problem; the private acceptance helper now has a proper main guard. A PC suspension interrupted an earlier regression run; that run is not counted as passing. Normal admission once reported router_cli_busy and stopped visibly; no guard was bypassed.

The owner's pre-existing CV DEVELOPMENT mode remains active. The live result is DEVELOPMENT_READY; this does not assert that disabled canonical CV factual checks passed. The cover's existing factual verifier remained active and rejected a quantified employment claim on an earlier attempt; the planner now omits quantified workplace metrics in cover prose. No verification gate was weakened.

No synthetic acceptance documents were sent to Discord, no employer was contacted and no application was submitted. Delivery adapter behavior is tested in isolation; a fresh public Discord attachment delivery is not claimed. Deployment acceptance requires gateway reload and matching dispatcher/source fingerprints in the startup log.
