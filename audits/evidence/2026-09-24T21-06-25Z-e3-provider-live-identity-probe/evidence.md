# E3 provider live endpoint / model-identity probe

- Started (UTC): 2026-09-24T21:06:25+00:00
- Finished (UTC): 2026-09-24T21:06:39+00:00
- Provider completion calls spent: 0
- Credential handling: resolved in-process, used only as an Authorization header; no value printed, logged, stored or passed as a shell argument

## mistral

- credential present: `True` (source `credential_manager`, target `mistral`)
- configured model id: `mistral-small-latest`
- configured endpoint reachable: `True`
- configured model id observed in catalogue: `True`
- authoritative-documentation backed: `False`

| Candidate | /models URL | HTTP | Models | Note |
|---|---|---|---|---|
| configured | `https://api.mistral.ai/v1/models` | 200 | 46 |  |

Observed model IDs: `codestral-2508`, `codestral-latest`, `mistral-code-latest`, `mistral-code-fim-latest`, `mistral-small-2603`, `mistral-small-latest`, `mistral-vibe-cli-fast`, `magistral-small-latest`, `voxtral-small-2507`, `voxtral-small-latest`, `labs-leanstral-1-5-1`, `labs-leanstral-1-5`, `ministral-3b-2512`, `ministral-3b-latest`, `ministral-8b-2512`, `ministral-8b-latest`, `ministral-14b-2512`, `ministral-14b-latest`, `mistral-medium-latest`, `mistral-medium`, `mistral-medium-3-5`, `mistral-medium-3.5`, `mistral-medium-3`, `mistral-medium-2604`, `mistral-vibe-cli-latest`, `mistral-vibe-cli-with-tools`, `magistral-medium-latest`, `mistral-embed-2312`, `mistral-embed`, `codestral-embed`, `codestral-embed-2505`, `mistral-moderation-2603`, `mistral-ocr-2512`, `mistral-ocr-3-0`, `mistral-ocr-3`, `mistral-ocr-4-0`, `mistral-ocr-latest`, `mistral-ocr-4`, `mistral-ocr-4-1`, `voxtral-mini-2602`, `voxtral-mini-latest`, `voxtral-mini-transcribe-realtime-2602`, `voxtral-mini-realtime-2602`, `voxtral-mini-realtime-latest`, `voxtral-mini-tts-2603`, `voxtral-mini-tts-latest`

## glm

- credential present: `True` (source `credential_manager`, target `glm`)
- configured model id: `glm-5.3-flash`
- configured endpoint reachable: `True`
- configured model id observed in catalogue: `True`
- authoritative-documentation backed: `False`

| Candidate | /models URL | HTTP | Models | Note |
|---|---|---|---|---|
| z_ai_configured | `https://api.z.ai/api/paas/v4/models` | 200 | 11 |  |
| bigmodel_cn_alternate | `https://open.bigmodel.cn/api/paas/v4/models` | 200 | 11 |  |

Observed model IDs: `glm-4.5`, `glm-4.5-air`, `glm-4.6`, `glm-4.7`, `glm-5`, `glm-5-turbo`, `glm-5.1`, `glm-5.2`, `glm-5.3`, `glm-5.3-flash`, `glm-5.3-flashx`

## qwen

- credential present: `True` (source `credential_manager`, target `qwen`)
- configured model id: `qwen3.8-27b`
- configured endpoint reachable: `True`
- configured model id observed in catalogue: `True`
- authoritative-documentation backed: `False`

| Candidate | /models URL | HTTP | Models | Note |
|---|---|---|---|---|
| dashscope_intl_configured | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models` | 200 | 172 |  |
| dashscope_cn_alternate | `https://dashscope.aliyuncs.com/compatible-mode/v1/models` | 401 | 0 | invalid_api_key |

