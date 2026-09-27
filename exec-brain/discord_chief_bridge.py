#!/usr/bin/env python3
"""Production entry point for a normal Discord Chief message.

The gateway calls this synchronous function in a worker thread.  It fails
closed on disabled Stage 2 and never invokes Hermes' native model resolver,
which is essential because that resolver was pinned to DeepSeek.
"""
from __future__ import annotations

from typing import Any, Dict


def dispatch_chief_message(message: str) -> Dict[str, Any]:
    from stage2_control import require_enabled
    from worker_registry import WorkerRegistry
    from e3_execution import ExecutionAdapterRegistry
    from chief_routing import ChiefRouteSelector

    state = require_enabled()
    workers = WorkerRegistry()
    adapters = ExecutionAdapterRegistry(worker_registry=workers)
    selector = ChiefRouteSelector(
        workers, adapters, allowed_workers=state.get("allowed_workers", []))
    return selector.dispatch(message)
