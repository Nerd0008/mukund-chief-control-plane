# E3 bounded real-provider smoke + live model identity

- Started (UTC): 2026-09-25T17:37:20+00:00
- Finished (UTC): 2026-09-25T17:37:22+00:00
- Budget: {'max_tokens_per_worker': 16, 'timeout_s': 90, 'attempts_per_worker': 1}
- Credential handling: resolved in-process, used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Completed: []
- Failed: ['qwen38-27b']
- Skipped: []

| Worker | Endpoint | HTTP | Model sent | Returned model field | Identity confirmed | Tokens (in/out) | E2 linkage | Error |
|---|---|---|---|---|---|---|---|---|
| qwen38-27b | qwen | 403 | `qwen3.7-plus` | `None` | False | None/None | recorded_failure | code=AccessDenied.Unpurchased |

## Per-worker detail

### qwen38-27b

```json
{
  "worker_id": "qwen38-27b",
  "adapter_created": true,
  "provider_key": "qwen",
  "display_name": "Qwen3.7-Plus",
  "configured_api_model_id": "qwen3.7-plus",
  "chat_endpoint": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
  "models_endpoint": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models",
  "credential_present": true,
  "auth_source": "credential_manager",
  "dispatch_status": "FAILED",
  "http_status": 403,
  "configured_model_sent": "qwen3.7-plus",
  "provider_returned_model_field": null,
  "model_identity_confirmed_by_provider": false,
  "finish_reason": null,
  "usage": null,
  "usage_source": "provider-returned usage object (never estimated)",
  "content_preview": null,
  "error": "Access to model denied. Please make sure you are eligible for using the model.",
  "provider_error_body": "code=AccessDenied.Unpurchased",
  "runtime_s": 1.034,
  "max_tokens_requested": 16,
  "e2_linkage": {
    "result": "recorded_failure",
    "request_row_id": "obs-20260925-5a4a0d40"
  },
  "catalogue": {
    "observed_model_count": 172,
    "configured_model_in_catalogue": true
  }
}
```