Observed model IDs: `qwen3.8-omni-flash-realtime`, `glm-5.3-prime`, `qwen-audio-3.1-realtime-plus`, `qwen3.8-omni-flash`, `qwen3.8-livetranslate-flash-realtime`, `glm-5.3`, `deepseek-v4.1-flash`, `qwen3.8-max-0902`, `kimi/kimi-k3`, `qwen3.8-flash`, `kimi-k3`, `qwen3.8-27b`, `ZHIPU/GLM-5.3`, `deepseek-v4-pro-0813`, `qwen3.8-2.4t-a95b`, `qwen3.7-text-embedding`, `qwen-image-3.0-pro`, `qwen-image-3.0`, `qwen3.8-max`, `deepseek-v4-flash-0731`, `qwen-audio-3.0-asr-flash`, `qwen3.7-flash-2026-07-15`, `qwen3.7-flash`, `glm-5.2-fast-preview`, `kimi-k2.7-code`, `glm-5.2`, `qwen-image-2.0-pro-2026-06-22`, `qwen3.7-max-2026-06-08`, `qwen3.7-plus-2026-05-26`, `qwen3.7-plus`, `glm-5.1`, `qwen3.7-max-2026-05-17`, `qwen3.7-max-preview`, `qwen3.7-max-2026-05-20`, `qwen3.7-max`, `qwen3.5-livetranslate-flash-realtime-2026-05-19`, `qwen3.5-livetranslate-flash-realtime`, `deepseek-v4-flash`, `deepseek-v4-pro`, `qwen-image-2.0-pro-2026-04-22`, `qwen3.6-27b`, `qwen3.5-plus-2026-04-20`, `qwen3.6-max-preview`, `qwen3.6-35b-a3b`, `qwen3.6-flash`, `qwen3.6-flash-2026-04-16`, `qwen3.5-omni-plus-realtime-2026-03-15`, `qwen3.5-omni-plus-realtime`, `qwen3.5-omni-plus-2026-03-15`, `qwen3.5-omni-plus`, `qwen3.5-omni-flash-realtime-2026-03-15`, `qwen3.5-omni-flash-realtime`, `qwen3.5-omni-flash-2026-03-15`, `qwen3.5-omni-flash`, `qwen3.6-plus-2026-04-02`, `qwen3.6-plus`, `wan2.7-image-pro`, `wan2.7-image`, `deepseek-v3.2`, `qwen-image-2.0-2026-03-03`

## minimax

- credential present: `True` (source `credential_manager`, target `minimax`)
- configured model id: `MiniMax-M3`
- configured endpoint reachable: `True`
- configured model id observed in catalogue: `True`
- authoritative-documentation backed: `False`

| Candidate | /models URL | HTTP | Models | Note |
|---|---|---|---|---|
| configured_minimax_io | `https://api.minimax.io/v1/models` | 200 | 8 |  |
| minimaxi_cn_alternate | `https://api.minimaxi.com/v1/models` | 401 | 0 | authorized_error |

Observed model IDs: `MiniMax-M3`, `MiniMax-M2.7`, `MiniMax-M2.7-highspeed`, `MiniMax-M2.5`, `MiniMax-M2.5-highspeed`, `MiniMax-M2.1`, `MiniMax-M2.1-highspeed`, `MiniMax-M2`

## longcat

- credential present: `True` (source `credential_manager`, target `longcat`)
- configured model id: `LongCat-2.0`
- configured endpoint reachable: `True`
- configured model id observed in catalogue: `True`
- authoritative-documentation backed: `False`

| Candidate | /models URL | HTTP | Models | Note |
|---|---|---|---|---|
| configured_openai_path | `https://api.longcat.chat/openai/v1/models` | 200 | 1 |  |
| direct_openai_root_alternate | `https://api.longcat.chat/v1/models` | 404 | 0 | unparsable_error_body |

Observed model IDs: `LongCat-2.0`

## stepfun

- credential present: `True` (source `credential_manager`, target `stepfun`)
- configured model id: `step-3.7-flash`
- configured endpoint reachable: `True`
- configured model id observed in catalogue: `True`
- authoritative-documentation backed: `False`

| Candidate | /models URL | HTTP | Models | Note |
|---|---|---|---|---|
| stepfun_global_configured | `https://api.stepfun.ai/v1/models` | 200 | 16 |  |
| stepfun_cn_alternate | `https://api.stepfun.com/v1/models` | 401 | 0 | invalid_api_key |

Observed model IDs: `step-3.5-flash`, `step-3.5-flash-2603`, `stepaudio-2.5-tts`, `stepaudio-2.5-asr`, `step-image-edit-2`, `step-3.7-flash`, `stepaudio-2.5-chat`, `stepaudio-2.5-realtime`, `stepaudio-2.5-asr-stream`, `stepaudio-3-realtime-preview`, `stepaudio-3-asr-max`, `stepaudio-3-music-preview`, `stepaudio-3-chat-preview`, `stepaudio-3-gen-preview`, `stepaudio-3-tts`, `step-5-preview`

## hunyuan

- credential present: `True` (source `credential_manager`, target `hunyuan`)
- configured model id: `hy3`
- configured endpoint reachable: `False`
- configured model id observed in catalogue: `False`
- authoritative-documentation backed: `True`

| Candidate | /models URL | HTTP | Models | Note |
|---|---|---|---|---|
| tokenhub_intl_configured | `https://tokenhub-intl.tencentcloudmaas.com/v1/models` | 401 | 0 | 401002 |
| tokenhub_guangzhou_cn | `https://tokenhub.tencentcloudmaas.com/v1/models` | 401 | 0 | 401002 |
| tokenhub_us_siliconvalley | `https://tokenhub-us.tencentcloudmaas.com/v1/models` | 401 | 0 | 401002 |
| legacy_lkeap_cn | `https://api.lkeap.cloud.tencent.com/v1/models` | 401 | 0 | not_authorized |
| legacy_hunyuan_cloud_cn | `https://api.hunyuan.cloud.tencent.com/v1/models` | 401 | 0 | invalid_api_key |

