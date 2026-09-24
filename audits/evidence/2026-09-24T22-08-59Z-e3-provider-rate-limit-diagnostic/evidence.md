# E3 provider rate-limit diagnostic (one bounded call)

- Started (UTC): 2026-09-24T22:08:59+00:00
- Finished (UTC): 2026-09-24T22:08:59+00:00
- Worker: `mistral-small-4` (provider `mistral`)
- Model: `mistral-small-latest`
- Budget: {'max_tokens': 16, 'attempts': 1, 'retry': False, 'timeout_s': 90}
- Credential handling: resolved in-process via the deployed adapter; used only as an Authorization header; never printed, logged, stored or passed as a shell argument
- Header allow-list: ['retry-after', 'retry-after-ms', 'x-ratelimit-limit', 'x-ratelimit-remaining', 'x-ratelimit-reset', 'x-ratelimit-limit-requests', 'x-ratelimit-remaining-requests', 'x-ratelimit-limit-tokens', 'x-ratelimit-remaining-tokens', 'x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens', 'ratelimit-limit', 'ratelimit-remaining', 'ratelimit-reset', 'x-request-id', 'request-id', 'x-should-retry']

- HTTP status: `429`
- Non-secret rate-limit headers captured: `[]`
- Provider error (sanitized): `Rate limit exceeded`
- Provider-returned model field: `None`
- Usage: `None`

```json
{
  "worker_id": "mistral-small-4",
  "budget": {
    "max_tokens": 16,
    "attempts": 1,
    "retry": false,
    "timeout_s": 90
  },
  "credential_handling": "resolved in-process via the deployed adapter; used only as an Authorization header; never printed, logged, stored or passed as a shell argument",
  "header_allowlist": [
    "retry-after",
    "retry-after-ms",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "x-request-id",
    "request-id",
    "x-should-retry"
  ],
  "provider_key": "mistral",
  "chat_endpoint": "https://api.mistral.ai/v1/chat/completions",
  "api_model_id": "mistral-small-latest",
  "credential_present": true,
  "auth_source": "credential_manager",
  "http_status": 429,
  "provider_returned_headers": {},
  "rate_limit_headers_present": [],
  "provider_error_body_sanitized": "Rate limit exceeded",
  "provider_returned_model_field": null,
  "usage": null
}
```
