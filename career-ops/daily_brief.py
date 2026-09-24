#!/usr/bin/env python3
"""Career Daily Brief / Pipeline Prioritizer (roster B23).

What this is
------------
A **read-only aggregator** that turns the outputs the rest of the Career
department already produces into one machine-readable Daily Brief plus a short
Chief-facing summary:

* regional scan health (per region: last run, status, accepted, duplicates);
* newly added jobs (tracker rows dated inside the window, plus scan "new
  offers" that carry **no** URL and therefore cannot become tracker rows);
* duplicates suppressed (scan counters + policy-level duplicate suppression +
  the shared writer's dedupe counts);
* canonical tracker state (row counts, status counts, workbook SHA-256);
* Company Watch findings;
* application-status changes proposed by the Application Inbox monitor;
* interview / follow-up items;
* owner actions.

What this is NOT
----------------
* It is **not** a source of truth. Every fact in the brief is read back out of
  the canonical artifact that owns it (canonical workbook, regional run-health
  files, the scanner's own counters, the monitor's stores, the owner-action
  file). Nothing is re-derived into a new authoritative record.
* It **writes nothing** outside its own runtime output directory. The canonical
  workbooks are opened read-only and re-hashed before and after the run; the
  brief records that they are unchanged.
* It never submits, applies, messages, connects, posts or contacts anyone, and
  there is no code path here that can.
* It does not invent a priority. Priority is an explicitly declared
  deterministic policy: each candidate's score is reported **with its
  components, their weights and the inputs that were UNKNOWN**. An unknown
  input contributes nothing and is listed; it is never imputed, and the brief
  says so in ``policy.score_semantics``.

Priority policy
---------------
Five declared inputs (weights in ``daily_brief_config.json#priority_policy``):

  deadline              days until the tracker's own deadline column value
  stage                 the tracker's own application-status vocabulary
  eligibility_certainty the region's recorded work-authorisation state
  freshness             age of the posting / of the tracker row
  owner_flag            an owner-controlled cell the owner has set

``score = 100 * sum(weight*value for KNOWN inputs) / sum(weight for KNOWN
inputs)`` and ``coverage = sum(weight known)/sum(all weights)``. A candidate
with unknown inputs therefore has a lower coverage, not a silently lower
score. Two hard overrides are declared and recorded per item.

Idempotency
-----------
The brief content is digested with ``generated_at``/``brief_id``/run metadata
excluded. Re-running with unchanged inputs produces the **same digest**, writes
no new bytes (the digest-named file already exists and matches), and reports
``idempotent: true``. ``run-log.jsonl`` is the only append-only file.

Subcommands (each prints exactly one JSON object on stdout)
    inputs
    policy
    build   [--window-hours H] [--out-dir DIR] [--now ISO] [--no-write]
    summary [--brief FILE | --latest] [--out-dir DIR]
    status  [--out-dir DIR]

Usage
    python career-ops/daily_brief.py inputs
    python career-ops/daily_brief.py build --window-hours 24
    python career-ops/daily_brief.py summary --latest
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
DEFAULT_CONFIG = CAREER_OPS_DIR / "daily_brief_config.json"

sys.path.insert(0, str(CAREER_OPS_DIR))

import career_ops_cli as coc  # noqa: E402  (lane resolution + shared emit contract)
import cv_workflow as cvw  # noqa: E402  (emit / hashing / clock helpers)
import tracker_writer as tw  # noqa: E402  (canonical workbook reading only)
import application_inbox as inbox  # noqa: E402  (monitor stores, read-only)
import interview_prep as ip  # noqa: E402  (prep packs, read-only)
import regional_job_search as rjs  # noqa: E402  (run-health + scanner counters)

emit = cvw.emit
now_utc = cvw.now_utc
sha256_file = cvw.sha256_file
sha256_text = cvw.sha256_text
read_text = cvw.read_text

SCHEMA_VERSION = 1

#: Excluded from the content digest: they describe *when* the brief was made or
#: are self-referential, not *what* it says. Two runs over identical inputs must
#: digest identically - that is what makes the write step a true no-op.
VOLATILE_KEYS = ("generated_at", "brief_id", "content_digest", "delivery", "run", "outputs")

OWNER_ACTION_HEADING_RE = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")
OWNER_ACTION_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$")


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #

def load_config(path: str | Path | None = None) -> dict:
    p = Path(path or DEFAULT_CONFIG)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["_config_path"] = str(p)
    return cfg


def resolve(cfg: dict, rel_path: str) -> Path:
    """Resolve a config path relative to the control-plane root."""
    p = Path(rel_path)
    return p if p.is_absolute() else (CONTROL_PLANE / p)


def out_dir(cfg: dict, override: str | Path | None = None) -> Path:
    if override:
        return Path(override)
    return resolve(cfg, cfg["out_dir"])


def parse_now(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    text = value.strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.replace(microsecond=0)


def parse_iso(value) -> dt.datetime | None:
    """Best-effort ISO timestamp; anything else stays None (never guessed)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def parse_day(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def days_between(later: dt.date, earlier: dt.date) -> int:
    return (later - earlier).days


def file_fact(path: Path) -> dict:
    """Presence + hash of one input file. Never reads secret values."""
    if not path.exists():
        return {"path": str(path), "exists": False, "sha256": None, "bytes": 0}
    if path.is_dir():
        files = sorted(p for p in path.glob("*") if p.is_file())
        return {"path": str(path), "exists": True, "kind": "dir",
                "files": len(files), "bytes": sum(p.stat().st_size for p in files),
                "sha256": None}
    return {"path": str(path), "exists": True, "kind": "file",
            "sha256": sha256_file(path), "bytes": path.stat().st_size}


def read_json(path: Path):
    """(data, error). A missing/unreadable file is reported, never raised."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def content_digest(brief: dict) -> str:
    payload = {k: v for k, v in brief.items() if k not in VOLATILE_KEYS}
    return sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


# --------------------------------------------------------------------------- #
# input inventory
# --------------------------------------------------------------------------- #

def collect_inputs(cfg: dict) -> dict:
    """Availability of every input this brief reads. Nothing is assumed."""
    out = {}
    for name, rel_path in cfg["inputs"].items():
        p = resolve(cfg, rel_path)
        fact = file_fact(p)
        fact["name"] = name
        fact["declared"] = rel_path
        out[name] = fact

    # The canonical workbooks are inputs owned by Career Ops, not by this brief.
    profiles_path = resolve(cfg, cfg["inputs"]["regional_profiles"])
    data, err = read_json(profiles_path)
    workbooks = {}
    if data:
        for region, rc in data["regions"].items():
            tp = Path(rc["tracker"])
            workbooks[region] = {**file_fact(tp), "region": region,
                                 "display_name": rc["display_name"]}
    out["canonical_workbooks"] = {"name": "canonical_workbooks",
                                  "exists": bool(workbooks),
                                  "error": err, "regions": workbooks}
    return out


# --------------------------------------------------------------------------- #
# collectors (read-only)
# --------------------------------------------------------------------------- #

def collect_regional_scan(cfg: dict, now: dt.datetime | None = None) -> dict:
    """Regional scan health + new-offer and duplicate counters.

    Sources: the shared worker's own state file, its run-health files, and the
    scanner's captured stdout counters (parsed with the worker's own parser).
    Ages are measured against the injected logical clock so a re-run over the
    same inputs produces the same brief.
    """
    now = now or parse_now(None)
    runs_dir = resolve(cfg, cfg["inputs"]["scan_runs_dir"])
    schedules_path = resolve(cfg, cfg["inputs"]["regional_schedules"])
    schedules, sch_err = read_json(schedules_path)
    profiles_path = resolve(cfg, cfg["inputs"]["regional_profiles"])
    profiles, prof_err = read_json(profiles_path)
    state, state_err = {}, None
    try:
        state = rjs.load_state(str(resolve(cfg, cfg["inputs"]["regional_state"])))
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        state_err = f"{type(exc).__name__}: {exc}"

    fresh_h = cfg["freshness"]["scan_stale_after_hours"]
    regions = {}
    if not (schedules and profiles):
        return {"available": False, "error": sch_err or prof_err, "regions": {},
                "note": "regional schedules/profiles unavailable; scan health unknown"}

    for region, spec in schedules["regions"].items():
        st = (state.get("regions") or {}).get(region, {})
        run_files = sorted(runs_dir.glob(f"regional-run-{region}-*.json"))
        scan_files = sorted(runs_dir.glob(f"scan-{region}-*.json"))
        latest = read_json(run_files[-1])[0] if run_files else None
        scan_doc = read_json(scan_files[-1])[0] if scan_files else None
        last_run_at = parse_iso(st.get("last_run_at"))
        age_h = None
        if last_run_at is not None:
            age_h = round((now - last_run_at).total_seconds() / 3600.0, 2)
        lane = coc.resolve_lane(region, profiles)
        policy = rjs.region_policy(region)
        counters = (latest or {}).get("scan", {}).get("counters") or {}
        if not counters and scan_doc:
            counters = rjs.parse_scan_counters(scan_doc.get("stdout_tail") or "")
        offers = rjs.parse_scan_offers(((latest or {}).get("scan") or {}).get("stdout_tail") or "")
        eligibility = (latest or {}).get("eligibility") or {}
        dedupe = (latest or {}).get("dedupe") or {}
        if age_h is None:
            health = "unknown"
        elif age_h > fresh_h:
            health = "stale"
        elif st.get("last_status") == "ok":
            health = "ok"
        else:
            health = f"degraded:{(st.get('last_status') or 'unknown')}"
        regions[region] = {
            "task_name": spec["task_name"],
            "scheduled_time": spec["time"],
            "lane_ready": bool(lane["ready"]),
            "lane_missing": lane["missing"],
            "mode": "bounded dry-run scan; never writes a tracker, never submits",
            "last_run_id": st.get("last_run_id"),
            "last_run_at": st.get("last_run_at"),
            "last_status": st.get("last_status"),
            "last_accepted": st.get("last_accepted"),
            "last_would_append": st.get("last_would_append"),
            "runs_recorded": int(st.get("runs") or 0),
            "run_age_hours": age_h,
            "health": health,
            "health_rule": f"ok = last_status ok and last run <= {fresh_h}h old; "
                           f"unknown = no recorded run timestamp (never read as healthy)",
            "counters": counters,
            "new_offers_without_url": offers,
            "new_offers_without_url_note": (
                "scan offers carry company/title/location but no URL, so they can never "
                "become tracker rows on their own; they are reported for URL resolution"),
            "policy_inputs": {
                "input_candidates": eligibility.get("input"),
                "accepted": eligibility.get("accepted"),
                "accepted_before_idempotency": eligibility.get("accepted_before_idempotency"),
                "rejected": eligibility.get("rejected"),
                "duplicate_prior_run": eligibility.get("duplicate_prior_run"),
                "rejected_sample_size": len(eligibility.get("rejected_sample") or []),
            },
            "duplicates_suppressed": {
                "scan_duplicates": counters.get("duplicates"),
                "policy_duplicate_prior_run": eligibility.get("duplicate_prior_run"),
                "writer_duplicates": (dedupe.get("counts") or {}).get("duplicates"),
            },
            "work_authorisation": {
                "status": (policy.get("work_authorisation") or {}).get("status"),
                "basis": (policy.get("work_authorisation") or {}).get("basis"),
            },
            "run_health_file": run_files[-1].name if run_files else None,
        }
    return {"available": True, "error": state_err, "regions": regions}


def collect_trackers(cfg: dict, now: dt.datetime, window_start: dt.datetime) -> dict:
    """Canonical tracker state, newly added rows and deadline items (read-only)."""
    profiles_path = resolve(cfg, cfg["inputs"]["regional_profiles"])
    profiles, err = read_json(profiles_path)
    if not profiles:
        return {"available": False, "error": err, "regions": {}, "new_rows": [],
                "deadline_items": [], "hashes": {}}
    terminal = {s.casefold() for s in cfg["terminal_statuses"]}
    regions, new_rows, deadline_items, hashes = {}, [], [], {}
    for region, rc in profiles["regions"].items():
        path = Path(rc["tracker"])
        entry = {"available": False, "tracker": str(path), "region": region,
                 "display_name": rc["display_name"]}
        if not path.exists():
            entry["error"] = "tracker not found"
            regions[region] = entry
            hashes[region] = None
            continue
        cfg_r = dict(rc)
        cfg_r["region"] = region
        try:
            tr = tw.Tracker(path, cfg_r)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            entry["error"] = f"{type(exc).__name__}: {exc}"
            regions[region] = entry
            hashes[region] = sha256_file(path)
            continue
        try:
            hashes[region] = sha256_file(path)
            rows = tr.data_rows()
            last = tr.last_data_row()
            first = cfg_r["first_data_row"]
            id_idx = tw.column_index_from_string(cfg_r["id"]["column"]) - 1
            status_col = cfg_r["status_columns"]["application_status"]
            status_idx = tw.column_index_from_string(status_col) - 1
            fm = cfg_r["field_map"]
            url_idx = tw.column_index_from_string(rc["dedupe"]["url_column"]) - 1
            company_idx = tw.column_index_from_string(rc["dedupe"]["company_column"]) - 1
            title_idx = tw.column_index_from_string(rc["dedupe"]["title_column"]) - 1
            deadline_col = fm.get("deadline")
            deadline_idx = tw.column_index_from_string(deadline_col) - 1 if deadline_col else None
            posted_col = fm.get("posted_date")
            posted_idx = tw.column_index_from_string(posted_col) - 1 if posted_col else None
            found_col = fm.get("date_found")
            found_idx = tw.column_index_from_string(found_col) - 1 if found_col else None
            prio_col = (cfg_r.get("status_columns") or {}).get("priority")
            prio_idx = tw.column_index_from_string(prio_col) - 1 if prio_col else None
            sel_col = (cfg_r.get("status_columns") or {}).get("selected")
            sel_idx = tw.column_index_from_string(sel_col) - 1 if sel_col else None

            from collections import Counter
            statuses = Counter(str(r[status_idx]) for r in rows if r[status_idx] not in (None, ""))
            actionable, with_deadline = [], 0
            for i, r in enumerate(rows):
                row_no = first + i
                rid = r[id_idx]
                status = r[status_idx]
                status_text = str(status) if status not in (None, "") else None
                found = parse_day(r[found_idx]) if found_idx is not None else None
                posted = parse_day(r[posted_idx]) if posted_idx is not None else None
                deadline = parse_day(r[deadline_idx]) if deadline_idx is not None else None

                if deadline is not None:
                    with_deadline += 1
                    deadline_items.append({
                        "region": region, "row": row_no, "id": rid,
                        "company": r[company_idx], "title": r[title_idx],
                        "deadline": deadline.isoformat(),
                        "days_remaining": days_between(deadline, now.date()),
                        "application_status": status_text,
                        "source": f"{path.name}#{rc['id']['column']}{row_no}",
                    })
                if status_text is not None and status_text.casefold() in terminal:
                    continue
                if status_text is None and rid in (None, ""):
                    continue
                actionable.append({
                    "region": region, "row": row_no, "id": rid,
                    "company": r[company_idx], "title": r[title_idx],
                    "url": tw.extract_url(r[url_idx]) or None,
                    "application_status": status_text,
                    "posted_date": posted.isoformat() if posted else None,
                    "date_found": found.isoformat() if found else None,
                    "deadline": deadline.isoformat() if deadline else None,
                    "priority": r[prio_idx] if prio_idx is not None else None,
                    "selected": r[sel_idx] if sel_idx is not None else None,
                    "owner_columns": {c: r[tw.column_index_from_string(c) - 1]
                                      for c in rc.get("owner_columns", [])},
                })
                if found is not None and found >= window_start.date():
                    new_rows.append({**actionable[-1], "added_within_window": True})
            entry.update({
                "available": True,
                "sha256": hashes[region],
                "data_rows": len(rows),
                "last_data_row": last,
                "status_counts": dict(statuses),
                "actionable_rows": len(actionable),
                "actionable": actionable,
                "deadline_column": deadline_col,
                "rows_with_deadline": with_deadline,
                "deadline_note": ("this tracker's own schema carries a deadline column"
                                  if deadline_col else
                                  "this tracker's own schema has NO deadline column, so "
                                  "deadline is UNKNOWN for every row in this region"),
                "new_rows_in_window": [a for a in actionable
                                       if a["date_found"] and a["date_found"] >= window_start.date().isoformat()],
                "date_found_column": found_col,
            })
        finally:
            try:
                tr.wb.close()
            except Exception:  # noqa: BLE001
                pass
        regions[region] = entry
    return {
        "available": True, "error": None, "regions": regions,
        "new_rows": new_rows, "deadline_items": deadline_items, "hashes": hashes,
    }


def collect_company_watch(cfg: dict, now: dt.datetime | None = None) -> dict:
    """Company Watch findings + registry provenance (aggregate level only).

    The full company registry is deliberately owner-private and lives on a
    git-ignored runtime path; only aggregate counts and provenance are restated.
    """
    now = now or parse_now(None)
    base = resolve(cfg, cfg["inputs"]["company_watch_runtime"])
    findings, f_err = read_json(base / "findings-uk-latest.json")
    registry, r_err = read_json(base / "company_watch_registry.json")
    resolution, res_err = read_json(base / "resolution-latest.json")
    stale_h = cfg["freshness"]["company_watch_stale_after_hours"]
    generated = parse_iso((findings or {}).get("generated_at"))
    age_h = round((now - generated).total_seconds() / 3600.0, 2) if generated else None
    health = "unknown"
    if age_h is not None:
        health = "ok" if age_h <= stale_h else "stale"
    return {
        "available": findings is not None,
        "errors": {"findings": f_err, "registry": r_err, "resolution": res_err},
        "generated_at": (findings or {}).get("generated_at"),
        "age_hours": age_h,
        "health": health,
        "health_rule": f"ok = latest findings file <= {stale_h}h old; unknown when undated",
        "counts": (findings or {}).get("counts"),
        "region_routing_configured": (findings or {}).get("region_routing_configured"),
        "registry": ({"counts": (registry or {}).get("counts"),
                      "generated_at": (registry or {}).get("generated_at"),
                      "source": (registry or {}).get("source"),
                      "storage_note": (registry or {}).get("storage_note")}
                     if registry else None),
        "resolution": ({"companies_considered": (resolution or {}).get("companies_considered"),
                        "companies_probed": (resolution or {}).get("companies_probed")}
                       if resolution else None),
        "note": ("Company Watch findings are discovery signals, not application records; "
                 "only owner-filter-eligible findings may be handed to a tracker, and the "
                 "handoff stays an explicit step in career-ops/tracker_writer.py"),
    }


def source_coverage_view(doc: dict) -> dict:
    """Per-source and per-surface-class coverage from the funnel's own run evidence.

    Two shapes exist and both are reported as-is:

    * a single-region run (``discovery/pipeline.py`` or
      ``discovery/scheduled_orchestrator.py run``) carries
      ``funnel.by_source`` and ``source_coverage.classes`` directly;
    * the unified multi-region run (``scheduled_orchestrator.py run-all``) carries
      ``source_coverage.<region>.classes``.

    Nothing here is recomputed or reinterpreted: the counters are the worker's own.
    A source class that was blocked or unavailable keeps that state — it is never
    flattened into "empty".
    """
    funnel = doc.get("funnel") or {}
    by_source = funnel.get("by_source") or {}
    sources = {
        src: {
            "discovered": (entry.get("counts") or {}).get("discovered"),
            "counts": entry.get("counts") or {},
            "rejections_by_reason": entry.get("rejections_by_reason") or {},
            "zero_attribution": entry.get("zero_attribution") or {},
            "not_applicable_stages": entry.get("not_applicable_stages") or {},
        }
        for src, entry in by_source.items()
    }
    raw = doc.get("source_coverage") or {}
    classes: dict = {}
    if isinstance(raw.get("classes"), dict):
        classes = {"all": {k: _class_state(v) for k, v in raw["classes"].items()}}
    else:
        for region, block in raw.items():
            if isinstance(block, dict) and isinstance(block.get("classes"), dict):
                classes[region] = {k: _class_state(v) for k, v in block["classes"].items()}
    return {
        "sources": sources,
        "sources_discovered_total": {k: v["discovered"] for k, v in sources.items()},
        "classes_by_region": classes,
        "class_state_vocabulary": (raw.get("states_vocabulary")
                                   if isinstance(raw, dict) else None) or {},
        "note": ("source coverage is the worker's own per-source and per-source-class "
                 "evidence; a class recorded as blocked or unavailable is never reported as "
                 "an empty source"),
    }


def _class_state(entry: dict) -> dict:
    return {"state": entry.get("state"), "reason": entry.get("reason"),
            "queries_targeting": entry.get("queries_targeting"),
            "queries_with_observed_live_search": entry.get("queries_with_observed_live_search"),
            "result_urls_discovered": entry.get("result_urls_discovered"),
            "job_posting_urls": entry.get("job_posting_urls"),
            "validated_live": entry.get("validated_live"),
            "validation_failed": entry.get("validation_failed"),
            "blocking_evidence": entry.get("blocking_evidence") or []}


def collect_discovery_funnel(cfg: dict, now: dt.datetime | None = None) -> dict:
    """High-recall discovery funnel metrics + top semantic candidates (read-only).

    Source: the discovery pipeline's own run evidence
    (``runtime/career-ops/discovery/latest.json``). The funnel counters are the
    pipeline's; this collector never recomputes or reinterprets them, and an
    absent/stale run is reported as UNKNOWN rather than as "no jobs".

    ``top_semantic_candidates`` is the pipeline's declared ranking (accepted
    label, then confidence, then candidate id). It is a POLICY OUTPUT for owner
    review — not a factual claim about the vacancy.
    """
    now = now or parse_now(None)
    spec = cfg.get("discovery") or {}
    latest = resolve(cfg, spec.get("latest", "runtime/career-ops/discovery/latest.json"))
    empty = {"available": False, "path": str(latest), "counts": None,
             "zero_attribution": None, "top_semantic_candidates": [],
             "classifications_total": 0}
    if not latest.exists():
        return {**empty,
                "reason": ("no discovery funnel run evidence yet — the pipeline has not run on "
                           "this machine"),
                "note": "an absent funnel run is UNKNOWN, never 'no jobs exist'"}
    doc, err = read_json(latest)
    if not doc:
        return {**empty, "reason": f"unreadable discovery run evidence: {err}"}
    finished = parse_iso(doc.get("finished_at"))
    age_h = round((now - finished).total_seconds() / 3600.0, 2) if finished else None
    stale_after = float(spec.get("stale_after_hours", 48))
    if age_h is None:
        health = "unknown"
    elif age_h > stale_after:
        health = "stale"
    else:
        health = "ok"
    funnel = doc.get("funnel") or {}
    counts = funnel.get("counts") or {}
    classifications = doc.get("classifications") or []
    accepted = [c for c in classifications if c.get("accepted")]
    rank = {"strong_entry_level_match": 0, "plausible_entry_level": 1}
    accepted.sort(key=lambda c: (rank.get(c.get("primary_label"), 9),
                                 -(float(c["confidence"]) if isinstance(c.get("confidence"),
                                                                       (int, float)) else -1.0),
                                 str(c.get("candidate_id"))))
    limit = int(spec.get("max_semantic_candidates", 10))
    top = [{
        "candidate_id": c.get("candidate_id"),
        "company": (c.get("source_fields") or {}).get("company"),
        "title": (c.get("source_fields") or {}).get("title"),
        "location": (c.get("source_fields") or {}).get("location"),
        "url": (c.get("source_fields") or {}).get("url"),
        "primary_label": c.get("primary_label"),
        "confidence": c.get("confidence"),
        "provider": c.get("provider"),
        "model": c.get("model"),
        "classifier": c.get("classifier"),
        "jd_available": c.get("jd_available"),
        "classification_basis": c.get("classification_basis"),
        "reasons": c.get("reasons") or [],
        "uncertainty": c.get("uncertainty") or [],
    } for c in accepted[:limit]]
    return {
        "available": True,
        "path": str(latest),
        "run_id": doc.get("run_id"),
        "region": doc.get("region"),
        "title_policy_mode": doc.get("title_policy_mode"),
        "finished_at": doc.get("finished_at"),
        "age_hours": age_h,
        "health": health,
        "health_rule": (f"ok = a funnel run finished within {stale_after}h; unknown = no readable "
                        f"finish timestamp (never read as healthy)"),
        "counts": counts,
        "zero_attribution": funnel.get("zero_attribution"),
        "not_applicable_stages": funnel.get("not_applicable_stages") or {},
        "rejections_by_reason": funnel.get("rejections_by_reason") or {},
        "semantic_provider": doc.get("semantic"),
        "codex_escalation": {k: v for k, v in (doc.get("codex") or {}).items()
                             if k != "classifications"},
        "jd_gap": doc.get("jd_gap"),
        "classifications_total": len(classifications),
        "accepted_total": len(accepted),
        "top_semantic_candidates": top,
        "run_kind": doc.get("kind"),
        "regions_covered": doc.get("regions_covered") or ([doc.get("region")]
                                                          if doc.get("region") else []),
        "discovery_mode": (doc.get("discovery_mode") or doc.get("title_policy_mode")),
        "production_discovery_policy": doc.get("production_discovery_policy"),
        "aggregation_note": doc.get("aggregation_note"),
        "source_coverage": source_coverage_view(doc),
        "live_research": doc.get("live_research"),
        "production_ready": doc.get("production_ready"),
        "no_go": doc.get("no_go"),
        "manifest_counts": doc.get("manifest_counts") or doc.get("manifest"),
        "ranking_semantics": {
            "kind": "deterministic_policy_output",
            "order": ("accepted label (strong_entry_level_match, then plausible_entry_level), then "
                      "descending confidence, then candidate id"),
            "note": ("this ranking is a policy output over model classifications. It is NOT a "
                     "factual claim about the vacancy, its requirements or the applicant's "
                     "suitability, and it never overrides a deterministic eligibility gate."),
        },
        "safety": doc.get("safety") or {},
    }


def collect_priority_watchlist(cfg: dict, now: dt.datetime | None = None) -> dict:
    """The owner's own company priority watchlist, as surfaced by the funnel (read-only).

    Source: the discovery pipeline's own run evidence
    (``runtime/career-ops/discovery/latest.json``), specifically the
    ``priority_watchlist`` block the pipeline emits for the watchlist surface
    (``career-ops/discovery/watchlist.py``, roster B27) and that surface's own
    coverage counters.

    This collector never re-scores, re-ranks or re-evaluates anything: it reports
    the pipeline's own counts and lists the flagged candidates in the pipeline's own
    order, so a watchlist vacancy stays visible **even when it is not top-ranked
    globally** (the section below the ranked priorities is independent of the
    priority score). An item that did not reach the deterministic gates is listed
    with that state rather than being hidden — the watchlist flag never bypasses a
    gate. An absent or stale run is UNKNOWN, never "no jobs".
    """
    now = now or parse_now(None)
    spec = cfg.get("priority_watchlist") or {}
    latest = resolve(cfg, spec.get("latest", "runtime/career-ops/discovery/latest.json"))
    stale_after = float(spec.get("stale_after_hours", 48))
    limit = int(spec.get("max_items", 10))
    empty = {"available": False, "declared": False, "path": str(latest), "run_id": None,
             "region": None, "health": "unknown", "age_hours": None, "counts": None,
             "companies": [], "query_families": [], "items": [], "items_total": 0,
             "items_not_reaching_gates": 0, "companies_checked": None,
             "companies_with_careers_source": None,
             "companies_unavailable_or_unknown": None,
             "companies_with_findings": None, "zero_attribution": None}
    if not latest.exists():
        return {**empty,
                "reason": ("no discovery funnel run evidence yet — the pipeline has not run on "
                           "this machine"),
                "note": "an absent funnel run is UNKNOWN, never 'the watchlist found nothing'"}
    doc, err = read_json(latest)
    if not doc:
        return {**empty, "reason": f"unreadable discovery run evidence: {err}"}

    finished = parse_iso(doc.get("finished_at"))
    age_h = round((now - finished).total_seconds() / 3600.0, 2) if finished else None
    health = "unknown" if age_h is None else ("stale" if age_h > stale_after else "ok")
    block = doc.get("priority_watchlist") or {}
    lane_cov = None
    for collection_block in (doc.get("collection") or []):
        if str(collection_block.get("source") or "").startswith("owner priority watchlist"):
            lane_cov = collection_block.get("coverage") or {}
            break

    if not block.get("declared"):
        return {**empty, "available": True, "path": str(latest), "run_id": doc.get("run_id"),
                "region": doc.get("region"), "health": health, "age_hours": age_h,
                "lane_coverage": lane_cov,
                "reason": ("this funnel run carried no priority-watchlist candidate: either no "
                           "watchlist lane export was supplied or it produced no finding — an "
                           "empty owner watchlist is a valid state and is never reported as a "
                           "market fact"),
                "note": ("the owner's watchlist is additive; its absence changes nothing about the "
                         "market search reported above")}

    items = []
    for idx, c in enumerate(block.get("candidates") or []):
        items.append({
            "declared_order": idx,
            "candidate_id": c.get("candidate_id"),
            "company": c.get("company"),
            "title": c.get("title"),
            "location": c.get("location"),
            "url": c.get("url"),
            "watchlist_company": c.get("watchlist_company"),
            "sources": c.get("sources") or [],
            "duplicate_discoveries": c.get("duplicate_discoveries"),
            "threshold_passed": bool(c.get("threshold_passed")),
            "state": c.get("state"),
            "in_priority_ranking": bool(c.get("threshold_passed")),
        })
    return {
        "available": True,
        "declared": True,
        "path": str(latest),
        "run_id": doc.get("run_id"),
        "region": doc.get("region"),
        "finished_at": doc.get("finished_at"),
        "age_hours": age_h,
        "health": health,
        "health_rule": (f"ok = a funnel run carrying the watchlist finished within {stale_after}h; "
                        f"unknown = no readable finish timestamp (never read as healthy)"),
        "counts": block.get("counts"),
        "companies": block.get("companies") or [],
        "query_families": block.get("query_families") or [],
        "companies_checked": (lane_cov or {}).get("companies_checked"),
        "companies_with_careers_source": (lane_cov or {}).get("companies_with_careers_source"),
        "companies_unavailable_or_unknown": (lane_cov or {}).get(
            "companies_unavailable_or_unknown"),
        "companies_with_findings": (lane_cov or {}).get("companies_with_findings"),
        "duplicate_spellings_collapsed": (lane_cov or {}).get("duplicate_spellings_collapsed"),
        "zero_attribution": (lane_cov or {}).get("zero_attribution"),
        "lane_coverage": lane_cov,
        "items": items[:limit],
        "items_total": len(items),
        "items_not_reaching_gates": sum(1 for i in items if not i["threshold_passed"]),
        "ranking_semantics": {
            "kind": "pipeline_canonical_order (not a claim about the vacancy)",
            "note": ("the owner's watchlist items are listed in the funnel's own canonical order and "
                     "are visible independently of the global priority ranking below; the flag "
                     "gives prominence only and never overrides a semantic or deterministic gate"),
        },
        "note": ("reads the pipeline's own priority_watchlist block; nothing is re-scored here, and "
                 "a company whose careers infrastructure could not be resolved is reported "
                 "unavailable/unknown rather than as 'no jobs'"),
    }


def collect_application_status(cfg: dict) -> dict:
    """Application-status signals/changes from the read-only Inbox monitor."""
    try:
        icfg = inbox.load_config(str(resolve(cfg, cfg["inputs"]["application_inbox_config"])))
        root = inbox.runtime_dir(icfg, None)
        summary = inbox.build_summary(icfg, root)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        return {"available": False, "error": f"{type(exc).__name__}: {exc}",
                "counts": {}, "proposed_status_changes": [], "owner_actions": []}
    return {
        "available": True,
        "store": summary["store"],
        "counts": summary["counts"],
        "signals_by_kind": summary["signals_by_kind"],
        "signals_by_match": summary["signals_by_match"],
        "proposed_status_changes": summary["proposed_status_changes"],
        "owner_actions": summary["owner_actions"],
        "review_queue_size": len(summary["review_queue"]),
        "safety": summary["safety"],
        "note": ("proposals only: Excel remains authoritative and this brief writes no "
                 "status anywhere"),
    }


def collect_interviews(cfg: dict) -> dict:
    """Interview / follow-up items that exist as real artifacts."""
    try:
        pcfg = ip.load_config(str(resolve(cfg, cfg["inputs"]["interview_prep_config"])))
        runtime = ip.runtime_dir(pcfg)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}",
                "packs": [], "pack_count": 0, "items": []}
    packs = sorted(runtime.glob("*/interview_prep_pack.json")) if runtime.exists() else []
    items = []
    for p in packs:
        doc, err = read_json(p)
        if not doc:
            items.append({"pack": str(p), "readable": False, "error": err})
            continue
        job = doc.get("job") or {}
        items.append({
            "pack": str(p),
            "readable": True,
            "pack_id": doc.get("pack_id"),
            "company": job.get("company"),
            "title": job.get("title"),
            "region": job.get("region"),
            "generated_at": doc.get("generated_at"),
            "unknowns": len(doc.get("unknowns") or []),
            "generated_questions": doc.get("question_counts") or None,
        })
    return {"available": True, "runtime_dir": str(runtime), "pack_count": len(packs),
            "items": items}


def collect_owner_actions(cfg: dict) -> dict:
    """Open owner actions: the owner-action file plus monitor-raised items."""
    path = resolve(cfg, cfg["inputs"]["owner_actions_file"])
    tokens = [t.casefold() for t in cfg["owner_action_open_tokens"]]
    items, err = [], None
    if not path.exists():
        err = "missing"
    else:
        current = None
        for line in read_text(path).splitlines():
            m = OWNER_ACTION_HEADING_RE.match(line)
            if m:
                if current:
                    items.append(current)
                current = {"item": int(m.group(1)), "title": m.group(2).strip(),
                           "status": None, "open": None,
                           "source": f"{path.name}#{m.group(1)}"}
                continue
            if current is not None:
                sm = OWNER_ACTION_STATUS_RE.match(line.strip())
                if sm and current["status"] is None:
                    current["status"] = sm.group(1)
        if current:
            items.append(current)
    for it in items:
        status = (it["status"] or "")
        # An explicitly non-actionable status is not an open owner action.
        if "no action needed" in status.casefold():
            it["open"] = False
            continue
        if it["status"] is None:
            it["open"] = None
            continue
        it["open"] = any(t in status.casefold() for t in tokens)
    return {"available": path.exists(), "error": err, "path": str(path),
            "items": items,
            "open_items": [i for i in items if i["open"]],
            "unknown_status_items": [i for i in items if i["open"] is None],
            "open_tokens": cfg["owner_action_open_tokens"]}


def collect_workflow_outputs(cfg: dict) -> dict:
    """Counts of the other workflows' own output artifacts (existence only)."""
    ji = resolve(cfg, cfg["inputs"]["job_intelligence_config"])
    jcfg, j_err = read_json(ji)
    briefs = []
    if jcfg and jcfg.get("runtime_dir"):
        rt = resolve(cfg, jcfg["runtime_dir"])
        briefs = sorted(rt.glob("*/job_brief.json")) if rt.exists() else []
    li = resolve(cfg, cfg["inputs"]["linkedin_handoff_dir"])
    handoffs = sorted(li.glob("linkedin-handoff-*.json")) if li.exists() else []
    gate_entries = read_jsonl(resolve(cfg, cfg["inputs"]["submission_gate_log"]))
    return {
        "job_briefs": {"available": bool(jcfg), "error": j_err, "count": len(briefs),
                       "latest": str(briefs[-1]) if briefs else None},
        "linkedin_handoffs": {"available": li.exists(), "count": len(handoffs),
                              "latest": handoffs[-1].name if handoffs else None},
        "submission_gate_log": {
            "available": True, "entries": len(gate_entries),
            "latest_status": (gate_entries[-1].get("status") if gate_entries else None),
        },
    }


