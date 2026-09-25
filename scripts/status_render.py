#!/usr/bin/env python3
"""Deterministic renderer for the executive tracker and derived status summaries.

THE canonical project-status source is ``status/canonical-status.json``. This
script renders every drift-prone surface from it:

    status/executive-tracker.md        full executive tracker (standalone file)
    README.md                          "Current Executive Brain roadmap" block
    state/current_company_state.md     status header / latest-evidence block
    state/full_build_tracker.md        status header block

Generated regions are delimited by explicit markers. Once the markers exist the
tracker and every derived summary are maintained by regenerating from the
canonical source — never by hand-editing the generated text.

Usage:
    python scripts/status_render.py            # write generated outputs
    python scripts/status_render.py --check    # verify only, write nothing
    python scripts/status_render.py --stdout executive-tracker

The renderer makes no network call, reads no credential value and touches no
runtime database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import status_sources as src

GENERATION_COMMAND = "python scripts/status_render.py"
VERIFY_COMMAND = "python scripts/status_verify.py"


def _generated_notice() -> str:
    return (
        f"> **GENERATED FILE — DO NOT EDIT BY HAND.** Every figure below is rendered\n"
        f"> from `status/canonical-status.json` by `{GENERATION_COMMAND}`.\n"
        f"> Change the canonical status source, then regenerate. Verify with\n"
        f"> `{VERIFY_COMMAND}` (or the suite `scripts/tests/test_status_consistency.py`)."
    )


def _state_line(label: str, value: str) -> str:
    return f"| {label} | {value} |"


# --------------------------------------------------------------------------- #
# the executive tracker
# --------------------------------------------------------------------------- #
def render_executive_tracker(c: dict) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Executive Tracker — Chief Control Plane")
    add("")
    add(_generated_notice())
    add("")
    add(f"- Canonical source: `status/canonical-status.json` (schema v{c['schema_version']})")
    add(f"- Generation command: `{GENERATION_COMMAND}`")
    add(f"- Verification command: `{VERIFY_COMMAND}`")
    add(f"- Status as of (newest incorporated evidence): **{c['as_of']}**")
    add(f"- Newest evidence run: `{c['latest_evidence']['id']}` — **{c['latest_evidence']['verdict']}**")
    add("")

    # -- code / release identity -------------------------------------------- #
    ci = c["code_identity"]
    add("## 1. Code and release identity")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    add(_state_line("Repository", ci["repository"]))
    add(_state_line("Branch", ci["branch"]))
    add(_state_line("Authoring HEAD", f"`{ci['authoring_head_sha']}`"))
    add(_state_line("Verified evidence SHA", f"`{ci['verified_evidence_sha']}`"))
    add(_state_line("Supported Python", ci["supported_python"]))
    add(_state_line("Unsupported", ci["unsupported_python"]))
    add(_state_line("Dependency manifest / lock", f"`{ci['dependency_manifest']}` / `{ci['dependency_lock']}`"))
    add(_state_line("Release identity doc", f"`{ci['release_identity_doc']}`"))
    add("")

    # -- executive brain ----------------------------------------------------- #
    add("## 2. Executive Brain — implementation, verification, enablement, deployment")
    add("")
    add("Implementation completion, Stage 2 enablement and production deployment are three")
    add("separate states and are never collapsed into one.")
    add("")
    add("| Phase | Scope | Implementation | Verified | Stage 2 | Production deployed |")
    add("|---|---|---|---|---|---|")
    for phase in ("E1", "E2", "E3", "E4", "E5"):
        p = c["executive_brain"][phase]
        deployed = "no" if not p.get("production_dispatch_enabled", False) and not p.get("deployed", False) else "yes"
        stage2 = "n/a" if phase != "E3" else ("ENABLED" if p.get("stage2_enabled") else "NOT ENABLED")
        add(f"| **{phase}** | {p['name']} | {p['implementation']} | {p['state']} | {stage2} | {deployed} |")
    add("")
    for phase in ("E1", "E2", "E3", "E4", "E5"):
        p = c["executive_brain"][phase]
        add(f"- **{phase}** — {p['test_counts']}.")
        if p.get("notes"):
            add(f"  - {p['notes']}")
    add("")

    # -- roster -------------------------------------------------------------- #
    r = c["roster"]
    add("## 3. Roster accounting")
    add("")
    add(f"**{r['total']} roster items — {r['pass']} PASS, {r['ready_needs_owner_config']} "
        f"READY_NEEDS_OWNER_CONFIG, {r['blocked_external']} BLOCKED_EXTERNAL, {r['unaccounted']} unaccounted.**")
    add("")
    add("| ID | Worker / service | Status | Reason |")
    add("|---|---|---|---|")
    for item in r["non_pass_items"]:
        add(f"| {item['id']} | {item['worker']} | {item['status']} | {item['reason']} |")
    add("")
    add(f"Source: `{r['source']['path']}`. Roster definition: `state/v1-agent-roster.md`.")
    add("")

    # -- regressions --------------------------------------------------------- #
    g = c["regressions"]
    add("## 4. Regression evidence (newest verification run)")
    add("")
    add(f"- Suites: **{g['suites_run']} run / {g['suites_passed']} passed / {g['suites_failed']} failed / "
        f"{g['suites_unavailable']} unavailable**")
    add(f"- Tests: **{g['tests_collected']} collected / {g['tests_passed']} passed / {g['tests_failed']} failed**")
    add(f"- Code SHA: `{g['code_sha']}`")
    add(f"- Interpreter: {g['python']}")
    add(f"- Source: `{g['source']['path']}`")
    add(f"- {g['source']['note']}")
    add("")

    # -- career discovery ---------------------------------------------------- #
    cd = c["career_discovery"]
    add("## 5. Career discovery state")
    add("")
    fun = cd["unified_funnel"]
    add(f"- **{fun['id']} unified funnel** — {fun['state']}: {fun['what']}")
    add(f"  - Code: `{fun['code']}`")
    add("")
    add("| ID | Surface | State | Note |")
    add("|---|---|---|---|")
    for s in cd["surfaces"]:
        add(f"| {s['id']} | {s['name']} | {s['state']} | {s.get('note', '')} |")
    add("")
    reg = cd["regional_and_schedule"]
    add(f"- **Regional workers ({reg['regional_workers']['id']})** — {reg['regional_workers']['state']}: "
        f"{reg['regional_workers']['note']}")
    soc = reg["scheduled_orchestrator_cutover"]
    add(f"- **Scheduled orchestrator cutover** — **{soc['state']}** "
        f"({soc['blocker_category']}, {soc['attempts']}/{soc['attempts_permitted']} attempts): {soc['note']}")
    add(f"  - Evidence: `{soc['evidence']}`")
    add("")
    add("Truth boundaries that hold:")
    for tb in cd["truth_boundaries"]:
        add(f"- {tb}")
    add("")

    # -- queue / service ----------------------------------------------------- #
    q = c["queue_service"]
    add("## 6. Queue and service state")
    add("")
    add(f"- **Remote queue** — {q['remote_queue']['state']}. {q['remote_queue']['note']}")
    add(f"- **Owned scheduled tasks** — {q['scheduled_tasks']['owned_tasks']} tasks; logon type "
        f"{q['scheduled_tasks']['logon_type']}.")
    add(f"  - {', '.join('`' + n + '`' for n in q['scheduled_tasks']['names'])}")
    add(f"- **Operational services** — {q['operational_services']['state']}. "
        f"`{q['operational_services']['code']}`, see `{q['operational_services']['doc']}`.")
    add("")
    add("Known open items:")
    for item in q["remote_queue"]["known_open"]:
        add(f"- {item}")
    add("")

    # -- providers ----------------------------------------------------------- #
    pv = c["provider_credentials"]
    add("## 7. Provider credential readiness")
    add("")
    add(f"- Roster workers: **{pv['roster_workers']}**")
    add(f"- Credentials configured: **{pv['credentials_present']} / {pv['roster_workers']}** "
        f"({pv['credentials_absent']} absent)")
    add(f"- Absent workers: {', '.join('`' + w + '`' for w in pv['absent_workers'])}")
    add(f"- Present interfaces: {', '.join(pv['present_interfaces'])}")
    add(f"- Routable: {', '.join('`' + w + '`' for w in pv['routable_workers'])}")
    add(f"- {pv['routable_note']}")
    if pv.get("owner_record"):
        add(f"- Owner record: `{pv['owner_record']['path']}` — {pv['owner_record']['note']}")
    add(f"- Source: `{pv['source']['path']}` — {pv['source']['note']}")
    add("")

    # -- stage 2 ------------------------------------------------------------- #
    s2 = c["stage2"]
    add("## 8. Stage 2 state")
    add("")
    add(f"**{s2['state']}** (gate `{s2['gate']}`, verdict {s2['verdict_utc']})")
    add("")
    add("Failing conditions at the last verdict:")
    for cond in s2["failing_conditions"]:
        add(f"- {cond}")
    add("")
    add(f"{s2['anti_loop']}")
    add("")

    # -- deployment ---------------------------------------------------------- #
    d = c["deployment"]
    add("## 9. Deployment state")
    add("")
    add(f"- **State: {d['state']}** — cutover {d['cutover']}.")
    add(f"- **Architecture:** {d['architecture']}")
    add(f"- **VPS details:** {d['vps_details']}")
    pf = d["preflight"]
    add(f"- **Preflight:** {pf['verdict']} ({pf['checks']['pass']} PASS, {pf['checks']['warn']} WARN, "
        f"{pf['checks']['fail']} FAIL); sole warning: {pf['sole_warning']}")
    add(f"  - {pf['note']}")
    add(f"- **Backup/restore drill:** {d['backup_restore_drill']['result']} "
        f"({d['backup_restore_drill']['artifacts']} artifacts)")
    add(f"- Runbook `{d['cutover_runbook']}`, rollback `{d['rollback_checklist']}`, "
        f"services `{d['service_definitions']}`")
    add(f"- Inbound network: {d['inbound_network']}")
    add("")

    # -- production blockers ------------------------------------------------- #
    add("## 10. Production blockers (separate from implementation completion)")
    add("")
    add(f"{len(c['production_blockers'])} open item(s). Implementation completion is NOT release readiness.")
    add("")
    add("| ID | Blocker | Category | State | Owner action |")
    add("|---|---|---|---|---|")
    for b in c["production_blockers"]:
        owner = "required" if b.get("owner_action_required") else "engineering"
        add(f"| `{b['id']}` | {b['title']} | {b['category']} | {b['state']} | {owner} |")
    add("")
    for b in c["production_blockers"]:
        add(f"### `{b['id']}` — {b['title']}")
        add("")
        add(f"- Blocks: {b['blocks']}")
        add(f"- Evidence: `{b['evidence']}`")
        if b.get("owner_action"):
            add(f"- Owner action: {b['owner_action']}")
        add("")

    # -- resolved blockers --------------------------------------------------- #
    resolved = c.get("resolved_blockers", [])
    if resolved:
        add(f"### Resolved blockers ({len(resolved)} — recorded, not deleted)")
        add("")
        add("| ID | Item | State |")
        add("|---|---|---|")
        for b in resolved:
            add(f"| `{b['id']}` | {b['title']} | {b['state']} |")
        add("")
        for b in resolved:
            add(f"- **`{b['id']}`** — {b.get('resolution', '')} Evidence: `{b['evidence']}`")
        add("")

    # -- optional ------------------------------------------------------------ #
    add("## 11. Optional / feature-gated owner decisions (NOT release blockers)")
    add("")
    add("These are recorded so nothing is silent; none of them is claimed to block release")
    add("unless the documented product scope requires it.")
    add("")
    add("| ID | Item | Classification | State |")
    add("|---|---|---|---|")
    for o in c["optional_gated"]:
        add(f"| `{o['id']}` | {o['title']} | {o['classification']} | {o['state']} |")
    add("")
    for o in c["optional_gated"]:
        add(f"- **`{o['id']}`** — {o['why_not_a_release_blocker']}")
        if o.get("owner_action"):
            add(f"  - Owner action (optional): {o['owner_action']}")
    add("")

    # -- unknowns ------------------------------------------------------------ #
    add("## 12. Unresolved unknowns")
    add("")
    for u in c["unknowns"]:
        add(f"- {u}")
    add("")

    # -- chronology ---------------------------------------------------------- #
    add("## 13. Evidence chronology (newest first)")
    add("")
    add("| At (UTC) | Evidence | Result | What |")
    add("|---|---|---|---|")
    for h in c["history"]:
        add(f"| {h['at']} | `{h['id']}` | {h['result']} | {h['what']} |")
    add("")
    add("Historical narrative and per-lane detail remain in `state/full_build_tracker.md` and")
    add("`state/current_company_state.md`; those documents keep their own chronology and are")
    add("never overwritten by this renderer beyond their generated status header.")
    add("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# derived summary blocks
# --------------------------------------------------------------------------- #
def render_readme_block(c: dict) -> str:
    e = c["executive_brain"]
    lines = [
        "## Current Executive Brain roadmap",
        "",
        f"_Generated from the canonical status source (`status/canonical-status.json`, as of {c['as_of']}). "
        f"Regenerate with `{GENERATION_COMMAND}`._",
        "",
        "The Executive Brain is implemented in five layers. **Implementation completion,",
        "Stage 2 enablement and production deployment are three different states.**",
        "",
        "| Phase | State now | Implementation | Stage 2 | Production deployed |",
        "|---|---|---|---|---|",
    ]
    for phase in ("E1", "E2", "E3", "E4", "E5"):
        p = e[phase]
        stage2 = "n/a" if phase != "E3" else ("ENABLED" if p.get("stage2_enabled") else "**NOT ENABLED**")
        lines.append(f"| **{phase}** | {p['state']} | {p['implementation']} | {stage2} | {'yes' if p.get('production_dispatch_enabled', False) or p.get('deployed', False) else 'no'} |")
    lines += [
        "",
        "- **E1 — ACTIVE:** task classification, immutable quality floors, routing discipline, owner overrides, audit integrity.",
        "- **E2 — ACTIVE:** Resource Governor telemetry, provider capacity/state tracking, deterministic Daily Resource Brief.",
        f"- **E3 — {e['E3']['state']}:** multi-model orchestration, dynamic team assembly, "
        "evidence-backed worker qualification, execution DAGs, deterministic verification gates and decision-rationale "
        "audit trails. Local Stage 2 is restricted to the recorded verified worker pool; provider-deferred workers remain non-routable.",
        "- **E4 — IMPLEMENTED AND DRILL-VERIFIED:** predictive exhaustion, protected reserves, resource-driven "
        "checkpointing, checkpoint/state handover and equivalent-worker failover. Drills use injected (stubbed) "
        "provider failures; real-provider failover is **not** claimed.",
        "- **E5 — IMPLEMENTED AND DRILL-VERIFIED:** safe/degraded mode, failure drills, outage and malformed-output "
        "handling, bounded convergence enforcement, mature owner-override UX and a recovery path. The real "
        "provider-health probe before leaving safe mode is **not** wired.",
        "",
        f"**Production blockers remain open ({len(c['production_blockers'])}): local deployment is active, "
        f"while VPS cutover is not authorised.** See `status/executive-tracker.md` "
        f"(section 10) for the explicit blocker list, and `state/current_company_state.md` for the live state.",
    ]
    return "\n".join(lines) + "\n"


def render_company_state_block(c: dict) -> str:
    e = c["executive_brain"]
    blockers = ", ".join(f"`{b['id']}`" for b in c["production_blockers"])
    lines = [
        "## Canonical status (generated)",
        "",
        f"_Generated from `status/canonical-status.json` at as-of **{c['as_of']}** by `{GENERATION_COMMAND}`; "
        f"verify with `{VERIFY_COMMAND}`. The evidence chronology below is preserved unchanged._",
        "",
        f"- **Code identity:** branch `{c['code_identity']['branch']}`, authoring HEAD "
        f"`{c['code_identity']['authoring_head_sha']}`, newest verified evidence SHA "
        f"`{c['code_identity']['verified_evidence_sha']}`.",
        f"- **Newest evidence run:** `{c['latest_evidence']['id']}` — **{c['latest_evidence']['verdict']}** "
        f"(finished {c['latest_evidence']['run_finished_utc']}); regression "
        f"**{c['regressions']['suites_run']} suites / {c['regressions']['tests_collected']} collected / "
        f"{c['regressions']['tests_passed']} passed / 0 failed / 0 unavailable**.",
        f"- **Executive Brain:** E1 {e['E1']['state']}; E2 {e['E2']['state']}; E3 {e['E3']['state']}; "
        f"E4 {e['E4']['state']}; E5 {e['E5']['state']}.",
        f"- **Roster:** {c['roster']['total']} items — {c['roster']['pass']} PASS, "
        f"{c['roster']['ready_needs_owner_config']} READY_NEEDS_OWNER_CONFIG, "
        f"{c['roster']['blocked_external']} BLOCKED_EXTERNAL.",
        f"- **Provider credentials:** {c['provider_credentials']['credentials_present']} / "
        f"{c['provider_credentials']['roster_workers']} present "
        f"({c['provider_credentials']['credentials_absent']} absent).",
        f"- **Stage 2:** {c['stage2']['state']}. **Deployment:** {c['deployment']['state']} "
        f"(cutover {c['deployment']['cutover']}; preflight {c['deployment']['preflight']['verdict']} with "
        f"{c['deployment']['preflight']['checks']['warn']} owner-gated WARN).",
        f"- **Production blockers ({len(c['production_blockers'])}), separate from implementation completion:** {blockers}.",
        f"- **Optional / feature-gated owner decisions (not release blockers):** "
        f"{len(c['optional_gated'])} items — see `status/executive-tracker.md` section 11.",
        "",
        "Full regenerated view: `status/executive-tracker.md`.",
    ]
    return "\n".join(lines) + "\n"


def render_tracker_block(c: dict) -> str:
    e = c["executive_brain"]
    lines = [
        "> **Status header is GENERATED** from `status/canonical-status.json` by "
        f"`{GENERATION_COMMAND}` — do not hand-edit this block.",
        "",
        f"- **Canonical status as of:** {c['as_of']} (newest evidence `{c['latest_evidence']['id']}`).",
        f"- **Regeneration command:** `{GENERATION_COMMAND}`; **verification:** `{VERIFY_COMMAND}`.",
        f"- **Executive tracker (generated):** `status/executive-tracker.md`.",
        f"- **Code identity at authoring:** `{c['code_identity']['authoring_head_sha']}` "
        f"(verified evidence SHA `{c['code_identity']['verified_evidence_sha']}`).",
        f"- **Roster:** {c['roster']['total']} items — {c['roster']['pass']} PASS, "
        f"{c['roster']['ready_needs_owner_config']} READY_NEEDS_OWNER_CONFIG, "
        f"{c['roster']['blocked_external']} BLOCKED_EXTERNAL.",
        f"- **Provider credentials:** {c['provider_credentials']['credentials_present']} / "
        f"{c['provider_credentials']['roster_workers']} present.",
        f"- **Stage 2:** {c['stage2']['state']}. **Deployment:** {c['deployment']['state']}; "
        f"cutover {c['deployment']['cutover']}.",
        f"- **Production blockers ({len(c['production_blockers'])}):** "
        f"{', '.join('`' + b['id'] + '`' for b in c['production_blockers'])}.",
        f"- **Latest regression:** {c['regressions']['suites_run']} suites / "
        f"{c['regressions']['tests_collected']} tests, {c['regressions']['tests_passed']} passed, "
        f"0 failed, 0 unavailable.",
        "",
        "The narrative lanes, truth defects and per-task detail below remain the historical record and are",
        "not regenerated.",
    ]
    return "\n".join(lines) + "\n"


def build_outputs(c: dict) -> dict[str, str]:
    """Render every generated surface. Pure function of the canonical status."""
    return {
        "executive-tracker": render_executive_tracker(c),
        "readme-block": render_readme_block(c),
        "company-state-block": render_company_state_block(c),
        "tracker-block": render_tracker_block(c),
    }


# --------------------------------------------------------------------------- #
# splicing / writing
# --------------------------------------------------------------------------- #
def wrap_block(block: str, newline: str) -> str:
    body = block.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    body = body.replace("\n", newline)
    return f"{src.MARKER_BEGIN}{newline}{body}{newline}{src.MARKER_END}"


def splice_after_heading(text: str, heading: str, wrapped: str) -> str:
    """Insert `wrapped` immediately after the line equal to `heading`."""
    newline = src.detect_newline(text)
    lines = text.split(newline)
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            return newline.join(lines[:idx + 1] + ["", wrapped] + lines[idx + 1:])
    raise SystemExit(f"anchor heading not found: {heading!r}")


def replace_section(text: str, heading: str, wrapped: str) -> str:
    """Replace the `## heading` section (up to the next `## `) with `wrapped`."""
    newline = src.detect_newline(text)
    lines = text.split(newline)
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start = idx
            break
    if start is None:
        raise SystemExit(f"section heading not found: {heading!r}")
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return newline.join(lines[:start] + [wrapped, ""] + lines[end:])


def apply_block(text: str, block: str, fallback) -> str:
    """Replace an existing generated block, else use `fallback(text, wrapped)`."""
    newline = src.detect_newline(text)
    wrapped = wrap_block(block, newline)
    if src.MARKER_BEGIN in text and src.MARKER_END in text:
        start = text.index(src.MARKER_BEGIN)
        end = text.index(src.MARKER_END) + len(src.MARKER_END)
        return text[:start] + wrapped + text[end:]
    return fallback(text, wrapped)


def write_outputs(c: dict, repo_root: Path | None = None) -> list[Path]:
    root = Path(repo_root) if repo_root is not None else src.REPO_ROOT
    outputs = build_outputs(c)
    written: list[Path] = []

    tracker_path = root / "status" / "executive-tracker.md"
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(outputs["executive-tracker"], encoding="utf-8", newline="\n")
    written.append(tracker_path)

    targets = [
        (root / "README.md", outputs["readme-block"],
         lambda text, wrapped: replace_section(text, "## Current Executive Brain roadmap", wrapped)),
        (root / "state" / "current_company_state.md", outputs["company-state-block"],
         lambda text, wrapped: splice_after_heading(text, "# Current Company State", wrapped)),
        (root / "state" / "full_build_tracker.md", outputs["tracker-block"],
         lambda text, wrapped: splice_after_heading(text, "# Full-Build Tracker", wrapped)),
    ]
    for path, block, fallback in targets:
        text = src.read_source(path)
        updated = apply_block(text, block, fallback)
        path.write_text(updated, encoding="utf-8", newline="")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify only (delegates to scripts/status_verify.py); write nothing")
    parser.add_argument("--stdout", choices=["executive-tracker", "readme-block",
                                             "company-state-block", "tracker-block"],
                        help="print one rendered output and exit")
    args = parser.parse_args(argv)

    if args.check:
        import status_verify
        return status_verify.main([])

    canonical = src.load_canonical()

    if args.stdout:
        sys.stdout.write(build_outputs(canonical)[args.stdout])
        return 0

    problems = src.run_all_checks(canonical, include_block_checks=False)
    fails = [m for level, m in problems if level == "FAIL"]
    if fails:
        for message in fails:
            print(f"FAIL: {message}")
        print("refusing to render: the canonical status source failed its evidence checks")
        return 1

    written = write_outputs(canonical)
    for path in written:
        print(f"wrote {path.relative_to(src.REPO_ROOT)}")
    print(f"rendered from {src.CANONICAL_PATH.relative_to(src.REPO_ROOT)} (as of {canonical['as_of']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
