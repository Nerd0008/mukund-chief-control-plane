# 02 — Secret, account and admin checklist

Every credential, account grant and admin action the deployment needs, listed
**by name only**. No value, token, cookie or password appears in this document
and none may ever be added to it.

Verification for every row is presence-only and makes no provider call:

```bash
python scripts/set_provider_key.py --status   # all 10 roster workers
python scripts/e3_credential_presence_probe.py       # the 7 API workers, 3 independent presence paths
```

---

## A. Owner-provisioned provider API keys (7 outstanding)

Storage rule: Windows Credential Manager, generic credential, target name exactly
as below. The env var is only a fallback; Credential Manager wins. Storage
method: `python scripts/set_provider_key.py --worker <id>` (prompts with
no echo, keeps the key out of shell history entirely).

| # | Worker id | Credential Manager target | Env var fallback | Provider signup/console |
|---|---|---|---|---|
| 1 | `mistral-small-4` | `mistral` | `MISTRAL_API_KEY` | Mistral console → API keys |
| 2 | `glm-53-flash` | `glm` | `GLM_API_KEY` | Zhipu/BigModel open platform |
| 3 | `qwen38-27b` | `qwen` | `DASHSCOPE_API_KEY` | Alibaba DashScope (Model Studio) |
| 4 | `longcat-2.0` | `nous` | `NOUS_API_KEY` | Nous inference API |
| 5 | `minimax-m3` | `minimax` | `MINIMAX_API_KEY` | MiniMax platform |
| 6 | `step-37-flash` | `stepfun` | `STEP_API_KEY` | StepFun platform |
| 7 | `tencent-hunyuan-hy3` | `hunyuan` | `HUNYUAN_API_KEY` | Tencent Cloud Hunyuan |

Do **not** rename these targets or env vars to "better" names: the code resolves
exactly these strings (`generic_openai_adapter.PROVIDER_CONFIGS`), and a
different name resolves to "no credential".

Billing/account note: each of these needs its own provider account and, where the
provider requires it, credit/quota. That is an owner financial decision — the
build will not select plans or spend on the owner's behalf.

## B. Already-provisioned credentials (verified present 2026-09-24)

| Credential | Credential Manager target | Env var | Present |
|---|---|---|---|
| DeepSeek API key (DeepSeek worker + Hermes primary brain) | `deepseek` | `DEEPSEEK_API_KEY` | yes |
| Google Gemini API key (image worker) | `gemini-api` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `GOOGLE_GENERATIVE_AI_API_KEY` | yes |
| Codex CLI login | n/a — CLI-managed ChatGPT auth (mode `chatgpt`) | n/a | yes |
| GitHub push access | `gh:github.com`, `gh:github.com:Nerd0008` | n/a | yes |

Related non-secret config (safe to read, no values in it):
`%LOCALAPPDATA%\hermes\exec-brain\deepseek-config.json` holds only the
`spending_budget_usd` budget and an explicit "do NOT put your API key here" note.

## C. OAuth / account grants (owner-only consent screens)

| Item | Status | Where the artifact must live (outside the repo) |
|---|---|---|
| Gmail read-only monitor (Application Inbox) | PENDING — owner OAuth | `C:\Users\mukun\AppData\Local\hermes\secrets\gmail-readonly\credentials.json` and `token.json` (scope `gmail.readonly` only; env overrides `CHIEF_GMAIL_CREDENTIALS`, `CHIEF_GMAIL_TOKEN`) |
| LinkedIn live account access | PENDING — owner decision (recommended: keep the owner-export path) | none — the runtime deliberately holds no LinkedIn credential |
| Research provider for JobBrief company facts | PENDING — owner decision | none yet; cited-file path works today |

Details and exact steps for these are in
`tasks-or-issues/overnight-owner-actions-2026-09-24.md` (items 9, 13, 11).

## D. Destination-node secret provisioning (for the eventual cutover)

Rule (applies to either topology, and required by the authority file): secrets go
into the **destination node's own secret store or service environment** — never
into GitHub, never into the repository, never into a queue job payload.

| Secret name | Laptop (current) | VPS (if that topology is chosen) |
|---|---|---|
| 7 provider API keys | Windows Credential Manager targets in §A | VPS-local secret store / service env file with `0600` perms outside the repo — `PENDING OWNER DECISION` on the mechanism |
| DeepSeek key | Credential Manager `deepseek` | same rule |
| Gemini key | Credential Manager `gemini-api` | same rule |
| GitHub token for the queue | Credential Manager `gh:github.com*` | a fine-grained PAT scoped to this repo only, stored in the VPS secret store |
| Hermes platform credentials (Discord) | `%LOCALAPPDATA%\hermes\auth.json` (must never be copied into the repo) | re-issued/rotated on the VPS rather than copying the laptop's file |
| Gmail OAuth client + refresh token | outside repo, per §C | re-authorise on the VPS if the monitor moves |

Never do any of these: commit a key, paste a key into chat/Discord/GitHub/queue,
put a key in `deepseek-config.json`, print a key in evidence/logs, or leave a key
in shell history.

## E. Admin actions on the destination node

| Action | Why | Status |
|---|---|---|
| Confirm the machine stays powered and signed in for the build window | every Chief task is `InteractiveToken` and only runs while signed in | owner-side precondition (already recorded) |
| Decide the disposition of the legacy `Mukund Chief of Staff` logon task | it starts the superseded Telegram/API/tunnel stack at sign-in | PENDING OWNER DECISION — not changed |
| Authorise the owner-attended laptop security audit | two unexplained UI events need attribution before the laptop is trusted as a production host | DEFERRED to an owner-attended session |
| Firewall: outbound 443 allow, inbound deny | only requirement identified; no inbound listener exists | to apply at cutover |
| Reboot-persistence confirmation | `Hermes_Gateway` has a logon trigger; the poller and Discord sync have time triggers only, so reboot survival is **unverified** | owner-initiated reboot required; cannot be forced by this task |
| VPS host/account details | needed only if the VPS topology is chosen | PENDING OWNER DECISION |

## F. What is deliberately absent

- No secret value anywhere in `deployments/`, in evidence reports, or in git.
- No credential was created, read out, rotated or transmitted by this task.
- No `.env` file, key file or token file was created for any provider.
