#!/usr/bin/env python3
"""Executive Brain E1 + E2 — classification, immutable floors, structural route gate,
Resource Governor telemetry, Daily Resource Brief.

E1 commands: init, classify, decompose, freeze, route, override, audit,
backup, restore, summary.
E2 commands: telemetry, brief, record-request, gov-status, gov-verify, gov-init.
All historical tables are append-only (DB triggers).
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# E2 imports (governor modules)
import governor
import adapters

EB_DIR = Path(os.environ.get("EB_HOME", Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "exec-brain"))
DB_PATH = EB_DIR / "exec_brain.db"
CHAIN_HEAD_PATH = EB_DIR / "chain-head.json"
BACKUP_DIR = EB_DIR / "backups"
SCHEMA_VERSION = 1

TASK_TYPES = {"code", "review", "research", "analysis", "writing", "data-processing",
              "ops", "monitoring", "decision-support", "extraction", "summarization",
              "verification", "other"}
ROLES = {"scout", "builder", "architect", "researcher", "critic", "classifier",
         "writer", "vision", "compressor"}
VERIF = {"V0", "V1", "V2", "V3"}
RISK = {"R0", "R1", "R2", "R3"}
PRIV = {"P0", "P1", "P2", "P3"}
EGRESS = {"LOCAL_ONLY", "APPROVED_PROVIDERS_ONLY", "REDACT_BEFORE_EXTERNAL",
          "EXTERNAL_ALLOWED", "OWNER_APPROVAL_REQUIRED"}
CONF = {"high", "medium", "low"}
VERIF_RANK = {"V0": 0, "V1": 1, "V2": 2, "V3": 3}
STRATEGIES = {"1", "2", "3", "4", "5", "6", "7"}

DDL = """
CREATE TABLE IF NOT EXISTS task_record (
  task_id        TEXT PRIMARY KEY,
  supersedes_task_id TEXT REFERENCES task_record(task_id),
  reclassification_reason TEXT,
  created_at     TEXT NOT NULL,
  request_text   TEXT NOT NULL,
  source_system  TEXT,
  source_event_id TEXT,
  task_type      TEXT NOT NULL,
  capability_roles TEXT NOT NULL,
  reasoning_depth INTEGER NOT NULL,
  verification_level TEXT NOT NULL,
  risk_class     TEXT NOT NULL,
  privacy_class  TEXT NOT NULL,
  egress_policy  TEXT NOT NULL,
  deadline       TEXT,
  idempotent     INTEGER NOT NULL,
  context_size   TEXT NOT NULL,
  known_workflows TEXT,
  classification_confidence TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(source_system, source_event_id)
);
CREATE TABLE IF NOT EXISTS subtask_record (
  subtask_id     TEXT PRIMARY KEY,
  task_id        TEXT NOT NULL REFERENCES task_record(task_id),
  parent_subtask_id TEXT,
  title          TEXT NOT NULL,
  order_index    INTEGER NOT NULL,
  legality_note  TEXT,
  created_at     TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS quality_floor (
  floor_id       TEXT PRIMARY KEY,
  task_id        TEXT NOT NULL REFERENCES task_record(task_id),
  subtask_id     TEXT REFERENCES subtask_record(subtask_id),
  classification_key TEXT NOT NULL UNIQUE,
  frozen_at      TEXT NOT NULL,
  seq            INTEGER NOT NULL UNIQUE,
  min_reasoning_depth INTEGER NOT NULL,
  required_roles TEXT NOT NULL,
  min_verification TEXT NOT NULL,
  risk_constraints TEXT,
  egress_constraints TEXT,
  strategy_constraints TEXT,
  record_sha256  TEXT NOT NULL,
  prev_sha256    TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS strategy_decision (
  decision_id    TEXT PRIMARY KEY,
  floor_id       TEXT NOT NULL REFERENCES quality_floor(floor_id),
  decided_at     TEXT NOT NULL,
  strategy       TEXT NOT NULL,
  chosen_class   TEXT,
  chosen_worker  TEXT,
  proposed_reasoning_depth INTEGER NOT NULL,
  proposed_verification   TEXT NOT NULL,
  execution_scope TEXT NOT NULL,
  proposed_egress TEXT NOT NULL,
  claimed_roles  TEXT NOT NULL,
  qualification_evidence TEXT NOT NULL,
  risk_approval  TEXT,
  ranked_candidates TEXT,
  gate_result    TEXT NOT NULL,
  gate_reasons   TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS override_record (
  override_id    TEXT PRIMARY KEY,
  floor_id       TEXT NOT NULL REFERENCES quality_floor(floor_id),
  overridden_at  TEXT NOT NULL,
  original_floor_summary TEXT NOT NULL,
  route_fingerprint TEXT NOT NULL,
  actual_route   TEXT NOT NULL,
  warning_text   TEXT NOT NULL,
  owner_confirmation TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS audit_log (
  audit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts             TEXT NOT NULL,
  seq            INTEGER NOT NULL UNIQUE,
  event          TEXT NOT NULL,
  task_id        TEXT, floor_id TEXT, decision_id TEXT,
  detail         TEXT NOT NULL,
  record_sha256  TEXT NOT NULL,
  prev_sha256    TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TRIGGER IF NOT EXISTS trg_task_record_no_update BEFORE UPDATE ON task_record
  BEGIN SELECT RAISE(ABORT, 'task_record is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_task_record_no_delete BEFORE DELETE ON task_record
  BEGIN SELECT RAISE(ABORT, 'task_record is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_subtask_no_update BEFORE UPDATE ON subtask_record
  BEGIN SELECT RAISE(ABORT, 'subtask_record is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_subtask_no_delete BEFORE DELETE ON subtask_record
  BEGIN SELECT RAISE(ABORT, 'subtask_record is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_quality_floor_no_update BEFORE UPDATE ON quality_floor
  BEGIN SELECT RAISE(ABORT, 'quality_floor is immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_quality_floor_no_delete BEFORE DELETE ON quality_floor
  BEGIN SELECT RAISE(ABORT, 'quality_floor is immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_strategy_no_update BEFORE UPDATE ON strategy_decision
  BEGIN SELECT RAISE(ABORT, 'strategy_decision is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_strategy_no_delete BEFORE DELETE ON strategy_decision
  BEGIN SELECT RAISE(ABORT, 'strategy_decision is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_override_no_update BEFORE UPDATE ON override_record
  BEGIN SELECT RAISE(ABORT, 'override_record is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_override_no_delete BEFORE DELETE ON override_record
  BEGIN SELECT RAISE(ABORT, 'override_record is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_no_update BEFORE UPDATE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete BEFORE DELETE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None):
    p = Path(path) if path else DB_PATH
    if not p.exists():
        raise SystemExit(f"eb: database not found at {p} (run: eb init)")
    con = sqlite3.connect(str(p), timeout=5)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def floor_hash(row_dict):
    canon = json.dumps({k: row_dict[k] for k in
                        ["floor_id", "task_id", "subtask_id", "classification_key",
                         "frozen_at", "seq", "min_reasoning_depth", "required_roles",
                         "min_verification", "risk_constraints", "egress_constraints",
                         "strategy_constraints"]},
                       sort_keys=True, ensure_ascii=False)
    return sha256(canon)


def route_fingerprint(strategy, chosen_class, chosen_worker, reasoning, verification,
                      scope, egress, roles):
    canon = json.dumps({
        "strategy": strategy, "chosen_class": chosen_class or "",
        "chosen_worker": chosen_worker or "", "reasoning": int(reasoning),
        "verification": verification, "scope": scope, "egress": egress,
        "roles": sorted(roles or [])},
        sort_keys=True, ensure_ascii=False)
    return sha256(canon)


def audit(con, event, detail, task_id=None, floor_id=None, decision_id=None, commit=True):
    cur = con.execute("SELECT COALESCE(MAX(seq),0) FROM audit_log")
    seq = cur.fetchone()[0] + 1
    prev = con.execute("SELECT record_sha256 FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    ts = now()
    d = {"ts": ts, "seq": seq, "event": event, "task_id": task_id,
         "floor_id": floor_id, "decision_id": decision_id, "detail": detail}
    h = sha256(json.dumps(d, sort_keys=True, ensure_ascii=False))
    con.execute("INSERT INTO audit_log (ts,seq,event,task_id,floor_id,decision_id,detail,"
                "record_sha256,prev_sha256,schema_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, seq, event, task_id, floor_id, decision_id, detail, h,
                 prev[0] if prev else None, SCHEMA_VERSION))
    if commit:
        con.commit()
    return seq


def fail(msg, event=None, con=None, **audit_kw):
    if con is not None and event:
        try:
            audit(con, event, msg, commit=True, **audit_kw)
        except Exception:
            pass
    print(f"eb: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_roles(s):
    roles = [r.strip() for r in s.split(",") if r.strip()]
    bad = [r for r in roles if r not in ROLES]
    if bad:
        raise SystemExit(f"eb: invalid capability roles: {bad}")
    return roles


# ---------- commands ----------

def cmd_init(args):
    EB_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.executescript(DDL)
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()
    print(f"initialized {DB_PATH}")


def cmd_classify(args):
    con = connect()
    if args.task_type not in TASK_TYPES:
        fail(f"invalid task_type {args.task_type!r}", "reject", con)
    if args.verification_level not in VERIF or args.risk_class not in RISK \
       or args.privacy_class not in PRIV or args.egress_policy not in EGRESS \
       or args.classification_confidence not in CONF:
        fail("invalid enum value", "reject", con)
    if args.reasoning_depth not in range(5):
        fail("reasoning_depth must be 0..4", "reject", con)
    roles = parse_roles(args.roles)
    if args.supersedes and not args.reason:
        fail("reclassification_reason required when supersedes_task_id set", "reject", con)
    # idempotency: same source identity returns existing record
    if args.source_event_id:
        row = con.execute(
            "SELECT task_id FROM task_record WHERE source_system=? AND source_event_id=?",
            (args.source_system, args.source_event_id)).fetchone()
        if row:
            print(f"existing:{row[0]}")
            audit(con, "classify", f"idempotent reuse for {args.source_system}:{args.source_event_id}",
                  task_id=row[0])
            return
    task_id = f"eb-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"
    try:
        con.execute(
            "INSERT INTO task_record (task_id,supersedes_task_id,reclassification_reason,"
            "created_at,request_text,source_system,source_event_id,task_type,capability_roles,"
            "reasoning_depth,verification_level,risk_class,privacy_class,egress_policy,"
            "deadline,idempotent,context_size,known_workflows,classification_confidence,"
            "schema_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, args.supersedes, args.reason, now(), args.request_text,
             args.source_system, args.source_event_id, args.task_type,
             json.dumps(roles), args.reasoning_depth, args.verification_level,
             args.risk_class, args.privacy_class, args.egress_policy, args.deadline,
             1 if args.idempotent else 0, args.context_size,
             json.dumps(args.known_workflows.split(",")) if args.known_workflows else None,
             args.classification_confidence, SCHEMA_VERSION))
        con.commit()
    except sqlite3.IntegrityError as e:
        fail(f"classify rejected: {e}", "reject", con)
    audit(con, "classify", f"task {task_id} type={args.task_type} conf={args.classification_confidence}",
          task_id=task_id)
    print(task_id)


def cmd_decompose(args):
    con = connect()
    if not con.execute("SELECT 1 FROM task_record WHERE task_id=?", (args.task_id,)).fetchone():
        fail("task not found (classify first)", "reject", con)
    sub_id = f"st-{uuid.uuid4().hex[:8]}"
    con.execute("INSERT INTO subtask_record (subtask_id,task_id,parent_subtask_id,title,"
                "order_index,legality_note,created_at,schema_version) VALUES (?,?,?,?,?,?,?,?)",
                (sub_id, args.task_id, args.parent, args.title, args.order_index,
                 args.legality_note, now(), SCHEMA_VERSION))
    con.commit()
    audit(con, "decompose", f"subtask {sub_id} added to {args.task_id}", task_id=args.task_id)
    print(sub_id)


def cmd_freeze(args):
    con = connect()
    if not con.execute("SELECT 1 FROM task_record WHERE task_id=?", (args.task_id,)).fetchone():
        fail("task not found", "reject", con)
    if args.subtask_id and not con.execute(
            "SELECT 1 FROM subtask_record WHERE subtask_id=?", (args.subtask_id,)).fetchone():
        fail("subtask not found", "reject", con)
    ckey = f"subtask:{args.subtask_id}" if args.subtask_id else f"task:{args.task_id}"
    if con.execute("SELECT 1 FROM quality_floor WHERE classification_key=?", (ckey,)).fetchone():
        fail(f"floor already exists for {ckey} — reclassify (new lineage) instead",
             "reject", con, task_id=args.task_id)
    roles = parse_roles(args.roles)
    cur = con.execute("SELECT COALESCE(MAX(seq),0) FROM quality_floor")
    seq = cur.fetchone()[0] + 1
    prev = con.execute("SELECT record_sha256 FROM quality_floor ORDER BY seq DESC LIMIT 1").fetchone()
    floor_id = f"fl-{uuid.uuid4().hex[:8]}"
    row = {"floor_id": floor_id, "task_id": args.task_id, "subtask_id": args.subtask_id,
           "classification_key": ckey, "frozen_at": now(), "seq": seq,
           "min_reasoning_depth": args.min_reasoning_depth, "required_roles": json.dumps(roles),
           "min_verification": args.min_verification, "risk_constraints": args.risk_constraints,
           "egress_constraints": args.egress_constraints, "strategy_constraints": args.strategy_constraints}
    h = floor_hash(row)
    try:
        con.execute("INSERT INTO quality_floor (floor_id,task_id,subtask_id,classification_key,"
                    "frozen_at,seq,min_reasoning_depth,required_roles,min_verification,"
                    "risk_constraints,egress_constraints,strategy_constraints,record_sha256,"
                    "prev_sha256,schema_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (floor_id, args.task_id, args.subtask_id, ckey, row["frozen_at"], seq,
                     args.min_reasoning_depth, row["required_roles"], args.min_verification,
                     args.risk_constraints, args.egress_constraints, args.strategy_constraints,
                     h, prev[0] if prev else None, SCHEMA_VERSION))
        con.commit()
    except sqlite3.IntegrityError as e:
        fail(f"freeze rejected: {e}", "reject", con, task_id=args.task_id)
    audit(con, "freeze", f"floor {floor_id} frozen for {ckey} seq={seq}",
          task_id=args.task_id, floor_id=floor_id)
    print(floor_id)


def cmd_override(args):
    con = connect()
    fl = con.execute("SELECT floor_id,task_id,min_reasoning_depth,min_verification,"
                     "egress_constraints,risk_constraints,strategy_constraints,required_roles "
                     "FROM quality_floor WHERE floor_id=?", (args.floor_id,)).fetchone()
    if not fl:
        fail("floor not found", "reject", con)
    if not args.warning.strip() or not args.confirmation.strip():
        fail("override requires non-empty warning and owner confirmation", "reject", con,
             floor_id=args.floor_id)
    roles = parse_roles(args.roles)
    fp = route_fingerprint(args.strategy, args.chosen_class, args.chosen_worker,
                           args.reasoning, args.verification, args.scope, args.egress, roles)
    oid = f"ov-{uuid.uuid4().hex[:8]}"
    summary = (f"min_reasoning={fl[2]} min_verification={fl[3]} "
               f"egress={fl[4]} risk={fl[5]} strategy={fl[6]} roles={fl[7]}")
    con.execute("INSERT INTO override_record (override_id,floor_id,overridden_at,"
                "original_floor_summary,route_fingerprint,actual_route,warning_text,"
                "owner_confirmation,schema_version) VALUES (?,?,?,?,?,?,?,?,?)",
                (oid, args.floor_id, now(), summary, fp, args.route_description,
                 args.warning, args.confirmation, SCHEMA_VERSION))
    con.commit()
    audit(con, "override", f"override {oid} on {args.floor_id} fp={fp[:12]}",
          floor_id=args.floor_id)
    print(oid)


def cmd_route(args):
    con = connect()
    fl = con.execute("SELECT qf.floor_id,qf.task_id,tr.classification_confidence,"
                     "qf.min_reasoning_depth,qf.min_verification,qf.egress_constraints,"
                     "qf.risk_constraints,qf.strategy_constraints,qf.required_roles "
                     "FROM quality_floor qf JOIN task_record tr ON tr.task_id=qf.task_id "
                     "WHERE qf.floor_id=?", (args.floor_id,)).fetchone()
    if not fl:
        fail("FLOOR REQUIRED BEFORE ROUTING (floor not found)", "reject", con)
    floor_id, task_id, conf, min_rd, min_v, egr, risk_c, strat_c, req_roles = fl
    if conf == "low" and not args.override_id:
        fail("classification_confidence is low — reclassify or owner override required",
             "reject", con, task_id=task_id, floor_id=floor_id)
    roles = parse_roles(args.roles)
    reasons = []
    if args.reasoning < min_rd:
        reasons.append(f"reasoning {args.reasoning} < floor {min_rd}")
    if VERIF_RANK[args.verification] < VERIF_RANK[min_v]:
        reasons.append(f"verification {args.verification} below floor {min_v}")
    if (egr == "LOCAL_ONLY" or args_egress_local_only(egr)) and args.scope == "external":
        reasons.append(f"LOCAL_ONLY egress constraint violated by external scope")
    if strat_c and args.strategy not in [s.strip() for s in strat_c.split(",")]:
        reasons.append(f"strategy {args.strategy} violates strategy_constraints")
    needed = set(json.loads(req_roles))
    missing = needed - set(roles)
    if missing:
        reasons.append(f"missing required roles: {sorted(missing)}")
    needs_approval = risk_c and "owner" in risk_c.lower() and "approval" in risk_c.lower()
    if needs_approval and not (args.risk_approval or args.override_id):
        reasons.append("floor requires owner approval; none provided")

    gate = "accept"
    if reasons:
        if args.override_id:
            ov = con.execute("SELECT route_fingerprint FROM override_record "
                             "WHERE override_id=? AND floor_id=?",
                             (args.override_id, floor_id)).fetchone()
            fp = route_fingerprint(args.strategy, args.chosen_class, args.chosen_worker,
                                   args.reasoning, args.verification, args.scope,
                                   args.egress, roles)
            if ov and ov[0] == fp:
                gate = "accept"
                reasons = [f"below-floor route accepted via override {args.override_id}"]
            else:
                fail("override does not authorize THIS route (fingerprint mismatch) — "
                     "new owner override required", "reject", con,
                     task_id=task_id, floor_id=floor_id)
        else:
            fail("; ".join(reasons), "reject", con, task_id=task_id, floor_id=floor_id)
    did = f"sd-{uuid.uuid4().hex[:8]}"
    con.execute("INSERT INTO strategy_decision (decision_id,floor_id,decided_at,strategy,"
                "chosen_class,chosen_worker,proposed_reasoning_depth,proposed_verification,"
                "execution_scope,proposed_egress,claimed_roles,qualification_evidence,"
                "risk_approval,ranked_candidates,gate_result,gate_reasons,schema_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (did, floor_id, now(), args.strategy, args.chosen_class, args.chosen_worker,
                 args.reasoning, args.verification, args.scope, args.egress,
                 json.dumps(roles), args.qualification_evidence, args.risk_approval,
                 args.ranked_candidates, gate, "; ".join(reasons), SCHEMA_VERSION))
    con.commit()
    audit(con, "route", f"decision {did} gate={gate} strategy={args.strategy}",
          task_id=task_id, floor_id=floor_id, decision_id=did)
    print(f"{did} gate={gate}")


def args_egress_local_only(egr):
    return bool(egr) and "LOCAL_ONLY" in egr


def cmd_audit(args):
    con = connect()
    ok = True
    ic = con.execute("PRAGMA integrity_check").fetchone()[0]
    if ic != "ok":
        print(f"integrity_check: {ic}")
        ok = False
    else:
        print("integrity_check: ok")
    for table in ("quality_floor", "audit_log"):
        prev = None
        n = 0
        for row in con.execute(f"SELECT seq, record_sha256, prev_sha256 FROM {table} ORDER BY seq"):
            n += 1
            if row[2] != prev:
                print(f"{table}: chain break at seq={row[0]} (prev mismatch)")
                ok = False
            prev = row[1]
        print(f"{table}: {n} rows, chain {'ok' if ok else 'BROKEN'}")
    # head anchor check
    if CHAIN_HEAD_PATH.exists():
        head = json.loads(CHAIN_HEAD_PATH.read_text(encoding="utf-8"))
        for table in ("quality_floor", "audit_log"):
            row = con.execute(f"SELECT seq, record_sha256 FROM {table} ORDER BY seq DESC LIMIT 1").fetchone()
            anchor = head.get(table)
            if not anchor:
                continue
            if row is None:
                # anchor exists but table is empty: rows were deleted
                print(f"{table}: head anchor MISMATCH — rows deleted behind anchor")
                ok = False
                continue
            if (row[0], row[1]) != tuple(anchor):
                # DB may simply have grown since anchor: anchor must be a PREFIX
                arow = con.execute(f"SELECT record_sha256 FROM {table} WHERE seq=?",
                                   (anchor[0],)).fetchone()
                if not arow or arow[0] != anchor[1]:
                    print(f"{table}: head anchor MISMATCH — tail tampering suspected")
                    ok = False
    if ok and args.verify:
        heads = {}
        for table in ("quality_floor", "audit_log"):
            row = con.execute(f"SELECT seq, record_sha256 FROM {table} ORDER BY seq DESC LIMIT 1").fetchone()
            heads[table] = list(row) if row else None
        CHAIN_HEAD_PATH.write_text(json.dumps(heads, indent=1), encoding="utf-8")
        print(f"chain-head anchor written to {CHAIN_HEAD_PATH}")
    print("verify:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def cmd_backup(args):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_dir = BACKUP_DIR / ts
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "exec_brain.db"
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    if CHAIN_HEAD_PATH.exists():
        (dest_dir / "chain-head.json").write_text(
            CHAIN_HEAD_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    # prune: keep newest 10
    backups = sorted(BACKUP_DIR.iterdir())
    for old in backups[:-10]:
        for f in old.iterdir():
            f.unlink()
        old.rmdir()
    print(f"backup: {dest}")


def cmd_restore(args):
    src_dir = Path(args.backup_dir)
    src_db = src_dir / "exec_brain.db"
    if not src_db.exists():
        fail(f"no exec_brain.db in {src_dir}")
    # verify backup integrity before touching live db
    con = sqlite3.connect(str(src_db))
    ic = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    if ic != "ok":
        fail(f"backup integrity_check failed: {ic}")
    dest = DB_PATH.with_suffix(".db.restoring")
    dest.write_bytes(src_db.read_bytes())
    # sanity: open restored copy and run chain verify logic quickly
    con = sqlite3.connect(str(dest))
    for table in ("quality_floor", "audit_log"):
        prev = None
        for row in con.execute(f"SELECT seq, record_sha256, prev_sha256 FROM {table} ORDER BY seq"):
            if row[2] != prev:
                con.close()
                dest.unlink()
                fail(f"restore aborted: {table} chain broken in backup")
            prev = row[1]
    con.close()
    DB_PATH.unlink()
    dest.rename(DB_PATH)
    print(f"restored {src_db} -> {DB_PATH}")


def cmd_summary(args):
    con = connect()
    out = {"generated_at": now(), "schema_version": SCHEMA_VERSION,
           "tasks": [], "floors": [], "decisions": [], "overrides": []}
    for r in con.execute("SELECT task_id,task_type,reasoning_depth,verification_level,"
                         "risk_class,privacy_class,classification_confidence,created_at "
                         "FROM task_record ORDER BY created_at"):
        out["tasks"].append(dict(zip(["task_id", "task_type", "reasoning_depth",
                                      "verification_level", "risk_class", "privacy_class",
                                      "classification_confidence", "created_at"], r)))
    for r in con.execute("SELECT floor_id,classification_key,min_reasoning_depth,"
                         "min_verification,frozen_at FROM quality_floor ORDER BY seq"):
        out["floors"].append(dict(zip(["floor_id", "classification_key",
                                       "min_reasoning_depth", "min_verification",
                                       "frozen_at"], r)))
    for r in con.execute("SELECT decision_id,floor_id,strategy,gate_result,decided_at "
                         "FROM strategy_decision ORDER BY decided_at"):
        out["decisions"].append(dict(zip(["decision_id", "floor_id", "strategy",
                                          "gate_result", "decided_at"], r)))
    for r in con.execute("SELECT override_id,floor_id,overridden_at FROM override_record "
                         "ORDER BY overridden_at"):
        out["overrides"].append(dict(zip(["override_id", "floor_id", "overridden_at"], r)))
    # chain head (non-sensitive) included per plan
    for table in ("quality_floor", "audit_log"):
        row = con.execute(f"SELECT seq, record_sha256 FROM {table} ORDER BY seq DESC LIMIT 1").fetchone()
        out[f"chain_head_{table}"] = list(row) if row else None
    print(json.dumps(out, indent=1, ensure_ascii=False))


# ─── E2 Governor commands ─────────────────────────────────────────

def cmd_gov_init(args):
    """Initialize governor.db."""
    db_path = governor.init_db()
    print(f"governor: initialized {db_path}")


def cmd_telemetry(args):
    """Run telemetry poll for all providers."""
    con = governor.connect_gov()
    results = adapters.probe_all()
    snapshots_written = 0
    errors = []
    
    for snapshot in results:
        try:
            governor.write_snapshot(con, snapshot)
            snapshots_written += 1
        except Exception as e:
            errors.append(f"Failed to write snapshot for {snapshot['provider']}: {e}")
    
    if errors:
        print(f"telemetry: partial failure — {len(errors)} errors", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"telemetry: {snapshots_written} snapshots written")


def cmd_brief(args):
    """Generate Daily Resource Brief."""
    con = governor.connect_gov()
    date_str = args.date if hasattr(args, 'date') and args.date else None
    brief = governor.generate_brief(con, date_str)
    print(brief)


def cmd_record_request(args):
    """Record an observed API request."""
    con = governor.connect_gov()
    rid = governor.record_request(
        con,
        provider=args.provider,
        model=args.model,
        input_tokens=args.input_tokens,
        output_tokens=args.output_tokens,
        monetary_cost=args.cost,
        status=args.status,
        error_code=args.error_code,
        latency_ms=args.latency_ms
    )
    print(rid)


def cmd_gov_status(args):
    """Show governor.db status."""
    con = governor.connect_gov()
    snapshots = con.execute("SELECT COUNT(*) FROM provider_snapshot").fetchone()[0]
    dimensions = con.execute("SELECT COUNT(*) FROM capacity_dimension").fetchone()[0]
    requests = con.execute("SELECT COUNT(*) FROM observed_request").fetchone()[0]
    briefs = con.execute("SELECT COUNT(*) FROM daily_brief_log").fetchone()[0]
    aggregates = con.execute("SELECT COUNT(*) FROM daily_aggregate").fetchone()[0]
    
    print("Governor Status:")
    print(f"  provider_snapshots: {snapshots}")
    print(f"  capacity_dimensions: {dimensions}")
    print(f"  observed_requests: {requests}")
    print(f"  daily_briefs: {briefs}")
    print(f"  daily_aggregates: {aggregates}")


def cmd_gov_verify(args):
    """Verify governor.db integrity and chain."""
    con = governor.connect_gov()
    ok, issues = governor.verify_db(con)
    if ok:
        print("governor: verify PASS")
    else:
        print("governor: verify FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(prog="eb")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)
    
    # E2: Governor init
    sub.add_parser("gov-init").set_defaults(func=cmd_gov_init)

    p = sub.add_parser("classify")
    p.add_argument("--request-text", required=True)
    p.add_argument("--task-type", required=True)
    p.add_argument("--roles", required=True)
    p.add_argument("--reasoning-depth", type=int, required=True)
    p.add_argument("--verification-level", required=True)
    p.add_argument("--risk-class", required=True)
    p.add_argument("--privacy-class", required=True)
    p.add_argument("--egress-policy", required=True)
    p.add_argument("--classification-confidence", required=True)
    p.add_argument("--deadline", default=None)
    p.add_argument("--idempotent", action="store_true")
    p.add_argument("--context-size", default="small", choices=["small", "medium", "large"])
    p.add_argument("--known-workflows", default=None)
    p.add_argument("--source-system", default=None)
    p.add_argument("--source-event-id", default=None)
    p.add_argument("--supersedes", default=None)
    p.add_argument("--reason", default=None)
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("decompose")
    p.add_argument("--task-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--order-index", type=int, required=True)
    p.add_argument("--parent", default=None)
    p.add_argument("--legality-note", default=None)
    p.set_defaults(func=cmd_decompose)

    p = sub.add_parser("freeze")
    p.add_argument("--task-id", required=True)
    p.add_argument("--subtask-id", default=None)
    p.add_argument("--roles", required=True)
    p.add_argument("--min-reasoning-depth", type=int, required=True)
    p.add_argument("--min-verification", required=True)
    p.add_argument("--risk-constraints", default=None)
    p.add_argument("--egress-constraints", default=None)
    p.add_argument("--strategy-constraints", default=None)
    p.set_defaults(func=cmd_freeze)

    p = sub.add_parser("route")
    p.add_argument("--floor-id", required=True)
    p.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    p.add_argument("--chosen-class", default=None)
    p.add_argument("--chosen-worker", default=None)
    p.add_argument("--reasoning", type=int, required=True)
    p.add_argument("--verification", required=True)
    p.add_argument("--scope", required=True, choices=["local", "external"])
    p.add_argument("--egress", required=True)
    p.add_argument("--roles", required=True)
    p.add_argument("--qualification-evidence", default="UNPROVEN")
    p.add_argument("--risk-approval", default=None)
    p.add_argument("--ranked-candidates", default=None)
    p.add_argument("--override-id", default=None)
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("override")
    p.add_argument("--floor-id", required=True)
    p.add_argument("--strategy", required=True)
    p.add_argument("--chosen-class", default=None)
    p.add_argument("--chosen-worker", default=None)
    p.add_argument("--reasoning", type=int, required=True)
    p.add_argument("--verification", required=True)
    p.add_argument("--scope", required=True)
    p.add_argument("--egress", required=True)
    p.add_argument("--roles", required=True)
    p.add_argument("--route-description", required=True)
    p.add_argument("--warning", required=True)
    p.add_argument("--confirmation", required=True)
    p.set_defaults(func=cmd_override)

    p = sub.add_parser("audit")
    p.add_argument("--verify", action="store_true")
    p.set_defaults(func=cmd_audit)

    sub.add_parser("backup").set_defaults(func=cmd_backup)
    p = sub.add_parser("restore")
    p.add_argument("--backup-dir", required=True)
    p.set_defaults(func=cmd_restore)

    sub.add_parser("summary").set_defaults(func=cmd_summary)

    # E2: Governor subcommands
    p = sub.add_parser("telemetry")
    p.set_defaults(func=cmd_telemetry)
    
    p = sub.add_parser("brief")
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_brief)
    
    p = sub.add_parser("record-request")
    p.add_argument("--provider", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--input-tokens", type=int, default=None)
    p.add_argument("--output-tokens", type=int, default=None)
    p.add_argument("--cost", default=None)
    p.add_argument("--status", default="success")
    p.add_argument("--error-code", default=None)
    p.add_argument("--latency-ms", type=int, default=None)
    p.set_defaults(func=cmd_record_request)
    
    p = sub.add_parser("gov-status")
    p.set_defaults(func=cmd_gov_status)
    
    p = sub.add_parser("gov-verify")
    p.set_defaults(func=cmd_gov_verify)

    # E3: orchestration subcommands (registered by scripts/deploy_e3_runtime.py)
    try:
        from e3_cli import register as _register_e3_subcommands
        _register_e3_subcommands(sub)
    except Exception as _e3_cli_error:  # pragma: no cover - degrade, never crash E1
        print(f"warning: E3 CLI bindings unavailable: {_e3_cli_error}",
              file=sys.stderr)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