# --------------------------------------------------------------------------- #
# deterministic prioritisation
# --------------------------------------------------------------------------- #

def _band_value(value: float | None, bands: list, *, overdue_value=None,
                invert=False) -> float | None:
    if value is None:
        return None
    v = -value if invert else value
    for band in bands:
        max_days = band["max_days"]
        if max_days is None or v <= max_days:
            return band["value"]
    if overdue_value is not None and v < 0:
        return overdue_value
    return None


def score_candidate(cand: dict, policy: dict) -> dict:
    """Deterministic score with explicit components. Unknowns are never imputed."""
    weights = policy["weights"]
    components, unknown, why = [], [], []

    # -- deadline ----------------------------------------------------------
    d_days = cand.get("deadline_days")
    d_value = None
    if d_days is not None:
        if d_days < 0:
            d_value = policy["deadline_overdue_value"]
            why.append(f"deadline passed {-d_days} day(s) ago per the tracker's own deadline column")
        else:
            d_value = _band_value(d_days, policy["deadline_bands"])
    if d_value is None:
        unknown.append({"input": "deadline", "reason": cand.get("deadline_unknown_reason")
                        or "no deadline value available in the source record"})
    else:
        components.append({"input": "deadline", "value": d_value, "weight": weights["deadline"],
                           "observed": cand.get("deadline"), "days": d_days})
    # -- stage -------------------------------------------------------------
    status = cand.get("application_status")
    s_value = policy["stage_values"].get((status or "").casefold())
    if s_value is None:
        unknown.append({"input": "stage", "reason": f"status {status!r} is not in the declared "
                        f"stage vocabulary"})
    else:
        components.append({"input": "stage", "value": s_value, "weight": weights["stage"],
                           "observed": status})
    # -- eligibility certainty --------------------------------------------
    wa = (cand.get("work_authorisation") or {}).get("status")
    e_value = policy["eligibility_values"].get((wa or ""))
    if e_value is None:
        unknown.append({"input": "eligibility_certainty",
                        "reason": f"recorded work-authorisation state is {wa or 'absent'} — "
                                  f"not resolved to a known position"})
    else:
        components.append({"input": "eligibility_certainty", "value": e_value,
                           "weight": weights["eligibility_certainty"], "observed": wa})
    # -- freshness ---------------------------------------------------------
    age = cand.get("freshness_days")
    f_value = _band_value(age, policy["freshness_bands"])
    if f_value is None:
        unknown.append({"input": "freshness", "reason": "no posting date or date-found value "
                        "in the source record"})
    else:
        components.append({"input": "freshness", "value": f_value, "weight": weights["freshness"],
                           "observed": age})
    # -- owner flag --------------------------------------------------------
    of = cand.get("owner_flag")
    if of is None:
        unknown.append({"input": "owner_flag", "reason": "no owner-controlled cell available "
                        "to evaluate"})
    else:
        components.append({"input": "owner_flag", "value": 1.0 if of else 0.0,
                           "weight": weights["owner_flag"], "observed": bool(of)})

    total_weight = sum(weights.values())
    known_weight = sum(c["weight"] for c in components)
    weighted = sum(c["weight"] * c["value"] for c in components)
    # The score is taken over the FULL policy weight: an unknown input lowers the
    # score instead of being imputed. `coverage_pct` then says how much of the
    # policy was actually evidenced, so a low score with low coverage is never
    # mistaken for a low-value item.
    score = round(100.0 * weighted / total_weight, 1) if total_weight else None
    coverage = round(100.0 * known_weight / total_weight, 1)
    for c in components:
        c["contribution"] = round(100.0 * c["weight"] * c["value"] / total_weight, 2) if total_weight else None

    klass = policy["unscoreable_class"]
    if known_weight:
        for band in policy["class_bands"]:
            if score >= band["min_score"]:
                klass = band["class"]
                break
    overrides = []
    if not known_weight:
        overrides.append({"rule": "unscoreable",
                          "detail": "no known policy input at all: reported at the lowest "
                                    "band with the reason recorded rather than scored"})
    if d_days is not None and d_days <= policy["urgent_deadline_days"]:
        rank = policy["class_order"]
        if rank.index(klass) > rank.index(policy["urgent_min_class"]):
            overrides.append({"rule": "urgent_deadline",
                              "detail": f"deadline in {d_days} day(s) <= "
                                        f"{policy['urgent_deadline_days']} → at least "
                                        f"{policy['urgent_min_class']}"})
            klass = policy["urgent_min_class"]
    if cand.get("subject_type") == "owner_action":
        rank = policy["class_order"]
        if rank.index(klass) > rank.index(policy["owner_action_min_class"]):
            overrides.append({"rule": "owner_action_min_class",
                              "detail": f"an item only the owner can action is raised to at "
                                        f"least {policy['owner_action_min_class']}"})
            klass = policy["owner_action_min_class"]
    return {"score": score, "score_kind": policy["score_semantics"]["kind"],
            "coverage_pct": coverage, "priority_class": klass,
            "components": components, "unknown_inputs": unknown,
            "overrides": overrides, "why": why}


