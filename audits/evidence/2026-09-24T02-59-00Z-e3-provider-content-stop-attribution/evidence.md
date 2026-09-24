# E3 provider content-side stop — truthful attribution + bounded same-request retry

- Task: `agent-e3-provider-content-stop-attribution-and-image-retry-policy-2026-09-24`
- Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
- Date (UTC): 2026-09-24
- Consumed evidence (no provider call repeated):
  `audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/`
  (`observations.json`, `evidence.json` — 9 recorded real Google image dispatches)

## Stated provider-call budget (up front)

| Item | Value |
|---|---|
| Real provider calls planned for this task | **0** |
| Real provider calls performed | **0** |
| Reason no call is needed | the recorded responses of the 2026-09-24T01:44:32Z series already contain the provider-returned values that define the behaviour (finishReason, empty part list, candidate count, usage); they are used verbatim as offline fixtures |

The provider-call budget is single-digit and stated before any work: **0**. No
real `generateContent` call is made by this task, by its tests, or by its
evidence run. The repeat series is explicitly **not** re-run.

## What the recorded provider data proves (facts)

From `observations.json` (provider-returned values only):

- 9 identical, deterministic, single-shot image dispatches on the real deployed
  path; objective hash `c2e948d48a63`.
- `no_image_part_in_response` recurred **2 of 9** (index 2 and 3).
- Both recurrences carried `finishReason=IMAGE_RECITATION` with
  `response_part_kinds=[]` (empty response part list), `candidate_count=1`, and
  usage `{promptTokenCount: 17, totalTokenCount: 17}` — i.e. **0 candidate
  tokens**.
- The successful calls (index 1, 4, 5, 6, 7, 8) carried `finishReason=STOP` with
  `inlineData:image/jpeg` and 1024x1024 (index 9, the size probe, returned
  512x512 under an explicit `imageConfig`).
- Terminal state recorded for both recurrences:
  `node_state=FAILED`, `final_verification=FAIL`,
  `failure_attribution=verification_fail` — the conflation this task corrects.

## Inference (not fact) — stated as such

- The two recorded stops fell on *consecutive* calls (index 2 and 3) and the
  immediately following identical call (index 4) succeeded. Reading this as
  "a bounded same-request retry is a valid recovery" is an **inference from the
  observed ordering**, not a recorded provider guarantee: the series shows the
  identical request succeeding around the stops, so the stop is not a
  deterministic property of the request. It is not claimed that 2 retries always
  recover, and the worker is not claimed stable.
- Which calls the recitation filter fires on is still **unknown**; the provider
  exposes the stop reason but not the filter input.

## Retry policy encoded (from the recorded evidence)

- A provider content-side stop (`finishReason` in the provider's content-side
  set, or a `promptFeedback` block) is a **distinct failure**:
  `failure_attribution = provider_content_stop`, recorded together with the
  provider finish reason in the persisted DAG transition cause
  (`provider_content_stop_unrecovered:<finishReason>`) and in the evidence row.
- Recovery is a **bounded same-request retry**: the identical objective and the
  identical contract-declared request shape, deterministic, single-shot, with a
  stated reason recorded per call
  (`kind=same_request_retry`, `reason=provider_content_stop`, `retry_index`,
  `retry_budget`). It is never a reworded repair and never a shape change.
- Budget: `DEFAULT_MAX_CONTENT_STOP_RETRIES = 2` (initial dispatch + 2 retries =
  at most 3 identical single-shot calls). This is the smallest bound that covers
  the observed consecutive-stop cluster; it is single-digit and fixed in code.
- **Non-silent terminal path** when the budget is exhausted: the node ends
  `BLOCKED` (not `FAILED` as a quality defect, not `COMPLETE`) with
  `failure_attribution=provider_content_stop` and
  `blocking_reason=provider_content_stop_unrecovered:<finishReason>`, plus an
  E3 escalation (`trigger=provider_content_stop`) naming the finish reason and
  the owner decision. Worker identity is **never** changed silently, so
  equivalent-worker failover remains an explicit E4/owner decision.
- **No unbounded path**: the node loop carries a hard, total attempt bound
  `1 + max_repair_attempts + max_content_stop_retries`; every continuation
  consumes a bounded counter, and the guard transitions to `BLOCKED`
  (`attempt_budget_exhausted`) if it were ever exceeded. The Stage-2 credential
  gate and deterministic owner/external blockers are untouched.

