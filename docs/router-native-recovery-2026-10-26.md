# Native controller routing repair — 26 October 2026

## Reproduced defects

1. The native execution middleware offered exactly one provider/model. The Codex brain could authorize it, but could not choose a different native model after a failure.
2. Our middleware wrapped `_DownstreamExecutionError` a second time. Hermes unwraps that container once. The actual SDK error, HTTP status, body and `Retry-After` were hidden from its retry classifier.
3. Selection was cached for 120 seconds without failure invalidation or health feedback. A failed choice could immediately be reused.
4. SDK streams were recorded as completed when created, before any stream was consumed. Later provider errors could escape the execution evidence and circuit breaker.
5. Each retry started a fresh elapsed-time budget.
6. The provider's advertised Qwen and Llama alternatives are not usable on this account. Both returned HTTP 404 with `insufficient_credits_for_paid_model`; this is model-specific billing denial, not a missing model or a provider-wide outage.

The original middleware reproduction had 16 failures and one pass. No production application was replayed to reproduce it.

## Production behavior

The existing native SDK client, provider, credentials, streaming and tool protocol remain in place. The native controller policy permits a bounded catalog of models on that same endpoint. Alternative models require an explicit live qualification, current policy fingerprint, fresh proof, compatible context/input/parameters and healthy circuit evidence. Provider-suggested alternate IDs do not grant eligibility. Embedding models cannot enter this pool.

The Codex `gpt-6.1-sol` high reasoning brain ranks opaque handles on capability and observed evidence. There is no automatic primary score boost. Codex remains a text worker only where the existing request contract allows it; this change does not turn its CLI into a native function-calling transport. The configured default provider/model is not changed.

Native conversation calls, auxiliary physical calls and compatible SDK workflow calls use the shared selection and health gate. The selected model is applied to the actual request. `responses` and `messages` transports are not silently converted to chat completions.

A model-specific 429 invalidates matching cached choices and excludes the model for at least 30 seconds or the longer bounded provider retry hint. Provider-wide outages/quota failures exclude the endpoint. Authentication, permissions and context errors retain the host's existing recovery semantics. A dispatch rechecks health to close the concurrent selection/send race. Missing health storage fails closed.

Retries sharing Hermes' `api_request_id` share a deadline; a new API/tool step receives its own budget. Routing, waiting and provider execution consume that budget. The middleware invokes `next_call` at most once. It never replays a turn, application, tool call or partially consumed stream.

The original SDK exception survives the host boundary. Streams receive `STREAM_STARTED`, followed by exactly one completion/failure/cancellation outcome. Closing a stream cannot replace an already-active provider exception. A failed evidence write cannot hide a provider failure; an evidence write failure on a successful result blocks that result.

## Live qualification and limits

Synthetic protocol probes verified chat, a declared tool call (not executed), tool-result continuation, English output and streaming for:

- Step 3.7 Flash free — also verified image input.
- Beam free — text input only.
- Ornith free — also verified image input.
- LongCat 2.5 free — core protocol passed; the image probe failed, so no additional image qualification is claimed for it.

The older LongCat 2.0 endpoint failed qualification. Qwen and Llama were denied for account credits. They remain ineligible without a passing qualification. No credits were bought or redeemed.

A real Codex-brain / real Hermes-middleware acceptance injected a synthetic 429 on the first selection. It selected Step first, then selected Beam after the failure. Beam returned a valid synthetic tool call. Total elapsed: 19.562 seconds; one real model completion, zero real tool executions, unchanged default model. This acceptance used private circuit state and receipts; it did not poison the live circuit with synthetic failures.

Qualification evidence is local, contains allowlisted booleans and timestamps, and expires after seven days or a policy fingerprint change. Refresh explicitly with the existing Hermes Python environment:

```
python scripts/qualify_native_controllers.py --live --output <private-report-path>
```

The default qualification command probes only the listed free models. `--models` can narrow the probe set. It never purchases access. Qualification is not a guarantee of model availability, factual quality or indefinite provider capacity. If all compatible qualified models are unavailable, the router returns a specific bounded failure; it does not bypass account limits or switch credentials/providers silently. An account-wide Nous breaker remains respected.

The direct image probe is independent from the existing Gemini image workflow; that workflow and its configuration are unchanged. CV templates, renderer code, Gmail/Calendar permissions and scheduled search configuration are unchanged.

## Evidence and regression

Private detailed receipts, original repro, XML test reports, qualification reports and pre-repair source copies are under `Documents/Codex/controller-router-repair-20261026`.

The full regression includes a known unrelated project-status test that flags evidence newer than its 25 September canonical cutoff. The same warning is reproduced by executing `scripts/status_sources.py` from pre-repair HEAD against unchanged canonical status inputs. Do not remove that assertion or manufacture a fresh executive status merely to make this router change green.

See the accompanying sanitized acceptance JSON for final counts, deployed fingerprints, gateway restart and commit evidence. Unrelated dirty runtime files are deliberately excluded from the commit.
