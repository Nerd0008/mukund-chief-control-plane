# 10 — Operational services (health, briefs, backup/retention, persistence)

Owner task: `agent-operational-brief-health-backup-persistence-2026-09-23`.
This is the **operational** layer that runs repeatedly on the primary node. The
one-shot cutover path stays in `01`–`09`; this document does not duplicate it.

Every command below was executed against the live system on 2026-09-24 and its
real result is recorded in
`audits/evidence/2026-09-24T02-49-47Z-operational-services-tests/` and the
per-command reports under `audits/evidence/2026-09-24T02-48-01Z-operational-services/`.

The single entry point is:

```bash
cd C:/Users/mukun/Documents/mukund-chief-control-plane
python scripts/operational_services.py <subcommand>
```

Subcommands: `health-snapshot`, `morning-brief`, `backup`, `validate-persistence`.

Safety properties shared by every subcommand: read-only against live state and
databases; no provider/network call; no credential *value* read (presence and
store name only); no scheduled task created, modified, started, stopped or
deleted. `backup` reads databases read-only and snapshots via the SQLite online
backup API.

---

## 1. Deterministic health snapshot (acceptance command)

```bash
python scripts/operational_services.py health-snapshot [--out-dir DIR] [--json]
```

Aggregates, in one machine-readable document: database existence + integrity +
size + table count (7 databases), queue state counts and task ids, scheduled-task
state, credential presence, E2 Daily Resource Brief generation, Career Daily
Brief availability, log sizes, and a failure-escalation list. Exit code is `0`
when nothing FAILs (an owner-gated ATTENTION such as missing provider keys does
not fail the snapshot), `1` on any FAIL.

- **Verified 2026-09-24: `verdict: ATTENTION`, `fail_count: 0`, 7/7 databases
  `integrity_check = ok`, 8/8 chief tasks present, credentials `configured=2
  missing=7` (truthful, owner-gated).**
- Output: `health_snapshot.json` + `health_snapshot.md` under the out-dir
  (default `audits/evidence/<stamp>-health-snapshot/`).

## 2. E2 Daily Resource Brief validation

The brief is generated deterministically (no LLM) from real governor state via
the live `governor.generate_brief(con)` path used by `eb brief`. The snapshot
records `renders`, `briefs_logged` and `unknown_preserved`.

- **Verified 2026-09-24: `renders=True`, `briefs_logged=3`,
  `unknown_preserved=True`.** Unobservable dimensions stay `unknown`; the brief
  never coerces an unobservable fact to a healthy/zero default.
- Honest gap: `governor.publish_brief()` exists but is **not wired to a CLI
  command** (`eb brief --publish` is not implemented at runtime), so
  `resource-status/latest-brief.md` is not yet produced by an operational run.
  Not claimed.

## 3. Morning Chief Brief

```bash
python scripts/operational_services.py morning-brief [--out-dir DIR] [--json]
```

Aggregates: E2 resource status, system health, active/blocked queue work, Career
Daily Brief availability, the exact owner actions parsed from
`tasks-or-issues/overnight-owner-actions-2026-09-24.md`, and a failure-escalation
section. Writes `latest.json` + `latest.md` (default `runtime/chief/morning-brief/`,
which is git-ignored — the brief is a derived aggregate regenerated each run).

- **Verified 2026-09-24: verdict `ATTENTION`; active queue work 4, blocked 12;
  17 recorded owner actions; 2 escalation items.**

## 4. Operational backup + retention

```bash
python scripts/operational_services.py backup [--snapshot-root DIR] [--keep N] \
    [--dry-run] [--rotate-logs] [--apply-logs]
```

- Snapshots the declared state set (7 SQLite databases + the E1/E2 chain-head
  JSON files) with the SQLite online backup API, verifies `PRAGMA
  integrity_check`, and records size + SHA-256 per artifact.
- **Snapshots are raw databases and are written outside the repository** — to
  `%LOCALAPPDATA%\hermes\backups\operational\snapshot-<stamp>\` by default. Only
  the aggregate report (hashes, sizes, verdicts) is publishable.
- Retention: keeps the newest `--keep` (default 7) `snapshot-*` directories and
  removes only older ones **inside that root**; nothing outside it is ever
  touched.
- `--dry-run` plans without writing (verified: wrote nothing).
- Restore procedure: see `05-backup-and-restore-plan.md` §3. This service never
  restores over live state.

- **Verified 2026-09-24: `status: PASS`, 0 failure labels; retention proven
  (a second run with `--keep 1` pruned the first snapshot); snapshot located
  outside the repo.**

## 5. Log rotation / retention

The gap recorded in `06-service-definitions.md` §5 (no rotation for
`hermes\logs`, `gateway-starts.log`, `remote-queue\logs\queue.log`) is now
covered by `backup --rotate-logs` (plan) / `--apply-logs` (apply):

- a log is rotated only once it passes 5 MB; the live log is copied to an
  archive and truncated **only when it can be opened for writing**; a
  service-held log is recorded as `skipped_locked` rather than forced;
- the archive set is pruned to the newest 5 copies;
- `--rotate-logs` without `--apply-logs` is a plan and changes nothing.

## 6. Scheduler / boot persistence validation

```bash
python scripts/operational_services.py validate-persistence [--out-dir DIR] [--json]
```

Read-only. Records, per task: enabled state, triggers, logon type, battery
settings, `StartWhenAvailable`, restart-on-failure, last result and next run
time, plus a `survives_boot` verdict and the exact owner checklist.

- **Verified 2026-09-24 — recorded, nothing changed:**
  - `Hermes_Gateway`: logon trigger + `StartWhenAvailable` → survives boot.
  - `HermesRemoteQueuePoller`, `ChiefDiscordSync` and the four
    `ChiefCareerScan-*` + `ChiefCareerBrief` (7 tasks total): time/calendar
    triggers, **no** boot/logon trigger, `StartWhenAvailable` not set →
    **persistence after a reboot is UNVERIFIED**. The exact remediating action
    (a small, reversible logon-trigger re-import) is item 6 in
    `tasks-or-issues/overnight-owner-actions-2026-09-24.md`.
  - 7 of 8 tasks set `DisallowStartIfOnBatteries` → will not run on battery.
  - All 8 run under the interactive user token → they do not run for a
    signed-out user.
  - Legacy `Mukund Chief of Staff` task: recorded, **not** touched (its
    disposition is an owner decision).

## 7. Remaining truthful gaps

- **Reboot persistence is verified by configuration, not by a reboot** — a
  reboot is prohibited by this task's stop conditions, so the finding is
  "configured to survive" for the gateway and "unverified" for the other seven,
  never a claimed PASS.
- **No off-site backup exists** (see `05` §5); the destination is an owner
  decision.
- **E2 brief publication to `resource-status/` is not wired** (§2).
- Log rotation is implemented but **not yet scheduled**; scheduling it is a
  small engineering step, not an owner blocker.