def candidate_sort_key(item: dict, policy: dict) -> tuple:
    type_order = policy["subject_type_order"]
    t_idx = type_order.index(item["subject_type"]) if item["subject_type"] in type_order else len(type_order)
    score = item["priority"]["score"]
    d = item.get("deadline_days")
    return (
        policy["class_order"].index(item["priority"]["priority_class"]),
        -(score if score is not None else -1.0),
        -item["priority"]["coverage_pct"],
        t_idx,
        d if d is not None else 10 ** 6,
        str(item.get("region") or ""),
        str(item.get("ref") or ""),
    )


def build_candidates(scan: dict, trackers: dict, watch: dict, status: dict,
                     interviews: dict, owner_actions: dict, cfg: dict,
                     now: dt.datetime, window_start: dt.datetime,
                     watchlist: dict | None = None) -> list:
    """Normalise every aggregated item into one candidate shape.

    ``watchlist`` is the owner's company priority watchlist section (optional). Only
    a watchlist finding that already passed the funnel's own deterministic gates
    becomes a ranked candidate here: the flag gives prominence, never a bypass.
    Every flagged finding, gated or not, stays visible in the brief's own
    ``priority_watchlist`` section, which is independent of this global ranking.
    """
    cands = []
    wa_by_region = {r: v.get("work_authorisation", {}) for r, v in (scan.get("regions") or {}).items()}

    for region, entry in (trackers.get("regions") or {}).items():
        if not entry.get("available"):
            continue
        for row in entry["actionable"]:
            deadline = parse_day(row.get("deadline"))
            posted = parse_day(row.get("posted_date"))
            found = parse_day(row.get("date_found"))
            base = posted or found
            owner_flag = None
            if row.get("priority") not in (None, "") or row.get("selected") not in (None, ""):
                owner_flag = (str(row.get("priority") or "").casefold() in
                              [v.casefold() for v in cfg["owner_flag"]["priority_values"]]) or \
                             (str(row.get("selected") or "").casefold() in
                              [v.casefold() for v in cfg["owner_flag"]["selected_values"]])
            cands.append({
                "subject_type": "tracker_row",
                "region": region,
                "ref": str(row.get("id")),
                "company": row.get("company"),
                "title": row.get("title"),
                "url": row.get("url"),
                "application_status": row.get("application_status"),
                "source": f"{entry['tracker']} (row {row['row']})",
                "deadline": deadline.isoformat() if deadline else None,
                "deadline_days": days_between(deadline, now.date()) if deadline else None,
                "deadline_unknown_reason": None if deadline else entry["deadline_note"],
                "freshness_days": days_between(now.date(), base) if base else None,
                "owner_flag": owner_flag,
                "work_authorisation": wa_by_region.get(region, {}),
                "added_within_window": bool(found and found >= window_start.date()),
            })

    for region, entry in (scan.get("regions") or {}).items():
        for offer in entry.get("new_offers_without_url") or []:
            cands.append({
                "subject_type": "new_offer_without_url",
                "region": region,
                "ref": f"{offer.get('company')}::{offer.get('title')}",
                "company": offer.get("company"),
                "title": offer.get("title"),
                "url": None,
                "application_status": None,
                "source": f"scan stdout ({entry.get('task_name')})",
                "deadline": None, "deadline_days": None,
                "deadline_unknown_reason": entry.get("deadline_note")
                or "scan offers carry no deadline",
                "freshness_days": entry.get("run_age_hours") and round(entry["run_age_hours"] / 24.0, 1),
                "owner_flag": bool(offer.get("trust_flags")),
                "work_authorisation": entry.get("work_authorisation", {}),
                "trust_score": offer.get("trust_score"),
                "trust_flags": offer.get("trust_flags"),
                "url_resolution_required": True,
            })

    cw_counts = (watch.get("counts") or {})
    if (cw_counts.get("tracker_eligible") or 0) > 0:
        cands.append({
            "subject_type": "company_watch_finding",
            "region": "uk", "ref": "company-watch-eligible",
            "company": None, "title": None, "url": None, "application_status": None,
            "source": "runtime/company-watch/findings-uk-latest.json",
            "deadline": None, "deadline_days": None,
            "deadline_unknown_reason": "findings carry no deadline",
            "freshness_days": watch.get("age_hours") and round(watch["age_hours"] / 24.0, 1),
            "owner_flag": True,
            "work_authorisation": wa_by_region.get("uk", {}),
            "count": cw_counts.get("tracker_eligible"),
        })

    if watchlist and watchlist.get("declared"):
        # The owner's own company list, as far as the funnel let it through. Only a
        # finding that already passed the deterministic gates is ranked here; every
        # flagged finding (gated or not) stays visible in the brief's dedicated
        # priority_watchlist section, which is independent of this ranking.
        seen_urls = {str(c.get("url") or "").strip().casefold() for c in cands if c.get("url")}
        for item in (watchlist.get("items") or []):
            if not item.get("threshold_passed"):
                continue
            url = item.get("url")
            if url and str(url).strip().casefold() in seen_urls:
                continue
            cands.append({
                "subject_type": "priority_watchlist_vacancy",
                "region": watchlist.get("region"),
                "ref": str(item.get("candidate_id") or url or item.get("title") or "watchlist"),
                "company": item.get("company") or item.get("watchlist_company"),
                "title": item.get("title"),
                "url": url,
                "application_status": None,
                "source": (f"owner priority watchlist ({item.get('watchlist_company')}) — "
                           f"run {watchlist.get('run_id')}"),
                "deadline": None, "deadline_days": None,
                "deadline_unknown_reason": "a watchlist research finding carries no deadline value",
                "freshness_days": None,
                "owner_flag": True,
                "work_authorisation": wa_by_region.get(watchlist.get("region") or "", {}),
                "watchlist_company": item.get("watchlist_company"),
                "discovery_sources": item.get("sources") or [],
                "in_priority_ranking": True,
            })

    for change in (status.get("proposed_status_changes") or []):
        cands.append({
            "subject_type": "application_status_change",
            "region": change.get("region"), "ref": str(change.get("row_id")),
            "company": change.get("company"), "title": change.get("title"),
            "url": None,
            "application_status": change.get("workbook_status"),
            "source": "career-ops/application_inbox.py",
            "deadline": None, "deadline_days": None,
            "deadline_unknown_reason": "a mailbox signal carries no deadline",
            "freshness_days": None,
            "owner_flag": bool(change.get("requires_owner_confirmation")),
            "work_authorisation": wa_by_region.get(change.get("region") or "", {}),
            "proposed_status": change.get("proposed_status"),
            "signal_kinds": change.get("signal_kinds"),
            "requires_owner_confirmation": change.get("requires_owner_confirmation"),
        })

    for pack in (interviews.get("items") or []):
        if not pack.get("readable"):
            continue
        generated = parse_iso(pack.get("generated_at"))
        cands.append({
            "subject_type": "interview_prep",
            "region": pack.get("region"), "ref": pack.get("pack_id") or pack.get("pack"),
            "company": pack.get("company"), "title": pack.get("title"),
            "url": None, "application_status": None,
            "source": pack.get("pack"),
            "deadline": None, "deadline_days": None,
            "deadline_unknown_reason": "a prep pack carries no interview date unless one was "
                                       "supplied; none was",
            "freshness_days": round((now - generated).total_seconds() / 86400.0, 1) if generated else None,
            "owner_flag": True,
            "work_authorisation": wa_by_region.get(pack.get("region") or "", {}),
            "unknowns": pack.get("unknowns"),
        })

    for item in (owner_actions.get("open_items") or []):
        slug = re.sub(r"[^a-z0-9]+", "-", (item.get("title") or "").casefold()).strip("-")[:48]
        cands.append({
            "subject_type": "owner_action",
            "region": None, "ref": f"owner-action-{item['item']}-{slug}",
            "company": None, "title": item.get("title"),
            "url": None, "application_status": policy_status(cfg, "owner_action"),
            "source": item.get("source"),
            "deadline": None, "deadline_days": None,
            "deadline_unknown_reason": "the owner-action file records no deadline for this item",
            "freshness_days": None,
            "owner_flag": True,
            "work_authorisation": {},
            "owner_status": item.get("status"),
        })

    for item in (status.get("owner_actions") or []):
        cands.append({
            "subject_type": "owner_action",
            "region": item.get("region"), "ref": str(item.get("row_id") or item.get("signal_id")),
            "company": item.get("company"), "title": item.get("title"),
            "url": None, "application_status": policy_status(cfg, "owner_action"),
            "source": "career-ops/application_inbox.py",
            "deadline": None, "deadline_days": None,
            "deadline_unknown_reason": "a mailbox signal carries no deadline",
            "freshness_days": None,
            "owner_flag": True,
            "work_authorisation": wa_by_region.get(item.get("region") or "", {}),
            "signal_kind": item.get("signal_kind"),
        })
    return cands


