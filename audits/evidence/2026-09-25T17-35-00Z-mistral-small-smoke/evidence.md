# E3 bounded real-provider smoke + live model identity

- Started (UTC): 2026-09-25T17:21:04+00:00
- Finished (UTC): 2026-09-25T17:21:04+00:00
- Budget: {'max_tokens_per_worker': 16, 'timeout_s': 90, 'attempts_per_worker': 1}
- Credential handling: resolved in-process, used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Completed: []
- Failed: ['mistral-small-4']
- Skipped: []

| Worker | Endpoint | HTTP | Model sent | Returned model field | Identity confirmed | Tokens (in/out) | E2 linkage | Error |
|---|---|---|---|---|---|---|---|---|
| mistral-small-4 | mistral | 429 | `mistral-small-latest` | `None` | False | None/None | recorded_failure | Rate limit exceeded |

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
  "dispatch_status": "FAILED",
  "http_status": 429,
  "configured_model_sent": "mistral-small-latest",
  "provider_returned_model_field": null,
  "model_identity_confirmed_by_provider": false,
  "finish_reason": null,
  "usage": null,
  "usage_source": "provider-returned usage object (never estimated)",
  "content_preview": null,
  "error": "http_429",
  "provider_error_body": "Rate limit exceeded",
  "runtime_s": 0.197,
  "max_tokens_requested": 16,
  "e2_linkage": {
    "result": "recorded_failure",
    "request_row_id": "obs-20260925-dc6a4939"
  },
  "catalogue": {
    "observed_model_count": 46,
    "configured_model_in_catalogue": true
  }
}
```

