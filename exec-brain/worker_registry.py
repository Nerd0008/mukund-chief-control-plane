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
        'routable': False  # E2 observed-only; CLI automation TBD
    },
    {
        'worker_id': 'mistral-small-4',
        'provider': 'mistral',
        'model': 'mistral-small-4',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'coding', 'instruction-following', 'agents'],
        'routable': True
    },
    {
        'worker_id': 'google-nano-banana-2',
        'provider': 'google',
        'model': 'nano-banana-2',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['image-generation', 'image-editing', 'vision'],
        'routable': True
    },
    {
        'worker_id': 'deepseek-v41-flash',
        'provider': 'deepseek',
        'model': 'deepseek-v4.1-flash',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'coding', 'long-context', 'agents'],
        'routable': True
    },
    {
        'worker_id': 'glm-53-flash',
        'provider': 'glm',
        'model': 'glm-5.3-flash',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['reasoning', 'tool-use', 'agents', 'high-volume'],
        'routable': True
    },
    {
        'worker_id': 'qwen38-27b',
        'provider': 'qwen',
        'model': 'qwen3.8-27b',
        'interface': 'api',
        'pool_status': 'LOCKED',
        'capability_hints': ['vision', 'multimodal', 'gui-understanding', 'screenshots'],
        'routable': True
    },
    {
        'worker_id': 'longcat-2.0',
        'provider': 'nous',
        'model': 'longcat-2.0',
        'interface': 'api',
        'pool_status': 'EVALUATE',
        'capability_hints': ['reasoning', 'coding'],
        'routable': True
    },
    {
        'worker_id': 'minimax-m3',
        'provider': 'minimax',
        'model': 'minimax-m3',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'agents'],
        'routable': True
    },
    {
        'worker_id': 'step-37-flash',
        'provider': 'step',
        'model': 'step-3.7-flash',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'fast'],
        'routable': True
    },
    {
        'worker_id': 'tencent-hunyuan-hy3',
        'provider': 'tencent',
        'model': 'hunyuan-hy3',
        'interface': 'api',
        'pool_status': 'BENCHMARK',
        'capability_hints': ['reasoning', 'coding', 'tool-use'],
        'routable': True
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
        """Get all currently routable workers."""
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
