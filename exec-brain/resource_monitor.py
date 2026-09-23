#!/usr/bin/env python3
"""E4 Resource Continuity — resource monitoring, runway calculation, checkpointing.

Monitors provider/resource usage, predicts exhaustion, manages checkpoint/state
handover, and coordinates equivalent-worker failover.

Integrates with E2 governor for usage data and E3 orchestration_db for checkpoint state.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

GOV_DIR = Path(__file__).parent


class ResourceMonitor:
    """Monitor resource usage and predict exhaustion."""

    def __init__(self, orchestration_con, governor_con=None):
        self.orchestration_con = orchestration_con
        self.gov_con = governor_con

    def get_resource_snapshot(self) -> Dict[str, Any]:
        """Get current resource state from governor."""
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "providers": {},
            "total_requests_today": 0,
            "total_cost_today": 0.0,
        }

        if self.gov_con is None:
            return snapshot

        try:
            rows = self.gov_con.execute(
                """SELECT provider, model, 
                          SUM(input_tokens) as total_input,
                          SUM(output_tokens) as total_output,
                          COUNT(*) as request_count,
                          AVG(latency_ms) as avg_latency
                   FROM observed_request 
                   WHERE date(created_at) = date('now')
                   GROUP BY provider, model"""
            ).fetchall()

            for row in rows:
                provider, model, input_tok, output_tok, count, avg_lat = row
                snapshot["providers"][f"{provider}/{model}"] = {
                    "input_tokens": input_tok or 0,
                    "output_tokens": output_tok or 0,
                    "request_count": count,
                    "avg_latency_ms": avg_lat,
                }
                snapshot["total_requests_today"] += count
        except Exception:
            pass

        return snapshot

    def calculate_runway(self, provider: str, model: str,
                         daily_budget: float = None) -> Dict[str, Any]:
        """Calculate resource runway (time until exhaustion)."""
        runway = {
            "provider": provider,
            "model": model,
            "status": "unknown",
            "estimated_hours_remaining": None,
            "burn_rate_per_hour": None,
        }

        if self.gov_con is None:
            return runway

        try:
            # Calculate burn rate from last 24 hours
            row = self.gov_con.execute(
                """SELECT COUNT(*) as count,
                          SUM(input_tokens) as input_tok
                   FROM observed_request 
                   WHERE provider=? AND model=?
                   AND created_at >= datetime('now', '-24 hours')""",
                (provider, model)
            ).fetchone()

            count, input_tok = row
            if count > 0:
                runway["burn_rate_per_hour"] = count / 24.0
                if daily_budget and input_tok:
                    hourly_cost_estimate = (input_tok / 24.0) * 0.000001  # rough
                    if hourly_cost_estimate > 0:
                        runway["estimated_hours_remaining"] = daily_budget / hourly_cost_estimate
                        runway["status"] = "healthy" if runway["estimated_hours_remaining"] > 24 else "degraded"
                    else:
                        runway["status"] = "healthy"
        except Exception:
            pass

        return runway

    def predict_exhaustion(self, threshold_hours: float = 4.0) -> List[Dict[str, Any]]:
        """Predict which resources will exhaust within threshold."""
        predictions = []

        if self.gov_con is None:
            return predictions

        try:
            rows = self.gov_con.execute(
                """SELECT provider, model, COUNT(*) as count
                   FROM observed_request 
                   WHERE created_at >= datetime('now', '-1 hour')
                   GROUP BY provider, model"""
            ).fetchall()

            for row in rows:
                provider, model, count = row
                if count > 0:
                    hours_remaining = 10000 / count  # simplified
                    if hours_remaining < threshold_hours:
                        predictions.append({
                            "provider": provider,
                            "model": model,
                            "estimated_hours_remaining": hours_remaining,
                            "severity": "critical" if hours_remaining < 1 else "warning",
                        })
        except Exception:
            pass

        return predictions


class CheckpointManager:
    """Manage task checkpoints for state handover."""

    def __init__(self, con):
        self.con = con

    def save_checkpoint(self, task_id: str, node_id: str,
                        state: Dict[str, Any]) -> str:
        """Save a checkpoint for a task node."""
        import uuid
        checkpoint_id = f"ckpt-{uuid.uuid4().hex[:12]}"
        ts = datetime.utcnow().isoformat()

        self.con.execute(
            """INSERT INTO resource_checkpoint 
               (checkpoint_id, task_id, node_id, state_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (checkpoint_id, task_id, node_id, json.dumps(state), ts)
        )
        self.con.commit()
        return checkpoint_id

    def get_latest_checkpoint(self, task_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest checkpoint for a task node."""
        row = self.con.execute(
            """SELECT state_json, created_at FROM resource_checkpoint
               WHERE task_id=? AND node_id=?
               ORDER BY created_at DESC LIMIT 1""",
            (task_id, node_id)
        ).fetchone()

        if row:
            return {
                "state": json.loads(row[0]),
                "created_at": row[1],
            }
        return None

    def list_checkpoints(self, task_id: str) -> List[Dict[str, Any]]:
        """List all checkpoints for a task."""
        rows = self.con.execute(
            """SELECT checkpoint_id, node_id, created_at 
               FROM resource_checkpoint WHERE task_id=?
               ORDER BY created_at""",
            (task_id,)
        ).fetchall()

        return [{"checkpoint_id": r[0], "node_id": r[1], "created_at": r[2]} for r in rows]


class EquivalentFailover:
    """Manage equivalent-worker failover."""

    def __init__(self, capability_registry):
        self.registry = capability_registry

    def find_equivalent_worker(self, failed_worker_id: str,
                               task_family: str,
                               role: str,
                               required_capabilities: List[str] = None) -> Optional[Dict[str, Any]]:
        """Find an equivalent worker to replace a failed one."""
        required_capabilities = required_capabilities or []
        candidates = self.registry.find_qualified_workers(task_family, role)

        # Exclude the failed worker
        candidates = [c for c in candidates if c != failed_worker_id]

        if not candidates:
            return None

        # For now, return first candidate (could be enhanced with capability scoring)
        return {
            "worker_id": candidates[0],
            "task_family": task_family,
            "role": role,
            "equivalence": "partial",  # since different models have different strengths
            "reason": "Same role/task family qualified worker available",
        }

    def find_best_available(self, task_family: str, role: str,
                           exclude: List[str] = None) -> Optional[Dict[str, Any]]:
        """Find the best available worker, excluding specified ones."""
        exclude = exclude or []
        candidates = self.registry.find_qualified_workers(task_family, role)
        candidates = [c for c in candidates if c not in exclude]

        if not candidates:
            return None

        return {
            "worker_id": candidates[0],
            "task_family": task_family,
            "role": role,
        }

    def escalate_no_equivalent(self, failed_worker_id: str,
                               task_family: str,
                               role: str) -> Dict[str, Any]:
        """Generate escalation record when no equivalent worker exists."""
        return {
            "escalation_type": "no_equivalent_worker",
            "failed_worker": failed_worker_id,
            "task_family": task_family,
            "role": role,
            "timestamp": datetime.utcnow().isoformat(),
            "owner_action": "Provide alternative worker or approve quality floor reduction",
            "auto_approve": False,
        }
