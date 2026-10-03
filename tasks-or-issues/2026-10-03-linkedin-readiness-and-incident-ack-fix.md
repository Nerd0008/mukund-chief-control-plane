# Proven fixes — LinkedIn readiness + incident ACK state

Date: 2026-10-03
Status: root causes proven; implement minimal fixes only.

## A. LinkedIn

### Proven facts

- Windows Credential Manager reads succeed under the Hermes interpreter and user `MISTY\mukun`.
- Present: client_id, client_secret, access_token.
- Absent: refresh_token.
- Stored access-token expiry: `2026-12-02T00:26:11Z`.
- The latest failed image-publish attempt failed before OAuth/API use because the caller passed an unsupported CLI argument:
  `linkedin_publish.py: error: unrecognized arguments: --image ...`
- A subsequent image post succeeded with HTTP 201.
- No account-context change is established.

### Bug 1 — readiness predicate is wrong

The repo currently treats OAuth readiness as:
`client_id && client_secret && refresh_token`.

That produces a false negative when a valid, unexpired access token is already present. The real publish path can use an existing access token and only needs the refresh grant if no usable access token is available.

Implement one canonical auth predicate/helper used by:
- `career-ops/linkedin_auth.py status`
- `career-ops/linkedin_publish.py` preflight/status
- `career-ops/linkedin_workflow.py publish-status`

Semantics:

```
usable_access_token =
    access_token present
    AND expiry exists
    AND expiry is in the future with a small safety skew

refresh_path_available =
    client_id present
    AND client_secret present
    AND refresh_token present

oauth_ready = usable_access_token OR refresh_path_available
```

If an access token exists but expiry is missing/invalid, fail closed or report UNKNOWN rather than assuming it is valid.

Do not print/read secret values in status output.

Add tests for:
1. valid access token + no refresh token => READY
2. expired access token + complete refresh path => READY
3. expired access token + no refresh token => NOT READY
4. no access token + complete refresh path => READY
5. no usable access token + incomplete refresh path => NOT READY

### Bug 2 — wrong image caller/CLI contract

Do NOT simply add `--image` to the existing text-only `linkedin_publish.py` CLI unless the intended production image-publish implementation actually belongs there.

Trace the successful HTTP 201 image-post path and make the caller invoke that supported image-aware interface with its documented argument name/shape.

Add an offline CLI contract regression proving the image workflow invokes the correct command/arguments and does not fail in argparse before OAuth.

No live LinkedIn post is required for this code fix.

## B. Incident delivery

### Proven facts

- Cron job delivery to Discord works.
- 09:40 delivery produced Discord message id `1555862125103030283`.
- Wrapper and inner script both produced empty stdout/stderr with exit 0 when reproduced.
- The output disappeared inside the underlying flush script's 60-minute grace-period filter.
- UTC/local comparison is correct.
- Therefore the earlier `silent (empty output)` observations were not evidence that stdout/no_agent delivery was broken.
- Incidents remain `delivered=false` after successful Discord delivery and are subsequently emitted again.
- The flush timestamp is written before delivery confirmation.

### Actual bug — no delivery acknowledgement reconciliation

The producer/flush side must not permanently mark state based only on "emitted to stdout", because stdout delivery and Discord acknowledgement occur afterward.

Implement an acknowledgement-safe state transition.

Required invariant:
- pending incident stays pending until Discord delivery is confirmed;
- successful Discord ACK marks exactly the delivered incident ids/records as delivered;
- failed/no ACK leaves them pending;
- retry is idempotent;
- no incident is lost if process exits between emission and delivery.

Prefer a two-phase state:
`pending -> in_flight/emitted -> delivered`
or an equivalent acknowledgement ledger keyed by stable incident id.

Do not remove the 60-minute grace period unless a separate requirement says to. Its current behavior explained the empty runs and is not the root delivery defect.

Do not replace deterministic delivery with an LLM/agent cron workaround.

Add tests for:
1. grace-period suppressed => empty stdout, state unchanged
2. eligible incident emitted => not yet delivered
3. ACK success => delivered true
4. delivery failure/no ACK => remains pending
5. repeated run after ACK => no duplicate delivery
6. crash/restart between emission and ACK => safely retryable without data loss

## Acceptance

LinkedIn:
- status reports READY with current valid access-token-only state;
- no secret printed;
- image caller passes offline CLI contract;
- no live post needed.

