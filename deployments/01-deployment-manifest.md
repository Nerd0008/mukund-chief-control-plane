# 01 — Deployment manifest

Status: **prepared, topology-neutral**. Topology-specific steps are marked
`PENDING OWNER DECISION` and must not be executed until the owner chooses an
architecture and authorises cutover.

Every fact below was read from the live machine on 2026-09-24 (see
`inventory-2026-09-24T02-13-33Z.json` and the preflight report). Nothing here is
inferred, and no credential value appears anywhere.

---

## 1. Host / runtime identity

| Item | Value |
|---|---|
| Platform | Windows 11 (`Windows-10-10.0.26200-SP0`), AMD64 |
| Shell for all commands in this package | git-bash (MSYS POSIX), **not** PowerShell |
| Repository (source of truth) | `C:\Users\mukun\Documents\mukund-chief-control-plane` |
| Live runtime root | `C:\Users\mukun\AppData\Local\hermes\exec-brain` |
| Hermes root | `C:\Users\mukun\AppData\Local\hermes` |
| Python the runtime actually uses | `C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` — **3.11.16** |
| Node runtime (Hermes) | `v22.23.2` bundled at `%LOCALAPPDATA%\hermes\node` |
| Codex CLI worker | `%LOCALAPPDATA%\OpenAI\Codex\bin\80f78947ad880e6e\codex.exe` — `0.155.0-alpha.16.3` (hash path is version-scoped; resolve it, never hardcode) |
| Git remote | `Nerd0008/mukund-chief-control-plane` (private) |

Guard rail: a bare `python` on `PATH` is 3.11.16; `python3` is 3.14.6. **Always
invoke the venv interpreter path explicitly** in services and runbooks. Running
the runtime under 3.14 is not a supported configuration.

---

## 2. Deployable artifacts

