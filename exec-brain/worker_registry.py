#!/usr/bin/env python3
"""E3 Worker Registry — 10-worker pool from handover authority."""

WORKER_ROSTER = [
    {
        'worker_id': 'codex-cli',
        'provider': 'openai',
        'model': 'codex-cli',
        'interface': 'cli',
        'pool_status': 'LOCKED',
        'capability_hints': ['coding', 'repository', 'debugging', 'implementation'],
        'routable': False,  # Issue #1: smoke test BLOCKED, not passed
        'auth_configured': True,
        'auth_mode': 'chatgpt',
        'exec_interface': 'codex exec --json',
        'adapter_implemented': True,
        'adapter_file': 'codex_adapter.py',
        'smoke_test': 'BLOCKED_USAGE_LIMIT',
        'cli_version': '0.155.0-alpha.9.2',
        'cli_path_configured': True,  # Issue #5: configurable path, not hardcoded
        'identity': {
            'provider': 'openai',
            'model': 'unknown',  # Issue #2: UNKNOWN until observed from execution
            'auth_mode': 'chatgpt',
            'cancellation_support': 'UNSUPPORTED',  # Issue #7
            'e2_usage_linkage': 'NOT_VERIFIED'     # Issue #6
        },
        'notes': 'Smoke test blocked by ChatGPT usage limit. Rerun after reset.'
    },
    {
        'worker_id': 'mistral-small-4',
        'provider': 'mistral',
        'model': 'mistral-small-4',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'coding', 'instruction-following', 'agents'],
        'routable': False,  # Issue #1: No credentials yet — adapter exists but auth not configured
        'auth_configured': False,
        'auth_source': 'none',
        'exec_interface': 'generic_openai_adapter (mistral)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'NOT_RUN',
        'notes': 'Generic OpenAI adapter implemented. Awaiting Mistral API key to enable smoke test.'
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
        'qualification': 'UNPROVEN',  # smoke test readiness != capability qualification
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
        'qualification': 'UNPROVEN',  # smoke test readiness != capability qualification
        'notes': 'Identity observed from provider /models. Old registry string deepseek-v4.1-flash is not an API model ID.'
    },
    {
        'worker_id': 'glm-53-flash',
        'provider': 'glm',
        'model': 'glm-5.3-flash',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'tool-use', 'agents', 'high-volume'],
        'routable': False,  # Issue #1: No credentials yet
        'auth_configured': False,
        'auth_source': 'none',
        'exec_interface': 'generic_openai_adapter (glm)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'NOT_RUN',
        'notes': 'Generic OpenAI adapter implemented. Awaiting GLM API key to enable smoke test.'
    },
    {
        'worker_id': 'qwen38-27b',
        'provider': 'qwen',
        'model': 'qwen3.8-27b',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['vision', 'multimodal', 'gui-understanding', 'screenshots'],
        'routable': False,  # Issue #1: No credentials yet
        'auth_configured': False,
        'auth_source': 'none',
        'exec_interface': 'generic_openai_adapter (qwen)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'NOT_RUN',
        'notes': 'Generic OpenAI adapter implemented. Awaiting Qwen API key to enable smoke test.'
    },
    {
        'worker_id': 'longcat-2.0',
        'provider': 'nous',
        'model': 'longcat-2.0',
        'interface': 'api',
        'pool_status': 'EVALUATE',
        'capability_hints': ['reasoning', 'coding'],
        'routable': False,  # Issue #1: auth unresolved yet
        'auth_configured': False,
        'auth_source': 'none',
        'exec_interface': 'generic_openai_adapter (longcat/nous)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'NOT_RUN',
        'notes': 'Generic OpenAI adapter implemented. Awaiting Nous API key (not OAuth) to enable smoke test.'
    },
    {
        'worker_id': 'minimax-m3',
        'provider': 'minimax',
        'model': 'minimax-m3',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'agents'],
        'routable': False,  # Issue #1: No credentials yet
        'auth_configured': False,
        'auth_source': 'none',
        'exec_interface': 'generic_openai_adapter (minimax)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'NOT_RUN',
        'notes': 'Generic OpenAI adapter implemented. Awaiting MiniMax API key to enable smoke test.'
    },
    {
        'worker_id': 'step-37-flash',
        'provider': 'step',
        'model': 'step-3.7-flash',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'fast'],
        'routable': False,  # Issue #1: No credentials yet
        'auth_configured': False,
        'auth_source': 'none',
        'exec_interface': 'generic_openai_adapter (stepfun)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'NOT_RUN',
        'notes': 'Generic OpenAI adapter implemented. Awaiting Step API key to enable smoke test.'
    },
    {
        'worker_id': 'tencent-hunyuan-hy3',
        'provider': 'tencent',
        'model': 'hunyuan-hy3',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'tool-use'],
        'routable': False,  # Issue #1: No credentials yet
        'auth_configured': False,
        'auth_source': 'none',
        'exec_interface': 'generic_openai_adapter (hunyuan)',
        'adapter_implemented': True,
        'adapter_file': 'generic_openai_adapter.py',
        'smoke_test': 'NOT_RUN',
        'notes': 'Generic OpenAI adapter implemented. Awaiting Hunyuan API key to enable smoke test.'
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
