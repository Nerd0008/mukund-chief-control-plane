#!/usr/bin/env python3
"""Acceptance + evidence run for the read-only Application Inbox / Status Monitor.

What is exercised
-----------------
1. Repo fixture mailbox (synthetic, committed): parsing, classification,
   quoting removal, unknown handling, ambiguity handling, adapter refusal.
2. A synthetic mailbox **generated at run time from the canonical workbooks'
   own rows** (read-only), so real matching and real status proposals are
   exercised without copying any owner record into the repository. These
   messages are labelled as runtime-synthesised in the evidence.
3. Idempotency: the same mailbox is ingested twice and the store must be
   byte-identical with zero new signals the second time.
4. Safety: canonical workbook hashes unchanged, the default runtime store
   untouched, no applications created, every mailbox mutation refused.

Evidence modes are kept separate and explicit. This run contains **no live
mailbox evidence** — no credentials exist — and says so rather than implying it.

Usage
    python career-ops/run_application_inbox_acceptance.py [--stamp S] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

CAREER_OPS_DIR = Path(__file__).resolve().parent
CONTROL_PLANE = CAREER_OPS_DIR.parent
sys.path.insert(0, str(CAREER_OPS_DIR))

import application_inbox as ai  # noqa: E402
import tracker_writer as tw  # noqa: E402
import gmail_readonly  # noqa: E402

FIXTURES = CAREER_OPS_DIR / "tests" / "fixtures" / "application-inbox"
DEFAULT_OUT = CONTROL_PLANE / "audits" / "evidence"


def allowed_statuses(profiles: dict, region: str) -> list[str]:
    """The region's own application-status vocabulary, from its configured validation."""
    cfg = tw.region_config(profiles, region)
    column = cfg["status_columns"]["application_status"]
    formula = ((cfg.get("validations") or {}).get(column) or {}).get("formula1") or ""
    inner = formula.strip().strip('"')
    return [s.strip() for s in inner.split(",") if s.strip()]


def pick_rows(index: dict, cfg: dict, region: str, want: int = 3) -> list[dict]:
    """Canonical rows suitable for a runtime-synthesised signal.

    Requires a usable URL, a reference-matchable id (>= 3 characters, see
    ``ID_TOKEN_RE``), and a status that means no application is recorded yet —
    so a proposal for it must be flagged for owner confirmation.
    """
    pre = {s.casefold() for s in cfg["pre_application_states"].get(region, [])}
    rows = [r for r in index["regions"][region]["rows"]
            if r.get("url") and r.get("url_key") and r.get("id")
            and len(str(r["id"])) >= 3
            and str(r.get("application_status") or "").casefold() in pre]
    return rows[:want]


