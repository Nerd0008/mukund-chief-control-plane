# 03 — Owner action TODO (exact order)

Consolidated single list of everything that genuinely needs Mukund, in the order
it should be executed. This is the deployment-package view; the authoritative
running list (with full context for every item) remains
`tasks-or-issues/overnight-owner-actions-2026-09-24.md`.

Estimated total for the critical path: **~45–60 minutes**, of which the seven
provider keys are ~30 minutes.

---

## Step 1 — Configure the seven provider credentials (the only blocking work)

```bash
# from the repository root, one command per worker; it prompts with no echo
python scripts/set_provider_key.py --worker mistral-small-4
python scripts/set_provider_key.py --worker glm-53-flash
python scripts/set_provider_key.py --worker qwen38-27b
python scripts/set_provider_key.py --worker longcat-2.0
python scripts/set_provider_key.py --worker minimax-m3
python scripts/set_provider_key.py --worker step-37-flash
python scripts/set_provider_key.py --worker tencent-hunyuan-hy3
```

- Why owner-only: provider accounts/billing and the key material are yours; no
  automation may create, hold or transmit them.
- Do **not** paste any key into chat, Discord, GitHub, a queue job or a file.
- Verify: `python scripts/set_provider_key.py --status` must show
  `credential_present: True` for all ten workers.

## Step 2 — Confirm the credential state, then run the post-key sequence

Full sequence, roles and expected results: `09-acceptance-and-health-commands.md`
and `overnight-owner-actions-2026-09-24.md` item 8. In order:

1. `python scripts/e3_credential_presence_probe.py` — expect 0/7 missing.
2. `python scripts/e3_stage2_readiness_gate.py` — expect readiness conditions MET.
3. `python scripts/evidence_runner.py --label post-keys-regression` — expect
   **438 collected / 438 passed / 0 failed / 0 errors / 0 skipped**, every suite
   exit 0 (15 suites; figure to beat as of 2026-09-24T23:55Z).
4. `python exec-brain/e3_execution_rehearsal.py` — bounded real-provider rehearsal.
5. `python exec-brain/e4e5_drill_harness.py` — expect 33/33, real provider calls 0.
6. Only then complete local E3 Stage 2.

Steps 1–6 are **engineering-run** once the keys exist; you only need to run step 1.
`TODO: 2026-09-24` — the queue executes these automatically after a verified
credential-state change (per the documented anti-loop rule).

## Step 3 — Deployment architecture decision (after local proof)

Choose one, in writing:

1. **Laptop primary + GitHub control plane + VPS watchdog/failover** (your
   recorded preference, not yet a decision), or
2. **VPS primary**, or
3. defer the whole topology question while local operation is the deliverable.

Blocks: every `PENDING OWNER DECISION` step in `07-cutover-runbook.md`. If you
pick (1) or (2), also supply the VPS host/account detail **outside GitHub**.

## Step 4 — VPS details (only if a VPS path is chosen)

Provide host/account access details locally. Do not place them in GitHub, chat,
logs or queue jobs.

## Step 5 — Owner-attended laptop security audit

Needed before the laptop is treated as a trusted production host. Two unexplained
visible UI events (`events near me` Edge search; a blank terminal window) must be
attributed first. Nothing was cleared or deleted; the correlation scope is
recorded in `overnight-owner-actions-2026-09-24.md` item 5.

## Step 6 — Reboot-persistence confirmation

After your next reboot, confirm `HermesRemoteQueuePoller` and `ChiefDiscordSync`
return to `Ready`/`Running` with an advancing next-run time. They currently have
no logon/boot trigger, so survival is unverified. If they do not come back, the
fix is a small, reversible logon-trigger addition (engineering).

## Step 7 — Optional, non-blocking decisions (answer whenever convenient)

| Item | Question | Recorded in |
|---|---|---|
| Tracker vocabulary | add `Assessment` / `Offer` (Dubai) / `Rejected` (Japan) statuses, or keep them as owner decisions? | owner-actions item 10 |
| Company/role research provider | name an approved source, or keep the cited-file path only? | item 11 |
| LinkedIn live account | keep the owner-export path (recommended), name another read-only source, or keep it owner-only forever? | item 13 |
| Career Daily Brief delivery | keep it local, or name a channel to deliver it to? | item 14 |
| Regional work authorisation (UAE / Japan / Singapore) | one line per region — sponsorship needed / no route / open | item 6 |
| Dubai + Japan discovery providers | add a regional provider, keep agent-driven search only, or park those lanes? | item 7 |
| Acceptance question | is the stubbed-failure E4/E5 drill (33/33) plus the real-path execution rehearsal enough for v1, or is a live-provider failover drill required before cutover? | item 8 |
| Legacy `Mukund Chief of Staff` task | disable/remove, or keep as a donor? | item 7 (legacy task) |

## What is explicitly NOT owner work

Ordinary engineering, scripting, testing, scheduling, integration, documentation,
acceptance preparation and deployment preparation are done by the build. If you
find yourself being asked to run a normal setup step, that is a bug in this list —
say so and it gets engineered instead.
