# Provider debug + Qwen model-selection reconciliation — 2026-09-24

Task: `agent-provider-debug-qwen-tencent-entitlement-2026-09-24`
Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
Runtime deployed: `C:\Users\mukun\AppData\Local\hermes\exec-brain` (via `scripts/deploy_e3_runtime.py`)
Stage 2: **NOT ENABLED** (unchanged; not touched by this task)

Every credential was resolved in-process and used only as an `Authorization` header.
No credential value was read into evidence, printed, logged, stored or passed as a shell argument.

## 1. The bug that was fixed — Qwen model selection

The prior closeout claimed the owner's intended model `qwen3.7-plus` was **not** in this
account's catalogue and selected `qwen3.8-27b` instead. That claim was wrong: the prior run's own
committed live catalogue evidence
(`audits/evidence/2026-09-24T21-06-25Z-e3-provider-live-identity-probe/evidence.json`) lists BOTH
`qwen3.7-plus` and its dated alias `qwen3.7-plus-2026-05-26` among the 172 observed ids.

The owner's intent is recorded in
`handovers/2026-09-24-provider-configuration-and-final-closeout-handover.md`:
*"The model selected from the live Alibaba Model Studio page was Qwen3.7-Plus … credential is
stored under worker `qwen38-27b` for compatibility with the current credential registry."*

Correction applied:

| File | Was | Now |
|---|---|---|
| `exec-brain/generic_openai_adapter.py` | `api_model_id = qwen3.8-27b`, display `Qwen3.8-27B` | `api_model_id = qwen3.7-plus`, display `Qwen3.7-Plus` |
| `exec-brain/worker_registry.py` | `model/api_model_id = qwen3.8-27b` | `model/api_model_id = qwen3.7-plus`, display `Qwen3.7-Plus` |

The `worker_id` was **preserved as `qwen38-27b`**: it is the stable roster / credential-registry key
the owner provisioned under (per the handover), and the credential resolves through the adapter's
`credential_target = "qwen"`, which is independent of the worker id. Renaming it would have churned
the credential registry, E2/E3 records, the readiness gate and the deployment manifest for no benefit.

## 2. Qwen — bounded re-test of the corrected model

Deployed the corrected E3 runtime, then made **exactly one** bounded real chat call to
`qwen3.7-plus` (`max_tokens = 16`, single attempt, no retry).

Evidence: `audits/evidence/2026-09-24T22-08-43Z-e3-provider-bounded-smoke/`

- configured model sent: `qwen3.7-plus`
- model present in the live catalogue: **true** (172 models)
- HTTP status: **403**
- provider error code: **`AccessDenied.Unpurchased`**
- provider error: `Access to model denied. Please make sure you are eligible for using the model.`
- provider-returned `model` field: **null** (no identity confirmation)
- usage: **null** (no completion consumed)
- E2 linkage: failure row `obs-20260924-c378d692` through `governor.record_request()`

**Classification:** a genuine **account entitlement blocker for the intended model**. The correction
fixed the Hermes-side mapping; the refusal is provider-side (the model exists and is served by the
platform but is not enabled/purchased for this account). Qwen stays `routable = false`,
`smoke_test = 'FAILED'`, `qualification = 'UNPROVEN'`.

## 3. Mis­tral — 429 header diagnostic

Two prior 429s carried only the message `Rate limit exceeded`. One additional bounded diagnostic
call (`max_tokens = 16`, single attempt) captured the response headers.

Evidence: `audits/evidence/2026-09-24T22-08-59Z-e3-provider-rate-limit-diagnostic/`

- HTTP status: **429**, body `Rate limit exceeded`
- non-secret rate-limit headers present from the allow-list (`Retry-After`,
  `x-ratelimit-*`, `ratelimit-*`, request ids): **none**

**Classification:** provider-side rate-limit refusal. The authenticated `GET /models` still returns
200 (46 models; `mistral-small-latest` observed), so it is **not** an auth or adapter fault. Because
the provider exposes no `Retry-After`/rate-limit/quota headers, a **transient request-rate limit
cannot be separated from an account/tier/monthly quota** from provider evidence; the distinction is
recorded as unresolved rather than guessed. `routable = false` unchanged.