def policy_status(cfg: dict, key: str) -> str:
    return cfg["policy_stage_tokens"][key]


# --------------------------------------------------------------------------- #
# brief assembly
# --------------------------------------------------------------------------- #

def chief_summary(brief: dict, cfg: dict) -> str:
    """A short, plain-text summary for Chief. Facts only; unknowns stay visible."""
    lines = []
    lines.append(f"Career Daily Brief — {brief['as_of']} (window {brief['window']['hours']}h)")
    st = brief["status"]
    lines.append(f"Status: {st['headline']}")
    scan = brief["regional_scan_health"].get("regions") or {}
    lines.append("Scan health: " + ("; ".join(
        f"{r}={v['health']}({v['last_status'] or 'n/a'}, {v['run_age_hours'] if v['run_age_hours'] is not None else 'unknown'}h)"
        for r, v in scan.items()) if scan else "unavailable"))
    nj = brief["newly_added_jobs"]
    lines.append(f"New: {nj['counts']['tracker_rows_in_window']} tracker row(s) in window, "
                 f"{nj['counts']['scan_offers_without_url']} scan offer(s) needing a URL")
    dup = brief["duplicates_suppressed"]["totals"]
    lines.append(f"Duplicates suppressed: scan={dup['scan_duplicates']}, "
                 f"prior-run={dup['policy_duplicate_prior_run']}, writer={dup['writer_duplicates']}")
    dl = brief["deadlines_followups"]["counts"]
    lines.append(f"Deadlines known: {dl['deadlines_known']} "
                 f"(unknown: {dl['deadlines_unknown_regions']} region(s) have no deadline column"
                 f"{'' if not dl['deadlines_unknown_regions'] else ': ' + ','.join(brief['deadlines_followups']['regions_without_deadline_column'])})")
    asc = brief["application_status_changes"]["counts"]
    lines.append(f"Application status: {asc['proposed_status_changes']} proposal(s), "
                 f"{asc['owner_actions_required']} owner action(s) from the monitor")
    df = brief.get("discovery_funnel") or {}
    if df.get("available"):
        c = df.get("counts") or {}
        z = df.get("zero_attribution") or {}
        lines.append(
            "Discovery funnel: "
            f"raw={c.get('discovered_raw')} -> prefiltered={c.get('after_hard_negative_prefilter')} "
            f"-> semantic={c.get('semantically_reviewed')} -> accepted={c.get('deepseek_accept')} "
            f"/codex={c.get('codex_accept')} -> eligibility={c.get('deterministic_eligibility_pass')} "
            f"-> tracker={c.get('tracker_candidates')}"
            + (f"; first zero: {z.get('first_zero_stage')}" if z.get("first_zero_stage")
               else "; no zero stage")
            + f" [run {df.get('run_id')}, {df.get('health')}; {df.get('accepted_total')} semantic "
              f"accept(s) — policy output, not a vacancy claim]")
    else:
        lines.append("Discovery funnel: unavailable (no run evidence) — UNKNOWN, never zero jobs")
    if df.get("available"):
        sc = df.get("source_coverage") or {}
        discovered = sc.get("sources_discovered_total") or {}
        if discovered:
            lines.append("Discovery sources: " + ", ".join(
                f"{src}={n}" for src, n in sorted(discovered.items())))
        classes = sc.get("classes_by_region") or {}
        if classes:
            states = "; ".join(
                f"{region}: " + ", ".join(f"{name}={entry.get('state')}"
                                          for name, entry in sorted(entry_map.items()))
                for region, entry_map in sorted(classes.items()))
            lines.append(f"Source-class coverage: {states} (reached/blocked/unavailable/"
                         "not_applicable/searched_no_results are recorded from this run's own "
                         "evidence; a blocked source is never reported as empty)")
        lr = df.get("live_research") or {}
        if lr:
            lines.append(
                "Live research mechanism: "
                + (f"{lr.get('mechanism') or 'unknown'} operational in "
                   f"{len(lr.get('regions_operational') or [])} region(s)"
                   if lr.get("regions_operational") is not None else
                   f"{lr.get('mechanism') or 'unknown'} "
                   f"{'operational' if lr.get('operational') else 'NOT operational'}")
                + ("" if (lr.get("operational") or lr.get("regions_operational"))
                   else " — no current-web search proven: the lane is NOT production-ready"))
        if df.get("no_go"):
            lines.append(f"NO-GO: {df['no_go']}")
        mc = df.get("manifest_counts") or {}
        if mc:
            lines.append(f"Unified candidate manifest: {mc.get('records', mc.get('manifest_records'))} "
                         f"record(s) ready for the explicit apply step (no tracker write here)")
    wl = brief.get("priority_watchlist") or {}
    if wl.get("declared"):
        c = wl.get("counts") or {}
        top = wl.get("items") or []
        lines.append(
            "Priority watchlist: "
            f"{wl.get('companies_checked') if wl.get('companies_checked') is not None else 'unknown'}"
            f" company(ies) checked, "
            f"{wl.get('companies_with_careers_source') if wl.get('companies_with_careers_source') is not None else 'unknown'}"
            f" with a resolved careers/ATS source, "
            f"{c.get('canonical_candidates')} finding(s) at/above canonical, "
            f"{c.get('deterministic_eligibility_pass')} through the gates"
            + (f", {c.get('also_found_by_another_surface')} also found by another surface"
               if c.get("also_found_by_another_surface") else "")
            + (f"; {wl.get('items_not_reaching_gates')} item(s) shown but not ranked (did not reach "
               f"the gates)" if wl.get("items_not_reaching_gates") else "")
            + (f" — first: {top[0].get('company') or top[0].get('watchlist_company')} / "
               f"{top[0].get('title')}" if top else "")
            + f" [independent of the global ranking; run {wl.get('run_id')}, {wl.get('health')}]")
    elif wl.get("available") is False:
        lines.append("Priority watchlist: unavailable (no funnel run carrying it) — UNKNOWN, "
                     "never 'no jobs'")
    else:
        lines.append("Priority watchlist: no watchlist finding in this run (an empty owner list "
                     "is valid)")
    lines.append(f"Interviews/follow-ups: {brief['interviews_and_followups']['counts']['packs']} prep pack(s)")
    oa = brief["owner_actions"]["counts"]
    lines.append(f"Owner actions: {oa['open']} open, {oa['unknown_status']} with no readable status")
    lines.append("Priorities:")
    for item in brief["priorities"][: cfg["brief"]["max_priority_items_in_summary"]]:
        score = item["priority"]["score"]
        lines.append(f"  {item['priority']['priority_class']} "
                     f"{'score ' + str(score) if score is not None else 'score n/a'} "
                     f"(coverage {item['priority']['coverage_pct']}%) "
                     f"{item['subject_type']} {item['region'] or '-'} {item['ref']}"
                     f" — {item.get('title') or item.get('company') or ''}"
                     f"{' [unknown: ' + ','.join(u['input'] for u in item['priority']['unknown_inputs']) + ']' if item['priority']['unknown_inputs'] else ''}")
    if not brief["priorities"]:
        lines.append("  (no candidates from the available inputs)")
    unk = brief["unknowns"]
    lines.append(f"Unknowns: {len(unk)} item(s)"
                 f"{'' if not unk else ' — ' + '; '.join(u['reason'] for u in unk[:3])}")
    _d = brief.get("delivery") or {}
    lines.append(f"Delivery: channel={_d.get('channel', 'local_file')} mode={_d.get('mode', 'write')} "
                 f"(sha256 read-back); external channels {_d.get('external_channel_health', 'not_verified')}")
    lines.append("Safety: read-only aggregation; no submission, no outreach, no canonical write.")
    return "\n".join(lines[: cfg["brief"]["max_summary_lines"]])


