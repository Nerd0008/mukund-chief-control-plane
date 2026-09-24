# E3 Google image worker — bounded repeat series + request-protocol conformance

- Started (UTC): 2026-09-24T01:44:32+00:00
- Finished (UTC): 2026-09-24T01:45:35+00:00
- Runtime root: `C:\Users\mukun\AppData\Local\hermes\exec-brain`
- Orchestration DB: `C:\Users\mukun\AppData\Local\hermes\exec-brain\orchestration.db`
- Worker: `google-nano-banana-2` (role `vision`)
- Objective (identical to the failing attempt): `Generate a small solid white square image, 64 by 64 pixels.`
- Objective hash: `c2e948d48a63`
- Real Google image generations planned (stated up front): **9**
- Real Google image generations attempted: 9 / recorded observations: 9
- Aborted: None

## Stated call budget (one real provider call in this table = one single-shot generateContent)

| Calls | Count | Request shape | Reason |
|---|---|---|---|
| 1-6 | 6 | `responseModalities=['IMAGE'], no imageConfig` | repeat series on the exact request that failed once and did not reproduce once, to measure whether/at what rate the no-image response recurs |
| 7-8 | 2 | `responseModalities=['TEXT','IMAGE'], no imageConfig` | controlled comparison: the production adapter sends IMAGE-only with no text modality and no image output config; two calls with the same objective but TEXT+IMAGE show what the provider does with the alternative shape (a shape-level acceptance/rejection is deterministic and does not need a large n) |
| 9 | 1 | `responseModalities=['TEXT','IMAGE'] + generationConfig.imageConfig (explicit output size)` | size-control probe: determine whether an explicitly requested output size is honoured, and whether the provider's own image-output parameter can control it (the earlier objective asked for 64x64 and the provider returned 1024x1024) |

the script spends at most TOTAL_PLANNED_CALLS real image generations; it records every call and stops rather than exceeding the stated budget

