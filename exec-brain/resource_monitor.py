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


# ─── E4 resource continuity — provider content-side stop pressure ────
#
# The continuity view measured only tokens, cost and time-to-exhaustion, so a
# provider (or provider/model pair) that repeatedly withholds content while
# still consuming prompt tokens was reported as healthy capacity. These helpers
# add a *recorded-evidence only* view of that pressure: per worker/provider/model
# the attempts observed, the content-side stops observed, the stop rate with its
# sample size, the last observed provider finishReason, the last recorded stop
# time and a bounded boolean flag.
#
# Guarantees:
# * read-only — nothing here writes a store and no E1/E2 store is touched;
# * observation only — a flagged group is information for the operator and an
#   explicit E4/owner decision, never an automatic worker swap, re-dispatch,
#   failover, retry or safe-mode entry;
# * no fabricated rate — a rate is only reported with its sample size, and is
#   ``None`` (rendered "unknown") when no classified attempt was recorded;
# * no provider call — every value comes from rows/artifacts already on disk.

# Marker key the execution leg writes into an evidence row's structured
# deterministic-test results when its content-stop classification ran. A row
# recorded before that classification existed does not carry it, so its attempts
# are counted as *unclassified* rather than silently counted as stop-free.
CONTENT_STOP_LEDGER_KEY = "content_stop_stops"
CONTENT_STOP_LEDGER_KEYS = ("content_stop_stops", "content_stop_retries",
                            "content_stop_finish_reasons")

# Provider-documented content-side stop reasons. The canonical set is owned by
# the E3 execution leg and imported lazily; this mirror is only the fallback used
# when that module cannot be imported (E4 read on its own).
CONTENT_SIDE_STOP_FINISH_REASONS_FALLBACK = frozenset({
    "IMAGE_RECITATION", "RECITATION", "SAFETY", "IMAGE_SAFETY",
    "PROHIBITED_CONTENT", "BLOCKLIST", "SPII",
})

# promptFeedback keys that report a content-side block at prompt level.
CONTENT_SIDE_BLOCK_FEEDBACK_KEYS = ("blockReason", "block_reason")

# Bounds on the "content was withheld at a measurable rate" boolean.
#
# The only recorded measurement of content-side withholding on this roster is
# the bounded Google series
# (audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/): 2 of 9
# identical, deterministic, single-shot image requests returned
# finishReason=IMAGE_RECITATION with an empty part list and 0 candidate tokens —
# a recorded rate of 0.222, while the same request returned a decodable image on
# the other 7. The threshold (0.2) sits just below that recorded rate so the one
# real measurement would flag; the minimum sample (5) keeps a single unlucky call
# from being reported as a rate on its own, since the bounded per-node path
# records at most 3 dispatch attempts for one node. Both bounds only bound the
# *flag*: the raw rate, its sample size and the last finishReason are reported
# whether or not the flag fires.
MEASURABLE_CONTENT_STOP_RATE = 0.2
MEASURABLE_CONTENT_STOP_MIN_SAMPLE = 5

# Statuses a pressure group can carry.
PRESSURE_STATUS_UNKNOWN = "unknown"
PRESSURE_STATUS_CLEAN = "clean"
PRESSURE_STATUS_STOPS_RECORDED_BELOW_BOUND = "stops_recorded_below_bound"
PRESSURE_STATUS_PRESSURED = "pressured"

PRESSURE_DECISION_NOTE = (
    "observation only — no automatic worker swap, re-dispatch, failover, retry "
    "or safe-mode entry; any failover or re-request stays an explicit E4/owner "
    "decision")


def content_side_stop_finish_reasons() -> frozenset:
    """The canonical provider content-side stop reasons (E3-owned, lazily)."""
    try:
        from e3_execution import CONTENT_SIDE_STOP_FINISH_REASONS
        return frozenset(CONTENT_SIDE_STOP_FINISH_REASONS)
    except Exception:  # noqa: BLE001 — E4 must not hard-depend on the E3 leg
        return CONTENT_SIDE_STOP_FINISH_REASONS_FALLBACK