## Separation of the three causes now encoded

| Cause | Attribution | Recovery |
|---|---|---|
| Provider content-side stop (provider `finishReason` withheld content) | `provider_content_stop` | bounded same-request retry → escalation |
| Transport/provider error (HTTP status, absent credential, raised exception, 200 with no image and no content-side stop reason) | `provider_error` | existing bounded repair budget, then FAILED |
| Delivered, well-formed output that fails its declared contract | `verification_fail` | existing bounded repair budget, then FAILED |

## Deterministic verification contract — unchanged

Only an independent deterministic verification PASS reaches `COMPLETE`. A
content-side stop is never a pass and never silently a verification failure.
Tests assert: a delivered image that fails the contract is still
`verification_fail`; the adapter's production request shape is unchanged.

## E4 / E5 interaction (confirmed, not weakened)

- **E4**: the content stop does not fabricate or silently perform a failover;
  the terminal escalation states that worker identity is not changed and names
  the owner decision. The designated-but-not-auto-selected equivalent worker is
  never dispatched (asserted).
- **E5**: the terminal outcome is a truthful `provider_content_stop`
  attribution on top of a non-`COMPLETE` node, so repeated-failure convergence
  still counts it; `ConvergenceEnforcer` cap behaviour (warn → quarantine →
  stop) is unchanged and asserted.

## Tests, exact commands, counts, exit codes

Evidence runner (all suites, real subprocesses):

- command: `python scripts/evidence_runner.py --label regression-post-content-stop`
- artifact: `audits/evidence/2026-09-24T02-56-57Z-regression-post-content-stop/`
  (`evidence.json`, `evidence.md`)
- result: **19 suites run, 19 passed, 0 failed, 0 unavailable — 507 tests
  collected, 507 passed**; runner exit code **0**
- code SHA at run: `d9d1a7f9972f65d1367c7ca4d79f7bf367aace52` (pre-commit working
  tree; the committed SHA is recorded in the terminal result)
- regression baseline beaten: 18 suites / 482 tests / exit 0 at `d9d1a7f`

New offline suite (0 provider calls, recorded-response fixtures, stubbed
transports):

- command:
  `PYTHONPATH=exec-brain python exec-brain/tests/test_e3_provider_content_stop.py`
- import root: `exec-brain/`
- result: `Ran 25 tests` — `OK`; exit code **0**

Post-deploy regression (after `scripts/deploy_e3_runtime.py`):

- command: `python scripts/evidence_runner.py --label regression-post-content-stop-postdeploy`
- artifact: `audits/evidence/2026-09-24T02-59-27Z-regression-post-content-stop-postdeploy/`
- result: **19 suites / 19 passed / 0 failed / 0 unavailable — 507 tests
  collected / 507 passed**; runner exit code **0**
- code SHA at run: `8930572` (committed)

Deployed-runtime verification (live runtime root, not the checkout):

- command:
  `python audits/evidence/2026-09-24T02-59-00Z-e3-provider-content-stop-attribution/verify_deployed_runtime.py`
- deployed `e3_execution.py` sha256
  `6f625a0a05e44b4f195ec1b53c8bc385ad4af389a9f9e2377a379778362d36f3` **equals**
  the repository source sha256
- deployed module reports `DEFAULT_MAX_CONTENT_STOP_RETRIES = 2` and classifies
  the recorded `IMAGE_RECITATION` response as `provider_content_stop`, an
  `http_503` as `provider_error`, and a `COMPLETE`-with-`STOP` delivery as
  `verification_fail`
- deployment manifest: source sha `8930572`; backup
  `%LOCALAPPDATA%\hermes\exec-brain\backups\e3-deploy-20260924T025913Z`

The full per-suite table and exact commands are in
`audits/evidence/2026-09-24T02-56-57Z-regression-post-content-stop/evidence.md`
(identical suite set to the post-deploy run).

## Limitations / not claimed

- The fixtures reproduce the recorded response *shape and values* that drive
  attribution; the image payload itself is a minimal valid PNG, not the recorded
  JPEG bytes (which are not reproduced in this artifact).
- No claim is made about the recitation trigger, about worker stability, or
  about the recovery rate of the bounded retry.
- No E3 Stage 2 enablement, no production dispatch, no VPS cutover, no
  readiness/qualification criterion changed.
