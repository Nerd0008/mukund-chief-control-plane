# E3 bounded real-provider smoke + live model identity

- Started (UTC): 2026-09-25T17:45:14+00:00
- Finished (UTC): 2026-09-25T17:45:17+00:00
- Budget: {'max_tokens_per_worker': 16, 'timeout_s': 90, 'attempts_per_worker': 1}
- Credential handling: resolved in-process, used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Completed: ['tencent-hunyuan-hy3']
- Failed: []
- Skipped: []

| Worker | Endpoint | HTTP | Model sent | Returned model field | Identity confirmed | Tokens (in/out) | E2 linkage | Error |
|---|---|---|---|---|---|---|---|---|
| tencent-hunyuan-hy3 | hunyuan | 200 | `hy3` | `hy3` | True | 20/16 | recorded |  |

## Per-worker detail

### tencent-hunyuan-hy3

```json
{
  "worker_id": "tencent-hunyuan-hy3",
  "adapter_created": true,
  "provider_key": "hunyuan",
  "display_name": "Tencent Hunyuan Hy3",
  "configured_api_model_id": "hy3",
  "chat_endpoint": "https://tokenhub-intl.tencentcloudmaas.com/v1/chat/completions",
  "models_endpoint": "https://tokenhub-intl.tencentcloudmaas.com/v1/models",
  "credential_present": true,
  "auth_source": "credential_manager",
  "dispatch_status": "COMPLETED",
  "http_status": 200,
  "configured_model_sent": "hy3",
  "provider_returned_model_field": "hy3",
  "model_identity_confirmed_by_provider": true,
  "finish_reason": "length",
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 16,
    "total_tokens": 36,
    "reasoning_tokens": null,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": null
  },
  "usage_source": "provider-returned usage object (never estimated)",
  "content_preview": null,
  "error": null,
  "provider_error_body": null,
  "runtime_s": 2.328,
  "max_tokens_requested": 16,
  "e2_linkage": {
    "result": "recorded",
    "request_row_id": "obs-20260925-c88cc8b7"
  },
  "catalogue": {
    "observed_model_count": 72,
    "configured_model_in_catalogue": true
  }
}
```