| Artifact | Source | Destination | Notes |
|---|---|---|---|
| E3 module set (34 files) | `exec-brain/` in the repo | `%LOCALAPPDATA%\hermes\exec-brain\` | Deployed by `scripts/deploy_e3_runtime.py`; every overwrite is backed up first |
| `eb.py` (E1/E2 CLI host) | runtime root only | — | patched in place once to register `e3-*` subcommands; pre-patch copy is backed up |
| Hermes runtime + config | `%LOCALAPPDATA%\hermes` | — | `config.yaml`, `auth.json`, `skills/`, `plugins/`, `cron/`, `memories/` |
| Career Ops runtime | `career-ops/` in the repo + `runtime/career-ops/` | — | Python/openpyxl; no Excel COM/`artifact-tool` dependency |
| Company Watch runtime | `company-watch/` + `runtime/company-watch/` | — | owner-private data is gitignored |
| LinkedIn / CV workflow | `runtime/linkedin/`, `runtime/career-ops/cv-drafts/` | — | owner-private, gitignored |
| Remote queue + poller | `remote_queue/`, `remote-queue/` | — | GitHub is the control plane; the poller drives it |
| Gateway service wrapper | `%LOCALAPPDATA%\hermes\gateway-service\Hermes_Gateway.vbs` | — | started by the `Hermes_Gateway` task |

Deployment/rollback of the E3 module set is atomic-ish and reversible:

```bash
python scripts/deploy_e3_runtime.py --dry-run          # plan only, writes nothing
python scripts/deploy_e3_runtime.py                    # deploy, backs up first
python scripts/deploy_e3_runtime.py --restore <backup-dir>   # byte-for-byte rollback
```

`deploy_e3_runtime.py` refuses any file whose name matches a secret pattern and
never touches `governor.py`, `governor.db`, `exec_brain.db` or (beyond the
`e3-*` registration patch) `eb.py`.

---

## 3. State that must be deployed / migrated

Databases (all verified `PRAGMA integrity_check = ok` on 2026-09-24):

| State | Path | Role | Migrate? |
|---|---|---|---|
| E1 audit DB | `%LOCALAPPDATA%\hermes\exec-brain\exec_brain.db` | E1 classifications, hash chain | **Yes** |
| E2 governor DB | `%LOCALAPPDATA%\hermes\exec-brain\governor.db` | E2 telemetry, request records | **Yes** |
| E3 orchestration DB | `%LOCALAPPDATA%\hermes\exec-brain\orchestration.db` | DAG, router decisions, evidence | **Yes** |
| E1 chain head | `%LOCALAPPDATA%\hermes\exec-brain\chain-head.json` | hash-chain continuity | **Yes** (must travel with its DB) |
| E2 chain head | `%LOCALAPPDATA%\hermes\exec-brain\gov-chain-head.json` | telemetry chain continuity | **Yes** (with its DB) |
| E2 budget config | `%LOCALAPPDATA%\hermes\exec-brain\deepseek-config.json` | spending budget only — deliberately holds **no key** | Yes |
| Hermes session/state DB | `%LOCALAPPDATA%\hermes\state.db` | sessions, message history (~45 MB) | Yes — contains owner conversations, keep local, never publish |
| Hermes kanban DB | `%LOCALAPPDATA%\hermes\kanban.db` | work tracking | Yes |
| Hermes shared state | `%LOCALAPPDATA%\hermes\shared-state.db` | cross-session state | Yes |
| Cron executions DB | `%LOCALAPPDATA%\hermes\cron\executions.db` | cron run history | Yes |

Non-migrating (must stay local to the node that produced them, by policy):
`runtime/company-watch/`, `runtime/linkedin/`, `runtime/career-ops/cv-drafts/`,
`runtime/career-ops/application-status/`, `runtime/career-ops/daily-brief/`,
`DiscordArchive/` under the owner's profile, and `audits/evidence/**/backup*`.

Chain-head files are part of integrity verification: restoring a DB without its
chain head (or vice versa) is an inconsistent restore. Treat each pair as one unit.

---

## 4. Services / background jobs

See `06-service-definitions.md` for exact task definitions. Summary:

| Service | Kind | Trigger | Restart on failure |
|---|---|---|---|
| `Hermes_Gateway` | at-logon task → `wscript.exe //B Hermes_Gateway.vbs` | logon | **Yes** (1 min) |
| `HermesRemoteQueuePoller` | time task, repeat every 2 min | time | No |
| `ChiefDiscordSync` | time task, repeat every 30 min | time | No |
| `ChiefCareerBrief` | daily 07:00 calendar task | calendar | No |
| `ChiefCareerScan-UK` | daily 23:45 | calendar | No |
| `ChiefCareerScan-Dubai` | daily 23:50 | calendar | No |
| `ChiefCareerScan-Japan` | daily 23:55 | calendar | No |
| `ChiefCareerScan-Singapore` | daily 00:00 | calendar | No |
| `Mukund Chief of Staff` | **legacy, superseded** | logon | No — disposition pending owner decision |

All tasks run as `mukun` with logon mode `InteractiveToken` (`Interactive only`):
**they only run while Mukund is signed in.** That is a hard constraint on any
unattended deployment topology and is the reason the laptop cannot currently be
an unattended production node without either (a) the owner staying signed in, or
(b) an owner-approved change to a non-interactive service account.

---

## 5. Ports / network requirements

**Inbound: none required.** No Chief/Hermes component binds a listening socket;
`config.yaml` declares no `api_server` host/port, and nothing in this package
needs one. (Unrelated localhost listeners exist on the host; none is required by
the Chief runtime and none was changed.)

**Outbound TCP 443 (HTTPS) only**, to:

| Purpose | Endpoint |
|---|---|
| DeepSeek (E2/E3 workhorse) | `https://api.deepseek.com` |
| Google Gemini (image worker) | `https://generativelanguage.googleapis.com` |
| Mistral | `https://api.mistral.ai/v1` |
| GLM / Zhipu | `https://open.bigmodel.cn/api/paas/v4` |
| Qwen / Alibaba DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| LongCat via Nous inference | `https://inference-api.nousresearch.com/v1` |
| MiniMax | `https://api.minimax.io/v1` |
| StepFun | `https://api.stepfun.com/v1` |
| Tencent Hunyuan | `https://api.hunyuan.cloud.tencent.com/v1` |
| GitHub (control plane, queue) | `https://github.com`, `https://api.github.com` |
| Discord (gateway, sync) | Discord gateway/API over 443 |
| Gmail read-only monitor (owner-gated, not yet enabled) | `https://www.googleapis.com` |

