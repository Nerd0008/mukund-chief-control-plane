#!/usr/bin/env python3
"""E3 Worker Registry — 10-worker pool from handover authority.

2026-09-24 post-credential verification (task
agent-e3-provider-verification-stage2-closeout-2026-09-24):

All ten roster credentials are now present in Windows Credential Manager. Each
of the seven generic API workers was reconciled against its provider's live
``GET /models`` catalogue and then given ONE bounded smoke completion
(``max_tokens=16``, single attempt, no retries) through the deployed adapter.
Observed outcome, recorded in
``audits/evidence/*-e3-provider-live-identity-probe`` and
``audits/evidence/*-e3-provider-bounded-smoke``:

* endpoints + API model IDs verified live: mistral, glm, qwen, minimax, longcat,
  stepfun (6/7);
* tencent/Hy3: endpoint (TokenHub international) and model ID ``hy3`` reconciled
  from official documentation because the stored credential is rejected
  (HTTP 401 / code 401002) so no catalogue can be read;
* **no** generic API worker produced a completion: every smoke call was refused
  by the provider at the billing/quota/entitlement/auth layer (mistral 429,
  glm 429 balance, qwen 403 unpurchased, longcat 402, minimax 402, stepfun 402,
  tencent 401). Each of the seven therefore stays ``routable=False`` with
  ``smoke_test='FAILED'`` and ``qualification='UNPROVEN'``; credential presence
  alone is never treated as routable or qualified.

E2 linkage was exercised for all seven (one ``governor.record_request()`` row
each, ids ``obs-20260924-3db12e3a``/``c87241eb``/``85e21e86``/``7f5c7fce``/
``5af88a42``/``f05452e1``/``242e4937``), so the linkage mechanism is proven even
though the recorded status is ``error``.
"""

