#!/usr/bin/env python3
"""E3 CLI bindings — `eb e3-*` commands.

Registered into the local runtime `eb.py` by ``scripts/deploy_e3_runtime.py``.
Every command operates on the orchestration store (schema v2) in the runtime
root; nothing here reads or writes E1/E2 stores.

``e3-execute`` drives the real production execution leg (orchestrator → worker
``ExecutionAdapter`` dispatch). Because it can spend real provider quota it
requires an explicit ``--confirm`` and never runs a call without it.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional

RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"

E3_COMMAND_NAMES = ["e3-init", "e3-register-workers", "e3-status", "e3-plan",
                    "e3-route", "e3-rationale", "e3-trace", "e3-why",
                    "e3-verify-db", "e3-execute"]


def _module_dir() -> str:
    return str(Path(__file__).resolve().parent)


def _db_path(args: Any) -> Path:
    override = getattr(args, "db", None)
    return Path(override) if override else RUNTIME_ROOT / "orchestration.db"


def _commands(args: Any):
    if _module_dir() not in sys.path:
        sys.path.insert(0, _module_dir())
    from e3_commands import E3Commands
    return E3Commands(_db_path(args))


# ── thin delegations to the existing E3 command implementations ─────

def cmd_e3_init(args):
    _commands(args).init(args)


def cmd_e3_register_workers(args):
    _commands(args).register_workers(args)


def cmd_e3_status(args):
    _commands(args).status(args)


def cmd_e3_plan(args):
    _commands(args).plan(args)


def cmd_e3_route(args):
    _commands(args).route(args)


def cmd_e3_rationale(args):
    _commands(args).rationale(args)


def cmd_e3_trace(args):
    _commands(args).trace(args)


def cmd_e3_why(args):
    _commands(args).why(args)


def cmd_e3_verify_db(args):
    _commands(args).verify_db(args)


# ── production execution leg ────────────────────────────────────────

def cmd_e3_execute(args):
    """Drive the real E3 production execution leg on the local path."""
    if _module_dir() not in sys.path:
        sys.path.insert(0, _module_dir())
    from e3_execution import ExecutionAdapterRegistry
    from e3_shadow_orchestrator import E3ShadowOrchestrator
    from task_fingerprint import TaskFingerprint

    db = _db_path(args)
    registry = ExecutionAdapterRegistry()
    routable = registry.routable_worker_ids()

    fp = TaskFingerprint(task_family=args.family, reasoning_depth=args.reasoning,
                         risk_class=args.risk, required_roles=[args.role],
                         verification_type="deterministic")
    orch = E3ShadowOrchestrator(db_path=db)
    plan = orch.planner.plan(args.objective, fp)
    node_ids = [n["node_id"] for n in plan["nodes"]]

    print(f"Orchestration DB: {db}")
    print(f"Routable workers: {routable}")
    print(f"Plan: {plan['plan_id']} ({len(node_ids)} node(s))")

    if not args.confirm:
        print()
        print("DRY RUN — no provider call made. Re-run with --confirm to "
              "dispatch the assembled nodes.")
        for node in plan["nodes"]:
            print(f"  {node['node_id']}  roles={node['capability_roles']}")
        return

    test_cases = {nid: [{"name": "provider returned content",
                         "field": "content_present", "expected": True}]
                  for nid in node_ids}
    out = orch.orchestrate_and_execute(
        args.objective, fp, plan=plan,
        verification_test_cases_by_node=test_cases,
        max_repair_attempts=args.max_repair_attempts,
        dispatch_timeout=args.timeout,
        adapter_registry=registry,
    )
    print(json.dumps({
        "outcome": out.get("outcome"),
        "plan_id": out.get("plan_id"),
        "team_complete": out.get("team_complete"),
        "team_assignments": out.get("team_assignments"),
        "execution": out.get("execution"),
        "escalation": out.get("escalation"),
        "execution_escalations": out.get("execution_escalations"),
        "content_stop_escalation": out.get("content_stop_escalation"),
    }, indent=2, default=str))


# ── registration ────────────────────────────────────────────────────

def register(subparsers) -> None:
    """Attach the `e3-*` subcommands to an argparse subparsers object."""
    p = subparsers.add_parser("e3-init", help="initialise the E3 orchestration store")
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_init)

    p = subparsers.add_parser("e3-register-workers",
                              help="register the worker roster (UNPROVEN)")
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_register_workers)

    p = subparsers.add_parser("e3-status", help="E3 orchestration status")
    p.add_argument("--db", default=None)
    p.add_argument("--pressure-series", dest="pressure_series", action="append",
                   default=None,
                   help="recorded provider series artifact (observations.json) to "
                        "include as an additional source in the E4 provider "
                        "content-side stop pressure view; repeatable")
    p.set_defaults(func=cmd_e3_status)

    p = subparsers.add_parser("e3-plan", help="plan a task (advisory)")
    p.add_argument("--task", default="Example task")
    p.add_argument("--family", default="other")
    p.add_argument("--reasoning", type=int, default=2)
    p.add_argument("--risk", default="R1")
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_plan)

    p = subparsers.add_parser("e3-route", help="propose candidate workers")
    p.add_argument("--task-id", dest="task_id", default="task-unknown")
    p.add_argument("--family", default="code")
    p.add_argument("--role", default="builder")
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_route)

    p = subparsers.add_parser("e3-rationale", help="show decision rationale")
    p.add_argument("--decision-id", dest="decision_id", default=None)
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_rationale)

    p = subparsers.add_parser("e3-trace", help="decision trace for a task")
    p.add_argument("task_id", nargs="?", default=None)
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_trace)

    p = subparsers.add_parser("e3-why", help="why a node was decided")
    p.add_argument("node_id", nargs="?", default=None)
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_why)

    p = subparsers.add_parser("e3-verify-db",
                              help="verify orchestration.db integrity")
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_verify_db)

    p = subparsers.add_parser(
        "e3-execute",
        help="run the real production execution leg (requires --confirm)")
    p.add_argument("--objective", required=True)
    p.add_argument("--family", default="code")
    p.add_argument("--role", default="builder")
    p.add_argument("--reasoning", type=int, default=1)
    p.add_argument("--risk", default="R1")
    p.add_argument("--max-repair-attempts", dest="max_repair_attempts",
                   type=int, default=1)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--confirm", action="store_true",
                   help="actually dispatch to providers (spends quota)")
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_e3_execute)


def main(argv: Optional[List[str]] = None) -> int:
    """Standalone entry point (mainly for inspection/testing)."""
    ap = argparse.ArgumentParser(prog="e3")
    sub = ap.add_subparsers(dest="cmd", required=True)
    register(sub)
    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