Firewall rule to apply at deployment: **outbound 443 allow; inbound all deny**
(no port forward, no public listener). If a topology later needs an inbound
control surface, that is a new architecture decision with its own review.

---

## 6. Worker roster and readiness (E3)

Read from `worker_registry.py` + adapter config, credential presence re-probed
live (`scripts/e3_credential_presence_probe.py`, 2026-09-24):

| # | Worker id | Provider / model | Interface | Credential store (name only) | Present |
|---|---|---|---|---|---|
| 1 | `codex-cli` | openai / codex CLI | cli (subprocess) | ChatGPT CLI login (no API key) | yes (auth mode `chatgpt`) |
| 2 | `mistral-small-4` | mistral / mistral-small-4 | api | `MISTRAL_API_KEY`, CredMgr target `mistral` | **no** |
| 3 | `google-nano-banana-2` | google / gemini-3.1-flash-image | api | CredMgr target `gemini-api`; `GEMINI_API_KEY`/`GOOGLE_API_KEY`/`GOOGLE_GENERATIVE_AI_API_KEY` | yes |
| 4 | `deepseek-v41-flash` | deepseek / deepseek-flash | api | CredMgr target `deepseek`; `DEEPSEEK_API_KEY` | yes |
| 5 | `glm-53-flash` | glm / glm-5.3-flash | api | `GLM_API_KEY`, CredMgr target `glm` | **no** |
| 6 | `qwen38-27b` | qwen / qwen3.8-27b | api | `DASHSCOPE_API_KEY`, CredMgr target `qwen` | **no** |
| 7 | `longcat-2.0` | nous / longcat-2.0 | api | `NOUS_API_KEY`, CredMgr target `nous` | **no** |
| 8 | `minimax-m3` | minimax / minimax-m3 | api | `MINIMAX_API_KEY`, CredMgr target `minimax` | **no** |
| 9 | `step-37-flash` | step / step-3.7-flash | api | `STEP_API_KEY`, CredMgr target `stepfun` | **no** |
| 10 | `tencent-hunyuan-hy3` | tencent / hunyuan-hy3 | api | `HUNYUAN_API_KEY`, CredMgr target `hunyuan` | **no** |

Auth resolution order for every API worker:
**Windows Credential Manager (target name above) → the env var above → none.**
A worker is `routable` only with configured access + implemented adapter +
successful smoke test; qualification remains evidence-driven and is **not**
implied by credential presence.

---

## 7. Topology variants (both prepared; neither chosen)

### Variant A — laptop primary, GitHub control plane, VPS watchdog/failover
Owner's recorded *preference*, **not** a final decision.
- Laptop runs the gateway, E1–E5 runtime, poller, career/company services and
  holds the canonical databases.
- GitHub remains the control/collaboration plane (queue, issues, state).
- VPS holds only a watchdog/failover role: health observation, alerting, and a
  restore-capable copy of the deployment artifacts.
- Blocking constraints to record honestly: interactive-token tasks (laptop must
  stay signed in), laptop availability, and the **owner-attended security audit**
  (`overnight-owner-actions-2026-09-24.md` item 5) before the laptop is treated
  as a trusted production host.

### Variant B — VPS primary
- Requires: VPS OS/runtime discovery, credential provisioning on the VPS through
  its own secret store, a non-interactive service account (or an accepted
  interactive constraint), and full backup/restore + acceptance evidence on the
  VPS.
- Not started: no VPS login was performed (stop condition) and no host detail is
  recorded.

`PENDING OWNER DECISION` marks every step that differs between A and B:
the VPS host/account facts, which node owns the canonical databases, and the
cutover direction (A→B or B→A).

---

## 8. What must NOT be deployed or published

- No credential value, token, cookie, session DB or `auth.json` may be committed,
  copied into a runbook, or pasted into chat/GitHub/queue jobs.
- `state.db` and the other Hermes databases contain owner conversations:
  local-only, never published, never committed.
- No raw chain-of-thought or provider secrets in rationale/performance logs.
- The legacy `mukund-chief-of-staff` stack must not be started; the `Mukund Chief
  of Staff` task stays untouched until the owner decides its disposition.
