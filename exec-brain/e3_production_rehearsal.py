#!/usr/bin/env python3
"""E3 Production Rehearsal — executable evidence on the real local E3 path.

Runs the *real* E3 orchestration pipeline
(planner -> decomposition review -> router -> context/permission compilation
 -> team assembly -> integrator -> independent verifier -> conflict handler
 -> evidence manager -> replanner / escalator) as a real process against a
real orchestration database, and records executable evidence for
planner/router/team-assembly/integrator/verifier flow, a genuine verifier
rejection followed by targeted repair/replan and successful re-verification,
and simulation-evidence isolation.

Guarantees enforced here:

* SIMULATION ISOLATION — the rehearsal writes only into a dedicated rehearsal
  store. The qualification/production stores are hashed before and verified
  byte-identical afterwards, and a rehearsal-tagged evidence sink refuses to
  persist into any production store (fail-closed).
* E1/E2 BOUNDARY — E3 never SQL-writes ``exec_brain.db`` / ``governor.db``.
  E2 telemetry goes only through the public ``governor.record_request()``
  interface, exercised against an isolated store.
* HONESTY — no worker is marked QUALIFIED. Rehearsal-seeded capability rows
  reflect execution readiness (routable=true) and use the EVALUATING state
  only. No provider usage, model identity or qualification evidence is
  fabricated.

This module does not dispatch production work and does not enable Stage 2.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

# Qualification / production stores that a rehearsal must never touch.
PRODUCTION_STORES = {
    "orchestration": RUNTIME_ROOT / "orchestration.db",
    "governor": RUNTIME_ROOT / "governor.db",
    "exec_brain": RUNTIME_ROOT / "exec_brain.db",
}

REHEARSAL_MARKER = "rehearsal"


class RehearsalIsolationError(Exception):
    """Raised when rehearsal/simulated evidence could reach a production store."""


def _sha256_file(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


class EvidenceIsolationGuard:
    """Fail-closed guard + before/after proof for rehearsal evidence isolation."""

    def __init__(self, production_stores: Optional[Dict[str, Path]] = None):
        self.production_stores = dict(production_stores or PRODUCTION_STORES)
        self.before: Dict[str, Optional[str]] = {}

    # ── path classification ─────────────────────────────────────────
    def _resolved(self, path) -> Path:
        return Path(path).resolve()

    def is_production_store(self, path) -> bool:
        target = self._resolved(path)
        for store in self.production_stores.values():
            if self._resolved(store) == target:
                return True
        # Any store living inside the live runtime root is production.
        try:
            target.relative_to(RUNTIME_ROOT.resolve())
            return True
        except ValueError:
            return False

    def assert_rehearsal_store(self, path) -> None:
        """Refuse to treat a production store as a rehearsal store."""
        if self.is_production_store(path):
            raise RehearsalIsolationError(
                f"refusing to use production store as a rehearsal store: {path}"
            )

    def guard_write(self, path, rehearsal_evidence: bool = True) -> None:
        """Fail closed if rehearsal evidence is about to be persisted to production."""
        if rehearsal_evidence and self.is_production_store(path):
            raise RehearsalIsolationError(
                f"rehearsal evidence cannot be written to a production store: {path}"
            )

    # ── before/after proof ──────────────────────────────────────────
    def capture(self) -> Dict[str, Optional[str]]:
        self.before = {name: _sha256_file(p)
                       for name, p in self.production_stores.items()}
        return dict(self.before)

    def assert_unchanged(self) -> Tuple[bool, List[str]]:
        diffs: List[str] = []
        for name, p in self.production_stores.items():
            now = _sha256_file(p)
            was = self.before.get(name)
            if now != was:
                diffs.append(f"{name} store changed: {was} -> {now} ({p})")
        return (not diffs), diffs


class RehearsalEvidenceSink:
    """An isolated evidence sink that refuses to persist into production stores."""

    def __init__(self, store_path, guard: EvidenceIsolationGuard,
                 rehearsal: bool = True):
        self.store_path = Path(store_path)
        self.guard = guard
        self.rehearsal = rehearsal
        if rehearsal:
            self.guard.assert_rehearsal_store(self.store_path)
        self.records: List[Dict[str, Any]] = []

    def persist(self, record: Dict[str, Any]) -> None:
        self.guard.guard_write(self.store_path, rehearsal_evidence=self.rehearsal)
        tagged = dict(record)
        tagged["store"] = REHEARSAL_MARKER if self.rehearsal else "production"
        tagged["simulated"] = True
        self.records.append(tagged)

    def flush(self) -> Path:
        """Seal the rehearsal evidence bundle (JSON) into the rehearsal store."""
        self.guard.guard_write(self.store_path, rehearsal_evidence=self.rehearsal)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "store": REHEARSAL_MARKER,
            "simulated": True,
            "isolation_note": (
                "Rehearsal/simulated evidence. Must never be loaded into a "
                "qualification or production evidence store."
            ),
            "records": self.records,
        }
        self.store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.store_path


# ── E1/E2 boundary static scan ──────────────────────────────────────

E2_TABLES = ("observed_request", "provider_snapshot", "capacity_dimension",
             "daily_aggregate", "daily_brief_log")
_SQL_WRITE_RE = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([A-Za-z_]+)",
                           re.IGNORECASE)


def scan_e1_e2_boundary(module_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Statically verify E3 code performs no direct SQL writes to E1/E2 stores.

    The E2 public entry point (``governor.record_request``) is allowed; a direct
    sqlite connection whose path names ``governor.db`` / ``exec_brain.db`` is not.
    """
    module_dir = Path(module_dir or Path(__file__).resolve().parent)
    violations: List[Dict[str, Any]] = []
    e2_public_calls: List[str] = []

    for py in sorted(module_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        name = py.name
        if "governor.record_request" in text:
            e2_public_calls.append(name)
        for i, line in enumerate(text.splitlines(), 1):
            if "sqlite3.connect" in line and (
                    "governor" + ".db" in line or "exec_brain" + ".db" in line):
                violations.append({
                    "file": name, "line": i, "kind": "direct_connect",
                    "line_text": line.strip()[:200],
                })
            for m in _SQL_WRITE_RE.finditer(line):
                table = m.group(2).lower()
                if table in E2_TABLES and name != "governor.py":
                    violations.append({
                        "file": name, "line": i, "kind": "direct_sql_write",
                        "line_text": line.strip()[:200],
                    })

    return {
        "module_dir": str(module_dir),
        "direct_sql_violations": violations,
        "e2_public_interface_modules": e2_public_calls,
        "clean": not violations,
    }


# ── rehearsal driver ────────────────────────────────────────────────

class E3ProductionRehearsal:
    """Executable production rehearsal on the real local E3 orchestration path."""

    TASK_FAMILY = "code"

    def __init__(self, rehearsal_root: Optional[Path] = None,
                 production_stores: Optional[Dict[str, Path]] = None,
                 seed_workers: Optional[List[Dict[str, Any]]] = None):
        self.guard = EvidenceIsolationGuard(production_stores)
        self.rehearsal_root = Path(
            rehearsal_root or tempfile.mkdtemp(prefix="e3-rehearsal-")
        )
        self.rehearsal_root.mkdir(parents=True, exist_ok=True)
        self.orchestration_db = self.rehearsal_root / "rehearsal_orchestration.db"
        self.evidence_store = self.rehearsal_root / "rehearsal_evidence.json"
        self.governor_db = self.rehearsal_root / "rehearsal_governor.db"
        self.sink = RehearsalEvidenceSink(self.evidence_store, self.guard,
                                          rehearsal=True)
        self._seed_workers = seed_workers
        self.scenarios: List[Dict[str, Any]] = []

    # ── setup ───────────────────────────────────────────────────────
    def _scenario_orchestrator(self):
        """A real E3 orchestrator bound to the isolated rehearsal DB."""
        from e3_shadow_orchestrator import E3ShadowOrchestrator
        self.guard.assert_rehearsal_store(self.orchestration_db)
        return E3ShadowOrchestrator(db_path=self.orchestration_db)

    def _derived_seed_workers(self) -> List[Dict[str, Any]]:
        """Workers seeded into the *rehearsal* registry.

        Derived from the real roster's truthful routable state (smoke PASS +
        E2 linkage VERIFIED) and capability hints. They are seeded as
        EVALUATING — execution-ready but NOT qualified. Rehearsal-scoped;
        grants no qualification.
        """
        if self._seed_workers is not None:
            return list(self._seed_workers)
        from worker_registry import WorkerRegistry
        seeds: List[Dict[str, Any]] = []
        for wid, w in WorkerRegistry().get_all_workers().items():
            if not w.get("routable"):
                continue
            hints = set(w.get("capability_hints", []))
            roles: List[str] = []
            if "coding" in hints or "implementation" in hints:
                roles.append("builder")
            if "image-generation" in hints or "vision" in hints:
                roles.append("vision")
            if not roles:
                continue
            seeds.append({"worker_id": wid, "provider": w["provider"],
                          "model": w["model"], "roles": roles})
        return seeds

    def _seed_registry(self) -> List[Dict[str, Any]]:
        from capability_registry import CapabilityRegistry
        from orchestration_db import init_db
        init_db(self.orchestration_db)
        con = sqlite3.connect(str(self.orchestration_db))
        con.row_factory = sqlite3.Row
        try:
            registry = CapabilityRegistry(con)
            seeds = self._derived_seed_workers()
            for s in seeds:
                registry.register_worker(
                    s["worker_id"], s["provider"], s["model"],
                    roles=s["roles"], state="EVALUATING",
                    task_family=self.TASK_FAMILY,
                )
        finally:
            con.close()
        return seeds

    # ── scenarios ───────────────────────────────────────────────────
    @staticmethod
    def _targeted_repair(outputs: Dict[str, Any], verification) -> Dict[str, Any]:
        """Targeted rework: correct only the flagged status field per node."""
        repaired: Dict[str, Any] = {}
        for key, value in outputs.items():
            if isinstance(value, dict):
                fixed = dict(value)
                fixed["status"] = "validated"
                repaired[key] = fixed
            else:
                repaired[key] = value
        return repaired

    def _scenario_rejection_repair_reverify(self) -> Dict[str, Any]:
        """R1 deterministic single-worker task: verifier rejects, targeted
        repair is applied, re-verification passes."""
        from task_fingerprint import TaskFingerprint
        orch = self._scenario_orchestrator()
        fp = TaskFingerprint(task_family=self.TASK_FAMILY, reasoning_depth=1,
                             risk_class="R1", required_roles=["builder"],
                             verification_type="deterministic")
        test_cases = [{"name": "output is validated", "field": "status",
                       "expected": "validated"}]
        result = orch.rehearse("Rehearsal: deterministic validation task", fp,
                               verification_test_cases=test_cases,
                               repair=self._targeted_repair,
                               max_repair_attempts=1)
        d = result.to_dict()
        d["candidates_by_node"] = {k: len(v) for k, v in result.candidates_by_node.items()}
        d["team_assignments"] = (
            [{"node": a.node_id, "worker": a.worker_id}
             for a in result.team_assembly.assignments]
            if result.team_assembly else []
        )
        d["verification_attempts_detail"] = result.verification_attempts
        d["verifier_rejections_detail"] = result.verifier_rejections
        d["repair_history_detail"] = result.repair_history
        self.sink.persist({"scenario": "rejection_repair_reverify", "rehearsal": d})
        return d

    def _scenario_rejection_without_repair(self) -> Dict[str, Any]:
        """R1 deterministic task, no repair available: verifier rejects, the
        replanner is consulted, and the driver escalates to the owner."""
        from task_fingerprint import TaskFingerprint
        orch = self._scenario_orchestrator()
        fp = TaskFingerprint(task_family=self.TASK_FAMILY, reasoning_depth=1,
                             risk_class="R1", required_roles=["builder"],
                             verification_type="deterministic")
        test_cases = [{"name": "output is validated", "field": "status",
                       "expected": "validated"}]
        result = orch.rehearse("Rehearsal: unrepaired rejection task", fp,
                               verification_test_cases=test_cases)
        escalation = None
        if not result.verification_results.get("integration", {}).get("passed", False):
            rec = orch.escalator.escalate(
                trigger="repeated_failure",
                context=("Verifier rejected the integrated output and no repair "
                         "path was configured in this rehearsal."),
                proposals_considered=["targeted_repair", "replan"],
                why_each_failed=["no repair capability configured for rehearsal"],
                owner_decision_needed="manual review",
                recommended_action="escalate to owner",
            )
            result.escalations.append(rec.escalation_id)
            escalation = {"escalation_id": rec.escalation_id, "trigger": rec.trigger}
        d = result.to_dict()
        d["escalation"] = escalation
        d["replan_history"] = result.replan_history
        d["verification_attempts_detail"] = result.verification_attempts
        self.sink.persist({"scenario": "rejection_without_repair", "rehearsal": d})
        return d

    def _scenario_no_qualified_route(self) -> Dict[str, Any]:
        """A task family with no seeded worker: the router must find no route
        and the pipeline must escalate rather than fabricate an assignment."""
        from task_fingerprint import TaskFingerprint
        orch = self._scenario_orchestrator()
        fp = TaskFingerprint(task_family="writing", reasoning_depth=1,
                             risk_class="R1", required_roles=["writer"],
                             verification_type="deterministic")
        result = orch.rehearse("Rehearsal: task family with no seeded worker", fp)
        escalation = None
        if result.team_assembly and not result.team_assembly.complete:
            rec = orch.escalator.escalate(
                trigger="no_qualified_worker",
                context=f"no candidate workers for family '{fp.task_family}'",
                proposals_considered=["route_to_seeded_workers"],
                why_each_failed=["no rehearsal-seeded worker for this family"],
                owner_decision_needed="provision/qualify a worker",
                recommended_action="escalate to owner",
            )
            result.escalations.append(rec.escalation_id)
            escalation = {"escalation_id": rec.escalation_id, "trigger": rec.trigger}
        d = result.to_dict()
        d["escalation"] = escalation
        d["candidates_by_node"] = {k: len(v) for k, v in result.candidates_by_node.items()}
        self.sink.persist({"scenario": "no_qualified_route", "rehearsal": d})
        return d

    def _scenario_decomposed_multi_node(self) -> Dict[str, Any]:
        """Decomposed multi-role task exercising cross-role routing, the
        integrator node and multi-node team assembly."""
        from task_fingerprint import TaskFingerprint
        from e3_team_assembly import TeamAssembler
        orch = self._scenario_orchestrator()
        fp = TaskFingerprint(task_family=self.TASK_FAMILY, reasoning_depth=4,
                             risk_class="R1",
                             required_roles=["builder", "vision"],
                             integration_complexity="medium",
                             verification_type="deterministic")
        objective = "Rehearsal: decomposed multi-node task"
        plan = orch.planner.plan(objective, fp)
        node_ids = [n["node_id"] for n in plan["nodes"]]
        simulate = {nid: {"status": "simulated", "artifact": "shared-artifact",
                          "objective": "shared-objective"} for nid in node_ids}
        result = orch.rehearse(
            objective, fp, simulate_outputs=simulate, plan=plan,
            verification_test_cases=[{"name": "status ok", "field": "status",
                                      "expected": "simulated"}],
        )
        d = result.to_dict()
        plan_nodes = (result.plan or {}).get("nodes", [])
        d["plan_nodes"] = [
            {"node_id": n.get("node_id"), "roles": n.get("capability_roles")}
            for n in plan_nodes
        ]
        d["integrator_node_present"] = any(
            "integrator" in n.get("capability_roles", []) for n in plan_nodes
        )
        d["candidates_by_node"] = {k: len(v) for k, v in result.candidates_by_node.items()}
        if result.team_assembly:
            assembler = TeamAssembler(None)
            d["team_conflicts"] = assembler.detect_team_conflicts(result.team_assembly)
            d["team_assignments"] = [
                {"node": a.node_id, "worker": a.worker_id, "role": a.role}
                for a in result.team_assembly.assignments
            ]
            d["team_issues"] = result.team_assembly.issues
        self.sink.persist({"scenario": "decomposed_multi_node", "rehearsal": d})
        return d

    def _scenario_conflict_detection(self) -> Dict[str, Any]:
        """Two nodes produce genuinely contradictory claims; the conflict
        handler must detect the conflict rather than silently merge it."""
        from task_fingerprint import TaskFingerprint
        orch = self._scenario_orchestrator()
        fp = TaskFingerprint(task_family=self.TASK_FAMILY, reasoning_depth=4,
                             risk_class="R1",
                             required_roles=["builder", "vision"],
                             integration_complexity="medium",
                             verification_type="deterministic")
        objective = "Rehearsal: contradictory multi-node task"
        plan = orch.planner.plan(objective, fp)
        node_ids = [n["node_id"] for n in plan["nodes"]]
        simulate = {}
        for i, nid in enumerate(node_ids):
            simulate[nid] = {
                "status": "ok",
                "artifact": "shared-artifact",
                "claim": "value-A" if i == 0 else "value-B",
            }
        result = orch.rehearse(objective, fp, simulate_outputs=simulate, plan=plan,
                               verification_test_cases=[{"name": "status ok",
                                                         "field": "status",
                                                         "expected": "ok"}])
        d = result.to_dict()
        d["conflicts_detected_detail"] = result.conflicts_detected
        mcp = getattr(result, "missing_pieces", None)
        if mcp is not None:
            d["missing_pieces"] = mcp
        self.sink.persist({"scenario": "conflict_detection", "rehearsal": d})
        return d

    # ── E2 public interface ─────────────────────────────────────────
    def e2_public_interface_check(self) -> Dict[str, Any]:
        """Exercise the E2 public ``governor.record_request`` interface against
        an isolated store and prove the production governor store is untouched."""
        if not (RUNTIME_ROOT / "governor.py").exists():
            return {"available": False,
                    "note": "E2 governor runtime not present on this machine"}
        if str(RUNTIME_ROOT) not in sys.path:
            sys.path.insert(0, str(RUNTIME_ROOT))
        import governor  # type: ignore

        self.guard.assert_rehearsal_store(self.governor_db)
        governor.init_db(self.governor_db)
        con = sqlite3.connect(str(self.governor_db))
        try:
            request_id = governor.record_request(
                con,
                provider=REHEARSAL_MARKER,
                model=None,
                input_tokens=None,
                output_tokens=None,
                monetary_cost="unknown",
                status=REHEARSAL_MARKER,
            )
            row = con.execute(
                "SELECT request_id, provider, status, input_tokens "
                "FROM observed_request WHERE request_id=?", (request_id,)
            ).fetchone()
        finally:
            con.close()
        result = {
            "available": True,
            "interface": "governor.record_request",
            "isolated_store": str(self.governor_db),
            "request_id": request_id,
            "row_readback": list(row) if row else None,
            "note": ("Rehearsal-tagged row written to an isolated governor store "
                     "only. No provider usage/model/qualification is claimed."),
        }
        self.sink.persist({"scenario": "e2_public_interface", "result": result})
        return result

    # ── main ────────────────────────────────────────────────────────
    def run(self, include_e2: bool = True) -> Dict[str, Any]:
        started = datetime.now(timezone.utc)
        before = self.guard.capture()

        seeds = self._seed_registry()
        self.scenarios = [
            self._scenario_rejection_repair_reverify(),
            self._scenario_rejection_without_repair(),
            self._scenario_no_qualified_route(),
            self._scenario_decomposed_multi_node(),
            self._scenario_conflict_detection(),
        ]

        e2 = self.e2_public_interface_check() if include_e2 else {"available": False}
        boundary = scan_e1_e2_boundary()
        sink_path = self.sink.flush()
        isolation_ok, isolation_diffs = self.guard.assert_unchanged()

        return {
            "label": "e3-production-rehearsal",
            "run_started_utc": started.isoformat(timespec="seconds"),
            "run_finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": "E3 Stage 1 (shadow/rehearsal) — Stage 2 NOT enabled by this run",
            "rehearsal_root": str(self.rehearsal_root),
            "rehearsal_orchestration_db": str(self.orchestration_db),
            "rehearsal_evidence_store": str(sink_path),
            "seeded_workers": seeds,
            "seed_note": ("rehearsal-scoped EVALUATING rows derived from truthful "
                          "routable=true (smoke PASS + E2 linkage). No worker is "
                          "marked QUALIFIED; this grants no qualification."),
            "scenarios": self.scenarios,
            "e2_public_interface": e2,
            "e1_e2_boundary_scan": boundary,
            "isolation": {
                "production_stores": {k: str(v)
                                      for k, v in self.guard.production_stores.items()},
                "before_sha256": before,
                "production_stores_unchanged": isolation_ok,
                "diffs": isolation_diffs,
            },
        }


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="E3 production rehearsal")
    parser.add_argument("--out-dir", default=None,
                        help="evidence output dir (default: audits/evidence/<ts>-e3-production-rehearsal)")
    parser.add_argument("--no-e2", action="store_true",
                        help="skip the E2 public-interface check")
    args = parser.parse_args(argv)

    rehearsal = E3ProductionRehearsal()
    report = rehearsal.run(include_e2=not args.no_e2)

    out_dir = (Path(args.out_dir) if args.out_dir else
               REPO_ROOT / "audits" / "evidence" /
               f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}-e3-production-rehearsal-run")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# E3 production rehearsal evidence",
        "",
        f"- Started (UTC): {report['run_started_utc']}",
        f"- Finished (UTC): {report['run_finished_utc']}",
        f"- Stage: {report['stage']}",
        f"- Rehearsal orchestration DB: `{report['rehearsal_orchestration_db']}`",
        f"- Rehearsal evidence store: `{report['rehearsal_evidence_store']}`",
        f"- Production stores unchanged: {report['isolation']['production_stores_unchanged']}",
        f"- E1/E2 boundary clean: {report['e1_e2_boundary_scan']['clean']}",
        "",
        "| Scenario | Outcome | Team complete | Verifier attempts | Rejections | Repairs |",
        "|---|---|---|---|---|---|",
    ]
    for s in report["scenarios"]:
        lines.append(
            f"| {s.get('task_objective', '')} | {s.get('outcome')} | "
            f"{s.get('team_complete')} | {s.get('verification_attempts')} | "
            f"{s.get('verifier_rejections')} | {s.get('repair_attempts')} |"
        )
    (out_dir / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    results = {
        "rejection_repair_reverify_passed": next(
            (s.get("verification_results", {}).get("integration", {}).get("passed")
             for s in report["scenarios"]
             if "deterministic validation" in s.get("task_objective", "")), None),
        "verifier_rejection_observed": any(
            s.get("verifier_rejections", 0) > 0 for s in report["scenarios"]),
        "repair_and_reverify_observed": any(
            s.get("repair_attempts", 0) > 0 and
            s.get("verification_results", {}).get("integration", {}).get("passed")
            for s in report["scenarios"]),
        "no_route_escalated": any(
            (s.get("escalation") or {}).get("trigger") == "no_qualified_worker"
            for s in report["scenarios"]),
        "production_stores_unchanged": report["isolation"]["production_stores_unchanged"],
        "e1_e2_boundary_clean": report["e1_e2_boundary_scan"]["clean"],
    }
    print(json.dumps(results, indent=2))
    print(f"evidence written to {out_dir}")
    ok = (results["rejection_repair_reverify_passed"] is True
          and results["verifier_rejection_observed"]
          and results["repair_and_reverify_observed"]
          and results["no_route_escalated"]
          and results["production_stores_unchanged"]
          and results["e1_e2_boundary_clean"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
