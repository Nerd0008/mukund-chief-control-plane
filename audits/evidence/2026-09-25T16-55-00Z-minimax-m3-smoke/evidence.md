# E3 bounded real-provider smoke + live model identity

- Started (UTC): 2026-09-25T16:25:08+00:00
- Finished (UTC): 2026-09-25T16:25:09+00:00
- Budget: {'max_tokens_per_worker': 16, 'timeout_s': 90, 'attempts_per_worker': 1}
- Credential handling: resolved in-process, used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Completed: []
- Failed: ['minimax-m3']
- Skipped: []

| Worker | Endpoint | HTTP | Model sent | Returned model field | Identity confirmed | Tokens (in/out) | E2 linkage | Error |
|---|---|---|---|---|---|---|---|---|
| minimax-m3 | minimax | 402 | `MiniMax-M3` | `None` | False | None/None | recorded_failure | insufficient balance (1008) |

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
  "dispatch_status": "FAILED",
  "http_status": 402,
  "configured_model_sent": "MiniMax-M3",
  "provider_returned_model_field": null,
  "model_identity_confirmed_by_provider": false,
  "finish_reason": null,
  "usage": null,
  "usage_source": "provider-returned usage object (never estimated)",
  "content_preview": null,
  "error": "insufficient balance (1008)",
  "provider_error_body": "insufficient balance (1008)",
  "runtime_s": 0.334,
  "max_tokens_requested": 16,
  "e2_linkage": {
    "result": "recorded_failure",
    "request_row_id": "obs-20260925-8fca9021"
  },
  "catalogue": {
    "observed_model_count": 8,
    "configured_model_in_catalogue": true
  }
}
```

