# LinkedIn live-account publish integration

Owner task: `agent-post-stage2-integrations-and-production-hardening-successor-2026-09-24`.
State recorded on 2026-09-24: **IMPLEMENTED AND DRILL-TESTED, NOT YET LIVE —
READY_NEEDS_OWNER_CONFIG.**

## 1. What changed

Before this task the whole LinkedIn layer (B19/B20/B21) was read-only plus
drafts. Generation and review were complete; account access did not exist, and
no code path performed a mutation.

This adds the missing credential/token and publish surfaces **next to** the
existing generators, and nothing else:

| File | Role |
|---|---|
| `career-ops/linkedin_workflow.py` | unchanged generation/review path (intake, dedupe, draft, handoff). `guard` still refuses `post`; `publish` resolves the draft artefact and delegates; `publish-status` reports availability. |
| `career-ops/linkedin_publish.py` | **the publish path** — official REST API, owner-approval gate, duplicate prevention, bounded retries, dry-run. |
| `career-ops/linkedin_auth.py` | OAuth 2.0 credential/token layer, Windows Credential Manager storage, presence-only `status`. |
| `career-ops/linkedin_workflow.json` | declares the one implemented mutation and names every action that stays refused. |

Generation stays fully independent of publishing: Hermes can research, generate
and review posts with no credential present, which is exactly the state today.

## 2. The gates on a real publish

All of these are evaluated before a single byte is sent. Any failure refuses and
records the refusal.

1. **Credentials present** — client id + client secret + refresh token resolve
   from the credential store.
2. **Explicit owner approval** — `--approve-publish` *and* `--confirm-token`
   equal to the SHA-256 of the exact draft body. The approved action therefore
   names the approved bytes; a draft edited after approval cannot be published by
   mistake.
3. **The draft passed review** — the B20 artefact's `blocked` flag and fact-gate
   verdict are honoured; a blocked draft is never publishable.
4. **Not a duplicate** — the body hash is checked against a local ledger of
   everything already published (`runtime/linkedin/published/posts.jsonl`).
5. **Dry-run by default** — without the flags the command plans, prints the exact
   request it would send (never the token) and spends zero network calls.

Result accounting: post URN, post URL, timestamp, HTTP status, attempt list and
body hash are recorded. The token and client secret are never recorded.

Retries are bounded (default 2) and apply **only** to transport errors, 429 and
5xx. A 4xx — authorization, permission, validation — is never retried: it is a
deterministic answer, not a transient one.

## 3. What is deliberately still refused

`comment`, `reaction`, `follow`, `connection_request`, `message`, `inmail`,
`apply`, `easy_apply`, `profile_update`, `headline_update`, `about_update`,
`account_settings`, `delete_account`, `job_save`.

There is no implementation for any of them, and no path that performs them.
Messages, connections, applications and profile edits keep their existing guards.

Also never used anywhere in this integration: browser automation or GUI control,
browser session/cookie reuse, CAPTCHA bypass, and scraping behind
authentication. The owner opens the authorization URL in whatever client he
chooses; this code never launches one.

## 4. Running it

```bash
# 0. availability, spending no call
python career-ops/linkedin_workflow.py publish-status

# 1. owner: create a LinkedIn app, then store the app credentials (no echo)
python career-ops/linkedin_auth.py set-client-id
python career-ops/linkedin_auth.py set-client-secret

# 2. owner: print the authorization URL, open it yourself, approve the scopes
python career-ops/linkedin_auth.py authorize-url

# 3. owner: paste the redirected URL back; the code is exchanged and stored
python career-ops/linkedin_auth.py exchange --callback-url "<redirected url>"

# 4. review the exact request that would be sent
python career-ops/linkedin_workflow.py publish --run <draft-stamp> --index 0 \
    --approve-publish --confirm-token <sha256 of the draft body> --dry-run

# 5. the real, explicitly approved publish (posts only)
python career-ops/linkedin_workflow.py publish --run <draft-stamp> --index 0 \
    --approve-publish --confirm-token <sha256 of the draft body>
```

Scopes requested: `openid profile w_member_social`. `w_member_social` is the
scope LinkedIn requires to publish a member post, and it is granted per app — a
LinkedIn app that has not been approved for it will fail at the provider, not
here.

## 5. Owner setup steps (the remaining blocker)

1. Create a LinkedIn app in the LinkedIn Developer Portal.
2. Add the redirect URI you intend to use (default in the tool:
   `https://localhost:8443/linkedin/callback`) and note the client id/secret.
3. Request the **"Share on LinkedIn"** product (`w_member_social`) for the app.
   App review is a LinkedIn-side step; it is the external-provider blocker.
4. Run steps 1–3 above. Then `python career-ops/linkedin_auth.py status` must
   report `oauth_ready: true`, and `publish-status` must report
   `LIVE PATH CONFIGURED`.
5. Only then does a real publish become possible — and it still requires the
   per-action approval described in §2.

## 6. Evidence and honest limits

`audits/evidence/2026-09-24T22-35-00Z-linkedin-live-publish-integration/`:

* `auth_status.json`, `publish_status.json`, `workflow_publish_status.json` —
  presence-only credential state (all four absent) and the refused-action list;
* `guard_post.json`, `guard_message.json` — the guard's refusal text, which now
  names the approved action for `post` and keeps every other mutation refused;
* `draft_run.json` — a real B20 draft run produced from the canonical CV text,
  with the install's fact gate passing;
* `plan_no_approval.json`, `plan_approved_no_credentials.json`,
  `publish_dry_run.json`, `publish_real_attempt.json`,
  `workflow_publish_dry_run.json`, `live_drill_summary.json` — the drill.

**Not claimed:**

* this integration has **not** been verified against the real LinkedIn account;
* a dry-run or fixture test passing is **not** a live PASS — the recorded state
  stays `READY_NEEDS_OWNER_CONFIG` until a real owner-approved publish happens;
* LinkedIn app review / product approval is not something this system can do.

## 7. Rollback / no-go

* Rollback is deletion of the three files plus the config keys; nothing else in
  the system depends on them, and generation/review keep working unchanged.
* No-go criteria: if the app cannot be granted `w_member_social`, publishing
  stays unavailable and the drafts-only path continues — that is the documented
  fallback, not a failure.
* To remove stored credentials: `python career-ops/linkedin_auth.py clear --clear
  client_id --clear client_secret --clear refresh_token --clear access_token`.