Not counted as image generations: metadata reads only (the adapter's /models health and identity calls) are not image generations; this run makes no metadata call either, so the real generation count equals the total

## Measured recurrence of the no-image response

- Dispatches executed: 9
- `no_image_part_in_response`: 2 of 9 (rate = 0.2222222222222222)
- Outcome counts: `{"image_decoded": 7, "no_image_part_in_response": 2}`

| Request shape | Executed | Image decoded | no_image_part_in_response | Other failures | Observed dims | finishReasons |
|---|---|---|---|---|---|---|
| `IMAGE-only` | 6 | 4 | 2 | 0 | `['1024x1024']` | `['IMAGE_RECITATION', 'STOP']` |
| `TEXT+IMAGE` | 2 | 2 | 0 | 0 | `['1024x1024']` | `['STOP']` |
| `TEXT+IMAGE+imageConfig` | 1 | 1 | 0 | 0 | `['512x512']` | `['STOP']` |

A rate is reported as counts over executed calls only. A bounded series of this size can establish that the condition is or is not repeated and give an observed rate; it cannot certify the worker as stable, and it is not described here as such.

## Diagnosis of the recurrence (derived from the records above)

- measured rate: 2 of 9 executed calls (rate = 0.2222222222222222)
- per request shape: `IMAGE-only` 2/6; `TEXT+IMAGE` 0/2; `TEXT+IMAGE+imageConfig` 0/1
- provider signals on every recurrence: finishReason counts `{"IMAGE_RECITATION": 2}`, response part shapes `{"[]": 2}`, shapes affected `{"IMAGE-only": 2}`

Supported by the recorded evidence:

- the no-image response recurred 2 time(s) in 9 executed identical single-shot dispatch(es) (observed rate 0.2222222222222222)
- every recurrence carried a provider-supplied finishReason of IMAGE_RECITATION with an empty response part list and no candidate tokens — that is the provider's own documented stop reason for a generated image withheld by its recitation filter, not an adapter-side or transport-side failure
- the production request shape (responseModalities=['IMAGE'], no imageConfig) was accepted by the provider and returned a decodable inline image on the other IMAGE-only call(s) of the same series, so an IMAGE-only modality list is not on its own rejected by this model

Not supported by this series (explicitly not claimed):

- a stability claim: a series this size bounds the rate, it does not certify the worker as stable
- a breakage claim: the same request succeeded on most calls in the same series
- a modality-shape cause: the recurrences happened to fall on the IMAGE-only shape, but that shape also succeeded repeatedly, and the provider reported an explicit content-side stop reason
- an attribution of the earlier 2026-09-23 failure to a specific trigger: that attempt did not capture finish_reason, so its identity with these recurrences is an inference from identical usage (17 prompt tokens / 0 output) and request, not a recorded fact

Remaining unknown: what makes the recitation filter fire on some calls and not others for the identical prompt; the provider exposes the stop reason but not the filter input. A bounded series cannot resolve that, and no unbounded generation was performed to chase it.

## Per-call record (provider-returned values only)

| # | Shape | status | classification | dispatch_id | finishReason | parts | dims | bytes | decode | usage | E2 request | node state | verification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | IMAGE-only | COMPLETED | image_decoded | `gem-c1221155bd5c` | STOP | `['inlineData:image/jpeg']` | `[1024, 1024]` | 238310 | True | `{"promptTokenCount": 17, "candidatesTokenCount": 1322, "totalTokenCount": 1339, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}], "serviceTier": "standard"}` | `obs-20260924-3dd57fa4` | COMPLETE | PASS |
| 2 | IMAGE-only | FAILED | no_image_part_in_response | `gem-ba1dd13e260d` | IMAGE_RECITATION | `[]` | `None` | None | False | `{"promptTokenCount": 17, "totalTokenCount": 17, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "serviceTier": "standard"}` | `obs-20260924-cb49d14a` | FAILED | FAIL |
| 3 | IMAGE-only | FAILED | no_image_part_in_response | `gem-809e7a8a3ec1` | IMAGE_RECITATION | `[]` | `None` | None | False | `{"promptTokenCount": 17, "totalTokenCount": 17, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "serviceTier": "standard"}` | `obs-20260924-4d42b6a0` | FAILED | FAIL |
| 4 | IMAGE-only | COMPLETED | image_decoded | `gem-dfee69d48d6a` | STOP | `['inlineData:image/jpeg']` | `[1024, 1024]` | 53415 | True | `{"promptTokenCount": 17, "candidatesTokenCount": 1365, "totalTokenCount": 1382, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}], "serviceTier": "standard"}` | `obs-20260924-ee966b4f` | COMPLETE | PASS |
| 5 | IMAGE-only | COMPLETED | image_decoded | `gem-2cdbcf6a38d0` | STOP | `['inlineData:image/jpeg']` | `[1024, 1024]` | 50645 | True | `{"promptTokenCount": 17, "candidatesTokenCount": 1291, "totalTokenCount": 1308, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}], "serviceTier": "standard"}` | `obs-20260924-47d6c78f` | COMPLETE | PASS |
| 6 | IMAGE-only | COMPLETED | image_decoded | `gem-88b08e79fc93` | STOP | `['inlineData:image/jpeg']` | `[1024, 1024]` | 43700 | True | `{"promptTokenCount": 17, "candidatesTokenCount": 1321, "totalTokenCount": 1338, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}], "serviceTier": "standard"}` | `obs-20260924-d54b7e2e` | COMPLETE | PASS |
| 7 | TEXT+IMAGE | COMPLETED | image_decoded | `gem-ba4c638a09d2` | STOP | `['inlineData:image/jpeg']` | `[1024, 1024]` | 63495 | True | `{"promptTokenCount": 17, "candidatesTokenCount": 1355, "totalTokenCount": 1372, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}], "serviceTier": "standard"}` | `obs-20260924-29ae0438` | COMPLETE | PASS |
| 8 | TEXT+IMAGE | COMPLETED | image_decoded | `gem-d9c5510cbd98` | STOP | `['inlineData:image/jpeg']` | `[1024, 1024]` | 711175 | True | `{"promptTokenCount": 17, "candidatesTokenCount": 1269, "totalTokenCount": 1286, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}], "serviceTier": "standard"}` | `obs-20260924-8f3bfa57` | COMPLETE | PASS |
| 9 | TEXT+IMAGE+imageConfig | COMPLETED | image_decoded | `gem-621009631cd2` | STOP | `['inlineData:image/jpeg']` | `[512, 512]` | 71330 | True | `{"promptTokenCount": 17, "candidatesTokenCount": 1030, "totalTokenCount": 1047, "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 17}], "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 747}], "serviceTier": "standard"}` | `obs-20260924-52847cf5` | COMPLETE | PASS |

## Request-protocol conformance (controlled comparison)

The production adapter sends `generationConfig.responseModalities=['IMAGE']` with no `TEXT` modality and no image output configuration. The table above records what the provider actually did with that shape (calls 1-6) and with `['TEXT','IMAGE']` (calls 7-8). Only the request shape was varied; the objective was identical.

## Output-size control

- Objective asked for: `64x64` (stated in the objective text only)
- Observed dims on the IMAGE-only series: `[[1024, 1024], [1024, 1024], [1024, 1024], [1024, 1024]]`
- Prompt-stated size honoured: **False**
- Verdict: **PROMPT_STATED_SIZE_IGNORED**

Explicit-size probe (provider image-output parameter):

- requested `{"imageSize": "512"}` -> status `COMPLETED`, error `None`, dims `[512, 512]`, parts `['inlineData:image/jpeg']`

Conclusions recorded from the probe (facts, not passes):

- a size stated only in the prompt is **NOT honoured**: the objective asked for `64x64` and the IMAGE-only series returned `[[1024, 1024], [1024, 1024], [1024, 1024], [1024, 1024]]`
- the provider's own image-output parameter (`generationConfig.imageConfig`) was accepted and changed the returned dimensions, so exact-pixel size is controlled through that supported parameter rather than through prompt text; the adapter accepts it through the contract-declared `image_config` key and its production default shape is unchanged
- a literal 64x64 output was NOT achieved and is not claimed: the supported parameter is a size class, not arbitrary pixel dimensions, so exact 64x64 remains a known limitation of this provider/model
- no readiness criterion was weakened for this: the node verification contract remains 'an image part arrived and decodes', and the size findings are recorded as protocol facts

## Request-protocol conformance conclusion

The production adapter sends `generationConfig.responseModalities=['IMAGE']` only, with no text modality and no image output configuration. Across the calls recorded above the provider accepted that shape and returned a decodable inline image on the majority of calls, and it also accepted `['TEXT','IMAGE']` (which additionally permits a text part and accepts `imageConfig`). The adapter's request shape is therefore complete enough for this model to generate images; the intermittent no-image responses are accompanied by an explicit provider content-side stop reason and are not a modality-list rejection. Where a text modality or an output-size parameter is wanted, it is available through the adapter's contract-declared `response_modalities` / `image_config` keys (production default unchanged).

## Store state after (E3's own store; E1/E2 are not written)

- schema/db: `{"db_path": "C:\\Users\\mukun\\AppData\\Local\\hermes\\exec-brain\\orchestration.db", "exists": true, "schema_version": 2, "row_counts": {"dag_node": 16, "dag_state_event": 114, "performance_evidence": 24, "router_decision": 0, "capability_registry": 4}}`
- E2 linkage (rows read back from governor.db, written only through `governor.record_request()`): `{"available": true, "path": "C:\\Users\\mukun\\AppData\\Local\\hermes\\exec-brain\\governor.db", "requested_ids": ["obs-20260924-3dd57fa4", "obs-20260924-cb49d14a", "obs-20260924-4d42b6a0", "obs-20260924-ee966b4f", "obs-20260924-47d6c78f", "obs-20260924-d54b7e2e", "obs-20260924-29ae0438", "obs-20260924-8f3bfa57", "obs-20260924-52847cf5"], "rows_read_back": [{"request_id": "obs-20260924-3dd57fa4", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": 1322, "status": "success", "error_code": null}, {"request_id": "obs-20260924-cb49d14a", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": null, "status": "error", "error_code": "no_image_part_in_response"}, {"request_id": "obs-20260924-4d42b6a0", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": null, "status": "error", "error_code": "no_image_part_in_response"}, {"request_id": "obs-20260924-ee966b4f", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": 1365, "status": "success", "error_code": null}, {"request_id": "obs-20260924-47d6c78f", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": 1291, "status": "success", "error_code": null}, {"request_id": "obs-20260924-d54b7e2e", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": 1321, "status": "success", "error_code": null}, {"request_id": "obs-20260924-29ae0438", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": 1355, "status": "success", "error_code": null}, {"request_id": "obs-20260924-8f3bfa57", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": 1269, "status": "success", "error_code": null}, {"request_id": "obs-20260924-52847cf5", "provider": "google", "model": "gemini-3.1-flash-image", "input_tokens": 17, "output_tokens": 1030, "status": "success", "error_code": null}], "all_found": true}`
- contamination check: `{"orchestration_db": "C:\\Users\\mukun\\AppData\\Local\\hermes\\exec-brain\\orchestration.db", "performance_evidence_by_execution_profile": {"production-execution-leg": 24}, "performance_evidence_by_provider": {"deepseek": 8, "google": 11, "openai": 5}, "simulated_or_shadow_evidence_rows": 0, "qualified_rows_without_evidence": 0, "capability_state_counts": {"EVALUATING": 1, "QUALIFIED": 3}, "dag_node_state_counts": {"BLOCKED": 1, "COMPLETE": 13, "FAILED": 2}, "dag_state_event_count": 114, "performance_evidence_count": 24, "simulated_evidence_absent": true, "no_unearned_qualification": true}`

This run records execution evidence only. Whether the vision role moves off EVALUATING is decided by scripts/e3_qualification_from_evidence.py from the recorded rows, not by this script.

