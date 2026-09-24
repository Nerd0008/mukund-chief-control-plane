# 03 — Owner action TODO (exact order)

Consolidated single list of everything that genuinely needs Mukund, in the order
it should be executed. This is the deployment-package view; the authoritative
running list (with full context for every item) remains
`tasks-or-issues/overnight-owner-actions-2026-09-24.md`.

Last reconciled: 2026-09-24 (task
`agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24`)
against measured live state. See
`audits/evidence/2026-09-24T22-37-43Z-post-stage2-integration-gap-audit/audit.md`
for the built-but-not-live gap audit behind this list.

Estimated total for the critical path: **~45–60 minutes**, of which the provider
account funding step is ~30 minutes.

---

## Resolved since the previous revision (no owner action needed)

- **Provider credentials** — all ten roster credentials are present (10/10,
  verified 2026-09-24T20:54:33Z). No key value was read, logged or committed.
- **Battery gating** — removed from all seven affected tasks; every owned task
  now also has `StartWhenAvailable`, `StopOnIdleEnd` cleared, and the two light
  periodic tasks have a logon trigger. Reversible backups exist.
- **Operational services scheduling** — backup (02:30), log rotation (03:00),
  morning brief (06:30) and health snapshot (08:00) are registered and Enabled,
  local artifacts only.
- **Log rotation/retention** — implemented and evidenced over every declared
  live log path.
- **Legacy `Mukund Chief of Staff` task** — confirmed `Disabled` and kept in
  place as a rollback donor (not deleted).
- **LinkedIn publishing path** — now built (OAuth + owner-gated publish). It
  needs credentials before it can go live (see Step 8).

---

## Step 1 — Fund / enable the seven provider accounts so the stored keys serve traffic

The keys are configured; the accounts refuse live dispatch. Verified errors
(provider-side, no further narrowing possible from here):

- mistral — HTTP 429 `Rate limit exceeded`
- GLM / Z.ai — HTTP 429 `Insufficient balance or no resource package`
- Qwen (intl dashscope) — HTTP 403 `AccessDenied.Unpurchased` on `qwen3.7-plus`
  (purchase/enable that model id for this account)
- LongCat — HTTP 402 `Insufficient token quota`
- MiniMax — HTTP 402 `insufficient balance (1008)`
- StepFun (global) — HTTP 402 `exceeded your current quota`
- Tencent Hunyuan/Hy3 — HTTP 401 `code 401002`; re-issue a TokenHub key at
  https://console.tencentcloud.com/tokenhub/apikey

- Why owner-only: provider accounts/billing and the key material are yours; no
  automation may create, hold or transmit them.
- Do **not** paste any key into chat, Discord, GitHub, a queue job or a file.
- Verify: `python scripts/set_provider_key.py --status` (expect 10/10 present),
  then `python scripts/e3_provider_bounded_smoke.py`.
- Full per-provider detail: `overnight-owner-actions-2026-09-24.md` item 1b.

## Step 2 — Post-key verification sequence (engineering-run)

The sequence already ran once (2026-09-24) and Stage 2 was **not** enabled
because a recorded readiness criterion is unmet and every newly-credentialed
provider refused live dispatch. Re-run after Step 1:

1. `python scripts/e3_credential_presence_probe.py` — expect 0/7 missing.
2. `python scripts/e3_stage2_readiness_gate.py` — expect readiness conditions MET.
3. `python scripts/evidence_runner.py --label post-keys-regression` — every suite
   must pass; the figure to beat is recorded in
   `overnight-owner-actions-2026-09-24.md` item 8.
4. `python exec-brain/e3_execution_rehearsal.py` — bounded real-provider rehearsal.
5. `python exec-brain/e4e5_drill_harness.py` — expect the full drill pass with
   `real_provider_calls = 0` (it has no live-provider mode by design).
6. Only then complete local E3 Stage 2.

Steps 1–6 are **engineering-run** once Step 1 is done. Two remaining
owner decisions also gate Stage 2: the Google-image criterion (item 2b) and the
live-provider E4/E5 acceptance question.

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

**Updated 2026-09-24:** all eleven owned tasks now carry `StartWhenAvailable` and
the two light periodic tasks carry a logon trigger, so they are *configured* to
survive a reboot (read-only assessment: `unverified_after_reboot = []`).
Engineering must not reboot your laptop, so the reboot itself is still
unobserved. Run the short checklist after your next reboot:
`deployments/11-owner-reboot-acceptance-checklist.md`.

## Step 7 — Optional, non-blocking decisions (answer whenever convenient)

| Item | Question | Recorded in |
|---|---|---|
| Tracker vocabulary | add `Assessment` / `Offer` (Dubai) / `Rejected` (Japan) statuses, or keep them as owner decisions? | owner-actions item 10 |
| Company/role research provider | name an approved source, or keep the cited-file path only? | item 11 |
| LinkedIn live account | create a LinkedIn app + store OAuth credentials (Step 8), or keep drafting/review only? | item 13 |
| Career Daily Brief delivery | keep it local, or name a channel to deliver it to? | item 14 |
| Regional work authorisation (UAE / Japan / Singapore) | one line per region — sponsorship needed / no route / open | item 6 |
| Dubai + Japan discovery providers | add a regional provider, keep agent-driven search only, or park those lanes? | item 7 |
| Acceptance question | is the stubbed-failure E4/E5 drill plus the real-path execution rehearsal enough for v1, or is a live-provider failover drill required before cutover? | item 8 |
| Company watchlist | supply your short target-company list, or leave the lane empty? | `runtime/career-ops/watchlist/company-watchlist.json` |
| Off-machine backup | choose a destination + retention, or accept local-only backup for now? | owner-actions (deployment-time facts) |
| Legacy `Mukund Chief of Staff` task | it is now `Disabled` and kept as a donor; confirm whether it should eventually be removed | item 7 (legacy task) |

## Step 8 — Optional: take the LinkedIn publishing path live

The owner-authenticated publishing path is **built but not live** — no LinkedIn
app or OAuth credential set exists, so nothing can be (and was not) published.

1. Create a LinkedIn developer app; request the `openid profile w_member_social`
   scopes through the official API path (do not bypass LinkedIn review).
2. Store the client id, client secret and a member access/refresh token in
   Windows Credential Manager under the `chief-linkedin-*` targets (never in
   chat, GitHub, a queue job or a log).
3. `python career-ops/linkedin_auth.py status` must then report them present.
4. Authorise one specific post: publishing needs both an owner approval flag and
   a confirm-token equal to the sha256 of the exact draft body. Dry-run is the
   default; duplicates are refused against a local body-hash ledger.

See `career-ops/linkedin-live-publish.md`.

## What is explicitly NOT owner work

Ordinary engineering, scripting, testing, scheduling, integration, documentation,
acceptance preparation and deployment preparation are done by the build. If you
find yourself being asked to run a normal setup step, that is a bug in this list —
say so and it gets engineered instead.
