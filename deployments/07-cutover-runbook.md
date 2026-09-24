# 07 — Cutover runbook

Ordered, executable runbook. **Prepared only — nothing in here has been
executed, and nothing here may be executed until the owner decides the topology
and authorises the cutover.**

Legend:
- `[READY]` — architecture-independent; safe to rehearse now.
- `[PENDING OWNER DECISION]` — differs by topology or needs explicit authorisation.
- `[OWNER]` — an action only Mukund can take.
- `[NO-GO]` — step that must not run until the no-go checklist in `08` is clear.

---

## Phase 0 — Pre-flight (rehearse today; no side effects)

| # | Step | Command | Gate |
|---|---|---|---|
| 0.1 | Machine inventory | `python scripts/deployment_inventory.py --out deployments/inventory-<stamp>.json` | `[READY]` |
| 0.2 | Go/no-go preflight | `python scripts/deployment_preflight.py` | must print `verdict: GO` (0 failures) |
| 0.3 | Backup/restore drill | `python scripts/deployment_backup_restore_drill.py` | must print `status: PASS` |
| 0.4 | Credential presence | `python scripts/set_provider_key.py --status` | 10/10 workers `credential_present: true` |
| 0.5 | E1–E5 regression | `python scripts/evidence_runner.py --label pre-cutover` | every suite pass, 0 failed/errors/skipped |
| 0.6 | E4/E5 drills | `python exec-brain/e4e5_drill_harness.py` | 33/33 checks, real provider calls 0 |
| 0.7 | Acceptance commands | `deployments/09-acceptance-and-health-commands.md` §1–§3 | all pass |
| 0.8 | No-go checklist | `deployments/08-rollback-and-no-go-checklist.md` | every box clear |

Exit criterion: 0.2–0.7 all green **and** 0.8 clear. Anything else is a stop.

## Phase 1 — Owner decisions and authorisation

| # | Step | Owner action | Blocks |
|---|---|---|---|
| 1.1 | `[OWNER]` Choose topology: laptop-primary / VPS-primary / defer | one written line | every step marked `[PENDING OWNER DECISION]` |
| 1.2 | `[OWNER]` If VPS: supply host/account details locally (never in GitHub/chat) | local note | Phase 3 |
| 1.3 | `[OWNER]` Authorise the cutover window | explicit instruction | Phase 3 onward |
| 1.4 | `[OWNER]` Clear the no-go list's owner items (laptop audit, reboot check, legacy task disposition) | per `02`/`03` | Phase 3 |
| 1.5 | `[OWNER]` Confirm provider keys configured (Phase 0.4 green) | — | Phase 2 |

Architecture is **not** chosen by this runbook. Until 1.1 lands, Phases 2–5 are
planning material only.

## Phase 2 — Topology-independent deployment (both variants)

Applies either way; safe once 1.1–1.5 are done.

| # | Step | Command / action |
|---|---|---|
| 2.1 | Commit + push the current control-plane state | `git status` clean, then push to the private remote |
| 2.2 | Provision the destination runtime | create the Python 3.11 venv, `pip install openpyxl PyYAML` (`04` §2) |
| 2.3 | Deploy the E3 module set | `python scripts/deploy_e3_runtime.py --dry-run` then run it for real (creates a rollback backup first) |
| 2.4 | Provision secrets **into the destination secret store** | owner action; names in `02` §A/§D. Never via GitHub |
| 2.5 | Copy/initialise state | new node: initialise fresh DBs and verify integrity; migrating node: use `05` §3 |
| 2.6 | Register services | `schtasks /Create /XML deployments/service-definitions/*.xml` (`06` §3) |
| 2.7 | Apply the battery gating fix if the node is a laptop | re-import XML with `DisallowStartIfOnBatteries`/`StopIfGoingOnBatteries` = false (`06` §2a) |
| 2.8 | Apply firewall policy | outbound 443 allow, inbound deny (`01` §5) |
| 2.9 | Configure log rotation/retention | **gap — not yet implemented**; see `06` §5. Must be closed before long unattended operation |
| 2.10 | Re-run Phase 0.2/0.3/0.5 on the destination node | evidence on the destination, not the laptop |

## Phase 3 — Cutover (direction depends on 1.1)

`[PENDING OWNER DECISION]` — the following are two alternatives, not a sequence.

### 3A — Laptop stays primary, VPS becomes watchdog/failover
1. Keep the laptop as the writer of record; no DB move.
2. Deploy the module set + config to the VPS in read-only/watch mode.
3. Give the VPS an independent restore-capable copy of the artifacts (not of the owner-private state).
4. Add a health-observation job on the VPS and a documented **manual** failover trigger (no automatic promotion until the owner approves one).
5. Failover test: simulate laptop loss (stop the gateway), confirm the watchdog alerts, confirm no split-brain writes.
6. Record the topology in `state/current_company_state.md`.

### 3B — VPS becomes primary
1. Stop writers on the laptop (`06` §4 stop order).
2. Back up the laptop state (`05` §2) and record the report.
3. Migrate the state set from `01` §3 to the VPS; verify integrity + row counts.
4. Deploy modules/config/services on the VPS (Phase 2).
5. Resolve the interactive-token constraint (owner-approved service account) — otherwise the VPS is no better than the laptop.
6. Point the control plane at the VPS; keep the laptop as a read-only replica for a defined observation period.
7. Decommission the laptop's writer role only after the observation period passes.

## Phase 4 — Acceptance (must pass on the destination node)

See `09-acceptance-and-health-commands.md`. Minimum set:
service survives restart, E1 audit PASS, E2 gov-verify PASS, E3 DB verify PASS,
E4/E5 drills PASS, provider health PASS or truthful external-blocker state, one
text task end-to-end, one multi-worker task end-to-end, one image task
end-to-end, verifier rejection+repair path, provider failure/failover path,
owner escalation path.

## Phase 5 — Close-out

1. Update `state/current_company_state.md` to match deployed reality.
2. Write the final handover with commit SHAs and the evidence paths.
3. Keep the rollback window open for the agreed observation period (`08`).
4. Do **not** delete the laptop's state or backups until the observation period ends.

---

## What is knowingly incomplete (do not paper over)

| Gap | Owner/task |
|---|---|
| Log rotation/retention not implemented | operational-services task |
| Reboot persistence unverified for poller + Discord sync | owner reboot (actions item 6) |
| Battery gating blocks 7 of 8 tasks on battery | decision/topology (finding recorded) |
| Interactive-token tasks: no signed-out operation | owner-approved service account needed for unattended topology |
| No off-site backup | owner decision |
| Live-provider E4/E5 failover drill not built (`e4e5_drill_harness.py` has no `--live` mode) | recorded in actions item 8; acceptance question for the owner |
| VPS OS/runtime not discovered (no VPS login performed) | Phase 1.2 + Phase 3 |