WORKER_ROSTER = [
    {
        'worker_id': 'codex-cli',
        'provider': 'openai',
        'model': 'codex-cli',
        'interface': 'cli',
        'pool_status': 'LOCKED',
        'capability_hints': ['coding', 'repository', 'debugging', 'implementation'],
        'routable': True,  # 2026-09-23: smoke PASS + E2 linkage VERIFIED (obs-20260923-d42e34a5)
        'auth_configured': True,
        'auth_mode': 'chatgpt',
        'exec_interface': 'codex exec --json',
        'adapter_implemented': True,
        'adapter_file': 'codex_adapter.py',
        'smoke_test': 'PASS',
        'e2_usage_linkage': 'VERIFIED',  # obs-20260923-d42e34a5 (tokens null: see notes)
        'qualification': 'UNPROVEN',  # static roster default; see qualification_source
        'qualification_source': (
            'Recorded evidence-backed state of record lives in the E3 capability_registry '
            '(orchestration.db), written by scripts/e3_qualification_from_evidence.py. '
            '2026-09-23: role "builder" QUALIFIED (3 recorded executions / 3 verified '
            'passes / 3 first-pass) and role "integrator" QUALIFIED (2 / 2 / 2) for '
            'task_family "code". This static field is not updated by the harness.'),
        'cli_version': '0.155.0-alpha.16.3',
        'cli_path_configured': True,  # stable resolver: override -> PATH -> validated bin dirs
        'identity': {
            'provider': 'openai',        # reported by `codex doctor --json`
            'model': 'unknown',          # served model not exposed by CLI/runtime
            'configured_model': 'gpt-6-astra',  # config declaration, NOT execution evidence
            'auth_mode': 'chatgpt',
            'cancellation_support': 'UNSUPPORTED',  # Issue #7
            'e2_usage_linkage': 'VERIFIED'          # Issue #6
        },
        'notes': ('2026-09-23 re-validation: usage-limit blocker cleared. Hash-specific resolver '
                  'replaced (stale bin/247581e40ee272fb removed by a Codex update); CLI resolved at '
                  'bin/80f78947ad880e6e/codex.exe v0.155.0-alpha.16.3. One harmless non-interactive '
                  'smoke returned READY (exit 0). Provider usage IS exposed on turn.completed '
                  '(16207 in / 5 out); the recorded E2 row has null tokens because the extractor ran '
                  'before that fix, so no second request was spent to correct it. Serviced model '
                  'identity remains UNKNOWN.')

    },
    {
        'worker_id': 'mistral-small-4',
        'provider': 'mistral',
        'model': 'mistral-small-latest',
        'api_model_id': 'mistral-small-latest',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'coding', 'instruction-following', 'agents'],
        'routable': False,  # credential valid, endpoint+model verified, but the
                            # provider rejects live dispatch (HTTP 429)
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generic_openai_adapter (mistral)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'FAILED',
        'e2_usage_linkage': 'VERIFIED',  # error row recorded via governor.record_request()
        'qualification': 'UNPROVEN',
        'verified_2026_09_24': {
            'credential_present': True,
            'endpoint': 'https://api.mistral.ai/v1',
            'endpoint_reachable': True,
            'observed_catalogue_size': 46,
            'api_model_id_in_live_catalogue': True,
            'smoke_http_status': 429,
            'provider_error': 'Rate limit exceeded',
            'routable_reason': 'provider_429_rate_limit',
        },
        'notes': ('2026-09-24 post-credential verification: the old registry string '
                  '"mistral-small-4" is NOT an API model ID and does not exist in the live '
                  'catalogue; corrected to the observed alias `mistral-small-latest` '
                  '(dated pin `mistral-small-2603`). One bounded smoke call (max_tokens=16) '
                  'returned HTTP 429 "Rate limit exceeded" — no tokens were consumed and no '
                  'completion was produced, so the worker is NOT execution-ready and stays '
                  'routable=false; qualification remains UNPROVEN.'),
    },
    {
        'worker_id': 'google-nano-banana-2',
        'provider': 'google',
        'display_name': 'Google Nano Banana 2',
        'model': 'gemini-3.1-flash-image',  # CONFIRMED by owner after live /models discovery 2026-09-23
        'api_model_id': 'gemini-3.1-flash-image',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['image-generation', 'image-editing', 'vision'],
        'routable': True,  # smoke test PASS + E2 linkage VERIFIED + no security blocker
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generativelanguage.googleapis.com/v1beta generateContent (IMAGE modality)',
        'adapter_implemented': True,
        'adapter_file': 'gemini_adapter.py',
        'smoke_test': 'PASS',
        'e2_usage_linkage': 'VERIFIED',  # obs-20260923-d44f030a
        'qualification': 'UNPROVEN',  # static roster default; see qualification_source
        'qualification_source': (
            'Recorded evidence-backed state of record lives in the E3 capability_registry '
            '(orchestration.db). 2026-09-23: role "vision" EVALUATING — 2 recorded '
            'executions, 1 verified pass (a real 1024x1024 JPEG that decoded cleanly), '
            '1 recorded failure (the earlier no-image response). Not qualified: the bar '
            'needs >=2 verified passes and the earlier failure remains on record.'),
        'notes': 'api_model_id confirmed live via /models (59 models observed) and owner confirmation. Image worker only: gemini-3.6-flash NOT configured as image worker (no image-output evidence).'
    },
    {
        'worker_id': 'deepseek-v41-flash',
        'provider': 'deepseek',
        'display_name': 'DeepSeek V4.1 Flash',
        'model': 'deepseek-flash',  # OBSERVED from /models endpoint 2026-09-23
        'api_model_id': 'deepseek-flash',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'coding', 'long-context', 'agents'],
        'routable': True,  # smoke test PASS + E2 linkage VERIFIED + no security issue
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'https://api.deepseek.com/chat/completions',
        'adapter_implemented': True,
        'adapter_file': 'deepseek_adapter.py',
        'smoke_test': 'PASS',
        'e2_usage_linkage': 'VERIFIED',  # obs-20260923-44da95cd
        'qualification': 'UNPROVEN',  # static roster default; see qualification_source
        'qualification_source': (
            'Recorded evidence-backed state of record lives in the E3 capability_registry '
            '(orchestration.db). 2026-09-23: role "builder" QUALIFIED (8 recorded '
            'executions / 8 verified passes / 3 first-pass, 0 recorded failures) for '
            'task_family "code". This static field is not updated by the harness.'),
        'notes': 'Identity observed from provider /models. Old registry string deepseek-v4.1-flash is not an API model ID.'
    },
    {
        'worker_id': 'glm-53-flash',
        'provider': 'glm',
        'model': 'glm-5.3-flash',
        'api_model_id': 'glm-5.3-flash',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'tool-use', 'agents', 'high-volume'],
        'routable': False,  # credential valid, endpoint+model verified, but the
                            # account has no balance/resource package
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generic_openai_adapter (glm)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'FAILED',
        'e2_usage_linkage': 'VERIFIED',
        'qualification': 'UNPROVEN',
        'verified_2026_09_24': {
            'credential_present': True,
            'endpoint': 'https://api.z.ai/api/paas/v4',
            'endpoint_reachable': True,
            'observed_catalogue_size': 11,
            'api_model_id_in_live_catalogue': True,
            'smoke_http_status': 429,
            'provider_error': 'Insufficient balance or no resource package. Please recharge.',
            'routable_reason': 'provider_account_has_no_balance',
        },
        'notes': ('2026-09-24 post-credential verification: moved from the legacy '
                  'BigModel CN host to the Z.ai international host (both answered 200 with '
                  'the same 11 models; international is the intended route). `glm-5.3-flash` '
                  'was observed in the live catalogue. One bounded smoke call returned HTTP 429 '
                  '"Insufficient balance or no resource package" — account billing blocker, not '
                  'an adapter/model fault; routable=false, qualification UNPROVEN.'),
    },
    {
        'worker_id': 'qwen38-27b',
        'provider': 'qwen',
        'model': 'qwen3.8-27b',
        'api_model_id': 'qwen3.8-27b',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['vision', 'multimodal', 'gui-understanding', 'screenshots'],
        'routable': False,  # credential valid on the international host, but the
                            # account has not purchased this model
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generic_openai_adapter (qwen)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'FAILED',
        'e2_usage_linkage': 'VERIFIED',
        'qualification': 'UNPROVEN',
        'verified_2026_09_24': {
            'credential_present': True,
            'endpoint': 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
            'endpoint_reachable': True,
            'observed_catalogue_size': 172,
            'api_model_id_in_live_catalogue': True,
            'smoke_http_status': 403,
            'provider_error_code': 'AccessDenied.Unpurchased',
            'provider_error': 'Access to model denied. Please make sure you are eligible for using the model.',
            'routable_reason': 'provider_model_not_purchased_for_this_account',
        },
        'notes': ('2026-09-24 post-credential verification: the credential is an Alibaba '
                  'Model Studio *international* key — the CN dashscope host rejected it with 401 '
                  'invalid_api_key, while dashscope-intl answered 200 with 172 models including '
                  '`qwen3.8-27b`. One bounded smoke call returned HTTP 403 '
                  'AccessDenied.Unpurchased: the model exists but is not enabled/purchased on this '
                  'account, so routable=false and qualification remains UNPROVEN.'),
    },
    {
        'worker_id': 'longcat-2.0',
        'provider': 'longcat',
        'model': 'LongCat-2.0',
        'api_model_id': 'LongCat-2.0',
        'interface': 'api',
        'pool_status': 'EVALUATE',
        'capability_hints': ['reasoning', 'coding'],
        'routable': False,  # direct endpoint + model verified; account has no quota
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generic_openai_adapter (longcat)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'FAILED',
        'e2_usage_linkage': 'VERIFIED',
        'qualification': 'UNPROVEN',
        'verified_2026_09_24': {
            'credential_present': True,
            'endpoint': 'https://api.longcat.chat/openai',
            'endpoint_reachable': True,
            'observed_catalogue_size': 1,
            'api_model_id_in_live_catalogue': True,
            'smoke_http_status': 402,
            'provider_error': 'Call failed: Insufficient token quota.',
            'routable_reason': 'provider_account_token_quota_exhausted',
        },
        'notes': ('2026-09-24 post-credential verification: the direct LongCat platform '
                  'endpoint work was already correct and is intentionally preserved — '
                  'https://api.longcat.chat/openai/v1/models answered 200 with `LongCat-2.0` '
                  'observed (the bare /v1 path 404s). One bounded smoke call returned HTTP 402 '
                  '"Insufficient token quota": account quota blocker, not an adapter fault; '
                  'routable=false, qualification UNPROVEN.'),
    },
    {
        'worker_id': 'minimax-m3',
        'provider': 'minimax',
        'model': 'MiniMax-M3',
        'api_model_id': 'MiniMax-M3',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'agents'],
        'routable': False,  # endpoint + case-correct model verified; no balance
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generic_openai_adapter (minimax)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'FAILED',
        'e2_usage_linkage': 'VERIFIED',
        'qualification': 'UNPROVEN',
        'verified_2026_09_24': {
            'credential_present': True,
            'endpoint': 'https://api.minimax.io/v1',
            'endpoint_reachable': True,
            'observed_catalogue_size': 8,
            'api_model_id_in_live_catalogue': True,
            'smoke_http_status': 402,
            'provider_error': 'insufficient balance (1008)',
            'routable_reason': 'provider_account_insufficient_balance',
        },
        'notes': ('2026-09-24 post-credential verification: the API model ID is '
                  'case-sensitive `MiniMax-M3`; the lower-case "minimax-m3" is not in the live '
                  'catalogue and was corrected. The international host api.minimax.io answered '
                  '200 with 8 models (api.minimaxi.com CN rejected the key with 401). One bounded '
                  'smoke call returned HTTP 402 "insufficient balance (1008)" — billing blocker; '
                  'routable=false, qualification UNPROVEN.'),
    },
    {
        'worker_id': 'step-37-flash',
        'provider': 'step',
        'model': 'step-3.7-flash',
        'api_model_id': 'step-3.7-flash',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'fast'],
        'routable': False,  # global endpoint + model verified; account quota exhausted
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generic_openai_adapter (stepfun)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'FAILED',
        'e2_usage_linkage': 'VERIFIED',
        'qualification': 'UNPROVEN',
        'verified_2026_09_24': {
            'credential_present': True,
            'endpoint': 'https://api.stepfun.ai/v1',
            'endpoint_reachable': True,
            'observed_catalogue_size': 16,
            'api_model_id_in_live_catalogue': True,
            'smoke_http_status': 402,
            'provider_error': 'You exceeded your current quota, please check your plan and billing details',
            'routable_reason': 'provider_account_quota_exceeded',
        },
        'notes': ('2026-09-24 post-credential verification (StepFun global API/provider '
                  'naming): the stored credential is a StepFun *global* account key — the CN host '
                  'api.stepfun.com rejected it with 401 invalid_api_key while the global host '
                  'api.stepfun.ai answered 200 with 16 models including `step-3.7-flash`; the '
                  'adapter was moved to the global host. One bounded smoke call returned HTTP 402 '
                  '"You exceeded your current quota": billing blocker; routable=false, '
                  'qualification UNPROVEN.'),
    },
    {
        'worker_id': 'tencent-hunyuan-hy3',
        'provider': 'tencent',
        'model': 'hy3',
        'api_model_id': 'hy3',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'tool-use'],
        'routable': False,  # endpoint+model reconciled, but the stored credential is
                            # rejected by the provider at every TokenHub region
        'auth_configured': True,
        'auth_source': 'credential_manager',
        'exec_interface': 'generic_openai_adapter (hunyuan)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'FAILED',
        'e2_usage_linkage': 'VERIFIED',
        'qualification': 'UNPROVEN',
        'verified_2026_09_24': {
            'credential_present': True,
            'endpoint': 'https://tokenhub-intl.tencentcloudmaas.com/v1',
            'endpoint_reachable': False,
            'endpoint_probe_http_status': 401,
            'endpoint_probe_error_code': '401002',
            'api_model_id_source': 'official TokenHub documentation table (Hy3 -> hy3), not a guessed name',
            'api_model_id_in_live_catalogue': None,
            'catalogue_unobservable_reason': 'the credential is rejected, so GET /v1/models cannot be read',
            'smoke_http_status': 401,
            'provider_error': 'The API Key does not exist or signature verification failed.',
            'routable_reason': 'provider_rejects_stored_credential_invalid_api_key',
        },
        'notes': ('2026-09-24 post-credential verification (Tencent international TokenHub/'
                  'Hy3): Tencent\'s international LLM gateway is TokenHub — documented base '
                  'https://tokenhub-intl.tencentcloudmaas.com/v1 (Singapore/global), model ID '
                  '`hy3` per the official supported-model table. The legacy hosts '
                  'api.hunyuan.cloud.tencent.com (invalid_api_key) and api.lkeap.cloud.tencent.com '
                  '(not_authorized) are deprecated CN routes and were replaced. The stored '
                  'credential is nevertheless rejected: GET /v1/models and one bounded chat call '
                  'both return HTTP 401 code 401002 (CodeInvalidAPIKey) on the intl, Guangzhou and '
                  'Silicon Valley TokenHub hosts. Provider identity is therefore documentation-'
                  'derived only and the credential is an unresolved EXTERNAL provider blocker — '
                  'owner must re-issue a TokenHub API key at '
                  'https://console.tencentcloud.com/tokenhub/apikey (or confirm the correct '
                  'product/account). routable=false, qualification UNPROVEN.'),
    }
]