## 4. GLM, LongCat, MiniMax, StepFun — classified without new calls

Existing committed evidence (`…21-06-25Z-e3-provider-live-identity-probe`,
`…21-14-53Z-e3-provider-bounded-smoke`) is sufficient; no call was re-spent.

| Provider | Live catalogue | Configured model observed | Smoke HTTP | Provider message | Class |
|---|---|---|---|---|---|
| GLM (Z.ai international) | 200, 11 models | `glm-5.3-flash` yes | 429 | `Insufficient balance or no resource package. Please recharge.` | account billing blocker |
| LongCat (direct API) | 200, 1 model | `LongCat-2.0` yes | 402 | `Call failed: Insufficient token quota.` | account token-quota blocker |
| MiniMax (api.minimax.io) | 200, 8 models | `MiniMax-M3` yes | 402 | `insufficient balance (1008)` | account balance blocker |
| StepFun (api.stepfun.ai global) | 200, 16 models | `step-3.7-flash` yes | 402 | `You exceeded your current quota, please check your plan and billing details` | account quota/billing blocker |

All four: endpoint + model correct, provider refuses at the billing/quota layer.
`routable = false`, `qualification = 'UNPROVEN'` unchanged.

## 5. Tencent Hunyuan Hy3 — TokenHub re-probe

Endpoint/key-product evidence inspected; one bounded `GET /v1/models` re-probe (no chat call).

Evidence: `audits/evidence/2026-09-24T22-09-28Z-e3-tencent-endpoint-reprobe/`

- endpoint: `https://tokenhub-intl.tencentcloudmaas.com/v1/models`
- HTTP status: **401**
- provider error code: **`401002`** — `The API Key does not exist or signature verification failed.`
- chat completion attempted: **false** (authentication did not succeed)

**Classification:** TokenHub **credential/product/account mismatch** (the stored key is not valid for
the TokenHub product/region). Owner action = re-issue a TokenHub API key at
`https://console.tencentcloud.com/tokenhub/apikey`. The Hy3 model id `hy3` remains
documentation-derived only.

## 6. Google image worker — IMAGE_RECITATION audit (no new images generated)

Using the existing 9-call series
(`audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/`) only:

- 2 of 9 dispatches returned no image part; **every** recurrence carried the provider's own
  `finishReason = IMAGE_RECITATION` with an empty part list and no candidate tokens.
- The production request shape (`responseModalities=['IMAGE']`) returned a decodable image on the
  other IMAGE-only calls, so an IMAGE-only modality list is not rejected by this model.

**Conclusion:** `IMAGE_RECITATION` is a **provider content-side stop** (recitation filter), not a
transport or authentication failure and not a Hermes adapter fault. The current Stage-2 criterion
(*"Google image worker real-dispatch failure resolved (not intermittent)"*) is **intentionally
conservative**: the gate derives it literally (`observed_recurrences == 0`) and reports the
recurrence to the owner as a re-scoping question rather than silently relaxing it. The criterion was
**not changed** in this task, and no additional images were generated.

## 7. Budget actually spent

- Qwen: 1 real chat completion (the corrected-id re-test).
- Mistral: 1 real chat completion (header diagnostic).
- Tencent: 1 `GET /v1/models` (no completion).
- GLM / LongCat / MiniMax / StepFun: **0** new calls (classified from committed evidence).
- Google image: **0** new generations.

## 8. Net state

| Worker | routable | smoke_test | qualification | Blocker |
|---|---|---|---|---|
| qwen38-27b (`qwen3.7-plus`) | false | FAILED | UNPROVEN | account entitlement (403 Unpurchased) |
| mistral-small-4 | false | FAILED | UNPROVEN | provider 429 (header cause unresolved) |
| glm-53-flash | false | FAILED | UNPROVEN | account balance |
| longcat-2.0 | false | FAILED | UNPROVEN | token quota |
| minimax-m3 | false | FAILED | UNPROVEN | account balance |
| step-37-flash | false | FAILED | UNPROVEN | quota/billing |
| tencent-hunyuan-hy3 | false | FAILED | UNPROVEN | TokenHub key mismatch (401 401002) |

No provider became execution-ready. Stage 2 remains **NOT ENABLED**; no gate was weakened.