Incidents:
- fixture incident survives failed delivery;
- successful mocked ACK marks delivered;
- subsequent flush emits nothing for that incident;
- 60-minute grace behavior remains explicit;
- existing Discord cron/no_agent mechanism unchanged.

Return changed files, tests, and PASS/BLOCKED. Do not redesign unrelated systems.

## Implementation status — 2026-10-03

Branch: `fix/e3-whole-repo-architecture`

### LinkedIn code — IMPLEMENTED, runtime acceptance pending

Changed:
- `career-ops/linkedin_auth.py`
- `career-ops/linkedin_publish.py`
- `career-ops/linkedin_workflow.py`
- `career-ops/tests/test_linkedin_readiness_regression.py`
- `career-ops/tests/test_linkedin_publish.py`

Commits:
- `9528452a43bc1b292f55e301ad64ee84e6012128` — canonical expiry-aware `oauth_ready()` plus raw-byte image transport
- `e6b5cee9ec031e745d3509153e3fcf0ec70edf46` — image-aware publisher contract
- `8061ac678b2d546f70a5d3d560752f55dfdbee0b` — workflow image forwarding + canonical readiness
- `1ebc188bd3d99598c2dd48b4325a5492589499c1` — focused readiness/image CLI regression tests
- `ddaacd48ac8944359c451de3a96d35fd73706ffe` — align existing LinkedIn test fixtures with expiry-aware readiness

Implemented semantics:
- usable access token requires token presence + parseable expiry + expiry beyond a 300-second safety skew;
- complete refresh grant remains an alternate READY path;
- missing/invalid expiry fails closed;
- status/preflight/workflow all use the same canonical readiness helper;
- the workflow forwards `--image` to the image-aware publisher;
- image upload uses initializeUpload -> raw byte PUT -> post with image URN;
- no live LinkedIn post was made while implementing this repair.

Offline regression coverage was added for the five required readiness cases, missing/invalid expiry behavior, safety skew, and workflow image-argument forwarding.

**Status:** code review/structural checks complete. Full LinkedIn pytest/runtime acceptance is **BLOCKED in this chat** because the isolated execution environment cannot check out the repository and does not have the laptop's Hermes/Windows Credential Manager context. Run the focused tests and `linkedin_auth.py status` under the Hermes interpreter on the laptop before calling live acceptance PASS. No live LinkedIn post is required.

Expected current laptop status after deployment:
- access token present;
- stored expiry `2026-12-02T00:26:11Z`;
- refresh token absent;
- `oauth_ready: true`.

### Incident delivery — IMPLEMENTED, offline tests PASS, live deployment pending

Changed:
- `career-ops/incident_flush.py`
- `career-ops/tests/test_incident_flush_ack.py`

Commits:
- `b5225285ecbce155ef2dd5bc793cbb6480e33156` — bind emitted incident batches to the exact Hermes cron execution and reconcile only after a durable delivery outcome
- `804c6329ef039a9c9dfe6a326a78b0bb7d4bbc9c` — six ACK/grace/retry/restart regression tests

Implementation:
- preserves the existing deterministic `no_agent` stdout delivery mechanism;
- persists `pending -> in_flight` before stdout emission;
- binds the batch to the exact Hermes cron execution id from `~/.hermes/cron/executions.db`;
- marks exactly those incident ids delivered only when that exact execution terminates with `status=completed` and `delivery_outcome=delivered`;
- failed, unknown, missing or unconfirmed delivery evidence leaves the incidents pending;
- keeps the existing 60-minute re-alert grace;
- is idempotent after ACK and restart-safe between emission and ACK;
- migrates the old row-index/timestamp grace-state shape without treating it as delivery confirmation.

Executed offline:
```
python -m pytest -q career-ops/tests/test_incident_flush_ack.py
...... [100%]
6 passed
```

**Status:** offline acceptance **PASS**. Live acceptance remains **BLOCKED until the laptop-local incident wrapper/script is deployed or pointed at this committed implementation**, because the original live script was local-only and was not present on this branch when the repair started. After deployment, one controlled cron delivery should prove that the exact execution receives a positive Discord delivery outcome and the corresponding incident record becomes `delivered=true` without repeating.

### Overall

- No Hermes/E3 redesign.
- No main merge.
- No live LinkedIn post.
- No autonomous application/outreach.
- No secret values committed or printed.
- Incident 60-minute grace retained.
- Discord `no_agent` mechanism retained.

Current branch head before this status-note commit: `ddaacd48ac8944359c451de3a96d35fd73706ffe`.
