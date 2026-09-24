# Built-but-not-live integration gap audit

- Task: `agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24`
- Generated (UTC): 2026-09-24T22:42:40+00:00
- Code SHA: `47899c2cd45a8551ca22b89d8943e92ee6792502`
- Read-only: every figure below was measured from live runtime/repository state.
- A fixture/dry-run pass is **never** recorded as a live PASS.

## Integration items

| # | Item | Measured state | Live PASS | Owner-gated |
|---|---|---|---|---|
| 1 | Gmail read-only OAuth live feed (B12 Application Inbox) | READY_NEEDS_OWNER_CONFIG | no | yes |
| 2 | JobBrief company/role research provider (B14) | READY_NEEDS_OWNER_CONFIG | no | yes |
| 3 | Live recruiter/intermediary feed (B11) | FIXTURES ONLY | no | yes |
| 4 | Career Daily Brief external delivery channel (B23) | LOCAL ONLY, external_channel_health = not_verified | no | yes |
| 5 | Tracker vocabulary gaps (Assessment / Japan Rejected / Dubai Offer) | OWNER DECISION PENDING | no | yes |
| 6 | Current-month tracker rollover policy (owner-state rows) | REFUSED, NOT DELETED | no | yes |
| 7 | Owner company watchlist names | AWAITING_OWNER_INPUT | no | yes |
| 8 | UAE / Japan provider coverage | OWNER DECISION PENDING | no | yes |
| 9 | LinkedIn live account OAuth/publishing integration | READY_NEEDS_OWNER_CONFIG | no | yes |
| 10 | Off-machine backup destination | OPEN | no | yes |
| 11 | Owner-attended laptop trust audit | OPEN | no | yes |
| 12 | Final deployment topology / VPS decision | OPEN | no | yes |
| 13 | Live-provider E4/E5 evidence | OPEN | no | yes |

## Exact next owner step per open item

- **gmail-readonly-oauth** — Optionally authorise a read-only Gmail OAuth grant (about 10 minutes) following the recorded steps in the owner-action TODO; until then the monitor runs on an owner-provided local export.
- **research-provider** — Optionally name an approved research source, or keep the cited-file path only.
- **recruiter-live-feed** — Optionally provide a read-only export or name a source.
- **career-brief-delivery** — Optionally name a delivery channel, or keep it local.
- **tracker-vocabulary** — Optionally extend the relevant tracker validation lists.
- **monthly-rollover-policy** — Optionally decide the rollover disposition for those owner-state rows.
- **owner-watchlist-names** — Optionally supply the short target-company list at runtime/career-ops/watchlist/company-watchlist.json (owner-edited, git-ignored); the lane stays honest and empty until then.
- **dubai-japan-provider-coverage** — Optionally choose to add a regional provider, keep the agent-driven search path only, or park a region.
- **linkedin-live-account** — To go live: create a LinkedIn developer app, store the client id/secret + a member OAuth token/refresh token in Windows Credential Manager under the chief-linkedin-* targets (never in chat, GitHub or logs), then publish a reviewed draft with an explicit approval + confirm-token. Dry-run is the default and nothing posts without that owner approval.
- **offsite-backup-absent** — Choose the off-site backup destination and retention, then authorise engineering to implement it (local backup/restore is already drilled and passing).
- **laptop-trust-audit** — Perform the recorded audit with Mukund present. Do not clear Edge/shell/Windows Event/Task Scheduler/Defender/Hermes logs or browser artifacts before attribution.
- **deployment-cutover-decision** — Record one written line choosing the deployment architecture, and supply VPS host/account details locally if a VPS path is chosen.
- **live-provider-failover-gap** — Decide whether the stubbed-failure drills (36/36) plus the real-path execution rehearsal are sufficient E4/E5 evidence for v1, or whether a live-provider failover drill is required before cutover. The harness has no live-provider mode and the real provider-health probe is not wired; both are deliberately out of the recorded scope.

## Operational hardening (this task)

| Fact | State |
|---|---|
| battery-gating | RESOLVED (applied + verified live) |
| ops-scheduling-cadence | SCHEDULED (owner-approved) — verified live |
| legacy-chief-task | DISABLED (verified live; kept as rollback donor, not deleted) |
| log-rotation-retention | IMPLEMENTED (dry-run then bounded apply evidenced) |
| reboot-persistence-unconfigured | CONFIGURED — reboot itself still UNVERIFIED (owner action) |

### Reboot persistence detail

StartWhenAvailable is set and StopOnIdleEnd cleared on the owned tasks; the two light periodic tasks (queue poller, Discord sync) additionally carry a logon trigger. No reboot was performed (prohibited).

Owner acceptance checklist: `deployments/11-owner-reboot-acceptance-checklist.md`.
