# E3 bounded real-provider smoke + live model identity

- Started (UTC): 2026-09-25T17:27:59+00:00
- Finished (UTC): 2026-09-25T17:27:59+00:00
- Budget: {'max_tokens_per_worker': 16, 'timeout_s': 90, 'attempts_per_worker': 1}
- Credential handling: resolved in-process, used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Completed: ['mistral-small-4']
- Failed: []
- Skipped: []

| Worker | Endpoint | HTTP | Model sent | Returned model field | Identity confirmed | Tokens (in/out) | E2 linkage | Error |
|---|---|---|---|---|---|---|---|---|
| mistral-small-4 | mistral | 200 | `mistral-small-latest` | `mistral-small-latest` | True | 23/3 | recorded |  |

## Per-worker detail

### mistral-small-4

```json
{
  "worker_id": "mistral-small-4",
  "adapter_created": true,
  "provider_key": "mistral",
  "display_name": "Mistral Small 4",
  "configured_api_model_id": "mistral-small-latest",
  "chat_endpoint": "https://api.mistral.ai/v1/chat/completions",
  "models_endpoint": "https://api.mistral.ai/v1/models",
  "credential_present": true,
  "auth_source": "credential_manager",
  "dispatch_status": "COMPLETED",
  "http_status": 200,
  "configured_model_sent": "mistral-small-latest",
  "provider_returned_model_field": "mistral-small-latest",
  "model_identity_confirmed_by_provider": true,
  "finish_reason": "stop",
  "usage": {
    "prompt_tokens": 23,
    "completion_tokens": 3,
    "total_tokens": 26,
    "reasoning_tokens": null,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": null
  },
  "usage_source": "provider-returned usage object (never estimated)",
  "content_preview": "READY",
  "error": null,
  "provider_error_body": null,
  "runtime_s": 0.488,
  "max_tokens_requested": 16,
  "e2_linkage": {
    "result": "recorded",
    "request_row_id": "obs-20260925-7a1d77ee"
  },
  "catalogue": {
    "observed_model_count": 53,
    "configured_model_in_catalogue": true
  }
}
```

