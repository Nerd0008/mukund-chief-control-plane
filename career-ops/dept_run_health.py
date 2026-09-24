#!/usr/bin/env python3
"""Department run-health metadata for the Career Ops Excel workers.

Why this exists
---------------
The canonical regional workbooks are the operational record for the Career
department. Chief only orchestrates: it needs to know *that* a worker ran, what
it did and how many rows it touched, without owning the rows themselves.

This module is the single deterministic place where that metadata is written and
read back. It is deliberately tiny and dependency-free (stdlib only) so both the
tracker writer and the monthly rollover worker can record the same shape.

Contract
--------
* One JSON document per job, at
  ``runtime/career-ops/run-health/<job>.json`` (overridable for tests).
* Deterministic: keys are sorted, the document shape never changes between runs.
* **Aggregate only.** No company, title, URL, note or other workbook content is
  ever stored here — only counts, hashes, statuses and file names. That keeps it
  safe to commit as evidence while the Excel workbooks stay owner-private.
* Excel stays authoritative for operational records; this file is orchestration
  state and says so explicitly (``excel_is_source_of_truth`` /
  ``chief_state_role``).

CLI (deterministic, one JSON object on stdout):

    python career-ops/dept_run_health.py summary [--job J] [--state-dir D]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL_PLANE = HERE.parent

SCHEMA_VERSION = 1

# The authoritative roster of jobs this module knows about. A job not listed
# here is refused rather than silently creating a new file with no provenance.
JOBS: dict[str, dict] = {
    "tracker-writer": {
        "worker": "career-ops/tracker_writer.py",
        "roster": "B08",
        "title": "Excel Tracker Writer",
        "owns": "deduplicated append into a canonical regional workbook",
    },
    "monthly-rollover": {
        "worker": "career-ops/tracker_rollover.py",
        "roster": "B09",
        "title": "Monthly Tracker Rollover / archive worker",
        "owns": "rotating one closed month of records per region into an archive workbook",
    },
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def default_state_dir() -> Path:
    return CONTROL_PLANE / "runtime" / "career-ops" / "run-health"


def state_path(job: str, state_dir: str | Path | None = None) -> Path:
    if job not in JOBS:
        raise KeyError(f"unknown job '{job}'; known: {sorted(JOBS)}")
    return Path(state_dir or default_state_dir()) / f"{job}.json"


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True, default=str),
                   encoding="utf-8")
    tmp.replace(path)


def load(job: str, state_dir: str | Path | None = None) -> dict:
    """Load a job's run-health document, or an empty skeleton if it never ran."""
    p = state_path(job, state_dir)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    spec = JOBS[job]
    return {
        "schema_version": SCHEMA_VERSION,
        "job": job,
        "worker": spec["worker"],
        "roster": spec["roster"],
        "title": spec["title"],
        "owns": spec["owns"],
        "excel_is_source_of_truth": True,
        "chief_state_role": "orchestration-only",
        "runs_recorded": 0,
        "updated_at": None,
        "last_run": None,
        "last_by_region": {},
    }


def record_run(job: str, *, region: str | None, status: str, counts: dict | None = None,
               mode: str | None = None, result: str | None = None,
               extra: dict | None = None, state_dir: str | Path | None = None) -> dict:
    """Append one run to a job's run-health document and return the new document.

    ``status`` is the machine decision for this run (e.g. ``ok``, ``dry-run``,
    ``no-op``, ``unchanged``, ``failed``, ``refused``). ``counts`` must be row
    counts only — never workbook content.
    """
    if job not in JOBS:
        raise KeyError(f"unknown job '{job}'; known: {sorted(JOBS)}")
    doc = load(job, state_dir)
    at = now_utc()
    counts = {k: v for k, v in (counts or {}).items() if isinstance(v, (int, float)) or v is None}
    run = {
        "at": at,
        "region": region,
        "status": status,
        "mode": mode,
        "result": result or status,
        "counts": counts,
    }
    if extra:
        # only scalar/JSON-safe orchestration facts; never workbook content
        run.update({k: v for k, v in sorted(extra.items()) if k != "counts"})
    doc["schema_version"] = SCHEMA_VERSION
    doc["runs_recorded"] = int(doc.get("runs_recorded") or 0) + 1
    doc["updated_at"] = at
    doc["last_run"] = run
    doc.setdefault("last_by_region", {})
    if region:
        doc["last_by_region"][region] = run
    write_json_atomic(state_path(job, state_dir), doc)
    return doc


def summarise(state_dir: str | Path | None = None, job: str | None = None) -> dict:
    """Chief-readable health summary over one or all jobs."""
    jobs = [job] if job else list(JOBS)
    out = {
        "generated_at": now_utc(),
        "state_dir": str(Path(state_dir or default_state_dir())),
        "excel_is_source_of_truth": True,
        "chief_state_role": "orchestration-only",
        "jobs": {},
    }
    for j in jobs:
        doc = load(j, state_dir)
        last = doc.get("last_run") or {}
        out["jobs"][j] = {
            "worker": doc.get("worker"),
            "roster": doc.get("roster"),
            "title": doc.get("title"),
            "runs_recorded": doc.get("runs_recorded", 0),
            "updated_at": doc.get("updated_at"),
            "last_run_at": last.get("at"),
            "last_region": last.get("region"),
            "last_status": last.get("status"),
            "last_result": last.get("result"),
            "last_mode": last.get("mode"),
            "last_counts": last.get("counts"),
            "regions_seen": sorted((doc.get("last_by_region") or {}).keys()),
            "state_file": str(state_path(j, state_dir)),
        }
    return out


def emit(obj) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = json.dumps(obj, indent=2, ensure_ascii=True, default=str)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Career Ops department run-health metadata")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("summary")
    p.add_argument("--job", choices=sorted(JOBS))
    p.add_argument("--state-dir")
    p.set_defaults(fn=lambda a: (emit(summarise(a.state_dir, a.job)), 0)[1])
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