class WorkerRegistry:
    """Manages the 10-worker pool."""

    def __init__(self):
        self.workers = {w['worker_id']: w for w in WORKER_ROSTER}

    def get_worker(self, worker_id):
        """Get a worker by ID."""
        return self.workers.get(worker_id)

    def get_routable_workers(self):
        """Get all currently routable workers.
        
        Issue #1: A worker is routable ONLY if it has:
        - Configured execution access
        - Implemented execution adapter
        - Successful smoke test
        """
        return {wid: w for wid, w in self.workers.items() if w.get('routable')}

    def get_workers_by_capability(self, capability):
        """Get workers that have a capability hint."""
        return {
            wid: w for wid, w in self.workers.items()
            if capability in w.get('capability_hints', [])
        }

    def get_workers_by_pool_status(self, status):
        """Get workers by pool status (LOCKED, EVALUATE, BENCHMARK)."""
        return {
            wid: w for wid, w in self.workers.items()
            if w.get('pool_status') == status
        }

    def get_all_workers(self):
        """Get all workers."""
        return self.workers.copy()

    def get_pool_summary(self):
        """Get summary of pool status."""
        summary = {}
        for wid, w in self.workers.items():
            status = w.get('pool_status', 'UNKNOWN')
            if status not in summary:
                summary[status] = []
            summary[status].append(wid)
        return summary

    def get_readiness_summary(self):
        """Get readiness summary for all workers."""
        readiness = {}
        for wid, w in self.workers.items():
            has_adapter = w.get('adapter_implemented', False)
            smoke = w.get('smoke_test', 'NOT_RUN')
            auth = w.get('auth_configured', False)
            readiness[wid] = {
                'pool_status': w.get('pool_status'),
                'adapter': has_adapter,
                'smoke_test': smoke,
                'auth': auth,
                'routable': w.get('routable', False)
            }
        return readiness