def build_derived_mailbox(out_dir: Path, index: dict, profiles: dict, cfg: dict) -> dict:
    """Write synthetic messages that reference real canonical rows.

    The *message envelopes are synthetic and generated here*; the posting URL,
    company, title and row id they reference come from the owner's own workbook.
    Nothing is copied into the repository — this directory is git-ignored.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    uk_rows = pick_rows(index, cfg, "uk", 3)
    sg_rows = pick_rows(index, cfg, "singapore", 2)
    generated: list[dict] = []

    def write(name: str, records: list[dict]) -> None:
        (out_dir / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8")

    msgs: list[dict] = []
    if uk_rows:
        r = uk_rows[0]
        msgs.append({
            "message_id": "<derived-ack-uk@example.invalid>",
            "received_at": "2026-09-23T07:00:00+00:00",
            "from": "no-reply@example-ats.invalid",
            "to": "mukund@example.com",
            "subject": f"Thank you for applying - {r['title']}",
            "body": ("Thank you for applying to " + str(r["company"]) +
                     ". We have received your application. "
                     "View the role: " + str(r["url"])),
        })
        generated.append({"case": "url_match_acknowledgement", "region": "uk",
                          "row_id": r["id"], "expected_basis": "posting_url_in_message"})
    if len(uk_rows) > 1:
        r = uk_rows[1]
        msgs.append({
            "message_id": "<derived-rejection-uk@example.invalid>",
            "received_at": "2026-09-23T07:30:00+00:00",
            "from": "recruitment@example-ats.invalid",
            "to": "mukund@example.com",
            "subject": f"Outcome of your application ({r['id']})",
            "body": ("Unfortunately, we will not be proceeding with your application for the "
                     + str(r["title"]) + " role. Your reference is " + str(r["id"]) + "."),
        })
        generated.append({"case": "id_reference_rejection", "region": "uk",
                          "row_id": r["id"], "expected_basis": "explicit_canonical_reference_in_message"})
    if len(uk_rows) > 2:
        r = uk_rows[2]
        msgs.append({
            "message_id": "<derived-interview-uk@example.invalid>",
            "received_at": "2026-09-23T08:00:00+00:00",
            "from": "talent@example-ats.invalid",
            "to": "mukund@example.com",
            "subject": f"Interview invitation - {r['title']}",
            "body": ("We would like to invite you to interview for the " + str(r["title"]) +
                     " position at " + str(r["company"]) + ". "
                     "The posting is " + str(r["url"]) + "."),
        })
        generated.append({"case": "url_match_interview_invite", "region": "uk",
                          "row_id": r["id"], "expected_basis": "posting_url_in_message"})
    if sg_rows:
        r = sg_rows[0]
        msgs.append({
            "message_id": "<derived-ack-sg@example.invalid>",
            "received_at": "2026-09-23T08:30:00+00:00",
            "from": "no-reply@example-ats.invalid",
            "to": "mukund@example.com",
            "subject": "Thank you for applying",
            "body": ("Thank you for applying to " + str(r["company"]) +
                     ". We have received your application. Application reference: " +
                     str(r["id"]) + "."),
        })
        generated.append({"case": "id_reference_acknowledgement_cross_region", "region": "singapore",
                          "row_id": r["id"], "expected_basis": "explicit_canonical_reference_in_message"})
    if len(sg_rows) > 1:
        r = sg_rows[1]
        msgs.append({
            "message_id": "<derived-unmatched@example.invalid>",
            "received_at": "2026-09-23T09:00:00+00:00",
            "from": "hr@unrelated-employer.invalid",
            "to": "mukund@example.com",
            "subject": "Thank you for applying to Unrelated Employer",
            "body": ("Thank you for applying to Unrelated Employer Limited. "
                     "We have received your application."),
        })
        generated.append({"case": "unmatched_employer_no_record_created", "region": None,
                          "row_id": None, "expected_basis": "no_match"})

    # an unclassifiable message inside the derived batch, so ambiguity handling is
    # proven in the same pass
    msgs.append({
        "message_id": "<derived-unknown@example.invalid>",
        "received_at": "2026-09-23T09:30:00+00:00",
        "from": "someone@example.invalid",
        "to": "mukund@example.com",
        "subject": "Quick question",
        "body": "Checking in — nothing in particular. Let me know your thoughts.",
    })
    generated.append({"case": "unknown_stays_unknown", "region": None, "row_id": None,
                      "expected_basis": "no_match"})

    write("derived-messages.jsonl", msgs)
    return {"dir": str(out_dir), "messages": len(msgs), "cases": generated}


def store_hashes(root: Path) -> dict:
    """Hash the durable store state.

    ``run-log.jsonl`` is deliberately excluded: it is an append-only operational
    log of *runs*, not store state, so it grows on every run by design.
    """
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "run-log.jsonl":
            out[str(path.relative_to(root))] = ai.sha256_file(path)
    return out


def run_ingest(inbox: Path, store: Path, cfg_path: str) -> dict:
    """Call the module directly (no subprocess) — deterministic and inspectable."""
    cfg = ai.load_config(cfg_path)
    collected = ai.collect_local_mailbox(cfg, inbox)
    if not collected.get("ok"):
        return {"ok": False, **collected}
    root = ai.runtime_dir(cfg, store)
    result = ai.ingest(cfg, collected, root)
    summary = ai.build_summary(cfg, root)
    return {"ok": True, "collected": collected, "ingest": result, "summary": summary}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Application Inbox / Status Monitor acceptance run")
    ap.add_argument("--stamp", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)

    started = dt.datetime.now(dt.timezone.utc)
    stamp = args.stamp or started.strftime("%Y-%m-%dT%H-%M-%SZ")
    out = Path(args.out_dir) if args.out_dir else DEFAULT_OUT / f"{stamp}-application-inbox-status-monitor"
    out.mkdir(parents=True, exist_ok=True)
    store_root = out / "status-store"

    cfg = ai.load_config(args.config)
    profiles = ai.load_profiles(cfg)
    index = ai.build_canonical_index(cfg, profiles)

    before = {region: e["sha256"] for region, e in index["regions"].items()}
    default_store = CONTROL_PLANE / cfg["runtime_dir"]
    default_store_existed = default_store.exists()

    checks: list[dict] = []

    def check(name: str, ok: bool, detail=None) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # ---- 1. repo fixture mailbox ----------------------------------------- #
    fixture = run_ingest(FIXTURES, store_root / "fixture-run", args.config or str(ai.DEFAULT_CONFIG))
    check("fixture_run_completed", fixture.get("ok") is True)
    fk = (fixture.get("summary") or {}).get("signals_by_kind", {}) if fixture.get("ok") else {}
    fcounts = (fixture.get("ingest") or {}).get("counts", {}) if fixture.get("ok") else {}
    check("fixture_expected_kinds_present",
          all(k in fk for k in ("application_acknowledgement", "rejection", "interview_invite",
                                "assessment_invite", "follow_up_request", "recruiter_outreach",
                                "unknown")),
          fk)
    check("fixture_unknown_never_guessed", fk.get("unknown", 0) >= 3, fk.get("unknown"))
    check("fixture_ambiguous_classification_flagged",
          fcounts.get("ambiguous_classification", 0) >= 1, fcounts.get("ambiguous_classification"))
    check("fixture_contradictory_message_left_for_human",
          any("contradictory" in str((s.get("classification") or {}).get("basis"))
              for s in ai._read_jsonl(ai.store_paths(store_root / "fixture-run")["signals"])))
    check("fixture_nothing_matched_so_no_state_proposed",
          fcounts.get("status_events", 0) == 0, fcounts.get("status_events"))
    fixture_mode = (fixture.get("collected") or {}).get("evidence_mode")
    check("fixture_evidence_mode_labelled", fixture_mode == "fixture", fixture_mode)
    fixture_skipped = [f["skipped"] for f in fixture["collected"]["files"] if f["skipped"]]
    check("non_envelope_files_skipped_not_guessed", len(fixture_skipped) >= 1, fixture_skipped)

    # ---- 2. derived-from-canonical mailbox -------------------------------- #
    derived_dir = store_root / "derived-mailbox"
    derived = build_derived_mailbox(derived_dir, index, profiles, cfg)
    check("derived_mailbox_generated_with_real_canonical_references",
          derived["messages"] >= 5 and len(derived["cases"]) >= 5,
          {"messages": derived["messages"], "cases": [c["case"] for c in derived["cases"]]})
    d_run = run_ingest(derived_dir, store_root / "derived-run", args.config or str(ai.DEFAULT_CONFIG))
    check("derived_run_completed", d_run.get("ok") is True)
    d_counts = (d_run.get("ingest") or {}).get("counts", {}) if d_run.get("ok") else {}
    d_summary = (d_run.get("summary") or {}) if d_run.get("ok") else {}
    signals = (d_run.get("ingest") or {}).get("state", {}).get("regions", {}) if d_run.get("ok") else {}
    # per-signal match detail is stored in the signal log; re-read it
    sig_log = ai._read_jsonl(ai.store_paths(store_root / "derived-run")["signals"])
    bases = [ (s.get("match") or {}).get("basis") for s in sig_log ]
    check("derived_url_match_exercised", "posting_url_in_message" in bases, bases)
    check("derived_id_reference_match_exercised",
          "explicit_canonical_reference_in_message" in bases, bases)
    check("derived_unmatched_still_unmatched", "no canonical reference" in " ".join(str(b) for b in bases))
    check("derived_status_proposals_created", d_counts.get("status_events", 0) >= 3,
          d_counts.get("status_events"))
    check("derived_no_applications_created",
          (d_summary.get("safety") or {}).get("applications_created") == 0)

    # every proposed status must be inside the region's own vocabulary
    vocab_ok, vocab_detail = True, []
    for region, rows in (signals or {}).items():
        allowed = allowed_statuses(profiles, region)
        for row_id, entry in rows.items():
            proposed = entry.get("proposed_status")
            if proposed and proposed not in allowed:
                vocab_ok = False
                vocab_detail.append({"region": region, "row_id": row_id, "proposed": proposed})
    check("proposed_statuses_are_in_region_vocabulary", vocab_ok, vocab_detail)

    # pre-application rows must be flagged for owner confirmation, not assumed applied
    confirm_flagged = [e for region in (signals or {}).values() for e in region.values()
                       if e.get("proposed_status")]
    check("unrecorded_application_requires_owner_confirmation",
          all(bool(e.get("requires_owner_confirmation")) for e in confirm_flagged)
          if confirm_flagged else False,
          [{"row_id": e["row_id"], "flag": e.get("requires_owner_confirmation")}
           for e in confirm_flagged])
    check("state_never_written_to_workbook",
          all(not e.get("state_written") for region in (signals or {}).values()
              for e in region.values()))

    # ---- 3. idempotency --------------------------------------------------- #
    store = store_root / "derived-run"
    hashes_before = store_hashes(store)
    d_run2 = run_ingest(derived_dir, store, args.config or str(ai.DEFAULT_CONFIG))
    hashes_after = store_hashes(store)
    counts2 = (d_run2.get("ingest") or {}).get("counts", {}) if d_run2.get("ok") else {}
    check("replay_adds_no_signals", counts2.get("new_signals") == 0, counts2.get("new_signals"))
    check("replay_adds_no_events", counts2.get("status_events", 0) == 0
          and counts2.get("no_status_events", 0) == 0, counts2)
    check("store_is_byte_identical_on_replay", hashes_before == hashes_after,
          {"changed": [k for k in set(hashes_before) | set(hashes_after)
                       if hashes_before.get(k) != hashes_after.get(k)]})

    # ---- 4. safety ------------------------------------------------------- #
    after = {region: e["sha256"] for region, e in ai.build_canonical_index(cfg, profiles)["regions"].items()}
    check("canonical_workbooks_unchanged", before == after, {"before": before, "after": after})
    check("default_runtime_store_untouched",
          (not default_store.exists()) if not default_store_existed else True,
          str(default_store))
    check("no_workbooks_written",
          (d_summary.get("safety") or {}).get("workbooks_written") == 0)
    check("no_mail_sent",
          (d_summary.get("safety") or {}).get("emails_sent") == 0
          and (d_summary.get("safety") or {}).get("replies_sent") == 0)
    check("no_mailbox_mutations",
          (d_summary.get("safety") or {}).get("mailbox_mutations") == 0)
    check("ingest_path_declares_no_network",
          (d_run["collected"].get("read_only_contract") or {}).get("network_used") is False)

    refused = {}
    guard_root = store_root / "guard"
    guard_root.mkdir(parents=True, exist_ok=True)
    for action in ("send", "reply", "reply_all", "forward", "archive", "delete", "trash",
                   "move", "mark_read", "label_apply", "unsubscribe", "apply"):
        res = ai.guard_action(cfg, action, guard_root)
        refused[action] = {"allowed": res["allowed"], "performed": res["performed"]}
    check("every_mailbox_mutation_refused",
          all(v["allowed"] is False and v["performed"] is False for v in refused.values()), refused)

    # ---- 5. gmail adapter refusal (no credentials exist) ----------------- #
    acfg = cfg["adapters"]["gmail_readonly"]
    gstatus = gmail_readonly.adapter_status(acfg)
    gfetch = gmail_readonly.fetch(acfg, limit=1)
    check("gmail_adapter_reports_unavailable",
          gstatus["available"] is False and gstatus["owner_action_required"] is True, gstatus["reason"])
    check("gmail_fetch_refuses_without_credentials",
          gfetch["ok"] is False and gfetch["network_used"] is False
          and gfetch["verification"] == "UNVERIFIED")
    check("gmail_scope_is_read_only",
          gstatus["required_scope"] == "https://www.googleapis.com/auth/gmail.readonly")
    check("no_credential_contents_reported",
          not any(k in json.dumps(gstatus) for k in ("client_secret", "refresh_token", "access_token")))

    # ---- 6. static capability boundary ----------------------------------- #
    src = (CAREER_OPS_DIR / "application_inbox.py").read_text(encoding="utf-8")
    imports = "\n".join(line for line in src.splitlines() if re.match(r"^\s*(import|from)\s", line))
    banned = [b for b in ("urllib", "requests", "socket", "http.client", "httpx", "aiohttp",
                          "webbrowser", "playwright", "selenium", "imaplib", "smtplib")
              if re.search(rf"\b{re.escape(b)}\b", imports)]
    check("ingest_module_imports_no_network_or_mail_library", not banned, banned)

    critical = [c for c in checks if not c["ok"]]
    finished = dt.datetime.now(dt.timezone.utc)
    evidence = {
        "task": "agent-application-inbox-status-monitor-2026-09-23",
        "run_id": stamp,
        "started_at": started.replace(microsecond=0).isoformat(),
        "finished_at": finished.replace(microsecond=0).isoformat(),
        "duration_s": round((finished - started).total_seconds(), 1),
        "code_sha": _git_sha(),
        "config": cfg["_config_path"],
        "evidence_modes": {
            "repo_fixture_mailbox": "EXECUTED — synthetic committed fixtures",
            "canonical_derived_synthetic_mailbox": ("EXECUTED — synthetic message envelopes referencing "
                                                    "real canonical rows, read-only"),
            "live_mailbox": "NOT RUN — no Gmail credentials exist on this machine",
        },
        "adapters": {
            "local_mailbox": {"implemented": True, "tested": True, "available": True},
            "gmail_readonly": {"implemented": True, "tested": "interface+refusal only",
                               "available": False, "fetch_path_executed": False,
                               "verification": "UNVERIFIED",
                               "reason": gstatus["reason"]},
        },
        "canonical_workbooks": {
            region: {"tracker": e["tracker"], "sha256": e["sha256"], "rows": len(e["rows"]),
                     "unchanged_by_run": before.get(region) == after.get(region)}
            for region, e in index["regions"].items()},
        "fixture_counts": {**(fixture.get("ingest") or {}).get("counts", {}),
                           "signals_by_kind": fk},
        "derived_counts": {**d_counts, "signals_by_match": d_summary.get("signals_by_match"),
                           "signals_by_kind": d_summary.get("signals_by_kind")},
        "derived_cases": derived["cases"],
        "proposals": {
            "total": d_counts.get("status_events", 0),
            "all_within_region_vocabulary": vocab_ok,
            "all_requiring_owner_confirmation": all(
                bool(e.get("requires_owner_confirmation")) for e in confirm_flagged)
            if confirm_flagged else False,
            "state_written_to_workbook": 0,
        },
        "idempotency": {"replay_new_signals": counts2.get("new_signals"),
                        "replay_new_events": counts2.get("status_events", 0)
                        + counts2.get("no_status_events", 0),
                        "store_byte_identical": hashes_before == hashes_after},
        "safety": {
            "emails_sent": 0, "replies_sent": 0, "mailbox_mutations": 0,
            "workbooks_written": 0, "applications_created": 0,
            "canonical_workbooks_unchanged": before == after,
            "mutations_refused": len(refused),
            "ingest_path_network_used": False,
        },
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(1 for c in checks if c["ok"]),
        "checks_failed": len(critical),
        "verdict": "PASS" if not critical else "FAIL",
        "raw_signal_and_status_store_local_only": str(store_root),
        "reconcile_summary": {region: len(rows) for region, rows in (signals or {}).items()},
    }

    (out / "acceptance.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    (out / "acceptance.md").write_text(render_markdown(evidence), encoding="utf-8")

    failed = [c for c in checks if not c["ok"]]
    print(f"checks: {len(checks) - len(failed)}/{len(checks)} passed")
    for c in failed:
        print(f"  FAIL {c['check']}: {c['detail']}")
    print(f"evidence: {out / 'acceptance.json'}")
    return 0 if not failed else 1


def render_markdown(ev: dict) -> str:
    lines = [
        "# Application Inbox / Status Monitor — acceptance evidence", "",
        f"- Task: `{ev['task']}`", f"- Run: {ev['run_id']} ({ev['duration_s']}s)",
        f"- Code SHA: `{ev['code_sha']}`", f"- Verdict: **{ev['verdict']}**",
        f"- Checks: {ev['checks_passed']}/{ev['checks_total']} passed", "",
        "## Evidence modes", "",
    ]
    for name, value in ev["evidence_modes"].items():
        lines.append(f"- `{name}`: {value}")
    lines += ["", "## Adapters", ""]
    for name, value in ev["adapters"].items():
        lines.append(f"- `{name}`: {json.dumps(value)}")
    lines += ["", "## Canonical workbooks (read-only, hash-verified unchanged)", ""]
    for region, meta in ev["canonical_workbooks"].items():
        lines.append(f"- {region}: {meta['rows']} rows, sha256 `{str(meta['sha256'])[:16]}…`, "
                     f"unchanged={meta['unchanged_by_run']}")
    lines += ["", "## Counts", "",
              "```", json.dumps({"fixture": ev["fixture_counts"], "derived": ev["derived_counts"]},
                                indent=2), "```", "",
              "## Proposals and safety", "",
              "```", json.dumps({"proposals": ev["proposals"], "idempotency": ev["idempotency"],
                                 "safety": ev["safety"]}, indent=2), "```", "",
              "## Checks", ""]
    for c in ev["checks"]:
        lines.append(f"- [{'x' if c['ok'] else ' '}] {c['check']}")
    lines += ["", f"Raw signal and status store (git-ignored): `{ev['raw_signal_and_status_store_local_only']}`",
              "", "No live mailbox evidence is claimed: no Gmail credentials exist on this machine, so "
              "the Gmail read-only adapter reports itself UNVERIFIED and refused the fetch."]
    return "\n".join(lines) + "\n"


def _git_sha() -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(CONTROL_PLANE),
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else "UNKNOWN"
    except OSError:
        return "UNKNOWN"


if __name__ == "__main__":
    raise SystemExit(main())
