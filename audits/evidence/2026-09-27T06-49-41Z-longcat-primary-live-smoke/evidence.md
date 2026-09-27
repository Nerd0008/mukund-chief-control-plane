# E3 bounded real-provider smoke + live model identity

- Started (UTC): 2026-09-27T06:49:41+00:00
- Finished (UTC): 2026-09-27T06:49:43+00:00
- Budget: {'max_tokens_per_worker': 16, 'timeout_s': 90, 'attempts_per_worker': 1}
- Credential handling: resolved in-process, used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Completed: ['longcat-2.0']
- Failed: []
- Skipped: []

| Worker | Endpoint | HTTP | Model sent | Returned model field | Identity confirmed | Tokens (in/out) | E2 linkage | Error |
|---|---|---|---|---|---|---|---|---|
| longcat-2.0 | longcat | 200 | `LongCat-2.0` | `LongCat-2.0` | True | 18/2 | recorded |  |

## Per-worker detail

### longcat-2.0

```json
{
  "worker_id": "longcat-2.0",
  "adapter_created": true,
  "provider_key": "longcat",
  "display_name": "LongCat 2.0",
  "configured_api_model_id": "LongCat-2.0",
  "chat_endpoint": "https://api.longcat.chat/openai/v1/chat/completions",
  "models_endpoint": "https://api.longcat.chat/openai/v1/models",
  "credential_present": true,
  "auth_source": "credential_manager",
  "dispatch_status": "COMPLETED",
  "http_status": 200,
  "configured_model_sent": "LongCat-2.0",
  "provider_returned_model_field": "LongCat-2.0",
  "model_identity_confirmed_by_provider": true,
  "finish_reason": "stop",
  "usage": {
    "prompt_tokens": 18,
    "completion_tokens": 2,
    "total_tokens": 20,
    "reasoning_tokens": null,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": null
  },
  "usage_source": "provider-returned usage object (never estimated)",
  "content_preview": "READY",
  "error": null,
  "provider_error_body": null,
  "runtime_s": 1.748,
  "max_tokens_requested": 16,
  "e2_linkage": {
    "result": "recorded",
    "request_row_id": "obs-20260927-1a7aed65"
  },
  "catalogue": {
    "observed_model_count": 2,
    "configured_model_in_catalogue": true
  }
}
```

