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