def _parse_ledger(raw: Any) -> Optional[Dict[str, Any]]:
    """Parse an evidence row's structured results, tolerating absence."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _recorded_stop_reason(observation: Dict[str, Any],
                          stop_reasons: frozenset) -> Optional[str]:
    """The recorded content-side stop reason of a series observation, else None.

    Mirrors the execution leg's rule exactly: only provider-returned
    ``finishReason`` / ``candidate_finish_reasons`` values in the documented
    content-side set, or a recorded prompt-level block reason. Never inferred.
    """
    values = [observation.get("finish_reason")] + list(
        observation.get("candidate_finish_reasons") or [])
    for reason in values:
        if reason and reason in stop_reasons:
            return str(reason)
    feedback = observation.get("prompt_feedback")
    if isinstance(feedback, dict):
        for key in CONTENT_SIDE_BLOCK_FEEDBACK_KEYS:
            if feedback.get(key):
                return str(feedback[key])
    return None


def _sort_key(timestamp: Optional[str]) -> str:
    """Order ISO-ish timestamps from either the store or a recorded artifact."""
    if not timestamp:
        return ""
    return str(timestamp).replace("T", " ").replace("+00:00", "")


def evidence_row_ledgers(con, source: str = "orchestration_store.performance_evidence"
                         ) -> List[Dict[str, Any]]:
    """One attempt-ledger summary per recorded ``performance_evidence`` row.

    Read-only. Columns are selected explicitly and read positionally, so both a
    ``sqlite3.Row`` connection and a plain tuple connection work. Every value is
    read from the row: ``attempts`` is the per-dispatch verification ledger the
    execution leg appends once per dispatch, so its length *is* the dispatch
    count; ``content_stop_stops`` is the number of dispatches that dispatch-time
    classification attributed to a provider content-side stop. A row that carries
    no ``content_stop_stops`` key predates that classification and is reported as
    unclassified, never as stop-free.
    """
    if con is None:
        return []
    rows = con.execute(
        "SELECT evidence_id, worker_id, provider, model, deterministic_test_results, "
        "failure_attribution, retries, timestamp, dag_node_id "
        "FROM performance_evidence").fetchall()

    ledgers = []
    for row in rows:
        parsed = _parse_ledger(row[4])
        ledger_readable = parsed is not None
        family = parsed if parsed is not None else {}
        has_family = any(key in family for key in CONTENT_STOP_LEDGER_KEYS)
        attempts = None
        if ledger_readable:
            recorded = family.get("attempts")
            if isinstance(recorded, list):
                attempts = len(recorded)
        classified = attempts if (
            attempts is not None
            and family.get(CONTENT_STOP_LEDGER_KEY) is not None) else 0
        stops = _as_int(family.get(CONTENT_STOP_LEDGER_KEY)) if classified else 0
        reasons = []
        if classified:
            for reason in family.get("content_stop_finish_reasons") or []:
                if reason and reason not in reasons:
                    reasons.append(reason)
        ledgers.append({
            "source": source,
            "evidence_id": row[0],
            "worker_id": row[1] or "unknown",
            "provider": row[2] or "unknown",
            "model": row[3] or "unknown",
            "attempts_recorded": attempts,
            "attempts_classified": classified,
            "content_stops_observed": stops or 0,
            "finish_reasons": reasons,
            "ledger_readable": ledger_readable,
            "content_stop_ledger_recorded": has_family,
            "failure_attribution": row[5],
            "timestamp": row[7],
            "dag_node_id": row[8],
        })
    return ledgers


def recorded_series_ledger(artifact_path, provider: Optional[str] = None,
                           model: Optional[str] = None,
                           source: str = "recorded_provider_series"
                           ) -> Dict[str, Any]:
    """Attempt ledger for a recorded provider series artifact (0 provider calls).

    Reads an already-recorded series file verbatim (e.g. the ``observations.json``
    of ``audits/evidence/2026-09-24T01-44-32Z-e3-google-image-repeat-series/``) and
    treats each executed observation as one observed dispatch attempt. A
    content-side stop is counted only when the *recorded* provider-returned
    ``finishReason``/``promptFeedback`` is a documented content-side value.

    The provider/model attribution comes from the worker roster entry for the
    artifact's ``worker_id`` (authoritative), falling back to the provider-returned
    model value recorded in the artifact and then to ``unknown``. Nothing is
    re-run and no provider is called.
    """
    import json as _json

    path = Path(artifact_path)
    data = _json.loads(path.read_text(encoding="utf-8"))
    worker_id = data.get("worker_id") or "unknown"

    resolved_provider, resolved_model = provider, model
    if resolved_provider is None or resolved_model is None:
        try:
            from worker_registry import WorkerRegistry
            entry = WorkerRegistry().get_worker(worker_id) or {}
            resolved_provider = resolved_provider or entry.get("provider")
            resolved_model = resolved_model or entry.get("model")
        except Exception:  # noqa: BLE001 — roster lookup is a convenience only
            pass

    stop_reasons = content_side_stop_finish_reasons()
    observations = [o for o in (data.get("observations") or [])
                    if o.get("executed") is not False]
    stops = [o for o in observations
             if _recorded_stop_reason(o, stop_reasons)]
    if not resolved_model:
        resolved_model = next((o.get("requested_model") or o.get("provider_model_returned")
                               for o in observations
                               if o.get("requested_model") or o.get("provider_model_returned")),
                              None)
    reasons = []
    for observation in stops:
        reason = _recorded_stop_reason(observation, stop_reasons)
        if reason and reason not in reasons:
            reasons.append(reason)

    label = data.get("label") or path.parent.name
    return {
        # The label is part of the source identity so two different recorded
        # series never collapse into one (merged) sample.
        "source": f"{source}:{label}" if label else source,
        "label": label,
        "artifact_path": str(path),
        "worker_id": worker_id,
        "provider": resolved_provider or "unknown",
        "model": resolved_model or "unknown",
        "attempts_recorded": len(observations),
        "attempts_classified": len(observations),
        "content_stops_observed": len(stops),
        "finish_reasons": reasons,
        "ledger_readable": True,
        "content_stop_ledger_recorded": True,
        "failure_attribution": None,
        "timestamp": data.get("run_started_utc"),
        "dag_node_id": None,
    }


def content_stop_pressure(ledgers: List[Dict[str, Any]],
                          rate_threshold: float = MEASURABLE_CONTENT_STOP_RATE,
                          min_sample: int = MEASURABLE_CONTENT_STOP_MIN_SAMPLE
                          ) -> Dict[str, Any]:
    """Aggregate attempt ledgers into the E4 content-side stop pressure view.

    Pure: no I/O, no store, no provider. Groups are keyed by
    ``(source, worker_id, provider, model)`` and are never merged across sources,
    so a recorded provider series and the store rows are always distinguishable.
    """
    groups: Dict[Any, Dict[str, Any]] = {}
    source_order: List[str] = []

    for ledger in ledgers:
        source = ledger.get("source") or "unknown_source"
        if source not in source_order:
            source_order.append(source)
        key = (source, ledger.get("worker_id"), ledger.get("provider"),
               ledger.get("model"))
        group = groups.get(key)
        if group is None:
            group = {
                "source": source,
                "worker_id": ledger.get("worker_id") or "unknown",
                "provider": ledger.get("provider") or "unknown",
                "model": ledger.get("model") or "unknown",
                "attempts_observed": 0,
                "attempts_classified": 0,
                "content_stops_observed": 0,
                "rows_observed": 0,
                "rows_without_readable_ledger": 0,
                "last_finish_reason": None,
                "last_stop_at": None,
            }
            groups[key] = group

        recorded = ledger.get("attempts_recorded")
        if not ledger.get("ledger_readable"):
            group["rows_without_readable_ledger"] += 1
        elif recorded is None:
            group["rows_without_readable_ledger"] += 1
        else:
            group["attempts_observed"] += recorded
        classified = ledger.get("attempts_classified") or 0
        group["attempts_classified"] += classified
        group["content_stops_observed"] += ledger.get("content_stops_observed") or 0
        group["rows_observed"] += 1

        if ledger.get("content_stops_observed"):
            timestamp = ledger.get("timestamp")
            if _sort_key(timestamp) >= _sort_key(group["last_stop_at"]):
                group["last_stop_at"] = timestamp
                for reason in ledger.get("finish_reasons") or []:
                    group["last_finish_reason"] = reason
                    break

    sources: List[Dict[str, Any]] = []
    detected = False
    for source in source_order:
        source_groups = [g for g in groups.values() if g["source"] == source]
        for group in source_groups:
            classified = group["attempts_classified"]
            stops = group["content_stops_observed"]
            group["attempts_unclassified"] = (
                group["attempts_observed"] - classified)
            group["sample_size"] = classified
            if classified <= 0:
                # No classified attempt was recorded: never invent a rate.
                group["content_stop_rate"] = None
                group["content_stop_rate_basis"] = None
                group["content_withheld_at_measurable_rate"] = None
                group["status"] = PRESSURE_STATUS_UNKNOWN
                continue
            rate = stops / classified
            group["content_stop_rate"] = rate
            group["content_stop_rate_basis"] = (
                f"{stops}/{classified} classified recorded dispatch attempts")
            flagged = bool(rate >= rate_threshold and classified >= min_sample)
            group["content_withheld_at_measurable_rate"] = flagged
            if flagged:
                group["status"] = PRESSURE_STATUS_PRESSURED
                detected = True
            elif stops > 0:
                group["status"] = PRESSURE_STATUS_STOPS_RECORDED_BELOW_BOUND
            else:
                group["status"] = PRESSURE_STATUS_CLEAN
        source_groups.sort(key=lambda g: (g["worker_id"], g["provider"], g["model"]))
        sources.append({
            "source": source,
            "groups": source_groups,
            "attempts_observed": sum(g["attempts_observed"] for g in source_groups),
            "attempts_classified": sum(g["attempts_classified"] for g in source_groups),
            "content_stops_observed": sum(g["content_stops_observed"]
                                          for g in source_groups),
        })

    return {
        "view": "e4_provider_content_stop_pressure",
        "observation_only": True,
        "rate_threshold": rate_threshold,
        "minimum_sample": min_sample,
        "sources": sources,
        "content_stop_pressure_detected": detected,
        "decision": PRESSURE_DECISION_NOTE,
    }


def render_content_stop_pressure(view: Dict[str, Any],
                                 indent: str = "  ") -> List[str]:
    """Operator lines for a pressure view.

    A rate is never printed without its sample size, and an unclassified group is
    printed as ``unknown`` rather than as healthy capacity.
    """
    lines: List[str] = []
    lines.append(f"{indent}bounds: rate >= {view.get('rate_threshold')} AND "
                 f"sample >= {view.get('minimum_sample')} recorded dispatch "
                 "attempts (bounded flag)")
    sources = view.get("sources") or []
    if not sources:
        lines.append(f"{indent}(no recorded dispatch-attempt rows available — "
                     "pressure unknown, not clear)")
    for source in sources:
        lines.append(f"{indent}source: {source['source']} "
                     f"(attempts observed {source['attempts_observed']}, "
                     f"classified {source['attempts_classified']}, "
                     f"content-side stops {source['content_stops_observed']})")
        for group in source["groups"]:
            lines.append(f"{indent * 2}{group['provider']}/{group['model']} "
                         f"[worker {group['worker_id']}]")
            lines.append(
                f"{indent * 3}attempts observed: {group['attempts_observed']} "
                f"({group['attempts_classified']} classified, "
                f"{group['attempts_unclassified']} without the content-stop "
                "ledger)")
            lines.append(f"{indent * 3}content-side stops observed: "
                         f"{group['content_stops_observed']}")
            rate = group["content_stop_rate"]
            if rate is None:
                lines.append(f"{indent * 3}stop rate: unknown (sample size 0 — "
                             "no classified attempt recorded; no rate is "
                             "reported from zero attempts)")
            else:
                lines.append(
                    f"{indent * 3}stop rate: {rate:.3f} "
                    f"(sample size {group['sample_size']} classified attempts; "
                    f"{group['content_stop_rate_basis']})")
            lines.append(f"{indent * 3}last observed finishReason: "
                         f"{group['last_finish_reason'] or 'none recorded'}")
            lines.append(f"{indent * 3}last stop recorded at: "
                         f"{group['last_stop_at'] or 'none recorded'}")
            flag = group["content_withheld_at_measurable_rate"]
            flag_text = ("unknown" if flag is None
                         else ("yes" if flag else "no"))
            lines.append(f"{indent * 3}content withheld at a measurable rate: "
                         f"{flag_text} (status: {group['status']})")
    lines.append(f"{indent}content_stop_pressure_detected: "
                 f"{'yes' if view.get('content_stop_pressure_detected') else 'no'}")
    lines.append(f"{indent}decision: {view.get('decision')}")
    return lines


def build_content_stop_pressure_view(con, series_paths=(),
                                     rate_threshold: float = MEASURABLE_CONTENT_STOP_RATE,
                                     min_sample: int = MEASURABLE_CONTENT_STOP_MIN_SAMPLE
                                     ) -> Dict[str, Any]:
    """The E4 pressure view over already-persisted/recorded evidence only.

    ``con`` is an orchestration-store connection (the same store the E4 surface
    reads); ``series_paths`` optionally adds recorded provider series artifacts,
    each kept as its own source so nothing is merged or double-counted. A store
    that cannot be read yields an empty view with an explicit reason instead of a
    fabricated one.
    """
    ledgers: List[Dict[str, Any]] = []
    errors: List[str] = []
    if con is not None:
        try:
            ledgers.extend(evidence_row_ledgers(con))
        except Exception as exc:  # noqa: BLE001 — report, never fabricate
            errors.append(f"{type(exc).__name__}: {exc}")
    for path in series_paths or ():
        try:
            ledgers.append(recorded_series_ledger(path))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}: {type(exc).__name__}: {exc}")

    view = content_stop_pressure(ledgers, rate_threshold=rate_threshold,
                                 min_sample=min_sample)
    if errors:
        view["source_errors"] = errors
    return view


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

    def get_content_stop_pressure(self, series_paths=(),
                                  rate_threshold: float = MEASURABLE_CONTENT_STOP_RATE,
                                  min_sample: int = MEASURABLE_CONTENT_STOP_MIN_SAMPLE
                                  ) -> Dict[str, Any]:
        """Recorded provider content-side stop pressure, per worker/provider/model.

        Reads the already-persisted ``performance_evidence`` rows of the
        orchestration store (read-only; no E1/E2 store) and, when given, recorded
        provider series artifacts, and reports for each worker/provider/model:
        attempts observed, content-side stops observed, the stop rate with its
        sample size, the last observed finishReason, the last recorded stop time
        and a bounded ``content_withheld_at_measurable_rate`` boolean.

        The result is an *observation*: it never swaps a worker, re-dispatches,
        enters safe mode or enables Stage 2. A provider with no classified attempt
        is reported as ``unknown``, never as a fabricated rate or as healthy
        capacity.
        """
        return build_content_stop_pressure_view(
            self.orchestration_con, series_paths=series_paths,
            rate_threshold=rate_threshold, min_sample=min_sample)


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
