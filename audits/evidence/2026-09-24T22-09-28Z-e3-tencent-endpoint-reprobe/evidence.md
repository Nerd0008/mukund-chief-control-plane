# E3 Tencent TokenHub endpoint re-probe (one GET /v1/models)

- Started (UTC): 2026-09-24T22:09:28+00:00
- Finished (UTC): 2026-09-24T22:09:29+00:00
- Worker: `tencent-hunyuan-hy3` (provider `hunyuan`)
- Configured models endpoint: `https://tokenhub-intl.tencentcloudmaas.com/v1/models`
- Configured chat endpoint: `https://tokenhub-intl.tencentcloudmaas.com/v1/chat/completions`
- Configured model id: `hy3`
- Calls: {'models_get': 1, 'chat_completions': 0}
- Credential handling: resolved in-process; used only as an Authorization header; never printed, logged, stored or passed as a shell argument

- HTTP status: `401`
- Provider error code: `401002`
- Provider error message (sanitized): `The API Key does not exist or signature verification failed. Please check whether the API Key is correct. See: https://console.cloud.tencent.com/tokenhub/apikey`
- Chat completion attempted: `False`

```json
{
  "worker_id": "tencent-hunyuan-hy3",
  "provider_key": "hunyuan",
  "configured_models_endpoint": "https://tokenhub-intl.tencentcloudmaas.com/v1/models",
  "configured_chat_endpoint": "https://tokenhub-intl.tencentcloudmaas.com/v1/chat/completions",
  "configured_api_model_id": "hy3",
  "calls": {
    "models_get": 1,
    "chat_completions": 0
  },
  "credential_handling": "resolved in-process; used only as an Authorization header; never printed, logged, stored or passed as a shell argument",
  "credential_present": true,
  "auth_source": "credential_manager",
  "http_status": 401,
  "model_count": null,
  "error_code": "401002",
  "error_message_sanitized": "The API Key does not exist or signature verification failed. Please check whether the API Key is correct. See: https://console.cloud.tencent.com/tokenhub/apikey",
  "chat_completion_attempted": false
}
```
