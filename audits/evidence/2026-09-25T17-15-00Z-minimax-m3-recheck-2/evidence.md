# E3 bounded real-provider smoke + live model identity

- Started (UTC): 2026-09-25T17:07:57+00:00
- Finished (UTC): 2026-09-25T17:08:00+00:00
- Budget: {'max_tokens_per_worker': 16, 'timeout_s': 90, 'attempts_per_worker': 1}
- Credential handling: resolved in-process, used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Completed: ['minimax-m3']
- Failed: []
- Skipped: []

| Worker | Endpoint | HTTP | Model sent | Returned model field | Identity confirmed | Tokens (in/out) | E2 linkage | Error |
|---|---|---|---|---|---|---|---|---|
| minimax-m3 | minimax | 200 | `MiniMax-M3` | `MiniMax-M3` | True | 184/16 | recorded |  |

## Per-worker detail

### minimax-m3

```json
{
  "worker_id": "minimax-m3",
  "adapter_created": true,
  "provider_key": "minimax",
  "display_name": "MiniMax M3",
  "configured_api_model_id": "MiniMax-M3",
  "chat_endpoint": "https://api.minimax.io/v1/chat/completions",
  "models_endpoint": "https://api.minimax.io/v1/models",
  "credential_present": true,
  "auth_source": "credential_manager",
  "dispatch_status": "COMPLETED",
  "http_status": 200,
  "configured_model_sent": "MiniMax-M3",
  "provider_returned_model_field": "MiniMax-M3",
  "model_identity_confirmed_by_provider": true,
  "finish_reason": "length",
  "usage": {
    "prompt_tokens": 184,
    "completion_tokens": 16,
    "total_tokens": 200,
    "reasoning_tokens": null,
    "prompt_cache_hit_tokens": 128,
    "prompt_cache_miss_tokens": null
  },
  "usage_source": "provider-returned usage object (never estimated)",
  "content_preview": "<think>\nThe user is asking me to reply with a single word: \"",
  "error": null,
  "provider_error_body": null,
  "runtime_s": 1.727,
  "max_tokens_requested": 16,
  "e2_linkage": {
    "result": "recorded",
    "request_row_id": "obs-20260925-24a64dff"
  },
  "catalogue": {
    "observed_model_count": 8,
    "configured_model_in_catalogue": true
  }
}
```

