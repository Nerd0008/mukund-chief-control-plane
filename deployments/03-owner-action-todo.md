# 03 — Owner action TODO (live priority order)

This is the concise list of what genuinely still needs Mukund. Detailed history remains in
`tasks-or-issues/overnight-owner-actions-2026-09-24.md`.

Last reconciled against live repository state and the post-hardening integration-gap audit:
`audits/evidence/2026-09-24T22-37-43Z-post-stage2-integration-gap-audit/audit.md`.

## A. Do now — blocks E3 Stage 2

### 1. Provider accounts: make the seven stored credentials actually serve traffic

Credentials are already present. The remaining work is provider-side account activation,
billing/quota/entitlement, plus a fresh Tencent TokenHub key.

Work **one provider at a time** in this order:

1. **Tencent TokenHub / Hy3**
   - revoke the previously exposed TokenHub key;
   - confirm TokenHub / Hy3 activation and required PAYG/billing;
   - create a fresh TokenHub key;
   - store it locally only with `python scripts/set_provider_key.py --target hunyuan`;
   - test `GET /v1/models`; only if HTTP 200, run one bounded `hy3` smoke.
2. **Qwen / Alibaba** — enable/purchase entitlement for `qwen3.7-plus`.
3. **GLM / Z.ai** — add the minimum usable API balance/resource package.
4. **LongCat** — add/activate minimum token quota.
5. **MiniMax** — add minimum usable API balance.
6. **StepFun** — enable/add minimum quota/PAYG billing.
7. **Mistral** — inspect billing/account tier/usage limits causing the 429, then make one bounded smoke only after an account-side change.

Do not paste keys into chat, GitHub, Discord, logs or queue JSON. Provider console work uses
the already-open Firefox tabs.

**After each owner-side fix:** engineering/Codex verifies credential presence, model identity and
exactly one bounded smoke. Do not rerun every provider after each fix.

### 2. Decide the Google-image Stage-2 criterion — only after the text providers are green

Observed evidence: 9 real image calls, 7 valid images, 2 provider-side
`IMAGE_RECITATION` stops.

Owner decision after provider setup:
- keep zero-intermittency as a hard Stage-2 requirement and investigate further; or
- approve a formally specified bounded retry/fallback policy and re-scope the criterion.

Do not weaken the criterion merely to turn the gate green.

### 3. Decide the E4/E5 acceptance standard before final cutover

Current evidence is truthful but limited:
- E4/E5 stubbed-failure drill: PASS;
- real-path execution rehearsal: PASS;
- real provider outage -> real equivalent-worker failover: **not yet exercised**.

Choose one:
- accept the current stubbed-failure drill + real-path rehearsal for v1; or
- require a bounded live-provider failover drill before cutover.

Once Steps 1–3 are resolved, engineering owns the regression, rehearsal and readiness-gate reruns.
Mukund should not need to manually run ordinary verification commands.

---

## B. Owner actions needed before treating the laptop as production

### 4. Owner-attended laptop trust/security audit

Two unexplained visible UI events remain unattributed (an Edge `events near me` search and a blank
terminal window). Do not clear Edge history, shell history, Windows Event Logs, Task Scheduler history,
Defender history, Hermes logs or related artifacts before the audit.

This is required before the laptop is treated as a trusted production host.

### 5. Reboot-persistence confirmation

Task configuration is hardened and reports no known reboot-configuration gap, but no reboot has been
observed.

After the next owner-initiated reboot, use:
`deployments/11-owner-reboot-acceptance-checklist.md`

Engineering must not reboot the laptop autonomously.

### 6. Choose an off-machine/off-site backup destination and retention

Local backup/restore is implemented and drilled, but no off-machine backup exists.

Choose a destination and retention policy, then authorise engineering to wire it. This is required
before claiming resilient production deployment.

### 7. Final deployment topology — deferred until local Stage 2 is proven

Current preference is recorded but is **not** a final decision:

- laptop primary + GitHub control plane + VPS watchdog/failover; or
- VPS primary; or
- keep local-only for now.

Only provide VPS host/account details locally if a VPS path is actually chosen.

---

## C. Career Ops owner setup — useful, but does not block Stage 2

### 8. Gmail read-only OAuth

The Application Inbox monitor is built; the live Gmail feed still needs your one-time read-only OAuth
grant. Until then it can use owner-provided local exports.

Follow the recorded Gmail instructions in the long owner-action file. The grant must remain read-only.

### 9. Supply the priority-company watchlist

The Company Watch lane is built but intentionally empty until you provide the target company names.

Owner-edited runtime target:
`runtime/career-ops/watchlist/company-watchlist.json`

### 10. Decide tracker vocabulary

Choose whether to add:
- `Assessment`;
- Dubai `Offer`;
- Japan `Rejected`;

or keep those events as explicit owner decisions.

### 11. Decide monthly-rollover handling for owner-state rows

The system currently refuses to delete or silently roll owner-state rows. Choose the rollover
disposition/policy; until then those rows stay preserved.

### 12. Dubai/Japan discovery coverage

Choose one per region:
- add a regional provider/source;
- keep the existing agent-driven search path only; or
- park that regional scan.

### 13. Application work-authorisation questions are not a proactive TODO

Do **not** add visa/sponsorship/right-to-work wording to generated materials or surface it as a routine
owner task. Only handle it when an application/employer explicitly asks, and answer from accurate
owner-grounded facts at that point.

---

## D. Optional integrations — only if Mukund wants them live

### 14. LinkedIn live publishing

The official OAuth/publishing path is built and remains `READY_NEEDS_OWNER_CONFIG`.
If live publishing is wanted, create/configure the LinkedIn developer app and store credentials only
in local secret storage. Publishing still requires explicit owner approval for the exact draft.

Keeping LinkedIn as draft/review-only is a valid final choice.

### 15. Company/role research provider

Either name an approved research source or keep the cited-file/manual research path only.

### 16. Live recruiter/intermediary feed

Either provide a read-only export/source or leave the fixture/local-input path as-is.

### 17. Career Daily Brief delivery

Choose a delivery channel, or explicitly keep the brief local. Local generation/scheduling already works.

### 18. Legacy `Mukund Chief of Staff` task

It is currently **Disabled** and preserved as a rollback donor. No action is needed now.
Decide later whether to keep it indefinitely or delete it after Hermes is fully accepted.

---

## Already done — no owner action

- Provider credential storage: 10/10 present.
- E1 and E2 active/verified.
- E3 implemented/verified.
- Clean regression baseline: 22 suites / 606 collected / 606 passed.
- Battery gating removed from affected tasks.
- Unattended task hardening applied while preserving user-scoped credential access.
- Operational backup, log rotation, morning brief and health snapshot schedules registered.
- Log rotation/retention implemented.
- Career scheduled cutover accepted.
- LinkedIn OAuth/publish code path built (not live).
- Legacy Chief task disabled, not deleted.
- Hardening successor worker completed.
- E3 Stage 2 remains OFF until the objective gates pass.