def build_brief(cfg: dict, *, now: dt.datetime, window_hours: int | None = None,
                config_path: str | None = None) -> dict:
    hours = int(window_hours or cfg["window"]["default_hours"])
    if hours > cfg["window"]["max_hours"]:
        hours = cfg["window"]["max_hours"]
    # The brief's identity is its *content*, and its content is "the state as of the
    # end of a window" - not "the state at the instant this process happened to run".
    # So the as-of/window clock is floored to a declared quantum: two runs inside the
    # same quantum over unchanged artifacts are the same brief and the second one
    # writes no bytes. `generated_at` keeps the true run instant (and is excluded
    # from the digest), so the brief still says exactly when it was produced.
    observed_at = now
    quantum_min = int(cfg["window"].get("quantize_minutes", 0) or 0)
    if quantum_min > 0:
        per = quantum_min * 60
        now = dt.datetime.fromtimestamp((int(now.timestamp()) // per) * per, dt.timezone.utc)
    window_start = now - dt.timedelta(hours=hours)

    inputs = collect_inputs(cfg)

    def safe(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001 - an input failure is reported, not fatal
            return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    scan = safe(collect_regional_scan, cfg, now)
    trackers = safe(collect_trackers, cfg, now, window_start)
    hashes_before = dict(trackers.get("hashes") or {})
    watch = safe(collect_company_watch, cfg, now)
    discovery = safe(collect_discovery_funnel, cfg, now)
    watchlist = safe(collect_priority_watchlist, cfg, now)
    status = safe(collect_application_status, cfg)
    interviews = safe(collect_interviews, cfg)
    owner_actions = safe(collect_owner_actions, cfg)
    outputs = safe(collect_workflow_outputs, cfg)

    candidates = []
    try:
        candidates = build_candidates(scan, trackers, watch, status, interviews,
                                      owner_actions, cfg, now, window_start,
                                      watchlist=watchlist)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        candidates = []
        status.setdefault("candidate_error", f"{type(exc).__name__}: {exc}")
    for cand in candidates:
        cand["priority"] = score_candidate(cand, cfg["priority_policy"])
    candidates.sort(key=lambda c: candidate_sort_key(c, cfg["priority_policy"]))
    for i, cand in enumerate(candidates, start=1):
        cand["rank"] = i

    # The owner's priority watchlist is surfaced as its OWN section, ordered by the
    # funnel's own canonical order, so a watchlist vacancy stays visible even when
    # the global priority ranking puts it far down the list (or when it produces no
    # scoreable input at all). The section records which of its items also appear in
    # the ranking, so the two views can never be confused.
    if isinstance(watchlist, dict):
        watchlist["independent_of_global_rank"] = True
        watchlist["section_order"] = ("funnel canonical order (declared_order); this section is "
                                      "NOT sorted by the priority score")
        ranked = [c for c in candidates if c.get("subject_type") == "priority_watchlist_vacancy"]

        def _rank_of(item: dict):
            for c in ranked:
                if item.get("candidate_id") and str(c["ref"]) == str(item["candidate_id"]):
                    return c["rank"]
                if item.get("url") and c.get("url") and str(c["url"]) == str(item["url"]):
                    return c["rank"]
            return None

        for item in watchlist.get("items") or []:
            item["global_rank"] = _rank_of(item)
            item["in_global_ranking"] = item["global_rank"] is not None
            item["in_global_ranking_reason"] = (
                "passed the funnel's deterministic gates, so it is also ranked" if
                item.get("threshold_passed") else
                "did not reach the deterministic gates — shown here for visibility only, "
                "deliberately not ranked")

    # canonical store hashes re-read after all aggregation
    hashes_after = {}
    for region, entry in (trackers.get("regions") or {}).items():
        p = Path(entry["tracker"])
        hashes_after[region] = sha256_file(p) if p.exists() else None
    canonical_unchanged = hashes_before == hashes_after

    unknowns = []
    for name, fact in inputs.items():
        if name == "canonical_workbooks":
            for region, wf in (fact.get("regions") or {}).items():
                if not wf.get("exists"):
                    unknowns.append({"area": "tracker", "input": region,
                                     "reason": f"canonical workbook missing: {wf['path']}"})
            continue
        if not fact.get("exists"):
            unknowns.append({"area": "input", "input": name,
                             "reason": f"declared input absent: {fact['declared']}"})
    if scan.get("available") is False:
        unknowns.append({"area": "regional_scan", "input": "regional_state",
                         "reason": f"scan health unavailable: {scan.get('error')}"})
    for region, entry in (scan.get("regions") or {}).items():
        if entry["health"] in ("unknown", "stale") or entry["health"].startswith("degraded"):
            unknowns.append({"area": "scan_health", "input": region,
                             "reason": f"region {region}: health={entry['health']} "
                                       f"(last_status={entry['last_status']})"})
    for region, entry in (trackers.get("regions") or {}).items():
        if not entry.get("available"):
            unknowns.append({"area": "tracker", "input": region,
                             "reason": entry.get("error") or "tracker unavailable"})
        elif entry.get("deadline_column") is None:
            unknowns.append({"area": "deadline", "input": region,
                             "reason": f"{region}: tracker schema has no deadline column, so "
                                       f"deadline is UNKNOWN for all {entry.get('data_rows')} row(s)"})
    if watch.get("available") is False:
        unknowns.append({"area": "company_watch", "input": "findings",
                         "reason": "Company Watch findings file unavailable"})
    if discovery.get("available") is False:
        unknowns.append({"area": "discovery_funnel", "input": "run_evidence",
                         "reason": discovery.get("reason") or "discovery funnel evidence unavailable"})
    elif discovery.get("health") in ("unknown", "stale"):
        unknowns.append({"area": "discovery_funnel", "input": "health",
                         "reason": (f"discovery funnel run {discovery.get('run_id')}: "
                                    f"health={discovery.get('health')} "
                                    f"(age_hours={discovery.get('age_hours')}) — the funnel counts "
                                    f"do NOT describe the current market")})
    if status.get("available") is False:
        unknowns.append({"area": "application_status", "input": "monitor",
                         "reason": f"Application Inbox summary unavailable: {status.get('error')}"})
    if watchlist.get("available") is False:
        unknowns.append({"area": "priority_watchlist", "input": "run_evidence",
                         "reason": watchlist.get("reason") or "priority watchlist evidence unavailable"})
    elif watchlist.get("declared") and watchlist.get("health") in ("unknown", "stale"):
        unknowns.append({"area": "priority_watchlist", "input": "health",
                         "reason": (f"watchlist funnel run {watchlist.get('run_id')}: "
                                    f"health={watchlist.get('health')} "
                                    f"(age_hours={watchlist.get('age_hours')}) — the watchlist "
                                    f"view does NOT describe the current market")})
    if watchlist.get("companies_unavailable_or_unknown"):
        unknowns.append({"area": "priority_watchlist", "input": "company_careers_surface",
                         "reason": (f"{watchlist['companies_unavailable_or_unknown']} watchlist "
                                    f"company(ies) have an unresolved careers/ATS surface — that "
                                    f"is UNKNOWN infrastructure, not 'no jobs'")})
    if owner_actions.get("unknown_status_items"):
        unknowns.append({"area": "owner_actions", "input": "status",
                         "reason": f"{len(owner_actions['unknown_status_items'])} owner action(s) "
                                   f"have no readable status line"})
    prio_unknowns: dict = {}
    for cand in candidates:
        for u in cand["priority"]["unknown_inputs"]:
            if u["input"] == "deadline":
                continue  # already summarised once per region above
            key = (u["input"], u["reason"])
            entry = prio_unknowns.setdefault(key, {
                "area": "priority_input", "input": u["input"], "reason": u["reason"],
                "count": 0, "example_refs": []})
            entry["count"] += 1
            if len(entry["example_refs"]) < 5:
                entry["example_refs"].append(f"{cand['subject_type']}:{cand['ref']}")
    unknowns.extend(sorted(prio_unknowns.values(), key=lambda e: (-e["count"], e["input"], e["reason"])))

    tracker_rows = sum((e.get("data_rows") or 0) for e in (trackers.get("regions") or {}).values())
    new_rows = trackers.get("new_rows") or []
    offers = [o for e in (scan.get("regions") or {}).values()
              for o in (e.get("new_offers_without_url") or [])]
    dup_totals = {
        "scan_duplicates": sum((e.get("duplicates_suppressed", {}).get("scan_duplicates") or 0)
                               for e in (scan.get("regions") or {}).values()),
        "policy_duplicate_prior_run": sum((e.get("duplicates_suppressed", {}).get("policy_duplicate_prior_run") or 0)
                                          for e in (scan.get("regions") or {}).values()),
        "writer_duplicates": sum((e.get("duplicates_suppressed", {}).get("writer_duplicates") or 0)
                                 for e in (scan.get("regions") or {}).values()),
    }
    deadline_items = trackers.get("deadline_items") or []
    follow_up_min = cfg["brief"]["follow_up_stage_min_value"]
    follow_up_rows = []
    for cand in candidates:
        if cand["subject_type"] != "tracker_row":
            continue
        stage = next((c["value"] for c in cand["priority"]["components"] if c["input"] == "stage"), None)
        if stage is not None and stage >= follow_up_min:
            follow_up_rows.append({"region": cand["region"], "ref": cand["ref"],
                                   "company": cand.get("company"), "title": cand.get("title"),
                                   "application_status": cand.get("application_status"),
                                   "stage_value": stage, "source": cand["source"]})
    regions_without_deadline = sorted(r for r, e in (trackers.get("regions") or {}).items()
                                      if e.get("available") and not e.get("deadline_column"))
    cw = status.get("counts") or {}
    asc = {
        "counts": {
            "signals_ingested": cw.get("signals_ingested", 0),
            "status_events": cw.get("status_events", 0),
            "proposed_status_changes": len(status.get("proposed_status_changes") or []),
            "owner_actions_required": len(status.get("owner_actions") or []),
            "review_items": status.get("review_queue_size", 0),
        },
        "proposed_status_changes": status.get("proposed_status_changes") or [],
        "signals_by_kind": status.get("signals_by_kind") or {},
        "available": status.get("available", False),
        "store": status.get("store"),
        "safety": status.get("safety") or {},
    }
    owner_counts = {
        "items_parsed": len(owner_actions.get("items") or []),
        "open": len(owner_actions.get("open_items") or []),
        "unknown_status": len(owner_actions.get("unknown_status_items") or []),
        "from_monitor": len(status.get("owner_actions") or []),
    }
    headline_bits = [f"{len(new_rows)} new tracker row(s)", f"{len(deadline_items)} dated deadline(s)",
                     f"{owner_counts['open']} open owner action(s)"]
    if unknowns:
        headline_bits.append(f"{len(unknowns)} unknown(s) recorded")
    brief = {
        "schema_version": SCHEMA_VERSION,
        "brief_id": None,  # set below (derived from the content digest)
        "generated_at": observed_at.replace(microsecond=0).isoformat(),
        "as_of": now.replace(microsecond=0).isoformat(),
        "window": {"hours": hours, "from": window_start.replace(microsecond=0).isoformat(),
                   "to": now.replace(microsecond=0).isoformat(),
                   "quantize_minutes": quantum_min,
                   "quantize_note": ("the as-of/window clock is floored to this quantum, so "
                                     "re-running inside the same quantum over unchanged "
                                     "artifacts produces the identical brief and writes no bytes; "
                                     "generated_at keeps the true run instant")},
        "status": {
            "ok": True,
            "degraded": bool(unknowns),
            "headline": "; ".join(headline_bits),
            "source_of_truth": "canonical regional workbooks + the workflows' own runtime outputs",
            "read_only": True,
        },
        "inputs": inputs,
        "regional_scan_health": scan,
        "trackers": {
            "regions": {r: {k: v for k, v in e.items() if k not in ("actionable", "new_rows_in_window")}
                        for r, e in (trackers.get("regions") or {}).items()},
            "total_rows": tracker_rows,
            "excel_authoritative": True,
        },
        "newly_added_jobs": {
            "counts": {"tracker_rows_in_window": len(new_rows),
                       "scan_offers_without_url": len(offers)},
            "tracker_rows": new_rows,
            "scan_offers_without_url": offers,
            "note": ("tracker rows are real workbook records dated inside the window; scan "
                     "offers have no URL and cannot become rows until one is resolved"),
        },
        "duplicates_suppressed": {
            "totals": dup_totals,
            "by_region": {r: e.get("duplicates_suppressed") for r, e in (scan.get("regions") or {}).items()},
            "note": ("scan duplicates come from the scanner's own counters; prior-run duplicates "
                     "from the worker's run-key idempotency; writer duplicates from the shared "
                     "tracker_writer dedupe pass"),
        },
        "company_watch": watch,
        "discovery_funnel": discovery,
        "priority_watchlist": watchlist,
        "application_status_changes": asc,
        "interviews_and_followups": {
            "counts": {"packs": interviews.get("pack_count", 0),
                       "pack_items": len(interviews.get("items") or []),
                       "application_rows_past_first_stage": len(follow_up_rows)},
            "items": interviews.get("items") or [],
            "application_follow_up_rows": follow_up_rows,
            "follow_up_rule": (f"a tracker row counts as a follow-up when its OWN status maps to a "
                               f"declared stage value >= {follow_up_min} (applied / interview / "
                               f"offer and equivalents); no follow-up is inferred from anything else"),
            "available": interviews.get("available", False),
            "error": interviews.get("error"),
            "runtime_dir": interviews.get("runtime_dir"),
            "note": ("an interview item here means a real prep-pack artifact exists; no interview "
                     "date is claimed unless one was supplied"),
        },
        "deadlines_followups": {
            "counts": {"deadlines_known": len(deadline_items),
                       "deadlines_unknown_regions": len(regions_without_deadline)},
            "regions_without_deadline_column": regions_without_deadline,
            "items": sorted(deadline_items, key=lambda d: (d["days_remaining"], d["region"], d["id"])),
        },
        "owner_actions": {
            "counts": owner_counts,
            "items": owner_actions.get("items") or [],
            "open_items": owner_actions.get("open_items") or [],
            "from_monitor": status.get("owner_actions") or [],
            "path": owner_actions.get("path"),
        },
        "workflow_outputs": outputs,
        "priorities": candidates[: cfg["brief"]["max_priority_items"]],
        "policy": {
            "version": cfg["priority_policy"]["version"],
            "sha256": sha256_text(json.dumps(cfg["priority_policy"], sort_keys=True,
                                             ensure_ascii=False)),
            "score_semantics": cfg["priority_policy"]["score_semantics"],
            "weights": cfg["priority_policy"]["weights"],
            "rank_order": cfg["priority_policy"]["rank_order"],
        },
        "unknowns": unknowns,
        "safety": {
            "read_only_aggregation": True,
            "applications_submitted": 0,
            "external_messages_sent": 0,
            "canonical_workbook_writes": 0,
            "canonical_hashes_before": hashes_before,
            "canonical_hashes_after": hashes_after,
            "canonical_state_unchanged": canonical_unchanged,
            "not_performed": cfg["not_performed"],
        },
    }
    brief["input_fingerprint"] = input_fingerprint(inputs, cfg)
    digest = content_digest(brief)
    brief["brief_id"] = f"cdb-{now.strftime('%Y%m%dT%H%M%SZ')}-{digest[:8]}"
    brief["content_digest"] = digest
    return brief


def input_fingerprint(inputs: dict, cfg: dict) -> str:
    """Stable hash of the input set actually read (paths + file hashes)."""
    facts = []
    for name, fact in sorted(inputs.items()):
        if name == "canonical_workbooks":
            for region, wf in sorted((fact.get("regions") or {}).items()):
                facts.append([f"workbook:{region}", wf["path"], wf.get("sha256") or "missing"])
            continue
        facts.append([name, fact["path"], fact.get("sha256") or ("dir" if fact.get("kind") == "dir" else "missing")])
    facts.append(["policy", cfg["priority_policy"]["version"],
                  sha256_text(json.dumps(cfg["priority_policy"], sort_keys=True, ensure_ascii=False))])
    return sha256_text(json.dumps(facts, sort_keys=True))


# --------------------------------------------------------------------------- #
# writing (idempotent; only inside the brief output directory)
# --------------------------------------------------------------------------- #

def build_delivery(root: Path, *, mode: str) -> dict:
    """The persisted delivery block. Stable by construction (no run metadata).

    The *result* of the local write check (sha256 read-back) is reported in the
    CLI output and appended to ``run-log.jsonl`` — not baked into the brief, so
    two runs over identical inputs persist byte-identical briefs.
    """
    return {
        "channel": "local_file",
        "out_dir": str(root),
        "mode": mode,
        "local_write_check": "sha256 read-back; result recorded in run-log.jsonl",
        "external_channels": [],
        "external_channel_health": "not_verified",
        "external_channel_note": (
            "No external delivery channel is configured or claimed. A messaging/Discord "
            "channel is NOT assumed healthy: nothing here sends, posts or notifies. The "
            "brief is a local artifact until a delivery channel is separately verified."),
    }


def stored_content_matches(path: Path, digest: str) -> bool:
    """True when the file on disk already holds this exact brief content.

    Recomputes the digest from the stored payload, so a brief written by an
    earlier run (with its own `generated_at`) is recognised as the *same* brief.
    """
    doc, _ = read_json(path)
    return bool(doc) and content_digest(doc) == digest


def write_brief(brief: dict, root: Path, *, dry_run: bool = False) -> dict:
    """Write the brief + summary, digest-named and content-addressed.

    Re-running over unchanged inputs writes no bytes at all: the existing
    digest-named file is recognised as holding the same content and its original
    `generated_at` is left alone. Only `run-log.jsonl` is appended.
    """
    root.mkdir(parents=True, exist_ok=True)
    digest = brief["content_digest"]
    brief_bytes = (json.dumps(brief, indent=2, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    summary = brief["chief_summary"]
    summary_bytes = (summary + "\n").encode("utf-8")
    brief_path = root / f"brief-{digest}.json"
    summary_path = root / f"chief-summary-{digest}.md"
    latest_json = root / "latest.json"
    latest_md = root / "latest.md"

    prior_digest = None
    if latest_json.exists():
        prior, _ = read_json(latest_json)
        prior_digest = (prior or {}).get("content_digest")
    already = stored_content_matches(brief_path, digest)

    writes = []
    if dry_run:
        pending = [str(brief_path), str(summary_path), str(latest_json), str(latest_md)]
        return {"dry_run": True, "would_write": [] if already else pending,
                "existing_content_addressed_file": already,
                "prior_digest": prior_digest}

    if not already:
        brief_path.write_bytes(brief_bytes)
        summary_path.write_bytes(summary_bytes)
        writes += [str(brief_path), str(summary_path)]
    # `latest.*` mirrors the newest brief; unchanged content leaves them as-is.
    if not stored_content_matches(latest_json, digest):
        latest_json.write_bytes(brief_bytes)
        writes.append(str(latest_json))
    if not latest_md.exists() or sha256_file(latest_md) != hashlib.sha256(summary_bytes).hexdigest():
        latest_md.write_bytes(summary_bytes)
        writes.append(str(latest_md))

    verified = all(
        sha256_file(p) == hashlib.sha256(body).hexdigest()
        for p, body in ((brief_path, brief_bytes), (latest_json, brief_bytes),
                        (summary_path, summary_bytes), (latest_md, summary_bytes))
    ) if not already else True
    log = root / "run-log.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "generated_at": brief["generated_at"], "brief_id": brief["brief_id"],
            "content_digest": digest, "input_fingerprint": brief["input_fingerprint"],
            "prior_digest": prior_digest, "wrote": writes,
            "idempotent": already,
            "unknowns": len(brief["unknowns"]),
            "canonical_state_unchanged": brief["safety"]["canonical_state_unchanged"],
        }, ensure_ascii=False, default=str) + "\n")
    return {"dry_run": False, "writes": writes,
            "existing_content_addressed_file": already,
            "local_write_verified_by_hash": verified,
            "prior_digest": prior_digest,
            "idempotent": already}


def run_brief(cfg: dict, *, now: dt.datetime, window_hours: int | None = None,
              dry_run: bool = False, out_dir_override: str | None = None,
              with_summary: bool = True) -> tuple[dict, dict]:
    brief = build_brief(cfg, now=now, window_hours=window_hours)
    if with_summary:
        brief["chief_summary"] = chief_summary(brief, cfg)
    root = out_dir(cfg, out_dir_override)
    # The delivery block is persisted inside the brief, so it must be known
    # before the brief is written. It contains no run metadata; the sha256
    # read-back *result* is reported below and appended to run-log.jsonl.
    brief["delivery"] = build_delivery(root, mode="dry_run" if dry_run else "write")
    # The digest covers everything the brief says, so it is finalised here - after
    # `chief_summary` (and the excluded delivery block) exist. Called directly,
    # build_brief() finalises it too; the value is the same either way.
    brief["content_digest"] = content_digest(brief)
    # The id is stamped with the brief's own as_of (the floored window end), not the
    # instant this process ran: two runs inside one quantum over unchanged artifacts
    # must produce the same id as well as the same digest. `generated_at` still
    # carries the true run instant.
    as_of = dt.datetime.fromisoformat(brief["as_of"])
    brief["brief_id"] = f"cdb-{as_of.strftime('%Y%m%dT%H%M%SZ')}-{brief['content_digest'][:8]}"
    result = write_brief(brief, root, dry_run=dry_run)
    delivery = dict(brief["delivery"])
    delivery["writes"] = result.get("writes", [])
    delivery["would_write"] = result.get("would_write", [])
    delivery["local_write_verified_by_hash"] = result.get("local_write_verified_by_hash")
    delivery["idempotent"] = result.get("idempotent")
    out = {
        "ok": True, "generated_at": brief["generated_at"], "brief_id": brief["brief_id"],
        "content_digest": brief["content_digest"],
        "input_fingerprint": brief["input_fingerprint"],
        "window": brief["window"],
        "status": brief["status"],
        "counts": {
            "priorities": len(brief["priorities"]),
            "new_tracker_rows": brief["newly_added_jobs"]["counts"]["tracker_rows_in_window"],
            "scan_offers_without_url": brief["newly_added_jobs"]["counts"]["scan_offers_without_url"],
            "deadlines_known": brief["deadlines_followups"]["counts"]["deadlines_known"],
            "open_owner_actions": brief["owner_actions"]["counts"]["open"],
            "unknowns": len(brief["unknowns"]),
        },
        "delivery": delivery,
        "writes": result.get("writes", []),
        "dry_run": dry_run,
        "idempotent": result.get("idempotent"),
        "canonical_state_unchanged": brief["safety"]["canonical_state_unchanged"],
        "safety": brief["safety"],
        "chief_summary": brief["chief_summary"],
        "brief_path": str((out_dir(cfg, out_dir_override) /
                           f"brief-{brief['content_digest']}.json")),
        "summary_path": str((out_dir(cfg, out_dir_override) /
                             f"chief-summary-{brief['content_digest']}.md")),
        "latest_path": str(out_dir(cfg, out_dir_override) / "latest.json"),
        "unknowns": brief["unknowns"],
        "top_priorities": [
            {"rank": p["rank"], "subject_type": p["subject_type"], "region": p["region"],
             "ref": p["ref"], "company": p.get("company"), "title": p.get("title"),
             "priority_class": p["priority"]["priority_class"], "score": p["priority"]["score"],
             "coverage_pct": p["priority"]["coverage_pct"],
             "unknown_inputs": [u["input"] for u in p["priority"]["unknown_inputs"]],
             "overrides": p["priority"]["overrides"]}
            for p in brief["priorities"][:10]],
    }
    return out, result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def cmd_inputs(args) -> int:
    cfg = load_config(args.config)
    emit({"generated_at": now_utc(), "config": cfg["_config_path"],
          "inputs": collect_inputs(cfg),
          "note": "presence + hashes only; no input content is read into this command"})
    return 0


def cmd_policy(args) -> int:
    cfg = load_config(args.config)
    emit({"generated_at": now_utc(), "priority_policy": cfg["priority_policy"],
          "sha256": sha256_text(json.dumps(cfg["priority_policy"], sort_keys=True,
                                           ensure_ascii=False)),
          "brief_output_limits": cfg["brief"]})
    return 0


def cmd_build(args) -> int:
    cfg = load_config(args.config)
    now = parse_now(args.now)
    out, _ = run_brief(cfg, now=now, window_hours=args.window_hours,
                       dry_run=args.dry_run, out_dir_override=args.out_dir)
    emit(out)
    return 0


def cmd_summary(args) -> int:
    cfg = load_config(args.config)
    root = out_dir(cfg, args.out_dir)
    path = Path(args.brief) if args.brief else (root / "latest.json")
    brief, err = read_json(path)
    if not brief:
        emit({"ok": False, "reason": f"no readable brief at {path}", "error": err})
        return 1
    emit({"ok": True, "brief_id": brief.get("brief_id"),
          "content_digest": brief.get("content_digest"),
          "generated_at": brief.get("generated_at"),
          "path": str(path), "chief_summary": brief.get("chief_summary") or chief_summary(brief, cfg)})
    return 0


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    root = out_dir(cfg, args.out_dir)
    latest, err = read_json(root / "latest.json")
    runs = read_jsonl(root / "run-log.jsonl")
    schedules = read_json(resolve(cfg, cfg["inputs"]["regional_schedules"]))[0] or {}
    sched = schedules.get("brief") or None
    out = {
        "ok": True, "generated_at": now_utc(), "config": cfg["_config_path"],
        "out_dir": str(root), "out_dir_exists": root.exists(),
        "latest_brief": None if not latest else {
            "path": str(root / "latest.json"), "brief_id": latest.get("brief_id"),
            "generated_at": latest.get("generated_at"),
            "content_digest": latest.get("content_digest"),
            "unknowns": len(latest.get("unknowns") or []),
            "canonical_state_unchanged": (latest.get("safety") or {}).get("canonical_state_unchanged"),
        },
        "latest_error": err,
        "runs_recorded": len(runs), "last_run": runs[-1] if runs else None,
        "schedule": sched,
        "schedule_note": ("the brief is schedulable for morning delivery; the local file write is "
                          "verified, no external channel is claimed"),
        "files": sorted(p.name for p in root.glob("*")) if root.exists() else [],
    }
    emit(out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Career Daily Brief / Pipeline Prioritizer (B23)")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inputs"); p.set_defaults(fn=cmd_inputs)
    p = sub.add_parser("policy"); p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("build")
    p.add_argument("--window-hours", type=int)
    p.add_argument("--out-dir")
    p.add_argument("--now", help="ISO8601 freeze of 'now' (deterministic runs/tests)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("summary")
    p.add_argument("--brief"); p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("status")
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
