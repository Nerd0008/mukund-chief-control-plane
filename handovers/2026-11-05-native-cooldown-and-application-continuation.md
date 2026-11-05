# Application continuation and native cooldown repair - 5 November 2026

The 17:49 failure had two independent causes. `its okay draft` missed the application dispatcher and an unrelated-turn branch erased its saved intake. The resulting general-agent turn then hit a LongCat connection timeout; its next attempt arrived 2.65 seconds into a 30-second model cooldown. The repository already contained a bounded wait, but the gateway loaded an older deployed copy. An eagerly imported host error-handler alias also retained misleading permanent endpoint rejection wording.

## Changes

- Resolve short document permissions against a JD-bound saved intake or the latest relevant history. Permission means draft documents only: it never establishes student status, legal permission or clearance and never submits anything.
- Preserve checkpoints across unrelated turns. Explicit cancellation deactivates the workflow while retaining its intake and receipts. Prevent short drafting acknowledgements from reaching across an intervening unrelated task.
- Carry eligibility warnings into the planner and final document response. Explicit mandatory clearance remains blocked by the existing evidence detector.
- Preserve actual worker failure causes in blocked-selection receipts and accurate temporary cooldown messages, including the host's eagerly imported handler alias.
- Deploy the existing bounded cooldown wait, retain cancellation and remaining deadline limits, and log the loaded router fingerprint and repository match on startup.
- Add a declared-module subset to the existing backup/manifest deployment script, avoiding unrelated runtime updates or E1 CLI patches during targeted deployment.

## Verification

300 selected application, compiler, owner-context, router, error-envelope and deployment regressions passed in the final combined run. These include real routing/health code with an isolated simulated clock: short cooldown recovery, retry after cooldown, and insufficient-budget refusal. No external provider calls were made by these tests.

Private acceptance evidence is under the owner's workspace `output/router-repair-20261105/`. Private JD, PDF, reference and runtime evidence must not be committed.

The first private live harness lacked the Windows multiprocessing main guard; its child re-entered the harness and correctly encountered the existing application lock. The harness was corrected. This is separate from production dispatch behavior and must not be described as a successful live acceptance.

The corrected live acceptance passed against the actual Revolut JD and exact failed phrase `its okay draft`: both existing compilers produced accepted one-page PDFs, five authoritative owner references were loaded, the eligibility warning remained `UNCONFIRMED_DRAFT_AUTHORIZED`, and a retry reused both original document hashes. Final status was `DEVELOPMENT_READY` because the existing CV development setting remains unchanged. Cover verification remained active. No document delivery or application submission occurred. Private result: `output/router-repair-20261105/live-acceptance-guarded/result.json` in the owner workspace.

Legacy empty checkpoints can recover a JD on retry without inventing permission. Short acknowledgements and retries cannot cross an intervening unrelated task or another JD. Negative drafting statements and requests for posts/articles are excluded.

## Limits

The current native tool transport has one configured provider. This repair does not add or qualify a backup provider and cannot guarantee the remote endpoint remains available. It does not bypass health, quota, authentication, factual checks or approval controls. CV development mode remains the owner's existing setting; do not claim its disabled factual gate passed. Cover verification remains enforced.

No applications, email, Calendar changes or LinkedIn publication are part of this repair. Preserve unrelated dirty runtime files. Do not merge main.
